#!/usr/bin/env python3
"""Run the daily 5pm message cycle for all active users (for testing).

Usage:
    python scripts/run_daily_once.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Force dry-run before loading config
os.environ["DRY_RUN"] = "true"

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=False)

from wamoyager_runtime.logging_setup import setup_logging

setup_logging("INFO")

import logging
logger = logging.getLogger(__name__)


def main() -> None:
    database_path = os.environ.get("DATABASE_PATH", "./wamoyager.db")
    logger.info("Running daily cycle once (DRY_RUN=true, DATABASE_PATH=%s)", database_path)

    from memory.db import Database
    from services.wmata_client import WmataClient
    from services.notifier_twilio import TwilioNotifier
    from brain.stub_brain import StubBrain
    from wamoyager_runtime.config import load_config
    from wamoyager_runtime.main import run_daily_cycle

    cfg = load_config()
    db = Database(cfg.DATABASE_PATH)
    wmata = WmataClient(api_key=cfg.WMATA_API_KEY)
    notifier = TwilioNotifier(
        account_sid=cfg.TWILIO_ACCOUNT_SID,
        auth_token=cfg.TWILIO_AUTH_TOKEN,
        from_number=cfg.TWILIO_FROM_NUMBER,
        db=db,
        dry_run=True,  # always forced
    )
    brain = StubBrain()

    try:
        run_daily_cycle(cfg, db, wmata, notifier, brain)
        logger.info("Daily cycle finished.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
