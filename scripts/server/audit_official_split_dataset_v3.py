#!/usr/bin/env python3
"""Independently audit causal global-session windows and seal admission."""

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
    LOOKBACK,
    PREDICT,
    RAW_RANGES,
    TEST_ELIGIBILITY_FILE,
    TRAINING_INDEX_FILES,
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


def load_pickle(path: Path) -> Any:
    with path.open("rb") as handle:
        return pickle.load(handle)


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
    manifest = validate_dataset_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
    if manifest["raw_manifest_sha256"] != sha256(raw / "manifest.json"):
        raise RuntimeError("dataset does not bind the raw manifest")
    for identity, entry in manifest["files"].items():
        path = dataset / identity
        if (
            not path.is_file()
            or path.stat().st_size != entry["bytes"]
            or sha256(path) != entry["sha256"]
        ):
            raise RuntimeError(f"dataset artifact changed: {identity}")

    calendar_frame = pd.read_csv(raw / "trade_cal.csv", dtype={"cal_date": str})
    sessions = pd.DatetimeIndex(
        pd.to_datetime(
            calendar_frame.loc[calendar_frame["is_open"].astype(int) == 1, "cal_date"],
            format="%Y%m%d",
        )
    ).sort_values()
    frozen = pd.Timestamp(manifest["frozen_latest_session"])
    sessions = sessions[sessions <= frozen]
    weights = pd.concat(
        [pd.read_csv(path, dtype=str) for path in sorted((raw / "index_weight").glob("*.csv"))],
        ignore_index=True,
    )
    weights["trade_date"] = pd.to_datetime(weights["trade_date"], format="%Y%m%d")
    counts = weights.groupby("trade_date")["con_code"].nunique().sort_index()
    excluded = {
        str(pd.Timestamp(day).date()): int(count)
        for day, count in counts.items()
        if int(count) != 300
    }
    complete = weights[weights["trade_date"].isin(set(counts[counts == 300].index))].copy()
    member_map, availability = availability_lagged_memberships(sessions, complete)
    member_dates = sorted(member_map)
    if (
        canonical_hash(availability) != manifest["membership_availability_sha256"]
        or excluded != manifest["excluded_membership_snapshots"]
        or any(len(value) != 300 for value in member_map.values())
    ):
        raise RuntimeError("membership reconstruction differs")

    data = {
        split: load_pickle(dataset / identity)
        for split, identity in DATASET_FILES.items()
    }
    if any(not isinstance(value, dict) or not value for value in data.values()):
        raise RuntimeError("dataset payload is invalid")
    index_payload = {
        split: load_pickle(dataset / identity)
        for split, identity in TRAINING_INDEX_FILES.items()
    }
    eligibility = json.loads((dataset / TEST_ELIGIBILITY_FILE).read_text(encoding="utf-8"))
    if not isinstance(eligibility, dict) or not eligibility:
        raise RuntimeError("test eligibility is invalid")
    index_identity = {
        name: canonical_hash([[str(code), int(start)] for code, start in rows])
        for name, rows in index_payload.items()
    }
    if (
        canonical_hash(index_identity) != manifest["training_index_sha256"]
        or canonical_hash(eligibility) != manifest["test_eligibility_sha256"]
    ):
        raise RuntimeError("eligible index identity mismatch")

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
    for split_name in ("train", "validation"):
        frames = data[split_name]
        raw_start, raw_end = ranges[split_name]
        split_calendar = sessions[(sessions >= raw_start) & (sessions <= raw_end)]
        per_symbol: dict[str, dict[str, Any]] = {}
        inputs: list[pd.Timestamp] = []
        anchors: list[pd.Timestamp] = []
        targets: list[pd.Timestamp] = []
        consumed: list[pd.Timestamp] = []
        reconstructed: list[tuple[str, int]] = []
        for code, frame in sorted(frames.items()):
            source = load_symbol(raw, code).loc[raw_start:raw_end, FEATURES]
            pd.testing.assert_frame_equal(frame, source, check_exact=True)
            positions = {pd.Timestamp(day): pos for pos, day in enumerate(frame.index)}
            symbol_windows = 0
            for offset in range(0, len(split_calendar) - TRAINING_ROWS + 1):
                window = split_calendar[offset : offset + TRAINING_ROWS]
                anchor = pd.Timestamp(window[LOOKBACK - 1])
                start = positions.get(pd.Timestamp(window[0]))
                if start is None or code not in latest_snapshot(member_dates, member_map, anchor):
                    continue
                observed = tuple(
                    pd.Timestamp(day)
                    for day in frame.index[start : start + TRAINING_ROWS]
                )
                if observed != tuple(pd.Timestamp(day) for day in window):
                    continue
                reconstructed.append((code, start))
                symbol_windows += 1
                inputs.append(pd.Timestamp(window[0]))
                anchors.append(anchor)
                targets.append(pd.Timestamp(window[LOOKBACK + PREDICT - 1]))
                consumed.append(pd.Timestamp(window[-1]))
            if symbol_windows:
                per_symbol[code] = {"rows": len(frame), "windows": symbol_windows}
        if reconstructed != index_payload[split_name]:
            raise RuntimeError(f"eligible training indices differ: {split_name}")
        coverage[split_name] = {
            "window_rows": TRAINING_ROWS,
            "symbols": len(per_symbol),
            "windows": len(reconstructed),
            "minimum_symbol_rows": min(row["rows"] for row in per_symbol.values()),
            "maximum_symbol_rows": max(row["rows"] for row in per_symbol.values()),
            "symbol_coverage_sha256": canonical_hash(per_symbol),
            "symbol_coverage": per_symbol,
        }
        actual[split_name] = {
            "first_input": str(min(inputs).date()),
            "first_anchor": str(min(anchors).date()),
            "last_anchor": str(max(anchors).date()),
            "last_target": str(max(targets).date()),
            "last_consumed": str(max(consumed).date()),
        }

    test_start, test_end = ranges["test_viewed"]
    test_calendar = sessions[(sessions >= test_start) & (sessions <= test_end)]
    test_rows: dict[str, dict[str, Any]] = {}
    anchors: list[pd.Timestamp] = []
    for code, frame in sorted(data["test_viewed"].items()):
        source = load_symbol(raw, code).loc[test_start:test_end, FEATURES]
        pd.testing.assert_frame_equal(frame, source, check_exact=True)
        available = {pd.Timestamp(day) for day in frame.index}
        observed: list[str] = []
        for position in range(LOOKBACK - 1, len(test_calendar)):
            anchor = pd.Timestamp(test_calendar[position])
            context = test_calendar[position - LOOKBACK + 1 : position + 1]
            if (
                code in latest_snapshot(member_dates, member_map, anchor)
                and all(pd.Timestamp(day) in available for day in context)
            ):
                observed.append(str(anchor.date()))
                anchors.append(anchor)
        if observed != eligibility.get(code):
            raise RuntimeError(f"test anchor eligibility differs: {code}")
        test_rows[code] = {"rows": len(frame), "windows": len(observed)}
    backtest = [day for day in anchors if day >= pd.Timestamp("2024-07-01")]
    coverage["test_viewed"] = {
        "window_rows": 100,
        "symbols": len(test_rows),
        "windows": len(anchors),
        "minimum_symbol_rows": min(row["rows"] for row in test_rows.values()),
        "maximum_symbol_rows": max(row["rows"] for row in test_rows.values()),
        "symbol_coverage_sha256": canonical_hash(test_rows),
        "symbol_coverage": test_rows,
    }
    actual["test_viewed"] = {
        "first_input": str(test_start.date()),
        "first_anchor": str(min(anchors).date()),
        "last_anchor": str(max(anchors).date()),
        "last_target": str(frozen.date()),
        "last_consumed": None,
        "actual_first_backtest_signal": str(min(backtest).date()),
    }
    if not actual["train"]["last_consumed"] < actual["validation"]["first_anchor"]:
        raise RuntimeError("train/validation effective ranges overlap")
    if not actual["validation"]["last_consumed"] < actual["test_viewed"]["first_anchor"]:
        raise RuntimeError("validation/test effective ranges overlap")
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
        "excluded_membership_snapshots": excluded,
        "excluded_membership_snapshots_sha256": canonical_hash(excluded),
        "every_consumed_membership_snapshot_exactly_300": True,
        "pickle_content_recomputed": True,
        "training_indices_recomputed": True,
        "test_eligibility_recomputed": True,
        "future_symbol_row_conditioning": False,
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
