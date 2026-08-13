#!/usr/bin/env python3
"""Run one sealed cell of the six-model historical backtest matrix."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import run_historical_top3_variant as helper_module
from elanquant.contracts.historical_matrix import (
    BACKTEST_SCHEMA,
    MODEL_CELLS,
    SPLITS,
    VARIANTS,
    backtest_id,
    validate_backtest_receipt,
    validate_matrix_lock,
    validate_signal_receipt,
)
from elanquant.contracts.historical_variants import (
    HOLDINGS_COLUMNS,
    HOLDINGS_SCHEMA,
    validate_holdings_records,
)

from elanquant.contracts.official_demo import (
    EXPECTED_EXECUTION,
    PRIMARY_SIGNAL,
    SIGNALS,
    canonical_hash,
    sha256_file,
)

atomic_json = helper_module.atomic_json
finite = helper_module.finite
holdings_records = helper_module.holdings_records
position_series = helper_module.position_series
risk_value = helper_module.risk_value
tree_hash = helper_module.tree_hash


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--matrix-lock", type=Path, required=True)
    parser.add_argument("--model-cell", choices=tuple(MODEL_CELLS), required=True)
    parser.add_argument("--split", choices=SPLITS, required=True)
    parser.add_argument("--strategy-variant", choices=tuple(VARIANTS), required=True)
    parser.add_argument("--qlib-site-packages", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.out_dir.resolve()
    if output.exists() or root not in output.parents:
        raise RuntimeError("matrix result must be a new directory under root")
    lock = validate_matrix_lock(read_json(args.matrix_lock))
    if sha256_file(Path(__file__).resolve()) != lock["runner_sha256"]:
        raise RuntimeError("matrix runner differs from the pre-result lock")
    if sha256_file(Path(str(helper_module.__file__)).resolve()) != lock["helper_sha256"]:
        raise RuntimeError("matrix helper differs from the pre-result lock")
    source = next(
        item
        for item in lock["sources"]
        if item["model_cell_id"] == args.model_cell
        and item["evaluation_split"] == args.split
    )
    signal_receipt_path = (root / source["signal_receipt_path"]).resolve()
    provider_receipt_path = (root / source["provider_receipt_path"]).resolve()
    if (
        sha256_file(signal_receipt_path) != source["signal_receipt_sha256"]
        or sha256_file(provider_receipt_path) != source["provider_receipt_sha256"]
    ):
        raise RuntimeError("matrix source receipt changed")
    signal_receipt = validate_signal_receipt(read_json(signal_receipt_path))
    signal_artifact = signal_receipt["artifacts"]["signals"]
    signal_path = (root / signal_artifact["path"]).resolve()
    if sha256_file(signal_path) != source["signal_artifact_sha256"]:
        raise RuntimeError("matrix signal artifact changed")
    provider_receipt = read_json(provider_receipt_path)
    provider_body = dict(provider_receipt)
    claimed = provider_body.pop("receipt_hash", None)
    if provider_receipt.get("status") != "PASS" or canonical_hash(provider_body) != claimed:
        raise RuntimeError("matrix provider receipt is not canonical")
    provider_root = (root / str(provider_receipt["provider_path"])).resolve()
    provider_sha, provider_files = tree_hash(provider_root)
    if (
        provider_sha != source["provider_tree_sha256"]
        or provider_files != provider_receipt["provider_files"]
    ):
        raise RuntimeError("matrix provider tree changed")

    sys.path.append(str(args.qlib_site_packages.resolve()))
    import qlib
    from qlib.backtest import backtest, executor
    from qlib.config import REG_CN
    from qlib.contrib.evaluate import risk_analysis
    from qlib.contrib.strategy import TopkDropoutStrategy

    distribution = importlib.metadata.distribution("pyqlib")
    dist_root = Path(str(distribution._path))
    qlib_sha, _ = tree_hash(Path(qlib.__file__).resolve().parent, "*.py")
    if (
        importlib.metadata.version("pyqlib") != lock["qlib_version"]
        or sha256_file(dist_root / "METADATA") != lock["qlib_metadata_sha256"]
        or sha256_file(dist_root / "RECORD") != lock["qlib_record_sha256"]
        or qlib_sha != lock["qlib_source_tree_sha256"]
    ):
        raise RuntimeError("Qlib differs from the historical matrix lock")
    qlib.init(provider_uri=str(provider_root), region=REG_CN)
    signals = pd.read_csv(signal_path, parse_dates=["datetime"])
    if set(signals.columns) != {"datetime", "instrument", *SIGNALS}:
        raise RuntimeError("matrix signal columns are not exact")
    expected_year = 2025 if args.split == "validation_2025" else 2026
    if signals["datetime"].dt.year.ne(expected_year).any():
        raise RuntimeError("matrix signal split crossed its frozen year")
    start, end = str(signals["datetime"].min().date()), str(signals["datetime"].max().date())
    daily_frames: list[pd.DataFrame] = []
    raw_frames: list[pd.DataFrame] = []
    holding_rows: list[dict[str, object]] = []
    metrics: dict[str, dict[str, float]] = {}
    turnover_exposed = False
    positions_exposed = False
    for signal_name in SIGNALS:
        series = signals.set_index(["instrument", "datetime"])[signal_name].sort_index()
        strategy = TopkDropoutStrategy(signal=series, **VARIANTS[args.strategy_variant])
        portfolio, _ = backtest(
            strategy=strategy,
            start_time=start,
            end_time=end,
            account=EXPECTED_EXECUTION["account"],
            benchmark=EXPECTED_EXECUTION["benchmark"],
            exchange_kwargs={
                key: EXPECTED_EXECUTION[key]
                for key in (
                    "freq",
                    "limit_threshold",
                    "deal_price",
                    "open_cost",
                    "close_cost",
                    "min_cost",
                )
            },
            executor=executor.SimulatorExecutor(
                time_per_step="day",
                generate_portfolio_metrics=True,
                delay_execution=True,
            ),
        )
        report, positions = portfolio.get("1day")
        if report is None or report.empty:
            raise RuntimeError(f"Qlib produced no report for {signal_name}")
        report = report.copy()
        report.index = pd.to_datetime(report.index)
        holding_rows.extend(holdings_records(positions, report.index, signal_name))
        counts = position_series(positions, report.index)
        positions_exposed = positions_exposed or counts.notna().any()
        turnover = (
            pd.to_numeric(report["turnover"], errors="coerce")
            if "turnover" in report
            else pd.Series(float("nan"), index=report.index)
        )
        turnover_exposed = turnover_exposed or turnover.notna().any()
        net = report["return"] - report["cost"]
        excess_without = report["return"] - report["bench"]
        excess_with = excess_without - report["cost"]
        net_risk = risk_analysis(net, freq="1day")
        excess_risk = risk_analysis(excess_with, freq="1day")
        metrics[signal_name] = {
            "total_return_with_cost": float(net.sum()),
            "benchmark_return": float(report["bench"].sum()),
            "excess_return_without_cost": float(excess_without.sum()),
            "excess_return_with_cost": float(excess_with.sum()),
            "annualized_return_with_cost": risk_value(
                net_risk, "annualized_return", net.mean() * 252
            ),
            "annualized_excess_return_with_cost": risk_value(
                excess_risk, "annualized_return", excess_with.mean() * 252
            ),
            "information_ratio_with_cost": risk_value(
                excess_risk,
                "information_ratio",
                excess_with.mean() / excess_with.std(ddof=1) * np.sqrt(252)
                if excess_with.std(ddof=1) > 0
                else 0.0,
            ),
            "max_drawdown_with_cost": risk_value(
                net_risk,
                "max_drawdown",
                (net.cumsum() - net.cumsum().cummax()).min(),
            ),
            "total_cost": float(report["cost"].sum()),
            "turnover_mean": finite(turnover.mean()),
        }
        daily_frames.append(
            pd.DataFrame(
                {
                    "datetime": report.index,
                    "signal": signal_name,
                    "return": report["return"].to_numpy(),
                    "cost": report["cost"].to_numpy(),
                    "benchmark": report["bench"].to_numpy(),
                    "turnover": turnover.to_numpy(),
                    "position_count": counts.reindex(report.index).to_numpy(),
                    "additive_strategy_with_cost": net.cumsum().to_numpy(),
                    "additive_benchmark": report["bench"].cumsum().to_numpy(),
                    "additive_excess_with_cost": excess_with.cumsum().to_numpy(),
                    "compounded_strategy_nav": (1 + net).cumprod().to_numpy(),
                    "compounded_benchmark_nav": (1 + report["bench"]).cumprod().to_numpy(),
                }
            )
        )
        raw = report.reset_index(names="datetime")
        raw.insert(1, "signal", signal_name)
        raw["position_count"] = counts.reindex(report.index).to_numpy()
        raw_frames.append(raw)

    output.mkdir(parents=True)
    daily_path, raw_path = output / "daily-series.csv", output / "raw-report.csv"
    holdings_path = output / "daily-holdings.csv"
    combined = pd.concat(daily_frames, ignore_index=True)
    combined.to_csv(daily_path, index=False, float_format="%.17g")
    pd.concat(raw_frames, ignore_index=True).to_csv(raw_path, index=False, float_format="%.17g")
    holding_rows.sort(
        key=lambda row: (
            str(row["session"]),
            str(row["signal"]),
            not bool(row["is_empty"]),
            str(row["instrument"]),
        )
    )
    sessions = int(combined.loc[combined["signal"] == PRIMARY_SIGNAL, "datetime"].nunique())
    holding_support = validate_holdings_records(holding_rows, expected_sessions=sessions)
    pd.DataFrame(holding_rows, columns=HOLDINGS_COLUMNS).to_csv(
        holdings_path, index=False, float_format="%.17g"
    )
    artifacts: dict[str, dict[str, object]] = {
        name: {
            "path": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        for name, path in (
            ("daily_series", daily_path),
            ("raw_report", raw_path),
            ("holdings", holdings_path),
        )
    }
    artifacts["holdings"].update(
        {
            "schema_version": HOLDINGS_SCHEMA,
            "columns": list(HOLDINGS_COLUMNS),
            **holding_support,
        }
    )
    receipt: dict[str, Any] = {
        "schema_version": BACKTEST_SCHEMA,
        "status": "PASS",
        "id": backtest_id(args.model_cell, args.split, args.strategy_variant),
        "generated_at": datetime.now(UTC).isoformat(),
        "model_cell_id": args.model_cell,
        "model_size": MODEL_CELLS[args.model_cell][0],
        "model_track": MODEL_CELLS[args.model_cell][1],
        "primary_signal": PRIMARY_SIGNAL,
        "strategy_variant_id": args.strategy_variant,
        "evaluation_split": args.split,
        "result_role": (
            "POST_HOC_OPENED_MODEL_STRATEGY_DIAGNOSTIC"
            if args.split == "test_viewed_2026"
            else "POST_HOC_MODEL_STRATEGY_COMPARISON"
        ),
        "test_data_access": "VIEWED" if args.split == "test_viewed_2026" else "NOT_APPLICABLE",
        "selection_eligible": False,
        "used_for_selection": False,
        "promotion_eligible": False,
        "online_paper_equivalent": False,
        "matrix_lock_sha256": sha256_file(args.matrix_lock),
        "source_signal_receipt_sha256": source["signal_receipt_sha256"],
        "source_provider_receipt_sha256": source["provider_receipt_sha256"],
        "backtest_code_sha256": sha256_file(Path(__file__).resolve()),
        "qlib": {
            "version": lock["qlib_version"],
            "metadata_sha256": lock["qlib_metadata_sha256"],
            "record_sha256": lock["qlib_record_sha256"],
            "source_tree_sha256": lock["qlib_source_tree_sha256"],
        },
        "strategy": VARIANTS[args.strategy_variant],
        "execution": EXPECTED_EXECUTION,
        "support": {
            "actual_start": str(pd.to_datetime(combined["datetime"]).min().date()),
            "actual_end": str(pd.to_datetime(combined["datetime"]).max().date()),
            "sessions": sessions,
            "signal_rows": len(signals),
            "signal_cross_sections": int(signals["datetime"].nunique()),
        },
        "observability": {
            "turnover_exposed": bool(turnover_exposed),
            "position_count_exposed": bool(positions_exposed),
        },
        "metrics": metrics,
        "artifacts": artifacts,
        "deviations": [
            "Cross-model historical comparison is post-hoc and never selection eligible.",
            "2026 is previously viewed and remains diagnostic only.",
            "Historical Qlib Top3 is not the online paper Top3 account.",
        ],
    }
    receipt["receipt_hash"] = canonical_hash(receipt)
    validate_backtest_receipt(receipt)
    atomic_json(receipt, output / "backtest-receipt.json")
    print(json.dumps({"status": "PASS", "out": str(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
