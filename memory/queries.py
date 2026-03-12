"""Typed query functions for all DB operations."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from memory.db import Database
from memory.models import (
    Incident,
    Notification,
    NormalizedIncident,
    User,
    UserPreferences,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse_dt(value: str) -> datetime:
    """Parse ISO/sqlite datetime string to a timezone-aware datetime (UTC assumed)."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {value!r}")


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def get_all_active_users(db: Database) -> list[User]:
    rows = db.conn.execute(
        "SELECT id, name, phone_e164, email, active, timezone, created_at FROM users WHERE active = 1"
    ).fetchall()
    return [_row_to_user(r) for r in rows]


def get_user_by_id(db: Database, user_id: int) -> User | None:
    row = db.conn.execute(
        "SELECT id, name, phone_e164, email, active, timezone, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    return _row_to_user(row) if row else None


def create_user(
    db: Database,
    name: str,
    email: str,
    phone_e164: str = "",
    timezone: str = "America/New_York",
) -> int:
    """Insert a new user and their default preferences. Returns new user id."""
    # phone_e164 is legacy — use email as the unique fallback if not provided
    if not phone_e164:
        phone_e164 = email
    with db.conn:
        cur = db.conn.execute(
            "INSERT INTO users (name, phone_e164, email, active, timezone, created_at) VALUES (?, ?, ?, 1, ?, ?)",
            (name, phone_e164, email, timezone, _now_utc()),
        )
        user_id = cur.lastrowid
        db.conn.execute(
            "INSERT INTO user_preferences (user_id) VALUES (?)",
            (user_id,),
        )
    logger.info("Created user id=%d name=%s email=%s", user_id, name, email)
    return user_id


def update_user_preferences(
    db: Database,
    user_id: int,
    station_codes: list[str] | None = None,
    lines: list[str] | None = None,
    direction: list[str] | None = None,
    daily_enabled: bool | None = None,
    daily_time: str | None = None,
) -> None:
    updates: list[str] = []
    params: list[Any] = []
    if station_codes is not None:
        updates.append("station_codes_json = ?")
        params.append(json.dumps(station_codes))
    if lines is not None:
        updates.append("lines_json = ?")
        params.append(json.dumps(lines))
    if direction is not None:
        updates.append("direction_json = ?")
        params.append(json.dumps(direction))
    if daily_enabled is not None:
        updates.append("daily_enabled = ?")
        params.append(1 if daily_enabled else 0)
    if daily_time is not None:
        updates.append("daily_time = ?")
        params.append(daily_time)

    if not updates:
        return

    params.append(user_id)
    with db.conn:
        db.conn.execute(
            f"UPDATE user_preferences SET {', '.join(updates)} WHERE user_id = ?",
            params,
        )


def get_user_preferences(db: Database, user_id: int) -> UserPreferences | None:
    row = db.conn.execute(
        "SELECT user_id, station_codes_json, lines_json, direction_json, daily_enabled, daily_time "
        "FROM user_preferences WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    return _row_to_prefs(row) if row else None


def _row_to_user(row: Any) -> User:
    return User(
        id=row["id"],
        name=row["name"],
        phone_e164=row["phone_e164"],
        email=row["email"],
        active=bool(row["active"]),
        timezone=row["timezone"],
        created_at=_parse_dt(row["created_at"]),
    )


def _row_to_prefs(row: Any) -> UserPreferences:
    return UserPreferences(
        user_id=row["user_id"],
        station_codes=json.loads(row["station_codes_json"]),
        lines=json.loads(row["lines_json"]),
        direction=json.loads(row["direction_json"]),
        daily_enabled=bool(row["daily_enabled"]),
        daily_time=row["daily_time"],
    )


# ---------------------------------------------------------------------------
# Incidents
# ---------------------------------------------------------------------------

def upsert_incident(db: Database, normalized: NormalizedIncident) -> tuple[int, bool]:
    """Insert or update an incident by fingerprint.

    Returns (incident_id, is_new).
    """
    now = _now_utc()
    existing = db.conn.execute(
        "SELECT id, severity FROM incidents WHERE fingerprint = ?",
        (normalized.fingerprint,),
    ).fetchone()

    with db.conn:
        if existing is None:
            cur = db.conn.execute(
                "INSERT INTO incidents (fingerprint, normalized_json, first_seen, last_seen, severity) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    normalized.fingerprint,
                    json.dumps(normalized.to_dict()),
                    now,
                    now,
                    normalized.severity,
                ),
            )
            return cur.lastrowid, True
        else:
            db.conn.execute(
                "UPDATE incidents SET normalized_json = ?, last_seen = ?, severity = ? WHERE fingerprint = ?",
                (
                    json.dumps(normalized.to_dict()),
                    now,
                    normalized.severity,
                    normalized.fingerprint,
                ),
            )
            return existing["id"], False


def get_incident_by_fingerprint(db: Database, fingerprint: str) -> Incident | None:
    row = db.conn.execute(
        "SELECT id, fingerprint, normalized_json, first_seen, last_seen, severity "
        "FROM incidents WHERE fingerprint = ?",
        (fingerprint,),
    ).fetchone()
    return _row_to_incident(row) if row else None


def get_recent_incidents(db: Database, limit: int = 20) -> list[Incident]:
    rows = db.conn.execute(
        "SELECT id, fingerprint, normalized_json, first_seen, last_seen, severity "
        "FROM incidents ORDER BY last_seen DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_row_to_incident(r) for r in rows]


def _row_to_incident(row: Any) -> Incident:
    return Incident(
        id=row["id"],
        fingerprint=row["fingerprint"],
        normalized_json=json.loads(row["normalized_json"]),
        first_seen=_parse_dt(row["first_seen"]),
        last_seen=_parse_dt(row["last_seen"]),
        severity=row["severity"],
    )


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

def log_notification(
    db: Database,
    user_id: int,
    body: str,
    notification_type: str,
    status: str,
    incident_id: int | None = None,
    provider_id: str | None = None,
) -> int:
    """Insert a notification record. Returns new notification id."""
    with db.conn:
        cur = db.conn.execute(
            "INSERT INTO notifications (user_id, incident_id, type, body, status, provider_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, incident_id, notification_type, body, status, provider_id, _now_utc()),
        )
    return cur.lastrowid


def update_notification_status(
    db: Database, notification_id: int, status: str, provider_id: str | None = None
) -> None:
    with db.conn:
        db.conn.execute(
            "UPDATE notifications SET status = ?, provider_id = COALESCE(?, provider_id) WHERE id = ?",
            (status, provider_id, notification_id),
        )


def get_notifications_for_user_since(
    db: Database, user_id: int, since: datetime
) -> list[Notification]:
    rows = db.conn.execute(
        "SELECT id, user_id, incident_id, type, body, status, provider_id, created_at "
        "FROM notifications WHERE user_id = ? AND created_at >= ? ORDER BY created_at DESC",
        (user_id, since.strftime("%Y-%m-%d %H:%M:%S")),
    ).fetchall()
    return [_row_to_notification(r) for r in rows]


def get_last_notification_for_fingerprint(
    db: Database, user_id: int, fingerprint: str
) -> Notification | None:
    """Get the most recent notification sent to a user for a specific incident fingerprint."""
    row = db.conn.execute(
        """
        SELECT n.id, n.user_id, n.incident_id, n.type, n.body, n.status, n.provider_id, n.created_at
        FROM notifications n
        JOIN incidents i ON i.id = n.incident_id
        WHERE n.user_id = ? AND i.fingerprint = ?
        ORDER BY n.created_at DESC
        LIMIT 1
        """,
        (user_id, fingerprint),
    ).fetchone()
    return _row_to_notification(row) if row else None


def prune_old_notifications(db: Database, days: int = 30) -> int:
    """Delete notifications older than `days` days. Returns count deleted."""
    with db.conn:
        cur = db.conn.execute(
            "DELETE FROM notifications WHERE created_at < datetime('now', ?)",
            (f"-{days} days",),
        )
    return cur.rowcount


def prune_old_incidents(db: Database, days: int = 90) -> int:
    """Delete incidents older than `days` days (by last_seen). Returns count deleted."""
    with db.conn:
        cur = db.conn.execute(
            "DELETE FROM incidents WHERE last_seen < datetime('now', ?)",
            (f"-{days} days",),
        )
    return cur.rowcount


def _row_to_notification(row: Any) -> Notification:
    return Notification(
        id=row["id"],
        user_id=row["user_id"],
        incident_id=row["incident_id"],
        type=row["type"],
        body=row["body"],
        status=row["status"],
        provider_id=row["provider_id"],
        created_at=_parse_dt(row["created_at"]),
    )


# ---------------------------------------------------------------------------
# Conversation state (inbound SMS setup flow)
# ---------------------------------------------------------------------------

def get_conversation_state(db: Database, phone_e164: str) -> dict | None:
    """Return the conversation state for a phone number, or None if not found."""
    row = db.conn.execute(
        "SELECT step, data_json FROM conversation_state WHERE phone_e164 = ?",
        (phone_e164,),
    ).fetchone()
    if row is None:
        return None
    return {"step": row["step"], "data": json.loads(row["data_json"])}


def set_conversation_state(db: Database, phone_e164: str, step: str, data: dict) -> None:
    """Upsert conversation state for a phone number."""
    with db.conn:
        db.conn.execute(
            "INSERT INTO conversation_state (phone_e164, step, data_json, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(phone_e164) DO UPDATE SET "
            "step = excluded.step, data_json = excluded.data_json, updated_at = excluded.updated_at",
            (phone_e164, step, json.dumps(data), _now_utc()),
        )


def delete_conversation_state(db: Database, phone_e164: str) -> None:
    """Remove conversation state once setup is complete or user resets."""
    with db.conn:
        db.conn.execute(
            "DELETE FROM conversation_state WHERE phone_e164 = ?", (phone_e164,)
        )


def get_user_by_phone(db: Database, phone_e164: str) -> "User | None":
    """Look up a user by phone number."""
    row = db.conn.execute(
        "SELECT id, name, phone_e164, email, active, timezone, created_at FROM users WHERE phone_e164 = ?",
        (phone_e164,),
    ).fetchone()
    return _row_to_user(row) if row else None


def deactivate_user(db: Database, user_id: int) -> None:
    """Set a user's active flag to 0 (STOP/unsubscribe)."""
    with db.conn:
        db.conn.execute("UPDATE users SET active = 0 WHERE id = ?", (user_id,))
    logger.info("Deactivated user id=%d", user_id)


# ---------------------------------------------------------------------------
# Agent state
# ---------------------------------------------------------------------------

def get_agent_state(db: Database, key: str) -> str | None:
    row = db.conn.execute(
        "SELECT value FROM agent_state WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else None


def set_agent_state(db: Database, key: str, value: str) -> None:
    now = _now_utc()
    with db.conn:
        db.conn.execute(
            "INSERT INTO agent_state (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, value, now),
        )
