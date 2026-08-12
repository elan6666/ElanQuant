#!/usr/bin/env python3
"""Materialize one immutable latest-session CSI300 snapshot for button inference."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import pickle
import time
from datetime import UTC, date, datetime, timedelta
from datetime import time as wall_time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

LOOKBACK = 90
MARKET_TIMEZONE = ZoneInfo("Asia/Shanghai")
DAILY_FINALIZATION_TIME = wall_time(16, 15)


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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_pickle(value: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    with temporary.open("wb") as handle:
        pickle.dump(value, handle, protocol=pickle.HIGHEST_PROTOCOL)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_json(value: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def manifest_files_valid(snapshot: Path, manifest: dict[str, Any]) -> bool:
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        return False
    for name, expected in files.items():
        path = snapshot / str(name)
        if not path.is_file() or sha256(path) != expected:
            return False
    return bool(manifest.get("generated_after_market_finalization"))


def latest_finalized_date(requested: date, now_market: datetime) -> date:
    if now_market.tzinfo is None or now_market.utcoffset() is None:
        raise ValueError("market clock must be timezone-aware")
    bounded = min(requested, now_market.date())
    if bounded == now_market.date() and now_market.time() < DAILY_FINALIZATION_TIME:
        bounded -= timedelta(days=1)
    return bounded


def strict_online_window(
    daily: pd.DataFrame,
    factors: pd.DataFrame,
    required: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Align daily observations to the exchange calendar without future filling.

    A suspended stock has no daily bar, but it remains a valid CSI300 member.
    We carry the last known close through the missing session and set turnover to
    zero.  A window with no earlier close or adjustment factor still fails closed.
    """
    daily = daily.sort_values("datetime").drop_duplicates("datetime", keep=False)
    factors = factors.sort_values("datetime").drop_duplicates("datetime", keep=False)
    daily = daily.set_index("datetime")
    factors = factors.set_index("datetime")
    observed = pd.Series(required.isin(daily.index), index=required, dtype=bool)
    frame = daily.reindex(required).copy()
    expanded_index = daily.index.union(required).sort_values()
    factor_index = factors.index.union(required).sort_values()
    adjustment = (
        pd.to_numeric(factors["adj_factor"], errors="coerce")
        .reindex(factor_index)
        .ffill()
        .reindex(required)
    )
    closes = (
        pd.to_numeric(daily["close"], errors="coerce")
        .reindex(expanded_index)
        .ffill()
        .reindex(required)
    )
    missing = ~observed
    for column in ("open", "high", "low", "close"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame.loc[missing, column] = closes.loc[missing]
    for column in ("vol", "amount"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame.loc[missing, column] = 0.0
    frame["adj_factor"] = adjustment
    frame["observed"] = observed
    return frame[["open", "high", "low", "close", "vol", "amount", "adj_factor", "observed"]]


def execution_record(
    code: str, name: str, latest_daily: pd.Series, suspended_codes: set[str]
) -> dict[str, float | str | bool]:
    observed = bool(latest_daily["observed"])
    return {
        "name": name,
        "open": float(latest_daily["open"]),
        "close": float(latest_daily["close"]),
        "observed": observed,
        "suspended": code in suspended_codes or not observed,
        "buy_restricted": "ST" in name.upper(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proxy-client", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--target-session", required=True)
    parser.add_argument("--interval", type=float, default=0.35)
    args = parser.parse_args()
    requested = date.fromisoformat(args.target_session)
    snapshot_logic_sha256 = sha256(Path(__file__).resolve())
    now_market = datetime.now(MARKET_TIMEZONE)
    latest_allowed_date = latest_finalized_date(requested, now_market)
    start = requested - timedelta(days=365)
    calendar_end = requested + timedelta(days=120)
    pro = approved_client(args.proxy_client.resolve())
    calendar = request(
        pro,
        "trade_cal",
        exchange="",
        start_date=start.strftime("%Y%m%d"),
        end_date=calendar_end.strftime("%Y%m%d"),
    )
    calendar["cal_date"] = calendar["cal_date"].astype(str)
    open_days = sorted(
        calendar.loc[
            (calendar["is_open"].astype(int) == 1)
            & (calendar["cal_date"] <= latest_allowed_date.strftime("%Y%m%d")),
            "cal_date",
        ].astype(str)
    )
    if len(open_days) < LOOKBACK:
        raise RuntimeError("trade calendar is too short")
    resolved = open_days[-1]
    history_days = open_days[-LOOKBACK:]
    out_root = args.out_root.resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    base_name = pd.Timestamp(resolved).strftime("%Y-%m-%d")
    canonical = out_root / base_name
    for prior_snapshot in sorted(out_root.glob(f"{base_name}*"), reverse=True):
        prior_manifest = prior_snapshot / "manifest.json"
        if not prior_manifest.is_file():
            continue
        prior = json.loads(prior_manifest.read_text(encoding="utf-8"))
        if (
            prior.get("status") == "PASS"
            and prior.get("snapshot_logic_sha256") == snapshot_logic_sha256
            and manifest_files_valid(prior_snapshot, prior)
        ):
            print(json.dumps({"status": "REUSED", "snapshot": prior_snapshot.as_posix()}))
            return 0
    snapshot = canonical
    if snapshot.exists():
        attempt = datetime.now(UTC).strftime("%H%M%S-%f")
        snapshot = out_root / f"{base_name}-attempt-{attempt}"
    manifest_path = snapshot / "manifest.json"
    snapshot.mkdir(parents=True, exist_ok=False)
    os.chmod(snapshot, 0o700)
    weights = request(
        pro,
        "index_weight",
        index_code="000300.SH",
        start_date=start.strftime("%Y%m%d"),
        end_date=resolved,
    )
    weights["trade_date"] = weights["trade_date"].astype(str)
    membership_date = weights.loc[weights["trade_date"] < resolved, "trade_date"].max()
    if not isinstance(membership_date, str):
        raise RuntimeError("no membership snapshot survives the one-session availability lag")
    members = sorted(
        weights.loc[weights["trade_date"] == membership_date, "con_code"].astype(str).unique()
    )
    if len(members) != 300:
        raise RuntimeError(f"resolved membership has {len(members)} members, expected 300")
    frames: dict[str, pd.DataFrame] = {}
    execution: dict[str, dict[str, float]] = {}
    excluded: dict[str, str] = {}
    suspended_frame = request(pro, "suspend_d", trade_date=resolved)
    suspended_codes = (
        set(suspended_frame["ts_code"].astype(str))
        if not suspended_frame.empty and "ts_code" in suspended_frame
        else set()
    )
    stock_frames = [
        request(pro, "stock_basic", exchange="", list_status=status, fields="ts_code,name")
        for status in ("L", "D", "P")
    ]
    stock_basic = pd.concat(stock_frames, ignore_index=True)
    current_names = (
        dict(zip(stock_basic["ts_code"].astype(str), stock_basic["name"].astype(str), strict=False))
        if not stock_basic.empty
        else {}
    )
    # Pull a buffer before the 90-session window so a suspension on its first
    # session can be filled only from information already available before it.
    query_start = (pd.Timestamp(history_days[0]) - pd.Timedelta(days=45)).strftime("%Y%m%d")
    for code in members:
        daily = request(pro, "daily", ts_code=code, start_date=query_start, end_date=resolved)
        time.sleep(args.interval)
        factors = request(
            pro, "adj_factor", ts_code=code, start_date=query_start, end_date=resolved
        )
        time.sleep(args.interval)
        limits = request(pro, "stk_limit", ts_code=code, start_date=query_start, end_date=resolved)
        time.sleep(args.interval)
        if daily.empty or factors.empty:
            excluded[code] = "missing_daily_or_adjustment"
            continue
        if "trade_date" not in daily or "trade_date" not in factors:
            excluded[code] = "provider_schema_mismatch"
            continue
        daily_dates = daily["trade_date"].astype(str)
        factor_dates = factors["trade_date"].astype(str)
        daily = daily.loc[daily_dates.str.fullmatch(r"\d{8}")].copy()
        factors = factors.loc[factor_dates.str.fullmatch(r"\d{8}")].copy()
        if daily.empty or factors.empty:
            excluded[code] = "provider_invalid_trade_date"
            continue
        daily["datetime"] = pd.to_datetime(daily["trade_date"].astype(str), format="%Y%m%d")
        factors["datetime"] = pd.to_datetime(
            factors["trade_date"].astype(str), format="%Y%m%d"
        )
        required = pd.DatetimeIndex(pd.to_datetime(history_days, format="%Y%m%d"))
        frame = strict_online_window(daily, factors, required)
        if (
            frame.isna().any().any()
            or not (frame[["open", "high", "low", "close", "adj_factor"]] > 0).all().all()
        ):
            excluded[code] = "invalid_numeric_values"
            continue
        frame["vol"] *= 100.0
        frame["amount"] *= 1000.0
        frame = frame.rename(columns={"amount": "amt"})
        frames[code] = frame
        latest_daily = frame.iloc[-1]
        execution[code] = execution_record(
            code, current_names.get(code, code), latest_daily, suspended_codes
        )
        if not limits.empty:
            limits["trade_date"] = limits["trade_date"].astype(str)
            latest_limit = limits.loc[limits["trade_date"] == resolved]
            if not latest_limit.empty:
                execution[code]["up_limit"] = float(latest_limit.iloc[0]["up_limit"])
                execution[code]["down_limit"] = float(latest_limit.iloc[0]["down_limit"])
    if len(frames) < 250:
        atomic_json(
            {
                "schema_version": "elanquant_online_snapshot_v1",
                "status": "DATA_INCOMPLETE",
                "requested_session": args.target_session,
                "resolved_session": pd.Timestamp(resolved).strftime("%Y-%m-%d"),
                "eligible_symbols": len(frames),
                "excluded": excluded,
            },
            manifest_path,
        )
        raise RuntimeError(f"only {len(frames)} members have complete online windows")
    data_path = snapshot / "online_data.pkl"
    calendar_path = snapshot / "trade_cal.csv"
    execution_path = snapshot / "execution.json"
    atomic_pickle(frames, data_path)
    calendar.sort_values("cal_date").to_csv(calendar_path, index=False)
    atomic_json(execution, execution_path)
    manifest = {
        "schema_version": "elanquant_online_snapshot_v1",
        "status": "PASS",
        "snapshot_logic_sha256": snapshot_logic_sha256,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "market_timezone": "Asia/Shanghai",
        "daily_finalization_cutoff": "16:15:00",
        "generated_after_market_finalization": (
            pd.Timestamp(resolved).date() < now_market.date()
            or now_market.time() >= DAILY_FINALIZATION_TIME
        ),
        "requested_session": args.target_session,
        "resolved_session": pd.Timestamp(resolved).strftime("%Y-%m-%d"),
        "membership_snapshot": pd.Timestamp(membership_date).strftime("%Y-%m-%d"),
        "membership_available_session": pd.Timestamp(resolved).strftime("%Y-%m-%d"),
        "membership_availability_policy": "provider_trade_date_plus_one_complete_session",
        "membership_revision_limitation": (
            "Provider supplies no historical first-seen receipt; later revisions "
            "cannot be excluded."
        ),
        "membership_count": len(members),
        "eligible_symbols": len(frames),
        "excluded": excluded,
        "provider": "Tushare-compatible proxy at http://jiaoch.site",
        "transport_caveat": "Provider tutorial proxy uses plain HTTP.",
        "files": {
            "online_data.pkl": sha256(data_path),
            "trade_cal.csv": sha256(calendar_path),
            "execution.json": sha256(execution_path),
        },
    }
    atomic_json(manifest, manifest_path)
    print(json.dumps({"status": "PASS", "snapshot": snapshot.as_posix(), "eligible": len(frames)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
