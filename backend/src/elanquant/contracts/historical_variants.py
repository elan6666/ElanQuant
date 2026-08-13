from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from elanquant.contracts.official_demo import (
    CATALOG_SCHEMA,
    CATALOG_SCHEMA_V2,
    EXPECTED_EXECUTION,
    FINAL_TEST_STRATEGY_ID,
    MODEL_CELL,
    PRIMARY_SIGNAL,
    SIGNALS,
    STRATEGY_ID,
    require_sha,
    validate_backtest_catalog,
    validate_backtest_receipt,
    verify_canonical_receipt,
)

VARIANT_LOCK_SCHEMA = "elanquant_historical_variant_lock_v1"
VARIANT_LOCK_SCHEMA_V2 = "elanquant_historical_variant_lock_v2"
VARIANT_BACKTEST_SCHEMA = "elanquant_qlib_topkdrop_variant_v1"
VARIANT_BACKTEST_SCHEMA_V2 = "elanquant_qlib_topkdrop_variant_v2"
HISTORICAL_CATALOG_SCHEMA = "elanquant_historical_backtest_catalog_v3"
HISTORICAL_CATALOG_SCHEMA_V2 = "elanquant_historical_backtest_catalog_v4"
HOLDINGS_SCHEMA = "elanquant_historical_daily_holdings_v1"
HOLDINGS_RECEIPT_SCHEMA = "elanquant_historical_holdings_receipt_v1"
HOLDINGS_COLUMNS = (
    "session",
    "signal",
    "instrument",
    "is_empty",
    "amount",
    "weight",
    "value",
)

TOP3_VARIANT_ID = "qlib-top3-drop1-hold5-variant-v1"
TOP3_VALIDATION_ID = "official-demo-top3-drop1-hold5-validation-2025-v1"
TOP3_OPENED_ID = "official-demo-top3-drop1-hold5-corrected-opened-2026-v1"
TOP3_VARIANT_ID_V2 = "qlib-top3-drop1-hold5-variant-v2"
TOP3_VALIDATION_ID_V2 = "official-demo-top3-drop1-hold5-validation-2025-v2"
TOP3_OPENED_ID_V2 = "official-demo-top3-drop1-hold5-corrected-opened-2026-v2"
EXECUTION_DOMAIN = "HISTORICAL_QLIB_SIMULATION"
TOP50_PUBLIC_VARIANT = "official_top50"
TOP3_PUBLIC_VARIANT = "historical_top3"
COMPARISON_GROUP_ID = "top50-vs-top3-v1"
TOP50_STRATEGY_ROLE = "OFFICIAL_METHOD_BASELINE"
TOP3_STRATEGY_ROLE = "PORTFOLIO_SENSITIVITY_VARIANT"

TOP3_STRATEGY: dict[str, object] = {
    "topk": 3,
    "n_drop": 1,
    "hold_thresh": 5,
    "method_sell": "bottom",
    "method_buy": "top",
    "only_tradable": False,
    "forbid_all_trade_at_limit": True,
    "risk_degree": 0.95,
}

SPLITS: dict[str, dict[str, object]] = {
    "validation_2025": {
        "variant_receipt_id": TOP3_VALIDATION_ID,
        "source_track_id": STRATEGY_ID,
        "year": 2025,
        "result_role": "POST_HOC_HISTORICAL_SENSITIVITY",
        "test_data_access": "NOT_APPLICABLE",
    },
    "test_viewed_2026": {
        "variant_receipt_id": TOP3_OPENED_ID,
        "source_track_id": FINAL_TEST_STRATEGY_ID,
        "year": 2026,
        "result_role": "POST_HOC_OPENED_STRATEGY_DIAGNOSTIC",
        "test_data_access": "VIEWED",
    },
}
SPLITS_V2: dict[str, dict[str, object]] = {
    split: {
        **contract,
        "variant_receipt_id": (
            TOP3_VALIDATION_ID_V2 if split == "validation_2025" else TOP3_OPENED_ID_V2
        ),
    }
    for split, contract in SPLITS.items()
}


def _finite(value: object, identity: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"{identity} is not numeric")
    result = float(value)
    if not math.isfinite(result):
        raise RuntimeError(f"{identity} is not finite")
    return result


def _relative_path(value: object, identity: str) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"{identity} is absent")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise RuntimeError(f"{identity} is not a safe relative path")
    return value


def _validate_source(source: object, identity: str) -> dict[str, Any]:
    if not isinstance(source, dict):
        raise RuntimeError(f"{identity} is not an object")
    split = source.get("split")
    contract = SPLITS.get(str(split))
    if contract is None or source.get("track_id") != contract["source_track_id"]:
        raise RuntimeError(f"{identity} split or track is invalid")
    for field in (
        "signal_receipt_sha256",
        "signal_artifact_sha256",
        "provider_receipt_sha256",
        "provider_tree_sha256",
    ):
        require_sha(source.get(field), f"{identity}.{field}")
    _relative_path(source.get("signal_receipt_path"), f"{identity}.signal_receipt_path")
    _relative_path(source.get("provider_receipt_path"), f"{identity}.provider_receipt_path")
    support = source.get("support")
    if not isinstance(support, dict):
        raise RuntimeError(f"{identity}.support is absent")
    for field in ("rows", "cross_sections"):
        if isinstance(support.get(field), bool) or not isinstance(support.get(field), int):
            raise RuntimeError(f"{identity}.support.{field} is invalid")
    require_sha(support.get("anchor_set_sha256"), f"{identity}.support.anchor_set_sha256")
    return source


def validate_holdings_records(
    records: object,
    *,
    expected_sessions: int,
    expected_signals: tuple[str, ...] = SIGNALS,
) -> dict[str, int]:
    """Validate canonical daily holdings, including explicit empty session/signal rows."""

    if not isinstance(records, list) or not records:
        raise RuntimeError("daily holdings records are absent")
    if expected_sessions <= 0 or not expected_signals:
        raise RuntimeError("daily holdings expected support is invalid")
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    previous_sort_key: tuple[str, str, bool, str] | None = None
    for index, record in enumerate(records):
        identity = f"holdings[{index}]"
        if not isinstance(record, dict) or set(record) != set(HOLDINGS_COLUMNS):
            raise RuntimeError(f"{identity} columns are not exact")
        session = record.get("session")
        signal = record.get("signal")
        instrument = record.get("instrument")
        is_empty = record.get("is_empty")
        if (
            not isinstance(session, str)
            or len(session) != 10
            or session[4] != "-"
            or session[7] != "-"
            or signal not in expected_signals
            or not isinstance(instrument, str)
            or not isinstance(is_empty, bool)
        ):
            raise RuntimeError(f"{identity} identity is invalid")
        amount = _finite(record.get("amount"), f"{identity}.amount")
        weight = _finite(record.get("weight"), f"{identity}.weight")
        value = _finite(record.get("value"), f"{identity}.value")
        if amount < 0 or weight < 0 or value < 0:
            raise RuntimeError(f"{identity} contains a negative holding")
        if is_empty:
            if instrument or any(number != 0.0 for number in (amount, weight, value)):
                raise RuntimeError(f"{identity} empty row is not zero-valued")
        elif not instrument:
            raise RuntimeError(f"{identity} held instrument is absent")
        sort_key = (session, str(signal), not is_empty, instrument)
        if previous_sort_key is not None and sort_key < previous_sort_key:
            raise RuntimeError("daily holdings records are not canonically sorted")
        previous_sort_key = sort_key
        grouped.setdefault((session, str(signal)), []).append(record)
    sessions = {session for session, _ in grouped}
    if len(sessions) != expected_sessions or len(grouped) != expected_sessions * len(
        expected_signals
    ):
        raise RuntimeError("daily holdings session/signal coverage is not exact")
    empty_pairs = 0
    for (session, signal), rows in grouped.items():
        if signal not in expected_signals:
            raise RuntimeError(f"daily holdings signal is invalid: {session}/{signal}")
        empty_rows = [row for row in rows if row["is_empty"]]
        if empty_rows:
            if len(rows) != 1:
                raise RuntimeError(f"daily holdings mixes empty and held rows: {session}/{signal}")
            empty_pairs += 1
            continue
        instruments = [str(row["instrument"]) for row in rows]
        if len(instruments) != len(set(instruments)):
            raise RuntimeError(f"daily holdings instruments are duplicated: {session}/{signal}")
    return {
        "rows": len(records),
        "sessions": len(sessions),
        "session_signal_pairs": len(grouped),
        "empty_session_signal_pairs": empty_pairs,
    }


def validate_holdings_receipt(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("historical holdings receipt is not an object")
    verify_canonical_receipt(payload, HOLDINGS_RECEIPT_SCHEMA)
    backtest_id = payload.get("backtest_id")
    contracts: dict[str, tuple[str, str]] = {
        STRATEGY_ID: ("validation_2025", TOP50_PUBLIC_VARIANT),
        FINAL_TEST_STRATEGY_ID: ("test_viewed_2026", TOP50_PUBLIC_VARIANT),
        TOP3_VALIDATION_ID_V2: ("validation_2025", TOP3_PUBLIC_VARIANT),
        TOP3_OPENED_ID_V2: ("test_viewed_2026", TOP3_PUBLIC_VARIANT),
    }
    contract = contracts.get(str(backtest_id))
    if (
        contract is None
        or payload.get("id") != f"{backtest_id}-holdings-v1"
        or payload.get("evaluation_split") != contract[0]
        or payload.get("strategy_variant_id") != contract[1]
        or payload.get("execution_domain") != EXECUTION_DOMAIN
        or payload.get("online_paper_equivalent") is not False
        or payload.get("promotion_eligible") is not False
    ):
        raise RuntimeError("historical holdings receipt identity is invalid")
    _relative_path(payload.get("backtest_receipt_path"), "holdings.backtest_receipt_path")
    for field in (
        "backtest_receipt_sha256",
        "generator_code_sha256",
        "source_signal_receipt_sha256",
        "source_provider_receipt_sha256",
    ):
        require_sha(payload.get(field), f"holdings.{field}")
    comparison = payload.get("metrics_comparison")
    if (
        not isinstance(comparison, dict)
        or comparison.get("status") != "PASS"
        or comparison.get("absolute_tolerance") != 1e-12
        or not isinstance(comparison.get("compared_values"), int)
        or comparison["compared_values"] <= 0
        or _finite(comparison.get("maximum_absolute_difference"), "holdings.max_diff")
        > comparison["absolute_tolerance"]
    ):
        raise RuntimeError("historical holdings metrics comparison is invalid")
    artifact = payload.get("artifact")
    if not isinstance(artifact, dict):
        raise RuntimeError("historical holdings artifact is absent")
    _relative_path(artifact.get("path"), "holdings.artifact.path")
    require_sha(artifact.get("sha256"), "holdings.artifact.sha256")
    if (
        artifact.get("schema_version") != HOLDINGS_SCHEMA
        or artifact.get("columns") != list(HOLDINGS_COLUMNS)
        or any(
            isinstance(artifact.get(field), bool) or not isinstance(artifact.get(field), int)
            for field in (
                "bytes",
                "rows",
                "sessions",
                "session_signal_pairs",
                "empty_session_signal_pairs",
            )
        )
        or artifact["bytes"] <= 0
        or artifact["rows"] < artifact["session_signal_pairs"]
        or artifact["sessions"] <= 0
        or artifact["session_signal_pairs"] != artifact["sessions"] * len(SIGNALS)
    ):
        raise RuntimeError("historical holdings artifact contract is invalid")
    return payload


def validate_variant_lock(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("historical variant lock is not an object")
    schema = payload.get("schema_version")
    if schema not in {VARIANT_LOCK_SCHEMA, VARIANT_LOCK_SCHEMA_V2}:
        raise RuntimeError("historical variant lock schema is invalid")
    verify_canonical_receipt(payload, str(schema))
    variant_id = TOP3_VARIANT_ID_V2 if schema == VARIANT_LOCK_SCHEMA_V2 else TOP3_VARIANT_ID
    if (
        payload.get("id") != variant_id
        or payload.get("model_cell_id") != MODEL_CELL
        or payload.get("primary_signal") != PRIMARY_SIGNAL
        or payload.get("signals") != list(SIGNALS)
        or payload.get("strategy") != TOP3_STRATEGY
        or payload.get("execution") != EXPECTED_EXECUTION
        or payload.get("execution_domain") != EXECUTION_DOMAIN
        or payload.get("online_paper_equivalent") is not False
        or payload.get("promotion_eligible") is not False
        or payload.get("selection_eligible") is not False
        or payload.get("used_for_selection") is not False
        or payload.get("post_hoc_after_test_viewed") is not True
    ):
        raise RuntimeError("historical variant lock protocol is invalid")
    for field in (
        "runner_sha256",
        "contract_sha256",
        "qlib_metadata_sha256",
        "qlib_record_sha256",
        "qlib_source_tree_sha256",
        "training_matrix_sha256",
        "tokenizer_sha256",
        "predictor_sha256",
        "model_config_sha256",
        "dataset_manifest_sha256",
    ):
        require_sha(payload.get(field), f"variant_lock.{field}")
    _relative_path(payload.get("runner_path"), "variant_lock.runner_path")
    _relative_path(payload.get("contract_path"), "variant_lock.contract_path")
    if payload.get("qlib_version") != "0.9.7":
        raise RuntimeError("historical variant lock Qlib version is invalid")
    sources = payload.get("sources")
    if not isinstance(sources, list) or len(sources) != 2:
        raise RuntimeError("historical variant lock requires two sources")
    validated = [
        _validate_source(source, f"variant_lock.sources[{i}]") for i, source in enumerate(sources)
    ]
    if {source["split"] for source in validated} != set(SPLITS):
        raise RuntimeError("historical variant lock source splits are not exact")
    return payload


def validate_variant_backtest_receipt(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("historical variant backtest receipt is not an object")
    schema = payload.get("schema_version")
    if schema not in {VARIANT_BACKTEST_SCHEMA, VARIANT_BACKTEST_SCHEMA_V2}:
        raise RuntimeError("historical variant backtest schema is invalid")
    verify_canonical_receipt(payload, str(schema))
    holdings_required = schema == VARIANT_BACKTEST_SCHEMA_V2
    split_contracts = SPLITS_V2 if holdings_required else SPLITS
    split = payload.get("evaluation_split")
    contract = split_contracts.get(str(split))
    definition_id = TOP3_VARIANT_ID_V2 if holdings_required else TOP3_VARIANT_ID
    if (
        contract is None
        or payload.get("id") != contract["variant_receipt_id"]
        or payload.get("source_backtest_id") != contract["source_track_id"]
        or payload.get("evaluation_split") != split
        or payload.get("result_role") != contract["result_role"]
        or payload.get("strategy_role") != TOP3_STRATEGY_ROLE
        or payload.get("test_data_access") != contract["test_data_access"]
        or payload.get("comparison_group_id") != COMPARISON_GROUP_ID
        or payload.get("strategy_variant_id") != TOP3_PUBLIC_VARIANT
        or payload.get("variant_definition_id") != definition_id
        or payload.get("model_cell_id") != MODEL_CELL
        or payload.get("primary_signal") != PRIMARY_SIGNAL
        or payload.get("strategy") != TOP3_STRATEGY
        or payload.get("execution") != EXPECTED_EXECUTION
        or payload.get("execution_domain") != EXECUTION_DOMAIN
        or payload.get("online_paper_equivalent") is not False
        or payload.get("promotion_eligible") is not False
        or payload.get("selection_eligible") is not False
        or payload.get("used_for_selection") is not False
    ):
        raise RuntimeError("historical variant receipt identity or firewall is invalid")
    for field in (
        "variant_lock_sha256",
        "source_signal_receipt_sha256",
        "source_provider_receipt_sha256",
        "backtest_code_sha256",
    ):
        require_sha(payload.get(field), f"variant_backtest.{field}")
    qlib = payload.get("qlib")
    if not isinstance(qlib, dict) or qlib.get("version") != "0.9.7":
        raise RuntimeError("historical variant Qlib identity is invalid")
    for field in ("metadata_sha256", "record_sha256", "source_tree_sha256"):
        require_sha(qlib.get(field), f"variant_backtest.qlib.{field}")
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict) or set(metrics) != set(SIGNALS):
        raise RuntimeError("historical variant metrics are not exact")
    for signal, values in metrics.items():
        if not isinstance(values, dict):
            raise RuntimeError(f"historical variant metrics.{signal} is invalid")
        for field in (
            "total_return_with_cost",
            "benchmark_return",
            "excess_return_without_cost",
            "excess_return_with_cost",
            "annualized_return_with_cost",
            "annualized_excess_return_with_cost",
            "information_ratio_with_cost",
            "max_drawdown_with_cost",
            "total_cost",
            "turnover_mean",
        ):
            _finite(values.get(field), f"variant_backtest.metrics.{signal}.{field}")
    support = payload.get("support")
    if not isinstance(support, dict) or support.get("sessions", 0) <= 0:
        raise RuntimeError("historical variant support is absent")
    if int(str(support.get("actual_start"))[:4]) != contract["year"]:
        raise RuntimeError("historical variant support year is invalid")
    observability = payload.get("observability")
    if (
        not isinstance(observability, dict)
        or not isinstance(observability.get("turnover_exposed"), bool)
        or not isinstance(observability.get("position_count_exposed"), bool)
    ):
        raise RuntimeError("historical variant observability is invalid")
    artifacts = payload.get("artifacts")
    expected_artifacts = (
        {"daily_series", "raw_report", "holdings"}
        if holdings_required
        else {
            "daily_series",
            "raw_report",
        }
    )
    if not isinstance(artifacts, dict) or set(artifacts) != expected_artifacts:
        raise RuntimeError("historical variant artifacts are not exact")
    for name, artifact in artifacts.items():
        if not isinstance(artifact, dict):
            raise RuntimeError(f"historical variant artifact {name} is invalid")
        _relative_path(artifact.get("path"), f"variant_backtest.artifacts.{name}.path")
        require_sha(artifact.get("sha256"), f"variant_backtest.artifacts.{name}.sha256")
        if holdings_required and (
            isinstance(artifact.get("bytes"), bool)
            or not isinstance(artifact.get("bytes"), int)
            or artifact["bytes"] <= 0
        ):
            raise RuntimeError(f"variant_backtest.artifacts.{name}.bytes is invalid")
    if holdings_required:
        holdings = artifacts["holdings"]
        if (
            holdings.get("schema_version") != HOLDINGS_SCHEMA
            or holdings.get("columns") != list(HOLDINGS_COLUMNS)
            or holdings.get("sessions") != support["sessions"]
            or holdings.get("session_signal_pairs") != support["sessions"] * len(SIGNALS)
        ):
            raise RuntimeError("historical holdings artifact contract is invalid")
        for field in ("rows", "empty_session_signal_pairs"):
            if isinstance(holdings.get(field), bool) or not isinstance(holdings.get(field), int):
                raise RuntimeError(f"historical holdings artifact {field} is invalid")
        if holdings["rows"] < holdings["session_signal_pairs"]:
            raise RuntimeError("historical holdings row support is invalid")
    return payload


def validate_any_backtest_receipt(payload: object) -> dict[str, Any]:
    if isinstance(payload, dict) and payload.get("schema_version") in {
        VARIANT_BACKTEST_SCHEMA,
        VARIANT_BACKTEST_SCHEMA_V2,
    }:
        return validate_variant_backtest_receipt(payload)
    return validate_backtest_receipt(payload)


def validate_historical_catalog(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("historical catalog is not an object")
    if payload.get("schema_version") in {CATALOG_SCHEMA, CATALOG_SCHEMA_V2}:
        return validate_backtest_catalog(payload)
    schema = payload.get("schema_version")
    if schema not in {HISTORICAL_CATALOG_SCHEMA, HISTORICAL_CATALOG_SCHEMA_V2}:
        raise RuntimeError("historical catalog schema is invalid")
    verify_canonical_receipt(payload, str(schema))
    if payload.get("comparison_group_id") != COMPARISON_GROUP_ID:
        raise RuntimeError("historical catalog comparison group is invalid")
    entries = payload.get("entries")
    legacy_expected_ids = {
        STRATEGY_ID,
        FINAL_TEST_STRATEGY_ID,
        TOP3_VALIDATION_ID,
        TOP3_OPENED_ID,
    }
    holdings_expected_ids = {
        STRATEGY_ID,
        FINAL_TEST_STRATEGY_ID,
        TOP3_VALIDATION_ID_V2,
        TOP3_OPENED_ID_V2,
    }
    expected_ids = (
        holdings_expected_ids if schema == HISTORICAL_CATALOG_SCHEMA_V2 else legacy_expected_ids
    )
    if (
        not isinstance(entries, list)
        or len(entries) != 4
        or not all(isinstance(entry, dict) for entry in entries)
        or {entry.get("id") for entry in entries} != expected_ids
    ):
        raise RuntimeError("historical catalog exact four-entry set is invalid")
    by_group: dict[str, list[dict[str, Any]]] = {split: [] for split in SPLITS}
    for entry in entries:
        split = entry.get("evaluation_split")
        if split not in SPLITS:
            raise RuntimeError("historical catalog evaluation split is invalid")
        by_group[str(split)].append(entry)
        if (
            entry.get("state") != "passed"
            or entry.get("model_cell_id") != MODEL_CELL
            or entry.get("execution_domain") != EXECUTION_DOMAIN
            or entry.get("online_paper_equivalent") is not False
            or entry.get("promotion_eligible") is not False
            or entry.get("primary_signal") != PRIMARY_SIGNAL
            or entry.get("comparison_group_id") != COMPARISON_GROUP_ID
        ):
            raise RuntimeError("historical catalog public safety fields are invalid")
        require_sha(entry.get("receipt_sha256"), "historical_catalog.entry.receipt_sha256")
        _relative_path(entry.get("receipt_path"), "historical_catalog.entry.receipt_path")
        variant_id = entry.get("strategy_variant_id")
        if variant_id == TOP3_PUBLIC_VARIANT:
            expected_strategy = TOP3_STRATEGY
            expected_strategy_role = TOP3_STRATEGY_ROLE
        elif variant_id == TOP50_PUBLIC_VARIANT:
            expected_strategy = {
                "topk": 50,
                "n_drop": 5,
                "hold_thresh": 5,
                "method_sell": "bottom",
                "method_buy": "top",
                "only_tradable": False,
                "forbid_all_trade_at_limit": True,
            }
            expected_strategy_role = TOP50_STRATEGY_ROLE
        else:
            raise RuntimeError("historical catalog strategy variant is invalid")
        if (
            entry.get("strategy") != expected_strategy
            or entry.get("strategy_role") != expected_strategy_role
        ):
            raise RuntimeError("historical catalog strategy is invalid")
        source_backtest_id = entry.get("source_backtest_id")
        if variant_id == TOP50_PUBLIC_VARIANT:
            if source_backtest_id is not None:
                raise RuntimeError("historical Top50 source backtest must be null")
        elif source_backtest_id not in {STRATEGY_ID, FINAL_TEST_STRATEGY_ID}:
            raise RuntimeError("historical Top3 source backtest is invalid")
        source = entry.get("source")
        if not isinstance(source, dict):
            raise RuntimeError("historical catalog source is absent")
        for field in (
            "backtest_receipt_sha256",
            "signal_receipt_sha256",
            "provider_receipt_sha256",
        ):
            require_sha(source.get(field), f"historical_catalog.entry.source.{field}")
        if schema == HISTORICAL_CATALOG_SCHEMA_V2:
            holdings = entry.get("holdings")
            if not isinstance(holdings, dict) or set(holdings) != {
                "receipt_path",
                "receipt_sha256",
            }:
                raise RuntimeError("historical catalog holdings source is invalid")
            _relative_path(
                holdings.get("receipt_path"), "historical_catalog.entry.holdings.receipt_path"
            )
            require_sha(
                holdings.get("receipt_sha256"),
                "historical_catalog.entry.holdings.receipt_sha256",
            )
        summary = entry.get("summary")
        if not isinstance(summary, dict):
            raise RuntimeError("historical catalog summary is absent")
        for field in (
            "total_return_with_cost",
            "benchmark_return",
            "excess_return_with_cost",
            "annualized_return_with_cost",
            "information_ratio_with_cost",
            "max_drawdown_with_cost",
        ):
            _finite(summary.get(field), f"historical_catalog.entry.summary.{field}")
    for group, grouped in by_group.items():
        if len(grouped) != 2 or {entry.get("strategy_variant_id") for entry in grouped} != {
            TOP50_PUBLIC_VARIANT,
            TOP3_PUBLIC_VARIANT,
        }:
            raise RuntimeError(f"historical catalog comparison pair is invalid: {group}")
        contract = SPLITS[group]
        top3 = next(
            entry for entry in grouped if entry["strategy_variant_id"] == TOP3_PUBLIC_VARIANT
        )
        top50 = next(
            entry for entry in grouped if entry["strategy_variant_id"] == TOP50_PUBLIC_VARIANT
        )
        if (
            top3.get("result_role") != contract["result_role"]
            or top3.get("source_backtest_id") != contract["source_track_id"]
            or top3.get("used_for_selection") is not False
            or top3.get("selection_eligible") is not False
            or top3.get("test_data_access") != contract["test_data_access"]
        ):
            raise RuntimeError(f"historical Top3 split firewall is invalid: {group}")
        expected_top50_role = (
            "TRAINING_VALIDATION_CHECKPOINT_SELECTION"
            if group == "validation_2025"
            else "CORRECTED_OPENED_OOS_DIAGNOSTIC"
        )
        if (
            top50.get("result_role") != expected_top50_role
            or top50.get("source_backtest_id") is not None
            or top50.get("used_for_selection") is not (group == "validation_2025")
            or top50.get("selection_eligible") is not (group == "validation_2025")
            or top50.get("test_data_access") != contract["test_data_access"]
        ):
            raise RuntimeError(f"historical Top50 split firewall is invalid: {group}")
    return payload
