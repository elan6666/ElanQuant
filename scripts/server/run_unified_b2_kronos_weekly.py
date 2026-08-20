#!/usr/bin/env python3
"""Server-only producer for the sealed B2/Kronos strict-weekly comparison.

Inputs are deliberately explicit, pre-materialised CSVs rather than an
implicit local data source.  ``--support`` must contain the B2 evaluation
anchors/labels and columns ``anchor,instrument,realized_return,benchmark_return``;
each score file must contain ``anchor,instrument,score`` for exactly those rows.
The B2 score file is produced from its R16g-r3 80-session window; Kronos Base
may have a different input window, but cannot use different anchors/labels.
Run this only under the research server.  It never writes a paper ledger.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import shutil
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from elanquant.contracts.unified_comparison import (
    ARTIFACT_ROOT,
    EVIDENCE_SCHEMA,
    MODEL_FAMILIES,
    PORTFOLIOS,
    PROTOCOL_SCHEMA,
    RESULT_SCHEMA,
    result_id,
    validate_model_evidence,
    validate_protocol,
    validate_result_receipt,
)

from elanquant.contracts.official_demo import canonical_hash, sha256_file


def _read_csv(path: Path, columns: set[str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        if not rows or not columns.issubset(set(reader.fieldnames or [])):
            raise RuntimeError(f"CSV columns are incomplete: {path}")
    return rows


def _sha(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"required file is absent: {path}")
    return sha256_file(path)


def _relative(root: Path, path: Path) -> str:
    path = path.resolve()
    if root not in path.parents:
        raise RuntimeError(f"path must be under root: {path}")
    return path.relative_to(root).as_posix()


def _copy(root: Path, output: Path, source: Path, name: str) -> dict[str, str]:
    target = output / "sources" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return {"path": _relative(root, target), "sha256": _sha(target)}


def _rank(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda pair: pair[1])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(ordered):
        end = position + 1
        while end < len(ordered) and ordered[end][1] == ordered[position][1]:
            end += 1
        value = (position + end - 1) / 2 + 1
        for index, _ in ordered[position:end]:
            ranks[index] = value
        position = end
    return ranks


def _corr(left: list[float], right: list[float]) -> float:
    if len(left) < 2:
        return 0.0
    a, b = mean(left), mean(right)
    numerator = sum((x - a) * (y - b) for x, y in zip(left, right, strict=True))
    denominator = math.sqrt(sum((x - a) ** 2 for x in left) * sum((y - b) ** 2 for y in right))
    return numerator / denominator if denominator else 0.0


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return {"path": path.as_posix(), "sha256": _sha(path)}


def _rebase_artifact(root: Path, artifact: dict[str, str]) -> dict[str, str]:
    return {"path": _relative(root, Path(artifact["path"])), "sha256": artifact["sha256"]}


def _scores(rows: list[dict[str, object]]) -> dict[str, float]:
    score = [float(row["score"]) for row in rows]
    realised = [float(row["realized_return"]) for row in rows]
    per_anchor: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        per_anchor[str(row["anchor"])].append(row)
    rank_ic = mean(
        _corr(
            _rank([float(row["score"]) for row in group]),
            _rank([float(row["realized_return"]) for row in group]),
        )
        for group in per_anchor.values()
    )
    return {
        "rank_ic": rank_ic,
        "pearson_ic": _corr(score, realised),
        "spearman_ic": _corr(_rank(score), _rank(realised)),
        "mae": mean(abs(x - y) for x, y in zip(score, realised, strict=True)),
        "rmse": math.sqrt(mean((x - y) ** 2 for x, y in zip(score, realised, strict=True))),
    }


def _backtest(
    root: Path, output: Path, family: str, topk: int, rows: list[dict[str, object]], costs: float
) -> tuple[dict[str, float], dict[str, dict[str, str]]]:
    by_anchor: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_anchor[str(row["anchor"])].append(row)
    series: list[dict[str, object]] = []
    holdings: list[dict[str, object]] = []
    previous: set[str] = set()
    strategy_nav = benchmark_nav = 1.0
    turnover: list[float] = []
    for anchor, group in sorted(by_anchor.items()):
        selected = sorted(group, key=lambda row: (-float(row["score"]), str(row["instrument"])))[
            :topk
        ]
        if len(selected) != topk:
            raise RuntimeError(f"insufficient candidates for {family}/{anchor}/Top{topk}")
        instruments = {str(row["instrument"]) for row in selected}
        change = 1.0 - len(instruments & previous) / topk if previous else 1.0
        previous = instruments
        # The aligned B2 cohort labels are log(open_exit / open_entry).
        # IC remains on that native label scale, while the portfolio curve
        # compounds the corresponding arithmetic return.
        gross = mean(math.expm1(float(row["realized_return"])) for row in selected)
        benchmark = mean(math.expm1(float(row["benchmark_return"])) for row in selected)
        cost = change * costs
        strategy_nav *= 1 + gross - cost
        benchmark_nav *= 1 + benchmark
        turnover.append(change)
        series.append(
            {
                "session": anchor,
                "strategy": strategy_nav - 1,
                "benchmark": benchmark_nav - 1,
                "excess": strategy_nav / benchmark_nav - 1,
                "strategy_nav": strategy_nav,
                "benchmark_nav": benchmark_nav,
                "cost": cost,
            }
        )
        holdings.append(
            {
                "session": anchor,
                "items": [
                    {"instrument": row["instrument"], "weight": 1 / topk, "amount": 0, "value": 0}
                    for row in selected
                ],
            }
        )
    running = 1.0
    drawdown = 0.0
    for row in series:
        running = max(running, float(row["strategy_nav"]))
        drawdown = min(drawdown, float(row["strategy_nav"]) / running - 1)
    excess = [float(row["strategy"]) - float(row["benchmark"]) for row in series]
    deviation = math.sqrt(mean((value - mean(excess)) ** 2 for value in excess))
    slug = f"results/{family}/top{topk}"
    artifacts = {
        "daily_series": _rebase_artifact(
            root, _write_csv(output / slug / "daily_series.csv", list(series[0]), series)
        ),
        "holdings": {},
    }
    holdings_path = output / slug / "holdings.json"
    # The public comparison card intentionally exposes the final sealed
    # portfolio.  The full period remains reproducible from daily series and
    # raw report, while this compact artifact prevents the web API from
    # treating a list of session snapshots as a single holding set.
    holdings_path.write_text(
        json.dumps(holdings[-1], sort_keys=True) + "\n", encoding="utf-8"
    )
    artifacts["holdings"] = {"path": _relative(root, holdings_path), "sha256": _sha(holdings_path)}
    report = output / slug / "raw_report.json"
    report.write_text(
        json.dumps({"family": family, "topk": topk, "sessions": len(series)}, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    artifacts["raw_report"] = {"path": _relative(root, report), "sha256": _sha(report)}
    return (
        {
            "total_return_with_cost": strategy_nav - 1,
            "benchmark_return": benchmark_nav - 1,
            "excess_return_with_cost": strategy_nav / benchmark_nav - 1,
            "information_ratio_with_cost": mean(excess) / deviation if deviation else 0.0,
            "max_drawdown_with_cost": drawdown,
            "turnover_mean": mean(turnover),
            "total_cost": sum(float(row["cost"]) for row in series),
        },
        artifacts,
    )


def _generate_kronos_scores(
    runner: Path, support: Path, model: Path, model_input: Path, output: Path
) -> None:
    """Call the pinned upstream adapter's real Base zero-shot signal stage.

    The adapter is supplied by the server workspace and must expose
    ``generate_scores(support_csv, model_path, input_path, output_csv)``.  This
    keeps this orchestration layer independent of pinned Kronos internals while
    making the actual model-load/inference step mandatory when no score file is
    supplied.
    """
    spec = importlib.util.spec_from_file_location("unified_kronos_adapter", runner)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Kronos zero-shot adapter")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    generate = getattr(module, "generate_scores", None)
    if not callable(generate):
        raise RuntimeError("Kronos adapter must expose generate_scores")
    output.parent.mkdir(parents=True, exist_ok=True)
    generate(support_csv=support, model_path=model, input_path=model_input, output_csv=output)
    _sha(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--support", type=Path, required=True)
    parser.add_argument("--b2-scores", type=Path, required=True)
    parser.add_argument("--kronos-scores", type=Path)
    parser.add_argument("--b2-input", type=Path, required=True)
    parser.add_argument("--kronos-input", type=Path, required=True)
    parser.add_argument("--b2-model", type=Path, required=True)
    parser.add_argument("--kronos-model", type=Path, required=True)
    parser.add_argument("--b2-runner", type=Path, required=True)
    parser.add_argument("--kronos-runner", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--b2-lookback", type=int, default=80)
    parser.add_argument("--kronos-lookback", type=int, default=90)
    parser.add_argument("--cost-rate", type=float, default=0.0025)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.out_dir.resolve()
    if (
        output.exists()
        or root not in output.parents
        or not _relative(root, output).startswith(f"{ARTIFACT_ROOT}/")
    ):
        raise RuntimeError("out-dir must be a new directory under the sealed artifact root")
    if args.b2_lookback != 80 or args.kronos_lookback <= 0 or not 0 <= args.cost_rate < 1:
        raise RuntimeError("invalid B2/Kronos window or cost configuration")
    if args.kronos_scores is None:
        args.kronos_scores = output / "generated" / "kronos-base-zero-shot-scores.csv"
        _generate_kronos_scores(
            args.kronos_runner.resolve(),
            args.support.resolve(),
            args.kronos_model.resolve(),
            args.kronos_input.resolve(),
            args.kronos_scores,
        )
    files = [
        args.support,
        args.b2_scores,
        args.kronos_scores,
        args.b2_input,
        args.kronos_input,
        args.b2_model,
        args.kronos_model,
        args.b2_runner,
        args.kronos_runner,
    ]
    for path in files:
        _sha(path)
    support = _read_csv(
        args.support, {"anchor", "instrument", "realized_return", "benchmark_return"}
    )
    pairs = [(row["anchor"], row["instrument"]) for row in support]
    if len(pairs) != len(set(pairs)):
        raise RuntimeError("support contains duplicate anchor/instrument rows")
    support_map = {(row["anchor"], row["instrument"]): row for row in support}
    common = {
        "evaluation_range": {
            "start": min(row["anchor"] for row in support),
            "end": max(row["anchor"] for row in support),
        },
        "anchor_set_sha256": _sha(args.support),
        "label_artifact_sha256": _sha(args.support),
        "universe_artifact_sha256": _sha(args.support),
        "execution_spec_sha256": _sha(Path(__file__)),
        "anchor_frequency": "strict_weekly",
        "label_definition": "strict_weekly_open_to_open_log_return",
        "execution_semantics": "next_trading_session_open",
        "delay_sessions": 1,
        "support": {
            "anchors": len({row["anchor"] for row in support}),
            "signal_rows": len(support),
        },
    }
    evidence: list[dict[str, Any]] = []
    merged_by_family: dict[str, list[dict[str, object]]] = {}
    for family, score_path, input_path, model_path, runner_path, lookback, feature in (
        (
            MODEL_FAMILIES[0],
            args.b2_scores,
            args.b2_input,
            args.b2_model,
            args.b2_runner,
            args.b2_lookback,
            "OHLCV+technical_factors",
        ),
        (
            MODEL_FAMILIES[1],
            args.kronos_scores,
            args.kronos_input,
            args.kronos_model,
            args.kronos_runner,
            args.kronos_lookback,
            "OHLCVA",
        ),
    ):
        scores = _read_csv(score_path, {"anchor", "instrument", "score"})
        score_map = {(row["anchor"], row["instrument"]): row for row in scores}
        if set(score_map) != set(support_map) or len(score_map) != len(scores):
            raise RuntimeError(f"{family} scores do not exactly match B2 strict-weekly support")
        merged = [
            {**support_row, "score": float(score_map[key]["score"])}
            for key, support_row in sorted(support_map.items())
        ]
        if not all(
            math.isfinite(float(row["score"])) and math.isfinite(float(row["realized_return"]))
            for row in merged
        ):
            raise RuntimeError(f"{family} contains a non-finite score or label")
        merged_by_family[family] = merged
        input_artifact = _copy(root, output, input_path, f"inputs/{family}{input_path.suffix}")
        predictions = _copy(root, output, score_path, f"predictions/{family}.csv")
        score_report = output / "scores" / f"{family}.json"
        score_report.parent.mkdir(parents=True, exist_ok=True)
        score_report.write_text(
            json.dumps(_scores(merged), sort_keys=True) + "\n", encoding="utf-8"
        )
        evidence_payload = {
            "schema_version": EVIDENCE_SCHEMA,
            "status": "PASS",
            "id": f"weekly-evidence-{family}-v1",
            "model_family_id": family,
            "common_protocol": common,
            "model_input": {
                "lookback_sessions": lookback,
                "feature_schema": feature,
                "input_artifact": input_artifact,
            },
            "model_sha256": _sha(model_path),
            "runner_code_sha256": _sha(runner_path),
            "artifacts": {
                "predictions": predictions,
                "scores": {"path": _relative(root, score_report), "sha256": _sha(score_report)},
            },
            "online_paper_equivalent": False,
            "promotion_eligible": False,
        }
        evidence_payload["receipt_hash"] = canonical_hash(evidence_payload)
        validate_model_evidence(evidence_payload)
        evidence_path = output / "evidence" / f"{family}.json"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(
            json.dumps(evidence_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        evidence.append(
            {
                "model_family_id": family,
                "receipt_path": _relative(root, evidence_path),
                "receipt_sha256": _sha(evidence_path),
                "common_protocol": common,
            }
        )
    protocol = {
        "schema_version": PROTOCOL_SCHEMA,
        "status": "PASS",
        "id": "itransformer-b2-vs-kronos-base-weekly-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "model_families": list(MODEL_FAMILIES),
        "portfolios": list(PORTFOLIOS),
        "common_protocol": common,
        "online_paper_equivalent": False,
        "promotion_eligible": False,
        "source_evidence": evidence,
    }
    protocol["receipt_hash"] = canonical_hash(protocol)
    validate_protocol(protocol)
    protocol_path = output / "protocol" / "protocol-receipt.json"
    protocol_path.parent.mkdir(parents=True, exist_ok=True)
    protocol_path.write_text(
        json.dumps(protocol, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for family, merged in merged_by_family.items():
        for portfolio in PORTFOLIOS:
            metrics, artifacts = _backtest(
                root, output, family, int(portfolio[3:]), merged, args.cost_rate
            )
            receipt = {
                "schema_version": RESULT_SCHEMA,
                "status": "PASS",
                "id": result_id(family, portfolio),
                "model_family_id": family,
                "portfolio_id": portfolio,
                "protocol_id": protocol["id"],
                "protocol_receipt_sha256": _sha(protocol_path),
                "source_evidence_receipt_sha256": next(
                    item["receipt_sha256"] for item in evidence if item["model_family_id"] == family
                ),
                "prediction_metrics": _scores(merged),
                "portfolio_metrics": metrics,
                "artifacts": artifacts,
                "online_paper_equivalent": False,
                "promotion_eligible": False,
            }
            receipt["receipt_hash"] = canonical_hash(receipt)
            validate_result_receipt(receipt)
            receipt_path = output / "results" / family / portfolio / "result-receipt.json"
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(
                json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
    print(json.dumps({"status": "PASS", "out_dir": str(output), "protocol": str(protocol_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
