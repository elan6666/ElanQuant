from __future__ import annotations

import csv
import json
from pathlib import Path

from fastapi.testclient import TestClient

from elanquant.api.app import create_app
from elanquant.contracts.official_demo import (
    BACKTEST_SCHEMA,
    CATALOG_SCHEMA,
    CATALOG_SCHEMA_V2,
    EXPECTED_EXECUTION,
    EXPECTED_STRATEGY,
    FINAL_TEST_BACKTEST_SCHEMA,
    FINAL_TEST_STRATEGY_ID,
    canonical_hash,
    sha256_file,
)
from elanquant.settings import Settings


def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "elanquant.sqlite3",
        artifact_root=tmp_path / "artifacts",
        frontend_dist=tmp_path / "missing-dist",
        historical_backtest_catalog=tmp_path / "releases" / "historical.json",
    )


def seal(payload: dict[str, object]) -> dict[str, object]:
    payload["receipt_hash"] = canonical_hash(payload)
    return payload


def publish_backtest(tmp_path: Path) -> tuple[Settings, Path]:
    active = settings(tmp_path)
    root = tmp_path
    output = root / "runs" / "backtests" / "official" / "result"
    output.mkdir(parents=True)
    series_path = output / "daily-series.csv"
    with series_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "datetime",
                "signal",
                "additive_strategy_with_cost",
                "additive_benchmark",
                "additive_excess_with_cost",
                "compounded_strategy_nav",
                "compounded_benchmark_nav",
            ],
        )
        writer.writeheader()
        for signal in ("mean", "last", "max", "min"):
            writer.writerow(
                {
                    "datetime": "2025-01-02",
                    "signal": signal,
                    "additive_strategy_with_cost": "0.01",
                    "additive_benchmark": "0.005",
                    "additive_excess_with_cost": "0.005",
                    "compounded_strategy_nav": "1.01",
                    "compounded_benchmark_nav": "1.005",
                }
            )
    metrics = {
        signal: {
            "total_return_with_cost": 0.1,
            "benchmark_return": 0.08,
            "excess_return_without_cost": 0.03,
            "excess_return_with_cost": 0.02,
            "annualized_return_with_cost": 0.11,
            "annualized_excess_return_with_cost": 0.021,
            "information_ratio_with_cost": 0.3,
            "max_drawdown_with_cost": -0.06,
            "total_cost": 0.01,
        }
        for signal in ("mean", "last", "max", "min")
    }
    receipt = seal(
        {
            "schema_version": BACKTEST_SCHEMA,
            "status": "PASS",
            "id": "official-demo-method-extended-pit-v1",
            "track_kind": "OFFICIAL_DEMO_METHOD_EXTENDED_PIT",
            "model_cell_id": "small-official-ft",
            "generated_at": "2026-08-13T00:00:00+00:00",
            "selection_split": "validation_2025",
            "selection_rule_predeclared": True,
            "test_viewed_consumed": False,
            "test_status": "NOT_ACCESSED_FOR_SELECTION",
            "selection_eligible": True,
            "primary_signal": "mean",
            "signal_receipt_sha256": "d" * 64,
            "provider_receipt_sha256": "2" * 64,
            "backtest_code_sha256": "3" * 64,
            "strategy": dict(EXPECTED_STRATEGY),
            "execution": dict(EXPECTED_EXECUTION),
            "qlib": {
                "version": "0.9.7",
                "metadata_sha256": "e" * 64,
                "record_sha256": "f" * 64,
                "source_tree_sha256": "0" * 64,
            },
            "support": {
                "sessions": 1,
                "signal_rows": 300,
                "signal_cross_sections": 1,
                "candidate_min": 300,
                "candidate_median": 300.0,
                "candidate_max": 300,
                "actual_start": "2025-01-02",
                "actual_end": "2025-01-02",
            },
            "metrics": metrics,
            "curve_semantics": {
                "official": "Arithmetic cumulative sum.",
                "derived": "Compounded NAV extension.",
            },
            "artifacts": {
                "daily_series": {
                    "path": series_path.relative_to(root).as_posix(),
                    "sha256": sha256_file(series_path),
                    "bytes": series_path.stat().st_size,
                }
            },
            "deviations": ["extended PIT data and split"],
        }
    )
    receipt_path = output / "backtest-receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    catalog = seal(
        {
            "schema_version": CATALOG_SCHEMA,
            "status": "PASS",
            "generated_at": "2026-08-13T00:00:01+00:00",
            "entries": [
                {
                    "id": receipt["id"],
                    "state": "passed",
                    "model_cell_id": receipt["model_cell_id"],
                    "selection_eligible": True,
                    "primary_signal": "mean",
                    "selection_split": "validation_2025",
                    "test_viewed_consumed": False,
                    "receipt_sha256": sha256_file(receipt_path),
                    "receipt_path": receipt_path.relative_to(root).as_posix(),
                    "summary": metrics["mean"],
                }
            ],
        }
    )
    active.historical_backtest_catalog.parent.mkdir(parents=True)
    active.historical_backtest_catalog.write_text(json.dumps(catalog), encoding="utf-8")
    return active, series_path


def publish_dual_backtest(tmp_path: Path) -> tuple[Settings, Path]:
    active, _ = publish_backtest(tmp_path)
    root = tmp_path
    validation_catalog = json.loads(
        active.historical_backtest_catalog.read_text(encoding="utf-8")
    )
    validation_entry = validation_catalog["entries"][0]
    validation_receipt_path = root / validation_entry["receipt_path"]
    validation_receipt = json.loads(validation_receipt_path.read_text(encoding="utf-8"))
    final_output = root / "runs" / "backtests" / "final" / "result"
    final_output.mkdir(parents=True)
    final_series = final_output / "daily-series.csv"
    with final_series.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "datetime",
                "signal",
                "additive_strategy_with_cost",
                "additive_benchmark",
                "additive_excess_with_cost",
                "compounded_strategy_nav",
                "compounded_benchmark_nav",
            ],
        )
        writer.writeheader()
        for signal in ("mean", "last", "max", "min"):
            writer.writerow(
                {
                    "datetime": "2026-01-05",
                    "signal": signal,
                    "additive_strategy_with_cost": "0.02",
                    "additive_benchmark": "0.01",
                    "additive_excess_with_cost": "0.01",
                    "compounded_strategy_nav": "1.02",
                    "compounded_benchmark_nav": "1.01",
                }
            )
    final_receipt = dict(validation_receipt)
    for key in (
        "receipt_hash",
        "selection_split",
        "selection_rule_predeclared",
        "test_viewed_consumed",
        "test_status",
    ):
        final_receipt.pop(key)
    final_receipt.update(
        {
            "schema_version": FINAL_TEST_BACKTEST_SCHEMA,
            "id": FINAL_TEST_STRATEGY_ID,
            "evaluation_split": "test_viewed_2026",
            "result_role": "CORRECTED_OPENED_OOS_DIAGNOSTIC",
            "selection_eligible": False,
            "used_for_selection": False,
            "test_data_access": "VIEWED",
            "strategy_locked_before_run": True,
            "analysis_lock_sha256": "9" * 64,
            "support": {
                "sessions": 1,
                "signal_rows": 300,
                "signal_cross_sections": 1,
                "candidate_min": 300,
                "candidate_median": 300.0,
                "candidate_max": 300,
                "actual_start": "2026-01-05",
                "actual_end": "2026-01-05",
            },
            "artifacts": {
                "daily_series": {
                    "path": final_series.relative_to(root).as_posix(),
                    "sha256": sha256_file(final_series),
                    "bytes": final_series.stat().st_size,
                }
            },
        }
    )
    final_receipt = seal(final_receipt)
    final_receipt_path = final_output / "backtest-receipt.json"
    final_receipt_path.write_text(json.dumps(final_receipt), encoding="utf-8")
    final_entry = {
        "id": FINAL_TEST_STRATEGY_ID,
        "state": "passed",
        "model_cell_id": "small-official-ft",
        "selection_eligible": False,
        "primary_signal": "mean",
        "evaluation_split": "test_viewed_2026",
        "result_role": "CORRECTED_OPENED_OOS_DIAGNOSTIC",
        "used_for_selection": False,
        "test_data_access": "VIEWED",
        "receipt_sha256": sha256_file(final_receipt_path),
        "receipt_path": final_receipt_path.relative_to(root).as_posix(),
        "summary": final_receipt["metrics"]["mean"],
    }
    catalog = seal(
        {
            "schema_version": CATALOG_SCHEMA_V2,
            "status": "PASS",
            "generated_at": "2026-08-13T18:00:00+00:00",
            "entries": [validation_entry, final_entry],
        }
    )
    active.historical_backtest_catalog.write_text(json.dumps(catalog), encoding="utf-8")
    return active, final_series


def test_backtest_api_is_get_only_and_keeps_paper_database_untouched(tmp_path: Path) -> None:
    active, _ = publish_backtest(tmp_path)
    client = TestClient(create_app(active))
    before = active.database_path.read_bytes()

    listed = client.get("/api/v1/research/backtests")
    assert listed.status_code == 200
    assert listed.json()["available"] is True
    assert listed.json()["backtests"][0]["strategy"]["topk"] == 50
    identifier = listed.json()["backtests"][0]["id"]
    assert client.get(f"/api/v1/research/backtests/{identifier}").status_code == 200
    series = client.get(f"/api/v1/research/backtests/{identifier}/series?signal=mean")
    assert series.status_code == 200
    assert series.json()["points"][0]["strategy"] == 0.01
    assert client.post("/api/v1/research/backtests").status_code == 405
    assert active.database_path.read_bytes() == before


def test_backtest_api_fails_closed_on_artifact_tampering(tmp_path: Path) -> None:
    active, series_path = publish_backtest(tmp_path)
    client = TestClient(create_app(active))
    series_path.write_text("tampered", encoding="utf-8")
    identifier = "official-demo-method-extended-pit-v1"
    assert client.get(f"/api/v1/research/backtests/{identifier}/series").status_code == 503


def test_missing_backtest_catalog_is_an_explicit_empty_state(tmp_path: Path) -> None:
    response = TestClient(create_app(settings(tmp_path))).get("/api/v1/research/backtests")
    assert response.json() == {
        "available": False,
        "generated_at": None,
        "backtests": [],
    }


def test_dual_catalog_exposes_validation_and_opened_final_test_without_mutation(
    tmp_path: Path,
) -> None:
    active, _ = publish_dual_backtest(tmp_path)
    client = TestClient(create_app(active))
    before = active.database_path.read_bytes()
    listed = client.get("/api/v1/research/backtests")
    assert listed.status_code == 200
    entries = listed.json()["backtests"]
    assert {entry["evaluation_split"] for entry in entries} == {
        "validation_2025",
        "test_viewed_2026",
    }
    final = next(entry for entry in entries if entry["evaluation_split"] == "test_viewed_2026")
    assert final["selection_eligible"] is False
    assert final["used_for_selection"] is False
    assert final["test_data_access"] == "VIEWED"
    series = client.get(
        f"/api/v1/research/backtests/{FINAL_TEST_STRATEGY_ID}/series?signal=mean"
    )
    assert series.status_code == 200
    assert series.json()["points"][0]["session"] == "2026-01-05"
    assert active.database_path.read_bytes() == before
