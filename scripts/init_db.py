#!/usr/bin/env python3
"""Initialize the SQLite database by applying all migrations in order.

Usage:
    python scripts/init_db.py
    DATABASE_PATH=/path/to/wamoyager.db python scripts/init_db.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=False)

from memory.db import apply_migrations
from wamoyager_runtime.logging_setup import setup_logging

setup_logging("INFO")

import logging
logger = logging.getLogger(__name__)


def main() -> None:
    database_path = os.environ.get("DATABASE_PATH", "./wamoyager.db")
    logger.info("Initializing database at: %s", database_path)
    apply_migrations(database_path)
    logger.info("Database initialization complete.")


if __name__ == "__main__":
    main()
