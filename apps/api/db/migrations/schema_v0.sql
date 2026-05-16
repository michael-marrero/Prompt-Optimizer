-- Phase 3 / Wave 1 initial schema (D-13).
--
-- Four tables for the per-turn chat lifecycle:
--
--   threads             top-level conversation (PK id)
--   messages            per-turn user + assistant rows (FK -> threads,
--                       cascade-on-delete so removing a thread also
--                       removes its messages atomically)
--   routing_decisions   one row per assistant message (FK -> messages,
--                       cascade-on-delete so removing a message also
--                       removes its routing decision atomically)
--   schema_meta         single-row version-tracking table that the
--                       migration runner (apps/api/db/migrate.py) reads
--                       and bumps; the seed row writes version 0.
--
-- FK cascades only fire when ``PRAGMA foreign_keys=ON`` is applied on
-- the connection — see Pitfall 1 in ``apps/api/db/connect.py``. Phase 3
-- enforces that pragma in ``open_db()`` so every connection sees the
-- cascades.
--
-- ISO 8601 UTC ``created_at`` / ``updated_at`` strings are written by
-- ``apps/api/db/queries.py:_now_iso()``. ``content_blocks`` is a JSON
-- array of non-TextDelta ChatChunk objects serialised via
-- ``chunk.model_dump_json()``; ``text`` is the collapsed TextDelta
-- text. ``signals`` is the Phase 1 RoutingDecision.signals dict
-- serialised to JSON.
--
-- Cross-refs:
--   - 03-CONTEXT.md D-13 lines 90-128 (canonical DDL block)
--   - 03-CONTEXT.md D-03 (PRAGMA foreign_keys=ON requirement)
--   - 03-CONTEXT.md D-04 (per-turn write triple this schema persists)
--   - 03-RESEARCH.md §"Pattern 3" (buffer-and-write-once on Done)

CREATE TABLE threads (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,            -- ISO 8601 UTC
    updated_at TEXT NOT NULL
);

CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user','assistant')),
    content_blocks TEXT NOT NULL,        -- JSON array of non-TextDelta chunks
    text TEXT NOT NULL,                  -- collapsed TextDelta text
    backend_used TEXT,
    model_used TEXT,
    cost_usd REAL,
    latency_ms INTEGER,
    tokens_in INTEGER,
    tokens_out INTEGER,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'complete'
        CHECK (status IN ('complete','error','cancelled'))
);

CREATE TABLE routing_decisions (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    task_type TEXT,
    task_confidence REAL,
    agentic_intent INTEGER,              -- 0/1
    agentic_confidence REAL,
    predicted_model TEXT,
    rationale TEXT NOT NULL,
    signals TEXT NOT NULL,               -- JSON of RoutingDecision.signals
    decided_at TEXT NOT NULL
);

CREATE TABLE schema_meta (
    version INTEGER NOT NULL
);

INSERT INTO schema_meta (version) VALUES (0);
