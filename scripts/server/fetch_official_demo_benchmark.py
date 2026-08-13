#!/usr/bin/env python3
"""Fetch one immutable CSI300 benchmark slice through the approved proxy."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from elanquant.contracts.official_demo import canonical_hash, sha256_file


def approved_client(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("elanquant_approved_proxy", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("approved proxy client cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    factory = getattr(module, "get_pro", None)
    if not callable(factory):
        raise RuntimeError("approved proxy client has no get_pro factory")
    return factory()


def atomic_json(payload: dict[str, object], path: Path) -> None:
    temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proxy-client", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--start", default="2024-08-01")
    parser.add_argument("--end", default="2025-12-31")
    args = parser.parse_args()
    out_dir = args.out_dir.resolve()
    if out_dir.exists():
        raise RuntimeError("benchmark output is immutable; use a new run id")
    out_dir.mkdir(parents=True, mode=0o700)
    client = approved_client(args.proxy_client.resolve())
    error: Exception | None = None
    for attempt in range(4):
        try:
            frame = client.index_daily(
                ts_code="000300.SH",
                start_date=args.start.replace("-", ""),
                end_date=args.end.replace("-", ""),
            )
            if not isinstance(frame, pd.DataFrame):
                raise TypeError("index_daily did not return a DataFrame")
            break
        except Exception as caught:
            error = caught
            if attempt == 3:
                raise
            time.sleep(2**attempt)
    else:
        raise RuntimeError("benchmark fetch failed") from error
    required = {"trade_date", "open", "high", "low", "close"}
    if frame.empty or not required.issubset(frame.columns):
        raise RuntimeError("CSI300 benchmark response is empty or incomplete")
    frame = frame.copy()
    frame["trade_date"] = frame["trade_date"].astype(str)
    frame = frame.sort_values("trade_date").drop_duplicates("trade_date", keep=False)
    for column in ("open", "high", "low", "close", "vol", "amount"):
        if column not in frame:
            frame[column] = 0.0
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if frame[["open", "high", "low", "close"]].isna().any().any():
        raise RuntimeError("CSI300 benchmark contains invalid prices")
    csv_path = out_dir / "SH000300.csv"
    frame[["trade_date", "open", "high", "low", "close", "vol", "amount"]].to_csv(
        csv_path, index=False, float_format="%.17g"
    )
    receipt: dict[str, object] = {
        "schema_version": "elanquant_official_demo_benchmark_v1",
        "status": "PASS",
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": "Tushare-compatible approved proxy",
        "transport_caveat": "The approved tutorial proxy uses plain HTTP.",
        "endpoint": "index_daily",
        "ts_code": "000300.SH",
        "benchmark": "SH000300",
        "start": frame["trade_date"].min(),
        "end": frame["trade_date"].max(),
        "rows": len(frame),
        "file": {"name": csv_path.name, "sha256": sha256_file(csv_path)},
    }
    receipt["receipt_hash"] = canonical_hash(receipt)
    atomic_json(receipt, out_dir / "receipt.json")
    print(json.dumps({"status": "PASS", "rows": len(frame), "out": str(out_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
