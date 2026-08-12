import json
from pathlib import Path

from elanquant.orchestration.jobs import JobStore
from elanquant.orchestration.worker import Worker
from elanquant.pipelines.paper import ensure_account, settle_due_orders, write_portfolio_snapshot
from elanquant.settings import Settings
from elanquant.storage.database import Database


def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "elanquant.sqlite3",
        artifact_root=tmp_path / "runs",
        frontend_dist=tmp_path / "missing-dist",
        initial_cash=100_000,
        top_k=3,
    )


def run_session(active: Settings, session: str) -> None:
    database = Database(active.database_path)
    database.initialize()
    JobStore(database).submit_update_infer(session)
    assert Worker(active).run_once() is True


def test_intents_are_frozen_at_t_and_fill_only_on_due_session(tmp_path: Path) -> None:
    active = settings(tmp_path)
    run_session(active, "2026-08-12")
    database = Database(active.database_path)
    with database.connect() as connection:
        initial_orders = connection.execute("SELECT * FROM paper_orders ORDER BY code").fetchall()
    assert len(initial_orders) == 3
    assert {row["status"] for row in initial_orders} == {"PENDING"}
    assert {row["due_session"] for row in initial_orders} == {"2026-08-13"}
    for row in initial_orders:
        intent = json.loads(row["frozen_intent_json"])
        assert intent["known_through"] == "2026-08-12"
        assert row["sizing_price"] == intent["sizing_price"]

    run_session(active, "2026-08-13")
    with database.connect() as connection:
        original = connection.execute(
            "SELECT * FROM paper_orders WHERE signal_session = '2026-08-12'"
        ).fetchall()
        fills = connection.execute("SELECT * FROM paper_fills").fetchall()
        account = connection.execute("SELECT * FROM paper_accounts").fetchone()
        positions = connection.execute("SELECT * FROM paper_positions").fetchall()
    assert len(fills) >= 1
    assert {row["status"] for row in original} <= {"FILLED", "REJECTED"}
    assert account["cash"] >= 0
    assert all(row["quantity"] % 100 == 0 for row in positions)
    assert all(row["available_quantity"] == 0 for row in positions)

    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        settle_due_orders(connection, "2026-08-14", {})
        connection.commit()
        unlocked = connection.execute("SELECT * FROM paper_positions").fetchall()
    assert all(row["available_quantity"] == row["quantity"] for row in unlocked)


def test_missed_next_session_rejects_without_late_fill(tmp_path: Path) -> None:
    active = settings(tmp_path)
    run_session(active, "2026-08-12")
    run_session(active, "2026-08-14")
    database = Database(active.database_path)
    with database.connect() as connection:
        missed = connection.execute(
            "SELECT * FROM paper_orders WHERE signal_session = '2026-08-12'"
        ).fetchall()
        fills = connection.execute(
            """
            SELECT pf.* FROM paper_fills pf
            JOIN paper_orders po ON po.id = pf.order_id
            WHERE po.signal_session = '2026-08-12'
            """
        ).fetchall()
    assert len(missed) == 3
    assert {row["status"] for row in missed} == {"REJECTED"}
    assert {row["reject_reason"] for row in missed} == {"MISSED_EXECUTION_SESSION"}
    assert fills == []


def test_limit_up_buy_is_rejected_without_replacement(tmp_path: Path) -> None:
    active = settings(tmp_path)
    run_session(active, "2026-08-12")
    database = Database(active.database_path)
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        order = connection.execute("SELECT * FROM paper_orders ORDER BY code LIMIT 1").fetchone()
        code = str(order["code"])
        settle_due_orders(
            connection,
            "2026-08-13",
            {code: 10.0},
            {code: {"up_limit": 10.0, "down_limit": 8.0}},
        )
        connection.commit()
        rejected = connection.execute(
            "SELECT * FROM paper_orders WHERE id = ?", (order["id"],)
        ).fetchone()
        replacement_count = connection.execute(
            "SELECT COUNT(*) AS count FROM paper_orders WHERE signal_session = '2026-08-13'"
        ).fetchone()["count"]
    assert rejected["status"] == "REJECTED"
    assert rejected["reject_reason"] == "BUY_LIMIT_UP"
    assert replacement_count == 0


def test_suspended_and_st_buy_are_rejected_without_replacement(tmp_path: Path) -> None:
    active = settings(tmp_path)
    run_session(active, "2026-08-12")
    database = Database(active.database_path)
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        orders = connection.execute("SELECT * FROM paper_orders ORDER BY code LIMIT 2").fetchall()
        prices = {str(row["code"]): 10.0 for row in orders}
        constraints = {
            str(orders[0]["code"]): {"suspended": True},
            str(orders[1]["code"]): {"buy_restricted": True},
        }
        settle_due_orders(connection, "2026-08-13", prices, constraints)
        connection.commit()
        rejected = connection.execute(
            "SELECT * FROM paper_orders WHERE id IN (?, ?) ORDER BY code",
            (orders[0]["id"], orders[1]["id"]),
        ).fetchall()
    assert {row["reject_reason"] for row in rejected} == {"SUSPENDED", "BUY_RESTRICTED"}


def test_snapshot_persists_position_valuations_that_reconcile_to_account(tmp_path: Path) -> None:
    database = Database(tmp_path / "valuation.sqlite3")
    database.initialize()
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        ensure_account(connection, 100_000)
        connection.executemany(
            """
            INSERT INTO paper_positions(
                account_id, code, name, quantity, available_quantity,
                average_cost, updated_at
            ) VALUES ('paper-default', ?, ?, ?, ?, ?, '2026-08-13T00:00:00Z')
            """,
            [
                ("000001.SZ", "A", 100, 100, 10.0),
                ("000002.SZ", "B", 200, 200, 20.0),
            ],
        )
        write_portfolio_snapshot(
            connection,
            "2026-08-13",
            {"000001.SZ": 12.0},
            valuation_policy="TEST_CLOSE_OR_BOOK_COST",
        )
        snapshot = connection.execute("SELECT * FROM portfolio_snapshots").fetchone()
        valuations = connection.execute(
            "SELECT * FROM portfolio_position_valuations ORDER BY code"
        ).fetchall()
        connection.commit()
    assert len(valuations) == 2
    assert valuations[0]["valuation_source"] == "MARKET_CLOSE"
    assert valuations[1]["valuation_source"] == "AVERAGE_COST_FALLBACK"
    assert snapshot["market_value"] == sum(row["market_value"] for row in valuations)


def test_database_migration_unlocks_legacy_positions_only(tmp_path: Path) -> None:
    database = Database(tmp_path / "migration.sqlite3")
    database.initialize()
    with database.connect() as connection:
        ensure_account(connection, 100_000)
        connection.executemany(
            """
            INSERT INTO paper_positions(
                account_id, code, name, quantity, available_quantity,
                average_cost, last_buy_session, updated_at
            ) VALUES ('paper-default', ?, ?, 100, 0, 10, ?, 'now')
            """,
            [("LEGACY", "Legacy", None), ("NEW", "New", "2026-08-13")],
        )
        connection.commit()
    database.initialize()
    with database.connect() as connection:
        rows = {
            row["code"]: row
            for row in connection.execute("SELECT * FROM paper_positions").fetchall()
        }
    assert rows["LEGACY"]["available_quantity"] == 100
    assert rows["NEW"]["available_quantity"] == 0
