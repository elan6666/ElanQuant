import json
from pathlib import Path

from elanquant.orchestration.jobs import JobStore
from elanquant.orchestration.worker import Worker
from elanquant.pipelines.paper import (
    Recommendation,
    create_frozen_intents,
    ensure_account,
    settle_due_orders,
    write_portfolio_snapshot,
)
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


def run_session(active: Settings, session: str, *, force: bool = False) -> None:
    database = Database(active.database_path)
    database.initialize()
    JobStore(database).submit_update_infer(session, force=force)
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


def test_force_rerun_keeps_first_signal_publication_immutable(tmp_path: Path) -> None:
    active = settings(tmp_path)
    run_session(active, "2026-08-12")
    database = Database(active.database_path)
    with database.connect() as connection:
        first_orders = connection.execute(
            "SELECT id, run_id, code, quantity FROM paper_orders ORDER BY code"
        ).fetchall()
        first_run_id = str(first_orders[0]["run_id"])

    run_session(active, "2026-08-12", force=True)
    with database.connect() as connection:
        orders = connection.execute(
            "SELECT id, run_id, code, quantity FROM paper_orders ORDER BY code"
        ).fetchall()
        runs = connection.execute(
            """
            SELECT id, paper_publication_state, paper_publication_run_id
            FROM inference_runs ORDER BY created_at, id
            """
        ).fetchall()
        publications = connection.execute(
            "SELECT * FROM paper_signal_publications"
        ).fetchall()
        skipped_decisions = connection.execute(
            """
            SELECT * FROM paper_intent_decisions
            WHERE run_id = ? ORDER BY rank
            """,
            (runs[-1]["id"],),
        ).fetchall()
    assert [tuple(row) for row in orders] == [tuple(row) for row in first_orders]
    assert len(publications) == 1
    assert publications[0]["run_id"] == first_run_id
    assert runs[0]["paper_publication_state"] == "FROZEN"
    assert runs[-1]["paper_publication_state"] == "SKIPPED_EXISTING_FROZEN_RUN"
    assert runs[-1]["paper_publication_run_id"] == first_run_id
    assert len(skipped_decisions) == 3
    assert {row["decision"] for row in skipped_decisions} == {"PAPER_PUBLICATION_SKIPPED"}


def test_migration_labels_legacy_mixed_run_orders_without_rewriting_them(tmp_path: Path) -> None:
    active = settings(tmp_path)
    run_session(active, "2026-08-12")
    run_session(active, "2026-08-12", force=True)
    database = Database(active.database_path)
    with database.connect() as connection:
        runs = connection.execute(
            "SELECT id FROM inference_runs ORDER BY created_at, id"
        ).fetchall()
        first_run_id, second_run_id = str(runs[0]["id"]), str(runs[1]["id"])
        connection.execute("DELETE FROM paper_signal_publications")
        connection.execute("DELETE FROM paper_intent_decisions")
        connection.execute(
            """
            UPDATE inference_runs
            SET paper_publication_state = NULL, paper_publication_run_id = NULL
            """
        )
        connection.execute(
            """
            INSERT INTO paper_orders(
                id, account_id, run_id, signal_session, due_session, code, name,
                side, quantity, sizing_price, target_weight, status,
                frozen_intent_json, created_at, updated_at
            ) VALUES ('legacy-second-order', 'paper-default', ?, '2026-08-12',
                '2026-08-13', '999999.SZ', 'Legacy mixed', 'BUY', 100, 10,
                0.333333, 'PENDING', '{}', 'later', 'later')
            """,
            (second_run_id,),
        )
        before = connection.execute("SELECT COUNT(*) FROM paper_orders").fetchone()[0]
        connection.commit()

    database.initialize()
    with database.connect() as connection:
        publication = connection.execute(
            "SELECT * FROM paper_signal_publications WHERE signal_session = '2026-08-12'"
        ).fetchone()
        states = {
            row["id"]: row["paper_publication_state"]
            for row in connection.execute("SELECT * FROM inference_runs").fetchall()
        }
        after = connection.execute("SELECT COUNT(*) FROM paper_orders").fetchone()[0]
    assert before == after
    assert publication["state"] == "LEGACY_MIXED_RUNS"
    assert publication["run_id"] == first_run_id
    assert "原始账本已保留" in publication["note"]
    assert states[first_run_id] == "LEGACY_MIXED_RUNS"
    assert states[second_run_id] == "LEGACY_MIXED_RUNS"


def test_migration_locks_zero_order_recommendation_day_to_first_run(tmp_path: Path) -> None:
    active = settings(tmp_path)
    run_session(active, "2026-08-12")
    database = Database(active.database_path)
    with database.connect() as connection:
        first_run_id = str(
            connection.execute(
                "SELECT run_id FROM recommendation_sets ORDER BY created_at, id LIMIT 1"
            ).fetchone()["run_id"]
        )
        connection.execute("DELETE FROM paper_signal_publications")
        connection.execute("DELETE FROM paper_intent_decisions")
        connection.execute("DELETE FROM paper_orders")
        connection.execute(
            """
            UPDATE inference_runs
            SET paper_publication_state = NULL, paper_publication_run_id = NULL
            """
        )
        connection.commit()

    database.initialize()
    run_session(active, "2026-08-12", force=True)
    with database.connect() as connection:
        publication = connection.execute(
            "SELECT * FROM paper_signal_publications WHERE signal_session = '2026-08-12'"
        ).fetchone()
        latest = connection.execute(
            "SELECT * FROM inference_runs ORDER BY created_at DESC, id DESC LIMIT 1"
        ).fetchone()
    assert publication["run_id"] == first_run_id
    assert publication["state"] == "FROZEN"
    assert latest["paper_publication_state"] == "SKIPPED_EXISTING_FROZEN_RUN"
    assert latest["paper_publication_run_id"] == first_run_id


def test_migration_marks_later_only_order_source_as_legacy_mixed(tmp_path: Path) -> None:
    active = settings(tmp_path)
    run_session(active, "2026-08-12")
    run_session(active, "2026-08-12", force=True)
    database = Database(active.database_path)
    with database.connect() as connection:
        runs = connection.execute(
            "SELECT id FROM inference_runs ORDER BY created_at, id"
        ).fetchall()
        first_run_id, second_run_id = str(runs[0]["id"]), str(runs[1]["id"])
        connection.execute("DELETE FROM paper_signal_publications")
        connection.execute("DELETE FROM paper_intent_decisions")
        connection.execute("DELETE FROM paper_orders")
        connection.execute(
            """
            UPDATE inference_runs
            SET paper_publication_state = NULL, paper_publication_run_id = NULL
            """
        )
        connection.execute(
            """
            INSERT INTO paper_orders(
                id, account_id, run_id, signal_session, due_session, code, name,
                side, quantity, rank, sizing_price, target_weight, status,
                frozen_intent_json, created_at, updated_at
            ) VALUES ('later-only', 'paper-default', ?, '2026-08-12', '2026-08-13',
                '999999.SZ', 'Later only', 'BUY', 100, 1, 10, 0.333333,
                'PENDING', '{}', 'later', 'later')
            """,
            (second_run_id,),
        )
        connection.commit()

    database.initialize()
    with database.connect() as connection:
        publication = connection.execute(
            "SELECT * FROM paper_signal_publications WHERE signal_session = '2026-08-12'"
        ).fetchone()
    assert publication["run_id"] == first_run_id
    assert publication["state"] == "LEGACY_MIXED_RUNS"
    assert "原始账本已保留" in publication["note"]


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


def test_top_ranked_stock_below_board_lot_is_an_explicit_decision(tmp_path: Path) -> None:
    database = Database(tmp_path / "board-lot.sqlite3")
    database.initialize()
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        ensure_account(connection, 100_000)
        connection.execute(
            """
            INSERT INTO jobs(
                id, idempotency_key, job_type, requested_session, status, stage,
                progress, message, created_at
            ) VALUES ('job', 'job', 'UPDATE_INFER', '2026-08-12', 'SUCCEEDED',
                'SUCCEEDED', 1, 'done', 'now')
            """
        )
        connection.execute(
            """
            INSERT INTO data_snapshots(
                id, as_of_session, source, status, row_count, manifest_sha256, created_at
            ) VALUES ('snapshot', '2026-08-12', 'TEST', 'PASS', 1, ?, 'now')
            """,
            ("a" * 64,),
        )
        connection.execute(
            """
            INSERT INTO inference_runs(
                id, job_id, snapshot_id, as_of_session, status, protocol,
                artifact_path, artifact_sha256, created_at
            ) VALUES ('run', 'job', 'snapshot', '2026-08-12', 'SUCCEEDED',
                'TEST', 'ignored', ?, 'now')
            """,
            ("b" * 64,),
        )
        result = create_frozen_intents(
            connection,
            "run",
            "2026-08-12",
            [
                Recommendation(
                    code="688001.SH",
                    name="High price",
                    score=0.1,
                    reference_price=1_000.0,
                    rank=1,
                )
            ],
            top_k=3,
            due_session="2026-08-13",
        )
        decision = connection.execute(
            "SELECT * FROM paper_intent_decisions WHERE run_id = 'run'"
        ).fetchone()
        order_count = connection.execute("SELECT COUNT(*) FROM paper_orders").fetchone()[0]
        connection.commit()
    assert result["state"] == "FROZEN"
    assert order_count == 0
    assert decision["decision"] == "SKIPPED_BELOW_BOARD_LOT"
    assert decision["quantity"] == 0


def test_buy_budget_reserves_commission_and_executes_by_rank(tmp_path: Path) -> None:
    database = Database(tmp_path / "ranked-orders.sqlite3")
    database.initialize()
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        ensure_account(connection, 100_000)
        connection.execute(
            """
            INSERT INTO jobs(
                id, idempotency_key, job_type, requested_session, status, stage,
                progress, message, created_at
            ) VALUES ('job', 'job', 'UPDATE_INFER', '2026-08-12', 'SUCCEEDED',
                'SUCCEEDED', 1, 'done', 'now')
            """
        )
        connection.execute(
            """
            INSERT INTO data_snapshots(
                id, as_of_session, source, status, row_count, manifest_sha256, created_at
            ) VALUES ('snapshot', '2026-08-12', 'TEST', 'PASS', 3, ?, 'now')
            """,
            ("a" * 64,),
        )
        connection.execute(
            """
            INSERT INTO inference_runs(
                id, job_id, snapshot_id, as_of_session, status, protocol,
                artifact_path, artifact_sha256, created_at
            ) VALUES ('run', 'job', 'snapshot', '2026-08-12', 'SUCCEEDED',
                'TEST', 'ignored', ?, 'now')
            """,
            ("b" * 64,),
        )
        recommendations = [
            Recommendation(
                code=f"00000{rank}.SZ",
                name=f"Rank {rank}",
                score=1 - rank / 10,
                reference_price=160.0,
                rank=rank,
            )
            for rank in (1, 2, 3)
        ]
        create_frozen_intents(
            connection,
            "run",
            "2026-08-12",
            recommendations,
            top_k=3,
            due_session="2026-08-13",
        )
        frozen = connection.execute(
            "SELECT * FROM paper_orders ORDER BY rank"
        ).fetchall()
        known_total = sum(
            row["quantity"] * row["sizing_price"]
            + json.loads(row["frozen_intent_json"])["reserved_commission"]
            for row in frozen
        )
        assert known_total <= 100_000
        settle_due_orders(
            connection,
            "2026-08-13",
            {str(row["code"]): 170.0 for row in frozen},
        )
        outcomes = connection.execute(
            "SELECT rank, status, reject_reason FROM paper_orders ORDER BY rank"
        ).fetchall()
        connection.commit()
    assert [(row["rank"], row["status"]) for row in outcomes] == [
        (1, "FILLED"),
        (2, "FILLED"),
        (3, "REJECTED"),
    ]
    assert outcomes[-1]["reject_reason"] == "INSUFFICIENT_CASH"
