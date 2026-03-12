"""Wamoyager entrypoint: initializes all services and starts the scheduler."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Any

from wamoyager_runtime.config import load_config
from wamoyager_runtime.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def build_runtime():
    """Build and return all runtime components without starting the scheduler."""
    from memory.db import Database
    from services.wmata_client import WmataClient
    from services.notifier_email import EmailNotifier
    from brain.stub_brain import StubBrain

    cfg = load_config()
    db = Database(cfg.DATABASE_PATH)
    wmata = WmataClient(api_key=cfg.WMATA_API_KEY)
    notifier = EmailNotifier(
        gmail_address=cfg.GMAIL_ADDRESS,
        app_password=cfg.GMAIL_APP_PASSWORD,
        from_name=cfg.GMAIL_FROM_NAME,
        db=db,
        dry_run=cfg.DRY_RUN,
    )
    brain = StubBrain()
    return cfg, db, wmata, notifier, brain


def run_poll_cycle(cfg: Any, db: Any, wmata: Any, notifier: Any, brain: Any) -> None:
    """Execute one poll-and-notify cycle (synchronous wrapper around async fetch)."""
    from memory.queries import (
        get_all_active_users,
        get_user_preferences,
        get_recent_incidents,
        upsert_incident,
    )
    from wamoyager_runtime.rails import (
        check_cooldown,
        check_rate_limit,
        validate_incident_decision,
    )

    logger.info("Poll cycle starting...")

    async def _fetch() -> list:
        return await wmata.fetch_incidents()

    incidents = asyncio.run(_fetch())
    if not incidents:
        logger.info("Poll cycle: no incidents returned.")
        return

    users = get_all_active_users(db)
    if not users:
        logger.info("Poll cycle: no active users.")
        return

    # Build user dicts with preferences
    user_dicts: list[dict[str, Any]] = []
    for u in users:
        prefs = get_user_preferences(db, u.id)
        d = u.to_dict()
        d["preferences"] = prefs.to_dict() if prefs else {}
        user_dicts.append(d)

    history = [i.to_dict() for i in get_recent_incidents(db, limit=50)]

    for normalized in incidents:
        incident_id, is_new = upsert_incident(db, normalized)
        incident_dict = normalized.to_dict()
        incident_dict["id"] = incident_id

        if not is_new:
            logger.debug("Incident fingerprint=%s already known.", normalized.fingerprint)

        decision = brain.decide_incident(incident_dict, user_dicts, history)

        if not validate_incident_decision(decision):
            logger.error("Brain returned invalid decision for fingerprint=%s; skipping.", normalized.fingerprint)
            continue

        if not decision.notify:
            continue

        for user_id in decision.audience_user_ids:
            # Find user dict
            user_d = next((u for u in user_dicts if u["id"] == user_id), None)
            if not user_d:
                continue

            if not check_rate_limit(user_id, db, cfg.RATE_LIMIT_MAX_PER_HOUR, decision.urgency_level):
                continue
            if not check_cooldown(user_id, normalized.fingerprint, db, cfg.COOLDOWN_MINUTES, decision.urgency_level):
                continue

            body = (
                decision.messages.get(user_id)
                or decision.message_all
                or f"[{decision.urgency_level}] WMATA Alert: {normalized.title}"
            )

            notifier.send_sms(
                to=user_d["email"],
                body=body,
                user_id=user_id,
                incident_id=incident_id,
                notification_type="incident",
            )

    logger.info("Poll cycle complete.")


def run_daily_cycle(cfg: Any, db: Any, wmata: Any, notifier: Any, brain: Any) -> None:
    """Execute the daily 5pm message cycle for all active users."""
    from memory.queries import get_all_active_users, get_user_preferences
    from wamoyager_runtime.rails import check_rate_limit, validate_daily_message_result

    logger.info("Daily cycle starting...")

    users = get_all_active_users(db)
    if not users:
        logger.info("Daily cycle: no active users.")
        return

    for user in users:
        prefs = get_user_preferences(db, user.id)
        if not prefs or not prefs.daily_enabled:
            logger.debug("Daily messages disabled for user_id=%d", user.id)
            continue

        station_codes = prefs.station_codes or []

        async def _fetch_preds(codes: list[str]) -> list:
            return await wmata.fetch_predictions(codes)

        predictions = asyncio.run(_fetch_preds(station_codes)) if station_codes else []

        user_dict = user.to_dict()
        user_dict["preferences"] = prefs.to_dict()

        result = brain.compose_daily_message(
            user=user_dict,
            predictions=[p.to_dict() for p in predictions],
            system_status_summary=None,
        )

        if not validate_daily_message_result(result):
            logger.error("Brain returned invalid daily result for user_id=%d; skipping.", user.id)
            continue

        if not check_rate_limit(user.id, db, cfg.RATE_LIMIT_MAX_PER_HOUR, "INFO"):
            continue

        notifier.send_sms(
            to=user.email,
            body=result.message,
            user_id=user.id,
            incident_id=None,
            notification_type="daily",
        )

    logger.info("Daily cycle complete.")


def run_housekeeping(db: Any) -> None:
    """Prune old notifications and incidents."""
    from memory.queries import prune_old_notifications, prune_old_incidents

    deleted_notifications = prune_old_notifications(db, days=30)
    deleted_incidents = prune_old_incidents(db, days=90)
    logger.info(
        "Housekeeping: pruned %d notifications and %d incidents.",
        deleted_notifications,
        deleted_incidents,
    )


def main() -> None:
    """Main entrypoint: configure logging, build services, start scheduler."""
    from wamoyager_runtime.config import load_config
    from wamoyager_runtime.logging_setup import setup_logging
    from services.scheduler import WamoyagerScheduler

    cfg = load_config()
    setup_logging(log_level=cfg.LOG_LEVEL)

    logger.info("Starting wamoyager. Config: %s", cfg)

    cfg, db, wmata, notifier, brain = build_runtime()

    def poll_job() -> None:
        try:
            run_poll_cycle(cfg, db, wmata, notifier, brain)
        except Exception:
            logger.exception("Unhandled error in poll_job")

    def daily_job() -> None:
        try:
            run_daily_cycle(cfg, db, wmata, notifier, brain)
        except Exception:
            logger.exception("Unhandled error in daily_job")

    def housekeeping_job() -> None:
        try:
            run_housekeeping(db)
        except Exception:
            logger.exception("Unhandled error in housekeeping_job")

    scheduler = WamoyagerScheduler(
        poll_job=poll_job,
        daily_job=daily_job,
        housekeeping_job=housekeeping_job,
        poll_interval_seconds=cfg.POLL_INTERVAL_SECONDS,
        daily_job_time=cfg.DAILY_JOB_TIME,
    )

    def _shutdown(signum: int, frame: object) -> None:
        logger.info("Signal %d received, shutting down...", signum)
        scheduler.stop()
        db.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    scheduler.start()

    logger.info("Wamoyager running. Press Ctrl+C to stop.")
    try:
        signal.pause()
    except (AttributeError, OSError):
        # signal.pause() not available on Windows; use a simple loop
        import time
        while True:
            time.sleep(1)


if __name__ == "__main__":
    main()
