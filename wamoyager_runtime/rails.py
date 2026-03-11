"""Safety rail checks enforced by the Runtime before any Twilio send."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memory.db import Database

logger = logging.getLogger(__name__)


def check_rate_limit(
    user_id: int,
    db: "Database",
    max_per_hour: int,
    urgency_level: str = "INFO",
) -> bool:
    """Return True (allowed) if the user has not exceeded the rate limit this hour.

    CRITICAL urgency bypasses the rate limit.
    """
    if urgency_level == "CRITICAL":
        return True

    from memory.queries import get_notifications_for_user_since

    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    recent = get_notifications_for_user_since(db, user_id, since=one_hour_ago)
    # Only count sent/dry_run notifications (not failed ones)
    sent_count = sum(1 for n in recent if n.status in ("sent", "dry_run"))

    if sent_count >= max_per_hour:
        logger.warning(
            "Rate limit exceeded for user_id=%d: %d/%d messages in last hour",
            user_id,
            sent_count,
            max_per_hour,
        )
        return False
    return True


def check_cooldown(
    user_id: int,
    fingerprint: str,
    db: "Database",
    cooldown_minutes: int,
    urgency_level: str = "INFO",
) -> bool:
    """Return True (allowed) if the cooldown period has elapsed since the last
    notification for this fingerprint.

    CRITICAL urgency bypasses the cooldown.
    """
    if urgency_level == "CRITICAL":
        return True

    from memory.queries import get_last_notification_for_fingerprint

    last = get_last_notification_for_fingerprint(db, user_id, fingerprint)
    if last is None:
        return True

    if last.status not in ("sent", "dry_run"):
        return True

    elapsed = datetime.now(timezone.utc) - last.created_at
    if elapsed < timedelta(minutes=cooldown_minutes):
        logger.info(
            "Cooldown active for user_id=%d fingerprint=%s: last sent %s ago (cooldown=%dm)",
            user_id,
            fingerprint,
            elapsed,
            cooldown_minutes,
        )
        return False
    return True


def validate_incident_decision(decision: object) -> bool:
    """Validate that a brain IncidentDecision object matches the expected schema."""
    from brain.interface import IncidentDecision

    if not isinstance(decision, IncidentDecision):
        logger.error("Brain output is not an IncidentDecision: %r", type(decision))
        return False

    valid_urgencies = {"INFO", "MINOR", "MAJOR", "CRITICAL"}
    if decision.urgency_level not in valid_urgencies:
        logger.error(
            "Invalid urgency_level %r; must be one of %s",
            decision.urgency_level,
            valid_urgencies,
        )
        return False

    if not isinstance(decision.audience_user_ids, list):
        logger.error("audience_user_ids must be a list")
        return False

    if not isinstance(decision.messages, dict):
        logger.error("messages must be a dict")
        return False

    return True


def validate_daily_message_result(result: object) -> bool:
    """Validate that a brain DailyMessageResult object matches the expected schema."""
    from brain.interface import DailyMessageResult

    if not isinstance(result, DailyMessageResult):
        logger.error("Brain output is not a DailyMessageResult: %r", type(result))
        return False

    if not isinstance(result.message, str) or not result.message.strip():
        logger.error("DailyMessageResult.message must be a non-empty string")
        return False

    return True
