"""Fail-closed contracts for the immutable Kronos official-split v3 release.

This module is deliberately standard-library only.  It describes evidence; it
does not download data, load a model, train, infer, or backtest.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

UPSTREAM_COMMIT = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"
LOOKBACK = 90
PREDICT = 10
TRAINING_ROWS = 101
INFERENCE_ROWS = 100
RAW_RANGES = {
    "train": (date(2011, 1, 1), date(2022, 12, 31)),
    "validation": (date(2022, 9, 1), date(2024, 6, 30)),
    "test_viewed": (date(2024, 4, 1), None),
}
REQUESTED_BACKTEST_START = date(2024, 7, 1)

SPLIT_SCHEMA = "elanquant_kronos_official_split_v3"
DATASET_SCHEMA = "elanquant_official_split_dataset_v3"
ADMISSION_SCHEMA = "elanquant_official_split_dataset_admission_v3"
MATRIX_SCHEMA = "elanquant_kronos_four_cell_matrix_v3"
ANALYSIS_LOCK_SCHEMA = "elanquant_kronos_official_split_analysis_lock_v3"
SIGNAL_SCHEMA = "elanquant_kronos_official_split_signal_v3"
BACKTEST_SCHEMA = "elanquant_kronos_official_split_backtest_v3"
EVALUATION_SCHEMA = "elanquant_kronos_rolling_evaluation_v3"
HISTORICAL_SCHEMA = "elanquant_kronos_historical_catalog_v3"
RETIREMENT_SCHEMA = "elanquant_kronos_strict_retirement_v1"
TERMINAL_SCHEMA = "elanquant_training_terminal_v3"

ACTIVE_CELLS = (
    "base-official-ft",
    "base-zero-shot",
    "small-official-ft",
    "small-zero-shot",
)
TRAINED_CELLS = ("base-official-ft", "small-official-ft")
RETIRED_STRICT_CELLS = ("base-strict-pit", "small-strict-pit")
STRATEGIES = {
    "historical_top3": {
        "topk": 3,
        "n_drop": 1,
        "hold_thresh": 5,
        "method_sell": "bottom",
        "method_buy": "top",
        "only_tradable": False,
        "forbid_all_trade_at_limit": True,
        "risk_degree": 0.95,
    },
    "official_top50": {
        "topk": 50,
        "n_drop": 5,
        "hold_thresh": 5,
        "method_sell": "bottom",
        "method_buy": "top",
        "only_tradable": False,
        "forbid_all_trade_at_limit": True,
    },
}
DATASET_FILES = {
    "train": "official/train_data.pkl",
    "validation": "official/val_data.pkl",
    "test_viewed": "official/test_data.pkl",
}

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ContractError(RuntimeError):
    """Raised when official-split evidence is incomplete or inconsistent."""


def canonical_json(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
        default=lambda value: value.isoformat() if isinstance(value, date) else asdict(value),
    )


def canonical_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ContractError(f"{field} must be a lowercase SHA-256")
    return value


def _sealed(payload: Mapping[str, Any], schema: str) -> dict[str, Any]:
    value = dict(payload)
    claimed = value.pop("receipt_hash", None)
    if value.get("schema_version") != schema or value.get("status") != "PASS":
        raise ContractError(f"expected terminal PASS {schema}")
    if claimed != canonical_hash(value):
        raise ContractError("receipt hash mismatch")
    value["receipt_hash"] = claimed
    return value


def _calendar(values: Sequence[date], frozen_latest: date) -> tuple[date, ...]:
    result = tuple(values)
    if result != tuple(sorted(set(result))):
        raise ContractError("calendar must be unique and increasing")
    if not result or result[-1] != frozen_latest:
        raise ContractError("frozen latest must be the final calendar session")
    return result


@dataclass(frozen=True)
class Window:
    partition: str
    input_start: date
    anchor: date
    target_start: date
    target_end: date
    consumed_end: date | None
    rows: int


def _windows(
    calendar: tuple[date, ...],
    partition: str,
    raw_start: date,
    raw_end: date,
    *,
    after: date | None,
    training: bool,
) -> tuple[Window, ...]:
    bounded = tuple(day for day in calendar if raw_start <= day <= raw_end)
    required = TRAINING_ROWS if training else INFERENCE_ROWS
    result: list[Window] = []
    for start in range(0, len(bounded) - required + 1):
        chunk = bounded[start : start + required]
        anchor = chunk[LOOKBACK - 1]
        if after is not None and anchor <= after:
            continue
        result.append(
            Window(
                partition=partition,
                input_start=chunk[0],
                anchor=anchor,
                target_start=chunk[LOOKBACK],
                target_end=chunk[LOOKBACK + PREDICT - 1],
                consumed_end=chunk[-1] if training else None,
                rows=required,
            )
        )
    if not result:
        raise ContractError(f"no mature {partition} windows")
    return tuple(result)


def build_split_receipt(
    trading_sessions: Sequence[date], *, frozen_latest: date
) -> dict[str, Any]:
    """Build official raw-slice windows and prove effective ranges are disjoint."""

    calendar = _calendar(trading_sessions, frozen_latest)
    train = _windows(
        calendar, "TRAIN", *RAW_RANGES["train"], after=None, training=True  # type: ignore[arg-type]
    )
    train_end = train[-1].consumed_end
    assert train_end is not None
    validation = _windows(
        calendar,
        "VALIDATION",
        *RAW_RANGES["validation"],  # type: ignore[arg-type]
        after=train_end,
        training=True,
    )
    validation_end = validation[-1].consumed_end
    assert validation_end is not None
    test = _windows(
        calendar,
        "TEST_VIEWED",
        RAW_RANGES["test_viewed"][0],
        frozen_latest,
        after=validation_end,
        training=False,
    )
    actual_backtest = next(
        (window.anchor for window in test if window.anchor >= REQUESTED_BACKTEST_START), None
    )
    if actual_backtest is None:
        raise ContractError("requested backtest range has no mature signal")

    def summary(rows: tuple[Window, ...]) -> dict[str, Any]:
        return {
            "count": len(rows),
            "first_input": rows[0].input_start.isoformat(),
            "first_anchor": rows[0].anchor.isoformat(),
            "last_anchor": rows[-1].anchor.isoformat(),
            "last_target": rows[-1].target_end.isoformat(),
            "last_consumed": (
                rows[-1].consumed_end.isoformat() if rows[-1].consumed_end else None
            ),
        }

    payload: dict[str, Any] = {
        "schema_version": SPLIT_SCHEMA,
        "status": "PASS",
        "upstream_commit": UPSTREAM_COMMIT,
        "frozen_latest_session": frozen_latest.isoformat(),
        "calendar_sha256": canonical_hash([day.isoformat() for day in calendar]),
        "lookback": LOOKBACK,
        "predict": PREDICT,
        "training_window_rows": TRAINING_ROWS,
        "inference_window_rows": INFERENCE_ROWS,
        "raw_ranges": {
            "train": ["2011-01-01", "2022-12-31"],
            "validation": ["2022-09-01", "2024-06-30"],
            "test_viewed": ["2024-04-01", frozen_latest.isoformat()],
        },
        "effective_ranges": {
            "train": summary(train),
            "validation": summary(validation),
            "test_viewed": summary(test),
        },
        "backtest_range": {
            "requested_start": REQUESTED_BACKTEST_START.isoformat(),
            "actual_first_signal": actual_backtest.isoformat(),
            "actual_last_signal": test[-1].anchor.isoformat(),
        },
        "test_status": "TEST_VIEWED",
        "used_for_selection": False,
        "promotion_eligible": False,
    }
    payload["receipt_hash"] = canonical_hash(payload)
    validate_split_receipt(payload)
    return payload


def validate_split_receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = _sealed(payload, SPLIT_SCHEMA)
    if value.get("upstream_commit") != UPSTREAM_COMMIT:
        raise ContractError("upstream commit mismatch")
    if (value.get("lookback"), value.get("predict")) != (LOOKBACK, PREDICT):
        raise ContractError("90/10 horizon mismatch")
    if (value.get("training_window_rows"), value.get("inference_window_rows")) != (
        TRAINING_ROWS,
        INFERENCE_ROWS,
    ):
        raise ContractError("official row semantics mismatch")
    frozen = str(value["frozen_latest_session"])
    expected_ranges = {
        "train": ["2011-01-01", "2022-12-31"],
        "validation": ["2022-09-01", "2024-06-30"],
        "test_viewed": ["2024-04-01", frozen],
    }
    if value.get("raw_ranges") != expected_ranges:
        raise ContractError("official raw ranges mismatch")
    effective = value.get("effective_ranges")
    if not isinstance(effective, Mapping):
        raise ContractError("effective ranges missing")
    train_end = str(effective["train"]["last_consumed"])
    val_start = str(effective["validation"]["first_anchor"])
    val_end = str(effective["validation"]["last_consumed"])
    test_start = str(effective["test_viewed"]["first_anchor"])
    if not train_end < val_start or not val_end < test_start:
        raise ContractError("effective partitions overlap")
    backtest = value.get("backtest_range")
    if not isinstance(backtest, Mapping) or backtest.get("requested_start") != "2024-07-01":
        raise ContractError("requested backtest start mismatch")
    if str(backtest.get("actual_first_signal")) < "2024-07-01":
        raise ContractError("actual backtest signal precedes requested start")
    if (
        value.get("test_status") != "TEST_VIEWED"
        or value.get("used_for_selection") is not False
        or value.get("promotion_eligible") is not False
    ):
        raise ContractError("opened test selection boundary violated")
    _sha(value.get("calendar_sha256"), "calendar_sha256")
    return value


def validate_dataset_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = _sealed(payload, DATASET_SCHEMA)
    split = value.get("split_contract")
    if not isinstance(split, Mapping):
        raise ContractError("dataset split contract missing")
    validated_split = validate_split_receipt(split)
    if value.get("split_receipt_hash") != validated_split["receipt_hash"]:
        raise ContractError("dataset split receipt binding mismatch")
    if value.get("future_symbol_row_conditioning") is not False:
        raise ContractError("dataset may not use future symbol-row conditioning")
    exclusions = value.get("excluded_membership_snapshots")
    if not isinstance(exclusions, Mapping):
        raise ContractError("membership snapshot exclusions missing")
    if value.get("excluded_membership_snapshots_sha256") != canonical_hash(exclusions):
        raise ContractError("membership snapshot exclusion hash mismatch")
    if (
        value.get("every_consumed_membership_snapshot_exactly_300") is not True
        or value.get("partial_membership_forward_filled") is not False
        or value.get("excluded_snapshot_effect")
        != "ignored; prior complete snapshot remains active"
    ):
        raise ContractError("partial membership snapshot entered the consumed stream")
    if int(value.get("consumed_membership_snapshot_count", 0)) <= 0:
        raise ContractError("no complete membership snapshot was consumed")
    files = value.get("files")
    if not isinstance(files, Mapping) or set(files) != set(DATASET_FILES.values()):
        raise ContractError("dataset file inventory is not exact")
    for identity, entry in files.items():
        if not isinstance(entry, Mapping) or not isinstance(entry.get("bytes"), int):
            raise ContractError(f"dataset file metadata invalid: {identity}")
        if entry["bytes"] <= 0:
            raise ContractError(f"dataset file is empty: {identity}")
        _sha(entry.get("sha256"), f"dataset.{identity}.sha256")
    _sha(value.get("raw_manifest_sha256"), "raw_manifest_sha256")
    _sha(value.get("membership_availability_sha256"), "membership_availability_sha256")
    _sha(value.get("materializer_code_sha256"), "materializer_code_sha256")
    return value


def validate_dataset_admission(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = _sealed(payload, ADMISSION_SCHEMA)
    for field in ("dataset_manifest_sha256", "raw_manifest_sha256", "auditor_code_sha256"):
        _sha(value.get(field), field)
    exclusions = value.get("excluded_membership_snapshots")
    if not isinstance(exclusions, Mapping):
        raise ContractError("admission membership exclusions missing")
    if value.get("excluded_membership_snapshots_sha256") != canonical_hash(exclusions):
        raise ContractError("admission membership exclusion hash mismatch")
    if value.get("every_consumed_membership_snapshot_exactly_300") is not True:
        raise ContractError("admission consumed a partial membership snapshot")
    coverage = value.get("coverage")
    if not isinstance(coverage, Mapping) or set(coverage) != set(DATASET_FILES):
        raise ContractError("dataset admission coverage is not exact")
    for split_name, expected_rows in (
        ("train", TRAINING_ROWS),
        ("validation", TRAINING_ROWS),
        ("test_viewed", INFERENCE_ROWS),
    ):
        row = coverage[split_name]
        if not isinstance(row, Mapping):
            raise ContractError(f"coverage is invalid: {split_name}")
        if row.get("window_rows") != expected_rows:
            raise ContractError(f"window length mismatch: {split_name}")
        if not isinstance(row.get("symbols"), int) or int(row["symbols"]) <= 0:
            raise ContractError(f"symbol coverage missing: {split_name}")
        if not isinstance(row.get("windows"), int) or int(row["windows"]) <= 0:
            raise ContractError(f"window coverage missing: {split_name}")
        _sha(row.get("symbol_coverage_sha256"), f"coverage.{split_name}.sha256")
        symbol_coverage = row.get("symbol_coverage")
        if not isinstance(symbol_coverage, Mapping):
            raise ContractError(f"per-symbol coverage missing: {split_name}")
        if row["symbol_coverage_sha256"] != canonical_hash(symbol_coverage):
            raise ContractError(f"per-symbol coverage hash mismatch: {split_name}")
        if len(symbol_coverage) != row["symbols"]:
            raise ContractError(f"per-symbol count mismatch: {split_name}")
        if sum(int(item["windows"]) for item in symbol_coverage.values()) != row["windows"]:
            raise ContractError(f"per-symbol window total mismatch: {split_name}")
    actual = value.get("actual_effective_ranges")
    if not isinstance(actual, Mapping) or set(actual) != set(DATASET_FILES):
        raise ContractError("actual effective ranges are not exact")
    for split_name, row in actual.items():
        if not isinstance(row, Mapping):
            raise ContractError(f"actual effective range invalid: {split_name}")
        for field in ("first_input", "first_anchor", "last_anchor", "last_target"):
            if not isinstance(row.get(field), str):
                raise ContractError(f"actual effective boundary missing: {split_name}.{field}")
    train_end = str(actual["train"]["last_consumed"])
    val_start = str(actual["validation"]["first_anchor"])
    val_end = str(actual["validation"]["last_consumed"])
    test_start = str(actual["test_viewed"]["first_anchor"])
    if not train_end < val_start or not val_end < test_start:
        raise ContractError("actual per-symbol effective ranges overlap")
    if str(actual["test_viewed"]["actual_first_backtest_signal"]) < "2024-07-01":
        raise ContractError("actual per-symbol backtest starts too early")
    if value.get("membership_rows_reverified") is not True:
        raise ContractError("per-symbol membership rows were not reverified")
    return value


def validate_training_terminal(payload: Mapping[str, Any], *, cell_id: str) -> dict[str, Any]:
    value = _sealed(payload, TERMINAL_SCHEMA)
    if cell_id not in TRAINED_CELLS or value.get("cell_id") != cell_id:
        raise ContractError("terminal cell mismatch")
    if value.get("stage") not in {"tokenizer", "predictor"}:
        raise ContractError("unknown training stage")
    if value.get("epochs_completed") != 30 or value.get("selected_checkpoint") != "best_model":
        raise ContractError("author 30-epoch/best-model behavior mismatch")
    for field in ("data_manifest_sha256", "config_sha256", "checkpoint_sha256"):
        _sha(value.get(field), field)
    return value


def validate_matrix(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = _sealed(payload, MATRIX_SCHEMA)
    if value.get("upstream_commit") != UPSTREAM_COMMIT:
        raise ContractError("matrix upstream mismatch")
    cells = value.get("cells")
    observed_cells = (
        tuple(sorted(str(row.get("id")) for row in cells))
        if isinstance(cells, list)
        else ()
    )
    if observed_cells != ACTIVE_CELLS:
        raise ContractError("active matrix must contain exactly four official cells")
    assert isinstance(cells, list)
    for row in cells:
        cell_id = str(row["id"])
        if "strict" in cell_id:
            raise ContractError("strict-PIT cannot be active")
        expected_mode = "official_ft" if cell_id in TRAINED_CELLS else "zero_shot"
        if row.get("training_mode") != expected_mode:
            raise ContractError("cell training mode mismatch")
        for field in ("tokenizer_sha256", "predictor_sha256", "config_sha256"):
            _sha(row.get(field), field)
        for field in ("tokenizer_path", "predictor_path"):
            path = row.get(field)
            if not isinstance(path, str) or not path or not path.startswith("/"):
                raise ContractError(f"{cell_id}.{field} must be an absolute model directory")
        if expected_mode == "official_ft":
            _sha(row.get("tokenizer_terminal_sha256"), "tokenizer_terminal_sha256")
            _sha(row.get("predictor_terminal_sha256"), "predictor_terminal_sha256")
            if row.get("predictor_input_tokenizer_sha256") != row.get("tokenizer_sha256"):
                raise ContractError("predictor is not linked to its trained tokenizer")
    _sha(value.get("split_receipt_sha256"), "split_receipt_sha256")
    return value


def validate_analysis_lock(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = _sealed(payload, ANALYSIS_LOCK_SCHEMA)
    if value.get("upstream_commit") != UPSTREAM_COMMIT:
        raise ContractError("analysis lock upstream mismatch")
    if tuple(value.get("model_cells", ())) != ACTIVE_CELLS:
        raise ContractError("analysis lock model cells are not exact")
    if value.get("strategies") != STRATEGIES or value.get("sample_count") != 5:
        raise ContractError("analysis lock strategy or sampling mismatch")
    if (
        value.get("test_status") != "TEST_VIEWED"
        or value.get("used_for_selection") is not False
        or value.get("promotion_eligible") is not False
    ):
        raise ContractError("analysis lock test firewall mismatch")
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
    ):
        _sha(value.get(field), field)
    if value.get("results_root_absent_at_lock") is not True:
        raise ContractError("analysis results existed before the lock")
    return value


def validate_signal_receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = _sealed(payload, SIGNAL_SCHEMA)
    if value.get("model_cell_id") not in ACTIVE_CELLS:
        raise ContractError("signal model cell is inactive")
    if value.get("sample_count") != 5 or value.get("mature_targets_only") is not True:
        raise ContractError("signal sampling or maturity mismatch")
    if (
        value.get("test_status") != "TEST_VIEWED"
        or value.get("used_for_selection") is not False
        or value.get("promotion_eligible") is not False
    ):
        raise ContractError("signal test firewall mismatch")
    for field in (
        "analysis_lock_sha256",
        "matrix_sha256",
        "dataset_admission_sha256",
        "signals_sha256",
        "labels_sha256",
        "candidate_set_sha256",
    ):
        _sha(value.get(field), field)
    support = value.get("support")
    if not isinstance(support, Mapping):
        raise ContractError("signal support missing")
    if int(support.get("rows", 0)) <= 0 or int(support.get("sessions", 0)) <= 0:
        raise ContractError("signal support is empty")
    metrics = value.get("metrics")
    if not isinstance(metrics, Mapping) or not metrics:
        raise ContractError("signal evaluation metrics missing")
    for metric in metrics.values():
        if metric is not None and (
            not isinstance(metric, (int, float)) or not math.isfinite(metric)
        ):
            raise ContractError("signal evaluation metric is not finite")
    return value


def validate_backtest_receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = _sealed(payload, BACKTEST_SCHEMA)
    cell = str(value.get("model_cell_id"))
    variant = str(value.get("strategy_variant_id"))
    if cell not in ACTIVE_CELLS or variant not in STRATEGIES:
        raise ContractError("backtest cell or strategy is invalid")
    if value.get("strategy") != STRATEGIES[variant] or value.get("sample_count") != 5:
        raise ContractError("backtest strategy or sample count mismatch")
    if (
        value.get("test_status") != "TEST_VIEWED"
        or value.get("evaluation_split") != "test_viewed_official_v3"
        or value.get("test_data_access") != "VIEWED"
        or value.get("selection_eligible") is not False
        or value.get("used_for_selection") is not False
        or value.get("promotion_eligible") is not False
        or value.get("online_paper_equivalent") is not False
        or value.get("primary_signal") != "mean"
    ):
        raise ContractError("backtest test firewall mismatch")
    for field in (
        "analysis_lock_sha256",
        "source_signal_receipt_sha256",
        "source_signal_sha256",
        "provider_receipt_sha256",
        "backtest_code_sha256",
        "daily_series_sha256",
        "raw_report_sha256",
        "holdings_sha256",
    ):
        _sha(value.get(field), field)
    if not isinstance(value.get("id"), str) or not str(value["id"]).startswith(
        f"official-split-v3-{cell}-test-viewed-{variant}-"
    ):
        raise ContractError("backtest public identity is invalid")
    if value.get("execution") is None or value.get("sample_count") != 5:
        raise ContractError("backtest execution or sampling identity is invalid")
    qlib = value.get("qlib")
    if not isinstance(qlib, Mapping):
        raise ContractError("backtest Qlib identity missing")
    for field in ("metadata_sha256", "record_sha256", "source_tree_sha256"):
        _sha(qlib.get(field), f"qlib.{field}")
    metrics = value.get("metrics")
    if not isinstance(metrics, Mapping) or not metrics:
        raise ContractError("backtest metrics missing")
    for signal_metrics in metrics.values():
        if not isinstance(signal_metrics, Mapping):
            raise ContractError("backtest signal metrics invalid")
        if any(
            not isinstance(metric, (int, float)) or not math.isfinite(metric)
            for metric in signal_metrics.values()
        ):
            raise ContractError("backtest metric is not finite")
    return value


def validate_evaluation(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = _sealed(payload, EVALUATION_SCHEMA)
    if value.get("test_status") != "TEST_VIEWED":
        raise ContractError("evaluation must be TEST_VIEWED")
    if value.get("used_for_selection") is not False or value.get("promotion_eligible") is not False:
        raise ContractError("opened test cannot select or promote")
    entries = value.get("entries")
    observed_cells = (
        tuple(sorted(str(row.get("model_cell_id")) for row in entries))
        if isinstance(entries, list)
        else ()
    )
    if observed_cells != ACTIVE_CELLS:
        raise ContractError("evaluation must contain the exact four active cells")
    assert isinstance(entries, list)
    for row in entries:
        if row.get("mature_targets_only") is not True:
            raise ContractError("evaluation contains immature targets")
        _sha(row.get("signal_sha256"), "signal_sha256")
        metrics = row.get("metrics")
        if not isinstance(metrics, Mapping) or not metrics:
            raise ContractError("evaluation metrics missing")
        if any(
            not isinstance(item, (int, float)) or not math.isfinite(item)
            for item in metrics.values()
        ):
            raise ContractError("evaluation metrics must be finite")
    return value


def validate_historical_catalog(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = _sealed(payload, HISTORICAL_SCHEMA)
    entries = value.get("entries")
    if not isinstance(entries, list) or len(entries) != 8:
        raise ContractError("historical catalog must contain exactly eight entries")
    expected = {(cell, variant) for cell in ACTIVE_CELLS for variant in STRATEGIES}
    observed = {
        (str(row.get("model_cell_id")), str(row.get("strategy_variant_id")))
        for row in entries
    }
    if observed != expected:
        raise ContractError("historical matrix identity mismatch")
    by_cell: dict[str, list[Mapping[str, Any]]] = {}
    for row in entries:
        cell = str(row["model_cell_id"])
        by_cell.setdefault(cell, []).append(row)
        variant = str(row["strategy_variant_id"])
        if row.get("strategy") != STRATEGIES[variant] or row.get("sample_count") != 5:
            raise ContractError("strategy or official sample count mismatch")
        if (
            row.get("test_status") != "TEST_VIEWED"
            or row.get("used_for_selection") is not False
            or row.get("promotion_eligible") is not False
        ):
            raise ContractError("historical test boundary violated")
        for field in ("signal_sha256", "holdings_sha256", "receipt_sha256"):
            _sha(row.get(field), field)
    if any(len({str(row["signal_sha256"]) for row in rows}) != 1 for rows in by_cell.values()):
        raise ContractError("Top50 and Top3 must reuse the same signal bytes")
    return value


def validate_retirement_receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = _sealed(payload, RETIREMENT_SCHEMA)
    if tuple(sorted(value.get("retired_cell_ids", []))) != RETIRED_STRICT_CELLS:
        raise ContractError("retirement receipt must name both old strict cells")
    if value.get("artifacts_deleted") is not False or value.get("active") is not False:
        raise ContractError("strict retirement must preserve evidence and remain inactive")
    evidence = value.get("legacy_evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ContractError("legacy strict evidence bindings missing")
    for row in evidence:
        _sha(row.get("receipt_sha256"), "legacy receipt_sha256")
    return value
