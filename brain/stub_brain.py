"""Stub (deterministic rule-based) brain — used before the AI session.

Rules:
- Incidents: notify if severity is MAJOR or CRITICAL.
  Filter users by lines_affected matching subscribed lines (or all users if no line prefs).
  Compose a short SMS from title + severity.
- Daily message: pick next 1-3 predictions matching user's direction/line prefs;
  compose a human-friendly "Next trains from {station}: ..." message.
"""

from __future__ import annotations

import logging
from typing import Any

from brain.interface import BrainInterface, DailyMessageResult, IncidentDecision

logger = logging.getLogger(__name__)

_NOTIFY_SEVERITIES = {"MAJOR", "CRITICAL"}


class StubBrain(BrainInterface):
    """Deterministic rule-based brain for pre-session use."""

    # ------------------------------------------------------------------
    # Incident decision
    # ------------------------------------------------------------------

    def decide_incident(
        self,
        incident: dict[str, Any],
        users_relevant: list[dict[str, Any]],
        history_recent: list[dict[str, Any]],
    ) -> IncidentDecision:
        severity = incident.get("severity", "INFO")
        should_notify = severity in _NOTIFY_SEVERITIES

        if not should_notify:
            logger.debug(
                "StubBrain: skipping incident fingerprint=%s severity=%s",
                incident.get("fingerprint"),
                severity,
            )
            return IncidentDecision(
                notify=False,
                urgency_level=severity,
                audience_user_ids=[],
                messages={},
            )

        lines_affected: list[str] = incident.get("lines_affected", [])
        lines_affected_upper = {ln.upper() for ln in lines_affected}

        audience: list[dict[str, Any]] = []
        for user in users_relevant:
            prefs = user.get("preferences", {})
            subscribed_lines: list[str] = prefs.get("lines", [])
            if not subscribed_lines:
                # No line preference → subscribe to everything
                audience.append(user)
            else:
                subscribed_upper = {ln.upper() for ln in subscribed_lines}
                if subscribed_upper & lines_affected_upper:
                    audience.append(user)

        audience_ids = [u["id"] for u in audience]

        # Compose a single message for all audience members
        title = incident.get("title", "Service Alert")
        lines_str = ", ".join(lines_affected) if lines_affected else "Multiple lines"
        message_all = (
            f"[{severity}] WMATA Alert: {title} — Lines: {lines_str}. "
            "Check wmata.com for details."
        )
        # Truncate to 160 chars
        if len(message_all) > 160:
            message_all = message_all[:159] + "…"

        logger.info(
            "StubBrain: notifying %d users for incident fingerprint=%s severity=%s",
            len(audience_ids),
            incident.get("fingerprint"),
            severity,
        )

        return IncidentDecision(
            notify=bool(audience_ids),
            urgency_level=severity,
            audience_user_ids=audience_ids,
            messages={},
            message_all=message_all,
        )

    # ------------------------------------------------------------------
    # Daily message
    # ------------------------------------------------------------------

    def compose_daily_message(
        self,
        user: dict[str, Any],
        predictions: list[dict[str, Any]],
        system_status_summary: str | None,
    ) -> DailyMessageResult:
        prefs = user.get("preferences", {})
        preferred_lines: list[str] = [ln.upper() for ln in prefs.get("lines", [])]
        preferred_directions: list[str] = [d.upper() for d in prefs.get("direction", [])]
        station_codes: list[str] = prefs.get("station_codes", [])

        # Filter predictions to user's preferences
        filtered = [p for p in predictions if _matches_prefs(p, preferred_lines, preferred_directions)]
        if not filtered:
            filtered = predictions  # fall back to all if nothing matches

        # Sort by numeric minutes (ARR/BRD treated as 0)
        def sort_key(p: dict[str, Any]) -> int:
            mins = p.get("minutes", "999")
            if mins in ("ARR", "BRD"):
                return 0
            try:
                return int(mins)
            except (ValueError, TypeError):
                return 999

        filtered_sorted = sorted(filtered, key=sort_key)
        top = filtered_sorted[:3]

        name = user.get("name", "Rider")
        station_label = station_codes[0] if station_codes else "your station"

        if not top:
            message = f"Hi {name}! No upcoming trains found for {station_label} right now."
        else:
            trains_str = "; ".join(_format_prediction(p) for p in top)
            message = f"Hi {name}! Next trains from {station_label}: {trains_str}."

        if system_status_summary:
            suffix = f" Status: {system_status_summary}"
            # Only append if it fits
            if len(message) + len(suffix) <= 160:
                message += suffix

        if len(message) > 160:
            message = message[:159] + "…"

        return DailyMessageResult(message=message)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _matches_prefs(
    prediction: dict[str, Any],
    preferred_lines: list[str],
    preferred_directions: list[str],
) -> bool:
    line_match = (
        not preferred_lines
        or prediction.get("line", "").upper() in preferred_lines
    )
    # Direction is the destination group; we do a simple substring match
    dest = prediction.get("destination", "").upper()
    dir_match = (
        not preferred_directions
        or any(d in dest for d in preferred_directions)
    )
    return line_match and dir_match


def _format_prediction(p: dict[str, Any]) -> str:
    line = p.get("line", "?")
    dest = p.get("destination", "Unknown")
    mins = p.get("minutes", "?")
    cars = p.get("car_count", "")
    if mins in ("ARR", "BRD"):
        time_str = mins
    else:
        time_str = f"{mins} min"
    car_str = f" ({cars} cars)" if cars and cars != "-" else ""
    return f"{line} to {dest} in {time_str}{car_str}"
