#!/usr/bin/env python3
"""Create the single immutable author-style workspace used by official-split v3."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

PINNED_COMMIT = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"

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
    files = (item for item in root.rglob("*") if item.is_file())
    for path in sorted(files):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(bytes.fromhex(sha256(path)))
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--workspace-id", required=True)
    args = parser.parse_args()

    root = args.root.resolve()
    upstream = root / "upstream" / "Kronos"
    commit = subprocess.check_output(
        ["git", "-C", upstream, "rev-parse", "HEAD"], text=True
    ).strip()
    if commit != PINNED_COMMIT:
        raise RuntimeError(f"unexpected upstream commit {commit}")
    dirty = subprocess.check_output(
        ["git", "-C", upstream, "status", "--porcelain"], text=True
    ).strip()
    if dirty:
        raise RuntimeError("pinned upstream repository is not clean")

    workspace_root = root / "workspaces" / args.workspace_id
    if workspace_root.exists():
        raise RuntimeError(f"immutable workspace already exists: {workspace_root}")
    destination = workspace_root / "official"
    shutil.copytree(upstream, destination, ignore=shutil.ignore_patterns(".git"))

    config_source = (
        root / "source" / "scripts" / "server" / "kronos_config_official_split_v3.py"
    )
    runtime_config = destination / "finetune" / "config.py"
    shutil.copy2(config_source, runtime_config)

    dataset_source = (
        root / "source" / "scripts" / "server" / "official_split_dataset_adapter_v3.py"
    )
    runtime_dataset = destination / "finetune" / "dataset.py"
    shutil.copy2(dataset_source, runtime_dataset)

    runtime_utility = destination / "finetune" / "utils" / "training_utils.py"
    source = runtime_utility.read_text(encoding="utf-8")
    if source.count(DDP_BEFORE) != 1:
        raise RuntimeError("pinned DDP setup block no longer matches reviewed patch")
    runtime_utility.write_text(source.replace(DDP_BEFORE, DDP_AFTER), encoding="utf-8")

    receipt = {
        "schema_version": "elanquant_kronos_official_split_workspace_v3",
        "status": "PASS",
        "workspace_id": args.workspace_id,
        "upstream_commit": commit,
        "workspace_tree_sha256": tree_hash(destination),
        "config_source_sha256": sha256(config_source),
        "runtime_config_sha256": sha256(runtime_config),
        "dataset_source_sha256": sha256(dataset_source),
        "dataset_sha256": sha256(runtime_dataset),
        "ddp_runtime_patch_sha256": sha256(runtime_utility),
        "deviations": [
            "filesystem paths are supplied by ElanQuant environment variables",
            "LOCAL_RANK is bound before NCCL initialization for RTX 5090 DDP",
            "sample index enumeration is supplied by a sealed causal global-calendar artifact",
        ],
    }
    if receipt["config_source_sha256"] != receipt["runtime_config_sha256"]:
        raise RuntimeError("runtime config copy does not match reviewed source")
    receipt_path = workspace_root / "receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
