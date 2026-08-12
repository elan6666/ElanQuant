from __future__ import annotations

import json
import math
import sqlite3
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any, TypedDict

ACCOUNT_ID = "paper-default"
BOARD_LOT = 100
COMMISSION_RATE = 0.0003
MINIMUM_COMMISSION = 5.0
SELL_STAMP_TAX_RATE = 0.0005


class Recommendation(TypedDict):
    code: str
    name: str
    score: float
    reference_price: float
    rank: int


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def next_weekday(session: str) -> str:
    candidate = date.fromisoformat(session) + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate.isoformat()


def ensure_account(connection: sqlite3.Connection, initial_cash: float) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO paper_accounts(id, name, initial_cash, cash, created_at)
        VALUES (?, 'ElanQuant simulated account', ?, ?, ?)
        """,
        (ACCOUNT_ID, initial_cash, initial_cash, utc_now()),
    )


def settle_due_orders(
    connection: sqlite3.Connection,
    as_of_session: str,
    execution_prices: dict[str, float],
    execution_constraints: dict[str, dict[str, Any]] | None = None,
) -> None:
    now = utc_now()
    connection.execute(
        """
        UPDATE paper_positions SET available_quantity = quantity
        WHERE account_id = ? AND last_buy_session IS NOT NULL AND last_buy_session < ?
        """,
        (ACCOUNT_ID, as_of_session),
    )
    orders = connection.execute(
        """
        SELECT * FROM paper_orders
        WHERE account_id = ? AND status = 'PENDING' AND due_session <= ?
        ORDER BY CASE side WHEN 'SELL' THEN 0 ELSE 1 END, created_at, id
        """,
        (ACCOUNT_ID, as_of_session),
    ).fetchall()
    for order in orders:
        if order["due_session"] != as_of_session:
            _reject(connection, order["id"], as_of_session, "MISSED_EXECUTION_SESSION", now)
            continue
        price = execution_prices.get(order["code"])
        if price is None or not math.isfinite(price) or price <= 0:
            _reject(connection, order["id"], as_of_session, "MISSING_EXECUTION_PRICE", now)
            continue
        constraints = (execution_constraints or {}).get(str(order["code"]), {})
        if bool(constraints.get("suspended")):
            _reject(connection, order["id"], as_of_session, "SUSPENDED", now)
            continue
        if order["side"] == "BUY" and bool(constraints.get("buy_restricted")):
            _reject(connection, order["id"], as_of_session, "BUY_RESTRICTED", now)
            continue
        up_limit = constraints.get("up_limit")
        down_limit = constraints.get("down_limit")
        if order["side"] == "BUY" and up_limit is not None and price >= up_limit - 1e-8:
            _reject(connection, order["id"], as_of_session, "BUY_LIMIT_UP", now)
            continue
        if order["side"] == "SELL" and down_limit is not None and price <= down_limit + 1e-8:
            _reject(connection, order["id"], as_of_session, "SELL_LIMIT_DOWN", now)
            continue
        quantity = int(order["quantity"])
        gross = round(price * quantity, 2)
        commission = round(max(gross * COMMISSION_RATE, MINIMUM_COMMISSION), 2)
        account = connection.execute(
            "SELECT cash FROM paper_accounts WHERE id = ?", (ACCOUNT_ID,)
        ).fetchone()
        position = connection.execute(
            "SELECT * FROM paper_positions WHERE account_id = ? AND code = ?",
            (ACCOUNT_ID, order["code"]),
        ).fetchone()
        if order["side"] == "BUY":
            total = gross + commission
            if account is None or float(account["cash"]) + 1e-9 < total:
                _reject(connection, order["id"], as_of_session, "INSUFFICIENT_CASH", now)
                continue
            old_quantity = 0 if position is None else int(position["quantity"])
            old_available = 0 if position is None else int(position["available_quantity"])
            old_cost = 0 if position is None else float(position["average_cost"])
            new_quantity = old_quantity + quantity
            average_cost = (old_quantity * old_cost + gross + commission) / new_quantity
            connection.execute(
                "UPDATE paper_accounts SET cash = cash - ? WHERE id = ?", (total, ACCOUNT_ID)
            )
            connection.execute(
                """
                INSERT INTO paper_positions(
                    account_id, code, name, quantity, available_quantity,
                    average_cost, last_buy_session, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id, code) DO UPDATE SET
                    name = excluded.name, quantity = excluded.quantity,
                    available_quantity = excluded.available_quantity,
                    average_cost = excluded.average_cost,
                    last_buy_session = excluded.last_buy_session,
                    updated_at = excluded.updated_at
                """,
                (
                    ACCOUNT_ID,
                    order["code"],
                    order["name"],
                    new_quantity,
                    old_available,
                    average_cost,
                    as_of_session,
                    now,
                ),
            )
            stamp_tax = 0.0
        else:
            if position is None or int(position["available_quantity"]) < quantity:
                _reject(connection, order["id"], as_of_session, "INSUFFICIENT_POSITION", now)
                continue
            stamp_tax = round(gross * SELL_STAMP_TAX_RATE, 2)
            connection.execute(
                "UPDATE paper_accounts SET cash = cash + ? WHERE id = ?",
                (gross - commission - stamp_tax, ACCOUNT_ID),
            )
            remaining = int(position["quantity"]) - quantity
            if remaining == 0:
                connection.execute(
                    "DELETE FROM paper_positions WHERE account_id = ? AND code = ?",
                    (ACCOUNT_ID, order["code"]),
                )
            else:
                connection.execute(
                    """
                    UPDATE paper_positions SET quantity = ?,
                        available_quantity = available_quantity - ?, updated_at = ?
                    WHERE account_id = ? AND code = ?
                    """,
                    (remaining, quantity, now, ACCOUNT_ID, order["code"]),
                )
        connection.execute(
            """
            INSERT INTO paper_fills(
                id, order_id, execution_session, price, quantity, gross_amount,
                commission, stamp_tax, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                order["id"],
                as_of_session,
                price,
                quantity,
                gross,
                commission,
                stamp_tax,
                now,
            ),
        )
        connection.execute(
            """
            UPDATE paper_orders SET status = 'FILLED', execution_session = ?, updated_at = ?
            WHERE id = ?
            """,
            (as_of_session, now, order["id"]),
        )


def create_frozen_intents(
    connection: sqlite3.Connection,
    run_id: str,
    signal_session: str,
    recommendations: list[Recommendation],
    top_k: int,
    due_session: str | None = None,
) -> None:
    now = utc_now()
    account = connection.execute(
        "SELECT cash FROM paper_accounts WHERE id = ?", (ACCOUNT_ID,)
    ).fetchone()
    if account is None:
        raise RuntimeError("Paper account is missing")
    positions = {
        row["code"]: row
        for row in connection.execute(
            "SELECT * FROM paper_positions WHERE account_id = ?", (ACCOUNT_ID,)
        ).fetchall()
    }
    pending_codes = {
        row["code"]
        for row in connection.execute(
            "SELECT code FROM paper_orders WHERE account_id = ? AND status = 'PENDING'",
            (ACCOUNT_ID,),
        ).fetchall()
    }
    selected = {str(item["code"]): item for item in recommendations[:top_k]}
    due_session = due_session or next_weekday(signal_session)
    for code, position in positions.items():
        if code in selected or code in pending_codes:
            continue
        _insert_order(
            connection,
            run_id,
            signal_session,
            due_session,
            code,
            str(position["name"]),
            "SELL",
            int(position["quantity"]),
            float(position["average_cost"]),
            0,
            {"reason": "left_top_k", "selected_at": signal_session},
            now,
        )
    allocation = float(account["cash"]) / max(1, top_k)
    for item in recommendations[:top_k]:
        code = str(item["code"])
        if code in positions or code in pending_codes:
            continue
        frozen_price = float(item["reference_price"])
        quantity = int(allocation // (frozen_price * BOARD_LOT)) * BOARD_LOT
        if quantity <= 0:
            continue
        intent = {
            "signal_session": signal_session,
            "rank": int(item["rank"]),
            "score": float(item["score"]),
            "sizing_price": frozen_price,
            "sizing_cash": allocation,
            "known_through": signal_session,
        }
        _insert_order(
            connection,
            run_id,
            signal_session,
            due_session,
            code,
            str(item["name"]),
            "BUY",
            quantity,
            frozen_price,
            1 / max(1, top_k),
            intent,
            now,
        )


def write_portfolio_snapshot(
    connection: sqlite3.Connection,
    as_of_session: str,
    prices: dict[str, float],
    valuation_policy: str = "PLACEHOLDER_CLOSE_OR_BOOK_COST",
) -> None:
    account = connection.execute(
        "SELECT cash, initial_cash FROM paper_accounts WHERE id = ?", (ACCOUNT_ID,)
    ).fetchone()
    if account is None:
        raise RuntimeError("Paper account is missing")
    market_value = 0.0
    valuations: list[tuple[object, ...]] = []
    for position in connection.execute(
        "SELECT * FROM paper_positions WHERE account_id = ?", (ACCOUNT_ID,)
    ).fetchall():
        average_cost = float(position["average_cost"])
        candidate = prices.get(str(position["code"]))
        price = average_cost
        has_market_price = False
        if candidate is not None and math.isfinite(candidate) and candidate > 0:
            price = candidate
            has_market_price = True
        quantity = int(position["quantity"])
        position_value = quantity * price
        market_value += position_value
        valuations.append(
            (
                ACCOUNT_ID,
                as_of_session,
                str(position["code"]),
                str(position["name"]),
                quantity,
                average_cost,
                price,
                "MARKET_CLOSE" if has_market_price else "AVERAGE_COST_FALLBACK",
                position_value,
                quantity * (price - average_cost),
            )
        )
    cash = float(account["cash"])
    connection.execute(
        """
        INSERT INTO portfolio_snapshots(
            id, account_id, as_of_session, cash, market_value, nav,
            valuation_policy, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(account_id, as_of_session) DO UPDATE SET
            cash = excluded.cash, market_value = excluded.market_value,
            nav = excluded.nav, valuation_policy = excluded.valuation_policy,
            created_at = excluded.created_at
        """,
        (
            str(uuid.uuid4()),
            ACCOUNT_ID,
            as_of_session,
            cash,
            market_value,
            (cash + market_value) / float(account["initial_cash"]),
            valuation_policy,
            utc_now(),
        ),
    )
    snapshot = connection.execute(
        "SELECT id FROM portfolio_snapshots WHERE account_id = ? AND as_of_session = ?",
        (ACCOUNT_ID, as_of_session),
    ).fetchone()
    if snapshot is None:
        raise RuntimeError("Portfolio snapshot publication failed")
    snapshot_id = str(snapshot["id"])
    connection.execute(
        "DELETE FROM portfolio_position_valuations WHERE snapshot_id = ?", (snapshot_id,)
    )
    connection.executemany(
        """
        INSERT INTO portfolio_position_valuations(
            snapshot_id, account_id, as_of_session, code, name, quantity,
            average_cost, valuation_price, valuation_source, market_value,
            unrealized_pnl
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [(snapshot_id, *valuation) for valuation in valuations],
    )


def _insert_order(
    connection: sqlite3.Connection,
    run_id: str,
    signal_session: str,
    due_session: str,
    code: str,
    name: str,
    side: str,
    quantity: int,
    sizing_price: float,
    target_weight: float,
    intent: dict[str, object],
    now: str,
) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO paper_orders(
            id, account_id, run_id, signal_session, due_session, code, name, side,
            quantity, sizing_price, target_weight, status, frozen_intent_json,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            ACCOUNT_ID,
            run_id,
            signal_session,
            due_session,
            code,
            name,
            side,
            quantity,
            sizing_price,
            target_weight,
            json.dumps(intent, sort_keys=True, separators=(",", ":")),
            now,
            now,
        ),
    )


def _reject(
    connection: sqlite3.Connection,
    order_id: str,
    execution_session: str,
    reason: str,
    now: str,
) -> None:
    connection.execute(
        """
        UPDATE paper_orders SET status = 'REJECTED', execution_session = ?,
            reject_reason = ?, updated_at = ? WHERE id = ?
        """,
        (execution_session, reason, now, order_id),
    )
