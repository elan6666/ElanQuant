from __future__ import annotations

import csv
import hashlib
import json
import math
import sqlite3
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from elanquant.contracts.historical_matrix import (
    BACKTEST_SCHEMA as HISTORICAL_MATRIX_BACKTEST_SCHEMA,
)
from elanquant.contracts.historical_matrix import (
    CATALOG_SCHEMA as HISTORICAL_MATRIX_CATALOG_SCHEMA,
)
from elanquant.contracts.historical_matrix import (
    backtest_id as historical_matrix_backtest_id,
)
from elanquant.contracts.historical_matrix import (
    validate_backtest_receipt as validate_matrix_backtest_receipt,
)
from elanquant.contracts.historical_matrix import (
    validate_catalog as validate_matrix_catalog,
)
from elanquant.contracts.historical_variants import (
    HOLDINGS_COLUMNS,
    validate_any_backtest_receipt,
    validate_historical_catalog,
    validate_holdings_receipt,
    validate_holdings_records,
)
from elanquant.contracts.official_demo import SIGNALS as OFFICIAL_DEMO_SIGNALS
from elanquant.contracts.official_demo import sha256_file
from elanquant.contracts.unified_comparison import (
    CATALOG_SCHEMA as UNIFIED_COMPARISON_CATALOG_SCHEMA,
)
from elanquant.contracts.unified_comparison import (
    RESULT_SCHEMA as UNIFIED_COMPARISON_RESULT_SCHEMA,
)
from elanquant.contracts.unified_comparison import (
    validate_catalog as validate_unified_comparison_catalog,
)
from elanquant.contracts.unified_comparison import (
    validate_model_evidence as validate_unified_comparison_evidence,
)
from elanquant.contracts.unified_comparison import (
    validate_result_receipt as validate_unified_comparison_result,
)
from elanquant.execution import load_execution_profile
from elanquant.orchestration.jobs import JobStore
from elanquant.pipelines.paper import ACCOUNT_ID
from elanquant.settings import Settings
from elanquant.storage.database import Database
from scripts.research import online_release_v3 as online_release_contract
from scripts.research.official_split_v3 import (
    BACKTEST_SCHEMA as OFFICIAL_SPLIT_V3_BACKTEST_SCHEMA,
)
from scripts.research.official_split_v3 import (
    HISTORICAL_SCHEMA as OFFICIAL_SPLIT_V3_HISTORICAL_SCHEMA,
)
from scripts.research.official_split_v3 import validate_analysis_lock
from scripts.research.official_split_v3 import (
    validate_backtest_receipt as validate_official_split_v3_backtest,
)
from scripts.research.official_split_v3 import (
    validate_historical_catalog as validate_official_split_v3_historical,
)
from scripts.research.online_compatibility_v3 import (
    COMPATIBILITY_RELEASE_SCHEMA,
    validate_compatibility_release,
    validate_compatibility_release_dir,
)
from scripts.research.online_release_v3 import validate_method_lock, validate_release

HISTORICAL_CURVE_SEMANTICS = {
    "official": "Arithmetic cumulative sum of daily returns, matching qlib_test.py.",
    "derived": "Compounded NAV is an ElanQuant instrumentation extension.",
}


class UpdateInferRequest(BaseModel):
    target_session: date | None = Field(default=None, description="Requested A-share session")
    force: bool = False
    execution_profile: str | None = Field(
        default=None, description="Frozen deployment execution profile"
    )
    model_release: str | None = Field(default=None, description="Small default or Base opt-in")


def canonical_hash(payload: object) -> str:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def official_split_v3_experiments(
    payload: object,
    matrix_payload: object,
    evaluation_sha256: str,
    matrix_sha256: str,
    release_payload: object,
) -> list[dict[str, object]]:
    if (
        not isinstance(payload, dict)
        or not isinstance(matrix_payload, dict)
        or not isinstance(release_payload, dict)
    ):
        raise RuntimeError("official-split-v3 catalog or matrix is not an object")
    release = (
        validate_compatibility_release(release_payload)
        if release_payload.get("schema_version") == COMPATIBILITY_RELEASE_SCHEMA
        else validate_release(release_payload)
    )
    if (
        release.get("training_matrix_sha256") != matrix_sha256
        or release.get("rolling_evaluation_sha256") != evaluation_sha256
        or payload.get("analysis_lock_sha256") != release.get("analysis_lock_sha256")
    ):
        raise RuntimeError("official-split-v3 release/evaluation/matrix binding differs")
    expected = {
        f"{size}-{variant}"
        for size in ("small", "base")
        for variant in ("zero-shot", "official-ft")
    }
    for value, schema in (
        (payload, "elanquant_kronos_rolling_evaluation_v3"),
        (matrix_payload, "elanquant_kronos_four_cell_matrix_v3"),
    ):
        content = dict(value)
        claimed = content.pop("receipt_hash", None)
        if (
            value.get("schema_version") != schema
            or value.get("status") != "PASS"
            or not valid_sha256(claimed)
            or canonical_hash(content) != claimed
        ):
            raise RuntimeError(f"official-split-v3 evidence is not sealed: {schema}")
    if (
        payload.get("test_status") != "TEST_VIEWED"
        or payload.get("used_for_selection") is not False
        or payload.get("promotion_eligible") is not False
    ):
        raise RuntimeError("official-split-v3 evaluation firewall is invalid")
    entries = payload.get("entries")
    matrix_cells = matrix_payload.get("cells")
    if (
        not isinstance(entries, list)
        or not all(isinstance(row, dict) for row in entries)
        or {str(row.get("model_cell_id")) for row in entries} != expected
        or not isinstance(matrix_cells, list)
        or not all(isinstance(row, dict) for row in matrix_cells)
        or {str(row.get("id")) for row in matrix_cells} != expected
    ):
        raise RuntimeError("official-split-v3 evidence is not the exact four-cell matrix")
    cells = {str(row["id"]): row for row in matrix_cells}
    experiments: list[dict[str, object]] = []
    common_support: tuple[int, int, str] | None = None
    for entry in entries:
        model_id = str(entry["model_cell_id"])
        metrics, support = entry.get("metrics"), entry.get("support")
        cell = cells[model_id]
        if not isinstance(metrics, dict) or not isinstance(support, dict):
            raise RuntimeError(f"official-split-v3 metrics are missing: {model_id}")
        if not all(
            not isinstance(metrics.get(name), bool)
            and isinstance(metrics.get(name), (int, float))
            and math.isfinite(float(metrics[name]))
            for name in ("rank_ic", "ic", "top10_mean_return")
        ):
            raise RuntimeError(f"official-split-v3 metrics are invalid: {model_id}")
        rows, sections = support.get("rows"), support.get("sessions")
        if (
            not isinstance(rows, int)
            or rows <= 0
            or not isinstance(sections, int)
            or sections <= 0
            or not valid_sha256(entry.get("signal_sha256"))
            or not all(
                valid_sha256(cell.get(field))
                for field in ("predictor_sha256", "tokenizer_sha256", "config_sha256")
            )
        ):
            raise RuntimeError(f"official-split-v3 identity is invalid: {model_id}")
        candidate_set_sha256 = entry.get("candidate_set_sha256")
        if not valid_sha256(candidate_set_sha256):
            raise RuntimeError(f"official-split-v3 candidate set is invalid: {model_id}")
        signature = (rows, sections, str(candidate_set_sha256))
        if common_support is not None and signature != common_support:
            raise RuntimeError("official-split-v3 cells do not share common support")
        common_support = signature
        split = {
            "rank_ic": metrics["rank_ic"],
            "pearson_ic": metrics["ic"],
            "top10_mean_return": metrics["top10_mean_return"],
            "rows": rows,
            "cross_sections": sections,
            "anchor_set_sha256": candidate_set_sha256,
        }
        experiments.append(
            {
                "id": model_id,
                "model_size": "small" if model_id.startswith("small-") else "base",
                "track": "zero_shot" if model_id.endswith("zero-shot") else "official_style",
                "state": "passed",
                "rank_ic": metrics["rank_ic"],
                "pearson_ic": metrics["ic"],
                "top10_mean_return": metrics["top10_mean_return"],
                "model_hash": cell["predictor_sha256"],
                "receipt": evaluation_sha256,
                "note": "Rolling test 已查看；只描述结果，不用于选模或上线提升。",
                "evaluations": {"test_viewed_official_v3": split},
            }
        )
    return sorted(experiments, key=lambda item: str(item["id"]))


def validate_research_catalog(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise RuntimeError("catalog is not an object")
    content = dict(payload)
    receipt_hash = content.pop("receipt_hash", None)
    expected_tracks = {
        f"{size}-{identity}": (size, track)
        for size in ("small", "base")
        for identity, track in (
            ("zero-shot", "zero_shot"),
            ("official-ft", "official_style"),
            ("strict-pit", "strict_pit"),
        )
    }
    experiments = payload.get("experiments")
    sources = payload.get("sources")
    compatibility = payload.get("compatibility")
    if (
        payload.get("schema_version") != "elanquant_research_catalog_v1"
        or payload.get("status") != "PASS"
        or not valid_sha256(receipt_hash)
        or canonical_hash(content) != receipt_hash
        or not isinstance(experiments, list)
        or len(experiments) != len(expected_tracks)
        or not all(isinstance(item, dict) for item in experiments)
        or not isinstance(sources, dict)
        or set(sources) != {"small", "base"}
        or not isinstance(compatibility, dict)
    ):
        raise RuntimeError("catalog top-level receipt is invalid")
    if {str(item["id"]) for item in experiments} != set(expected_tracks):
        raise RuntimeError("catalog is not the exact six-cell experiment")
    support_by_split: dict[str, tuple[int, int, str]] = {}
    for item in experiments:
        model_id = str(item["id"])
        expected_size, expected_track = expected_tracks[model_id]
        if (
            item.get("model_size") != expected_size
            or item.get("track") != expected_track
            or item.get("state") != "passed"
            or not valid_sha256(item.get("model_hash"))
            or not valid_sha256(item.get("receipt"))
        ):
            raise RuntimeError(f"catalog cell identity is invalid: {model_id}")
        evaluations = item.get("evaluations")
        if not isinstance(evaluations, dict) or set(evaluations) != {
            "validation_2025",
            "test_viewed_2026",
        }:
            raise RuntimeError(f"catalog split evidence is incomplete: {model_id}")
        for split, values in evaluations.items():
            if not isinstance(values, dict):
                raise RuntimeError(f"catalog split evidence is invalid: {model_id}.{split}")
            for metric in ("rank_ic", "pearson_ic", "top10_mean_return"):
                value = values.get(metric)
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                ):
                    raise RuntimeError(f"catalog metric is invalid: {model_id}.{split}.{metric}")
            rows = values.get("rows")
            sections = values.get("cross_sections")
            anchor = values.get("anchor_set_sha256")
            if (
                isinstance(rows, bool)
                or not isinstance(rows, int)
                or rows <= 0
                or isinstance(sections, bool)
                or not isinstance(sections, int)
                or sections <= 0
                or not valid_sha256(anchor)
            ):
                raise RuntimeError(f"catalog support is invalid: {model_id}.{split}")
            signature = (rows, sections, str(anchor))
            if split in support_by_split and support_by_split[split] != signature:
                raise RuntimeError(f"catalog common support disagrees: {split}")
            support_by_split[split] = signature
    comparable_keys = (
        "upstream_commit",
        "official_weights_receipt_sha256",
        "training_data_sha256",
        "admission_sha256",
        "split_contract_sha256",
        "evaluation_data_sha256",
        "evaluation_protocol_sha256",
        "compatibility_receipt_sha256",
        "as_of_session",
        "support",
    )
    source_payloads: dict[str, dict[str, object]] = {}
    for size in ("small", "base"):
        source = sources.get(size)
        if not isinstance(source, dict):
            raise RuntimeError(f"catalog source is invalid: {size}")
        for identity in (
            "matrix_sha256",
            "evaluation_sha256",
            "official_weights_receipt_sha256",
            "training_data_sha256",
            "admission_sha256",
            "split_contract_sha256",
            "evaluation_data_sha256",
            "evaluation_config_sha256",
            "inference_code_sha256",
            "evaluation_protocol_sha256",
            "compatibility_receipt_sha256",
        ):
            if not valid_sha256(source.get(identity)):
                raise RuntimeError(f"catalog source identity is invalid: {size}.{identity}")
        upstream = source.get("upstream_commit")
        if (
            not isinstance(upstream, str)
            or len(upstream) != 40
            or any(character not in "0123456789abcdef" for character in upstream.lower())
        ):
            raise RuntimeError(f"catalog upstream identity is invalid: {size}")
        as_of = source.get("as_of_session")
        try:
            parsed_as_of = date.fromisoformat(str(as_of))
        except ValueError as error:
            raise RuntimeError(f"catalog as-of session is invalid: {size}") from error
        if parsed_as_of.isoformat() != as_of:
            raise RuntimeError(f"catalog as-of session is invalid: {size}")
        source_support = source.get("support")
        if not isinstance(source_support, dict) or set(source_support) != set(support_by_split):
            raise RuntimeError(f"catalog source support is invalid: {size}")
        for split, expected_signature in support_by_split.items():
            values = source_support.get(split)
            if not isinstance(values, dict):
                raise RuntimeError(f"catalog source support is invalid: {size}.{split}")
            eligible_rows = values.get("eligible_rows")
            if (
                isinstance(eligible_rows, bool)
                or not isinstance(eligible_rows, int)
                or eligible_rows < expected_signature[0]
            ):
                raise RuntimeError(f"catalog source support is invalid: {size}.{split}")
            signature = (
                values.get("evaluated_rows"),
                values.get("evaluated_cross_sections"),
                values.get("anchor_set_sha256"),
            )
            if signature != expected_signature:
                raise RuntimeError(f"catalog source support is mismatched: {size}.{split}")
        source_payloads[size] = source
    compatibility_content = dict(compatibility)
    compatibility_hash = compatibility_content.pop("receipt_hash", None)
    normalized_protocol = compatibility.get("normalized_protocol")
    source_identities = compatibility.get("source_identities")
    if (
        compatibility.get("schema_version") != "elanquant_evaluation_compatibility_v1"
        or compatibility.get("status") != "PASS"
        or compatibility.get("decision") != "SEMANTICALLY_COMPARABLE"
        or not valid_sha256(compatibility_hash)
        or canonical_hash(compatibility_content) != compatibility_hash
        or not isinstance(normalized_protocol, dict)
        or compatibility.get("protocol_sha256") != canonical_hash(normalized_protocol)
        or not isinstance(source_identities, dict)
        or set(source_identities) != {"small", "base"}
        or compatibility.get("source_revisions")
        != {
            "small": "ec5ccffd1353da792d0dd5274b7a279918a0f1e2",
            "base": "266bab286a03c07a8b186a443c64144bfa35c487",
        }
        or compatibility.get("source_path") != "scripts/server/evaluate_and_infer.py"
        or compatibility.get("source_diff_sha256")
        != "7fff6d49340c5ac08b006cd72f858ba314535a7176da07d97704344648861308"
        or compatibility.get("allowed_differences")
        != [
            "MODEL_SIZE_PARAMETERIZATION",
            "MODEL_CELL_ID_PREFIX",
            "BATCH_CONFIG_KEY_RENAMED",
            "ONLINE_BATCH_SIZE_EXPLICIT_50",
            "PRIMARY_STRICT_MODEL_ID_AND_LABEL",
        ]
    ):
        raise RuntimeError("catalog compatibility receipt is invalid")
    for size in ("small", "base"):
        identities = source_identities.get(size)
        source = source_payloads[size]
        if not isinstance(identities, dict) or identities != {
            "evaluation_config_sha256": source["evaluation_config_sha256"],
            "inference_code_sha256": source["inference_code_sha256"],
        }:
            raise RuntimeError(f"catalog compatibility identity differs: {size}")
        if source["evaluation_protocol_sha256"] != compatibility["protocol_sha256"]:
            raise RuntimeError(f"catalog compatibility protocol differs: {size}")
        if source["compatibility_receipt_sha256"] != compatibility_hash:
            raise RuntimeError(f"catalog compatibility receipt differs: {size}")
    if compatibility.get("evaluation_receipts") != {
        "small": source_payloads["small"]["evaluation_sha256"],
        "base": source_payloads["base"]["evaluation_sha256"],
    }:
        raise RuntimeError("catalog compatibility evaluations differ")
    for key in comparable_keys:
        if source_payloads["small"].get(key) != source_payloads["base"].get(key):
            raise RuntimeError(f"catalog Small/Base identity differs: {key}")
    for item in experiments:
        size = str(item["model_size"])
        if item.get("receipt") != source_payloads[size].get("evaluation_sha256"):
            raise RuntimeError(f"catalog cell receipt is mismatched: {item['id']}")
    return payload


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings.load()
    active_profile = load_execution_profile(
        active_settings.execution_profile, active_settings.execution_profiles_root
    )
    active_profile.validate_request(active_settings.model_release, active_settings.execution_device)
    database = Database(active_settings.database_path)
    database.initialize()
    jobs = JobStore(database)
    app = FastAPI(
        title="ElanQuant",
        version="0.1.0",
        description="Loopback-only research and simulated-account control plane",
    )
    app.state.settings = active_settings
    app.state.database = database
    app.state.jobs = jobs
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"],
    )

    def historical_public_identity(
        entry: dict[str, Any], receipt: dict[str, Any]
    ) -> dict[str, object]:
        split = receipt.get(
            "evaluation_split", entry.get("evaluation_split", entry.get("selection_split"))
        )
        if split not in {
            "validation_2025",
            "test_viewed_2026",
            "test_viewed_official_v3",
        }:
            raise RuntimeError("historical public split identity is invalid")
        top50 = receipt["strategy"].get("topk") == 50
        matrix = receipt.get("schema_version") in {
            HISTORICAL_MATRIX_BACKTEST_SCHEMA,
            OFFICIAL_SPLIT_V3_BACKTEST_SCHEMA,
        }
        source_backtest_id = None
        comparison_group_id = "top50-vs-top3-v1"
        if matrix:
            comparison_group_id = (
                "official-split-v3-top50-top3-v1"
                if receipt.get("schema_version") == OFFICIAL_SPLIT_V3_BACKTEST_SCHEMA
                else "six-model-top50-top3-v1"
            )
            if not top50:
                source_backtest_id = (
                    str(receipt["id"]).replace("historical_top3", "official_top50")
                    if receipt.get("schema_version") == OFFICIAL_SPLIT_V3_BACKTEST_SCHEMA
                    else historical_matrix_backtest_id(
                        str(receipt["model_cell_id"]),
                        str(split),
                        "official_top50",
                    )
                )
        elif not top50:
            source_backtest_id = receipt.get("source_backtest_id")
        expected: dict[str, object] = {
            "strategy_variant_id": "official_top50" if top50 else "historical_top3",
            "strategy_role": (
                "OFFICIAL_METHOD_BASELINE" if top50 else "PORTFOLIO_SENSITIVITY_VARIANT"
            ),
            "comparison_group_id": comparison_group_id,
            "execution_domain": "HISTORICAL_QLIB_SIMULATION",
            "online_paper_equivalent": False,
            "promotion_eligible": False,
            "source_backtest_id": source_backtest_id,
        }
        for identity, value in expected.items():
            if identity in entry:
                declared = entry[identity]
            elif identity in receipt:
                declared = receipt[identity]
            else:
                declared = value
            if declared != value:
                raise RuntimeError(f"historical public identity disagrees: {identity}")
            if not top50 and identity == "source_backtest_id" and value is None:
                raise RuntimeError("historical Top3 source backtest identity is absent")
        return expected

    def historical_artifact_root(catalog: dict[str, Any]) -> Path:
        catalog_path = active_settings.historical_backtest_catalog.resolve()
        if catalog.get("schema_version") == OFFICIAL_SPLIT_V3_HISTORICAL_SCHEMA:
            declared_root = catalog.get("artifact_root")
            if not isinstance(declared_root, str) or not Path(declared_root).is_absolute():
                raise RuntimeError("historical artifact root is invalid")
            root = Path(declared_root).resolve()
        else:
            root = catalog_path.parent.parent.resolve()
        if not root.is_dir():
            raise RuntimeError("historical artifact root is unavailable")
        return root

    def load_historical_backtests() -> tuple[
        dict[str, Any] | None,
        dict[str, tuple[dict[str, Any], dict[str, Any]]],
    ]:
        catalog_path = active_settings.historical_backtest_catalog.resolve()
        if not catalog_path.is_file():
            return None, {}
        try:
            raw_catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            if raw_catalog.get("schema_version") == HISTORICAL_MATRIX_CATALOG_SCHEMA:
                catalog = validate_matrix_catalog(raw_catalog)
            elif raw_catalog.get("schema_version") == OFFICIAL_SPLIT_V3_HISTORICAL_SCHEMA:
                catalog = validate_official_split_v3_historical(raw_catalog)
            else:
                catalog = validate_historical_catalog(raw_catalog)
            root = historical_artifact_root(catalog)
            loaded: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
            for entry in catalog["entries"]:
                receipt_path = (root / str(entry["receipt_path"])).resolve()
                if root not in receipt_path.parents or not receipt_path.is_file():
                    raise RuntimeError("historical backtest receipt escaped its sealed root")
                if sha256_file(receipt_path) != entry["receipt_sha256"]:
                    raise RuntimeError("historical backtest receipt hash mismatch")
                raw_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                if raw_receipt.get("schema_version") == HISTORICAL_MATRIX_BACKTEST_SCHEMA:
                    receipt = validate_matrix_backtest_receipt(raw_receipt)
                elif raw_receipt.get("schema_version") == OFFICIAL_SPLIT_V3_BACKTEST_SCHEMA:
                    receipt = validate_official_split_v3_backtest(raw_receipt)
                else:
                    receipt = validate_any_backtest_receipt(raw_receipt)
                summary = entry["summary"]
                if (
                    receipt["id"] != entry["id"]
                    or receipt["model_cell_id"] != entry["model_cell_id"]
                    or not isinstance(summary, dict)
                    or any(
                        receipt["metrics"][receipt["primary_signal"]].get(key) != value
                        for key, value in summary.items()
                    )
                ):
                    raise RuntimeError("historical backtest catalog and receipt disagree")
                entry = {**entry, **historical_public_identity(entry, receipt)}
                identifier = str(receipt["id"])
                if identifier in loaded:
                    raise RuntimeError("historical backtest identity is duplicated")
                loaded[identifier] = (entry, receipt)
            if len(loaded) != len(catalog["entries"]):
                raise RuntimeError("historical backtest catalog did not load exactly")
        except (
            KeyError,
            OSError,
            json.JSONDecodeError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as error:
            raise HTTPException(
                status_code=503,
                detail="Historical backtest failed its sealed evidence gate",
            ) from error
        return catalog, loaded

    def _unified_comparison_root(catalog_path: Path) -> Path:
        """Resolve the project root from a catalog below artifacts/.

        The cross-model track is deliberately outside the Qlib catalog.  Its
        receipt paths are project-root-relative and therefore cannot inherit
        the historical catalog's parent arithmetic.
        """
        for candidate in (catalog_path.resolve(), *catalog_path.resolve().parents):
            if candidate.name == "artifacts":
                root = candidate.parent.resolve()
                if root.is_dir():
                    return root
        raise RuntimeError("unified comparison catalog is not below artifacts")

    def _unified_artifact(root: Path, artifact: object, name: str) -> Path:
        if not isinstance(artifact, dict):
            raise RuntimeError(f"unified {name} artifact is invalid")
        path, digest = artifact.get("path"), artifact.get("sha256")
        if not isinstance(path, str) or not valid_sha256(digest):
            raise RuntimeError(f"unified {name} artifact identity is invalid")
        resolved = (root / path).resolve()
        if root not in resolved.parents or not resolved.is_file():
            raise RuntimeError(f"unified {name} artifact escaped the sealed root")
        if sha256_file(resolved) != digest:
            raise RuntimeError(f"unified {name} artifact hash differs")
        return resolved

    def _unified_csv_series(path: Path) -> list[dict[str, object]]:
        points: list[dict[str, object]] = []
        previous = ""
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            required_columns = {"session", "strategy", "benchmark", "excess"}
            if reader.fieldnames is None or not required_columns.issubset(reader.fieldnames):
                raise RuntimeError("unified daily series columns differ")
            for row in reader:
                session = row.get("session")
                if not isinstance(session, str) or not session or session <= previous:
                    raise RuntimeError("unified daily series session ordering differs")
                try:
                    strategy = float(row["strategy"])
                    benchmark = float(row["benchmark"])
                    excess = float(row["excess"])
                except (KeyError, TypeError, ValueError) as error:
                    raise RuntimeError("unified daily series numeric cell is invalid") from error
                if not all(math.isfinite(item) for item in (strategy, benchmark, excess)):
                    raise RuntimeError("unified daily series contains non-finite values")
                points.append(
                    {
                        "session": session,
                        "strategy": strategy,
                        "benchmark": benchmark,
                        "excess": excess,
                        "strategy_nav": 1.0 + strategy,
                        "benchmark_nav": 1.0 + benchmark,
                    }
                )
                previous = session
        if not points:
            raise RuntimeError("unified daily series is empty")
        return points

    def _unified_holdings(path: Path) -> dict[str, object]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or set(raw) != {"session", "items"}:
            raise RuntimeError("unified holdings payload is invalid")
        session, items = raw["session"], raw["items"]
        if not isinstance(session, str) or not session or not isinstance(items, list):
            raise RuntimeError("unified holdings identity is invalid")
        output: list[dict[str, object]] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, dict) or set(item) != {
                "instrument",
                "weight",
                "amount",
                "value",
            }:
                raise RuntimeError("unified holding is invalid")
            code = item["instrument"]
            if not isinstance(code, str) or not code or code in seen:
                raise RuntimeError("unified holding instrument is invalid")
            values = (item["weight"], item["amount"], item["value"])
            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0
                for value in values
            ):
                raise RuntimeError("unified holding numeric value is invalid")
            seen.add(code)
            output.append(
                {
                    "instrument": code,
                    "weight": float(item["weight"]),
                    "amount": float(item["amount"]),
                    "value": float(item["value"]),
                }
            )
        return {"session": session, "items": output}

    def load_unified_comparison() -> dict[str, object]:
        catalog_path = active_settings.unified_comparison_catalog.resolve()
        if not catalog_path.is_file():
            return {"available": False, "id": None, "protocol": None, "models": []}
        try:
            catalog = validate_unified_comparison_catalog(
                json.loads(catalog_path.read_text(encoding="utf-8"))
            )
            if catalog.get("schema_version") != UNIFIED_COMPARISON_CATALOG_SCHEMA:
                raise RuntimeError("unified comparison catalog schema differs")
            root = _unified_comparison_root(catalog_path)
            entries: dict[str, dict[str, Any]] = {}
            protocol_sha = catalog.get("protocol_receipt_sha256")
            if not valid_sha256(protocol_sha):
                raise RuntimeError("unified comparison protocol identity is invalid")
            for entry in catalog["entries"]:
                receipt_path = _unified_artifact(
                    root,
                    {"path": entry["receipt_path"], "sha256": entry["receipt_sha256"]},
                    "result receipt",
                )
                receipt = validate_unified_comparison_result(
                    json.loads(receipt_path.read_text(encoding="utf-8"))
                )
                if (
                    receipt.get("schema_version") != UNIFIED_COMPARISON_RESULT_SCHEMA
                    or receipt.get("protocol_receipt_sha256") != protocol_sha
                    or receipt.get("protocol_id") != catalog.get("protocol_id")
                ):
                    raise RuntimeError("unified comparison result protocol differs")
                key = f"{receipt['model_family_id']}:{receipt['portfolio_id']}"
                entries[key] = receipt
            if len(entries) != 6:
                raise RuntimeError("unified comparison matrix is incomplete")
            protocol_path = _unified_artifact(
                root,
                {"path": catalog.get("protocol_path"), "sha256": protocol_sha},
                "protocol receipt",
            )
            if not protocol_path.is_file():
                raise RuntimeError("unified comparison protocol receipt differs")
            protocol_raw = json.loads(protocol_path.read_text(encoding="utf-8"))
            common = protocol_raw.get("common_protocol")
            if not isinstance(common, dict):
                raise RuntimeError("unified common protocol is invalid")
            evaluation_range = common.get("evaluation_range")
            support = common.get("support")
            if not isinstance(evaluation_range, dict) or not isinstance(support, dict):
                raise RuntimeError("unified comparison protocol support is invalid")
            evidence_by_family: dict[str, dict[str, Any]] = {}
            evidence_rows = protocol_raw.get("source_evidence")
            if not isinstance(evidence_rows, list):
                raise RuntimeError("unified comparison evidence is invalid")
            for evidence_row in evidence_rows:
                if not isinstance(evidence_row, dict):
                    raise RuntimeError("unified comparison evidence row is invalid")
                evidence_path = _unified_artifact(
                    root,
                    {
                        "path": evidence_row.get("receipt_path"),
                        "sha256": evidence_row.get("receipt_sha256"),
                    },
                    "model evidence receipt",
                )
                evidence = validate_unified_comparison_evidence(
                    json.loads(evidence_path.read_text(encoding="utf-8"))
                )
                if evidence.get("model_family_id") != evidence_row.get("model_family_id"):
                    raise RuntimeError("unified comparison evidence identity differs")
                evidence_by_family[str(evidence["model_family_id"])] = evidence
            if len(evidence_by_family) != 2:
                raise RuntimeError("unified comparison evidence is incomplete")
            families = (
                (
                    "itransformer-b2-r16g-r3",
                    "itransformer_b2",
                    "iTransformer B2",
                    "过去 80 个交易日的 CSI300 开盘到开盘对数收益",
                    80,
                    ["open-to-open log return"],
                ),
                (
                    "kronos-base-zero-shot",
                    "kronos_base",
                    "Kronos Base（公开 zero-shot）",
                    "过去 90 个交易日 OHLCVA，经实例标准化后预测路径",
                    90,
                    ["open", "high", "low", "close", "volume", "amount"],
                ),
            )
            models: list[dict[str, object]] = []
            for family_id, family, label, description, lookback, features in families:
                cells = [
                    entries[f"{family_id}:{portfolio}"] for portfolio in ("top1", "top3", "top50")
                ]
                first = cells[0]
                source = evidence_by_family[family_id]
                _unified_artifact(root, source["artifacts"]["scores"], "score")
                strategies: list[dict[str, object]] = []
                for receipt in cells:
                    artifacts = receipt["artifacts"]
                    series = _unified_csv_series(
                        _unified_artifact(root, artifacts["daily_series"], "daily series")
                    )
                    holdings_artifact = _unified_artifact(root, artifacts["holdings"], "holdings")
                    holdings = _unified_holdings(holdings_artifact)
                    holdings["receipt_sha256"] = artifacts["holdings"]["sha256"]
                    strategies.append(
                        {
                            "id": receipt["portfolio_id"],
                            "label": f"Top{receipt['portfolio_id'][3:]}",
                            "topk": int(receipt["portfolio_id"][3:]),
                            "metrics": receipt["portfolio_metrics"],
                            "series": series,
                            "holdings": holdings,
                        }
                    )
                models.append(
                    {
                        "id": family_id,
                        "family": family,
                        "label": label,
                        "input": {
                            "description": description,
                            "lookback_sessions": lookback,
                            "features": features,
                        },
                        "checkpoint_sha256": source.get("model_sha256"),
                        "common_metrics": first["prediction_metrics"],
                        "strategies": strategies,
                    }
                )
            return {
                "available": True,
                "id": catalog["protocol_id"],
                "protocol": {
                    "id": catalog["protocol_id"],
                    "label": "CSI300 严格周频共同评估（已查看研究结果）",
                    "universe": "CSI300 共同支持集",
                    "frequency": "严格周频（约 5 个交易日）",
                    "signal_start": evaluation_range["start"],
                    "signal_end": evaluation_range["end"],
                    "execution_start": common.get("execution_start", evaluation_range["start"]),
                    "execution_end": common.get("execution_end", evaluation_range["end"]),
                    "anchor_set_sha256": common["anchor_set_sha256"],
                    "label_definition": "同一锚点后下一周开盘到开盘实际收益",
                    "viewed": True,
                },
                "models": models,
            }
        except (
            KeyError,
            OSError,
            json.JSONDecodeError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as error:
            raise HTTPException(
                status_code=503, detail="Unified comparison failed its sealed evidence gate"
            ) from error

    def public_backtest(
        entry: dict[str, Any], receipt: dict[str, Any], receipt_sha256: str
    ) -> dict[str, object]:
        source = entry.get("source")
        if not isinstance(source, dict):
            source = {}
        signal_receipt_sha256 = receipt.get(
            "signal_receipt_sha256",
            receipt.get("source_signal_receipt_sha256", source.get("signal_receipt_sha256")),
        )
        provider_receipt_sha256 = receipt.get(
            "provider_receipt_sha256",
            receipt.get("source_provider_receipt_sha256", source.get("provider_receipt_sha256")),
        )
        if not valid_sha256(signal_receipt_sha256) or not valid_sha256(provider_receipt_sha256):
            raise RuntimeError("historical public source identity is incomplete")
        curve_semantics = receipt.get(
            "curve_semantics",
            HISTORICAL_CURVE_SEMANTICS,
        )
        result: dict[str, object] = {
            "id": receipt["id"],
            "state": "passed",
            "track_kind": receipt.get(
                "track_kind",
                (
                    "OFFICIAL_SPLIT_V3_MODEL_MATRIX"
                    if receipt.get("schema_version") == OFFICIAL_SPLIT_V3_BACKTEST_SCHEMA
                    else "HISTORICAL_MODEL_MATRIX"
                    if receipt.get("schema_version") == HISTORICAL_MATRIX_BACKTEST_SCHEMA
                    else "OFFICIAL_DEMO_METHOD_EXTENDED_PIT"
                ),
            ),
            "model_cell_id": receipt["model_cell_id"],
            "generated_at": receipt["generated_at"],
            "selection_eligible": receipt["selection_eligible"],
            "primary_signal": receipt["primary_signal"],
            "receipt_sha256": receipt_sha256,
            "signal_receipt_sha256": signal_receipt_sha256,
            "provider_receipt_sha256": provider_receipt_sha256,
            "backtest_code_sha256": receipt["backtest_code_sha256"],
            "strategy": receipt["strategy"],
            "execution": receipt["execution"],
            "support": receipt["support"],
            "metrics": receipt["metrics"],
            "qlib": receipt["qlib"],
            "curve_semantics": curve_semantics,
            "deviations": receipt["deviations"],
            "observability": receipt.get("observability"),
        }
        for identity in (
            "strategy_variant_id",
            "strategy_role",
            "comparison_group_id",
            "execution_domain",
            "online_paper_equivalent",
            "promotion_eligible",
            "source_backtest_id",
        ):
            result[identity] = entry[identity]
        evaluation_split = receipt.get(
            "evaluation_split", entry.get("evaluation_split", entry.get("selection_split"))
        )
        if evaluation_split not in {
            "validation_2025",
            "test_viewed_2026",
            "test_viewed_official_v3",
        }:
            raise RuntimeError("historical public split identity is invalid")
        result.update(
            {
                "evaluation_split": evaluation_split,
                "result_role": receipt.get(
                    "result_role",
                    entry.get("result_role", "TRAINING_VALIDATION_CHECKPOINT_SELECTION"),
                ),
                "used_for_selection": receipt.get(
                    "used_for_selection", entry.get("used_for_selection", True)
                ),
                "test_data_access": receipt.get(
                    "test_data_access", entry.get("test_data_access", "NOT_APPLICABLE")
                ),
            }
        )
        if "analysis_lock_sha256" in receipt:
            result["analysis_lock_sha256"] = receipt["analysis_lock_sha256"]
        return result

    @app.middleware("http")
    async def browser_boundary(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            allowed = {
                f"http://127.0.0.1:{active_settings.port}",
                f"http://localhost:{active_settings.port}",
            }
            if origin is not None and origin not in allowed:
                return Response(status_code=403, content="Origin is not allowed")
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/api/v1/health")
    def health() -> dict[str, object]:
        with database.connect() as connection:
            connection.execute("SELECT 1").fetchone()
        return {"status": "ok", "service": "elanquant-api"}

    def run_payload(row: sqlite3.Row) -> dict[str, object]:
        run: dict[str, object] = dict(row)
        with database.connect() as connection:
            snapshot = connection.execute(
                "SELECT * FROM data_snapshots WHERE id = ?", (run["snapshot_id"],)
            ).fetchone()
            models = connection.execute(
                """
                SELECT mv.* FROM inference_run_models irm
                JOIN model_versions mv ON mv.id = irm.model_version_id
                WHERE irm.run_id = ? ORDER BY mv.size, mv.variant
                """,
                (run["id"],),
            ).fetchall()
            evaluations = connection.execute(
                """
                SELECT * FROM run_model_evaluations
                WHERE run_id = ? ORDER BY base_model_id, split
                """,
                (run["id"],),
            ).fetchall()
            job_identity = connection.execute(
                """
                SELECT execution_profile, model_release, requested_device,
                    execution_receipt_json
                FROM jobs WHERE id = ?
                """,
                (run["job_id"],),
            ).fetchone()
            if not models and str(run["protocol"]).startswith("PLACEHOLDER"):
                models = connection.execute(
                    """
                    SELECT * FROM model_versions
                    WHERE status = 'PLACEHOLDER_ONLY' ORDER BY size, variant
                    """
                ).fetchall()
        model_rows = [dict(model) for model in models]
        checkpoint_material = "|".join(
            f"{model['id']}:{model['checkpoint_sha256']}" for model in model_rows
        )
        model_hash = hashlib.sha256(checkpoint_material.encode()).hexdigest()
        warnings: list[str] = []
        if str(run["protocol"]).startswith("PLACEHOLDER"):
            warnings.append("占位输出，不是市场数据、模型结论或投资建议。")
        elif not bool(run.get("scoreable")):
            warnings.append("这是最新在线预测，未来十个交易日标签尚未成熟，不能计入评估指标。")
        if run.get("paper_publication_state") == "LEGACY_MIXED_RUNS":
            warnings.append("该历史信号日包含多个运行来源；原始账本已保留且未被改写。")
        if run.get("paper_publication_state") == "SKIPPED_EXISTING_FROZEN_RUN":
            warnings.append("该信号日的模拟意图已由更早运行冻结；本次只更新研究结果。")
        evaluations_by_model: dict[str, dict[str, dict[str, object]]] = {}
        for evaluation in evaluations:
            raw = dict(evaluation)
            evaluations_by_model.setdefault(str(raw["base_model_id"]), {})[str(raw["split"])] = {
                "rank_ic": raw["rank_ic"],
                "pearson_ic": raw["ic"],
                "top10_mean_return": raw["top10_mean_return"],
                "rows": raw["rows"],
                "cross_sections": raw["cross_sections"],
                "anchor_set_sha256": raw["anchor_set_sha256"],
            }
        official_v3 = str(run["protocol"]).startswith("OFFICIAL_SPLIT_V3")
        expected_evaluation_splits = (
            {"test_viewed_official_v3"} if official_v3 else {"validation_2025", "test_viewed_2026"}
        )
        expected_model_count = 2 if official_v3 else 3
        formal_evidence_complete = (
            bool(run.get("evaluation_receipt_sha256"))
            and len(model_rows) == expected_model_count
            and all(
                set(evaluations_by_model.get(str(model["base_model_id"] or model["id"]), {}))
                == expected_evaluation_splits
                for model in model_rows
            )
        )
        if not formal_evidence_complete and not str(run["protocol"]).startswith("PLACEHOLDER"):
            warnings.append(
                "该历史运行缺少完整的逐运行评估回执；实验指标已阻止展示。"
                if official_v3
                else "该历史运行缺少逐运行的双分区正式评估回执；实验指标已阻止展示。"
            )
        track_by_variant = {
            "zero_shot": "zero_shot",
            "official_ft": "official_style",
            "strict_pit_ft": "strict_pit",
        }
        matrix = []
        for model in model_rows:
            variant = str(model["variant"]).split("@", 1)[0]
            track = track_by_variant.get(variant)
            public_evaluations = evaluations_by_model.get(
                str(model["base_model_id"] or model["id"]), {}
            )
            displayed_evaluation = (
                public_evaluations.get("test_viewed_official_v3", {}) if official_v3 else {}
            )
            matrix.append(
                {
                    "id": model["id"],
                    "model_size": model["size"],
                    "track": track or "zero_shot",
                    "state": (
                        "passed"
                        if formal_evidence_complete
                        and track is not None
                        and model["status"] == "PASS"
                        and model["evaluation_receipt_sha256"]
                        else "blocked"
                    ),
                    "rank_ic": (
                        displayed_evaluation.get("rank_ic")
                        if official_v3 and formal_evidence_complete
                        else model["validation_rank_ic"]
                        if formal_evidence_complete
                        else None
                    ),
                    "pearson_ic": (
                        displayed_evaluation.get("pearson_ic")
                        if official_v3 and formal_evidence_complete
                        else model["validation_ic"]
                        if formal_evidence_complete
                        else None
                    ),
                    "top10_mean_return": (
                        displayed_evaluation.get("top10_mean_return")
                        if official_v3 and formal_evidence_complete
                        else model["validation_top10_mean_return"]
                        if formal_evidence_complete
                        else None
                    ),
                    "model_hash": model["checkpoint_sha256"],
                    "receipt": (model["evaluation_receipt"] if formal_evidence_complete else None),
                    "evaluations": (public_evaluations if formal_evidence_complete else {}),
                    "note": (
                        f"未知模型变体 {variant}；已阻止展示为正式实验。"
                        if track is None
                        else warnings[0]
                        if warnings
                        else None
                    ),
                }
            )
        snapshot_dict = {} if snapshot is None else dict(snapshot)
        data_health: dict[str, object] | None = None
        if snapshot_dict.get("summary_json"):
            parsed = json.loads(str(snapshot_dict["summary_json"]))
            if isinstance(parsed, dict):
                data_health = parsed
        return {
            "id": run["id"],
            "as_of": run["as_of_session"],
            "status": "success" if run["status"] == "SUCCEEDED" else str(run["status"]).lower(),
            "created_at": run["created_at"],
            "model_id": (
                f"{job_identity['model_release']}-official-ft"
                if official_v3 and job_identity is not None
                else "small-strict-pit"
            ),
            "protocol": run["protocol"],
            "model_versions": [model["id"] for model in model_rows],
            "scoreable": bool(run.get("scoreable")),
            "viewed_test": formal_evidence_complete,
            "provenance": {
                "data_hash": snapshot_dict.get("manifest_sha256", ""),
                "model_hash": model_hash,
                "tokenizer_hash": hashlib.sha256(
                    "|".join(str(model["tokenizer_sha256"] or "") for model in model_rows).encode()
                ).hexdigest(),
                "config_hash": str(run.get("config_sha256") or ""),
                "code_hash": str(run.get("code_sha256") or ""),
                "evaluation_hash": str(run.get("evaluation_receipt_sha256") or ""),
            },
            "warnings": warnings,
            "paper_publication": {
                "state": run.get("paper_publication_state"),
                "source_run_id": run.get("paper_publication_run_id"),
            },
            "execution": (
                {
                    "profile": job_identity["execution_profile"],
                    "model_release": job_identity["model_release"],
                    "requested_device": job_identity["requested_device"],
                    "receipt_available": job_identity["execution_receipt_json"] is not None,
                }
                if job_identity is not None
                else None
            ),
            "data_health": data_health,
            "experiment_matrix": matrix,
        }

    @app.get("/api/v1/system/status")
    def system_status() -> dict[str, object]:
        with database.connect() as connection:
            active = connection.execute(
                """
                SELECT id FROM jobs WHERE status IN ('QUEUED', 'RUNNING')
                ORDER BY created_at LIMIT 1
                """
            ).fetchone()
            latest = connection.execute(
                """
                SELECT as_of_session, id, status
                FROM inference_runs
                WHERE COALESCE(paper_publication_state, '')
                      != 'RESEARCH_ONLY_NOT_PUBLISHED'
                ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
            snapshot = connection.execute(
                "SELECT as_of_session FROM data_snapshots ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            worker = connection.execute(
                "SELECT * FROM service_heartbeats WHERE service = 'worker'"
            ).fetchone()
        latest_session = None if latest is None else str(latest["as_of_session"])
        data_session = None if snapshot is None else str(snapshot["as_of_session"])
        warnings: list[str] = []
        worker_ready = False
        if worker is None:
            warnings.append("Worker 尚未写入心跳；API可访问不代表推理可执行。")
        else:
            heartbeat_at = datetime.fromisoformat(str(worker["heartbeat_at"]))
            worker_ready = datetime.now(UTC) - heartbeat_at <= timedelta(seconds=15)
            if not worker_ready:
                warnings.append("Worker 心跳已过期；请检查服务状态。")
        if active_settings.pipeline_mode == "real":
            if not active_settings.matrix_receipt.is_file():
                warnings.append("正式训练矩阵回执尚未发布。")
            if not active_settings.evaluation_receipt.is_file():
                warnings.append("正式评估回执尚未发布。")
        primary_model = None
        if latest is not None and active_settings.matrix_receipt.is_file():
            try:
                matrix_schema = json.loads(
                    active_settings.matrix_receipt.read_text(encoding="utf-8")
                ).get("schema_version")
            except (OSError, json.JSONDecodeError, AttributeError):
                matrix_schema = None
                warnings.append("训练矩阵回执无法安全解析。")
            primary_model = (
                f"{active_settings.model_release}-official-ft"
                if matrix_schema == "elanquant_kronos_four_cell_matrix_v3"
                else "small-strict-pit"
                if matrix_schema == "elanquant_training_matrix_v2"
                else None
            )
        return {
            "status": "ok",
            "service_state": "ready" if worker_ready and not warnings else "degraded",
            "server_time": datetime.now(UTC).isoformat(),
            "latest_closed_session": data_session,
            "data_as_of": data_session,
            "inference_as_of": latest_session,
            "active_job_id": None if active is None else str(active["id"]),
            "primary_model": primary_model,
            "warnings": warnings,
            "active_jobs": 0 if active is None else 1,
            "latest_run": None if latest is None else dict(latest),
            "execution_mode": (
                "REAL_MODEL_INFERENCE"
                if active_settings.pipeline_mode == "real"
                else "PLACEHOLDER_RESEARCH_ONLY"
            ),
            "execution_profile": active_profile.id,
            "model_release": active_settings.model_release,
            "execution_device": active_settings.execution_device,
            "inference_batch_size": active_settings.inference_batch_size,
            "release_research_only": active_profile.is_research_only(active_settings.model_release),
            "available_releases": list(active_profile.allowed_releases),
            "broker_connected": False,
            "automatic_schedule": False,
        }

    @app.get("/api/v1/research/experiments")
    def research_experiments() -> dict[str, object]:
        if not active_settings.research_catalog.is_file():
            return {"generated_at": None, "experiments": []}
        try:
            payload = json.loads(active_settings.research_catalog.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise HTTPException(
                status_code=503, detail="Research catalog could not be read safely"
            ) from error
        try:
            if (
                isinstance(payload, dict)
                and payload.get("schema_version") == "elanquant_kronos_rolling_evaluation_v3"
            ):
                release_root = active_settings.matrix_receipt.resolve().parent
                manifest_path = release_root / "manifest.json"
                method_lock_path = release_root / "online-method-lock.json"
                analysis_lock_path = release_root / "analysis-lock.json"
                historical_path = release_root / "historical-catalog.json"
                matrix_payload = json.loads(
                    active_settings.matrix_receipt.read_text(encoding="utf-8")
                )
                release_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                method_lock = validate_method_lock(
                    json.loads(method_lock_path.read_text(encoding="utf-8"))
                )
                analysis_lock = validate_analysis_lock(
                    json.loads(analysis_lock_path.read_text(encoding="utf-8"))
                )
                if release_payload.get("schema_version") == COMPATIBILITY_RELEASE_SCHEMA:
                    source_root = active_settings.execution_profiles_root.resolve().parents[1]
                    release, _, _ = validate_compatibility_release_dir(
                        release_root,
                        adapter_path=source_root
                        / "scripts/server/adapt_online_snapshot_official_split_v3.py",
                        fetcher_path=source_root / "scripts/server/fetch_online_snapshot.py",
                    )
                else:
                    release = validate_release(release_payload)
                matrix_sha = sha256_file(active_settings.matrix_receipt)
                if (
                    release.get("online_method_lock_sha256") != sha256_file(method_lock_path)
                    or release.get("analysis_lock_sha256") != sha256_file(analysis_lock_path)
                    or release.get("historical_catalog_sha256") != sha256_file(historical_path)
                    or method_lock.get("training_matrix_sha256") != matrix_sha
                    or method_lock.get("online_runner_sha256")
                    != release.get("online_runner_sha256")
                    or method_lock.get("online_contract_sha256")
                    != sha256_file(Path(str(online_release_contract.__file__)).resolve())
                    or analysis_lock.get("matrix_sha256") != matrix_sha
                    or method_lock.get("viewed_results_root") != analysis_lock.get("results_root")
                ):
                    raise RuntimeError("official-split-v3 active release chain is mismatched")
                experiments = official_split_v3_experiments(
                    payload,
                    matrix_payload,
                    sha256_file(active_settings.research_catalog),
                    matrix_sha,
                    release,
                )
                return {"generated_at": payload.get("generated_at"), "experiments": experiments}
            validated = validate_research_catalog(payload)
        except (
            KeyError,
            OSError,
            json.JSONDecodeError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as error:
            raise HTTPException(
                status_code=503, detail="Research catalog failed its receipt gate"
            ) from error
        return {
            "generated_at": validated.get("generated_at"),
            "experiments": validated["experiments"],
        }

    @app.get("/api/v1/research/backtests")
    def research_backtests() -> dict[str, object]:
        catalog, loaded = load_historical_backtests()
        if not loaded:
            return {"available": False, "generated_at": None, "backtests": []}
        if catalog is None:
            raise HTTPException(status_code=503, detail="Historical catalog disappeared")
        return {
            "available": True,
            "generated_at": catalog["generated_at"],
            "backtests": [
                public_backtest(entry, receipt, str(entry["receipt_sha256"]))
                for entry, receipt in loaded.values()
            ],
        }

    @app.get("/api/v1/research/comparisons")
    def research_comparisons() -> dict[str, object]:
        """Return the separately sealed B2/Kronos common-weekly comparison.

        Absence is normal before the server-only producer finishes; a malformed
        or tampered catalog deliberately returns 503 through the loader.
        """
        return load_unified_comparison()

    @app.get("/api/v1/research/backtests/{backtest_id}")
    def research_backtest(backtest_id: str) -> dict[str, object]:
        _, loaded = load_historical_backtests()
        selected = loaded.get(backtest_id)
        if selected is None:
            raise HTTPException(status_code=404, detail="Historical backtest not found")
        entry, receipt = selected
        return {"backtest": public_backtest(entry, receipt, str(entry["receipt_sha256"]))}

    @app.get("/api/v1/research/backtests/{backtest_id}/series")
    def research_backtest_series(
        backtest_id: str,
        signal: Annotated[str, Query()] = "mean",
    ) -> dict[str, object]:
        catalog, loaded = load_historical_backtests()
        selected = loaded.get(backtest_id)
        if selected is None:
            raise HTTPException(status_code=404, detail="Historical backtest not found")
        if catalog is None:
            raise HTTPException(status_code=503, detail="Historical catalog disappeared")
        _, receipt = selected
        if signal not in OFFICIAL_DEMO_SIGNALS:
            raise HTTPException(status_code=422, detail="Unsupported official demo signal")
        try:
            root = historical_artifact_root(catalog)
        except RuntimeError as error:
            raise HTTPException(
                status_code=503, detail="Historical series is unavailable"
            ) from error
        official_v3 = receipt.get("schema_version") == OFFICIAL_SPLIT_V3_BACKTEST_SCHEMA
        artifact = (
            {
                "path": receipt["daily_series_path"],
                "sha256": receipt["daily_series_sha256"],
            }
            if official_v3
            else receipt["artifacts"]["daily_series"]
        )
        artifact_path = (root / str(artifact["path"])).resolve()
        if root not in artifact_path.parents or not artifact_path.is_file():
            raise HTTPException(status_code=503, detail="Historical series is unavailable")
        if sha256_file(artifact_path) != artifact["sha256"]:
            raise HTTPException(status_code=503, detail="Historical series hash mismatch")
        required = (
            {
                "datetime",
                "signal",
                "return",
                "cost",
                "benchmark",
                "strategy_with_cost",
                "benchmark_curve",
                "excess_with_cost",
            }
            if official_v3
            else {
                "datetime",
                "signal",
                "additive_strategy_with_cost",
                "additive_benchmark",
                "additive_excess_with_cost",
                "compounded_strategy_nav",
                "compounded_benchmark_nav",
            }
        )
        points: list[dict[str, object]] = []
        strategy_nav = 1.0
        benchmark_nav = 1.0
        try:
            with artifact_path.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                    raise RuntimeError("historical series columns are incomplete")
                for row in reader:
                    if row["signal"] != signal:
                        continue
                    if official_v3:
                        daily_return = float(row["return"])
                        daily_cost = float(row["cost"])
                        daily_benchmark = float(row["benchmark"])
                        strategy_nav *= 1.0 + daily_return - daily_cost
                        benchmark_nav *= 1.0 + daily_benchmark
                        values = {
                            "strategy": float(row["strategy_with_cost"]),
                            "benchmark": float(row["benchmark_curve"]),
                            "excess": float(row["excess_with_cost"]),
                            "strategy_nav": strategy_nav,
                            "benchmark_nav": benchmark_nav,
                        }
                    else:
                        values = {
                            "strategy": float(row["additive_strategy_with_cost"]),
                            "benchmark": float(row["additive_benchmark"]),
                            "excess": float(row["additive_excess_with_cost"]),
                            "strategy_nav": float(row["compounded_strategy_nav"]),
                            "benchmark_nav": float(row["compounded_benchmark_nav"]),
                        }
                    if not all(math.isfinite(value) for value in values.values()):
                        raise RuntimeError("historical series contains a non-finite value")
                    optional_values: dict[str, float | None] = {}
                    for identity in ("turnover", "position_count"):
                        raw = row.get(identity)
                        if raw is None or raw == "":
                            optional_values[identity] = None
                            continue
                        value = float(str(raw))
                        if not math.isfinite(value):
                            raise RuntimeError(
                                f"historical series contains a non-finite {identity}"
                            )
                        optional_values[identity] = value
                    points.append({"session": row["datetime"], **values, **optional_values})
        except (OSError, TypeError, ValueError, RuntimeError) as error:
            raise HTTPException(
                status_code=503, detail="Historical series failed its evidence gate"
            ) from error
        if (
            not points
            or len(points) > 1000
            or len(points) != receipt["support"]["sessions"]
            or [point["session"] for point in points]
            != sorted({str(point["session"]) for point in points})
        ):
            raise HTTPException(status_code=503, detail="Historical series support is invalid")
        return {
            "backtest_id": receipt["id"],
            "signal": signal,
            "curve_semantics": receipt.get("curve_semantics", HISTORICAL_CURVE_SEMANTICS),
            "points": points,
        }

    @app.get("/api/v1/research/backtests/{backtest_id}/holdings")
    def research_backtest_holdings(
        backtest_id: str,
        session: Annotated[date | None, Query()] = None,
    ) -> dict[str, object]:
        catalog, loaded = load_historical_backtests()
        selected = loaded.get(backtest_id)
        if selected is None:
            raise HTTPException(status_code=404, detail="Historical backtest not found")
        if catalog is None:
            raise HTTPException(status_code=503, detail="Historical catalog disappeared")
        entry, receipt = selected
        official_v3 = receipt.get("schema_version") == OFFICIAL_SPLIT_V3_BACKTEST_SCHEMA
        holdings_pointer = entry.get("holdings")
        sidecar_holdings = isinstance(holdings_pointer, dict) and set(holdings_pointer) == {
            "receipt_path",
            "receipt_sha256",
        }
        matrix_holdings = isinstance(holdings_pointer, dict) and set(holdings_pointer) == {
            "artifact_path",
            "artifact_sha256",
        }
        if official_v3:
            holdings_pointer = {
                "artifact_path": receipt["holdings_path"],
                "artifact_sha256": receipt["holdings_sha256"],
            }
            matrix_holdings = True
        if not sidecar_holdings and not matrix_holdings:
            raise HTTPException(
                status_code=404,
                detail="Historical holdings are unavailable for this backtest",
            )
        assert isinstance(holdings_pointer, dict)
        holdings_receipt_sha256 = str(
            entry["receipt_sha256"] if matrix_holdings else holdings_pointer["receipt_sha256"]
        )
        try:
            root = historical_artifact_root(catalog)
        except RuntimeError as error:
            raise HTTPException(
                status_code=503, detail="Historical holdings evidence mismatch"
            ) from error
        if matrix_holdings:
            artifact = (
                {
                    "path": receipt["holdings_path"],
                    "sha256": receipt["holdings_sha256"],
                    "schema_version": "elanquant_historical_model_holdings_v1",
                    "columns": list(HOLDINGS_COLUMNS),
                    "sessions": receipt["support"]["sessions"],
                }
                if official_v3
                else receipt.get("artifacts", {}).get("holdings")
            )
            if (
                not isinstance(artifact, dict)
                or artifact.get("path") != holdings_pointer.get("artifact_path")
                or artifact.get("sha256") != holdings_pointer.get("artifact_sha256")
            ):
                raise HTTPException(
                    status_code=503,
                    detail="Historical matrix holdings identity mismatch",
                )
        else:
            sidecar_path = (root / str(holdings_pointer.get("receipt_path"))).resolve()
            try:
                if (
                    root not in sidecar_path.parents
                    or not sidecar_path.is_file()
                    or sidecar_path.stat().st_size > 1_000_000
                    or not valid_sha256(holdings_pointer.get("receipt_sha256"))
                    or sha256_file(sidecar_path) != holdings_pointer["receipt_sha256"]
                ):
                    raise RuntimeError("historical holdings receipt mismatch")
            except (OSError, RuntimeError) as error:
                raise HTTPException(
                    status_code=503, detail="Historical holdings receipt mismatch"
                ) from error
            try:
                sidecar = validate_holdings_receipt(
                    json.loads(sidecar_path.read_text(encoding="utf-8"))
                )
                artifact = sidecar["artifact"]
                receipt_signal_sha256 = receipt.get(
                    "signal_receipt_sha256", receipt.get("source_signal_receipt_sha256")
                )
                receipt_provider_sha256 = receipt.get(
                    "provider_receipt_sha256",
                    receipt.get("source_provider_receipt_sha256"),
                )
                if (
                    sidecar.get("backtest_id") != receipt["id"]
                    or sidecar.get("evaluation_split") != entry["evaluation_split"]
                    or sidecar.get("strategy_variant_id") != entry["strategy_variant_id"]
                    or sidecar.get("execution_domain") != "HISTORICAL_QLIB_SIMULATION"
                    or sidecar.get("online_paper_equivalent") is not False
                    or sidecar.get("promotion_eligible") is not False
                    or sidecar.get("backtest_receipt_path") != entry["receipt_path"]
                    or sidecar.get("backtest_receipt_sha256") != entry["receipt_sha256"]
                    or sidecar.get("source_signal_receipt_sha256") != receipt_signal_sha256
                    or sidecar.get("source_provider_receipt_sha256") != receipt_provider_sha256
                    or not isinstance(artifact, dict)
                ):
                    raise RuntimeError("historical holdings sidecar identity is invalid")
            except (
                KeyError,
                OSError,
                json.JSONDecodeError,
                RuntimeError,
                TypeError,
            ) as error:
                raise HTTPException(
                    status_code=503,
                    detail="Historical holdings receipt failed its evidence gate",
                ) from error
        artifact_path = (root / str(artifact.get("path"))).resolve()
        try:
            artifact_bytes = artifact_path.stat().st_size
            if (
                root not in artifact_path.parents
                or not artifact_path.is_file()
                or (not official_v3 and artifact_bytes != artifact.get("bytes"))
                or artifact_bytes > 64_000_000
                or not valid_sha256(artifact.get("sha256"))
                or sha256_file(artifact_path) != artifact["sha256"]
                or artifact.get("schema_version")
                not in {
                    "elanquant_historical_daily_holdings_v1",
                    "elanquant_historical_model_holdings_v1",
                }
                or artifact.get("columns") != list(HOLDINGS_COLUMNS)
                or (not official_v3 and artifact.get("rows", 200_001) > 200_000)
                or artifact.get("sessions", 1_001) > 1000
            ):
                raise RuntimeError("historical holdings evidence mismatch")
        except (OSError, RuntimeError) as error:
            raise HTTPException(
                status_code=503, detail="Historical holdings evidence mismatch"
            ) from error
        required = list(HOLDINGS_COLUMNS)
        rows: list[dict[str, object]] = []
        try:
            with artifact_path.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames != required:
                    raise RuntimeError("historical holdings columns are not exact")
                for raw in reader:
                    instrument = raw["instrument"]
                    parsed_session = date.fromisoformat(raw["session"])
                    if raw["signal"] not in OFFICIAL_DEMO_SIGNALS:
                        raise RuntimeError("historical holding signal is invalid")
                    if raw["is_empty"] not in {"True", "False"}:
                        raise RuntimeError("historical holding empty marker is invalid")
                    is_empty = raw["is_empty"] == "True"
                    if (not is_empty and not instrument) or len(instrument) > 32:
                        raise RuntimeError("historical holding instrument is invalid")
                    values: dict[str, float] = {}
                    for identity in ("amount", "weight", "value"):
                        cell = raw[identity]
                        value = float(cell)
                        if not math.isfinite(value) or value < 0:
                            raise RuntimeError("historical holding value is not finite")
                        values[identity] = value
                    if values["weight"] > 1:
                        raise RuntimeError("historical holding weight is invalid")
                    if is_empty and (instrument or any(value != 0 for value in values.values())):
                        raise RuntimeError("historical empty holding row is invalid")
                    rows.append(
                        {
                            "session": parsed_session.isoformat(),
                            "signal": raw["signal"],
                            "is_empty": is_empty,
                            "instrument": instrument,
                            **values,
                        }
                    )
                    if len(rows) > 200_000:
                        raise RuntimeError("historical holdings artifact is unbounded")
            observed_support = validate_holdings_records(
                rows,
                expected_sessions=artifact["sessions"],
            )
            support_fields = (
                ("sessions",)
                if official_v3
                else (
                    "rows",
                    "sessions",
                    "session_signal_pairs",
                    "empty_session_signal_pairs",
                )
            )
            if any(observed_support[identity] != artifact[identity] for identity in support_fields):
                raise RuntimeError("historical holdings support receipt disagrees")
        except (OSError, TypeError, ValueError, RuntimeError) as error:
            raise HTTPException(
                status_code=503, detail="Historical holdings failed its evidence gate"
            ) from error
        primary_rows = [row for row in rows if row["signal"] == receipt["primary_signal"]]
        sessions = sorted({str(row["session"]) for row in primary_rows})
        if not sessions or len(sessions) > 1000:
            raise HTTPException(status_code=503, detail="Historical holdings support is invalid")
        selected_session = session.isoformat() if session is not None else sessions[-1]
        if selected_session not in sessions:
            raise HTTPException(status_code=404, detail="Historical holdings session not found")
        holdings = [
            {
                "instrument": row["instrument"],
                "amount": row["amount"],
                "weight": row["weight"],
                "value": row["value"],
            }
            for row in primary_rows
            if row["session"] == selected_session and row["is_empty"] is False
        ]
        empty_rows = [
            row
            for row in primary_rows
            if row["session"] == selected_session and row["is_empty"] is True
        ]
        if (
            len(holdings) > 500
            or len({str(row["instrument"]) for row in holdings}) != len(holdings)
            or (not holdings and len(empty_rows) != 1)
            or (holdings and empty_rows)
        ):
            raise HTTPException(status_code=503, detail="Historical holdings rows are invalid")
        return {
            "backtest_id": receipt["id"],
            "available": True,
            "sessions": sessions,
            "default_session": sessions[-1],
            "selected_session": selected_session,
            "signal": receipt["primary_signal"],
            "empty": not holdings,
            "source": {
                "artifact_sha256": artifact["sha256"],
                "receipt_sha256": holdings_receipt_sha256,
                "backtest_receipt_sha256": entry["receipt_sha256"],
            },
            "holdings": holdings,
        }

    @app.post("/api/v1/jobs/update-infer", status_code=status.HTTP_202_ACCEPTED)
    def submit_update_infer(payload: UpdateInferRequest, response: Response) -> dict[str, object]:
        requested_profile = payload.execution_profile or active_profile.id
        if requested_profile != active_profile.id:
            raise HTTPException(
                status_code=409,
                detail="Requested execution profile differs from this deployment",
            )
        requested_release = payload.model_release or active_settings.model_release
        try:
            active_profile.validate_request(requested_release, active_settings.execution_device)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        job, created = jobs.submit_update_infer(
            payload.target_session,
            force=payload.force,
            execution_profile=requested_profile,
            model_release=requested_release,
            requested_device=active_settings.execution_device,
        )
        response.headers["Location"] = f"/api/v1/jobs/{job['id']}"
        return {"created": created, "job": job}

    @app.get("/api/v1/jobs")
    def list_jobs(limit: Annotated[int, Query(ge=1, le=200)] = 50) -> dict[str, object]:
        return {"jobs": jobs.list(limit)}

    @app.get("/api/v1/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, object]:
        try:
            return jobs.get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Job not found") from error

    @app.post("/api/v1/jobs/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
    def retry_job(job_id: str, response: Response) -> dict[str, object]:
        try:
            job = jobs.retry(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Job not found") from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        response.headers["Location"] = f"/api/v1/jobs/{job['id']}"
        return job

    @app.get("/api/v1/runs/latest")
    def latest_run() -> dict[str, object]:
        with database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM inference_runs
                WHERE status = 'SUCCEEDED'
                  AND COALESCE(paper_publication_state, '')
                      != 'RESEARCH_ONLY_NOT_PUBLISHED'
                ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="No completed run")
        return run_payload(row)

    @app.get("/api/v1/runs")
    def list_runs(limit: Annotated[int, Query(ge=1, le=50)] = 10) -> dict[str, object]:
        with database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, as_of_session, status, protocol, created_at,
                    finished_at, scoreable, matrix_receipt_sha256,
                    evaluation_receipt_sha256, config_sha256, code_sha256,
                    paper_publication_state,
                    paper_publication_run_id
                FROM inference_runs WHERE status = 'SUCCEEDED'
                ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return {"runs": [dict(row) for row in rows]}

    def strict_ranks(connection: sqlite3.Connection, run_id: str) -> dict[str, int]:
        run = connection.execute(
            "SELECT protocol FROM inference_runs WHERE id = ?", (run_id,)
        ).fetchone()
        suffix = (
            "%-official-ft"
            if run is not None and str(run["protocol"]).startswith("OFFICIAL_SPLIT_V3")
            else "%-strict-pit"
        )
        return {
            str(row["code"]): int(row["rank"])
            for row in connection.execute(
                """
                SELECT ss.code, ss.rank FROM stock_scores ss
                JOIN inference_run_models irm
                  ON irm.run_id = ss.run_id AND irm.model_version_id = ss.model_version_id
                WHERE ss.run_id = ? AND irm.base_model_id LIKE ?
                """,
                (run_id, suffix),
            ).fetchall()
        }

    @app.get("/api/v1/runs/{run_id}/diff")
    def run_diff(run_id: str, against: str | None = None) -> dict[str, object]:
        with database.connect() as connection:
            current = connection.execute(
                "SELECT * FROM inference_runs WHERE id = ? AND status = 'SUCCEEDED'", (run_id,)
            ).fetchone()
            if current is None:
                raise HTTPException(status_code=404, detail="Run not found")
            baseline = (
                connection.execute(
                    "SELECT * FROM inference_runs WHERE id = ? AND status = 'SUCCEEDED'",
                    (against,),
                ).fetchone()
                if against is not None
                else connection.execute(
                    """
                    SELECT * FROM inference_runs
                    WHERE status = 'SUCCEEDED' AND (created_at < ? OR (created_at = ? AND id < ?))
                    ORDER BY created_at DESC, id DESC LIMIT 1
                    """,
                    (current["created_at"], current["created_at"], run_id),
                ).fetchone()
            )
            current_ranks = strict_ranks(connection, run_id)
            baseline_ranks = (
                {} if baseline is None else strict_ranks(connection, str(baseline["id"]))
            )
        if baseline is None:
            return {
                "run_id": run_id,
                "against_run_id": None,
                "comparable": False,
                "reason": "NO_PREVIOUS_COMPLETED_RUN",
            }
        common = set(current_ranks) & set(baseline_ranks)
        minimum_coverage = 250
        if (
            len(current_ranks) < minimum_coverage
            or len(baseline_ranks) < minimum_coverage
            or len(common) < minimum_coverage
        ):
            return {
                "run_id": run_id,
                "against_run_id": str(baseline["id"]),
                "comparable": False,
                "reason": "STRICT_RANK_COVERAGE_INCOMPLETE",
                "coverage": {
                    "current": len(current_ranks),
                    "baseline": len(baseline_ranks),
                    "common": len(common),
                    "required": minimum_coverage,
                },
            }
        current_top3 = {code for code, rank in current_ranks.items() if rank <= 3}
        baseline_top3 = {code for code, rank in baseline_ranks.items() if rank <= 3}
        current_top10 = {code for code, rank in current_ranks.items() if rank <= 10}
        baseline_top10 = {code for code, rank in baseline_ranks.items() if rank <= 10}
        largest_changes = sorted(
            (
                {
                    "code": code,
                    "from_rank": baseline_ranks[code],
                    "to_rank": current_ranks[code],
                    "delta": baseline_ranks[code] - current_ranks[code],
                }
                for code in common
            ),
            key=lambda item: (-abs(int(item["delta"])), str(item["code"])),
        )[:20]
        fields = (
            "snapshot_id",
            "matrix_receipt_sha256",
            "evaluation_receipt_sha256",
            "config_sha256",
            "code_sha256",
        )
        return {
            "run_id": run_id,
            "against_run_id": str(baseline["id"]),
            "comparable": True,
            "same_session": current["as_of_session"] == baseline["as_of_session"],
            "identity_changes": {field: current[field] != baseline[field] for field in fields},
            "top3_overlap": len(current_top3 & baseline_top3),
            "top10_overlap": len(current_top10 & baseline_top10),
            "top3_added": sorted(current_top3 - baseline_top3),
            "top3_dropped": sorted(baseline_top3 - current_top3),
            "largest_rank_changes": largest_changes,
        }

    @app.get("/api/v1/runs/{run_id}/data-health")
    def run_data_health(run_id: str) -> dict[str, object]:
        with database.connect() as connection:
            row = connection.execute(
                """
                SELECT ds.* FROM inference_runs ir
                JOIN data_snapshots ds ON ds.id = ir.snapshot_id
                WHERE ir.id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Run not found")
        summary: dict[str, object] = {
            "status": row["status"],
            "resolved_session": row["as_of_session"],
            "eligible_symbols": row["row_count"],
        }
        if row["summary_json"]:
            parsed = json.loads(str(row["summary_json"]))
            if isinstance(parsed, dict):
                summary = parsed
        return {
            "run_id": run_id,
            "manifest_sha256": row["manifest_sha256"],
            "summary": summary,
        }

    @app.get("/api/v1/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, object]:
        with database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM inference_runs WHERE id = ?", (run_id,)
            ).fetchone()
            recommendations = connection.execute(
                """
                SELECT ri.* FROM recommendation_items ri
                JOIN recommendation_sets rs ON rs.id = ri.recommendation_set_id
                WHERE rs.run_id = ? ORDER BY ri.rank
                """,
                (run_id,),
            ).fetchall()
        if row is None:
            raise HTTPException(status_code=404, detail="Run not found")
        safe_run = dict(row)
        safe_run.pop("artifact_path", None)
        return {"run": safe_run, "recommendations": [dict(item) for item in recommendations]}

    @app.get("/api/v1/runs/{run_id}/scores")
    def run_scores(run_id: str, model_id: str | None = None) -> dict[str, object]:
        query = """
            SELECT ss.*, irm.base_model_id FROM stock_scores ss
            JOIN inference_run_models irm
              ON irm.run_id = ss.run_id AND irm.model_version_id = ss.model_version_id
            WHERE ss.run_id = ?
        """
        params: tuple[str, ...] = (run_id,)
        if model_id is not None:
            query += " AND (ss.model_version_id = ? OR irm.base_model_id = ?)"
            params = (run_id, model_id, model_id)
        query += " ORDER BY irm.base_model_id, ss.rank"
        with database.connect() as connection:
            exists = connection.execute(
                "SELECT * FROM inference_runs WHERE id = ?", (run_id,)
            ).fetchone()
            rows = connection.execute(query, params).fetchall()
            previous = (
                None
                if exists is None
                else connection.execute(
                    """
                    SELECT id FROM inference_runs
                    WHERE status = 'SUCCEEDED'
                      AND (created_at < ? OR (created_at = ? AND id < ?))
                    ORDER BY created_at DESC, id DESC LIMIT 1
                    """,
                    (exists["created_at"], exists["created_at"], run_id),
                ).fetchone()
            )
            previous_ranks = (
                {} if previous is None else strict_ranks(connection, str(previous["id"]))
            )
            recommended = {
                str(row["code"])
                for row in connection.execute(
                    """
                    SELECT ri.code FROM recommendation_items ri
                    JOIN recommendation_sets rs ON rs.id = ri.recommendation_set_id
                    WHERE rs.run_id = ?
                    """,
                    (run_id,),
                ).fetchall()
            }
            decisions = {
                str(row["code"]): dict(row)
                for row in connection.execute(
                    "SELECT * FROM paper_intent_decisions WHERE run_id = ?", (run_id,)
                ).fetchall()
            }
        if exists is None:
            raise HTTPException(status_code=404, detail="Run not found")
        by_code: dict[str, dict[str, object]] = {}
        for raw in rows:
            row = dict(raw)
            code = str(row["code"])
            item = by_code.setdefault(
                code,
                {
                    "code": code,
                    "name": row["name"],
                    "values": [],
                    "primary_values": [],
                    "model_scores": {},
                    "reference_price": row["reference_price"],
                    "eligible": True,
                },
            )
            values = item["values"]
            primary_values = item["primary_values"]
            scores = item["model_scores"]
            assert isinstance(values, list)
            assert isinstance(primary_values, list)
            assert isinstance(scores, dict)
            score = float(row["score"])
            values.append(score)
            base_model_id = str(row["base_model_id"])
            official_v3 = str(exists["protocol"]).startswith("OFFICIAL_SPLIT_V3")
            if (official_v3 and base_model_id.endswith("official-ft")) or (
                not official_v3 and base_model_id.endswith("strict-pit")
            ):
                primary_values.append(score)
            scores[base_model_id] = score
            if str(row["scoreability"]).startswith("PLACEHOLDER"):
                item["eligible"] = False
        aggregated = []
        for item in by_code.values():
            values = item.pop("values")
            primary_values = item.pop("primary_values")
            assert isinstance(values, list)
            assert isinstance(primary_values, list)
            consensus_values = primary_values or values
            consensus = sum(consensus_values) / len(consensus_values)
            item["model_spread"] = max(values) - min(values) if values else None
            aggregated.append((consensus, item))
        aggregated.sort(key=lambda pair: (-pair[0], str(pair[1]["code"])))
        scores_payload = []
        for rank, (consensus, item) in enumerate(aggregated, start=1):
            eligible = bool(item.pop("eligible"))
            scores_payload.append(
                {
                    **item,
                    "rank": rank,
                    "score": consensus,
                    "forecast_return": consensus,
                    "coverage": 1.0 if eligible else 0.0,
                    "input_completeness": 1.0 if eligible else 0.0,
                    "eligible": eligible,
                    "model_spread": item.pop("model_spread"),
                    "previous_rank": previous_ranks.get(str(item["code"])),
                    "rank_delta": (
                        None
                        if str(item["code"]) not in previous_ranks
                        else previous_ranks[str(item["code"])] - rank
                    ),
                    "selected_top3": str(item["code"]) in recommended,
                    "paper_decision": decisions.get(str(item["code"]), {}).get("decision"),
                    "paper_reason": decisions.get(str(item["code"]), {}).get("reason"),
                    "explanation": (
                        "严格PIT轨驱动排名；三轨分歧只用于解释，不代表置信区间。"
                        if eligible
                        else "占位分数，不可用于研究结论或投资决策。"
                    ),
                    "forecast": [],
                }
            )
        return {"scores": scores_payload}

    @app.get("/api/v1/runs/{run_id}/stocks/{code}")
    def stock_detail(run_id: str, code: str) -> dict[str, object]:
        with database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM stock_scores WHERE run_id = ? AND code = ?
                ORDER BY model_version_id
                """,
                (run_id, code),
            ).fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail="Stock score not found")
        return {"code": code, "models": [dict(row) for row in rows]}

    @app.get("/api/v1/paper/account")
    def paper_account() -> dict[str, object]:
        with database.connect() as connection:
            account = connection.execute(
                "SELECT * FROM paper_accounts WHERE id = ?", (ACCOUNT_ID,)
            ).fetchone()
            positions = connection.execute(
                "SELECT * FROM paper_positions WHERE account_id = ? ORDER BY code", (ACCOUNT_ID,)
            ).fetchall()
            pending = connection.execute(
                """
                SELECT * FROM paper_orders WHERE account_id = ? AND status = 'PENDING'
                ORDER BY due_session, created_at
                """,
                (ACCOUNT_ID,),
            ).fetchall()
            latest_snapshot = connection.execute(
                """
                SELECT * FROM portfolio_snapshots WHERE account_id = ?
                ORDER BY as_of_session DESC LIMIT 1
                """,
                (ACCOUNT_ID,),
            ).fetchone()
            snapshot_valuations = (
                []
                if latest_snapshot is None
                else connection.execute(
                    """
                    SELECT * FROM portfolio_position_valuations
                    WHERE snapshot_id = ? ORDER BY code
                    """,
                    (latest_snapshot["id"],),
                ).fetchall()
            )
            gaps = connection.execute(
                "SELECT session FROM paper_gaps WHERE account_id = ? ORDER BY session",
                (ACCOUNT_ID,),
            ).fetchall()
            latest_prices = connection.execute(
                """
                SELECT ss.code, ss.reference_price
                FROM stock_scores ss
                JOIN inference_run_models irm
                  ON irm.run_id = ss.run_id AND irm.model_version_id = ss.model_version_id
                JOIN inference_runs ir ON ir.id = ss.run_id
                WHERE irm.base_model_id = CASE
                    WHEN ir.protocol LIKE 'OFFICIAL_SPLIT_V3%'
                    THEN 'small-official-ft'
                    ELSE 'small-strict-pit'
                END
                  AND ir.id = (
                    SELECT id FROM inference_runs
                    WHERE status = 'SUCCEEDED' ORDER BY created_at DESC LIMIT 1
                  )
                """
            ).fetchall()
        if account is None:
            raise HTTPException(status_code=404, detail="Paper account not initialized")
        account_dict = dict(account)
        snapshot_dict = {} if latest_snapshot is None else dict(latest_snapshot)
        cash = float(snapshot_dict.get("cash", account_dict["cash"]))
        price_by_code = {str(row["code"]): float(row["reference_price"]) for row in latest_prices}
        valuation_by_code = {str(row["code"]): row for row in snapshot_valuations}
        position_payload = []
        for row in positions:
            code = str(row["code"])
            valuation = valuation_by_code.get(code)
            if valuation is not None:
                last_price = float(valuation["valuation_price"])
                source = str(valuation["valuation_source"])
                position_value = float(valuation["market_value"])
                unrealized = float(valuation["unrealized_pnl"])
            else:
                last_price = price_by_code.get(code, float(row["average_cost"]))
                source = (
                    "LATEST_STRICT_SCORE_CLOSE"
                    if code in price_by_code
                    else "AVERAGE_COST_FALLBACK"
                )
                position_value = int(row["quantity"]) * last_price
                unrealized = int(row["quantity"]) * (last_price - float(row["average_cost"]))
            position_payload.append(
                {
                    "code": row["code"],
                    "name": row["name"],
                    "quantity": row["quantity"],
                    "available_quantity": row["available_quantity"],
                    "average_cost": row["average_cost"],
                    "last_price": last_price,
                    "valuation_source": source,
                    "market_value": position_value,
                    "unrealized_pnl": unrealized,
                    "held_sessions": None,
                }
            )
        market_value = sum(float(item["market_value"]) for item in position_payload)
        return {
            "as_of": snapshot_dict.get("as_of_session"),
            "initial_cash": float(account_dict["initial_cash"]),
            "cash": cash,
            "market_value": market_value,
            "equity": cash + market_value,
            "valuation_policy": snapshot_dict.get("valuation_policy"),
            "positions": position_payload,
            "pending_orders": [dict(row) for row in pending],
            "gaps": [str(row["session"]) for row in gaps],
        }

    @app.get("/api/v1/paper/orders")
    def paper_orders(limit: Annotated[int, Query(ge=1, le=500)] = 100) -> dict[str, object]:
        with database.connect() as connection:
            rows = connection.execute(
                """
                SELECT po.*, pf.price AS fill_price, pf.commission, pf.stamp_tax
                FROM paper_orders po
                LEFT JOIN paper_fills pf ON pf.order_id = po.id
                WHERE po.account_id = ?
                ORDER BY po.created_at DESC LIMIT ?
                """,
                (ACCOUNT_ID, limit),
            ).fetchall()
        status_map = {"PENDING": "intent", "FILLED": "filled", "REJECTED": "rejected"}
        return {
            "orders": [
                {
                    "id": row["id"],
                    "run_id": row["run_id"],
                    "signal_date": row["signal_session"],
                    "execution_date": row["execution_session"],
                    "code": row["code"],
                    "name": row["name"],
                    "side": str(row["side"]).lower(),
                    "quantity": row["quantity"],
                    "status": status_map.get(str(row["status"]), "rejected"),
                    "price": row["fill_price"],
                    "fees": (
                        None
                        if row["commission"] is None
                        else float(row["commission"]) + float(row["stamp_tax"])
                    ),
                    "rejection_reason": row["reject_reason"],
                }
                for row in rows
            ]
        }

    @app.get("/api/v1/paper/summary")
    def paper_summary() -> dict[str, object]:
        with database.connect() as connection:
            account = connection.execute(
                "SELECT * FROM paper_accounts WHERE id = ?", (ACCOUNT_ID,)
            ).fetchone()
            nav_rows = connection.execute(
                """
                SELECT * FROM portfolio_snapshots
                WHERE account_id = ? ORDER BY as_of_session
                """,
                (ACCOUNT_ID,),
            ).fetchall()
            order_rows = connection.execute(
                "SELECT * FROM paper_orders WHERE account_id = ?", (ACCOUNT_ID,)
            ).fetchall()
            fill_rows = connection.execute(
                """
                SELECT pf.* FROM paper_fills pf
                JOIN paper_orders po ON po.id = pf.order_id
                WHERE po.account_id = ?
                """,
                (ACCOUNT_ID,),
            ).fetchall()
            latest_run = connection.execute(
                """
                SELECT id, as_of_session, paper_publication_state, paper_publication_run_id
                FROM inference_runs
                WHERE status = 'SUCCEEDED'
                  AND COALESCE(paper_publication_state, '')
                      != 'RESEARCH_ONLY_NOT_PUBLISHED'
                ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
            decisions = (
                []
                if latest_run is None
                else connection.execute(
                    """
                    SELECT * FROM paper_intent_decisions
                    WHERE run_id = ? ORDER BY rank, code
                    """,
                    (latest_run["id"],),
                ).fetchall()
            )
            legacy = connection.execute(
                """
                SELECT signal_session, run_id, note FROM paper_signal_publications
                WHERE account_id = ? AND state = 'LEGACY_MIXED_RUNS'
                ORDER BY signal_session
                """,
                (ACCOUNT_ID,),
            ).fetchall()
        if account is None:
            raise HTTPException(status_code=404, detail="Paper account not initialized")
        status_counts = Counter(str(row["status"]).lower() for row in order_rows)
        decision_counts = Counter(str(row["decision"]) for row in decisions)
        max_drawdown: float | None = None
        if len(nav_rows) >= 2:
            peak = float(nav_rows[0]["nav"])
            max_drawdown = 0.0
            for row in nav_rows:
                value = float(row["nav"])
                peak = max(peak, value)
                max_drawdown = min(max_drawdown, value / peak - 1)
        initial_cash = float(account["initial_cash"])
        gross = sum(float(row["gross_amount"]) for row in fill_rows)
        return {
            "sample_sessions": len(nav_rows),
            "evidence_state": "available" if len(nav_rows) >= 2 else "insufficient_evidence",
            "order_counts": {
                "pending": status_counts.get("pending", 0),
                "filled": status_counts.get("filled", 0),
                "rejected": status_counts.get("rejected", 0),
            },
            "decision_counts": dict(sorted(decision_counts.items())),
            "total_fees": sum(
                float(row["commission"]) + float(row["stamp_tax"]) for row in fill_rows
            ),
            "gross_turnover": gross / initial_cash if initial_cash > 0 else None,
            "max_drawdown": max_drawdown,
            "latest_publication": (
                None
                if latest_run is None
                else {
                    "run_id": latest_run["id"],
                    "signal_session": latest_run["as_of_session"],
                    "state": latest_run["paper_publication_state"],
                    "source_run_id": latest_run["paper_publication_run_id"],
                }
            ),
            "latest_decisions": [dict(row) for row in decisions],
            "warnings": [f"{row['signal_session']}: {row['note']}" for row in legacy],
        }

    @app.get("/api/v1/paper/nav")
    def paper_nav() -> dict[str, object]:
        with database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM portfolio_snapshots WHERE account_id = ? ORDER BY as_of_session
                """,
                (ACCOUNT_ID,),
            ).fetchall()
        return {
            "nav": [
                {
                    "session": row["as_of_session"],
                    "nav": row["nav"],
                    "benchmark_nav": None,
                }
                for row in rows
            ]
        }

    if active_settings.frontend_dist.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=active_settings.frontend_dist, html=True),
            name="frontend",
        )
    return app


def main() -> None:
    settings = Settings.load()
    if settings.host not in {"127.0.0.1", "::1", "localhost"}:
        raise RuntimeError("ElanQuant API must bind to loopback")
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
