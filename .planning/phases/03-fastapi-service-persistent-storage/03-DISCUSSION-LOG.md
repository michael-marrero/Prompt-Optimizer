# Phase 3: FastAPI Service & Persistent Storage — Discussion Log

**Date:** 2026-05-15
**Mode:** discuss (default — single-question turns)
**Areas surfaced:** 4 phase-specific gray areas
**Areas user selected:** all 4
**Total questions asked:** 14 (4 + 4 + 4 + 4 + 3 final touch-ups, minus 1 confirmation re-ask)

This log is for human reference (audits, retrospectives). Downstream agents (researcher, planner, executor) consume `03-CONTEXT.md` — NOT this file.

---

## Pre-Discussion Context Loaded

Read before opening discussion:
- `.planning/PROJECT.md` (Active requirements show FastAPI, Next.js, persistence are Phase 3 territory)
- `.planning/ROADMAP.md` §"Phase 3: FastAPI Service & Persistent Storage" — 5 success criteria, 15 requirements
- `.planning/REQUIREMENTS.md` — API-01..08, STORE-01..06, OSS-05
- `.planning/STATE.md` — Phase 2 just closed with gap-closure CR-01/02/04/05; 15/15 Phase-2 requirements satisfied
- `.planning/phases/01-router-brain-foundation/01-CONTEXT.md` — D-01 cascade, D-04 backend sentinels + model strings, D-18 import-graph guard
- `.planning/phases/02-backend-adapters-chatchunk-contract/02-CONTEXT.md` — full set of 20 decisions including D-01 (Pydantic v2 union), D-08 (per-backend module layout), D-10 (KeyStore), D-11 (dotenv + redaction filter at import), D-14 (Screenshot dual schema), D-15 (per-iteration step caps), D-17 (PricingTable), D-19 (contract test), D-20 (CI green = unit tests)
- `.planning/codebase/ARCHITECTURE.md`, `STACK.md`, `STRUCTURE.md`, `CONCERNS.md` — for anti-pattern context

Scouted the live codebase:
- `pyproject.toml` — confirmed deps already present (pydantic, openai, anthropic, claude-agent-sdk, playwright, python-dotenv, httpx, tiktoken, pre-commit; pytest with asyncio_mode=auto and live marker)
- `apps/api/__init__.py` — dotenv + redaction filter at import (Phase 2 D-11)
- `apps/api/backends/protocol.py` — BackendAdapter + Message + AdapterOptions frozen dataclass
- `apps/api/backends/chunks.py` — 7-variant Pydantic union + chat_chunk_adapter TypeAdapter
- `apps/api/backends/keystore.py` — in-memory + optional keyring (SECURE-04)
- Each adapter dir: `openrouter/`, `claude_code/`, `computer_use/` with `__init__.py`, `__main__.py`, `adapter.py`, `cost.py`, `errors.py`, `tests/`

Cross-referenced todos: `gsd-sdk query todo.match-phase 3` returned 0 matches. None to fold.

---

## Gray Areas Already Decided (NOT Re-Asked)

These were locked by ROADMAP or by Phase 1/2 CONTEXT and not surfaced as questions:

- Routing source must be `src.routing.decide()` — Phase 1 D-18 import-graph guard intact
- Adapter contract is the existing `BackendAdapter` Protocol returning `AsyncIterator[ChatChunk]` — Phase 2 D-08
- `ChatChunk` is the Pydantic v2 discriminated union from Phase 2 D-01 (7 variants, `model_dump_json()` for SSE)
- Joblib artifacts load once at lifespan startup — ROADMAP SC #1 / API-01
- 15-second heartbeat — API-05 / ROADMAP SC #2
- `request.is_disconnected()` polling for cancellation within 2s — API-06 / ROADMAP SC #2
- WAL + `busy_timeout=5000` — STORE-01 / ROADMAP SC #3
- Schema column set fixed by STORE-02
- Large blobs ≥256 KB → `~/.prompt-optimizer/blobs/<sha256>` — STORE-04 / ROADMAP SC #4
- JSONL log at `.planning/data/routing_decisions.jsonl` — STORE-06 / ROADMAP SC #4
- BYOK keys NEVER persisted to DB or logs — SECURE-04 / ROADMAP SC #5
- `KeyStore` + dotenv loader at `apps/api/__init__.py` import — Phase 2 D-10/D-11
- CORS explicit Next.js dev origin (no `*`) — OSS-05 / ROADMAP SC #5
- Per-thread workspace `~/.prompt-optimizer/workspaces/<thread_id>/` — Phase 2 specifics line 264
- `httpx.AsyncClient + ASGITransport` for integration tests — API-08
- `apps/api/backends/cost.py:DEFAULT_PER_TURN_COST_USD = 0.50` — Phase 2 specifics line 260
- Backend literal = `"openrouter" | "claude_code" | "computer_use"` — Phase 1 D-04 / Phase 2 protocol
- Asyncio runtime (vs trio/anyio) — Phase 2 D-Claude's-Discretion (CONTEXT.md)
- pytest with `--import-mode=importlib`, `asyncio_mode = "auto"`, `markers = ["live"]` — Phase 2 D-20

---

## Area 1 — Persistence layer + migrations

**Question 1.1:** Which SQLite access layer should Phase 3 use?
**Options presented:**
- (A) Raw aiosqlite + Pydantic models for input/output validation (Recommended)
- (B) SQLModel + Alembic — typed-model continuity DB → API
- (C) databases package + Alembic — unmaintained dep risk

**User selected:** (A) Raw aiosqlite + Pydantic models

**Why this matters:** Determines the entire access pattern, dep weight, and migration tool choice downstream. Matches repo's existing "filesystem is the database" minimalism (codebase ARCHITECTURE.md).

---

**Question 1.2:** Which migration approach fits raw aiosqlite best?
**Options presented:**
- (A) yoyo-migrations — lightweight Python migration tool
- (B) Hand-rolled `schema_v{N}.sql` runner (Recommended)
- (C) Alembic offline mode — drags in SQLAlchemy

**User selected:** (B) Hand-rolled `schema_v{N}.sql` runner

**Notes:** ~40 lines of Python, zero deps, full control. STORE-03 migration test is straightforward against `schema_v{N}.sql` files. Numbered SQL files under `apps/api/db/migrations/`.

---

**Question 1.3:** How should writes happen during streaming (STORE-05)?
**Options presented:**
- (A) Single commit on Done (Recommended)
- (B) User message upfront, assistant on Done — two transactions, crash-safer
- (C) Write-ahead JSONL + DB on Done — most complex

**User selected:** (A) Single commit on Done

**Notes:** Matches STORE-05 verbatim. Buffer ChatChunks in memory, write user + assistant + routing_decisions in ONE transaction at Done. Partial assistant content preserved on StreamError+Done paths.

---

**Question 1.4:** When does `routing_decisions.jsonl` get appended (STORE-06)?
**Options presented:**
- (A) After decide() returns, before adapter dispatch (Recommended)
- (B) After Done, alongside DB write
- (C) Both ("attempt" + "outcome" lines)

**User selected:** (A) After decide() returns, before adapter dispatch

**Notes:** Captures EVERY decision including cancelled / errored turns. Mirrors Phase 1 canary CSV consumer pattern for offline analysis.

---

## Area 2 — SSE library + wire framing

**Question 2.1:** Which SSE library should Phase 3 use?
**Options presented:**
- (A) sse-starlette EventSourceResponse (Recommended)
- (B) Raw StreamingResponse + manual SSE framing
- (C) StreamingResponse + sse-starlette helpers only — worst of both

**User selected:** (A) sse-starlette EventSourceResponse

**Notes:** Built-in `ping=15` for heartbeat (API-05), built-in `request.is_disconnected()` polling (API-06). Active maintenance, de-facto FastAPI choice. ~200 LOC dep.

---

**Question 2.2:** Which SSE wire framing?
**Options presented:**
- (A) Named events keyed by chunk.type (Recommended)
- (B) Data-only single channel
- (C) AI SDK v5 "UI Message Stream Protocol" framing — couples Phase 3 to a frontend lib

**User selected:** (A) Named events keyed by chunk.type

**Notes:** `event: text_delta\ndata: {json}\n\n` per chunk. Enables Phase 4 `addEventListener('text_delta', ...)` dispatch. Heartbeat = `: ping` SSE comment. If Phase 4 wants AI SDK v5 protocol, the Next.js proxy translates.

---

**Question 2.3:** HTTP error vs mid-stream error shape?
**Options presented:**
- (A) Pre-stream: FastAPI HTTPException; mid-stream: existing StreamError ChatChunk (Recommended)
- (B) RFC 7807 problem+json for HTTP errors
- (C) Custom envelope everywhere

**User selected:** (A) HTTPException pre-stream + StreamError chunk in-stream

**Notes:** Two clean boundaries. HTTPException is the FastAPI idiom. StreamError vocabulary is already closed by Phase 2 D-06.

---

**Question 2.4:** Should the API namespace under `/api/v1` from day one?
**Options presented:**
- (A) /api/v1 from day one (Recommended)
- (B) Bare paths, defer versioning
- (C) Mixed — inconsistent

**User selected:** (A) /api/v1 from day one

**Notes:** Aligns with Phase 5 UI-11's pre-existing `/api/v1/models` reference. Future v2 gets a clean `/api/v2` path.

---

## Area 3 — Settings/BYOK endpoint + opt-in coupling

**Question 3.1:** Settings endpoint shape?
**Options presented:**
- (A) Bulk PATCH /settings with partial body / JSON Merge Patch (Recommended)
- (B) Per-resource (PUT /settings/keys/{provider}, PATCH /settings/backends)
- (C) Full-replacement PATCH

**User selected:** (A) Bulk PATCH with partial body

**Notes:** Single endpoint, partial updates. GET returns full doc with keys ALWAYS masked. Plaintext keys are write-only on the wire. SECURE-04 regression test will assert no key leaks.

---

**Question 3.2:** Where do non-key settings persist?
**Options presented:**
- (A) JSON file at ~/.prompt-optimizer/settings.json (Recommended)
- (B) settings table in SQLite
- (C) In-process only — no persistence

**User selected:** (A) JSON file at ~/.prompt-optimizer/settings.json

**Notes:** Keys stay in KeyStore (in-memory + optional keyring per Phase 2 D-10). Non-key settings (backends_enabled, computer_use_opt_in, default_max_cost_usd) in the JSON file. Chat reset and settings reset are independent.

---

**Question 3.3:** Computer-use enable logic — env OR settings, env AND settings, or env only?
**Options presented:**
- (A) Permissive "Both required: env OR settings.json must opt-in" [LABEL/DESCRIPTION CONFLICT NOTED]
- (B) Strict "Both required: env AND settings.json must opt-in"
- (C) Env only (Phase 2 status quo) — UI toggle informational

**User selected:** (A) [labeled "Both required: env OR settings.json"]

**RE-ASKED to confirm intent because the option's label said "Both required" but the description said "if EITHER env OR settings.json".**

---

**Question 3.3-confirm:** STRICT (AND) vs PERMISSIVE (OR)?
**Options presented:**
- (A) STRICT (AND) — matches ROADMAP Phase 6 SC #5 verbatim (Recommended)
- (B) PERMISSIVE (OR) — would require updating ROADMAP Phase 6 SC #5

**User selected:** (A) STRICT (AND)

**Notes:** Both `COMPUTER_USE_OPT_IN=1` env var AND `settings.json computer_use_opt_in=true` must be set. Defensive default, two independent gates. Adapter `__init__` raises if either gate is unset.

---

**Question 3.4:** Phase 5 UI-14 thread auto-rename hook?
**Options presented:**
- (A) Dedicated POST /threads/{id}/rename endpoint (Recommended)
- (B) bypass_routing flag on /turn endpoint
- (C) Defer entirely to Phase 5

**User selected:** (A) Dedicated endpoint

**Notes:** Internal implementation uses fresh `OpenRouterAdapter` with hardcoded cheap model (`openai/gpt-4o-mini`), `max_cost_usd=0.01`, `max_steps=1`. Bypasses decide() entirely. Returns `{"title": "..."}` JSON (no SSE).

---

## Area 4 — DB file location + lifespan posture

**Question 4.1:** Default SQLite DB path?
**Options presented:**
- (A) ~/.prompt-optimizer/chat.db (Recommended)
- (B) ./chat.db (cwd-anchored)
- (C) Env-configurable, default ./chat.db

**User selected:** (A) ~/.prompt-optimizer/chat.db

**Notes:** User-home, invariant across cwd. Matches existing ~/.prompt-optimizer/{workspaces,blobs,cache}. One user-state root for the whole product. Override via PROMPT_OPTIMIZER_HOME env var.

---

**Question 4.2:** Adapter construction at lifespan vs per-turn?
**Options presented:**
- (A) Lazy per-turn with cached instances (Recommended)
- (B) Eager at lifespan, fail-fast
- (C) Eager with graceful degradation status

**User selected:** (A) Lazy per-turn with cached instances

**Notes:** Server boots even when ANTHROPIC_API_KEY or COMPUTER_USE_OPT_IN are unset. Only the specific backend that's selected raises. Crucial fresh-clone UX. PATCH /settings invalidates cache via `app.state.adapters.clear()`.

---

**Question 4.3:** Threading model for sklearn predict_proba (API-07)?
**Options presented:**
- (A) asyncio.to_thread (Recommended)
- (B) starlette.concurrency.run_in_threadpool (matches REQUIREMENTS verbatim)
- (C) Dedicated ThreadPoolExecutor with bounded size

**User selected:** (A) asyncio.to_thread

**Notes:** Stdlib (3.9+), zero extra deps, semantically identical to run_in_threadpool. REQUIREMENTS.md API-07 wording updated in this phase to allow "asyncio.to_thread or equivalent thread-pool offload."

---

## Area 5 — Final touch-ups (user selected ALL three follow-ups)

**Question 5.1:** Orphan blob cleanup policy?
**Options presented:**
- (A) Cascade unlink on thread delete (Recommended)
- (B) Never delete (let disk grow)
- (C) Reference-counted GC

**User selected:** (A) Cascade unlink on thread delete

**Notes:** DELETE /threads/{id} walks message rows for blob refs, unlinks each file BEFORE deleting DB rows (interrupted delete leaves orphan blobs, recoverable by Phase 6 sweeper; never leaves stale DB refs to missing files).

---

**Question 5.2:** Healthcheck shape?
**Options presented:**
- (A) Rich health with backend status (Recommended)
- (B) Minimal {status:'ok'} — separate /api/v1/models
- (C) /healthz + /readyz split — K8s-style

**User selected:** (A) Rich health with backend status

**Notes:** Single endpoint Phase 5 UI-11 hits. Adapter statuses: `ready` | `missing_key` | `opt_out` | `error`. Read-only checks (KeyStore + env + settings); no adapter construction.

---

**Question 5.3:** Default logging level?
**Options presented:**
- (A) INFO per-turn boundary lines, DEBUG for chunks (Recommended)
- (B) WARNING+ only
- (C) DEBUG everywhere with structured JSON

**User selected:** (A) INFO boundaries + DEBUG chunks

**Notes:** Three INFO lines per turn (turn_start / routing_decision / turn_done). Phase 2 RedactionFilter still load-bearing. New regression test: PATCH /settings with `sk-or-v1-...` value → grep captured logs for `sk-or-v1` returns zero matches.

---

## Deferred Ideas Captured

- `/api/v1/models` endpoint — Phase 5 UI-11 adds it
- Per-thread workspace cleanup on thread delete — included in `delete_thread` query function
- AI SDK v5 "UI Message Stream Protocol" framing — Next.js proxy handles translation
- OpenAPI schema snapshot to JSON — defer to Phase 5/6
- Migration rollback — forward-only in v1
- `make gc-blobs` orphan sweeper — Phase 6 hardening
- Query-param `override_backend` — body field used instead (safer against intermediate proxies)
- WebSocket alternative — SSE sufficient
- Migrations as separate CLI — inline at lifespan; CLI defer to Phase 6 ops
- Concurrent-turn rate limit per thread — single-user; not needed in v1
- Rate-limiting middleware — single-user; not needed in v1
- Multi-user / auth — PROJECT.md Out of Scope
- Server-side analytics — PROJECT.md Out of Scope

---

## Claude's Discretion (planner / researcher own)

These were left to downstream agents — no user preference expressed:

- sse-starlette exact version pin (within >=2.1,<3.0)
- CORS origin defaults (default `["http://localhost:3000"]`; env-configurable via `PROMPT_OPTIMIZER_CORS_ORIGINS`)
- ID generation (`secrets.token_urlsafe(12)` default; planner may swap for ULID / UUIDv7)
- Settings file atomic-write pattern (`tmp.rename(target)`)
- Lifespan loader internals (order: open DB → migrate → pragmas → artifacts → settings → KeyStore)
- Turn endpoint request body shape (`{message, override_backend?, max_cost_usd?}`)
- Healthz adapter status detection (read-only — KeyStore + env + settings)
- OpenAPI tags / response models (FastAPI auto-generation)
- Tiktoken pre-flight estimator (reused inside rename endpoint to enforce input length cap)
- Migration test fixture path (`apps/api/tests/fixtures/schema_v0_seed.sql`)

---

## REQUIREMENTS.md Update This Phase

API-07 wording is updated in this phase from:
> "Synchronous sklearn `predict` / `predict_proba` calls are wrapped in `run_in_threadpool` when invoked from async handlers"

to:
> "Synchronous sklearn `predict` / `predict_proba` calls are wrapped in `asyncio.to_thread` (or equivalent thread-pool offload such as `starlette.concurrency.run_in_threadpool`) when invoked from async handlers"

Same intent (don't block the event loop); broader allowed implementations.

---

*Discussion log captured: 2026-05-15*
