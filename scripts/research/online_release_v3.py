"""Contracts for the portable official-split-v3 online release."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

RELEASE_SCHEMA = "elanquant_official_split_online_release_v3"
INFERENCE_SCHEMA = "elanquant_official_split_online_inference_v3"
PRIMARY_MODELS = {
    "small": "small-official-ft",
    "base": "base-official-ft",
}
ONLINE_SAMPLING = {
    "temperature": 0.6,
    "top_p": 0.9,
    "top_k": 0,
    "sample_count": 10,
}
ONLINE_SIGNAL = "INVERSE_NORMALIZED_TEN_DAY_MEAN_CLOSE_RETURN"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class OnlineReleaseError(RuntimeError):
    """Raised when a v3 online release is incomplete or mismatched."""


def canonical_hash(payload: Any) -> str:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(rendered.encode()).hexdigest()


def _sha(value: object, name: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise OnlineReleaseError(f"{name} must be a lowercase SHA-256")
    return value


def validate_release(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(payload)
    claimed = value.pop("receipt_hash", None)
    if (
        value.get("schema_version") != RELEASE_SCHEMA
        or value.get("status") != "PASS"
        or claimed != canonical_hash(value)
    ):
        raise OnlineReleaseError("online release is not sealed PASS")
    if not isinstance(value.get("release_id"), str) or not value["release_id"]:
        raise OnlineReleaseError("online release id is missing")
    for field in (
        "training_matrix_sha256",
        "analysis_lock_sha256",
        "rolling_evaluation_sha256",
        "historical_catalog_sha256",
        "online_runner_sha256",
    ):
        _sha(value.get(field), field)
    if (
        value.get("primary_models") != PRIMARY_MODELS
        or value.get("selection_basis") != "PREDECLARED_OFFICIAL_FT_METHOD_IDENTITY"
        or value.get("test_metrics_used_for_selection") is not False
        or value.get("online_signal") != ONLINE_SIGNAL
        or value.get("online_sampling") != ONLINE_SAMPLING
    ):
        raise OnlineReleaseError("online release method firewall is invalid")
    value["receipt_hash"] = claimed
    return value


def validate_inference(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(payload)
    if value.get("schema_version") != INFERENCE_SCHEMA or value.get("status") != "PASS":
        raise OnlineReleaseError("online inference is not terminal PASS")
    size = value.get("model_size")
    expected = {f"{size}-zero-shot", f"{size}-official-ft"}
    if size not in PRIMARY_MODELS or value.get("primary_model_id") != PRIMARY_MODELS[size]:
        raise OnlineReleaseError("online primary model is not predeclared official-ft")
    models = value.get("models")
    if not isinstance(models, Mapping) or set(models) != expected:
        raise OnlineReleaseError("online inference model set is not exact")
    if value.get("sampling") != ONLINE_SAMPLING or value.get("signal_definition") != ONLINE_SIGNAL:
        raise OnlineReleaseError("online inference signal protocol drifted")
    for field in (
        "training_matrix_receipt_sha256",
        "data_manifest_sha256",
        "inference_code_sha256",
        "config_sha256",
    ):
        _sha(value.get(field), field)
    return value
