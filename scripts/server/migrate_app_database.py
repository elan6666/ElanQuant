from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from elanquant.storage.database import Database


def backup_and_migrate(database_path: Path, backup_dir: Path) -> dict[str, object]:
    if not database_path.is_file():
        raise RuntimeError(f"database does not exist: {database_path}")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = backup_dir / f"elanquant-pre-migration-{stamp}.sqlite3"
    if backup_path.exists():
        raise RuntimeError(f"backup already exists: {backup_path}")
    with sqlite3.connect(database_path) as source, sqlite3.connect(backup_path) as target:
        source.backup(target)
    os.chmod(backup_path, 0o600)

    Database(database_path).initialize()
    with sqlite3.connect(database_path) as connection:
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    if integrity != "ok" or foreign_keys:
        raise RuntimeError(
            "migration verification failed; services must remain stopped and the backup preserved"
        )
    return {
        "status": "PASS",
        "database": str(database_path),
        "backup": str(backup_path),
        "backup_mode": oct(backup_path.stat().st_mode & 0o777),
        "integrity_check": integrity,
        "foreign_key_violations": len(foreign_keys),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument(
        "--confirm-services-stopped",
        action="store_true",
        help="Required acknowledgement that elanquant-api and elanquant-worker are stopped.",
    )
    args = parser.parse_args()
    if not args.confirm_services_stopped:
        raise RuntimeError("refusing migration until both app services are confirmed stopped")
    print(json.dumps(backup_and_migrate(args.database, args.backup_dir), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
