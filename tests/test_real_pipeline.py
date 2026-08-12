import json
from pathlib import Path
from typing import Any

import pytest
from elanquant.api.app import create_app
from elanquant.orchestration.jobs import JobStore
from elanquant.pipelines import real
from elanquant.settings import Settings
from elanquant.storage.database import Database
from fastapi.testclient import TestClient


@pytest.mark.parametrize("fail_finalization", [False, True])
def test_real_pipeline_publishes_only_contract_complete_artifacts_atomically(
    tmp_path: Path, monkeypatch: Any, fail_finalization: bool
) -> None:
    research_root = tmp_path / "research"
    matrix_receipt = research_root / "releases/training-matrix.json"
    evaluation_receipt = research_root / "releases/formal-evaluation.json"
    matrix_receipt.parent.mkdir(parents=True)
    matrix_receipt.write_text('{"status":"PASS"}\n', encoding="utf-8")
    matrix_sha = real.sha256(matrix_receipt)
    active = Settings(
        database_path=research_root / "artifacts/elanquant.sqlite3",
        artifact_root=research_root / "artifacts/runs",
        frontend_dist=tmp_path / "missing-dist",
        pipeline_mode="real",
        matrix_receipt=matrix_receipt,
        evaluation_receipt=evaluation_receipt,
    )
    database = Database(active.database_path)
    database.initialize()
    jobs = JobStore(database)
    submitted, _ = jobs.submit_update_infer("2026-08-12")
    job = jobs.claim_next()
    assert job is not None

    model_ids = (
        "small-zero-shot",
        "small-official-ft",
        "small-strict-pit",
    )
    commands: list[list[str]] = []

    def fake_run(command: list[str], _settings: Settings) -> dict[str, Any]:
        commands.append(command)
        if any("fetch_online_snapshot.py" in item for item in command):
            snapshot = research_root / "artifacts/online-snapshots/2026-08-12"
            snapshot.mkdir(parents=True)
            (snapshot / "online_data.pkl").write_bytes(b"test-online-data")
            (snapshot / "trade_cal.csv").write_text(
                "cal_date,is_open\n20260812,1\n20260813,1\n", encoding="utf-8"
            )
            execution = {
                f"{index:06d}.SZ": {"open": 10.0, "close": 10.1, "up_limit": 11.0}
                for index in range(250)
            }
            (snapshot / "execution.json").write_text(json.dumps(execution), encoding="utf-8")
            (snapshot / "manifest.json").write_text(
                json.dumps(
                    {
                        "status": "PASS",
                        "resolved_session": "2026-08-12",
                        "eligible_symbols": 250,
                        "files": {
                            name: real.sha256(snapshot / name)
                            for name in ("online_data.pkl", "trade_cal.csv", "execution.json")
                        },
                    }
                ),
                encoding="utf-8",
            )
            return {"status": "PASS", "snapshot": str(snapshot)}

        output = Path(command[command.index("--out") + 1])
        output.parent.mkdir(parents=True)
        models = {
            model_id: {
                "size": model_id.split("-", 1)[0],
                "track": (
                    "zero_shot"
                    if "zero-shot" in model_id
                    else "official_style"
                    if "official-ft" in model_id
                    else "strict_pit"
                ),
                "predictor_sha256": model_id.encode().hex().ljust(64, "0")[:64],
                "tokenizer_sha256": (model_id + "-tokenizer").encode().hex().ljust(64, "0")[:64],
                "config_sha256": "c" * 64,
            }
            for model_id in model_ids
        }
        scores = []
        for index in range(250):
            code = f"{index:06d}.SZ"
            model_scores = {model_id: (250 - index) / 10_000 for model_id in model_ids}
            scores.append(
                {
                    "rank": index + 1,
                    "code": code,
                    "name": code,
                    "score": model_scores["small-strict-pit"],
                    "reference_price": 10.1,
                    "model_scores": model_scores,
                }
            )
        output.write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "models": models,
                    "scores": scores,
                    "forecast_sessions": ["2026-08-13"],
                    "inference_code_sha256": "d" * 64,
                    "config_sha256": "c" * 64,
                }
            ),
            encoding="utf-8",
        )
        return {"status": "PASS", "scores": 250}

    evaluation_receipt.write_text(
        json.dumps(
            {
                "status": "PASS",
                "schema_version": "elanquant_kronos_inference_v1",
                "evaluation_mode": "FORMAL",
                "test_status": "TEST_VIEWED",
                "training_matrix_receipt_sha256": matrix_sha,
                "evaluation_support": {
                    "validation_2025": {
                        "evaluated_rows": 300,
                        "evaluated_cross_sections": 10,
                        "anchor_set_sha256": "a" * 64,
                    },
                    "test_viewed_2026": {
                        "evaluated_rows": 200,
                        "evaluated_cross_sections": 8,
                        "anchor_set_sha256": "b" * 64,
                    },
                },
                "models": {
                    model_id: {
                        "size": "small",
                        "track": (
                            "zero_shot"
                            if "zero-shot" in model_id
                            else "official_style"
                            if "official-ft" in model_id
                            else "strict_pit"
                        ),
                        "predictor_sha256": model_id.encode().hex().ljust(64, "0")[:64],
                        "tokenizer_sha256": (model_id + "-tokenizer")
                        .encode()
                        .hex()
                        .ljust(64, "0")[:64],
                        "config_sha256": "c" * 64,
                        "metrics": {
                            "validation_2025": {
                                "rank_ic": 0.1,
                                "ic": 0.08,
                                "top10_mean_return": 0.03,
                                "rows": 300,
                                "cross_sections": 10,
                            },
                            "test_viewed_2026": {
                                "rank_ic": 0.05,
                                "ic": 0.04,
                                "top10_mean_return": 0.01,
                                "rows": 200,
                                "cross_sections": 8,
                            },
                        }
                    }
                    for model_id in model_ids
                },
            }
        ),
        encoding="utf-8",
    )
    original_fake_run = fake_run

    def provenance_fake_run(command: list[str], settings: Settings) -> dict[str, Any]:
        receipt = original_fake_run(command, settings)
        if any("evaluate_and_infer.py" in item for item in command):
            output = Path(command[command.index("--out") + 1])
            result = json.loads(output.read_text(encoding="utf-8"))
            snapshot = research_root / "artifacts/online-snapshots/2026-08-12/manifest.json"
            result["training_matrix_receipt_sha256"] = matrix_sha
            result["data_manifest_sha256"] = real.sha256(snapshot)
            output.write_text(json.dumps(result), encoding="utf-8")
        return receipt

    monkeypatch.setattr(real, "_run", provenance_fake_run)
    stages: list[str] = []
    if fail_finalization:
        def fail_snapshot(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("injected finalization failure")

        monkeypatch.setattr(real, "write_portfolio_snapshot", fail_snapshot)
        with pytest.raises(RuntimeError, match="injected finalization failure"):
            real.run_real_pipeline(
                database,
                active,
                job,
                lambda stage, _progress, _message, _resolved: stages.append(stage),
            )
        with database.connect() as connection:
            for table in ("inference_runs", "stock_scores", "paper_orders"):
                assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
            current = connection.execute(
                "SELECT status FROM jobs WHERE id = ?", (job["id"],)
            ).fetchone()
        assert current["status"] == "RUNNING"
        return

    run_id = real.run_real_pipeline(
        database,
        active,
        job,
        lambda stage, _progress, _message, _resolved: stages.append(stage),
    )

    with database.connect() as connection:
        run = connection.execute("SELECT * FROM inference_runs WHERE id = ?", (run_id,)).fetchone()
        score_count = connection.execute("SELECT COUNT(*) AS n FROM stock_scores").fetchone()["n"]
        model_count = connection.execute("SELECT COUNT(*) AS n FROM model_versions").fetchone()["n"]
        evaluation_count = connection.execute(
            "SELECT COUNT(*) AS n FROM run_model_evaluations WHERE run_id = ?", (run_id,)
        ).fetchone()["n"]
        decision_count = connection.execute(
            "SELECT COUNT(*) AS n FROM paper_intent_decisions WHERE run_id = ?", (run_id,)
        ).fetchone()["n"]
        snapshot_summary = connection.execute(
            "SELECT summary_json FROM data_snapshots WHERE id = ?", (run["snapshot_id"],)
        ).fetchone()["summary_json"]
        orders = connection.execute("SELECT * FROM paper_orders").fetchall()
        completed_job = connection.execute(
            "SELECT * FROM jobs WHERE id = ?", (job["id"],)
        ).fetchone()
    assert run["protocol"] == "STRICT_PIT_SMALL"
    assert run["evaluation_receipt_sha256"] == real.sha256(evaluation_receipt)
    inference_command = next(
        command for command in commands if any("evaluate_and_infer.py" in item for item in command)
    )
    assert inference_command[inference_command.index("--online-batch-size") + 1] == "50"
    assert score_count == 250 * 3
    assert model_count == 3
    assert evaluation_count == 6
    assert decision_count == 3
    assert json.loads(snapshot_summary)["eligible_symbols"] == 250
    assert len(orders) == 3
    assert run["scoreable"] == 0
    assert completed_job["status"] == "SUCCEEDED"
    assert {row["due_session"] for row in orders} == {"2026-08-13"}
    api = TestClient(create_app(active))
    payload = api.get("/api/v1/runs/latest").json()
    assert payload["scoreable"] is False
    assert len(payload["model_versions"]) == 3
    assert all("@" in identity for identity in payload["model_versions"])
    assert payload["provenance"]["evaluation_hash"] == real.sha256(evaluation_receipt)
    assert {cell["state"] for cell in payload["experiment_matrix"]} == {"passed"}
    dashboard_scores = api.get(f"/api/v1/runs/{run_id}/scores").json()["scores"]
    assert len(dashboard_scores[0]["model_scores"]) == 3
    assert all("@" not in identity for identity in dashboard_scores[0]["model_scores"])
    assert stages == [
        "UPDATING_DATA",
        "VALIDATING_DATA",
        "INFER_SMALL",
        "SCORING",
        "PAPER_LEDGER",
    ]


def test_verified_snapshot_inputs_rejects_file_tampering(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "online_data.pkl").write_bytes(b"online")
    (snapshot / "trade_cal.csv").write_text(
        "cal_date,is_open\n20260812,1\n20260813,1\n", encoding="utf-8"
    )
    (snapshot / "execution.json").write_text(
        json.dumps({"000001.SZ": {"open": 10.0, "close": 10.1}}),
        encoding="utf-8",
    )
    manifest = {
        "files": {
            name: real.sha256(snapshot / name)
            for name in ("online_data.pkl", "trade_cal.csv", "execution.json")
        }
    }
    manifest_path = snapshot / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    manifest_sha = real.sha256(manifest_path)

    execution, open_days = real.verified_snapshot_inputs(
        snapshot, manifest_path, manifest, manifest_sha
    )
    assert execution["000001.SZ"]["close"] == 10.1
    assert open_days == ["20260812", "20260813"]

    (snapshot / "execution.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="execution.json"):
        real.verified_snapshot_inputs(snapshot, manifest_path, manifest, manifest_sha)


def test_snapshot_summary_counts_symbol_reason_mapping() -> None:
    summary = real.safe_snapshot_summary(
        {
            "status": "PASS",
            "excluded": {
                "000001.SZ": "missing_daily_or_adjustment",
                "000002.SZ": "missing_daily_or_adjustment",
                "000003.SZ": "provider_schema_mismatch",
            },
        }
    )
    assert summary["excluded_counts"] == {
        "missing_daily_or_adjustment": 2,
        "provider_schema_mismatch": 1,
    }
