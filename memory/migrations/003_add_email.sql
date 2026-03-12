-- Migration 003: add email/gateway address to users

ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT '';
