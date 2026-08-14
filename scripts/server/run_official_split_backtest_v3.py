#!/usr/bin/env python3
"""Run one locked Plan011 model x Top50/Top3 Qlib backtest cell."""

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
import run_historical_top3_variant as backtest_helper
from elanquant.contracts.historical_variants import HOLDINGS_COLUMNS, validate_holdings_records

from elanquant.contracts.official_demo import EXPECTED_EXECUTION, SIGNALS
from scripts.research import official_split_v3 as contract_module
from scripts.research.official_split_v3 import (
    ACTIVE_CELLS,
    BACKTEST_SCHEMA,
    STRATEGIES,
    canonical_hash,
    validate_analysis_lock,
    validate_backtest_receipt,
    validate_signal_receipt,
)


def sha256(path: Path) -> str:
    return backtest_helper.sha256_file(path)


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--analysis-lock", type=Path, required=True)
    parser.add_argument("--model-cell", choices=ACTIVE_CELLS, required=True)
    parser.add_argument("--strategy-variant", choices=tuple(STRATEGIES), required=True)
    parser.add_argument("--signal-receipt", type=Path, required=True)
    parser.add_argument("--qlib-site-packages", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.out_dir.resolve()
    if output.exists() or root not in output.parents:
        raise RuntimeError("backtest output must be a new directory under root")
    lock = validate_analysis_lock(read_object(args.analysis_lock))
    if sha256(Path(__file__).resolve()) != lock["backtest_runner_sha256"]:
        raise RuntimeError("backtest runner differs from the pre-result lock")
    if sha256(Path(str(backtest_helper.__file__)).resolve()) != lock["backtest_helper_sha256"]:
        raise RuntimeError("backtest helper differs from the pre-result lock")
    if sha256(Path(str(contract_module.__file__)).resolve()) != lock["contract_sha256"]:
        raise RuntimeError("backtest contract differs from the pre-result lock")
    receipt = validate_signal_receipt(read_object(args.signal_receipt))
    if receipt["model_cell_id"] != args.model_cell:
        raise RuntimeError("signal receipt belongs to a different model cell")
    if receipt["analysis_lock_sha256"] != sha256(args.analysis_lock):
        raise RuntimeError("signal receipt belongs to a different analysis lock")
    signal_path = (root / str(receipt["signals_path"])).resolve()
    if root not in signal_path.parents or sha256(signal_path) != receipt["signals_sha256"]:
        raise RuntimeError("signal artifact differs from its receipt")
    provider_receipt_path = (root / str(lock["provider_receipt_path"])).resolve()
    if sha256(provider_receipt_path) != lock["provider_receipt_sha256"]:
        raise RuntimeError("provider receipt differs from the pre-result lock")
    provider_receipt = read_object(provider_receipt_path)
    provider_body = dict(provider_receipt)
    claimed = provider_body.pop("receipt_hash", None)
    if provider_receipt.get("status") != "PASS" or canonical_hash(provider_body) != claimed:
        raise RuntimeError("provider receipt is not canonical PASS")
    provider_root = (root / str(provider_receipt["provider_path"])).resolve()
    provider_hash, provider_files = backtest_helper.tree_hash(provider_root)
    if (
        provider_hash != provider_receipt.get("provider_tree_sha256")
        or provider_files != provider_receipt.get("provider_files")
    ):
        raise RuntimeError("Qlib provider differs from its sealed receipt")

    sys.path.append(str(args.qlib_site_packages.resolve()))
    import qlib
    from qlib.backtest import backtest, executor
    from qlib.config import REG_CN
    from qlib.contrib.evaluate import risk_analysis
    from qlib.contrib.strategy import TopkDropoutStrategy

    distribution = importlib.metadata.distribution("pyqlib")
    metadata_root = Path(str(distribution._path))
    qlib_hash, _ = backtest_helper.tree_hash(Path(qlib.__file__).resolve().parent, "*.py")
    if (
        importlib.metadata.version("pyqlib") != lock["qlib_version"]
        or sha256(metadata_root / "METADATA") != lock["qlib_metadata_sha256"]
        or sha256(metadata_root / "RECORD") != lock["qlib_record_sha256"]
        or qlib_hash != lock["qlib_source_tree_sha256"]
    ):
        raise RuntimeError("Qlib runtime differs from the pre-result lock")
    qlib.init(provider_uri=str(provider_root), region=REG_CN)
    signals = pd.read_csv(signal_path, parse_dates=["datetime"])
    if set(signals.columns) != {"datetime", "instrument", *SIGNALS}:
        raise RuntimeError("signal columns are not exact")
    start = str(signals["datetime"].min().date())
    end = str(signals["datetime"].max().date())
    daily_frames: list[pd.DataFrame] = []
    raw_frames: list[pd.DataFrame] = []
    holdings: list[dict[str, object]] = []
    metrics: dict[str, dict[str, float]] = {}
    for signal_name in SIGNALS:
        series = signals.set_index(["instrument", "datetime"])[signal_name].sort_index()
        strategy = TopkDropoutStrategy(signal=series, **STRATEGIES[args.strategy_variant])
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
            raise RuntimeError(f"Qlib produced no report: {signal_name}")
        report = report.copy()
        report.index = pd.to_datetime(report.index)
        holdings.extend(backtest_helper.holdings_records(positions, report.index, signal_name))
        counts = backtest_helper.position_series(positions, report.index)
        turnover = (
            pd.to_numeric(report["turnover"], errors="coerce")
            if "turnover" in report
            else pd.Series(float("nan"), index=report.index)
        )
        net = report["return"] - report["cost"]
        gross_excess = report["return"] - report["bench"]
        excess = report["return"] - report["bench"] - report["cost"]
        net_risk = risk_analysis(net, freq="1day")
        excess_risk = risk_analysis(excess, freq="1day")
        metrics[signal_name] = {
            "total_return_with_cost": float(net.sum()),
            "benchmark_return": float(report["bench"].sum()),
            "excess_return_without_cost": float(gross_excess.sum()),
            "excess_return_with_cost": float(excess.sum()),
            "annualized_return_with_cost": backtest_helper.risk_value(
                net_risk, "annualized_return", float(net.mean() * 252)
            ),
            "annualized_excess_return_with_cost": backtest_helper.risk_value(
                excess_risk, "annualized_return", float(excess.mean() * 252)
            ),
            "information_ratio_with_cost": backtest_helper.risk_value(
                excess_risk,
                "information_ratio",
                float(excess.mean() / excess.std(ddof=1) * np.sqrt(252))
                if excess.std(ddof=1) > 0
                else 0.0,
            ),
            "max_drawdown_with_cost": backtest_helper.risk_value(
                net_risk,
                "max_drawdown",
                float((net.cumsum() - net.cumsum().cummax()).min()),
            ),
            "total_cost": float(report["cost"].sum()),
            "turnover_mean": backtest_helper.finite(turnover.mean()),
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
                    "strategy_with_cost": net.cumsum().to_numpy(),
                    "benchmark_curve": report["bench"].cumsum().to_numpy(),
                    "excess_with_cost": excess.cumsum().to_numpy(),
                }
            )
        )
        raw = report.reset_index(names="datetime")
        raw.insert(1, "signal", signal_name)
        raw["position_count"] = counts.reindex(report.index).to_numpy()
        raw_frames.append(raw)
    output.mkdir(parents=True)
    daily_path = output / "daily-series.csv"
    raw_path = output / "raw-report.csv"
    holdings_path = output / "daily-holdings.csv"
    daily = pd.concat(daily_frames, ignore_index=True)
    daily.to_csv(daily_path, index=False, float_format="%.17g")
    pd.concat(raw_frames, ignore_index=True).to_csv(raw_path, index=False, float_format="%.17g")
    holdings.sort(
        key=lambda row: (str(row["session"]), str(row["signal"]), str(row["instrument"]))
    )
    sessions = int(daily.loc[daily["signal"] == "mean", "datetime"].nunique())
    validate_holdings_records(holdings, expected_sessions=sessions)
    pd.DataFrame(holdings, columns=HOLDINGS_COLUMNS).to_csv(
        holdings_path, index=False, float_format="%.17g"
    )
    result: dict[str, Any] = {
        "schema_version": BACKTEST_SCHEMA,
        "status": "PASS",
        "id": (
            f"official-split-v3-{args.model_cell}-test-viewed-"
            f"{args.strategy_variant}-v1"
        ),
        "generated_at": datetime.now(UTC).isoformat(),
        "model_cell_id": args.model_cell,
        "evaluation_split": "test_viewed_official_v3",
        "strategy_variant_id": args.strategy_variant,
        "strategy": STRATEGIES[args.strategy_variant],
        "execution": EXPECTED_EXECUTION,
        "primary_signal": "mean",
        "sample_count": 5,
        "test_status": "TEST_VIEWED",
        "test_data_access": "VIEWED",
        "selection_eligible": False,
        "used_for_selection": False,
        "promotion_eligible": False,
        "online_paper_equivalent": False,
        "result_role": "OPENED_ROLLING_TEST_MODEL_STRATEGY_DIAGNOSTIC",
        "analysis_lock_sha256": sha256(args.analysis_lock),
        "source_signal_receipt_sha256": sha256(args.signal_receipt),
        "source_signal_sha256": sha256(signal_path),
        "provider_receipt_sha256": sha256(provider_receipt_path),
        "backtest_code_sha256": sha256(Path(__file__).resolve()),
        "qlib": {
            "version": importlib.metadata.version("pyqlib"),
            "metadata_sha256": lock["qlib_metadata_sha256"],
            "record_sha256": lock["qlib_record_sha256"],
            "source_tree_sha256": lock["qlib_source_tree_sha256"],
        },
        "curve_semantics": {
            "official": "Arithmetic cumulative sum of daily returns, matching qlib_test.py.",
            "derived": "Compounded NAV is an ElanQuant instrumentation extension.",
        },
        "deviations": [
            "Uses the admitted official-split-v3 A-share data and dynamic CSI300 universe.",
            "Rolling test is already viewed and is never used for selection or promotion.",
            "Historical Top3 is a Qlib portfolio-size sensitivity variant, not online paper Top3.",
        ],
        "observability": {"turnover_exposed": True, "position_count_exposed": True},
        "daily_series_path": daily_path.relative_to(root).as_posix(),
        "daily_series_sha256": sha256(daily_path),
        "raw_report_path": raw_path.relative_to(root).as_posix(),
        "raw_report_sha256": sha256(raw_path),
        "holdings_path": holdings_path.relative_to(root).as_posix(),
        "holdings_sha256": sha256(holdings_path),
        "support": {
            "signal_rows": len(signals),
            "sessions": sessions,
            "signal_cross_sections": sessions,
            "actual_start": start,
            "actual_end": end,
        },
        "metrics": metrics,
    }
    result["receipt_hash"] = canonical_hash(result)
    validate_backtest_receipt(result)
    (output / "backtest-receipt.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "PASS", "cell": args.model_cell, "variant": args.strategy_variant}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
