#!/usr/bin/env python3
"""Fetch resumable CSI300 PIT OHLCVA evidence through the approved server proxy.

This script must run on the research server. It never reads or prints credential
bytes; the approved client factory owns credential access. Raw responses are
published immutably and indexed by a content-hashed manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import time
from datetime import UTC, datetime
from datetime import time as wall_time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

MARKET_TIMEZONE = ZoneInfo("Asia/Shanghai")
DAILY_FINALIZATION_TIME = wall_time(16, 15)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    frame.to_csv(temp, index=False)
    with temp.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temp, path)


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with temp.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temp, path)


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


def request(pro: Any, endpoint: str, attempts: int = 4, **params: str) -> pd.DataFrame:
    for attempt in range(attempts):
        try:
            frame = getattr(pro, endpoint)(**params)
            if not isinstance(frame, pd.DataFrame):
                raise TypeError(f"{endpoint} returned {type(frame)!r}")
            return frame
        except Exception:
            if attempt + 1 == attempts:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def file_entry(path: Path, rows: int, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
    return {
        "path": path.as_posix(),
        "endpoint": endpoint,
        "params": params,
        "rows": rows,
        "sha256": sha256(path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proxy-client", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--start", default="20110101")
    parser.add_argument("--end", required=True)
    parser.add_argument("--interval", type=float, default=0.35)
    args = parser.parse_args()

    out = args.out_root.resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.chmod(out, 0o700)
    manifest_path = out / "manifest.json"
    prior = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    if prior and (
        str(prior.get("start")) != args.start or str(prior.get("requested_end")) != args.end
    ):
        raise RuntimeError(
            "raw roots are immutable per requested range; use a new out-root for a new as-of"
        )
    files: dict[str, Any] = dict(prior.get("files", {}))
    for identity, entry in files.items():
        candidate = Path(str(entry.get("path", "")))
        if not candidate.is_file() or sha256(candidate) != entry.get("sha256"):
            raise RuntimeError(f"cannot resume because a raw file hash changed: {identity}")
    now_market = datetime.now(MARKET_TIMEZONE)
    requested_day = datetime.strptime(args.end, "%Y%m%d").date()
    if requested_day > now_market.date():
        raise RuntimeError("requested end cannot be a future date")
    if requested_day == now_market.date() and now_market.time() < DAILY_FINALIZATION_TIME:
        raise RuntimeError("requested end is not past the 16:15 Asia/Shanghai finalization gate")
    pro = approved_client(args.proxy_client.resolve())

    calendar_params = {"exchange": "", "start_date": args.start, "end_date": args.end}
    calendar_path = out / "trade_cal.csv"
    if not calendar_path.exists():
        calendar = request(pro, "trade_cal", **calendar_params).sort_values("cal_date")
        atomic_csv(calendar, calendar_path)
        time.sleep(args.interval)
    calendar = pd.read_csv(calendar_path, dtype=str)
    open_days = calendar.loc[calendar["is_open"].astype(int) == 1, "cal_date"].astype(str)
    if open_days.empty:
        raise RuntimeError("trade calendar has no open sessions")
    latest_closed = str(open_days.max())
    files["trade_cal"] = file_entry(calendar_path, len(calendar), "trade_cal", calendar_params)

    weight_frames: list[pd.DataFrame] = []
    for year in range(int(args.start[:4]), int(args.end[:4]) + 1):
        start = max(args.start, f"{year}0101")
        end = min(args.end, f"{year}1231")
        params = {"index_code": "000300.SH", "start_date": start, "end_date": end}
        path = out / "index_weight" / f"{year}.csv"
        if not path.exists():
            frame = request(pro, "index_weight", **params).sort_values(["trade_date", "con_code"])
            if frame.empty:
                raise RuntimeError(f"index_weight returned no rows for {year}")
            atomic_csv(frame, path)
            time.sleep(args.interval)
        frame = pd.read_csv(path, dtype=str)
        weight_frames.append(frame)
        files[f"index_weight/{year}"] = file_entry(path, len(frame), "index_weight", params)

    weights = pd.concat(weight_frames, ignore_index=True)
    if weights.duplicated(["trade_date", "con_code"]).any():
        raise RuntimeError("duplicate index membership rows")
    member_counts = weights.groupby("trade_date")["con_code"].nunique()
    if member_counts.min() != 300 or member_counts.max() != 300:
        bad = member_counts[(member_counts != 300)].head().to_dict()
        raise RuntimeError(f"membership snapshots are not exactly 300: {bad}")
    codes = sorted(weights["con_code"].unique())

    endpoints: dict[str, tuple[str, ...]] = {
        "daily": ("ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"),
        "adj_factor": ("ts_code", "trade_date", "adj_factor"),
        "stk_limit": ("ts_code", "trade_date", "up_limit", "down_limit"),
        "namechange": ("ts_code", "name", "start_date", "end_date", "ann_date", "change_reason"),
    }
    for offset, code in enumerate(codes, start=1):
        for endpoint, expected in endpoints.items():
            params = {"ts_code": code, "start_date": args.start, "end_date": args.end}
            path = out / endpoint / f"{code}.csv"
            if not path.exists():
                frame = request(pro, endpoint, **params)
                if endpoint == "daily" and frame.empty:
                    raise RuntimeError(f"daily returned no rows for {code}")
                if frame.empty and not len(frame.columns):
                    frame = pd.DataFrame(columns=expected)
                missing = set(expected) - set(frame.columns)
                if missing and not frame.empty:
                    raise RuntimeError(f"{endpoint} {code} missing columns {sorted(missing)}")
                sort_column = "trade_date" if "trade_date" in frame else "start_date"
                if sort_column in frame:
                    frame = frame.sort_values(sort_column)
                atomic_csv(frame, path)
                time.sleep(args.interval)
            frame = pd.read_csv(path, dtype=str)
            files[f"{endpoint}/{code}"] = file_entry(path, len(frame), endpoint, params)
        if offset % 25 == 0:
            atomic_json(
                {
                    "schema_version": "elanquant_extended_csi300_raw_v1",
                    "status": "IN_PROGRESS",
                    "start": args.start,
                    "requested_end": args.end,
                    "latest_closed_session": latest_closed,
                    "membership_codes": len(codes),
                    "completed_codes": offset,
                    "provider": "Tushare-compatible proxy at http://jiaoch.site",
                    "credential_in_artifact": False,
                    "files": files,
                },
                manifest_path,
            )

    payload = {
        "schema_version": "elanquant_extended_csi300_raw_v1",
        "status": "PASS",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "start": args.start,
        "requested_end": args.end,
        "latest_closed_session": latest_closed,
        "membership_snapshot_count": int(weights["trade_date"].nunique()),
        "membership_codes": len(codes),
        "membership_count_min": int(member_counts.min()),
        "membership_count_max": int(member_counts.max()),
        "provider": "Tushare-compatible proxy at http://jiaoch.site",
        "transport_caveat": "Provider tutorial proxy uses plain HTTP.",
        "unit_contract": {
            "vol_source": "Tushare vol in 100-share lots; model view multiplies by 100",
            "amount_source": "Tushare amount in thousand RMB; model view multiplies by 1000",
        },
        "credential_in_artifact": False,
        "files": files,
    }
    atomic_json(payload, manifest_path)
    print(json.dumps({k: payload[k] for k in payload if k != "files"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
