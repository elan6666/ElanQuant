from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from scripts.server.build_research_catalog import (
    ALLOWED_COMPATIBILITY_DIFFERENCES,
    BASE_COMPATIBLE_SOURCE_REVISION,
    COMPATIBILITY_SCHEMA,
    COMPATIBLE_SOURCE_PATH,
    EVALUATION_PROTOCOL,
    EXPECTED_SOURCE_DIFF_SHA256,
    SMALL_COMPATIBLE_SOURCE_REVISION,
    atomic_write,
    canonical_hash,
    read_json,
    sha256,
)


def git_blob(repo: Path, revision: str, source_path: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), "show", f"{revision}:{source_path}"],
        check=True,
        capture_output=True,
    )
    return completed.stdout


def config_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--small-evaluation", type=Path, required=True)
    parser.add_argument("--base-evaluation", type=Path, required=True)
    parser.add_argument("--small-source-revision", required=True)
    parser.add_argument("--base-source-revision", required=True)
    parser.add_argument("--source-path", default="scripts/server/evaluate_and_infer.py")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if (
        args.small_source_revision != SMALL_COMPATIBLE_SOURCE_REVISION
        or args.base_source_revision != BASE_COMPATIBLE_SOURCE_REVISION
        or args.source_path != COMPATIBLE_SOURCE_PATH
    ):
        raise RuntimeError("evaluation compatibility revisions are not the reviewed pair")
    small = read_json(args.small_evaluation)
    base = read_json(args.base_evaluation)
    for name, receipt in (("small", small), ("base", base)):
        if (
            receipt.get("status") != "PASS"
            or receipt.get("evaluation_mode") != "FORMAL"
            or receipt.get("test_status") != "TEST_VIEWED"
        ):
            raise RuntimeError(f"{name} formal evaluation is not terminal")
    for identity in (
        "upstream_commit",
        "data_manifest_sha256",
        "as_of_session",
        "sampling",
        "evaluation_support",
    ):
        if small.get(identity) != base.get(identity):
            raise RuntimeError(f"Small/Base formal evidence differs: {identity}")
    small_source = git_blob(args.repo, args.small_source_revision, args.source_path)
    base_source = git_blob(args.repo, args.base_source_revision, args.source_path)
    source_hashes = {
        "small": hashlib.sha256(small_source).hexdigest(),
        "base": hashlib.sha256(base_source).hexdigest(),
    }
    if source_hashes != {
        "small": small.get("inference_code_sha256"),
        "base": base.get("inference_code_sha256"),
    }:
        raise RuntimeError("Git source revisions do not reproduce formal code identities")
    legacy_config = {
        "batch_size": EVALUATION_PROTOCOL["evaluation_batch_size"],
        "evaluation_mode": EVALUATION_PROTOCOL["evaluation_mode"],
        "formal_sessions_per_month": EVALUATION_PROTOCOL["formal_sessions_per_month"],
        "sampling": EVALUATION_PROTOCOL["sampling"],
    }
    current_config = {
        "evaluation_batch_size": EVALUATION_PROTOCOL["evaluation_batch_size"],
        "online_batch_size": EVALUATION_PROTOCOL["online_batch_size"],
        "evaluation_mode": EVALUATION_PROTOCOL["evaluation_mode"],
        "formal_sessions_per_month": EVALUATION_PROTOCOL["formal_sessions_per_month"],
        "sampling": EVALUATION_PROTOCOL["sampling"],
    }
    if config_hash(legacy_config) != small.get("config_sha256"):
        raise RuntimeError("Small formal config is not the reviewed legacy protocol")
    if config_hash(current_config) != base.get("config_sha256"):
        raise RuntimeError("Base formal config is not the reviewed explicit protocol")
    diff = "".join(
        difflib.unified_diff(
            small_source.decode().splitlines(keepends=True),
            base_source.decode().splitlines(keepends=True),
            fromfile=f"{args.small_source_revision}:{args.source_path}",
            tofile=f"{args.base_source_revision}:{args.source_path}",
        )
    ).encode()
    source_diff_sha256 = hashlib.sha256(diff).hexdigest()
    if source_diff_sha256 != EXPECTED_SOURCE_DIFF_SHA256:
        raise RuntimeError("evaluation source diff is not the reviewed allowlist")
    payload: dict[str, object] = {
        "schema_version": COMPATIBILITY_SCHEMA,
        "status": "PASS",
        "decision": "SEMANTICALLY_COMPARABLE",
        "normalized_protocol": EVALUATION_PROTOCOL,
        "protocol_sha256": canonical_hash(EVALUATION_PROTOCOL),
        "source_identities": {
            "small": {
                "evaluation_config_sha256": small["config_sha256"],
                "inference_code_sha256": source_hashes["small"],
            },
            "base": {
                "evaluation_config_sha256": base["config_sha256"],
                "inference_code_sha256": source_hashes["base"],
            },
        },
        "source_revisions": {
            "small": args.small_source_revision,
            "base": args.base_source_revision,
        },
        "source_path": args.source_path,
        "source_diff_sha256": source_diff_sha256,
        "allowed_differences": ALLOWED_COMPATIBILITY_DIFFERENCES,
        "evaluation_receipts": {
            "small": sha256(args.small_evaluation),
            "base": sha256(args.base_evaluation),
        },
    }
    payload["receipt_hash"] = canonical_hash(payload)
    atomic_write(args.out, payload)
    print(json.dumps({"status": "PASS", "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
