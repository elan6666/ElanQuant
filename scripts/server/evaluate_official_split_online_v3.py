#!/usr/bin/env python3
"""Run portable latest-session inference for a sealed official-split-v3 matrix."""

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

import evaluate_and_infer as legacy_helper
import generate_official_demo_signals as signal_helper
import numpy as np
import pandas as pd

from scripts.research.official_split_v3 import validate_matrix
from scripts.research.online_release_v3 import (
    INFERENCE_SCHEMA,
    ONLINE_SAMPLING,
    ONLINE_SIGNAL,
    PRIMARY_MODELS,
    validate_inference,
)

LOOKBACK = 90
PREDICT = 10
FEATURES = ["open", "high", "low", "close", "volume", "amount"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def verify_upstream(upstream: Path) -> str:
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
    if head != "67b630e67f6a18c9e9be918d9b4337c960db1e9a" or status:
        raise RuntimeError("online upstream is not the pinned clean Kronos source")
    return head


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--matrix-receipt", type=Path, required=True)
    parser.add_argument("--model-size", choices=("small", "base"), required=True)
    parser.add_argument(
        "--execution-profile",
        choices=tuple(legacy_helper.EXECUTION_PROFILES),
        required=True,
    )
    parser.add_argument("--device", choices=("cpu", "mps", "cuda", "cuda:0"), required=True)
    parser.add_argument("--online-root", type=Path, required=True)
    parser.add_argument("--online-batch-size", type=int, default=50)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.online_batch_size <= 0:
        raise RuntimeError("online batch size must be positive")

    import torch

    device = legacy_helper.resolve_device(torch, args.execution_profile, args.device)
    upstream = args.upstream.resolve()
    upstream_head = verify_upstream(upstream)
    matrix_path = args.matrix_receipt.resolve()
    matrix = validate_matrix(json.loads(matrix_path.read_text(encoding="utf-8")))
    selected = [row for row in matrix["cells"] if str(row["id"]).startswith(args.model_size)]
    expected_ids = {f"{args.model_size}-zero-shot", f"{args.model_size}-official-ft"}
    if {str(row["id"]) for row in selected} != expected_ids:
        raise RuntimeError("official-split online matrix does not contain the exact two cells")
    if matrix.get("upstream_commit") != upstream_head:
        raise RuntimeError("online matrix and upstream identities disagree")

    online_root = args.online_root.resolve()
    online_manifest_path = online_root / "manifest.json"
    online_manifest = json.loads(online_manifest_path.read_text(encoding="utf-8"))
    if online_manifest.get("status") != "PASS":
        raise RuntimeError("online snapshot is not PASS")
    legacy_helper.verify_manifest_files(online_root, online_manifest)
    with (online_root / "online_data.pkl").open("rb") as handle:
        symbols: dict[str, pd.DataFrame] = pickle.load(handle)
    execution = json.loads((online_root / "execution.json").read_text(encoding="utf-8"))
    latest = pd.Timestamp(online_manifest["resolved_session"])
    calendar_frame = pd.read_csv(online_root / "trade_cal.csv", dtype={"cal_date": str})
    calendar = pd.DatetimeIndex(
        pd.to_datetime(
            calendar_frame.loc[calendar_frame["is_open"].astype(int) == 1, "cal_date"],
            format="%Y%m%d",
        )
    ).sort_values()
    y_dates = legacy_helper.future_sessions(calendar, latest)
    windows: list[tuple[str, pd.DataFrame]] = []
    for code, frame in sorted(symbols.items()):
        ordered = frame.sort_index()
        matching = np.flatnonzero(ordered.index == latest)
        if not len(matching):
            continue
        start = int(matching[0]) - LOOKBACK + 1
        context = ordered.iloc[start : start + LOOKBACK]
        if start >= 0 and len(context) == LOOKBACK:
            windows.append((code, context))
    if len(windows) < 250:
        raise RuntimeError(f"only {len(windows)} symbols have complete latest windows")

    sys.path.insert(0, str(upstream))
    from model.kronos import Kronos, KronosTokenizer, auto_regressive_inference

    models: dict[str, dict[str, Any]] = {}
    online_rows: dict[str, dict[str, Any]] = {}
    for cell in sorted(selected, key=lambda row: str(row["id"])):
        model_id = str(cell["id"])
        tokenizer_path = Path(str(cell["tokenizer_path"]))
        predictor_path = Path(str(cell["predictor_path"]))
        if (
            sha256(tokenizer_path / "model.safetensors") != cell["tokenizer_sha256"]
            or sha256(predictor_path / "model.safetensors") != cell["predictor_sha256"]
        ):
            raise RuntimeError(f"online model files differ from matrix: {model_id}")
        random.seed(100)
        np.random.seed(100)
        torch.manual_seed(100)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(100)
        tokenizer = KronosTokenizer.from_pretrained(tokenizer_path).to(device).eval()
        model = Kronos.from_pretrained(predictor_path).to(device).eval()
        with torch.no_grad():
            for offset in range(0, len(windows), args.online_batch_size):
                batch = windows[offset : offset + args.online_batch_size]
                contexts: list[np.ndarray] = []
                x_stamps: list[np.ndarray] = []
                y_stamps: list[np.ndarray] = []
                identities: list[tuple[str, float, float, float]] = []
                for code, frame in batch:
                    values = frame[FEATURES].to_numpy(dtype=np.float32)
                    means = np.mean(values, axis=0)
                    stds = np.std(values, axis=0)
                    contexts.append(
                        np.clip((values - means) / (stds + 1e-5), -5.0, 5.0).astype(
                            np.float32
                        )
                    )
                    x_stamps.append(signal_helper.time_features(frame.index))
                    y_stamps.append(signal_helper.time_features(y_dates))
                    identities.append((code, float(values[-1, 3]), float(means[3]), float(stds[3])))
                predictions = auto_regressive_inference(
                    tokenizer,
                    model,
                    torch.from_numpy(np.stack(contexts)).to(device),
                    torch.from_numpy(np.stack(x_stamps)).to(device),
                    torch.from_numpy(np.stack(y_stamps)).to(device),
                    max_context=512,
                    pred_len=PREDICT,
                    clip=5.0,
                    T=0.6,
                    top_k=0,
                    top_p=0.9,
                    sample_count=10,
                )
                for identity, prediction in zip(identities, np.asarray(predictions), strict=True):
                    code, reference, mean_close, std_close = identity
                    predicted_close = prediction[-PREDICT:, 3] * (std_close + 1e-5) + mean_close
                    signal = float(np.mean(predicted_close) / reference - 1)
                    item = online_rows.setdefault(
                        code,
                        {
                            "code": code,
                            "name": str(execution.get(code, {}).get("name") or code),
                            "reference_price": reference,
                            "model_scores": {},
                        },
                    )
                    item["model_scores"][model_id] = signal
        models[model_id] = {
            "size": args.model_size,
            "track": "zero_shot" if model_id.endswith("zero-shot") else "official_style",
            "tokenizer_sha256": str(cell["tokenizer_sha256"]),
            "predictor_sha256": str(cell["predictor_sha256"]),
            "config_sha256": str(cell["config_sha256"]),
            "metrics": {},
        }
        del model, tokenizer
        legacy_helper.empty_device_cache(torch, device)

    primary = PRIMARY_MODELS[args.model_size]
    rows = []
    for item in online_rows.values():
        if set(item["model_scores"]) != expected_ids:
            continue
        item["score"] = float(item["model_scores"][primary])
        item["forecast_return"] = item["score"]
        item["coverage"] = 1.0
        item["eligible"] = True
        item["explanation"] = "Official-FT 10日预测平均收盘价相对当前收盘价的变化。"
        item["forecast"] = []
        rows.append(item)
    rows.sort(key=lambda row: (-float(row["score"]), str(row["code"])))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    config = {
        "model_size": args.model_size,
        "execution_profile": args.execution_profile,
        "execution_device": device,
        "online_batch_size": args.online_batch_size,
        "sampling": ONLINE_SAMPLING,
        "signal_definition": ONLINE_SIGNAL,
        "primary_model_id": primary,
    }
    output: dict[str, Any] = {
        "schema_version": INFERENCE_SCHEMA,
        "status": "PASS",
        "as_of_session": latest.strftime("%Y-%m-%d"),
        "forecast_sessions": [stamp.strftime("%Y-%m-%d") for stamp in y_dates],
        "data_manifest_sha256": sha256(online_manifest_path),
        "upstream_commit": upstream_head,
        "training_matrix_receipt_sha256": sha256(matrix_path),
        "model_size": args.model_size,
        "primary_model_id": primary,
        "execution_profile": args.execution_profile,
        "requested_device": args.device,
        "execution_device": device,
        "inference_code_sha256": sha256(Path(__file__).resolve()),
        "config_sha256": hashlib.sha256(
            json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "sampling": ONLINE_SAMPLING,
        "signal_definition": ONLINE_SIGNAL,
        "models": models,
        "scores": rows,
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    validate_inference(output)
    atomic_json(output, args.out)
    print(
        json.dumps(
            {
                "status": "PASS",
                "as_of": output["as_of_session"],
                "scores": len(rows),
                "model_size": args.model_size,
                "execution_profile": args.execution_profile,
                "execution_device": device,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
