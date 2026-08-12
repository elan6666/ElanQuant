from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from elanquant.orchestration.jobs import JobStore, default_requested_session
from elanquant.orchestration.worker import Worker
from elanquant.settings import Settings
from elanquant.storage.database import Database


def test_default_request_key_changes_only_after_market_finalization() -> None:
    market = ZoneInfo("Asia/Shanghai")
    assert (
        default_requested_session(datetime(2026, 8, 13, 15, 0, tzinfo=market))
        == "2026-08-12"
    )
    assert (
        default_requested_session(datetime(2026, 8, 13, 16, 15, tzinfo=market))
        == "2026-08-13"
    )


def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "elanquant.sqlite3",
        artifact_root=tmp_path / "runs",
        frontend_dist=tmp_path / "missing-dist",
        poll_seconds=0.01,
    )


def test_claim_is_atomic_and_worker_publishes_terminal_run(tmp_path: Path) -> None:
    active = settings(tmp_path)
    database = Database(active.database_path)
    database.initialize()
    jobs = JobStore(database)
    submitted, _ = jobs.submit_update_infer("2026-08-12")

    worker = Worker(active)
    assert worker.run_once() is True
    assert worker.run_once() is False
    completed = jobs.get(str(submitted["id"]))
    assert completed["status"] == "SUCCEEDED"
    assert completed["run_id"]
    assert (active.artifact_root / str(completed["run_id"]) / "manifest.json").is_file()

    with database.connect() as connection:
        run_count = connection.execute("SELECT COUNT(*) AS n FROM inference_runs").fetchone()["n"]
        score_count = connection.execute("SELECT COUNT(*) AS n FROM stock_scores").fetchone()["n"]
    assert run_count == 1
    assert score_count == 15


def test_recovery_fails_abandoned_running_job_without_auto_resume(tmp_path: Path) -> None:
    active = settings(tmp_path)
    database = Database(active.database_path)
    database.initialize()
    jobs = JobStore(database)
    submitted, _ = jobs.submit_update_infer("2026-08-12")
    assert jobs.claim_next() is not None

    worker = Worker(active)
    assert worker.recover() == 1
    failed = jobs.get(str(submitted["id"]))
    assert failed["status"] == "FAILED"
    assert failed["error_code"] == "WORKER_INTERRUPTED"
