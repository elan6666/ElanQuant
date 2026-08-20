#!/usr/bin/env python3
"""Actual Kronos Base zero-shot scoring adapter for the B2 weekly cohort.

The adapter is deliberately invoked by ``run_unified_b2_kronos_weekly.py``.
It consumes only the already frozen B2 anchor/instrument support and an
explicit JSON input manifest; it never invents a calendar, universe, label or
execution session of its own.
"""
from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

LOOKBACK = 90
SAMPLE_COUNT = 5
SEED = 100
BATCH = 128


def _config(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    expected = {"canonical_root", "upstream", "tokenizer", "device", "trade_calendar"}
    if not isinstance(value, dict) or set(value) != expected:
        raise RuntimeError("Kronos weekly input manifest has an invalid schema")
    if not all(isinstance(value[key], str) and value[key] for key in expected):
        raise RuntimeError("Kronos weekly input manifest has invalid paths")
    return value


def _history(
    root: Path, code: str, anchor: str, calendar: pd.DatetimeIndex
) -> pd.DataFrame:
    path = root / "common/daily_market" / f"{code}.jsonl"
    if not path.is_file():
        raise RuntimeError(f"canonical B2 market input is absent: {code}")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    frame = pd.DataFrame(rows)
    required = ["trade_date", "open", "high", "low", "close", "volume", "amount"]
    if any(column not in frame for column in required):
        raise RuntimeError(f"canonical B2 market schema is incomplete: {code}")
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    anchor_date = pd.Timestamp(anchor)
    positions = {day: index for index, day in enumerate(calendar)}
    position = positions.get(anchor_date)
    if position is None or position < LOOKBACK - 1:
        raise RuntimeError(f"B2 strict-weekly calendar lacks 90 prior sessions: {code}/{anchor}")
    # Do not create a Kronos context by stitching together a symbol's last
    # available rows.  Eligibility at T is determined only by the 90 known
    # *global* sessions ending at T; gaps fail closed and future availability
    # is never inspected.
    expected = calendar[position - LOOKBACK + 1 : position + 1]
    frame = frame.loc[frame["trade_date"] <= anchor_date, required].set_index("trade_date")
    context = frame.reindex(expected)
    if context.isnull().any().any():
        raise RuntimeError(
            f"B2 common support has an incomplete 90-session context: {code}/{anchor}"
        )
    # The B2 canonical store names the same two fields ``volume``/``amount``;
    # pinned Kronos expects ``vol``/``amt``.  Select exactly six columns after
    # this one-to-one alias, so a duplicate source column cannot alter feature
    # order or width.
    context = context.rename(columns={"volume": "vol", "amount": "amt"})
    if list(context.columns) != ["open", "high", "low", "close", "vol", "amt"]:
        raise RuntimeError(f"canonical B2 feature aliases are ambiguous: {code}/{anchor}")
    values = context[
        ["open", "high", "low", "close", "vol", "amt"]
    ].to_numpy(dtype=np.float32)
    if not np.isfinite(values).all() or (values[:, :4] <= 0).any() or (values[:, 4:] < 0).any():
        raise RuntimeError(f"non-finite or invalid OHLCVA context: {code}/{anchor}")
    return context


def generate_scores(
    support_csv: Path, model_path: Path, input_path: Path, output_csv: Path
) -> None:
    """Write exactly one Base score for every supplied B2 support row.

    ``model_path`` is the public Base ``model.safetensors`` path.  Its parent
    is passed to ``from_pretrained``; the separately locked manifest carries
    the tokenizer directory and pinned upstream source.
    """
    config = _config(input_path)
    canonical_root = Path(str(config["canonical_root"])).resolve()
    upstream = Path(str(config["upstream"])).resolve()
    tokenizer_path = Path(str(config["tokenizer"])).resolve()
    calendar_path = Path(str(config["trade_calendar"])).resolve()
    device = str(config["device"])
    if (
        not canonical_root.is_dir()
        or not upstream.is_dir()
        or not tokenizer_path.is_dir()
        or not calendar_path.is_file()
    ):
        raise RuntimeError("Kronos weekly input manifest references an absent path")
    if not model_path.is_file():
        raise RuntimeError("public Kronos Base model file is absent")
    sys.path.insert(0, str(upstream))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import torch
    from generate_official_demo_signals import normalized_context, time_features
    from model.kronos import Kronos, KronosTokenizer, auto_regressive_inference

    if device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("requested CUDA device is unavailable")
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)
    tokenizer = KronosTokenizer.from_pretrained(tokenizer_path).to(device).eval()
    model = Kronos.from_pretrained(model_path.parent).to(device).eval()
    with support_csv.open(encoding="utf-8", newline="") as handle:
        support = list(csv.DictReader(handle))
    if not support or any(not row.get("anchor") or not row.get("instrument") for row in support):
        raise RuntimeError("B2 support CSV is invalid")
    calendar_raw = json.loads(calendar_path.read_text(encoding="utf-8"))
    days = calendar_raw.get("sessions") if isinstance(calendar_raw, dict) else calendar_raw
    if not isinstance(days, list) or not all(isinstance(day, str) for day in days):
        raise RuntimeError("B2 strict-weekly calendar payload is invalid")
    calendar = pd.DatetimeIndex(pd.to_datetime(days)).sort_values()
    positions = {str(day.date()): index for index, day in enumerate(calendar)}
    rows: list[dict[str, object]] = []
    with torch.no_grad():
        for offset in range(0, len(support), BATCH):
            batch = support[offset : offset + BATCH]
            contexts, x_stamps, y_stamps, identities = [], [], [], []
            for row in batch:
                context = _history(
                    canonical_root,
                    str(row["instrument"]),
                    str(row["anchor"]),
                    calendar,
                )
                normalized = normalized_context(context)
                # The common B2 outcome is the next strict-week holding period;
                # use the first five predicted sessions for a path-derived
                # ranking score, not an invented predicted open-to-open return.
                position = positions.get(str(pd.Timestamp(row["anchor"]).date()))
                if position is None or position + 5 >= len(calendar):
                    raise RuntimeError("B2 support anchor has no five-session global horizon")
                future = calendar[position + 1 : position + 6]
                contexts.append(normalized)
                x_stamps.append(time_features(context.index))
                y_stamps.append(time_features(future))
                identities.append(
                    (
                        str(row["anchor"]),
                        str(row["instrument"]),
                        float(normalized[-1, 3]),
                    )
                )
            prediction = auto_regressive_inference(
                tokenizer, model,
                torch.from_numpy(np.stack(contexts)).to(device),
                torch.from_numpy(np.stack(x_stamps)).to(device),
                torch.from_numpy(np.stack(y_stamps)).to(device),
                max_context=512, pred_len=5, clip=5.0, T=0.6, top_k=0, top_p=0.9,
                sample_count=SAMPLE_COUNT,
            )
            for (anchor, instrument, reference), item in zip(
                identities, np.asarray(prediction), strict=True
            ):
                score = float(np.asarray(item)[-5:, 3].mean() - reference)
                rows.append({"anchor": anchor, "instrument": instrument, "score": score})
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["anchor", "instrument", "score"])
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: (str(row["anchor"]), str(row["instrument"]))))
