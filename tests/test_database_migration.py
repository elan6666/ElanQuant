import sqlite3
from pathlib import Path

from scripts.server.migrate_app_database import backup_and_migrate


def test_backup_and_migrate_preserves_source_and_verifies_database(tmp_path: Path) -> None:
    database_path = tmp_path / "elanquant.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE legacy_marker(value TEXT NOT NULL)")
        connection.execute("INSERT INTO legacy_marker VALUES ('preserve-me')")
        connection.commit()

    receipt = backup_and_migrate(database_path, tmp_path / "backups")

    backup_path = Path(str(receipt["backup"]))
    assert receipt["status"] == "PASS"
    assert receipt["integrity_check"] == "ok"
    assert receipt["foreign_key_violations"] == 0
    assert receipt["backup_mode"] == "0o600"
    assert backup_path.is_file()
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT value FROM legacy_marker").fetchone()[0] == "preserve-me"
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='paper_signal_publications'"
        ).fetchone()
    with sqlite3.connect(backup_path) as connection:
        assert connection.execute("SELECT value FROM legacy_marker").fetchone()[0] == "preserve-me"
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='paper_signal_publications'"
        ).fetchone() is None
