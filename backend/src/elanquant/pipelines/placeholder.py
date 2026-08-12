from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from elanquant.pipelines.paper import (
    Recommendation,
    create_frozen_intents,
    ensure_account,
    settle_due_orders,
    write_portfolio_snapshot,
)
from elanquant.settings import Settings
from elanquant.storage.database import Database

StageCallback = Callable[[str, float, str, str | None], None]

MODELS = (
    ("small-zero-shot", "small", "zero_shot", "OFFICIAL_REPRODUCTION"),
    ("small-official-ft", "small", "official_ft", "OFFICIAL_REPRODUCTION"),
    ("small-strict-pit", "small", "strict_pit_ft", "STRICT_PIT"),
)

STOCKS = (
    ("000001.SZ", "平安银行"),
    ("000333.SZ", "美的集团"),
    ("300750.SZ", "宁德时代"),
    ("600036.SH", "招商银行"),
    ("600519.SH", "贵州茅台"),
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def deterministic_number(key: str, low: float, high: float) -> float:
    raw = int(hashlib.sha256(key.encode()).hexdigest()[:12], 16) / float(0xFFFFFFFFFFFF)
    return low + raw * (high - low)


def run_placeholder_pipeline(
    database: Database,
    settings: Settings,
    job: dict[str, object],
    advance: StageCallback,
) -> str:
    job_id = str(job["id"])
    as_of = str(job["requested_session"])
    advance("UPDATING_DATA", 0.15, "Materializing deterministic placeholder snapshot", as_of)
    snapshot_payload = {
        "as_of_session": as_of,
        "source": "PLACEHOLDER_DETERMINISTIC_NOT_MARKET_DATA",
        "stocks": [code for code, _ in STOCKS],
    }
    snapshot_bytes = json.dumps(snapshot_payload, sort_keys=True).encode()
    snapshot_hash = hashlib.sha256(snapshot_bytes).hexdigest()
    snapshot_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"elanquant:snapshot:{as_of}:{snapshot_hash}"))
    run_id = str(uuid.uuid4())
    artifact_path = settings.artifact_root / run_id / "manifest.json"
    now = utc_now()
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            INSERT OR IGNORE INTO data_snapshots(
                id, as_of_session, source, status, row_count, manifest_sha256, created_at
            ) VALUES (?, ?, ?, 'PLACEHOLDER_COMPLETE', ?, ?, ?)
            """,
            (snapshot_id, as_of, snapshot_payload["source"], len(STOCKS), snapshot_hash, now),
        )
        for model_id, size, variant, protocol in MODELS:
            connection.execute(
                """
                INSERT OR IGNORE INTO model_versions(
                    id, size, variant, protocol, status, checkpoint_sha256
                ) VALUES (?, ?, ?, ?, 'PLACEHOLDER_ONLY', 'NOT_A_REAL_CHECKPOINT')
                """,
                (model_id, size, variant, protocol),
            )
        connection.execute(
            """
            INSERT INTO inference_runs(
                id, job_id, snapshot_id, as_of_session, status, protocol,
                artifact_path, artifact_sha256, created_at
            ) VALUES (?, ?, ?, ?, 'RUNNING', 'PLACEHOLDER_DETERMINISTIC', ?, 'PENDING', ?)
            """,
            (run_id, job_id, snapshot_id, as_of, str(artifact_path), now),
        )
        for model_id, *_ in MODELS:
            connection.execute(
                """
                INSERT INTO inference_run_models(run_id, model_version_id, base_model_id)
                VALUES (?, ?, ?)
                """,
                (run_id, model_id, model_id),
            )
        connection.commit()

    advance("VALIDATING_DATA", 0.25, "Placeholder snapshot contract validated", as_of)
    model_rows: dict[str, list[Recommendation]] = {}
    for index, (model_id, _size, _variant, _protocol) in enumerate(MODELS):
        stage = "INFER_SMALL"
        advance(stage, 0.3 + 0.07 * index, f"Scoring {model_id}", as_of)
        scored: list[Recommendation] = []
        for code, name in STOCKS:
            scored.append(
                Recommendation(
                    code=code,
                    name=name,
                    score=deterministic_number(f"{as_of}:{model_id}:{code}:score", -0.08, 0.12),
                    reference_price=deterministic_number(f"{as_of}:{code}:close", 8.0, 180.0),
                    rank=0,
                )
            )
        scored.sort(key=lambda item: (-float(item["score"]), str(item["code"])))
        for rank, item in enumerate(scored, start=1):
            item["rank"] = rank
        model_rows[model_id] = scored

    advance("SCORING", 0.75, "Building strict-PIT Small placeholder ranking", as_of)
    recommendations: list[Recommendation] = []
    for code, name in STOCKS:
        small = next(item for item in model_rows["small-strict-pit"] if item["code"] == code)
        recommendations.append(
            Recommendation(
                code=code,
                name=name,
                score=small["score"],
                reference_price=small["reference_price"],
                rank=0,
            )
        )
    recommendations.sort(key=lambda item: (-float(item["score"]), str(item["code"])))
    for rank, item in enumerate(recommendations, start=1):
        item["rank"] = rank

    recommendation_id = str(uuid.uuid4())
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        for model_id, rows in model_rows.items():
            for item in rows:
                connection.execute(
                    """
                    INSERT INTO stock_scores(
                        run_id, model_version_id, code, name, score, rank,
                        reference_price, scoreability
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PLACEHOLDER_NOT_SCOREABLE')
                    """,
                    (
                        run_id,
                        model_id,
                        item["code"],
                        item["name"],
                        item["score"],
                        item["rank"],
                        item["reference_price"],
                    ),
                )
        connection.execute(
            """
            INSERT INTO recommendation_sets(
                id, run_id, signal_session, execution_policy, created_at
            )
            VALUES (?, ?, ?, 'NEXT_SESSION_OPEN_FROZEN_T_INTENT', ?)
            """,
            (recommendation_id, run_id, as_of, utc_now()),
        )
        for item in recommendations[: settings.top_k]:
            connection.execute(
                """
                INSERT INTO recommendation_items(
                    recommendation_set_id, code, name, rank, score,
                    target_weight, frozen_price
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    recommendation_id,
                    item["code"],
                    item["name"],
                    item["rank"],
                    item["score"],
                    1 / settings.top_k,
                    item["reference_price"],
                ),
            )
        connection.commit()

    advance("PAPER_LEDGER", 0.88, "Applying due fills and freezing next-session intents", as_of)
    prices = {code: deterministic_number(f"{as_of}:{code}:open", 8.0, 180.0) for code, _ in STOCKS}

    manifest = {
        "schema_version": "elanquant_placeholder_v1",
        "run_id": run_id,
        "job_id": job_id,
        "as_of_session": as_of,
        "snapshot_sha256": snapshot_hash,
        "models": [model_id for model_id, *_ in MODELS],
        "warning": "Deterministic placeholder output; not market data or investment advice.",
    }
    manifest_bytes = json.dumps(manifest, sort_keys=True, indent=2).encode()
    artifact_hash = hashlib.sha256(manifest_bytes).hexdigest()
    _atomic_write(artifact_path, manifest_bytes)
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        ensure_account(connection, settings.initial_cash)
        settle_due_orders(connection, as_of, prices)
        paper_publication = create_frozen_intents(
            connection, run_id, as_of, recommendations, settings.top_k
        )
        connection.execute(
            """
            UPDATE inference_runs
            SET paper_publication_state = ?, paper_publication_run_id = ?
            WHERE id = ?
            """,
            (
                paper_publication["state"],
                paper_publication["source_run_id"],
                run_id,
            ),
        )
        write_portfolio_snapshot(connection, as_of, prices)
        finished = utc_now()
        connection.execute(
            """
            UPDATE inference_runs SET status = 'SUCCEEDED', artifact_sha256 = ?, finished_at = ?
            WHERE id = ? AND status = 'RUNNING'
            """,
            (artifact_hash, finished, run_id),
        )
        completed_message = (
            "Run completed; paper intents were already frozen by "
            f"{paper_publication['source_run_id']}"
            if paper_publication["state"] == "SKIPPED_EXISTING_FROZEN_RUN"
            else "Run completed"
        )
        changed = connection.execute(
            """
            UPDATE jobs SET status = 'SUCCEEDED', stage = 'SUCCEEDED', progress = 1,
                message = ?, heartbeat_at = ?, finished_at = ?, run_id = ?
            WHERE id = ? AND status = 'RUNNING'
            """,
            (completed_message, finished, finished, run_id, job_id),
        ).rowcount
        if changed != 1:
            raise RuntimeError("job terminal state changed before atomic placeholder publication")
        connection.execute(
            """
            INSERT INTO job_events(job_id, created_at, status, stage, progress, message)
            VALUES (?, ?, 'SUCCEEDED', 'SUCCEEDED', 1, ?)
            """,
            (job_id, finished, completed_message),
        )
        connection.commit()
    return run_id


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
