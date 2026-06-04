-- Phase 11 / Wave 0 control-substrate migration (CTRL-02 storage half, D-02).
--
-- Adds the append-only ``control_events`` audit table — one row per
-- control command (approve / reject / pause / resume / take_over) that
-- the per-turn control channel receives. The substrate persists every
-- command for an after-the-fact audit trail; ``insert_control_event``
-- in ``apps/api/db/queries.py`` is the parameterised writer.
--
--   control_events      append-only audit log:
--       id           TEXT PK   — secrets.token_urlsafe(12)
--       turn_id      TEXT      — the turn the command targeted
--       kind         TEXT      — D-01 closed verb set, CHECK-constrained
--                                so a forged/unknown verb is rejected at
--                                the storage layer too (T-11-03), mirroring
--                                the ControlMessage Literal in mailbox.py
--       payload      TEXT      — opaque JSON (D-01), nullable
--       received_at  TEXT      — ISO 8601 UTC ``Z`` (server-stamped)
--       delivered    INTEGER   — 0/1 delivered/drained marker (D-02)
--
--   idx_control_events_turn_id   index for the per-turn audit fetch.
--
-- APPEND-ONLY DDL ONLY (CREATE TABLE / CREATE INDEX) — no destructive
-- change — so the Pitfall 3 caveat in ``apps/api/db/migrate.py`` about
-- the ``executescript()`` implicit commit stays benign for this file.
--
-- This file MUST NOT seed the schema_meta version row: only
-- schema_v0.sql does that, and ``migrate.py:up_to_latest`` owns the
-- version bump (it UPDATEs schema_meta to 2 after this script runs).
--
-- Cross-refs:
--   - 11-01-PLAN Task 2 (action + acceptance criteria)
--   - apps/api/db/migrations/schema_v1.sql (CREATE INDEX + header convention)
--   - apps/api/control/mailbox.py (the D-01 kind Literal this CHECK mirrors)
--   - 03-CONTEXT.md D-02 (migration runner shape; forward-only rule)

CREATE TABLE control_events (
    id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL,
    kind TEXT NOT NULL
        CHECK (kind IN ('approve','reject','pause','resume','take_over')),
    payload TEXT,                        -- opaque JSON (D-01), nullable
    received_at TEXT NOT NULL,           -- ISO 8601 UTC, server-stamped
    delivered INTEGER NOT NULL DEFAULT 0 -- 0/1 delivered/drained marker (D-02)
);

CREATE INDEX idx_control_events_turn_id
    ON control_events (turn_id);
