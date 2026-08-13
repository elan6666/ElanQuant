from __future__ import annotations

import pandas as pd

from scripts.server.generate_official_demo_signals import candidate_windows


def frame(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "vol": 1.0,
            "amt": 1.0,
        },
        index=index,
    )


def test_candidate_does_not_require_future_symbol_rows() -> None:
    calendar = pd.bdate_range("2025-09-01", periods=105)
    data = {
        "FULL": frame(calendar),
        # Has the full T-known 90-session context but disappears immediately
        # after T.  It must remain eligible at T.
        "EXIT": frame(calendar[:90]),
    }
    candidates = candidate_windows(data, calendar[89], calendar[-1])
    first_session = [item for item in candidates if item[1][-1] == calendar[89]]
    assert {item[0] for item in first_session} == {"EXIT", "FULL"}
    assert all(item[2] == tuple(calendar[90:100]) for item in first_session)


def test_candidate_requires_complete_prior_global_context() -> None:
    calendar = pd.bdate_range("2025-09-01", periods=105)
    missing_past = calendar.delete(50)
    data = {"FULL": frame(calendar), "GAP": frame(missing_past)}
    candidates = candidate_windows(data, calendar[89], calendar[99])
    first_session = [item for item in candidates if item[1][-1] == calendar[89]]
    assert {item[0] for item in first_session} == {"FULL"}
