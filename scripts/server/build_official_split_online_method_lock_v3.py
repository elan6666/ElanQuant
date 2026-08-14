#!/usr/bin/env python3
"""Freeze the online v3 method before any viewed-result artifact exists."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.research import online_release_v3 as contract_module
from scripts.research.official_split_v3 import validate_matrix
from scripts.research.online_release_v3 import (
    METHOD_LOCK_SCHEMA,
    ONLINE_SAMPLING,
    ONLINE_SIGNAL,
    PRIMARY_MODELS,
    canonical_hash,
    validate_method_lock,
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--online-runner", type=Path, required=True)
    parser.add_argument("--viewed-results-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.out.resolve()
    matrix_path = args.matrix.resolve()
    runner_path = args.online_runner.resolve()
    viewed_root = args.viewed_results_root.resolve()
    if output.exists() or root not in output.parents:
        raise RuntimeError("online method lock must be a new file under root")
    if root not in matrix_path.parents or root not in runner_path.parents:
        raise RuntimeError("online method inputs must remain under root")
    if viewed_root.exists():
        raise RuntimeError("viewed results already exist; online method lock refused")
    validate_matrix(read_object(matrix_path))
    payload: dict[str, Any] = {
        "schema_version": METHOD_LOCK_SCHEMA,
        "status": "PASS",
        "locked_at": datetime.now(UTC).isoformat(),
        "training_matrix_sha256": sha256(matrix_path),
        "online_runner_sha256": sha256(runner_path),
        "online_contract_sha256": sha256(Path(str(contract_module.__file__)).resolve()),
        "primary_models": PRIMARY_MODELS,
        "selection_basis": "PREDECLARED_OFFICIAL_FT_METHOD_IDENTITY",
        "test_metrics_used_for_selection": False,
        "viewed_results_root": viewed_root.relative_to(root).as_posix(),
        "viewed_results_present_at_lock": False,
        "online_signal": ONLINE_SIGNAL,
        "online_sampling": ONLINE_SAMPLING,
    }
    payload["receipt_hash"] = canonical_hash(payload)
    validate_method_lock(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    print(json.dumps({"status": "PASS", "receipt_hash": payload["receipt_hash"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
