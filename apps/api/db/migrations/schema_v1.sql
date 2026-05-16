-- Phase 3 / Wave 1 first follow-up migration.
--
-- Adds an index on ``messages(thread_id, created_at)`` so the per-
-- thread history fetch in ``get_thread_messages(db, thread_id)`` walks
-- an index instead of doing a full table scan. Phase 4's chat UI loads
-- the full thread history on every navigation; without this index the
-- read cost grows linearly in total messages across all threads.
--
-- Choice rationale (RESEARCH Open Question 2):
--   (a) ``ALTER TABLE threads ADD COLUMN pinned BOOLEAN DEFAULT 0`` —
--       too trivial; pure DDL with no query-plan impact. Rejected.
--   (b) ``CREATE INDEX idx_messages_thread_id_created_at ON
--       messages(thread_id, created_at)`` — cheapest defensible
--       evolution that DOES affect query plans (the round-trip test
--       can observe the index appearing in ``sqlite_master``).
--       RECOMMENDED.
--   (c) New ``routing_feedback`` table coupling Phase 3 to Phase 5 —
--       too much scope creep. Deferred.
--
-- The index is APPEND-ONLY DDL — no destructive change, no column
-- deletion — so the Pitfall 3 caveat in ``apps/api/db/migrate.py``
-- about ``executescript()`` implicit commits is benign for this file.
--
-- Cross-refs:
--   - 03-RESEARCH.md §"Open Question 2" lines 1102-1108 (option (b))
--   - 03-CONTEXT.md deferred line 369 (forward-only-migrations rule)
--   - 03-CONTEXT.md D-02 (migration runner shape)

CREATE INDEX idx_messages_thread_id_created_at
    ON messages (thread_id, created_at);
