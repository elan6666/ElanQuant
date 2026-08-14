#!/usr/bin/env python3
"""Generate one locked mature TEST_VIEWED signal/evaluation cell."""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import random
import sys
from pathlib import Path
from typing import Any

import evaluate_and_infer as evaluation_helper
import generate_official_demo_signals as signal_helper
import numpy as np
import pandas as pd
from elanquant.contracts.official_demo import SIGNALS, standardized_close_signals

from scripts.research import official_split_v3 as contract_module
from scripts.research.official_split_v3 import (
    ACTIVE_CELLS,
    SIGNAL_SCHEMA,
    canonical_hash,
    validate_analysis_lock,
    validate_dataset_admission,
    validate_dataset_manifest,
    validate_matrix,
    validate_signal_receipt,
)

SAMPLE_COUNT = 5
SERIES_BATCH = 200
SEED = 100


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return value


def global_candidates(
    data: dict[str, pd.DataFrame],
    calendar: pd.DatetimeIndex,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[tuple[str, tuple[pd.Timestamp, ...], tuple[pd.Timestamp, ...]]]:
    eligible_positions = [
        position
        for position in range(89, len(calendar) - 10)
        if calendar[position] >= start and calendar[position + 10] <= end
    ]
    candidates: list[tuple[str, tuple[pd.Timestamp, ...], tuple[pd.Timestamp, ...]]] = []
    for code in sorted(data):
        available = {pd.Timestamp(stamp) for stamp in data[code].index}
        for position in eligible_positions:
            context = tuple(calendar[position - 89 : position + 1])
            if all(stamp in available for stamp in context):
                candidates.append(
                    (code, context, tuple(calendar[position + 1 : position + 11]))
                )
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--analysis-lock", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--dataset-admission", type=Path, required=True)
    parser.add_argument("--trade-calendar", type=Path, required=True)
    parser.add_argument("--model-cell", choices=ACTIVE_CELLS, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.out_dir.resolve()
    if output.exists() or root not in output.parents:
        raise RuntimeError("signal output must be a new directory under root")
    lock = validate_analysis_lock(read_object(args.analysis_lock))
    if sha256(Path(__file__).resolve()) != lock["signal_runner_sha256"]:
        raise RuntimeError("signal runner differs from the pre-result lock")
    if sha256(Path(str(signal_helper.__file__)).resolve()) != lock["signal_helper_sha256"]:
        raise RuntimeError("signal helper differs from the pre-result lock")
    if (
        sha256(Path(str(evaluation_helper.__file__)).resolve())
        != lock["evaluation_helper_sha256"]
        or sha256(Path(str(contract_module.__file__)).resolve()) != lock["contract_sha256"]
    ):
        raise RuntimeError("signal contract/helper differs from the pre-result lock")
    if sha256(args.trade_calendar) != lock["trade_calendar_sha256"]:
        raise RuntimeError("trade calendar differs from the pre-result lock")
    matrix = validate_matrix(read_object(args.matrix))
    manifest = validate_dataset_manifest(read_object(args.dataset_manifest))
    admission = validate_dataset_admission(read_object(args.dataset_admission))
    if (
        sha256(args.matrix) != lock["matrix_sha256"]
        or sha256(args.dataset_manifest) != lock["dataset_manifest_sha256"]
        or sha256(args.dataset_admission) != lock["dataset_admission_sha256"]
        or admission["dataset_manifest_sha256"] != sha256(args.dataset_manifest)
    ):
        raise RuntimeError("signal inputs differ from the pre-result lock")
    test_path = args.dataset_manifest.parent / "official/test_data.pkl"
    if (
        sha256(test_path) != lock["test_pickle_sha256"]
        or sha256(test_path) != manifest["files"]["official/test_data.pkl"]["sha256"]
    ):
        raise RuntimeError("test pickle differs from locked admitted bytes")
    signal_helper.verify_upstream(args.upstream.resolve())
    cells = [row for row in matrix["cells"] if row["id"] == args.model_cell]
    if len(cells) != 1:
        raise RuntimeError("selected cell is absent from the matrix")
    cell = cells[0]
    tokenizer_path = Path(str(cell["tokenizer_path"]))
    predictor_path = Path(str(cell["predictor_path"]))
    if (
        sha256(tokenizer_path / "model.safetensors") != cell["tokenizer_sha256"]
        or sha256(predictor_path / "model.safetensors") != cell["predictor_sha256"]
    ):
        raise RuntimeError("model files differ from the sealed matrix")

    with test_path.open("rb") as handle:
        data: Any = pickle.load(handle)
    if not isinstance(data, dict) or not data:
        raise RuntimeError("test pickle is empty")
    effective = admission["actual_effective_ranges"]["test_viewed"]
    start = pd.Timestamp(effective["actual_first_backtest_signal"])
    end = pd.Timestamp(manifest["frozen_latest_session"])
    calendar_frame = pd.read_csv(args.trade_calendar, dtype={"cal_date": str})
    calendar = pd.DatetimeIndex(
        pd.to_datetime(
            calendar_frame.loc[
                calendar_frame["is_open"].astype(int) == 1, "cal_date"
            ],
            format="%Y%m%d",
        )
    ).sort_values()
    calendar = calendar[calendar <= end]
    if canonical_hash([str(stamp.date()) for stamp in calendar]) != manifest[
        "split_contract"
    ]["calendar_sha256"]:
        raise RuntimeError("global exchange timestamps differ from admitted split")
    candidates = global_candidates(data, calendar, start, end)
    if not candidates:
        raise RuntimeError("no mature TEST_VIEWED candidates")
    candidate_identity = [
        {
            "instrument": code,
            "context": [str(stamp.date()) for stamp in context],
            "future": [str(stamp.date()) for stamp in future],
        }
        for code, context, future in candidates
    ]
    candidate_hash = canonical_hash(candidate_identity)

    sys.path.insert(0, str(args.upstream.resolve()))
    import torch
    from model.kronos import Kronos, KronosTokenizer, auto_regressive_inference

    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)
    tokenizer = KronosTokenizer.from_pretrained(tokenizer_path).to(args.device).eval()
    model = Kronos.from_pretrained(predictor_path).to(args.device).eval()
    signal_rows: list[dict[str, object]] = []
    label_rows: list[dict[str, object]] = []
    with torch.no_grad():
        for batch_start in range(0, len(candidates), SERIES_BATCH):
            batch = candidates[batch_start : batch_start + SERIES_BATCH]
            contexts: list[np.ndarray] = []
            x_stamps: list[np.ndarray] = []
            y_stamps: list[np.ndarray] = []
            identities: list[tuple[str, str, float, float]] = []
            for code, context_dates, future_dates in batch:
                frame = data[code].sort_index()
                context = frame.loc[list(context_dates)]
                normalized = signal_helper.normalized_context(context)
                future_close = frame["close"].reindex(future_dates)
                carried = pd.concat(
                    [
                        pd.Series([float(context.iloc[-1]["close"])]),
                        future_close.reset_index(drop=True),
                    ]
                ).ffill().iloc[1:]
                if len(carried) != 10 or carried.isna().any():
                    raise RuntimeError(f"mature label construction failed: {code}")
                realized = float(carried.mean() / float(context.iloc[-1]["close"]) - 1)
                contexts.append(normalized)
                x_stamps.append(signal_helper.time_features(context.index))
                y_stamps.append(signal_helper.time_features(pd.DatetimeIndex(future_dates)))
                identities.append(
                    (
                        code,
                        str(pd.Timestamp(context.index[-1]).date()),
                        float(normalized[-1, 3]),
                        realized,
                    )
                )
            predictions = auto_regressive_inference(
                tokenizer,
                model,
                torch.from_numpy(np.stack(contexts)).to(args.device),
                torch.from_numpy(np.stack(x_stamps)).to(args.device),
                torch.from_numpy(np.stack(y_stamps)).to(args.device),
                max_context=512,
                pred_len=10,
                clip=5.0,
                T=0.6,
                top_k=0,
                top_p=0.9,
                sample_count=SAMPLE_COUNT,
            )
            predictions = np.asarray(predictions)[:, -10:, :]
            for (code, session, reference, realized), prediction in zip(
                identities, predictions, strict=True
            ):
                signals = standardized_close_signals(prediction[:, 3], reference)
                signal_rows.append({"datetime": session, "instrument": code, **signals})
                label_rows.append(
                    {
                        "datetime": session,
                        "instrument": code,
                        "realized": realized,
                    }
                )
            print(
                json.dumps(
                    {
                        "stage": "SIGNALS",
                        "completed": len(signal_rows),
                        "total": len(candidates),
                    }
                ),
                flush=True,
            )
    del model, tokenizer
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    output.mkdir(parents=True)
    signals_path, labels_path = output / "signals.csv", output / "mature-labels.csv"
    signals = pd.DataFrame(signal_rows).sort_values(["datetime", "instrument"])
    labels = pd.DataFrame(label_rows).sort_values(["datetime", "instrument"])
    signals.to_csv(signals_path, index=False, float_format="%.17g")
    labels.to_csv(labels_path, index=False, float_format="%.17g")
    joined = signals.merge(labels, on=["datetime", "instrument"], validate="one_to_one")
    evaluation = evaluation_helper.evaluate_rows(
        [
            {
                "signal_session": row.datetime,
                "signal": row.mean,
                "realized": row.realized,
            }
            for row in joined[["datetime", "mean", "realized"]].itertuples(index=False)
        ]
    )
    metrics = {
        key: evaluation[key]
        for key in ("rank_ic", "ic", "top10_mean_return", "rows", "cross_sections")
    }
    receipt: dict[str, Any] = {
        "schema_version": SIGNAL_SCHEMA,
        "status": "PASS",
        "model_cell_id": args.model_cell,
        "sample_count": SAMPLE_COUNT,
        "mature_targets_only": True,
        "test_status": "TEST_VIEWED",
        "used_for_selection": False,
        "promotion_eligible": False,
        "analysis_lock_sha256": sha256(args.analysis_lock),
        "matrix_sha256": sha256(args.matrix),
        "dataset_admission_sha256": sha256(args.dataset_admission),
        "signals_path": signals_path.relative_to(root).as_posix(),
        "signals_sha256": sha256(signals_path),
        "labels_path": labels_path.relative_to(root).as_posix(),
        "labels_sha256": sha256(labels_path),
        "candidate_set_sha256": candidate_hash,
        "support": {
            "rows": len(signals),
            "sessions": int(signals["datetime"].nunique()),
            "actual_start": str(signals["datetime"].min()),
            "actual_end": str(signals["datetime"].max()),
        },
        "metrics": metrics,
        "signals": list(SIGNALS),
    }
    receipt["receipt_hash"] = canonical_hash(receipt)
    validate_signal_receipt(receipt)
    receipt_path = output / "signal-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "model_cell_id": args.model_cell}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
