"""Strict-PIT sample, signal, experiment, and paper-execution contracts.

The module intentionally uses only the Python standard library.  It is safe to
import in control-plane tests, while every data-producing caller remains a
server-only concern.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from enum import Enum, StrEnum
from typing import Any

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class ContractError(ValueError):
    """Raised when an auditable research invariant is violated."""


def _json_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    """Serialize contract content deterministically."""

    return json.dumps(
        _json_value(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class SamplePartition(StrEnum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    TEST_VIEWED = "TEST_VIEWED"


@dataclass(frozen=True)
class SampleWindow:
    partition: SamplePartition
    anchor_date: date
    input_start: date
    input_end: date
    target_start: date
    target_end: date
    consumed_end: date
    lookback_sessions: int
    predict_sessions: int
    training_window_rows: int

    def validate(self) -> None:
        if self.lookback_sessions <= 0 or self.predict_sessions <= 0:
            raise ContractError("sample lengths must be positive")
        if self.input_end != self.anchor_date:
            raise ContractError("sample input must end on its signal anchor")
        if not self.input_start <= self.input_end < self.target_start <= self.target_end:
            raise ContractError("sample dates are not strictly causal")
        if self.target_end >= self.consumed_end:
            raise ContractError("author loss-consumed row must follow the economic target")
        if self.training_window_rows != self.lookback_sessions + self.predict_sessions + 1:
            raise ContractError("author training window must include the shifted-loss row")


@dataclass(frozen=True)
class PartitionSummary:
    partition: SamplePartition
    count: int
    first_anchor: date | None
    last_anchor: date | None
    last_target: date | None


@dataclass(frozen=True)
class SampleSplitReceipt:
    protocol: str
    calendar_hash: str
    raw_start: date
    latest_closed_session: date
    lookback_sessions: int
    predict_sessions: int
    train_target_end: date
    validation_anchor_start: date
    validation_target_end: date
    test_viewed_anchor_start: date
    latest_scoreable_anchor: date
    latest_online_anchor: date
    online_latest_is_unscored: bool
    summaries: tuple[PartitionSummary, ...]
    windows: tuple[SampleWindow, ...]
    receipt_hash: str

    def content_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("receipt_hash")
        return payload

    def validate(self) -> None:
        if self.protocol != "strict_pit_v1":
            raise ContractError("unexpected split protocol")
        if not _SHA256.fullmatch(self.calendar_hash):
            raise ContractError("calendar hash must be SHA-256")
        if not self.online_latest_is_unscored:
            raise ContractError("latest online anchor must remain unscored")
        if self.latest_scoreable_anchor > self.latest_online_anchor:
            raise ContractError("scoreable anchor cannot follow the online anchor")
        expected = tuple(SamplePartition)
        if tuple(summary.partition for summary in self.summaries) != expected:
            raise ContractError("split summaries must contain each partition once")
        for window in self.windows:
            window.validate()
            if window.partition is SamplePartition.TRAIN:
                if window.consumed_end > self.train_target_end:
                    raise ContractError("training loss-consumed row crosses its boundary")
            elif window.partition is SamplePartition.VALIDATION:
                if window.anchor_date < self.validation_anchor_start:
                    raise ContractError("validation anchor precedes its boundary")
                if window.consumed_end > self.validation_target_end:
                    raise ContractError("validation loss-consumed row crosses its boundary")
            elif window.partition is SamplePartition.TEST_VIEWED:
                if window.anchor_date < self.test_viewed_anchor_start:
                    raise ContractError("test anchor precedes its boundary")
                if window.target_end > self.latest_closed_session:
                    raise ContractError("test target is not label-mature")
        if canonical_hash(self.content_without_hash()) != self.receipt_hash:
            raise ContractError("split receipt hash mismatch")


def _strict_calendar(
    trading_dates: Sequence[date], *, raw_start: date, latest_closed_session: date
) -> tuple[date, ...]:
    calendar = tuple(trading_dates)
    if calendar != tuple(sorted(set(calendar))):
        raise ContractError("trading calendar must be unique and increasing")
    bounded = tuple(day for day in calendar if raw_start <= day <= latest_closed_session)
    if not bounded or bounded[-1] != latest_closed_session:
        raise ContractError("latest closed session is absent from the bounded calendar")
    return bounded


def build_strict_pit_split(
    trading_dates: Sequence[date],
    *,
    raw_start: date = date(2011, 1, 1),
    latest_closed_session: date,
    train_target_end: date = date(2024, 12, 31),
    validation_anchor_start: date = date(2025, 1, 1),
    validation_target_end: date = date(2025, 12, 31),
    test_viewed_anchor_start: date = date(2026, 1, 1),
    lookback_sessions: int = 90,
    predict_sessions: int = 10,
) -> SampleSplitReceipt:
    """Build target-bounded samples and leave boundary-crossing anchors unused."""

    if lookback_sessions <= 0 or predict_sessions <= 0:
        raise ContractError("lookback and prediction horizon must be positive")
    if not (
        raw_start
        <= train_target_end
        < validation_anchor_start
        <= validation_target_end
        < test_viewed_anchor_start
        <= latest_closed_session
    ):
        raise ContractError("split boundaries are not strictly ordered")
    calendar = _strict_calendar(
        trading_dates, raw_start=raw_start, latest_closed_session=latest_closed_session
    )
    training_window_rows = lookback_sessions + predict_sessions + 1
    if len(calendar) < training_window_rows:
        raise ContractError("calendar is too short for one complete sample")

    windows: list[SampleWindow] = []
    for anchor_index in range(lookback_sessions - 1, len(calendar) - predict_sessions - 1):
        anchor = calendar[anchor_index]
        target_end = calendar[anchor_index + predict_sessions]
        consumed_end = calendar[anchor_index + predict_sessions + 1]
        partition: SamplePartition | None = None
        if consumed_end <= train_target_end:
            partition = SamplePartition.TRAIN
        elif anchor >= validation_anchor_start and consumed_end <= validation_target_end:
            partition = SamplePartition.VALIDATION
        elif anchor >= test_viewed_anchor_start:
            partition = SamplePartition.TEST_VIEWED
        if partition is None:
            continue
        windows.append(
            SampleWindow(
                partition=partition,
                anchor_date=anchor,
                input_start=calendar[anchor_index - lookback_sessions + 1],
                input_end=anchor,
                target_start=calendar[anchor_index + 1],
                target_end=target_end,
                consumed_end=consumed_end,
                lookback_sessions=lookback_sessions,
                predict_sessions=predict_sessions,
                training_window_rows=training_window_rows,
            )
        )

    summaries = tuple(
        PartitionSummary(
            partition=partition,
            count=len(partition_windows),
            first_anchor=partition_windows[0].anchor_date if partition_windows else None,
            last_anchor=partition_windows[-1].anchor_date if partition_windows else None,
            last_target=partition_windows[-1].target_end if partition_windows else None,
        )
        for partition in SamplePartition
        for partition_windows in [tuple(row for row in windows if row.partition is partition)]
    )
    if any(summary.count == 0 for summary in summaries):
        raise ContractError("each configured split must contain at least one mature sample")

    content = {
        "protocol": "strict_pit_v1",
        "calendar_hash": canonical_hash(calendar),
        "raw_start": raw_start,
        "latest_closed_session": latest_closed_session,
        "lookback_sessions": lookback_sessions,
        "predict_sessions": predict_sessions,
        "train_target_end": train_target_end,
        "validation_anchor_start": validation_anchor_start,
        "validation_target_end": validation_target_end,
        "test_viewed_anchor_start": test_viewed_anchor_start,
        "latest_scoreable_anchor": calendar[-predict_sessions - 1],
        "latest_online_anchor": calendar[-1],
        "online_latest_is_unscored": True,
        "summaries": summaries,
        "windows": tuple(windows),
    }
    receipt = SampleSplitReceipt(**content, receipt_hash=canonical_hash(content))
    receipt.validate()
    return receipt


def _aware_datetime(value: datetime | str) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError("availability timestamps must be timezone-aware")
    return parsed


def rows_asof_hash(
    rows: Iterable[Mapping[str, Any]],
    cutoff: datetime,
    *,
    availability_field: str = "availability_time",
) -> str:
    """Hash only rows available by cutoff, independent of input ordering."""

    cutoff = _aware_datetime(cutoff)
    included: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        if availability_field not in row:
            raise ContractError(f"row lacks {availability_field}")
        if _aware_datetime(row[availability_field]) <= cutoff:
            included.append(row)
    included.sort(key=canonical_json)
    return canonical_hash(included)


def assert_future_perturbation_invariant(
    original: Iterable[Mapping[str, Any]],
    perturbed: Iterable[Mapping[str, Any]],
    cutoff: datetime,
) -> str:
    original_hash = rows_asof_hash(original, cutoff)
    perturbed_hash = rows_asof_hash(perturbed, cutoff)
    if original_hash != perturbed_hash:
        raise ContractError("future perturbation changed causal content")
    return original_hash


@dataclass(frozen=True)
class PaperSignalReceipt:
    signal_formula: str
    source_space: str
    horizon: int
    path_count: int
    current_close: float
    mean_predicted_close: float
    signal: float
    receipt_hash: str


def paper_signal_from_inverse_closes(
    current_close: float,
    predicted_close_paths: Sequence[Sequence[float]],
    *,
    horizon: int = 10,
) -> PaperSignalReceipt:
    """Compute the paper signal from already inverse-transformed price paths."""

    if not math.isfinite(current_close) or current_close <= 0:
        raise ContractError("current close must be finite and positive")
    paths = tuple(tuple(path) for path in predicted_close_paths)
    if not paths or any(len(path) != horizon for path in paths):
        raise ContractError("every prediction path must match the configured horizon")
    values = tuple(value for path in paths for value in path)
    if any(not math.isfinite(value) or value <= 0 for value in values):
        raise ContractError("inverse-transformed predicted closes must be positive and finite")
    mean_close = sum(values) / len(values)
    signal = (mean_close - current_close) / current_close
    content = {
        "signal_formula": "(mean_inverse_predicted_close-current_close)/current_close",
        "source_space": "PRICE_INVERSE_TRANSFORMED",
        "horizon": horizon,
        "path_count": len(paths),
        "current_close": current_close,
        "mean_predicted_close": mean_close,
        "signal": signal,
    }
    return PaperSignalReceipt(**content, receipt_hash=canonical_hash(content))


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class OrderIntent:
    order_id: str
    signal_date: date
    trade_date: date
    ts_code: str
    side: OrderSide
    quantity: int
    rank: int | None
    t_known_price: float

    def validate(self, board_lot: int) -> None:
        if not self.ts_code or self.trade_date <= self.signal_date:
            raise ContractError("order identity or dates are invalid")
        if self.quantity <= 0 or self.quantity % board_lot:
            raise ContractError("order quantity must be a positive board-lot multiple")
        if not math.isfinite(self.t_known_price) or self.t_known_price <= 0:
            raise ContractError("T-known sizing price must be positive and finite")
        if self.side is OrderSide.BUY and (self.rank is None or self.rank <= 0):
            raise ContractError("buy order must retain its frozen signal rank")
        expected = canonical_hash(
            {
                "signal_date": self.signal_date,
                "trade_date": self.trade_date,
                "ts_code": self.ts_code,
                "side": self.side,
                "quantity": self.quantity,
                "rank": self.rank,
                "t_known_price": self.t_known_price,
            }
        )
        if self.order_id != expected:
            raise ContractError("order id does not match frozen content")


@dataclass(frozen=True)
class PlanningRejection:
    ts_code: str
    rank: int
    reason: str


@dataclass(frozen=True)
class OrderPlan:
    signal_date: date
    trade_date: date
    board_lot: int
    opening_cash: float
    opening_holdings: dict[str, int]
    t_known_prices: dict[str, float]
    selected_codes: tuple[str, ...]
    intents: tuple[OrderIntent, ...]
    planning_rejections: tuple[PlanningRejection, ...]
    plan_hash: str

    def content_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("plan_hash")
        return payload

    def validate(self) -> None:
        if self.board_lot != 100:
            raise ContractError("A-share paper orders require 100-share board lots")
        if not math.isfinite(self.opening_cash) or self.opening_cash < 0:
            raise ContractError("frozen opening cash must be finite and nonnegative")
        if any(
            type(quantity) is not int or quantity < 0 or quantity % self.board_lot
            for quantity in self.opening_holdings.values()
        ):
            raise ContractError("frozen holdings must use nonnegative board lots")
        if any(not math.isfinite(price) or price <= 0 for price in self.t_known_prices.values()):
            raise ContractError("frozen T-known prices must be positive and finite")
        if not self.selected_codes or len(set(self.selected_codes)) != len(self.selected_codes):
            raise ContractError("selected codes must be unique and non-empty")
        by_code: dict[str, set[OrderSide]] = {}
        for intent in self.intents:
            intent.validate(self.board_lot)
            if (intent.signal_date, intent.trade_date) != (self.signal_date, self.trade_date):
                raise ContractError("intent dates differ from the frozen plan")
            by_code.setdefault(intent.ts_code, set()).add(intent.side)
        if any(len(sides) > 1 for sides in by_code.values()):
            raise ContractError("one plan cannot buy and sell the same code")
        if canonical_hash(self.content_without_hash()) != self.plan_hash:
            raise ContractError("order plan hash mismatch")


def _intent(
    *,
    signal_date: date,
    trade_date: date,
    ts_code: str,
    side: OrderSide,
    quantity: int,
    rank: int | None,
    t_known_price: float,
) -> OrderIntent:
    content = {
        "signal_date": signal_date,
        "trade_date": trade_date,
        "ts_code": ts_code,
        "side": side,
        "quantity": quantity,
        "rank": rank,
        "t_known_price": t_known_price,
    }
    return OrderIntent(order_id=canonical_hash(content), **content)


def freeze_equal_weight_order_plan(
    *,
    signal_date: date,
    trade_date: date,
    ranked_codes: Sequence[str],
    t_known_prices: Mapping[str, float],
    opening_cash: float,
    opening_holdings: Mapping[str, int],
    top_k: int = 3,
    board_lot: int = 100,
) -> OrderPlan:
    """Freeze target orders using only T-known prices; no T+1 state is accepted."""

    if trade_date <= signal_date:
        raise ContractError("trade date must follow the signal date")
    if board_lot != 100 or top_k <= 0:
        raise ContractError("invalid Top-K or board-lot policy")
    if not math.isfinite(opening_cash) or opening_cash < 0:
        raise ContractError("opening cash must be finite and nonnegative")
    ranked = tuple(ranked_codes)
    if len(ranked) != len(set(ranked)):
        raise ContractError("ranked codes contain duplicates")
    selected = ranked[:top_k]
    if not selected:
        raise ContractError("ranked list cannot be empty")
    relevant = set(selected) | set(opening_holdings)
    missing_prices = sorted(code for code in relevant if code not in t_known_prices)
    if missing_prices:
        raise ContractError(f"T-known prices are missing for: {', '.join(missing_prices)}")
    for code in relevant:
        price = t_known_prices[code]
        if not math.isfinite(price) or price <= 0:
            raise ContractError("T-known prices must be finite and positive")
    for quantity in opening_holdings.values():
        if type(quantity) is not int or quantity < 0 or quantity % board_lot:
            raise ContractError("opening holdings must use nonnegative board lots")

    estimated_nav = opening_cash + sum(
        quantity * t_known_prices[code] for code, quantity in opening_holdings.items()
    )
    target_value = estimated_nav / len(selected)
    selected_rank = {code: rank for rank, code in enumerate(selected, start=1)}
    intents: list[OrderIntent] = []
    rejections: list[PlanningRejection] = []
    for code in sorted(relevant):
        current = opening_holdings.get(code, 0)
        desired = (
            math.floor(target_value / t_known_prices[code] / board_lot) * board_lot
            if code in selected_rank
            else 0
        )
        delta = desired - current
        if delta > 0:
            intents.append(
                _intent(
                    signal_date=signal_date,
                    trade_date=trade_date,
                    ts_code=code,
                    side=OrderSide.BUY,
                    quantity=delta,
                    rank=selected_rank[code],
                    t_known_price=t_known_prices[code],
                )
            )
        elif delta < 0:
            intents.append(
                _intent(
                    signal_date=signal_date,
                    trade_date=trade_date,
                    ts_code=code,
                    side=OrderSide.SELL,
                    quantity=-delta,
                    rank=selected_rank.get(code),
                    t_known_price=t_known_prices[code],
                )
            )
        elif desired == 0 and code in selected_rank and current == 0:
            rejections.append(
                PlanningRejection(code, selected_rank[code], "BELOW_ONE_BOARD_LOT")
            )
    content = {
        "signal_date": signal_date,
        "trade_date": trade_date,
        "board_lot": board_lot,
        "opening_cash": opening_cash,
        "opening_holdings": dict(sorted(opening_holdings.items())),
        "t_known_prices": {
            code: t_known_prices[code] for code in sorted(relevant)
        },
        "selected_codes": selected,
        "intents": tuple(intents),
        "planning_rejections": tuple(rejections),
    }
    plan = OrderPlan(**content, plan_hash=canonical_hash(content))
    plan.validate()
    return plan


@dataclass(frozen=True)
class ExecutionQuote:
    trade_date: date
    ts_code: str
    open_price: float | None
    suspended: bool = False
    at_up_limit: bool = False
    at_down_limit: bool = False
    buy_restricted: bool = False


class FillStatus(StrEnum):
    FILLED = "FILLED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ExecutionRecord:
    order_id: str
    ts_code: str
    side: OrderSide
    requested_quantity: int
    filled_quantity: int
    status: FillStatus
    price: float | None
    commission: float
    stamp_tax: float
    slippage: float
    reject_reason: str | None


@dataclass(frozen=True)
class ExecutionResult:
    plan_hash: str
    trade_date: date
    opening_cash: float
    closing_cash: float
    opening_holdings: dict[str, int]
    closing_holdings: dict[str, int]
    records: tuple[ExecutionRecord, ...]
    result_hash: str


def _reject(intent: OrderIntent, reason: str) -> ExecutionRecord:
    return ExecutionRecord(
        order_id=intent.order_id,
        ts_code=intent.ts_code,
        side=intent.side,
        requested_quantity=intent.quantity,
        filled_quantity=0,
        status=FillStatus.REJECTED,
        price=None,
        commission=0.0,
        stamp_tax=0.0,
        slippage=0.0,
        reject_reason=reason,
    )


def execute_frozen_plan(
    plan: OrderPlan,
    *,
    quotes: Mapping[str, ExecutionQuote],
    opening_cash: float,
    opening_holdings: Mapping[str, int],
    commission_rate: float = 0.0003,
    minimum_commission: float = 5.0,
    sell_stamp_tax_rate: float = 0.0005,
    slippage_rate: float = 0.0005,
) -> ExecutionResult:
    """Execute only frozen intents; failed orders remain cash/holdings, never replacements."""

    plan.validate()
    costs = (commission_rate, minimum_commission, sell_stamp_tax_rate, slippage_rate)
    if any(not math.isfinite(value) or value < 0 for value in costs):
        raise ContractError("execution costs must be finite and nonnegative")
    if not math.isfinite(opening_cash) or opening_cash < 0:
        raise ContractError("opening cash must be finite and nonnegative")
    if abs(opening_cash - plan.opening_cash) > 1e-9:
        raise ContractError("execution cash differs from the frozen T plan")
    if dict(sorted(opening_holdings.items())) != plan.opening_holdings:
        raise ContractError("execution holdings differ from the frozen T plan")
    holdings = dict(opening_holdings)
    if any(type(value) is not int or value < 0 for value in holdings.values()):
        raise ContractError("opening holdings must be nonnegative integers")
    cash = opening_cash
    records: list[ExecutionRecord] = []
    ordered = sorted(
        plan.intents,
        key=lambda intent: (
            0 if intent.side is OrderSide.SELL else 1,
            intent.rank if intent.rank is not None else 10**9,
            intent.ts_code,
        ),
    )
    for intent in ordered:
        quote = quotes.get(intent.ts_code)
        reason: str | None = None
        if quote is None:
            reason = "MISSING_QUOTE"
        elif quote.trade_date != plan.trade_date:
            reason = "WRONG_TRADE_DATE"
        elif quote.suspended:
            reason = "SUSPENDED"
        elif (
            quote.open_price is None
            or not math.isfinite(quote.open_price)
            or quote.open_price <= 0
        ):
            reason = "INVALID_OPEN"
        elif intent.side is OrderSide.BUY and quote.buy_restricted:
            reason = "BUY_RESTRICTED"
        elif intent.side is OrderSide.BUY and quote.at_up_limit:
            reason = "LIMIT_UP"
        elif intent.side is OrderSide.SELL and quote.at_down_limit:
            reason = "LIMIT_DOWN"
        if reason is not None:
            records.append(_reject(intent, reason))
            continue

        assert quote is not None and quote.open_price is not None
        gross = intent.quantity * quote.open_price
        commission = max(gross * commission_rate, minimum_commission)
        stamp_tax = gross * sell_stamp_tax_rate if intent.side is OrderSide.SELL else 0.0
        slippage = gross * slippage_rate
        if intent.side is OrderSide.SELL:
            if holdings.get(intent.ts_code, 0) < intent.quantity:
                records.append(_reject(intent, "INSUFFICIENT_POSITION"))
                continue
            holdings[intent.ts_code] -= intent.quantity
            if holdings[intent.ts_code] == 0:
                holdings.pop(intent.ts_code)
            cash += gross - commission - stamp_tax - slippage
        else:
            required_cash = gross + commission + slippage
            if required_cash > cash + 1e-9:
                records.append(_reject(intent, "INSUFFICIENT_CASH"))
                continue
            cash -= required_cash
            holdings[intent.ts_code] = holdings.get(intent.ts_code, 0) + intent.quantity
        records.append(
            ExecutionRecord(
                order_id=intent.order_id,
                ts_code=intent.ts_code,
                side=intent.side,
                requested_quantity=intent.quantity,
                filled_quantity=intent.quantity,
                status=FillStatus.FILLED,
                price=quote.open_price,
                commission=commission,
                stamp_tax=stamp_tax,
                slippage=slippage,
                reject_reason=None,
            )
        )
    content = {
        "plan_hash": plan.plan_hash,
        "trade_date": plan.trade_date,
        "opening_cash": opening_cash,
        "closing_cash": cash,
        "opening_holdings": dict(sorted(opening_holdings.items())),
        "closing_holdings": dict(sorted(holdings.items())),
        "records": tuple(records),
    }
    return ExecutionResult(**content, result_hash=canonical_hash(content))


class ExperimentRegime(StrEnum):
    ZERO_SHOT = "ZERO_SHOT"
    OFFICIAL_STYLE = "OFFICIAL_STYLE"
    STRICT_PIT = "STRICT_PIT"


class ExperimentStatus(StrEnum):
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    PASS = "PASS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ExperimentCell:
    experiment_id: str
    model_size: str
    regime: ExperimentRegime
    status: ExperimentStatus
    upstream_commit: str
    data_receipt_hash: str
    split_receipt_hash: str
    config_hash: str
    tokenizer_id: str
    predictor_id: str
    seed: int
    trained_components: tuple[str, ...]
    strict_pit: bool

    def validate(self) -> None:
        if self.model_size not in {"small", "base"}:
            raise ContractError("experiment model size must be small or base")
        if not self.experiment_id or not self.tokenizer_id or not self.predictor_id:
            raise ContractError("experiment identities are required")
        if not _GIT_COMMIT.fullmatch(self.upstream_commit):
            raise ContractError("upstream commit must be a full Git SHA")
        if any(
            not _SHA256.fullmatch(value)
            for value in (self.data_receipt_hash, self.split_receipt_hash, self.config_hash)
        ):
            raise ContractError("experiment receipt/config hashes must be SHA-256")
        if type(self.seed) is not int or self.seed < 0:
            raise ContractError("experiment seed must be a nonnegative integer")
        if len(set(self.trained_components)) != len(self.trained_components):
            raise ContractError("trained components contain duplicates")
        allowed_components = {"tokenizer", "predictor"}
        if not set(self.trained_components) <= allowed_components:
            raise ContractError("experiment has an unknown trained component")
        if self.regime is ExperimentRegime.ZERO_SHOT:
            if self.trained_components or self.strict_pit:
                raise ContractError("zero-shot cells cannot train or claim strict fitting")
        elif self.model_size == "small" and set(self.trained_components) != allowed_components:
            raise ContractError("fine-tuned Small cells must train tokenizer and predictor")
        elif self.model_size == "base" and self.trained_components != ("predictor",):
            raise ContractError("fine-tuned Base cells must reuse the shared Small tokenizer")
        if self.strict_pit is not (self.regime is ExperimentRegime.STRICT_PIT):
            raise ContractError("strict_pit flag disagrees with experiment regime")


@dataclass(frozen=True)
class ExperimentMatrixReceipt:
    schema_version: str
    cells: tuple[ExperimentCell, ...]
    shared_upstream_commit: str
    shared_data_receipt_hash: str
    shared_split_receipt_hash: str
    terminal: bool
    receipt_hash: str

    def content_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("receipt_hash")
        return payload

    def validate(self) -> None:
        for cell in self.cells:
            cell.validate()
        expected = {("small", regime) for regime in ExperimentRegime}
        actual = {(cell.model_size, cell.regime) for cell in self.cells}
        if len(self.cells) != 3 or actual != expected:
            raise ContractError("matrix must contain exactly three Small regime cells")
        if len({cell.experiment_id for cell in self.cells}) != 3:
            raise ContractError("experiment ids must be unique")
        if {cell.upstream_commit for cell in self.cells} != {self.shared_upstream_commit}:
            raise ContractError("matrix cells do not share the pinned upstream commit")
        if {cell.data_receipt_hash for cell in self.cells} != {self.shared_data_receipt_hash}:
            raise ContractError("matrix cells do not share the extended dataset receipt")
        if {cell.split_receipt_hash for cell in self.cells} != {self.shared_split_receipt_hash}:
            raise ContractError("matrix cells do not share the split receipt")
        terminal_statuses = {
            ExperimentStatus.PASS,
            ExperimentStatus.FAILED,
            ExperimentStatus.BLOCKED,
        }
        if self.terminal != all(cell.status in terminal_statuses for cell in self.cells):
            raise ContractError("matrix terminal flag disagrees with cell statuses")
        if canonical_hash(self.content_without_hash()) != self.receipt_hash:
            raise ContractError("matrix receipt hash mismatch")


def build_experiment_matrix_receipt(
    cells: Sequence[ExperimentCell], *, require_terminal: bool = False
) -> ExperimentMatrixReceipt:
    ordered = tuple(sorted(cells, key=lambda cell: (cell.model_size, cell.regime.value)))
    if not ordered:
        raise ContractError("experiment matrix cannot be empty")
    terminal_statuses = {
        ExperimentStatus.PASS,
        ExperimentStatus.FAILED,
        ExperimentStatus.BLOCKED,
    }
    terminal = all(cell.status in terminal_statuses for cell in ordered)
    if require_terminal and not terminal:
        raise ContractError("experiment matrix is not terminal")
    content = {
        "schema_version": "elanquant_experiment_matrix_v1",
        "cells": ordered,
        "shared_upstream_commit": ordered[0].upstream_commit,
        "shared_data_receipt_hash": ordered[0].data_receipt_hash,
        "shared_split_receipt_hash": ordered[0].split_receipt_hash,
        "terminal": terminal,
    }
    receipt = ExperimentMatrixReceipt(**content, receipt_hash=canonical_hash(content))
    receipt.validate()
    return receipt
