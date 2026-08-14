from __future__ import annotations

import argparse
import importlib
import json
import math
import os
import random
import subprocess
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from elanquant.repro.common import atomic_json, canonical_sha256, sha256_file
from elanquant.repro.weights import verify_weights

UPSTREAM_COMMIT = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"
FEATURES = ("open", "high", "low", "close", "volume", "amount")
SAMPLING = {"temperature": 0.6, "top_k": 0, "top_p": 0.9, "sample_count": 5}


def zero_shot_plan(args: argparse.Namespace) -> dict[str, object]:
    return {
        "schema_version": "elanquant_zero_shot_plan_v1",
        "scope": "SINGLE_INSTRUMENT_OFFICIAL_WEIGHT_FORECAST_NOT_A_BACKTEST",
        "release": args.release,
        "device": args.device,
        "input": str(args.input),
        "instrument": args.instrument,
        "future_sessions": str(args.future_sessions),
        "lookback": args.lookback,
        "prediction_sessions": 10,
        "weights_root": str(args.weights_root),
        "upstream": str(args.upstream),
        "output": str(args.output),
        "sampling": SAMPLING,
        "requirements": [
            f"Kronos source checkout at commit {UPSTREAM_COMMIT}",
            "verified official Tokenizer and selected predictor weights",
            "at least lookback structurally valid rows for one instrument",
            "ten user-supplied future exchange sessions",
            "a working torch device with no silent fallback",
        ],
    }


def _pandas() -> Any:
    try:
        return importlib.import_module("pandas")
    except ImportError as error:  # pragma: no cover - package smoke exercises the message
        raise RuntimeError("zero-shot inference requires elanquant[repro,inference]") from error


def _upstream_head(upstream: Path) -> str:
    model_init = upstream / "model/__init__.py"
    if not model_init.is_file():
        raise RuntimeError("Kronos upstream checkout is incomplete")
    completed = subprocess.run(
        ["git", "-C", str(upstream), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    head = completed.stdout.strip()
    if completed.returncode != 0 or head != UPSTREAM_COMMIT:
        raise RuntimeError(f"Kronos upstream must be pinned to {UPSTREAM_COMMIT}")
    return head


def _read_frame(source: Path, instrument: str | None, lookback: int) -> tuple[Any, str]:
    pd = _pandas()
    if source.suffix.lower() == ".csv":
        frame = pd.read_csv(source)
    elif source.suffix.lower() in {".parquet", ".pq"}:
        frame = pd.read_parquet(source)
    else:
        raise ValueError("inference input must be CSV or Parquet")
    required = {"instrument", "timestamp", "open", "high", "low", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"inference input is missing columns: {sorted(missing)}")
    frame["instrument"] = frame["instrument"].astype(str).str.strip()
    available = sorted(str(value) for value in frame["instrument"].unique())
    if instrument is None:
        if len(available) != 1:
            raise ValueError("--instrument is required when input contains multiple instruments")
        instrument = available[0]
    if instrument not in available:
        raise ValueError(f"instrument is absent from input: {instrument}")
    selected = frame.loc[frame["instrument"] == instrument].copy()
    selected["timestamp"] = pd.to_datetime(selected["timestamp"], errors="raise")
    selected = selected.sort_values("timestamp", kind="stable")
    if selected["timestamp"].duplicated().any():
        raise ValueError("inference input contains duplicate timestamps")
    for column in ("open", "high", "low", "close"):
        selected[column] = pd.to_numeric(selected[column], errors="raise")
    if "volume" not in selected:
        selected["volume"] = 0.0
        selected["amount"] = 0.0
    else:
        selected["volume"] = pd.to_numeric(selected["volume"], errors="raise")
        if "amount" not in selected:
            selected["amount"] = selected["volume"] * selected[
                ["open", "high", "low", "close"]
            ].mean(axis=1)
        else:
            selected["amount"] = pd.to_numeric(selected["amount"], errors="raise")
    values = selected[list(FEATURES)].to_numpy(dtype=float)
    if not all(math.isfinite(float(value)) for value in values.flat):
        raise ValueError("inference input values must be finite")
    if len(selected) < lookback:
        raise ValueError(f"inference input needs at least {lookback} rows")
    return selected.iloc[-lookback:].reset_index(drop=True), instrument


def _future_index(path: Path, after: Any) -> Any:
    pd = _pandas()
    frame = pd.read_csv(path)
    columns = [name for name in ("session", "timestamp", "date") if name in frame]
    if len(columns) != 1:
        raise ValueError(
            "future-session CSV must contain exactly one session/timestamp/date column"
        )
    sessions = pd.DatetimeIndex(pd.to_datetime(frame[columns[0]], errors="raise"))
    if len(sessions) != 10 or sessions.has_duplicates or not sessions.is_monotonic_increasing:
        raise ValueError("future-session CSV must contain exactly ten unique increasing sessions")
    if sessions[0] <= after:
        raise ValueError("future sessions must begin after the final context timestamp")
    return sessions


def _runtime(upstream: Path) -> tuple[Any, Any, Any, Any]:
    try:
        torch = importlib.import_module("torch")
    except ImportError as error:  # pragma: no cover - clean-install smoke checks the message
        raise RuntimeError("zero-shot inference requires elanquant[inference]") from error
    sys.path.insert(0, str(upstream))
    try:
        model_module = importlib.import_module("model")
    finally:
        sys.path.pop(0)
    module_path = Path(str(model_module.__file__)).resolve()
    if upstream.resolve() not in module_path.parents:
        raise RuntimeError("imported Kronos model does not come from the pinned upstream checkout")
    return (
        torch,
        model_module.Kronos,
        model_module.KronosTokenizer,
        model_module.KronosPredictor,
    )


def _require_device(torch: Any, requested: str) -> str:
    if requested == "cuda":
        if not bool(torch.cuda.is_available()):
            raise RuntimeError("requested CUDA device is unavailable")
        return "cuda:0"
    if requested == "mps":
        mps = getattr(getattr(torch, "backends", None), "mps", None)
        if mps is None or not bool(mps.is_available()):
            raise RuntimeError("requested MPS device is unavailable")
    return requested


def run_zero_shot_inference(args: argparse.Namespace) -> dict[str, object]:
    if args.lookback < 2 or args.lookback > 512:
        raise ValueError("lookback must be between 2 and 512")
    upstream = args.upstream.resolve()
    upstream_head = _upstream_head(upstream)
    weights = verify_weights(args.weights_root.resolve(), args.release)
    context, instrument = _read_frame(args.input.resolve(), args.instrument, args.lookback)
    future = _future_index(args.future_sessions.resolve(), context.iloc[-1]["timestamp"])
    torch, Kronos, KronosTokenizer, KronosPredictor = _runtime(upstream)
    device = _require_device(torch, args.device)
    random.seed(100)
    try:
        import numpy as np
    except ImportError as error:  # pragma: no cover - declared inference dependency
        raise RuntimeError("zero-shot inference requires elanquant[inference]") from error
    np.random.seed(100)
    torch.manual_seed(100)
    if args.device == "cuda":
        torch.cuda.manual_seed_all(100)
    tokenizer_dir = args.weights_root.resolve() / "Kronos-Tokenizer-base"
    predictor_dir = args.weights_root.resolve() / f"Kronos-{args.release}"
    tokenizer = KronosTokenizer.from_pretrained(str(tokenizer_dir)).eval()
    model = Kronos.from_pretrained(str(predictor_dir)).eval()
    predictor = KronosPredictor(model, tokenizer, device=device, max_context=512, clip=5)
    features = context[list(FEATURES)]
    timestamps = context["timestamp"]
    with torch.inference_mode():
        forecast = predictor.predict(
            features,
            timestamps,
            future,
            pred_len=10,
            T=SAMPLING["temperature"],
            top_k=SAMPLING["top_k"],
            top_p=SAMPLING["top_p"],
            sample_count=SAMPLING["sample_count"],
            verbose=False,
        )
    predicted_close = [float(value) for value in forecast["close"]]
    if len(predicted_close) != 10 or not all(
        math.isfinite(value) and value > 0 for value in predicted_close
    ):
        raise RuntimeError("Kronos returned an invalid ten-session close forecast")
    reference = float(context.iloc[-1]["close"])
    forecast_return = math.fsum(predicted_close) / len(predicted_close) / reference - 1
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    rendered = forecast.reset_index(drop=True)
    rendered.insert(0, "timestamp", future)
    temporary = output.with_suffix(output.suffix + f".tmp-{os.getpid()}")
    rendered.to_csv(temporary, index=False, date_format="%Y-%m-%dT%H:%M:%S")
    os.replace(temporary, output)
    receipt: dict[str, object] = {
        "schema_version": "elanquant_official_zero_shot_forecast_v1",
        "status": "PASS",
        "scope": "SINGLE_INSTRUMENT_FORECAST_NOT_A_BACKTEST_OR_RECOMMENDATION",
        "generated_at": datetime.now(UTC).isoformat(),
        "instrument": instrument,
        "as_of": context.iloc[-1]["timestamp"].isoformat(),
        "release": args.release,
        "device": device,
        "upstream_commit": upstream_head,
        "weights_receipt_hash": weights["receipt_hash"],
        "input_sha256": sha256_file(args.input.resolve()),
        "future_sessions_sha256": sha256_file(args.future_sessions.resolve()),
        "output_sha256": sha256_file(output),
        "reference_close": reference,
        "forecast_mean_close": math.fsum(predicted_close) / len(predicted_close),
        "forecast_return": forecast_return,
        "forecast_return_formula": "mean(next_10_predicted_closes) / current_close - 1",
        "sampling": SAMPLING,
    }
    receipt["receipt_hash"] = canonical_sha256(receipt)
    atomic_json(output.with_suffix(output.suffix + ".receipt.json"), receipt)
    return receipt


def add_infer_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser("infer", help="Run a public, pinned inference workflow")
    actions = parser.add_subparsers(dest="infer_action", required=True)
    command = actions.add_parser("zero-shot", help="Forecast one instrument with official weights")
    command.add_argument("--input", type=Path, required=True)
    command.add_argument("--instrument")
    command.add_argument("--future-sessions", type=Path, required=True)
    command.add_argument("--weights-root", type=Path, default=Path(".elanquant/weights"))
    command.add_argument("--upstream", type=Path, default=Path(".elanquant/upstream/Kronos"))
    command.add_argument("--release", choices=("small", "base"), default="small")
    command.add_argument("--device", choices=("cpu", "mps", "cuda"), required=True)
    command.add_argument("--lookback", type=int, default=90)
    command.add_argument("--output", type=Path, required=True)
    command.add_argument("--dry-run", action="store_true")
    command.set_defaults(handler=run_infer_command)


def run_infer_command(args: argparse.Namespace) -> int:
    if args.dry_run:
        plan = zero_shot_plan(args)
        plan["plan_hash"] = canonical_sha256(plan)
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    receipt = run_zero_shot_inference(args)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_infer_parser(subparsers)
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
