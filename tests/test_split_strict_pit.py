from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from scripts.research.contracts import (
    ContractError,
    SamplePartition,
    assert_future_perturbation_invariant,
    build_strict_pit_split,
    rows_asof_hash,
)
from scripts.server.build_extended_dataset import strict_session_frame
from scripts.server.fetch_online_snapshot import latest_finalized_date


def _weekdays(start: date, end: date) -> tuple[date, ...]:
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return tuple(days)


def test_90_10_split_is_target_bounded_and_latest_online_is_unscored() -> None:
    calendar = _weekdays(date(2011, 1, 1), date(2026, 2, 27))
    receipt = build_strict_pit_split(
        calendar,
        latest_closed_session=calendar[-1],
    )

    by_partition = {
        partition: tuple(row for row in receipt.windows if row.partition is partition)
        for partition in SamplePartition
    }
    train = by_partition[SamplePartition.TRAIN]
    validation = by_partition[SamplePartition.VALIDATION]
    viewed = by_partition[SamplePartition.TEST_VIEWED]

    assert train[-1].target_end.year == 2024
    assert validation[0].anchor_date.year == 2025
    assert validation[-1].target_end.year == 2025
    assert viewed[0].anchor_date.year == 2026
    assert receipt.latest_scoreable_anchor == calendar[-11]
    assert receipt.latest_online_anchor == calendar[-1]
    assert receipt.online_latest_is_unscored is True
    assert receipt.receipt_hash

    positions = {day: index for index, day in enumerate(calendar)}
    for sample in receipt.windows:
        assert positions[sample.input_end] - positions[sample.input_start] + 1 == 90
        assert positions[sample.target_end] - positions[sample.target_start] + 1 == 10
        assert positions[sample.target_start] == positions[sample.anchor_date] + 1
        assert positions[sample.consumed_end] == positions[sample.target_end] + 1
        assert sample.training_window_rows == 101


def test_boundary_crossing_anchors_are_purged_for_full_ten_session_target() -> None:
    calendar = _weekdays(date(2024, 1, 1), date(2026, 2, 27))
    receipt = build_strict_pit_split(
        calendar,
        raw_start=calendar[0],
        latest_closed_session=calendar[-1],
    )
    positions = {day: index for index, day in enumerate(calendar)}
    first_2025 = next(day for day in calendar if day.year == 2025)
    first_2026 = next(day for day in calendar if day.year == 2026)
    train_last = next(
        summary.last_anchor
        for summary in receipt.summaries
        if summary.partition is SamplePartition.TRAIN
    )
    validation_last = next(
        summary.last_anchor
        for summary in receipt.summaries
        if summary.partition is SamplePartition.VALIDATION
    )
    assert train_last is not None and validation_last is not None
    assert positions[train_last] + 11 < positions[first_2025]
    assert positions[validation_last] + 11 < positions[first_2026]


def test_future_perturbation_does_not_change_asof_hash() -> None:
    cutoff = datetime(2025, 1, 2, 18, tzinfo=UTC)
    past = {
        "ts_code": "000001.SZ",
        "close": 10.0,
        "availability_time": "2025-01-02T17:00:00+00:00",
    }
    future_a = {
        "ts_code": "000001.SZ",
        "close": 11.0,
        "availability_time": "2025-01-03T17:00:00+00:00",
    }
    future_b = {**future_a, "close": 999.0}

    expected = rows_asof_hash((past, future_a), cutoff)
    assert expected == rows_asof_hash((future_a, past), cutoff)
    assert (
        assert_future_perturbation_invariant((past, future_a), (past, future_b), cutoff) == expected
    )


def test_asof_hash_rejects_naive_availability_time() -> None:
    with pytest.raises(ContractError, match="timezone-aware"):
        rows_asof_hash(
            ({"availability_time": "2025-01-02T17:00:00"},),
            datetime(2025, 1, 2, 18, tzinfo=UTC),
        )


def test_future_missing_row_does_not_change_signal_day_history_eligibility() -> None:
    pd = pytest.importorskip("pandas")
    sessions = pd.date_range("2025-01-02", periods=101, freq="B")
    values = pd.DataFrame(
        {
            "open": 10.0,
            "high": 10.0,
            "low": 10.0,
            "close": 10.0,
            "vol": 100.0,
            "amt": 1000.0,
            "adj_factor": 1.0,
        },
        index=sessions,
    )
    signal = sessions[89]
    complete = strict_session_frame(values, sessions)
    perturbed = strict_session_frame(values.drop(index=sessions[95]), sessions)

    columns = ["open", "high", "low", "close", "vol", "amt", "adj_factor"]
    pd.testing.assert_frame_equal(complete.loc[:signal, columns], perturbed.loc[:signal, columns])
    assert len(complete.loc[:signal]) == len(perturbed.loc[:signal]) == 90
    assert not bool(perturbed.loc[sessions[95], "observed"])
    assert perturbed.loc[sessions[95], "vol"] == 0.0


def test_online_session_is_capped_by_market_finalization_and_today() -> None:
    market = ZoneInfo("Asia/Shanghai")
    before_cutoff = datetime(2026, 8, 13, 15, 30, tzinfo=market)
    after_cutoff = datetime(2026, 8, 13, 16, 30, tzinfo=market)
    assert latest_finalized_date(date(2026, 8, 13), before_cutoff) == date(2026, 8, 12)
    assert latest_finalized_date(date(2026, 8, 20), before_cutoff) == date(2026, 8, 12)
    assert latest_finalized_date(date(2026, 8, 20), after_cutoff) == date(2026, 8, 13)
    assert latest_finalized_date(date(2026, 8, 11), before_cutoff) == date(2026, 8, 11)
