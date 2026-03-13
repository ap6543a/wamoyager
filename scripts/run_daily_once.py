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

# DRY_RUN is read from .env — override here if you want to force a value
# os.environ["DRY_RUN"] = "true"

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=False)

from wamoyager_runtime.logging_setup import setup_logging

setup_logging("INFO")

import logging
logger = logging.getLogger(__name__)


def main() -> None:
    database_path = os.environ.get("DATABASE_PATH", "./wamoyager.db")
    dry_run = os.environ.get("DRY_RUN", "false").lower() in ("1", "true", "yes")
    logger.info("Running daily cycle once (DRY_RUN=%s, DATABASE_PATH=%s)", dry_run, database_path)

    from memory.db import Database
    from services.wmata_client import WmataClient
    from services.notifier_email import EmailNotifier
    # from brain.stub_brain import StubBrain
    from brain.agents_sdk_brain import AgentsSdkBrain
    from wamoyager_runtime.config import load_config
    from wamoyager_runtime.main import run_daily_cycle

    cfg = load_config()
    db = Database(cfg.DATABASE_PATH)
    wmata = WmataClient(api_key=cfg.WMATA_API_KEY)
    notifier = EmailNotifier(
        smtp_login=cfg.MAILGUN_SMTP_LOGIN,
        smtp_password=cfg.MAILGUN_SMTP_PASSWORD,
        from_address=cfg.MAILGUN_FROM_ADDRESS,
        from_name=cfg.MAILGUN_FROM_NAME,
        db=db,
        dry_run=cfg.DRY_RUN,
    )
    brain = AgentsSdkBrain(db=db)

    try:
        run_daily_cycle(cfg, db, wmata, notifier, brain)
        logger.info("Daily cycle finished.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
