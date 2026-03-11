"""Dataclass models for wamoyager domain objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class User:
    id: int
    name: str
    phone_e164: str
    active: bool
    timezone: str
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "phone_e164": self.phone_e164,
            "active": self.active,
            "timezone": self.timezone,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class UserPreferences:
    user_id: int
    station_codes: list[str]  # deserialized from JSON
    lines: list[str]          # deserialized from JSON
    direction: list[str]      # deserialized from JSON
    daily_enabled: bool
    daily_time: str           # "HH:MM"

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "station_codes": self.station_codes,
            "lines": self.lines,
            "direction": self.direction,
            "daily_enabled": self.daily_enabled,
            "daily_time": self.daily_time,
        }


@dataclass
class Incident:
    id: int
    fingerprint: str
    normalized_json: dict[str, Any]
    first_seen: datetime
    last_seen: datetime
    severity: str  # INFO | MINOR | MAJOR | CRITICAL

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "fingerprint": self.fingerprint,
            "normalized_json": self.normalized_json,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "severity": self.severity,
        }


@dataclass
class Notification:
    id: int
    user_id: int
    incident_id: int | None
    type: str
    body: str
    status: str
    provider_id: str | None
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "incident_id": self.incident_id,
            "type": self.type,
            "body": self.body,
            "status": self.status,
            "provider_id": self.provider_id,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class NormalizedIncident:
    """Normalized incident from WMATA API, before DB persistence."""
    fingerprint: str
    title: str
    description: str
    lines_affected: list[str]
    stations_affected: list[str]
    severity: str  # INFO | MINOR | MAJOR | CRITICAL
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "title": self.title,
            "description": self.description,
            "lines_affected": self.lines_affected,
            "stations_affected": self.stations_affected,
            "severity": self.severity,
            "raw": self.raw,
        }


@dataclass
class NormalizedPrediction:
    """Normalized train prediction from WMATA API."""
    station_code: str
    destination: str
    line: str
    minutes: str  # can be "ARR", "BRD", or numeric string
    car_count: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "station_code": self.station_code,
            "destination": self.destination,
            "line": self.line,
            "minutes": self.minutes,
            "car_count": self.car_count,
        }
