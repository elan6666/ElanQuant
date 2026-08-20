"""Sealed contract for the iTransformer B2 / Kronos weekly comparison.

This module deliberately compares *execution outcomes*, not model internals.
Both families must use the same strict-weekly anchors, realised labels, universe
and next-session-open execution; their input windows/features may differ and
are exposed as model-specific provenance.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from elanquant.contracts.official_demo import require_sha, verify_canonical_receipt

EVIDENCE_SCHEMA = "elanquant_unified_weekly_model_evidence_v1"
PROTOCOL_SCHEMA = "elanquant_unified_weekly_comparison_protocol_v1"
RESULT_SCHEMA = "elanquant_unified_weekly_comparison_result_v1"
CATALOG_SCHEMA = "elanquant_unified_weekly_comparison_catalog_v1"

MODEL_FAMILIES = ("itransformer-b2-r16g-r3", "kronos-base-zero-shot")
PORTFOLIOS = ("top1", "top3", "top50")
ARTIFACT_ROOT = "artifacts/unified-weekly-comparison"
COMMON_PROTOCOL_KEYS = (
    "evaluation_range",
    "anchor_set_sha256",
    "label_artifact_sha256",
    "universe_artifact_sha256",
    "execution_spec_sha256",
    "anchor_frequency",
    "label_definition",
    "execution_semantics",
    "delay_sessions",
)
PREDICTION_METRICS = ("rank_ic", "pearson_ic", "spearman_ic", "mae", "rmse")
PORTFOLIO_METRICS = (
    "total_return_with_cost",
    "benchmark_return",
    "excess_return_with_cost",
    "information_ratio_with_cost",
    "max_drawdown_with_cost",
    "turnover_mean",
    "total_cost",
)


def result_id(family: str, portfolio: str) -> str:
    return f"unified-weekly-{family}-{portfolio}-v1"


def _relative_artifact(value: object, identity: str) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"{identity} is absent")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not value.startswith(f"{ARTIFACT_ROOT}/"):
        raise RuntimeError(f"{identity} is outside the sealed artifact root")
    return value


def _finite(value: object, identity: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"{identity} is not numeric")
    value = float(value)
    if not math.isfinite(value):
        raise RuntimeError(f"{identity} is not finite")
    return value


def _positive_int(value: object, identity: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RuntimeError(f"{identity} is not a positive integer")
    return value


def _artifact(value: object, identity: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        raise RuntimeError(f"{identity} artifact is invalid")
    _relative_artifact(value["path"], f"{identity}.path")
    require_sha(value["sha256"], f"{identity}.sha256")
    return value


def _common_protocol(value: object, identity: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != set(COMMON_PROTOCOL_KEYS) | {"support"}:
        raise RuntimeError(f"{identity} common protocol is invalid")
    if (
        not isinstance(value["evaluation_range"], dict)
        or set(value["evaluation_range"]) != {"start", "end"}
        or not all(isinstance(value["evaluation_range"][key], str) for key in ("start", "end"))
        or value["anchor_frequency"] != "strict_weekly"
        or value["label_definition"] != "strict_weekly_open_to_open_log_return"
        or value["execution_semantics"] != "next_trading_session_open"
        or value["delay_sessions"] != 1
    ):
        raise RuntimeError(f"{identity} anchor, label or execution semantics are invalid")
    for key in (
        "anchor_set_sha256",
        "label_artifact_sha256",
        "universe_artifact_sha256",
        "execution_spec_sha256",
    ):
        require_sha(value[key], f"{identity}.{key}")
    support = value["support"]
    if not isinstance(support, dict) or set(support) != {"anchors", "signal_rows"}:
        raise RuntimeError(f"{identity}.support is invalid")
    _positive_int(support["anchors"], f"{identity}.support.anchors")
    _positive_int(support["signal_rows"], f"{identity}.support.signal_rows")
    return value


def validate_model_evidence(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("weekly model evidence is not an object")
    verify_canonical_receipt(payload, EVIDENCE_SCHEMA)
    family = payload.get("model_family_id")
    if family not in MODEL_FAMILIES or payload.get("id") != f"weekly-evidence-{family}-v1":
        raise RuntimeError("weekly model evidence identity is invalid")
    if (
        payload.get("online_paper_equivalent") is not False
        or payload.get("promotion_eligible") is not False
    ):
        raise RuntimeError("weekly model evidence firewall is invalid")
    _common_protocol(payload.get("common_protocol"), "weekly_evidence")
    inputs = payload.get("model_input")
    if not isinstance(inputs, dict) or set(inputs) != {
        "lookback_sessions",
        "feature_schema",
        "input_artifact",
    }:
        raise RuntimeError("weekly model evidence input provenance is invalid")
    _positive_int(inputs["lookback_sessions"], "weekly_evidence.lookback_sessions")
    if not isinstance(inputs["feature_schema"], str) or not inputs["feature_schema"]:
        raise RuntimeError("weekly model evidence feature schema is invalid")
    _artifact(inputs["input_artifact"], "weekly_evidence.input_artifact")
    for key in ("model_sha256", "runner_code_sha256"):
        require_sha(payload.get(key), f"weekly_evidence.{key}")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {"predictions", "scores"}:
        raise RuntimeError("weekly model evidence artifacts are invalid")
    for name, artifact in artifacts.items():
        _artifact(artifact, f"weekly_evidence.{name}")
    return payload


def validate_protocol(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("unified weekly protocol is not an object")
    verify_canonical_receipt(payload, PROTOCOL_SCHEMA)
    if payload.get("id") != "itransformer-b2-vs-kronos-base-weekly-v1":
        raise RuntimeError("unified weekly protocol identity is invalid")
    if payload.get("model_families") != list(MODEL_FAMILIES) or payload.get("portfolios") != list(
        PORTFOLIOS
    ):
        raise RuntimeError("unified weekly protocol matrix is invalid")
    if (
        payload.get("online_paper_equivalent") is not False
        or payload.get("promotion_eligible") is not False
    ):
        raise RuntimeError("unified weekly protocol firewall is invalid")
    common = _common_protocol(payload.get("common_protocol"), "weekly_protocol")
    evidence = payload.get("source_evidence")
    if not isinstance(evidence, list) or len(evidence) != len(MODEL_FAMILIES):
        raise RuntimeError("unified weekly protocol evidence is invalid")
    families: set[str] = set()
    for item in evidence:
        if not isinstance(item, dict) or set(item) != {
            "model_family_id",
            "receipt_path",
            "receipt_sha256",
            "common_protocol",
        }:
            raise RuntimeError("unified weekly protocol evidence entry is invalid")
        family = item["model_family_id"]
        if family not in MODEL_FAMILIES or family in families:
            raise RuntimeError("unified weekly protocol evidence family is invalid")
        families.add(family)
        _relative_artifact(item["receipt_path"], "weekly_protocol.evidence.receipt_path")
        require_sha(item["receipt_sha256"], "weekly_protocol.evidence.receipt_sha256")
        if _common_protocol(item["common_protocol"], "weekly_protocol.evidence") != common:
            raise RuntimeError("unified weekly protocol anchor, label or execution differs")
    return payload


def validate_result_receipt(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("unified weekly result is not an object")
    verify_canonical_receipt(payload, RESULT_SCHEMA)
    family, portfolio = payload.get("model_family_id"), payload.get("portfolio_id")
    if (
        family not in MODEL_FAMILIES
        or portfolio not in PORTFOLIOS
        or payload.get("id") != result_id(str(family), str(portfolio))
    ):
        raise RuntimeError("unified weekly result identity is invalid")
    if (
        payload.get("online_paper_equivalent") is not False
        or payload.get("promotion_eligible") is not False
    ):
        raise RuntimeError("unified weekly result firewall is invalid")
    require_sha(payload.get("protocol_receipt_sha256"), "weekly_result.protocol_receipt_sha256")
    if payload.get("protocol_id") != "itransformer-b2-vs-kronos-base-weekly-v1":
        raise RuntimeError("unified weekly result protocol linkage is invalid")
    require_sha(
        payload.get("source_evidence_receipt_sha256"),
        "weekly_result.source_evidence_receipt_sha256",
    )
    prediction = payload.get("prediction_metrics")
    portfolio_metrics = payload.get("portfolio_metrics")
    if not isinstance(prediction, dict) or set(prediction) != set(PREDICTION_METRICS):
        raise RuntimeError("unified weekly result prediction metrics are invalid")
    if not isinstance(portfolio_metrics, dict) or set(portfolio_metrics) != set(PORTFOLIO_METRICS):
        raise RuntimeError("unified weekly result portfolio metrics are invalid")
    for name, value in {**prediction, **portfolio_metrics}.items():
        _finite(value, f"weekly_result.{name}")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {
        "daily_series",
        "holdings",
        "raw_report",
    }:
        raise RuntimeError("unified weekly result artifacts are invalid")
    for name, artifact in artifacts.items():
        _artifact(artifact, f"weekly_result.{name}")
    return payload


def validate_catalog(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("unified weekly catalog is not an object")
    verify_canonical_receipt(payload, CATALOG_SCHEMA)
    expected = {(family, portfolio) for family in MODEL_FAMILIES for portfolio in PORTFOLIOS}
    if payload.get("protocol_id") != "itransformer-b2-vs-kronos-base-weekly-v1" or not isinstance(
        payload.get("entries"), list
    ):
        raise RuntimeError("unified weekly catalog identity is invalid")
    _relative_artifact(payload.get("protocol_path"), "weekly_catalog.protocol_path")
    require_sha(payload.get("protocol_receipt_sha256"), "weekly_catalog.protocol_receipt_sha256")
    observed: set[tuple[str, str]] = set()
    for entry in payload["entries"]:
        if not isinstance(entry, dict):
            raise RuntimeError("unified weekly catalog entry is invalid")
        pair = (entry.get("model_family_id"), entry.get("portfolio_id"))
        if pair not in expected or pair in observed or entry.get("id") != result_id(*pair):
            raise RuntimeError("unified weekly catalog matrix is invalid")
        observed.add(pair)
        if (
            entry.get("online_paper_equivalent") is not False
            or entry.get("promotion_eligible") is not False
        ):
            raise RuntimeError("unified weekly catalog firewall is invalid")
        _relative_artifact(entry.get("receipt_path"), "weekly_catalog.receipt_path")
        require_sha(entry.get("receipt_sha256"), "weekly_catalog.receipt_sha256")
    if observed != expected:
        raise RuntimeError("unified weekly catalog is incomplete")
    return payload
