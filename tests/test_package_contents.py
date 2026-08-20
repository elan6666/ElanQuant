from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_wheel_declares_public_reproduction_resources() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    wheel = project["tool"]["hatch"]["build"]["targets"]["wheel"]
    force = wheel["force-include"]
    assert force == {
        "README.md": "elanquant/resources/README.md",
        "THIRD_PARTY_NOTICES.md": "elanquant/resources/THIRD_PARTY_NOTICES.md",
        "assets": "elanquant/resources/assets",
        "configs": "elanquant/resources/configs",
        "docs": "elanquant/resources/docs",
        "examples": "elanquant/resources/examples",
    }
    assert (ROOT / "examples/data/synthetic_daily.csv").is_file()


def test_inference_extra_declares_the_upstream_runtime() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = "\n".join(project["project"]["optional-dependencies"]["inference"])
    for required in ("torch", "einops", "safetensors", "huggingface-hub", "pandas"):
        assert required in dependencies
