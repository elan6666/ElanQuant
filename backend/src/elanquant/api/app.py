from __future__ import annotations

import hashlib
import sqlite3
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
        warning = None
        if str(run["protocol"]).startswith("PLACEHOLDER"):
            warning = "占位输出，不是市场数据、模型结论或投资建议。"
        elif not bool(run.get("scoreable")):
            warning = "这是最新在线预测，未来十个交易日标签尚未成熟，不能计入评估指标。"
        track_by_variant = {
            "zero_shot": "zero_shot",
            "official_ft": "official_style",
            "strict_pit_ft": "strict_pit",
        }
        matrix = []
        for model in model_rows:
            variant = str(model["variant"]).split("@", 1)[0]
            matrix.append(
                {
                    "id": model["id"],
                    "model_size": model["size"],
                    "track": track_by_variant.get(variant, "strict_pit"),
                    "state": (
                        "passed"
                        if model["status"] == "PASS" and model["evaluation_receipt_sha256"]
                        else "blocked"
                    ),
                    "rank_ic": model["validation_rank_ic"],
                    "pearson_ic": model["validation_ic"],
                    "top10_mean_return": model["validation_top10_mean_return"],
                    "model_hash": model["checkpoint_sha256"],
                    "receipt": model["evaluation_receipt"],
                    "note": warning,
                }
            )
        snapshot_dict = {} if snapshot is None else dict(snapshot)
        return {
            "id": run["id"],
            "as_of": run["as_of_session"],
            "status": "success" if run["status"] == "SUCCEEDED" else str(run["status"]).lower(),
            "created_at": run["created_at"],
            "model_id": "small-strict-pit",
            "protocol": run["protocol"],
            "model_versions": [model["id"] for model in model_rows],
            "scoreable": bool(run.get("scoreable")),
            "viewed_test": any(model["viewed_test_rank_ic"] is not None for model in models),
            "provenance": {
                "data_hash": snapshot_dict.get("manifest_sha256", ""),
                "model_hash": model_hash,
                "tokenizer_hash": hashlib.sha256(
                    "|".join(str(model["tokenizer_sha256"] or "") for model in model_rows).encode()
                ).hexdigest(),
                "config_hash": str(run.get("config_sha256") or ""),
                "code_hash": str(run.get("code_sha256") or ""),
            },
            "warnings": [] if warning is None else [warning],
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
            "primary_model": "strict-pit-small" if latest is not None else None,
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
        return {"run": dict(row), "recommendations": [dict(item) for item in recommendations]}

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
                "SELECT 1 FROM inference_runs WHERE id = ?", (run_id,)
            ).fetchone()
            rows = connection.execute(query, params).fetchall()
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
                    "eligible": eligible,
                    "explanation": (
                        "Small 严格PIT模型分数。"
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
