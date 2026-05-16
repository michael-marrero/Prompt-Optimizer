-- Phase 3 / Wave 1 migration round-trip seed.
--
-- This file is INSERT-only. It loads a known v0 dataset (1 thread +
-- 2 messages + 1 routing_decisions row) into a database that already
-- has the ``schema_v0.sql`` tables applied. The Wave 1
-- ``test_v0_to_v1_preserves_data`` test then runs
-- ``migrate.up_to_latest()`` and asserts:
--
--   1. ``schema_meta.version`` advanced to the latest.
--   2. The seeded rows are still present (by their literal IDs).
--   3. Any v1 columns added by ``schema_v1.sql`` have their default
--      values populated for the seed rows.
--
-- The literal IDs are 13 chars (``thr_seed_0001``, ``msg_seed_*_0001``,
-- ``rd_seed_0001``) — distinct from the production IDs produced by
-- ``secrets.token_urlsafe(12)`` so they never collide with real data
-- if the seed accidentally runs against a non-test DB.
--
-- IMPORTANT: This seed MUST NOT reference any v1 columns; that would
-- break the migration round-trip test (the v0 DB doesn't have them
-- yet at the moment this seed runs).
--
-- Cross-refs:
--   - 03-CONTEXT.md specifics line 346 (seed contract)
--   - 03-CONTEXT.md D-13 lines 90-128 (schema_v0 column list)
--   - 03-PLAN-00 Task 3 lines 351-370

INSERT INTO threads (id, title, created_at, updated_at)
  VALUES ('thr_seed_0001', 'Seed Thread', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');

INSERT INTO messages (id, thread_id, role, content_blocks, text, backend_used, model_used,
                      cost_usd, latency_ms, tokens_in, tokens_out, created_at, status)
  VALUES ('msg_seed_user_0001', 'thr_seed_0001', 'user', '[]', 'hello',
          NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-01T00:00:01Z', 'complete');

INSERT INTO messages (id, thread_id, role, content_blocks, text, backend_used, model_used,
                      cost_usd, latency_ms, tokens_in, tokens_out, created_at, status)
  VALUES ('msg_seed_asst_0001', 'thr_seed_0001', 'assistant', '[]', 'hi back',
          'openrouter', 'openai/gpt-5', 0.0001, 250, 5, 7, '2026-01-01T00:00:02Z', 'complete');

INSERT INTO routing_decisions (id, message_id, task_type, task_confidence, agentic_intent,
                               agentic_confidence, predicted_model, rationale, signals, decided_at)
  VALUES ('rd_seed_0001', 'msg_seed_asst_0001', 'chat', 0.95, 0, 0.10,
          'openai/gpt-5', 'short conversational', '{}', '2026-01-01T00:00:01Z');
