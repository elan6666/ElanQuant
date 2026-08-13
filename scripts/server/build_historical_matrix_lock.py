#!/usr/bin/env python3
"""Seal the six-model, two-split, two-strategy backtest protocol."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from elanquant.contracts.historical_matrix import (
    LOCK_SCHEMA,
    MODEL_CELLS,
    SPLITS,
    VARIANTS,
    validate_matrix_lock,
    validate_signal_receipt,
)

from elanquant.contracts.official_demo import (
    EXPECTED_EXECUTION,
    PRIMARY_SIGNAL,
    SIGNALS,
    canonical_hash,
    sha256_file,
)


def tree_hash(root: Path, pattern: str = "*") -> tuple[str, int]:
    digest, count = hashlib.sha256(), 0
    for path in sorted(item for item in root.rglob(pattern) if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
        count += 1
    return digest.hexdigest(), count


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return value


def provider_source(root: Path, path: Path) -> dict[str, object]:
    receipt = read_json(path)
    body = dict(receipt)
    claimed = body.pop("receipt_hash", None)
    if receipt.get("status") != "PASS" or canonical_hash(body) != claimed:
        raise RuntimeError(f"provider receipt is not canonical: {path}")
    provider_root = (root / str(receipt["provider_path"])).resolve()
    provider_sha, provider_files = tree_hash(provider_root)
    if (
        provider_sha != receipt.get("provider_tree_sha256")
        or provider_files != receipt.get("provider_files")
    ):
        raise RuntimeError(f"provider tree changed: {provider_root}")
    return {
        "provider_receipt_path": path.resolve().relative_to(root).as_posix(),
        "provider_receipt_sha256": sha256_file(path),
        "provider_tree_sha256": provider_sha,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--signals-root", type=Path, required=True)
    parser.add_argument("--validation-provider-receipt", type=Path, required=True)
    parser.add_argument("--opened-provider-receipt", type=Path, required=True)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--qlib-site-packages", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.out.resolve()
    if output.exists() or root not in output.parents:
        raise RuntimeError("historical matrix lock must be a new file under root")
    providers = {
        "validation_2025": provider_source(root, args.validation_provider_receipt),
        "test_viewed_2026": provider_source(root, args.opened_provider_receipt),
    }
    sources: list[dict[str, object]] = []
    for model in MODEL_CELLS:
        for split in SPLITS:
            path = args.signals_root / model / split / "signal-receipt.json"
            receipt = validate_signal_receipt(read_json(path))
            if receipt["model_cell_id"] != model or receipt["evaluation_split"] != split:
                raise RuntimeError(f"matrix signal source identity mismatch: {model}/{split}")
            artifact = receipt["artifacts"]["signals"]
            artifact_path = (root / str(artifact["path"])).resolve()
            if sha256_file(artifact_path) != artifact["sha256"]:
                raise RuntimeError(f"matrix signal artifact changed: {model}/{split}")
            sources.append(
                {
                    "model_cell_id": model,
                    "evaluation_split": split,
                    "signal_receipt_path": path.resolve().relative_to(root).as_posix(),
                    "signal_receipt_sha256": sha256_file(path),
                    "signal_artifact_sha256": artifact["sha256"],
                    **providers[split],
                    "support": receipt["support"],
                    "model": {
                        key: receipt[key]
                        for key in (
                            "training_matrix_sha256",
                            "tokenizer_sha256",
                            "predictor_sha256",
                            "model_config_sha256",
                            "dataset_manifest_sha256",
                            "dataset_file_sha256",
                        )
                    },
                }
            )
    sys.path.append(str(args.qlib_site_packages.resolve()))
    import qlib

    distribution = importlib.metadata.distribution("pyqlib")
    dist_root = Path(str(distribution._path))
    qlib_sha, _ = tree_hash(Path(qlib.__file__).resolve().parent, "*.py")
    payload: dict[str, Any] = {
        "schema_version": LOCK_SCHEMA,
        "status": "PASS",
        "id": "historical-six-model-matrix-v1",
        "locked_at": datetime.now(UTC).isoformat(),
        "models": list(MODEL_CELLS),
        "splits": list(SPLITS),
        "variants": VARIANTS,
        "primary_signal": PRIMARY_SIGNAL,
        "signals": list(SIGNALS),
        "execution": EXPECTED_EXECUTION,
        "selection_eligible": False,
        "used_for_selection": False,
        "promotion_eligible": False,
        "runner_path": args.runner.resolve().relative_to(root).as_posix(),
        "runner_sha256": sha256_file(args.runner),
        "contract_path": args.contract.resolve().relative_to(root).as_posix(),
        "contract_sha256": sha256_file(args.contract),
        "qlib_version": importlib.metadata.version("pyqlib"),
        "qlib_metadata_sha256": sha256_file(dist_root / "METADATA"),
        "qlib_record_sha256": sha256_file(dist_root / "RECORD"),
        "qlib_source_tree_sha256": qlib_sha,
        "sources": sources,
    }
    payload["receipt_hash"] = canonical_hash(payload)
    validate_matrix_lock(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, output)
    print(json.dumps({"status": "PASS", "out": str(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
