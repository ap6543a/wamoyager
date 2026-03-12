#!/usr/bin/env python3
"""Query and display all rows from a database table.

Usage:
    python test/query_table.py users
    python test/query_table.py notifications
    python test/query_table.py incidents
"""

import sqlite3
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

DB_PATH = os.environ.get("DATABASE_PATH", "./wamoyager.db")
TABLES = ["users", "user_preferences", "incidents", "notifications", "agent_state", "conversation_state"]


def query_table(table: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    if not rows:
        print(f"No records in '{table}'.")
        return
    print(f"\n=== {table} ({len(rows)} rows) ===")
    for row in rows:
        print(dict(row))


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: python test/query_table.py <table>")
        print(f"Available tables: {', '.join(TABLES)}")
        sys.exit(1)

    table = sys.argv[1]
    if table not in TABLES:
        print(f"Unknown table '{table}'. Available: {', '.join(TABLES)}")
        sys.exit(1)

    query_table(table)


if __name__ == "__main__":
    main()
