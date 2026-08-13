from __future__ import annotations

import json
from pathlib import Path

import pytest
from elanquant.contracts.official_demo import (
    BACKTEST_SCHEMA,
    CATALOG_SCHEMA,
    EXPECTED_EXECUTION,
    EXPECTED_STRATEGY,
    SIGNAL_SCHEMA,
    canonical_hash,
    standardized_close_signals,
    validate_backtest_catalog,
    validate_backtest_receipt,
    validate_signal_receipt,
)


def seal(payload: dict[str, object]) -> dict[str, object]:
    payload["receipt_hash"] = canonical_hash(payload)
    return payload


def signal_receipt() -> dict[str, object]:
    return seal(
        {
            "schema_version": SIGNAL_SCHEMA,
            "status": "PASS",
            "id": "official-demo-method-extended-pit-v1",
            "track_kind": "OFFICIAL_DEMO_METHOD",
            "model_cell_id": "small-official-ft",
            "generated_at": "2026-08-13T00:00:00+00:00",
            "selection_split": "validation_2025",
            "test_viewed_consumed": False,
            "primary_signal": "mean",
            "signals": ["mean", "last", "max", "min"],
            "upstream_commit": "1" * 40,
            "training_matrix_sha256": "2" * 64,
            "tokenizer_sha256": "3" * 64,
            "predictor_sha256": "4" * 64,
            "model_config_sha256": "5" * 64,
            "dataset_manifest_sha256": "6" * 64,
            "dataset_file_sha256": "7" * 64,
            "generator_code_sha256": "8" * 64,
            "rng_state_before_sha256": "9" * 64,
            "rng_state_after_sha256": "a" * 64,
            "normalization": {
                "policy": "INSTANCE_PER_SYMBOL_90_SESSION",
                "lookback": 90,
                "predict": 10,
                "epsilon": 1e-5,
                "clip": 5.0,
                "feature_order": ["open", "high", "low", "close", "vol", "amt"],
                "close_index": 3,
            },
            "inference": {
                "T": 0.6,
                "top_p": 0.9,
                "top_k": 0,
                "sample_count": 5,
                "batch_size": 1000,
                "effective_series_batch": 200,
                "seed": 100,
            },
            "runtime": {
                "python": "3.12.0",
                "torch": "2.7.0",
                "cuda": "12.8",
                "numpy": "2.0.0",
                "pandas": "2.2.0",
                "device": "cuda:1",
                "gpu_name": "NVIDIA RTX 5090",
            },
            "support": {
                "rows": 300,
                "cross_sections": 10,
                "anchor_set_sha256": "b" * 64,
            },
            "artifacts": {
                "signals": {
                    "path": "runs/backtests/demo/signals.csv",
                    "sha256": "c" * 64,
                    "bytes": 10,
                }
            },
        }
    )


def backtest_receipt() -> dict[str, object]:
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
    return seal(
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
                "sessions": 100,
                "signal_rows": 30_000,
                "signal_cross_sections": 100,
                "candidate_min": 250,
                "candidate_median": 290.0,
                "candidate_max": 300,
                "actual_start": "2025-01-02",
                "actual_end": "2025-12-31",
            },
            "metrics": metrics,
            "curve_semantics": {
                "official": "Arithmetic cumulative sum.",
                "derived": "Compounded NAV extension.",
            },
            "artifacts": {
                "daily_series": {
                    "path": "runs/backtests/demo/daily-series.csv",
                    "sha256": "1" * 64,
                    "bytes": 20,
                }
            },
            "deviations": ["extended PIT data and split"],
        }
    )


def test_standardized_close_signals_match_pinned_demo_formulas() -> None:
    values = [float(value) for value in range(1, 11)]
    signals = standardized_close_signals(values, 2.0)
    assert signals == {"mean": 3.5, "last": 8.0, "max": 8.0, "min": -1.0}


def test_signal_receipt_rejects_percentage_or_ten_sample_substitution() -> None:
    receipt = signal_receipt()
    validate_signal_receipt(receipt)
    inference = receipt["inference"]
    assert isinstance(inference, dict)
    inference["sample_count"] = 10
    receipt["receipt_hash"] = canonical_hash(
        {key: value for key, value in receipt.items() if key != "receipt_hash"}
    )
    with pytest.raises(RuntimeError, match="inference"):
        validate_signal_receipt(receipt)


def test_backtest_receipt_enforces_top50_drop5_hold5_and_selection_firewall() -> None:
    receipt = backtest_receipt()
    validate_backtest_receipt(receipt)
    strategy = receipt["strategy"]
    assert isinstance(strategy, dict)
    strategy["topk"] = 3
    receipt["receipt_hash"] = canonical_hash(
        {key: value for key, value in receipt.items() if key != "receipt_hash"}
    )
    with pytest.raises(RuntimeError, match="TopkDropout"):
        validate_backtest_receipt(receipt)

    receipt = backtest_receipt()
    receipt["test_viewed_consumed"] = True
    receipt["receipt_hash"] = canonical_hash(
        {key: value for key, value in receipt.items() if key != "receipt_hash"}
    )
    with pytest.raises(RuntimeError, match="firewall"):
        validate_backtest_receipt(receipt)


def test_catalog_rejects_path_traversal_and_nonfinite_metrics() -> None:
    receipt = backtest_receipt()
    summary = receipt["metrics"]
    assert isinstance(summary, dict)
    entry = {
        "id": "official-demo-method-extended-pit-v1",
        "state": "passed",
        "model_cell_id": "small-official-ft",
        "selection_eligible": True,
        "primary_signal": "mean",
        "selection_split": "validation_2025",
        "test_viewed_consumed": False,
        "receipt_sha256": "a" * 64,
        "receipt_path": "runs/backtests/demo/backtest-receipt.json",
        "summary": summary["mean"],
    }
    catalog = seal(
        {
            "schema_version": CATALOG_SCHEMA,
            "status": "PASS",
            "entries": [entry],
        }
    )
    validate_backtest_catalog(catalog)
    entry["receipt_path"] = "../secret.json"
    catalog["receipt_hash"] = canonical_hash(
        {key: value for key, value in catalog.items() if key != "receipt_hash"}
    )
    with pytest.raises(RuntimeError, match="allowlisted"):
        validate_backtest_catalog(catalog)


def test_receipts_remain_strict_json_without_nan(tmp_path: Path) -> None:
    receipt = backtest_receipt()
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt, allow_nan=False), encoding="utf-8")
    assert validate_backtest_receipt(json.loads(path.read_text(encoding="utf-8")))
