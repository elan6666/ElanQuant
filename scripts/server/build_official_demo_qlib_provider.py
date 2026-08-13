#!/usr/bin/env python3
"""Build an immutable Qlib provider for the official-demo method track."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import pickle
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from elanquant.contracts.official_demo import canonical_hash, sha256_file


def tree_hash(root: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
        count += 1
    return digest.hexdigest(), count


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def write_symbol(frame: pd.DataFrame, path: Path) -> None:
    output = frame.copy().sort_index()
    output = output[~output.index.duplicated(keep=False)]
    output.index = pd.to_datetime(output.index)
    output = output.rename(columns={"vol": "volume", "amt": "amount"})
    output["factor"] = 1.0
    output["change"] = output["close"].pct_change(fill_method=None).fillna(0.0)
    output.insert(0, "date", output.index.strftime("%Y-%m-%d"))
    output[
        ["date", "open", "high", "low", "close", "volume", "amount", "factor", "change"]
    ].to_csv(path, index=False, float_format="%.17g")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--benchmark-receipt", type=Path, required=True)
    parser.add_argument("--dumper", type=Path, required=True)
    parser.add_argument("--qlib-site-packages", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    out_dir = args.out_dir.resolve()
    if out_dir.exists():
        raise RuntimeError("Qlib provider output is immutable; use a new run id")
    if root not in out_dir.parents:
        raise RuntimeError("Qlib provider must remain under the ElanQuant root")
    manifest = json.loads(args.dataset_manifest.read_text(encoding="utf-8"))
    relative_dataset = args.dataset.resolve().relative_to(args.dataset_manifest.parent).as_posix()
    dataset_entry = manifest.get("files", {}).get(relative_dataset)
    if (
        manifest.get("status") != "PASS"
        or not isinstance(dataset_entry, dict)
        or dataset_entry.get("sha256") != sha256_file(args.dataset)
    ):
        raise RuntimeError("Qlib provider source does not match the admitted dataset")
    benchmark = json.loads(args.benchmark_receipt.read_text(encoding="utf-8"))
    benchmark_content = dict(benchmark)
    benchmark_claimed = benchmark_content.pop("receipt_hash", None)
    benchmark_csv = args.benchmark_receipt.parent / str(benchmark.get("file", {}).get("name"))
    if (
        benchmark.get("status") != "PASS"
        or canonical_hash(benchmark_content) != benchmark_claimed
        or benchmark.get("file", {}).get("sha256") != sha256_file(benchmark_csv)
    ):
        raise RuntimeError("benchmark receipt is invalid")
    data = pickle.loads(args.dataset.read_bytes())
    if not isinstance(data, dict) or not data:
        raise RuntimeError("official validation dataset is empty")

    csv_root = out_dir / "csv"
    provider_root = out_dir / "provider"
    csv_root.mkdir(parents=True, mode=0o700)
    for code in sorted(data):
        write_symbol(data[code], csv_root / f"{code}.csv")
    benchmark_frame = pd.read_csv(benchmark_csv, dtype={"trade_date": str})
    benchmark_frame["datetime"] = pd.to_datetime(
        benchmark_frame["trade_date"], format="%Y%m%d"
    )
    benchmark_frame = benchmark_frame.set_index("datetime").rename(
        columns={"vol": "volume", "amount": "amount"}
    )
    if "volume" not in benchmark_frame:
        benchmark_frame["volume"] = 0.0
    if "amount" not in benchmark_frame:
        benchmark_frame["amount"] = 0.0
    write_symbol(
        benchmark_frame[["open", "high", "low", "close", "volume", "amount"]].rename(
            columns={"volume": "vol", "amount": "amt"}
        ),
        csv_root / "SH000300.csv",
    )

    # Append only after importing the research environment's pandas/numpy. The
    # existing Qlib venv uses an older pandas that cannot read extended-v2.
    sys.path.append(str(args.qlib_site_packages.resolve()))
    spec = importlib.util.spec_from_file_location("elanquant_qlib_dumper", args.dumper.resolve())
    if spec is None or spec.loader is None:
        raise RuntimeError("Qlib dumper cannot be imported")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    dumper = module.DumpDataAll(
        csv_path=csv_root,
        qlib_dir=provider_root,
        freq="day",
        max_workers=min(16, os.cpu_count() or 1),
        date_field_name="date",
        include_fields="open,high,low,close,volume,amount,factor,change",
    )
    dumper.dump()
    provider_sha, provider_files = tree_hash(provider_root)
    csv_sha, csv_files = tree_hash(csv_root)
    receipt: dict[str, Any] = {
        "schema_version": "elanquant_official_demo_qlib_provider_v1",
        "status": "PASS",
        "generated_at": datetime.now(UTC).isoformat(),
        "selection_split": "validation_2025",
        "test_viewed_consumed": False,
        "dataset_manifest_sha256": sha256_file(args.dataset_manifest),
        "dataset_file_sha256": sha256_file(args.dataset),
        "benchmark_receipt_sha256": sha256_file(args.benchmark_receipt),
        "dumper_sha256": sha256_file(args.dumper),
        "provider_tree_sha256": provider_sha,
        "provider_files": provider_files,
        "source_csv_tree_sha256": csv_sha,
        "source_csv_files": csv_files,
        "provider_path": provider_root.relative_to(root).as_posix(),
        "symbol_count": len(data),
        "benchmark": "SH000300",
        "deviations": [
            (
                "Provider is exported from admitted ElanQuant data rather than the "
                "author's Qlib bundle."
            ),
            (
                "Raw prices use factor=1; corporate-action handling remains a disclosed "
                "data limitation."
            ),
            (
                "Dynamic PIT membership is enforced by signal availability rather than "
                "a static csi300 file."
            ),
        ],
    }
    receipt["receipt_hash"] = canonical_hash(receipt)
    atomic_json(receipt, out_dir / "provider-receipt.json")
    print(
        json.dumps(
            {"status": "PASS", "provider_files": provider_files, "out": str(out_dir)}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
