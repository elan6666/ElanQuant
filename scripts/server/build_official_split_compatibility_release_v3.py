#!/usr/bin/env python3
"""Build a sibling v3 release for column and evaluation-filename compatibility."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any

from scripts.research import online_compatibility_v3 as compatibility_contract
from scripts.research.online_compatibility_v3 import (
    ALIAS_MAPPING,
    COMPATIBILITY_MODE,
    COMPATIBILITY_RELEASE_SCHEMA,
    COMPATIBILITY_SCHEMA,
    canonical_hash,
    sha256,
    validate_compatibility_receipt,
    validate_compatibility_release,
    validate_compatibility_release_dir,
)
from scripts.research.online_release_v3 import validate_method_lock, validate_release

SOURCE_FILES = (
    "training-matrix.json",
    "analysis-lock.json",
    "online-method-lock.json",
    "rolling-evaluation.json",
    "historical-catalog.json",
    "manifest.json",
)


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source-release", type=Path, required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--fetcher", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    source, output = args.source_release.resolve(), args.out_dir.resolve()
    adapter, fetcher = args.adapter.resolve(), args.fetcher.resolve()
    if (
        output.exists()
        or root not in output.parents
        or source.parent != output.parent
        or output.name != args.release_id
        or source == output
    ):
        raise RuntimeError("compatibility release must be a new sibling under root")
    if {path.name for path in source.iterdir()} != set(SOURCE_FILES):
        raise RuntimeError("source release file set is not exact")
    if any(not path.is_file() or path.is_symlink() for path in source.iterdir()):
        raise RuntimeError("source release must contain regular files")
    source_manifest_path = source / "manifest.json"
    source_manifest = validate_release(read_object(source_manifest_path))
    method_lock = validate_method_lock(read_object(source / "online-method-lock.json"))
    if (
        source_manifest["release_id"] == args.release_id
        or method_lock["online_runner_sha256"] != source_manifest["online_runner_sha256"]
        or method_lock["online_contract_sha256"]
        != sha256(root / "source/scripts/research/online_release_v3.py")
        or source_manifest["online_runner_sha256"]
        != sha256(root / "source/scripts/server/evaluate_official_split_online_v3.py")
    ):
        raise RuntimeError("source release method identity is not the locked v3 runtime")
    source_artifacts = {
        name: {"sha256": sha256(source / name), "bytes": (source / name).stat().st_size}
        for name in SOURCE_FILES
    }
    receipt: dict[str, Any] = {
        "schema_version": COMPATIBILITY_SCHEMA,
        "status": "PASS",
        "source_release_id": source_manifest["release_id"],
        "target_release_id": args.release_id,
        "compatibility_mode": COMPATIBILITY_MODE,
        "source_manifest_sha256": sha256(source_manifest_path),
        "source_manifest_receipt_hash": source_manifest["receipt_hash"],
        "source_artifacts": source_artifacts,
        "source_artifact_set_sha256": canonical_hash(source_artifacts),
        "online_snapshot_adapter_sha256": sha256(adapter),
        "online_fetcher_sha256": sha256(fetcher),
        "compatibility_contract_sha256": sha256(
            Path(str(compatibility_contract.__file__)).resolve()
        ),
        "original_online_runner_sha256": source_manifest["online_runner_sha256"],
        "original_online_contract_sha256": method_lock["online_contract_sha256"],
        "column_aliases": ALIAS_MAPPING,
        "value_transform": "IDENTITY_NO_SCALE_NO_FILL_NO_REORDER",
        "formal_evaluation_alias": {
            "source": "rolling-evaluation.json",
            "alias": "formal-evaluation.json",
            "semantics": "BYTE_IDENTICAL_INDEPENDENT_COPY",
        },
        "source_preserved": True,
        "method_identity_unchanged": True,
        "applied_after_viewed_results": True,
        "test_metrics_used_for_selection": False,
        "training_evaluation_backtest_rerun": False,
        "used_for_selection": False,
        "promotion_eligible": False,
    }
    receipt["receipt_hash"] = canonical_hash(receipt)
    validate_compatibility_receipt(receipt)
    temporary = output.with_name(output.name + f".tmp-{os.getpid()}")
    temporary.mkdir(parents=True)
    for name in SOURCE_FILES:
        target_name = "source-manifest.json" if name == "manifest.json" else name
        shutil.copyfile(source / name, temporary / target_name)
    shutil.copyfile(
        source / "rolling-evaluation.json", temporary / "formal-evaluation.json"
    )
    compatibility_path = temporary / "compatibility-receipt.json"
    compatibility_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest: dict[str, Any] = {
        **{
            key: source_manifest[key]
            for key in (
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
        },
        "schema_version": COMPATIBILITY_RELEASE_SCHEMA,
        "status": "PASS",
        "release_id": args.release_id,
        "source_release_id": source_manifest["release_id"],
        "source_manifest_sha256": receipt["source_manifest_sha256"],
        "source_manifest_receipt_hash": receipt["source_manifest_receipt_hash"],
        "compatibility_receipt_sha256": sha256(compatibility_path),
        "compatibility_mode": COMPATIBILITY_MODE,
        "online_snapshot_adapter_sha256": receipt["online_snapshot_adapter_sha256"],
        "compatibility_contract_sha256": receipt["compatibility_contract_sha256"],
    }
    manifest["receipt_hash"] = canonical_hash(manifest)
    validate_compatibility_release(manifest)
    (temporary / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for path in temporary.iterdir():
        os.chmod(path, 0o440)
    os.chmod(temporary, 0o550)
    os.replace(temporary, output)
    validate_compatibility_release_dir(output, adapter_path=adapter, fetcher_path=fetcher)
    print(json.dumps({"status": "PASS", "release_id": args.release_id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
