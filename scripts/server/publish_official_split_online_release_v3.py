#!/usr/bin/env python3
"""Publish an immutable online-admission release from sealed v3 evidence."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any

from scripts.research import online_release_v3 as online_contract_module
from scripts.research.official_split_v3 import (
    validate_analysis_lock,
    validate_evaluation,
    validate_historical_catalog,
    validate_matrix,
)
from scripts.research.online_release_v3 import (
    RELEASE_SCHEMA,
    canonical_hash,
    validate_method_lock,
    validate_release,
)


def sha256(path: Path) -> str:
    import hashlib

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
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--analysis-lock", type=Path, required=True)
    parser.add_argument("--online-method-lock", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--historical", type=Path, required=True)
    parser.add_argument("--online-runner", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.out_dir.resolve()
    if output.exists() or root not in output.parents:
        raise RuntimeError("release output must be a new directory under root")
    matrix = validate_matrix(read_object(args.matrix))
    analysis_lock = validate_analysis_lock(read_object(args.analysis_lock))
    method_lock = validate_method_lock(read_object(args.online_method_lock))
    evaluation = validate_evaluation(read_object(args.evaluation))
    historical = validate_historical_catalog(read_object(args.historical))
    matrix_sha = sha256(args.matrix)
    if (
        analysis_lock.get("matrix_sha256") != matrix_sha
        or method_lock.get("training_matrix_sha256") != matrix_sha
        or method_lock.get("online_runner_sha256") != sha256(args.online_runner)
        or method_lock.get("online_contract_sha256")
        != sha256(Path(str(online_contract_module.__file__)).resolve())
        or method_lock.get("viewed_results_root") != analysis_lock.get("results_root")
        or evaluation.get("analysis_lock_sha256") != sha256(args.analysis_lock)
        or evaluation.get("analysis_lock_sha256") != historical.get("analysis_lock_sha256")
        or {str(row["model_cell_id"]) for row in evaluation["entries"]}
        != {str(row["id"]) for row in matrix["cells"]}
    ):
        raise RuntimeError("v3 matrix/evaluation/historical evidence is not one release")
    manifest: dict[str, Any] = {
        "schema_version": RELEASE_SCHEMA,
        "status": "PASS",
        "release_id": args.release_id,
        "training_matrix_sha256": matrix_sha,
        "analysis_lock_sha256": sha256(args.analysis_lock),
        "online_method_lock_sha256": sha256(args.online_method_lock),
        "rolling_evaluation_sha256": sha256(args.evaluation),
        "historical_catalog_sha256": sha256(args.historical),
        "online_runner_sha256": sha256(args.online_runner),
        "primary_models": method_lock["primary_models"],
        "selection_basis": method_lock["selection_basis"],
        "test_metrics_used_for_selection": method_lock["test_metrics_used_for_selection"],
        "online_signal": method_lock["online_signal"],
        "online_sampling": method_lock["online_sampling"],
    }
    manifest["receipt_hash"] = canonical_hash(manifest)
    validate_release(manifest)
    temporary = output.with_name(output.name + f".tmp-{os.getpid()}")
    temporary.mkdir(parents=True)
    shutil.copyfile(args.matrix, temporary / "training-matrix.json")
    shutil.copyfile(args.analysis_lock, temporary / "analysis-lock.json")
    shutil.copyfile(args.online_method_lock, temporary / "online-method-lock.json")
    shutil.copyfile(args.evaluation, temporary / "rolling-evaluation.json")
    shutil.copyfile(args.historical, temporary / "historical-catalog.json")
    (temporary / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for path in temporary.iterdir():
        os.chmod(path, 0o440)
    os.chmod(temporary, 0o550)
    os.replace(temporary, output)
    print(json.dumps({"status": "PASS", "release_id": args.release_id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
