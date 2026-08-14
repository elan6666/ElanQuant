#!/usr/bin/env python3
"""Seal independently reconstructed official-training fidelity evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from scripts.research.official_split_v3 import (
    TRAINED_CELLS,
    TRAINING_AUDIT_SCHEMA,
    UPSTREAM_COMMIT,
    canonical_hash,
    validate_dataset_admission,
    validate_dataset_manifest,
    validate_training_audit,
    validate_training_terminal,
)

EPOCH = re.compile(r"--- Epoch ([0-9]+)/30 Summary ---")
FINISHED = "Training finished. Summary file saved."


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


def model_entry(receipt: dict[str, Any], name: str, root: Path) -> tuple[Path, str]:
    models = receipt.get("models")
    if not isinstance(models, dict) or not isinstance(models.get(name), dict):
        raise RuntimeError(f"official model absent from receipt: {name}")
    row = models[name]
    path = Path(str(row["path"])).resolve()
    claimed = str(row["model_sha256"])
    if root not in path.parents or sha256(path / "model.safetensors") != claimed:
        raise RuntimeError(f"official model bytes differ: {name}")
    return path, claimed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--weights-receipt", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--dataset-admission", type=Path, required=True)
    parser.add_argument("--training-runner", type=Path, required=True)
    parser.add_argument("--terminal-builder", type=Path, required=True)
    parser.add_argument("--small-run-id", required=True)
    parser.add_argument("--base-run-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root, workspace = args.root.resolve(), args.workspace.resolve()
    if args.out.exists() or root not in args.out.resolve().parents:
        raise RuntimeError("training audit output must be a new path under root")
    receipt_path = workspace.parent / "receipt.json"
    workspace_receipt = read_object(receipt_path)
    if (
        workspace_receipt.get("status") != "PASS"
        or workspace_receipt.get("upstream_commit") != UPSTREAM_COMMIT
    ):
        raise RuntimeError("workspace receipt is not admitted")
    upstream = root / "upstream" / "Kronos"
    head = subprocess.check_output(["git", "-C", upstream, "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(
        ["git", "-C", upstream, "status", "--porcelain"], text=True
    ).strip()
    if head != UPSTREAM_COMMIT or dirty:
        raise RuntimeError("pinned upstream is not clean")
    core = {
        "runtime_config_sha256": (
            workspace / "finetune/config.py",
            "runtime_config_sha256",
        ),
        "dataset_adapter_sha256": (
            workspace / "finetune/dataset.py",
            "dataset_sha256",
        ),
        "ddp_runtime_patch_sha256": (
            workspace / "finetune/utils/training_utils.py",
            "ddp_runtime_patch_sha256",
        ),
    }
    for field, (path, receipt_field) in core.items():
        if sha256(path) != workspace_receipt.get(receipt_field):
            raise RuntimeError(f"workspace core differs: {field}")
    for script in ("train_tokenizer.py", "train_predictor.py"):
        if sha256(workspace / "finetune" / script) != sha256(upstream / "finetune" / script):
            raise RuntimeError(f"author training script differs: {script}")
    manifest = validate_dataset_manifest(read_object(args.dataset_manifest))
    admission = validate_dataset_admission(read_object(args.dataset_admission))
    if admission["dataset_manifest_sha256"] != sha256(args.dataset_manifest):
        raise RuntimeError("dataset admission does not bind the manifest")
    weights = read_object(args.weights_receipt)
    if weights.get("status") != "PASS":
        raise RuntimeError("official weights receipt is not PASS")
    _, official_tokenizer_sha = model_entry(
        weights, "NeoQuasar/Kronos-Tokenizer-base", root
    )
    official_predictors = {
        size: model_entry(weights, f"NeoQuasar/Kronos-{size}", root)[1]
        for size in ("small", "base")
    }
    stages: dict[str, Any] = {}
    for size, run_id in (("small", args.small_run_id), ("base", args.base_run_id)):
        cell = f"{size}-official-ft"
        if cell not in TRAINED_CELLS:
            raise RuntimeError("unexpected trained cell")
        for stage in ("tokenizer", "predictor"):
            stage_root = root / "runs/training" / run_id / stage
            terminal_path = stage_root / "terminal.json"
            terminal = validate_training_terminal(read_object(terminal_path), cell_id=cell)
            log_path = stage_root / "output.log"
            log = log_path.read_text(encoding="utf-8")
            epochs = [int(value) for value in EPOCH.findall(log)]
            if epochs != list(range(1, 31)) or log.count(FINISHED) != 1:
                raise RuntimeError(f"training log is incomplete: {cell}/{stage}")
            summary_path = (
                root
                / "models/training"
                / run_id
                / "official"
                / ("tokenizer" if stage == "tokenizer" else f"predictor-{size}")
                / "summary.json"
            )
            summary = read_object(summary_path)
            best = summary.get("final_result", {}).get("best_val_loss")
            if (
                summary.get("world_size") != 2
                or not isinstance(best, (int, float))
                or not math.isfinite(float(best))
            ):
                raise RuntimeError(f"training summary is invalid: {cell}/{stage}")
            checkpoint = Path(str(terminal["checkpoint_path"])).resolve()
            expected_checkpoint = (
                root
                / "models/training"
                / run_id
                / "official"
                / ("tokenizer" if stage == "tokenizer" else f"predictor-{size}")
                / "checkpoints/best_model/model.safetensors"
            ).resolve()
            if (
                checkpoint != expected_checkpoint
                or sha256(checkpoint) != terminal["checkpoint_sha256"]
            ):
                raise RuntimeError(f"checkpoint path/hash mismatch: {cell}/{stage}")
            if (
                terminal["data_manifest_sha256"] != sha256(args.dataset_manifest)
                or terminal["config_sha256"] != sha256(workspace / "finetune/config.py")
                or terminal["input_predictor_sha256"] != official_predictors[size]
            ):
                raise RuntimeError(f"training input mismatch: {cell}/{stage}")
            input_tokenizer = (
                official_tokenizer_sha
                if stage == "tokenizer"
                else stages[f"{cell}:tokenizer"]["checkpoint_sha256"]
            )
            if stage == "predictor" and terminal["input_tokenizer_sha256"] != input_tokenizer:
                raise RuntimeError(f"predictor tokenizer link mismatch: {cell}")
            stages[f"{cell}:{stage}"] = {
                "terminal_sha256": sha256(terminal_path),
                "log_sha256": sha256(log_path),
                "summary_sha256": sha256(summary_path),
                "checkpoint_sha256": terminal["checkpoint_sha256"],
                "input_tokenizer_sha256": input_tokenizer,
                "input_predictor_sha256": official_predictors[size],
                "epochs_observed": epochs,
                "world_size": 2,
                "finished_marker_count": 1,
                "best_validation_loss": float(best),
            }
    payload: dict[str, Any] = {
        "schema_version": TRAINING_AUDIT_SCHEMA,
        "status": "PASS",
        "upstream_commit": UPSTREAM_COMMIT,
        "workspace_receipt_sha256": sha256(receipt_path),
        "official_weights_receipt_sha256": sha256(args.weights_receipt),
        "dataset_manifest_sha256": sha256(args.dataset_manifest),
        "dataset_manifest_receipt_hash": manifest["receipt_hash"],
        "dataset_admission_sha256": sha256(args.dataset_admission),
        "dataset_admission_receipt_hash": admission["receipt_hash"],
        "training_runner_sha256": sha256(args.training_runner),
        "terminal_builder_sha256": sha256(args.terminal_builder),
        "runtime_config_sha256": sha256(workspace / "finetune/config.py"),
        "dataset_adapter_sha256": sha256(workspace / "finetune/dataset.py"),
        "train_tokenizer_sha256": sha256(workspace / "finetune/train_tokenizer.py"),
        "train_predictor_sha256": sha256(workspace / "finetune/train_predictor.py"),
        "ddp_runtime_patch_sha256": sha256(
            workspace / "finetune/utils/training_utils.py"
        ),
        "stages": stages,
    }
    payload["receipt_hash"] = canonical_hash(payload)
    validate_training_audit(payload)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.out.with_suffix(args.out.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, args.out)
    print(json.dumps({"status": "PASS", "receipt_hash": payload["receipt_hash"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
