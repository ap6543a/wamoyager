-- Migration 002: conversation state for inbound SMS setup flow

CREATE TABLE IF NOT EXISTS conversation_state (
    phone_e164  TEXT    PRIMARY KEY,
    step        TEXT    NOT NULL DEFAULT 'new',
    data_json   TEXT    NOT NULL DEFAULT '{}',
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
