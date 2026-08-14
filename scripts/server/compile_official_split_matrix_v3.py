#!/usr/bin/env python3
"""Compile the exact four-cell v3 matrix from immutable terminal evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from scripts.research.official_split_v3 import (
    ACTIVE_CELLS,
    MATRIX_SCHEMA,
    RETIREMENT_SCHEMA,
    TRAINED_CELLS,
    UPSTREAM_COMMIT,
    canonical_hash,
    validate_matrix,
    validate_retirement_receipt,
    validate_split_receipt,
    validate_training_audit,
    validate_training_terminal,
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
        raise RuntimeError(f"immutable output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def compile_matrix(
    root: Path,
    source: dict[str, Any],
    split_path: Path,
    dataset_manifest_path: Path,
    dataset_admission_path: Path,
    weights_receipt_path: Path,
    training_audit_path: Path,
) -> dict[str, Any]:
    split = validate_split_receipt(read_object(split_path))
    audit = validate_training_audit(read_object(training_audit_path))
    if (
        audit["dataset_manifest_sha256"] != sha256(dataset_manifest_path)
        or audit["dataset_admission_sha256"] != sha256(dataset_admission_path)
        or audit["official_weights_receipt_sha256"] != sha256(weights_receipt_path)
    ):
        raise RuntimeError("training audit does not bind matrix inputs")
    rows = source.get("cells")
    if not isinstance(rows, list):
        raise RuntimeError("matrix source must contain cells")
    cells: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            raise RuntimeError("matrix cells must be objects")
        row = dict(raw)
        cell_id = str(row.get("id"))
        if cell_id in TRAINED_CELLS:
            tokenizer_path = (root / str(row.pop("tokenizer_terminal_path"))).resolve()
            predictor_path = (root / str(row.pop("predictor_terminal_path"))).resolve()
            if root not in tokenizer_path.parents or root not in predictor_path.parents:
                raise RuntimeError("terminal paths must remain under root")
            tokenizer = validate_training_terminal(read_object(tokenizer_path), cell_id=cell_id)
            predictor = validate_training_terminal(read_object(predictor_path), cell_id=cell_id)
            if tokenizer["stage"] != "tokenizer" or predictor["stage"] != "predictor":
                raise RuntimeError("terminal stage order mismatch")
            if predictor.get("input_tokenizer_sha256") != tokenizer["checkpoint_sha256"]:
                raise RuntimeError("predictor did not consume the sealed tokenizer")
            if tokenizer["data_manifest_sha256"] != predictor["data_manifest_sha256"]:
                raise RuntimeError("training stages used different datasets")
            for stage, path in (("tokenizer", tokenizer_path), ("predictor", predictor_path)):
                audit_stage = audit["stages"][f"{cell_id}:{stage}"]
                if audit_stage["terminal_sha256"] != sha256(path):
                    raise RuntimeError("matrix terminal differs from training audit")
            row.update(
                {
                    "tokenizer_sha256": tokenizer["checkpoint_sha256"],
                    "predictor_sha256": predictor["checkpoint_sha256"],
                    "config_sha256": predictor["config_sha256"],
                    "tokenizer_path": str(
                        Path(str(tokenizer["checkpoint_path"])).resolve().parent
                    ),
                    "predictor_path": str(
                        Path(str(predictor["checkpoint_path"])).resolve().parent
                    ),
                    "tokenizer_terminal_sha256": sha256(tokenizer_path),
                    "predictor_terminal_sha256": sha256(predictor_path),
                    "predictor_input_tokenizer_sha256": predictor[
                        "input_tokenizer_sha256"
                    ],
                }
            )
        cells.append(row)
    payload: dict[str, Any] = {
        "schema_version": MATRIX_SCHEMA,
        "status": "PASS",
        "run_id": source.get("run_id"),
        "upstream_commit": UPSTREAM_COMMIT,
        "split_receipt_sha256": sha256(split_path),
        "split_receipt_hash": split["receipt_hash"],
        "dataset_manifest_sha256": sha256(dataset_manifest_path),
        "dataset_admission_sha256": sha256(dataset_admission_path),
        "official_weights_receipt_sha256": sha256(weights_receipt_path),
        "training_audit_sha256": sha256(training_audit_path),
        "cells": sorted(cells, key=lambda item: str(item["id"])),
    }
    payload["receipt_hash"] = canonical_hash(payload)
    validate_matrix(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--split-receipt", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--dataset-admission", type=Path, required=True)
    parser.add_argument("--weights-receipt", type=Path, required=True)
    parser.add_argument("--training-audit", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--retirement-source", type=Path, required=True)
    parser.add_argument("--retirement-out", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    matrix = compile_matrix(
        root,
        read_object(args.source),
        args.split_receipt.resolve(),
        args.dataset_manifest.resolve(),
        args.dataset_admission.resolve(),
        args.weights_receipt.resolve(),
        args.training_audit.resolve(),
    )
    if tuple(row["id"] for row in matrix["cells"]) != ACTIVE_CELLS:
        raise RuntimeError("compiler did not produce exact active matrix")
    retirement = read_object(args.retirement_source)
    retirement["schema_version"] = RETIREMENT_SCHEMA
    retirement["status"] = "PASS"
    retirement.pop("receipt_hash", None)
    retirement["receipt_hash"] = canonical_hash(retirement)
    validate_retirement_receipt(retirement)
    atomic_new(args.out, matrix)
    atomic_new(args.retirement_out, retirement)
    print(json.dumps({"status": "PASS", "active_cells": list(ACTIVE_CELLS)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
