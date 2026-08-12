#!/usr/bin/env python3
"""Derive the sealed Small three-cell matrix from immutable receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

UPSTREAM_COMMIT = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"
OFFICIAL_REPOS = {
    "tokenizer": "NeoQuasar/Kronos-Tokenizer-base",
    "small": "NeoQuasar/Kronos-small",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(payload: Any) -> str:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def load_pass(path: Path, schema: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != schema or payload.get("status") != "PASS":
        raise RuntimeError(f"receipt is not terminal PASS: {path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    run_root = root / "runs/training" / args.run_id
    save_root = root / "models/training" / args.run_id
    official = load_pass(root / "models/pretrained/receipt.json", "elanquant_official_weights_v1")
    data_manifest_path = root / "data/processed/extended-v2/manifest.json"
    data_manifest = load_pass(data_manifest_path, "elanquant_extended_dataset_v1")
    data_sha = sha256(data_manifest_path)
    admission_path = root / "runs/admission/extended-v2.json"
    admission = load_pass(admission_path, "elanquant_dataset_admission_v1")
    if admission.get("processed_manifest_sha256") != data_sha:
        raise RuntimeError("dataset admission receipt does not bind the training manifest")
    raw_manifest_path = root / "data/raw/extended-csi300-v1/manifest.json"
    if admission.get("raw_manifest_sha256") != sha256(raw_manifest_path):
        raise RuntimeError("dataset admission receipt does not bind the immutable raw manifest")
    split_sha = canonical_hash(data_manifest["split_contract"])
    official_config_sha = sha256(root / "source/configs/models/official.yaml")

    terminals: dict[tuple[str, str, str], dict[str, Any]] = {}
    for track in ("official", "strict"):
        for stage, size in (("tokenizer", "small"), ("predictor", "small")):
            path = run_root / f"{track}-{stage}-{size}" / "terminal.json"
            terminal = load_pass(path, "elanquant_training_terminal_v2")
            if not terminal.get("checkpoint_created_by_this_stage"):
                raise RuntimeError(f"stage did not create a fresh checkpoint: {path}")
            if terminal.get("data_manifest_sha256") != data_sha:
                raise RuntimeError(f"stage data identity mismatch: {path}")
            checkpoint = Path(str(terminal["checkpoint_path"]))
            if (
                save_root not in checkpoint.parents
                or sha256(checkpoint) != terminal["checkpoint_sha256"]
            ):
                raise RuntimeError(f"stage checkpoint identity mismatch: {path}")
            terminals[(track, stage, size)] = terminal

    weight_models = official.get("models", {})
    pretrained_hashes = {
        size: str(weight_models[repo]["model_sha256"]) for size, repo in OFFICIAL_REPOS.items()
    }
    cells: list[dict[str, Any]] = []
    for size in ("small",):
        cells.append(
            {
                "id": f"{size}-zero-shot",
                "size": size,
                "track": "zero_shot",
                "tokenizer_path": str(root / "models/pretrained/Kronos-Tokenizer-base"),
                "tokenizer_sha256": pretrained_hashes["tokenizer"],
                "predictor_path": str(root / f"models/pretrained/Kronos-{size}"),
                "predictor_sha256": pretrained_hashes[size],
                "config_sha256": official_config_sha,
                "trained_components": [],
            }
        )
        for track, cell_track in (("official", "official_style"), ("strict", "strict_pit")):
            tokenizer = terminals[(track, "tokenizer", "small")]
            predictor = terminals[(track, "predictor", size)]
            if predictor["input_tokenizer_sha256"] != tokenizer["checkpoint_sha256"]:
                raise RuntimeError(f"{track}/{size} predictor did not reuse the sealed tokenizer")
            if predictor["input_predictor_sha256"] != pretrained_hashes[size]:
                raise RuntimeError(
                    f"{track}/{size} predictor input is not the pinned official weight"
                )
            cells.append(
                {
                    "id": f"{size}-{'official-ft' if track == 'official' else 'strict-pit'}",
                    "size": size,
                    "track": cell_track,
                    "tokenizer_path": str(Path(tokenizer["checkpoint_path"]).parent),
                    "tokenizer_sha256": tokenizer["checkpoint_sha256"],
                    "predictor_path": str(Path(predictor["checkpoint_path"]).parent),
                    "predictor_sha256": predictor["checkpoint_sha256"],
                    "config_sha256": predictor["runtime_config_sha256"],
                    "trained_components": ["tokenizer", "predictor"],
                    "tokenizer_terminal_sha256": sha256(
                        run_root / f"{track}-tokenizer-small/terminal.json"
                    ),
                    "predictor_terminal_sha256": sha256(
                        run_root / f"{track}-predictor-{size}/terminal.json"
                    ),
                }
            )

    payload = {
        "schema_version": "elanquant_training_matrix_v2",
        "status": "PASS",
        "run_id": args.run_id,
        "upstream_commit": UPSTREAM_COMMIT,
        "data_manifest_sha256": data_sha,
        "dataset_admission_receipt_sha256": sha256(admission_path),
        "split_contract_sha256": split_sha,
        "official_weights_receipt_sha256": sha256(root / "models/pretrained/receipt.json"),
        "cells": sorted(cells, key=lambda cell: cell["id"]),
    }
    payload["receipt_hash"] = canonical_hash(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, args.output)
    print(json.dumps({"status": "PASS", "receipt_hash": payload["receipt_hash"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
