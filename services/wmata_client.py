"""WMATA API client with response normalization."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import httpx

from memory.models import NormalizedIncident, NormalizedPrediction

logger = logging.getLogger(__name__)

_INCIDENTS_URL = "https://api.wmata.com/Incidents.svc/json/Incidents"
_PREDICTIONS_URL = "https://api.wmata.com/StationPrediction.svc/json/GetPrediction/{station_codes}"

# Keyword sets for severity heuristics (checked in order)
_CRITICAL_KEYWORDS = {"major", "significant", "suspended", "no service", "emergency"}
_MAJOR_KEYWORDS = {"delay", "single tracking", "single-tracking", "reduced service"}
_MINOR_KEYWORDS = {"minor", "slow", "residual", "recovering"}


def _classify_severity(text: str) -> str:
    """Heuristic severity from incident title/description."""
    lower = text.lower()
    if any(kw in lower for kw in _CRITICAL_KEYWORDS):
        return "CRITICAL"
    if any(kw in lower for kw in _MAJOR_KEYWORDS):
        return "MAJOR"
    if any(kw in lower for kw in _MINOR_KEYWORDS):
        return "MINOR"
    return "INFO"


def _make_fingerprint(title: str, lines_affected: list[str]) -> str:
    """Stable fingerprint: sha256(title + sorted lines)."""
    key = title.strip().lower() + "|" + ",".join(sorted(ln.upper() for ln in lines_affected))
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def _normalize_incident(raw: dict[str, Any]) -> NormalizedIncident:
    """Convert a WMATA Incidents API entry to a NormalizedIncident."""
    title: str = raw.get("Description", "") or raw.get("IncidentType", "Service Alert")
    description: str = raw.get("Description", "")

    # LinesAffected is a string like "RD; BL; OR;" in the WMATA API
    lines_raw: str = raw.get("LinesAffected", "") or ""
    lines_affected = [ln.strip() for ln in lines_raw.split(";") if ln.strip()]

    # WMATA incidents don't always have specific station info at this endpoint
    stations_affected: list[str] = []

    severity = _classify_severity(title + " " + description)
    fingerprint = _make_fingerprint(title, lines_affected)

    return NormalizedIncident(
        fingerprint=fingerprint,
        title=title,
        description=description,
        lines_affected=lines_affected,
        stations_affected=stations_affected,
        severity=severity,
        raw=raw,
    )


def _normalize_prediction(raw: dict[str, Any]) -> NormalizedPrediction:
    """Convert a WMATA RealTimePredictions entry to a NormalizedPrediction."""
    return NormalizedPrediction(
        station_code=raw.get("LocationCode", ""),
        destination=raw.get("DestinationName", raw.get("Destination", "")),
        line=raw.get("Line", ""),
        minutes=str(raw.get("Min", "")),
        car_count=str(raw.get("Car", "")),
    )


class WmataClient:
    """Async WMATA API client."""

    def __init__(self, api_key: str, timeout: float = 15.0) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._headers = {"api_key": api_key}

    async def fetch_incidents(self) -> list[NormalizedIncident]:
        """Fetch and normalize all current WMATA rail incidents."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                response = await client.get(_INCIDENTS_URL, headers=self._headers)
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as exc:
                logger.error("WMATA incidents HTTP error: %s", exc)
                return []
            except httpx.RequestError as exc:
                logger.error("WMATA incidents request error: %s", exc)
                return []
            except Exception as exc:
                logger.error("WMATA incidents unexpected error: %s", exc)
                return []

        raw_incidents: list[dict[str, Any]] = data.get("Incidents", [])
        normalized = [_normalize_incident(r) for r in raw_incidents]
        logger.info("Fetched %d incidents from WMATA", len(normalized))
        return normalized

    async def fetch_predictions(
        self, station_codes: list[str]
    ) -> list[NormalizedPrediction]:
        """Fetch real-time train predictions for one or more station codes.

        Args:
            station_codes: list of WMATA station codes, e.g. ["A01", "C01"].
                           Pass ["All"] for all stations.
        """
        if not station_codes:
            return []

        codes_str = ",".join(station_codes)
        url = _PREDICTIONS_URL.format(station_codes=codes_str)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                response = await client.get(url, headers=self._headers)
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as exc:
                logger.error("WMATA predictions HTTP error: %s", exc)
                return []
            except httpx.RequestError as exc:
                logger.error("WMATA predictions request error: %s", exc)
                return []
            except Exception as exc:
                logger.error("WMATA predictions unexpected error: %s", exc)
                return []

        raw_trains: list[dict[str, Any]] = data.get("Trains", [])
        normalized = [_normalize_prediction(r) for r in raw_trains]
        logger.debug(
            "Fetched %d predictions for stations %s", len(normalized), codes_str
        )
        return normalized
