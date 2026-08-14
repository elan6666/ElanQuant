from __future__ import annotations

import json
from pathlib import Path

import pytest
from elanquant.repro.bootstrap import PUBLIC_PROFILES, bootstrap_plan
from elanquant.repro.cli import main


def test_bootstrap_plan_separates_profile_from_release() -> None:
    local = bootstrap_plan("local-apple-silicon", "small")
    remote = bootstrap_plan("remote-linux-nvidia", "small")
    assert local["release"] == remote["release"] == "small"
    assert local["profile"] != remote["profile"]
    assert local["training_supported"] is False
    assert remote["training_supported"] is True
    assert PUBLIC_PROFILES == ("local-apple-silicon", "remote-linux-nvidia")


def test_cli_dry_run_does_not_create_root(tmp_path) -> None:
    root = tmp_path / "state"
    assert (
        main(
            [
                "bootstrap",
                "--profile",
                "local-apple-silicon",
                "--release",
                "small",
                "--root",
                str(root),
                "--dry-run",
            ]
        )
        == 0
    )
    assert not root.exists()


def test_cli_dry_run_prints_a_truthful_weights_only_plan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "state"
    assert (
        main(
            [
                "bootstrap",
                "--profile",
                "local-apple-silicon",
                "--release",
                "small",
                "--root",
                str(root),
                "--dry-run",
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    assert plan["scope"] == "WEIGHTS_ONLY_NO_MODEL_INFERENCE"
    assert plan["actions"] == [
        "verify_profile_operating_system",
        "fetch_and_verify_official_weights",
        "write_partial_bootstrap_receipt",
    ]
    assert "run_zero_shot_or_configure_service" in plan["deferred_requirements"]
    assert len(plan["plan_hash"]) == 64
