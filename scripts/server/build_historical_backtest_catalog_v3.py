#!/usr/bin/env python3
"""Build the exact 2x2 Top50-versus-Top3 historical catalog."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from elanquant.contracts.historical_variants import (
    COMPARISON_GROUP_ID,
    EXECUTION_DOMAIN,
    HISTORICAL_CATALOG_SCHEMA_V2,
    SPLITS,
    TOP3_OPENED_ID_V2,
    TOP3_PUBLIC_VARIANT,
    TOP3_STRATEGY_ROLE,
    TOP3_VALIDATION_ID_V2,
    TOP50_PUBLIC_VARIANT,
    TOP50_STRATEGY_ROLE,
    validate_any_backtest_receipt,
    validate_historical_catalog,
    validate_holdings_receipt,
)

from elanquant.contracts.official_demo import (
    FINAL_TEST_STRATEGY_ID,
    PRIMARY_SIGNAL,
    STRATEGY_ID,
    canonical_hash,
    sha256_file,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--backtest-receipt", type=Path, action="append", required=True)
    parser.add_argument("--holdings-receipt", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.out.resolve()
    if output.exists() or root not in output.parents:
        raise RuntimeError("v3 catalog must be a new file under root")
    loaded: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in args.backtest_receipt:
        receipt = validate_any_backtest_receipt(json.loads(path.read_text(encoding="utf-8")))
        if receipt["id"] in loaded:
            raise RuntimeError(f"duplicate receipt: {receipt['id']}")
        loaded[receipt["id"]] = (path.resolve(), receipt)
    expected = {
        STRATEGY_ID,
        FINAL_TEST_STRATEGY_ID,
        TOP3_VALIDATION_ID_V2,
        TOP3_OPENED_ID_V2,
    }
    if set(loaded) != expected:
        raise RuntimeError("v3 catalog requires the exact four receipts")
    holdings_loaded: dict[str, tuple[Path, dict[str, Any]]] = {}
    for holdings_path in args.holdings_receipt:
        holdings_receipt = validate_holdings_receipt(
            json.loads(holdings_path.read_text(encoding="utf-8"))
        )
        backtest_id = str(holdings_receipt["backtest_id"])
        if backtest_id in holdings_loaded:
            raise RuntimeError(f"duplicate holdings receipt: {backtest_id}")
        holdings_loaded[backtest_id] = (holdings_path.resolve(), holdings_receipt)
    if set(holdings_loaded) != expected:
        raise RuntimeError("v3 catalog requires exact holdings for all four receipts")
    entries: list[dict[str, Any]] = []
    for identifier in (
        STRATEGY_ID,
        TOP3_VALIDATION_ID_V2,
        FINAL_TEST_STRATEGY_ID,
        TOP3_OPENED_ID_V2,
    ):
        path, receipt = loaded[identifier]
        is_top3 = identifier in {TOP3_VALIDATION_ID_V2, TOP3_OPENED_ID_V2}
        split = (
            "validation_2025"
            if identifier in {STRATEGY_ID, TOP3_VALIDATION_ID_V2}
            else "test_viewed_2026"
        )
        source_id = SPLITS[split]["source_track_id"] if is_top3 else None
        if is_top3:
            source_path, source_receipt = loaded[str(source_id)]
            source = {
                "backtest_receipt_sha256": sha256_file(source_path),
                "signal_receipt_sha256": source_receipt["signal_receipt_sha256"],
                "provider_receipt_sha256": source_receipt["provider_receipt_sha256"],
            }
            strategy_variant_id = TOP3_PUBLIC_VARIANT
            strategy_role = TOP3_STRATEGY_ROLE
            result_role = SPLITS[split]["result_role"]
            used_for_selection = False
        else:
            source = {
                "backtest_receipt_sha256": sha256_file(path),
                "signal_receipt_sha256": receipt["signal_receipt_sha256"],
                "provider_receipt_sha256": receipt["provider_receipt_sha256"],
            }
            strategy_variant_id = TOP50_PUBLIC_VARIANT
            strategy_role = TOP50_STRATEGY_ROLE
            result_role = (
                "TRAINING_VALIDATION_CHECKPOINT_SELECTION"
                if split == "validation_2025"
                else "CORRECTED_OPENED_OOS_DIAGNOSTIC"
            )
            used_for_selection = split == "validation_2025"
        holdings_path, holdings_receipt = holdings_loaded[identifier]
        if holdings_receipt["backtest_id"] != identifier or holdings_receipt[
            "backtest_receipt_sha256"
        ] != sha256_file(path):
            raise RuntimeError("holdings sidecar differs from its backtest receipt")
        entries.append(
            {
                "id": identifier,
                "state": "passed",
                "model_cell_id": receipt["model_cell_id"],
                "primary_signal": PRIMARY_SIGNAL,
                "strategy_variant_id": strategy_variant_id,
                "strategy_role": strategy_role,
                "comparison_group_id": COMPARISON_GROUP_ID,
                "evaluation_split": split,
                "result_role": result_role,
                "used_for_selection": used_for_selection,
                "test_data_access": SPLITS[split]["test_data_access"],
                "source_backtest_id": source_id,
                "execution_domain": EXECUTION_DOMAIN,
                "online_paper_equivalent": False,
                "promotion_eligible": False,
                "selection_eligible": bool(receipt["selection_eligible"]),
                "strategy": receipt["strategy"],
                "receipt_path": path.relative_to(root).as_posix(),
                "receipt_sha256": sha256_file(path),
                "summary": receipt["metrics"][PRIMARY_SIGNAL],
                "source": source,
                "holdings": {
                    "receipt_path": holdings_path.relative_to(root).as_posix(),
                    "receipt_sha256": sha256_file(holdings_path),
                },
            }
        )
    payload: dict[str, Any] = {
        "schema_version": HISTORICAL_CATALOG_SCHEMA_V2,
        "status": "PASS",
        "generated_at": datetime.now(UTC).isoformat(),
        "comparison_group_id": COMPARISON_GROUP_ID,
        "entries": entries,
    }
    payload["receipt_hash"] = canonical_hash(payload)
    validate_historical_catalog(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, output)
    print(json.dumps({"status": "PASS", "entries": 4, "out": str(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
