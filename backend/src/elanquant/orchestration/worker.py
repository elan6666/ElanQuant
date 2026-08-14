from __future__ import annotations

import argparse
import logging
import threading
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from elanquant.execution import (
    CapabilityUnavailableError,
    SystemCapabilities,
    build_execution_receipt,
    load_execution_profile,
    probe_system_capabilities,
    require_capability,
    restricted_process_environment,
    runtime_values,
    sanitized_subprocess_environment,
)
from elanquant.orchestration.jobs import JobStore
from elanquant.pipelines.placeholder import run_placeholder_pipeline
from elanquant.pipelines.real import DataIncompleteError, run_real_pipeline
from elanquant.settings import Settings
from elanquant.storage.database import Database

LOGGER = logging.getLogger("elanquant.worker")


class Worker:
    def __init__(
        self,
        settings: Settings,
        capability_probe: Callable[[str], SystemCapabilities] = probe_system_capabilities,
    ):
        self.settings = settings
        self.capability_probe = capability_probe
        self.database = Database(settings.database_path)
        self.database.initialize()
        self.jobs = JobStore(self.database)

    def recover(self) -> int:
        return self.jobs.fail_interrupted()

    def heartbeat(self, state: str = "IDLE", detail: str = "") -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO service_heartbeats(service, heartbeat_at, state, detail)
                VALUES ('worker', ?, ?, ?)
                ON CONFLICT(service) DO UPDATE SET heartbeat_at=excluded.heartbeat_at,
                    state=excluded.state, detail=excluded.detail
                """,
                (datetime.now(UTC).isoformat(), state, detail[:200]),
            )

    def run_once(self) -> bool:
        self.heartbeat()
        queued = self.jobs.peek_next()
        if queued is None:
            return False
        queued_id = str(queued["id"])
        if self.settings.pipeline_mode == "real":
            if queued["execution_profile"] != self.settings.execution_profile:
                self.jobs.fail(
                    queued_id,
                    "EXECUTION_PROFILE_MISMATCH",
                    "Queued job execution profile differs from this worker deployment",
                )
                return True
            try:
                profile = load_execution_profile(
                    str(queued["execution_profile"]), self.settings.execution_profiles_root
                )
                receipt = build_execution_receipt(
                    profile,
                    str(queued["model_release"]),
                    str(queued["requested_device"]),
                    self.capability_probe(str(queued["requested_device"])),
                    inference_batch_size=self.settings.inference_batch_size,
                )
                self.jobs.record_execution_receipt(queued_id, receipt)
                require_capability(receipt)
                if profile.is_research_only(str(queued["model_release"])):
                    self.jobs.fail(
                        queued_id,
                        "MODEL_RELEASE_RESEARCH_ONLY",
                        "This model release is admitted for research smoke only and cannot publish",
                    )
                    return True
            except CapabilityUnavailableError as error:
                LOGGER.warning("Job %s stopped at capability gate: %s", queued_id, error)
                self.jobs.fail(queued_id, "CAPABILITY_UNAVAILABLE", str(error))
                return True
            except (OSError, TypeError, ValueError) as error:
                LOGGER.warning("Job %s has an invalid execution profile: %s", queued_id, error)
                self.jobs.fail(queued_id, "EXECUTION_PROFILE_INVALID", str(error))
                return True
        job = self.jobs.claim_next(queued_id)
        if job is None:
            return False
        job_id = str(job["id"])
        self.heartbeat("RUNNING", job_id)
        heartbeat_stop = threading.Event()

        def keep_heartbeat() -> None:
            while not heartbeat_stop.wait(5):
                self.heartbeat("RUNNING", job_id)

        heartbeat_thread = threading.Thread(
            target=keep_heartbeat, name=f"heartbeat-{job_id}", daemon=True
        )
        heartbeat_thread.start()

        def advance(stage: str, progress: float, message: str, resolved: str | None) -> None:
            self.jobs.advance(job_id, stage, progress, message, resolved_session=resolved)
            self.heartbeat("RUNNING", f"{job_id}:{stage}")

        try:
            pipeline = (
                run_real_pipeline
                if self.settings.pipeline_mode == "real"
                else run_placeholder_pipeline
            )
            if self.settings.pipeline_mode == "real":
                environment = sanitized_subprocess_environment(
                    runtime_values=runtime_values(
                        str(job["execution_profile"]),
                        str(job["model_release"]),
                        str(job["requested_device"]),
                        self.settings.inference_batch_size,
                    )
                )
                with restricted_process_environment(environment):
                    run_id = pipeline(self.database, self.settings, job, advance)
            else:
                run_id = pipeline(self.database, self.settings, job, advance)
            if self.jobs.get(job_id)["status"] == "RUNNING":
                self.jobs.succeed(job_id, run_id)
        except DataIncompleteError as error:
            LOGGER.warning("Job %s stopped at data gate: %s", job_id, error)
            self.jobs.data_incomplete(job_id, str(error))
        except Exception as error:
            LOGGER.exception("Job %s failed", job_id)
            self.jobs.fail(job_id, type(error).__name__.upper(), str(error) or repr(error))
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=2)
        self.heartbeat()
        return True

    def run_forever(self) -> None:
        interrupted = self.recover()
        if interrupted:
            LOGGER.warning("Marked %d interrupted jobs failed", interrupted)
        while True:
            if not self.run_once():
                time.sleep(self.settings.poll_seconds)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the durable ElanQuant worker")
    parser.add_argument("--once", action="store_true", help="Process at most one queued job")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    worker = Worker(Settings.load())
    if args.once:
        worker.recover()
        worker.run_once()
    else:
        worker.run_forever()


if __name__ == "__main__":
    main()
