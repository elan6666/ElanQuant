"""Validate and seal the three-cell Small experiment matrix."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from scripts.research.contracts import (
    ExperimentCell,
    ExperimentRegime,
    ExperimentStatus,
    build_experiment_matrix_receipt,
    canonical_json,
)


def _load_cells(path: Path) -> tuple[ExperimentCell, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload.get("cells") if isinstance(payload, dict) else payload
    if not isinstance(values, list):
        raise ValueError("matrix JSON must be a list or contain cells")
    return tuple(
        ExperimentCell(
            **{
                **row,
                "regime": ExperimentRegime(row["regime"]),
                "status": ExperimentStatus(row["status"]),
                "trained_components": tuple(row["trained_components"]),
            }
        )
        for row in values
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-terminal", action="store_true")
    args = parser.parse_args(argv)
    receipt = build_experiment_matrix_receipt(
        _load_cells(args.input), require_terminal=args.require_terminal
    )
    rendered = json.dumps(
        json.loads(canonical_json(asdict(receipt))), ensure_ascii=False, indent=2, sort_keys=True
    )
    if args.output is None:
        print(rendered)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(rendered + "\n", encoding="utf-8")
        temporary.replace(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
