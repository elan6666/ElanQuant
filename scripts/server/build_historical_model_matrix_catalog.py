#!/usr/bin/env python3
"""Publish the exact 6 model x 2 split x 2 strategy historical catalog."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from elanquant.contracts.historical_matrix import (
    CATALOG_SCHEMA,
    MODEL_CELLS,
    SPLITS,
    VARIANTS,
    backtest_id,
    validate_backtest_receipt,
    validate_catalog,
)
from elanquant.contracts.official_demo import PRIMARY_SIGNAL, canonical_hash, sha256_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.out.resolve()
    if output.exists() or root not in output.parents:
        raise RuntimeError("matrix catalog must be a new file under root")
    entries: list[dict[str, Any]] = []
    for model in MODEL_CELLS:
        for split in SPLITS:
            for variant in VARIANTS:
                path = args.results_root / model / split / variant / "backtest-receipt.json"
                receipt = validate_backtest_receipt(
                    json.loads(path.read_text(encoding="utf-8"))
                )
                expected_id = backtest_id(model, split, variant)
                if receipt["id"] != expected_id:
                    raise RuntimeError(f"matrix result identity mismatch: {expected_id}")
                summary = {
                    key: receipt["metrics"][PRIMARY_SIGNAL][key]
                    for key in (
                        "total_return_with_cost",
                        "benchmark_return",
                        "excess_return_with_cost",
                        "annualized_return_with_cost",
                        "information_ratio_with_cost",
                        "max_drawdown_with_cost",
                    )
                }
                entries.append(
                    {
                        "id": expected_id,
                        "state": "passed",
                        "model_cell_id": model,
                        "model_size": MODEL_CELLS[model][0],
                        "model_track": MODEL_CELLS[model][1],
                        "evaluation_split": split,
                        "strategy_variant_id": variant,
                        "primary_signal": PRIMARY_SIGNAL,
                        "strategy": receipt["strategy"],
                        "result_role": receipt["result_role"],
                        "test_data_access": receipt["test_data_access"],
                        "selection_eligible": False,
                        "used_for_selection": False,
                        "promotion_eligible": False,
                        "online_paper_equivalent": False,
                        "receipt_path": path.resolve().relative_to(root).as_posix(),
                        "receipt_sha256": sha256_file(path),
                        "source": {
                            "signal_receipt_sha256": receipt[
                                "source_signal_receipt_sha256"
                            ],
                            "provider_receipt_sha256": receipt[
                                "source_provider_receipt_sha256"
                            ],
                        },
                        "support": receipt["support"],
                        "holdings": {
                            "artifact_path": receipt["artifacts"]["holdings"]["path"],
                            "artifact_sha256": receipt["artifacts"]["holdings"]["sha256"],
                        },
                        "summary": summary,
                    }
                )
    payload: dict[str, Any] = {
        "schema_version": CATALOG_SCHEMA,
        "status": "PASS",
        "generated_at": datetime.now(UTC).isoformat(),
        "comparison_group_id": "six-model-top50-top3-v1",
        "entries": entries,
    }
    payload["receipt_hash"] = canonical_hash(payload)
    validate_catalog(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, output)
    print(json.dumps({"status": "PASS", "entries": len(entries), "out": str(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
