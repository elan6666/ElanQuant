from __future__ import annotations

import hashlib
import importlib
import json
import os
import platform
import subprocess
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from elanquant.contracts.portable_runtime import (
    DEVICES,
    FROZEN_PROFILE_PAYLOADS,
    PROFILE_IDS,
    RECEIPT_SCHEMA,
    RELEASES,
    canonical_hash,
    validate_execution_profile,
    validate_execution_receipt,
)

RESEARCH_ENV_ALLOWLIST = frozenset(
    {
        "PATH",
        "HOME",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TZ",
        "PYTHONPATH",
        "PYTHONUNBUFFERED",
        "PYTHONUTF8",
        "PYTHONHASHSEED",
        "CUDA_VISIBLE_DEVICES",
        "HF_HOME",
        "HUGGINGFACE_HUB_CACHE",
        "TRANSFORMERS_CACHE",
        "TORCH_HOME",
        "LD_LIBRARY_PATH",
        "DYLD_LIBRARY_PATH",
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
    }
)
SAFE_RUNTIME_KEYS = frozenset(
    {
        "ELANQUANT_EXECUTION_PROFILE",
        "ELANQUANT_EXECUTION_DEVICE",
        "ELANQUANT_MODEL_RELEASE",
        "ELANQUANT_INFERENCE_BATCH_SIZE",
    }
)
INFERENCE_CODE_PATH = Path(__file__).resolve().parent / "pipelines/real.py"


class CapabilityUnavailableError(RuntimeError):
    """Raised before a job claim when its frozen execution profile is unavailable."""


@dataclass(frozen=True)
class ExecutionProfile:
    id: str
    visibility: str
    operating_systems: tuple[str, ...]
    architectures: tuple[str, ...]
    allowed_devices: tuple[str, ...]
    default_device: str
    allowed_releases: tuple[str, ...]
    default_release: str
    research_only_releases: tuple[str, ...]
    require_explicit_base: bool

    @classmethod
    def from_payload(cls, payload: object) -> ExecutionProfile:
        profile = validate_execution_profile(payload)
        return cls(
            id=str(profile["id"]),
            visibility=str(profile["visibility"]),
            operating_systems=tuple(str(item) for item in profile["operating_systems"]),
            architectures=tuple(str(item) for item in profile["architectures"]),
            allowed_devices=tuple(str(item) for item in profile["allowed_devices"]),
            default_device=str(profile["default_device"]),
            allowed_releases=tuple(str(item) for item in profile["allowed_releases"]),
            default_release=str(profile["default_release"]),
            research_only_releases=tuple(
                str(item) for item in profile["research_only_releases"]
            ),
            require_explicit_base=bool(profile["require_explicit_base"]),
        )

    def validate_request(self, model_release: str, requested_device: str) -> None:
        if model_release not in RELEASES or model_release not in self.allowed_releases:
            raise ValueError(f"release {model_release!r} is not allowed by profile {self.id}")
        if requested_device not in DEVICES or requested_device not in self.allowed_devices:
            raise ValueError(f"device {requested_device!r} is not allowed by profile {self.id}")

    def is_research_only(self, model_release: str) -> bool:
        return model_release in self.research_only_releases


@dataclass(frozen=True)
class SystemCapabilities:
    operating_system: str
    architecture: str
    python_version: str
    torch_version: str | None
    cpu_available: bool
    mps_available: bool
    cuda_available: bool
    device_name: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "operating_system": self.operating_system,
            "architecture": self.architecture,
            "python_version": self.python_version,
            "torch_version": self.torch_version,
            "cpu_available": self.cpu_available,
            "mps_available": self.mps_available,
            "cuda_available": self.cuda_available,
            "device_name": self.device_name,
        }


def load_execution_profile(profile_id: str, profiles_root: Path) -> ExecutionProfile:
    if profile_id not in PROFILE_IDS:
        raise ValueError(f"unknown execution profile: {profile_id}")
    root = profiles_root.resolve()
    path = (root / f"{profile_id}.yaml").resolve()
    if path.parent != root:
        raise ValueError(f"execution profile path is unsafe: {profile_id}")
    if path.is_file():
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            raise ValueError(f"execution profile could not be read: {profile_id}") from error
    else:
        payload = FROZEN_PROFILE_PAYLOADS[profile_id]
    profile = ExecutionProfile.from_payload(payload)
    if profile.id != profile_id:
        raise ValueError("execution profile filename and identity differ")
    return profile


def probe_system_capabilities(requested_device: str) -> SystemCapabilities:
    if requested_device not in DEVICES:
        raise ValueError(f"unsupported requested device: {requested_device}")
    torch_version: str | None = None
    mps_available = False
    cuda_available = False
    device_name: str | None = platform.processor() or platform.machine()
    try:
        torch = importlib.import_module("torch")
    except (ImportError, OSError):
        torch = None
    if torch is not None:
        torch_version = str(getattr(torch, "__version__", "unknown"))
        backends = getattr(torch, "backends", None)
        mps = getattr(backends, "mps", None)
        is_mps_available = getattr(mps, "is_available", None)
        if callable(is_mps_available):
            mps_available = bool(is_mps_available())
        cuda = getattr(torch, "cuda", None)
        is_cuda_available = getattr(cuda, "is_available", None)
        if callable(is_cuda_available):
            cuda_available = bool(is_cuda_available())
        if requested_device == "cuda" and cuda_available:
            get_device_name = getattr(cuda, "get_device_name", None)
            if callable(get_device_name):
                device_name = str(get_device_name(0))
        elif requested_device == "mps" and mps_available:
            device_name = "Apple Silicon MPS"
    return SystemCapabilities(
        operating_system=platform.system(),
        architecture=platform.machine().lower(),
        python_version=platform.python_version(),
        torch_version=torch_version,
        cpu_available=torch is not None,
        mps_available=mps_available,
        cuda_available=cuda_available,
        device_name=device_name,
    )


def probe_python_runtime(python: Path, requested_device: str) -> SystemCapabilities:
    """Probe the configured research interpreter instead of the lightweight app venv."""

    if requested_device not in DEVICES:
        raise ValueError(f"unsupported requested device: {requested_device}")
    script = """
import json
import platform
import sys

try:
    import torch
except (ImportError, OSError):
    torch = None

mps_available = False
cuda_available = False
device_name = platform.processor() or platform.machine()
if torch is not None:
    mps = getattr(getattr(torch, "backends", None), "mps", None)
    is_mps_available = getattr(mps, "is_available", None)
    if callable(is_mps_available):
        mps_available = bool(is_mps_available())
    cuda = getattr(torch, "cuda", None)
    is_cuda_available = getattr(cuda, "is_available", None)
    if callable(is_cuda_available):
        cuda_available = bool(is_cuda_available())
    if sys.argv[1] == "cuda" and cuda_available:
        get_device_name = getattr(cuda, "get_device_name", None)
        if callable(get_device_name):
            device_name = str(get_device_name(0))
    elif sys.argv[1] == "mps" and mps_available:
        device_name = "Apple Silicon MPS"

print(json.dumps({
    "operating_system": platform.system(),
    "architecture": platform.machine().lower(),
    "python_version": platform.python_version(),
    "torch_version": None if torch is None else str(getattr(torch, "__version__", "unknown")),
    "cpu_available": torch is not None,
    "mps_available": mps_available,
    "cuda_available": cuda_available,
    "device_name": device_name,
}, sort_keys=True))
"""
    completed = subprocess.run(
        [str(python), "-c", script, requested_device],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env=sanitized_subprocess_environment(),
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "runtime probe failed")[-500:]
        raise OSError(f"research runtime capability probe failed: {detail}")
    try:
        payload = json.loads(completed.stdout)
        if not isinstance(payload, dict):
            raise TypeError("capability payload is not an object")
        return SystemCapabilities(
            operating_system=str(payload["operating_system"]),
            architecture=str(payload["architecture"]),
            python_version=str(payload["python_version"]),
            torch_version=(
                None if payload["torch_version"] is None else str(payload["torch_version"])
            ),
            cpu_available=bool(payload["cpu_available"]),
            mps_available=bool(payload["mps_available"]),
            cuda_available=bool(payload["cuda_available"]),
            device_name=(
                None if payload["device_name"] is None else str(payload["device_name"])
            ),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise OSError("research runtime capability probe returned invalid JSON") from error


def build_execution_receipt(
    profile: ExecutionProfile,
    model_release: str,
    requested_device: str,
    capabilities: SystemCapabilities,
    *,
    inference_batch_size: int = 50,
    inference_code_sha256: str | None = None,
    checked_at: str | None = None,
) -> dict[str, Any]:
    profile.validate_request(model_release, requested_device)
    reasons: list[str] = []
    if capabilities.operating_system not in profile.operating_systems:
        reasons.append(
            f"operating system {capabilities.operating_system} is not admitted by {profile.id}"
        )
    if capabilities.architecture not in profile.architectures:
        reasons.append(
            f"architecture {capabilities.architecture} is not admitted by {profile.id}"
        )
    available = {
        "cpu": capabilities.cpu_available,
        "mps": capabilities.mps_available,
        "cuda": capabilities.cuda_available,
    }[requested_device]
    if not available:
        reasons.append(f"requested device {requested_device} is unavailable")
    resolved_device = requested_device if not reasons else None
    code_sha256 = inference_code_sha256 or sha256_file(INFERENCE_CODE_PATH)
    identity = {
        "profile_id": profile.id,
        "requested_device": requested_device,
        "resolved_device": resolved_device,
        "inference_batch_size": inference_batch_size,
        "inference_code_sha256": code_sha256,
        "capabilities": capabilities.as_dict(),
    }
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "status": "PASS" if not reasons else "UNAVAILABLE",
        "checked_at": checked_at or datetime.now(UTC).isoformat(),
        "profile_id": profile.id,
        "model_release": model_release,
        "research_only": profile.is_research_only(model_release),
        "requested_device": requested_device,
        "resolved_device": resolved_device,
        "inference_batch_size": inference_batch_size,
        "inference_code_sha256": code_sha256,
        "capabilities": capabilities.as_dict(),
        "reasons": reasons,
        "execution_identity_sha256": canonical_hash(identity),
    }
    receipt["receipt_hash"] = canonical_hash(receipt)
    return validate_execution_receipt(receipt)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_capability(receipt: Mapping[str, object]) -> None:
    validated = validate_execution_receipt(dict(receipt))
    if validated["status"] != "PASS":
        reasons = "; ".join(str(item) for item in validated["reasons"])
        raise CapabilityUnavailableError(reasons or "execution capability is unavailable")


def sanitized_subprocess_environment(
    source: Mapping[str, str] | None = None,
    *,
    runtime_values: Mapping[str, str] | None = None,
) -> dict[str, str]:
    parent = os.environ if source is None else source
    environment = {key: value for key, value in parent.items() if key in RESEARCH_ENV_ALLOWLIST}
    for key, value in (runtime_values or {}).items():
        if key not in SAFE_RUNTIME_KEYS:
            raise ValueError(f"runtime environment key is not allowlisted: {key}")
        environment[key] = value
    return environment


@contextmanager
def restricted_process_environment(environment: Mapping[str, str]) -> Iterator[None]:
    """Temporarily expose only an already-sanitized environment to research subprocesses."""

    if set(environment) - (RESEARCH_ENV_ALLOWLIST | SAFE_RUNTIME_KEYS):
        raise ValueError("research environment contains non-allowlisted keys")
    original = dict(os.environ)
    try:
        os.environ.clear()
        os.environ.update(environment)
        yield
    finally:
        os.environ.clear()
        os.environ.update(original)


def runtime_values(
    profile_id: str, model_release: str, device: str, inference_batch_size: int = 50
) -> dict[str, str]:
    if profile_id not in PROFILE_IDS or model_release not in RELEASES or device not in DEVICES:
        raise ValueError("runtime identity is invalid")
    if inference_batch_size <= 0:
        raise ValueError("inference batch size must be positive")
    return {
        "ELANQUANT_EXECUTION_PROFILE": profile_id,
        "ELANQUANT_MODEL_RELEASE": model_release,
        "ELANQUANT_EXECUTION_DEVICE": device,
        "ELANQUANT_INFERENCE_BATCH_SIZE": str(inference_batch_size),
    }
