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

    # Twilio
    TWILIO_ACCOUNT_SID: str = _get("TWILIO_ACCOUNT_SID", required=True)
    TWILIO_AUTH_TOKEN: str = _get("TWILIO_AUTH_TOKEN", required=True)
    TWILIO_FROM_NUMBER: str = _get("TWILIO_FROM_NUMBER", required=True)

    # Database
    DATABASE_PATH: str = _get("DATABASE_PATH", default="./wamoyager.db")

    # Behaviour
    DRY_RUN: bool = _get("DRY_RUN", default="false").lower() in ("1", "true", "yes")
    POLL_INTERVAL_SECONDS: int = int(_get("POLL_INTERVAL_SECONDS", default="120"))
    DAILY_JOB_TIME: str = _get("DAILY_JOB_TIME", default="17:00")
    RATE_LIMIT_MAX_PER_HOUR: int = int(_get("RATE_LIMIT_MAX_PER_HOUR", default="3"))
    COOLDOWN_MINUTES: int = int(_get("COOLDOWN_MINUTES", default="30"))

    # Logging
    LOG_LEVEL: str = _get("LOG_LEVEL", default="INFO").upper()

    def __repr__(self) -> str:
        return (
            f"Config(DRY_RUN={self.DRY_RUN}, "
            f"POLL_INTERVAL_SECONDS={self.POLL_INTERVAL_SECONDS}, "
            f"DAILY_JOB_TIME={self.DAILY_JOB_TIME!r}, "
            f"DATABASE_PATH={self.DATABASE_PATH!r}, "
            f"LOG_LEVEL={self.LOG_LEVEL!r})"
        )


def load_config() -> Config:
    """Return a fully-validated Config instance."""
    return Config()
