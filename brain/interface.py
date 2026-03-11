"""Brain contract: abstract base class that all brain implementations must satisfy."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class InboundSmsResult:
    """Returned by handle_inbound_sms; drives the conversation forward."""
    reply: str                  # the SMS text to send back to the user
    next_step: str              # new conversation step to store (e.g. "awaiting_name")
    data_update: dict           # partial data to merge into conversation state
    setup_complete: bool = False  # when True, Runtime creates the user in the DB


@dataclass
class IncidentDecision:
    notify: bool
    urgency_level: str  # INFO | MINOR | MAJOR | CRITICAL
    audience_user_ids: list[int]
    messages: dict[int, str]    # user_id → sms text
    message_all: str | None = None  # if set, use for all audience members instead of per-user messages


@dataclass
class DailyMessageResult:
    message: str


class BrainInterface(ABC):
    """Contract that both StubBrain and AgentsSdkBrain must implement.

    Rule: the Brain only decides *what to say* and *who to notify*.
    All side effects (Twilio sends, DB writes) are performed by the Runtime.
    """

    @abstractmethod
    def handle_inbound_sms(
        self,
        from_number: str,
        body: str,
        conv_state: dict[str, Any],
    ) -> InboundSmsResult:
        """Handle one inbound SMS message and drive the setup conversation.

        Args:
            from_number: E.164 number of the sender (e.g. "+12025551234").
            body:        Cleaned SMS body text.
            conv_state:  Current state dict with keys "step" and "data".
                         "step" is the current position in the setup flow.
                         "data" holds collected values so far (name, station_codes, etc.)

        Returns:
            InboundSmsResult with reply text, next step, data updates,
            and a setup_complete flag to trigger user creation.
        """
        ...

    @abstractmethod
    def decide_incident(
        self,
        incident: dict[str, Any],
        users_relevant: list[dict[str, Any]],
        history_recent: list[dict[str, Any]],
    ) -> IncidentDecision:
        """Decide whether and how to notify users about an incident.

        Args:
            incident: normalized incident dict (from NormalizedIncident.to_dict())
            users_relevant: list of active user dicts with their preferences
            history_recent: recent notification history for dedup context

        Returns:
            IncidentDecision with notify flag, urgency, audience, and per-user messages.
        """
        ...

    @abstractmethod
    def compose_daily_message(
        self,
        user: dict[str, Any],
        predictions: list[dict[str, Any]],
        system_status_summary: str | None,
    ) -> DailyMessageResult:
        """Compose the daily 5pm next-train message for a user.

        Args:
            user: user dict merged with preferences
            predictions: list of NormalizedPrediction dicts for user's stations
            system_status_summary: optional brief system-wide status string

        Returns:
            DailyMessageResult with the SMS text.
        """
        ...
