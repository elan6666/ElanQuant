#!/usr/bin/env python3
"""Seal the already-decided protocol before running the 2026 viewed test track."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from elanquant.contracts.official_demo import (
    ANALYSIS_LOCK_SCHEMA,
    EXPECTED_EXECUTION,
    EXPECTED_STRATEGY,
    FINAL_TEST_STRATEGY_ID,
    MODEL_CELL,
    PRIMARY_SIGNAL,
    canonical_hash,
    sha256_file,
    validate_analysis_lock,
    validate_backtest_receipt,
)


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validation-backtest-receipt", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    output = args.out.resolve()
    if output.exists():
        raise RuntimeError("analysis lock is immutable")
    validate_backtest_receipt(
        json.loads(args.validation_backtest_receipt.read_text(encoding="utf-8"))
    )
    matrix = json.loads(args.matrix.read_text(encoding="utf-8"))
    cells = [cell for cell in matrix.get("cells", []) if cell.get("id") == MODEL_CELL]
    if matrix.get("status") != "PASS" or len(cells) != 1:
        raise RuntimeError("sealed Small official-ft matrix cell is absent")
    cell = cells[0]
    manifest = json.loads(args.dataset_manifest.read_text(encoding="utf-8"))
    dataset_relative = args.dataset.resolve().relative_to(
        args.dataset_manifest.resolve().parent
    ).as_posix()
    dataset_entry = manifest.get("files", {}).get(dataset_relative)
    if (
        manifest.get("status") != "PASS"
        or not isinstance(dataset_entry, dict)
        or dataset_entry.get("sha256") != sha256_file(args.dataset)
    ):
        raise RuntimeError("final-test dataset is not bound by the admitted manifest")
    payload: dict[str, Any] = {
        "schema_version": ANALYSIS_LOCK_SCHEMA,
        "status": "PASS",
        "id": FINAL_TEST_STRATEGY_ID,
        "locked_at": datetime.now(UTC).isoformat(),
        "model_cell_id": MODEL_CELL,
        "primary_signal": PRIMARY_SIGNAL,
        "evaluation_split": "test_viewed_2026",
        "test_data_access": "VIEWED",
        "used_for_selection": False,
        "viewed_before_track_freeze": True,
        "validation_backtest_receipt_sha256": sha256_file(
            args.validation_backtest_receipt
        ),
        "training_matrix_sha256": sha256_file(args.matrix),
        "tokenizer_sha256": cell["tokenizer_sha256"],
        "predictor_sha256": cell["predictor_sha256"],
        "model_config_sha256": cell["config_sha256"],
        "dataset_manifest_sha256": sha256_file(args.dataset_manifest),
        "dataset_file_sha256": sha256_file(args.dataset),
        "maturity_rule": (
            "t_known_universe_with_complete_prior_90_global_sessions_and_"
            "ten_future_global_exchange_timestamps_without_future_symbol_filter"
        ),
        "expected_support": {
            "rows": 39072,
            "cross_sections": 137,
            "signal_start": "2026-01-05",
            "signal_end": "2026-07-29",
            "target_end": "2026-08-12",
            "candidate_min": 278,
            "candidate_median": 283.0,
            "candidate_max": 297,
            "anchor_set_sha256": (
                "35d43fd0e4cf216753ee8fa95c78474a18b37492e5f3bb0b190c6526f300d7a7"
            ),
        },
        "inference": {
            "T": 0.6,
            "top_p": 0.9,
            "top_k": 0,
            "sample_count": 5,
            "batch_size": 1000,
            "effective_series_batch": 200,
            "seed": 100,
        },
        "strategy": dict(EXPECTED_STRATEGY),
        "execution": dict(EXPECTED_EXECUTION),
    }
    payload["receipt_hash"] = canonical_hash(payload)
    validate_analysis_lock(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(payload, output)
    print(json.dumps({"status": "PASS", "out": str(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
