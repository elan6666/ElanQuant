from __future__ import annotations

import argparse
import json
import platform
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from elanquant.repro.common import atomic_json, canonical_sha256
from elanquant.repro.weights import fetch_weights

PUBLIC_PROFILES = ("local-apple-silicon", "remote-linux-nvidia")


def bootstrap_plan(profile: str, release: str) -> dict[str, Any]:
    incompatible = (
        profile == "local-apple-silicon" and platform.system() != "Darwin"
    ) or (
        profile == "remote-linux-nvidia" and platform.system() != "Linux"
    )
    compatibility = "UNAVAILABLE_ON_THIS_HOST" if incompatible else "PREFLIGHT_REQUIRED"
    return {
        "schema_version": "elanquant_bootstrap_plan_v1",
        "profile": profile,
        "release": release,
        "compatibility": compatibility,
        "scope": "WEIGHTS_ONLY_NO_MODEL_INFERENCE",
        "actions": [
            "verify_profile_operating_system",
            "fetch_and_verify_official_weights",
            "write_partial_bootstrap_receipt",
        ],
        "deferred_requirements": [
            "install_inference_runtime",
            "checkout_pinned_kronos_source",
            "import_user_owned_data",
            "run_zero_shot_or_configure_service",
        ],
        "training_supported": profile == "remote-linux-nvidia",
    }


def add_bootstrap_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser("bootstrap", help="Prepare a portable ElanQuant profile")
    parser.add_argument("--profile", choices=PUBLIC_PROFILES, required=True)
    parser.add_argument("--release", choices=("small", "base"), default="small")
    parser.add_argument("--root", type=Path, default=Path(".elanquant"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.set_defaults(handler=run_bootstrap_command)


def run_bootstrap_command(args: argparse.Namespace) -> int:
    plan = bootstrap_plan(args.profile, args.release)
    if args.dry_run:
        plan["plan_hash"] = canonical_sha256(plan)
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if plan["compatibility"] == "UNAVAILABLE_ON_THIS_HOST":
        raise RuntimeError(f"profile {args.profile} is not compatible with this host")
    weights = fetch_weights(root / "weights", args.release, offline=args.offline)
    receipt = {
        **plan,
        "status": "PARTIAL_READY",
        "weights_receipt_hash": weights["receipt_hash"],
        "next_required_stage": "doctor_and_data",
    }
    receipt["receipt_hash"] = canonical_sha256(receipt)
    atomic_json(root / "bootstrap-receipt.json", receipt)
    print(receipt["receipt_hash"])
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_bootstrap_parser(subparsers)
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
