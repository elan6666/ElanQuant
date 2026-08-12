"""CLI for producing an immutable strict-PIT 90/10 split receipt."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from scripts.research.contracts import build_strict_pit_split, canonical_json


def _load_dates(path: Path) -> tuple[date, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    values: Any = payload.get("trading_dates") if isinstance(payload, dict) else payload
    if not isinstance(values, list):
        raise ValueError("calendar JSON must be a list or contain trading_dates")
    return tuple(date.fromisoformat(str(value)) for value in values)


def _write(path: Path | None, payload: object) -> None:
    rendered = json.dumps(
        json.loads(canonical_json(payload)), ensure_ascii=False, indent=2, sort_keys=True
    )
    if path is None:
        print(rendered)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered + "\n", encoding="utf-8")
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calendar", type=Path, required=True)
    parser.add_argument("--latest-closed", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    receipt = build_strict_pit_split(
        _load_dates(args.calendar), latest_closed_session=args.latest_closed
    )
    _write(args.output, asdict(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
