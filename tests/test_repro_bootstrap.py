from __future__ import annotations

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
