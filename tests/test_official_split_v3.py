from __future__ import annotations

import copy
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from scripts.research.official_split_v3 import (
    ACTIVE_CELLS,
    ADMISSION_SCHEMA,
    ANALYSIS_LOCK_SCHEMA,
    BACKTEST_SCHEMA,
    EVALUATION_SCHEMA,
    HISTORICAL_SCHEMA,
    MATRIX_SCHEMA,
    RETIREMENT_SCHEMA,
    SIGNAL_SCHEMA,
    SPLIT_SCHEMA,
    STRATEGIES,
    TRAINED_CELLS,
    TRAINING_AUDIT_SCHEMA,
    ContractError,
    build_split_receipt,
    canonical_hash,
    validate_analysis_lock,
    validate_backtest_receipt,
    validate_dataset_admission,
    validate_evaluation,
    validate_historical_catalog,
    validate_matrix,
    validate_retirement_receipt,
    validate_signal_receipt,
    validate_split_receipt,
    validate_training_audit,
)
from scripts.research.online_release_v3 import validate_method_lock
from scripts.server import build_official_split_online_method_lock_v3 as method_lock_builder
from scripts.server.materialize_official_split_dataset_v3 import consecutive_indices

SHA = "a" * 64


def seal(payload: dict[str, object]) -> dict[str, object]:
    payload["receipt_hash"] = canonical_hash(payload)
    return payload


def sessions(start: date, end: date) -> list[date]:
    rows: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            rows.append(current)
        current += timedelta(days=1)
    return rows


def split() -> dict[str, object]:
    return build_split_receipt(
        sessions(date(2010, 1, 1), date(2026, 8, 13)),
        frozen_latest=date(2026, 8, 13),
    )


def test_official_raw_slices_have_101_row_training_and_disjoint_effective_ranges() -> None:
    payload = validate_split_receipt(split())
    assert payload["schema_version"] == SPLIT_SCHEMA
    assert payload["training_window_rows"] == 101
    assert payload["inference_window_rows"] == 100
    assert payload["raw_ranges"] == {
        "train": ["2011-01-01", "2022-12-31"],
        "validation": ["2022-09-01", "2024-06-30"],
        "test_viewed": ["2024-04-01", "2026-08-13"],
    }
    effective = payload["effective_ranges"]
    assert effective["train"]["last_consumed"] < effective["validation"]["first_anchor"]
    assert effective["validation"]["last_consumed"] < effective["test_viewed"]["first_anchor"]
    assert payload["backtest_range"]["requested_start"] == "2024-07-01"
    assert payload["backtest_range"]["actual_first_signal"] >= "2024-07-01"


def test_future_calendar_perturbation_cannot_change_frozen_receipt() -> None:
    frozen = date(2026, 8, 13)
    base = sessions(date(2010, 1, 1), frozen)
    original = split()
    with pytest.raises(ContractError, match="final calendar"):
        build_split_receipt(base + [date(2026, 8, 14)], frozen_latest=frozen)
    assert split()["receipt_hash"] == original["receipt_hash"]


def test_training_eligibility_uses_anchor_membership_not_future_membership() -> None:
    calendar = pd.date_range("2024-01-01", periods=101, freq="B")
    frame = pd.DataFrame(
        {name: range(101) for name in ("open", "high", "low", "close", "vol", "amt")},
        index=calendar,
    )
    anchor = pd.Timestamp(calendar[89])
    member_map = {anchor: {"000001.SZ"}, pd.Timestamp(calendar[90]): set()}
    rows = consecutive_indices(
        frame,
        pd.DatetimeIndex(calendar),
        sorted(member_map),
        member_map,
        "000001.SZ",
    )
    assert rows == [("000001.SZ", 0)]


def test_training_eligibility_rejects_gappy_global_window() -> None:
    calendar = pd.date_range("2024-01-01", periods=101, freq="B")
    frame = pd.DataFrame(
        {name: range(100) for name in ("open", "high", "low", "close", "vol", "amt")},
        index=calendar.delete(10),
    )
    anchor = pd.Timestamp(calendar[89])
    assert consecutive_indices(
        frame,
        pd.DatetimeIndex(calendar),
        [anchor],
        {anchor: {"000001.SZ"}},
        "000001.SZ",
    ) == []


def matrix() -> dict[str, object]:
    cells: list[dict[str, object]] = []
    for cell_id in ACTIVE_CELLS:
        trained = cell_id.endswith("official-ft")
        row: dict[str, object] = {
            "id": cell_id,
            "training_mode": "official_ft" if trained else "zero_shot",
            "tokenizer_sha256": SHA,
            "predictor_sha256": SHA,
            "config_sha256": SHA,
            "tokenizer_path": f"/models/{cell_id}/tokenizer",
            "predictor_path": f"/models/{cell_id}/predictor",
        }
        if trained:
            row.update(
                tokenizer_terminal_sha256=SHA,
                predictor_terminal_sha256=SHA,
                predictor_input_tokenizer_sha256=SHA,
            )
        cells.append(row)
    return seal(
        {
            "schema_version": MATRIX_SCHEMA,
            "status": "PASS",
            "upstream_commit": "67b630e67f6a18c9e9be918d9b4337c960db1e9a",
            "split_receipt_sha256": SHA,
            "dataset_manifest_sha256": SHA,
            "dataset_admission_sha256": SHA,
            "official_weights_receipt_sha256": SHA,
            "training_audit_sha256": SHA,
            "cells": cells,
        }
    )


def test_active_matrix_is_exactly_four_cells_and_rejects_strict() -> None:
    assert tuple(row["id"] for row in validate_matrix(matrix())["cells"]) == ACTIVE_CELLS
    invalid = copy.deepcopy(matrix())
    invalid["cells"][0]["id"] = "base-strict-pit"
    invalid["receipt_hash"] = canonical_hash(
        {key: value for key, value in invalid.items() if key != "receipt_hash"}
    )
    with pytest.raises(ContractError, match="exactly four"):
        validate_matrix(invalid)
    missing_path = copy.deepcopy(matrix())
    del missing_path["cells"][0]["predictor_path"]
    missing_path["receipt_hash"] = canonical_hash(
        {key: value for key, value in missing_path.items() if key != "receipt_hash"}
    )
    with pytest.raises(ContractError, match="absolute model directory"):
        validate_matrix(missing_path)


def test_online_method_lock_builder_runs_only_before_viewed_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    matrix_path = tmp_path / "matrix.json"
    runner_path = tmp_path / "online-runner.py"
    viewed_root = tmp_path / "viewed-results"
    output = tmp_path / "locks" / "online-method.json"
    matrix_path.write_text(json.dumps(matrix()), encoding="utf-8")
    runner_path.write_text("# frozen online runner\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build-online-method-lock",
            "--root",
            str(tmp_path),
            "--matrix",
            str(matrix_path),
            "--online-runner",
            str(runner_path),
            "--viewed-results-root",
            str(viewed_root),
            "--out",
            str(output),
        ],
    )
    assert method_lock_builder.main() == 0
    assert validate_method_lock(json.loads(output.read_text(encoding="utf-8")))[
        "viewed_results_present_at_lock"
    ] is False

    viewed_root.mkdir()
    monkeypatch.setattr(sys, "argv", [*sys.argv[:-1], str(tmp_path / "locks/second.json")])
    with pytest.raises(RuntimeError, match="viewed results already exist"):
        method_lock_builder.main()


def test_training_audit_requires_exact_four_completed_stages() -> None:
    stages = {}
    for cell in TRAINED_CELLS:
        for stage in ("tokenizer", "predictor"):
            stages[f"{cell}:{stage}"] = {
                field: SHA
                for field in (
                    "terminal_sha256",
                    "log_sha256",
                    "summary_sha256",
                    "checkpoint_sha256",
                    "input_tokenizer_sha256",
                    "input_predictor_sha256",
                )
            }
            stages[f"{cell}:{stage}"].update(
                epochs_observed=list(range(1, 31)),
                world_size=2,
                finished_marker_count=1,
                best_validation_loss=0.1,
            )
    payload = seal(
        {
            "schema_version": TRAINING_AUDIT_SCHEMA,
            "status": "PASS",
            "upstream_commit": "67b630e67f6a18c9e9be918d9b4337c960db1e9a",
            "stages": stages,
            **{
                field: SHA
                for field in (
                    "workspace_receipt_sha256",
                    "official_weights_receipt_sha256",
                    "dataset_manifest_sha256",
                    "dataset_admission_sha256",
                    "training_runner_sha256",
                    "terminal_builder_sha256",
                    "runtime_config_sha256",
                    "dataset_adapter_sha256",
                    "train_tokenizer_sha256",
                    "train_predictor_sha256",
                    "ddp_runtime_patch_sha256",
                )
            },
        }
    )
    assert len(validate_training_audit(payload)["stages"]) == 4


def evaluation() -> dict[str, object]:
    return seal(
        {
            "schema_version": EVALUATION_SCHEMA,
            "status": "PASS",
            "test_status": "TEST_VIEWED",
            "used_for_selection": False,
            "promotion_eligible": False,
            "generated_at": "2026-08-14T00:00:00+00:00",
            "entries": [
                {
                    "model_cell_id": cell,
                    "mature_targets_only": True,
                    "signal_sha256": SHA,
                    "candidate_set_sha256": "c" * 64,
                    "metrics": {"rank_ic": 0.01, "rank_icir": 0.1},
                }
                for cell in ACTIVE_CELLS
            ],
        }
    )


def historical() -> dict[str, object]:
    entries = []
    for cell in ACTIVE_CELLS:
        signal = canonical_hash(cell)
        for variant, strategy in STRATEGIES.items():
            entries.append(
                {
                    "model_cell_id": cell,
                    "strategy_variant_id": variant,
                    "strategy": strategy,
                    "sample_count": 5,
                    "test_status": "TEST_VIEWED",
                    "used_for_selection": False,
                    "promotion_eligible": False,
                    "signal_sha256": signal,
                    "holdings_sha256": SHA,
                    "receipt_sha256": SHA,
                }
            )
    return seal(
        {
            "schema_version": HISTORICAL_SCHEMA,
            "status": "PASS",
            "generated_at": "2026-08-14T00:00:00+00:00",
            "artifact_root": "/data/elanquant",
            "entries": entries,
        }
    )


def test_viewed_evaluation_and_same_signal_historical_catalog_validate() -> None:
    assert len(validate_evaluation(evaluation())["entries"]) == 4
    assert len(validate_historical_catalog(historical())["entries"]) == 8
    selected = copy.deepcopy(evaluation())
    selected["used_for_selection"] = True
    selected["receipt_hash"] = canonical_hash(
        {key: value for key, value in selected.items() if key != "receipt_hash"}
    )
    with pytest.raises(ContractError, match="cannot select"):
        validate_evaluation(selected)
    mismatched_candidates = copy.deepcopy(evaluation())
    mismatched_candidates["entries"][0]["candidate_set_sha256"] = "d" * 64
    mismatched_candidates["receipt_hash"] = canonical_hash(
        {
            key: value
            for key, value in mismatched_candidates.items()
            if key != "receipt_hash"
        }
    )
    with pytest.raises(ContractError, match="one candidate set"):
        validate_evaluation(mismatched_candidates)
    different = copy.deepcopy(historical())
    different["entries"][0]["signal_sha256"] = "b" * 64
    different["receipt_hash"] = canonical_hash(
        {key: value for key, value in different.items() if key != "receipt_hash"}
    )
    with pytest.raises(ContractError, match="same signal"):
        validate_historical_catalog(different)


def test_retirement_preserves_old_strict_evidence_without_activation() -> None:
    payload = seal(
        {
            "schema_version": RETIREMENT_SCHEMA,
            "status": "PASS",
            "retired_cell_ids": ["small-strict-pit", "base-strict-pit"],
            "active": False,
            "artifacts_deleted": False,
            "legacy_evidence": [
                {"cell_id": "small-strict-pit", "receipt_sha256": SHA},
                {"cell_id": "base-strict-pit", "receipt_sha256": SHA},
            ],
        }
    )
    assert validate_retirement_receipt(payload)["active"] is False


def admission() -> dict[str, object]:
    coverage = {}
    for name in ("train", "validation", "test_viewed"):
        symbols = {
            "000001.SZ": {"windows": 400},
            "000002.SZ": {"windows": 600},
        }
        coverage[name] = {
            "window_rows": 100 if name == "test_viewed" else 101,
            "symbols": 2,
            "windows": 1000,
            "symbol_coverage_sha256": canonical_hash(symbols),
            "symbol_coverage": symbols,
        }
    return seal(
        {
            "schema_version": ADMISSION_SCHEMA,
            "status": "PASS",
            "dataset_manifest_sha256": SHA,
            "raw_manifest_sha256": SHA,
            "auditor_code_sha256": SHA,
            "membership_rows_reverified": True,
            "excluded_membership_snapshots": {},
            "excluded_membership_snapshots_sha256": canonical_hash({}),
            "every_consumed_membership_snapshot_exactly_300": True,
            "coverage": coverage,
            "actual_effective_ranges": {
                "train": {
                    "first_input": "2011-01-04",
                    "first_anchor": "2011-05-09",
                    "last_anchor": "2022-12-16",
                    "last_target": "2022-12-29",
                    "last_consumed": "2022-12-30",
                },
                "validation": {
                    "first_input": "2022-09-01",
                    "first_anchor": "2023-01-03",
                    "last_anchor": "2024-06-13",
                    "last_target": "2024-06-27",
                    "last_consumed": "2024-06-28",
                },
                "test_viewed": {
                    "first_input": "2024-04-01",
                    "first_anchor": "2024-07-01",
                    "last_anchor": "2026-07-30",
                    "last_target": "2026-08-13",
                    "actual_first_backtest_signal": "2024-07-01",
                },
            },
        }
    )


def test_actual_pickle_admission_rejects_window_and_effective_overlap_tampering() -> None:
    assert validate_dataset_admission(admission())["coverage"]["train"]["window_rows"] == 101
    wrong_rows = copy.deepcopy(admission())
    wrong_rows["coverage"]["test_viewed"]["window_rows"] = 101
    wrong_rows["receipt_hash"] = canonical_hash(
        {key: value for key, value in wrong_rows.items() if key != "receipt_hash"}
    )
    with pytest.raises(ContractError, match="window length"):
        validate_dataset_admission(wrong_rows)
    overlap = copy.deepcopy(admission())
    overlap["actual_effective_ranges"]["test_viewed"]["first_anchor"] = "2024-06-28"
    overlap["receipt_hash"] = canonical_hash(
        {key: value for key, value in overlap.items() if key != "receipt_hash"}
    )
    with pytest.raises(ContractError, match="overlap"):
        validate_dataset_admission(overlap)
    exclusions = copy.deepcopy(admission())
    exclusions["excluded_membership_snapshots"] = {"2022-01-04": 100}
    exclusions["receipt_hash"] = canonical_hash(
        {key: value for key, value in exclusions.items() if key != "receipt_hash"}
    )
    with pytest.raises(ContractError, match="exclusion hash"):
        validate_dataset_admission(exclusions)


def analysis_lock() -> dict[str, object]:
    return seal(
        {
            "schema_version": ANALYSIS_LOCK_SCHEMA,
            "status": "PASS",
            "upstream_commit": "67b630e67f6a18c9e9be918d9b4337c960db1e9a",
            "model_cells": list(ACTIVE_CELLS),
            "strategies": STRATEGIES,
            "sample_count": 5,
            "test_status": "TEST_VIEWED",
            "used_for_selection": False,
            "promotion_eligible": False,
            "results_root_absent_at_lock": True,
            **{
                field: SHA
                for field in (
                    "matrix_sha256",
                    "dataset_manifest_sha256",
                    "dataset_admission_sha256",
                    "test_pickle_sha256",
                    "provider_receipt_sha256",
                    "signal_runner_sha256",
                    "signal_helper_sha256",
                    "evaluation_helper_sha256",
                    "backtest_runner_sha256",
                    "backtest_helper_sha256",
                    "contract_sha256",
                    "qlib_metadata_sha256",
                    "qlib_record_sha256",
                    "qlib_source_tree_sha256",
                    "trade_calendar_sha256",
                )
            },
        }
    )


def test_pre_result_lock_requires_absent_results_and_exact_four_cells() -> None:
    assert len(validate_analysis_lock(analysis_lock())["model_cells"]) == 4
    existing = copy.deepcopy(analysis_lock())
    existing["results_root_absent_at_lock"] = False
    existing["receipt_hash"] = canonical_hash(
        {key: value for key, value in existing.items() if key != "receipt_hash"}
    )
    with pytest.raises(ContractError, match="existed before"):
        validate_analysis_lock(existing)


def signal_receipt() -> dict[str, object]:
    return seal(
        {
            "schema_version": SIGNAL_SCHEMA,
            "status": "PASS",
            "model_cell_id": "small-zero-shot",
            "sample_count": 5,
            "mature_targets_only": True,
            "test_status": "TEST_VIEWED",
            "used_for_selection": False,
            "promotion_eligible": False,
            "label_policy": "NEXT_10_GLOBAL_SESSIONS_LAST_CLOSE_CARRY_ON_MISSING",
            "carried_future_close_rows": 7,
            "support": {"rows": 300, "sessions": 1},
            "metrics": {"rank_ic": 0.01, "rows": 300},
            **{
                field: SHA
                for field in (
                    "analysis_lock_sha256",
                    "matrix_sha256",
                    "dataset_admission_sha256",
                    "signals_sha256",
                    "labels_sha256",
                    "candidate_set_sha256",
                )
            },
        }
    )


def backtest_receipt() -> dict[str, object]:
    return seal(
        {
            "schema_version": BACKTEST_SCHEMA,
            "status": "PASS",
            "id": "official-split-v3-small-zero-shot-test-viewed-official_top50-v1",
            "model_cell_id": "small-zero-shot",
            "evaluation_split": "test_viewed_official_v3",
            "strategy_variant_id": "official_top50",
            "strategy": STRATEGIES["official_top50"],
            "execution": {"account": 100_000_000},
            "primary_signal": "mean",
            "sample_count": 5,
            "test_status": "TEST_VIEWED",
            "test_data_access": "VIEWED",
            "selection_eligible": False,
            "used_for_selection": False,
            "promotion_eligible": False,
            "online_paper_equivalent": False,
            "qlib": {
                "version": "0.9.7",
                "metadata_sha256": SHA,
                "record_sha256": SHA,
                "source_tree_sha256": SHA,
            },
            "metrics": {"mean": {"total_return_with_cost": 0.01}},
            **{
                field: SHA
                for field in (
                    "analysis_lock_sha256",
                    "source_signal_receipt_sha256",
                    "source_signal_sha256",
                    "provider_receipt_sha256",
                    "backtest_code_sha256",
                    "daily_series_sha256",
                    "raw_report_sha256",
                    "holdings_sha256",
                )
            },
        }
    )


def test_mature_signal_and_backtest_receipts_reject_selection_or_signal_drift() -> None:
    assert validate_signal_receipt(signal_receipt())["sample_count"] == 5
    assert validate_backtest_receipt(backtest_receipt())["sample_count"] == 5
    immature = copy.deepcopy(signal_receipt())
    immature["mature_targets_only"] = False
    immature["receipt_hash"] = canonical_hash(
        {key: value for key, value in immature.items() if key != "receipt_hash"}
    )
    with pytest.raises(ContractError, match="maturity"):
        validate_signal_receipt(immature)
    selected = copy.deepcopy(backtest_receipt())
    selected["used_for_selection"] = True
    selected["receipt_hash"] = canonical_hash(
        {key: value for key, value in selected.items() if key != "receipt_hash"}
    )
    with pytest.raises(ContractError, match="firewall"):
        validate_backtest_receipt(selected)
