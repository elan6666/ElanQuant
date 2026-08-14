from __future__ import annotations

import argparse
import json
from contextlib import nullcontext
from pathlib import Path

import pandas as pd
import pytest
from elanquant.repro import infer
from elanquant.repro.cli import main


def write_context(path: Path, *, instruments: tuple[str, ...] = ("SYNTH_A",)) -> None:
    rows: list[dict[str, object]] = []
    for instrument in instruments:
        for index, timestamp in enumerate(pd.bdate_range("2024-01-02", periods=90)):
            close = 100 + index / 10
            rows.append(
                {
                    "instrument": instrument,
                    "timestamp": timestamp,
                    "open": close - 0.2,
                    "high": close + 0.5,
                    "low": close - 0.5,
                    "close": close,
                    "volume": 1_000 + index,
                    "amount": (1_000 + index) * close,
                }
            )
    pd.DataFrame(rows).to_csv(path, index=False)


def write_future(path: Path) -> None:
    pd.DataFrame(
        {"session": pd.bdate_range("2024-05-07", periods=10)}
    ).to_csv(path, index=False)


def args(tmp_path: Path) -> argparse.Namespace:
    source = tmp_path / "context.csv"
    future = tmp_path / "future.csv"
    write_context(source)
    write_future(future)
    return argparse.Namespace(
        input=source,
        instrument="SYNTH_A",
        future_sessions=future,
        weights_root=tmp_path / "weights",
        upstream=tmp_path / "Kronos",
        release="small",
        device="cpu",
        lookback=90,
        output=tmp_path / "forecast.csv",
        dry_run=False,
    )


def test_zero_shot_dry_run_is_structured_and_does_not_touch_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "forecast.csv"
    assert (
        main(
            [
                "infer",
                "zero-shot",
                "--input",
                str(tmp_path / "missing.csv"),
                "--future-sessions",
                str(tmp_path / "future.csv"),
                "--device",
                "cpu",
                "--output",
                str(output),
                "--dry-run",
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    assert plan["scope"] == "SINGLE_INSTRUMENT_OFFICIAL_WEIGHT_FORECAST_NOT_A_BACKTEST"
    assert plan["prediction_sessions"] == 10
    assert len(plan["plan_hash"]) == 64
    assert not output.exists()


def test_zero_shot_requires_explicit_instrument_for_multi_symbol_input(tmp_path: Path) -> None:
    source = tmp_path / "context.csv"
    write_context(source, instruments=("SYNTH_A", "SYNTH_B"))
    with pytest.raises(ValueError, match="--instrument"):
        infer._read_frame(source, None, 90)


def test_zero_shot_matches_upstream_amount_fallback(tmp_path: Path) -> None:
    source = tmp_path / "context.csv"
    write_context(source)
    frame = pd.read_csv(source).drop(columns="amount")
    frame.to_csv(source, index=False)

    normalized, _ = infer._read_frame(source, "SYNTH_A", 90)

    expected = normalized["volume"] * normalized[["open", "high", "low", "close"]].mean(
        axis=1
    )
    pd.testing.assert_series_equal(normalized["amount"], expected, check_names=False)


def test_zero_shot_runs_pinned_runtime_and_seals_formula(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    command = args(tmp_path)

    class FakeArtifact:
        def eval(self):  # type: ignore[no-untyped-def]
            return self

    class FakeModel:
        @classmethod
        def from_pretrained(cls, path):  # type: ignore[no-untyped-def]
            assert Path(path).name in {"Kronos-Tokenizer-base", "Kronos-small"}
            return FakeArtifact()

    class FakePredictor:
        def __init__(self, model, tokenizer, **kwargs):  # type: ignore[no-untyped-def]
            assert kwargs["device"] == "cpu"

        def predict(self, frame, timestamps, future, **kwargs):  # type: ignore[no-untyped-def]
            assert len(frame) == len(timestamps) == 90
            assert kwargs["sample_count"] == 5
            return pd.DataFrame(
                {
                    "open": [112.0] * 10,
                    "high": [113.0] * 10,
                    "low": [111.0] * 10,
                    "close": [112.0] * 10,
                    "volume": [1_000.0] * 10,
                    "amount": [112_000.0] * 10,
                },
                index=future,
            )

    class FakeTorch:
        @staticmethod
        def manual_seed(seed: int) -> None:
            assert seed == 100

        @staticmethod
        def inference_mode():  # type: ignore[no-untyped-def]
            return nullcontext()

    monkeypatch.setattr(infer, "_upstream_head", lambda _: infer.UPSTREAM_COMMIT)
    monkeypatch.setattr(
        infer,
        "verify_weights",
        lambda *_: {"receipt_hash": "a" * 64},
    )
    monkeypatch.setattr(
        infer,
        "_runtime",
        lambda _: (FakeTorch(), FakeModel, FakeModel, FakePredictor),
    )
    receipt = infer.run_zero_shot_inference(command)
    assert receipt["status"] == "PASS"
    assert receipt["forecast_return_formula"] == (
        "mean(next_10_predicted_closes) / current_close - 1"
    )
    assert receipt["scope"] == "SINGLE_INSTRUMENT_FORECAST_NOT_A_BACKTEST_OR_RECOMMENDATION"
    assert command.output.is_file()
    assert command.output.with_suffix(".csv.receipt.json").is_file()
