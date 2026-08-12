from __future__ import annotations

import csv
import hashlib
import io
import json
import math
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


def valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_snapshot_summary(manifest: dict[str, Any]) -> dict[str, object]:
    excluded = manifest.get("excluded")
    excluded_counts: dict[str, int] = {}
    if isinstance(excluded, dict):
        if all(isinstance(entries, (list, int)) for entries in excluded.values()):
            for reason, entries in excluded.items():
                excluded_counts[str(reason)] = (
                    len(entries) if isinstance(entries, list) else int(entries)
                )
        else:
            for reason in excluded.values():
                reason_key = str(reason)
                excluded_counts[reason_key] = excluded_counts.get(reason_key, 0) + 1
    return {
        "status": manifest.get("status"),
        "requested_session": manifest.get("requested_session"),
        "resolved_session": manifest.get("resolved_session"),
        "generated_at_utc": manifest.get("generated_at_utc"),
        "generated_after_market_finalization": manifest.get(
            "generated_after_market_finalization"
        ),
        "daily_finalization_cutoff": manifest.get("daily_finalization_cutoff"),
        "market_timezone": manifest.get("market_timezone"),
        "membership_count": manifest.get("membership_count"),
        "eligible_symbols": manifest.get("eligible_symbols"),
        "excluded_counts": excluded_counts,
        "membership_snapshot": manifest.get("membership_snapshot"),
        "membership_available_session": manifest.get("membership_available_session"),
        "membership_availability_policy": manifest.get("membership_availability_policy"),
        "membership_revision_limitation": manifest.get("membership_revision_limitation"),
        "transport_caveat": manifest.get("transport_caveat"),
        "snapshot_logic_sha256": manifest.get("snapshot_logic_sha256"),
    }


def record_manual_gaps(
    connection: Any, current_session: str, open_days: list[str], now: str
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


def verified_snapshot_inputs(
    snapshot_path: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
    manifest_sha256: str,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    if sha256(manifest_path) != manifest_sha256:
        raise RuntimeError("online snapshot manifest changed before paper publication")
    files = manifest.get("files")
    expected_names = ("online_data.pkl", "trade_cal.csv", "execution.json")
    if not isinstance(files, dict) or not all(name in files for name in expected_names):
        raise RuntimeError("online snapshot manifest lacks the closed file receipt")
    contents: dict[str, bytes] = {}
    for name in expected_names:
        expected = files.get(name)
        if not isinstance(expected, str) or len(expected) != 64:
            raise RuntimeError(f"online snapshot file identity is invalid: {name}")
        payload = (snapshot_path / name).read_bytes()
        if hashlib.sha256(payload).hexdigest() != expected:
            raise RuntimeError(f"online snapshot file changed before paper publication: {name}")
        contents[name] = payload
    execution_raw = json.loads(contents["execution.json"].decode("utf-8"))
    if not isinstance(execution_raw, dict):
        raise RuntimeError("online execution payload is not an object")
    execution = {
        str(code): values
        for code, values in execution_raw.items()
        if isinstance(values, dict)
    }
    open_days = [
        str(row["cal_date"])
        for row in csv.DictReader(io.StringIO(contents["trade_cal.csv"].decode("utf-8")))
        if int(row["is_open"]) == 1
    ]
    if sha256(manifest_path) != manifest_sha256:
        raise RuntimeError("online snapshot manifest changed during paper publication")
    return execution, open_days


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
    evaluation_support = evaluation_result.get("evaluation_support")
    if (
        evaluation_result.get("status") != "PASS"
        or evaluation_result.get("schema_version") != "elanquant_kronos_inference_v1"
        or evaluation_result.get("evaluation_mode") != "FORMAL"
        or evaluation_result.get("test_status") != "TEST_VIEWED"
        or not isinstance(evaluation_models, dict)
        or set(evaluation_models) != expected_models
        or not isinstance(evaluation_support, dict)
        or evaluation_result.get("training_matrix_receipt_sha256") != matrix_sha
    ):
        raise RuntimeError("formal Small evaluation receipt is incomplete or mismatched")
    expected_support: dict[str, tuple[int, int]] = {}
    for split_name in ("validation_2025", "test_viewed_2026"):
        support = evaluation_support.get(split_name)
        if not isinstance(support, dict):
            raise RuntimeError(f"formal support is incomplete: {split_name}")
        rows = support.get("evaluated_rows")
        sections = support.get("evaluated_cross_sections")
        anchor_sha = support.get("anchor_set_sha256")
        if (
            not isinstance(rows, int)
            or rows <= 0
            or not isinstance(sections, int)
            or sections <= 0
            or not valid_sha256(anchor_sha)
        ):
            raise RuntimeError(f"formal support is invalid: {split_name}")
        expected_support[split_name] = (rows, sections)
    for model_id in expected_models:
        metrics = evaluation_models[model_id].get("metrics")
        if not isinstance(metrics, dict) or set(metrics) != set(expected_support):
            raise RuntimeError(f"formal split metrics are incomplete: {model_id}")
        for split_name, expected in expected_support.items():
            split_metrics = metrics.get(split_name)
            if (
                not isinstance(split_metrics, dict)
                or not all(
                    not isinstance(split_metrics.get(key), bool)
                    and isinstance(split_metrics.get(key), (int, float))
                    and math.isfinite(float(split_metrics[key]))
                    for key in ("rank_ic", "ic", "top10_mean_return")
                )
                or (split_metrics.get("rows"), split_metrics.get("cross_sections")) != expected
            ):
                raise RuntimeError(f"formal metrics are incomplete: {model_id}.{split_name}")
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
            "--online-batch-size",
            "50",
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
    for model_id in expected_models:
        evaluated_model = evaluation_models[model_id]
        online_model = models[model_id]
        if not isinstance(evaluated_model, dict) or not isinstance(online_model, dict):
            raise RuntimeError(f"model identity is incomplete: {model_id}")
        for identity in ("predictor_sha256", "tokenizer_sha256", "config_sha256"):
            if (
                not valid_sha256(evaluated_model.get(identity))
                or evaluated_model.get(identity) != online_model.get(identity)
            ):
                raise RuntimeError(f"formal/online model identity differs: {model_id}.{identity}")
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
    execution, calendar_open_days = verified_snapshot_inputs(
        snapshot_path, snapshot_manifest_path, snapshot_manifest, snapshot_hash
    )
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
                id, as_of_session, source, status, row_count, manifest_sha256,
                summary_json, created_at
            ) VALUES (?, ?, 'TUSHARE_PROXY_IMMUTABLE_ONLINE', 'PASS', ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                resolved,
                len(scores),
                snapshot_hash,
                json.dumps(safe_snapshot_summary(snapshot_manifest), sort_keys=True),
                now,
            ),
        )
        connection.execute(
            """
            UPDATE data_snapshots SET summary_json = COALESCE(summary_json, ?)
            WHERE id = ?
            """,
            (json.dumps(safe_snapshot_summary(snapshot_manifest), sort_keys=True), snapshot_id),
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
            version_identity = hashlib.sha256(
                (
                    f"{predictor_sha}:{model['tokenizer_sha256']}:"
                    f"{model.get('config_sha256', '')}:{evaluation_sha}"
                ).encode()
            ).hexdigest()
            version_id = f"{model_id}@{version_identity[:16]}"
            version_ids[model_id] = version_id
            variant = f"{variant_base}@{version_identity[:16]}"
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
                ON CONFLICT(id) DO UPDATE SET
                    base_model_id = excluded.base_model_id,
                    size = excluded.size,
                    variant = excluded.variant,
                    protocol = excluded.protocol,
                    status = excluded.status,
                    checkpoint_sha256 = excluded.checkpoint_sha256,
                    tokenizer_sha256 = excluded.tokenizer_sha256,
                    config_sha256 = excluded.config_sha256,
                    code_sha256 = excluded.code_sha256,
                    validation_rank_ic = excluded.validation_rank_ic,
                    validation_ic = excluded.validation_ic,
                    validation_top10_mean_return = excluded.validation_top10_mean_return,
                    viewed_test_rank_ic = excluded.viewed_test_rank_ic,
                    evaluation_receipt = excluded.evaluation_receipt,
                    evaluation_receipt_sha256 = excluded.evaluation_receipt_sha256
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
                    f"sha256:{evaluation_sha}" if evaluation_models else None,
                    evaluation_sha,
                ),
            )
        connection.execute(
            """
            INSERT INTO inference_runs(
                id, job_id, snapshot_id, as_of_session, status, protocol,
                artifact_path, artifact_sha256, scoreable, matrix_receipt_sha256,
                evaluation_receipt_sha256, config_sha256, code_sha256,
                created_at, finished_at
            ) VALUES (?, ?, ?, ?, 'SUCCEEDED', 'STRICT_PIT_SMALL',
                ?, ?, 0, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                str(job["id"]),
                snapshot_id,
                resolved,
                str(artifact_path),
                sha256(artifact_path),
                matrix_sha,
                evaluation_sha,
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
            metrics = evaluation_models[base_model_id]["metrics"]
            for split_name, split_metrics in metrics.items():
                support = evaluation_support[split_name]
                connection.execute(
                    """
                    INSERT INTO run_model_evaluations(
                        run_id, base_model_id, split, rank_ic, ic,
                        top10_mean_return, rows, cross_sections, anchor_set_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        base_model_id,
                        split_name,
                        float(split_metrics["rank_ic"]),
                        float(split_metrics["ic"]),
                        float(split_metrics["top10_mean_return"]),
                        int(split_metrics["rows"]),
                        int(split_metrics["cross_sections"]),
                        str(support["anchor_set_sha256"]),
                    ),
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
        record_manual_gaps(connection, resolved, calendar_open_days, now)
        settle_due_orders(connection, resolved, prices, execution)
        paper_publication = create_frozen_intents(
            connection,
            run_id,
            resolved,
            recommendations,
            settings.top_k,
            due_session=str(forecast_sessions[0]),
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
        write_portfolio_snapshot(
            connection, resolved, closes, valuation_policy="REAL_CLOSE_OR_BOOK_COST"
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
            (completed_message, now, now, run_id, str(job["id"])),
        ).rowcount
        if changed != 1:
            raise RuntimeError("job terminal state changed before atomic publication")
        connection.execute(
            """
            INSERT INTO job_events(job_id, created_at, status, stage, progress, message)
            VALUES (?, ?, 'SUCCEEDED', 'SUCCEEDED', 1, ?)
            """,
            (str(job["id"]), now, completed_message),
        )
        connection.commit()
    return run_id
