from __future__ import annotations

import argparse
import math
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from elanquant.repro.common import atomic_json, canonical_sha256, sha256_file

REQUIRED = ("instrument", "timestamp", "open", "high", "low", "close")
OPTIONAL = ("volume", "amount")


def _pandas() -> Any:
    try:
        import pandas as pd
    except ImportError as error:  # pragma: no cover - exercised by package smoke
        raise RuntimeError("data import requires elanquant[repro]") from error
    return pd


def _canonical_rows(frame: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in frame.itertuples(index=False):
        row = {
            "instrument": str(item.instrument),
            "timestamp": item.timestamp.isoformat(),
        }
        for column in (*REQUIRED[2:], *OPTIONAL):
            row[column] = format(float(getattr(item, column)), ".17g")
        rows.append(row)
    return rows


def normalize_market_file(
    source: Path,
    output: Path,
    *,
    timezone: str,
    calendar: str,
    universe_policy: str,
    pit_declaration: str,
    source_license: str,
) -> dict[str, Any]:
    pd = _pandas()
    if source.suffix.lower() == ".csv":
        frame = pd.read_csv(source)
        source_format = "csv"
    elif source.suffix.lower() in {".parquet", ".pq"}:
        frame = pd.read_parquet(source)
        source_format = "parquet"
    else:
        raise ValueError("input must be CSV or Parquet")
    missing = set(REQUIRED) - set(frame.columns)
    if missing:
        raise ValueError(f"input is missing columns: {sorted(missing)}")
    frame = frame[list(REQUIRED) + [column for column in OPTIONAL if column in frame]].copy()
    for column in OPTIONAL:
        if column not in frame:
            frame[column] = 0.0
    frame["instrument"] = frame["instrument"].astype(str).str.strip()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="raise")
    if getattr(frame["timestamp"].dt, "tz", None) is not None:
        frame["timestamp"] = frame["timestamp"].dt.tz_convert(timezone).dt.tz_localize(None)
    numeric = [*REQUIRED[2:], *OPTIONAL]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="raise")
    if frame.empty:
        raise ValueError("input contains no rows")
    if not frame["instrument"].str.fullmatch(r"[A-Za-z0-9._-]+", na=False).all():
        raise ValueError("instrument identity is empty or malformed")
    if frame.duplicated(["instrument", "timestamp"]).any():
        raise ValueError("duplicate instrument/timestamp rows")
    values = frame[numeric].to_numpy(dtype=float)
    if not all(math.isfinite(float(value)) for value in values.flat):
        raise ValueError("market values must be finite")
    if (frame[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("OHLC values must be positive")
    if (frame[["volume", "amount"]] < 0).any().any():
        raise ValueError("volume and amount must be non-negative")
    if (
        (frame["high"] < frame[["open", "close", "low"]].max(axis=1)).any()
        or (frame["low"] > frame[["open", "close", "high"]].min(axis=1)).any()
    ):
        raise ValueError("OHLC relationship is invalid")
    frame = frame.sort_values(["instrument", "timestamp"], kind="stable").reset_index(drop=True)
    if (frame.groupby("instrument")["timestamp"].diff().dropna() <= pd.Timedelta(0)).any():
        raise ValueError("timestamps must be strictly increasing per instrument")
    now = pd.Timestamp(datetime.now(UTC)).tz_convert(timezone).tz_localize(None)
    if frame["timestamp"].max() > now:
        raise ValueError("input contains a future timestamp")
    rows = _canonical_rows(frame)
    canonical_data_sha = canonical_sha256(rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + f".tmp-{os.getpid()}")
    if output.suffix.lower() == ".csv":
        frame.to_csv(temp, index=False, date_format="%Y-%m-%dT%H:%M:%S")
    elif output.suffix.lower() in {".parquet", ".pq"}:
        frame.to_parquet(temp, index=False)
    else:
        raise ValueError("output must be CSV or Parquet")
    os.replace(temp, output)
    identity = {
        "calendar": calendar,
        "canonical_data_sha256": canonical_data_sha,
        "columns": [*REQUIRED, *OPTIONAL],
        "first_timestamp": frame["timestamp"].min().isoformat(),
        "instruments": int(frame["instrument"].nunique()),
        "last_timestamp": frame["timestamp"].max().isoformat(),
        "output_bytes": output.stat().st_size,
        "output_sha256": sha256_file(output),
        "pit_declaration": pit_declaration,
        "rows": len(frame),
        "sessions": int(frame["timestamp"].nunique()),
        "source_file_sha256": sha256_file(source),
        "source_format": source_format,
        "source_license": source_license,
        "timezone": timezone,
        "universe_policy": universe_policy,
    }
    receipt = {
        "schema_version": "elanquant_input_data_receipt_v1",
        "status": "PASS",
        "credential_in_artifact": False,
        **identity,
    }
    receipt["receipt_hash"] = canonical_sha256(receipt)
    atomic_json(output.with_suffix(output.suffix + ".receipt.json"), receipt)
    return receipt


def add_data_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser("data", help="Import user-owned market data")
    actions = parser.add_subparsers(dest="data_action", required=True)
    command = actions.add_parser("import", help="Validate CSV/Parquet and write a receipt")
    command.add_argument("--input", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    command.add_argument("--timezone", default="Asia/Shanghai")
    command.add_argument("--calendar", required=True)
    command.add_argument("--universe-policy", required=True)
    command.add_argument("--pit-declaration", required=True)
    command.add_argument("--source-license", required=True)
    command.set_defaults(handler=run_data_command)


def run_data_command(args: argparse.Namespace) -> int:
    receipt = normalize_market_file(
        args.input,
        args.output,
        timezone=args.timezone,
        calendar=args.calendar,
        universe_policy=args.universe_policy,
        pit_declaration=args.pit_declaration,
        source_license=args.source_license,
    )
    print(receipt["receipt_hash"])
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_data_parser(subparsers)
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
