"""SQLite connection management and DB initialization."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def get_connection(database_path: str) -> sqlite3.Connection:
    """Return a sqlite3 connection with row_factory and foreign keys enabled."""
    conn = sqlite3.connect(database_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def apply_migrations(database_path: str) -> None:
    """Apply all SQL migration files in order."""
    conn = get_connection(database_path)
    migration_files = sorted(_MIGRATIONS_DIR.glob("*.sql"))

    if not migration_files:
        logger.warning("No migration files found in %s", _MIGRATIONS_DIR)
        return

    with conn:
        for migration_file in migration_files:
            logger.info("Applying migration: %s", migration_file.name)
            sql = migration_file.read_text(encoding="utf-8")
            conn.executescript(sql)

    logger.info("All migrations applied successfully.")
    conn.close()


class Database:
    """Lightweight wrapper around a SQLite connection, used throughout the app."""

    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = get_connection(self.database_path)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
