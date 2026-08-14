from __future__ import annotations

import copy

import pytest

from elanquant.pipelines.real import expected_model_ids, normalized_evaluation_evidence
from scripts.research.online_release_v3 import (
    ONLINE_SAMPLING,
    ONLINE_SIGNAL,
    PRIMARY_MODELS,
    RELEASE_SCHEMA,
    OnlineReleaseError,
    canonical_hash,
    validate_release,
)


def release() -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": RELEASE_SCHEMA,
        "status": "PASS",
        "release_id": "official-split-v3-20260814",
        "training_matrix_sha256": "a" * 64,
        "analysis_lock_sha256": "e" * 64,
        "rolling_evaluation_sha256": "b" * 64,
        "historical_catalog_sha256": "c" * 64,
        "online_runner_sha256": "d" * 64,
        "primary_models": PRIMARY_MODELS,
        "selection_basis": "PREDECLARED_OFFICIAL_FT_METHOD_IDENTITY",
        "test_metrics_used_for_selection": False,
        "online_signal": ONLINE_SIGNAL,
        "online_sampling": ONLINE_SAMPLING,
    }
    value["receipt_hash"] = canonical_hash(value)
    return value


def test_online_release_freezes_official_ft_without_test_selection() -> None:
    assert validate_release(release())["primary_models"] == PRIMARY_MODELS
    altered = copy.deepcopy(release())
    altered["test_metrics_used_for_selection"] = True
    altered["receipt_hash"] = canonical_hash(
        {key: value for key, value in altered.items() if key != "receipt_hash"}
    )
    with pytest.raises(OnlineReleaseError, match="firewall"):
        validate_release(altered)


def test_real_pipeline_normalizes_four_cell_v3_evidence_by_size() -> None:
    matrix = {
        "schema_version": "elanquant_kronos_four_cell_matrix_v3",
        "cells": [
            {
                "id": f"{size}-{variant}",
                "predictor_sha256": character * 64,
                "tokenizer_sha256": "e" * 64,
                "config_sha256": "f" * 64,
            }
            for size, character in (("small", "a"), ("base", "b"))
            for variant in ("official-ft", "zero-shot")
        ],
    }
    evaluation = {
        "schema_version": "elanquant_kronos_rolling_evaluation_v3",
        "status": "PASS",
        "test_status": "TEST_VIEWED",
        "used_for_selection": False,
        "promotion_eligible": False,
        "entries": [
            {
                "model_cell_id": f"{size}-{variant}",
                "signal_sha256": "d" * 64,
                "support": {"rows": 300, "sessions": 10},
                "metrics": {"rank_ic": 0.01, "ic": 0.02, "top10_mean_return": 0.03},
            }
            for size in ("small", "base")
            for variant in ("official-ft", "zero-shot")
        ],
    }
    models, support, runner = normalized_evaluation_evidence(matrix, evaluation, "small")
    assert set(models) == {"small-zero-shot", "small-official-ft"}
    assert support["test_viewed_official_v3"]["evaluated_rows"] == 300
    assert runner == "evaluate_official_split_online_v3.py"
    assert expected_model_ids("base", matrix["schema_version"]) == {
        "base-zero-shot",
        "base-official-ft",
    }
