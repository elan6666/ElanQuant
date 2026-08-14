from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from elanquant.execution import load_execution_profile

PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    database_path: Path
    artifact_root: Path
    frontend_dist: Path
    host: str = "127.0.0.1"
    port: int = 8765
    poll_seconds: float = 2.0
    initial_cash: float = 100_000.0
    top_k: int = 3
    pipeline_mode: str = "placeholder"
    execution_profiles_root: Path = PROJECT_ROOT / "configs/execution"
    execution_profile: str = "local-apple-silicon"
    model_release: str = "small"
    execution_device: str = "mps"
    inference_batch_size: int = 50
    research_python: Path = PROJECT_ROOT / ".venv/bin/python"
    research_deps: Path = PROJECT_ROOT / ".elanquant/research-deps"
    proxy_client: Path = PROJECT_ROOT / ".elanquant/provider/get_pro.py"
    upstream_root: Path = PROJECT_ROOT / ".elanquant/upstream/Kronos"
    matrix_receipt: Path = PROJECT_ROOT / ".elanquant/releases/current/training-matrix.json"
    evaluation_receipt: Path = (
        PROJECT_ROOT / ".elanquant/releases/current/formal-evaluation.json"
    )
    research_catalog: Path = PROJECT_ROOT / ".elanquant/releases/research-catalog.json"
    historical_backtest_catalog: Path = (
        PROJECT_ROOT / ".elanquant/releases/historical-backtest-catalog-v6.json"
    )

    @classmethod
    def load(cls, config_path: Path | None = None) -> Settings:
        root = PROJECT_ROOT
        path = config_path or Path(os.environ.get("ELANQUANT_CONFIG", root / "configs/app.yaml"))
        raw: dict[str, object] = {}
        if path.is_file():
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw = loaded

        def resolved_path(env_name: str, key: str, default: Path) -> Path:
            value = os.environ.get(env_name, str(raw.get(key, default)))
            candidate = Path(value)
            return candidate if candidate.is_absolute() else root / candidate

        profiles_root = resolved_path(
            "ELANQUANT_EXECUTION_PROFILES_ROOT",
            "execution_profiles_root",
            Path("configs/execution"),
        )
        profile_id = os.environ.get(
            "ELANQUANT_EXECUTION_PROFILE",
            str(raw.get("execution_profile", "local-apple-silicon")),
        )
        profile = load_execution_profile(profile_id, profiles_root)
        model_release = os.environ.get(
            "ELANQUANT_MODEL_RELEASE",
            str(raw.get("model_release", profile.default_release)),
        )
        execution_device = os.environ.get(
            "ELANQUANT_EXECUTION_DEVICE",
            str(raw.get("execution_device", profile.default_device)),
        )
        profile.validate_request(model_release, execution_device)
        inference_batch_size = int(
            os.environ.get(
                "ELANQUANT_INFERENCE_BATCH_SIZE",
                str(raw.get("inference_batch_size", 50)),
            )
        )
        if inference_batch_size <= 0:
            raise ValueError("inference_batch_size must be positive")

        return cls(
            database_path=resolved_path(
                "ELANQUANT_DB_PATH", "database_path", Path("artifacts/elanquant.sqlite3")
            ),
            artifact_root=resolved_path(
                "ELANQUANT_ARTIFACT_ROOT", "artifact_root", Path("artifacts/runs")
            ),
            frontend_dist=resolved_path(
                "ELANQUANT_FRONTEND_DIST", "frontend_dist", Path("frontend/dist")
            ),
            host=os.environ.get("ELANQUANT_HOST", str(raw.get("loopback_host", "127.0.0.1"))),
            port=int(os.environ.get("ELANQUANT_PORT", str(raw.get("port", 8765)))),
            poll_seconds=float(
                os.environ.get("ELANQUANT_POLL_SECONDS", str(raw.get("poll_seconds", 2)))
            ),
            initial_cash=float(
                os.environ.get("ELANQUANT_INITIAL_CASH", str(raw.get("initial_cash", 100000)))
            ),
            top_k=int(os.environ.get("ELANQUANT_TOP_K", str(raw.get("top_k", 3)))),
            pipeline_mode=os.environ.get(
                "ELANQUANT_PIPELINE_MODE", str(raw.get("pipeline_mode", "placeholder"))
            ),
            execution_profiles_root=profiles_root,
            execution_profile=profile_id,
            model_release=model_release,
            execution_device=execution_device,
            inference_batch_size=inference_batch_size,
            research_python=Path(
                os.environ.get(
                    "ELANQUANT_RESEARCH_PYTHON",
                    str(
                        raw.get(
                            "research_python",
                            root / ".venv/bin/python",
                        )
                    ),
                )
            ),
            research_deps=Path(
                os.environ.get(
                    "ELANQUANT_RESEARCH_DEPS",
                    str(
                        raw.get(
                            "research_deps",
                            root / ".elanquant/research-deps",
                        )
                    ),
                )
            ),
            proxy_client=Path(
                os.environ.get(
                    "ELANQUANT_PROXY_CLIENT",
                    str(
                        raw.get(
                            "proxy_client",
                            root / ".elanquant/provider/get_pro.py",
                        )
                    ),
                )
            ),
            upstream_root=Path(
                os.environ.get(
                    "ELANQUANT_UPSTREAM_ROOT",
                    str(
                        raw.get(
                            "upstream_root",
                            root / ".elanquant/upstream/Kronos",
                        )
                    ),
                )
            ),
            matrix_receipt=Path(
                os.environ.get(
                    "ELANQUANT_MATRIX_RECEIPT",
                    str(
                        raw.get(
                            "matrix_receipt",
                            root / ".elanquant/releases/current/training-matrix.json",
                        )
                    ),
                )
            ),
            evaluation_receipt=Path(
                os.environ.get(
                    "ELANQUANT_EVALUATION_RECEIPT",
                    str(
                        raw.get(
                            "evaluation_receipt",
                            root / ".elanquant/releases/current/formal-evaluation.json",
                        )
                    ),
                )
            ),
            research_catalog=Path(
                os.environ.get(
                    "ELANQUANT_RESEARCH_CATALOG",
                    str(
                        raw.get(
                            "research_catalog",
                            root / ".elanquant/releases/research-catalog.json",
                        )
                    ),
                )
            ),
            historical_backtest_catalog=resolved_path(
                "ELANQUANT_HISTORICAL_BACKTEST_CATALOG",
                "historical_backtest_catalog",
                Path(
                    root / ".elanquant/releases/historical-backtest-catalog-v6.json"
                ),
            ),
        )
