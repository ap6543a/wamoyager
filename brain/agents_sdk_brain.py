"""OpenAI Agents SDK brain — production implementation.

Two-agent pipeline:
    IncidentClassifier — decides notify / urgency / audience using targeted DB tools
    MessageComposer    — writes the SMS with a 160-char output guardrail

Swap in via wamoyager_runtime/main.py:
    from brain.agents_sdk_brain import AgentsSdkBrain
    brain = AgentsSdkBrain(db)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from agents import (
    Agent,
    GuardrailFunctionOutput,
    OutputGuardrailTripwireTriggered,
    Runner,
    RunContextWrapper,
    function_tool,
    output_guardrail,
)
from pydantic import BaseModel

from brain.interface import BrainInterface, DailyMessageResult, IncidentDecision

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structured output models
# ---------------------------------------------------------------------------

class ClassifierOutput(BaseModel):
    notify: bool
    urgency_level: str          # INFO | MINOR | MAJOR | CRITICAL
    audience_user_ids: list[int]
    rationale: str


class ComposerOutput(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Output guardrail — trips if message exceeds 160 chars
# ---------------------------------------------------------------------------

@output_guardrail
def sms_length_guardrail(
    ctx: RunContextWrapper, agent: Agent, output: ComposerOutput
) -> GuardrailFunctionOutput:
    """Trips when the composed message would exceed the SMS character limit."""
    return GuardrailFunctionOutput(
        output_info=output,
        tripwire_triggered=len(output.message) > 160,
    )


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_CLASSIFIER_PROMPT = """
You are the IncidentClassifier for Wamoyager, a WMATA Metrorail commute alert system.

Your job is to evaluate a Metro incident and decide:
1. Whether commuters should be notified at all
2. The urgency level
3. Which subscribed users are actually affected

URGENCY LEVELS:
    CRITICAL — station closure, total line suspension, safety incident
    MAJOR    — significant delay (>10 min), single-tracking, major disruption
    MINOR    — minor delay (<10 min), slow speeds, partial disruption
    INFO     — informational only, no immediate impact

NOTIFICATION RULES:
    - Only notify if urgency is MAJOR or CRITICAL
    - Only include users whose subscribed lines overlap with lines_affected
    - Users with no line preference should be included for CRITICAL only
    - Do NOT notify for an incident already in recent history at the same or higher severity
    - Use your tools to check per-user notification history and line severity trends
      before finalizing your decision
""".strip()

_COMPOSER_PROMPT = """
You are the MessageComposer for Wamoyager, a WMATA Metrorail commute alert system.

Your job is to write concise, clear SMS messages for Metro commuters.

STRICT RULES:
    - Maximum 155 characters (hard SMS limit is 160; leave margin)
    - Always name the affected line (e.g. "Red Line", "Blue Line")
    - Include estimated delay or impact if known
    - For daily messages: greet by first name, list up to 3 trains (line, destination, min away)
    - Include exactly one emoji
    - Daily messages on weekdays only (Mon–Fri)

FORMAT:
    Incident alert  → "[MAJOR] Red Line: 15 min delays, single-tracking at Farragut. 🚇"
    Daily message   → "Hi Alice! 🚇 Red: Shady Grove 3 min, 11 min. No alerts."
""".strip()


# ---------------------------------------------------------------------------
# Brain
# ---------------------------------------------------------------------------

class AgentsSdkBrain(BrainInterface):
    """Production AI brain backed by the OpenAI Agents SDK.

    Two-agent pipeline:
        IncidentClassifier — decides notify/urgency/audience using targeted DB tools
        MessageComposer    — writes the SMS with a 160-char output guardrail
    """

    def __init__(self, db) -> None:
        self._db = db
        tools = self._build_tools()

        self._classifier_agent = Agent(
            name="IncidentClassifier",
            instructions=_CLASSIFIER_PROMPT,
            tools=tools,
            output_type=ClassifierOutput,
            model="gpt-4.1-nano",
        )

        self._composer_agent = Agent(
            name="MessageComposer",
            instructions=_COMPOSER_PROMPT,
            output_type=ComposerOutput,
            output_guardrails=[sms_length_guardrail],
            model="gpt-4.1-nano",
        )

    # -----------------------------------------------------------------------
    # Tool factory — closures over self._db; no globals, no thread-safety issues
    # -----------------------------------------------------------------------

    def _build_tools(self) -> list:
        db = self._db

        @function_tool
        def read_agent_state(key: str) -> str:
            """Read a value from persistent agent memory by key."""
            from memory.queries import get_agent_state
            try:
                return get_agent_state(db, key) or ""
            except Exception as exc:
                logger.warning("read_agent_state(%r) failed: %s", key, exc)
                return ""

        @function_tool
        def write_agent_state(key: str, value: str) -> str:
            """Write a value to persistent agent memory."""
            from memory.queries import set_agent_state
            try:
                set_agent_state(db, key, value)
                return "ok"
            except Exception as exc:
                logger.warning("write_agent_state(%r) failed: %s", key, exc)
                return f"error: {exc}"

        @function_tool
        def lookup_station_name(station_code: str) -> str:
            """Convert a WMATA station code (e.g. A01) to a human-readable station name."""
            stations = {
                "A01": "Metro Center", "A02": "Farragut North", "A03": "Dupont Circle",
                "A04": "Woodley Park-Zoo/Adams Morgan", "A05": "Cleveland Park",
                "A06": "Van Ness-UDC", "A07": "Tenleytown-AU", "A08": "Friendship Heights",
                "A09": "Bethesda", "A10": "Medical Center", "A11": "Grosvenor-Strathmore",
                "A12": "North Bethesda", "A13": "Twinbrook", "A14": "Rockville",
                "A15": "Shady Grove",
                "B01": "Gallery Pl-Chinatown", "B02": "Judiciary Square",
                "B03": "Union Station", "B04": "Rhode Island Ave-Brentwood",
                "B05": "Brookland-CUA", "B06": "Fort Totten", "B07": "Takoma",
                "B08": "Silver Spring", "B09": "Forest Glen", "B10": "Wheaton",
                "B11": "Glenmont", "B35": "NoMa-Gallaudet U",
                "C01": "Metro Center", "C02": "McPherson Square", "C03": "Farragut West",
                "C04": "Foggy Bottom-GWU", "C05": "Rosslyn", "C06": "Arlington Cemetery",
                "C07": "Pentagon", "C08": "Pentagon City", "C09": "Crystal City",
                "C10": "DCA", "C11": "Potomac Yard", "C12": "Braddock Road",
                "C13": "King St-Old Town", "C14": "Eisenhower Avenue", "C15": "Huntington",
                "D01": "Federal Triangle", "D02": "Smithsonian", "D03": "L'Enfant Plaza",
                "D04": "Federal Center SW", "D05": "Capitol South", "D06": "Eastern Market",
                "D07": "Potomac Ave", "D08": "Stadium-Armory", "D09": "Minnesota Ave",
                "D10": "Deanwood", "D11": "Cheverly", "D12": "Landover",
                "D13": "New Carrollton",
                "E01": "Mt Vernon Sq 7th St-Convention Center", "E02": "Shaw-Howard U",
                "E03": "U Street/African-Amer Civil War Memorial/Cardozo",
                "E04": "Columbia Heights", "E05": "Georgia Ave-Petworth",
                "E06": "Fort Totten", "E07": "West Hyattsville",
                "E08": "Hyattsville Crossing", "E09": "College Park-U of Md",
                "E10": "Greenbelt",
                "F01": "Gallery Pl-Chinatown",
                "F02": "Archives-Navy Memorial-Penn Quarter",
                "F03": "L'Enfant Plaza", "F04": "Waterfront",
                "F05": "Navy Yard-Ballpark", "F06": "Anacostia",
                "F07": "Congress Heights", "F08": "Southern Avenue",
                "F09": "Naylor Road", "F10": "Suitland", "F11": "Branch Ave",
                "G01": "Benning Road", "G02": "Capitol Heights",
                "G03": "Addison Road-Seat Pleasant", "G04": "Morgan Boulevard",
                "G05": "Downtown Largo",
                "J02": "Van Dorn Street", "J03": "Franconia-Springfield",
                "K01": "Court House", "K02": "Clarendon", "K03": "Virginia Square-GMU",
                "K04": "Ballston-MU", "K05": "East Falls Church",
                "K06": "West Falls Church", "K07": "Dunn Loring-Merrifield",
                "K08": "Vienna/Fairfax-GMU",
                "N01": "McLean", "N02": "Tysons", "N03": "Greensboro",
                "N04": "Spring Hill", "N06": "Wiehle-Reston East",
                "N07": "Reston Town Center", "N08": "Herndon",
                "N09": "Innovation Center",
                "N10": "Washington Dulles International Airport",
                "N11": "Loudoun Gateway", "N12": "Ashburn",
            }
            return stations.get(station_code.upper(), f"Station {station_code}")

        @function_tool
        def get_notification_history_for_user(user_id: int, hours: int = 24) -> str:
            """Get recent notifications sent to a user (last N hours).
            Returns a JSON list of {type, body snippet, sent_at}."""
            from memory.queries import get_notifications_for_user_since
            try:
                since = datetime.now(timezone.utc) - timedelta(hours=hours)
                notifications = get_notifications_for_user_since(db, user_id, since)
                if not notifications:
                    return "[]"
                return json.dumps([
                    {"type": n.type, "body": n.body[:80], "sent_at": str(n.created_at)}
                    for n in notifications[:10]
                ])
            except Exception as exc:
                logger.warning("get_notification_history_for_user(%d) failed: %s", user_id, exc)
                return "[]"

        @function_tool
        def get_line_severity_trend(line_code: str) -> str:
            """Get recent incident severity history for a Metro line.
            Returns a JSON list of the last 5 incidents with title, severity, and first_seen."""
            from memory.queries import get_recent_incidents
            try:
                incidents = get_recent_incidents(db, limit=20)
                relevant = [
                    {
                        "title": i.normalized_json.get("title", ""),
                        "severity": i.severity,
                        "first_seen": str(i.first_seen),
                    }
                    for i in incidents
                    if line_code.upper() in (i.normalized_json.get("lines_affected") or [])
                ]
                if not relevant:
                    return f"No recent incidents for {line_code}."
                return json.dumps(relevant[-5:])
            except Exception as exc:
                logger.warning("get_line_severity_trend(%r) failed: %s", line_code, exc)
                return "[]"

        @function_tool
        def get_active_incident_count() -> str:
            """Return the number of incidents active in the last 2 hours."""
            from memory.queries import get_recent_incidents
            try:
                incidents = get_recent_incidents(db, limit=50)
                cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
                active = [i for i in incidents if i.last_seen >= cutoff]
                return str(len(active))
            except Exception as exc:
                logger.warning("get_active_incident_count failed: %s", exc)
                return "0"

        return [
            read_agent_state,
            write_agent_state,
            lookup_station_name,
            get_notification_history_for_user,
            get_line_severity_trend,
            get_active_incident_count,
        ]

    # -----------------------------------------------------------------------
    # BrainInterface implementation
    # -----------------------------------------------------------------------

    def decide_incident(
        self,
        incident: dict[str, Any],
        users_relevant: list[dict[str, Any]],
        history_recent: list[dict[str, Any]],
    ) -> IncidentDecision:
        try:
            # Step 1: Classifier decides notify / urgency / audience
            classifier_prompt = (
                f"INCIDENT:\n{json.dumps(incident, indent=2)}\n\n"
                f"SUBSCRIBED USERS:\n{json.dumps(users_relevant, indent=2)}\n\n"
                f"RECENT INCIDENT HISTORY (last 10):\n{json.dumps(history_recent[-10:], indent=2)}\n\n"
                "Classify this incident and select the affected audience."
            )
            classification: ClassifierOutput = Runner.run_sync(
                self._classifier_agent, classifier_prompt
            ).final_output

            if not classification.notify:
                logger.info(
                    "Classifier suppressed notification: urgency=%s reason=%r",
                    classification.urgency_level,
                    classification.rationale,
                )
                return IncidentDecision(
                    notify=False,
                    urgency_level=classification.urgency_level,
                    audience_user_ids=[],
                    messages={},
                    message_all=None,
                )

            # Step 2: Composer writes the SMS for the selected audience
            audience = [u for u in users_relevant if u["id"] in classification.audience_user_ids]
            composer_prompt = (
                f"Write a {classification.urgency_level} incident alert SMS.\n\n"
                f"INCIDENT:\n{json.dumps(incident, indent=2)}\n\n"
                f"AUDIENCE ({len(audience)} user(s) — "
                f"{', '.join(u['name'] for u in audience)}):\n"
                f"{json.dumps(audience, indent=2)}"
            )
            try:
                message = Runner.run_sync(
                    self._composer_agent, composer_prompt
                ).final_output.message
            except OutputGuardrailTripwireTriggered as exc:
                raw: ComposerOutput = exc.guardrail_result.output.output_info
                message = raw.message[:159] + "…"
                logger.warning("Incident message truncated to %d chars", len(message))

            return IncidentDecision(
                notify=True,
                urgency_level=classification.urgency_level,
                audience_user_ids=classification.audience_user_ids,
                messages={},
                message_all=message,
            )

        except Exception as exc:
            logger.error("decide_incident failed: %s", exc, exc_info=True)
            return IncidentDecision(
                notify=False,
                urgency_level="INFO",
                audience_user_ids=[],
                messages={},
                message_all=None,
            )

    def compose_daily_message(
        self,
        user: dict[str, Any],
        predictions: list[dict[str, Any]],
        system_status_summary: str | None,
    ) -> DailyMessageResult:
        try:
            prompt = (
                f"USER:\n{json.dumps(user, indent=2)}\n\n"
                f"UPCOMING TRAINS:\n{json.dumps(predictions, indent=2)}\n\n"
                f"SYSTEM STATUS: {system_status_summary or 'No active alerts.'}\n\n"
                "Compose the daily 5pm commute SMS for this user."
            )
            try:
                message = Runner.run_sync(
                    self._composer_agent, prompt
                ).final_output.message
            except OutputGuardrailTripwireTriggered as exc:
                raw: ComposerOutput = exc.guardrail_result.output.output_info
                message = raw.message[:159] + "…"
                logger.warning("Daily message truncated to %d chars", len(message))

            return DailyMessageResult(message=message)

        except Exception as exc:
            logger.error("compose_daily_message failed: %s", exc, exc_info=True)
            return DailyMessageResult(
                message="Metro update unavailable. Check wmata.com for service alerts."
            )
