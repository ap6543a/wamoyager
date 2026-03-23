-- Initial schema for wamoyager
-- Migration 001: create all core tables

CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    phone_e164  TEXT    NOT NULL UNIQUE,
    active      INTEGER NOT NULL DEFAULT 1,   -- 0=false, 1=true
    timezone    TEXT    NOT NULL DEFAULT 'America/New_York',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    email       TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id             INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    station_codes_json  TEXT    NOT NULL DEFAULT '[]',
    lines_json          TEXT    NOT NULL DEFAULT '[]',
    direction_json      TEXT    NOT NULL DEFAULT '[]',
    daily_enabled       INTEGER NOT NULL DEFAULT 1,
    daily_time          TEXT    NOT NULL DEFAULT '17:00'
);

CREATE TABLE IF NOT EXISTS incidents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint     TEXT    NOT NULL UNIQUE,
    normalized_json TEXT    NOT NULL,
    first_seen      TEXT    NOT NULL DEFAULT (datetime('now')),
    last_seen       TEXT    NOT NULL DEFAULT (datetime('now')),
    severity        TEXT    NOT NULL DEFAULT 'INFO'
);

CREATE INDEX IF NOT EXISTS idx_incidents_fingerprint ON incidents(fingerprint);
CREATE INDEX IF NOT EXISTS idx_incidents_last_seen   ON incidents(last_seen);

CREATE TABLE IF NOT EXISTS notifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    incident_id INTEGER REFERENCES incidents(id) ON DELETE SET NULL,
    type        TEXT    NOT NULL,   -- 'incident' | 'daily'
    body        TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'pending',  -- pending | sent | failed | dry_run
    provider_id TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_id    ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at);
CREATE INDEX IF NOT EXISTS idx_notifications_incident_id ON notifications(incident_id);

CREATE TABLE IF NOT EXISTS agent_state (
    key         TEXT    PRIMARY KEY,
    value       TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
