#!/usr/bin/env python3
"""Build official-style and strict-PIT Kronos datasets from immutable raw evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
from bisect import bisect_right
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

LOOKBACK = 90
PREDICT = 10
WINDOW = LOOKBACK + PREDICT + 1


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_pickle(value: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    with temp.open("wb") as handle:
        pickle.dump(value, handle, protocol=pickle.HIGHEST_PROTOCOL)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def atomic_json(value: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with temp.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temp, path)


def latest_snapshot(
    dates: list[pd.Timestamp], members: dict[pd.Timestamp, frozenset[str]], day: pd.Timestamp
) -> frozenset[str]:
    index = bisect_right(dates, day) - 1
    return members[dates[index]] if index >= 0 else frozenset()


def verify_raw_manifest(raw: Path, manifest: dict[str, Any]) -> None:
    root = raw.resolve()
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise RuntimeError("raw manifest has no file inventory")
    requested_end = str(manifest.get("requested_end", ""))
    expected_paths: set[Path] = set()
    for identity, entry in files.items():
        if not isinstance(entry, dict):
            raise RuntimeError(f"invalid raw manifest entry: {identity}")
        path = Path(str(entry.get("path", ""))).resolve()
        if path != root and root not in path.parents:
            raise RuntimeError(f"raw manifest path escapes raw root: {identity}")
        relative = path.relative_to(root)
        if str(identity) != relative.with_suffix("").as_posix():
            raise RuntimeError(f"raw manifest identity/path mismatch: {identity}")
        expected_paths.add(relative)
        if not path.is_file() or sha256(path) != entry.get("sha256"):
            raise RuntimeError(f"raw manifest hash mismatch: {identity}")
        params = entry.get("params", {})
        expected_endpoint = "trade_cal" if relative == Path("trade_cal.csv") else relative.parts[0]
        if entry.get("endpoint") != expected_endpoint:
            raise RuntimeError(f"raw manifest endpoint/path mismatch: {identity}")
        if not isinstance(params, dict):
            raise RuntimeError(f"raw manifest params are invalid: {identity}")
        expected_code = relative.stem if expected_endpoint in {
            "daily", "adj_factor", "stk_limit", "namechange"
        } else None
        if expected_code is not None and str(params.get("ts_code", "")) != expected_code:
            raise RuntimeError(f"raw manifest symbol/path mismatch: {identity}")
        frame = pd.read_csv(path, dtype=str)
        if len(frame) != int(entry.get("rows", -1)):
            raise RuntimeError(f"raw manifest row count mismatch: {identity}")
        if (
            expected_code is not None
            and "ts_code" in frame
            and not frame.empty
            and set(frame["ts_code"].dropna().astype(str)) != {expected_code}
        ):
            raise RuntimeError(f"raw CSV symbol identity mismatch: {identity}")
        date_column = "cal_date" if expected_endpoint == "trade_cal" else "trade_date"
        if date_column in frame and not frame.empty:
            dates = frame[date_column].dropna().astype(str)
            start_date = str(params.get("start_date", ""))
            end_date = str(params.get("end_date", ""))
            if (
                not dates.str.fullmatch(r"\d{8}").all()
                or (start_date and dates.min() < start_date)
                or (end_date and dates.max() > end_date)
            ):
                raise RuntimeError(f"raw CSV date range mismatch: {identity}")
        if (
            requested_end
            and params.get("end_date")
            and str(params["end_date"]) > requested_end
        ):
            raise RuntimeError(f"raw file exceeds requested as-of: {identity}")
    actual_paths = {
        path.relative_to(root)
        for path in root.rglob("*.csv")
        if path.is_file()
    }
    if actual_paths != expected_paths:
        extra = sorted(str(path) for path in actual_paths - expected_paths)[:5]
        missing = sorted(str(path) for path in expected_paths - actual_paths)[:5]
        raise RuntimeError(f"raw manifest is not closed-world: extra={extra}, missing={missing}")


def load_symbol(raw: Path, code: str) -> pd.DataFrame:
    daily = pd.read_csv(raw / "daily" / f"{code}.csv", dtype={"trade_date": str})
    adj = pd.read_csv(raw / "adj_factor" / f"{code}.csv", dtype={"trade_date": str})
    if daily.empty or adj.empty:
        return pd.DataFrame()
    daily["datetime"] = pd.to_datetime(daily["trade_date"], format="%Y%m%d")
    adj["datetime"] = pd.to_datetime(adj["trade_date"], format="%Y%m%d")
    frame = daily.merge(adj[["datetime", "adj_factor"]], on="datetime", how="inner")
    frame = frame.sort_values("datetime").drop_duplicates("datetime", keep=False)
    numeric = ["open", "high", "low", "close", "vol", "amount", "adj_factor"]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="coerce")
    frame = frame.dropna(subset=numeric)
    frame = frame[(frame[["open", "high", "low", "close", "adj_factor"]] > 0).all(axis=1)]
    frame["vol"] *= 100.0
    frame["amount"] *= 1000.0
    frame = frame.rename(columns={"amount": "amt"})
    return frame.set_index("datetime")[["open", "high", "low", "close", "vol", "amt", "adj_factor"]]


def strict_session_frame(frame: pd.DataFrame, sessions: pd.DatetimeIndex) -> pd.DataFrame:
    """Represent missing exchange sessions without looking beyond the anchor.

    Once a symbol has its first observation, a missing row is represented as an
    unchanged-price, zero-liquidity session.  This is the conservative suspension
    convention used by the training tokens and prevents future missingness from
    deciding whether an earlier anchor exists.
    """

    if frame.empty:
        return frame
    expanded = frame.reindex(sessions).copy()
    observed = expanded["close"].notna()
    price_columns = ["open", "high", "low", "close", "adj_factor"]
    expanded[price_columns] = expanded[price_columns].ffill()
    expanded[["vol", "amt"]] = expanded[["vol", "amt"]].fillna(0.0)
    expanded["observed"] = observed
    first = frame.index.min()
    return expanded.loc[first:]


def availability_lagged_memberships(
    sessions: pd.DatetimeIndex, weights: pd.DataFrame
) -> tuple[dict[pd.Timestamp, frozenset[str]], list[dict[str, str]]]:
    """Apply a one-complete-session availability lag to provider snapshots.

    The provider does not expose historical first-seen timestamps.  We therefore
    never use a weight snapshot on its own ``trade_date`` and record the residual
    historical-revision limitation in the dataset manifest.
    """

    member_map: dict[pd.Timestamp, frozenset[str]] = {}
    receipts: list[dict[str, str]] = []
    for source_day, group in weights.groupby("trade_date", sort=True):
        position = int(sessions.searchsorted(source_day, side="right"))
        if position >= len(sessions):
            continue
        available = sessions[position]
        member_map[available] = frozenset(group["con_code"].astype(str))
        receipts.append(
            {
                "source_trade_date": source_day.strftime("%Y-%m-%d"),
                "available_session": available.strftime("%Y-%m-%d"),
            }
        )
    return member_map, receipts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    args = parser.parse_args()
    raw = args.raw_root.resolve()
    out = args.out_root.resolve()
    source_manifest = json.loads((raw / "manifest.json").read_text(encoding="utf-8"))
    if source_manifest.get("status") != "PASS":
        raise RuntimeError("raw manifest is not terminal PASS")
    verify_raw_manifest(raw, source_manifest)

    calendar = pd.read_csv(raw / "trade_cal.csv", dtype={"cal_date": str})
    sessions = pd.DatetimeIndex(
        pd.to_datetime(
            calendar.loc[calendar["is_open"].astype(int) == 1, "cal_date"], format="%Y%m%d"
        )
    ).sort_values()
    sessions = sessions[sessions <= pd.Timestamp(source_manifest["latest_closed_session"])]
    session_position = {day: index for index, day in enumerate(sessions)}
    if len(sessions) < WINDOW:
        raise RuntimeError("calendar is too short")

    weight_parts = [
        pd.read_csv(path, dtype=str) for path in sorted((raw / "index_weight").glob("*.csv"))
    ]
    weights = pd.concat(weight_parts, ignore_index=True)
    weights["trade_date"] = pd.to_datetime(weights["trade_date"], format="%Y%m%d")
    source_member_counts = weights.groupby("trade_date")["con_code"].nunique()
    if (source_member_counts != 300).any():
        raise RuntimeError("membership source snapshot is not exactly 300")
    member_map, membership_receipts = availability_lagged_memberships(sessions, weights)
    snapshot_dates = sorted(member_map)
    if any(len(value) != 300 for value in member_map.values()):
        raise RuntimeError("membership snapshot is not exactly 300")
    codes = sorted(set(weights["con_code"].astype(str)))

    raw_symbols: dict[str, pd.DataFrame] = {}
    symbols: dict[str, pd.DataFrame] = {}
    for code in codes:
        frame = load_symbol(raw, code)
        if not frame.empty:
            raw_symbols[code] = frame
            symbols[code] = strict_session_frame(frame, sessions)
    if len(symbols) < 300:
        raise RuntimeError("fewer than 300 symbols have usable OHLCVA")

    final_2024 = sessions[sessions.year == 2024][-1]
    first_2025, final_2025 = sessions[sessions.year == 2025][[0, -1]]
    first_2026 = sessions[sessions.year == 2026][0]
    split_anchors: dict[str, list[tuple[str, int]]] = {"train": [], "val": [], "test": []}
    exclusion_counts: dict[str, int] = {}

    for code, frame in symbols.items():
        dates = frame.index
        positions = {day: idx for idx, day in enumerate(dates)}
        # The pinned author dataset materializes lookback + predict + 1 rows
        # (101 for 90/10) for its shifted next-token loss.  The research signal
        # remains ten sessions, but the extra consumed row must stay inside the
        # same split to avoid a boundary leak.
        for signal_position in range(LOOKBACK - 1, len(sessions) - PREDICT - 1):
            signal = sessions[signal_position]
            if code not in latest_snapshot(snapshot_dates, member_map, signal):
                continue
            window_dates = sessions[signal_position - LOOKBACK + 1 : signal_position + PREDICT + 2]
            historical_dates = window_dates[:LOOKBACK]
            if any(day not in positions for day in historical_dates):
                exclusion_counts["non_contiguous_or_missing"] = (
                    exclusion_counts.get("non_contiguous_or_missing", 0) + 1
                )
                continue
            consumed_end = sessions[signal_position + PREDICT + 1]
            if consumed_end <= final_2024:
                split = "train"
            elif signal >= first_2025 and consumed_end <= final_2025:
                split = "val"
            elif signal >= first_2026:
                split = "test"
            else:
                exclusion_counts["target_crosses_split"] = (
                    exclusion_counts.get("target_crosses_split", 0) + 1
                )
                continue
            start = positions[window_dates[0]]
            if list(dates[start : start + WINDOW]) != list(window_dates):
                raise RuntimeError("symbol window does not match global sessions")
            split_anchors[split].append((code, start))

    strict_root = out / "strict"
    atomic_pickle(symbols, strict_root / "full_data.pkl")
    for split, anchors in split_anchors.items():
        if not anchors:
            raise RuntimeError(f"strict {split} has no anchors")
        atomic_pickle(tuple(anchors), strict_root / f"{split}_anchors.pkl")

    # Official-style slices deliberately retain the author's per-symbol/gappy
    # behavior but use the extended split boundaries agreed for this project.
    official_ranges = {
        "train": (sessions[0], final_2024),
        "val": (sessions[session_position[first_2025] - LOOKBACK], final_2025),
        "test": (sessions[session_position[first_2026] - LOOKBACK], sessions[-1]),
    }
    official_root = out / "official"
    for split, (start, end) in official_ranges.items():
        payload: dict[str, pd.DataFrame] = {}
        for code, frame in raw_symbols.items():
            selected_dates = [
                day
                for day in frame.loc[start:end].index
                if code in latest_snapshot(snapshot_dates, member_map, day)
            ]
            sliced = frame.loc[selected_dates, ["open", "high", "low", "close", "vol", "amt"]]
            if len(sliced) >= WINDOW:
                sliced.index.name = "datetime"
                payload[code] = sliced
        atomic_pickle(payload, official_root / f"{split}_data.pkl")

    online_count = 0
    latest = sessions[-1]
    for code, frame in symbols.items():
        if code not in latest_snapshot(snapshot_dates, member_map, latest):
            continue
        required = sessions[-LOOKBACK:]
        if all(day in frame.index for day in required):
            online_count += 1

    files = {}
    for path in sorted(out.rglob("*.pkl")):
        files[path.relative_to(out).as_posix()] = {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    manifest = {
        "schema_version": "elanquant_extended_dataset_v1",
        "status": "PASS",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "raw_manifest_sha256": sha256(raw / "manifest.json"),
        "raw_start": source_manifest["start"],
        "latest_closed_session": latest.strftime("%Y-%m-%d"),
        "lookback": LOOKBACK,
        "predict": PREDICT,
        "author_training_window_rows": WINDOW,
        "author_extra_shift_row_purged_with_split": True,
        "split_contract": {
            "train_target_end": final_2024.strftime("%Y-%m-%d"),
            "validation_anchor_start": first_2025.strftime("%Y-%m-%d"),
            "validation_target_end": final_2025.strftime("%Y-%m-%d"),
            "test_viewed_anchor_start": first_2026.strftime("%Y-%m-%d"),
            "test_target_end": latest.strftime("%Y-%m-%d"),
        },
        "strict_anchor_counts": {key: len(value) for key, value in split_anchors.items()},
        "online_latest_eligible_symbols": online_count,
        "membership_snapshot_count": len(snapshot_dates),
        "membership_availability_contract": {
            "policy": "provider_trade_date_plus_one_complete_exchange_session",
            "receipts": membership_receipts,
            "historical_revision_receipts_available": False,
            "limitation": (
                "The provider exposes no historical first-seen timestamp; a one-session lag "
                "prevents same-day use but cannot prove freedom from later vendor revisions."
            ),
        },
        "missing_session_contract": (
            "After first observation, missing exchange rows are unchanged-price, zero-volume "
            "and zero-amount sessions; future missingness never removes an earlier anchor."
        ),
        "symbol_count": len(symbols),
        "exclusion_counts": exclusion_counts,
        "price_contract": (
            "Raw OHLC plus per-date adjustment factor; strict loader adjusts "
            "each window to its signal-date scale."
        ),
        "volume_amount_contract": "vol converted lots->shares; amount converted thousand RMB->RMB",
        "test_status": "TEST_VIEWED",
        "files": files,
    }
    atomic_json(manifest, out / "manifest.json")
    print(json.dumps({key: value for key, value in manifest.items() if key != "files"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
