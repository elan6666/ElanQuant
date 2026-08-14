from __future__ import annotations

import argparse
import json
import math
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from elanquant.cli.doctor import doctor_report
from elanquant.contracts.portable_runtime import canonical_hash
from elanquant.execution import (
    CapabilityUnavailableError,
    load_execution_profile,
    require_capability,
)
from elanquant.settings import Settings

SYNTHETIC_CLOSES = (100.0, 101.5, 100.75, 103.0, 104.25, 103.5, 105.0)


def synthetic_smoke_report(settings: Settings) -> dict[str, object]:
    doctor = doctor_report(settings, scope="capability")
    execution = doctor["execution"]
    assert isinstance(execution, dict)
    require_capability(execution)
    changes = [
        (current / previous) - 1.0
        for previous, current in zip(
            SYNTHETIC_CLOSES[:-1], SYNTHETIC_CLOSES[1:], strict=True
        )
    ]
    score = math.fsum(changes) / len(changes)
    fixture = {
        "schema_version": "elanquant_synthetic_fixture_v1",
        "sessions": len(SYNTHETIC_CLOSES),
        "close_sha256": canonical_hash(SYNTHETIC_CLOSES),
    }
    report: dict[str, object] = {
        "schema_version": "elanquant_portable_synthetic_smoke_v1",
        "status": "PASS",
        "scope": "PORTABLE_RUNTIME_SYNTHETIC_ONLY_NOT_KRONOS_MODEL_INFERENCE",
        "execution_receipt_hash": execution["receipt_hash"],
        "fixture": fixture,
        "result": {"mean_close_change": score, "finite": math.isfinite(score)},
    }
    report["receipt_hash"] = canonical_hash(report)
    return report


def add_smoke_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--fixture", choices=("synthetic",), default="synthetic")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--profile")
    parser.add_argument("--release", choices=("small", "base"))
    parser.add_argument("--device", choices=("cpu", "mps", "cuda"))


def run_smoke_command(args: argparse.Namespace) -> int:
    settings = Settings.load(args.config)
    if args.profile is not None:
        profile = load_execution_profile(args.profile, settings.execution_profiles_root)
        settings = replace(
            settings,
            execution_profile=args.profile,
            execution_device=args.device or profile.default_device,
        )
    if args.release is not None:
        settings = replace(settings, model_release=args.release)
    if args.device is not None and args.profile is None:
        settings = replace(settings, execution_device=args.device)
    try:
        report = synthetic_smoke_report(settings)
    except CapabilityUnavailableError as error:
        unavailable: dict[str, object] = {
            "schema_version": "elanquant_portable_synthetic_smoke_v1",
            "status": "UNAVAILABLE",
            "scope": "PORTABLE_RUNTIME_SYNTHETIC_ONLY_NOT_KRONOS_MODEL_INFERENCE",
            "reason": str(error),
        }
        unavailable["receipt_hash"] = canonical_hash(unavailable)
        print(json.dumps(unavailable, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the ElanQuant synthetic runtime smoke")
    add_smoke_arguments(parser)
    raise SystemExit(run_smoke_command(parser.parse_args(argv)))


if __name__ == "__main__":
    main()
