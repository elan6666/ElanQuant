#!/usr/bin/env python3
"""Seal the GET-only official-demo historical backtest catalog."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from elanquant.contracts.official_demo import (
    CATALOG_SCHEMA,
    PRIMARY_SIGNAL,
    STRATEGY_ID,
    canonical_hash,
    sha256_file,
    validate_backtest_catalog,
    validate_backtest_receipt,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--backtest-receipt", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.out.resolve()
    if output.exists():
        raise RuntimeError("historical backtest catalog is immutable; inspect before replacement")
    if root not in output.parents:
        raise RuntimeError("historical backtest catalog must remain under the ElanQuant root")
    receipt = validate_backtest_receipt(
        json.loads(args.backtest_receipt.read_text(encoding="utf-8"))
    )
    payload: dict[str, object] = {
        "schema_version": CATALOG_SCHEMA,
        "status": "PASS",
        "generated_at": datetime.now(UTC).isoformat(),
        "entries": [
            {
                "id": STRATEGY_ID,
                "state": "passed",
                "track_kind": receipt["track_kind"],
                "model_cell_id": receipt["model_cell_id"],
                "selection_eligible": True,
                "selection_split": "validation_2025",
                "test_viewed_consumed": False,
                "primary_signal": PRIMARY_SIGNAL,
                "receipt_sha256": sha256_file(args.backtest_receipt),
                "receipt_path": args.backtest_receipt.resolve().relative_to(root).as_posix(),
                "summary": receipt["metrics"][PRIMARY_SIGNAL],
            }
        ],
    }
    payload["receipt_hash"] = canonical_hash(payload)
    validate_backtest_catalog(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, output)
    print(json.dumps({"status": "PASS", "entries": 1, "out": str(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
