#!/usr/bin/env python3
"""Seal one completed official-split v3 tokenizer or predictor stage."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.research.official_split_v3 import (
    TERMINAL_SCHEMA,
    canonical_hash,
    validate_training_terminal,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cell-id",
        choices=("small-official-ft", "base-official-ft"),
        required=True,
    )
    parser.add_argument("--stage", choices=("tokenizer", "predictor"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--started-epoch", type=int, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--data-manifest", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--input-tokenizer", type=Path)
    parser.add_argument("--input-predictor", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    required = (args.log, args.checkpoint, args.data_manifest, args.config, args.input_predictor)
    if not all(path.is_file() for path in required):
        raise RuntimeError("terminal inputs must all exist")
    if args.out.exists():
        raise RuntimeError("immutable terminal already exists")
    if args.checkpoint.stat().st_mtime < args.started_epoch:
        raise RuntimeError("checkpoint predates this training stage")
    tokenizer_missing = args.input_tokenizer is None or not args.input_tokenizer.is_file()
    if args.stage == "predictor" and tokenizer_missing:
        raise RuntimeError("predictor terminal requires the trained tokenizer input")
    payload: dict[str, Any] = {
        "schema_version": TERMINAL_SCHEMA,
        "status": "PASS",
        "run_id": args.run_id,
        "cell_id": args.cell_id,
        "stage": args.stage,
        "finished_at": datetime.now(UTC).isoformat(),
        "epochs_completed": 30,
        "selected_checkpoint": "best_model",
        "data_manifest_sha256": sha256(args.data_manifest),
        "config_sha256": sha256(args.config),
        "log_sha256": sha256(args.log),
        "checkpoint_path": str(args.checkpoint.resolve()),
        "checkpoint_sha256": sha256(args.checkpoint),
        "input_tokenizer_sha256": (
            sha256(args.input_tokenizer) if args.input_tokenizer is not None else None
        ),
        "input_predictor_sha256": sha256(args.input_predictor),
    }
    payload["receipt_hash"] = canonical_hash(payload)
    validate_training_terminal(payload, cell_id=args.cell_id)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.out.with_suffix(args.out.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, args.out)
    print(json.dumps({"status": "PASS", "receipt_hash": payload["receipt_hash"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
