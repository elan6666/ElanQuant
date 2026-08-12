import hashlib
from pathlib import Path

import pandas as pd
import pytest

from scripts.server.build_extended_dataset import verify_raw_manifest
from scripts.server.evaluate_and_infer import (
    kronos_timestamp_series,
    materialize_evaluation_window,
    realized_mean_return,
    verify_manifest_files,
)
from scripts.server.fetch_online_snapshot import (
    execution_record,
    manifest_files_valid,
    strict_online_window,
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_consumers_fail_closed_when_manifest_file_is_tampered(tmp_path: Path) -> None:
    payload = tmp_path / "payload.bin"
    payload.write_bytes(b"sealed")
    manifest = {"files": {"payload.bin": {"sha256": digest(payload)}}}
    verify_manifest_files(tmp_path, manifest)

    payload.write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="hash mismatch"):
        verify_manifest_files(tmp_path, manifest)


def test_online_snapshot_reuse_requires_hashes_and_finalization_gate(tmp_path: Path) -> None:
    payload = tmp_path / "online_data.pkl"
    payload.write_bytes(b"sealed")
    manifest = {
        "generated_after_market_finalization": True,
        "files": {"online_data.pkl": digest(payload)},
    }
    assert manifest_files_valid(tmp_path, manifest)
    payload.write_bytes(b"tampered")
    assert not manifest_files_valid(tmp_path, manifest)


def test_missing_outcome_uses_same_last_close_carry_for_every_model_track() -> None:
    history = pd.DataFrame({"close": [10.0]})
    future = pd.DataFrame(
        {"close": [11.0, 11.0, 11.0, 11.0], "observed": [True, True, False, False]}
    )
    realized, status = realized_mean_return(history, future)
    assert realized == pytest.approx(0.1)
    assert status == "MISSING_SESSION_LAST_CLOSE_CARRY"


def test_kronos_timestamps_match_pinned_official_series_contract() -> None:
    values = pd.date_range("2026-08-01", periods=3, freq="B")
    converted = kronos_timestamp_series(values)
    assert isinstance(converted, pd.Series)
    assert converted.dt.day.tolist() == [3, 4, 5]
    assert converted.name == "timestamps"


def test_evaluation_outcome_is_track_independent_under_corporate_action() -> None:
    index = pd.date_range("2025-01-01", periods=100, freq="B")
    frame = pd.DataFrame(
        {
            "open": [10.0] * 100,
            "high": [10.0] * 100,
            "low": [10.0] * 100,
            "close": [10.0] * 100,
            "vol": [100.0] * 100,
            "amt": [1000.0] * 100,
            "adj_factor": [1.0] * 90 + [0.5] * 10,
            "observed": [True] * 100,
        },
        index=index,
    )
    official = materialize_evaluation_window(frame, 0, strict_input=False)
    strict = materialize_evaluation_window(frame, 0, strict_input=True)
    official_realized, _ = realized_mean_return(official[2], official[3])
    strict_realized, _ = realized_mean_return(strict[2], strict[3])
    assert official_realized == strict_realized == pytest.approx(-0.5)
    assert float(official[0].iloc[-1]["close"]) == 10.0
    assert float(strict[0].iloc[-1]["close"]) == 10.0


def test_online_window_carries_suspension_from_past_and_never_backfills_future() -> None:
    required = pd.date_range("2026-08-10", periods=3, freq="D")
    daily = pd.DataFrame(
        {
            "datetime": [required[0], required[2]],
            "open": [10.0, 12.0],
            "high": [10.5, 12.5],
            "low": [9.5, 11.5],
            "close": [10.0, 12.0],
            "vol": [100.0, 120.0],
            "amount": [1000.0, 1440.0],
        }
    )
    factors = pd.DataFrame(
        {"datetime": [required[0], required[2]], "adj_factor": [1.0, 1.0]}
    )
    window = strict_online_window(daily, factors, required)
    assert window.loc[required[1], "close"] == 10.0
    assert window.loc[required[1], "vol"] == 0.0
    assert not bool(window.loc[required[1], "observed"])

    future_only = strict_online_window(daily.iloc[1:], factors.iloc[1:], required)
    assert pd.isna(future_only.loc[required[0], "close"])

    prior_daily = pd.concat(
        [
            daily.iloc[1:],
            pd.DataFrame(
                [
                    {
                        "datetime": pd.Timestamp("2026-08-09"),
                        "open": 9.0,
                        "high": 9.0,
                        "low": 9.0,
                        "close": 9.0,
                        "vol": 90.0,
                        "amount": 810.0,
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    prior_factors = pd.concat(
        [
            factors.iloc[1:],
            pd.DataFrame([{"datetime": pd.Timestamp("2026-08-09"), "adj_factor": 1.0}]),
        ],
        ignore_index=True,
    )
    from_prior = strict_online_window(prior_daily, prior_factors, required)
    assert from_prior.loc[required[0], "close"] == 9.0
    assert not bool(from_prior.loc[required[0], "observed"])

    record = execution_record(
        "000001.SZ", "Example", from_prior.loc[required[0]], suspended_codes=set()
    )
    assert record["suspended"] is True
    assert record["observed"] is False


def test_raw_manifest_is_closed_world_and_binds_csv_semantics(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    daily = raw / "daily" / "000001.SZ.csv"
    daily.parent.mkdir(parents=True)
    daily.write_text(
        "ts_code,trade_date,close\n000001.SZ,20260102,10\n", encoding="utf-8"
    )
    manifest = {
        "requested_end": "20261231",
        "files": {
            "daily/000001.SZ": {
                "path": daily.as_posix(),
                "endpoint": "daily",
                "params": {
                    "ts_code": "000001.SZ",
                    "start_date": "20260101",
                    "end_date": "20261231",
                },
                "rows": 1,
                "sha256": digest(daily),
            }
        },
    }
    verify_raw_manifest(raw, manifest)

    extra = raw / "daily" / "UNLISTED.csv"
    extra.write_text("ts_code,trade_date\nUNLISTED,20260102\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="not closed-world"):
        verify_raw_manifest(raw, manifest)
    extra.unlink()

    manifest["files"]["daily/000001.SZ"]["params"]["ts_code"] = "OTHER"
    with pytest.raises(RuntimeError, match="symbol/path mismatch"):
        verify_raw_manifest(raw, manifest)
