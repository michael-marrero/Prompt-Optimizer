---
phase: 03-fastapi-service-persistent-storage
verified: 2026-05-17T12:00:00Z
status: passed
score: 22/22 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: n/a
  gaps_closed: []
  gaps_remaining: []
  regressions: []
---

# Phase 3: FastAPI Service & Persistent Storage Verification Report

**Phase Goal:** A running `uvicorn apps.api.main:app` process exposes thread CRUD, settings, and `POST /threads/{id}/turn` over SSE; routing artifacts load once at lifespan startup; SQLite (WAL + busy_timeout) persists threads, messages, routing decisions, and large blobs by reference; integration tests exercise streaming end-to-end without a browser.

**Verified:** 2026-05-17T12:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Mapped to ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `uvicorn apps.api.main:app` boots in <3 s | VERIFIED | `apps/api/tests/test_boot_smoke.py::test_boot_under_3_seconds` passes; spot-check shows 2.56s wall (1.65s Python) on warm cache |
| 2 | Joblib artifacts load exactly once at lifespan | VERIFIED | `apps/api/lifespan.py:139` calls `_load_default_artifacts()` once; `apps/api/tests/test_health.py::test_artifacts_loaded_once` monkeypatches a counter and asserts call count = 1 |
| 3 | `GET /healthz` served on `/api/v1/healthz` | VERIFIED | `apps/api/routes/health.py:133-178`; `apps/api/tests/test_health.py::test_healthz_status_dots` passes |
| 4 | Thread CRUD on `POST/GET/PATCH/DELETE /threads` | VERIFIED | `apps/api/routes/threads.py:118-211` implements all five endpoints; `apps/api/tests/test_threads_crud.py` 10 tests pass; `test_all_phase_3_routes_mounted` confirms paths mounted |
| 5 | `POST /threads/{id}/turn` streams SSE `ChatChunk`s | VERIFIED | `apps/api/routes/turn.py:317-590` implements EventSourceResponse; `apps/api/tests/test_turn_streaming.py::test_streams_chatchunks` confirms event stream + named events keyed by `chunk.type` |
| 6 | 15-second SSE heartbeat during long agent runs | VERIFIED | `apps/api/routes/turn.py:590` uses `EventSourceResponse(event_stream(), ping=15)`; `test_heartbeat_emits` proves comment-line `:` heartbeats fire via monkeypatched ping interval |
| 7 | `request.is_disconnected()` cancels upstream within 2s | VERIFIED | `apps/api/routes/turn.py:494` polls disconnect; `apps/api/routes/turn.py:496-514` re-raises CancelledError after StreamError+Done; `test_cancellation_within_2s` enforces `elapsed < 2.0s` |
| 8 | One transaction per turn (1 thread row, 2 messages, 1 routing_decision) | VERIFIED | `apps/api/db/queries.py:429-527 persist_turn` wraps three inserts in ONE `BEGIN/COMMIT`; `apps/api/tests/test_turn_streaming.py::test_one_transaction_per_turn` asserts row counts |
| 9 | Assistant `content_blocks` JSON contains every non-TextDelta chunk | VERIFIED | `apps/api/db/queries.py:460-477` collapses TextDelta→text, non-TextDelta→content_blocks JSON; `test_one_transaction_per_turn` asserts `ToolCall in content_blocks; TextDelta not in content_blocks` |
| 10 | `PRAGMA journal_mode == wal` | VERIFIED | `apps/api/db/connect.py:81` executes `PRAGMA journal_mode=WAL`; `apps/api/tests/test_migrations.py::test_pragmas_applied` asserts WAL (file DBs) / memory (in-memory) |
| 11 | `PRAGMA busy_timeout == 5000` | VERIFIED | `apps/api/db/connect.py:83` executes `PRAGMA busy_timeout=5000`; test asserts `bt == 5000` |
| 12 | `PRAGMA foreign_keys == 1` | VERIFIED | `apps/api/db/connect.py:88`; test asserts `fk == 1` (required for D-13 cascade) |
| 13 | Routing decisions appended as JSON lines to `.planning/data/routing_decisions.jsonl` | VERIFIED | `apps/api/jsonl_log.py:76-141` writes one line per decision at decide-time (D-05); `apps/api/routes/turn.py:416` calls writer BEFORE adapter dispatch; `test_jsonl_log_appended` validates 8 canonical keys |
| 14 | Screenshots ≥256 KB written under `~/.prompt-optimizer/blobs/<sha256>` | VERIFIED | `apps/api/blobs.py:128-185 _maybe_externalize_screenshot` uses `INLINE_THRESHOLD_BYTES = 256*1024`; `apps/api/tests/test_blobs_by_hash.py::test_large_screenshot_becomes_ref` + `test_screenshot_chunk_externalized_in_stream` pass |
| 15 | Large blobs referenced by sha256 hash from DB row | VERIFIED | `apps/api/blobs.py:182-184` returns chunk with `image_ref=str(target)`; persisted in `content_blocks` JSON via `persist_turn`; cascade unlink walks JSON refs in `delete_thread` |
| 16 | Computer-use simulation test validates blob path | VERIFIED | `apps/api/tests/test_blobs_by_hash.py::test_screenshot_chunk_externalized_in_stream` simulates a turn emitting a Screenshot and asserts file lands at `<BLOBS_DIR>/<sha>.png` |
| 17 | Schema migration v0→v1 without data loss | VERIFIED | `apps/api/db/migrate.py:109-171 up_to_latest`; `apps/api/db/migrations/schema_v0.sql` (4 tables) + `schema_v1.sql` (index); `apps/api/tests/test_migrations.py::test_v0_to_v1_preserves_data` seeds v0, migrates, asserts all rows by literal ID + index landed |
| 18 | CORS explicit `http://localhost:3000` origin (no `allow_origins=["*"]`) | VERIFIED | `apps/api/main.py:95-99` reads env or defaults to `["http://localhost:3000"]`; `apps/api/tests/test_cors.py` 3 tests pass (allowed, rejected evil, env-override) |
| 19 | BYOK keys never appear in DB | VERIFIED | `apps/api/tests/test_secure_no_key_in_logs.py::test_secure_no_key_in_logs_after_patch_settings` scans threads/messages/routing_decisions/schema_meta for key prefix — zero matches across all 4 disclosure tests |
| 20 | BYOK keys never appear in log lines (regression) | VERIFIED | RedactionFilter installed at `apps/api/__init__.py` import time; `test_secure_no_key_in_logs.py` 4 tests capture DEBUG-level logs and assert OPENROUTER_KEY / ANTHROPIC_KEY / BEARER_KEY are redacted |
| 21 | BYOK keys never appear in `settings.json` (D-11) | VERIFIED | `apps/api/routes/settings.py:294 pop("keys")` ensures `write_settings_file` never sees keys; `test_secure_no_key_in_logs_after_patch_settings` reads `SETTINGS_PATH` and asserts absence |
| 22 | Integration tests use `httpx AsyncClient + ASGITransport` (no TestClient) | VERIFIED | `apps/api/tests/conftest.py:124-155 asgi_client` fixture uses `httpx.ASGITransport(app=app)`; `apps/api/tests/test_smoke.py::test_no_testclient_imports_under_apps_api_tests` greps for forbidden imports — zero matches |

**Score:** 22/22 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `apps/api/main.py` | App constructor + CORS + lifespan + route mounts | VERIFIED | 135 LOC; `create_app()` mounts health, threads, settings, turn, rename routers; CORS via env or default `["http://localhost:3000"]` |
| `apps/api/lifespan.py` | D-15 lifespan ordering | VERIFIED | 180 LOC; 7-step order: open DB → migrate → load artifacts → load settings → KeyStore → empty adapter registry → cache schema_version; defensive close in finally |
| `apps/api/paths.py` | Path constants + env override | VERIFIED | 70 LOC; `USER_HOME`, `DB_PATH`, `BLOBS_DIR`, `SETTINGS_PATH`, `JSONL_LOG_PATH`; honors `PROMPT_OPTIMIZER_HOME` |
| `apps/api/settings.py` | D-11 atomic write + D-12 STRICT AND | VERIFIED | 181 LOC; `write_settings_file` uses `tmp.replace(target)`; `computer_use_enabled` requires env AND settings gate |
| `apps/api/blobs.py` | sha256 by-hash transcoder | VERIFIED | 228 LOC; `_maybe_externalize_screenshot`, `_collect_blob_refs_from_content_blocks`, `_is_inside_blobs_dir` (path-traversal defense) |
| `apps/api/jsonl_log.py` | D-05 / STORE-06 jsonl appender | VERIFIED | 142 LOC; 8 canonical fields appended at decide-time |
| `apps/api/routes/health.py` | D-18 healthz with adapter status | VERIFIED | 178 LOC; read-only KeyStore/env/settings checks; never constructs adapters |
| `apps/api/routes/threads.py` | API-03 thread CRUD | VERIFIED | 211 LOC; POST/GET/PATCH/DELETE; 204 on delete; cascade via FK+pragma |
| `apps/api/routes/settings.py` | D-10 PATCH merge + masked GET | VERIFIED | 317 LOC; JSON Merge Patch via Pydantic `exclude_unset`; keys popped before settings.json write; adapter cache cleared |
| `apps/api/routes/turn.py` | API-02/05/06/07 + STORE-05/06 heart | VERIFIED | 590 LOC; `asyncio.to_thread(decide)`; `EventSourceResponse(ping=15)`; buffer-and-persist-on-Done; jsonl BEFORE adapter dispatch; override synthesis; D-12 gate; CancelledError handler |
| `apps/api/routes/rename.py` | D-17 one-shot OpenRouter rename | VERIFIED | 302 LOC; fresh adapter; tiktoken pre-flight (413); ≤60 char trim; plain JSON response; never SSE |
| `apps/api/db/connect.py` | D-03 four pragmas in order | VERIFIED | 92 LOC; WAL → NORMAL → busy_timeout=5000 → foreign_keys=ON; commit |
| `apps/api/db/migrate.py` | D-02 runner | VERIFIED | 172 LOC; hand-rolled; version-gate idempotent; BEGIN/COMMIT per migration |
| `apps/api/db/migrations/schema_v0.sql` | D-13 four-table schema | VERIFIED | threads/messages/routing_decisions/schema_meta with FK ON DELETE CASCADE; CHECK constraints on role + status |
| `apps/api/db/migrations/schema_v1.sql` | First follow-up migration | VERIFIED | `CREATE INDEX idx_messages_thread_id_created_at ON messages(thread_id, created_at)` |
| `apps/api/db/models.py` | Pydantic row models | VERIFIED | 152 LOC; frozen Thread/Message/RoutingDecision; non-frozen ThreadCreate/ThreadUpdate |
| `apps/api/db/queries.py` | D-01 typed async helpers + persist_turn ONE-tx + delete cascade | VERIFIED | 551 LOC; 11 functions; persist_turn is ONE BEGIN/COMMIT; delete_thread does blobs-FIRST-then-DB (D-14) |
| `apps/api/tests/conftest.py` | Wave 0 fixtures | VERIFIED | 225 LOC; `aiosqlite_inmemory_db`, `asgi_client`, `app_factory` with B3 lazy-import pattern |
| `apps/api/tests/test_smoke.py` | Wave 0 sanity + API-08 negative grep | VERIFIED | 180 LOC; deps importable + paths + env override + fake adapter + negative-grep guard |
| `apps/api/tests/test_migrations.py` | STORE-01/02/03 | VERIFIED | 4 tests pass: four-table presence, pragmas applied, idempotent, v0→v1 round-trip |
| `apps/api/tests/test_health.py` | API-01 / OSS-05 / D-18 | VERIFIED | 5 tests pass: artifacts loaded once, pragmas applied, status dots |
| `apps/api/tests/test_cors.py` | OSS-05 | VERIFIED | 3 tests pass: allowed localhost, rejected evil, env override |
| `apps/api/tests/test_threads_crud.py` | API-03 + cascade | VERIFIED | 10 tests pass including `test_delete_unlinks_blobs` |
| `apps/api/tests/test_settings.py` | D-10/D-11/D-15 | VERIFIED | 8 tests pass: GET masked, PATCH merge, atomic write, adapter cache clear |
| `apps/api/tests/test_turn_streaming.py` | API-02/05/06/07 + STORE-05/06 | VERIFIED | 9 tests pass: streams, decide_in_thread, heartbeat, 2s cancellation, ONE transaction, jsonl, override, opt-out gate, 404 |
| `apps/api/tests/test_blobs_by_hash.py` | STORE-04 + D-14 | VERIFIED | 9 tests pass: inline/external, idempotent, race-safe tmp suffix, ext honored, JSON walk, path-traversal defense, integration |
| `apps/api/tests/test_rename.py` | D-17 + API-04 | VERIFIED | 8 tests pass: happy path, 413 cap, ≤60 trim, brain bypass, fresh adapter, 404, quote-strip, missing key 400 |
| `apps/api/tests/test_secure_no_key_in_logs.py` | API-04 / SECURE-04 | VERIFIED | 4 tests pass: PATCH/turn/Anthropic/Bearer disclosure-regression across logs/DB/settings/jsonl |
| `apps/api/tests/test_boot_smoke.py` | ROADMAP SC #1 boot under 3s | VERIFIED | 3 tests pass: subprocess <3s, FastAPI instance, all routes mounted |
| `pyproject.toml` Phase 3 deps | fastapi, uvicorn[standard], sse-starlette, aiosqlite, httpx-sse | VERIFIED | All present; version pins: fastapi>=0.115,<1.0; uvicorn[standard]>=0.30,<1.0; sse-starlette>=2.1,<4.0; aiosqlite>=0.20,<1.0; dev: httpx-sse>=0.4,<1.0 |
| `.env.example` | Phase 3 env vars enumerated | VERIFIED | Contains OPENROUTER_API_KEY, ANTHROPIC_API_KEY, COMPUTER_USE_OPT_IN, PROMPT_OPTIMIZER_HOME (commented), PROMPT_OPTIMIZER_CORS_ORIGINS (commented) |
| `.gitignore` | DB sidecars + jsonl excluded | VERIFIED | `*.db`, `*.db-journal`, `*.db-wal`, `*.db-shm`, `chat.db`, `.planning/data/` all listed |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `main.py` | `lifespan.py` | `FastAPI(lifespan=lifespan)` | WIRED | line 83 |
| `main.py` | `routes/*.py` | `app.include_router(...)` | WIRED | lines 123-127 — all 5 routers (health, threads, settings, turn, rename) |
| `lifespan.py` | `src.routing.decide._load_default_artifacts` | direct import | WIRED | line 90; one-directional import (D-18) |
| `lifespan.py` | `db.connect.open_db` | `await open_db(DB_PATH)` | WIRED | line 129 |
| `lifespan.py` | `db.migrate.up_to_latest` | `await up_to_latest(app.state.db)` | WIRED | line 132 |
| `routes/turn.py` | `decide()` via `asyncio.to_thread` | `await asyncio.to_thread(decide, ...)` | WIRED | line 385-391 (API-07 / D-16) |
| `routes/turn.py` | `jsonl_log.append_routing_decisions_jsonl` | `await ...` BEFORE adapter | WIRED | line 416 (D-05) |
| `routes/turn.py` | `db.queries.persist_turn` | `await persist_turn(...)` in finally | WIRED | line 540 |
| `routes/turn.py` | `blobs._maybe_externalize_screenshot` | conditional inside event_stream | WIRED | line 478-479 |
| `routes/turn.py` | `EventSourceResponse(ping=15)` | terminal `return` | WIRED | line 590 |
| `routes/threads.py` | `db.queries.delete_thread` | cascade unlink | WIRED | line 206 (which calls blobs walk + FK cascade) |
| `routes/settings.py` | `app.state.adapters.clear()` | after settings write | WIRED | line 307 (D-15 cache invalidation) |
| `routes/rename.py` | fresh `OpenRouterAdapter` (NOT cached) | `OpenRouterAdapter(api_key=key, ...)` | WIRED | line 251 (D-17 defense) |
| `db.queries.persist_turn` | `BEGIN/COMMIT` | explicit `db.execute("BEGIN")` + `db.commit()` + `rollback` on exception | WIRED | lines 496-527 |
| `db.queries.delete_thread` | blobs-FIRST-then-DB unlink | walk content_blocks, `_is_inside_blobs_dir` guard, unlink, then DELETE | WIRED | lines 230-263 (D-14) |
| `db.connect.open_db` | 4 pragmas + commit | sequence of execute() | WIRED | lines 81-90 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `routes/turn.py:event_stream` | `buffer: list[ChatChunk]` | `adapter.stream(...)` async generator | Yes — adapter yields real ChatChunk instances; test confirms TextDelta + ToolCall + Done | FLOWING |
| `routes/turn.py:persist_turn call` | `content_blocks JSON` | `[c.model_dump() for c in buffer if not TextDelta]` | Yes — `test_one_transaction_per_turn` asserts ToolCall.type appears in JSON | FLOWING |
| `routes/turn.py:event_stream` | `decision` | `await asyncio.to_thread(decide, ...)` or override synthesis | Yes — `test_decide_runs_in_thread` confirms decide called via to_thread; `test_override_backend` confirms override synthesis | FLOWING |
| `routes/health.py:healthz` | `adapters` dict | `_openrouter_status` / `_claude_code_status` / `_computer_use_status` consulting KeyStore + settings + env | Yes — `test_healthz_status_dots` confirms ready/missing_key/opt_out states | FLOWING |
| `routes/threads.py:get_threads` | `threads: list[Thread]` | `list_threads(db)` SQL: `SELECT id, title, created_at, updated_at FROM threads ORDER BY created_at DESC LIMIT ? OFFSET ?` | Yes — real query against shared aiosqlite connection | FLOWING |
| `routes/settings.py:get_settings` | `keys_block + non-key fields` | KeyStore.get() + app.state.settings dict | Yes — masked key form returns from real KeyStore lookups | FLOWING |
| `db.queries.persist_turn` | `signals_json` | `json.dumps(decision.signals)` | Yes — Phase 1 decide() produces signals dict; override synthesizes `{"override": True}` | FLOWING |
| `blobs._maybe_externalize_screenshot` | `target = BLOBS_DIR / f"{sha}.{ext}"` | base64 decode → sha256 → atomic write | Yes — `test_large_screenshot_becomes_ref` confirms file lands on disk and image_ref is set | FLOWING |
| `jsonl_log.append_routing_decisions_jsonl` | `record` | `getattr(decision, ...)` on real RoutingDecision | Yes — `test_jsonl_log_appended` asserts 8 canonical fields populated | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| App boots under 3 seconds | `time uv run python -c "from apps.api.main import app; print('ok')"` | 2.56s wall (1.65s Python user), printed `ok` | PASS |
| Full non-live test suite passes | `uv run pytest -m 'not live' --timeout=60` | 301 passed, 2 skipped, 3 deselected in 84.45s | PASS |
| Phase 1 D-18 import-graph guard green | `uv run pytest src/routing/tests/test_decide_smoke.py -x` | 7 passed in 1.87s | PASS |
| Phase 3 test suite (full) | `uv run pytest apps/api/tests/ -x --timeout=60` | 68 passed in 11.68s | PASS |
| Boot smoke test passes | `uv run pytest apps/api/tests/test_boot_smoke.py -v --timeout=60` | 3 passed in 3.14s | PASS |
| Heart-of-phase tests (turn + blobs + secure + migrations) | `uv run pytest apps/api/tests/test_turn_streaming.py apps/api/tests/test_blobs_by_hash.py apps/api/tests/test_secure_no_key_in_logs.py apps/api/tests/test_migrations.py -v --timeout=60` | 26 passed in 5.68s | PASS |
| API-08 negative grep (no TestClient) | `grep -rE 'from fastapi.testclient\|fastapi\.testclient\.TestClient' apps/api/tests/` | exit 1 (no matches) | PASS |
| OSS-05 negative grep (no wildcard CORS) | `grep -rE 'allow_origins=\["\*"\]' apps/api/` after filtering docstrings | only docstring-cite of forbidden pattern remains; no real `allow_origins=["*"]` in code | PASS |
| sys.path.append anti-pattern absent | `grep -r 'sys.path.append' apps/api/` | exit 1 (no matches) | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| API-01 | 03-02 | FastAPI loads joblib artifacts once at lifespan | SATISFIED | `lifespan.py:139`, `test_artifacts_loaded_once` |
| API-02 | 03-04 | POST /threads/{id}/turn over SSE | SATISFIED | `routes/turn.py:317-590`, `test_streams_chatchunks` |
| API-03 | 03-03, 03-05 | Thread CRUD + cascade | SATISFIED | `routes/threads.py`, `test_threads_crud.py` (10 tests) |
| API-04 | 03-03, 03-06 | BYOK keys in-process only | SATISFIED | KeyStore + `routes/settings.py` + `test_secure_no_key_in_logs.py` (4 tests) |
| API-05 | 03-04 | SSE heartbeat every 15s | SATISFIED | `ping=15` + `test_heartbeat_emits` |
| API-06 | 03-04 | Client disconnect cancels within 2s | SATISFIED | `is_disconnected` poll + `test_cancellation_within_2s` |
| API-07 | 03-04 | sklearn calls in asyncio.to_thread | SATISFIED | `routes/turn.py:385` + `test_decide_runs_in_thread` |
| API-08 | 03-00 | httpx AsyncClient + ASGITransport | SATISFIED | `conftest.py:asgi_client` + negative-grep guard test |
| STORE-01 | 03-01 | aiosqlite WAL + busy_timeout=5000 | SATISFIED | `db/connect.py` + `test_pragmas_applied` |
| STORE-02 | 03-01 | Threads/messages/routing_decisions schema | SATISFIED | `schema_v0.sql` + `test_schema_v0_has_all_four_tables` |
| STORE-03 | 03-01 | Forward-only migrations | SATISFIED | `db/migrate.py` + `test_v0_to_v1_preserves_data` |
| STORE-04 | 03-05 | Large blobs by sha256 ref | SATISFIED | `blobs.py` + `test_blobs_by_hash.py` (9 tests) |
| STORE-05 | 03-04 | One transaction per turn on Done | SATISFIED | `persist_turn` + `test_one_transaction_per_turn` |
| STORE-06 | 03-04 | Routing decisions appended to jsonl | SATISFIED | `jsonl_log.py` + `test_jsonl_log_appended` |
| OSS-05 | 03-02 | Explicit CORS origin, no wildcard | SATISFIED | `main.py:95-99` + `test_cors.py` (3 tests) |

### Anti-Patterns Found

None. Spot-checks:
- Debt markers (`TBD`, `FIXME`, `XXX`) — XXX hits are inside test fixture key padding (`"sk-or-v1-XXXXXXXX..."`) and example docstrings, not debt markers.
- No `sys.path.append` anywhere under `apps/api/`.
- No `TestClient` imports under `apps/api/tests/` (API-08 enforced by source-level negative-grep test).
- No `allow_origins=["*"]` (only docstring documenting it as forbidden).
- No reverse imports from `src/routing/` into `apps/api/` (D-18 import-graph guard green).
- All async DB writes go through parameterized `?` placeholders (T-03-SQLi mitigated).
- Path-traversal defense at unlink time (`_is_inside_blobs_dir`) covers T-03-Path.

### Locked-Decision Cross-Check (D-01 through D-20)

| D-XX | Decision | Status |
|------|----------|--------|
| D-01 | Raw aiosqlite + Pydantic + ~10-12 typed async queries | VERIFIED (`db/queries.py` 11 functions; no SQLAlchemy/SQLModel) |
| D-02 | Hand-rolled `schema_v{N}.sql` runner | VERIFIED (`db/migrate.py` 172 LOC; no Alembic/yoyo) |
| D-03 | Four pragmas on first connect in order | VERIFIED (`db/connect.py:81-88`) |
| D-04 | Buffer-and-write-once on Done | VERIFIED (`routes/turn.py:464-523`; `persist_turn` is ONE BEGIN/COMMIT) |
| D-05 | jsonl appended BEFORE adapter dispatch | VERIFIED (`routes/turn.py:416` runs before `_get_or_create_adapter` line 425) |
| D-06 | sse-starlette EventSourceResponse ping=15 | VERIFIED (`routes/turn.py:590`) |
| D-07 | Named SSE events keyed by chunk.type | VERIFIED (`routes/turn.py:481-483 ServerSentEvent(event=chunk.type, data=chunk.model_dump_json())`) |
| D-08 | HTTPException pre-stream; StreamError+Done mid-stream | VERIFIED (`routes/turn.py:344-347` 404; `routes/turn.py:498-513` mid-stream cancel emits StreamError + Done) |
| D-09 | `/api/v1` URL namespace | VERIFIED (all routers use `prefix="/api/v1"`) |
| D-10 | PATCH bulk merge + GET masked | VERIFIED (`routes/settings.py:276 model_dump(exclude_unset=True)`, `_mask_key` masks plaintext) |
| D-11 | Atomic settings write (tmp + replace) | VERIFIED (`settings.py:142-147 tmp.replace(SETTINGS_PATH)`) |
| D-12 | Computer-use STRICT AND env+settings | VERIFIED (`settings.py:178-180 env_ok AND setting_ok`) |
| D-13 | Four-table schema with ON DELETE CASCADE | VERIFIED (`schema_v0.sql:34-75`) |
| D-14 | Blobs unlinked BEFORE DB delete | VERIFIED (`db/queries.py:230-263 delete_thread`) |
| D-15 | Lazy adapter cache; clear on settings PATCH | VERIFIED (`lifespan.py:155-156` empty registry; `routes/settings.py:307 clear()`; `routes/turn.py:270-272` lazy build) |
| D-16 | asyncio.to_thread (not run_in_threadpool) | VERIFIED (`routes/turn.py:385 asyncio.to_thread(decide, ...)`) |
| D-17 | Fresh OpenRouterAdapter for rename | VERIFIED (`routes/rename.py:251 OpenRouterAdapter(...)` — not from `app.state.adapters`) |
| D-18 | Read-only healthz precheck | VERIFIED (`routes/health.py:64-130` only consults KeyStore + settings + env; never constructs adapter) |
| D-19 | INFO log lines at per-turn boundaries | VERIFIED (`routes/turn.py:365 turn_start`, `:399 routing_decision`, `:572 turn_done`) |
| D-20 | httpx + ASGITransport tests | VERIFIED (`tests/conftest.py asgi_client` + 20+ tests use it) |

### Human Verification Required

None for codebase verification. Three items in `03-VALIDATION.md` are documented as live/manual-only and explicitly deferred to non-CI exercises (live OpenRouter SSE, real 15s heartbeat against live agent run, live Next.js CORS preflight) — these are out of automated scope by design and do not block phase completion.

### Gaps Summary

No gaps found. Every observable truth derived from the phase goal and ROADMAP success criteria is backed by source code + a passing test. Every locked decision (D-01 through D-20) is reflected verbatim in the implementation. Every Phase 3 requirement (API-01..08, STORE-01..06, OSS-05) is satisfied. The full non-live test suite passes (301 passed / 2 skipped / 3 deselected), the Phase 1 D-18 import-graph guard remains green (7/7), and all negative-grep anti-pattern guards return clean.

The boot smoke test passes within budget (2.56s wall on a warm cache; budget is 3.0s). The SSE end-to-end suite covers the streaming wire format, heartbeat, cancellation, JSONL log, ONE-transaction persistence, override-backend bypass, and computer-use opt-out gate. The blob storage suite covers inline/external threshold, idempotency, race-safe tmp suffix, path-traversal defense, and end-to-end Screenshot externalization through a real `event_stream`. The secure-disclosure suite covers four key shapes across four disclosure surfaces (logs, DB, settings.json, jsonl). The schema migration round-trip preserves seeded data and lands the v1 index.

Phase 3 is goal-achieved and ready to release.

---

*Verified: 2026-05-17T12:00:00Z*
*Verifier: Claude (gsd-verifier)*
