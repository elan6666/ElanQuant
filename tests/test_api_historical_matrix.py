from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from elanquant.contracts.historical_matrix import (
    BACKTEST_SCHEMA,
    CATALOG_SCHEMA,
    HOLDINGS_SCHEMA,
    MODEL_CELLS,
    SPLITS,
    VARIANTS,
    backtest_id,
)
from fastapi.testclient import TestClient

from elanquant.api.app import create_app
from elanquant.contracts.official_demo import EXPECTED_EXECUTION, SIGNALS, canonical_hash
from elanquant.settings import Settings

SHA = "a" * 64


def write_csv(path: Path, *, holdings: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if holdings:
        fields = ["session", "signal", "instrument", "is_empty", "amount", "weight", "value"]
        rows = [
            {
                "session": "2026-01-05",
                "signal": signal,
                "instrument": "600000.SH",
                "is_empty": "False",
                "amount": "100",
                "weight": "0.5",
                "value": "1000",
            }
            for signal in sorted(SIGNALS)
        ]
    else:
        fields = [
            "datetime",
            "signal",
            "additive_strategy_with_cost",
            "additive_benchmark",
            "additive_excess_with_cost",
            "compounded_strategy_nav",
            "compounded_benchmark_nav",
            "turnover",
            "position_count",
        ]
        rows = [
            {
                "datetime": "2026-01-05",
                "signal": signal,
                "additive_strategy_with_cost": "0.01",
                "additive_benchmark": "0.005",
                "additive_excess_with_cost": "0.005",
                "compounded_strategy_nav": "1.01",
                "compounded_benchmark_nav": "1.005",
                "turnover": "0.1",
                "position_count": "4",
            }
            for signal in SIGNALS
        ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def metric() -> dict[str, float]:
    return {
        "total_return_with_cost": 0.01,
        "benchmark_return": 0.005,
        "excess_return_without_cost": 0.006,
        "excess_return_with_cost": 0.005,
        "annualized_return_with_cost": 0.02,
        "annualized_excess_return_with_cost": 0.01,
        "information_ratio_with_cost": 0.2,
        "max_drawdown_with_cost": -0.01,
        "total_cost": 0.001,
        "turnover_mean": 0.1,
    }


def publish(tmp_path: Path) -> Settings:
    entries = []
    for model in MODEL_CELLS:
        for split in SPLITS:
            for variant in VARIANTS:
                identifier = backtest_id(model, split, variant)
                result = tmp_path / "runs" / identifier
                daily = result / "daily-series.csv"
                raw = result / "raw-report.csv"
                holdings = result / "daily-holdings.csv"
                write_csv(daily, holdings=False)
                write_csv(raw, holdings=False)
                write_csv(holdings, holdings=True)
                artifacts = {
                    "daily_series": {
                        "path": daily.relative_to(tmp_path).as_posix(),
                        "sha256": hashlib.sha256(daily.read_bytes()).hexdigest(),
                    },
                    "raw_report": {
                        "path": raw.relative_to(tmp_path).as_posix(),
                        "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
                    },
                    "holdings": {
                        "path": holdings.relative_to(tmp_path).as_posix(),
                        "sha256": hashlib.sha256(holdings.read_bytes()).hexdigest(),
                        "bytes": holdings.stat().st_size,
                        "schema_version": HOLDINGS_SCHEMA,
                        "columns": [
                            "session",
                            "signal",
                            "instrument",
                            "is_empty",
                            "amount",
                            "weight",
                            "value",
                        ],
                        "rows": 4,
                        "sessions": 1,
                        "session_signal_pairs": 4,
                        "empty_session_signal_pairs": 0,
                    },
                }
                metrics = {signal: metric() for signal in SIGNALS}
                receipt = {
                    "schema_version": BACKTEST_SCHEMA,
                    "status": "PASS",
                    "id": identifier,
                    "generated_at": "2026-08-14T00:00:00+00:00",
                    "model_cell_id": model,
                    "evaluation_split": split,
                    "strategy_variant_id": variant,
                    "primary_signal": "mean",
                    "strategy": VARIANTS[variant],
                    "execution": EXPECTED_EXECUTION,
                    "result_role": (
                        "POST_HOC_OPENED_MODEL_STRATEGY_DIAGNOSTIC"
                        if split == "test_viewed_2026"
                        else "POST_HOC_MODEL_STRATEGY_COMPARISON"
                    ),
                    "selection_eligible": False,
                    "used_for_selection": False,
                    "promotion_eligible": False,
                    "online_paper_equivalent": False,
                    "test_data_access": (
                        "VIEWED" if split == "test_viewed_2026" else "NOT_APPLICABLE"
                    ),
                    "matrix_lock_sha256": SHA,
                    "source_signal_receipt_sha256": SHA,
                    "source_provider_receipt_sha256": SHA,
                    "backtest_code_sha256": SHA,
                    "qlib": {
                        "version": "0.9.7",
                        "metadata_sha256": SHA,
                        "record_sha256": SHA,
                        "source_tree_sha256": SHA,
                    },
                    "support": {
                        "actual_start": "2026-01-05",
                        "actual_end": "2026-01-05",
                        "sessions": 1,
                        "signal_rows": 300,
                        "signal_cross_sections": 1,
                    },
                    "observability": {
                        "turnover_exposed": True,
                        "position_count_exposed": True,
                    },
                    "metrics": metrics,
                    "artifacts": artifacts,
                    "deviations": ["fixture"],
                }
                receipt["receipt_hash"] = canonical_hash(receipt)
                receipt_path = result / "backtest-receipt.json"
                receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
                receipt_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
                entries.append(
                    {
                        "id": identifier,
                        "state": "passed",
                        "model_cell_id": model,
                        "evaluation_split": split,
                        "strategy_variant_id": variant,
                        "selection_eligible": False,
                        "used_for_selection": False,
                        "promotion_eligible": False,
                        "online_paper_equivalent": False,
                        "receipt_path": receipt_path.relative_to(tmp_path).as_posix(),
                        "receipt_sha256": receipt_sha,
                        "summary": metrics["mean"],
                        "source": {
                            "signal_receipt_sha256": SHA,
                            "provider_receipt_sha256": SHA,
                        },
                        "support": receipt["support"],
                        "holdings": {
                            "artifact_path": artifacts["holdings"]["path"],
                            "artifact_sha256": artifacts["holdings"]["sha256"],
                        },
                    }
                )
    catalog = {
        "schema_version": CATALOG_SCHEMA,
        "status": "PASS",
        "generated_at": "2026-08-14T00:00:00+00:00",
        "entries": entries,
    }
    catalog["receipt_hash"] = canonical_hash(catalog)
    catalog_path = tmp_path / "releases" / "historical-backtest-catalog-v6.json"
    catalog_path.parent.mkdir(parents=True)
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    return Settings(
        database_path=tmp_path / "elanquant.sqlite3",
        artifact_root=tmp_path / "artifacts",
        frontend_dist=tmp_path / "missing-dist",
        historical_backtest_catalog=catalog_path,
    )


def test_api_serves_exact_matrix_series_and_holdings(tmp_path: Path) -> None:
    client = TestClient(create_app(publish(tmp_path)))
    listing = client.get("/api/v1/research/backtests")
    assert listing.status_code == 200
    assert len(listing.json()["backtests"]) == 24
    identifier = backtest_id("base-strict-pit", "test_viewed_2026", "historical_top3")
    detail = client.get(f"/api/v1/research/backtests/{identifier}")
    assert detail.status_code == 200
    assert detail.json()["backtest"]["model_cell_id"] == "base-strict-pit"
    series = client.get(f"/api/v1/research/backtests/{identifier}/series?signal=mean")
    assert series.status_code == 200
    holdings = client.get(f"/api/v1/research/backtests/{identifier}/holdings")
    assert holdings.status_code == 200
    assert holdings.json()["holdings"][0]["instrument"] == "600000.SH"
