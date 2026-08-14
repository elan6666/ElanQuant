#!/usr/bin/env python3
"""Build deterministic compiler inputs for the official-split v3 four-cell matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return value


def atomic_new(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise RuntimeError(f"immutable output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--small-training-run-id", required=True)
    parser.add_argument("--base-training-run-id", required=True)
    parser.add_argument("--small-legacy-matrix", type=Path, required=True)
    parser.add_argument("--base-legacy-matrix", type=Path, required=True)
    parser.add_argument("--matrix-source-out", type=Path, required=True)
    parser.add_argument("--retirement-source-out", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()

    weights = read_object(root / "models" / "pretrained" / "receipt.json")
    if weights.get("status") != "PASS" or not isinstance(weights.get("models"), dict):
        raise RuntimeError("official pretrained weight receipt is not PASS")
    models = weights["models"]
    tokenizer_sha = str(models["NeoQuasar/Kronos-Tokenizer-base"]["model_sha256"])

    cells: list[dict[str, Any]] = []
    for size, training_run_id in (
        ("base", args.base_training_run_id),
        ("small", args.small_training_run_id),
    ):
        predictor_sha = str(models[f"NeoQuasar/Kronos-{size}"]["model_sha256"])
        zero_config = root / "source" / "configs" / "models" / (
            f"official_split_v3_{size}_zero_shot.yaml"
        )
        cells.append(
            {
                "id": f"{size}-zero-shot",
                "training_mode": "zero_shot",
                "tokenizer_sha256": tokenizer_sha,
                "predictor_sha256": predictor_sha,
                "config_sha256": sha256(zero_config),
            }
        )
        terminal_root = root / "runs" / "training" / training_run_id
        tokenizer_terminal = terminal_root / "tokenizer" / "terminal.json"
        predictor_terminal = terminal_root / "predictor" / "terminal.json"
        if not tokenizer_terminal.is_file() or not predictor_terminal.is_file():
            raise RuntimeError(f"training terminals are incomplete: {training_run_id}")
        cells.append(
            {
                "id": f"{size}-official-ft",
                "training_mode": "official_ft",
                "tokenizer_terminal_path": tokenizer_terminal.relative_to(root).as_posix(),
                "predictor_terminal_path": predictor_terminal.relative_to(root).as_posix(),
            }
        )

    small_legacy = args.small_legacy_matrix.resolve()
    base_legacy = args.base_legacy_matrix.resolve()
    for path in (small_legacy, base_legacy):
        if not path.is_file() or root not in path.parents:
            raise RuntimeError(f"legacy matrix path is invalid: {path}")
    matrix_source = {"run_id": args.run_id, "cells": cells}
    retirement_source = {
        "retired_cell_ids": ["small-strict-pit", "base-strict-pit"],
        "active": False,
        "artifacts_deleted": False,
        "legacy_evidence": [
            {"cell_id": "small-strict-pit", "receipt_sha256": sha256(small_legacy)},
            {"cell_id": "base-strict-pit", "receipt_sha256": sha256(base_legacy)},
        ],
    }
    atomic_new(args.matrix_source_out, matrix_source)
    atomic_new(args.retirement_source_out, retirement_source)
    print(json.dumps({"status": "PASS", "cells": [row["id"] for row in cells]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
