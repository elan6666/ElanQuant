#!/usr/bin/env python3
"""Materialize immutable official-style raw slices for Plan011 on the server."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.research.official_split_v3 import (
    DATASET_SCHEMA,
    INFERENCE_ROWS,
    RAW_RANGES,
    TRAINING_ROWS,
    build_split_receipt,
    canonical_hash,
)
from scripts.server.build_extended_dataset import (
    atomic_json,
    atomic_pickle,
    availability_lagged_memberships,
    latest_snapshot,
    load_symbol,
    sha256,
    verify_raw_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    args = parser.parse_args()
    raw, output = args.raw_root.resolve(), args.out_root.resolve()
    if output.exists():
        raise RuntimeError("immutable official-split-v3 output already exists")
    source: dict[str, Any] = json.loads((raw / "manifest.json").read_text(encoding="utf-8"))
    if source.get("status") != "PASS":
        raise RuntimeError("raw manifest is not terminal PASS")
    verify_raw_manifest(raw, source)
    frozen_latest = pd.Timestamp(str(source["latest_closed_session"]))
    calendar = pd.read_csv(raw / "trade_cal.csv", dtype={"cal_date": str})
    sessions = pd.DatetimeIndex(
        pd.to_datetime(
            calendar.loc[calendar["is_open"].astype(int) == 1, "cal_date"],
            format="%Y%m%d",
        )
    ).sort_values()
    sessions = sessions[sessions <= frozen_latest]
    if sessions.empty or sessions[-1] != frozen_latest:
        raise RuntimeError("raw manifest latest session is absent from trade calendar")
    split = build_split_receipt(
        [stamp.date() for stamp in sessions], frozen_latest=frozen_latest.date()
    )

    weight_parts = [
        pd.read_csv(path, dtype=str) for path in sorted((raw / "index_weight").glob("*.csv"))
    ]
    if not weight_parts:
        raise RuntimeError("CSI300 membership evidence is missing")
    weights = pd.concat(weight_parts, ignore_index=True)
    weights["trade_date"] = pd.to_datetime(weights["trade_date"], format="%Y%m%d")
    snapshot_counts = weights.groupby("trade_date")["con_code"].nunique().sort_index()
    excluded_snapshots = {
        str(pd.Timestamp(source_date).date()): int(count)
        for source_date, count in snapshot_counts.items()
        if int(count) != 300
    }
    if (
        source.get("excluded_membership_snapshots") != excluded_snapshots
        or source.get("excluded_membership_snapshots_sha256")
        != canonical_hash(excluded_snapshots)
        or source.get("partial_membership_forward_filled") is not False
        or source.get("excluded_snapshot_effect")
        != "ignored; prior complete snapshot remains active"
    ):
        raise RuntimeError("raw manifest membership exclusions are absent or incorrect")
    complete_dates = set(snapshot_counts[snapshot_counts == 300].index)
    complete_weights = weights[weights["trade_date"].isin(complete_dates)].copy()
    if complete_weights.empty:
        raise RuntimeError("no complete 300-member membership snapshots")
    member_map, availability = availability_lagged_memberships(sessions, complete_weights)
    member_dates = sorted(member_map)
    if not member_dates or any(len(members) != 300 for members in member_map.values()):
        raise RuntimeError("membership evidence is not a complete CSI300 history")
    codes = sorted(set(complete_weights["con_code"].astype(str)))
    ranges = {
        "train": (pd.Timestamp(RAW_RANGES["train"][0]), pd.Timestamp(RAW_RANGES["train"][1])),
        "val": (
            pd.Timestamp(RAW_RANGES["validation"][0]),
            pd.Timestamp(RAW_RANGES["validation"][1]),
        ),
        "test": (pd.Timestamp(RAW_RANGES["test_viewed"][0]), frozen_latest),
    }
    payloads: dict[str, dict[str, pd.DataFrame]] = {key: {} for key in ranges}
    for code in codes:
        frame = load_symbol(raw, code)
        if frame.empty:
            continue
        for split_name, (start, end) in ranges.items():
            selected = [
                stamp
                for stamp in frame.loc[start:end].index
                if code in latest_snapshot(member_dates, member_map, stamp)
            ]
            columns = ["open", "high", "low", "close", "vol", "amt"]
            sliced = frame.loc[selected, columns].copy()
            minimum = INFERENCE_ROWS if split_name == "test" else TRAINING_ROWS
            if len(sliced) >= minimum:
                sliced.index.name = "datetime"
                payloads[split_name][code] = sliced
    if any(not rows for rows in payloads.values()):
        raise RuntimeError("at least one official raw slice has no eligible symbols")

    official = output / "official"
    for split_name, rows in payloads.items():
        atomic_pickle(rows, official / f"{split_name}_data.pkl")
    files = {
        path.relative_to(output).as_posix(): {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in sorted(output.rglob("*.pkl"))
    }
    manifest: dict[str, Any] = {
        "schema_version": DATASET_SCHEMA,
        "status": "PASS",
        "raw_manifest_sha256": sha256(raw / "manifest.json"),
        "materializer_code_sha256": sha256(Path(__file__).resolve()),
        "frozen_latest_session": frozen_latest.strftime("%Y-%m-%d"),
        "split_contract": split,
        "split_receipt_hash": split["receipt_hash"],
        "symbol_counts": {key: len(rows) for key, rows in payloads.items()},
        "membership_policy": "trade_date_plus_one_complete_exchange_session",
        "membership_availability_sha256": canonical_hash(availability),
        "excluded_membership_snapshots": excluded_snapshots,
        "excluded_membership_snapshots_sha256": canonical_hash(excluded_snapshots),
        "consumed_membership_snapshot_count": len(member_map),
        "every_consumed_membership_snapshot_exactly_300": True,
        "partial_membership_forward_filled": False,
        "excluded_snapshot_effect": "ignored; prior complete snapshot remains active",
        "future_symbol_row_conditioning": False,
        "files": files,
    }
    manifest["receipt_hash"] = canonical_hash(manifest)
    atomic_json(manifest, output / "manifest.json")
    print(json.dumps({"status": "PASS", "symbol_counts": manifest["symbol_counts"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
