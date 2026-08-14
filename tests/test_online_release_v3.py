from __future__ import annotations

import copy

import pytest

import elanquant.api.app as api
from elanquant.pipelines.real import expected_model_ids, normalized_evaluation_evidence
from scripts.research.online_release_v3 import (
    METHOD_LOCK_SCHEMA,
    ONLINE_SAMPLING,
    ONLINE_SIGNAL,
    PRIMARY_MODELS,
    RELEASE_SCHEMA,
    OnlineReleaseError,
    canonical_hash,
    validate_method_lock,
    validate_release,
)


def release() -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": RELEASE_SCHEMA,
        "status": "PASS",
        "release_id": "official-split-v3-20260814",
        "training_matrix_sha256": "a" * 64,
        "analysis_lock_sha256": "e" * 64,
        "online_method_lock_sha256": "9" * 64,
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


def test_pre_result_online_method_lock_freezes_exact_runtime_method() -> None:
    lock: dict[str, object] = {
        "schema_version": METHOD_LOCK_SCHEMA,
        "status": "PASS",
        "locked_at": "2026-08-14T00:00:00+00:00",
        "training_matrix_sha256": "a" * 64,
        "online_runner_sha256": "b" * 64,
        "online_contract_sha256": "c" * 64,
        "primary_models": PRIMARY_MODELS,
        "selection_basis": "PREDECLARED_OFFICIAL_FT_METHOD_IDENTITY",
        "test_metrics_used_for_selection": False,
        "viewed_results_root": "results/official-split-v3",
        "viewed_results_present_at_lock": False,
        "online_signal": ONLINE_SIGNAL,
        "online_sampling": ONLINE_SAMPLING,
    }
    lock["receipt_hash"] = canonical_hash(lock)
    assert validate_method_lock(lock)["viewed_results_present_at_lock"] is False
    lock["viewed_results_present_at_lock"] = True
    lock["receipt_hash"] = canonical_hash(
        {key: value for key, value in lock.items() if key != "receipt_hash"}
    )
    with pytest.raises(OnlineReleaseError, match="firewall"):
        validate_method_lock(lock)


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
                "signal_sha256": (
                    character if size == "small" else str(int(character) + 2)
                )
                * 64,
                "candidate_set_sha256": "d" * 64,
                "support": {"rows": 300, "sessions": 10},
                "metrics": {"rank_ic": 0.01, "ic": 0.02, "top10_mean_return": 0.03},
            }
            for size in ("small", "base")
            for variant, character in (("official-ft", "1"), ("zero-shot", "2"))
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


def test_experiment_projection_requires_release_matrix_evaluation_binding() -> None:
    matrix: dict[str, object] = {
        "schema_version": "elanquant_kronos_four_cell_matrix_v3",
        "status": "PASS",
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
    matrix["receipt_hash"] = api.canonical_hash(matrix)
    evaluation: dict[str, object] = {
        "schema_version": "elanquant_kronos_rolling_evaluation_v3",
        "status": "PASS",
        "analysis_lock_sha256": "e" * 64,
        "test_status": "TEST_VIEWED",
        "used_for_selection": False,
        "promotion_eligible": False,
        "entries": [
            {
                "model_cell_id": f"{size}-{variant}",
                "signal_sha256": character * 64,
                "candidate_set_sha256": "d" * 64,
                "support": {"rows": 300, "sessions": 10},
                "metrics": {"rank_ic": 0.01, "ic": 0.02, "top10_mean_return": 0.03},
            }
            for size, character in (("small", "1"), ("base", "2"))
            for variant in ("official-ft", "zero-shot")
        ],
    }
    evaluation["receipt_hash"] = api.canonical_hash(evaluation)
    sealed_release = release()
    projected = api.official_split_v3_experiments(
        evaluation, matrix, "b" * 64, "a" * 64, sealed_release
    )
    assert len(projected) == 4
    assert {
        item["evaluations"]["test_viewed_official_v3"]["anchor_set_sha256"]  # type: ignore[index]
        for item in projected
    } == {"d" * 64}
    drifted = copy.deepcopy(sealed_release)
    drifted["training_matrix_sha256"] = "9" * 64
    drifted["receipt_hash"] = canonical_hash(
        {key: value for key, value in drifted.items() if key != "receipt_hash"}
    )
    with pytest.raises(RuntimeError, match="binding differs"):
        api.official_split_v3_experiments(
            evaluation, matrix, "b" * 64, "a" * 64, drifted
        )
