#!/usr/bin/env python3
"""Run the pinned Kronos Qlib Top50/Drop5/Hold5 demo method.

The output is historical research only. It never imports or writes ElanQuant's
paper-account database.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from elanquant.contracts.official_demo import (
    BACKTEST_SCHEMA,
    EXPECTED_EXECUTION,
    EXPECTED_STRATEGY,
    FINAL_TEST_BACKTEST_SCHEMA,
    FINAL_TEST_STRATEGY_ID,
    MODEL_CELL,
    PRIMARY_SIGNAL,
    SIGNALS,
    STRATEGY_ID,
    canonical_hash,
    require_positive_int,
    require_sha,
    sha256_file,
    validate_analysis_lock,
    validate_backtest_receipt,
    validate_signal_receipt,
)


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def source_tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def provider_tree_identity(root: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
        count += 1
    return digest.hexdigest(), count


def finite(value: object, fallback: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return fallback
    return result if math.isfinite(result) else fallback


def risk_value(analysis: pd.DataFrame, name: str, fallback: float) -> float:
    if name not in analysis.index:
        return fallback
    row = analysis.loc[name]
    if isinstance(row, pd.Series):
        return finite(row.get("risk"), fallback)
    return finite(row, fallback)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--signal-receipt", type=Path, required=True)
    parser.add_argument("--provider-receipt", type=Path, required=True)
    parser.add_argument("--qlib-site-packages", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--analysis-lock", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    out_dir = args.out_dir.resolve()
    if out_dir.exists():
        raise RuntimeError("official demo backtest output is immutable; use a new run id")
    if root not in out_dir.parents:
        raise RuntimeError("official demo backtest must remain under the ElanQuant root")
    signal_receipt = validate_signal_receipt(
        json.loads(args.signal_receipt.read_text(encoding="utf-8"))
    )
    final_test = signal_receipt["id"] == FINAL_TEST_STRATEGY_ID
    if final_test and args.analysis_lock is None:
        raise RuntimeError("final-test backtest requires an analysis lock")
    if final_test:
        validate_analysis_lock(
            json.loads(args.analysis_lock.read_text(encoding="utf-8"))
        )
        if signal_receipt["analysis_lock_sha256"] != sha256_file(args.analysis_lock):
            raise RuntimeError("signal receipt differs from the final-test analysis lock")
    signal_artifact = signal_receipt["artifacts"]["signals"]
    signal_path = root / str(signal_artifact["path"])
    if sha256_file(signal_path) != signal_artifact["sha256"]:
        raise RuntimeError("standardized signal artifact hash mismatch")
    provider_receipt = json.loads(args.provider_receipt.read_text(encoding="utf-8"))
    provider_content = dict(provider_receipt)
    provider_claimed = provider_content.pop("receipt_hash", None)
    if (
        provider_receipt.get("schema_version")
        != (
            "elanquant_official_demo_qlib_provider_v2"
            if final_test
            else "elanquant_official_demo_qlib_provider_v1"
        )
        or provider_receipt.get("status") != "PASS"
        or canonical_hash(provider_content) != provider_claimed
    ):
        raise RuntimeError("Qlib provider receipt is invalid")
    if final_test:
        if (
            provider_receipt.get("id") != FINAL_TEST_STRATEGY_ID
            or provider_receipt.get("evaluation_split") != "test_viewed_2026"
            or provider_receipt.get("test_data_access") != "VIEWED"
            or provider_receipt.get("used_for_selection") is not False
            or provider_receipt.get("selection_eligible") is not False
            or provider_receipt.get("analysis_lock_sha256")
            != sha256_file(args.analysis_lock)
        ):
            raise RuntimeError("final-test provider firewall is invalid")
    elif (
        provider_receipt.get("selection_split") != "validation_2025"
        or provider_receipt.get("test_viewed_consumed") is not False
    ):
        raise RuntimeError("validation provider firewall is invalid")
    for identity in (
        "dataset_manifest_sha256",
        "dataset_file_sha256",
        "benchmark_receipt_sha256",
        "dumper_sha256",
        "provider_tree_sha256",
        "source_csv_tree_sha256",
    ):
        require_sha(provider_receipt.get(identity), f"provider.{identity}")
    require_positive_int(provider_receipt.get("provider_files"), "provider.provider_files")
    provider_root = (root / str(provider_receipt["provider_path"])).resolve()
    if root not in provider_root.parents:
        raise RuntimeError("Qlib provider path escaped the research root")
    provider_sha, provider_files = provider_tree_identity(provider_root)
    if (
        provider_sha != provider_receipt["provider_tree_sha256"]
        or provider_files != provider_receipt["provider_files"]
    ):
        raise RuntimeError("Qlib provider tree changed after admission")

    # Keep the research environment's modern pandas loaded while resolving the
    # isolated, pinned Qlib distribution and its remaining dependencies.
    sys.path.append(str(args.qlib_site_packages.resolve()))
    import qlib
    from qlib.backtest import backtest, executor
    from qlib.config import REG_CN
    from qlib.contrib.evaluate import risk_analysis
    from qlib.contrib.strategy import TopkDropoutStrategy

    qlib.init(provider_uri=str(provider_root), region=REG_CN)
    signals = pd.read_csv(signal_path, parse_dates=["datetime"])
    if set(signals.columns) != {"datetime", "instrument", *SIGNALS}:
        raise RuntimeError("standardized signal columns are not exact")
    expected_year = 2026 if final_test else 2025
    if signals["datetime"].dt.year.ne(expected_year).any():
        raise RuntimeError("evaluation firewall rejected an unexpected signal year")
    start = str(signals["datetime"].min().date())
    # delay_execution needs one provider session after the configured end. The
    # final validation signal already has a ten-session target fully inside
    # 2025, so using the last signal date keeps execution support inside 2025.
    end = str(signals["datetime"].max().date())
    reports: list[pd.DataFrame] = []
    metrics: dict[str, dict[str, float]] = {}
    for signal_name in SIGNALS:
        series = signals.set_index(["instrument", "datetime"])[signal_name].sort_index()
        strategy = TopkDropoutStrategy(
            topk=50,
            n_drop=5,
            hold_thresh=5,
            signal=series,
        )
        portfolio_metric_dict, _ = backtest(
            strategy=strategy,
            start_time=start,
            end_time=end,
            account=100_000_000,
            benchmark="SH000300",
            exchange_kwargs={
                "freq": "day",
                "limit_threshold": 0.095,
                "deal_price": "open",
                "open_cost": 0.001,
                "close_cost": 0.0015,
                "min_cost": 5,
            },
            executor=executor.SimulatorExecutor(
                time_per_step="day",
                generate_portfolio_metrics=True,
                delay_execution=True,
            ),
        )
        report, _ = portfolio_metric_dict.get("1day")
        if report is None or report.empty:
            raise RuntimeError(f"Qlib produced no daily report for {signal_name}")
        report = report.copy()
        net = report["return"] - report["cost"]
        excess_without = report["return"] - report["bench"]
        excess_with = report["return"] - report["bench"] - report["cost"]
        net_risk = risk_analysis(net, freq="1day")
        excess_risk = risk_analysis(excess_with, freq="1day")
        max_drawdown = risk_value(
            net_risk,
            "max_drawdown",
            float((net.cumsum() - net.cumsum().cummax()).min()),
        )
        metrics[signal_name] = {
            "total_return_with_cost": float(net.sum()),
            "benchmark_return": float(report["bench"].sum()),
            "excess_return_without_cost": float(excess_without.sum()),
            "excess_return_with_cost": float(excess_with.sum()),
            "annualized_return_with_cost": risk_value(
                net_risk, "annualized_return", float(net.mean() * 252)
            ),
            "annualized_excess_return_with_cost": risk_value(
                excess_risk, "annualized_return", float(excess_with.mean() * 252)
            ),
            "information_ratio_with_cost": risk_value(
                excess_risk,
                "information_ratio",
                float(excess_with.mean() / excess_with.std(ddof=1) * np.sqrt(252))
                if float(excess_with.std(ddof=1)) > 0
                else 0.0,
            ),
            "max_drawdown_with_cost": max_drawdown,
            "total_cost": float(report["cost"].sum()),
            "turnover_mean": finite(report.get("turnover", pd.Series(dtype=float)).mean()),
        }
        daily = pd.DataFrame(
            {
                "datetime": report.index,
                "signal": signal_name,
                "return": report["return"].to_numpy(),
                "cost": report["cost"].to_numpy(),
                "benchmark": report["bench"].to_numpy(),
                "additive_strategy_with_cost": net.cumsum().to_numpy(),
                "additive_benchmark": report["bench"].cumsum().to_numpy(),
                "additive_excess_with_cost": excess_with.cumsum().to_numpy(),
                "compounded_strategy_nav": (1 + net).cumprod().to_numpy(),
                "compounded_benchmark_nav": (1 + report["bench"]).cumprod().to_numpy(),
            }
        )
        reports.append(daily)
        print(json.dumps({"stage": "BACKTEST", "signal": signal_name, "rows": len(daily)}))

    out_dir.mkdir(parents=True)
    daily_path = out_dir / "daily-series.csv"
    combined = pd.concat(reports, ignore_index=True)
    combined.to_csv(daily_path, index=False, float_format="%.17g")
    distribution = importlib.metadata.distribution("pyqlib")
    dist_root = Path(str(distribution._path))
    qlib_root = Path(qlib.__file__).resolve().parent
    metadata_path, record_path = dist_root / "METADATA", dist_root / "RECORD"
    receipt: dict[str, Any] = {
        "schema_version": FINAL_TEST_BACKTEST_SCHEMA if final_test else BACKTEST_SCHEMA,
        "status": "PASS",
        "id": FINAL_TEST_STRATEGY_ID if final_test else STRATEGY_ID,
        "track_kind": "OFFICIAL_DEMO_METHOD_EXTENDED_PIT",
        "model_cell_id": MODEL_CELL,
        "generated_at": datetime.now(UTC).isoformat(),
        "primary_signal": PRIMARY_SIGNAL,
        "signal_receipt_sha256": sha256_file(args.signal_receipt),
        "provider_receipt_sha256": sha256_file(args.provider_receipt),
        "backtest_code_sha256": sha256_file(Path(__file__).resolve()),
        "qlib": {
            "version": importlib.metadata.version("pyqlib"),
            "metadata_sha256": sha256_file(metadata_path),
            "record_sha256": sha256_file(record_path),
            "source_tree_sha256": source_tree_hash(qlib_root),
        },
        "strategy": dict(EXPECTED_STRATEGY),
        "execution": dict(EXPECTED_EXECUTION),
        "support": {
            "requested_start": start,
            "requested_end": end,
            "actual_start": str(pd.to_datetime(combined["datetime"]).min().date()),
            "actual_end": str(pd.to_datetime(combined["datetime"]).max().date()),
            "sessions": int(
                combined.loc[
                    combined["signal"] == PRIMARY_SIGNAL, "datetime"
                ].nunique()
            ),
            "signal_rows": len(signals),
            "signal_cross_sections": int(signals["datetime"].nunique()),
            "candidate_min": int(signals.groupby("datetime")["instrument"].nunique().min()),
            "candidate_median": float(signals.groupby("datetime")["instrument"].nunique().median()),
            "candidate_max": int(signals.groupby("datetime")["instrument"].nunique().max()),
        },
        "metrics": metrics,
        "curve_semantics": {
            "official": "Arithmetic cumulative sum of daily returns, matching qlib_test.py.",
            "derived": "Compounded NAV is an ElanQuant instrumentation extension.",
        },
        "artifacts": {
            "daily_series": {
                "path": daily_path.relative_to(root).as_posix(),
                "sha256": sha256_file(daily_path),
                "bytes": daily_path.stat().st_size,
            }
        },
        "deviations": [
            (
                "Uses the admitted opened test_viewed_2026 split for a frozen "
                "post-selection evaluation."
                if final_test
                else (
                    "Uses the admitted extended validation_2025 split, not the "
                    "author's fixed dates."
                )
            ),
            "Uses dynamic PIT CSI300 membership and provider data, not the author's Qlib bundle.",
            "Uses true provider amount instead of OHLC-average times volume.",
            "Pins pyqlib 0.9.7 because the Kronos repository does not pin a Qlib version.",
            "Adds seed 100 and machine-readable receipts for reproducibility.",
            "Provider factor=1 leaves corporate-action handling as a disclosed limitation.",
            *(
                [
                    "Corrected signal candidates do not depend on future symbol membership "
                    "or future symbol-row availability."
                ]
                if final_test
                else []
            ),
        ],
    }
    if final_test:
        receipt.update(
            {
                "evaluation_split": "test_viewed_2026",
                "result_role": "CORRECTED_OPENED_OOS_DIAGNOSTIC",
                "selection_eligible": False,
                "used_for_selection": False,
                "test_data_access": "VIEWED",
                "strategy_locked_before_run": True,
                "analysis_lock_sha256": sha256_file(args.analysis_lock),
            }
        )
    else:
        receipt.update(
            {
                "selection_split": "validation_2025",
                "selection_rule_predeclared": True,
                "test_viewed_consumed": False,
                "test_status": "NOT_ACCESSED_FOR_SELECTION",
                "selection_eligible": True,
            }
        )
    receipt["receipt_hash"] = canonical_hash(receipt)
    validate_backtest_receipt(receipt)
    atomic_json(receipt, out_dir / "backtest-receipt.json")
    print(json.dumps({"status": "PASS", "out": str(out_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
