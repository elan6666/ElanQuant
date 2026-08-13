from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from elanquant.contracts.official_demo import (
    EXPECTED_EXECUTION,
    PRIMARY_SIGNAL,
    SIGNALS,
    canonical_hash,
    require_sha,
)

SIGNAL_SCHEMA = "elanquant_historical_model_signal_v1"
LOCK_SCHEMA = "elanquant_historical_model_matrix_lock_v1"
BACKTEST_SCHEMA = "elanquant_historical_model_backtest_v1"
HOLDINGS_SCHEMA = "elanquant_historical_model_holdings_v1"
CATALOG_SCHEMA = "elanquant_historical_backtest_catalog_v5"

MODEL_CELLS: dict[str, tuple[str, str]] = {
    "small-zero-shot": ("small", "zero_shot"),
    "small-official-ft": ("small", "official_style"),
    "small-strict-pit": ("small", "strict_pit"),
    "base-zero-shot": ("base", "zero_shot"),
    "base-official-ft": ("base", "official_style"),
    "base-strict-pit": ("base", "strict_pit"),
}
SPLITS = ("validation_2025", "test_viewed_2026")
VARIANTS: dict[str, dict[str, object]] = {
    "official_top50": {
        "topk": 50,
        "n_drop": 5,
        "hold_thresh": 5,
        "method_sell": "bottom",
        "method_buy": "top",
        "only_tradable": False,
        "forbid_all_trade_at_limit": True,
    },
    "historical_top3": {
        "topk": 3,
        "n_drop": 1,
        "hold_thresh": 5,
        "method_sell": "bottom",
        "method_buy": "top",
        "only_tradable": False,
        "forbid_all_trade_at_limit": True,
        "risk_degree": 0.95,
    },
}


def _canonical(payload: dict[str, Any], schema: str) -> None:
    if payload.get("schema_version") != schema or payload.get("status") != "PASS":
        raise RuntimeError(f"{schema} identity is invalid")
    body = dict(payload)
    claimed = body.pop("receipt_hash", None)
    if canonical_hash(body) != claimed:
        raise RuntimeError(f"{schema} canonical hash is invalid")


def _relative(value: object, identity: str) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"{identity} is absent")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise RuntimeError(f"{identity} is unsafe")
    return value


def _finite(value: object, identity: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"{identity} is not numeric")
    result = float(value)
    if not math.isfinite(result):
        raise RuntimeError(f"{identity} is not finite")
    return result


def backtest_id(model: str, split: str, variant: str) -> str:
    return f"historical-{model}-{split}-{variant}-v1"


def validate_signal_receipt(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("matrix signal receipt is not an object")
    _canonical(payload, SIGNAL_SCHEMA)
    model = payload.get("model_cell_id")
    split = payload.get("evaluation_split")
    if (
        model not in MODEL_CELLS
        or split not in SPLITS
        or payload.get("id") != f"historical-signal-{model}-{split}-v1"
        or payload.get("model_size") != MODEL_CELLS[str(model)][0]
        or payload.get("model_track") != MODEL_CELLS[str(model)][1]
        or payload.get("primary_signal") != PRIMARY_SIGNAL
        or payload.get("signals") != list(SIGNALS)
        or payload.get("selection_eligible") is not False
        or payload.get("used_for_selection") is not False
        or payload.get("test_data_access")
        != ("VIEWED" if split == "test_viewed_2026" else "NOT_APPLICABLE")
    ):
        raise RuntimeError("matrix signal identity or firewall is invalid")
    for field in (
        "training_matrix_sha256",
        "tokenizer_sha256",
        "predictor_sha256",
        "model_config_sha256",
        "dataset_manifest_sha256",
        "dataset_file_sha256",
        "generator_code_sha256",
        "reference_signal_receipt_sha256",
    ):
        require_sha(payload.get(field), f"matrix_signal.{field}")
    support = payload.get("support")
    if not isinstance(support, dict):
        raise RuntimeError("matrix signal support is absent")
    for field in ("rows", "cross_sections"):
        if isinstance(support.get(field), bool) or not isinstance(support.get(field), int):
            raise RuntimeError(f"matrix signal support.{field} is invalid")
    require_sha(support.get("anchor_set_sha256"), "matrix_signal.support.anchor")
    artifact = payload.get("artifacts", {}).get("signals")
    if not isinstance(artifact, dict):
        raise RuntimeError("matrix signal artifact is absent")
    _relative(artifact.get("path"), "matrix_signal.artifact.path")
    require_sha(artifact.get("sha256"), "matrix_signal.artifact.sha256")
    return payload


def validate_matrix_lock(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("historical matrix lock is not an object")
    _canonical(payload, LOCK_SCHEMA)
    if (
        payload.get("id") != "historical-six-model-matrix-v1"
        or payload.get("models") != list(MODEL_CELLS)
        or payload.get("splits") != list(SPLITS)
        or payload.get("variants") != VARIANTS
        or payload.get("primary_signal") != PRIMARY_SIGNAL
        or payload.get("signals") != list(SIGNALS)
        or payload.get("execution") != EXPECTED_EXECUTION
        or payload.get("selection_eligible") is not False
        or payload.get("used_for_selection") is not False
        or payload.get("promotion_eligible") is not False
    ):
        raise RuntimeError("historical matrix lock protocol is invalid")
    for field in (
        "runner_sha256",
        "helper_sha256",
        "contract_sha256",
        "qlib_metadata_sha256",
        "qlib_record_sha256",
        "qlib_source_tree_sha256",
    ):
        require_sha(payload.get(field), f"matrix_lock.{field}")
    _relative(payload.get("runner_path"), "matrix_lock.runner_path")
    _relative(payload.get("helper_path"), "matrix_lock.helper_path")
    _relative(payload.get("contract_path"), "matrix_lock.contract_path")
    sources = payload.get("sources")
    if not isinstance(sources, list) or len(sources) != len(MODEL_CELLS) * len(SPLITS):
        raise RuntimeError("historical matrix lock sources are not exact")
    pairs: set[tuple[str, str]] = set()
    split_identity: dict[str, tuple[object, object, object, object]] = {}
    for source in sources:
        if not isinstance(source, dict):
            raise RuntimeError("historical matrix lock source is invalid")
        pair = (str(source.get("model_cell_id")), str(source.get("evaluation_split")))
        if pair[0] not in MODEL_CELLS or pair[1] not in SPLITS or pair in pairs:
            raise RuntimeError("historical matrix lock source identity is invalid")
        pairs.add(pair)
        for field in (
            "signal_receipt_sha256",
            "signal_artifact_sha256",
            "provider_receipt_sha256",
            "provider_tree_sha256",
        ):
            require_sha(source.get(field), f"matrix_lock.source.{field}")
        _relative(source.get("signal_receipt_path"), "matrix_lock.source.signal_path")
        _relative(source.get("provider_receipt_path"), "matrix_lock.source.provider_path")
        support = source.get("support")
        model_identity = source.get("model")
        if not isinstance(support, dict) or not isinstance(model_identity, dict):
            raise RuntimeError("historical matrix lock support or model identity is absent")
        require_sha(support.get("anchor_set_sha256"), "matrix_lock.source.support.anchor")
        for field in (
            "training_matrix_sha256",
            "tokenizer_sha256",
            "predictor_sha256",
            "model_config_sha256",
            "dataset_manifest_sha256",
            "dataset_file_sha256",
        ):
            require_sha(model_identity.get(field), f"matrix_lock.source.model.{field}")
        comparable = (
            support,
            model_identity["dataset_manifest_sha256"],
            model_identity["dataset_file_sha256"],
            source["provider_tree_sha256"],
        )
        prior = split_identity.setdefault(pair[1], comparable)
        if comparable != prior:
            raise RuntimeError(f"historical matrix split support differs: {pair[1]}")
    return payload


def validate_backtest_receipt(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("historical matrix backtest receipt is not an object")
    _canonical(payload, BACKTEST_SCHEMA)
    model = str(payload.get("model_cell_id"))
    split = str(payload.get("evaluation_split"))
    variant = str(payload.get("strategy_variant_id"))
    if (
        model not in MODEL_CELLS
        or split not in SPLITS
        or variant not in VARIANTS
        or payload.get("id") != backtest_id(model, split, variant)
        or payload.get("strategy") != VARIANTS[variant]
        or payload.get("execution") != EXPECTED_EXECUTION
        or payload.get("primary_signal") != PRIMARY_SIGNAL
        or payload.get("selection_eligible") is not False
        or payload.get("used_for_selection") is not False
        or payload.get("promotion_eligible") is not False
        or payload.get("online_paper_equivalent") is not False
        or payload.get("test_data_access")
        != ("VIEWED" if split == "test_viewed_2026" else "NOT_APPLICABLE")
    ):
        raise RuntimeError("historical matrix backtest identity is invalid")
    for field in (
        "matrix_lock_sha256",
        "source_signal_receipt_sha256",
        "source_provider_receipt_sha256",
        "backtest_code_sha256",
    ):
        require_sha(payload.get(field), f"matrix_backtest.{field}")
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict) or set(metrics) != set(SIGNALS):
        raise RuntimeError("historical matrix metrics are not exact")
    for signal, values in metrics.items():
        if not isinstance(values, dict):
            raise RuntimeError(f"historical matrix metrics.{signal} is invalid")
        for field in (
            "total_return_with_cost",
            "benchmark_return",
            "excess_return_with_cost",
            "information_ratio_with_cost",
            "max_drawdown_with_cost",
        ):
            _finite(values.get(field), f"matrix_backtest.metrics.{signal}.{field}")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {
        "daily_series",
        "raw_report",
        "holdings",
    }:
        raise RuntimeError("historical matrix artifacts are not exact")
    for name, artifact in artifacts.items():
        if not isinstance(artifact, dict):
            raise RuntimeError(f"historical matrix artifact {name} is invalid")
        _relative(artifact.get("path"), f"matrix_backtest.{name}.path")
        require_sha(artifact.get("sha256"), f"matrix_backtest.{name}.sha256")
    return payload


def validate_catalog(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("historical matrix catalog is not an object")
    _canonical(payload, CATALOG_SCHEMA)
    entries = payload.get("entries")
    expected = {
        (model, split, variant)
        for model in MODEL_CELLS
        for split in SPLITS
        for variant in VARIANTS
    }
    if not isinstance(entries, list) or len(entries) != len(expected):
        raise RuntimeError("historical matrix catalog size is invalid")
    observed: set[tuple[str, str, str]] = set()
    split_support: dict[str, tuple[object, object]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise RuntimeError("historical matrix catalog entry is invalid")
        key = (
            str(entry.get("model_cell_id")),
            str(entry.get("evaluation_split")),
            str(entry.get("strategy_variant_id")),
        )
        if key not in expected or key in observed:
            raise RuntimeError("historical matrix catalog identity is invalid")
        observed.add(key)
        if (
            entry.get("id") != backtest_id(*key)
            or entry.get("state") != "passed"
            or entry.get("selection_eligible") is not False
            or entry.get("used_for_selection") is not False
            or entry.get("promotion_eligible") is not False
            or entry.get("online_paper_equivalent") is not False
        ):
            raise RuntimeError("historical matrix catalog firewall is invalid")
        require_sha(entry.get("receipt_sha256"), "matrix_catalog.receipt_sha256")
        _relative(entry.get("receipt_path"), "matrix_catalog.receipt_path")
        source = entry.get("source")
        support = entry.get("support")
        if not isinstance(source, dict) or not isinstance(support, dict):
            raise RuntimeError("historical matrix catalog source or support is absent")
        require_sha(
            source.get("signal_receipt_sha256"),
            "matrix_catalog.source.signal_receipt_sha256",
        )
        require_sha(
            source.get("provider_receipt_sha256"),
            "matrix_catalog.source.provider_receipt_sha256",
        )
        comparable = (support, source["provider_receipt_sha256"])
        prior = split_support.setdefault(key[1], comparable)
        if comparable != prior:
            raise RuntimeError(f"historical matrix catalog split support differs: {key[1]}")
    if observed != expected:
        raise RuntimeError("historical matrix catalog matrix is incomplete")
    return payload
