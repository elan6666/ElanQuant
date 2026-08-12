from dataclasses import replace
from datetime import date

import pytest

from scripts.research.contracts import (
    ContractError,
    ExecutionQuote,
    ExperimentCell,
    ExperimentRegime,
    ExperimentStatus,
    FillStatus,
    OrderSide,
    build_experiment_matrix_receipt,
    execute_frozen_plan,
    freeze_equal_weight_order_plan,
    paper_signal_from_inverse_closes,
)

HASH = "a" * 64
COMMIT = "b" * 40


def test_paper_signal_uses_inverse_transformed_predicted_closes() -> None:
    receipt = paper_signal_from_inverse_closes(
        10.0,
        (
            tuple(11.0 for _ in range(10)),
            tuple(12.0 for _ in range(10)),
        ),
    )
    assert receipt.source_space == "PRICE_INVERSE_TRANSFORMED"
    assert receipt.mean_predicted_close == pytest.approx(11.5)
    assert receipt.signal == pytest.approx(0.15)


def test_order_plan_is_frozen_from_t_prices_and_uses_board_lots() -> None:
    plan = freeze_equal_weight_order_plan(
        signal_date=date(2026, 1, 2),
        trade_date=date(2026, 1, 5),
        ranked_codes=("000001.SZ", "600000.SH", "000002.SZ", "000003.SZ"),
        t_known_prices={
            "000001.SZ": 10.0,
            "600000.SH": 20.0,
            "000002.SZ": 25.0,
            "000003.SZ": 5.0,
        },
        opening_cash=100_000.0,
        opening_holdings={},
        top_k=3,
    )
    assert plan.selected_codes == ("000001.SZ", "600000.SH", "000002.SZ")
    assert "000003.SZ" not in {intent.ts_code for intent in plan.intents}
    assert all(intent.quantity % 100 == 0 for intent in plan.intents)
    assert all(intent.side is OrderSide.BUY for intent in plan.intents)


def test_t_plus_one_limit_rejects_without_replacement() -> None:
    signal_date, trade_date = date(2026, 1, 2), date(2026, 1, 5)
    plan = freeze_equal_weight_order_plan(
        signal_date=signal_date,
        trade_date=trade_date,
        ranked_codes=("000001.SZ", "600000.SH", "000002.SZ", "000003.SZ"),
        t_known_prices={
            "000001.SZ": 10.0,
            "600000.SH": 10.0,
            "000002.SZ": 10.0,
            "000003.SZ": 10.0,
        },
        opening_cash=100_000.0,
        opening_holdings={},
    )
    result = execute_frozen_plan(
        plan,
        quotes={
            "000001.SZ": ExecutionQuote(trade_date, "000001.SZ", 10.0, at_up_limit=True),
            "600000.SH": ExecutionQuote(trade_date, "600000.SH", 10.0),
            "000002.SZ": ExecutionQuote(trade_date, "000002.SZ", 10.0),
            "000003.SZ": ExecutionQuote(trade_date, "000003.SZ", 1.0),
        },
        opening_cash=100_000.0,
        opening_holdings={},
    )
    rejected = [record for record in result.records if record.status is FillStatus.REJECTED]
    assert len(rejected) == 1
    assert rejected[0].ts_code == "000001.SZ"
    assert rejected[0].reject_reason == "LIMIT_UP"
    assert "000003.SZ" not in result.closing_holdings
    assert set(result.closing_holdings) == {"600000.SH", "000002.SZ"}


def test_failed_sell_carries_position_and_can_force_buy_cash_rejection() -> None:
    signal_date, trade_date = date(2026, 1, 2), date(2026, 1, 5)
    plan = freeze_equal_weight_order_plan(
        signal_date=signal_date,
        trade_date=trade_date,
        ranked_codes=("000001.SZ",),
        t_known_prices={"000001.SZ": 10.0, "600000.SH": 10.0},
        opening_cash=0.0,
        opening_holdings={"600000.SH": 1000},
        top_k=1,
    )
    result = execute_frozen_plan(
        plan,
        quotes={
            "000001.SZ": ExecutionQuote(trade_date, "000001.SZ", 10.0),
            "600000.SH": ExecutionQuote(trade_date, "600000.SH", 10.0, at_down_limit=True),
        },
        opening_cash=0.0,
        opening_holdings={"600000.SH": 1000},
    )
    reasons = {record.ts_code: record.reject_reason for record in result.records}
    assert reasons == {"600000.SH": "LIMIT_DOWN", "000001.SZ": "INSUFFICIENT_CASH"}
    assert result.closing_holdings == {"600000.SH": 1000}
    assert result.closing_cash == 0.0


def test_execution_rejects_state_that_differs_from_frozen_t_plan() -> None:
    signal_date, trade_date = date(2026, 1, 2), date(2026, 1, 5)
    plan = freeze_equal_weight_order_plan(
        signal_date=signal_date,
        trade_date=trade_date,
        ranked_codes=("000001.SZ",),
        t_known_prices={"000001.SZ": 10.0},
        opening_cash=100_000.0,
        opening_holdings={},
    )
    with pytest.raises(ContractError, match="cash differs"):
        execute_frozen_plan(
            plan,
            quotes={"000001.SZ": ExecutionQuote(trade_date, "000001.SZ", 10.0)},
            opening_cash=99_999.0,
            opening_holdings={},
        )


def _matrix_cells(status: ExperimentStatus = ExperimentStatus.PASS) -> tuple[ExperimentCell, ...]:
    return tuple(
        ExperimentCell(
            experiment_id=f"{size}-{regime.value.lower()}",
            model_size=size,
            regime=regime,
            status=status,
            upstream_commit=COMMIT,
            data_receipt_hash=HASH,
            split_receipt_hash=HASH,
            config_hash=HASH,
            tokenizer_id="NeoQuasar/Kronos-Tokenizer-base",
            predictor_id=f"NeoQuasar/Kronos-{size}",
            seed=100,
            trained_components=(
                ()
                if regime is ExperimentRegime.ZERO_SHOT
                else (("tokenizer", "predictor") if size == "small" else ("predictor",))
            ),
            strict_pit=regime is ExperimentRegime.STRICT_PIT,
        )
        for size in ("small",)
        for regime in ExperimentRegime
    )


def test_small_three_cell_matrix_requires_common_receipts_and_can_be_terminal() -> None:
    receipt = build_experiment_matrix_receipt(_matrix_cells(), require_terminal=True)
    assert len(receipt.cells) == 3
    assert receipt.terminal is True

    drifted = list(_matrix_cells())
    drifted[-1] = replace(drifted[-1], data_receipt_hash="c" * 64)
    with pytest.raises(ContractError, match="extended dataset"):
        build_experiment_matrix_receipt(drifted)


def test_zero_shot_cell_cannot_claim_trained_components() -> None:
    cell = next(row for row in _matrix_cells() if row.regime is ExperimentRegime.ZERO_SHOT)
    with pytest.raises(ContractError, match="zero-shot"):
        replace(cell, trained_components=("predictor",)).validate()
