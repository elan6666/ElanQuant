#!/usr/bin/env python3
"""Seal a post-build admission receipt for the immutable extended-v2 dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.server.build_extended_dataset import verify_raw_manifest
from scripts.server.evaluate_and_infer import verify_manifest_files


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_receipt(root: Path) -> dict[str, Any]:
    raw_root = root / "data/raw/extended-csi300-v1"
    processed_root = root / "data/processed/extended-v2"
    raw_manifest_path = raw_root / "manifest.json"
    processed_manifest_path = processed_root / "manifest.json"
    raw_manifest = json.loads(raw_manifest_path.read_text(encoding="utf-8"))
    processed_manifest = json.loads(processed_manifest_path.read_text(encoding="utf-8"))
    if raw_manifest.get("status") != "PASS" or processed_manifest.get("status") != "PASS":
        raise RuntimeError("dataset manifests are not terminal PASS")
    verify_raw_manifest(raw_root, raw_manifest)
    verify_manifest_files(processed_root, processed_manifest)
    raw_sha = sha256(raw_manifest_path)
    if processed_manifest.get("raw_manifest_sha256") != raw_sha:
        raise RuntimeError("processed dataset does not bind the admitted raw manifest")
    return {
        "schema_version": "elanquant_dataset_admission_v1",
        "status": "PASS",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "latest_closed_session": processed_manifest.get("latest_closed_session"),
        "raw_manifest_sha256": raw_sha,
        "processed_manifest_sha256": sha256(processed_manifest_path),
        "raw_files_verified": len(raw_manifest["files"]),
        "processed_files_verified": len(processed_manifest["files"]),
        "admission_code_sha256": sha256(Path(__file__).resolve()),
        "raw_semantic_contract": (
            "closed_world_path_endpoint_symbol_row_count_date_range_sha256"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    output = args.out.resolve()
    if output.exists():
        raise RuntimeError(f"immutable admission receipt already exists: {output}")
    payload = build_receipt(args.root.resolve())
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
