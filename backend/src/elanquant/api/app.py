from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from elanquant.orchestration.jobs import JobStore
from elanquant.pipelines.paper import ACCOUNT_ID
from elanquant.settings import Settings
from elanquant.storage.database import Database


class UpdateInferRequest(BaseModel):
    target_session: date | None = Field(default=None, description="Requested A-share session")
    force: bool = False


def canonical_hash(payload: object) -> str:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def validate_research_catalog(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise RuntimeError("catalog is not an object")
    content = dict(payload)
    receipt_hash = content.pop("receipt_hash", None)
    expected_tracks = {
        f"{size}-{identity}": (size, track)
        for size in ("small", "base")
        for identity, track in (
            ("zero-shot", "zero_shot"),
            ("official-ft", "official_style"),
            ("strict-pit", "strict_pit"),
        )
    }
    experiments = payload.get("experiments")
    sources = payload.get("sources")
    if (
        payload.get("schema_version") != "elanquant_research_catalog_v1"
        or payload.get("status") != "PASS"
        or not valid_sha256(receipt_hash)
        or canonical_hash(content) != receipt_hash
        or not isinstance(experiments, list)
        or len(experiments) != len(expected_tracks)
        or not all(isinstance(item, dict) for item in experiments)
        or not isinstance(sources, dict)
        or set(sources) != {"small", "base"}
    ):
        raise RuntimeError("catalog top-level receipt is invalid")
    if {str(item["id"]) for item in experiments} != set(expected_tracks):
        raise RuntimeError("catalog is not the exact six-cell experiment")
    support_by_split: dict[str, tuple[int, int, str]] = {}
    for item in experiments:
        model_id = str(item["id"])
        expected_size, expected_track = expected_tracks[model_id]
        if (
            item.get("model_size") != expected_size
            or item.get("track") != expected_track
            or item.get("state") != "passed"
            or not valid_sha256(item.get("model_hash"))
            or not valid_sha256(item.get("receipt"))
        ):
            raise RuntimeError(f"catalog cell identity is invalid: {model_id}")
        evaluations = item.get("evaluations")
        if not isinstance(evaluations, dict) or set(evaluations) != {
            "validation_2025",
            "test_viewed_2026",
        }:
            raise RuntimeError(f"catalog split evidence is incomplete: {model_id}")
        for split, values in evaluations.items():
            if not isinstance(values, dict):
                raise RuntimeError(f"catalog split evidence is invalid: {model_id}.{split}")
            for metric in ("rank_ic", "pearson_ic", "top10_mean_return"):
                value = values.get(metric)
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                ):
                    raise RuntimeError(f"catalog metric is invalid: {model_id}.{split}.{metric}")
            rows = values.get("rows")
            sections = values.get("cross_sections")
            anchor = values.get("anchor_set_sha256")
            if (
                isinstance(rows, bool)
                or not isinstance(rows, int)
                or rows <= 0
                or isinstance(sections, bool)
                or not isinstance(sections, int)
                or sections <= 0
                or not valid_sha256(anchor)
            ):
                raise RuntimeError(f"catalog support is invalid: {model_id}.{split}")
            signature = (rows, sections, str(anchor))
            if split in support_by_split and support_by_split[split] != signature:
                raise RuntimeError(f"catalog common support disagrees: {split}")
            support_by_split[split] = signature
    comparable_keys = (
        "upstream_commit",
        "official_weights_receipt_sha256",
        "training_data_sha256",
        "admission_sha256",
        "split_contract_sha256",
        "evaluation_data_sha256",
        "evaluation_config_sha256",
        "inference_code_sha256",
        "as_of_session",
        "support",
    )
    source_payloads: dict[str, dict[str, object]] = {}
    for size in ("small", "base"):
        source = sources.get(size)
        if not isinstance(source, dict):
            raise RuntimeError(f"catalog source is invalid: {size}")
        for identity in (
            "matrix_sha256",
            "evaluation_sha256",
            "official_weights_receipt_sha256",
            "training_data_sha256",
            "admission_sha256",
            "split_contract_sha256",
            "evaluation_data_sha256",
            "evaluation_config_sha256",
            "inference_code_sha256",
        ):
            if not valid_sha256(source.get(identity)):
                raise RuntimeError(f"catalog source identity is invalid: {size}.{identity}")
        upstream = source.get("upstream_commit")
        if (
            not isinstance(upstream, str)
            or len(upstream) != 40
            or any(character not in "0123456789abcdef" for character in upstream.lower())
        ):
            raise RuntimeError(f"catalog upstream identity is invalid: {size}")
        as_of = source.get("as_of_session")
        try:
            parsed_as_of = date.fromisoformat(str(as_of))
        except ValueError as error:
            raise RuntimeError(f"catalog as-of session is invalid: {size}") from error
        if parsed_as_of.isoformat() != as_of:
            raise RuntimeError(f"catalog as-of session is invalid: {size}")
        source_support = source.get("support")
        if not isinstance(source_support, dict) or set(source_support) != set(support_by_split):
            raise RuntimeError(f"catalog source support is invalid: {size}")
        for split, expected_signature in support_by_split.items():
            values = source_support.get(split)
            if not isinstance(values, dict):
                raise RuntimeError(f"catalog source support is invalid: {size}.{split}")
            eligible_rows = values.get("eligible_rows")
            if (
                isinstance(eligible_rows, bool)
                or not isinstance(eligible_rows, int)
                or eligible_rows < expected_signature[0]
            ):
                raise RuntimeError(f"catalog source support is invalid: {size}.{split}")
            signature = (
                values.get("evaluated_rows"),
                values.get("evaluated_cross_sections"),
                values.get("anchor_set_sha256"),
            )
            if signature != expected_signature:
                raise RuntimeError(f"catalog source support is mismatched: {size}.{split}")
        source_payloads[size] = source
    for key in comparable_keys:
        if source_payloads["small"].get(key) != source_payloads["base"].get(key):
            raise RuntimeError(f"catalog Small/Base identity differs: {key}")
    for item in experiments:
        size = str(item["model_size"])
        if item.get("receipt") != source_payloads[size].get("evaluation_sha256"):
            raise RuntimeError(f"catalog cell receipt is mismatched: {item['id']}")
    return payload


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings.load()
    database = Database(active_settings.database_path)
    database.initialize()
    jobs = JobStore(database)
    app = FastAPI(
        title="ElanQuant",
        version="0.1.0",
        description="Loopback-only research and simulated-account control plane",
    )
    app.state.settings = active_settings
    app.state.database = database
    app.state.jobs = jobs
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"],
    )

    @app.middleware("http")
    async def browser_boundary(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            allowed = {
                f"http://127.0.0.1:{active_settings.port}",
                f"http://localhost:{active_settings.port}",
            }
            if origin is not None and origin not in allowed:
                return Response(status_code=403, content="Origin is not allowed")
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/api/v1/health")
    def health() -> dict[str, object]:
        with database.connect() as connection:
            connection.execute("SELECT 1").fetchone()
        return {"status": "ok", "service": "elanquant-api"}

    def run_payload(row: sqlite3.Row) -> dict[str, object]:
        run: dict[str, object] = dict(row)
        with database.connect() as connection:
            snapshot = connection.execute(
                "SELECT * FROM data_snapshots WHERE id = ?", (run["snapshot_id"],)
            ).fetchone()
            models = connection.execute(
                """
                SELECT mv.* FROM inference_run_models irm
                JOIN model_versions mv ON mv.id = irm.model_version_id
                WHERE irm.run_id = ? ORDER BY mv.size, mv.variant
                """,
                (run["id"],),
            ).fetchall()
            evaluations = connection.execute(
                """
                SELECT * FROM run_model_evaluations
                WHERE run_id = ? ORDER BY base_model_id, split
                """,
                (run["id"],),
            ).fetchall()
            if not models and str(run["protocol"]).startswith("PLACEHOLDER"):
                models = connection.execute(
                    """
                    SELECT * FROM model_versions
                    WHERE status = 'PLACEHOLDER_ONLY' ORDER BY size, variant
                    """
                ).fetchall()
        model_rows = [dict(model) for model in models]
        checkpoint_material = "|".join(
            f"{model['id']}:{model['checkpoint_sha256']}" for model in model_rows
        )
        model_hash = hashlib.sha256(checkpoint_material.encode()).hexdigest()
        warnings: list[str] = []
        if str(run["protocol"]).startswith("PLACEHOLDER"):
            warnings.append("占位输出，不是市场数据、模型结论或投资建议。")
        elif not bool(run.get("scoreable")):
            warnings.append("这是最新在线预测，未来十个交易日标签尚未成熟，不能计入评估指标。")
        if run.get("paper_publication_state") == "LEGACY_MIXED_RUNS":
            warnings.append("该历史信号日包含多个运行来源；原始账本已保留且未被改写。")
        if run.get("paper_publication_state") == "SKIPPED_EXISTING_FROZEN_RUN":
            warnings.append("该信号日的模拟意图已由更早运行冻结；本次只更新研究结果。")
        evaluations_by_model: dict[str, dict[str, dict[str, object]]] = {}
        for evaluation in evaluations:
            raw = dict(evaluation)
            evaluations_by_model.setdefault(str(raw["base_model_id"]), {})[
                str(raw["split"])
            ] = {
                "rank_ic": raw["rank_ic"],
                "pearson_ic": raw["ic"],
                "top10_mean_return": raw["top10_mean_return"],
                "rows": raw["rows"],
                "cross_sections": raw["cross_sections"],
                "anchor_set_sha256": raw["anchor_set_sha256"],
            }
        expected_evaluation_splits = {"validation_2025", "test_viewed_2026"}
        formal_evidence_complete = bool(run.get("evaluation_receipt_sha256")) and len(
            model_rows
        ) == 3 and all(
            set(
                evaluations_by_model.get(
                    str(model["base_model_id"] or model["id"]), {}
                )
            )
            == expected_evaluation_splits
            for model in model_rows
        )
        if not formal_evidence_complete and not str(run["protocol"]).startswith("PLACEHOLDER"):
            warnings.append(
                "该历史运行缺少逐运行的双分区正式评估回执；实验指标已阻止展示。"
            )
        track_by_variant = {
            "zero_shot": "zero_shot",
            "official_ft": "official_style",
            "strict_pit_ft": "strict_pit",
        }
        matrix = []
        for model in model_rows:
            variant = str(model["variant"]).split("@", 1)[0]
            track = track_by_variant.get(variant)
            matrix.append(
                {
                    "id": model["id"],
                    "model_size": model["size"],
                    "track": track or "zero_shot",
                    "state": (
                        "passed"
                        if formal_evidence_complete
                        and track is not None
                        and model["status"] == "PASS"
                        and model["evaluation_receipt_sha256"]
                        else "blocked"
                    ),
                    "rank_ic": model["validation_rank_ic"] if formal_evidence_complete else None,
                    "pearson_ic": model["validation_ic"] if formal_evidence_complete else None,
                    "top10_mean_return": (
                        model["validation_top10_mean_return"]
                        if formal_evidence_complete
                        else None
                    ),
                    "model_hash": model["checkpoint_sha256"],
                    "receipt": (
                        model["evaluation_receipt"] if formal_evidence_complete else None
                    ),
                    "evaluations": (
                        evaluations_by_model.get(
                            str(model["base_model_id"] or model["id"]), {}
                        )
                        if formal_evidence_complete
                        else {}
                    ),
                    "note": (
                        f"未知模型变体 {variant}；已阻止展示为正式实验。"
                        if track is None
                        else warnings[0] if warnings else None
                    ),
                }
            )
        snapshot_dict = {} if snapshot is None else dict(snapshot)
        data_health: dict[str, object] | None = None
        if snapshot_dict.get("summary_json"):
            parsed = json.loads(str(snapshot_dict["summary_json"]))
            if isinstance(parsed, dict):
                data_health = parsed
        return {
            "id": run["id"],
            "as_of": run["as_of_session"],
            "status": "success" if run["status"] == "SUCCEEDED" else str(run["status"]).lower(),
            "created_at": run["created_at"],
            "model_id": "small-strict-pit",
            "protocol": run["protocol"],
            "model_versions": [model["id"] for model in model_rows],
            "scoreable": bool(run.get("scoreable")),
            "viewed_test": formal_evidence_complete,
            "provenance": {
                "data_hash": snapshot_dict.get("manifest_sha256", ""),
                "model_hash": model_hash,
                "tokenizer_hash": hashlib.sha256(
                    "|".join(str(model["tokenizer_sha256"] or "") for model in model_rows).encode()
                ).hexdigest(),
                "config_hash": str(run.get("config_sha256") or ""),
                "code_hash": str(run.get("code_sha256") or ""),
                "evaluation_hash": str(run.get("evaluation_receipt_sha256") or ""),
            },
            "warnings": warnings,
            "paper_publication": {
                "state": run.get("paper_publication_state"),
                "source_run_id": run.get("paper_publication_run_id"),
            },
            "data_health": data_health,
            "experiment_matrix": matrix,
        }

    @app.get("/api/v1/system/status")
    def system_status() -> dict[str, object]:
        with database.connect() as connection:
            active = connection.execute(
                """
                SELECT id FROM jobs WHERE status IN ('QUEUED', 'RUNNING')
                ORDER BY created_at LIMIT 1
                """
            ).fetchone()
            latest = connection.execute(
                """
                SELECT as_of_session, id, status
                FROM inference_runs ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
            snapshot = connection.execute(
                "SELECT as_of_session FROM data_snapshots ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            worker = connection.execute(
                "SELECT * FROM service_heartbeats WHERE service = 'worker'"
            ).fetchone()
        latest_session = None if latest is None else str(latest["as_of_session"])
        data_session = None if snapshot is None else str(snapshot["as_of_session"])
        warnings: list[str] = []
        worker_ready = False
        if worker is None:
            warnings.append("Worker 尚未写入心跳；API可访问不代表推理可执行。")
        else:
            heartbeat_at = datetime.fromisoformat(str(worker["heartbeat_at"]))
            worker_ready = datetime.now(UTC) - heartbeat_at <= timedelta(seconds=15)
            if not worker_ready:
                warnings.append("Worker 心跳已过期；请检查服务状态。")
        if active_settings.pipeline_mode == "real":
            if not active_settings.matrix_receipt.is_file():
                warnings.append("正式训练矩阵回执尚未发布。")
            if not active_settings.evaluation_receipt.is_file():
                warnings.append("正式评估回执尚未发布。")
        return {
            "status": "ok",
            "service_state": "ready" if worker_ready and not warnings else "degraded",
            "server_time": datetime.now(UTC).isoformat(),
            "latest_closed_session": data_session,
            "data_as_of": data_session,
            "inference_as_of": latest_session,
            "active_job_id": None if active is None else str(active["id"]),
            "primary_model": "small-strict-pit" if latest is not None else None,
            "warnings": warnings,
            "active_jobs": 0 if active is None else 1,
            "latest_run": None if latest is None else dict(latest),
            "execution_mode": (
                "REAL_STRICT_PIT"
                if active_settings.pipeline_mode == "real"
                else "PLACEHOLDER_RESEARCH_ONLY"
            ),
            "broker_connected": False,
            "automatic_schedule": False,
        }

    @app.get("/api/v1/research/experiments")
    def research_experiments() -> dict[str, object]:
        if not active_settings.research_catalog.is_file():
            return {"generated_at": None, "experiments": []}
        try:
            payload = json.loads(active_settings.research_catalog.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise HTTPException(
                status_code=503, detail="Research catalog could not be read safely"
            ) from error
        try:
            validated = validate_research_catalog(payload)
        except (KeyError, RuntimeError, TypeError, ValueError) as error:
            raise HTTPException(
                status_code=503, detail="Research catalog failed its receipt gate"
            ) from error
        return {
            "generated_at": validated.get("generated_at"),
            "experiments": validated["experiments"],
        }

    @app.post("/api/v1/jobs/update-infer", status_code=status.HTTP_202_ACCEPTED)
    def submit_update_infer(payload: UpdateInferRequest, response: Response) -> dict[str, object]:
        job, created = jobs.submit_update_infer(payload.target_session, force=payload.force)
        response.headers["Location"] = f"/api/v1/jobs/{job['id']}"
        return {"created": created, "job": job}

    @app.get("/api/v1/jobs")
    def list_jobs(limit: Annotated[int, Query(ge=1, le=200)] = 50) -> dict[str, object]:
        return {"jobs": jobs.list(limit)}

    @app.get("/api/v1/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, object]:
        try:
            return jobs.get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Job not found") from error

    @app.post("/api/v1/jobs/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
    def retry_job(job_id: str, response: Response) -> dict[str, object]:
        try:
            job = jobs.retry(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Job not found") from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        response.headers["Location"] = f"/api/v1/jobs/{job['id']}"
        return job

    @app.get("/api/v1/runs/latest")
    def latest_run() -> dict[str, object]:
        with database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM inference_runs
                WHERE status = 'SUCCEEDED' ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="No completed run")
        return run_payload(row)

    @app.get("/api/v1/runs")
    def list_runs(limit: Annotated[int, Query(ge=1, le=50)] = 10) -> dict[str, object]:
        with database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, as_of_session, status, protocol, created_at,
                    finished_at, scoreable, matrix_receipt_sha256,
                    evaluation_receipt_sha256, config_sha256, code_sha256,
                    paper_publication_state,
                    paper_publication_run_id
                FROM inference_runs WHERE status = 'SUCCEEDED'
                ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return {"runs": [dict(row) for row in rows]}

    def strict_ranks(connection: sqlite3.Connection, run_id: str) -> dict[str, int]:
        return {
            str(row["code"]): int(row["rank"])
            for row in connection.execute(
                """
                SELECT ss.code, ss.rank FROM stock_scores ss
                JOIN inference_run_models irm
                  ON irm.run_id = ss.run_id AND irm.model_version_id = ss.model_version_id
                WHERE ss.run_id = ? AND irm.base_model_id LIKE '%-strict-pit'
                """,
                (run_id,),
            ).fetchall()
        }

    @app.get("/api/v1/runs/{run_id}/diff")
    def run_diff(run_id: str, against: str | None = None) -> dict[str, object]:
        with database.connect() as connection:
            current = connection.execute(
                "SELECT * FROM inference_runs WHERE id = ? AND status = 'SUCCEEDED'", (run_id,)
            ).fetchone()
            if current is None:
                raise HTTPException(status_code=404, detail="Run not found")
            baseline = (
                connection.execute(
                    "SELECT * FROM inference_runs WHERE id = ? AND status = 'SUCCEEDED'",
                    (against,),
                ).fetchone()
                if against is not None
                else connection.execute(
                    """
                    SELECT * FROM inference_runs
                    WHERE status = 'SUCCEEDED' AND (created_at < ? OR (created_at = ? AND id < ?))
                    ORDER BY created_at DESC, id DESC LIMIT 1
                    """,
                    (current["created_at"], current["created_at"], run_id),
                ).fetchone()
            )
            current_ranks = strict_ranks(connection, run_id)
            baseline_ranks = (
                {} if baseline is None else strict_ranks(connection, str(baseline["id"]))
            )
        if baseline is None:
            return {
                "run_id": run_id,
                "against_run_id": None,
                "comparable": False,
                "reason": "NO_PREVIOUS_COMPLETED_RUN",
            }
        common = set(current_ranks) & set(baseline_ranks)
        minimum_coverage = 250
        if (
            len(current_ranks) < minimum_coverage
            or len(baseline_ranks) < minimum_coverage
            or len(common) < minimum_coverage
        ):
            return {
                "run_id": run_id,
                "against_run_id": str(baseline["id"]),
                "comparable": False,
                "reason": "STRICT_RANK_COVERAGE_INCOMPLETE",
                "coverage": {
                    "current": len(current_ranks),
                    "baseline": len(baseline_ranks),
                    "common": len(common),
                    "required": minimum_coverage,
                },
            }
        current_top3 = {code for code, rank in current_ranks.items() if rank <= 3}
        baseline_top3 = {code for code, rank in baseline_ranks.items() if rank <= 3}
        current_top10 = {code for code, rank in current_ranks.items() if rank <= 10}
        baseline_top10 = {code for code, rank in baseline_ranks.items() if rank <= 10}
        largest_changes = sorted(
            (
                {
                    "code": code,
                    "from_rank": baseline_ranks[code],
                    "to_rank": current_ranks[code],
                    "delta": baseline_ranks[code] - current_ranks[code],
                }
                for code in common
            ),
            key=lambda item: (-abs(int(item["delta"])), str(item["code"])),
        )[:20]
        fields = (
            "snapshot_id",
            "matrix_receipt_sha256",
            "evaluation_receipt_sha256",
            "config_sha256",
            "code_sha256",
        )
        return {
            "run_id": run_id,
            "against_run_id": str(baseline["id"]),
            "comparable": True,
            "same_session": current["as_of_session"] == baseline["as_of_session"],
            "identity_changes": {
                field: current[field] != baseline[field] for field in fields
            },
            "top3_overlap": len(current_top3 & baseline_top3),
            "top10_overlap": len(current_top10 & baseline_top10),
            "top3_added": sorted(current_top3 - baseline_top3),
            "top3_dropped": sorted(baseline_top3 - current_top3),
            "largest_rank_changes": largest_changes,
        }

    @app.get("/api/v1/runs/{run_id}/data-health")
    def run_data_health(run_id: str) -> dict[str, object]:
        with database.connect() as connection:
            row = connection.execute(
                """
                SELECT ds.* FROM inference_runs ir
                JOIN data_snapshots ds ON ds.id = ir.snapshot_id
                WHERE ir.id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Run not found")
        summary: dict[str, object] = {
            "status": row["status"],
            "resolved_session": row["as_of_session"],
            "eligible_symbols": row["row_count"],
        }
        if row["summary_json"]:
            parsed = json.loads(str(row["summary_json"]))
            if isinstance(parsed, dict):
                summary = parsed
        return {
            "run_id": run_id,
            "manifest_sha256": row["manifest_sha256"],
            "summary": summary,
        }

    @app.get("/api/v1/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, object]:
        with database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM inference_runs WHERE id = ?", (run_id,)
            ).fetchone()
            recommendations = connection.execute(
                """
                SELECT ri.* FROM recommendation_items ri
                JOIN recommendation_sets rs ON rs.id = ri.recommendation_set_id
                WHERE rs.run_id = ? ORDER BY ri.rank
                """,
                (run_id,),
            ).fetchall()
        if row is None:
            raise HTTPException(status_code=404, detail="Run not found")
        safe_run = dict(row)
        safe_run.pop("artifact_path", None)
        return {"run": safe_run, "recommendations": [dict(item) for item in recommendations]}

    @app.get("/api/v1/runs/{run_id}/scores")
    def run_scores(run_id: str, model_id: str | None = None) -> dict[str, object]:
        query = """
            SELECT ss.*, irm.base_model_id FROM stock_scores ss
            JOIN inference_run_models irm
              ON irm.run_id = ss.run_id AND irm.model_version_id = ss.model_version_id
            WHERE ss.run_id = ?
        """
        params: tuple[str, ...] = (run_id,)
        if model_id is not None:
            query += " AND (ss.model_version_id = ? OR irm.base_model_id = ?)"
            params = (run_id, model_id, model_id)
        query += " ORDER BY irm.base_model_id, ss.rank"
        with database.connect() as connection:
            exists = connection.execute(
                "SELECT * FROM inference_runs WHERE id = ?", (run_id,)
            ).fetchone()
            rows = connection.execute(query, params).fetchall()
            previous = (
                None
                if exists is None
                else connection.execute(
                    """
                    SELECT id FROM inference_runs
                    WHERE status = 'SUCCEEDED'
                      AND (created_at < ? OR (created_at = ? AND id < ?))
                    ORDER BY created_at DESC, id DESC LIMIT 1
                    """,
                    (exists["created_at"], exists["created_at"], run_id),
                ).fetchone()
            )
            previous_ranks = (
                {}
                if previous is None
                else strict_ranks(connection, str(previous["id"]))
            )
            recommended = {
                str(row["code"])
                for row in connection.execute(
                    """
                    SELECT ri.code FROM recommendation_items ri
                    JOIN recommendation_sets rs ON rs.id = ri.recommendation_set_id
                    WHERE rs.run_id = ?
                    """,
                    (run_id,),
                ).fetchall()
            }
            decisions = {
                str(row["code"]): dict(row)
                for row in connection.execute(
                    "SELECT * FROM paper_intent_decisions WHERE run_id = ?", (run_id,)
                ).fetchall()
            }
        if exists is None:
            raise HTTPException(status_code=404, detail="Run not found")
        by_code: dict[str, dict[str, object]] = {}
        for raw in rows:
            row = dict(raw)
            code = str(row["code"])
            item = by_code.setdefault(
                code,
                {
                    "code": code,
                    "name": row["name"],
                    "values": [],
                    "strict_values": [],
                    "model_scores": {},
                    "reference_price": row["reference_price"],
                    "eligible": True,
                },
            )
            values = item["values"]
            strict_values = item["strict_values"]
            scores = item["model_scores"]
            assert isinstance(values, list)
            assert isinstance(strict_values, list)
            assert isinstance(scores, dict)
            score = float(row["score"])
            values.append(score)
            base_model_id = str(row["base_model_id"])
            if base_model_id.endswith("strict-pit"):
                strict_values.append(score)
            scores[base_model_id] = score
            if str(row["scoreability"]).startswith("PLACEHOLDER"):
                item["eligible"] = False
        aggregated = []
        for item in by_code.values():
            values = item.pop("values")
            strict_values = item.pop("strict_values")
            assert isinstance(values, list)
            assert isinstance(strict_values, list)
            consensus_values = strict_values or values
            consensus = sum(consensus_values) / len(consensus_values)
            item["model_spread"] = max(values) - min(values) if values else None
            aggregated.append((consensus, item))
        aggregated.sort(key=lambda pair: (-pair[0], str(pair[1]["code"])))
        scores_payload = []
        for rank, (consensus, item) in enumerate(aggregated, start=1):
            eligible = bool(item.pop("eligible"))
            scores_payload.append(
                {
                    **item,
                    "rank": rank,
                    "score": consensus,
                    "forecast_return": consensus,
                    "coverage": 1.0 if eligible else 0.0,
                    "input_completeness": 1.0 if eligible else 0.0,
                    "eligible": eligible,
                    "model_spread": item.pop("model_spread"),
                    "previous_rank": previous_ranks.get(str(item["code"])),
                    "rank_delta": (
                        None
                        if str(item["code"]) not in previous_ranks
                        else previous_ranks[str(item["code"])] - rank
                    ),
                    "selected_top3": str(item["code"]) in recommended,
                    "paper_decision": decisions.get(str(item["code"]), {}).get("decision"),
                    "paper_reason": decisions.get(str(item["code"]), {}).get("reason"),
                    "explanation": (
                        "严格PIT轨驱动排名；三轨分歧只用于解释，不代表置信区间。"
                        if eligible
                        else "占位分数，不可用于研究结论或投资决策。"
                    ),
                    "forecast": [],
                }
            )
        return {"scores": scores_payload}

    @app.get("/api/v1/runs/{run_id}/stocks/{code}")
    def stock_detail(run_id: str, code: str) -> dict[str, object]:
        with database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM stock_scores WHERE run_id = ? AND code = ?
                ORDER BY model_version_id
                """,
                (run_id, code),
            ).fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail="Stock score not found")
        return {"code": code, "models": [dict(row) for row in rows]}

    @app.get("/api/v1/paper/account")
    def paper_account() -> dict[str, object]:
        with database.connect() as connection:
            account = connection.execute(
                "SELECT * FROM paper_accounts WHERE id = ?", (ACCOUNT_ID,)
            ).fetchone()
            positions = connection.execute(
                "SELECT * FROM paper_positions WHERE account_id = ? ORDER BY code", (ACCOUNT_ID,)
            ).fetchall()
            pending = connection.execute(
                """
                SELECT * FROM paper_orders WHERE account_id = ? AND status = 'PENDING'
                ORDER BY due_session, created_at
                """,
                (ACCOUNT_ID,),
            ).fetchall()
            latest_snapshot = connection.execute(
                """
                SELECT * FROM portfolio_snapshots WHERE account_id = ?
                ORDER BY as_of_session DESC LIMIT 1
                """,
                (ACCOUNT_ID,),
            ).fetchone()
            snapshot_valuations = (
                []
                if latest_snapshot is None
                else connection.execute(
                    """
                    SELECT * FROM portfolio_position_valuations
                    WHERE snapshot_id = ? ORDER BY code
                    """,
                    (latest_snapshot["id"],),
                ).fetchall()
            )
            gaps = connection.execute(
                "SELECT session FROM paper_gaps WHERE account_id = ? ORDER BY session",
                (ACCOUNT_ID,),
            ).fetchall()
            latest_prices = connection.execute(
                """
                SELECT ss.code, ss.reference_price
                FROM stock_scores ss
                JOIN inference_run_models irm
                  ON irm.run_id = ss.run_id AND irm.model_version_id = ss.model_version_id
                JOIN inference_runs ir ON ir.id = ss.run_id
                WHERE irm.base_model_id = 'small-strict-pit'
                  AND ir.id = (
                    SELECT id FROM inference_runs
                    WHERE status = 'SUCCEEDED' ORDER BY created_at DESC LIMIT 1
                  )
                """
            ).fetchall()
        if account is None:
            raise HTTPException(status_code=404, detail="Paper account not initialized")
        account_dict = dict(account)
        snapshot_dict = {} if latest_snapshot is None else dict(latest_snapshot)
        cash = float(snapshot_dict.get("cash", account_dict["cash"]))
        price_by_code = {str(row["code"]): float(row["reference_price"]) for row in latest_prices}
        valuation_by_code = {str(row["code"]): row for row in snapshot_valuations}
        position_payload = []
        for row in positions:
            code = str(row["code"])
            valuation = valuation_by_code.get(code)
            if valuation is not None:
                last_price = float(valuation["valuation_price"])
                source = str(valuation["valuation_source"])
                position_value = float(valuation["market_value"])
                unrealized = float(valuation["unrealized_pnl"])
            else:
                last_price = price_by_code.get(code, float(row["average_cost"]))
                source = (
                    "LATEST_STRICT_SCORE_CLOSE"
                    if code in price_by_code
                    else "AVERAGE_COST_FALLBACK"
                )
                position_value = int(row["quantity"]) * last_price
                unrealized = int(row["quantity"]) * (
                    last_price - float(row["average_cost"])
                )
            position_payload.append(
                {
                    "code": row["code"],
                    "name": row["name"],
                    "quantity": row["quantity"],
                    "available_quantity": row["available_quantity"],
                    "average_cost": row["average_cost"],
                    "last_price": last_price,
                    "valuation_source": source,
                    "market_value": position_value,
                    "unrealized_pnl": unrealized,
                    "held_sessions": None,
                }
            )
        market_value = sum(float(item["market_value"]) for item in position_payload)
        return {
            "as_of": snapshot_dict.get("as_of_session"),
            "initial_cash": float(account_dict["initial_cash"]),
            "cash": cash,
            "market_value": market_value,
            "equity": cash + market_value,
            "valuation_policy": snapshot_dict.get("valuation_policy"),
            "positions": position_payload,
            "pending_orders": [dict(row) for row in pending],
            "gaps": [str(row["session"]) for row in gaps],
        }

    @app.get("/api/v1/paper/orders")
    def paper_orders(limit: Annotated[int, Query(ge=1, le=500)] = 100) -> dict[str, object]:
        with database.connect() as connection:
            rows = connection.execute(
                """
                SELECT po.*, pf.price AS fill_price, pf.commission, pf.stamp_tax
                FROM paper_orders po
                LEFT JOIN paper_fills pf ON pf.order_id = po.id
                WHERE po.account_id = ?
                ORDER BY po.created_at DESC LIMIT ?
                """,
                (ACCOUNT_ID, limit),
            ).fetchall()
        status_map = {"PENDING": "intent", "FILLED": "filled", "REJECTED": "rejected"}
        return {
            "orders": [
                {
                    "id": row["id"],
                    "run_id": row["run_id"],
                    "signal_date": row["signal_session"],
                    "execution_date": row["execution_session"],
                    "code": row["code"],
                    "name": row["name"],
                    "side": str(row["side"]).lower(),
                    "quantity": row["quantity"],
                    "status": status_map.get(str(row["status"]), "rejected"),
                    "price": row["fill_price"],
                    "fees": (
                        None
                        if row["commission"] is None
                        else float(row["commission"]) + float(row["stamp_tax"])
                    ),
                    "rejection_reason": row["reject_reason"],
                }
                for row in rows
            ]
        }

    @app.get("/api/v1/paper/summary")
    def paper_summary() -> dict[str, object]:
        with database.connect() as connection:
            account = connection.execute(
                "SELECT * FROM paper_accounts WHERE id = ?", (ACCOUNT_ID,)
            ).fetchone()
            nav_rows = connection.execute(
                """
                SELECT * FROM portfolio_snapshots
                WHERE account_id = ? ORDER BY as_of_session
                """,
                (ACCOUNT_ID,),
            ).fetchall()
            order_rows = connection.execute(
                "SELECT * FROM paper_orders WHERE account_id = ?", (ACCOUNT_ID,)
            ).fetchall()
            fill_rows = connection.execute(
                """
                SELECT pf.* FROM paper_fills pf
                JOIN paper_orders po ON po.id = pf.order_id
                WHERE po.account_id = ?
                """,
                (ACCOUNT_ID,),
            ).fetchall()
            latest_run = connection.execute(
                """
                SELECT id, as_of_session, paper_publication_state, paper_publication_run_id
                FROM inference_runs WHERE status = 'SUCCEEDED'
                ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
            decisions = (
                []
                if latest_run is None
                else connection.execute(
                    """
                    SELECT * FROM paper_intent_decisions
                    WHERE run_id = ? ORDER BY rank, code
                    """,
                    (latest_run["id"],),
                ).fetchall()
            )
            legacy = connection.execute(
                """
                SELECT signal_session, run_id, note FROM paper_signal_publications
                WHERE account_id = ? AND state = 'LEGACY_MIXED_RUNS'
                ORDER BY signal_session
                """,
                (ACCOUNT_ID,),
            ).fetchall()
        if account is None:
            raise HTTPException(status_code=404, detail="Paper account not initialized")
        status_counts = Counter(str(row["status"]).lower() for row in order_rows)
        decision_counts = Counter(str(row["decision"]) for row in decisions)
        max_drawdown: float | None = None
        if len(nav_rows) >= 2:
            peak = float(nav_rows[0]["nav"])
            max_drawdown = 0.0
            for row in nav_rows:
                value = float(row["nav"])
                peak = max(peak, value)
                max_drawdown = min(max_drawdown, value / peak - 1)
        initial_cash = float(account["initial_cash"])
        gross = sum(float(row["gross_amount"]) for row in fill_rows)
        return {
            "sample_sessions": len(nav_rows),
            "evidence_state": "available" if len(nav_rows) >= 2 else "insufficient_evidence",
            "order_counts": {
                "pending": status_counts.get("pending", 0),
                "filled": status_counts.get("filled", 0),
                "rejected": status_counts.get("rejected", 0),
            },
            "decision_counts": dict(sorted(decision_counts.items())),
            "total_fees": sum(
                float(row["commission"]) + float(row["stamp_tax"]) for row in fill_rows
            ),
            "gross_turnover": gross / initial_cash if initial_cash > 0 else None,
            "max_drawdown": max_drawdown,
            "latest_publication": (
                None
                if latest_run is None
                else {
                    "run_id": latest_run["id"],
                    "signal_session": latest_run["as_of_session"],
                    "state": latest_run["paper_publication_state"],
                    "source_run_id": latest_run["paper_publication_run_id"],
                }
            ),
            "latest_decisions": [dict(row) for row in decisions],
            "warnings": [
                f"{row['signal_session']}: {row['note']}" for row in legacy
            ],
        }

    @app.get("/api/v1/paper/nav")
    def paper_nav() -> dict[str, object]:
        with database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM portfolio_snapshots WHERE account_id = ? ORDER BY as_of_session
                """,
                (ACCOUNT_ID,),
            ).fetchall()
        return {
            "nav": [
                {
                    "session": row["as_of_session"],
                    "nav": row["nav"],
                    "benchmark_nav": None,
                }
                for row in rows
            ]
        }

    if active_settings.frontend_dist.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=active_settings.frontend_dist, html=True),
            name="frontend",
        )
    return app


def main() -> None:
    settings = Settings.load()
    if settings.host not in {"127.0.0.1", "::1", "localhost"}:
        raise RuntimeError("ElanQuant API must bind to loopback")
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
