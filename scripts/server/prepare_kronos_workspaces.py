#!/usr/bin/env python3
"""Create source-hashed official and strict training workspaces."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

DDP_BEFORE = """    dist.init_process_group(backend="nccl")
    rank = int(os.environ["RANK"])
    world_size = int(os.environ["WORLD_SIZE"])
    local_rank = int(os.environ["LOCAL_RANK"])
    torch.cuda.set_device(local_rank)
"""
DDP_AFTER = """    local_rank = int(os.environ["LOCAL_RANK"])
    torch.cuda.set_device(local_rank)
    dist.init_process_group(
        backend="nccl", device_id=torch.device(f"cuda:{local_rank}")
    )
    rank = int(os.environ["RANK"])
    world_size = int(os.environ["WORLD_SIZE"])
"""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    files = (item for item in root.rglob("*") if item.is_file() and ".git" not in item.parts)
    for path in sorted(files):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(bytes.fromhex(sha256(path)))
    return digest.hexdigest()


def patch_ddp_device_binding(workspace: Path) -> Path:
    utility = workspace / "finetune/utils/training_utils.py"
    source = utility.read_text(encoding="utf-8")
    if source.count(DDP_BEFORE) != 1:
        raise RuntimeError("pinned DDP setup block no longer matches the audited patch")
    utility.write_text(source.replace(DDP_BEFORE, DDP_AFTER), encoding="utf-8")
    return utility


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--workspace-id", required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    upstream = root / "upstream" / "Kronos"
    commit = subprocess.check_output(
        ["git", "-C", upstream, "rev-parse", "HEAD"], text=True
    ).strip()
    if commit != "67b630e67f6a18c9e9be918d9b4337c960db1e9a":
        raise RuntimeError(f"unexpected upstream commit {commit}")
    if subprocess.check_output(["git", "-C", upstream, "status", "--porcelain"], text=True).strip():
        raise RuntimeError("upstream repository is not clean")
    workspaces = root / "workspaces" / args.workspace_id
    if workspaces.exists():
        raise RuntimeError(f"immutable workspace already exists: {workspaces}")
    config = root / "source" / "scripts" / "server" / "kronos_config.py"
    strict_dataset = root / "source" / "scripts" / "server" / "strict_dataset.py"
    receipt = {
        "schema_version": "elanquant_kronos_workspaces_v2",
        "workspace_id": args.workspace_id,
        "upstream_commit": commit,
    }
    for track in ("official", "strict"):
        destination = workspaces / track
        shutil.copytree(upstream, destination, ignore=shutil.ignore_patterns(".git"))
        shutil.copy2(config, destination / "finetune" / "config.py")
        if track == "strict":
            shutil.copy2(strict_dataset, destination / "finetune" / "dataset.py")
        runtime_utility = patch_ddp_device_binding(destination)
        receipt[track] = {
            "tree_sha256": tree_hash(destination),
            "config_sha256": sha256(destination / "finetune" / "config.py"),
            "dataset_sha256": sha256(destination / "finetune" / "dataset.py"),
            "ddp_runtime_patch_sha256": sha256(runtime_utility),
            "deviation": (
                "paths/env plus DDP device-before-NCCL binding; "
                "official model/dataset behavior retained"
                if track == "official"
                else "target-bounded anchors, deterministic DDP sampling, "
                "causal adjustment, DDP device-before-NCCL binding"
            ),
        }
    receipt["status"] = "PASS"
    (workspaces / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
