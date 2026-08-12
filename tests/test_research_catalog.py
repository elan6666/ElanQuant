import hashlib
import json
from pathlib import Path

import pytest

from scripts.server.build_research_catalog import canonical_hash, compile_cells, main


def write_receipts(tmp_path: Path, size: str) -> tuple[Path, Path]:
    identities = {
        f"{size}-zero-shot": "zero_shot",
        f"{size}-official-ft": "official_style",
        f"{size}-strict-pit": "strict_pit",
    }
    matrix = tmp_path / f"{size}-matrix.json"
    matrix_payload = {
        "schema_version": "elanquant_training_matrix_v2",
        "status": "PASS",
        "upstream_commit": "1" * 40,
        "data_manifest_sha256": "d" * 64,
        "dataset_admission_receipt_sha256": "e" * 64,
        "split_contract_sha256": "f" * 64,
        "official_weights_receipt_sha256": "0" * 64,
        "cells": [
            {
                "id": model_id,
                "size": size,
                "track": identities[model_id],
                "predictor_sha256": (model_id + "p").encode().hex().ljust(64, "0")[:64],
                "tokenizer_sha256": (model_id + "t").encode().hex().ljust(64, "0")[:64],
                "config_sha256": (model_id + "c").encode().hex().ljust(64, "0")[:64],
            }
            for model_id in identities
        ],
    }
    matrix_payload["receipt_hash"] = canonical_hash(matrix_payload)
    matrix.write_text(json.dumps(matrix_payload), encoding="utf-8")
    matrix_sha = hashlib.sha256(matrix.read_bytes()).hexdigest()
    support = {
        "validation_2025": {
            "eligible_rows": 400,
            "evaluated_rows": 300,
            "evaluated_cross_sections": 10,
            "anchor_set_sha256": "a" * 64,
        },
        "test_viewed_2026": {
            "eligible_rows": 250,
            "evaluated_rows": 200,
            "evaluated_cross_sections": 8,
            "anchor_set_sha256": "b" * 64,
        },
    }
    cells = {cell["id"]: cell for cell in matrix_payload["cells"]}
    evaluation = tmp_path / f"{size}-formal.json"
    evaluation.write_text(
        json.dumps(
            {
                "status": "PASS",
                "schema_version": "elanquant_kronos_inference_v1",
                "evaluation_mode": "FORMAL",
                "test_status": "TEST_VIEWED",
                "upstream_commit": "1" * 40,
                "inference_code_sha256": "1" * 64,
                "data_manifest_sha256": "2" * 64,
                "config_sha256": "3" * 64,
                "as_of_session": "2026-08-12",
                "training_matrix_receipt_sha256": matrix_sha,
                "evaluation_support": support,
                "models": {
                    model_id: {
                        **cells[model_id],
                        "track": track,
                        "metrics": {
                            split: {
                                "rank_ic": 0.01,
                                "ic": 0.02,
                                "top10_mean_return": 0.03,
                                "rows": values["evaluated_rows"],
                                "cross_sections": values["evaluated_cross_sections"],
                            }
                            for split, values in support.items()
                        },
                    }
                    for model_id, track in identities.items()
                },
                "scores": [{} for _ in range(300)],
            }
        ),
        encoding="utf-8",
    )
    return matrix, evaluation


def test_catalog_compiles_exact_three_cells_and_dual_split(tmp_path: Path) -> None:
    matrix, evaluation = write_receipts(tmp_path, "base")
    cells, identities = compile_cells("base", matrix, evaluation)
    assert len(cells) == 3
    assert {cell["id"] for cell in cells} == {
        "base-zero-shot",
        "base-official-ft",
        "base-strict-pit",
    }
    for cell in cells:
        evaluations = cell["evaluations"]
        assert isinstance(evaluations, dict)
        assert set(evaluations) == {"validation_2025", "test_viewed_2026"}
    assert len(identities["matrix_sha256"]) == 64


def test_catalog_rejects_track_tampering_and_fractional_support(tmp_path: Path) -> None:
    matrix, evaluation = write_receipts(tmp_path, "base")
    matrix_payload = json.loads(matrix.read_text(encoding="utf-8"))
    matrix_payload["cells"][0]["track"] = "strict_pit"
    matrix_payload["receipt_hash"] = canonical_hash(
        {key: value for key, value in matrix_payload.items() if key != "receipt_hash"}
    )
    matrix.write_text(json.dumps(matrix_payload), encoding="utf-8")
    evaluation_payload = json.loads(evaluation.read_text(encoding="utf-8"))
    evaluation_payload["training_matrix_receipt_sha256"] = hashlib.sha256(
        matrix.read_bytes()
    ).hexdigest()
    evaluation.write_text(json.dumps(evaluation_payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="track mismatch"):
        compile_cells("base", matrix, evaluation)

    matrix, evaluation = write_receipts(tmp_path, "small")
    payload = json.loads(evaluation.read_text(encoding="utf-8"))
    payload["evaluation_support"]["validation_2025"]["evaluated_rows"] = 300.5
    evaluation.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="positive integer"):
        compile_cells("small", matrix, evaluation)


def test_catalog_rejects_small_base_support_mismatch(tmp_path: Path, monkeypatch) -> None:
    small_matrix, small_evaluation = write_receipts(tmp_path, "small")
    base_matrix, base_evaluation = write_receipts(tmp_path, "base")
    payload = json.loads(base_evaluation.read_text(encoding="utf-8"))
    payload["evaluation_support"]["validation_2025"]["anchor_set_sha256"] = "c" * 64
    base_evaluation.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "build_research_catalog.py",
            "--small-matrix", str(small_matrix),
            "--small-evaluation", str(small_evaluation),
            "--base-matrix", str(base_matrix),
            "--base-evaluation", str(base_evaluation),
            "--out", str(tmp_path / "catalog.json"),
        ],
    )
    with pytest.raises(RuntimeError, match="support"):
        main()


def test_catalog_rejects_cross_size_weight_or_as_of_mismatch(tmp_path: Path, monkeypatch) -> None:
    small_matrix, small_evaluation = write_receipts(tmp_path, "small")
    base_matrix, base_evaluation = write_receipts(tmp_path, "base")
    base_payload = json.loads(base_matrix.read_text(encoding="utf-8"))
    base_payload["official_weights_receipt_sha256"] = "9" * 64
    base_payload["receipt_hash"] = canonical_hash(
        {key: value for key, value in base_payload.items() if key != "receipt_hash"}
    )
    base_matrix.write_text(json.dumps(base_payload), encoding="utf-8")
    evaluation_payload = json.loads(base_evaluation.read_text(encoding="utf-8"))
    evaluation_payload["training_matrix_receipt_sha256"] = hashlib.sha256(
        base_matrix.read_bytes()
    ).hexdigest()
    base_evaluation.write_text(json.dumps(evaluation_payload), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "build_research_catalog.py",
            "--small-matrix", str(small_matrix),
            "--small-evaluation", str(small_evaluation),
            "--base-matrix", str(base_matrix),
            "--base-evaluation", str(base_evaluation),
            "--out", str(tmp_path / "catalog.json"),
        ],
    )
    with pytest.raises(RuntimeError, match="official_weights"):
        main()

    _, evaluation = write_receipts(tmp_path, "small")
    invalid = json.loads(evaluation.read_text(encoding="utf-8"))
    invalid["as_of_session"] = "not-a-date"
    evaluation.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(RuntimeError, match="as-of"):
        compile_cells("small", small_matrix, evaluation)
