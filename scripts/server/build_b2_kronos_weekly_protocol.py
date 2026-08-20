#!/usr/bin/env python3
"""Seal the shared B2/Kronos strict-weekly evaluation protocol.

This is intentionally a receipt builder, not an inference runner.  Real
server jobs must first materialise each family evidence receipt from its own
input window (B2 currently: prior 80 sessions), then invoke this builder.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from elanquant.contracts.official_demo import canonical_hash, sha256_file
from elanquant.contracts.unified_comparison import (
    ARTIFACT_ROOT,
    MODEL_FAMILIES,
    PROTOCOL_SCHEMA,
    validate_model_evidence,
    validate_protocol,
)


def _relative(root: Path, path: Path) -> str:
    resolved = path.resolve()
    if root not in resolved.parents:
        raise RuntimeError("input receipt must be under --root")
    return resolved.relative_to(root).as_posix()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--b2-evidence", type=Path, required=True)
    parser.add_argument("--kronos-evidence", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.out.resolve()
    if (
        output.exists()
        or root not in output.parents
        or not output.relative_to(root).as_posix().startswith(f"{ARTIFACT_ROOT}/")
    ):
        raise RuntimeError("output must be a new file under the sealed artifact root")
    evidence_paths = (args.b2_evidence.resolve(), args.kronos_evidence.resolve())
    evidence = [
        validate_model_evidence(json.loads(path.read_text(encoding="utf-8")))
        for path in evidence_paths
    ]
    if tuple(item["model_family_id"] for item in evidence) != MODEL_FAMILIES:
        raise RuntimeError("evidence order must be B2 followed by Kronos Base")
    common = evidence[0]["common_protocol"]
    if any(item["common_protocol"] != common for item in evidence[1:]):
        raise RuntimeError("strict-weekly anchors, labels or execution are not identical")
    payload = {
        "schema_version": PROTOCOL_SCHEMA,
        "status": "PASS",
        "id": "itransformer-b2-vs-kronos-base-weekly-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "model_families": list(MODEL_FAMILIES),
        "portfolios": ["top1", "top3", "top50"],
        "common_protocol": common,
        "online_paper_equivalent": False,
        "promotion_eligible": False,
        "source_evidence": [
            {
                "model_family_id": item["model_family_id"],
                "receipt_path": _relative(root, path),
                "receipt_sha256": sha256_file(path),
                "common_protocol": item["common_protocol"],
            }
            for item, path in zip(evidence, evidence_paths, strict=True)
        ],
    }
    payload["receipt_hash"] = canonical_hash(payload)
    validate_protocol(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    print(json.dumps({"status": "PASS", "out": str(output), "families": list(MODEL_FAMILIES)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
