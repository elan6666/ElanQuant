#!/usr/bin/env python3
"""Atomically publish one sealed training/evaluation pair to the app worker."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
from pathlib import Path
from typing import Any

EXPECTED_MODEL_IDS = {
    "small-zero-shot",
    "small-official-ft",
    "small-strict-pit",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"receipt is not an object: {path}")
    return value


def canonical_hash(payload: Any) -> str:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def finite_number(value: Any, identity: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"{identity} is not numeric")
    number = float(value)
    if not math.isfinite(number):
        raise RuntimeError(f"{identity} is not finite")
    return number


def validate_release_pair(
    matrix_payload: dict[str, Any],
    evaluation_payload: dict[str, Any],
    matrix_sha256: str,
) -> None:
    if matrix_payload.get("schema_version") != "elanquant_training_matrix_v2":
        raise RuntimeError("matrix schema is not supported")
    if matrix_payload.get("status") != "PASS":
        raise RuntimeError("matrix is not terminal PASS")
    matrix_content = dict(matrix_payload)
    claimed_receipt_hash = matrix_content.pop("receipt_hash", None)
    if canonical_hash(matrix_content) != claimed_receipt_hash:
        raise RuntimeError("matrix receipt hash is invalid")
    cells = matrix_payload.get("cells")
    if not isinstance(cells, list):
        raise RuntimeError("matrix cells are missing")
    cell_ids = [cell.get("id") for cell in cells if isinstance(cell, dict)]
    if len(cell_ids) != 3 or set(cell_ids) != EXPECTED_MODEL_IDS:
        raise RuntimeError("matrix is not the exact Small three-cell experiment")

    if evaluation_payload.get("schema_version") != "elanquant_kronos_inference_v1":
        raise RuntimeError("evaluation schema is not supported")
    if evaluation_payload.get("status") != "PASS":
        raise RuntimeError("evaluation is not terminal PASS")
    if evaluation_payload.get("evaluation_mode") != "FORMAL":
        raise RuntimeError("only FORMAL evaluation may be released")
    if evaluation_payload.get("training_matrix_receipt_sha256") != matrix_sha256:
        raise RuntimeError("evaluation was not generated from this matrix")
    models = evaluation_payload.get("models")
    if not isinstance(models, dict) or set(models) != EXPECTED_MODEL_IDS:
        raise RuntimeError("evaluation is not the exact Small three-cell experiment")
    for model_id in sorted(EXPECTED_MODEL_IDS):
        model = models[model_id]
        if not isinstance(model, dict):
            raise RuntimeError(f"evaluation model is invalid: {model_id}")
        metrics = model.get("metrics")
        validation = metrics.get("validation_2025") if isinstance(metrics, dict) else None
        if not isinstance(validation, dict):
            raise RuntimeError(f"formal validation metrics are missing: {model_id}")
        for metric in ("rank_ic", "ic", "top10_mean_return"):
            finite_number(validation.get(metric), f"{model_id}.validation_2025.{metric}")
        if (
            int(finite_number(validation.get("rows"), f"{model_id}.validation_2025.rows"))
            <= 0
        ):
            raise RuntimeError(f"formal validation has no rows: {model_id}")
        if int(
            finite_number(
                validation.get("cross_sections"),
                f"{model_id}.validation_2025.cross_sections",
            )
        ) <= 0:
            raise RuntimeError(f"formal validation has no cross-sections: {model_id}")
    support = evaluation_payload.get("evaluation_support")
    validation_support = support.get("validation_2025") if isinstance(support, dict) else None
    if not isinstance(validation_support, dict):
        raise RuntimeError("formal validation support receipt is missing")
    eligible = finite_number(validation_support.get("eligible_rows"), "eligible_rows")
    evaluated = finite_number(validation_support.get("evaluated_rows"), "evaluated_rows")
    if eligible <= 0 or evaluated <= 0 or evaluated > eligible:
        raise RuntimeError("formal validation coverage is invalid")
    scores = evaluation_payload.get("scores")
    if not isinstance(scores, list) or len(scores) < 250:
        raise RuntimeError("release ranking has insufficient CSI300 coverage")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    matrix = args.matrix.resolve()
    evaluation = args.evaluation.resolve()
    matrix_payload = load(matrix)
    evaluation_payload = load(evaluation)
    matrix_sha256 = sha256(matrix)
    validate_release_pair(matrix_payload, evaluation_payload, matrix_sha256)

    releases = root / "releases"
    destination = releases / args.release_id
    if destination.exists():
        raise RuntimeError(f"immutable release already exists: {destination}")
    temporary = releases / f".{args.release_id}.tmp-{os.getpid()}"
    temporary.mkdir(parents=True)
    shutil.copy2(matrix, temporary / "training-matrix.json")
    shutil.copy2(evaluation, temporary / "formal-evaluation.json")
    manifest = {
        "schema_version": "elanquant_release_v1",
        "status": "PASS",
        "release_id": args.release_id,
        "training_matrix_sha256": sha256(temporary / "training-matrix.json"),
        "formal_evaluation_sha256": sha256(temporary / "formal-evaluation.json"),
    }
    (temporary / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, destination)
    next_link = releases / f".current.tmp-{os.getpid()}"
    next_link.symlink_to(destination.name, target_is_directory=True)
    os.replace(next_link, releases / "current")
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
