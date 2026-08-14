from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from elanquant.contracts.portable_runtime import (
    DEVICES,
    PROFILE_IDS,
    RELEASES,
    validate_execution_receipt,
)
from elanquant.storage.database import Database

TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "DATA_INCOMPLETE"}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def default_requested_session(now: datetime | None = None) -> str:
    market_now = now or datetime.now(ZoneInfo("Asia/Shanghai"))
    if market_now.tzinfo is None or market_now.utcoffset() is None:
        raise ValueError("market clock must be timezone-aware")
    session = market_now.date()
    if market_now.time() < time(16, 15):
        session -= timedelta(days=1)
    return session.isoformat()


class JobStore:
    def __init__(self, database: Database):
        self.database = database

    def submit_update_infer(
        self,
        target_session: date | str | None = None,
        *,
        force: bool = False,
        execution_profile: str = "legacy-yilangliu",
        model_release: str = "small",
        requested_device: str = "cuda",
    ) -> tuple[dict[str, object], bool]:
        if execution_profile not in PROFILE_IDS:
            raise ValueError("Unknown execution profile")
        if model_release not in RELEASES:
            raise ValueError("Unknown model release")
        if requested_device not in DEVICES:
            raise ValueError("Unknown execution device")
        session = str(target_session) if target_session is not None else default_requested_session()
        base_key = (
            f"UPDATE_INFER:{session}:{execution_profile}:{model_release}:{requested_device}"
        )
        now = utc_now()
        job_id = str(uuid.uuid4())
        idempotency_key = f"{base_key}:force:{job_id}" if force else base_key
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    INSERT INTO jobs (
                        id, idempotency_key, job_type, requested_session, status,
                        stage, progress, message, created_at, execution_profile,
                        model_release, requested_device
                    ) VALUES (?, ?, 'UPDATE_INFER', ?, 'QUEUED', 'QUEUED', 0, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        idempotency_key,
                        session,
                        "Job accepted",
                        now,
                        execution_profile,
                        model_release,
                        requested_device,
                    ),
                )
                self._insert_event(connection, job_id, "QUEUED", "QUEUED", 0, "Job accepted", now)
                connection.commit()
                return self.get(job_id), True
            except sqlite3.IntegrityError:
                connection.rollback()
                row = connection.execute(
                    "SELECT * FROM jobs WHERE idempotency_key = ?", (idempotency_key,)
                ).fetchone()
                if row is None:
                    raise
                return self._job_dict(connection, row), False

    def list(self, limit: int = 50) -> list[dict[str, object]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 200)),)
            ).fetchall()
            return [self._job_dict(connection, row, include_events=True) for row in rows]

    def get(self, job_id: str) -> dict[str, object]:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            return self._job_dict(connection, row)

    def retry(self, job_id: str) -> dict[str, object]:
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            parent = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if parent is None:
                connection.rollback()
                raise KeyError(job_id)
            if parent["status"] not in {"FAILED", "DATA_INCOMPLETE"}:
                connection.rollback()
                raise ValueError("Only failed jobs may be retried")
            attempt = int(parent["attempt"]) + 1
            new_id = str(uuid.uuid4())
            now = utc_now()
            connection.execute(
                """
                INSERT INTO jobs (
                    id, idempotency_key, job_type, requested_session, status, stage,
                    progress, message, attempt, parent_job_id, created_at,
                    execution_profile, model_release, requested_device
                ) VALUES (?, ?, ?, ?, 'QUEUED', 'QUEUED', 0, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id,
                    f"{parent['idempotency_key']}:retry:{attempt}:{new_id}",
                    parent["job_type"],
                    parent["requested_session"],
                    "Retry accepted",
                    attempt,
                    job_id,
                    now,
                    parent["execution_profile"],
                    parent["model_release"],
                    parent["requested_device"],
                ),
            )
            self._insert_event(connection, new_id, "QUEUED", "QUEUED", 0, "Retry accepted", now)
            connection.commit()
        return self.get(new_id)

    def peek_next(self) -> dict[str, object] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE status = 'QUEUED' ORDER BY created_at, id LIMIT 1"
            ).fetchone()
            return None if row is None else self._job_dict(connection, row)

    def record_execution_receipt(self, job_id: str, receipt: dict[str, object]) -> None:
        validated = validate_execution_receipt(receipt)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                connection.rollback()
                raise KeyError(job_id)
            if row["status"] != "QUEUED":
                connection.rollback()
                raise ValueError("Execution capability may only be recorded before claim")
            if (
                validated["profile_id"] != row["execution_profile"]
                or validated["model_release"] != row["model_release"]
                or validated["requested_device"] != row["requested_device"]
            ):
                connection.rollback()
                raise ValueError("Execution receipt disagrees with frozen job identity")
            connection.execute(
                "UPDATE jobs SET execution_receipt_json = ? WHERE id = ? AND status = 'QUEUED'",
                (
                    json.dumps(
                        validated, ensure_ascii=False, separators=(",", ":"), sort_keys=True
                    ),
                    job_id,
                ),
            )
            connection.commit()

    def claim_next(self, job_id: str | None = None) -> dict[str, object] | None:
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if job_id is None:
                row = connection.execute(
                    "SELECT * FROM jobs WHERE status = 'QUEUED' ORDER BY created_at, id LIMIT 1"
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM jobs WHERE id = ? AND status = 'QUEUED'", (job_id,)
                ).fetchone()
            if row is None:
                connection.commit()
                return None
            now = utc_now()
            changed = connection.execute(
                """
                UPDATE jobs SET status = 'RUNNING', stage = 'RESOLVING_SESSION',
                    progress = 0.05, message = 'Resolving requested session',
                    started_at = ?, heartbeat_at = ?
                WHERE id = ? AND status = 'QUEUED'
                """,
                (now, now, row["id"]),
            ).rowcount
            if changed != 1:
                connection.rollback()
                return None
            self._insert_event(
                connection,
                row["id"],
                "RUNNING",
                "RESOLVING_SESSION",
                0.05,
                "Resolving requested session",
                now,
            )
            connection.commit()
        return self.get(str(row["id"]))

    def advance(
        self,
        job_id: str,
        stage: str,
        progress: float,
        message: str,
        *,
        resolved_session: str | None = None,
    ) -> None:
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                connection.rollback()
                raise KeyError(job_id)
            if row["status"] != "RUNNING":
                connection.rollback()
                raise ValueError("Only running jobs may advance")
            connection.execute(
                """
                UPDATE jobs SET stage = ?, progress = ?, message = ?, heartbeat_at = ?,
                    resolved_session = COALESCE(?, resolved_session)
                WHERE id = ?
                """,
                (stage, progress, message, now, resolved_session, job_id),
            )
            self._insert_event(connection, job_id, "RUNNING", stage, progress, message, now)
            connection.commit()

    def succeed(self, job_id: str, run_id: str) -> None:
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE jobs SET status = 'SUCCEEDED', stage = 'SUCCEEDED', progress = 1,
                    message = 'Run completed', heartbeat_at = ?, finished_at = ?, run_id = ?
                WHERE id = ? AND status = 'RUNNING'
                """,
                (now, now, run_id, job_id),
            )
            self._insert_event(
                connection, job_id, "SUCCEEDED", "SUCCEEDED", 1, "Run completed", now
            )
            connection.commit()

    def fail(self, job_id: str, code: str, summary: str) -> None:
        now = utc_now()
        safe_summary = summary[:500]
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE jobs SET status = 'FAILED', stage = 'FAILED', message = ?,
                    heartbeat_at = ?, finished_at = ?, error_code = ?, error_summary = ?
                WHERE id = ? AND status IN ('QUEUED', 'RUNNING')
                """,
                (safe_summary, now, now, code, safe_summary, job_id),
            )
            connection.execute(
                """
                UPDATE inference_runs SET status = 'FAILED', finished_at = ?
                WHERE job_id = ? AND status = 'RUNNING'
                """,
                (now, job_id),
            )
            self._insert_event(connection, job_id, "FAILED", "FAILED", 1, safe_summary, now)
            connection.commit()

    def data_incomplete(self, job_id: str, summary: str) -> None:
        now = utc_now()
        safe_summary = summary[:500]
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE jobs SET status = 'DATA_INCOMPLETE', stage = 'DATA_INCOMPLETE',
                    message = ?, heartbeat_at = ?, finished_at = ?,
                    error_code = 'DATA_INCOMPLETE', error_summary = ?
                WHERE id = ? AND status IN ('QUEUED', 'RUNNING')
                """,
                (safe_summary, now, now, safe_summary, job_id),
            )
            self._insert_event(
                connection,
                job_id,
                "DATA_INCOMPLETE",
                "DATA_INCOMPLETE",
                1,
                safe_summary,
                now,
            )
            connection.commit()

    def fail_interrupted(self) -> int:
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute("SELECT id FROM jobs WHERE status = 'RUNNING'").fetchall()
            for row in rows:
                connection.execute(
                    """
                    UPDATE jobs SET status = 'FAILED', stage = 'FAILED', finished_at = ?,
                        error_code = 'WORKER_INTERRUPTED',
                        error_summary = 'Worker restarted before the job completed',
                        message = 'Worker restarted before the job completed'
                    WHERE id = ?
                    """,
                    (now, row["id"]),
                )
                connection.execute(
                    """
                    UPDATE inference_runs SET status = 'FAILED', finished_at = ?
                    WHERE job_id = ? AND status = 'RUNNING'
                    """,
                    (now, row["id"]),
                )
                self._insert_event(
                    connection,
                    row["id"],
                    "FAILED",
                    "FAILED",
                    1,
                    "Worker restarted before the job completed",
                    now,
                )
            connection.commit()
            return len(rows)

    @staticmethod
    def _insert_event(
        connection: sqlite3.Connection,
        job_id: str,
        status: str,
        stage: str,
        progress: float,
        message: str,
        created_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO job_events(job_id, created_at, status, stage, progress, message)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (job_id, created_at, status, stage, progress, message),
        )

    @staticmethod
    def _job_dict(
        connection: sqlite3.Connection, row: sqlite3.Row, *, include_events: bool = True
    ) -> dict[str, object]:
        result = dict(row)
        receipt_json = result.pop("execution_receipt_json", None)
        result["execution_receipt"] = (
            None if receipt_json is None else validate_execution_receipt(json.loads(receipt_json))
        )
        if include_events:
            result["events"] = [
                {**dict(event), "id": str(event["id"])}
                for event in connection.execute(
                    """
                    SELECT id, created_at, status, stage, progress, message
                    FROM job_events WHERE job_id = ? ORDER BY id
                    """,
                    (row["id"],),
                ).fetchall()
            ]
        return result
