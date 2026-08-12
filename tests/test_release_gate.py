from __future__ import annotations

import copy
import hashlib
import json

import pytest

from scripts.server.publish_release import canonical_hash, validate_release_pair

MODEL_IDS = ("small-zero-shot", "small-official-ft", "small-strict-pit")


def fixtures() -> tuple[dict[str, object], dict[str, object], str]:
    matrix: dict[str, object] = {
        "schema_version": "elanquant_training_matrix_v2",
        "status": "PASS",
        "cells": [{"id": model_id} for model_id in MODEL_IDS],
    }
    matrix["receipt_hash"] = canonical_hash(matrix)
    rendered = json.dumps(matrix, sort_keys=True).encode()
    matrix_sha = hashlib.sha256(rendered).hexdigest()
    metrics = {
        "validation_2025": {
            "rank_ic": 0.1,
            "ic": 0.08,
            "top10_mean_return": 0.03,
            "rows": 300,
            "cross_sections": 10,
        }
    }
    evaluation: dict[str, object] = {
        "schema_version": "elanquant_kronos_inference_v1",
        "status": "PASS",
        "evaluation_mode": "FORMAL",
        "training_matrix_receipt_sha256": matrix_sha,
        "evaluation_support": {
            "validation_2025": {"eligible_rows": 1000, "evaluated_rows": 300}
        },
        "models": {model_id: {"metrics": copy.deepcopy(metrics)} for model_id in MODEL_IDS},
        "scores": [{} for _ in range(250)],
    }
    return matrix, evaluation, matrix_sha


def test_accepts_exact_small_formal_release() -> None:
    matrix, evaluation, matrix_sha = fixtures()
    validate_release_pair(matrix, evaluation, matrix_sha)


@pytest.mark.parametrize("missing", MODEL_IDS)
def test_rejects_incomplete_small_matrix_or_evaluation(missing: str) -> None:
    matrix, evaluation, matrix_sha = fixtures()
    evaluation["models"].pop(missing)  # type: ignore[union-attr]
    with pytest.raises(RuntimeError, match="exact Small three-cell"):
        validate_release_pair(matrix, evaluation, matrix_sha)


def test_rejects_non_finite_formal_metric() -> None:
    matrix, evaluation, matrix_sha = fixtures()
    models = evaluation["models"]
    models["small-strict-pit"]["metrics"]["validation_2025"]["rank_ic"] = float("nan")  # type: ignore[index]
    with pytest.raises(RuntimeError, match="not finite"):
        validate_release_pair(matrix, evaluation, matrix_sha)
