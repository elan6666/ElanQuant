#!/usr/bin/env python3
"""Fetch Plan011 raw data while explicitly excluding partial membership snapshots."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import fetch_extended_csi300 as legacy
import pandas as pd

from scripts.research.official_split_v3 import canonical_hash

RAW_SCHEMA = "elanquant_official_split_raw_v3"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proxy-client", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--start", default="20110101")
    parser.add_argument("--end", required=True)
    parser.add_argument("--interval", type=float, default=0.35)
    parser.add_argument(
        "--allow-recorded-incomplete-membership-snapshots",
        action="store_true",
        help="exclude and receipt, never consume or forward-fill, snapshots whose count != 300",
    )
    args = parser.parse_args()
    output = args.out_root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.chmod(output, 0o700)
    manifest_path = output / "manifest.json"
    prior = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    if prior and (
        str(prior.get("start")) != args.start
        or str(prior.get("requested_end")) != args.end
    ):
        raise RuntimeError("raw root belongs to a different requested range")
    files: dict[str, Any] = dict(prior.get("files", {}))
    for identity, entry in files.items():
        candidate = Path(str(entry.get("path", "")))
        if not candidate.is_file() or legacy.sha256(candidate) != entry.get("sha256"):
            raise RuntimeError(f"cannot resume changed raw file: {identity}")
    now_market = datetime.now(legacy.MARKET_TIMEZONE)
    requested_day = datetime.strptime(args.end, "%Y%m%d").date()
    if requested_day > now_market.date():
        raise RuntimeError("requested end cannot be future")
    if requested_day == now_market.date() and now_market.time() < legacy.DAILY_FINALIZATION_TIME:
        raise RuntimeError("requested end is before the 16:15 Asia/Shanghai gate")
    pro = legacy.approved_client(args.proxy_client.resolve())

    calendar_params = {"exchange": "", "start_date": args.start, "end_date": args.end}
    calendar_path = output / "trade_cal.csv"
    if not calendar_path.exists():
        calendar = legacy.request(pro, "trade_cal", **calendar_params).sort_values("cal_date")
        legacy.atomic_csv(calendar, calendar_path)
        time.sleep(args.interval)
    calendar = pd.read_csv(calendar_path, dtype=str)
    open_days = calendar.loc[calendar["is_open"].astype(int) == 1, "cal_date"].astype(str)
    if open_days.empty:
        raise RuntimeError("trade calendar has no open sessions")
    latest_closed = str(open_days.max())
    files["trade_cal"] = legacy.file_entry(
        calendar_path, len(calendar), "trade_cal", calendar_params
    )

    weight_frames: list[pd.DataFrame] = []
    for year in range(int(args.start[:4]), int(args.end[:4]) + 1):
        start, end = max(args.start, f"{year}0101"), min(args.end, f"{year}1231")
        params = {"index_code": "000300.SH", "start_date": start, "end_date": end}
        path = output / "index_weight" / f"{year}.csv"
        if not path.exists():
            frame = legacy.request(pro, "index_weight", **params).sort_values(
                ["trade_date", "con_code"]
            )
            if frame.empty:
                raise RuntimeError(f"index_weight returned no rows: {year}")
            legacy.atomic_csv(frame, path)
            time.sleep(args.interval)
        frame = pd.read_csv(path, dtype=str)
        weight_frames.append(frame)
        files[f"index_weight/{year}"] = legacy.file_entry(
            path, len(frame), "index_weight", params
        )
    weights = pd.concat(weight_frames, ignore_index=True)
    if weights.duplicated(["trade_date", "con_code"]).any():
        raise RuntimeError("duplicate membership rows")
    counts = weights.groupby("trade_date")["con_code"].nunique().sort_index()
    excluded = {
        str(pd.to_datetime(str(source_date), format="%Y%m%d").date()): int(count)
        for source_date, count in counts.items()
        if int(count) != 300
    }
    if excluded and not args.allow_recorded_incomplete_membership_snapshots:
        raise RuntimeError(
            "incomplete membership snapshots require the explicit recorded-exclusion flag"
        )
    complete_dates = set(counts[counts == 300].index.astype(str))
    if not complete_dates:
        raise RuntimeError("provider supplied no complete 300-member snapshot")
    complete_weights = weights[weights["trade_date"].astype(str).isin(complete_dates)]
    if complete_weights.groupby("trade_date")["con_code"].nunique().ne(300).any():
        raise RuntimeError("consumed membership snapshot is not exactly 300")
    codes = sorted(complete_weights["con_code"].astype(str).unique())

    endpoints: dict[str, tuple[str, ...]] = {
        "daily": ("ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"),
        "adj_factor": ("ts_code", "trade_date", "adj_factor"),
        "stk_limit": ("ts_code", "trade_date", "up_limit", "down_limit"),
        "namechange": (
            "ts_code",
            "name",
            "start_date",
            "end_date",
            "ann_date",
            "change_reason",
        ),
    }
    exclusion_hash = canonical_hash(excluded)
    for offset, code in enumerate(codes, start=1):
        for endpoint, expected in endpoints.items():
            params = {"ts_code": code, "start_date": args.start, "end_date": args.end}
            path = output / endpoint / f"{code}.csv"
            if not path.exists():
                frame = legacy.request(pro, endpoint, **params)
                if endpoint == "daily" and frame.empty:
                    raise RuntimeError(f"daily returned no rows: {code}")
                if frame.empty and not len(frame.columns):
                    frame = pd.DataFrame(columns=expected)
                missing = set(expected) - set(frame.columns)
                if missing and not frame.empty:
                    raise RuntimeError(f"{endpoint}/{code} missing {sorted(missing)}")
                sort_column = "trade_date" if "trade_date" in frame else "start_date"
                if sort_column in frame:
                    frame = frame.sort_values(sort_column)
                legacy.atomic_csv(frame, path)
                time.sleep(args.interval)
            frame = pd.read_csv(path, dtype=str)
            files[f"{endpoint}/{code}"] = legacy.file_entry(path, len(frame), endpoint, params)
        if offset % 25 == 0:
            legacy.atomic_json(
                {
                    "schema_version": RAW_SCHEMA,
                    "status": "IN_PROGRESS",
                    "start": args.start,
                    "requested_end": args.end,
                    "latest_closed_session": latest_closed,
                    "membership_codes": len(codes),
                    "complete_membership_snapshot_count": len(complete_dates),
                    "excluded_membership_snapshots": excluded,
                    "excluded_membership_snapshots_sha256": exclusion_hash,
                    "partial_membership_forward_filled": False,
                    "excluded_snapshot_effect": "ignored; prior complete snapshot remains active",
                    "fetch_code_sha256": legacy.sha256(Path(__file__).resolve()),
                    "completed_codes": offset,
                    "provider": "Tushare-compatible proxy at http://jiaoch.site",
                    "credential_in_artifact": False,
                    "files": files,
                },
                manifest_path,
            )
    payload: dict[str, Any] = {
        "schema_version": RAW_SCHEMA,
        "status": "PASS",
        "start": args.start,
        "requested_end": args.end,
        "latest_closed_session": latest_closed,
        "membership_codes": len(codes),
        "complete_membership_snapshot_count": len(complete_dates),
        "excluded_membership_snapshots": excluded,
        "excluded_membership_snapshots_sha256": exclusion_hash,
        "partial_membership_forward_filled": False,
        "excluded_snapshot_effect": "ignored; prior complete snapshot remains active",
        "fetch_code_sha256": legacy.sha256(Path(__file__).resolve()),
        "provider": "Tushare-compatible proxy at http://jiaoch.site",
        "transport_caveat": "Provider tutorial proxy uses plain HTTP.",
        "credential_in_artifact": False,
        "files": files,
    }
    legacy.atomic_json(payload, manifest_path)
    print(json.dumps({key: value for key, value in payload.items() if key != "files"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
