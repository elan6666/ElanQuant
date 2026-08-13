from __future__ import annotations

import csv
import json
from pathlib import Path

from elanquant.api.app import create_app
from elanquant.contracts.official_demo import (
    BACKTEST_SCHEMA,
    CATALOG_SCHEMA,
    EXPECTED_EXECUTION,
    EXPECTED_STRATEGY,
    canonical_hash,
    sha256_file,
)
from elanquant.settings import Settings
from fastapi.testclient import TestClient


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
