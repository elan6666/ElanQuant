from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


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
    research_python: Path = Path(
        "/data/yilangliu/a_share_research/seven_model_research/.venv/bin/python"
    )
    research_deps: Path = Path("/data/yilangliu/a_share_research/elanquant/research-deps")
    proxy_client: Path = Path("/data/yilangliu/a_share_research/scripts/tushare_proxy_client.py")
    upstream_root: Path = Path("/data/yilangliu/a_share_research/elanquant/upstream/Kronos")
    matrix_receipt: Path = Path(
        "/data/yilangliu/a_share_research/elanquant/releases/current/training-matrix.json"
    )
    evaluation_receipt: Path = Path(
        "/data/yilangliu/a_share_research/elanquant/releases/current/formal-evaluation.json"
    )

    @classmethod
    def load(cls, config_path: Path | None = None) -> Settings:
        root = Path(__file__).resolve().parents[3]
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
            research_python=Path(
                os.environ.get(
                    "ELANQUANT_RESEARCH_PYTHON",
                    str(
                        raw.get(
                            "research_python",
                            "/data/yilangliu/a_share_research/seven_model_research/.venv/bin/python",
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
                            "/data/yilangliu/a_share_research/elanquant/research-deps",
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
                            "/data/yilangliu/a_share_research/scripts/tushare_proxy_client.py",
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
                            "/data/yilangliu/a_share_research/elanquant/upstream/Kronos",
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
                            "/data/yilangliu/a_share_research/elanquant/releases/current/training-matrix.json",
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
                            "/data/yilangliu/a_share_research/elanquant/releases/current/formal-evaluation.json",
                        )
                    ),
                )
            ),
        )
