#!/usr/bin/env python3
"""Generate the pinned Kronos demo's four standardized-space signals.

This is intentionally separate from ElanQuant's inverse-price Top-3 online
signal. It consumes only the 2025 validation slice and the Small official-style
fine-tuned cell, then publishes an immutable machine-readable receipt.
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
from elanquant.contracts.official_demo import (
    MODEL_CELL,
    PRIMARY_SIGNAL,
    SIGNAL_SCHEMA,
    SIGNALS,
    STRATEGY_ID,
    canonical_hash,
    sha256_file,
    standardized_close_signals,
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


def load_matrix(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    matrix = json.loads(path.read_text(encoding="utf-8"))
    content = dict(matrix)
    claimed = content.pop("receipt_hash", None)
    if (
        matrix.get("schema_version") != "elanquant_training_matrix_v2"
        or matrix.get("status") != "PASS"
        or canonical_hash(content) != claimed
    ):
        raise RuntimeError("training matrix is not sealed PASS")
    cells = [cell for cell in matrix.get("cells", []) if cell.get("id") == MODEL_CELL]
    if len(cells) != 1 or cells[0].get("track") != "official_style":
        raise RuntimeError("Small official-style model cell is absent")
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
) -> list[tuple[str, int]]:
    candidates: list[tuple[str, int]] = []
    for code in sorted(data):
        frame = data[code].sort_index()
        for offset in range(0, len(frame) - LOOKBACK - PREDICT + 1):
            signal_session = pd.Timestamp(frame.index[offset + LOOKBACK - 1])
            target_end = pd.Timestamp(frame.index[offset + LOOKBACK + PREDICT - 1])
            if signal_session >= start and target_end <= end:
                candidates.append((code, offset))
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args()

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
    matrix, cell = load_matrix(matrix_path)
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
        raise RuntimeError("official validation dataset is empty")
    start, end = pd.Timestamp(args.start), pd.Timestamp(args.end)
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
            for code, offset in batch:
                frame = data[code].sort_index()
                context = frame.iloc[offset : offset + LOOKBACK]
                future = frame.iloc[offset + LOOKBACK : offset + LOOKBACK + PREDICT]
                normalized = normalized_context(context)
                contexts.append(normalized)
                x_stamps.append(time_features(context.index))
                y_stamps.append(time_features(future.index))
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
        "schema_version": SIGNAL_SCHEMA,
        "status": "PASS",
        "id": STRATEGY_ID,
        "track_kind": "OFFICIAL_DEMO_METHOD",
        "model_cell_id": MODEL_CELL,
        "model_size": "small",
        "model_track": "official_style",
        "selection_split": "validation_2025",
        "test_viewed_consumed": False,
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
            "Extended validation_2025 split replaces the author's fixed demo dates.",
            "Dynamic provider membership and true amount replace the author's Qlib data semantics.",
            "Seed 100 is explicitly fixed because qlib_test.py does not seed inference.",
            "CSV is an auditable instrumentation extension to the author's predictions.pkl.",
        ],
    }
    receipt["receipt_hash"] = canonical_hash(receipt)
    validate_signal_receipt(receipt)
    atomic_json(receipt, out_dir / "signal-receipt.json")
    print(json.dumps({"status": "PASS", "rows": len(frame), "out": str(out_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
