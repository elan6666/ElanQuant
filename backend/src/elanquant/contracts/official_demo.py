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
SIGNAL_SCHEMA = "elanquant_kronos_standardized_signal_v1"
BACKTEST_SCHEMA = "elanquant_qlib_topkdrop_v1"
CATALOG_SCHEMA = "elanquant_historical_backtest_catalog_v1"

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


def validate_signal_receipt(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("signal receipt is not an object")
    verify_canonical_receipt(payload, SIGNAL_SCHEMA)
    if (
        payload.get("id") != STRATEGY_ID
        or payload.get("track_kind") != "OFFICIAL_DEMO_METHOD"
        or payload.get("model_cell_id") != MODEL_CELL
        or payload.get("selection_split") != "validation_2025"
        or payload.get("test_viewed_consumed") is not False
        or payload.get("primary_signal") != PRIMARY_SIGNAL
        or payload.get("signals") != list(SIGNALS)
    ):
        raise RuntimeError("signal receipt identity or selection firewall is invalid")
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
    verify_canonical_receipt(payload, BACKTEST_SCHEMA)
    if (
        payload.get("id") != STRATEGY_ID
        or payload.get("track_kind") != "OFFICIAL_DEMO_METHOD_EXTENDED_PIT"
        or payload.get("model_cell_id") != MODEL_CELL
        or payload.get("selection_split") != "validation_2025"
        or payload.get("selection_rule_predeclared") is not True
        or payload.get("test_viewed_consumed") is not False
        or payload.get("test_status") != "NOT_ACCESSED_FOR_SELECTION"
        or payload.get("selection_eligible") is not True
        or payload.get("primary_signal") != PRIMARY_SIGNAL
    ):
        raise RuntimeError("backtest selection firewall or identity is invalid")
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
    if actual_start.year != 2025 or actual_end.year != 2025 or actual_start > actual_end:
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
    verify_canonical_receipt(payload, CATALOG_SCHEMA)
    entries = payload.get("entries")
    if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
        raise RuntimeError("backtest catalog must contain the single canonical demo track")
    entry = entries[0]
    if (
        entry.get("id") != STRATEGY_ID
        or entry.get("state") != "passed"
        or entry.get("model_cell_id") != MODEL_CELL
        or entry.get("selection_eligible") is not True
        or entry.get("primary_signal") != PRIMARY_SIGNAL
        or entry.get("selection_split") != "validation_2025"
        or entry.get("test_viewed_consumed") is not False
    ):
        raise RuntimeError("backtest catalog entry is invalid")
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
