---
phase: "03"
plan: "01"
subsystem: "fastapi-service-persistent-storage / storage layer"
tags: [database, sqlite, aiosqlite, pydantic-v2, migrations, schema, async, STORE-01, STORE-02, STORE-03]
requires:
  - phase: "03-00"
    provides: "apps.api.paths.DB_PATH (default db file location), apps/api/tests/conftest.py:aiosqlite_inmemory_db fixture, apps/api/tests/fixtures/schema_v0_seed.sql (round-trip seed)"
  - phase: "01"
    provides: "src.routing.schema.RoutingDecision (in-flight) — duck-typed by insert_routing_decision so the D-18 import-graph guard stays green inside src/routing/"
  - phase: "02"
    provides: "apps.api.backends.chunks.ChatChunk discriminated union — buffer dispatch in persist_turn calls chunk.model_dump() on the seven variants"
provides:
  - "apps.api.db.connect.open_db(path) — aiosqlite factory with the D-03 four-pragma prefix"
  - "apps.api.db.migrate.up_to_latest(db) — idempotent schema_v{N}.sql runner with explicit BEGIN/COMMIT and Pitfall 3 awareness"
  - "apps.api.db.migrate.MIGRATIONS_DIR / _current_version / _discover_migrations — public-ish helpers Wave 2 lifespan can call"
  - "apps.api.db.migrations.schema_v0.sql — D-13 four-table seed (threads, messages, routing_decisions, schema_meta)"
  - "apps.api.db.migrations.schema_v1.sql — RESEARCH OQ2 (b) recommendation: CREATE INDEX idx_messages_thread_id_created_at"
  - "apps.api.db.models.Thread / Message / RoutingDecision — frozen Pydantic v2 read-path BaseModels"
  - "apps.api.db.models.ThreadCreate / ThreadUpdate — non-frozen Pydantic v2 write-path models for Waves 3 / 6"
  - "apps.api.db.queries — 11 typed async functions (create_thread, get_thread, list_threads, update_thread_title, delete_thread, get_thread_messages, insert_user_message, insert_assistant_message_with_blocks, insert_routing_decision, persist_turn, read_schema_version)"
  - "apps/api/tests/test_migrations.py — 4 passing tests covering STORE-01 (pragmas), STORE-02 (four-table presence), STORE-03 (v0->v1 round-trip)"
affects:
  - "Phase 3 Wave 2 (lifespan) — calls open_db(DB_PATH) + up_to_latest(db), caches read_schema_version into app.state.schema_version"
  - "Phase 3 Wave 3 (thread CRUD) — POST/GET/PATCH/DELETE /api/v1/threads route handlers call create_thread / get_thread / list_threads / update_thread_title / delete_thread"
  - "Phase 3 Wave 4 (turn SSE) — persist_turn drains the buffered ChatChunks into one BEGIN/COMMIT on terminal Done; D-04 contract"
  - "Phase 3 Wave 5 (blob cascade) — extends delete_thread with a pre-step that walks messages.content_blocks JSON to unlink referenced blob files BEFORE the DB delete fires"
  - "Phase 3 Wave 6 (rename) — POST /api/v1/threads/{id}/rename calls update_thread_title once the cheap-model bypass collects ≤60 chars of TextDelta"
tech-stack:
  added:
    - "(none — fastapi/uvicorn/sse-starlette/aiosqlite already landed in Wave 0)"
  patterns:
    - "Pydantic v2 frozen read-path / non-frozen write-path split (BaseModel + model_config = ConfigDict(frozen=True) for read; bare BaseModel for write)"
    - "Closed-vocabulary Literal[\"user\", \"assistant\"] / Literal[\"complete\", \"error\", \"cancelled\"] mirroring schema_v0 CHECK constraints so Pydantic ValidationError fires loudly on a corrupted SELECT result"
    - "Hand-rolled schema_v{N}.sql migration runner — explicit BEGIN/COMMIT around executescript, Pitfall 3 (executescript implicit commit) cited inline as a forward-only-migrations gate"
    - "Re-read schema_meta row count AFTER executescript() to decide INSERT vs UPDATE — handles the case where the SQL file itself seeds the version row (schema_v0 does)"
    - "Duck-typed routing-decision dispatch in insert_routing_decision / persist_turn (getattr(decision, ...)) so apps.api.db never imports from src.routing.* — preserves Phase 1 D-18 isolation"
    - "secrets.token_urlsafe(12) for paste-safe, collision-free server-side IDs (CONTEXT discretion line 176; ~16 chars URL-safe base64)"
    - "_now_iso() returns ISO 8601 UTC with explicit Z suffix to match the schema_v0 `-- ISO 8601 UTC` comment"
key-files:
  created:
    - "apps/api/db/__init__.py"
    - "apps/api/db/connect.py"
    - "apps/api/db/migrate.py"
    - "apps/api/db/migrations/schema_v0.sql"
    - "apps/api/db/migrations/schema_v1.sql"
    - "apps/api/db/models.py"
    - "apps/api/db/queries.py"
    - "apps/api/tests/test_migrations.py"
  modified: []
key-decisions:
  - "RESEARCH Open Question 2 resolved as option (b): schema_v1 is the pure index addition CREATE INDEX idx_messages_thread_id_created_at ON messages(thread_id, created_at). Option (a) `pinned BOOLEAN` rejected (too trivial); option (c) `routing_feedback` table rejected (couples Phase 3 to Phase 5)."
  - "Plan literal logic for INSERT-vs-UPDATE on schema_meta was incorrect (would duplicate the row on fresh-DB v0 apply because schema_v0.sql itself seeds version 0). Fixed by re-reading SELECT COUNT(*) FROM schema_meta after executescript and choosing INSERT only when meta_count == 0. Tracked as Rule 1 deviation."
  - "Routing-decision dispatch in queries.py uses getattr(decision, attr, default) and signals_dict.get(...) so this module never imports from src.routing.*; preserves the Phase 1 D-18 import-graph guard when src/routing/ is tested in isolation."
  - "delete_thread ships the minimal DB-only path in Wave 1; Wave 5 will wrap it with the messages.content_blocks blob-unlink pre-step per D-14 + STORE-04 cascade unlink (CONTEXT line 360 carry-forward)."
patterns-established:
  - "Frozen Pydantic v2 read-path / non-frozen write-path split for DB row models"
  - "schema_v{N}.sql append-only migrations + explicit BEGIN/COMMIT + Pitfall 3 awareness"
  - "Post-executescript schema_meta re-read for safe INSERT/UPDATE choice"
  - "secrets.token_urlsafe(12) ID generation for thread / message / routing_decision rows"
  - "_now_iso() ISO 8601 UTC with Z suffix"
  - "Duck-typed cross-package dispatch via getattr to keep import-graph guards green"
requirements-completed: [STORE-01, STORE-02, STORE-03]

duration: 21m
completed: 2026-05-16
---

# Phase 03 Plan 01: Wave 1 Storage Layer Summary

**Async SQLite storage layer — aiosqlite open_db with the D-03 four-pragma prefix, hand-rolled schema_v{N}.sql migration runner with Pitfall 3 awareness, Pydantic v2 frozen DB-row models, 11 typed async query functions, and the v0->v1 round-trip migration test (STORE-03) that confirms the schema_v1 index lands and seeded rows survive.**

## Performance

- **Duration:** ~21 min
- **Started:** 2026-05-16T18:30:00Z (approx)
- **Completed:** 2026-05-16T18:51:19Z
- **Tasks:** 3 (all type=auto, tdd=true)
- **Files created:** 8
- **Files modified:** 0
- **Lines added (db + tests):** 1,283

## Accomplishments

- **STORE-01 satisfied:** `open_db(path)` factory applies the four D-03 pragmas (`journal_mode=WAL` → `synchronous=NORMAL` → `busy_timeout=5000` → `foreign_keys=ON`) in the canonical order; Pitfall 1 (SQLite disables FK enforcement by default per connection) cited inline above the `foreign_keys=ON` pragma. The `mkdir(parents=True, exist_ok=True)` bootstrap on first boot creates the user-home dir.
- **STORE-02 satisfied:** `schema_v0.sql` writes the canonical D-13 four-table set (`threads`, `messages`, `routing_decisions`, `schema_meta`) with two `ON DELETE CASCADE` foreign keys (`messages.thread_id`, `routing_decisions.message_id`) and two `CHECK` constraints (`role IN ('user','assistant')`, `status IN ('complete','error','cancelled')`). The initial `schema_meta` row is seeded with version 0.
- **STORE-03 satisfied:** `apps/api/tests/test_migrations.py::test_v0_to_v1_preserves_data` round-trips a fresh `:memory:` DB through `schema_v0.sql` + the Wave 0 seed (1 thread + 2 messages + 1 routing_decisions row) + `up_to_latest(db)`, then asserts `schema_meta.version == 1`, every seeded row is present by literal ID (`thr_seed_0001`, `msg_seed_user_0001`, `msg_seed_asst_0001`, `rd_seed_0001`), and `idx_messages_thread_id_created_at` landed in `sqlite_master`.
- **RESEARCH Open Question 2 resolved:** `schema_v1.sql` ships option (b) `CREATE INDEX idx_messages_thread_id_created_at ON messages(thread_id, created_at)` — pure index addition with no destructive DDL. Option (a) `pinned BOOLEAN` rejected as too trivial; option (c) `routing_feedback` table rejected for coupling Phase 3 to Phase 5.
- **11 typed async query functions** in `apps/api/db/queries.py` covering thread CRUD, per-turn write helpers (no individual commits), the buffer-and-write-once `persist_turn` (one BEGIN/COMMIT for the user msg + assistant msg + routing_decisions triple per D-04), and `read_schema_version` (Wave 2 lifespan will cache this).
- **Phase 1 D-18 import-graph guard still green:** queries.py duck-types the in-flight RoutingDecision via `getattr(decision, ...)` and `signals_dict.get(...)`, so `apps.api.db.*` never imports from `src.routing.*`. `uv run pytest src/routing/tests/test_decide_smoke.py -x` exits 0.
- **Phase 2 whole-repo non-live suite still green:** 242 passed / 2 skipped / 3 deselected (`uv run pytest -m 'not live'`).

## Task Commits

Each task was committed atomically. Task 1 and Task 2 are pure `feat`; Task 3 split into a Rule 1 `fix` (the schema_meta double-row bug surfaced by the test) followed by the `test` commit.

1. **Task 1: db/connect + db/migrate + schema_v0.sql + schema_v1.sql** — `1a767e5` (feat)
2. **Task 2: db/models + db/queries (11 typed async functions)** — `abd6345` (feat)
3. **Task 3 Rule 1 fix: migrate runner schema_meta double-row bug** — `a99fd61` (fix)
4. **Task 3: test_migrations.py (4 passing tests)** — `b06dcec` (test)

**Plan metadata commit:** to be authored after this SUMMARY lands.

## Files Created/Modified

### Created (8)

- `apps/api/db/__init__.py` — package marker docstring; no exports (mirror of `apps/api/backends/__init__.py`).
- `apps/api/db/connect.py` — `async def open_db(path: Path | str) -> aiosqlite.Connection`. Coerces str → Path, `mkdir(parents=True, exist_ok=True)` when path is NOT `":memory:"`, applies the four D-03 pragmas in order, single `commit()`. Pitfall 1 cited inline.
- `apps/api/db/migrate.py` — `MIGRATIONS_DIR: Final[Path]`, `async def _current_version(db) -> int` (returns -1 on OperationalError / 0 on empty schema_meta), `def _discover_migrations() -> list[tuple[int, Path]]` (glob + integer-suffix parse + sort), `async def up_to_latest(db) -> None` (explicit BEGIN/COMMIT per migration, post-executescript schema_meta count check, INFO log per applied file). Pitfall 3 (executescript implicit commit) cited inline above the executescript call.
- `apps/api/db/migrations/schema_v0.sql` — D-13 canonical DDL verbatim: 4 CREATE TABLEs, 2 ON DELETE CASCADE FKs, 2 CHECK constraints, `INSERT INTO schema_meta (version) VALUES (0)`.
- `apps/api/db/migrations/schema_v1.sql` — single `CREATE INDEX idx_messages_thread_id_created_at ON messages (thread_id, created_at);`. No destructive DDL.
- `apps/api/db/models.py` — Pydantic v2 BaseModels. Read paths (`Thread`, `Message`, `RoutingDecision`) use `model_config = ConfigDict(frozen=True)`; closed-vocabulary `Literal["user","assistant"]` / `Literal["complete","error","cancelled"]` on `Message.role` / `Message.status` mirrors the schema-level CHECK constraints. Non-frozen write-path models `ThreadCreate` / `ThreadUpdate`.
- `apps/api/db/queries.py` — 11 typed async functions: `create_thread`, `get_thread`, `list_threads`, `update_thread_title`, `delete_thread`, `get_thread_messages`, `insert_user_message`, `insert_assistant_message_with_blocks`, `insert_routing_decision`, `persist_turn`, `read_schema_version`. All parameter substitution via `?` placeholders. IDs via `secrets.token_urlsafe(12)`. Timestamps via `_now_iso()` (ISO 8601 UTC with Z suffix). The three insert helpers do NOT call `db.commit()` — `persist_turn` owns the per-turn transaction.
- `apps/api/tests/test_migrations.py` — 4 async tests: `test_schema_v0_has_all_four_tables`, `test_pragmas_applied`, `test_up_to_latest_idempotent`, `test_v0_to_v1_preserves_data`. Uses raw `aiosqlite.connect(":memory:")` for the schema-only branches and `open_db(":memory:")` for the pragma check.

### Modified (0)

(No existing files were touched. The Wave 0 conftest fixtures call into `apps.api.db.connect.open_db` and `apps.api.db.migrate.up_to_latest` via B3 lazy imports — those Wave 0 fixtures were authored *for* this Wave 1 contract and now their lazy-import skip branch falls through to the real modules.)

## Decisions Made

- **Open Question 2 → option (b):** schema_v1 is a pure index addition. Cheapest defensible evolution that DOES affect query plans (the round-trip test can observe the index appearing in `sqlite_master`).
- **Migrate runner upsert logic:** plan literal said `if current < 0: INSERT else: UPDATE`, but schema_v0.sql itself seeds the schema_meta row (`INSERT INTO schema_meta (version) VALUES (0)`), so on a fresh-DB v0 apply the captured `current=-1` led to a duplicate row. Fix: re-read `SELECT COUNT(*) FROM schema_meta` AFTER executescript and choose INSERT only when `meta_count == 0`. Idempotent on both branches.
- **Duck-typed routing-decision dispatch:** `insert_routing_decision` and `persist_turn` use `getattr(decision, attr, default)` + `signals_dict.get(...)`. This keeps `apps.api.db.*` clean of any `src.routing.*` import — preserves the Phase 1 D-18 import-graph guard when src/routing/ is tested in isolation. The Wave 4 turn route handler is the one place that actually imports `from src.routing.decide import decide` + `from src.routing.schema import RoutingDecision`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Migrate runner double-inserts schema_meta on fresh-DB v0 apply**

- **Found during:** Task 3 (`test_up_to_latest_idempotent` failed with `assert 2 == 1` for `SELECT COUNT(*) FROM schema_meta`).
- **Issue:** The plan's literal Task 1 logic was `if current < 0: INSERT INTO schema_meta (version) VALUES (?); else: UPDATE schema_meta SET version = ?`. On a fresh DB `_current_version()` returns -1 (OperationalError — table absent). After `executescript()` applies `schema_v0.sql`, the `INSERT INTO schema_meta (version) VALUES (0)` inside the SQL file runs and creates a row. The captured `current = -1` then takes the INSERT branch and inserts a SECOND row with `version = 0` (or `version = N` for subsequent migrations). Result: two `schema_meta` rows on a fresh DB, breaking the single-row invariant the runner relies on.
- **Fix:** After `executescript()` returns, re-read `SELECT COUNT(*) FROM schema_meta`. Choose INSERT only when `meta_count == 0` (a future migration that doesn't seed); choose UPDATE otherwise. The post-executescript re-read is safe because executescript's implicit commit means the schema_v0 INSERT is durable by the time we check.
- **Files modified:** `apps/api/db/migrate.py` (13 inserted, 1 deleted)
- **Verification:** `test_up_to_latest_idempotent` now passes (1 row after either call); `test_v0_to_v1_preserves_data` confirms version bumps cleanly 0 → 1 with no row duplication; the full `apps/api/tests/test_migrations.py` is 4/4 green.
- **Committed in:** `a99fd61` (`fix(03-01): migrate runner mis-counts schema_meta on fresh-DB v0 apply (Rule 1)`)

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug)
**Impact on plan:** Critical correctness fix — the plan's literal logic produced a multi-row schema_meta on every fresh DB, which would cascade into every Wave 2+ lifespan / healthz call (`read_schema_version` uses LIMIT 1 and would non-deterministically return one of the rows depending on storage order). No scope creep — the fix is internal to `up_to_latest` and the public API surface is unchanged.

## Issues Encountered

The only issue was the Rule 1 deviation above. No environment problems, no test infrastructure problems, no dependency surprises.

## User Setup Required

None — no external service configuration required for this wave. The DB lives at `apps.api.paths.DB_PATH` (default `~/.prompt-optimizer/chat.db`) which the Wave 2 lifespan will create on first boot. All tests run against `:memory:`.

## Next Phase Readiness

- **Wave 2 (lifespan + app shell + healthz):** Ready to consume `open_db(DB_PATH)`, `up_to_latest(db)`, and `read_schema_version(db)`. The plan already specifies these as the canonical entry points; no additional surface needed from Wave 1.
- **Wave 3 (thread CRUD):** Ready to consume `create_thread`, `get_thread`, `list_threads`, `update_thread_title`, `delete_thread`. Pydantic v2 request/response models are the `ThreadCreate` + `ThreadUpdate` shapes already exported.
- **Wave 4 (turn SSE):** Ready to consume `persist_turn` — the buffer-and-write-once primitive. The function takes a `list[ChatChunk]` and the in-flight `RoutingDecision`, runs ONE BEGIN/COMMIT, handles TextDelta collapse + non-TextDelta JSON serialisation + per-stage signal extraction.
- **Wave 5 (blob cascade unlink on thread delete):** Will wrap `delete_thread` with a pre-step that walks `messages.content_blocks` JSON to unlink referenced blob files BEFORE the DB DELETE fires. The Wave 1 path ships the minimal DB-only delete; nothing in Wave 1 conflicts with the Wave 5 wrap.
- **Wave 6 (rename):** Will call `update_thread_title` after the cheap-model bypass collects ≤60 chars of TextDelta. The Wave 1 signature is final.

No blockers. No concerns. The 11 Wave 1 `must_haves.truths` all verify at a CLI / pytest level (verified programmatically post-implementation; output below).

## All 11 Wave 1 Truths Verified

```
Truth 1 OK: no sys.path.append in apps/api/*.py
Truth 2 OK: apps/api/__init__.py installs redaction filter and load_dotenv()
Truth 3+4 OK: pragmas applied + ordered correctly (journal_mode=WAL -> synchronous=NORMAL -> busy_timeout=5000 -> foreign_keys=ON)
Truth 5 OK: schema_v0 has 4 tables + 2 ON DELETE CASCADE FKs
Truth 6 OK: schema_v1 adds idx_messages_thread_id_created_at
Truth 7 OK: up_to_latest idempotent
Truth 8 OK: v0 seed preserved + index landed
Truth 9 OK: 11 typed async functions, parameterised SQL only
Truth 10 OK: models include frozen read-path + non-frozen write-path
Truth 11 OK: test_migrations.py passes (4/4)
```

## Self-Check: PASSED

- All 8 files referenced in `key-files.created` exist on disk.
- All 4 task commits referenced above are present in `git log`:
  - `1a767e5` — feat(03-01) Task 1
  - `abd6345` — feat(03-01) Task 2
  - `a99fd61` — fix(03-01) Rule 1 deviation
  - `b06dcec` — test(03-01) Task 3
- The plan-metadata commit follows this SUMMARY landing on disk.

---

*Phase: 03-fastapi-service-persistent-storage*
*Plan: 01 (Wave 1 — storage layer)*
*Completed: 2026-05-16*
