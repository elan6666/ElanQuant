from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    job_type TEXT NOT NULL,
    requested_session TEXT NOT NULL,
    resolved_session TEXT,
    status TEXT NOT NULL,
    stage TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT '',
    attempt INTEGER NOT NULL DEFAULT 1,
    parent_job_id TEXT REFERENCES jobs(id),
    created_at TEXT NOT NULL,
    started_at TEXT,
    heartbeat_at TEXT,
    finished_at TEXT,
    error_code TEXT,
    error_summary TEXT,
    run_id TEXT
);
CREATE INDEX IF NOT EXISTS jobs_status_created_idx ON jobs(status, created_at);

CREATE TABLE IF NOT EXISTS service_heartbeats (
    service TEXT PRIMARY KEY,
    heartbeat_at TEXT NOT NULL,
    state TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS job_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT NOT NULL,
    progress REAL NOT NULL,
    message TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS job_events_job_idx ON job_events(job_id, id);

CREATE TABLE IF NOT EXISTS data_snapshots (
    id TEXT PRIMARY KEY,
    as_of_session TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    manifest_sha256 TEXT NOT NULL,
    summary_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(as_of_session, manifest_sha256)
);

CREATE TABLE IF NOT EXISTS model_versions (
    id TEXT PRIMARY KEY,
    base_model_id TEXT,
    size TEXT NOT NULL,
    variant TEXT NOT NULL,
    protocol TEXT NOT NULL,
    status TEXT NOT NULL,
    checkpoint_sha256 TEXT NOT NULL,
    tokenizer_sha256 TEXT,
    config_sha256 TEXT,
    code_sha256 TEXT,
    evaluation_receipt_sha256 TEXT,
    validation_rank_ic REAL,
    validation_ic REAL,
    validation_top10_mean_return REAL,
    viewed_test_rank_ic REAL,
    evaluation_receipt TEXT,
    UNIQUE(size, variant, protocol)
);

CREATE TABLE IF NOT EXISTS inference_run_models (
    run_id TEXT NOT NULL REFERENCES inference_runs(id),
    model_version_id TEXT NOT NULL REFERENCES model_versions(id),
    base_model_id TEXT NOT NULL,
    PRIMARY KEY(run_id, model_version_id),
    UNIQUE(run_id, base_model_id)
);

CREATE TABLE IF NOT EXISTS run_model_evaluations (
    run_id TEXT NOT NULL REFERENCES inference_runs(id),
    base_model_id TEXT NOT NULL,
    split TEXT NOT NULL,
    rank_ic REAL NOT NULL,
    ic REAL NOT NULL,
    top10_mean_return REAL NOT NULL,
    rows INTEGER NOT NULL,
    cross_sections INTEGER NOT NULL,
    anchor_set_sha256 TEXT NOT NULL,
    PRIMARY KEY(run_id, base_model_id, split)
);

CREATE TABLE IF NOT EXISTS inference_runs (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id),
    snapshot_id TEXT NOT NULL REFERENCES data_snapshots(id),
    as_of_session TEXT NOT NULL,
    status TEXT NOT NULL,
    protocol TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL,
    scoreable INTEGER NOT NULL DEFAULT 0,
    matrix_receipt_sha256 TEXT,
    evaluation_receipt_sha256 TEXT,
    config_sha256 TEXT,
    code_sha256 TEXT,
    paper_publication_state TEXT,
    paper_publication_run_id TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS inference_runs_session_idx
    ON inference_runs(as_of_session, created_at DESC);

CREATE TABLE IF NOT EXISTS stock_scores (
    run_id TEXT NOT NULL REFERENCES inference_runs(id),
    model_version_id TEXT NOT NULL REFERENCES model_versions(id),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    score REAL NOT NULL,
    rank INTEGER NOT NULL,
    reference_price REAL NOT NULL,
    scoreability TEXT NOT NULL,
    PRIMARY KEY(run_id, model_version_id, code)
);
CREATE INDEX IF NOT EXISTS stock_scores_run_rank_idx ON stock_scores(run_id, rank);

CREATE TABLE IF NOT EXISTS recommendation_sets (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE REFERENCES inference_runs(id),
    signal_session TEXT NOT NULL,
    execution_policy TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recommendation_items (
    recommendation_set_id TEXT NOT NULL REFERENCES recommendation_sets(id),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    rank INTEGER NOT NULL,
    score REAL NOT NULL,
    target_weight REAL NOT NULL,
    frozen_price REAL NOT NULL,
    PRIMARY KEY(recommendation_set_id, code)
);

CREATE TABLE IF NOT EXISTS paper_accounts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    initial_cash REAL NOT NULL,
    cash REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_positions (
    account_id TEXT NOT NULL REFERENCES paper_accounts(id),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    available_quantity INTEGER NOT NULL DEFAULT 0,
    average_cost REAL NOT NULL,
    last_buy_session TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(account_id, code)
);

CREATE TABLE IF NOT EXISTS paper_gaps (
    account_id TEXT NOT NULL REFERENCES paper_accounts(id),
    session TEXT NOT NULL,
    reason TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY(account_id, session)
);

CREATE TABLE IF NOT EXISTS paper_signal_publications (
    account_id TEXT NOT NULL REFERENCES paper_accounts(id),
    signal_session TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES inference_runs(id),
    state TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    PRIMARY KEY(account_id, signal_session)
);

CREATE TABLE IF NOT EXISTS paper_intent_decisions (
    run_id TEXT NOT NULL REFERENCES inference_runs(id),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    rank INTEGER NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    sizing_price REAL NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(run_id, code)
);

CREATE TABLE IF NOT EXISTS paper_orders (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES paper_accounts(id),
    run_id TEXT NOT NULL REFERENCES inference_runs(id),
    signal_session TEXT NOT NULL,
    due_session TEXT NOT NULL,
    execution_session TEXT,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    rank INTEGER NOT NULL DEFAULT 0,
    sizing_price REAL NOT NULL,
    target_weight REAL NOT NULL,
    status TEXT NOT NULL,
    reject_reason TEXT,
    frozen_intent_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(account_id, signal_session, code, side)
);
CREATE INDEX IF NOT EXISTS paper_orders_status_due_idx
    ON paper_orders(account_id, status, due_session);

CREATE TABLE IF NOT EXISTS paper_fills (
    id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL UNIQUE REFERENCES paper_orders(id),
    execution_session TEXT NOT NULL,
    price REAL NOT NULL,
    quantity INTEGER NOT NULL,
    gross_amount REAL NOT NULL,
    commission REAL NOT NULL,
    stamp_tax REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES paper_accounts(id),
    as_of_session TEXT NOT NULL,
    cash REAL NOT NULL,
    market_value REAL NOT NULL,
    nav REAL NOT NULL,
    valuation_policy TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(account_id, as_of_session)
);

CREATE TABLE IF NOT EXISTS portfolio_position_valuations (
    snapshot_id TEXT NOT NULL REFERENCES portfolio_snapshots(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL REFERENCES paper_accounts(id),
    as_of_session TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    average_cost REAL NOT NULL,
    valuation_price REAL NOT NULL,
    valuation_source TEXT NOT NULL,
    market_value REAL NOT NULL,
    unrealized_pnl REAL NOT NULL,
    PRIMARY KEY(snapshot_id, code)
);
CREATE INDEX IF NOT EXISTS portfolio_position_valuations_account_session_idx
    ON portfolio_position_valuations(account_id, as_of_session, code);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            model_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(model_versions)").fetchall()
            }
            snapshot_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(data_snapshots)").fetchall()
            }
            if "summary_json" not in snapshot_columns:
                connection.execute("ALTER TABLE data_snapshots ADD COLUMN summary_json TEXT")
            for name, definition in (
                ("base_model_id", "TEXT"),
                ("validation_rank_ic", "REAL"),
                ("validation_ic", "REAL"),
                ("validation_top10_mean_return", "REAL"),
                ("viewed_test_rank_ic", "REAL"),
                ("evaluation_receipt", "TEXT"),
                ("tokenizer_sha256", "TEXT"),
                ("config_sha256", "TEXT"),
                ("code_sha256", "TEXT"),
                ("evaluation_receipt_sha256", "TEXT"),
            ):
                if name not in model_columns:
                    connection.execute(f"ALTER TABLE model_versions ADD COLUMN {name} {definition}")
            run_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(inference_runs)").fetchall()
            }
            for name, definition in (
                ("scoreable", "INTEGER NOT NULL DEFAULT 0"),
                ("matrix_receipt_sha256", "TEXT"),
                ("evaluation_receipt_sha256", "TEXT"),
                ("config_sha256", "TEXT"),
                ("code_sha256", "TEXT"),
                ("paper_publication_state", "TEXT"),
                ("paper_publication_run_id", "TEXT"),
            ):
                if name not in run_columns:
                    connection.execute(f"ALTER TABLE inference_runs ADD COLUMN {name} {definition}")
            position_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(paper_positions)").fetchall()
            }
            for name, definition in (
                ("available_quantity", "INTEGER NOT NULL DEFAULT 0"),
                ("last_buy_session", "TEXT"),
            ):
                if name not in position_columns:
                    connection.execute(
                        f"ALTER TABLE paper_positions ADD COLUMN {name} {definition}"
                    )
            order_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(paper_orders)").fetchall()
            }
            if "rank" not in order_columns:
                connection.execute(
                    "ALTER TABLE paper_orders ADD COLUMN rank INTEGER NOT NULL DEFAULT 0"
                )
                connection.execute(
                    """
                    UPDATE paper_orders
                    SET rank = COALESCE((
                        SELECT ri.rank FROM recommendation_sets rs
                        JOIN recommendation_items ri ON ri.recommendation_set_id = rs.id
                        WHERE rs.run_id = paper_orders.run_id AND ri.code = paper_orders.code
                        LIMIT 1
                    ), 0)
                    """
                )
            connection.execute(
                """
                UPDATE paper_positions SET available_quantity = quantity
                WHERE last_buy_session IS NULL AND available_quantity = 0 AND quantity > 0
                """
            )
            legacy_sessions = connection.execute(
                """
                SELECT rs.signal_session
                FROM recommendation_sets rs
                GROUP BY rs.signal_session
                """
            ).fetchall()
            for legacy in legacy_sessions:
                first = connection.execute(
                    """
                    SELECT run_id, created_at FROM recommendation_sets
                    WHERE signal_session = ?
                    ORDER BY created_at, id LIMIT 1
                    """,
                    (legacy["signal_session"],),
                ).fetchone()
                if first is None:
                    continue
                order_runs = {
                    str(row["run_id"])
                    for row in connection.execute(
                        """
                        SELECT DISTINCT run_id FROM paper_orders
                        WHERE account_id = ? AND signal_session = ?
                        """,
                        ("paper-default", legacy["signal_session"]),
                    ).fetchall()
                }
                mixed = bool(order_runs - {str(first["run_id"])})
                connection.execute(
                    """
                    INSERT OR IGNORE INTO paper_signal_publications(
                        account_id, signal_session, run_id, state, note, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "paper-default",
                        legacy["signal_session"],
                        first["run_id"],
                        "LEGACY_MIXED_RUNS" if mixed else "FROZEN",
                        (
                            f"检测到 {len(order_runs)} 个历史订单运行来源；"
                            "原始账本已保留，未静默改写。"
                            if mixed
                            else "由该信号日最早的推荐 run 回填冻结发布来源。"
                        ),
                        first["created_at"],
                    ),
                )
                if mixed:
                    connection.execute(
                        """
                        UPDATE inference_runs
                        SET paper_publication_state = 'LEGACY_MIXED_RUNS',
                            paper_publication_run_id = ?
                        WHERE id IN (
                            SELECT DISTINCT run_id FROM paper_orders
                            WHERE account_id = ? AND signal_session = ?
                        )
                          AND paper_publication_state IS NULL
                        """,
                        (
                            first["run_id"],
                            "paper-default",
                            legacy["signal_session"],
                        ),
                    )
                connection.execute(
                    """
                    UPDATE inference_runs
                    SET paper_publication_state = ?, paper_publication_run_id = ?
                    WHERE id = ? AND paper_publication_state IS NULL
                    """,
                    (
                        "LEGACY_MIXED_RUNS" if mixed else "FROZEN",
                        first["run_id"],
                        first["run_id"],
                    ),
                )
                connection.execute(
                    """
                    UPDATE inference_runs
                    SET paper_publication_state = 'SKIPPED_EXISTING_FROZEN_RUN',
                        paper_publication_run_id = ?
                        WHERE id IN (
                            SELECT run_id FROM recommendation_sets
                            WHERE signal_session = ?
                        ) AND id != ?
                          AND paper_publication_state IS NULL
                    """,
                    (first["run_id"], legacy["signal_session"], first["run_id"]),
                )
            connection.execute(
                """
                INSERT OR IGNORE INTO paper_intent_decisions(
                    run_id, code, name, rank, decision, reason, quantity,
                    sizing_price, created_at
                )
                SELECT rs.run_id, ri.code, ri.name, ri.rank,
                    CASE WHEN po.id IS NULL THEN 'LEGACY_NO_ORDER_UNCLASSIFIED'
                         ELSE 'ORDER_FROZEN' END,
                    CASE WHEN po.id IS NULL
                         THEN 'Historical run predates explicit decision receipts.'
                         ELSE 'Recovered from immutable historical paper order.' END,
                    COALESCE(po.quantity, 0), ri.frozen_price, rs.created_at
                FROM recommendation_sets rs
                JOIN recommendation_items ri ON ri.recommendation_set_id = rs.id
                LEFT JOIN paper_orders po
                  ON po.run_id = rs.run_id AND po.code = ri.code
                """
            )
            connection.commit()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=10000")
        try:
            yield connection
        finally:
            connection.close()
