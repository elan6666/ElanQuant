from __future__ import annotations

import copy

import pytest
from elanquant.contracts.historical_matrix import (
    BACKTEST_SCHEMA,
    CATALOG_SCHEMA,
    MODEL_CELLS,
    SPLITS,
    VARIANTS,
    backtest_id,
    validate_backtest_receipt,
    validate_catalog,
)

from elanquant.contracts.official_demo import EXPECTED_EXECUTION, SIGNALS, canonical_hash

SHA = "a" * 64


def sealed(payload: dict[str, object]) -> dict[str, object]:
    payload["receipt_hash"] = canonical_hash(payload)
    return payload


def backtest(model: str, split: str, variant: str) -> dict[str, object]:
    metrics = {
        signal: {
            "total_return_with_cost": 0.01,
            "benchmark_return": 0.02,
            "excess_return_without_cost": -0.005,
            "excess_return_with_cost": -0.01,
            "annualized_return_with_cost": 0.03,
            "annualized_excess_return_with_cost": -0.02,
            "information_ratio_with_cost": -0.1,
            "max_drawdown_with_cost": -0.05,
            "total_cost": 0.001,
            "turnover_mean": 0.1,
        }
        for signal in SIGNALS
    }
    return sealed(
        {
            "schema_version": BACKTEST_SCHEMA,
            "status": "PASS",
            "id": backtest_id(model, split, variant),
            "model_cell_id": model,
            "evaluation_split": split,
            "strategy_variant_id": variant,
            "primary_signal": "mean",
            "strategy": VARIANTS[variant],
            "execution": EXPECTED_EXECUTION,
            "selection_eligible": False,
            "used_for_selection": False,
            "promotion_eligible": False,
            "online_paper_equivalent": False,
            "test_data_access": "VIEWED" if split == "test_viewed_2026" else "NOT_APPLICABLE",
            "matrix_lock_sha256": SHA,
            "source_signal_receipt_sha256": SHA,
            "source_provider_receipt_sha256": SHA,
            "backtest_code_sha256": SHA,
            "metrics": metrics,
            "artifacts": {
                name: {"path": f"runs/{name}.csv", "sha256": SHA}
                for name in ("daily_series", "raw_report", "holdings")
            },
        }
    )


def catalog() -> dict[str, object]:
    entries = []
    for model in MODEL_CELLS:
        for split in SPLITS:
            for variant in VARIANTS:
                entries.append(
                    {
                        "id": backtest_id(model, split, variant),
                        "state": "passed",
                        "model_cell_id": model,
                        "evaluation_split": split,
                        "strategy_variant_id": variant,
                        "selection_eligible": False,
                        "used_for_selection": False,
                        "promotion_eligible": False,
                        "online_paper_equivalent": False,
                        "receipt_path": f"runs/{model}/{split}/{variant}/receipt.json",
                        "receipt_sha256": SHA,
                        "source": {
                            "signal_receipt_sha256": SHA,
                            "provider_receipt_sha256": SHA,
                        },
                        "support": {"sessions": 1, "signal_rows": 300},
                    }
                )
    return sealed(
        {
            "schema_version": CATALOG_SCHEMA,
            "status": "PASS",
            "entries": entries,
        }
    )


def test_all_six_model_backtest_cells_validate() -> None:
    for model in MODEL_CELLS:
        for split in SPLITS:
            for variant in VARIANTS:
                assert validate_backtest_receipt(backtest(model, split, variant))["id"]


def test_catalog_requires_exact_twenty_four_cells() -> None:
    payload = catalog()
    assert len(validate_catalog(payload)["entries"]) == 24
    missing = copy.deepcopy(payload)
    missing["entries"].pop()
    missing["receipt_hash"] = canonical_hash(
        {key: value for key, value in missing.items() if key != "receipt_hash"}
    )
    with pytest.raises(RuntimeError, match="size"):
        validate_catalog(missing)


def test_opened_split_cannot_be_selection_eligible() -> None:
    payload = backtest("base-strict-pit", "test_viewed_2026", "official_top50")
    payload["selection_eligible"] = True
    payload["receipt_hash"] = canonical_hash(
        {key: value for key, value in payload.items() if key != "receipt_hash"}
    )
    with pytest.raises(RuntimeError, match="identity"):
        validate_backtest_receipt(payload)
