from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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


class DataIncompleteError(RuntimeError):
    """Raised when a provider snapshot fails a typed data admission gate."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record_manual_gaps(
    connection: Any, current_session: str, calendar_path: Path, now: str
) -> None:
    previous = connection.execute(
        """
        SELECT signal_session FROM recommendation_sets
        WHERE signal_session < ? ORDER BY signal_session DESC LIMIT 1
        """,
        (current_session,),
    ).fetchone()
    if previous is None:
        return
    with calendar_path.open(newline="", encoding="utf-8") as handle:
        open_days = [
            str(row["cal_date"])
            for row in csv.DictReader(handle)
            if int(row["is_open"]) == 1
        ]
    previous_compact = str(previous["signal_session"]).replace("-", "")
    current_compact = current_session.replace("-", "")
    skipped = sorted(day for day in open_days if previous_compact < day < current_compact)
    for day in skipped:
        session = f"{day[:4]}-{day[4:6]}-{day[6:]}"
        connection.execute(
            """
            INSERT OR IGNORE INTO paper_gaps(account_id, session, reason, recorded_at)
            VALUES ('paper-default', ?, 'MANUAL_RUN_NOT_REQUESTED', ?)
            """,
            (session, now),
        )


def _run(command: list[str], settings: Settings) -> dict[str, Any]:
    environment = os.environ.copy()
    prior = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        str(settings.research_deps) if not prior else f"{settings.research_deps}:{prior}"
    )
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=6 * 60 * 60,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "research command failed")[-1000:]
        if "DATA_INCOMPLETE" in detail or "complete online windows" in detail:
            raise DataIncompleteError(detail)
        raise RuntimeError(detail)
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("research command returned no receipt")
    payload = json.loads(lines[-1])
    if not isinstance(payload, dict):
        raise RuntimeError("research receipt is not an object")
    return payload


def run_real_pipeline(
    database: Database,
    settings: Settings,
    job: dict[str, object],
    advance: StageCallback,
) -> str:
    requested = str(job["requested_session"])
    root = Path(__file__).resolve().parents[4]
    server_scripts = root / "scripts/server"
    online_root = settings.artifact_root.parent / "online-snapshots"
    advance("UPDATING_DATA", 0.12, "Fetching immutable CSI300 online snapshot", None)
    fetch = _run(
        [
            str(settings.research_python),
            str(server_scripts / "fetch_online_snapshot.py"),
            "--proxy-client",
            str(settings.proxy_client),
            "--out-root",
            str(online_root),
            "--target-session",
            requested,
        ],
        settings,
    )
    snapshot_path = Path(str(fetch["snapshot"]))
    snapshot_manifest_path = snapshot_path / "manifest.json"
    snapshot_manifest = json.loads(snapshot_manifest_path.read_text(encoding="utf-8"))
    if snapshot_manifest.get("status") != "PASS":
        raise RuntimeError("online snapshot failed its terminal data gate")
    resolved = str(snapshot_manifest["resolved_session"])
    snapshot_hash = sha256(snapshot_manifest_path)
    evaluation_path = settings.evaluation_receipt
    if not settings.matrix_receipt.is_file() or not evaluation_path.is_file():
        raise RuntimeError("sealed matrix/evaluation release is missing")
    matrix_sha = sha256(settings.matrix_receipt)
    evaluation_sha = sha256(evaluation_path)
    evaluation_result = json.loads(evaluation_path.read_text(encoding="utf-8"))
    expected_models = {"small-zero-shot", "small-official-ft", "small-strict-pit"}
    evaluation_models = evaluation_result.get("models")
    if (
        evaluation_result.get("status") != "PASS"
        or evaluation_result.get("evaluation_mode") != "FORMAL"
        or not isinstance(evaluation_models, dict)
        or set(evaluation_models) != expected_models
        or evaluation_result.get("training_matrix_receipt_sha256") != matrix_sha
    ):
        raise RuntimeError("formal Small evaluation receipt is incomplete or mismatched")
    for model_id in expected_models:
        metrics = evaluation_models[model_id].get("metrics")
        validation = metrics.get("validation_2025") if isinstance(metrics, dict) else None
        if not isinstance(validation, dict) or not all(
            isinstance(validation.get(key), (int, float))
            for key in ("rank_ic", "ic", "top10_mean_return")
        ):
            raise RuntimeError(f"formal validation metrics are incomplete: {model_id}")
    advance(
        "VALIDATING_DATA", 0.25, "Online snapshot passed coverage and continuity gates", resolved
    )
    run_id = str(uuid.uuid4())
    artifact_path = settings.artifact_root / run_id / "inference.json"
    advance("INFER_SMALL", 0.38, "Running pinned Small cells", resolved)
    inference_receipt = _run(
        [
            str(settings.research_python),
            str(server_scripts / "evaluate_and_infer.py"),
            "--root",
            str(settings.artifact_root.parents[1]),
            "--upstream",
            str(settings.upstream_root),
            "--matrix-receipt",
            str(settings.matrix_receipt),
            "--online-root",
            str(snapshot_path),
            "--skip-evaluation",
            "--out",
            str(artifact_path),
        ],
        settings,
    )
    if inference_receipt.get("status") != "PASS":
        raise RuntimeError("Kronos inference receipt is not PASS")
    result = json.loads(artifact_path.read_text(encoding="utf-8"))
    scores = result.get("scores")
    models = result.get("models")
    if (
        not isinstance(scores, list)
        or not isinstance(models, dict)
        or set(models) != expected_models
        or len(scores) < 250
    ):
        raise RuntimeError("Kronos output does not meet the complete ranking contract")
    if (
        sha256(settings.matrix_receipt) != matrix_sha
        or sha256(evaluation_path) != evaluation_sha
        or result.get("training_matrix_receipt_sha256") != matrix_sha
        or result.get("data_manifest_sha256") != snapshot_hash
    ):
        raise RuntimeError("inference provenance changed or disagrees during publication")
    if any(
        not isinstance(item.get("model_scores"), dict)
        or set(item["model_scores"]) != expected_models
        for item in scores
    ):
        raise RuntimeError("ranking rows do not contain the exact Small model set")
    advance("SCORING", 0.74, "Publishing strict-PIT Small ranking", resolved)
    snapshot_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"elanquant:{resolved}:{snapshot_hash}"))
    recommendations: list[Recommendation] = [
        Recommendation(
            code=str(item["code"]),
            name=str(item["name"]),
            score=float(item["score"]),
            reference_price=float(item["reference_price"]),
            rank=int(item["rank"]),
        )
        for item in scores
    ]
    now = utc_now()
    execution = json.loads((snapshot_path / "execution.json").read_text(encoding="utf-8"))
    prices = {code: float(values["open"]) for code, values in execution.items()}
    closes = {code: float(values["close"]) for code, values in execution.items()}
    forecast_sessions = result.get("forecast_sessions")
    if not isinstance(forecast_sessions, list) or not forecast_sessions:
        raise RuntimeError("inference artifact lacks the next real trading session")
    advance(
        "PAPER_LEDGER",
        0.88,
        "Settling due intents and freezing next-session paper orders",
        resolved,
    )
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            INSERT OR IGNORE INTO data_snapshots(
                id, as_of_session, source, status, row_count, manifest_sha256, created_at
            ) VALUES (?, ?, 'TUSHARE_PROXY_IMMUTABLE_ONLINE', 'PASS', ?, ?, ?)
            """,
            (snapshot_id, resolved, len(scores), snapshot_hash, now),
        )
        version_ids: dict[str, str] = {}
        for model_id, model in models.items():
            size = str(model["size"])
            variant_base = {
                "zero_shot": "zero_shot",
                "official_style": "official_ft",
                "strict_pit": "strict_pit_ft",
            }[str(model["track"])]
            predictor_sha = str(model["predictor_sha256"])
            version_id = f"{model_id}@{predictor_sha[:12]}"
            version_ids[model_id] = version_id
            variant = f"{variant_base}@{predictor_sha[:12]}"
            evaluated = evaluation_models.get(model_id, {})
            evaluated_metrics = evaluated.get("metrics", {}) if isinstance(evaluated, dict) else {}
            validation = evaluated_metrics.get("validation_2025", {})
            viewed = evaluated_metrics.get("test_viewed_2026", {})
            connection.execute(
                """
                INSERT INTO model_versions(
                    id, base_model_id, size, variant, protocol, status, checkpoint_sha256,
                    tokenizer_sha256, config_sha256, code_sha256,
                    validation_rank_ic, validation_ic, validation_top10_mean_return,
                    viewed_test_rank_ic, evaluation_receipt,
                    evaluation_receipt_sha256
                ) VALUES (?, ?, ?, ?, ?, 'PASS', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (
                    version_id,
                    model_id,
                    size,
                    variant,
                    str(model["track"]),
                    predictor_sha,
                    str(model["tokenizer_sha256"]),
                    str(model.get("config_sha256", "")),
                    str(result["inference_code_sha256"]),
                    validation.get("rank_ic") if isinstance(validation, dict) else None,
                    validation.get("ic") if isinstance(validation, dict) else None,
                    (
                        validation.get("top10_mean_return")
                        if isinstance(validation, dict)
                        else None
                    ),
                    viewed.get("rank_ic") if isinstance(viewed, dict) else None,
                    str(evaluation_path) if evaluation_models else None,
                    sha256(evaluation_path),
                ),
            )
        connection.execute(
            """
            INSERT INTO inference_runs(
                id, job_id, snapshot_id, as_of_session, status, protocol,
                artifact_path, artifact_sha256, scoreable, matrix_receipt_sha256,
                config_sha256, code_sha256, created_at, finished_at
            ) VALUES (?, ?, ?, ?, 'SUCCEEDED', 'STRICT_PIT_SMALL',
                ?, ?, 0, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                str(job["id"]),
                snapshot_id,
                resolved,
                str(artifact_path),
                sha256(artifact_path),
                matrix_sha,
                str(result.get("config_sha256", "")),
                str(result["inference_code_sha256"]),
                now,
                now,
            ),
        )
        for base_model_id, version_id in version_ids.items():
            connection.execute(
                """
                INSERT INTO inference_run_models(run_id, model_version_id, base_model_id)
                VALUES (?, ?, ?)
                """,
                (run_id, version_id, base_model_id),
            )
        for model_id in models:
            ordered = sorted(
                scores, key=lambda item: (-float(item["model_scores"][model_id]), str(item["code"]))
            )
            for rank, item in enumerate(ordered, start=1):
                connection.execute(
                    """
                    INSERT INTO stock_scores(
                        run_id, model_version_id, code, name, score, rank,
                        reference_price, scoreability
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'ONLINE_UNMATURED')
                    """,
                    (
                        run_id,
                        version_ids[model_id],
                        item["code"],
                        item["name"],
                        item["model_scores"][model_id],
                        rank,
                        item["reference_price"],
                    ),
                )
        recommendation_id = str(uuid.uuid4())
        connection.execute(
            """
            INSERT INTO recommendation_sets(
                id, run_id, signal_session, execution_policy, created_at
            ) VALUES (?, ?, ?, 'T_CLOSE_FROZEN_NEXT_REAL_SESSION_NO_REPLACEMENT', ?)
            """,
            (recommendation_id, run_id, resolved, now),
        )
        for item in recommendations[: settings.top_k]:
            connection.execute(
                """
                INSERT INTO recommendation_items(
                    recommendation_set_id, code, name, rank, score, target_weight, frozen_price
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
        ensure_account(connection, settings.initial_cash)
        record_manual_gaps(connection, resolved, snapshot_path / "trade_cal.csv", now)
        settle_due_orders(connection, resolved, prices, execution)
        create_frozen_intents(
            connection,
            run_id,
            resolved,
            recommendations,
            settings.top_k,
            due_session=str(forecast_sessions[0]),
        )
        write_portfolio_snapshot(
            connection, resolved, closes, valuation_policy="REAL_CLOSE_OR_BOOK_COST"
        )
        changed = connection.execute(
            """
            UPDATE jobs SET status = 'SUCCEEDED', stage = 'SUCCEEDED', progress = 1,
                message = 'Run completed', heartbeat_at = ?, finished_at = ?, run_id = ?
            WHERE id = ? AND status = 'RUNNING'
            """,
            (now, now, run_id, str(job["id"])),
        ).rowcount
        if changed != 1:
            raise RuntimeError("job terminal state changed before atomic publication")
        connection.execute(
            """
            INSERT INTO job_events(job_id, created_at, status, stage, progress, message)
            VALUES (?, ?, 'SUCCEEDED', 'SUCCEEDED', 1, 'Run completed')
            """,
            (str(job["id"]), now),
        )
        connection.commit()
    return run_id
