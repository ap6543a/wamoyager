"""Twilio SMS notifier with retries, logging, and dry-run support."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memory.db import Database

logger = logging.getLogger(__name__)

_MAX_SMS_CHARS = 160
_MAX_RETRIES = 2
_RETRY_SLEEP_SECONDS = 2


def _truncate(body: str) -> str:
    if len(body) <= _MAX_SMS_CHARS:
        return body
    return body[: _MAX_SMS_CHARS - 1] + "…"


class TwilioNotifier:
    """Send SMS messages via Twilio with retry logic and notification logging."""

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
        db: "Database",
        dry_run: bool = False,
    ) -> None:
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number
        self._db = db
        self._dry_run = dry_run
        self._client = None  # lazy init to avoid import cost if not needed

    def _get_client(self) -> object:
        if self._client is None:
            from twilio.rest import Client  # type: ignore[import]
            self._client = Client(self._account_sid, self._auth_token)
        return self._client

    def send_sms(
        self,
        to: str,
        body: str,
        user_id: int,
        incident_id: int | None = None,
        notification_type: str = "incident",
    ) -> str:
        """Send an SMS and log it to the notifications table.

        Args:
            to: E.164 phone number, e.g. "+12025551234".
            body: Message text (will be truncated to 160 chars).
            user_id: DB user id for logging.
            incident_id: Optional associated incident id.
            notification_type: "incident" or "daily".

        Returns:
            Twilio message SID, or "DRY_RUN" in dry-run mode.
        """
        from memory.queries import log_notification, update_notification_status

        body = _truncate(body)

        # Pre-insert as pending
        notification_id = log_notification(
            db=self._db,
            user_id=user_id,
            body=body,
            notification_type=notification_type,
            status="dry_run" if self._dry_run else "pending",
            incident_id=incident_id,
        )

        if self._dry_run:
            logger.info(
                "[DRY RUN] Would send SMS to %s (user_id=%d): %s",
                to,
                user_id,
                body,
            )
            return "DRY_RUN"

        provider_sid = self._send_with_retry(to, body)

        if provider_sid:
            update_notification_status(
                self._db, notification_id, status="sent", provider_id=provider_sid
            )
            logger.info(
                "SMS sent to %s (user_id=%d) sid=%s", to, user_id, provider_sid
            )
        else:
            update_notification_status(self._db, notification_id, status="failed")
            logger.error("SMS failed to send to %s (user_id=%d)", to, user_id)

        return provider_sid or ""

    def _send_with_retry(self, to: str, body: str) -> str | None:
        """Attempt to send via Twilio, retrying up to _MAX_RETRIES times."""
        client = self._get_client()
        last_error: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 2):  # 1 initial + 2 retries
            try:
                message = client.messages.create(  # type: ignore[union-attr]
                    body=body,
                    from_=self._from_number,
                    to=to,
                )
                return message.sid
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Twilio send attempt %d failed for %s: %s",
                    attempt,
                    to,
                    exc,
                )
                if attempt <= _MAX_RETRIES:
                    time.sleep(_RETRY_SLEEP_SECONDS)

        logger.error(
            "All %d Twilio send attempts failed for %s. Last error: %s",
            _MAX_RETRIES + 1,
            to,
            last_error,
        )
        return None
