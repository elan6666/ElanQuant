from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from elanquant.contracts.portable_runtime import canonical_hash
from elanquant.execution import (
    build_execution_receipt,
    load_execution_profile,
    probe_system_capabilities,
)
from elanquant.settings import Settings


def doctor_report(settings: Settings, *, scope: str = "service") -> dict[str, object]:
    if scope not in {"capability", "service"}:
        raise ValueError("doctor scope must be capability or service")
    profile = load_execution_profile(
        settings.execution_profile, settings.execution_profiles_root
    )
    profile.validate_request(settings.model_release, settings.execution_device)
    receipt = build_execution_receipt(
        profile,
        settings.model_release,
        settings.execution_device,
        probe_system_capabilities(settings.execution_device),
        inference_batch_size=settings.inference_batch_size,
    )
    checks = {
        "database_parent_exists": settings.database_path.parent.is_dir(),
        "artifact_parent_exists": settings.artifact_root.parent.is_dir(),
        "frontend_dist_exists": settings.frontend_dist.is_dir(),
        "research_python_exists": settings.research_python.is_file(),
        "matrix_receipt_exists": settings.matrix_receipt.is_file(),
        "evaluation_receipt_exists": settings.evaluation_receipt.is_file(),
    }
    readiness_complete = all(checks.values())
    status = str(receipt["status"])
    if status == "PASS" and scope == "service" and not readiness_complete:
        status = "INCOMPLETE"
    report: dict[str, object] = {
        "schema_version": "elanquant_doctor_report_v1",
        "status": status,
        "scope": scope,
        "capability_status": receipt["status"],
        "check_only": True,
        "profile_visibility": profile.visibility,
        "execution": receipt,
        "readiness": checks,
    }
    report["report_hash"] = canonical_hash(report)
    return report


def _settings_from_args(args: argparse.Namespace) -> Settings:
    settings = Settings.load(args.config)
    profile_id = args.profile or settings.execution_profile
    profile = load_execution_profile(profile_id, settings.execution_profiles_root)
    model_release = args.release or settings.model_release
    device = args.device or profile.default_device
    profile.validate_request(model_release, device)
    return replace(
        settings,
        execution_profile=profile_id,
        model_release=model_release,
        execution_device=device,
    )


def add_doctor_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--check-only", action="store_true", help="Retained explicit no-write flag")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--profile")
    parser.add_argument("--release", choices=("small", "base"))
    parser.add_argument("--device", choices=("cpu", "mps", "cuda"))
    parser.add_argument("--scope", choices=("capability", "service"), default="service")


def run_doctor_command(args: argparse.Namespace) -> int:
    report = doctor_report(_settings_from_args(args), scope=args.scope)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if report["status"] == "PASS":
        return 0
    return 2 if report["status"] == "INCOMPLETE" else 1


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Read-only ElanQuant runtime doctor")
    add_doctor_arguments(parser)
    raise SystemExit(run_doctor_command(parser.parse_args(argv)))


if __name__ == "__main__":
    main()
