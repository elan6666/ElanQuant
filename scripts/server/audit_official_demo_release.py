#!/usr/bin/env python3
"""Independently validate the sealed official-demo historical research track."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from elanquant.contracts.official_demo import (
    FINAL_TEST_STRATEGY_ID,
    canonical_hash,
    sha256_file,
    validate_analysis_lock,
    validate_backtest_catalog,
    validate_backtest_receipt,
    validate_signal_receipt,
)


def tree_identity(root: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
        count += 1
    return digest.hexdigest(), count


def read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON artifact is not an object: {path.name}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    catalog_path = args.catalog.resolve()
    catalog = validate_backtest_catalog(read_json(catalog_path))
    audited: list[dict[str, object]] = []
    for entry in catalog["entries"]:
        receipt_path = (root / str(entry["receipt_path"])).resolve()
        if (
            root not in receipt_path.parents
            or sha256_file(receipt_path) != entry["receipt_sha256"]
        ):
            raise RuntimeError("catalog backtest receipt identity is invalid")
        receipt = validate_backtest_receipt(read_json(receipt_path))
        run_root = receipt_path.parent.parent
        signal_receipt_path = run_root / "signals" / "signal-receipt.json"
        if sha256_file(signal_receipt_path) != receipt["signal_receipt_sha256"]:
            raise RuntimeError("backtest and signal receipt identities differ")
        signal_receipt = validate_signal_receipt(read_json(signal_receipt_path))
        signal_artifact = signal_receipt["artifacts"]["signals"]
        signal_path = (root / str(signal_artifact["path"])).resolve()
        if sha256_file(signal_path) != signal_artifact["sha256"]:
            raise RuntimeError("signal artifact hash mismatch")
        daily_artifact = receipt["artifacts"]["daily_series"]
        daily_path = (root / str(daily_artifact["path"])).resolve()
        if sha256_file(daily_path) != daily_artifact["sha256"]:
            raise RuntimeError("daily series hash mismatch")
        if sha256_file(run_root / "signals" / "generator-source.py") != signal_receipt[
            "generator_code_sha256"
        ]:
            raise RuntimeError("preserved signal source hash mismatch")
        if sha256_file(run_root / "result" / "backtest-source.py") != receipt[
            "backtest_code_sha256"
        ]:
            raise RuntimeError("preserved backtest source hash mismatch")

        provider_dir = (
            "qlib-provider"
            if receipt["id"] == FINAL_TEST_STRATEGY_ID
            else "qlib-provider-r4"
        )
        provider_receipt_path = run_root / provider_dir / "provider-receipt.json"
        if sha256_file(provider_receipt_path) != receipt["provider_receipt_sha256"]:
            raise RuntimeError("provider receipt hash mismatch")
        provider = read_json(provider_receipt_path)
        provider_content = dict(provider)
        provider_claimed = provider_content.pop("receipt_hash", None)
        if (
            provider.get("status") != "PASS"
            or canonical_hash(provider_content) != provider_claimed
        ):
            raise RuntimeError("provider canonical receipt is invalid")
        provider_root = (root / str(provider["provider_path"])).resolve()
        provider_sha, provider_files = tree_identity(provider_root)
        if (
            provider_sha != provider["provider_tree_sha256"]
            or provider_files != provider["provider_files"]
        ):
            raise RuntimeError("provider tree hash mismatch")
        if receipt["id"] == FINAL_TEST_STRATEGY_ID:
            lock_path = run_root / "analysis-lock-receipt.json"
            validate_analysis_lock(read_json(lock_path))
            if sha256_file(lock_path) != receipt["analysis_lock_sha256"]:
                raise RuntimeError("final-test analysis lock identity differs")

        before = read_json(run_root / "paper-boundary-before.json")
        after = read_json(run_root / "paper-boundary-after.json")
        if before.get("tables") != after.get("tables") or after.get(
            "unchanged_from_baseline"
        ) is not True:
            raise RuntimeError("Top3 paper boundary was not preserved")
        audited.append(
            {
                "id": receipt["id"],
                "signal_rows": signal_receipt["support"]["rows"],
                "sessions": receipt["support"]["sessions"],
            }
        )
    print(
        json.dumps(
            {
                "status": "PASS",
                "tracks": audited,
                "paper_tables_unchanged": True,
                "catalog_receipt_hash": catalog["receipt_hash"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
