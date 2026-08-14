#!/usr/bin/env python3
"""Build, validate, and atomically write an official-split v3 receipt."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path
from typing import Any

from scripts.research.official_split_v3 import build_split_receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calendar", type=Path, required=True)
    parser.add_argument("--frozen-latest", type=date.fromisoformat, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    raw: Any = json.loads(args.calendar.read_text(encoding="utf-8"))
    values = raw.get("trading_dates") if isinstance(raw, dict) else raw
    if not isinstance(values, list):
        raise RuntimeError("calendar must be a list or contain trading_dates")
    payload = build_split_receipt(
        [date.fromisoformat(str(value)) for value in values],
        frozen_latest=args.frozen_latest,
    )
    if args.out.exists():
        raise RuntimeError("official-split receipt is immutable; output already exists")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.out.with_suffix(args.out.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, args.out)
    print(json.dumps({"status": "PASS", "receipt_hash": payload["receipt_hash"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
