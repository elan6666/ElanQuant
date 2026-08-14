#!/usr/bin/env python3
"""Read-only audit for the sealed Top3 variants and exact v3 catalog."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

from elanquant.contracts.historical_variants import (
    HOLDINGS_COLUMNS,
    TOP3_PUBLIC_VARIANT,
    validate_any_backtest_receipt,
    validate_historical_catalog,
    validate_holdings_receipt,
    validate_holdings_records,
    validate_variant_lock,
)
from elanquant.contracts.official_demo import canonical_hash, sha256_file, validate_signal_receipt


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return value


def require_read_only(path: Path) -> None:
    if stat.S_IMODE(path.stat().st_mode) & 0o222:
        raise RuntimeError(f"sealed artifact remains writable: {path}")


def tree_hash(root: Path) -> tuple[str, int]:
    digest, count = hashlib.sha256(), 0
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
        count += 1
    return digest.hexdigest(), count


def read_holdings(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(HOLDINGS_COLUMNS):
            raise RuntimeError("daily holdings CSV columns are not exact")
        records: list[dict[str, object]] = []
        for row in reader:
            if row["is_empty"] not in {"True", "False"}:
                raise RuntimeError("daily holdings CSV boolean is invalid")
            records.append(
                {
                    "session": row["session"],
                    "signal": row["signal"],
                    "instrument": row["instrument"],
                    "is_empty": row["is_empty"] == "True",
                    "amount": float(row["amount"]),
                    "weight": float(row["weight"]),
                    "value": float(row["value"]),
                }
            )
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--variant-lock", type=Path, required=True)
    parser.add_argument("--paper-before", type=Path, required=True)
    parser.add_argument("--paper-after", type=Path, required=True)
    parser.add_argument("--current-link", type=Path, required=True)
    parser.add_argument("--expected-current-target", required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    catalog_path = args.catalog.resolve()
    catalog = validate_historical_catalog(read_json(catalog_path))
    lock = validate_variant_lock(read_json(args.variant_lock))
    require_read_only(catalog_path)
    require_read_only(args.variant_lock)
    if (
        not args.current_link.is_symlink()
        or os.readlink(args.current_link) != args.expected_current_target
    ):
        raise RuntimeError("releases/current changed during historical research")
    before, after = read_json(args.paper_before), read_json(args.paper_after)
    if (
        before.get("tables") != after.get("tables")
        or after.get("unchanged_from_baseline") is not True
    ):
        raise RuntimeError("paper-account boundary changed")
    for source in lock["sources"]:
        signal_path = (root / source["signal_receipt_path"]).resolve()
        provider_path = (root / source["provider_receipt_path"]).resolve()
        if (
            sha256_file(signal_path) != source["signal_receipt_sha256"]
            or sha256_file(provider_path) != source["provider_receipt_sha256"]
        ):
            raise RuntimeError("sealed source receipt changed")
        signal = validate_signal_receipt(read_json(signal_path))
        signal_artifact = (root / signal["artifacts"]["signals"]["path"]).resolve()
        if sha256_file(signal_artifact) != source["signal_artifact_sha256"]:
            raise RuntimeError("sealed signal artifact changed")
        provider = read_json(provider_path)
        provider_content = dict(provider)
        provider_claimed = provider_content.pop("receipt_hash", None)
        if provider.get("status") != "PASS" or canonical_hash(provider_content) != provider_claimed:
            raise RuntimeError("sealed provider receipt is not canonical")
        provider_root = (root / provider["provider_path"]).resolve()
        provider_sha, provider_files = tree_hash(provider_root)
        if (
            provider_sha != source["provider_tree_sha256"]
            or provider_files != provider["provider_files"]
        ):
            raise RuntimeError("sealed provider tree changed")
    audited: list[dict[str, Any]] = []
    loaded: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for entry in catalog["entries"]:
        receipt_path = (root / entry["receipt_path"]).resolve()
        if root not in receipt_path.parents or sha256_file(receipt_path) != entry["receipt_sha256"]:
            raise RuntimeError("catalog receipt identity mismatch")
        receipt = validate_any_backtest_receipt(read_json(receipt_path))
        if receipt["id"] != entry["id"]:
            raise RuntimeError("catalog receipt id mismatch")
        loaded[receipt["id"]] = (entry, receipt)
        holdings_pointer = entry["holdings"]
        holdings_receipt_path = (root / holdings_pointer["receipt_path"]).resolve()
        if (
            root not in holdings_receipt_path.parents
            or sha256_file(holdings_receipt_path) != holdings_pointer["receipt_sha256"]
        ):
            raise RuntimeError("catalog holdings receipt identity mismatch")
        holdings_receipt = validate_holdings_receipt(read_json(holdings_receipt_path))
        if (
            holdings_receipt["backtest_id"] != receipt["id"]
            or holdings_receipt["backtest_receipt_sha256"] != entry["receipt_sha256"]
            or holdings_receipt["generator_code_sha256"] != lock["runner_sha256"]
        ):
            raise RuntimeError("holdings sidecar binding mismatch")
        holdings_artifact = holdings_receipt["artifact"]
        holdings_path = (root / holdings_artifact["path"]).resolve()
        if (
            root not in holdings_path.parents
            or sha256_file(holdings_path) != holdings_artifact["sha256"]
            or holdings_path.stat().st_size != holdings_artifact["bytes"]
        ):
            raise RuntimeError("daily holdings artifact identity mismatch")
        holding_support = validate_holdings_records(
            read_holdings(holdings_path),
            expected_sessions=holdings_artifact["sessions"],
        )
        if any(holding_support[field] != holdings_artifact[field] for field in holding_support):
            raise RuntimeError("daily holdings support differs from receipt")
        require_read_only(holdings_receipt_path)
        require_read_only(holdings_path)
        for artifact in receipt["artifacts"].values():
            artifact_path = (root / artifact["path"]).resolve()
            if (
                root not in artifact_path.parents
                or sha256_file(artifact_path) != artifact["sha256"]
            ):
                raise RuntimeError("backtest artifact identity mismatch")
        if entry["strategy_variant_id"] == TOP3_PUBLIC_VARIANT:
            require_read_only(receipt_path)
            if receipt["variant_lock_sha256"] != sha256_file(args.variant_lock):
                raise RuntimeError("Top3 result differs from variant lock")
            split = receipt["evaluation_split"]
            source = next(item for item in lock["sources"] if item["split"] == split)
            if (
                receipt["source_signal_receipt_sha256"] != source["signal_receipt_sha256"]
                or receipt["source_provider_receipt_sha256"] != source["provider_receipt_sha256"]
            ):
                raise RuntimeError("Top3 did not byte-reuse the sealed source")
            preserved = receipt_path.parent / "backtest-source.py"
            if sha256_file(preserved) != receipt["backtest_code_sha256"]:
                raise RuntimeError("preserved Top3 runner identity mismatch")
            require_read_only(preserved)
            for artifact in receipt["artifacts"].values():
                require_read_only(root / artifact["path"])
        audited.append(
            {
                "id": receipt["id"],
                "split": entry["evaluation_split"],
                "variant": entry["strategy_variant_id"],
                "sessions": receipt["support"]["sessions"],
            }
        )
    for identifier, (entry, receipt) in loaded.items():
        source = entry["source"]
        source_id = entry["source_backtest_id"]
        if source_id is None:
            if source["backtest_receipt_sha256"] != entry["receipt_sha256"]:
                raise RuntimeError("Top50 catalog self provenance mismatch")
            continue
        source_entry, source_receipt = loaded[source_id]
        if (
            source["backtest_receipt_sha256"] != source_entry["receipt_sha256"]
            or source["signal_receipt_sha256"] != source_receipt["signal_receipt_sha256"]
            or source["provider_receipt_sha256"] != source_receipt["provider_receipt_sha256"]
            or receipt["source_signal_receipt_sha256"] != source_receipt["signal_receipt_sha256"]
            or receipt["source_provider_receipt_sha256"]
            != source_receipt["provider_receipt_sha256"]
        ):
            raise RuntimeError(f"cross-variant provenance mismatch: {identifier}")
    print(
        json.dumps(
            {
                "status": "PASS",
                "catalog_receipt_hash": catalog["receipt_hash"],
                "variant_lock_receipt_hash": lock["receipt_hash"],
                "paper_unchanged": True,
                "current_release_unchanged": True,
                "entries": audited,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
