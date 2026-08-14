#!/usr/bin/env python3
"""Seal all inputs before any Plan011 TEST_VIEWED signal or backtest exists."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.research import official_split_v3 as contract_module
from scripts.research.official_split_v3 import (
    ACTIVE_CELLS,
    ANALYSIS_LOCK_SCHEMA,
    STRATEGIES,
    UPSTREAM_COMMIT,
    canonical_hash,
    validate_analysis_lock,
    validate_dataset_admission,
    validate_dataset_manifest,
    validate_matrix,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_hash(root: Path, pattern: str = "*.py") -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob(pattern) if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256(path)))
    return digest.hexdigest()


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--dataset-admission", type=Path, required=True)
    parser.add_argument("--provider-receipt", type=Path, required=True)
    parser.add_argument("--signal-runner", type=Path, required=True)
    parser.add_argument("--signal-helper", type=Path, required=True)
    parser.add_argument("--evaluation-helper", type=Path, required=True)
    parser.add_argument("--backtest-runner", type=Path, required=True)
    parser.add_argument("--backtest-helper", type=Path, required=True)
    parser.add_argument("--qlib-site-packages", type=Path, required=True)
    parser.add_argument("--trade-calendar", type=Path, required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.out.resolve()
    if output.exists() or root not in output.parents:
        raise RuntimeError("analysis lock must be a new file under root")
    if args.results_root.exists():
        raise RuntimeError("analysis results already exist; pre-result lock refused")
    matrix = validate_matrix(read_object(args.matrix))
    manifest = validate_dataset_manifest(read_object(args.dataset_manifest))
    admission = validate_dataset_admission(read_object(args.dataset_admission))
    if admission["dataset_manifest_sha256"] != sha256(args.dataset_manifest):
        raise RuntimeError("dataset admission does not bind the manifest")
    test_identity = "official/test_data.pkl"
    test_pickle = args.dataset_manifest.parent / test_identity
    if sha256(test_pickle) != manifest["files"][test_identity]["sha256"]:
        raise RuntimeError("test pickle differs from the manifest")
    if matrix.get("split_receipt_hash") != manifest["split_receipt_hash"]:
        raise RuntimeError("training matrix and dataset split differ")
    with args.trade_calendar.open(encoding="utf-8", newline="") as handle:
        calendar_rows = list(csv.DictReader(handle))
    frozen = str(manifest["frozen_latest_session"]).replace("-", "")
    sessions = sorted(
        {
            str(row["cal_date"])
            for row in calendar_rows
            if str(row.get("is_open")) == "1" and str(row["cal_date"]) <= frozen
        }
    )
    session_hash = canonical_hash(
        [f"{value[:4]}-{value[4:6]}-{value[6:]}" for value in sessions]
    )
    if session_hash != manifest["split_contract"]["calendar_sha256"]:
        raise RuntimeError("trade calendar differs from the admitted split calendar")
    provider = read_object(args.provider_receipt)
    provider_body = dict(provider)
    claimed = provider_body.pop("receipt_hash", None)
    if provider.get("status") != "PASS" or canonical_hash(provider_body) != claimed:
        raise RuntimeError("provider receipt is not canonical PASS")

    qlib_root = args.qlib_site_packages.resolve()
    distribution = importlib.metadata.distribution("pyqlib")
    metadata_root = Path(str(distribution._path))
    qlib_package = qlib_root / "qlib"
    if not qlib_package.is_dir():
        raise RuntimeError("Qlib source package missing from locked site-packages")
    payload: dict[str, Any] = {
        "schema_version": ANALYSIS_LOCK_SCHEMA,
        "status": "PASS",
        "locked_at": datetime.now(UTC).isoformat(),
        "upstream_commit": UPSTREAM_COMMIT,
        "model_cells": list(ACTIVE_CELLS),
        "strategies": STRATEGIES,
        "sample_count": 5,
        "test_status": "TEST_VIEWED",
        "used_for_selection": False,
        "promotion_eligible": False,
        "results_root": args.results_root.resolve().relative_to(root).as_posix(),
        "results_root_absent_at_lock": True,
        "matrix_sha256": sha256(args.matrix),
        "dataset_manifest_sha256": sha256(args.dataset_manifest),
        "dataset_admission_sha256": sha256(args.dataset_admission),
        "test_pickle_sha256": sha256(test_pickle),
        "provider_receipt_sha256": sha256(args.provider_receipt),
        "provider_receipt_path": args.provider_receipt.resolve().relative_to(root).as_posix(),
        "signal_runner_sha256": sha256(args.signal_runner),
        "signal_helper_sha256": sha256(args.signal_helper),
        "evaluation_helper_sha256": sha256(args.evaluation_helper),
        "backtest_runner_sha256": sha256(args.backtest_runner),
        "backtest_helper_sha256": sha256(args.backtest_helper),
        "contract_sha256": sha256(Path(str(contract_module.__file__)).resolve()),
        "qlib_version": importlib.metadata.version("pyqlib"),
        "qlib_metadata_sha256": sha256(metadata_root / "METADATA"),
        "qlib_record_sha256": sha256(metadata_root / "RECORD"),
        "qlib_source_tree_sha256": tree_hash(qlib_package),
        "trade_calendar_sha256": sha256(args.trade_calendar),
    }
    payload["receipt_hash"] = canonical_hash(payload)
    validate_analysis_lock(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    print(json.dumps({"status": "PASS", "receipt_hash": payload["receipt_hash"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
