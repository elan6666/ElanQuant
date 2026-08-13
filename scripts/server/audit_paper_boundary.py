#!/usr/bin/env python3
"""Prove that artifact-only research does not mutate the Top3 paper ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TABLES = (
    "recommendation_sets",
    "recommendation_items",
    "paper_accounts",
    "paper_positions",
    "paper_orders",
    "paper_fills",
    "portfolio_snapshots",
    "paper_signal_publications",
    "paper_intent_decisions",
)
FROZEN_LEDGER_TABLES = (
    "paper_accounts",
    "paper_positions",
    "paper_orders",
    "paper_fills",
    "paper_signal_publications",
)


def canonical(payload: object) -> bytes:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def normalize(value: object) -> object:
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    return value


def table_identity(connection: sqlite3.Connection, table: str) -> dict[str, object]:
    columns = [
        str(row[1])
        for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    ]
    if not columns:
        raise RuntimeError(f"required paper boundary table is absent: {table}")
    rows = [
        [normalize(value) for value in row]
        for row in connection.execute(f'SELECT * FROM "{table}"').fetchall()
    ]
    rendered_rows = sorted(canonical(row) for row in rows)
    digest = hashlib.sha256()
    digest.update(canonical(columns))
    for row in rendered_rows:
        digest.update(row)
    return {"columns": columns, "rows": len(rows), "sha256": digest.hexdigest()}


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--scope", choices=("full", "frozen-ledger"), default="full")
    args = parser.parse_args()
    database = args.database.resolve()
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        selected_tables = TABLES if args.scope == "full" else FROZEN_LEDGER_TABLES
        tables = {table: table_identity(connection, table) for table in selected_tables}
    finally:
        connection.close()
    unchanged: bool | None = None
    if args.compare is not None:
        baseline = json.loads(args.compare.read_text(encoding="utf-8"))
        unchanged = baseline.get("tables") == tables
        if not unchanged:
            raise RuntimeError("Top3 recommendation or paper ledger changed")
    payload: dict[str, Any] = {
        "schema_version": "elanquant_paper_boundary_audit_v1",
        "status": "PASS",
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": args.scope,
        "tables": tables,
        "unchanged_from_baseline": unchanged,
    }
    atomic_json(payload, args.out)
    print(json.dumps({"status": "PASS", "unchanged": unchanged, "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
