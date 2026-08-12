from __future__ import annotations

import argparse
import logging
import threading
import time
from collections.abc import Sequence
from datetime import UTC, datetime

from elanquant.orchestration.jobs import JobStore
from elanquant.pipelines.placeholder import run_placeholder_pipeline
from elanquant.pipelines.real import DataIncompleteError, run_real_pipeline
from elanquant.settings import Settings
from elanquant.storage.database import Database

LOGGER = logging.getLogger("elanquant.worker")


class Worker:
    def __init__(self, settings: Settings):
        self.settings = settings
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
        job = self.jobs.claim_next()
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
