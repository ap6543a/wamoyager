"""Mailgun SMTP notifier — sends messages to user email addresses.

Mailgun SMTP credentials are found in the Mailgun dashboard under
Sending → Domain Settings → SMTP credentials.

  MAILGUN_SMTP_LOGIN:    your Mailgun SMTP username (e.g. postmaster@mg.yourdomain.com)
  MAILGUN_SMTP_PASSWORD: your Mailgun SMTP password
  MAILGUN_FROM_ADDRESS:  the From address (must be authorised in your Mailgun domain)
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

_MAX_RETRIES = 2
_RETRY_SLEEP_SECONDS = 2
_MAILGUN_SMTP_HOST = "smtp.mailgun.org"
_MAILGUN_SMTP_PORT = 587


class EmailNotifier:
    """Send messages via Mailgun SMTP."""

    def __init__(
        self,
        smtp_login: str,
        smtp_password: str,
        from_address: str,
        from_name: str,
        db: "Database",
        dry_run: bool = False,
    ) -> None:
        self._smtp_login = smtp_login
        self._smtp_password = smtp_password
        self._from_address = from_address
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
        """Send a message to a user email address and log it.

        Args:
            to: User email address.
            body: Message text.
            user_id: DB user id for logging.
            incident_id: Optional associated incident id.
            notification_type: "incident" or "daily".

        Returns:
            "sent", "DRY_RUN", or "" on failure.
        """
        from memory.queries import log_notification, update_notification_status

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
                msg["From"] = f"{self._from_name} <{self._from_address}>"
                msg["To"] = to
                msg["Subject"] = "Wamoyager Alert"

                with smtplib.SMTP(_MAILGUN_SMTP_HOST, _MAILGUN_SMTP_PORT) as server:
                    server.starttls()
                    server.login(self._smtp_login, self._smtp_password)
                    server.sendmail(self._from_address, to, msg.as_string())
                return True
            except Exception as exc:
                last_error = exc
                logger.warning("Send attempt %d failed for %s: %s", attempt, to, exc)
                if attempt <= _MAX_RETRIES:
                    time.sleep(_RETRY_SLEEP_SECONDS)

        logger.error("All send attempts failed for %s. Last error: %s", to, last_error)
        return False
