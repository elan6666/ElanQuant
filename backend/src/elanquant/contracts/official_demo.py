from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

SIGNALS = ("mean", "last", "max", "min")
PRIMARY_SIGNAL = "mean"
MODEL_CELL = "small-official-ft"
STRATEGY_ID = "official-demo-method-extended-pit-v1"
FINAL_TEST_STRATEGY_ID = "official-demo-method-corrected-opened-2026-v1"
SIGNAL_SCHEMA = "elanquant_kronos_standardized_signal_v1"
FINAL_TEST_SIGNAL_SCHEMA = "elanquant_kronos_standardized_signal_v2"
BACKTEST_SCHEMA = "elanquant_qlib_topkdrop_v1"
FINAL_TEST_BACKTEST_SCHEMA = "elanquant_qlib_topkdrop_v2"
CATALOG_SCHEMA = "elanquant_historical_backtest_catalog_v1"
CATALOG_SCHEMA_V2 = "elanquant_historical_backtest_catalog_v2"
ANALYSIS_LOCK_SCHEMA = "elanquant_official_demo_analysis_lock_v1"

SPLIT_CONTRACTS: dict[str, dict[str, object]] = {
    STRATEGY_ID: {
        "split": "validation_2025",
        "year": 2025,
        "role": "TRAINING_VALIDATION_CHECKPOINT_SELECTION",
        "selection_eligible": True,
        "used_for_selection": True,
        "test_data_access": "NOT_APPLICABLE",
    },
    FINAL_TEST_STRATEGY_ID: {
        "split": "test_viewed_2026",
        "year": 2026,
        "role": "CORRECTED_OPENED_OOS_DIAGNOSTIC",
        "selection_eligible": False,
        "used_for_selection": False,
        "test_data_access": "VIEWED",
    },
}

EXPECTED_STRATEGY: dict[str, object] = {
    "topk": 50,
    "n_drop": 5,
    "hold_thresh": 5,
    "method_sell": "bottom",
    "method_buy": "top",
    "only_tradable": False,
    "forbid_all_trade_at_limit": True,
}
EXPECTED_EXECUTION: dict[str, object] = {
    "time_per_step": "day",
    "generate_portfolio_metrics": True,
    "delay_execution": True,
    "account": 100_000_000,
    "benchmark": "SH000300",
    "freq": "day",
    "limit_threshold": 0.095,
    "deal_price": "open",
    "open_cost": 0.001,
    "close_cost": 0.0015,
    "min_cost": 5,
}


def canonical_hash(payload: object) -> str:
    rendered = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_sha(value: object, identity: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value.lower())
    ):
        raise RuntimeError(f"{identity} is not a SHA-256 identity")
    return value


def require_finite(value: object, identity: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"{identity} is not numeric")
    number = float(value)
    if not math.isfinite(number):
        raise RuntimeError(f"{identity} is not finite")
    return number


def require_positive_int(value: object, identity: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RuntimeError(f"{identity} is not a positive integer")
    return value


def verify_canonical_receipt(payload: Mapping[str, Any], schema: str) -> None:
    content = dict(payload)
    claimed = content.pop("receipt_hash", None)
    if (
        payload.get("schema_version") != schema
        or payload.get("status") != "PASS"
        or canonical_hash(content) != require_sha(claimed, f"{schema}.receipt_hash")
    ):
        raise RuntimeError(f"{schema} receipt is invalid")


def standardized_close_signals(
    predicted_close: Sequence[float],
    last_context_close: float,
) -> dict[str, float]:
    """Pinned Kronos demo signal formulas in per-instance normalized space."""

    values = [float(value) for value in predicted_close]
    if len(values) != 10 or not all(math.isfinite(value) for value in values):
        raise ValueError("official demo requires ten finite normalized close predictions")
    reference = float(last_context_close)
    if not math.isfinite(reference):
        raise ValueError("last normalized context close is not finite")
    return {
        "mean": sum(values) / len(values) - reference,
        "last": values[-1] - reference,
        "max": max(values) - reference,
        "min": min(values) - reference,
    }


def split_contract(payload: Mapping[str, Any]) -> dict[str, object]:
    strategy_id = payload.get("id")
    contract = SPLIT_CONTRACTS.get(str(strategy_id))
    if contract is None:
        raise RuntimeError("official demo split identity is not allowlisted")
    return contract


def validate_analysis_lock(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("analysis lock is not an object")
    verify_canonical_receipt(payload, ANALYSIS_LOCK_SCHEMA)
    if (
        payload.get("id") != FINAL_TEST_STRATEGY_ID
        or payload.get("model_cell_id") != MODEL_CELL
        or payload.get("primary_signal") != PRIMARY_SIGNAL
        or payload.get("evaluation_split") != "test_viewed_2026"
        or payload.get("used_for_selection") is not False
        or payload.get("test_data_access") != "VIEWED"
        or payload.get("viewed_before_track_freeze") is not True
        or payload.get("maturity_rule")
        != (
            "t_known_universe_with_complete_prior_90_global_sessions_and_"
            "ten_future_global_exchange_timestamps_without_future_symbol_filter"
        )
        or payload.get("strategy") != EXPECTED_STRATEGY
        or payload.get("execution") != EXPECTED_EXECUTION
        or payload.get("expected_support")
        != {
            "rows": 39072,
            "cross_sections": 137,
            "signal_start": "2026-01-05",
            "signal_end": "2026-07-29",
            "target_end": "2026-08-12",
            "candidate_min": 278,
            "candidate_median": 283.0,
            "candidate_max": 297,
            "anchor_set_sha256": (
                "35d43fd0e4cf216753ee8fa95c78474a18b37492e5f3bb0b190c6526f300d7a7"
            ),
        }
        or payload.get("inference")
        != {
            "T": 0.6,
            "top_p": 0.9,
            "top_k": 0,
            "sample_count": 5,
            "batch_size": 1000,
            "effective_series_batch": 200,
            "seed": 100,
        }
    ):
        raise RuntimeError("analysis lock identity or frozen protocol is invalid")
    if not isinstance(payload.get("locked_at"), str) or not payload["locked_at"]:
        raise RuntimeError("analysis lock timestamp is absent")
    for identity in (
        "validation_backtest_receipt_sha256",
        "training_matrix_sha256",
        "tokenizer_sha256",
        "predictor_sha256",
        "model_config_sha256",
        "dataset_manifest_sha256",
        "dataset_file_sha256",
    ):
        require_sha(payload.get(identity), f"analysis_lock.{identity}")
    return payload


def validate_signal_receipt(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("signal receipt is not an object")
    contract = split_contract(payload)
    schema = SIGNAL_SCHEMA if payload.get("id") == STRATEGY_ID else FINAL_TEST_SIGNAL_SCHEMA
    verify_canonical_receipt(payload, schema)
    if (
        payload.get("track_kind") != "OFFICIAL_DEMO_METHOD"
        or payload.get("model_cell_id") != MODEL_CELL
        or payload.get("primary_signal") != PRIMARY_SIGNAL
        or payload.get("signals") != list(SIGNALS)
    ):
        raise RuntimeError("signal receipt identity or selection firewall is invalid")
    if payload.get("id") == STRATEGY_ID:
        if (
            payload.get("selection_split") != contract["split"]
            or payload.get("test_viewed_consumed") is not False
        ):
            raise RuntimeError("signal receipt identity or selection firewall is invalid")
    elif (
        payload.get("evaluation_split") != contract["split"]
        or payload.get("result_role") != contract["role"]
        or payload.get("selection_eligible") is not False
        or payload.get("used_for_selection") is not False
        or payload.get("test_data_access") != "VIEWED"
    ):
        raise RuntimeError("final-test signal firewall is invalid")
    if payload.get("id") == FINAL_TEST_STRATEGY_ID:
        require_sha(payload.get("analysis_lock_sha256"), "signal.analysis_lock_sha256")
        if (
            payload.get("signal_start") != "2026-01-05"
            or payload.get("signal_end") != "2026-07-29"
        ):
            raise RuntimeError("final-test signal date support differs from the frozen lock")
    inference = payload.get("inference")
    normalization = payload.get("normalization")
    support = payload.get("support")
    artifacts = payload.get("artifacts")
    if not isinstance(inference, dict) or inference != {
        "T": 0.6,
        "top_p": 0.9,
        "top_k": 0,
        "sample_count": 5,
        "batch_size": 1000,
        "effective_series_batch": 200,
        "seed": 100,
    }:
        raise RuntimeError("signal inference parameters are not the sealed demo contract")
    if not isinstance(normalization, dict) or normalization != {
        "policy": "INSTANCE_PER_SYMBOL_90_SESSION",
        "lookback": 90,
        "predict": 10,
        "epsilon": 1e-5,
        "clip": 5.0,
        "feature_order": ["open", "high", "low", "close", "vol", "amt"],
        "close_index": 3,
    }:
        raise RuntimeError("signal normalization is not the pinned demo contract")
    runtime = payload.get("runtime")
    if (
        not isinstance(runtime, dict)
        or set(runtime)
        != {"python", "torch", "cuda", "numpy", "pandas", "device", "gpu_name"}
        or not all(isinstance(value, str) and value for value in runtime.values())
    ):
        raise RuntimeError("signal runtime identity is incomplete")
    if not isinstance(support, dict):
        raise RuntimeError("signal support is absent")
    require_positive_int(support.get("rows"), "signal.support.rows")
    require_positive_int(support.get("cross_sections"), "signal.support.cross_sections")
    require_sha(support.get("anchor_set_sha256"), "signal.support.anchor_set_sha256")
    if payload.get("id") == FINAL_TEST_STRATEGY_ID:
        expected = {
            "rows": 39072,
            "cross_sections": 137,
            "anchor_set_sha256": (
                "35d43fd0e4cf216753ee8fa95c78474a18b37492e5f3bb0b190c6526f300d7a7"
            ),
        }
        if any(support.get(key) != value for key, value in expected.items()):
            raise RuntimeError("final-test signal support differs from the frozen lock")
    for identity in (
        "upstream_commit",
        "training_matrix_sha256",
        "tokenizer_sha256",
        "predictor_sha256",
        "model_config_sha256",
        "dataset_manifest_sha256",
        "dataset_file_sha256",
        "generator_code_sha256",
        "rng_state_before_sha256",
        "rng_state_after_sha256",
    ):
        value = payload.get(identity)
        if identity == "upstream_commit":
            if not isinstance(value, str) or len(value) != 40:
                raise RuntimeError("signal upstream commit is invalid")
        else:
            require_sha(value, f"signal.{identity}")
    if not isinstance(artifacts, dict) or set(artifacts) != {"signals"}:
        raise RuntimeError("signal artifacts are incomplete")
    artifact = artifacts["signals"]
    if not isinstance(artifact, dict):
        raise RuntimeError("signal artifact is invalid")
    require_sha(artifact.get("sha256"), "signal.artifacts.signals.sha256")
    require_positive_int(artifact.get("bytes"), "signal.artifacts.signals.bytes")
    if not isinstance(artifact.get("path"), str) or Path(str(artifact["path"])).is_absolute():
        raise RuntimeError("signal artifact path must be relative")
    return payload


def validate_backtest_receipt(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("backtest receipt is not an object")
    contract = split_contract(payload)
    schema = BACKTEST_SCHEMA if payload.get("id") == STRATEGY_ID else FINAL_TEST_BACKTEST_SCHEMA
    verify_canonical_receipt(payload, schema)
    if (
        payload.get("track_kind") != "OFFICIAL_DEMO_METHOD_EXTENDED_PIT"
        or payload.get("model_cell_id") != MODEL_CELL
        or payload.get("primary_signal") != PRIMARY_SIGNAL
    ):
        raise RuntimeError("backtest selection firewall or identity is invalid")
    if payload.get("id") == STRATEGY_ID:
        if (
            payload.get("selection_split") != contract["split"]
            or payload.get("selection_rule_predeclared") is not True
            or payload.get("test_viewed_consumed") is not False
            or payload.get("test_status") != "NOT_ACCESSED_FOR_SELECTION"
            or payload.get("selection_eligible") is not True
        ):
            raise RuntimeError("backtest selection firewall or identity is invalid")
    elif (
        payload.get("evaluation_split") != contract["split"]
        or payload.get("result_role") != contract["role"]
        or payload.get("selection_eligible") is not False
        or payload.get("used_for_selection") is not False
        or payload.get("test_data_access") != "VIEWED"
        or payload.get("strategy_locked_before_run") is not True
    ):
        raise RuntimeError("final-test backtest firewall is invalid")
    if payload.get("id") == FINAL_TEST_STRATEGY_ID:
        require_sha(payload.get("analysis_lock_sha256"), "backtest.analysis_lock_sha256")
    if payload.get("strategy") != EXPECTED_STRATEGY:
        raise RuntimeError("backtest strategy differs from pinned TopkDropout demo")
    if payload.get("execution") != EXPECTED_EXECUTION:
        raise RuntimeError("backtest execution differs from pinned Qlib demo")
    require_sha(payload.get("signal_receipt_sha256"), "backtest.signal_receipt_sha256")
    require_sha(payload.get("provider_receipt_sha256"), "backtest.provider_receipt_sha256")
    require_sha(payload.get("backtest_code_sha256"), "backtest.backtest_code_sha256")
    qlib = payload.get("qlib")
    if not isinstance(qlib, dict) or qlib.get("version") != "0.9.7":
        raise RuntimeError("backtest Qlib dependency is not pinned")
    for identity in ("metadata_sha256", "record_sha256", "source_tree_sha256"):
        require_sha(qlib.get(identity), f"backtest.qlib.{identity}")
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict) or set(metrics) != set(SIGNALS):
        raise RuntimeError("backtest does not contain all four official signals")
    for signal, values in metrics.items():
        if not isinstance(values, dict):
            raise RuntimeError(f"backtest metrics are invalid: {signal}")
        for metric in (
            "total_return_with_cost",
            "benchmark_return",
            "excess_return_without_cost",
            "excess_return_with_cost",
            "annualized_return_with_cost",
            "annualized_excess_return_with_cost",
            "information_ratio_with_cost",
            "max_drawdown_with_cost",
            "total_cost",
        ):
            require_finite(values.get(metric), f"backtest.metrics.{signal}.{metric}")
    support = payload.get("support")
    if not isinstance(support, dict):
        raise RuntimeError("backtest support is absent")
    require_positive_int(support.get("sessions"), "backtest.support.sessions")
    require_positive_int(support.get("signal_rows"), "backtest.support.signal_rows")
    cross_sections = require_positive_int(
        support.get("signal_cross_sections"), "backtest.support.signal_cross_sections"
    )
    candidate_min = require_positive_int(
        support.get("candidate_min"), "backtest.support.candidate_min"
    )
    candidate_max = require_positive_int(
        support.get("candidate_max"), "backtest.support.candidate_max"
    )
    candidate_median = require_finite(
        support.get("candidate_median"), "backtest.support.candidate_median"
    )
    if (
        candidate_min < 50
        or candidate_min > candidate_median
        or candidate_median > candidate_max
        or support["signal_rows"] < candidate_min * cross_sections
    ):
        raise RuntimeError("backtest candidate support is insufficient or inconsistent")
    try:
        actual_start = date.fromisoformat(str(support.get("actual_start")))
        actual_end = date.fromisoformat(str(support.get("actual_end")))
    except ValueError as error:
        raise RuntimeError("backtest actual date support is invalid") from error
    expected_year = contract["year"]
    if not isinstance(expected_year, int):
        raise RuntimeError("backtest split year is invalid")
    if (
        actual_start.year != expected_year
        or actual_end.year != expected_year
        or actual_start > actual_end
    ):
        raise RuntimeError("backtest selection firewall rejected its actual dates")
    if not isinstance(payload.get("generated_at"), str) or not payload["generated_at"]:
        raise RuntimeError("backtest generation timestamp is absent")
    curve_semantics = payload.get("curve_semantics")
    if not isinstance(curve_semantics, dict) or set(curve_semantics) != {
        "official",
        "derived",
    }:
        raise RuntimeError("backtest curve semantics are incomplete")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {"daily_series"}:
        raise RuntimeError("backtest artifacts are incomplete")
    artifact = artifacts["daily_series"]
    if not isinstance(artifact, dict):
        raise RuntimeError("backtest daily artifact is invalid")
    require_sha(artifact.get("sha256"), "backtest.artifacts.daily_series.sha256")
    require_positive_int(artifact.get("bytes"), "backtest.artifacts.daily_series.bytes")
    if not isinstance(artifact.get("path"), str) or Path(str(artifact["path"])).is_absolute():
        raise RuntimeError("backtest artifact path must be relative")
    deviations = payload.get("deviations")
    if not isinstance(deviations, list) or not deviations or not all(
        isinstance(item, str) and item for item in deviations
    ):
        raise RuntimeError("backtest deviations must be disclosed")
    return payload


def validate_backtest_catalog(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("backtest catalog is not an object")
    schema = payload.get("schema_version")
    if schema not in {CATALOG_SCHEMA, CATALOG_SCHEMA_V2}:
        raise RuntimeError("backtest catalog schema is not allowlisted")
    verify_canonical_receipt(payload, str(schema))
    entries = payload.get("entries")
    expected_ids = {STRATEGY_ID} if schema == CATALOG_SCHEMA else set(SPLIT_CONTRACTS)
    if (
        not isinstance(entries, list)
        or len(entries) != len(expected_ids)
        or not all(isinstance(entry, dict) for entry in entries)
        or {entry.get("id") for entry in entries} != expected_ids
    ):
        raise RuntimeError("backtest catalog has an invalid exact entry set")
    for entry in entries:
        contract = split_contract(entry)
        if (
            entry.get("state") != "passed"
            or entry.get("model_cell_id") != MODEL_CELL
            or entry.get("selection_eligible") is not contract["selection_eligible"]
            or entry.get("primary_signal") != PRIMARY_SIGNAL
        ):
            raise RuntimeError("backtest catalog entry is invalid")
        if entry.get("id") == STRATEGY_ID:
            if (
                entry.get("selection_split") != contract["split"]
                or entry.get("test_viewed_consumed") is not False
            ):
                raise RuntimeError("validation catalog entry is invalid")
        elif (
            entry.get("evaluation_split") != contract["split"]
            or entry.get("result_role") != contract["role"]
            or entry.get("used_for_selection") is not False
            or entry.get("test_data_access") != "VIEWED"
        ):
            raise RuntimeError("final-test catalog entry is invalid")
        require_sha(entry.get("receipt_sha256"), "catalog.entry.receipt_sha256")
        path = entry.get("receipt_path")
        if not isinstance(path, str) or Path(path).is_absolute() or ".." in Path(path).parts:
            raise RuntimeError("backtest receipt path is not allowlisted")
        summary = entry.get("summary")
        if not isinstance(summary, dict):
            raise RuntimeError("backtest catalog summary is absent")
        for metric in (
            "total_return_with_cost",
            "benchmark_return",
            "excess_return_with_cost",
            "annualized_return_with_cost",
            "information_ratio_with_cost",
            "max_drawdown_with_cost",
        ):
            require_finite(summary.get(metric), f"catalog.entry.summary.{metric}")
    return payload
