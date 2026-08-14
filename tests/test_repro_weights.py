from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from elanquant.repro.weights import ALLOWED_FILES, MODEL_SPECS, verify_weights


def create_model(root: Path, key: str, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = MODEL_SPECS[key]
    destination = root / str(spec["repo"]).split("/", 1)[1]
    destination.mkdir(parents=True)
    weight = destination / "model.safetensors"
    weight.write_bytes(key.encode())
    monkeypatch.setitem(
        spec,
        "model_sha256",
        hashlib.sha256(key.encode()).hexdigest(),
    )
    (destination / "config.json").write_text("{}")


def test_verify_small_is_default_and_base_is_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_model(tmp_path, "tokenizer", monkeypatch)
    create_model(tmp_path, "small", monkeypatch)
    receipt = verify_weights(tmp_path, "small")
    assert set(receipt["models"]) == {"tokenizer", "small"}
    assert receipt["release"] == "small"


def test_verify_rejects_extra_or_corrupt_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_model(tmp_path, "tokenizer", monkeypatch)
    create_model(tmp_path, "small", monkeypatch)
    directory = tmp_path / "Kronos-small"
    (directory / "secret.txt").write_text("no")
    with pytest.raises(RuntimeError, match="unexpected"):
        verify_weights(tmp_path, "small")
    assert "secret.txt" not in ALLOWED_FILES
