"""APScheduler-based job scheduler for poll, daily, and housekeeping jobs."""

from __future__ import annotations

import logging
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import pytz

logger = logging.getLogger(__name__)

_ET = pytz.timezone("America/New_York")


class WamoyagerScheduler:
    """Manages the three recurring jobs: poll, daily, and housekeeping."""

    def __init__(
        self,
        poll_job: Callable[[], None],
        daily_job: Callable[[], None],
        housekeeping_job: Callable[[], None],
        poll_interval_seconds: int = 120,
        daily_job_time: str = "17:00",
    ) -> None:
        self._poll_job = poll_job
        self._daily_job = daily_job
        self._housekeeping_job = housekeeping_job
        self._poll_interval_seconds = poll_interval_seconds
        self._daily_job_time = daily_job_time

        self._scheduler = BackgroundScheduler(timezone="UTC")

    def start(self) -> None:
        """Register all jobs and start the scheduler."""
        hour, minute = self._parse_time(self._daily_job_time)

        # Poll job: every N seconds
        self._scheduler.add_job(
            self._poll_job,
            trigger=IntervalTrigger(seconds=self._poll_interval_seconds),
            id="poll_job",
            name="WMATA poll",
            replace_existing=True,
            misfire_grace_time=30,
        )
        logger.info("Poll job scheduled every %ds", self._poll_interval_seconds)

        # Daily job: cron at configured time in ET
        self._scheduler.add_job(
            self._daily_job,
            trigger=CronTrigger(
                hour=hour, minute=minute, timezone=_ET
            ),
            id="daily_job",
            name=f"Daily {self._daily_job_time} ET message",
            replace_existing=True,
            misfire_grace_time=300,
        )
        logger.info("Daily job scheduled at %s ET", self._daily_job_time)

        # Housekeeping: daily at 02:00 ET
        self._scheduler.add_job(
            self._housekeeping_job,
            trigger=CronTrigger(hour=2, minute=0, timezone=_ET),
            id="housekeeping_job",
            name="Housekeeping 02:00 ET",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info("Housekeeping job scheduled at 02:00 ET")

        self._scheduler.start()
        logger.info("Scheduler started.")

    def stop(self) -> None:
        """Shut down the scheduler gracefully."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=True)
            logger.info("Scheduler stopped.")

    @staticmethod
    def _parse_time(time_str: str) -> tuple[int, int]:
        """Parse "HH:MM" into (hour, minute) ints."""
        parts = time_str.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid time format {time_str!r}; expected HH:MM")
        return int(parts[0]), int(parts[1])
