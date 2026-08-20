#!/usr/bin/env python3
"""Materialise the immutable common input for the B2/Kronos weekly comparison.

This server-only producer reads the sealed B2 common-support and prediction
artifacts, then reconstructs its strict-weekly open-to-open labels from the
same canonical market files.  It does not create new B2 predictions and it
does not read any post-anchor row to decide whether a name is eligible.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path


def sha256(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"required source is absent: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def payload(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def market_opens(canonical_root: Path, instrument: str) -> dict[str, float]:
    path = canonical_root / "common" / "daily_market" / f"{instrument}.jsonl"
    if not path.is_file():
        raise RuntimeError(f"canonical daily market file is absent: {instrument}")
    values: dict[str, float] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        day, open_ = row.get("trade_date"), row.get("open")
        if (
            not isinstance(day, str)
            or isinstance(open_, bool)
            or not isinstance(open_, (int, float))
        ):
            raise RuntimeError(f"canonical daily market row is malformed: {instrument}")
        if not math.isfinite(float(open_)) or float(open_) <= 0:
            raise RuntimeError(f"canonical open is invalid: {instrument}/{day}")
        values[day] = float(open_)
    return values


def next_session(calendar: list[str], index: dict[str, int], anchor: str) -> str:
    position = index.get(anchor)
    if position is None or position + 1 >= len(calendar):
        raise RuntimeError(f"strict-weekly anchor has no next session: {anchor}")
    return calendar[position + 1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--common-support", type=Path, required=True)
    parser.add_argument("--b2-predictions", type=Path, required=True)
    parser.add_argument("--canonical-root", type=Path, required=True)
    parser.add_argument("--signal-calendar", type=Path, required=True)
    parser.add_argument("--b2-checkpoint", type=Path, required=True)
    parser.add_argument("--b2-runner", type=Path, required=True)
    parser.add_argument("--kronos-upstream", type=Path, required=True)
    parser.add_argument("--kronos-tokenizer", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    root, out = args.root.resolve(), args.out_dir.resolve()
    if out.exists() or root not in out.parents:
        raise RuntimeError("out-dir must be a new path below the server research root")
    for path in (
        args.common_support,
        args.b2_predictions,
        args.signal_calendar,
        args.b2_checkpoint,
        args.b2_runner,
    ):
        sha256(path.resolve())
    if (
        not args.canonical_root.is_dir()
        or not args.kronos_upstream.is_dir()
        or not args.kronos_tokenizer.is_dir()
    ):
        raise RuntimeError("canonical, upstream or tokenizer input is absent")

    common = payload(args.common_support)
    keys = common.get("keys")
    if not isinstance(keys, list) or not keys:
        raise RuntimeError("sealed B2 common support is empty")
    pairs = [
        (str(row.get("signal_date")), str(row.get("ts_code")))
        for row in keys
        if isinstance(row, dict)
    ]
    if len(pairs) != len(keys) or len(set(pairs)) != len(pairs):
        raise RuntimeError("sealed B2 common support has malformed or duplicate keys")
    anchors = sorted({anchor for anchor, _ in pairs})

    calendar_payload = payload(args.signal_calendar)
    calendar = calendar_payload.get("signal_dates")
    if not isinstance(calendar, list) or not all(isinstance(day, str) for day in calendar):
        raise RuntimeError("canonical global signal calendar is invalid")
    calendar = list(calendar)
    calendar_index = {day: position for position, day in enumerate(calendar)}
    if len(calendar_index) != len(calendar):
        raise RuntimeError("canonical global signal calendar contains duplicates")
    if any(anchor not in calendar_index for anchor in anchors):
        raise RuntimeError("B2 common support anchor is absent from the canonical calendar")

    # Holding periods are the B2 strict-weekly convention: T+1 open through
    # the next weekly anchor's T+1 open.  The terminal period uses the next
    # final weekday anchor even though no new prediction is emitted there.
    exits: dict[str, str] = {}
    for current, following in zip(anchors, anchors[1:], strict=False):
        exits[current] = next_session(calendar, calendar_index, following)
    last_position = calendar_index[anchors[-1]]
    # The strict schedule takes the last trading session of a calendar week.
    # In the terminal week that is normally Friday; if a holiday removes it,
    # the five-session fallback keeps the horizon explicit rather than
    # inventing a post-cutoff label.
    final_anchor = next(
        (day for day in calendar[last_position + 1 :] if date.fromisoformat(day).weekday() == 4),
        None,
    )
    if final_anchor is None:
        final_anchor = calendar[last_position + 5]
    exits[anchors[-1]] = next_session(calendar, calendar_index, final_anchor)

    prediction = payload(args.b2_predictions)
    records = prediction.get("records")
    if not isinstance(records, list):
        raise RuntimeError("B2 prediction frame is invalid")
    b2_scores: dict[tuple[str, str], float] = {}
    for row in records:
        if not isinstance(row, dict) or row.get("coverage_state") != "SCORED":
            continue
        key = (str(row.get("signal_date")), str(row.get("ts_code")))
        score = row.get("score")
        if key in set(pairs):
            if (
                isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not math.isfinite(float(score))
            ):
                raise RuntimeError(f"B2 score is invalid: {key}")
            b2_scores[key] = float(score)
    if set(b2_scores) != set(pairs):
        raise RuntimeError("B2 prediction frame does not exactly cover sealed common support")

    opens_by_instrument = {
        instrument: market_opens(args.canonical_root, instrument) for _, instrument in pairs
    }
    # A common evaluation row must be usable by *both* models.  The B2 common
    # support already proves its own 80-session context; Kronos additionally
    # requires all 90 globally scheduled sessions ending at T.  This filter
    # inspects only rows dated at or before T, never the label horizon.
    joint_pairs: list[tuple[str, str]] = []
    excluded_past_context: dict[str, int] = defaultdict(int)
    for anchor, instrument in pairs:
        position = calendar_index[anchor]
        required_history = calendar[position - 89 : position + 1]
        if position < 89 or any(
            day not in opens_by_instrument[instrument] for day in required_history
        ):
            excluded_past_context[anchor] += 1
            continue
        joint_pairs.append((anchor, instrument))
    if not joint_pairs:
        raise RuntimeError("B2/Kronos joint causal support is empty")
    by_anchor = defaultdict(int)
    for anchor, _ in joint_pairs:
        by_anchor[anchor] += 1
    if any(by_anchor[anchor] < 50 for anchor in anchors):
        raise RuntimeError("B2/Kronos joint causal support has fewer than Top50 candidates")
    label_rows: list[dict[str, object]] = []
    per_anchor: dict[str, list[float]] = defaultdict(list)
    for anchor, instrument in sorted(joint_pairs):
        entry, exit_ = next_session(calendar, calendar_index, anchor), exits[anchor]
        opens = opens_by_instrument[instrument]
        if entry not in opens or exit_ not in opens:
            raise RuntimeError(f"sealed common support lacks label prices: {anchor}/{instrument}")
        result = math.log(opens[exit_] / opens[entry])
        per_anchor[anchor].append(result)
        label_rows.append({"anchor": anchor, "instrument": instrument, "realized_return": result})
    benchmark = {anchor: sum(values) / len(values) for anchor, values in per_anchor.items()}
    for row in label_rows:
        row["benchmark_return"] = benchmark[str(row["anchor"])]

    out.mkdir(parents=True)
    support_path = out / "support.csv"
    with support_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["anchor", "instrument", "realized_return", "benchmark_return"]
        )
        writer.writeheader()
        writer.writerows(label_rows)
    scores_path = out / "b2-scores.csv"
    with scores_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["anchor", "instrument", "score"])
        writer.writeheader()
        writer.writerows(
            {"anchor": anchor, "instrument": instrument, "score": b2_scores[(anchor, instrument)]}
            for anchor, instrument in sorted(joint_pairs)
        )
    calendar_path = out / "global-calendar.json"
    calendar_path.write_text(
        json.dumps({"sessions": calendar}, sort_keys=True) + "\n", encoding="utf-8"
    )
    kronos_input = out / "kronos-input.json"
    kronos_input.write_text(
        json.dumps(
            {
                "canonical_root": str(args.canonical_root.resolve()),
                "upstream": str(args.kronos_upstream.resolve()),
                "tokenizer": str(args.kronos_tokenizer.resolve()),
                "device": args.device,
                "trade_calendar": str(calendar_path.resolve()),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    b2_input = out / "b2-input.json"
    b2_input.write_text(
        json.dumps(
            {
                "common_support": str(args.common_support.resolve()),
                "predictions": str(args.b2_predictions.resolve()),
                "canonical_root": str(args.canonical_root.resolve()),
                "signal_calendar": str(args.signal_calendar.resolve()),
                "label_semantics": "log(next_week_exit_open / next_session_open)",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    receipt = {
        "schema_version": "elanquant_b2_kronos_weekly_input_v1",
        "status": "PASS",
        "generated_at": datetime.now(UTC).isoformat(),
        "anchors": len(anchors),
        "signal_rows": len(label_rows),
        "source_signal_rows": len(pairs),
        "excluded_for_kronos_past_context": dict(sorted(excluded_past_context.items())),
        "label_definition": "strict_weekly_open_to_open_log_return",
        "sources": {
            "common_support_sha256": sha256(args.common_support.resolve()),
            "b2_predictions_sha256": sha256(args.b2_predictions.resolve()),
            "b2_checkpoint_sha256": sha256(args.b2_checkpoint.resolve()),
            "b2_runner_sha256": sha256(args.b2_runner.resolve()),
            "signal_calendar_sha256": sha256(args.signal_calendar.resolve()),
        },
        "artifacts": {
            "support_sha256": sha256(support_path),
            "b2_scores_sha256": sha256(scores_path),
            "calendar_sha256": sha256(calendar_path),
        },
        "online_paper_equivalent": False,
        "promotion_eligible": False,
    }
    (out / "input-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps({"status": "PASS", "out_dir": str(out), **receipt["artifacts"]}, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
