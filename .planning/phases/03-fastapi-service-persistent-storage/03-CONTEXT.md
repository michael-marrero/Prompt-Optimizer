# Phase 3: FastAPI Service & Persistent Storage - Context

**Gathered:** 2026-05-15
**Status:** Ready for planning

<domain>
## Phase Boundary

A running `uvicorn apps.api.main:app` process exposes thread CRUD, settings, and `POST /api/v1/threads/{id}/turn` over SSE. It fuses three pre-existing layers:

1. **Phase 1 routing brain** — `src.routing.decide(prompt, history, artifacts, settings) -> RoutingDecision` (pure-function, FastAPI-free import graph; D-18 guard intact).
2. **Phase 2 adapter triplet** — `apps.api.backends.{openrouter, claude_code, computer_use}` each implementing the `BackendAdapter` Protocol → `AsyncIterator[ChatChunk]`.
3. **Persistent storage** — `aiosqlite 0.20+` over a `~/.prompt-optimizer/chat.db` (WAL, busy_timeout=5000) with three tables (`threads`, `messages`, `routing_decisions`), large blobs (≥256 KB screenshots / diffs) referenced by `~/.prompt-optimizer/blobs/<sha256>`, and a per-turn JSONL log at `.planning/data/routing_decisions.jsonl`.

Per-turn lifecycle:

```
POST /api/v1/threads/{thread_id}/turn
  ├─ validate body → fetch thread + history from SQLite
  ├─ await asyncio.to_thread(decide, prompt, history, artifacts, settings)  # API-07
  ├─ append routing_decisions.jsonl line                                    # STORE-06
  ├─ lazily get-or-create app.state.adapters[backend]
  └─ EventSourceResponse(ping=15) streaming named SSE events                # API-05
       event: text_delta\ndata: {…}
       event: tool_call\ndata: {…}
       …
       event: stream_error\ndata: {…}   (optional, on cap/cancel/provider error)
       event: done\ndata: {…}
       └─ on Done: ONE SQLite transaction writes
            user message + assistant message (content_blocks JSON)
            + routing_decisions row
            (STORE-05)
```

Integration tests (API-08) use `httpx AsyncClient + ASGITransport`, never `TestClient`. CORS middleware (OSS-05) allows the explicit Next.js dev origin (`http://localhost:3000`); no wildcard. BYOK keys live in the existing in-process `KeyStore` + optional OS keyring (Phase 2 D-10) and never enter SQLite, settings.json, or any log line (SECURE-04; redaction filter from Phase 2 D-11 still installed at `apps/api/__init__.py` import).

**Verification surface:** `uvicorn apps.api.main:app` boots in <3 s; `pytest apps/api/tests` exercises every endpoint end-to-end with an in-process ASGI client; a schema-migration test round-trips a v0 DB to v1 (STORE-03) without data loss.

**Not in scope (deferred to later phases):**
- Any Next.js / browser code — Phase 4 (Minimal Chat UI: OpenRouter only) and Phase 5 (Feature-Complete UI: all three backends + sidebar + override + status dots + auto-rename).
- Playwright UI E2E, `make setup`, README golden path, fresh-clone UAT, threat-model docs — Phase 6.
- Live retraining loop, v2 routing items, voice / audio, file uploads, MCP marketplace — out of milestone.

</domain>

<decisions>
## Implementation Decisions

### Persistence Layer

- **D-01: Raw `aiosqlite` + Pydantic models + a thin query module.** No SQLModel, no SQLAlchemy, no `databases` package. Queries live in `apps/api/db/queries.py` as ~10–12 async functions (`create_thread`, `get_thread`, `list_threads`, `delete_thread`, `insert_user_message`, `insert_assistant_message_with_blocks`, `insert_routing_decision`, `update_thread_title`, `get_thread_messages`, plus migration helpers). Each query takes a connection + typed args, returns Pydantic models for input/output validation. Phase 2 already pulled `pydantic>=2.6,<3.0` in; we reuse the dep. Aligns with the repo's "filesystem is the database" minimalism (codebase ARCHITECTURE.md) and keeps the wheel slim.

- **D-02: Migrations are a hand-rolled `schema_v{N}.sql` runner.** `apps/api/db/migrate.py` (~40 lines) reads `schema_meta.version` (a single-row table created on first run), applies pending `schema_v0.sql`, `schema_v1.sql`, … in order, and bumps `version` inside the same transaction. Numbered SQL files live in `apps/api/db/migrations/`. The runner is called from the FastAPI lifespan event AFTER opening the connection and setting WAL pragmas. The STORE-03 success-criterion test creates a v0 DB by running only `schema_v0.sql`, then calls `migrate.up_to_latest()` and asserts no data loss + version bump. No Alembic, no yoyo, no SQLAlchemy in the import graph.

- **D-03: WAL + busy_timeout + foreign keys ON FIRST CONNECT.** `apps/api/db/connect.py:open_db()` returns an `aiosqlite.Connection` after executing, in order: `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL`, `PRAGMA busy_timeout=5000`, `PRAGMA foreign_keys=ON`. Verified via the success-criterion #3 test that asserts `PRAGMA journal_mode` returns `wal` and `busy_timeout` returns `5000`. `foreign_keys=ON` is REQUIRED for the ON DELETE CASCADE in D-13 to work (SQLite's foreign-key enforcement is OFF by default per-connection).

- **D-04: One transaction per turn on Done.** Buffer every `ChatChunk` in memory during the stream. When the terminal `Done` chunk arrives, run ONE transaction inside `BEGIN…COMMIT` that writes (a) the user message row, (b) the assistant message row with `content_blocks = JSON([c.model_dump() for c in buffer if not isinstance(c, TextDelta)])` and `text = "".join(c.text for c in buffer if isinstance(c, TextDelta))`, and (c) the `routing_decisions` row. STORE-05 explicit. Partial assistant content is preserved on `StreamError + Done` paths (cap exceeded, cancellation, provider failure) because the buffer accumulates the partial stream before the terminal pair lands. NO per-chunk writes on the hot path.

- **D-05: `routing_decisions.jsonl` is appended at decide()-time, BEFORE adapter dispatch.** After `decide()` returns and before the adapter is consulted, append one JSON line to `.planning/data/routing_decisions.jsonl` with `{turn_id, thread_id, timestamp_iso, backend, model_or_agent, rationale, confidence, signals}`. This captures EVERY decision the brain emitted — including turns that the user cancels mid-stream, that hit a cost cap, or that error before a token streams. The DB row (STORE-02 `routing_decisions` table) is the persistence-with-DB-foreign-key path; the JSONL is the offline-analysis path that mirrors the Phase 1 canary CSV shape (`evaluate_routing.py` consumer pattern). Slight asymmetry (JSONL has cancelled rows that DB doesn't) is documented in the file's header comment.

### SSE Wire Layer

- **D-06: `sse-starlette` `EventSourceResponse` is the streaming primitive.** Add `sse-starlette>=2.1,<3.0` as a base dep. The library handles three things we'd otherwise hand-roll: (a) automatic 15-second heartbeat via the `ping=15` constructor param → satisfies API-05 by emitting `: ping` comment lines; (b) `request.is_disconnected()` polling that aborts the generator within the cancellation window → satisfies API-06; (c) ASGI `send()` plumbing that works under both Uvicorn and Hypercorn. ROADMAP Phase 3 SC #2 ("heartbeat event at the 15-second mark") and SC #2 ("`request.is_disconnected()` polling cancels the upstream provider call within 2 seconds") both map directly. The library is actively maintained (last release within the year) and is the de-facto SSE choice in the FastAPI ecosystem.

- **D-07: Named SSE events keyed by `chunk.type`.** Each chunk emits as `event: <chunk.type>\ndata: <chunk.model_dump_json()>\n\n`. Discriminator values from Phase 2 D-01 — `text_delta`, `tool_call`, `tool_result`, `file_diff`, `screenshot`, `stream_error`, `done` — are the event names. Browser EventSource API and AI SDK v5 both support `addEventListener('text_delta', …)`-style dispatch, which is cleaner than `data:`-only parsing. Heartbeat lines are `: ping` SSE comments (sse-starlette default; comments are valid SSE per the WHATWG spec and ignored by EventSource). Phase 4's Next.js parser at `apps/web/app/api/chat/route.ts` MUST honor this wire format verbatim. If Phase 4 ends up wanting the Vercel AI SDK v5 "UI Message Stream Protocol" (numeric-prefix lines), the Next.js proxy translates — Phase 3 stays JSON-only.

- **D-08: Pre-stream errors are FastAPI `HTTPException`; mid-stream errors are `StreamError` ChatChunk + `Done`.** Two clean boundaries: (a) before the SSE response starts (validation 422, missing thread 404, missing backend key 400, malformed body 422) → standard `HTTPException(status_code, detail="…")` with `{"detail": "…"}` JSON body; (b) after the SSE response opens (200 OK + `text/event-stream`) → all errors become `StreamError` chunks per Phase 2 D-06 closed vocabulary (`cost_cap_exceeded`, `step_cap_exceeded`, `cancelled`, `rate_limited`, `auth_failed`, `provider_unavailable`, `timeout`, `validation_error`, `internal_error`) followed by the terminal `Done`. No RFC 7807, no custom envelope — `HTTPException` is the FastAPI idiom and the SSE side already has a typed contract from Phase 2.

- **D-09: `/api/v1` URL namespace from day one.** All routes under `/api/v1`: `GET /api/v1/healthz`, `POST/GET/PATCH/DELETE /api/v1/threads(/{id})`, `POST /api/v1/threads/{id}/turn`, `POST /api/v1/threads/{id}/rename` (D-17 below), `GET/PATCH /api/v1/settings`. Aligns with Phase 5 UI-11's pre-existing `/api/v1/models` reference (Phase 5 adds that endpoint; Phase 3 establishes the namespace). Future v2 breaking changes can land under `/api/v2` without coexistence churn. Cost: ~6-char prefix on every route.

### Settings & BYOK API

- **D-10: Bulk `PATCH /api/v1/settings` with JSON Merge Patch semantics.** Single endpoint accepts a partial settings document: keys omitted from the patch are unchanged. Body shape:
  ```json
  {
    "keys": {"openrouter": "sk-or-v1-...", "anthropic": "sk-ant-..."},
    "backends_enabled": {"openrouter": true, "claude_code": true, "computer_use": false},
    "computer_use_opt_in": true,
    "default_max_cost_usd": 0.50
  }
  ```
  `GET /api/v1/settings` returns the same shape with **keys ALWAYS masked** — `{"openrouter": {"present": true, "masked": "sk-…ABC123"}, "anthropic": {"present": false}}`. Plaintext keys are write-only on the wire. SECURE-04 regression test asserts that no GET response and no log line contains the plaintext.

- **D-11: Non-key settings persist to `~/.prompt-optimizer/settings.json`.** Keys stay in `KeyStore` (Phase 2 D-10: in-memory primary, optional OS keyring fallback) — they NEVER hit SQLite or `settings.json`. Everything else (`backends_enabled`, `computer_use_opt_in`, `default_max_cost_usd`, future toggles) lives in a small JSON file under the user home root. Loaded at lifespan startup; `PATCH /settings` rewrites the file atomically (`tmp_path.rename(target)` pattern). Settings reset and chat reset are independent — wiping `chat.db` does not wipe preferences. Settings file shipped with sensible defaults if absent on first boot.

- **D-12: STRICT AND-semantics for computer-use enable.** `computer_use_enabled(settings) -> bool` returns `True` only when `os.environ.get("COMPUTER_USE_OPT_IN") == "1"` AND `settings["computer_use_opt_in"] is True`. Both gates required. Matches ROADMAP Phase 6 SC #5 verbatim: "computer-use is OFF unless both `COMPUTER_USE_OPT_IN=1` and the in-app toggle are set." UI toggle alone (without env) leaves computer-use OFF — user must also set the env var (likely via `.env`). Most defensive default. The `ComputerUseAdapter.__init__` check from Phase 2 D-15 (specifics line 263) is extended to consult settings as well; the adapter raises `RuntimeError("computer-use is OFF — set COMPUTER_USE_OPT_IN=1 in env AND enable in settings panel")` if either gate is unset.

### Lifespan & Adapter Construction

- **D-13: SQLite schema enforces ON DELETE CASCADE for thread → messages → routing_decisions.** Foreign-key cascade so `DELETE FROM threads WHERE id=?` removes all child rows in one statement. Pairs with D-14 below. Schema sketch (canonical SQL lives in `apps/api/db/migrations/schema_v0.sql`):
  ```sql
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
  CREATE TABLE schema_meta (version INTEGER NOT NULL);
  INSERT INTO schema_meta (version) VALUES (0);
  ```

- **D-14: Blob cascade unlink on thread delete (STORE-04).** `DELETE /api/v1/threads/{id}` walks the thread's `messages.content_blocks` JSON, collects every `image_ref` / `diff_ref` path, then unlinks each file (`Path(p).unlink(missing_ok=True)`), then runs the DB delete (cascade). Order matters: unlink blobs BEFORE DB rows so an interrupted delete leaves orphan blobs (recoverable by a future `make gc-blobs`) rather than stale DB rows pointing to missing files. Phase 5 UI-02 (`thread delete` button) flows through this naturally.

- **D-15: Lazy per-turn adapter construction with cached instances.** Lifespan creates an EMPTY adapter registry: `app.state.adapters = {}`. The first turn that resolves to a given backend instantiates the adapter (reading current `KeyStore` + `settings`) and caches it in `app.state.adapters[backend]`. Subsequent turns reuse. `PATCH /api/v1/settings` invalidates the cache via `app.state.adapters.clear()` so the next turn rebuilds with the new keys / toggles. **Crucial UX win:** the server still boots and serves `/healthz`, `/threads`, OpenRouter-routable turns even when `ANTHROPIC_API_KEY` or `COMPUTER_USE_OPT_IN` are unset — only the specific backend that's selected raises. Matches the BYOK ergonomic (user runs server, enters keys via UI Phase 5, never needs to restart).

- **D-16: `decide()` runs via `asyncio.to_thread`, not `run_in_threadpool`.** API-07 says verbatim "wrapped in `run_in_threadpool`" — we interpret this as "must NOT block the event loop with the synchronous sklearn predict_proba." `asyncio.to_thread` (Python 3.9+ stdlib) is semantically identical to `starlette.concurrency.run_in_threadpool` (both delegate to `loop.run_in_executor(None, fn, ...)` with the default ThreadPoolExecutor) but lives in stdlib, doesn't tie us to starlette as a direct dep, and reads more naturally. **REQUIREMENTS.md API-07 wording is updated in this phase** to "Synchronous sklearn `predict` / `predict_proba` calls are wrapped in `asyncio.to_thread` (or equivalent thread-pool offload) when invoked from async handlers."

### Auxiliary Endpoints

- **D-17: Dedicated `POST /api/v1/threads/{id}/rename` endpoint.** Pre-wires Phase 5 UI-14 ("Thread auto-renames from the first user message; cheap-model bypass route; never calls the main router"). Body: `{"first_user_message": "..."}`. Internal implementation instantiates a fresh `OpenRouterAdapter` (NOT the cached one — defensive, single-use), calls `stream()` with `model="openai/gpt-4o-mini"` (hardcoded cheap default; planner may swap to whichever cheapest-quality OpenRouter slug is current at execute time), `max_cost_usd=0.01`, `max_steps=1`, a tight system prompt ("Summarize this user request in 5 words or fewer; respond with the title only, no quotes."). Collects `TextDelta` chunks into a string, trims to ≤60 chars, persists via `update_thread_title`, returns `{"title": "..."}` JSON. NO SSE — it's a small one-shot completion. Bypasses `decide()` entirely → satisfies UI-14's "never calls the main router."

- **D-18: Rich `GET /api/v1/healthz` with backend status.** Single endpoint Phase 5 UI-11 can hit for the status-dot strip — no separate `/api/v1/models` needed in Phase 3 (Phase 5 adds it for model-list refresh, distinct concern). Response shape:
  ```json
  {
    "status": "ok" | "degraded",
    "artifacts_loaded": true,
    "db_ok": true,
    "schema_version": 1,
    "adapters": {
      "openrouter":   {"status": "ready"},
      "claude_code":  {"status": "missing_key", "reason": "ANTHROPIC_API_KEY not set"},
      "computer_use": {"status": "opt_out", "reason": "COMPUTER_USE_OPT_IN not set"}
    },
    "version": "0.1.0"
  }
  ```
  Adapter statuses: `ready` | `missing_key` | `opt_out` | `error` (computed via a lightweight precheck — KeyStore lookup + settings consult — without actually constructing the adapter, so `/healthz` is fast and side-effect-free). HTTP 200 always when the process is alive; `"status": "degraded"` indicates ≥1 adapter not ready. HTTP 500 only when `artifacts_loaded == false` or `db_ok == false` (process is genuinely broken).

### Logging

- **D-19: INFO at per-turn boundaries; DEBUG for chunks; redaction filter from Phase 2 still load-bearing.** Three INFO lines per turn:
  1. `turn_start thread_id=… user_msg_len=…`
  2. `routing_decision backend=… model=… rationale='…' confidence=…`
  3. `turn_done thread_id=… backend=… cost_usd=… tokens_in=… tokens_out=… latency_ms=… status=complete|error|cancelled`

  DEBUG (off by default) logs every `ChatChunk` shape. Uvicorn's default access logs cover HTTP-layer requests. Phase 2 `RedactionFilter` (root-logger filter + `LogRecord` factory) still installed at `apps.api.__init__` import time, so any accidental key in a log record is rewritten before any handler sees it. New regression assertion in Phase 3 tests: hit `PATCH /settings` with a real-shaped `sk-or-v1-XXXX…` value and grep the captured logs for `sk-or-v1` → must return zero matches.

### Test Strategy

- **D-20: Integration tests use `httpx.AsyncClient + ASGITransport`; NO `TestClient` (API-08).** Per the FastAPI / httpx documentation: `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")`. Streaming tests use `async with client.stream("POST", "/api/v1/threads/{id}/turn", ...) as resp` then iterate `resp.aiter_lines()`. The `TestClient` is sync and uses `anyio` worker threads — it does NOT exercise the real async cancellation path and is a well-known foot-gun for SSE testing. Adapter fakes from Phase 2 (`FakeOpenAIClient`, `FakeAnthropicClient`, `fake_claude_code_query`, `FakePlaywrightScreen`) are reused via constructor injection at the lifespan layer (test-mode lifespan overrides `app.state.adapters` with fake-driven instances before any request fires). New shared test fixture: `aiosqlite_inmemory_db` that creates `aiosqlite.connect(":memory:")`, runs `migrate.up_to_latest()`, yields the connection. Every test that needs storage uses this fixture; no file I/O in unit tests.

### Claude's Discretion

The planner / researcher own these implementation details — no user preference was expressed:

- **sse-starlette exact version pin** — researcher picks within `>=2.1,<3.0`; the latest 2.x at planning time is fine.
- **CORS origin defaults** — `http://localhost:3000` (Next.js dev default). Make the list configurable via env (`PROMPT_OPTIMIZER_CORS_ORIGINS`) so contributors on non-default ports can override without code changes.
- **Thread / message / routing_decision ID generation** — `secrets.token_urlsafe(12)` (URL-safe base64, ~16 chars) so IDs are paste-safe and collision-free at single-user scale. Planner may swap for ULID or UUIDv7 if a research finding surfaces a reason.
- **Settings file atomic-write pattern** — `tmp = path.with_suffix(".tmp"); tmp.write_text(json.dumps(...)); tmp.replace(path)`.
- **lifespan loader internals** — `load_joblib_artifacts()` from Phase 1 demo is the canonical loader; lifespan calls it once, stashes in `app.state.artifacts`. Order: open DB → run migrations → set pragmas → load artifacts → load settings → instantiate KeyStore.
- **Turn endpoint request body shape** — `{message: str, override_backend?: "openrouter"|"claude_code"|"computer_use", max_cost_usd?: float}`. The optional `override_backend` is the Phase 5 UI-05 hook (slash command / dropdown override); Phase 3 honors it by bypassing `decide()` when set and synthesizing a `RoutingDecision` with `rationale="user override"`. Phase 5 wires the UI; Phase 3 just lights up the endpoint.
- **Healthz adapter status detection** — read-only checks (KeyStore present + env var + settings flag); never construct the adapter to find out.
- **OpenAPI tags / response models** — let FastAPI generate. One tag per resource (`threads`, `settings`, `health`).
- **Tiktoken pre-flight estimator** — Phase 2 already added `tiktoken`; Phase 3 reuses it only inside the rename endpoint to enforce a hard prompt-length cap on the rename input (to prevent `max_cost_usd=0.01` overrun).
- **Migration test fixture path** — `apps/api/tests/fixtures/schema_v0_seed.sql` seeds a known v0 DB with 1 thread + 2 messages; migration test asserts row counts unchanged after `up_to_latest()`.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner, executor) MUST read these before planning or implementing.**

### Phase Scope & Requirements

- `.planning/ROADMAP.md` §"Phase 3: FastAPI Service & Persistent Storage" — goal, dependencies, requirement mapping, 5 success criteria. Phase boundary is FIXED.
- `.planning/REQUIREMENTS.md` — read API-01 through API-08, STORE-01 through STORE-06, OSS-05 (the 15 requirements assigned to Phase 3). **Update API-07 wording** in this phase to "wrapped in `asyncio.to_thread` (or equivalent thread-pool offload)" per D-16.
- `.planning/PROJECT.md` — Core Value ("quality first, cost as tiebreaker"), constraints (BYOK; single-process Python; open-source local-only).
- `CLAUDE.md` (repo root) — project conventions, GSD workflow enforcement.

### Phase 1 & Phase 2 Carry-Forward (the upstream contract Phase 3 consumes)

- `.planning/phases/01-router-brain-foundation/01-CONTEXT.md` — D-01 (cascade), D-04 (backend sentinels + model strings; `model_or_agent` is a provider-ready string already), D-18 (import-graph guard for `src/routing/`; Phase 3 MUST NOT add `fastapi` / `httpx` / SDK imports to anything in `src/routing/`).
- `.planning/phases/02-backend-adapters-chatchunk-contract/02-CONTEXT.md` — D-01 (`ChatChunk` Pydantic v2 discriminated union; serialise via `model_dump_json`), D-02 (7-variant union), D-04 (terminal `[StreamError]? + Done` invariant), D-06 (`StreamError.code` closed vocabulary), D-08 (per-backend module layout), D-10 (KeyStore optional keyring), D-11 (dotenv + redaction filter at `apps.api.__init__` import), D-14 (Screenshot dual `image_b64`/`image_ref` schema), D-15 (per-iteration step caps), D-17 (PricingTable + `config/pricing.json`), D-19 (shared adapter contract test), D-20 (CI green = unit tests, not live calls).
- `.planning/phases/02-backend-adapters-chatchunk-contract/02-VERIFICATION.md` — Phase 2 closing state; gap-closure plans 02-05/06/07 already shipped (CR-01/02/04/05 closed). All 15 Phase-2 requirements satisfied.
- `src/routing/schema.py` — `RoutingDecision` frozen dataclass; `signals: dict` carries the per-stage telemetry. `Backend = Literal["openrouter","claude_code","computer_use"]` (matches `apps/api/backends/protocol.py:Backend`).
- `src/routing/decide.py` — pure-function entry point Phase 3 calls via `asyncio.to_thread`.
- `apps/api/backends/protocol.py` — `BackendAdapter` Protocol, `Message`, `AdapterOptions` (frozen dataclass: `model`, `max_cost_usd`, `max_steps`, `cwd`, `routing_signals`).
- `apps/api/backends/chunks.py` — `ChatChunk = Annotated[Union[…], Field(discriminator="type")]`, `chat_chunk_adapter = TypeAdapter(ChatChunk)`. Use `chunk.model_dump_json()` for SSE.
- `apps/api/backends/keystore.py` — `KeyStore` (in-memory + optional keyring); `SERVICE_NAME = "prompt-optimizer"`; provider env var map (`OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`).
- `apps/api/backends/{openrouter,claude_code,computer_use}/adapter.py` — concrete adapter implementations Phase 3 lazily constructs (D-15).
- `apps/api/__init__.py` — already calls `dotenv.load_dotenv()` and `install_redaction_filter()` at import. Phase 3 does NOT duplicate.

### Existing Codebase Maps (read before touching repo)

- `.planning/codebase/ARCHITECTURE.md` — pipeline diagram; the **path-discovery / sys.path injection** anti-patterns (use `pathlib.Path(__file__).resolve().parents[N]` and proper packages — NEVER `sys.path.append`).
- `.planning/codebase/STACK.md` — Python 3.10+; pyproject.toml is the single dep source; `pytest --import-mode=importlib`, `asyncio_mode = "auto"`, `markers = ["live"]` are already configured (Phase 2 D-20).
- `.planning/codebase/STRUCTURE.md` — module layout; `apps/api/` exists from Phase 2; Phase 3 adds `apps/api/main.py`, `apps/api/routes/`, `apps/api/db/`, `apps/api/paths.py`, `apps/api/lifespan.py`, `apps/api/settings.py`.
- `.planning/codebase/INTEGRATIONS.md` — `config/model_mapping.json` (16 slugs) and `config/pricing.json` (Phase 2 D-17). Phase 3 reads both via the existing `apps/api/backends/pricing.py` loader pattern.
- `.planning/codebase/CONCERNS.md` — `joblib.load` security note (artifacts produced by THIS repo; trust boundary = "the contributor who pushed last"); no need to re-establish in Phase 3.

### External Dependencies

- `fastapi>=0.115,<1.0` — primary web framework. **NEW in Phase 3** (Phase 1 D-18 / Phase 2 explicitly avoided it).
- `uvicorn[standard]>=0.30,<1.0` — ASGI server (the `[standard]` extra brings in `httptools`, `uvloop`, `watchfiles` for `--reload`). **NEW in Phase 3.**
- `sse-starlette>=2.1,<3.0` — `EventSourceResponse` with built-in heartbeat + disconnect (D-06). **NEW in Phase 3.**
- `aiosqlite>=0.20,<1.0` — async SQLite driver (STORE-01). **NEW in Phase 3.**
- `httpx>=0.27,<1.0` — already a Phase 2 dep (used by `pricing.py` for OpenRouter `/api/v1/models`). Phase 3 reuses for `httpx.AsyncClient + ASGITransport` integration tests (API-08).
- `pydantic>=2.6,<3.0` — already a Phase 2 dep. Phase 3 uses for request/response models + DB row models.
- `pytest-asyncio` already configured; Phase 3 adds no test-framework deps.

### Source Files That Must Stay Compatible

- `src/routing/*` — Phase 1 D-18 import-graph guard MUST stay green. Phase 3 imports `from src.routing.decide import decide` and `from src.routing.schema import RoutingDecision, Backend` (those modules use stdlib + sklearn only). `apps/api/` MAY depend on `src/routing/`; the reverse is forbidden. The smoke test in `src/routing/tests/test_decide_smoke.py` must keep passing after Phase 3's adapter imports land.
- `apps/api/__init__.py` — `dotenv.load_dotenv()` + `install_redaction_filter()` side effects MUST remain at module import time. Phase 3's `main.py` imports `apps.api.*` first, triggering both side effects before any FastAPI app is constructed.
- `apps/api/backends/protocol.py:AdapterOptions` — Phase 3 constructs `AdapterOptions(model=routing_decision.model_or_agent, max_cost_usd=settings.default_max_cost_usd, max_steps=None, cwd=None, routing_signals=routing_decision.signals)`. Phase 3 may grow `AdapterOptions` with new fields (defaults preserve back-compat per Phase 2 D-08).
- `apps/api/backends/chunks.py:ChatChunk` — Phase 3 does NOT change the union shape. If new event types are needed (e.g., `Heartbeat` as a typed chunk), defer to a follow-up plan — the comment-line heartbeat (D-07) is sufficient for v1.
- `pyproject.toml` — add Phase 3 deps (`fastapi`, `uvicorn[standard]`, `sse-starlette`, `aiosqlite`). `[tool.hatch.build.targets.wheel] packages = ["src", "apps"]` already covers `apps/api/`. Phase 3 does NOT need to extend.

### New Files Phase 3 Creates

- `apps/api/main.py` — FastAPI app constructor; mounts routers; sets up CORS middleware (OSS-05); declares the lifespan (D-15).
- `apps/api/lifespan.py` — `@asynccontextmanager async def lifespan(app: FastAPI)`: opens DB, runs migrations, sets pragmas, loads joblib artifacts (API-01), instantiates `KeyStore`, loads settings JSON, sets `app.state.adapters = {}`.
- `apps/api/paths.py` — single source for path constants: `USER_HOME`, `DB_PATH`, `BLOBS_DIR`, `WORKSPACES_DIR`, `SETTINGS_PATH`, `JSONL_LOG_PATH`. Honors `PROMPT_OPTIMIZER_HOME` env override.
- `apps/api/settings.py` — `load_settings_file()`, `write_settings_file()`, `computer_use_enabled(settings)` per D-12.
- `apps/api/routes/health.py` — `GET /api/v1/healthz` per D-18.
- `apps/api/routes/threads.py` — thread CRUD (`POST/GET/PATCH/DELETE /api/v1/threads(/{id})`).
- `apps/api/routes/turn.py` — `POST /api/v1/threads/{id}/turn` SSE handler; the heart of the phase.
- `apps/api/routes/rename.py` — `POST /api/v1/threads/{id}/rename` per D-17.
- `apps/api/routes/settings.py` — `GET/PATCH /api/v1/settings` per D-10/D-11.
- `apps/api/db/connect.py` — `open_db()` with pragmas (D-03).
- `apps/api/db/queries.py` — typed async query functions (D-01).
- `apps/api/db/migrate.py` — schema migration runner (D-02).
- `apps/api/db/migrations/schema_v0.sql` — initial schema (D-13).
- `apps/api/db/migrations/schema_v1.sql` — first follow-up migration (planner picks the first non-trivial schema evolution; e.g., adding an index or a new column referenced by Phase 5).
- `apps/api/db/models.py` — Pydantic models for `Thread`, `Message`, `RoutingDecision` (DB row shapes; distinct from request/response models in `routes/*`).
- `apps/api/tests/conftest.py` — `aiosqlite_inmemory_db` fixture, `asgi_client` fixture (httpx.AsyncClient + ASGITransport), fake-adapter overrides.
- `apps/api/tests/test_threads_crud.py`, `test_turn_streaming.py`, `test_settings.py`, `test_health.py`, `test_rename.py`, `test_migrations.py`, `test_secure_no_key_in_logs.py`, `test_cors.py`.
- `.env.example` — enumerate Phase 3 env vars: `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `COMPUTER_USE_OPT_IN`, `PROMPT_OPTIMIZER_HOME` (optional), `PROMPT_OPTIMIZER_CORS_ORIGINS` (optional). (OSS-03 is Phase 6, but the file may land here and grow in Phase 6.)
- `.planning/data/` — created on first turn; `routing_decisions.jsonl` is the only file. Gitignored by Phase 1 SECURE-03 (`.planning/data/` should be added if not already covered; planner verifies).

### Storage Layout (new user-home root)

```
~/.prompt-optimizer/
  chat.db                              # SQLite (this phase)
  chat.db-wal                          # WAL sidecar (D-03)
  chat.db-shm
  settings.json                        # non-key settings (D-11)
  blobs/<sha256>.<png|json>            # ≥256 KB screenshots / diffs (STORE-04)
  workspaces/<thread_id>/              # Claude Code per-thread workspace (Phase 2 specifics, this phase wraps)
  cache/openrouter_models.json         # Phase 2 D-17 (already exists)
```

Repo-relative `.planning/data/routing_decisions.jsonl` is the offline-analysis log (STORE-06).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`src.routing.decide()`** (`src/routing/decide.py`) — pure-function brain. Phase 3 calls via `await asyncio.to_thread(decide, ...)` exactly once per turn.
- **`apps/api/backends/protocol.py:BackendAdapter`** — single-method async-iterator Protocol. Phase 3 stores instances in `app.state.adapters: dict[Backend, BackendAdapter]`.
- **`apps/api/backends/chunks.py:ChatChunk` + `chat_chunk_adapter`** — discriminated Pydantic union. `chunk.model_dump_json()` is the SSE serializer; `chat_chunk_adapter.validate_json(line)` is the reader (used in tests).
- **`apps/api/backends/keystore.py:KeyStore`** — already supports the `provider -> key` lookup (`openrouter`, `anthropic`). Phase 3 instantiates once at lifespan and stashes in `app.state.keystore`.
- **`apps/api/backends/cost.py:DEFAULT_PER_TURN_COST_USD = 0.50`** — Phase 3 `settings.json` `default_max_cost_usd` defaults to this; per-turn override comes from the turn endpoint body.
- **`apps/api/__init__.py`** — `dotenv.load_dotenv()` + `install_redaction_filter()` side effects ALREADY run at import; Phase 3 modules import from `apps.api.*` first.
- **`src/demo/demo_router.py:load_joblib_artifacts()`** (Phase 1 reused convention) — Phase 3 lifespan imports / lifts this loader to load all three joblib heads ONCE at startup. The pattern is canonical.
- **`config/model_mapping.json`** (16 entries) + **`config/pricing.json`** (13 entries + `_default`) — both `json.load()` at lifespan. The OpenRouter `api_model` resolution from Phase 1 D-02 / D-04 already happens inside `decide()`; Phase 3 doesn't re-resolve.

### Established Patterns

- **`pathlib.Path(__file__).resolve().parents[N]`** is the Phase 2 path convention (matches `apps/api/__init__.py` line 49). Phase 3 reuses verbatim; NEVER add `sys.path.append`.
- **Frozen dataclass for ID-keyed data** — Phase 2's `Message(role, content)` + `AdapterOptions(...)` use `@dataclass(frozen=True)`. Phase 3's DB-row Pydantic models use `model_config = ConfigDict(frozen=True)` for the read paths (Thread, Message-as-returned-from-DB); write paths take ordinary models for ergonomics.
- **Per-package `__init__.py` + `__main__.py`** — Phase 2 adapter packages already follow this. Phase 3 keeps `apps/api/main.py` as the FastAPI app constructor and does NOT add an `apps/api/__main__.py` — users invoke `uvicorn apps.api.main:app` directly (matches ROADMAP SC #1).
- **Side-effect modules guarded by import-time idempotency** — `install_redaction_filter()` is idempotent (Phase 2 D-11). The lifespan migration runner is similarly idempotent (no-op if `schema_meta.version` matches the latest).
- **Closed-vocabulary `Literal[...]`** — Phase 2 D-06's `StreamError.code` and Phase 1 D-04's `Backend` literal. Phase 3 health adapter status is the same shape: `Literal["ready","missing_key","opt_out","error"]`.

### Integration Points

- **Phase 3 → Phase 1** — `from src.routing.decide import decide` + `from src.routing.schema import RoutingDecision, Backend`. One-directional.
- **Phase 3 → Phase 2** — `from apps.api.backends.openrouter import OpenRouterAdapter`, `from apps.api.backends.claude_code import ClaudeCodeAdapter`, `from apps.api.backends.computer_use import ComputerUseAdapter`, `from apps.api.backends.chunks import ChatChunk, chat_chunk_adapter, TextDelta, ToolCall, ToolResult, FileDiff, Screenshot, StreamError, Done`, `from apps.api.backends.keystore import KeyStore`, `from apps.api.backends.protocol import BackendAdapter, AdapterOptions, Message as AdapterMessage`.
- **Phase 3 → Phase 4** (downstream) — SSE wire format (named events, JSON data lines) is the contract Phase 4's `apps/web/app/api/chat/route.ts` proxy honors. Any wire-format change post-Phase-3 is a Phase 4 breaking change.
- **Phase 3 → Phase 5** (downstream) — `GET /api/v1/healthz` adapter status feeds UI-11 status dots; `PATCH /api/v1/settings` is UI-12's settings panel write endpoint; `POST /api/v1/threads/{id}/rename` is UI-14's auto-rename hook; the optional `override_backend` field on the turn endpoint body is UI-05's per-turn override mechanism.
- **Phase 3 → Phase 6** (downstream) — `make setup` (Phase 6 OSS-02) will reference Phase 3's `~/.prompt-optimizer/` directory creation and `.env.example` enumeration.

### Anti-Patterns to AVOID

- **Do NOT add `sys.path.append`** anywhere — Phase 2 D-08 anti-pattern guard still applies. Use `from apps.api.*` and `from src.routing.*` directly via the hatchling-packaged wheel.
- **Do NOT import FastAPI / httpx / sse-starlette from `src/routing/`.** Phase 1 D-18 import-graph guard test asserts this. Direction: `apps.api → src.routing`, never the reverse.
- **Do NOT call `decide()` synchronously from the async handler.** API-07 violation; would block the event loop on the sklearn `predict_proba` call. Always wrap with `asyncio.to_thread` (D-16).
- **Do NOT use `TestClient` for streaming tests.** API-08 explicit. `httpx.AsyncClient + ASGITransport` is the only path that exercises the real async cancellation + heartbeat code.
- **Do NOT write per-chunk to SQLite.** STORE-05 explicit and D-04 enforces. Buffer in memory, write once on Done. Per-chunk writes would saturate SQLite's single-writer lock under streaming load.
- **Do NOT log raw keys.** Phase 2 redaction filter is load-bearing; PATCH /settings handler MUST use `logging.getLogger(__name__)` so the filter applies. Direct `print(body.keys.openrouter)` is forbidden by the regression test.
- **Do NOT eagerly construct adapters at lifespan.** D-15 explicit. Eager construction breaks fresh-clone UX because the default `COMPUTER_USE_OPT_IN` is unset.
- **Do NOT couple computer-use opt-in to env-only.** D-12 explicit — both env AND settings.json. Otherwise Phase 5 UI-12 toggle is dead weight.
- **Do NOT silently fall back to wildcards in CORS.** OSS-05 explicit. If `PROMPT_OPTIMIZER_CORS_ORIGINS` env var is unset, default to `["http://localhost:3000"]`. NEVER `["*"]`.

</code_context>

<specifics>
## Specific Ideas

- **Storage root:** `~/.prompt-optimizer/` (override via `PROMPT_OPTIMIZER_HOME` env var). DB: `~/.prompt-optimizer/chat.db`. Blobs: `~/.prompt-optimizer/blobs/<sha256>.<ext>`. Settings: `~/.prompt-optimizer/settings.json`. Workspaces (Phase 2 carry): `~/.prompt-optimizer/workspaces/<thread_id>/`.

- **JSONL log path:** `.planning/data/routing_decisions.jsonl` (repo-relative; gitignored). Created on first append. One JSON object per line: `{"turn_id": "...", "thread_id": "...", "timestamp": "2026-05-15T18:00:00Z", "backend": "openrouter", "model_or_agent": "openai/gpt-5", "rationale": "...", "confidence": 0.92, "signals": {...}}`. Appended at decide()-time, BEFORE adapter dispatch (D-05).

- **URL namespace:** `/api/v1/*` for every endpoint (D-09). `/api/v1/healthz`, `/api/v1/threads`, `/api/v1/threads/{id}`, `/api/v1/threads/{id}/turn`, `/api/v1/threads/{id}/rename`, `/api/v1/settings`.

- **SSE wire format:** `event: <chunk.type>\ndata: <chunk.model_dump_json()>\n\n` blocks separated by blank lines. Heartbeat: `: ping\n\n` every 15 s via sse-starlette `ping=15` (D-06/D-07).

- **Settings endpoint contract:** `PATCH /api/v1/settings` with partial body; `GET /api/v1/settings` returns `{keys: {provider: {present: bool, masked: str}}, backends_enabled: {...}, computer_use_opt_in: bool, default_max_cost_usd: float}` with keys ALWAYS masked. `keys` is write-only on the wire (D-10).

- **Computer-use enable:** `os.environ["COMPUTER_USE_OPT_IN"] == "1"` AND `settings["computer_use_opt_in"] is True`. Both required. Adapter `__init__` raises `RuntimeError("computer-use is OFF — ...")` if either is unset (D-12).

- **Per-turn cost-cap default:** `settings.default_max_cost_usd` (default `0.50` per Phase 2 `DEFAULT_PER_TURN_COST_USD`). Per-turn override via turn endpoint body `max_cost_usd` field.

- **`asyncio.to_thread(decide, ...)` is the ONLY way to call `decide()` from a route handler.** Direct synchronous calls would block the event loop and break SSE for other concurrent turns.

- **DB pragmas on first connect:** `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=5000; PRAGMA foreign_keys=ON;` (D-03). The `foreign_keys=ON` is REQUIRED for cascade deletes (D-13) and is OFF by default in SQLite per connection.

- **Adapter cache invalidation:** `app.state.adapters.clear()` runs inside `PATCH /api/v1/settings` AFTER the settings file is rewritten and BEFORE the response is returned. The next turn rebuilds with fresh KeyStore values (D-15).

- **Healthz adapter status check is read-only** — KeyStore presence + env var + settings flag. Does NOT instantiate the adapter. Cost: ~0.5 ms (D-18).

- **Migration test seed file:** `apps/api/tests/fixtures/schema_v0_seed.sql` inserts 1 thread + 2 messages into a fresh v0 DB; the test then calls `migrate.up_to_latest()` and asserts (a) `schema_meta.version` equals the latest, (b) thread + message rows still present, (c) any new v1 columns have their default values populated.

- **Rename endpoint defensive constants:** Hardcoded model `"openai/gpt-4o-mini"` (cheapest GPT-class OpenRouter slug at this writing; planner verifies current cheapest at execute time). `max_cost_usd=0.01`. `max_steps=1`. Prompt: `"Summarize this user request in 5 words or fewer; respond with the title only, no quotes."` Result trimmed to ≤60 chars before persisting.

- **`override_backend` field on turn body** — optional. When set, Phase 3 skips `decide()` and synthesizes a `RoutingDecision(backend=<override>, model_or_agent="<sensible default>", rationale="user override", confidence=1.0, signals={"override": true})`. Phase 5 UI-05's slash-command / dropdown override flows through this.

- **Update REQUIREMENTS.md API-07 wording** to: "Synchronous sklearn `predict` / `predict_proba` calls are wrapped in `asyncio.to_thread` (or equivalent thread-pool offload such as `starlette.concurrency.run_in_threadpool`) when invoked from async handlers." Matches D-16.

</specifics>

<deferred>
## Deferred Ideas

- **`/api/v1/models` endpoint** — Phase 5 UI-11 adds it; Phase 3 ships only `/healthz` with adapter status. Splitting "is the server alive" from "list available models" is a clean boundary.
- **Per-thread workspace cleanup on thread delete (Phase 2 carry-forward)** — `DELETE /api/v1/threads/{id}` should also `shutil.rmtree(~/.prompt-optimizer/workspaces/<thread_id>/)`. Planner: include in `delete_thread` query function alongside the blob unlink.
- **AI SDK v5 "UI Message Stream Protocol" framing** — if Phase 4 wants the numeric-prefix lines (0:"text", 1:tool_call, …) for `@ai-sdk/react useChat` compatibility, the Next.js proxy at `apps/web/app/api/chat/route.ts` handles the translation. Phase 3 stays JSON-only with named events (D-07).
- **OpenAPI schema export to JSON file** — FastAPI auto-generates at `/openapi.json`. Phase 5 / Phase 6 may want a committed snapshot for client codegen. Deferred.
- **Bulk export thread to markdown** — v2 UI-V2-01. Out of scope.
- **Server-side analytics / telemetry** — PROJECT.md Out of Scope.
- **Multi-user / auth layer** — PROJECT.md Out of Scope.
- **Rate-limiting middleware** — not needed for single-user local server. Defer until hosted version exists (v2+).
- **Prometheus / structured-logging exporter** — defer to Phase 6 hardening or v2.
- **`make gc-blobs` orphan-blob garbage collector** — D-14 covers the cascade path. A separate sweeper for blobs orphaned by mid-delete crashes is a Phase 6 hardening item.
- **Migration rollback (`schema_v{N}_down.sql`)** — Phase 3 ships forward-only migrations. Down migrations are deferred until v2 (where production rollbacks become a real concern).
- **`POST /api/v1/threads/{id}/turn?override_backend=...` query-param style override** — Phase 3 uses body field instead. Query-param overrides for SSE endpoints can be cached by intermediate proxies in unexpected ways.
- **WebSocket alternative to SSE** — SSE is sufficient for one-way streaming; WebSocket complexity (full-duplex, ping/pong, frame handling) isn't justified. Defer indefinitely.
- **Refactor Phase 2 `apps/api/backends/cost.py` `DEFAULT_PER_TURN_COST_USD`** — Phase 3 makes the default configurable via `settings.default_max_cost_usd`. The Phase 2 module constant stays as the ultimate fallback when `settings.json` is absent on first boot.
- **Concurrent-turn rate-limit per thread** — single-user local server doesn't need it. Optimistic concurrency via SQLite's WAL is sufficient for v1.
- **Migrations run as a separate CLI** (`python -m apps.api.db.migrate`) — Phase 3 calls the runner inline at lifespan; a separate CLI may land in Phase 6 for ops scenarios. Trivial to add.
- **Tier-router family migration** — Phase 1 deferred item; still out of scope.

</deferred>

---

*Phase: 03-fastapi-service-persistent-storage*
*Context gathered: 2026-05-15*
