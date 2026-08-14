from __future__ import annotations

import pytest
from elanquant.contracts.historical_variants import (
    COMPARISON_GROUP_ID,
    EXECUTION_DOMAIN,
    HISTORICAL_CATALOG_SCHEMA,
    HISTORICAL_CATALOG_SCHEMA_V2,
    HOLDINGS_COLUMNS,
    HOLDINGS_RECEIPT_SCHEMA,
    HOLDINGS_SCHEMA,
    SPLITS,
    TOP3_OPENED_ID_V2,
    TOP3_PUBLIC_VARIANT,
    TOP3_STRATEGY,
    TOP3_STRATEGY_ROLE,
    TOP3_VALIDATION_ID_V2,
    TOP3_VARIANT_ID,
    TOP50_PUBLIC_VARIANT,
    TOP50_STRATEGY_ROLE,
    VARIANT_BACKTEST_SCHEMA,
    VARIANT_BACKTEST_SCHEMA_V2,
    VARIANT_LOCK_SCHEMA,
    validate_historical_catalog,
    validate_holdings_receipt,
    validate_holdings_records,
    validate_variant_backtest_receipt,
    validate_variant_lock,
)
from elanquant.contracts.official_demo import (
    CATALOG_SCHEMA,
    EXPECTED_EXECUTION,
    EXPECTED_STRATEGY,
    FINAL_TEST_STRATEGY_ID,
    SIGNALS,
    STRATEGY_ID,
    canonical_hash,
)


def seal(payload: dict[str, object]) -> dict[str, object]:
    payload["receipt_hash"] = canonical_hash(payload)
    return payload


def source(split: str, character: str) -> dict[str, object]:
    return {
        "split": split,
        "track_id": SPLITS[split]["source_track_id"],
        "signal_receipt_path": f"runs/{split}/signal-receipt.json",
        "signal_receipt_sha256": character * 64,
        "signal_artifact_sha256": "a" * 64,
        "provider_receipt_path": f"runs/{split}/provider-receipt.json",
        "provider_receipt_sha256": "b" * 64,
        "provider_tree_sha256": "c" * 64,
        "support": {
            "rows": 100,
            "cross_sections": 10,
            "anchor_set_sha256": "d" * 64,
        },
    }


def variant_lock() -> dict[str, object]:
    return seal(
        {
            "schema_version": VARIANT_LOCK_SCHEMA,
            "status": "PASS",
            "id": TOP3_VARIANT_ID,
            "model_cell_id": "small-official-ft",
            "primary_signal": "mean",
            "signals": list(SIGNALS),
            "strategy": dict(TOP3_STRATEGY),
            "execution": dict(EXPECTED_EXECUTION),
            "execution_domain": EXECUTION_DOMAIN,
            "online_paper_equivalent": False,
            "promotion_eligible": False,
            "selection_eligible": False,
            "used_for_selection": False,
            "post_hoc_after_test_viewed": True,
            "runner_path": "source/scripts/server/run_historical_top3_variant.py",
            "contract_path": "source/backend/src/elanquant/contracts/historical_variants.py",
            "runner_sha256": "1" * 64,
            "contract_sha256": "2" * 64,
            "qlib_version": "0.9.7",
            "qlib_metadata_sha256": "3" * 64,
            "qlib_record_sha256": "4" * 64,
            "qlib_source_tree_sha256": "5" * 64,
            "training_matrix_sha256": "6" * 64,
            "tokenizer_sha256": "7" * 64,
            "predictor_sha256": "8" * 64,
            "model_config_sha256": "9" * 64,
            "dataset_manifest_sha256": "a" * 64,
            "sources": [source("validation_2025", "e"), source("test_viewed_2026", "f")],
        }
    )


def metrics() -> dict[str, dict[str, float]]:
    return {
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
            "turnover_mean": 0.2,
        }
        for signal in SIGNALS
    }


def variant_receipt(split: str) -> dict[str, object]:
    contract = SPLITS[split]
    year = contract["year"]
    return seal(
        {
            "schema_version": VARIANT_BACKTEST_SCHEMA,
            "status": "PASS",
            "id": contract["variant_receipt_id"],
            "model_cell_id": "small-official-ft",
            "primary_signal": "mean",
            "strategy_variant_id": TOP3_PUBLIC_VARIANT,
            "variant_definition_id": TOP3_VARIANT_ID,
            "strategy_role": TOP3_STRATEGY_ROLE,
            "comparison_group_id": COMPARISON_GROUP_ID,
            "evaluation_split": split,
            "result_role": contract["result_role"],
            "source_backtest_id": contract["source_track_id"],
            "test_data_access": contract["test_data_access"],
            "execution_domain": EXECUTION_DOMAIN,
            "online_paper_equivalent": False,
            "promotion_eligible": False,
            "selection_eligible": False,
            "used_for_selection": False,
            "variant_lock_sha256": "1" * 64,
            "source_signal_receipt_sha256": "2" * 64,
            "source_provider_receipt_sha256": "3" * 64,
            "backtest_code_sha256": "4" * 64,
            "qlib": {
                "version": "0.9.7",
                "metadata_sha256": "5" * 64,
                "record_sha256": "6" * 64,
                "source_tree_sha256": "7" * 64,
            },
            "strategy": dict(TOP3_STRATEGY),
            "execution": dict(EXPECTED_EXECUTION),
            "support": {
                "sessions": 100,
                "actual_start": f"{year}-01-02",
            },
            "observability": {
                "turnover_exposed": True,
                "position_count_exposed": True,
            },
            "metrics": metrics(),
            "artifacts": {
                "daily_series": {"path": f"runs/{split}/daily.csv", "sha256": "8" * 64},
                "raw_report": {"path": f"runs/{split}/raw.csv", "sha256": "9" * 64},
            },
        }
    )


def catalog_entry(split: str, top3: bool) -> dict[str, object]:
    contract = SPLITS[split]
    return {
        "id": contract["variant_receipt_id"] if top3 else contract["source_track_id"],
        "state": "passed",
        "model_cell_id": "small-official-ft",
        "primary_signal": "mean",
        "strategy_variant_id": TOP3_PUBLIC_VARIANT if top3 else TOP50_PUBLIC_VARIANT,
        "strategy_role": TOP3_STRATEGY_ROLE if top3 else TOP50_STRATEGY_ROLE,
        "comparison_group_id": COMPARISON_GROUP_ID,
        "evaluation_split": split,
        "result_role": (
            contract["result_role"]
            if top3
            else (
                "TRAINING_VALIDATION_CHECKPOINT_SELECTION"
                if split == "validation_2025"
                else "CORRECTED_OPENED_OOS_DIAGNOSTIC"
            )
        ),
        "used_for_selection": not top3 and split == "validation_2025",
        "test_data_access": contract["test_data_access"],
        "source_backtest_id": contract["source_track_id"] if top3 else None,
        "execution_domain": EXECUTION_DOMAIN,
        "online_paper_equivalent": False,
        "promotion_eligible": False,
        "selection_eligible": not top3 and split == "validation_2025",
        "strategy": dict(TOP3_STRATEGY if top3 else EXPECTED_STRATEGY),
        "receipt_path": f"runs/{split}/{'top3' if top3 else 'top50'}/receipt.json",
        "receipt_sha256": "a" * 64,
        "summary": metrics()["mean"],
        "source": {
            "backtest_receipt_sha256": "b" * 64,
            "signal_receipt_sha256": "c" * 64,
            "provider_receipt_sha256": "d" * 64,
        },
    }


def test_variant_lock_pins_strategy_and_two_sources() -> None:
    validate_variant_lock(variant_lock())
    changed = variant_lock()
    changed["strategy"] = {**TOP3_STRATEGY, "risk_degree": 1.0}
    changed = seal({key: value for key, value in changed.items() if key != "receipt_hash"})
    with pytest.raises(RuntimeError, match="protocol"):
        validate_variant_lock(changed)


@pytest.mark.parametrize("split", tuple(SPLITS))
def test_variant_receipt_has_independent_strategy_and_result_roles(split: str) -> None:
    validate_variant_backtest_receipt(variant_receipt(split))
    changed = variant_receipt(split)
    changed["strategy_role"] = changed["result_role"]
    changed = seal({key: value for key, value in changed.items() if key != "receipt_hash"})
    with pytest.raises(RuntimeError, match="firewall"):
        validate_variant_backtest_receipt(changed)


def test_catalog_requires_exact_two_by_two_public_contract() -> None:
    payload = seal(
        {
            "schema_version": HISTORICAL_CATALOG_SCHEMA,
            "status": "PASS",
            "comparison_group_id": COMPARISON_GROUP_ID,
            "entries": [
                catalog_entry("validation_2025", False),
                catalog_entry("validation_2025", True),
                catalog_entry("test_viewed_2026", False),
                catalog_entry("test_viewed_2026", True),
            ],
        }
    )
    validate_historical_catalog(payload)
    top50 = payload["entries"][0]
    assert isinstance(top50, dict)
    top50["source_backtest_id"] = STRATEGY_ID
    payload.pop("receipt_hash")
    seal(payload)
    with pytest.raises(RuntimeError, match="must be null"):
        validate_historical_catalog(payload)


def test_public_variant_values_are_exact() -> None:
    assert TOP50_PUBLIC_VARIANT == "official_top50"
    assert TOP3_PUBLIC_VARIANT == "historical_top3"
    assert SPLITS["test_viewed_2026"]["source_track_id"] == FINAL_TEST_STRATEGY_ID


def test_legacy_v1_catalog_still_dispatches_to_official_validator() -> None:
    legacy = seal(
        {
            "schema_version": CATALOG_SCHEMA,
            "status": "PASS",
            "entries": [
                {
                    "id": STRATEGY_ID,
                    "state": "passed",
                    "model_cell_id": "small-official-ft",
                    "selection_eligible": True,
                    "primary_signal": "mean",
                    "selection_split": "validation_2025",
                    "test_viewed_consumed": False,
                    "receipt_sha256": "1" * 64,
                    "receipt_path": "runs/legacy/backtest-receipt.json",
                    "summary": {
                        "total_return_with_cost": 0.1,
                        "benchmark_return": 0.08,
                        "excess_return_with_cost": 0.02,
                        "annualized_return_with_cost": 0.11,
                        "information_ratio_with_cost": 0.3,
                        "max_drawdown_with_cost": -0.06,
                    },
                }
            ],
        }
    )
    validate_historical_catalog(legacy)


def holdings_rows() -> list[dict[str, object]]:
    return [
        {
            "session": "2025-01-02",
            "signal": signal,
            "instrument": "" if signal == "min" else "SH600000",
            "is_empty": signal == "min",
            "amount": 0.0 if signal == "min" else 100.0,
            "weight": 0.0 if signal == "min" else 0.25,
            "value": 0.0 if signal == "min" else 1000.0,
        }
        for signal in sorted(SIGNALS)
    ]


def test_holdings_records_require_finite_values_and_explicit_empty_sessions() -> None:
    support = validate_holdings_records(holdings_rows(), expected_sessions=1)
    assert support == {
        "rows": 4,
        "sessions": 1,
        "session_signal_pairs": 4,
        "empty_session_signal_pairs": 1,
    }
    invalid = holdings_rows()
    invalid[0]["amount"] = float("nan")
    with pytest.raises(RuntimeError, match="not finite"):
        validate_holdings_records(invalid, expected_sessions=1)
    missing = holdings_rows()[:-1]
    with pytest.raises(RuntimeError, match="coverage"):
        validate_holdings_records(missing, expected_sessions=1)


def test_holdings_receipt_binds_backtest_and_artifact() -> None:
    payload = seal(
        {
            "schema_version": HOLDINGS_RECEIPT_SCHEMA,
            "status": "PASS",
            "id": f"{STRATEGY_ID}-holdings-v1",
            "backtest_id": STRATEGY_ID,
            "evaluation_split": "validation_2025",
            "strategy_variant_id": TOP50_PUBLIC_VARIANT,
            "execution_domain": EXECUTION_DOMAIN,
            "online_paper_equivalent": False,
            "promotion_eligible": False,
            "backtest_receipt_path": "runs/top50/backtest-receipt.json",
            "backtest_receipt_sha256": "1" * 64,
            "generator_code_sha256": "2" * 64,
            "source_signal_receipt_sha256": "3" * 64,
            "source_provider_receipt_sha256": "4" * 64,
            "metrics_comparison": {
                "status": "PASS",
                "absolute_tolerance": 1e-12,
                "compared_values": 36,
                "maximum_absolute_difference": 0.0,
            },
            "artifact": {
                "path": "runs/top50/daily-holdings.csv",
                "sha256": "5" * 64,
                "bytes": 100,
                "schema_version": HOLDINGS_SCHEMA,
                "columns": list(HOLDINGS_COLUMNS),
                "rows": 400,
                "sessions": 100,
                "session_signal_pairs": 400,
                "empty_session_signal_pairs": 0,
            },
        }
    )
    validate_holdings_receipt(payload)
    payload.pop("receipt_hash")
    artifact = payload["artifact"]
    assert isinstance(artifact, dict)
    artifact["columns"] = ["session", "instrument"]
    seal(payload)
    with pytest.raises(RuntimeError, match="artifact contract"):
        validate_holdings_receipt(payload)


def test_v2_variant_receipt_requires_sealed_holdings_artifact() -> None:
    receipt = variant_receipt("validation_2025")
    receipt.pop("receipt_hash")
    receipt["schema_version"] = VARIANT_BACKTEST_SCHEMA_V2
    receipt["id"] = "official-demo-top3-drop1-hold5-validation-2025-v2"
    receipt["variant_definition_id"] = "qlib-top3-drop1-hold5-variant-v2"
    artifacts = receipt["artifacts"]
    assert isinstance(artifacts, dict)
    for artifact in artifacts.values():
        assert isinstance(artifact, dict)
        artifact["bytes"] = 100
    artifacts["holdings"] = {
        "path": "runs/validation_2025/daily-holdings.csv",
        "sha256": "a" * 64,
        "bytes": 100,
        "schema_version": HOLDINGS_SCHEMA,
        "columns": list(HOLDINGS_COLUMNS),
        "rows": 400,
        "sessions": 100,
        "session_signal_pairs": 400,
        "empty_session_signal_pairs": 0,
    }
    seal(receipt)
    validate_variant_backtest_receipt(receipt)
    receipt.pop("receipt_hash")
    artifacts.pop("holdings")
    seal(receipt)
    with pytest.raises(RuntimeError, match="artifacts are not exact"):
        validate_variant_backtest_receipt(receipt)


def test_v2_catalog_requires_holdings_receipt_pointer_for_all_four_entries() -> None:
    entries = [
        catalog_entry("validation_2025", False),
        catalog_entry("validation_2025", True),
        catalog_entry("test_viewed_2026", False),
        catalog_entry("test_viewed_2026", True),
    ]
    entries[1]["id"] = TOP3_VALIDATION_ID_V2
    entries[3]["id"] = TOP3_OPENED_ID_V2
    for index, entry in enumerate(entries):
        entry["holdings"] = {
            "receipt_path": f"runs/holdings/{index}/holdings-receipt.json",
            "receipt_sha256": f"{index + 1}" * 64,
        }
    payload = seal(
        {
            "schema_version": HISTORICAL_CATALOG_SCHEMA_V2,
            "status": "PASS",
            "comparison_group_id": COMPARISON_GROUP_ID,
            "entries": entries,
        }
    )
    validate_historical_catalog(payload)
    payload.pop("receipt_hash")
    entries[0].pop("holdings")
    seal(payload)
    with pytest.raises(RuntimeError, match="holdings source"):
        validate_historical_catalog(payload)
