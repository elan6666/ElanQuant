from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from elanquant.repro.data import normalize_market_file


def frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "instrument": "000001.SZ",
                "timestamp": "2024-01-02",
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.5,
                "volume": 100.0,
                "amount": 1000.0,
            },
            {
                "instrument": "000001.SZ",
                "timestamp": "2024-01-03",
                "open": 10.5,
                "high": 11.5,
                "low": 10.0,
                "close": 11.0,
                "volume": 120.0,
                "amount": 1300.0,
            },
        ]
    )


def import_file(source: Path, output: Path) -> dict[str, object]:
    return normalize_market_file(
        source,
        output,
        timezone="Asia/Shanghai",
        calendar="SSE_SZSE_DAILY",
        universe_policy="USER_DECLARED",
        pit_declaration="USER_ASSERTS_POINT_IN_TIME",
        source_license="USER_OWNED",
    )


def test_csv_and_parquet_have_same_canonical_identity(tmp_path: Path) -> None:
    csv = tmp_path / "input.csv"
    parquet = tmp_path / "input.parquet"
    frame().to_csv(csv, index=False)
    try:
        frame().to_parquet(parquet, index=False)
    except ImportError:
        pytest.skip("pyarrow is not installed")
    csv_receipt = import_file(csv, tmp_path / "canonical.csv")
    parquet_receipt = import_file(parquet, tmp_path / "canonical.parquet")
    assert csv_receipt["canonical_data_sha256"] == parquet_receipt["canonical_data_sha256"]
    stored = json.loads((tmp_path / "canonical.csv.receipt.json").read_text())
    assert stored["credential_in_artifact"] is False
    assert "input.csv" not in json.dumps(stored)


def test_import_rejects_duplicate_and_invalid_ohlc(tmp_path: Path) -> None:
    duplicated = pd.concat([frame(), frame().iloc[[0]]], ignore_index=True)
    source = tmp_path / "duplicate.csv"
    duplicated.to_csv(source, index=False)
    with pytest.raises(ValueError, match="duplicate"):
        import_file(source, tmp_path / "out.csv")
    invalid = frame()
    invalid.loc[0, "high"] = 8.0
    invalid.to_csv(source, index=False)
    with pytest.raises(ValueError, match="OHLC"):
        import_file(source, tmp_path / "out.csv")
