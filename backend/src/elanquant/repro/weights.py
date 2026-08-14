from __future__ import annotations

import argparse
import importlib
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from elanquant.repro.common import atomic_json, canonical_sha256, sha256_file

MODEL_SPECS = {
    "tokenizer": {
        "repo": "NeoQuasar/Kronos-Tokenizer-base",
        "revision": "0e0117387f39004a9016484a186a908917e22426",
        "model_sha256": "59d85f6af76a2c3b8240ea06cb21db4213b4eeca053f246b23e29cf832fc6bee",
    },
    "small": {
        "repo": "NeoQuasar/Kronos-small",
        "revision": "901c26c1332695a2a8f243eb2f37243a37bea320",
        "model_sha256": "b082dfcbd8e8c142a725c8bbb99781802f38fec81210e13479effb32b3c3e020",
    },
    "base": {
        "repo": "NeoQuasar/Kronos-base",
        "revision": "2b554741eca47781b64468546e77fef3e85130e6",
        "model_sha256": "abff193acab6db1a0368e9773e75799d11403b6d054ee6d5f0a11aeabc5f4b83",
    },
}
ALLOWED_FILES = {".gitattributes", "README.md", "config.json", "model.safetensors"}


def _tree_identity(root: Path) -> tuple[list[dict[str, Any]], str]:
    files: list[dict[str, Any]] = []
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] == ".cache":
            continue
        if relative.as_posix() not in ALLOWED_FILES:
            raise RuntimeError(f"unexpected weight file: {relative.as_posix()}")
        files.append(
            {"bytes": path.stat().st_size, "path": relative.as_posix(), "sha256": sha256_file(path)}
        )
    return files, canonical_sha256(files)


def verify_weights(root: Path, release: str) -> dict[str, Any]:
    selected = ("tokenizer", release)
    models: dict[str, Any] = {}
    for key in selected:
        spec = MODEL_SPECS[key]
        destination = root / str(spec["repo"]).split("/", 1)[1]
        weight = destination / "model.safetensors"
        if not weight.is_file() or sha256_file(weight) != spec["model_sha256"]:
            raise RuntimeError(f"weight is missing or corrupt: {key}")
        files, tree_sha = _tree_identity(destination)
        models[key] = {
            **spec,
            "directory": destination.name,
            "files": files,
            "tree_sha256": tree_sha,
        }
    payload = {
        "schema_version": "elanquant_official_weights_v2",
        "status": "PASS",
        "release": release,
        "license": "MIT (upstream model card; verify source terms before redistribution)",
        "models": models,
    }
    payload["receipt_hash"] = canonical_sha256(payload)
    return payload


def fetch_weights(root: Path, release: str, *, offline: bool) -> dict[str, Any]:
    try:
        snapshot_download = importlib.import_module("huggingface_hub").snapshot_download
    except ImportError as error:  # pragma: no cover - package smoke
        raise RuntimeError("weight fetch requires elanquant[repro]") from error
    root.mkdir(parents=True, exist_ok=True)
    for key in ("tokenizer", release):
        spec = MODEL_SPECS[key]
        destination = root / str(spec["repo"]).split("/", 1)[1]
        snapshot_download(
            repo_id=str(spec["repo"]),
            revision=str(spec["revision"]),
            local_dir=destination,
            local_files_only=offline,
            allow_patterns=sorted(ALLOWED_FILES),
        )
    receipt = verify_weights(root, release)
    receipt["generated_at"] = datetime.now(UTC).isoformat()
    receipt["offline"] = offline
    # generated_at/offline are operational fields and intentionally outside canonical identity.
    atomic_json(root / f"receipt-{release}.json", receipt)
    os.chmod(root / f"receipt-{release}.json", 0o600)
    return receipt


def add_weights_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser("weights", help="Fetch or verify pinned Kronos weights")
    actions = parser.add_subparsers(dest="weights_action", required=True)
    for action in ("fetch", "verify"):
        command = actions.add_parser(action)
        command.add_argument("--root", type=Path, required=True)
        command.add_argument("--release", choices=("small", "base"), default="small")
        command.add_argument("--offline", action="store_true")
        command.set_defaults(handler=run_weights_command)


def run_weights_command(args: argparse.Namespace) -> int:
    receipt = (
        fetch_weights(args.root, args.release, offline=args.offline)
        if args.weights_action == "fetch"
        else verify_weights(args.root, args.release)
    )
    print(receipt["receipt_hash"])
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_weights_parser(subparsers)
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
