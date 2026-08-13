from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

TRACKS = {
    "zero_shot": "zero_shot",
    "official_style": "official_style",
    "strict_pit": "strict_pit",
}
SPLITS = ("validation_2025", "test_viewed_2026")
MATRIX_SCHEMA = "elanquant_training_matrix_v2"
EVALUATION_SCHEMA = "elanquant_kronos_inference_v1"
COMPATIBILITY_SCHEMA = "elanquant_evaluation_compatibility_v1"
EVALUATION_PROTOCOL = {
    "evaluation_mode": "FORMAL",
    "evaluation_batch_size": 50,
    "online_batch_size": 50,
    "formal_sessions_per_month": 5,
    "sampling": {"temperature": 0.6, "top_p": 0.9, "top_k": 0, "sample_count": 10},
}
ALLOWED_COMPATIBILITY_DIFFERENCES = [
    "MODEL_SIZE_PARAMETERIZATION",
    "MODEL_CELL_ID_PREFIX",
    "BATCH_CONFIG_KEY_RENAMED",
    "ONLINE_BATCH_SIZE_EXPLICIT_50",
    "PRIMARY_STRICT_MODEL_ID_AND_LABEL",
]
SMALL_COMPATIBLE_SOURCE_REVISION = "ec5ccffd1353da792d0dd5274b7a279918a0f1e2"
BASE_COMPATIBLE_SOURCE_REVISION = "266bab286a03c07a8b186a443c64144bfa35c487"
EXPECTED_SOURCE_DIFF_SHA256 = "7fff6d49340c5ac08b006cd72f858ba314535a7176da07d97704344648861308"
COMPATIBLE_SOURCE_PATH = "scripts/server/evaluate_and_infer.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"receipt is not an object: {path.name}")
    return payload


def canonical_hash(payload: Any) -> str:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def finite_number(value: Any, identity: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"{identity} is not numeric")
    number = float(value)
    if not math.isfinite(number):
        raise RuntimeError(f"{identity} is not finite")
    return number


def positive_integer(value: Any, identity: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RuntimeError(f"{identity} is not a positive integer")
    return value


def sha_identity(value: Any, identity: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value.lower())
    ):
        raise RuntimeError(f"{identity} is invalid")
    return value


def compile_cells(
    model_size: str,
    matrix_path: Path,
    evaluation_path: Path,
) -> tuple[list[dict[str, object]], dict[str, Any]]:
    matrix = read_json(matrix_path)
    evaluation = read_json(evaluation_path)
    matrix_sha = sha256(matrix_path)
    expected_tracks = {
        f"{model_size}-zero-shot": "zero_shot",
        f"{model_size}-official-ft": "official_style",
        f"{model_size}-strict-pit": "strict_pit",
    }
    expected_ids = set(expected_tracks)
    cells = matrix.get("cells")
    models = evaluation.get("models")
    support = evaluation.get("evaluation_support")
    matrix_content = dict(matrix)
    claimed_hash = matrix_content.pop("receipt_hash", None)
    if (
        matrix.get("schema_version") != MATRIX_SCHEMA
        or matrix.get("status") != "PASS"
        or canonical_hash(matrix_content) != claimed_hash
        or not isinstance(cells, list)
    ):
        raise RuntimeError(f"{model_size} matrix is not terminal PASS")
    for identity in (
        "data_manifest_sha256",
        "dataset_admission_receipt_sha256",
        "split_contract_sha256",
        "official_weights_receipt_sha256",
    ):
        sha_identity(matrix.get(identity), f"{model_size} matrix {identity}")
    upstream_commit = matrix.get("upstream_commit")
    if (
        not isinstance(upstream_commit, str)
        or len(upstream_commit) != 40
        or any(character not in "0123456789abcdef" for character in upstream_commit.lower())
    ):
        raise RuntimeError(f"{model_size} matrix upstream identity is invalid")
    matrix_cells = {
        str(cell.get("id")): cell for cell in cells if isinstance(cell, dict)
    }
    if set(matrix_cells) != expected_ids:
        raise RuntimeError(f"{model_size} matrix is not the exact three-cell experiment")
    if (
        evaluation.get("schema_version") != EVALUATION_SCHEMA
        or evaluation.get("status") != "PASS"
        or evaluation.get("evaluation_mode") != "FORMAL"
        or evaluation.get("test_status") != "TEST_VIEWED"
        or evaluation.get("training_matrix_receipt_sha256") != matrix_sha
        or evaluation.get("upstream_commit") != matrix.get("upstream_commit")
        or not isinstance(evaluation.get("inference_code_sha256"), str)
        or len(str(evaluation.get("inference_code_sha256"))) != 64
        or not isinstance(models, dict)
        or set(models) != expected_ids
        or not isinstance(support, dict)
    ):
        raise RuntimeError(f"{model_size} formal evaluation is incomplete or mismatched")
    evaluation_data_sha = sha_identity(
        evaluation.get("data_manifest_sha256"), f"{model_size} evaluation data"
    )
    evaluation_config_sha = sha_identity(
        evaluation.get("config_sha256"), f"{model_size} evaluation config"
    )
    inference_code_sha = sha_identity(
        evaluation.get("inference_code_sha256"), f"{model_size} inference code"
    )
    scores = evaluation.get("scores")
    if not isinstance(scores, list) or len(scores) < 250:
        raise RuntimeError(f"{model_size} formal ranking coverage is incomplete")
    output: list[dict[str, object]] = []
    for model_id in sorted(expected_ids):
        model = models[model_id]
        matrix_cell = matrix_cells[model_id]
        if not isinstance(model, dict):
            raise RuntimeError(f"invalid model receipt: {model_id}")
        if matrix_cell.get("size") != model_size:
            raise RuntimeError(f"matrix size mismatch: {model_id}")
        expected_track = expected_tracks[model_id]
        if matrix_cell.get("track") != expected_track or model.get("track") != expected_track:
            raise RuntimeError(f"model track mismatch: {model_id}")
        for identity in ("predictor_sha256", "tokenizer_sha256", "config_sha256"):
            sha_identity(matrix_cell.get(identity), f"{model_id}.{identity}")
            if model.get(identity) != matrix_cell.get(identity):
                raise RuntimeError(f"model identity mismatch: {model_id}.{identity}")
        metrics = model.get("metrics")
        if not isinstance(metrics, dict) or set(metrics) != set(SPLITS):
            raise RuntimeError(f"formal metrics are incomplete: {model_id}")
        evaluations: dict[str, dict[str, object]] = {}
        for split in SPLITS:
            values = metrics[split]
            split_support = support.get(split)
            if not isinstance(values, dict) or not isinstance(split_support, dict):
                raise RuntimeError(f"formal support is incomplete: {model_id}.{split}")
            rows = positive_integer(values.get("rows"), f"{model_id}.{split}.rows")
            sections = positive_integer(
                values.get("cross_sections"), f"{model_id}.{split}.cross_sections"
            )
            support_rows = positive_integer(
                split_support.get("evaluated_rows"), f"{split}.evaluated_rows"
            )
            support_sections = positive_integer(
                split_support.get("evaluated_cross_sections"),
                f"{split}.evaluated_cross_sections",
            )
            eligible_rows = positive_integer(
                split_support.get("eligible_rows"), f"{split}.eligible_rows"
            )
            if rows != support_rows or sections != support_sections or rows > eligible_rows:
                raise RuntimeError(f"formal support disagrees: {model_id}.{split}")
            numeric_metrics = (
                finite_number(values.get("rank_ic"), f"{model_id}.{split}.rank_ic"),
                finite_number(values.get("ic"), f"{model_id}.{split}.ic"),
                finite_number(
                    values.get("top10_mean_return"),
                    f"{model_id}.{split}.top10_mean_return",
                ),
            )
            anchor_hash = sha_identity(
                split_support.get("anchor_set_sha256"),
                f"{model_id}.{split}.anchor_set_sha256",
            )
            evaluations[split] = {
                "rank_ic": numeric_metrics[0],
                "pearson_ic": numeric_metrics[1],
                "top10_mean_return": numeric_metrics[2],
                "rows": rows,
                "cross_sections": sections,
                "anchor_set_sha256": anchor_hash,
            }
        track = expected_track
        validation = evaluations["validation_2025"]
        output.append(
            {
                "id": model_id,
                "model_size": model_size,
                "track": TRACKS[track],
                "state": "passed",
                "rank_ic": validation["rank_ic"],
                "pearson_ic": validation["pearson_ic"],
                "top10_mean_return": validation["top10_mean_return"],
                "model_hash": model["predictor_sha256"],
                "receipt": sha256(evaluation_path),
                "note": (
                    "严格PIT资格；不代表它自动是验证集最佳模型。"
                    if track == "strict_pit"
                    else "可审计对照轨；不进入模拟组合主排名。"
                ),
                "evaluations": evaluations,
            }
        )
    as_of_session = evaluation.get("as_of_session")
    try:
        parsed_as_of = date.fromisoformat(str(as_of_session))
    except ValueError as error:
        raise RuntimeError(f"{model_size} evaluation as-of session is invalid") from error
    if parsed_as_of.isoformat() != as_of_session:
        raise RuntimeError(f"{model_size} evaluation as-of session is invalid")
    return output, {
        "matrix_sha256": matrix_sha,
        "evaluation_sha256": sha256(evaluation_path),
        "upstream_commit": matrix["upstream_commit"],
        "official_weights_receipt_sha256": matrix["official_weights_receipt_sha256"],
        "training_data_sha256": matrix["data_manifest_sha256"],
        "admission_sha256": matrix["dataset_admission_receipt_sha256"],
        "split_contract_sha256": matrix["split_contract_sha256"],
        "evaluation_data_sha256": evaluation_data_sha,
        "evaluation_config_sha256": evaluation_config_sha,
        "inference_code_sha256": inference_code_sha,
        "as_of_session": as_of_session,
        "support": {
            split: {
                "eligible_rows": support[split]["eligible_rows"],
                "evaluated_rows": support[split]["evaluated_rows"],
                "evaluated_cross_sections": support[split]["evaluated_cross_sections"],
                "anchor_set_sha256": support[split]["anchor_set_sha256"],
            }
            for split in SPLITS
        },
    }


def atomic_write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_compatibility_receipt(
    path: Path,
    sources: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    receipt = read_json(path)
    content = dict(receipt)
    claimed = content.pop("receipt_hash", None)
    if (
        receipt.get("schema_version") != COMPATIBILITY_SCHEMA
        or receipt.get("status") != "PASS"
        or receipt.get("decision") != "SEMANTICALLY_COMPARABLE"
        or canonical_hash(content) != sha_identity(claimed, "compatibility receipt hash")
        or receipt.get("normalized_protocol") != EVALUATION_PROTOCOL
        or receipt.get("allowed_differences") != ALLOWED_COMPATIBILITY_DIFFERENCES
        or receipt.get("source_revisions")
        != {
            "small": SMALL_COMPATIBLE_SOURCE_REVISION,
            "base": BASE_COMPATIBLE_SOURCE_REVISION,
        }
        or receipt.get("source_path") != COMPATIBLE_SOURCE_PATH
        or receipt.get("source_diff_sha256") != EXPECTED_SOURCE_DIFF_SHA256
    ):
        raise RuntimeError("evaluation compatibility receipt is invalid")
    source_identities = receipt.get("source_identities")
    if not isinstance(source_identities, dict) or set(source_identities) != {"small", "base"}:
        raise RuntimeError("evaluation compatibility source identities are incomplete")
    for size in ("small", "base"):
        identities = source_identities[size]
        if not isinstance(identities, dict) or identities != {
            "evaluation_config_sha256": sources[size]["evaluation_config_sha256"],
            "inference_code_sha256": sources[size]["inference_code_sha256"],
        }:
            raise RuntimeError(f"evaluation compatibility identity mismatch: {size}")
    for identity in ("source_diff_sha256", "protocol_sha256"):
        sha_identity(receipt.get(identity), f"compatibility.{identity}")
    if receipt.get("evaluation_receipts") != {
        "small": sources["small"]["evaluation_sha256"],
        "base": sources["base"]["evaluation_sha256"],
    }:
        raise RuntimeError("evaluation compatibility receipts are not bound")
    if receipt["protocol_sha256"] != canonical_hash(EVALUATION_PROTOCOL):
        raise RuntimeError("evaluation compatibility protocol hash is invalid")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--small-matrix", type=Path, required=True)
    parser.add_argument("--small-evaluation", type=Path, required=True)
    parser.add_argument("--base-matrix", type=Path, required=True)
    parser.add_argument("--base-evaluation", type=Path, required=True)
    parser.add_argument("--compatibility-receipt", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    experiments: list[dict[str, object]] = []
    sources: dict[str, dict[str, Any]] = {}
    for size in ("small", "base"):
        matrix = getattr(args, f"{size}_matrix")
        evaluation = getattr(args, f"{size}_evaluation")
        cells, identity = compile_cells(size, matrix, evaluation)
        experiments.extend(cells)
        sources[size] = identity
    compatibility = validate_compatibility_receipt(args.compatibility_receipt, sources)
    compatibility_sha = str(compatibility["receipt_hash"])
    for source in sources.values():
        source["evaluation_protocol_sha256"] = compatibility["protocol_sha256"]
        source["compatibility_receipt_sha256"] = compatibility_sha
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
    for key in comparable_keys:
        if sources["small"].get(key) != sources["base"].get(key):
            raise RuntimeError(f"Small/Base catalog identity is not comparable: {key}")
    payload: dict[str, object] = {
        "schema_version": "elanquant_research_catalog_v1",
        "status": "PASS",
        "generated_at": datetime.now(UTC).isoformat(),
        "experiments": experiments,
        "sources": sources,
        "compatibility": compatibility,
    }
    payload["receipt_hash"] = canonical_hash(payload)
    atomic_write(args.out, payload)
    print(json.dumps({"status": "PASS", "experiments": len(experiments), "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
