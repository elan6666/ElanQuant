#!/usr/bin/env python3
"""Evaluate the three Kronos Small cells and publish a latest-session ranking.

This server-only command keeps model selection on the 2025 validation split and
labels 2026 metrics TEST_VIEWED.  It uses the pinned author's predictor without
changing architecture, sampling temperature, top-p, or inverse transform.
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

LOOKBACK = 90
PREDICT = 10
UPSTREAM_COMMIT = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"
FEATURES = ["open", "high", "low", "close", "volume", "amount"]
MODEL_CELLS = (
    ("small-zero-shot", "small", "zero_shot"),
    ("small-official-ft", "small", "official_style"),
    ("small-strict-pit", "small", "strict_pit"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(value: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def verify_manifest_files(root: Path, manifest: dict[str, Any]) -> None:
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise RuntimeError(f"manifest has no file inventory: {root}")
    for identity, entry in files.items():
        expected = entry.get("sha256") if isinstance(entry, dict) else entry
        candidate = root / str(identity)
        if not candidate.is_file() or sha256(candidate) != expected:
            raise RuntimeError(f"manifest file hash mismatch: {identity}")


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
    if head != UPSTREAM_COMMIT or status:
        raise RuntimeError("inference upstream is not the pinned clean Kronos source")
    return head


def load_matrix(path: Path) -> dict[str, Any]:
    matrix = json.loads(path.read_text(encoding="utf-8"))
    if (
        matrix.get("schema_version") != "elanquant_training_matrix_v2"
        or matrix.get("status") != "PASS"
    ):
        raise RuntimeError("training matrix is not sealed PASS")
    content = dict(matrix)
    claimed = content.pop("receipt_hash", None)
    rendered = json.dumps(
        content,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if hashlib.sha256(rendered.encode("utf-8")).hexdigest() != claimed:
        raise RuntimeError("training matrix receipt hash mismatch")
    return matrix


def evaluate_rows(
    rows: list[dict[str, Any]],
) -> dict[str, float | int | None | dict[str, int]]:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return {"rank_ic": None, "ic": None, "top10_mean_return": None, "rows": 0}
    grouped = frame.groupby("signal_session")
    daily_rank = grouped[["signal", "realized"]].apply(
        lambda group: group["signal"].corr(group["realized"], method="spearman")
    )
    daily_ic = grouped[["signal", "realized"]].apply(
        lambda group: group["signal"].corr(group["realized"], method="pearson")
    )
    daily_top = grouped.apply(
        lambda group: group.nlargest(min(10, len(group)), "signal")["realized"].mean(),
        include_groups=False,
    )

    def mean_or_none(values: pd.Series) -> float | None:
        clean = values.dropna()
        return None if clean.empty else float(clean.mean())

    result: dict[str, float | int | None | dict[str, int]] = {
        "rank_ic": mean_or_none(daily_rank),
        "ic": mean_or_none(daily_ic),
        "top10_mean_return": mean_or_none(daily_top),
        "rows": len(frame),
        "cross_sections": int(frame["signal_session"].nunique()),
    }
    if "outcome_status" in frame:
        result["outcome_counts"] = {
            str(key): int(value) for key, value in frame["outcome_status"].value_counts().items()
        }
    return result


def realized_mean_return(history: pd.DataFrame, future: pd.DataFrame) -> tuple[float, str]:
    reference = float(history.iloc[-1]["close"])
    closes = future["close"].astype(float).copy()
    observed = (
        future["observed"].to_numpy(dtype=bool)
        if "observed" in future
        else np.ones(len(future), dtype=bool)
    )
    status = "COMPLETE" if bool(observed.all()) else "MISSING_SESSION_LAST_CLOSE_CARRY"
    return float(closes.mean() / reference - 1), status


def materialize_window(frame: pd.DataFrame, start: int, *, strict: bool) -> pd.DataFrame:
    window = frame.iloc[start : start + LOOKBACK + PREDICT].copy()
    if len(window) != LOOKBACK + PREDICT:
        raise RuntimeError("incomplete anchor window")
    if strict:
        signal_factor = float(window.iloc[LOOKBACK - 1]["adj_factor"])
        factor = window["adj_factor"].to_numpy(dtype=np.float64) / signal_factor
        window.loc[:, ["open", "high", "low", "close"]] = (
            window[["open", "high", "low", "close"]].to_numpy(dtype=np.float64) * factor[:, None]
        )
    return window.rename(columns={"vol": "volume", "amt": "amount"})


def materialize_evaluation_window(
    frame: pd.DataFrame, start: int, *, strict_input: bool
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return model input and one track-independent, signal-date-adjusted outcome."""
    model_window = materialize_window(frame, start, strict=strict_input)
    outcome_window = model_window if strict_input else materialize_window(frame, start, strict=True)
    return (
        model_window.iloc[:LOOKBACK],
        model_window.iloc[LOOKBACK:],
        outcome_window.iloc[:LOOKBACK],
        outcome_window.iloc[LOOKBACK:],
    )


def materialize_history(frame: pd.DataFrame, *, strict: bool) -> pd.DataFrame:
    history = frame.copy()
    if len(history) != LOOKBACK:
        raise RuntimeError("online history is not a complete lookback window")
    if strict:
        signal_factor = float(history.iloc[-1]["adj_factor"])
        factor = history["adj_factor"].to_numpy(dtype=np.float64) / signal_factor
        history.loc[:, ["open", "high", "low", "close"]] = (
            history[["open", "high", "low", "close"]].to_numpy(dtype=np.float64) * factor[:, None]
        )
    return history.rename(columns={"vol": "volume", "amt": "amount"})


def model_paths(matrix: dict[str, Any], model_id: str) -> tuple[Path, Path, dict[str, Any]]:
    matches = [cell for cell in matrix["cells"] if cell.get("id") == model_id]
    if len(matches) != 1:
        raise RuntimeError(f"matrix cell identity is missing or duplicated: {model_id}")
    cell = matches[0]
    return Path(cell["tokenizer_path"]), Path(cell["predictor_path"]), cell


def future_sessions(calendar: pd.DatetimeIndex, signal: pd.Timestamp) -> pd.DatetimeIndex:
    values = calendar[calendar > signal][:PREDICT]
    if len(values) != PREDICT:
        raise RuntimeError("trade calendar does not include ten future sessions")
    return values


def kronos_timestamp_series(values: pd.Index | pd.Series) -> pd.Series:
    """Match the pinned official batch example and its `.dt` implementation."""
    return pd.Series(pd.to_datetime(values), name="timestamps").reset_index(drop=True)


def reset_sampling_seed(torch_module: Any, seed: int = 100) -> None:
    """Give evaluation and online inference independent, repeatable RNG streams."""
    np.random.seed(seed)
    torch_module.manual_seed(seed)
    if torch_module.cuda.is_available():
        torch_module.cuda.manual_seed_all(seed)


def sample_cross_sections(
    anchors: list[tuple[str, int]],
    symbols: dict[str, pd.DataFrame],
    sample_count: int,
    seed: int,
) -> list[tuple[str, int]]:
    by_session: dict[pd.Timestamp, list[tuple[str, int]]] = {}
    for code, start in anchors:
        session = symbols[code].index[start + LOOKBACK - 1]
        by_session.setdefault(session, []).append((code, start))
    rng = random.Random(seed)
    sessions = sorted(by_session)
    rng.shuffle(sessions)
    per_session = min(30, max(10, sample_count // max(1, min(30, len(sessions)))))
    selected: list[tuple[str, int]] = []
    for session in sessions:
        cross_section = by_session[session]
        rng.shuffle(cross_section)
        selected.extend(cross_section[:per_session])
        if len(selected) >= sample_count:
            break
    return selected[:sample_count]


def formal_cross_sections(
    anchors: list[tuple[str, int]],
    symbols: dict[str, pd.DataFrame],
    sessions_per_month: int,
) -> list[tuple[str, int]]:
    by_session: dict[pd.Timestamp, list[tuple[str, int]]] = {}
    for code, start in anchors:
        session = symbols[code].index[start + LOOKBACK - 1]
        by_session.setdefault(session, []).append((code, start))
    selected: list[tuple[str, int]] = []
    grouped: dict[tuple[int, int], list[pd.Timestamp]] = {}
    for session in sorted(by_session):
        grouped.setdefault((session.year, session.month), []).append(session)
    for sessions in grouped.values():
        count = min(sessions_per_month, len(sessions))
        positions = np.linspace(0, len(sessions) - 1, count, dtype=int)
        for position in sorted(set(int(value) for value in positions)):
            selected.extend(sorted(by_session[sessions[position]]))
    return selected


def anchor_hash(anchors: list[tuple[str, int]], symbols: dict[str, pd.DataFrame]) -> str:
    identities = [
        f"{code}:{symbols[code].index[start + LOOKBACK - 1].strftime('%Y-%m-%d')}"
        for code, start in anchors
    ]
    return hashlib.sha256("\n".join(identities).encode()).hexdigest()


def main() -> int:
    import torch

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--matrix-receipt", type=Path, required=True)
    parser.add_argument("--smoke-evaluation-samples", type=int)
    parser.add_argument("--formal-sessions-per-month", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--online-root", type=Path)
    parser.add_argument("--skip-evaluation", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    dataset_root = root / "data/processed/extended-v2"
    manifest_path = dataset_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "PASS":
        raise RuntimeError("processed dataset is not PASS")
    verify_manifest_files(dataset_root, manifest)
    upstream = args.upstream.resolve()
    upstream_head = verify_upstream(upstream)
    matrix_path = args.matrix_receipt.resolve()
    matrix = load_matrix(matrix_path)
    if matrix.get("upstream_commit") != upstream_head:
        raise RuntimeError("matrix and inference upstream identities disagree")
    if matrix.get("data_manifest_sha256") != sha256(manifest_path):
        raise RuntimeError("matrix and processed dataset identities disagree")
    sys.path.insert(0, str(upstream))
    from model.kronos import (  # type: ignore[import-not-found]
        Kronos,
        KronosPredictor,
        KronosTokenizer,
    )

    with (dataset_root / "strict/full_data.pkl").open("rb") as handle:
        symbols: dict[str, pd.DataFrame] = pickle.load(handle)
    validation_anchors: list[tuple[str, int]] = []
    viewed_anchors: list[tuple[str, int]] = []
    if not args.skip_evaluation:
        with (dataset_root / "strict/val_anchors.pkl").open("rb") as handle:
            validation_anchors = list(pickle.load(handle))
        with (dataset_root / "strict/test_anchors.pkl").open("rb") as handle:
            viewed_anchors = list(pickle.load(handle))
    raw_root = root / "data/raw/extended-csi300-v1"
    online_manifest_path: Path | None = None
    if args.online_root is not None:
        online_root = args.online_root.resolve()
        online_manifest_path = online_root / "manifest.json"
        online_manifest = json.loads(online_manifest_path.read_text(encoding="utf-8"))
        if online_manifest.get("status") != "PASS":
            raise RuntimeError("online snapshot is not PASS")
        verify_manifest_files(online_root, online_manifest)
        with (online_root / "online_data.pkl").open("rb") as handle:
            online_symbols: dict[str, pd.DataFrame] = pickle.load(handle)
        latest = pd.Timestamp(online_manifest["resolved_session"])
        calendar_frame = pd.read_csv(online_root / "trade_cal.csv", dtype={"cal_date": str})
    else:
        online_symbols = symbols
        latest = pd.Timestamp(manifest["latest_closed_session"])
        calendar_frame = pd.read_csv(raw_root / "trade_cal.csv", dtype={"cal_date": str})
    calendar = pd.DatetimeIndex(
        pd.to_datetime(
            calendar_frame.loc[calendar_frame["is_open"].astype(int) == 1, "cal_date"],
            format="%Y%m%d",
        )
    ).sort_values()
    if args.skip_evaluation:
        evaluation_mode = "ONLINE_ONLY"
        eval_sets = {"validation_2025": [], "test_viewed_2026": []}
    elif args.smoke_evaluation_samples is not None:
        evaluation_mode = "SMOKE"
        n_each = max(1, args.smoke_evaluation_samples // 2)
        eval_sets = {
            "validation_2025": sample_cross_sections(validation_anchors, symbols, n_each, 100),
            "test_viewed_2026": sample_cross_sections(viewed_anchors, symbols, n_each, 101),
        }
    else:
        evaluation_mode = "FORMAL"
        eval_sets = {
            "validation_2025": formal_cross_sections(
                validation_anchors, symbols, args.formal_sessions_per_month
            ),
            "test_viewed_2026": formal_cross_sections(
                viewed_anchors, symbols, args.formal_sessions_per_month
            ),
        }
    output: dict[str, Any] = {
        "schema_version": "elanquant_kronos_inference_v1",
        "status": "RUNNING",
        "as_of_session": latest.strftime("%Y-%m-%d"),
        "data_manifest_sha256": sha256(online_manifest_path or manifest_path),
        "upstream_commit": upstream_head,
        "training_matrix_receipt_sha256": sha256(matrix_path),
        "inference_code_sha256": sha256(Path(__file__)),
        "config_sha256": hashlib.sha256(
            json.dumps(
                {
                    "batch_size": args.batch_size,
                    "evaluation_mode": evaluation_mode,
                    "formal_sessions_per_month": args.formal_sessions_per_month,
                    "sampling": {"temperature": 0.6, "top_p": 0.9, "top_k": 0, "sample_count": 10},
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        "sampling": {"temperature": 0.6, "top_p": 0.9, "top_k": 0, "sample_count": 10},
        "test_status": "TEST_VIEWED",
        "evaluation_mode": evaluation_mode,
        "evaluation_support": {
            name: {
                "eligible_rows": len(
                    validation_anchors if name == "validation_2025" else viewed_anchors
                ),
                "evaluated_rows": len(anchors),
                "evaluated_cross_sections": len(
                    {
                        symbols[code].index[start + LOOKBACK - 1]
                        for code, start in anchors
                    }
                ),
                "anchor_set_sha256": anchor_hash(anchors, symbols),
            }
            for name, anchors in eval_sets.items()
        },
        "models": {},
    }
    online_rows: dict[str, dict[str, Any]] = {}
    if args.online_root is not None:
        latest_members = set(online_symbols)
    else:
        weight_parts = [
            pd.read_csv(path, dtype=str)
            for path in sorted((raw_root / "index_weight").glob("*.csv"))
        ]
        weights = pd.concat(weight_parts, ignore_index=True)
        latest_membership_date = weights["trade_date"].astype(str).max()
        latest_members = set(
            weights.loc[weights["trade_date"].astype(str) == latest_membership_date, "con_code"]
        )
    names: dict[str, str] = {}
    if args.online_root is not None:
        online_execution = json.loads((online_root / "execution.json").read_text(encoding="utf-8"))
        names.update(
            {
                str(code): str(values["name"])
                for code, values in online_execution.items()
                if isinstance(values, dict) and values.get("name")
            }
        )
    for code in latest_members:
        name_path = raw_root / "namechange" / f"{code}.csv"
        if not name_path.is_file():
            continue
        changes = pd.read_csv(name_path, dtype=str)
        if not changes.empty and "name" in changes:
            names[code] = str(changes.iloc[-1]["name"])
    latest_starts = []
    for code, frame in online_symbols.items():
        if code not in latest_members:
            continue
        matching = np.flatnonzero(frame.index == latest)
        if not len(matching):
            continue
        start = int(matching[0]) - LOOKBACK + 1
        if start >= 0 and len(frame.iloc[start : start + LOOKBACK]) == LOOKBACK:
            latest_starts.append((code, start))
    if len(latest_starts) < 250:
        raise RuntimeError(f"only {len(latest_starts)} symbols have latest online windows")
    y_latest = future_sessions(calendar, latest)
    output["forecast_sessions"] = [session.strftime("%Y-%m-%d") for session in y_latest]

    for model_id, size, track in MODEL_CELLS:
        reset_sampling_seed(torch)
        tokenizer_path, predictor_path, matrix_cell = model_paths(matrix, model_id)
        if not (tokenizer_path / "model.safetensors").is_file():
            raise RuntimeError(f"missing tokenizer checkpoint for {model_id}")
        if not (predictor_path / "model.safetensors").is_file():
            raise RuntimeError(f"missing predictor checkpoint for {model_id}")
        if sha256(tokenizer_path / "model.safetensors") != matrix_cell["tokenizer_sha256"]:
            raise RuntimeError(f"tokenizer checkpoint hash mismatch for {model_id}")
        if sha256(predictor_path / "model.safetensors") != matrix_cell["predictor_sha256"]:
            raise RuntimeError(f"predictor checkpoint hash mismatch for {model_id}")
        tokenizer = KronosTokenizer.from_pretrained(tokenizer_path)
        model = Kronos.from_pretrained(predictor_path)
        tokenizer.eval()
        model.eval()
        predictor = KronosPredictor(model, tokenizer, device="cuda:0", max_context=512, clip=5)
        metrics: dict[str, Any] = {}
        with torch.inference_mode():
            for split_name, anchors in eval_sets.items():
                evaluation: list[dict[str, Any]] = []
                for batch_start in range(0, len(anchors), args.batch_size):
                    batch = anchors[batch_start : batch_start + args.batch_size]
                    frames, x_times, y_times, identities = [], [], [], []
                    for code, start in batch:
                        history, future, outcome_history, outcome_future = (
                            materialize_evaluation_window(
                                symbols[code], start, strict_input=track == "strict_pit"
                            )
                        )
                        model_history = history[FEATURES]
                        frames.append(model_history)
                        x_times.append(kronos_timestamp_series(model_history.index))
                        y_times.append(kronos_timestamp_series(future.index))
                        identities.append(
                            (code, model_history, outcome_history, outcome_future)
                        )
                    predictions = predictor.predict_batch(
                        frames,
                        x_times,
                        y_times,
                        PREDICT,
                        T=0.6,
                        top_p=0.9,
                        top_k=0,
                        sample_count=10,
                        verbose=False,
                    )
                    for (code, history, outcome_history, outcome_future), prediction in zip(
                        identities, predictions, strict=True
                    ):
                        reference = float(history.iloc[-1]["close"])
                        realized, outcome_status = realized_mean_return(
                            outcome_history, outcome_future
                        )
                        evaluation.append(
                            {
                                "code": code,
                                "signal_session": history.index[-1].strftime("%Y-%m-%d"),
                                "signal": float(prediction["close"].mean() / reference - 1),
                                "realized": realized,
                                "outcome_status": outcome_status,
                            }
                        )
                metrics[split_name] = evaluate_rows(evaluation)

            # Evaluation may consume tens of thousands of Monte Carlo draws.
            # Reset before the online cross-section so FORMAL and ONLINE_ONLY
            # produce the same score for the same model, data and configuration.
            reset_sampling_seed(torch)
            for batch_start in range(0, len(latest_starts), args.batch_size):
                batch = latest_starts[batch_start : batch_start + args.batch_size]
                frames, times = [], []
                for code, start in batch:
                    history = materialize_history(
                        online_symbols[code].iloc[start : start + LOOKBACK],
                        strict=track == "strict_pit",
                    )
                    history = history[FEATURES]
                    frames.append(history)
                    times.append(kronos_timestamp_series(history.index))
                predictions = predictor.predict_batch(
                    frames,
                    times,
                    [kronos_timestamp_series(y_latest) for _ in batch],
                    PREDICT,
                    T=0.6,
                    top_p=0.9,
                    top_k=0,
                    sample_count=10,
                    verbose=False,
                )
                for (code, _start), history, prediction in zip(
                    batch, frames, predictions, strict=True
                ):
                    reference = float(history.iloc[-1]["close"])
                    signal = float(prediction["close"].mean() / reference - 1)
                    item = online_rows.setdefault(
                        code,
                        {
                            "code": code,
                            "name": names.get(code, code),
                            "reference_price": reference,
                            "model_scores": {},
                        },
                    )
                    item["model_scores"][model_id] = signal

        output["models"][model_id] = {
            "size": size,
            "track": track,
            "tokenizer_sha256": sha256(tokenizer_path / "model.safetensors"),
            "predictor_sha256": sha256(predictor_path / "model.safetensors"),
            "config_sha256": str(matrix_cell["config_sha256"]),
            "metrics": metrics,
        }
        del predictor, model, tokenizer
        torch.cuda.empty_cache()

    rows = []
    for item in online_rows.values():
        scores = item["model_scores"]
        if not all(model_id in scores for model_id, *_ in MODEL_CELLS):
            continue
        item["score"] = float(scores["small-strict-pit"])
        item["forecast_return"] = item["score"]
        item["coverage"] = 1.0
        item["eligible"] = True
        item["explanation"] = "严格PIT Small 十日平均收盘预测收益。"
        item["forecast"] = []
        rows.append(item)
    rows.sort(key=lambda item: (-float(item["score"]), str(item["code"])))
    for rank, item in enumerate(rows, start=1):
        item["rank"] = rank
    output["scores"] = rows
    output["status"] = "PASS"
    output["generated_at_utc"] = datetime.now(UTC).isoformat()
    atomic_json(output, args.out)
    print(json.dumps({"status": "PASS", "as_of": output["as_of_session"], "scores": len(rows)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
