#!/usr/bin/env python3
"""Build the six-cell B2/Kronos strict-weekly comparison catalog.

Run only after server-side inference and Top1/Top3/Top50 backtests wrote
sealed result receipts.  The command never runs models or makes paper orders.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from elanquant.contracts.unified_comparison import (
    ARTIFACT_ROOT,
    CATALOG_SCHEMA,
    MODEL_FAMILIES,
    PORTFOLIOS,
    result_id,
    validate_catalog,
    validate_protocol,
    validate_result_receipt,
)

from elanquant.contracts.official_demo import canonical_hash, sha256_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.out.resolve()
    if (
        output.exists()
        or root not in output.parents
        or not output.relative_to(root).as_posix().startswith(f"{ARTIFACT_ROOT}/")
    ):
        raise RuntimeError("output must be a new file under the sealed artifact root")
    protocol = args.protocol.resolve()
    if root not in protocol.parents:
        raise RuntimeError("protocol must be under --root")
    validate_protocol(json.loads(protocol.read_text(encoding="utf-8")))
    entries = []
    for family in MODEL_FAMILIES:
        for portfolio in PORTFOLIOS:
            path = args.results_root / family / portfolio / "result-receipt.json"
            receipt = validate_result_receipt(json.loads(path.read_text(encoding="utf-8")))
            if receipt["id"] != result_id(family, portfolio):
                raise RuntimeError("result receipt identity mismatch")
            resolved = path.resolve()
            if root not in resolved.parents:
                raise RuntimeError("result receipt must be under --root")
            entries.append(
                {
                    "id": receipt["id"],
                    "model_family_id": family,
                    "portfolio_id": portfolio,
                    "receipt_path": resolved.relative_to(root).as_posix(),
                    "receipt_sha256": sha256_file(resolved),
                    "online_paper_equivalent": False,
                    "promotion_eligible": False,
                }
            )
    payload = {
        "schema_version": CATALOG_SCHEMA,
        "status": "PASS",
        "generated_at": datetime.now(UTC).isoformat(),
        "protocol_id": "itransformer-b2-vs-kronos-base-weekly-v1",
        "protocol_path": protocol.relative_to(root).as_posix(),
        "protocol_receipt_sha256": sha256_file(protocol),
        "entries": entries,
    }
    payload["receipt_hash"] = canonical_hash(payload)
    validate_catalog(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    print(json.dumps({"status": "PASS", "entries": len(entries), "out": str(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
