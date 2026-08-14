"""Fail-closed contracts for the official-split-v3 online compatibility release."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from scripts.research.online_release_v3 import validate_method_lock, validate_release

COMPATIBILITY_SCHEMA = "elanquant_official_split_online_compatibility_v1"
COMPATIBILITY_RELEASE_SCHEMA = (
    "elanquant_official_split_online_compatibility_release_v1"
)
COMPATIBILITY_MODE = "COLUMN_ALIAS_AND_EVALUATION_FILENAME_ONLY"
ALIAS_MAPPING = {"vol": "volume", "amt": "amount"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RELEASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SOURCE_FILES = {
    "training-matrix.json",
    "analysis-lock.json",
    "online-method-lock.json",
    "rolling-evaluation.json",
    "historical-catalog.json",
    "manifest.json",
}
_TARGET_FILES = {
    "training-matrix.json",
    "analysis-lock.json",
    "online-method-lock.json",
    "rolling-evaluation.json",
    "formal-evaluation.json",
    "historical-catalog.json",
    "source-manifest.json",
    "compatibility-receipt.json",
    "manifest.json",
}


class OnlineCompatibilityError(RuntimeError):
    """Raised when compatibility evidence is incomplete or changed."""


def canonical_hash(payload: Any) -> str:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(rendered.encode()).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha(value: object, name: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise OnlineCompatibilityError(f"{name} must be a lowercase SHA-256")
    return value


def validate_compatibility_receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(payload)
    claimed = value.pop("receipt_hash", None)
    expected_keys = {
        "schema_version",
        "status",
        "source_release_id",
        "target_release_id",
        "compatibility_mode",
        "source_manifest_sha256",
        "source_manifest_receipt_hash",
        "source_artifacts",
        "source_artifact_set_sha256",
        "online_snapshot_adapter_sha256",
        "online_fetcher_sha256",
        "compatibility_contract_sha256",
        "original_online_runner_sha256",
        "original_online_contract_sha256",
        "column_aliases",
        "value_transform",
        "formal_evaluation_alias",
        "source_preserved",
        "method_identity_unchanged",
        "applied_after_viewed_results",
        "test_metrics_used_for_selection",
        "training_evaluation_backtest_rerun",
        "used_for_selection",
        "promotion_eligible",
    }
    if set(value) != expected_keys or claimed != canonical_hash(value):
        raise OnlineCompatibilityError("compatibility receipt is not canonical")
    if (
        value.get("schema_version") != COMPATIBILITY_SCHEMA
        or value.get("status") != "PASS"
        or value.get("compatibility_mode") != COMPATIBILITY_MODE
        or value.get("column_aliases") != ALIAS_MAPPING
        or value.get("value_transform") != "IDENTITY_NO_SCALE_NO_FILL_NO_REORDER"
        or value.get("formal_evaluation_alias")
        != {
            "source": "rolling-evaluation.json",
            "alias": "formal-evaluation.json",
            "semantics": "BYTE_IDENTICAL_INDEPENDENT_COPY",
        }
        or value.get("source_preserved") is not True
        or value.get("method_identity_unchanged") is not True
        or value.get("applied_after_viewed_results") is not True
        or value.get("test_metrics_used_for_selection") is not False
        or value.get("training_evaluation_backtest_rerun") is not False
        or value.get("used_for_selection") is not False
        or value.get("promotion_eligible") is not False
    ):
        raise OnlineCompatibilityError("compatibility firewall is invalid")
    source_id, target_id = value.get("source_release_id"), value.get("target_release_id")
    if (
        not isinstance(source_id, str)
        or not source_id
        or not isinstance(target_id, str)
        or not target_id
        or source_id == target_id
        or _RELEASE_ID.fullmatch(source_id) is None
        or _RELEASE_ID.fullmatch(target_id) is None
    ):
        raise OnlineCompatibilityError("compatibility release ids are invalid")
    for field in (
        "source_manifest_sha256",
        "source_manifest_receipt_hash",
        "source_artifact_set_sha256",
        "online_snapshot_adapter_sha256",
        "online_fetcher_sha256",
        "compatibility_contract_sha256",
        "original_online_runner_sha256",
        "original_online_contract_sha256",
    ):
        _sha(value.get(field), field)
    artifacts = value.get("source_artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != _SOURCE_FILES:
        raise OnlineCompatibilityError("source artifact set is not exact")
    for name, identity in artifacts.items():
        if (
            not isinstance(identity, Mapping)
            or set(identity) != {"sha256", "bytes"}
            or not isinstance(identity.get("bytes"), int)
            or isinstance(identity.get("bytes"), bool)
            or int(identity["bytes"]) <= 0
        ):
            raise OnlineCompatibilityError(f"source artifact identity is invalid: {name}")
        _sha(identity.get("sha256"), f"source_artifacts.{name}.sha256")
    if value["source_artifact_set_sha256"] != canonical_hash(dict(artifacts)):
        raise OnlineCompatibilityError("source artifact set hash is invalid")
    value["receipt_hash"] = claimed
    return value


def validate_compatibility_release(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(payload)
    claimed = value.pop("receipt_hash", None)
    if (
        value.get("schema_version") != COMPATIBILITY_RELEASE_SCHEMA
        or value.get("status") != "PASS"
        or claimed != canonical_hash(value)
    ):
        raise OnlineCompatibilityError("compatibility release is not canonical PASS")
    for field in (
        "source_manifest_sha256",
        "source_manifest_receipt_hash",
        "compatibility_receipt_sha256",
        "online_snapshot_adapter_sha256",
        "compatibility_contract_sha256",
        "training_matrix_sha256",
        "analysis_lock_sha256",
        "online_method_lock_sha256",
        "rolling_evaluation_sha256",
        "historical_catalog_sha256",
        "online_runner_sha256",
    ):
        _sha(value.get(field), field)
    if (
        value.get("compatibility_mode") != COMPATIBILITY_MODE
        or value.get("test_metrics_used_for_selection") is not False
    ):
        raise OnlineCompatibilityError("compatibility release firewall is invalid")
    value["receipt_hash"] = claimed
    return value


def validate_compatibility_release_dir(
    target: Path, *, adapter_path: Path, fetcher_path: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    target = target.resolve()
    if not target.is_dir() or {path.name for path in target.iterdir()} != _TARGET_FILES:
        raise OnlineCompatibilityError("compatibility release file set is not exact")
    if any(not path.is_file() or path.is_symlink() for path in target.iterdir()):
        raise OnlineCompatibilityError("compatibility release must contain regular files")
    manifest = validate_compatibility_release(
        json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    )
    receipt = validate_compatibility_receipt(
        json.loads((target / "compatibility-receipt.json").read_text(encoding="utf-8"))
    )
    source = target.parent / str(receipt["source_release_id"])
    if not source.is_dir() or {path.name for path in source.iterdir()} != _SOURCE_FILES:
        raise OnlineCompatibilityError("source release file set is not exact")
    if any(not path.is_file() or path.is_symlink() for path in source.iterdir()):
        raise OnlineCompatibilityError("source release must contain regular files")
    source_manifest_path = source / "manifest.json"
    source_manifest = validate_release(
        json.loads(source_manifest_path.read_text(encoding="utf-8"))
    )
    method_lock = validate_method_lock(
        json.loads((source / "online-method-lock.json").read_text(encoding="utf-8"))
    )
    if (
        sha256(source_manifest_path) != receipt["source_manifest_sha256"]
        or source_manifest["receipt_hash"] != receipt["source_manifest_receipt_hash"]
        or (target / "source-manifest.json").read_bytes() != source_manifest_path.read_bytes()
        or sha256(target / "compatibility-receipt.json")
        != manifest["compatibility_receipt_sha256"]
        or sha256(adapter_path.resolve()) != receipt["online_snapshot_adapter_sha256"]
        or sha256(fetcher_path.resolve()) != receipt["online_fetcher_sha256"]
        or sha256(Path(__file__).resolve()) != receipt["compatibility_contract_sha256"]
        or manifest["online_snapshot_adapter_sha256"]
        != receipt["online_snapshot_adapter_sha256"]
        or manifest["compatibility_contract_sha256"]
        != receipt["compatibility_contract_sha256"]
        or manifest["source_manifest_sha256"] != receipt["source_manifest_sha256"]
        or manifest["source_manifest_receipt_hash"]
        != receipt["source_manifest_receipt_hash"]
        or manifest.get("release_id") != receipt["target_release_id"]
        or manifest.get("source_release_id") != receipt["source_release_id"]
        or target.name != receipt["target_release_id"]
        or source.name != receipt["source_release_id"]
        or manifest.get("compatibility_mode") != receipt["compatibility_mode"]
        or receipt["original_online_runner_sha256"]
        != source_manifest["online_runner_sha256"]
        or receipt["original_online_contract_sha256"]
        != method_lock["online_contract_sha256"]
    ):
        raise OnlineCompatibilityError("compatibility release provenance is mismatched")
    for name, identity in receipt["source_artifacts"].items():
        source_path, target_path = source / name, target / name
        if (
            source_path.stat().st_size != identity["bytes"]
            or sha256(source_path) != identity["sha256"]
        ):
            raise OnlineCompatibilityError(f"source artifact changed: {name}")
        if name == "manifest.json":
            continue
        if target_path.read_bytes() != source_path.read_bytes():
            raise OnlineCompatibilityError(f"compatibility payload differs: {name}")
    if (target / "formal-evaluation.json").read_bytes() != (
        target / "rolling-evaluation.json"
    ).read_bytes():
        raise OnlineCompatibilityError("formal evaluation alias is not byte-identical")
    core_fields = (
        "training_matrix_sha256",
        "analysis_lock_sha256",
        "online_method_lock_sha256",
        "rolling_evaluation_sha256",
        "historical_catalog_sha256",
        "online_runner_sha256",
        "primary_models",
        "selection_basis",
        "test_metrics_used_for_selection",
        "online_signal",
        "online_sampling",
    )
    if any(manifest.get(field) != source_manifest.get(field) for field in core_fields):
        raise OnlineCompatibilityError("compatibility release changed method identity")
    return manifest, receipt, source_manifest
