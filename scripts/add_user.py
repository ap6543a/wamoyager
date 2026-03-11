#!/usr/bin/env python3
"""CLI script to add a new user to the database.

Usage:
    python scripts/add_user.py --name "Alice" --phone "+12025551234"
    python scripts/add_user.py --name "Bob" --phone "+12025559876" \
        --station-codes "A01,C01" --lines "RD,BL"
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=False)

from memory.db import Database
from memory.queries import create_user, update_user_preferences
from wamoyager_runtime.logging_setup import setup_logging

setup_logging("INFO")

import logging
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Add a new wamoyager user.")
    parser.add_argument("--name", required=True, help="User's full name")
    parser.add_argument(
        "--phone",
        required=True,
        help="Phone number in E.164 format, e.g. +12025551234",
    )
    parser.add_argument(
        "--station-codes",
        default="",
        help="Comma-separated WMATA station codes, e.g. A01,C01",
    )
    parser.add_argument(
        "--lines",
        default="",
        help="Comma-separated WMATA line codes, e.g. RD,BL",
    )
    parser.add_argument(
        "--direction",
        default="",
        help="Comma-separated destination direction keywords, e.g. Shady,Glenmont",
    )
    parser.add_argument(
        "--timezone",
        default="America/New_York",
        help="User timezone (default: America/New_York)",
    )
    parser.add_argument(
        "--no-daily",
        action="store_true",
        help="Disable daily 5pm messages for this user",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    database_path = os.environ.get("DATABASE_PATH", "./wamoyager.db")

    db = Database(database_path)
    try:
        user_id = create_user(
            db=db,
            name=args.name,
            phone_e164=args.phone,
            timezone=args.timezone,
        )

        station_codes = [s.strip() for s in args.station_codes.split(",") if s.strip()]
        lines = [ln.strip().upper() for ln in args.lines.split(",") if ln.strip()]
        direction = [d.strip() for d in args.direction.split(",") if d.strip()]

        update_user_preferences(
            db=db,
            user_id=user_id,
            station_codes=station_codes or None,
            lines=lines or None,
            direction=direction or None,
            daily_enabled=not args.no_daily,
        )

        logger.info(
            "User created: id=%d name=%r phone=%r station_codes=%r lines=%r",
            user_id,
            args.name,
            args.phone,
            station_codes,
            lines,
        )
        print(f"User '{args.name}' created with id={user_id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
