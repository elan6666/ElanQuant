#!/usr/bin/env python3
"""Generate the pinned Kronos demo's four standardized-space signals.

This is intentionally separate from ElanQuant's inverse-price Top-3 online
signal. It consumes one explicitly selected sealed slice and the Small
official-style fine-tuned cell, then publishes an immutable receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import random
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from elanquant.contracts.historical_matrix import (
    MODEL_CELLS,
)
from elanquant.contracts.historical_matrix import (
    SIGNAL_SCHEMA as MATRIX_SIGNAL_SCHEMA,
)
from elanquant.contracts.historical_matrix import (
    validate_signal_receipt as validate_matrix_signal_receipt,
)
from elanquant.contracts.official_demo import (
    FINAL_TEST_SIGNAL_SCHEMA,
    FINAL_TEST_STRATEGY_ID,
    MODEL_CELL,
    PRIMARY_SIGNAL,
    SIGNAL_SCHEMA,
    SIGNALS,
    STRATEGY_ID,
    canonical_hash,
    sha256_file,
    standardized_close_signals,
    validate_analysis_lock,
    validate_signal_receipt,
)

UPSTREAM_COMMIT = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"
FEATURES = ["open", "high", "low", "close", "vol", "amt"]
LOOKBACK = 90
PREDICT = 10
SAMPLE_COUNT = 5
TOTAL_BATCH = 1000
SERIES_BATCH = TOTAL_BATCH // SAMPLE_COUNT
SEED = 100


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def verify_upstream(upstream: Path) -> None:
    head = subprocess.run(
        ["git", "-C", str(upstream), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "-C", str(upstream), "status", "--porcelain", "--untracked-files=no"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if head != UPSTREAM_COMMIT or status:
        raise RuntimeError("Kronos upstream is not the pinned clean source")


def load_matrix(path: Path, model_cell: str) -> tuple[dict[str, Any], dict[str, Any]]:
    matrix = json.loads(path.read_text(encoding="utf-8"))
    content = dict(matrix)
    claimed = content.pop("receipt_hash", None)
    if (
        matrix.get("schema_version") != "elanquant_training_matrix_v2"
        or matrix.get("status") != "PASS"
        or canonical_hash(content) != claimed
    ):
        raise RuntimeError("training matrix is not sealed PASS")
    cells = [cell for cell in matrix.get("cells", []) if cell.get("id") == model_cell]
    expected_track = MODEL_CELLS[model_cell][1]
    if len(cells) != 1 or cells[0].get("track") != expected_track:
        raise RuntimeError(f"sealed model cell is absent: {model_cell}")
    return matrix, cells[0]


def time_features(index: pd.Index) -> np.ndarray:
    timestamps = pd.Series(pd.to_datetime(index))
    return np.stack(
        [
            timestamps.dt.minute,
            timestamps.dt.hour,
            timestamps.dt.weekday,
            timestamps.dt.day,
            timestamps.dt.month,
        ],
        axis=1,
    ).astype(np.float32)


def normalized_context(frame: pd.DataFrame) -> np.ndarray:
    values = frame[FEATURES].to_numpy(dtype=np.float32)
    mean = np.mean(values, axis=0)
    std = np.std(values, axis=0)
    return np.clip((values - mean) / (std + 1e-5), -5.0, 5.0).astype(np.float32)


def rng_hash(torch_module: Any) -> str:
    digest = hashlib.sha256()
    digest.update(torch_module.get_rng_state().cpu().numpy().tobytes())
    if torch_module.cuda.is_available():
        for state in torch_module.cuda.get_rng_state_all():
            digest.update(state.cpu().numpy().tobytes())
    return digest.hexdigest()


def candidate_windows(
    data: dict[str, pd.DataFrame], start: pd.Timestamp, end: pd.Timestamp
) -> list[tuple[str, tuple[pd.Timestamp, ...], tuple[pd.Timestamp, ...]]]:
    """Build candidates from information available at the signal close.

    Eligibility requires the symbol to have the complete preceding 90 global
    exchange sessions through T.  The forecast stamps are the next ten global
    sessions, but their symbol rows are never inspected.  This prevents future
    membership or future missing rows from changing the T-day universe.
    """

    calendar = pd.DatetimeIndex(
        sorted({pd.Timestamp(day) for frame in data.values() for day in frame.index})
    )
    candidates: list[tuple[str, tuple[pd.Timestamp, ...], tuple[pd.Timestamp, ...]]] = []
    eligible_positions = [
        position
        for position in range(LOOKBACK - 1, len(calendar) - PREDICT)
        if calendar[position] >= start and calendar[position + PREDICT] <= end
    ]
    for code in sorted(data):
        frame = data[code].sort_index()
        available = {pd.Timestamp(day) for day in frame.index}
        for position in eligible_positions:
            context_dates = tuple(calendar[position - LOOKBACK + 1 : position + 1])
            if all(day in available for day in context_dates):
                future_dates = tuple(calendar[position + 1 : position + PREDICT + 1])
                candidates.append((code, context_dates, future_dates))
    return candidates


def referenced_windows(
    data: dict[str, pd.DataFrame],
    reference: pd.DataFrame,
    split: str,
) -> list[tuple[str, tuple[pd.Timestamp, ...], tuple[pd.Timestamp, ...]]]:
    """Rebuild the exact sealed anchor set without inspecting target values."""

    calendar = pd.DatetimeIndex(
        sorted({pd.Timestamp(day) for frame in data.values() for day in frame.index})
    )
    calendar_position = {day: index for index, day in enumerate(calendar)}
    result: list[tuple[str, tuple[pd.Timestamp, ...], tuple[pd.Timestamp, ...]]] = []
    for row in reference[["datetime", "instrument"]].itertuples(index=False):
        session, code = pd.Timestamp(row.datetime), str(row.instrument)
        frame = data[code].sort_index()
        if split == "validation_2025":
            position = frame.index.get_indexer([session])[0]
            if position < LOOKBACK - 1 or position + PREDICT >= len(frame):
                raise RuntimeError(
                    f"reference anchor is outside its symbol slice: {code}/{session}"
                )
            context_dates = tuple(
                pd.DatetimeIndex(frame.index[position - LOOKBACK + 1 : position + 1])
            )
            future_dates = tuple(
                pd.DatetimeIndex(frame.index[position + 1 : position + PREDICT + 1])
            )
        else:
            position = calendar_position.get(session, -1)
            if position < LOOKBACK - 1 or position + PREDICT >= len(calendar):
                raise RuntimeError(f"reference anchor is outside the exchange calendar: {session}")
            context_dates = tuple(calendar[position - LOOKBACK + 1 : position + 1])
            future_dates = tuple(calendar[position + 1 : position + PREDICT + 1])
            available = {pd.Timestamp(day) for day in frame.index}
            if not all(day in available for day in context_dates):
                raise RuntimeError(f"reference anchor lacks causal context: {code}/{session}")
        result.append((code, context_dates, future_dates))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--model-cell", choices=tuple(MODEL_CELLS), default=MODEL_CELL)
    parser.add_argument("--reference-signal-receipt", type=Path)
    parser.add_argument(
        "--evaluation-split",
        choices=("validation_2025", "test_viewed_2026"),
        default="validation_2025",
    )
    parser.add_argument("--analysis-lock", type=Path)
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args()

    final_test = args.evaluation_split == "test_viewed_2026"
    matrix_mode = args.model_cell != MODEL_CELL or args.reference_signal_receipt is not None
    strategy_id = FINAL_TEST_STRATEGY_ID if final_test else STRATEGY_ID
    receipt_schema = FINAL_TEST_SIGNAL_SCHEMA if final_test else SIGNAL_SCHEMA
    if final_test and not matrix_mode and args.analysis_lock is None:
        raise RuntimeError("final-test signal generation requires an analysis lock")

    root = args.root.resolve()
    upstream = args.upstream.resolve()
    matrix_path = args.matrix.resolve()
    dataset_path = args.dataset.resolve()
    out_dir = args.out_dir.resolve()
    if out_dir.exists():
        raise RuntimeError("official demo signal output is immutable; use a new run id")
    if root not in out_dir.parents:
        raise RuntimeError("official demo output must remain under the ElanQuant root")
    verify_upstream(upstream)
    if matrix_mode and args.reference_signal_receipt is None:
        raise RuntimeError("historical matrix signal generation requires a reference receipt")
    matrix, cell = load_matrix(matrix_path, args.model_cell)
    manifest_sha256 = sha256_file(args.dataset_manifest)
    generator_code_sha256 = sha256_file(Path(__file__).resolve())
    manifest = json.loads(args.dataset_manifest.read_text(encoding="utf-8"))
    relative_dataset = dataset_path.relative_to(args.dataset_manifest.parent).as_posix()
    dataset_entry = manifest.get("files", {}).get(relative_dataset)
    if (
        manifest.get("status") != "PASS"
        or matrix.get("data_manifest_sha256") != manifest_sha256
        or not isinstance(dataset_entry, dict)
        or dataset_entry.get("sha256") != sha256_file(dataset_path)
    ):
        raise RuntimeError("validation dataset does not match its admitted manifest")
    analysis_lock = None
    if final_test and not matrix_mode:
        assert args.analysis_lock is not None
        analysis_lock = validate_analysis_lock(
            json.loads(args.analysis_lock.read_text(encoding="utf-8"))
        )
        if (
            analysis_lock["training_matrix_sha256"] != sha256_file(matrix_path)
            or analysis_lock["dataset_manifest_sha256"] != manifest_sha256
            or analysis_lock["dataset_file_sha256"] != sha256_file(dataset_path)
            or analysis_lock["tokenizer_sha256"] != cell["tokenizer_sha256"]
            or analysis_lock["predictor_sha256"] != cell["predictor_sha256"]
            or analysis_lock["model_config_sha256"] != cell["config_sha256"]
        ):
            raise RuntimeError("analysis lock differs from final-test inputs")
    tokenizer_path = Path(str(cell["tokenizer_path"]))
    predictor_path = Path(str(cell["predictor_path"]))
    tokenizer_file = tokenizer_path / "model.safetensors"
    predictor_file = predictor_path / "model.safetensors"
    if (
        sha256_file(tokenizer_file) != cell["tokenizer_sha256"]
        or sha256_file(predictor_file) != cell["predictor_sha256"]
    ):
        raise RuntimeError("model checkpoint no longer matches the matrix")

    sys.path.insert(0, str(upstream))
    import torch
    from model.kronos import Kronos, KronosTokenizer, auto_regressive_inference

    data = pickle.loads(dataset_path.read_bytes())
    if not isinstance(data, dict) or not data:
        raise RuntimeError("official evaluation dataset is empty")
    start, end = pd.Timestamp(args.start), pd.Timestamp(args.end)
    reference_receipt = None
    if args.reference_signal_receipt is not None:
        reference_receipt = json.loads(args.reference_signal_receipt.read_text(encoding="utf-8"))
        reference_artifact = reference_receipt.get("artifacts", {}).get("signals")
        if not isinstance(reference_artifact, dict):
            raise RuntimeError("reference signal artifact is absent")
        reference_path = (root / str(reference_artifact["path"])).resolve()
        if sha256_file(reference_path) != reference_artifact.get("sha256"):
            raise RuntimeError("reference signal artifact changed")
        reference = pd.read_csv(reference_path, parse_dates=["datetime"])
        candidates = referenced_windows(data, reference, args.evaluation_split)
    else:
        candidates = candidate_windows(data, start, end)
    if not candidates:
        raise RuntimeError("no official demo validation windows are available")

    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)
    tokenizer = KronosTokenizer.from_pretrained(tokenizer_path).to(args.device).eval()
    model = Kronos.from_pretrained(predictor_path).to(args.device).eval()
    before_rng = rng_hash(torch)
    rows: list[dict[str, object]] = []
    with torch.no_grad():
        for batch_start in range(0, len(candidates), SERIES_BATCH):
            batch = candidates[batch_start : batch_start + SERIES_BATCH]
            contexts: list[np.ndarray] = []
            x_stamps: list[np.ndarray] = []
            y_stamps: list[np.ndarray] = []
            identities: list[tuple[str, str, float]] = []
            for code, context_dates, future_dates in batch:
                frame = data[code].sort_index()
                context = frame.loc[list(context_dates)]
                normalized = normalized_context(context)
                contexts.append(normalized)
                x_stamps.append(time_features(context.index))
                y_stamps.append(time_features(pd.DatetimeIndex(future_dates)))
                identities.append(
                    (
                        code,
                        pd.Timestamp(context.index[-1]).strftime("%Y-%m-%d"),
                        float(normalized[-1, 3]),
                    )
                )
            predictions = auto_regressive_inference(
                tokenizer,
                model,
                torch.from_numpy(np.stack(contexts)).to(args.device),
                torch.from_numpy(np.stack(x_stamps)).to(args.device),
                torch.from_numpy(np.stack(y_stamps)).to(args.device),
                max_context=512,
                pred_len=PREDICT,
                clip=5.0,
                T=0.6,
                top_k=0,
                top_p=0.9,
                sample_count=SAMPLE_COUNT,
            )
            predictions = np.asarray(predictions)[:, -PREDICT:, :]
            for (code, session, reference), prediction in zip(
                identities, predictions, strict=True
            ):
                signals = standardized_close_signals(prediction[:, 3], reference)
                rows.append({"datetime": session, "instrument": code, **signals})
            print(
                json.dumps(
                    {"stage": "SIGNALS", "completed": len(rows), "total": len(candidates)}
                ),
                flush=True,
            )
    after_rng = rng_hash(torch)
    del model, tokenizer
    torch.cuda.empty_cache()

    out_dir.mkdir(parents=True)
    signals_path = out_dir / "signals.csv"
    frame = pd.DataFrame(rows).sort_values(["datetime", "instrument"])
    temporary = signals_path.with_suffix(".csv.tmp")
    frame.to_csv(temporary, index=False, float_format="%.17g")
    os.replace(temporary, signals_path)
    anchors = "\n".join(
        f"{session}|{instrument}"
        for session, instrument in frame[["datetime", "instrument"]].itertuples(index=False)
    )
    receipt: dict[str, Any] = {
        "schema_version": MATRIX_SIGNAL_SCHEMA if matrix_mode else receipt_schema,
        "status": "PASS",
        "id": (
            f"historical-signal-{args.model_cell}-{args.evaluation_split}-v1"
            if matrix_mode
            else strategy_id
        ),
        "track_kind": "HISTORICAL_MODEL_COMPARISON" if matrix_mode else "OFFICIAL_DEMO_METHOD",
        "model_cell_id": args.model_cell,
        "model_size": MODEL_CELLS[args.model_cell][0],
        "model_track": MODEL_CELLS[args.model_cell][1],
        "primary_signal": PRIMARY_SIGNAL,
        "signals": list(SIGNALS),
        "generated_at": datetime.now(UTC).isoformat(),
        "signal_start": str(frame["datetime"].min()),
        "signal_end": str(frame["datetime"].max()),
        "upstream_commit": matrix["upstream_commit"],
        "training_matrix_sha256": sha256_file(matrix_path),
        "tokenizer_sha256": cell["tokenizer_sha256"],
        "predictor_sha256": cell["predictor_sha256"],
        "model_config_sha256": cell["config_sha256"],
        "dataset_manifest_sha256": manifest_sha256,
        "dataset_file_sha256": sha256_file(dataset_path),
        "generator_code_sha256": generator_code_sha256,
        "rng_state_before_sha256": before_rng,
        "rng_state_after_sha256": after_rng,
        "normalization": {
            "policy": "INSTANCE_PER_SYMBOL_90_SESSION",
            "lookback": LOOKBACK,
            "predict": PREDICT,
            "epsilon": 1e-5,
            "clip": 5.0,
            "feature_order": FEATURES,
            "close_index": 3,
        },
        "inference": {
            "T": 0.6,
            "top_p": 0.9,
            "top_k": 0,
            "sample_count": SAMPLE_COUNT,
            "batch_size": TOTAL_BATCH,
            "effective_series_batch": SERIES_BATCH,
            "seed": SEED,
        },
        "runtime": {
            "python": sys.version.split()[0],
            "torch": str(torch.__version__),
            "cuda": str(torch.version.cuda),
            "numpy": str(np.__version__),
            "pandas": str(pd.__version__),
            "device": str(args.device),
            "gpu_name": torch.cuda.get_device_name(torch.device(args.device)),
        },
        "support": {
            "rows": len(frame),
            "cross_sections": int(frame["datetime"].nunique()),
            "anchor_set_sha256": hashlib.sha256(anchors.encode("utf-8")).hexdigest(),
        },
        "artifacts": {
            "signals": {
                "path": signals_path.relative_to(root).as_posix(),
                "sha256": sha256_file(signals_path),
                "bytes": signals_path.stat().st_size,
            }
        },
        "deviations": [
            (
                "Extended test_viewed_2026 split is an opened, frozen post-selection "
                "evaluation."
                if final_test
                else "Extended validation_2025 split replaces the author's fixed demo dates."
            ),
            "Dynamic provider membership and true amount replace the author's Qlib data semantics.",
            (
                "Candidate eligibility uses only T-known membership/data with a complete "
                "prior 90-global-session context; forecast timestamps use the next ten "
                "global exchange sessions without reading future symbol rows."
                if final_test
                else "Legacy validation candidates follow the author's per-symbol slices."
            ),
            "Seed 100 is explicitly fixed because qlib_test.py does not seed inference.",
            "CSV is an auditable instrumentation extension to the author's predictions.pkl.",
        ],
    }
    if matrix_mode:
        assert args.reference_signal_receipt is not None
        receipt.update(
            {
                "evaluation_split": args.evaluation_split,
                "result_role": (
                    "POST_HOC_OPENED_MODEL_DIAGNOSTIC"
                    if final_test
                    else "POST_HOC_MODEL_COMPARISON_VALIDATION"
                ),
                "selection_eligible": False,
                "used_for_selection": False,
                "test_data_access": "VIEWED" if final_test else "NOT_APPLICABLE",
                "reference_signal_receipt_sha256": sha256_file(
                    args.reference_signal_receipt
                ),
            }
        )
    if final_test and not matrix_mode:
        receipt.update(
            {
                "evaluation_split": "test_viewed_2026",
                "result_role": "CORRECTED_OPENED_OOS_DIAGNOSTIC",
                "selection_eligible": False,
                "used_for_selection": False,
                "test_data_access": "VIEWED",
                "analysis_lock_sha256": sha256_file(args.analysis_lock),
            }
        )
    elif not matrix_mode:
        receipt.update(
            {
                "selection_split": "validation_2025",
                "test_viewed_consumed": False,
            }
        )
    receipt["receipt_hash"] = canonical_hash(receipt)
    if matrix_mode:
        validate_matrix_signal_receipt(receipt)
    else:
        validate_signal_receipt(receipt)
    atomic_json(receipt, out_dir / "signal-receipt.json")
    print(json.dumps({"status": "PASS", "rows": len(frame), "out": str(out_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
