from __future__ import annotations

import hashlib
import json
from typing import Any

PROFILE_SCHEMA = "elanquant_execution_profile_v1"
RECEIPT_SCHEMA = "elanquant_execution_receipt_v1"
PROFILE_IDS = {
    "local-apple-silicon",
    "remote-linux-nvidia",
    "legacy-yilangliu",
}
RELEASES = {"small", "base"}
DEVICES = {"cpu", "mps", "cuda"}
RECEIPT_STATUSES = {"PASS", "UNAVAILABLE"}
FROZEN_PROFILE_PAYLOADS: dict[str, dict[str, object]] = {
    "local-apple-silicon": {
        "schema_version": PROFILE_SCHEMA,
        "id": "local-apple-silicon",
        "visibility": "public",
        "operating_systems": ["Darwin"],
        "architectures": ["arm64", "aarch64"],
        "allowed_devices": ["mps", "cpu"],
        "default_device": "mps",
        "allowed_releases": ["small", "base"],
        "default_release": "small",
        "research_only_releases": ["base"],
        "require_explicit_base": True,
    },
    "remote-linux-nvidia": {
        "schema_version": PROFILE_SCHEMA,
        "id": "remote-linux-nvidia",
        "visibility": "public",
        "operating_systems": ["Linux"],
        "architectures": ["x86_64", "aarch64"],
        "allowed_devices": ["cuda"],
        "default_device": "cuda",
        "allowed_releases": ["small", "base"],
        "default_release": "small",
        "research_only_releases": ["base"],
        "require_explicit_base": True,
    },
    "legacy-yilangliu": {
        "schema_version": PROFILE_SCHEMA,
        "id": "legacy-yilangliu",
        "visibility": "private",
        "operating_systems": ["Linux"],
        "architectures": ["x86_64"],
        "allowed_devices": ["cuda"],
        "default_device": "cuda",
        "allowed_releases": ["small"],
        "default_release": "small",
        "research_only_releases": [],
        "require_explicit_base": False,
    },
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


def valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def validate_execution_profile(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("execution profile must be an object")
    profile = dict(payload)
    expected_keys = {
        "schema_version",
        "id",
        "visibility",
        "operating_systems",
        "architectures",
        "allowed_devices",
        "default_device",
        "allowed_releases",
        "default_release",
        "research_only_releases",
        "require_explicit_base",
    }
    if set(profile) != expected_keys:
        raise ValueError("execution profile fields are not canonical")
    if profile["schema_version"] != PROFILE_SCHEMA or profile["id"] not in PROFILE_IDS:
        raise ValueError("execution profile identity is invalid")
    if profile["visibility"] not in {"public", "private"}:
        raise ValueError("execution profile visibility is invalid")
    for field in ("operating_systems", "architectures"):
        values = profile[field]
        if (
            not isinstance(values, list)
            or not values
            or not all(isinstance(item, str) and item for item in values)
            or len(values) != len(set(values))
        ):
            raise ValueError(f"execution profile {field} is invalid")
    devices = profile["allowed_devices"]
    releases = profile["allowed_releases"]
    research_only = profile["research_only_releases"]
    if (
        not isinstance(devices, list)
        or not devices
        or not set(devices) <= DEVICES
        or len(devices) != len(set(devices))
        or profile["default_device"] not in devices
    ):
        raise ValueError("execution profile device policy is invalid")
    if (
        not isinstance(releases, list)
        or not releases
        or not set(releases) <= RELEASES
        or len(releases) != len(set(releases))
        or profile["default_release"] not in releases
        or not isinstance(research_only, list)
        or not set(research_only) <= set(releases)
        or len(research_only) != len(set(research_only))
    ):
        raise ValueError("execution profile release policy is invalid")
    if not isinstance(profile["require_explicit_base"], bool):
        raise ValueError("execution profile Base policy is invalid")
    if profile["require_explicit_base"] and "base" not in research_only:
        raise ValueError("Base must remain research-only when explicit opt-in is required")
    if profile["id"] == "legacy-yilangliu" and profile["visibility"] != "private":
        raise ValueError("legacy profile must remain private")
    if profile != FROZEN_PROFILE_PAYLOADS[str(profile["id"])]:
        raise ValueError("execution profile differs from its frozen policy")
    return profile


def validate_execution_receipt(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("execution receipt must be an object")
    receipt = dict(payload)
    receipt_hash = receipt.pop("receipt_hash", None)
    expected_keys = {
        "schema_version",
        "status",
        "checked_at",
        "profile_id",
        "model_release",
        "research_only",
        "requested_device",
        "resolved_device",
        "inference_batch_size",
        "inference_code_sha256",
        "capabilities",
        "reasons",
        "execution_identity_sha256",
    }
    if set(receipt) != expected_keys:
        raise ValueError("execution receipt fields are not canonical")
    if (
        receipt["schema_version"] != RECEIPT_SCHEMA
        or receipt["status"] not in RECEIPT_STATUSES
        or receipt["profile_id"] not in PROFILE_IDS
        or receipt["model_release"] not in RELEASES
        or receipt["requested_device"] not in DEVICES
        or receipt["resolved_device"] not in DEVICES | {None}
        or not isinstance(receipt["inference_batch_size"], int)
        or isinstance(receipt["inference_batch_size"], bool)
        or receipt["inference_batch_size"] <= 0
        or not valid_sha256(receipt["inference_code_sha256"])
        or not isinstance(receipt["research_only"], bool)
        or not isinstance(receipt["checked_at"], str)
        or not receipt["checked_at"]
        or not isinstance(receipt["reasons"], list)
        or not all(isinstance(item, str) and item for item in receipt["reasons"])
        or not valid_sha256(receipt["execution_identity_sha256"])
        or not valid_sha256(receipt_hash)
    ):
        raise ValueError("execution receipt identity is invalid")
    capabilities = receipt["capabilities"]
    if not isinstance(capabilities, dict) or set(capabilities) != {
        "operating_system",
        "architecture",
        "python_version",
        "torch_version",
        "cpu_available",
        "mps_available",
        "cuda_available",
        "device_name",
    }:
        raise ValueError("execution capabilities are invalid")
    if (
        not all(
            isinstance(capabilities[field], bool)
            for field in ("cpu_available", "mps_available", "cuda_available")
        )
        or not all(
            isinstance(capabilities[field], str) and capabilities[field]
            for field in ("operating_system", "architecture", "python_version")
        )
        or capabilities["torch_version"] is not None
        and not isinstance(capabilities["torch_version"], str)
        or capabilities["device_name"] is not None
        and not isinstance(capabilities["device_name"], str)
    ):
        raise ValueError("execution capability values are invalid")
    profile = FROZEN_PROFILE_PAYLOADS[str(receipt["profile_id"])]
    if (
        receipt["model_release"] not in profile["allowed_releases"]
        or receipt["requested_device"] not in profile["allowed_devices"]
        or receipt["research_only"]
        != (receipt["model_release"] in profile["research_only_releases"])
    ):
        raise ValueError("execution receipt differs from its profile policy")
    if receipt["status"] == "PASS":
        if receipt["resolved_device"] != receipt["requested_device"] or receipt["reasons"]:
            raise ValueError("passing execution receipt contains a fallback or reasons")
        availability_field = {
            "cpu": "cpu_available",
            "mps": "mps_available",
            "cuda": "cuda_available",
        }[str(receipt["requested_device"])]
        if (
            not capabilities[availability_field]
            or capabilities["operating_system"] not in profile["operating_systems"]
            or capabilities["architecture"] not in profile["architectures"]
        ):
            raise ValueError("passing execution receipt is not supported by its capabilities")
    elif receipt["resolved_device"] is not None or not receipt["reasons"]:
        raise ValueError("unavailable execution receipt is incomplete")
    identity = {
        "profile_id": receipt["profile_id"],
        "requested_device": receipt["requested_device"],
        "resolved_device": receipt["resolved_device"],
        "inference_batch_size": receipt["inference_batch_size"],
        "inference_code_sha256": receipt["inference_code_sha256"],
        "capabilities": capabilities,
    }
    if canonical_hash(identity) != receipt["execution_identity_sha256"]:
        raise ValueError("execution identity hash is invalid")
    if canonical_hash(receipt) != receipt_hash:
        raise ValueError("execution receipt hash is invalid")
    payload_copy = dict(receipt)
    payload_copy["receipt_hash"] = receipt_hash
    return payload_copy
