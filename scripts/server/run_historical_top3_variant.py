#!/usr/bin/env python3
"""Run a sealed Top3/Drop1/Hold5 Qlib sensitivity backtest."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import elanquant.contracts.historical_variants as contract_module
import numpy as np
import pandas as pd
from elanquant.contracts.historical_variants import (
    COMPARISON_GROUP_ID,
    EXECUTION_DOMAIN,
    HOLDINGS_COLUMNS,
    HOLDINGS_RECEIPT_SCHEMA,
    HOLDINGS_SCHEMA,
    SPLITS,
    SPLITS_V2,
    TOP3_PUBLIC_VARIANT,
    TOP3_STRATEGY,
    TOP3_STRATEGY_ROLE,
    TOP3_VARIANT_ID_V2,
    TOP50_PUBLIC_VARIANT,
    VARIANT_BACKTEST_SCHEMA_V2,
    validate_holdings_receipt,
    validate_holdings_records,
    validate_variant_backtest_receipt,
    validate_variant_lock,
)

from elanquant.contracts.official_demo import (
    EXPECTED_EXECUTION,
    EXPECTED_STRATEGY,
    MODEL_CELL,
    PRIMARY_SIGNAL,
    SIGNALS,
    canonical_hash,
    sha256_file,
    validate_backtest_receipt,
    validate_signal_receipt,
)


def tree_hash(root: Path, pattern: str = "*") -> tuple[str, int]:
    digest, count = hashlib.sha256(), 0
    for path in sorted(item for item in root.rglob(pattern) if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
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


def risk_value(frame: pd.DataFrame, name: str, fallback: float) -> float:
    if name not in frame.index:
        return fallback
    row = frame.loc[name]
    return (
        finite(row.get("risk"), fallback) if isinstance(row, pd.Series) else finite(row, fallback)
    )


def position_count(position: object) -> float:
    if hasattr(position, "get_stock_list"):
        return float(len(position.get_stock_list()))
    if isinstance(position, Mapping):
        if "position" in position and isinstance(position["position"], Mapping):
            return float(len(position["position"]))
        return float(sum(key not in {"cash", "now_account_value"} for key in position))
    return float("nan")


def position_series(positions: object, index: pd.Index) -> pd.Series:
    result = pd.Series(float("nan"), index=pd.to_datetime(index), dtype=float)
    if isinstance(positions, Mapping):
        observed = pd.Series(
            {pd.Timestamp(key): position_count(value) for key, value in positions.items()},
            dtype=float,
        )
        result.update(observed)
    return result


def strict_finite(value: object, identity: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise RuntimeError(f"{identity} is not numeric") from error
    if not math.isfinite(result):
        raise RuntimeError(f"{identity} is not finite")
    return result


def normalized_positions(positions: object) -> dict[pd.Timestamp, object]:
    if not isinstance(positions, Mapping):
        raise RuntimeError("Qlib did not expose the position mapping")
    return {pd.Timestamp(session).normalize(): position for session, position in positions.items()}


def holdings_records(
    positions: object,
    sessions: pd.Index,
    signal_name: str,
) -> list[dict[str, object]]:
    by_session = normalized_positions(positions)
    records: list[dict[str, object]] = []
    for session_value in pd.to_datetime(sessions):
        session = pd.Timestamp(session_value).normalize()
        position = by_session.get(session)
        stocks = sorted(position.get_stock_list()) if position is not None else []
        if not stocks:
            records.append(
                {
                    "session": str(session.date()),
                    "signal": signal_name,
                    "instrument": "",
                    "is_empty": True,
                    "amount": 0.0,
                    "weight": 0.0,
                    "value": 0.0,
                }
            )
            continue
        weights = position.get_stock_weight_dict(only_stock=False)
        for instrument in stocks:
            amount = strict_finite(
                position.get_stock_amount(instrument),
                f"holdings.{session.date()}.{instrument}.amount",
            )
            price = strict_finite(
                position.get_stock_price(instrument),
                f"holdings.{session.date()}.{instrument}.price",
            )
            weight = strict_finite(
                weights[instrument],
                f"holdings.{session.date()}.{instrument}.weight",
            )
            records.append(
                {
                    "session": str(session.date()),
                    "signal": signal_name,
                    "instrument": str(instrument),
                    "is_empty": False,
                    "amount": amount,
                    "weight": weight,
                    "value": strict_finite(
                        amount * price,
                        f"holdings.{session.date()}.{instrument}.value",
                    ),
                }
            )
    return records


def compare_metrics(
    observed: Mapping[str, Mapping[str, float]],
    sealed: Mapping[str, Mapping[str, float]],
) -> tuple[int, float]:
    compared, maximum = 0, 0.0
    if set(observed) != set(sealed):
        raise RuntimeError("replayed signal metrics differ from sealed signals")
    for signal, sealed_values in sealed.items():
        for metric, expected in sealed_values.items():
            if metric not in observed[signal]:
                raise RuntimeError(f"replayed metric is absent: {signal}.{metric}")
            difference = abs(
                strict_finite(observed[signal][metric], f"observed.{signal}.{metric}")
                - strict_finite(expected, f"sealed.{signal}.{metric}")
            )
            compared += 1
            maximum = max(maximum, difference)
    if maximum > 1e-12:
        raise RuntimeError(f"replayed metrics exceed strict tolerance: {maximum}")
    return compared, maximum


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return value


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--variant-lock", type=Path, required=True)
    parser.add_argument("--split", choices=tuple(SPLITS), required=True)
    parser.add_argument(
        "--strategy-variant",
        choices=(TOP50_PUBLIC_VARIANT, TOP3_PUBLIC_VARIANT),
        required=True,
    )
    parser.add_argument("--backtest-receipt", type=Path)
    parser.add_argument("--qlib-site-packages", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.out_dir.resolve()
    if output.exists() or root not in output.parents:
        raise RuntimeError("Top3 result must be a new directory under root")
    lock = validate_variant_lock(read_json(args.variant_lock))
    if sha256_file(Path(__file__).resolve()) != lock["runner_sha256"]:
        raise RuntimeError("runner differs from the pre-result lock")
    contract_path = Path(str(contract_module.__file__)).resolve()
    if sha256_file(contract_path) != lock["contract_sha256"]:
        raise RuntimeError("contract differs from the pre-result lock")
    source = next(item for item in lock["sources"] if item["split"] == args.split)
    top50 = args.strategy_variant == TOP50_PUBLIC_VARIANT
    if top50 and args.backtest_receipt is None:
        raise RuntimeError("Top50 holdings replay requires its sealed backtest receipt")
    if not top50 and args.backtest_receipt is not None:
        raise RuntimeError("Top3 result creates its own sealed backtest receipt")
    sealed_backtest = validate_backtest_receipt(read_json(args.backtest_receipt)) if top50 else None
    if sealed_backtest is not None and sealed_backtest["id"] != source["track_id"]:
        raise RuntimeError("Top50 backtest receipt differs from the selected split")
    signal_receipt_path = (root / source["signal_receipt_path"]).resolve()
    provider_receipt_path = (root / source["provider_receipt_path"]).resolve()
    if (
        sha256_file(signal_receipt_path) != source["signal_receipt_sha256"]
        or sha256_file(provider_receipt_path) != source["provider_receipt_sha256"]
    ):
        raise RuntimeError("sealed source receipt changed")
    signal_receipt = validate_signal_receipt(read_json(signal_receipt_path))
    signal_artifact = signal_receipt["artifacts"]["signals"]
    signal_path = (root / signal_artifact["path"]).resolve()
    if sha256_file(signal_path) != source["signal_artifact_sha256"]:
        raise RuntimeError("sealed signal artifact changed")
    provider_receipt = read_json(provider_receipt_path)
    provider_content = dict(provider_receipt)
    provider_claimed = provider_content.pop("receipt_hash", None)
    if (
        provider_receipt.get("status") != "PASS"
        or canonical_hash(provider_content) != provider_claimed
    ):
        raise RuntimeError("provider receipt is not canonical")
    provider_root = (root / str(provider_receipt["provider_path"])).resolve()
    provider_sha, provider_files = tree_hash(provider_root)
    if (
        provider_sha != source["provider_tree_sha256"]
        or provider_files != provider_receipt["provider_files"]
    ):
        raise RuntimeError("sealed provider changed")

    sys.path.append(str(args.qlib_site_packages.resolve()))
    import qlib
    from qlib.backtest import backtest, executor
    from qlib.config import REG_CN
    from qlib.contrib.evaluate import risk_analysis
    from qlib.contrib.strategy import TopkDropoutStrategy

    distribution = importlib.metadata.distribution("pyqlib")
    dist_root = Path(str(distribution._path))
    qlib_root = Path(qlib.__file__).resolve().parent
    qlib_sha, _ = tree_hash(qlib_root, "*.py")
    if (
        importlib.metadata.version("pyqlib") != lock["qlib_version"]
        or sha256_file(dist_root / "METADATA") != lock["qlib_metadata_sha256"]
        or sha256_file(dist_root / "RECORD") != lock["qlib_record_sha256"]
        or qlib_sha != lock["qlib_source_tree_sha256"]
    ):
        raise RuntimeError("Qlib differs from the pre-result lock")
    qlib.init(provider_uri=str(provider_root), region=REG_CN)
    signals = pd.read_csv(signal_path, parse_dates=["datetime"])
    if set(signals.columns) != {"datetime", "instrument", *SIGNALS}:
        raise RuntimeError("signal columns are not exact")
    expected_year = int(SPLITS[args.split]["year"])
    if signals["datetime"].dt.year.ne(expected_year).any():
        raise RuntimeError("signal split crossed the frozen year")
    start, end = str(signals["datetime"].min().date()), str(signals["datetime"].max().date())
    daily_frames: list[pd.DataFrame] = []
    raw_frames: list[pd.DataFrame] = []
    holding_rows: list[dict[str, object]] = []
    metrics: dict[str, dict[str, float]] = {}
    turnover_exposed = False
    positions_exposed = False
    for signal_name in SIGNALS:
        series = signals.set_index(["instrument", "datetime"])[signal_name].sort_index()
        strategy_config = EXPECTED_STRATEGY if top50 else TOP3_STRATEGY
        strategy = TopkDropoutStrategy(signal=series, **strategy_config)
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
                time_per_step="day", generate_portfolio_metrics=True, delay_execution=True
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
        net_risk, excess_risk = (
            risk_analysis(net, freq="1day"),
            risk_analysis(excess_with, freq="1day"),
        )
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
                net_risk, "max_drawdown", (net.cumsum() - net.cumsum().cummax()).min()
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
    daily_path = output / "daily-series.csv"
    raw_path = output / "raw-report.csv"
    holdings_path = output / "daily-holdings.csv"
    combined = pd.concat(daily_frames, ignore_index=True)
    if not top50:
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
    holding_support = validate_holdings_records(
        holding_rows,
        expected_sessions=int(
            combined.loc[combined["signal"] == PRIMARY_SIGNAL, "datetime"].nunique()
        ),
    )
    pd.DataFrame(holding_rows, columns=HOLDINGS_COLUMNS).to_csv(
        holdings_path,
        index=False,
        float_format="%.17g",
    )
    split_contract = SPLITS_V2[args.split]
    compared_values, maximum_difference = (
        compare_metrics(metrics, sealed_backtest["metrics"])
        if sealed_backtest is not None
        else compare_metrics(metrics, metrics)
    )
    if top50:
        backtest_path = args.backtest_receipt.resolve()
        backtest_id = sealed_backtest["id"]
    else:
        backtest_path = output / "backtest-receipt.json"
        backtest_id = split_contract["variant_receipt_id"]
    holdings_artifact = {
        "path": holdings_path.relative_to(root).as_posix(),
        "sha256": sha256_file(holdings_path),
        "bytes": holdings_path.stat().st_size,
        "schema_version": HOLDINGS_SCHEMA,
        "columns": list(HOLDINGS_COLUMNS),
        **holding_support,
    }
    if top50:
        holdings_receipt: dict[str, Any] = {
            "schema_version": HOLDINGS_RECEIPT_SCHEMA,
            "status": "PASS",
            "id": f"{backtest_id}-holdings-v1",
            "backtest_id": backtest_id,
            "generated_at": datetime.now(UTC).isoformat(),
            "evaluation_split": args.split,
            "strategy_variant_id": TOP50_PUBLIC_VARIANT,
            "execution_domain": EXECUTION_DOMAIN,
            "online_paper_equivalent": False,
            "promotion_eligible": False,
            "backtest_receipt_path": backtest_path.relative_to(root).as_posix(),
            "backtest_receipt_sha256": sha256_file(backtest_path),
            "generator_code_sha256": sha256_file(Path(__file__).resolve()),
            "source_signal_receipt_sha256": source["signal_receipt_sha256"],
            "source_provider_receipt_sha256": source["provider_receipt_sha256"],
            "metrics_comparison": {
                "status": "PASS",
                "absolute_tolerance": 1e-12,
                "compared_values": compared_values,
                "maximum_absolute_difference": maximum_difference,
            },
            "artifact": holdings_artifact,
        }
        holdings_receipt["receipt_hash"] = canonical_hash(holdings_receipt)
        validate_holdings_receipt(holdings_receipt)
        holdings_receipt_path = output / "holdings-receipt.json"
        atomic_json(holdings_receipt, holdings_receipt_path)
        print(json.dumps({"status": "PASS", "out": str(output)}))
        return 0
    receipt: dict[str, Any] = {
        "schema_version": VARIANT_BACKTEST_SCHEMA_V2,
        "status": "PASS",
        "id": split_contract["variant_receipt_id"],
        "generated_at": datetime.now(UTC).isoformat(),
        "model_cell_id": MODEL_CELL,
        "primary_signal": PRIMARY_SIGNAL,
        "strategy_variant_id": TOP3_PUBLIC_VARIANT,
        "variant_definition_id": TOP3_VARIANT_ID_V2,
        "strategy_role": TOP3_STRATEGY_ROLE,
        "comparison_group_id": COMPARISON_GROUP_ID,
        "evaluation_split": args.split,
        "result_role": split_contract["result_role"],
        "source_backtest_id": split_contract["source_track_id"],
        "test_data_access": split_contract["test_data_access"],
        "execution_domain": EXECUTION_DOMAIN,
        "online_paper_equivalent": False,
        "promotion_eligible": False,
        "selection_eligible": False,
        "used_for_selection": False,
        "variant_lock_sha256": sha256_file(args.variant_lock),
        "source_signal_receipt_sha256": source["signal_receipt_sha256"],
        "source_provider_receipt_sha256": source["provider_receipt_sha256"],
        "backtest_code_sha256": sha256_file(Path(__file__).resolve()),
        "qlib": {
            "version": lock["qlib_version"],
            "metadata_sha256": lock["qlib_metadata_sha256"],
            "record_sha256": lock["qlib_record_sha256"],
            "source_tree_sha256": lock["qlib_source_tree_sha256"],
        },
        "strategy": dict(TOP3_STRATEGY),
        "execution": dict(EXPECTED_EXECUTION),
        "support": {
            "requested_start": start,
            "requested_end": end,
            "actual_start": str(pd.to_datetime(combined["datetime"]).min().date()),
            "actual_end": str(pd.to_datetime(combined["datetime"]).max().date()),
            "sessions": int(
                combined.loc[combined["signal"] == PRIMARY_SIGNAL, "datetime"].nunique()
            ),
            "signal_rows": len(signals),
            "signal_cross_sections": int(signals["datetime"].nunique()),
        },
        "observability": {
            "turnover_exposed": bool(turnover_exposed),
            "position_count_exposed": bool(positions_exposed),
        },
        "metrics": metrics,
        "artifacts": {
            name: {
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for name, path in (("daily_series", daily_path), ("raw_report", raw_path))
        },
        "deviations": [
            "Post-hoc portfolio-size sensitivity; never used for model or strategy selection.",
            "Uses byte-identical admitted signals and Qlib provider from the matching Top50 track.",
            "Uses dynamic PIT CSI300 and provider data rather than the author's Qlib bundle.",
        ],
    }
    receipt["artifacts"]["holdings"] = holdings_artifact
    receipt["receipt_hash"] = canonical_hash(receipt)
    validate_variant_backtest_receipt(receipt)
    receipt_path = output / "backtest-receipt.json"
    temporary = receipt_path.with_suffix(f".json.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(receipt, allow_nan=False, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, receipt_path)
    holdings_receipt = {
        "schema_version": HOLDINGS_RECEIPT_SCHEMA,
        "status": "PASS",
        "id": f"{backtest_id}-holdings-v1",
        "backtest_id": backtest_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "evaluation_split": args.split,
        "strategy_variant_id": TOP3_PUBLIC_VARIANT,
        "execution_domain": EXECUTION_DOMAIN,
        "online_paper_equivalent": False,
        "promotion_eligible": False,
        "backtest_receipt_path": receipt_path.relative_to(root).as_posix(),
        "backtest_receipt_sha256": sha256_file(receipt_path),
        "generator_code_sha256": sha256_file(Path(__file__).resolve()),
        "source_signal_receipt_sha256": source["signal_receipt_sha256"],
        "source_provider_receipt_sha256": source["provider_receipt_sha256"],
        "metrics_comparison": {
            "status": "PASS",
            "absolute_tolerance": 1e-12,
            "compared_values": compared_values,
            "maximum_absolute_difference": maximum_difference,
        },
        "artifact": holdings_artifact,
    }
    holdings_receipt["receipt_hash"] = canonical_hash(holdings_receipt)
    validate_holdings_receipt(holdings_receipt)
    atomic_json(holdings_receipt, output / "holdings-receipt.json")
    print(json.dumps({"status": "PASS", "out": str(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
