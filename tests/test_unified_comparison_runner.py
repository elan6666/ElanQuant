from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

from elanquant.contracts.unified_comparison import validate_result_receipt


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_runner_seals_two_by_three_common_weekly_matrix(tmp_path: Path) -> None:
    root = tmp_path / "research"
    output = root / "artifacts/unified-weekly-comparison/itransformer-b2-vs-kronos-base-weekly-v1"
    external = tmp_path / "external"
    dates = ("2026-04-03", "2026-04-10", "2026-04-17")
    support = [
        {
            "anchor": day,
            "instrument": f"{index:06d}.SZ",
            "realized_return": (index - 25) / 10_000,
            "benchmark_return": 0.001,
        }
        for day in dates
        for index in range(50)
    ]
    b2 = [
        {"anchor": row["anchor"], "instrument": row["instrument"], "score": 50 - index}
        for index, row in enumerate(support)
    ]
    kronos = [
        {"anchor": row["anchor"], "instrument": row["instrument"], "score": index % 50}
        for index, row in enumerate(support)
    ]
    support_path, b2_path, kronos_path = (
        external / "support.csv",
        external / "b2.csv",
        external / "kronos.csv",
    )
    _write_csv(
        support_path,
        ["anchor", "instrument", "realized_return", "benchmark_return"],
        support,
    )
    _write_csv(b2_path, ["anchor", "instrument", "score"], b2)
    _write_csv(kronos_path, ["anchor", "instrument", "score"], kronos)
    files = [
        external / name
        for name in (
            "b2-input.json",
            "kronos-input.json",
            "b2.model",
            "kronos.model",
            "b2.py",
            "kronos.py",
        )
    ]
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
    script = Path(__file__).parents[1] / "scripts/server/run_unified_b2_kronos_weekly.py"
    environment = {
        **os.environ,
        "PYTHONPATH": f"{Path(__file__).parents[1] / 'backend/src'}:{Path(__file__).parents[1]}",
    }
    subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(root),
            "--support",
            str(support_path),
            "--b2-scores",
            str(b2_path),
            "--kronos-scores",
            str(kronos_path),
            "--b2-input",
            str(files[0]),
            "--kronos-input",
            str(files[1]),
            "--b2-model",
            str(files[2]),
            "--kronos-model",
            str(files[3]),
            "--b2-runner",
            str(files[4]),
            "--kronos-runner",
            str(files[5]),
            "--out-dir",
            str(output),
        ],
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )
    for family in ("itransformer-b2-r16g-r3", "kronos-base-zero-shot"):
        for topk in (1, 3, 50):
            target = output / "results" / family / f"top{topk}"
            receipt = validate_result_receipt(
                json.loads((target / "result-receipt.json").read_text(encoding="utf-8"))
            )
            assert receipt["portfolio_id"] == f"top{topk}"
            assert (target / "daily_series.csv").is_file()
            holdings = json.loads((target / "holdings.json").read_text(encoding="utf-8"))
            assert len(holdings["items"]) == topk
