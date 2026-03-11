"""OpenAI Agents SDK brain — placeholder for team build session.

This module will be implemented during the team session to replace StubBrain.
All methods raise NotImplementedError until then.
"""

from __future__ import annotations

from typing import Any

from brain.interface import BrainInterface, DailyMessageResult, IncidentDecision


class AgentsSdkBrain(BrainInterface):
    """Agent brain backed by the OpenAI Agents SDK.

    TODO (team session):
    1. Add OpenAI Agents SDK client + agent definition.
    2. Write instruction prompt covering urgency rules and message style.
    3. Define tools: read_memory, write_memory, fetch_wmata_details, format_sms.
    4. Implement decide_incident to return structured IncidentDecision JSON.
    5. Implement compose_daily_message to produce a friendly SMS.
    """

    def decide_incident(
        self,
        incident: dict[str, Any],
        users_relevant: list[dict[str, Any]],
        history_recent: list[dict[str, Any]],
    ) -> IncidentDecision:
        raise NotImplementedError(
            "AgentsSdkBrain.decide_incident is not yet implemented. "
            "Use StubBrain for pre-session runs."
        )

    def compose_daily_message(
        self,
        user: dict[str, Any],
        predictions: list[dict[str, Any]],
        system_status_summary: str | None,
    ) -> DailyMessageResult:
        raise NotImplementedError(
            "AgentsSdkBrain.compose_daily_message is not yet implemented. "
            "Use StubBrain for pre-session runs."
        )
