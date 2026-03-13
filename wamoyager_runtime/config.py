"""Environment-variable based configuration using python-dotenv."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (two levels up from this file)
_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env", override=False)


def _get(key: str, default: str | None = None, required: bool = False) -> str:
    value = os.environ.get(key, default)
    if required and not value:
        raise EnvironmentError(
            f"Required environment variable {key!r} is not set. "
            "Check your .env file or environment."
        )
    return value or ""


class Config:
    """Central config object. Reads all settings from the environment."""

    # WMATA
    WMATA_API_KEY: str = _get("WMATA_API_KEY", required=True)

    # Mailgun SMTP
    MAILGUN_SMTP_LOGIN: str = _get("MAILGUN_SMTP_LOGIN", required=True)
    MAILGUN_SMTP_PASSWORD: str = _get("MAILGUN_SMTP_PASSWORD", required=True)
    MAILGUN_FROM_ADDRESS: str = _get("MAILGUN_FROM_ADDRESS", required=True)
    MAILGUN_FROM_NAME: str = _get("MAILGUN_FROM_NAME", default="Wamoyager")

    # Database
    DATABASE_PATH: str = _get("DATABASE_PATH", default="./wamoyager.db")

    # Behaviour
    DRY_RUN: bool = _get("DRY_RUN", default="false").lower() in ("1", "true", "yes")
    POLL_INTERVAL_SECONDS: int = int(_get("POLL_INTERVAL_SECONDS", default="120"))
    DAILY_JOB_TIME: str = _get("DAILY_JOB_TIME", default="17:00")
    RATE_LIMIT_MAX_PER_HOUR: int = int(_get("RATE_LIMIT_MAX_PER_HOUR", default="3"))
    COOLDOWN_MINUTES: int = int(_get("COOLDOWN_MINUTES", default="30"))

    # Inbound SMS webhook
    WEBHOOK_ENABLED: bool = _get("WEBHOOK_ENABLED", default="true").lower() in ("1", "true", "yes")
    WEBHOOK_PORT: int = int(_get("WEBHOOK_PORT", default="8080"))

    # Logging
    LOG_LEVEL: str = _get("LOG_LEVEL", default="INFO").upper()

    def __repr__(self) -> str:
        return (
            f"Config(DRY_RUN={self.DRY_RUN}, "
            f"POLL_INTERVAL_SECONDS={self.POLL_INTERVAL_SECONDS}, "
            f"DAILY_JOB_TIME={self.DAILY_JOB_TIME!r}, "
            f"DATABASE_PATH={self.DATABASE_PATH!r}, "
            f"MAILGUN_FROM_ADDRESS={self.MAILGUN_FROM_ADDRESS!r}, "
            f"WEBHOOK_ENABLED={self.WEBHOOK_ENABLED}, "
            f"WEBHOOK_PORT={self.WEBHOOK_PORT}, "
            f"LOG_LEVEL={self.LOG_LEVEL!r})"
        )


def load_config() -> Config:
    """Return a fully-validated Config instance."""
    return Config()
