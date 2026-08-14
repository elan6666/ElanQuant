#!/usr/bin/env python3
"""Materialize causal official-date slices and explicit eligible indices."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.research.official_split_v3 import (
    DATASET_SCHEMA,
    LOOKBACK,
    RAW_RANGES,
    TEST_ELIGIBILITY_FILE,
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

FEATURES = ["open", "high", "low", "close", "vol", "amt"]


def consecutive_indices(
    frame: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    member_dates: list[pd.Timestamp],
    member_map: dict[pd.Timestamp, set[str]],
    code: str,
) -> list[tuple[str, int]]:
    positions = {pd.Timestamp(stamp): index for index, stamp in enumerate(frame.index)}
    admitted: list[tuple[str, int]] = []
    for offset in range(0, len(calendar) - TRAINING_ROWS + 1):
        window = calendar[offset : offset + TRAINING_ROWS]
        anchor = pd.Timestamp(window[LOOKBACK - 1])
        start = positions.get(pd.Timestamp(window[0]))
        if start is None or code not in latest_snapshot(member_dates, member_map, anchor):
            continue
        observed = tuple(
            pd.Timestamp(stamp)
            for stamp in frame.index[start : start + TRAINING_ROWS]
        )
        if observed == tuple(pd.Timestamp(stamp) for stamp in window):
            admitted.append((code, start))
    return admitted


def test_anchors(
    frame: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    member_dates: list[pd.Timestamp],
    member_map: dict[pd.Timestamp, set[str]],
    code: str,
) -> list[str]:
    available = {pd.Timestamp(stamp) for stamp in frame.index}
    anchors: list[str] = []
    for position in range(LOOKBACK - 1, len(calendar)):
        anchor = pd.Timestamp(calendar[position])
        context = calendar[position - LOOKBACK + 1 : position + 1]
        if (
            code in latest_snapshot(member_dates, member_map, anchor)
            and all(pd.Timestamp(stamp) in available for stamp in context)
        ):
            anchors.append(str(anchor.date()))
    return anchors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    args = parser.parse_args()
    raw, output = args.raw_root.resolve(), args.out_root.resolve()
    if output.exists():
        raise RuntimeError("immutable official split output already exists")
    source: dict[str, Any] = json.loads((raw / "manifest.json").read_text(encoding="utf-8"))
    if source.get("status") != "PASS":
        raise RuntimeError("raw manifest is not terminal PASS")
    verify_raw_manifest(raw, source)
    frozen = pd.Timestamp(str(source["latest_closed_session"]))
    calendar_frame = pd.read_csv(raw / "trade_cal.csv", dtype={"cal_date": str})
    sessions = pd.DatetimeIndex(
        pd.to_datetime(
            calendar_frame.loc[calendar_frame["is_open"].astype(int) == 1, "cal_date"],
            format="%Y%m%d",
        )
    ).sort_values()
    sessions = sessions[sessions <= frozen]
    if sessions.empty or sessions[-1] != frozen:
        raise RuntimeError("frozen session is absent from the global calendar")
    split = build_split_receipt([stamp.date() for stamp in sessions], frozen_latest=frozen.date())

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
    if (
        source.get("excluded_membership_snapshots") != excluded
        or source.get("excluded_membership_snapshots_sha256") != canonical_hash(excluded)
        or source.get("partial_membership_forward_filled") is not False
    ):
        raise RuntimeError("raw membership exclusion evidence mismatch")
    complete = weights[weights["trade_date"].isin(set(counts[counts == 300].index))].copy()
    member_map, availability = availability_lagged_memberships(sessions, complete)
    member_dates = sorted(member_map)
    if not member_dates or any(len(value) != 300 for value in member_map.values()):
        raise RuntimeError("complete CSI300 membership history is unavailable")
    codes = sorted(set(complete["con_code"].astype(str)))
    ranges = {
        "train": (pd.Timestamp(RAW_RANGES["train"][0]), pd.Timestamp(RAW_RANGES["train"][1])),
        "validation": (
            pd.Timestamp(RAW_RANGES["validation"][0]),
            pd.Timestamp(RAW_RANGES["validation"][1]),
        ),
        "test_viewed": (pd.Timestamp(RAW_RANGES["test_viewed"][0]), frozen),
    }
    data: dict[str, dict[str, pd.DataFrame]] = {name: {} for name in ranges}
    indices: dict[str, list[tuple[str, int]]] = {"train": [], "validation": []}
    eligibility: dict[str, list[str]] = {}
    for code in codes:
        source_frame = load_symbol(raw, code)
        if source_frame.empty:
            continue
        for split_name, (start, end) in ranges.items():
            frame = source_frame.loc[start:end, FEATURES].copy()
            frame.index.name = "datetime"
            if split_name in indices:
                split_calendar = sessions[(sessions >= start) & (sessions <= end)]
                eligible = consecutive_indices(
                    frame, split_calendar, member_dates, member_map, code
                )
                if eligible:
                    data[split_name][code] = frame
                    indices[split_name].extend(eligible)
            else:
                split_calendar = sessions[(sessions >= start) & (sessions <= end)]
                anchors = test_anchors(frame, split_calendar, member_dates, member_map, code)
                if anchors:
                    data[split_name][code] = frame
                    eligibility[code] = anchors
    if any(not rows for rows in data.values()) or any(not rows for rows in indices.values()):
        raise RuntimeError("causal dataset has an empty partition")

    official = output / "official"
    atomic_pickle(data["train"], official / "train_data.pkl")
    atomic_pickle(data["validation"], official / "val_data.pkl")
    atomic_pickle(data["test_viewed"], official / "test_data.pkl")
    atomic_pickle(indices["train"], official / "train_indices.pkl")
    atomic_pickle(indices["validation"], official / "val_indices.pkl")
    atomic_json(eligibility, output / TEST_ELIGIBILITY_FILE)
    files = {
        path.relative_to(output).as_posix(): {"bytes": path.stat().st_size, "sha256": sha256(path)}
        for path in sorted(official.iterdir())
        if path.is_file()
    }
    index_identity = {
        name: canonical_hash([[code, start] for code, start in rows])
        for name, rows in indices.items()
    }
    manifest: dict[str, Any] = {
        "schema_version": DATASET_SCHEMA,
        "status": "PASS",
        "raw_manifest_sha256": sha256(raw / "manifest.json"),
        "materializer_code_sha256": sha256(Path(__file__).resolve()),
        "frozen_latest_session": frozen.strftime("%Y-%m-%d"),
        "split_contract": split,
        "split_receipt_hash": split["receipt_hash"],
        "symbol_counts": {name: len(rows) for name, rows in data.items()},
        "eligible_window_counts": {name: len(rows) for name, rows in indices.items()},
        "eligible_test_anchor_count": sum(len(rows) for rows in eligibility.values()),
        "training_index_sha256": canonical_hash(index_identity),
        "test_eligibility_sha256": canonical_hash(eligibility),
        "training_window_policy": "GLOBAL_CONSECUTIVE_SESSIONS_ANCHOR_MEMBERSHIP",
        "test_candidate_policy": "PAST_90_GLOBAL_SESSIONS_AND_T_KNOWN_MEMBERSHIP",
        "membership_policy": "trade_date_plus_one_complete_exchange_session",
        "membership_availability_sha256": canonical_hash(availability),
        "excluded_membership_snapshots": excluded,
        "excluded_membership_snapshots_sha256": canonical_hash(excluded),
        "consumed_membership_snapshot_count": len(member_map),
        "every_consumed_membership_snapshot_exactly_300": True,
        "partial_membership_forward_filled": False,
        "excluded_snapshot_effect": "ignored; prior complete snapshot remains active",
        "future_symbol_row_conditioning": False,
        "files": files,
    }
    manifest["receipt_hash"] = canonical_hash(manifest)
    atomic_json(manifest, output / "manifest.json")
    print(
        json.dumps(
            {
                "status": "PASS",
                "symbol_counts": manifest["symbol_counts"],
                "eligible_window_counts": manifest["eligible_window_counts"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
