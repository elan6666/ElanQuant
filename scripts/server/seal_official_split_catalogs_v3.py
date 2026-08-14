#!/usr/bin/env python3
"""Build four-cell evaluation and eight-cell historical catalogs from receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.research import official_split_v3 as contract_module
from scripts.research.official_split_v3 import (
    ACTIVE_CELLS,
    EVALUATION_SCHEMA,
    HISTORICAL_SCHEMA,
    STRATEGIES,
    canonical_hash,
    validate_analysis_lock,
    validate_backtest_receipt,
    validate_evaluation,
    validate_historical_catalog,
    validate_signal_receipt,
)


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
        raise RuntimeError(f"immutable catalog already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--analysis-lock", type=Path, required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--evaluation-out", type=Path, required=True)
    parser.add_argument("--historical-out", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    lock = validate_analysis_lock(read_object(args.analysis_lock))
    if sha256(Path(str(contract_module.__file__)).resolve()) != lock["contract_sha256"]:
        raise RuntimeError("catalog contract differs from the pre-result lock")
    lock_sha = sha256(args.analysis_lock)
    evaluation_entries: list[dict[str, Any]] = []
    historical_entries: list[dict[str, Any]] = []
    for cell in ACTIVE_CELLS:
        signal_receipt_path = args.results_root / "signals" / cell / "signal-receipt.json"
        signal_receipt = validate_signal_receipt(read_object(signal_receipt_path))
        if (
            signal_receipt["model_cell_id"] != cell
            or signal_receipt["analysis_lock_sha256"] != lock_sha
        ):
            raise RuntimeError(f"signal receipt identity mismatch: {cell}")
        signals_path = (root / str(signal_receipt["signals_path"])).resolve()
        labels_path = (root / str(signal_receipt["labels_path"])).resolve()
        if (
            root not in signals_path.parents
            or root not in labels_path.parents
            or sha256(signals_path) != signal_receipt["signals_sha256"]
            or sha256(labels_path) != signal_receipt["labels_sha256"]
        ):
            raise RuntimeError(f"signal artifacts changed: {cell}")
        evaluation_entries.append(
            {
                "model_cell_id": cell,
                "mature_targets_only": True,
                "signal_sha256": signal_receipt["signals_sha256"],
                "candidate_set_sha256": signal_receipt["candidate_set_sha256"],
                "signal_receipt_path": signal_receipt_path.resolve().relative_to(root).as_posix(),
                "signal_receipt_sha256": sha256(signal_receipt_path),
                "support": signal_receipt["support"],
                "metrics": signal_receipt["metrics"],
            }
        )
        for variant in STRATEGIES:
            backtest_path = (
                args.results_root
                / "backtests"
                / cell
                / variant
                / "backtest-receipt.json"
            )
            backtest = validate_backtest_receipt(read_object(backtest_path))
            if (
                backtest["model_cell_id"] != cell
                or backtest["strategy_variant_id"] != variant
                or backtest["analysis_lock_sha256"] != lock_sha
                or backtest["source_signal_receipt_sha256"] != sha256(signal_receipt_path)
                or backtest["source_signal_sha256"] != signal_receipt["signals_sha256"]
            ):
                raise RuntimeError(f"backtest receipt identity mismatch: {cell}/{variant}")
            for path_field, hash_field in (
                ("daily_series_path", "daily_series_sha256"),
                ("raw_report_path", "raw_report_sha256"),
                ("holdings_path", "holdings_sha256"),
            ):
                artifact = (root / str(backtest[path_field])).resolve()
                if root not in artifact.parents or sha256(artifact) != backtest[hash_field]:
                    raise RuntimeError(f"backtest artifact changed: {cell}/{variant}/{path_field}")
            historical_entries.append(
                {
                    "id": backtest["id"],
                    "model_cell_id": cell,
                    "evaluation_split": backtest["evaluation_split"],
                    "strategy_variant_id": variant,
                    "strategy": STRATEGIES[variant],
                    "sample_count": 5,
                    "test_status": "TEST_VIEWED",
                    "used_for_selection": False,
                    "promotion_eligible": False,
                    "signal_sha256": signal_receipt["signals_sha256"],
                    "holdings_sha256": backtest["holdings_sha256"],
                    "receipt_path": backtest_path.resolve().relative_to(root).as_posix(),
                    "receipt_sha256": sha256(backtest_path),
                    "support": backtest["support"],
                    "metrics": backtest["metrics"],
                    "summary": backtest["metrics"][backtest["primary_signal"]],
                }
            )
    generated_at = datetime.now(UTC).isoformat()
    evaluation: dict[str, Any] = {
        "schema_version": EVALUATION_SCHEMA,
        "status": "PASS",
        "analysis_lock_sha256": lock_sha,
        "test_status": "TEST_VIEWED",
        "used_for_selection": False,
        "promotion_eligible": False,
        "generated_at": generated_at,
        "entries": evaluation_entries,
    }
    evaluation["receipt_hash"] = canonical_hash(evaluation)
    validate_evaluation(evaluation)
    historical: dict[str, Any] = {
        "schema_version": HISTORICAL_SCHEMA,
        "status": "PASS",
        "generated_at": generated_at,
        "artifact_root": root.as_posix(),
        "analysis_lock_sha256": lock_sha,
        "provider_receipt_sha256": lock["provider_receipt_sha256"],
        "entries": historical_entries,
    }
    historical["receipt_hash"] = canonical_hash(historical)
    validate_historical_catalog(historical)
    atomic_new(args.evaluation_out, evaluation)
    atomic_new(args.historical_out, historical)
    print(json.dumps({"status": "PASS", "evaluation_cells": 4, "historical_entries": 8}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
