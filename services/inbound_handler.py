"""Inbound SMS handler: routes messages to the Brain and manages conversation state.

Flow:
  1. Look up conversation state for the caller's phone number.
  2. Pass (from_number, body, conv_state) to brain.handle_inbound_sms().
  3. Merge any data updates returned by the Brain into the stored state.
  4. If Brain signals setup_complete, create the user in the DB.
  5. Return the reply text to the webhook server (delivered back via TwiML).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brain.interface import BrainInterface
    from memory.db import Database

logger = logging.getLogger(__name__)

# Keywords that always (re)start the setup flow regardless of current state
_SETUP_KEYWORDS = {"setup", "start", "subscribe", "sign up", "signup"}
_STOP_KEYWORDS = {"stop", "unsubscribe", "cancel", "quit"}


def handle(from_number: str, body: str, db: "Database", brain: "BrainInterface") -> str:
    """Process one inbound SMS message. Returns the reply text to send back.

    Args:
        from_number: E.164 phone number of the sender (e.g. "+12025551234").
        body:        Raw SMS body text.
        db:          Active Database instance.
        brain:       The current Brain implementation.

    Returns:
        Reply SMS text (max 160 chars recommended).
    """
    from memory.queries import (
        create_user,
        delete_conversation_state,
        get_conversation_state,
        get_user_by_phone,
        set_conversation_state,
        update_user_preferences,
    )

    body_clean = body.strip()
    body_lower = body_clean.lower()

    # Hard stop: user wants to unsubscribe
    if body_lower in _STOP_KEYWORDS:
        _deactivate_user(from_number, db)
        delete_conversation_state(db, from_number)
        logger.info("User %s unsubscribed via STOP.", from_number)
        return "You've been unsubscribed from Wamoyager. Text SETUP to re-enroll anytime."

    # Load current conversation state
    conv_state = get_conversation_state(db, from_number)
    if conv_state is None:
        conv_state = {"step": "new", "data": {}}

    # Force restart on setup keywords
    if body_lower in _SETUP_KEYWORDS:
        conv_state = {"step": "new", "data": {}}

    # Delegate to brain
    result = brain.handle_inbound_sms(
        from_number=from_number,
        body=body_clean,
        conv_state=conv_state,
    )

    # Merge data update into stored state
    merged_data: dict = {**conv_state.get("data", {}), **result.data_update}

    if result.setup_complete:
        # Create user in the DB
        name = merged_data.get("name", "Rider")
        station_codes = merged_data.get("station_codes", [])
        lines = merged_data.get("lines", [])
        direction = merged_data.get("direction", [])

        try:
            user_id = create_user(db, name=name, phone_e164=from_number)
            update_user_preferences(
                db,
                user_id=user_id,
                station_codes=station_codes,
                lines=lines,
                direction=direction,
                daily_enabled=True,
            )
            logger.info(
                "New user created via SMS setup: id=%d name=%s phone=%s",
                user_id, name, from_number,
            )
        except Exception:
            logger.exception("Failed to create user for %s during setup completion.", from_number)
            return "Sorry, something went wrong saving your info. Please text SETUP to try again."

        delete_conversation_state(db, from_number)
    else:
        set_conversation_state(db, from_number, step=result.next_step, data=merged_data)

    return result.reply


def _deactivate_user(phone_e164: str, db: "Database") -> None:
    """Set active=0 for the user with this phone number, if they exist."""
    try:
        from memory.queries import get_user_by_phone, deactivate_user
        user = get_user_by_phone(db, phone_e164)
        if user:
            deactivate_user(db, user.id)
    except Exception:
        logger.exception("Error deactivating user %s on STOP.", phone_e164)
