#!/usr/bin/env python3
"""Recompute actual per-symbol official-split windows and seal admission."""

from __future__ import annotations

import argparse
import json
import os
import pickle
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.research.official_split_v3 import (
    ADMISSION_SCHEMA,
    DATASET_FILES,
    INFERENCE_ROWS,
    LOOKBACK,
    PREDICT,
    RAW_RANGES,
    TRAINING_ROWS,
    canonical_hash,
    validate_dataset_admission,
    validate_dataset_manifest,
)
from scripts.server.build_extended_dataset import (
    availability_lagged_memberships,
    latest_snapshot,
    load_symbol,
    sha256,
    verify_raw_manifest,
)

FEATURES = ["open", "high", "low", "close", "vol", "amt"]


def load_pickle(path: Path) -> dict[str, pd.DataFrame]:
    with path.open("rb") as handle:
        value: Any = pickle.load(handle)
    if not isinstance(value, dict) or not value:
        raise RuntimeError(f"dataset pickle is empty or invalid: {path}")
    if any(not isinstance(frame, pd.DataFrame) for frame in value.values()):
        raise RuntimeError(f"dataset pickle contains non-frame values: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    raw, dataset = args.raw_root.resolve(), args.dataset_root.resolve()
    if args.out.exists():
        raise RuntimeError("immutable dataset admission already exists")
    raw_manifest = json.loads((raw / "manifest.json").read_text(encoding="utf-8"))
    verify_raw_manifest(raw, raw_manifest)
    manifest_path = dataset / "manifest.json"
    manifest = validate_dataset_manifest(
        json.loads(manifest_path.read_text(encoding="utf-8"))
    )
    if manifest["raw_manifest_sha256"] != sha256(raw / "manifest.json"):
        raise RuntimeError("dataset does not bind the admitted raw manifest")
    for identity, entry in manifest["files"].items():
        path = dataset / identity
        if (
            not path.is_file()
            or path.stat().st_size != entry["bytes"]
            or sha256(path) != entry["sha256"]
        ):
            raise RuntimeError(f"dataset pickle hash/bytes mismatch: {identity}")

    calendar = pd.read_csv(raw / "trade_cal.csv", dtype={"cal_date": str})
    sessions = pd.DatetimeIndex(
        pd.to_datetime(
            calendar.loc[calendar["is_open"].astype(int) == 1, "cal_date"],
            format="%Y%m%d",
        )
    ).sort_values()
    frozen = pd.Timestamp(manifest["frozen_latest_session"])
    sessions = sessions[sessions <= frozen]
    weights = pd.concat(
        [
            pd.read_csv(path, dtype=str)
            for path in sorted((raw / "index_weight").glob("*.csv"))
        ],
        ignore_index=True,
    )
    weights["trade_date"] = pd.to_datetime(weights["trade_date"], format="%Y%m%d")
    snapshot_counts = weights.groupby("trade_date")["con_code"].nunique().sort_index()
    excluded_snapshots = {
        str(pd.Timestamp(source_date).date()): int(count)
        for source_date, count in snapshot_counts.items()
        if int(count) != 300
    }
    if (
        raw_manifest.get("excluded_membership_snapshots") != excluded_snapshots
        or raw_manifest.get("excluded_membership_snapshots_sha256")
        != canonical_hash(excluded_snapshots)
        or raw_manifest.get("partial_membership_forward_filled") is not False
        or raw_manifest.get("excluded_snapshot_effect")
        != "ignored; prior complete snapshot remains active"
    ):
        raise RuntimeError("raw membership exclusion receipt is incorrect")
    if (
        manifest["excluded_membership_snapshots"] != excluded_snapshots
        or manifest["excluded_membership_snapshots_sha256"]
        != canonical_hash(excluded_snapshots)
    ):
        raise RuntimeError("dataset membership exclusions differ from raw evidence")
    complete_dates = set(snapshot_counts[snapshot_counts == 300].index)
    complete_weights = weights[weights["trade_date"].isin(complete_dates)].copy()
    member_map, availability = availability_lagged_memberships(sessions, complete_weights)
    if (
        not member_map
        or any(len(members) != 300 for members in member_map.values())
        or canonical_hash(availability) != manifest["membership_availability_sha256"]
    ):
        raise RuntimeError("consumed membership snapshots are not independently exact")
    member_dates = sorted(member_map)
    ranges = {
        "train": (pd.Timestamp(RAW_RANGES["train"][0]), pd.Timestamp(RAW_RANGES["train"][1])),
        "validation": (
            pd.Timestamp(RAW_RANGES["validation"][0]),
            pd.Timestamp(RAW_RANGES["validation"][1]),
        ),
        "test_viewed": (pd.Timestamp(RAW_RANGES["test_viewed"][0]), frozen),
    }
    coverage: dict[str, Any] = {}
    actual: dict[str, Any] = {}
    for split_name, identity in DATASET_FILES.items():
        payload = load_pickle(dataset / identity)
        required = INFERENCE_ROWS if split_name == "test_viewed" else TRAINING_ROWS
        rows: dict[str, Any] = {}
        inputs: list[pd.Timestamp] = []
        anchors: list[pd.Timestamp] = []
        target_ends: list[pd.Timestamp] = []
        consumed: list[pd.Timestamp] = []
        raw_start, raw_end = ranges[split_name]
        for code, frame in sorted(payload.items()):
            if list(frame.columns) != FEATURES:
                raise RuntimeError(f"feature columns differ: {split_name}/{code}")
            if not frame.index.is_unique or not frame.index.is_monotonic_increasing:
                raise RuntimeError(f"dates are not unique/increasing: {split_name}/{code}")
            outside_range = frame.index.min() < raw_start or frame.index.max() > raw_end
            if len(frame) < required or outside_range:
                raise RuntimeError(f"raw slice/window containment failed: {split_name}/{code}")
            source = load_symbol(raw, code)
            expected_dates = [
                stamp
                for stamp in source.loc[raw_start:raw_end].index
                if code in latest_snapshot(member_dates, member_map, stamp)
            ]
            expected = source.loc[expected_dates, FEATURES]
            pd.testing.assert_frame_equal(frame, expected, check_exact=True)
            window_count = len(frame) - required + 1
            inputs.append(pd.Timestamp(frame.index[0]))
            first_anchor = pd.Timestamp(frame.index[LOOKBACK - 1])
            last_start = len(frame) - required
            last_anchor = pd.Timestamp(frame.index[last_start + LOOKBACK - 1])
            last_target = pd.Timestamp(frame.index[last_start + LOOKBACK + PREDICT - 1])
            symbol_anchors = pd.DatetimeIndex(
                frame.index[LOOKBACK - 1 : last_start + LOOKBACK]
            )
            if len(symbol_anchors) != window_count:
                raise RuntimeError(f"window enumeration mismatch: {split_name}/{code}")
            anchors.extend(pd.Timestamp(stamp) for stamp in symbol_anchors)
            target_ends.append(last_target)
            if split_name != "test_viewed":
                consumed.append(pd.Timestamp(frame.index[-1]))
            rows[code] = {
                "rows": len(frame),
                "windows": window_count,
                "first_input": str(pd.Timestamp(frame.index[0]).date()),
                "first_anchor": str(first_anchor.date()),
                "last_anchor": str(last_anchor.date()),
                "last_target": str(last_target.date()),
                "last_consumed": (
                    str(pd.Timestamp(frame.index[-1]).date())
                    if split_name != "test_viewed"
                    else None
                ),
            }
        backtest_anchors = [stamp for stamp in anchors if stamp >= pd.Timestamp("2024-07-01")]
        coverage[split_name] = {
            "window_rows": required,
            "symbols": len(rows),
            "windows": sum(int(row["windows"]) for row in rows.values()),
            "minimum_symbol_rows": min(int(row["rows"]) for row in rows.values()),
            "maximum_symbol_rows": max(int(row["rows"]) for row in rows.values()),
            "symbol_coverage_sha256": canonical_hash(rows),
            "symbol_coverage": rows,
        }
        actual[split_name] = {
            "first_input": str(min(inputs).date()),
            "first_anchor": str(min(anchors).date()),
            "last_anchor": str(max(anchors).date()),
            "last_target": str(max(target_ends).date()),
            "last_consumed": str(max(consumed).date()) if consumed else None,
        }
        if split_name == "test_viewed":
            if not backtest_anchors:
                raise RuntimeError("test payload has no requested-range backtest signal")
            actual[split_name]["actual_first_backtest_signal"] = str(
                min(backtest_anchors).date()
            )
    payload: dict[str, Any] = {
        "schema_version": ADMISSION_SCHEMA,
        "status": "PASS",
        "dataset_manifest_sha256": sha256(manifest_path),
        "dataset_manifest_receipt_hash": manifest["receipt_hash"],
        "raw_manifest_sha256": sha256(raw / "manifest.json"),
        "auditor_code_sha256": sha256(Path(__file__).resolve()),
        "coverage": coverage,
        "actual_effective_ranges": actual,
        "membership_rows_reverified": True,
        "excluded_membership_snapshots": excluded_snapshots,
        "excluded_membership_snapshots_sha256": canonical_hash(excluded_snapshots),
        "every_consumed_membership_snapshot_exactly_300": True,
        "pickle_content_recomputed": True,
    }
    payload["receipt_hash"] = canonical_hash(payload)
    validate_dataset_admission(payload)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.out.with_suffix(args.out.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, args.out)
    print(json.dumps({"status": "PASS", "coverage": coverage}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
