from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from elanquant.cli import doctor, smoke
from elanquant.contracts.portable_runtime import validate_execution_receipt
from elanquant.execution import (
    CapabilityUnavailableError,
    SystemCapabilities,
    build_execution_receipt,
    load_execution_profile,
    probe_python_runtime,
    require_capability,
    sanitized_subprocess_environment,
)
from fastapi.testclient import TestClient

from elanquant.api.app import create_app
from elanquant.orchestration.jobs import JobStore
from elanquant.orchestration.worker import Worker
from elanquant.settings import PROJECT_ROOT, Settings
from elanquant.storage.database import Database

PROFILES_ROOT = PROJECT_ROOT / "configs/execution"


def test_research_runtime_probe_uses_configured_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    python = tmp_path / "research-python"
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        captured["command"] = command
        captured["environment"] = kwargs["env"]
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "operating_system": "Linux",
                    "architecture": "x86_64",
                    "python_version": "3.12.3",
                    "torch_version": "2.13.0+cu130",
                    "cpu_available": True,
                    "mps_available": False,
                    "cuda_available": True,
                    "device_name": "NVIDIA RTX 5090",
                }
            ),
            stderr="",
        )

    monkeypatch.setattr("elanquant.execution.subprocess.run", fake_run)
    result = probe_python_runtime(python, "cuda")

    assert captured["command"][0] == str(python)  # type: ignore[index]
    assert result.cuda_available is True
    assert result.torch_version == "2.13.0+cu130"


def active_settings(tmp_path: Path, **overrides: object) -> Settings:
    settings = Settings(
        database_path=tmp_path / "elanquant.sqlite3",
        artifact_root=tmp_path / "runs",
        frontend_dist=tmp_path / "missing-dist",
        execution_profiles_root=PROFILES_ROOT,
        execution_profile="local-apple-silicon",
        model_release="small",
        execution_device="cpu",
    )
    return replace(settings, **overrides)


def capabilities(
    *,
    operating_system: str = "Darwin",
    architecture: str = "arm64",
    cpu: bool = True,
    mps: bool = False,
    cuda: bool = False,
) -> SystemCapabilities:
    return SystemCapabilities(
        operating_system=operating_system,
        architecture=architecture,
        python_version="3.11.9",
        torch_version="2.5.1",
        cpu_available=cpu,
        mps_available=mps,
        cuda_available=cuda,
        device_name="test-device",
    )


def test_profiles_are_canonical_and_base_is_explicit_research_only() -> None:
    local = load_execution_profile("local-apple-silicon", PROFILES_ROOT)
    remote = load_execution_profile("remote-linux-nvidia", PROFILES_ROOT)
    legacy = load_execution_profile("legacy-yilangliu", PROFILES_ROOT)

    assert local.default_release == "small"
    assert local.default_device == "mps"
    assert local.is_research_only("base") is True
    assert remote.allowed_devices == ("cuda",)
    assert remote.is_research_only("base") is True
    assert legacy.visibility == "private"
    assert load_execution_profile("local-apple-silicon", Path("/missing/profiles")) == local
    with pytest.raises(ValueError, match="device"):
        remote.validate_request("small", "cpu")


def test_public_default_is_local_and_units_are_portable_templates(
    tmp_path: Path,
) -> None:
    settings = Settings(
        database_path=tmp_path / "db.sqlite3",
        artifact_root=tmp_path / "runs",
        frontend_dist=tmp_path / "dist",
    )
    assert settings.execution_profile == "local-apple-silicon"
    assert settings.model_release == "small"
    assert settings.execution_device == "mps"
    for unit_name in ("elanquant-api.service.in", "elanquant-worker.service.in"):
        unit = (PROJECT_ROOT / "deploy/systemd" / unit_name).read_text(encoding="utf-8")
        assert "@ELANQUANT_EXECUTION_PROFILE@" in unit
        assert "@ELANQUANT_ENV_FILE@" in unit
        assert "/data/yilangliu" not in unit
    legacy = (PROJECT_ROOT / "deploy/profiles/legacy-yilangliu.env.in").read_text(
        encoding="utf-8"
    )
    assert "ELANQUANT_EXECUTION_PROFILE=legacy-yilangliu" in legacy
    assert "ELANQUANT_MODEL_RELEASE=small" in legacy


def test_execution_receipt_never_silently_falls_back_and_detects_tampering() -> None:
    local = load_execution_profile("local-apple-silicon", PROFILES_ROOT)
    remote = load_execution_profile("remote-linux-nvidia", PROFILES_ROOT)
    unavailable = build_execution_receipt(
        local, "small", "mps", capabilities(cpu=True, mps=False), checked_at="fixed"
    )
    assert unavailable["status"] == "UNAVAILABLE"
    assert unavailable["resolved_device"] is None
    with pytest.raises(CapabilityUnavailableError):
        require_capability(unavailable)

    passing = build_execution_receipt(
        local, "small", "cpu", capabilities(), checked_at="fixed"
    )
    base = build_execution_receipt(
        local, "base", "cpu", capabilities(), checked_at="fixed"
    )
    assert passing["status"] == "PASS"
    assert passing["resolved_device"] == "cpu"
    assert passing["execution_identity_sha256"] == base["execution_identity_sha256"]
    assert passing["receipt_hash"] != base["receipt_hash"]
    assert build_execution_receipt(
        local,
        "small",
        "mps",
        capabilities(mps=True),
        checked_at="fixed",
    )["status"] == "PASS"
    assert build_execution_receipt(
        remote,
        "small",
        "cuda",
        capabilities(
            operating_system="Linux", architecture="x86_64", cpu=True, cuda=True
        ),
        checked_at="fixed",
    )["status"] == "PASS"
    passing["capabilities"]["device_name"] = "tampered"
    with pytest.raises(ValueError, match="identity hash"):
        validate_execution_receipt(passing)


def test_research_environment_is_allowlisted_and_rejects_secret_injection() -> None:
    environment = sanitized_subprocess_environment(
        {
            "PATH": "/usr/bin",
            "HOME": "/safe/home",
            "TUSHARE_TOKEN": "secret",
            "AWS_SECRET_ACCESS_KEY": "secret",
            "HTTP_PROXY": "http://credential@example.invalid",
        },
        runtime_values={"ELANQUANT_EXECUTION_PROFILE": "local-apple-silicon"},
    )
    assert environment == {
        "PATH": "/usr/bin",
        "HOME": "/safe/home",
        "ELANQUANT_EXECUTION_PROFILE": "local-apple-silicon",
    }
    with pytest.raises(ValueError, match="not allowlisted"):
        sanitized_subprocess_environment(runtime_values={"TUSHARE_TOKEN": "secret"})


def test_job_identity_is_idempotent_and_retry_inherits_profile(tmp_path: Path) -> None:
    database = Database(tmp_path / "elanquant.sqlite3")
    database.initialize()
    jobs = JobStore(database)
    first, created = jobs.submit_update_infer(
        "2026-08-12",
        execution_profile="local-apple-silicon",
        model_release="base",
        requested_device="cpu",
    )
    duplicate, duplicate_created = jobs.submit_update_infer(
        "2026-08-12",
        execution_profile="local-apple-silicon",
        model_release="base",
        requested_device="cpu",
    )
    different, different_created = jobs.submit_update_infer(
        "2026-08-12",
        execution_profile="local-apple-silicon",
        model_release="small",
        requested_device="cpu",
    )
    assert created is True
    assert duplicate_created is False
    assert duplicate["id"] == first["id"]
    assert different_created is True
    assert different["id"] != first["id"]

    jobs.fail(str(first["id"]), "TEST", "retry")
    retried = jobs.retry(str(first["id"]))
    assert retried["execution_profile"] == "local-apple-silicon"
    assert retried["model_release"] == "base"
    assert retried["requested_device"] == "cpu"
    assert retried["execution_receipt"] is None


def test_legacy_database_migration_assigns_private_profile(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE jobs (
                id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE,
                job_type TEXT NOT NULL, requested_session TEXT NOT NULL,
                resolved_session TEXT, status TEXT NOT NULL, stage TEXT NOT NULL,
                progress REAL NOT NULL DEFAULT 0, message TEXT NOT NULL DEFAULT '',
                attempt INTEGER NOT NULL DEFAULT 1, parent_job_id TEXT,
                created_at TEXT NOT NULL, started_at TEXT, heartbeat_at TEXT,
                finished_at TEXT, error_code TEXT, error_summary TEXT, run_id TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO jobs(id,idempotency_key,job_type,requested_session,status,stage,created_at)
            VALUES ('legacy','legacy-key','UPDATE_INFER','2026-08-12','FAILED','FAILED','now')
            """
        )
    database = Database(path)
    database.initialize()
    migrated = JobStore(database).get("legacy")
    assert migrated["execution_profile"] == "legacy-yilangliu"
    assert migrated["model_release"] == "small"
    assert migrated["requested_device"] == "cuda"


def test_real_worker_gates_before_claim_and_sanitizes_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = active_settings(tmp_path, pipeline_mode="real")
    database = Database(settings.database_path)
    database.initialize()
    jobs = JobStore(database)
    submitted, _ = jobs.submit_update_infer(
        "2026-08-12",
        execution_profile=settings.execution_profile,
        model_release=settings.model_release,
        requested_device=settings.execution_device,
    )
    monkeypatch.setenv("TUSHARE_TOKEN", "must-not-reach-subprocess")

    def fake_pipeline(database, settings, job, advance):  # type: ignore[no-untyped-def]
        assert "TUSHARE_TOKEN" not in os.environ
        assert os.environ["ELANQUANT_EXECUTION_PROFILE"] == "local-apple-silicon"
        advance("SYNTHETIC", 0.9, "synthetic", "2026-08-12")
        return "synthetic-run"

    monkeypatch.setattr("elanquant.orchestration.worker.run_real_pipeline", fake_pipeline)
    worker = Worker(settings, capability_probe=lambda _: capabilities())
    assert worker.run_once() is True
    assert os.environ["TUSHARE_TOKEN"] == "must-not-reach-subprocess"
    completed = jobs.get(str(submitted["id"]))
    assert completed["status"] == "SUCCEEDED"
    assert completed["execution_receipt"]["status"] == "PASS"


def test_unavailable_worker_job_fails_without_being_claimed(tmp_path: Path) -> None:
    settings = active_settings(tmp_path, pipeline_mode="real", execution_device="mps")
    database = Database(settings.database_path)
    database.initialize()
    jobs = JobStore(database)
    submitted, _ = jobs.submit_update_infer(
        "2026-08-12",
        execution_profile=settings.execution_profile,
        model_release=settings.model_release,
        requested_device=settings.execution_device,
    )
    worker = Worker(settings, capability_probe=lambda _: capabilities(mps=False))
    assert worker.run_once() is True
    failed = jobs.get(str(submitted["id"]))
    assert failed["status"] == "FAILED"
    assert failed["started_at"] is None
    assert failed["error_code"] == "CAPABILITY_UNAVAILABLE"
    assert failed["execution_receipt"]["status"] == "UNAVAILABLE"


def test_base_capability_runs_research_only_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = active_settings(tmp_path, pipeline_mode="real", model_release="base")
    database = Database(settings.database_path)
    database.initialize()
    jobs = JobStore(database)
    submitted, _ = jobs.submit_update_infer(
        "2026-08-12",
        execution_profile=settings.execution_profile,
        model_release=settings.model_release,
        requested_device=settings.execution_device,
    )
    def fake_pipeline(database, active_settings, job, advance):  # type: ignore[no-untyped-def]
        assert job["model_release"] == "base"
        assert active_settings.model_release == "base"
        advance("RESEARCH_ONLY", 0.9, "research only", "2026-08-12")
        return "base-research-run"

    monkeypatch.setattr("elanquant.orchestration.worker.run_real_pipeline", fake_pipeline)
    worker = Worker(settings, capability_probe=lambda _: capabilities())
    assert worker.run_once() is True
    completed = jobs.get(str(submitted["id"]))
    assert completed["status"] == "SUCCEEDED"
    assert completed["run_id"] == "base-research-run"
    assert completed["execution_receipt"]["status"] == "PASS"
    assert completed["execution_receipt"]["research_only"] is True


def test_api_freezes_active_profile_and_exposes_additive_status(tmp_path: Path) -> None:
    settings = active_settings(tmp_path)
    client = TestClient(create_app(settings))
    status = client.get("/api/v1/system/status").json()
    assert status["execution_profile"] == "local-apple-silicon"
    assert status["model_release"] == "small"
    assert status["execution_device"] == "cpu"
    assert status["available_releases"] == ["small", "base"]

    mismatch = client.post(
        "/api/v1/jobs/update-infer",
        json={"target_session": "2026-08-12", "execution_profile": "remote-linux-nvidia"},
    )
    assert mismatch.status_code == 409
    submitted = client.post(
        "/api/v1/jobs/update-infer",
        json={
            "target_session": "2026-08-12",
            "execution_profile": "local-apple-silicon",
            "model_release": "base",
        },
    )
    assert submitted.status_code == 202
    assert submitted.json()["job"]["model_release"] == "base"


def test_doctor_is_read_only_and_smoke_is_explicitly_not_model_inference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = active_settings(tmp_path)
    monkeypatch.setattr(doctor, "probe_system_capabilities", lambda _: capabilities())
    report = doctor.doctor_report(settings)
    assert report["status"] == "INCOMPLETE"
    assert report["capability_status"] == "PASS"
    assert report["scope"] == "service"
    assert not all(report["readiness"].values())
    assert report["check_only"] is True
    assert not settings.database_path.exists()
    assert "token" not in json.dumps(report).lower()

    capability = doctor.doctor_report(settings, scope="capability")
    assert capability["status"] == "PASS"

    smoke_report = smoke.synthetic_smoke_report(settings)
    assert smoke_report["status"] == "PASS"
    assert smoke_report["scope"] == "PORTABLE_RUNTIME_SYNTHETIC_ONLY_NOT_KRONOS_MODEL_INFERENCE"
