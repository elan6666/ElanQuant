#!/usr/bin/env python3
"""Freeze the Top3/Drop1/Hold5 post-hoc protocol before either backtest."""

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

from elanquant.contracts.historical_variants import (
    EXECUTION_DOMAIN,
    TOP3_STRATEGY,
    TOP3_VARIANT_ID_V2,
    VARIANT_LOCK_SCHEMA_V2,
    validate_variant_lock,
)

from elanquant.contracts.official_demo import (
    EXPECTED_EXECUTION,
    MODEL_CELL,
    PRIMARY_SIGNAL,
    SIGNALS,
    canonical_hash,
    sha256_file,
    validate_signal_receipt,
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


def source(root: Path, split: str, signal_path: Path, provider_path: Path) -> dict[str, Any]:
    signal = validate_signal_receipt(read_json(signal_path))
    provider = read_json(provider_path)
    content = dict(provider)
    claimed = content.pop("receipt_hash", None)
    if provider.get("status") != "PASS" or canonical_hash(content) != claimed:
        raise RuntimeError(f"provider receipt is not canonical: {provider_path}")
    provider_root = (root / str(provider["provider_path"])).resolve()
    provider_sha, provider_files = tree_hash(provider_root)
    if provider_sha != provider.get("provider_tree_sha256") or provider_files != provider.get(
        "provider_files"
    ):
        raise RuntimeError(f"provider tree changed: {provider_root}")
    expected_track = (
        "official-demo-method-extended-pit-v1"
        if split == "validation_2025"
        else "official-demo-method-corrected-opened-2026-v1"
    )
    if signal.get("id") != expected_track:
        raise RuntimeError(f"signal split mismatch: {split}")
    artifact = signal["artifacts"]["signals"]
    signal_artifact = (root / str(artifact["path"])).resolve()
    if sha256_file(signal_artifact) != artifact["sha256"]:
        raise RuntimeError("signal artifact changed")
    return {
        "split": split,
        "track_id": expected_track,
        "signal_receipt_path": signal_path.resolve().relative_to(root).as_posix(),
        "signal_receipt_sha256": sha256_file(signal_path),
        "signal_artifact_sha256": artifact["sha256"],
        "provider_receipt_path": provider_path.resolve().relative_to(root).as_posix(),
        "provider_receipt_sha256": sha256_file(provider_path),
        "provider_tree_sha256": provider_sha,
        "support": {
            "rows": signal["support"]["rows"],
            "cross_sections": signal["support"]["cross_sections"],
            "anchor_set_sha256": signal["support"]["anchor_set_sha256"],
        },
        "model": {
            key: signal[key]
            for key in (
                "training_matrix_sha256",
                "tokenizer_sha256",
                "predictor_sha256",
                "model_config_sha256",
                "dataset_manifest_sha256",
            )
        },
        "dataset_file_sha256": signal["dataset_file_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--qlib-site-packages", type=Path, required=True)
    parser.add_argument("--validation-signal-receipt", type=Path, required=True)
    parser.add_argument("--validation-provider-receipt", type=Path, required=True)
    parser.add_argument("--opened-signal-receipt", type=Path, required=True)
    parser.add_argument("--opened-provider-receipt", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.out.resolve()
    if output.exists() or root not in output.parents:
        raise RuntimeError("variant lock must be a new file under root")
    sources = [
        source(
            root,
            "validation_2025",
            args.validation_signal_receipt,
            args.validation_provider_receipt,
        ),
        source(
            root,
            "test_viewed_2026",
            args.opened_signal_receipt,
            args.opened_provider_receipt,
        ),
    ]
    if sources[0]["model"] != sources[1]["model"]:
        raise RuntimeError("source tracks do not bind the same frozen model")
    matrix = read_json(args.matrix)
    cells = [cell for cell in matrix.get("cells", []) if cell.get("id") == MODEL_CELL]
    if matrix.get("status") != "PASS" or len(cells) != 1:
        raise RuntimeError("sealed Small official-ft matrix cell is absent")
    cell = cells[0]
    if (
        sha256_file(args.matrix) != sources[0]["model"]["training_matrix_sha256"]
        or cell.get("tokenizer_sha256") != sources[0]["model"]["tokenizer_sha256"]
        or cell.get("predictor_sha256") != sources[0]["model"]["predictor_sha256"]
        or cell.get("config_sha256") != sources[0]["model"]["model_config_sha256"]
    ):
        raise RuntimeError("source tracks differ from the sealed matrix")
    sys.path.append(str(args.qlib_site_packages.resolve()))
    import qlib

    distribution = importlib.metadata.distribution("pyqlib")
    dist_root = Path(str(distribution._path))
    qlib_sha, _ = tree_hash(Path(qlib.__file__).resolve().parent, "*.py")
    model = sources[0].pop("model")
    sources[1].pop("model")
    payload: dict[str, Any] = {
        "schema_version": VARIANT_LOCK_SCHEMA_V2,
        "status": "PASS",
        "id": TOP3_VARIANT_ID_V2,
        "locked_at": datetime.now(UTC).isoformat(),
        "model_cell_id": MODEL_CELL,
        "primary_signal": PRIMARY_SIGNAL,
        "signals": list(SIGNALS),
        "strategy": dict(TOP3_STRATEGY),
        "execution": dict(EXPECTED_EXECUTION),
        "execution_domain": EXECUTION_DOMAIN,
        "online_paper_equivalent": False,
        "promotion_eligible": False,
        "selection_eligible": False,
        "used_for_selection": False,
        "post_hoc_after_test_viewed": True,
        "runner_path": args.runner.resolve().relative_to(root).as_posix(),
        "runner_sha256": sha256_file(args.runner),
        "contract_path": args.contract.resolve().relative_to(root).as_posix(),
        "contract_sha256": sha256_file(args.contract),
        "qlib_version": importlib.metadata.version("pyqlib"),
        "qlib_metadata_sha256": sha256_file(dist_root / "METADATA"),
        "qlib_record_sha256": sha256_file(dist_root / "RECORD"),
        "qlib_source_tree_sha256": qlib_sha,
        **model,
        "sources": sources,
    }
    payload["receipt_hash"] = canonical_hash(payload)
    validate_variant_lock(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, output)
    print(json.dumps({"status": "PASS", "out": str(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
