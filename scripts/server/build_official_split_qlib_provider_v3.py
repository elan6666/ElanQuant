#!/usr/bin/env python3
"""Build the immutable Qlib provider for official-split v3 TEST_VIEWED analysis."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pickle
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from elanquant.contracts.official_demo import sha256_file
from scripts.research.official_split_v3 import canonical_hash, validate_dataset_manifest
from scripts.server.build_official_demo_qlib_provider import tree_hash, write_symbol


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return value


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--benchmark-receipt", type=Path, required=True)
    parser.add_argument("--dumper", type=Path, required=True)
    parser.add_argument("--qlib-site-packages", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    root, output = args.root.resolve(), args.out_dir.resolve()
    if output.exists() or root not in output.parents:
        raise RuntimeError("provider output must be a new directory under root")
    manifest = validate_dataset_manifest(read_object(args.dataset_manifest))
    dataset_path = args.dataset_manifest.parent / "official" / "test_data.pkl"
    entry = manifest["files"].get("official/test_data.pkl")
    if not isinstance(entry, dict) or sha256_file(dataset_path) != entry.get("sha256"):
        raise RuntimeError("test dataset differs from the admitted manifest")

    benchmark = read_object(args.benchmark_receipt)
    benchmark_body = dict(benchmark)
    benchmark_claimed = benchmark_body.pop("receipt_hash", None)
    benchmark_csv = args.benchmark_receipt.parent / str(benchmark.get("file", {}).get("name"))
    if (
        benchmark.get("status") != "PASS"
        or canonical_hash(benchmark_body) != benchmark_claimed
        or benchmark.get("file", {}).get("sha256") != sha256_file(benchmark_csv)
    ):
        raise RuntimeError("benchmark receipt is not canonical PASS")

    data = pickle.loads(dataset_path.read_bytes())
    if not isinstance(data, dict) or not data:
        raise RuntimeError("official-split test dataset is empty")
    csv_root, provider_root = output / "csv", output / "provider"
    csv_root.mkdir(parents=True, mode=0o700)
    for code in sorted(data):
        write_symbol(data[code], csv_root / f"{code}.csv")

    benchmark_frame = pd.read_csv(benchmark_csv, dtype={"trade_date": str})
    benchmark_frame["datetime"] = pd.to_datetime(
        benchmark_frame["trade_date"], format="%Y%m%d"
    )
    benchmark_frame = benchmark_frame.set_index("datetime")
    for column in ("vol", "amount"):
        if column not in benchmark_frame:
            benchmark_frame[column] = 0.0
    write_symbol(
        benchmark_frame[["open", "high", "low", "close", "vol", "amount"]],
        csv_root / "SH000300.csv",
    )

    sys.path.append(str(args.qlib_site_packages.resolve()))
    spec = importlib.util.spec_from_file_location(
        "elanquant_official_split_qlib_dumper", args.dumper.resolve()
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Qlib dumper cannot be imported")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.DumpDataAll(
        csv_path=csv_root,
        qlib_dir=provider_root,
        freq="day",
        max_workers=min(16, os.cpu_count() or 1),
        date_field_name="date",
        include_fields="open,high,low,close,volume,amount,factor,change",
    ).dump()

    provider_sha, provider_files = tree_hash(provider_root)
    csv_sha, csv_files = tree_hash(csv_root)
    receipt: dict[str, Any] = {
        "schema_version": "elanquant_official_split_qlib_provider_v3",
        "status": "PASS",
        "generated_at": datetime.now(UTC).isoformat(),
        "test_status": "TEST_VIEWED",
        "used_for_selection": False,
        "promotion_eligible": False,
        "dataset_manifest_sha256": sha256_file(args.dataset_manifest),
        "dataset_file_sha256": sha256_file(dataset_path),
        "benchmark_receipt_sha256": sha256_file(args.benchmark_receipt),
        "provider_builder_sha256": sha256_file(Path(__file__).resolve()),
        "dumper_sha256": sha256_file(args.dumper),
        "provider_tree_sha256": provider_sha,
        "provider_files": provider_files,
        "source_csv_tree_sha256": csv_sha,
        "source_csv_files": csv_files,
        "provider_path": provider_root.relative_to(root).as_posix(),
        "symbol_count": len(data),
        "benchmark": "SH000300",
        "deviations": [
            "provider is exported from admitted ElanQuant data",
            "prices use factor=1; corporate-action handling remains a limitation",
            "dynamic membership is enforced in the admitted per-symbol dataset",
        ],
    }
    receipt["receipt_hash"] = canonical_hash(receipt)
    output.mkdir(parents=True, exist_ok=True)
    atomic_json(receipt, output / "provider-receipt.json")
    print(json.dumps({"status": "PASS", "provider_files": provider_files}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
