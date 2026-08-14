import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from elanquant.api.app import create_app
from elanquant.orchestration.jobs import JobStore
from elanquant.pipelines import real
from elanquant.settings import Settings
from elanquant.storage.database import Database
from scripts.research import online_release_v3
from scripts.research.online_release_v3 import (
    METHOD_LOCK_SCHEMA,
    ONLINE_SAMPLING,
    ONLINE_SIGNAL,
    PRIMARY_MODELS,
    RELEASE_SCHEMA,
    canonical_hash,
)
from scripts.server import evaluate_and_infer


def test_research_subprocess_uses_configured_source_root(
    tmp_path: Path, monkeypatch: Any
) -> None:
    source = tmp_path / "source"
    profiles = source / "configs/execution"
    dependencies = tmp_path / "research-deps"
    profiles.mkdir(parents=True)
    dependencies.mkdir()
    active = Settings(
        database_path=tmp_path / "db.sqlite3",
        artifact_root=tmp_path / "runs",
        frontend_dist=tmp_path / "dist",
        execution_profiles_root=profiles,
        research_deps=dependencies,
    )
    captured: dict[str, Any] = {}

    def fake_subprocess(command, **kwargs):  # type: ignore[no-untyped-def]
        captured["environment"] = kwargs["env"]
        return SimpleNamespace(returncode=0, stdout="{}\n", stderr="")

    monkeypatch.setattr(real.subprocess, "run", fake_subprocess)
    assert real._run(["research-python"], active) == {}
    python_path = str(captured["environment"]["PYTHONPATH"]).split(real.os.pathsep)
    assert python_path[:3] == [
        str(source / "backend/src"),
        str(source),
        str(dependencies),
    ]


@pytest.mark.parametrize(
    ("fail_finalization", "model_release"),
    [(False, "small"), (True, "small"), (False, "base")],
)
def test_real_pipeline_publishes_only_contract_complete_artifacts_atomically(
    tmp_path: Path, monkeypatch: Any, fail_finalization: bool, model_release: str
) -> None:
    research_root = tmp_path / "research"
    matrix_receipt = research_root / "releases/training-matrix.json"
    evaluation_receipt = research_root / "releases/formal-evaluation.json"
    matrix_receipt.parent.mkdir(parents=True)
    matrix_receipt.write_text(
        '{"schema_version":"elanquant_training_matrix_v2","status":"PASS"}\n',
        encoding="utf-8",
    )
    matrix_sha = real.sha256(matrix_receipt)
    active = Settings(
        database_path=research_root / "artifacts/elanquant.sqlite3",
        artifact_root=research_root / "artifacts/runs",
        frontend_dist=tmp_path / "missing-dist",
        pipeline_mode="real",
        matrix_receipt=matrix_receipt,
        evaluation_receipt=evaluation_receipt,
        execution_profile="local-apple-silicon",
        model_release=model_release,
        execution_device="cpu",
    )
    database = Database(active.database_path)
    database.initialize()
    jobs = JobStore(database)
    submitted, _ = jobs.submit_update_infer(
        "2026-08-12",
        execution_profile=active.execution_profile,
        model_release=model_release,
        requested_device=active.execution_device,
    )
    job = jobs.claim_next()
    assert job is not None

    model_ids = (
        f"{model_release}-zero-shot",
        f"{model_release}-official-ft",
        f"{model_release}-strict-pit",
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
                    "score": model_scores[f"{model_release}-strict-pit"],
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
                    "model_size": model_release,
                    "execution_profile": active.execution_profile,
                    "execution_device": active.execution_device,
                }
            ),
            encoding="utf-8",
        )
        return {
            "status": "PASS",
            "scores": 250,
            "model_size": model_release,
            "execution_profile": active.execution_profile,
            "execution_device": active.execution_device,
        }

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
                        "size": model_release,
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
    if model_release == "small":
        (matrix_receipt.parent / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "elanquant_release_v1",
                    "status": "PASS",
                    "release_id": "small-test-release",
                    "training_matrix_sha256": real.sha256(matrix_receipt),
                    "formal_evaluation_sha256": real.sha256(evaluation_receipt),
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
    expected_scripts = active.execution_profiles_root.resolve().parents[1] / "scripts/server"
    assert Path(commands[0][1]).resolve() == expected_scripts / "fetch_online_snapshot.py"

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
        publication_counts = {
            table: connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            for table in (
                "recommendation_sets",
                "recommendation_items",
                "paper_accounts",
                "paper_positions",
                "paper_gaps",
                "paper_signal_publications",
                "paper_intent_decisions",
                "paper_orders",
                "paper_fills",
                "portfolio_snapshots",
                "portfolio_position_valuations",
            )
        }
    assert run["protocol"] == (
        "STRICT_PIT_SMALL" if model_release == "small" else "STRICT_PIT_BASE_RESEARCH_ONLY"
    )
    assert run["evaluation_receipt_sha256"] == real.sha256(evaluation_receipt)
    inference_command = next(
        command for command in commands if any("evaluate_and_infer.py" in item for item in command)
    )
    assert inference_command[inference_command.index("--online-batch-size") + 1] == "50"
    assert inference_command[inference_command.index("--model-size") + 1] == model_release
    assert (
        inference_command[inference_command.index("--execution-profile") + 1]
        == "local-apple-silicon"
    )
    assert inference_command[inference_command.index("--device") + 1] == "cpu"
    assert score_count == 250 * 3
    assert model_count == 3
    assert evaluation_count == 6
    assert decision_count == (3 if model_release == "small" else 0)
    assert json.loads(snapshot_summary)["eligible_symbols"] == 250
    assert len(orders) == (3 if model_release == "small" else 0)
    if model_release == "base":
        assert set(publication_counts.values()) == {0}
    else:
        assert publication_counts["recommendation_sets"] == 1
        assert publication_counts["recommendation_items"] == 3
        assert publication_counts["paper_accounts"] == 1
        assert publication_counts["portfolio_snapshots"] == 1
    assert run["paper_publication_state"] == (
        "FROZEN" if model_release == "small" else "RESEARCH_ONLY_NOT_PUBLISHED"
    )
    assert run["scoreable"] == 0
    assert completed_job["status"] == "SUCCEEDED"
    assert {row["due_session"] for row in orders} == (
        {"2026-08-13"} if model_release == "small" else set()
    )
    api = TestClient(create_app(active))
    latest_response = api.get("/api/v1/runs/latest")
    if model_release == "base":
        assert latest_response.status_code == 404
        assert api.get("/api/v1/runs").json()["runs"][0]["id"] == run_id
    else:
        payload = latest_response.json()
        assert payload["scoreable"] is False
        assert len(payload["model_versions"]) == 3
        assert all("@" in identity for identity in payload["model_versions"])
        assert payload["provenance"]["evaluation_hash"] == real.sha256(
            evaluation_receipt
        )
        assert {cell["state"] for cell in payload["experiment_matrix"]} == {"passed"}
    dashboard_scores = api.get(f"/api/v1/runs/{run_id}/scores").json()["scores"]
    assert len(dashboard_scores[0]["model_scores"]) == 3
    assert all("@" not in identity for identity in dashboard_scores[0]["model_scores"])
    assert stages == [
        "UPDATING_DATA",
        "VALIDATING_DATA",
        f"INFER_{model_release.upper()}",
        "SCORING",
        "PAPER_LEDGER" if model_release == "small" else "RESEARCH_ONLY",
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


def test_small_publication_requires_one_hash_bound_release_manifest(tmp_path: Path) -> None:
    release = tmp_path / "release"
    release.mkdir()
    matrix = release / "training-matrix.json"
    evaluation = release / "formal-evaluation.json"
    matrix.write_text("matrix", encoding="utf-8")
    evaluation.write_text("evaluation", encoding="utf-8")
    settings = Settings(
        database_path=tmp_path / "db.sqlite3",
        artifact_root=tmp_path / "runs",
        frontend_dist=tmp_path / "dist",
        matrix_receipt=matrix,
        evaluation_receipt=evaluation,
    )
    matrix_sha = real.sha256(matrix)
    evaluation_sha = real.sha256(evaluation)
    with pytest.raises(RuntimeError, match="manifest is missing"):
        real.validate_publication_release(settings, matrix_sha, evaluation_sha)

    manifest = release / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "elanquant_release_v1",
                "status": "PASS",
                "release_id": "sealed-small",
                "training_matrix_sha256": matrix_sha,
                "formal_evaluation_sha256": evaluation_sha,
            }
        ),
        encoding="utf-8",
    )
    assert real.validate_publication_release(settings, matrix_sha, evaluation_sha)[
        "release_id"
    ] == "sealed-small"
    with pytest.raises(RuntimeError, match="invalid or mismatched"):
        real.validate_publication_release(settings, matrix_sha, "0" * 64)


def test_v3_publication_requires_pre_result_online_method_lock(
    tmp_path: Path, monkeypatch: Any
) -> None:
    release = tmp_path / "release-v3"
    release.mkdir()
    matrix = release / "training-matrix.json"
    evaluation = release / "rolling-evaluation.json"
    analysis = release / "analysis-lock.json"
    historical = release / "historical-catalog.json"
    method_path = release / "online-method-lock.json"
    matrix.write_text("matrix-v3", encoding="utf-8")
    evaluation.write_text("evaluation-v3", encoding="utf-8")
    analysis.write_text("{}", encoding="utf-8")
    historical.write_text("historical-v3", encoding="utf-8")
    matrix_sha = real.sha256(matrix)
    evaluation_sha = real.sha256(evaluation)
    runner_sha = "d" * 64
    method: dict[str, object] = {
        "schema_version": METHOD_LOCK_SCHEMA,
        "status": "PASS",
        "locked_at": "2026-08-14T00:00:00+00:00",
        "training_matrix_sha256": matrix_sha,
        "online_runner_sha256": runner_sha,
        "online_contract_sha256": real.sha256(
            Path(str(online_release_v3.__file__)).resolve()
        ),
        "primary_models": PRIMARY_MODELS,
        "selection_basis": "PREDECLARED_OFFICIAL_FT_METHOD_IDENTITY",
        "test_metrics_used_for_selection": False,
        "viewed_results_root": "results/viewed-v3",
        "viewed_results_present_at_lock": False,
        "online_signal": ONLINE_SIGNAL,
        "online_sampling": ONLINE_SAMPLING,
    }
    method["receipt_hash"] = canonical_hash(method)
    method_path.write_text(json.dumps(method), encoding="utf-8")
    monkeypatch.setattr(
        real,
        "validate_analysis_lock",
        lambda _payload: {"results_root": "results/viewed-v3"},
    )
    manifest: dict[str, object] = {
        "schema_version": RELEASE_SCHEMA,
        "status": "PASS",
        "release_id": "official-split-v3-test",
        "training_matrix_sha256": matrix_sha,
        "analysis_lock_sha256": real.sha256(analysis),
        "online_method_lock_sha256": real.sha256(method_path),
        "rolling_evaluation_sha256": evaluation_sha,
        "historical_catalog_sha256": real.sha256(historical),
        "online_runner_sha256": runner_sha,
        "primary_models": PRIMARY_MODELS,
        "selection_basis": "PREDECLARED_OFFICIAL_FT_METHOD_IDENTITY",
        "test_metrics_used_for_selection": False,
        "online_signal": ONLINE_SIGNAL,
        "online_sampling": ONLINE_SAMPLING,
    }
    manifest["receipt_hash"] = canonical_hash(manifest)
    (release / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    settings = Settings(
        database_path=tmp_path / "db.sqlite3",
        artifact_root=tmp_path / "runs",
        frontend_dist=tmp_path / "dist",
        matrix_receipt=matrix,
        evaluation_receipt=evaluation,
    )
    assert real.validate_publication_release(settings, matrix_sha, evaluation_sha)[
        "release_id"
    ] == "official-split-v3-test"
    method["viewed_results_present_at_lock"] = True
    method["receipt_hash"] = canonical_hash(
        {key: value for key, value in method.items() if key != "receipt_hash"}
    )
    method_path.write_text(json.dumps(method), encoding="utf-8")
    with pytest.raises(RuntimeError, match="firewall"):
        real.validate_publication_release(settings, matrix_sha, evaluation_sha)


def test_runtime_selection_is_frozen_to_job_profile_release_and_device(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "db.sqlite3",
        artifact_root=tmp_path / "runs",
        frontend_dist=tmp_path / "dist",
        execution_profile="remote-linux-nvidia",
        execution_device="cuda",
    )
    selected = real.resolve_runtime_selection(
        settings,
        {
            "execution_profile": "remote-linux-nvidia",
            "model_release": "base",
            "requested_device": "cuda",
        },
    )
    assert selected.execution_device == "cuda:0"
    assert selected.publish_paper is False
    with pytest.raises(RuntimeError, match="differs from the active deployment"):
        real.resolve_runtime_selection(
            settings,
            {
                "execution_profile": "local-apple-silicon",
                "model_release": "small",
                "requested_device": "cuda",
            },
        )


def test_evaluator_device_resolution_is_explicit_and_has_no_fallback(
    monkeypatch: Any,
) -> None:
    unavailable_cuda = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    with pytest.raises(RuntimeError, match="CPU fallback is forbidden"):
        evaluate_and_infer.resolve_device(
            unavailable_cuda, "remote-linux-nvidia", "cuda"
        )

    cuda = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True))
    assert (
        evaluate_and_infer.resolve_device(cuda, "remote-linux-nvidia", "cuda")
        == "cuda:0"
    )
    mps = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: True)),
    )
    assert evaluate_and_infer.resolve_device(mps, "local-apple-silicon", "mps") == "mps"
    monkeypatch.setenv("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    with pytest.raises(RuntimeError, match="must be disabled"):
        evaluate_and_infer.resolve_device(mps, "local-apple-silicon", "mps")
    with pytest.raises(RuntimeError, match="not admitted"):
        evaluate_and_infer.resolve_device(cuda, "remote-linux-nvidia", "cpu")
