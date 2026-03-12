"""Gmail SMTP notifier — sends messages to email-to-SMS gateway addresses.

Each user's `email` field should be their carrier gateway address, e.g.:
  2025551234@tmomail.net      (T-Mobile)
  2025551234@vtext.com        (Verizon)
  2025551234@txt.att.net      (AT&T)
  2025551234@messaging.sprintpcs.com  (Sprint)

Gmail requires an App Password (not your normal password):
  Google Account → Security → 2-Step Verification → App Passwords
"""

from __future__ import annotations

import logging
import smtplib
import time
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memory.db import Database

logger = logging.getLogger(__name__)

_MAX_SMS_CHARS = 160
_MAX_RETRIES = 2
_RETRY_SLEEP_SECONDS = 2
_GMAIL_SMTP_HOST = "smtp.gmail.com"
_GMAIL_SMTP_PORT = 465


def _truncate(body: str) -> str:
    if len(body) <= _MAX_SMS_CHARS:
        return body
    return body[: _MAX_SMS_CHARS - 1] + "…"


class EmailNotifier:
    """Send messages via Gmail SMTP to carrier email-to-SMS gateway addresses."""

    def __init__(
        self,
        gmail_address: str,
        app_password: str,
        from_name: str,
        db: "Database",
        dry_run: bool = False,
    ) -> None:
        self._gmail_address = gmail_address
        self._app_password = app_password
        self._from_name = from_name
        self._db = db
        self._dry_run = dry_run

    def send_sms(
        self,
        to: str,
        body: str,
        user_id: int,
        incident_id: int | None = None,
        notification_type: str = "incident",
    ) -> str:
        """Send a message to a gateway email address and log it.

        Args:
            to: Carrier gateway email, e.g. "2025551234@tmomail.net".
            body: Message text (truncated to 160 chars).
            user_id: DB user id for logging.
            incident_id: Optional associated incident id.
            notification_type: "incident" or "daily".

        Returns:
            "sent", "DRY_RUN", or "" on failure.
        """
        from memory.queries import log_notification, update_notification_status

        body = _truncate(body)

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
                "[DRY RUN] Would send to %s (user_id=%d): %s",
                to, user_id, body,
            )
            return "DRY_RUN"

        success = self._send_with_retry(to, body)

        if success:
            update_notification_status(self._db, notification_id, status="sent", provider_id=None)
            logger.info("Message sent to %s (user_id=%d)", to, user_id)
            return "sent"
        else:
            update_notification_status(self._db, notification_id, status="failed")
            logger.error("Message failed to send to %s (user_id=%d)", to, user_id)
            return ""

    def _send_with_retry(self, to: str, body: str) -> bool:
        last_error: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 2):
            try:
                msg = MIMEText(body)
                msg["From"] = f"{self._from_name} <{self._gmail_address}>"
                msg["To"] = to
                msg["Subject"] = ""  # SMS gateways ignore the subject line

                with smtplib.SMTP_SSL(_GMAIL_SMTP_HOST, _GMAIL_SMTP_PORT) as server:
                    server.login(self._gmail_address, self._app_password)
                    server.sendmail(self._gmail_address, to, msg.as_string())
                return True
            except Exception as exc:
                last_error = exc
                logger.warning("Send attempt %d failed for %s: %s", attempt, to, exc)
                if attempt <= _MAX_RETRIES:
                    time.sleep(_RETRY_SLEEP_SECONDS)

        logger.error("All send attempts failed for %s. Last error: %s", to, last_error)
        return False
