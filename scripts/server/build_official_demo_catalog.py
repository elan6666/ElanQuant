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
    CATALOG_SCHEMA_V2,
    FINAL_TEST_STRATEGY_ID,
    PRIMARY_SIGNAL,
    canonical_hash,
    sha256_file,
    validate_backtest_catalog,
    validate_backtest_receipt,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--backtest-receipt", type=Path, action="append", required=True
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.out.resolve()
    if output.exists():
        raise RuntimeError("historical backtest catalog is immutable; inspect before replacement")
    if root not in output.parents:
        raise RuntimeError("historical backtest catalog must remain under the ElanQuant root")
    receipts = [
        (
            path,
            validate_backtest_receipt(json.loads(path.read_text(encoding="utf-8"))),
        )
        for path in args.backtest_receipt
    ]
    if len(receipts) not in {1, 2}:
        raise RuntimeError("historical catalog requires one legacy or two split receipts")
    entries: list[dict[str, object]] = []
    for path, receipt in receipts:
        entry: dict[str, object] = {
            "id": receipt["id"],
            "state": "passed",
            "track_kind": receipt["track_kind"],
            "model_cell_id": receipt["model_cell_id"],
            "selection_eligible": receipt["selection_eligible"],
            "primary_signal": PRIMARY_SIGNAL,
            "receipt_sha256": sha256_file(path),
            "receipt_path": path.resolve().relative_to(root).as_posix(),
            "summary": receipt["metrics"][PRIMARY_SIGNAL],
        }
        if receipt["id"] == FINAL_TEST_STRATEGY_ID:
            entry.update(
                {
                    "evaluation_split": "test_viewed_2026",
                    "result_role": "CORRECTED_OPENED_OOS_DIAGNOSTIC",
                    "used_for_selection": False,
                    "test_data_access": "VIEWED",
                }
            )
        else:
            entry.update(
                {
                    "selection_split": "validation_2025",
                    "test_viewed_consumed": False,
                }
            )
        entries.append(entry)
    payload: dict[str, object] = {
        "schema_version": CATALOG_SCHEMA_V2 if len(receipts) == 2 else CATALOG_SCHEMA,
        "status": "PASS",
        "generated_at": datetime.now(UTC).isoformat(),
        "entries": entries,
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
    print(json.dumps({"status": "PASS", "entries": len(entries), "out": str(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
