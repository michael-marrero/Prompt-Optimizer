# Phase 3: FastAPI Service & Persistent Storage — Research

**Researched:** 2026-05-15
**Domain:** Async HTTP service (FastAPI + SSE) + persistent storage (aiosqlite + blob filesystem)
**Confidence:** HIGH

## Summary

Phase 3 fuses the Phase 1 routing brain with the Phase 2 adapter triplet behind a FastAPI service. The CONTEXT.md locks 20 implementation decisions (D-01..D-20) covering persistence (aiosqlite + hand-rolled migrations + WAL pragmas), SSE framing (`sse-starlette` named events keyed by `chunk.type`), BYOK settings (`PATCH /api/v1/settings` with JSON Merge Patch semantics), lifespan (lazy per-turn adapter cache), auxiliary endpoints (rich `/healthz`, dedicated `/rename`), logging (Phase 2 redaction filter carries forward), and tests (`httpx.AsyncClient + ASGITransport`). The researcher's job here is NOT to relitigate those — it is to surface the **library facts**, **exact signatures**, **edge cases**, and **wiring patterns** the planner needs to write task-level plans without re-discovering them mid-execute.

Every library on the deps list has been verified at PyPI within the CONTEXT-locked ranges. The single non-obvious finding is a constraint conflict: `sse-starlette 3.x` is already in the venv as a transitive of `mcp`, while CONTEXT.md D-06 declares `>=2.1,<3.0`. The 2.x→3.x API for the surface this phase uses (`EventSourceResponse(content, ping=15, send_timeout=...)`, `request.is_disconnected()`, named events via `ServerSentEvent`) is unchanged — 3.x added internal test-isolation improvements and a `shutdown_event` knob. **Recommendation: loosen the dep range to `>=2.1,<4.0` and pin to 3.x in `uv.lock` to avoid forcing a downgrade of `mcp`'s transitive.** Planner owns the call; see Open Question 1.

The second non-obvious finding is a real, unresolved upstream issue: `httpx.AsyncClient + ASGITransport.stream()` against an **infinite** SSE generator hangs forever ([encode/httpx#2186](https://github.com/encode/httpx/issues/2186)). Our streams are **finite** by construction (D-04 terminal-pair invariant from Phase 2), so the standard pattern works — but the test code MUST consume `aiter_lines()` in a finite loop (break on the `event: done` line) or use `httpx-sse`'s `aconnect_sse` helper. This shapes the conftest fixtures (see Wave 0 gaps in §Validation Architecture).

**Primary recommendation:** Build Phase 3 as a 6-wave plan: (Wave 0) `pyproject.toml` deps + path constants + `apps/api/paths.py` + base test scaffolding; (Wave 1) `db/connect.py + migrate.py + queries.py + schema_v0.sql` + isolated unit tests; (Wave 2) `lifespan.py + main.py + routes/health.py + CORS` (server boots, healthz + DB only); (Wave 3) `routes/threads.py + routes/settings.py + KeyStore wiring`; (Wave 4) `routes/turn.py` — the heart of the phase, SSE + adapter dispatch + buffer-and-write-on-Done + cancellation + heartbeat assertion; (Wave 5) `routes/rename.py + blob storage transcoder + STORE-04 + JSONL log` + integration tests for SECURE-04 + STORE-03 + STORE-04.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| HTTP routing + middleware | FastAPI app (`apps/api/main.py`) | — | Owns OpenAPI generation, CORS, request validation. |
| Lifespan startup (artifacts, DB, KeyStore, settings) | FastAPI lifespan (`apps/api/lifespan.py`) | — | Single source of one-time initialisation; D-15. |
| SSE wire serialization | sse-starlette `EventSourceResponse` | — | Heartbeat + disconnect detection built in (D-06). |
| Per-chunk JSON encoding | Pydantic v2 `chunk.model_dump_json()` | — | Discriminated union from Phase 2 D-01. |
| Routing brain invocation | `src.routing.decide` via `asyncio.to_thread` | — | API-07 / D-16; sklearn predict_proba is sync. |
| Backend adapters | `apps.api.backends.*` (Phase 2) | — | Phase 3 imports unchanged; D-15 lazy cache. |
| BYOK keys | `KeyStore` (Phase 2) | OS keyring (opt-in) | In-memory primary; never disk/log. |
| Non-key settings | `~/.prompt-optimizer/settings.json` | — | Atomic write pattern; D-11. |
| Persistent state | aiosqlite (SQLite WAL) | — | Threads / messages / routing_decisions; STORE-01..06. |
| Schema evolution | Hand-rolled `schema_v{N}.sql` runner | `schema_meta(version)` table | D-02; ~40 LOC, zero deps. |
| Large blob storage | Filesystem `~/.prompt-optimizer/blobs/<sha256>` | DB foreign-key by hash | STORE-04 + D-14. |
| Offline analysis log | `.planning/data/routing_decisions.jsonl` | DB row | STORE-06 + D-05; appended at decide-time. |
| Buffer-and-write-once | In-memory chunk list, ONE BEGIN/COMMIT on Done | — | STORE-05 + D-04; no per-chunk writes. |
| Integration testing | `httpx.AsyncClient + ASGITransport` | `aiosqlite.connect(":memory:")` | API-08 + D-20; never `TestClient`. |

## Standard Stack

### Core (new in Phase 3)

| Library | Version pin (CONTEXT range) | Verified latest | Purpose | Why standard |
|---------|------------------------------|------------------|---------|--------------|
| `fastapi` | `>=0.115,<1.0` | **0.136.1** (Apr 23, 2026) | ASGI web framework; declares routes, middleware, lifespan | `[VERIFIED: pypi.org/project/fastapi/]` Industry default for Python ASGI; native Pydantic v2 + OpenAPI generation. |
| `uvicorn[standard]` | `>=0.30,<1.0` | **0.47.0** (May 14, 2026) | ASGI server with httptools/uvloop/watchfiles | `[VERIFIED: pypi.org/project/uvicorn/]` `[standard]` extra brings the C-speed deps. |
| `sse-starlette` | `>=2.1,<3.0` (CONTEXT D-06) | **2.4.1** (Jul 6, 2025) is highest 2.x; **3.4.4** is current | `EventSourceResponse` with `ping=15` heartbeat + disconnect detection | `[VERIFIED: pypi.org/project/sse-starlette/]` De-facto FastAPI SSE choice. See Open Question 1 — venv has 3.x via `mcp` transitive. |
| `aiosqlite` | `>=0.20,<1.0` | **0.22.1** (Dec 23, 2025) | Async SQLite driver, asyncio-friendly | `[VERIFIED: pypi.org/project/aiosqlite/]` Wraps `sqlite3` in a single worker thread; uses async context manager. |
| `httpx` | `>=0.27,<1.0` (already locked) | **0.28.1** (in venv) | Test client via `ASGITransport`; also reused by Phase 2 pricing refresh | `[VERIFIED: uv pip list]` Already a Phase 2 dep. |
| `pydantic` | `>=2.6,<3.0` (already locked) | venv 2.x present | Request/response/DB models; partial-update via `exclude_unset` | `[VERIFIED: pyproject.toml]` Already a Phase 2 dep. |

### Already in `pyproject.toml`, reused in Phase 3
- `python-dotenv` — loads `.env` at `apps/api/__init__.py` import (Phase 2 D-11).
- `tiktoken` — Phase 2 dep; Phase 3 reuses in `routes/rename.py` for input-length pre-flight (D-17).
- `pytest`, `pytest-asyncio`, `pytest-timeout` — already configured (`asyncio_mode=auto`, `markers=["live"]`).

### Optional but recommended for tests
| Library | Version | Why | Status in venv |
|---------|---------|-----|----------------|
| `httpx-sse` | `>=0.4,<1.0` | `aconnect_sse(client, "POST", url) as event_source: async for sse in event_source.aiter_sse()` — clean SSE event parsing in tests. Optional because we can also parse `aiter_lines()` manually. | **0.4.3** already installed (verified `uv pip show`). Recommended for test ergonomics. |

### Alternatives considered (NOT to use)
| Instead of | Could use | Tradeoff | Decision |
|------------|-----------|----------|----------|
| `aiosqlite` (D-01) | `SQLModel + Alembic` | Typed model continuity DB→API; but drags SQLAlchemy + Alembic deps | CONTEXT D-01 locks aiosqlite. Do not relitigate. |
| Hand-rolled migrations (D-02) | `yoyo-migrations` or `Alembic offline mode` | Both are mature; yoyo is lighter than Alembic | CONTEXT D-02 locks hand-rolled. ~40 LOC; zero dep. |
| `sse-starlette` (D-06) | Raw `StreamingResponse` with manual SSE framing | Would have to hand-write heartbeat + disconnect | CONTEXT D-06 locks sse-starlette. |
| `asyncio.to_thread` (D-16) | `starlette.concurrency.run_in_threadpool` | The two are subtly different — `run_in_threadpool` delegates to `anyio.to_thread.run_sync` (richer contextvars + cancellation), `asyncio.to_thread` uses `loop.run_in_executor`. CONTEXT D-16 picks asyncio.to_thread for stdlib hygiene. | CONTEXT D-16 locks asyncio.to_thread. Decision is justified; not equivalent but functionally interchangeable here (no contextvar dependency in `decide()`). |
| `TestClient` (D-20) | `httpx.AsyncClient + ASGITransport` | TestClient is sync and uses anyio threads — does not exercise real async cancellation | CONTEXT D-20 locks AsyncClient + ASGITransport. |
| `keyring` always-on | optional extra | Drags platform-specific deps onto fresh-clone users who never want disk persistence | Phase 2 D-10 already settled. |

**Installation (planner edits `pyproject.toml`):**
```toml
# Add to existing dependencies array
"fastapi>=0.115,<1.0",
"uvicorn[standard]>=0.30,<1.0",
"sse-starlette>=2.1,<4.0",   # Open Question 1 — see below
"aiosqlite>=0.20,<1.0",
# Optional test-only convenience:
# Add to [project.optional-dependencies].dev:
"httpx-sse>=0.4,<1.0",
```

**Version verification (run before writing the Standard Stack table):**
```bash
uv pip install "fastapi==0.136.1" "uvicorn[standard]==0.47.0" "sse-starlette==3.4.4" "aiosqlite==0.22.1"
uv pip show fastapi uvicorn sse-starlette aiosqlite | grep -E "^(Name|Version|Requires)"
```

## Architecture Patterns

### System Architecture Diagram

```text
Client (Phase 4/5 Next.js)
    │
    │  POST /api/v1/threads/{id}/turn   { message, override_backend?, max_cost_usd? }
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  FastAPI app (apps/api/main.py)                                          │
│    ├── lifespan (apps/api/lifespan.py)                                   │
│    │     · open DB ─→ migrate ─→ pragmas (WAL/busy_timeout/FK ON)        │
│    │     · load joblib artifacts (API-01, once)                          │
│    │     · instantiate KeyStore (in-memory + optional keyring)           │
│    │     · load settings.json                                            │
│    │     · app.state.adapters = {}     ← empty; lazy build (D-15)        │
│    │                                                                     │
│    ├── CORSMiddleware ── explicit Next.js dev origin (OSS-05)            │
│    ├── routes/health.py        (D-18 — rich healthz + adapter status)    │
│    ├── routes/threads.py       (POST/GET/PATCH/DELETE /api/v1/threads)   │
│    ├── routes/settings.py      (GET masked / PATCH plaintext)            │
│    ├── routes/rename.py        (D-17 — one-shot OpenRouterAdapter)       │
│    └── routes/turn.py          (POST .../turn — SSE heart of phase)      │
│            │                                                             │
│            │  1. fetch thread + history from SQLite                      │
│            │  2. await asyncio.to_thread(decide, ...)  ← D-16            │
│            │  3. append routing_decisions.jsonl line   ← D-05            │
│            │  4. get-or-create app.state.adapters[backend]               │
│            │  5. EventSourceResponse(stream_generator, ping=15)          │
│            │            │                                                │
│            │            ▼                                                │
│            │     for chunk in adapter.stream(...):                       │
│            │        buffer.append(chunk)                                 │
│            │        yield ServerSentEvent(                               │
│            │            event=chunk.type,                                │
│            │            data=chunk.model_dump_json(),                    │
│            │        )                                                    │
│            │        if await request.is_disconnected(): break            │
│            │                                                             │
│            │     ↓ on Done chunk:                                        │
│            │     async with db.execute("BEGIN") -- ONE TRANSACTION       │
│            │       INSERT user message                                   │
│            │       INSERT assistant message (content_blocks=buffer JSON) │
│            │       INSERT routing_decisions row                          │
│            │     COMMIT                                                  │
│            │     (STORE-05 + D-04)                                       │
│            ▼                                                             │
│     SSE stream:                                                          │
│       event: text_delta\ndata: {"type":"text_delta","text":"hi"}\n\n     │
│       event: tool_call\ndata: {...}\n\n                                  │
│       : ping\n\n   ← every 15s heartbeat (sse-starlette built-in)        │
│       event: stream_error\ndata: {...}\n\n  (optional, on error/cancel)  │
│       event: done\ndata: {...}\n\n                                       │
└─────────────────────────────────────────────────────────────────────────┘
            │                                                  │
            │ async                                            │ async
            ▼                                                  ▼
   src/routing/decide()                              apps/api/backends/{...}
   (sync sklearn, wrapped in to_thread)              (Phase 2 adapters; unchanged)

State on disk:
~/.prompt-optimizer/
  chat.db           (aiosqlite, WAL mode)
  chat.db-wal       (sidecar)
  chat.db-shm
  settings.json     (non-key settings)
  blobs/<sha256>.png  (STORE-04, ≥256 KB screenshots/diffs)
  workspaces/<thread_id>/   (Claude Code per-thread workspace)
  cache/openrouter_models.json  (Phase 2 D-17 carry-forward)

.planning/data/
  routing_decisions.jsonl   (STORE-06 + D-05)
```

### Recommended Project Structure

```text
apps/api/
├── __init__.py                  # (Phase 2 — load_dotenv + install_redaction_filter)
├── main.py                      # FastAPI app constructor + middleware + router include
├── lifespan.py                  # @asynccontextmanager async def lifespan(app)
├── paths.py                     # NEW — USER_HOME, DB_PATH, BLOBS_DIR, SETTINGS_PATH, JSONL_LOG_PATH
├── settings.py                  # NEW — load/write settings.json, computer_use_enabled()
├── routes/
│   ├── __init__.py
│   ├── health.py                # GET  /api/v1/healthz
│   ├── threads.py               # POST/GET/PATCH/DELETE /api/v1/threads(/{id})
│   ├── settings.py              # GET/PATCH /api/v1/settings
│   ├── turn.py                  # POST /api/v1/threads/{id}/turn  ← SSE
│   └── rename.py                # POST /api/v1/threads/{id}/rename
├── db/
│   ├── __init__.py
│   ├── connect.py               # open_db() with pragmas (D-03)
│   ├── queries.py               # async DB functions (D-01)
│   ├── migrate.py               # schema runner (D-02)
│   ├── models.py                # Pydantic DB-row models
│   └── migrations/
│       ├── schema_v0.sql        # initial schema (D-13)
│       └── schema_v1.sql        # first follow-up (planner picks evolution)
├── blobs.py                     # NEW — sha256-by-hash blob writer (STORE-04)
├── backends/                    # Phase 2 — unchanged
└── tests/
    ├── __init__.py
    ├── conftest.py              # NEW — aiosqlite_inmemory_db + asgi_client + fake-adapter fixtures
    ├── fixtures/
    │   └── schema_v0_seed.sql   # NEW — seeds 1 thread + 2 messages into a v0 DB
    ├── test_health.py
    ├── test_threads_crud.py
    ├── test_settings.py
    ├── test_turn_streaming.py
    ├── test_rename.py
    ├── test_migrations.py
    ├── test_blobs_by_hash.py
    ├── test_cors.py
    └── test_secure_no_key_in_logs.py
```

### Pattern 1: Lifespan with asynccontextmanager + app.state

**What:** FastAPI ≥0.95 deprecated `@app.on_event("startup"/"shutdown")` in favor of an `@asynccontextmanager` lifespan. The order locked by CONTEXT discretion (line 178): open DB → run migrations → set pragmas → load artifacts → load settings → instantiate KeyStore. Empty `app.state.adapters` registry per D-15.

**When to use:** Always for Phase 3. This is the only place artifacts load (API-01 SC #1).

**Example pattern:**
```python
# apps/api/lifespan.py — sketch, NOT full impl
from contextlib import asynccontextmanager
from fastapi import FastAPI
import aiosqlite

from apps.api.db.connect import open_db
from apps.api.db.migrate import up_to_latest
from apps.api.backends.keystore import KeyStore
from apps.api.settings import load_settings_file
from apps.api.paths import DB_PATH

# Source: fastapi.tiangolo.com/advanced/events/ + CONTEXT D-15 + discretion line 178
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. open DB (single shared connection — see Pattern 4)
    app.state.db = await open_db(DB_PATH)   # pragmas applied inside
    # 2. run migrations (idempotent — no-op if at latest)
    await up_to_latest(app.state.db)
    # 3. load joblib artifacts ONCE (API-01)
    app.state.artifacts = _load_default_artifacts()  # reuse Phase 1 loader
    # 4. load settings.json
    app.state.settings = load_settings_file()
    # 5. KeyStore — in-memory + optional keyring
    app.state.keystore = KeyStore(use_keyring=False)
    # 6. Empty adapter registry — D-15 lazy build
    app.state.adapters = {}

    try:
        yield  # ← server runs
    finally:
        await app.state.db.close()
```

### Pattern 2: sse-starlette EventSourceResponse with heartbeat + disconnect

**What:** `EventSourceResponse(content, ping=15)` wraps an async generator and adds (a) automatic 15s comment-line heartbeat (`: ping\n\n`), (b) client-disconnect detection via background `_listen_for_disconnect()` task that cancels the user generator on `http.disconnect`. Named events emitted via `ServerSentEvent(event=..., data=...)`.

**When to use:** ONE place — `routes/turn.py` (the only SSE endpoint). `routes/rename.py` returns JSON, NOT SSE.

**Example pattern:**
```python
# apps/api/routes/turn.py — sketch
import asyncio
from fastapi import APIRouter, Request, HTTPException
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from src.routing.decide import decide
from apps.api.backends.chunks import Done

router = APIRouter(prefix="/api/v1", tags=["threads"])

@router.post("/threads/{thread_id}/turn")
async def post_turn(thread_id: str, body: TurnRequest, request: Request):
    db = request.app.state.db
    artifacts = request.app.state.artifacts

    # Pre-stream errors are HTTPException (D-08)
    thread = await get_thread(db, thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    history = await get_thread_messages(db, thread_id)

    # Wrap sync sklearn (D-16 / API-07)
    if body.override_backend:
        decision = _synthesize_override_decision(body.override_backend)
    else:
        decision = await asyncio.to_thread(
            decide, body.message, history, artifacts, None
        )

    # STORE-06 — append BEFORE adapter dispatch (D-05)
    await append_routing_decisions_jsonl(decision, thread_id)

    adapter = await _get_or_create_adapter(request.app, decision.backend)

    async def event_stream():
        buffer: list = []
        try:
            async for chunk in adapter.stream(body.message, history, options):
                buffer.append(chunk)
                yield ServerSentEvent(
                    event=chunk.type,
                    data=chunk.model_dump_json(),
                )
                if isinstance(chunk, Done):
                    break
                # Proactive disconnect check (defense-in-depth; sse-starlette
                # also auto-cancels the generator on http.disconnect)
                if await request.is_disconnected():
                    break
        finally:
            # ONE transaction on Done — STORE-05 + D-04
            if buffer and isinstance(buffer[-1], Done):
                await persist_turn(db, thread_id, body.message, buffer, decision)

    return EventSourceResponse(event_stream(), ping=15)
```

### Pattern 3: Buffer-and-write-once-on-Done (STORE-05 + D-04)

**What:** Stream chunks pass through the generator without per-chunk DB writes. Accumulate in `buffer: list[ChatChunk]`. When the terminal `Done` arrives (always, per Phase 2 D-04), run ONE `BEGIN ... COMMIT` inserting the user row, the assistant row (with `content_blocks = JSON(non-TextDelta chunks)` and `text = "".join(TextDelta.text)`), and the `routing_decisions` row.

**Edge case:** Partial assistant content is preserved on `StreamError + Done` paths (cap exceeded, cancellation, provider failure) because the buffer accumulates the partial stream **before** the terminal pair lands. The `Done` chunk *always* lands per the Phase 2 D-04 invariant, so the persist call runs in every termination path. Only the bare CancelledError path (where the consumer raised before consuming `Done`) might miss the buffer flush — see Pitfall 6.

**Example:**
```python
# Inside event_stream() finally block — sketch
async def persist_turn(db, thread_id, user_text, buffer, decision):
    text_buffer = [c.text for c in buffer if c.type == "text_delta"]
    non_text = [c.model_dump() for c in buffer if c.type != "text_delta"]
    done = next((c for c in buffer if c.type == "done"), None)
    last_error = next(
        (c for c in buffer if c.type == "stream_error"), None
    )
    status = "complete"
    if last_error:
        status = "cancelled" if last_error.code == "cancelled" else "error"

    user_msg_id = _gen_id()
    assistant_msg_id = _gen_id()
    routing_id = _gen_id()

    async with db.execute("BEGIN") as _cur:
        await insert_user_message(db, user_msg_id, thread_id, user_text)
        await insert_assistant_message_with_blocks(
            db,
            assistant_msg_id,
            thread_id,
            text="".join(text_buffer),
            content_blocks=json.dumps(non_text),
            backend_used=decision.backend,
            model_used=decision.model_or_agent,
            cost_usd=done.cost_usd if done else None,
            tokens_in=done.tokens_in if done else None,
            tokens_out=done.tokens_out if done else None,
            latency_ms=done.latency_ms if done else None,
            status=status,
        )
        await insert_routing_decision(
            db, routing_id, assistant_msg_id, decision
        )
    await db.commit()
```

### Pattern 4: aiosqlite connection lifecycle (single shared connection)

**What:** Single `aiosqlite.Connection` stored on `app.state.db`, opened at lifespan, closed at shutdown. WAL mode allows concurrent readers without blocking writers — single connection is enough for the single-user local server. NO connection pool; planner does NOT add `aiosqlitepool` or similar (CONTEXT keeps the dep surface slim).

**Pragmas on first connect (D-03):** ORDER MATTERS. `journal_mode=WAL` first, then `synchronous=NORMAL`, then `busy_timeout=5000`, then `foreign_keys=ON`. **`foreign_keys=ON` is required for `ON DELETE CASCADE` (D-13) to actually fire — SQLite disables FK enforcement by default per connection.** `[CITED: sqlite.org/foreignkeys.html]`

**Example:**
```python
# apps/api/db/connect.py — full implementation sketch
import aiosqlite
from pathlib import Path

async def open_db(path: Path) -> aiosqlite.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(str(path))
    # Order matters
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA synchronous=NORMAL")
    await db.execute("PRAGMA busy_timeout=5000")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.commit()
    return db
```

**`:memory:` vs file for tests:** `aiosqlite.connect(":memory:")` creates a private, single-process database — perfect for unit tests because there's zero file I/O and zero cleanup. **Caveat:** every connection sees its OWN `:memory:` DB. If a test opens two connections, they don't share data. The Phase 3 pattern is a single shared connection on `app.state.db`, so `:memory:` is fine. **DO NOT use `file::memory:?cache=shared`** unless the planner needs the shared-cache trick — adds complexity without benefit here.

**Aiosqlite v0.22+ shutdown note:** Starting with v0.22.0, `aiosqlite.Connection` no longer inherits from `threading.Thread`. If used outside the async-context-manager pattern, callers MUST `await connection.close()` (which we already do in lifespan `finally`). `[CITED: aiosqlite changelog]`

### Pattern 5: Hand-rolled migration runner (D-02)

**What:** ~40 LOC runner reading `schema_meta.version` (single-row table), discovering `schema_v{N}.sql` files in `apps/api/db/migrations/` in numeric order, applying any unapplied file inside one transaction, and bumping `version`. Idempotent.

**Example:**
```python
# apps/api/db/migrate.py — full sketch
from pathlib import Path
import aiosqlite

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

async def _current_version(db: aiosqlite.Connection) -> int:
    """Returns -1 if schema_meta does not yet exist (fresh DB)."""
    try:
        async with db.execute(
            "SELECT version FROM schema_meta LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else -1
    except aiosqlite.OperationalError:
        # schema_meta absent — fresh DB at version -1
        return -1

def _discover_migrations() -> list[tuple[int, Path]]:
    """Return [(version_int, sql_path), ...] sorted by version_int."""
    found = []
    for path in MIGRATIONS_DIR.glob("schema_v*.sql"):
        # schema_v0.sql, schema_v1.sql, ...
        try:
            num = int(path.stem.removeprefix("schema_v"))
        except ValueError:
            continue
        found.append((num, path))
    return sorted(found)

async def up_to_latest(db: aiosqlite.Connection) -> None:
    """Apply every pending schema_v{N}.sql in numeric order.

    Idempotent: re-running with version already at latest is a no-op.
    """
    current = await _current_version(db)
    for version, path in _discover_migrations():
        if version <= current:
            continue
        sql = path.read_text(encoding="utf-8")
        # executescript runs multiple statements in one call.
        # NOTE: executescript implicitly commits the OUTER transaction
        # before running — for atomicity per migration, we BEGIN/COMMIT
        # explicitly around executescript.
        await db.execute("BEGIN")
        try:
            await db.executescript(sql)
            # Bump version (or insert if first run / schema_meta absent).
            if current < 0:
                await db.execute(
                    "INSERT INTO schema_meta (version) VALUES (?)",
                    (version,),
                )
            else:
                await db.execute(
                    "UPDATE schema_meta SET version = ?", (version,)
                )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        current = version
```

**Caveat — `executescript()` implicit commit:** aiosqlite's `executescript()` calls into sqlite3's `executescript()`, which **commits any pending transaction before executing the script**. The pattern above runs `BEGIN` and then `executescript()`, so the implicit commit from executescript ends our BEGIN before the script runs — meaning the DDL statements inside `schema_v{N}.sql` are NOT inside our transaction. This is a SQLite design quirk, NOT an aiosqlite bug. For Phase 3's threat model (single-user, local, append-only schema additions), this is acceptable. If a future schema introduces destructive DDL (DROP COLUMN, etc.), the planner should restructure: read SQL, split on `;`, execute each statement individually inside an explicit BEGIN/COMMIT. `[CITED: SQLite docs on executescript]`

### Pattern 6: SSE event parsing in tests (httpx ASGITransport caveat)

**What:** `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")` is the recommended pattern (D-20 / API-08). To consume SSE in tests:

```python
# apps/api/tests/conftest.py — sketch
import pytest
import httpx
from apps.api.main import app   # ← imported AFTER fixtures override state

@pytest.fixture
async def asgi_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        yield client

# Test usage — manual aiter_lines parsing
async def test_turn_streams_text_delta(asgi_client, monkeypatch_fake_adapter):
    async with asgi_client.stream(
        "POST",
        "/api/v1/threads/abc/turn",
        json={"message": "hi"},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = []
        cur_event = None
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                cur_event = line.removeprefix("event: ").strip()
            elif line.startswith("data: ") and cur_event:
                events.append((cur_event, line.removeprefix("data: ")))
                if cur_event == "done":
                    break   # critical: finite stream consume
                cur_event = None
        assert any(name == "text_delta" for name, _ in events)
        assert events[-1][0] == "done"
```

**`httpx-sse` alternative (cleaner):**
```python
from httpx_sse import aconnect_sse

async def test_turn_streams_text_delta_via_sse(asgi_client):
    async with aconnect_sse(
        asgi_client, "POST", "/api/v1/threads/abc/turn",
        json={"message": "hi"},
    ) as event_source:
        events = []
        async for sse in event_source.aiter_sse():
            events.append((sse.event, sse.data))
            if sse.event == "done":
                break
    assert any(name == "text_delta" for name, _ in events)
```

**Critical:** the test MUST consume in a finite loop and `break` on `done`. An infinite consume (`events = [sse async for sse in event_source.aiter_sse()]`) hangs forever against ASGITransport because of [encode/httpx#2186](https://github.com/encode/httpx/issues/2186) and [florimondmanca/httpx-sse#4](https://github.com/florimondmanca/httpx-sse/issues/4). Our streams are always finite (Phase 2 D-04 terminal Done invariant), so the break-on-done pattern is correct.

### Pattern 7: Heartbeat assertion in tests WITHOUT sleeping 15s

**What:** sse-starlette's `ping=15` default would force the test suite to wait 15 seconds to observe a heartbeat. There are two clean ways to avoid this:

1. **Pass `ping=1` (or 0.5) via a per-test app fixture.** The constructor accepts an `int` — but sse-starlette also accepts `float`-ish use in practice for sub-second intervals. Use a small int (`ping=1`) and assert the comment line appears.
2. **Monkeypatch `sse_starlette.sse.DEFAULT_PING_INTERVAL = 0.5`.** Module-level constant; fixture-scope override.

```python
# Option 1 — preferred: parametrise EventSourceResponse via app fixture
@pytest.fixture
def app_with_fast_ping(monkeypatch):
    # The cleanest hook: monkeypatch the helper at app construction time
    import sse_starlette.sse as sse_mod
    monkeypatch.setattr(sse_mod, "DEFAULT_PING_INTERVAL", 0.5)
    from apps.api.main import create_app
    return create_app()  # builds the app fresh per test

async def test_heartbeat_emits_within_1_second(asgi_client):
    # Use a slow fake adapter that yields one text_delta after 1.2s, then Done
    async with asgi_client.stream("POST", "/api/v1/threads/abc/turn", ...) as resp:
        lines = []
        async for line in resp.aiter_lines():
            lines.append(line)
            if "data: " in line and '"type":"done"' in line:
                break
        # sse-starlette ping is a comment line starting with ":"
        assert any(line.startswith(":") for line in lines)
```

### Pattern 8: JSON Merge Patch semantics for PATCH /settings (D-10)

**What:** RFC 7396 JSON Merge Patch — keys omitted from the patch are unchanged; explicit `null` values delete; nested objects merge recursively (NOT shallow). For Phase 3, only `keys.<provider>` deletion is interesting (set provider key to `null` to forget it). All other fields are simple scalars / dicts.

**Pydantic v2 partial-update pattern:**
```python
# apps/api/routes/settings.py — sketch
from typing import Optional, Annotated
from pydantic import BaseModel, ConfigDict
from fastapi import APIRouter, Request

class KeyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    openrouter: str | None = None
    anthropic: str | None = None

class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keys: KeyPatch | None = None
    backends_enabled: dict[str, bool] | None = None
    computer_use_opt_in: bool | None = None
    default_max_cost_usd: float | None = None

@router.patch("/api/v1/settings")
async def patch_settings(body: SettingsPatch, request: Request):
    # exclude_unset preserves "field not in patch" vs "field is null"
    # — but only if you use Optional[X] = None and the client sends nothing.
    patch = body.model_dump(exclude_unset=True)
    # ... merge patch into current settings, handling None as delete
    current = request.app.state.settings.copy()
    new_settings = _merge_patch(current, patch)
    write_settings_file(new_settings)
    request.app.state.settings = new_settings
    # Invalidate lazy adapter cache (D-15)
    request.app.state.adapters.clear()
    # Apply keys to KeyStore (NOT to disk)
    if patch.get("keys"):
        for provider, key in patch["keys"].items():
            if key is None:
                request.app.state.keystore._memory.pop(provider, None)
            else:
                request.app.state.keystore.set(provider, key)
    return _mask_settings_for_response(new_settings)
```

**Important:** Pydantic v2's `exclude_unset=True` differentiates "field omitted from request" (excluded) from "field present with value `None`" (included with `None`). This gives us the JSON Merge Patch null-as-delete semantic for free, IF the client uses two distinct shapes. `[CITED: pydantic.dev/concepts/serialization/]`

### Pattern 9: CORS for SSE (OSS-05)

**What:** `CORSMiddleware` with explicit Next.js origin (`http://localhost:3000`), `allow_credentials=True`, GET+POST+PATCH+DELETE methods, and explicit headers (`*` is forbidden when `allow_credentials=True`). For SSE the browser sends a `Last-Event-ID` header on reconnect; we don't use it in v1, but it costs nothing to allow.

```python
# apps/api/main.py — sketch
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apps.api.lifespan import lifespan

def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan, title="Prompt-Optimizer API", version="0.1.0")
    origins = os.environ.get(
        "PROMPT_OPTIMIZER_CORS_ORIGINS",
        "http://localhost:3000",
    ).split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins if o.strip()],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
        expose_headers=["X-Request-Id"],  # if we emit one; harmless otherwise
        max_age=600,
    )
    # routes
    from apps.api.routes import health, threads, settings, turn, rename
    app.include_router(health.router)
    app.include_router(threads.router)
    app.include_router(settings.router)
    app.include_router(turn.router)
    app.include_router(rename.router)
    return app

app = create_app()
```

**NEVER `allow_origins=["*"]`** when `allow_credentials=True` — browsers reject the configuration. `[CITED: fastapi.tiangolo.com/tutorial/cors/]`

### Pattern 10: Blob storage layout (STORE-04 + D-14)

**What:** Screenshots ≥256 KB and large file diffs are written under `~/.prompt-optimizer/blobs/<sha256>.<ext>` and the DB row stores `image_ref="~/.prompt-optimizer/blobs/<hash>.png"` instead of the base64 inline. The threshold check happens in Phase 3 — Phase 2 adapters emit `image_b64` ALWAYS.

**Where the conversion happens:** Inside `routes/turn.py`'s `event_stream` generator, BEFORE writing to buffer and BEFORE yielding to the SSE wire. Two-step: (1) intercept `Screenshot` chunks, (2) if `len(image_b64) * 0.75 >= 256 * 1024` (base64 -> bytes overhead), compute sha256 of the decoded bytes, write to `blobs/<sha256>.<ext>`, and emit a new `Screenshot(image_ref=..., image_b64=None, ...)`. The wire and the DB both see the ref. UI handles either shape (Phase 2 D-14).

**Atomic write pattern** (race safety when two concurrent turns write identical content):
```python
# apps/api/blobs.py — sketch
import base64
import hashlib
from pathlib import Path

BLOBS_DIR = Path.home() / ".prompt-optimizer" / "blobs"
INLINE_THRESHOLD_BYTES = 256 * 1024   # STORE-04

def _maybe_externalize_screenshot(chunk: Screenshot) -> Screenshot:
    if chunk.image_b64 is None:
        return chunk
    raw = base64.b64decode(chunk.image_b64)
    if len(raw) < INLINE_THRESHOLD_BYTES:
        return chunk
    sha = hashlib.sha256(raw).hexdigest()
    ext = chunk.image_format  # "png" | "jpeg"
    target = BLOBS_DIR / f"{sha}.{ext}"
    if not target.exists():
        BLOBS_DIR.mkdir(parents=True, exist_ok=True)
        # Atomic write: tmp file in same directory, then os.replace
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(raw)
        tmp.replace(target)
    return chunk.model_copy(update={
        "image_ref": str(target),
        "image_b64": None,
    })
```

**Cascade unlink on thread delete (D-14):** `DELETE /api/v1/threads/{id}` walks `messages.content_blocks` JSON for the thread, collects every `image_ref` / `diff_ref` path, unlinks each file (`Path(p).unlink(missing_ok=True)`), THEN runs the DB delete. Order matters: blobs FIRST so an interrupted delete leaves orphan blobs (recoverable by future `make gc-blobs`) rather than stale DB rows pointing to missing files.

### Pattern 11: Override-backend body field (D-15 Claude's Discretion)

**What:** Optional `override_backend` field on the turn endpoint body. When set, skip `decide()` and synthesize a `RoutingDecision` with `rationale="user override"`. Phase 5 UI-05 hook.

**Sensible-default model per backend:**
| Backend | Override model_or_agent (planner picks at execute time) | Source |
|---------|---------------------------------------------------------|--------|
| `openrouter` | `"openrouter/auto"` | matches D-11 fallback target; lets OpenRouter's meta-router decide. |
| `claude_code` | `"claude-agent-sdk"` | Phase 1 D-04 sentinel — adapter does not consume model id beyond passing through. |
| `computer_use` | `"computer-use-2025-11-24"` | Phase 1 D-04 sentinel — beta header matches. |

```python
# routes/turn.py — sketch
def _synthesize_override_decision(backend: str) -> RoutingDecision:
    return RoutingDecision(
        backend=backend,
        model_or_agent={
            "openrouter": "openrouter/auto",
            "claude_code": "claude-agent-sdk",
            "computer_use": "computer-use-2025-11-24",
        }[backend],
        rationale="user override",
        confidence=1.0,
        signals={"override": True},
    )
```

### Pattern 12: Healthz adapter status detection (D-18)

**What:** Read-only checks — never construct the adapter. Per backend:

| Backend | Status checks (read-only, in this order) |
|---------|------------------------------------------|
| `openrouter` | `KeyStore.get("openrouter") is not None` → `ready`. Else `missing_key`. |
| `claude_code` | `KeyStore.get("anthropic") is not None` → `ready`. Else `missing_key`. |
| `computer_use` | `computer_use_enabled(settings) is True` AND `KeyStore.get("anthropic") is not None` → `ready`. Else `opt_out` (if env/setting absent) or `missing_key` (if env+setting but no key). |

```python
# apps/api/routes/health.py — sketch
@router.get("/api/v1/healthz")
async def healthz(request: Request):
    settings = request.app.state.settings
    ks = request.app.state.keystore
    adapters = {
        "openrouter": (
            {"status": "ready"}
            if ks.get("openrouter")
            else {"status": "missing_key", "reason": "OPENROUTER_API_KEY not set"}
        ),
        "claude_code": (
            {"status": "ready"}
            if ks.get("anthropic")
            else {"status": "missing_key", "reason": "ANTHROPIC_API_KEY not set"}
        ),
        "computer_use": _computer_use_health(settings, ks),
    }
    artifacts_ok = request.app.state.artifacts is not None
    db_ok = True   # if we got here, lifespan opened the DB
    schema_version = await _read_schema_version(request.app.state.db)
    overall = "ok" if all(a["status"] == "ready" for a in adapters.values()) else "degraded"
    return {
        "status": overall,
        "artifacts_loaded": artifacts_ok,
        "db_ok": db_ok,
        "schema_version": schema_version,
        "adapters": adapters,
        "version": "0.1.0",
    }
```

### Pattern 13: D-12 STRICT AND-semantics for computer-use enable

**What:** `computer_use_enabled(settings) -> bool` returns `True` ONLY when `os.environ.get("COMPUTER_USE_OPT_IN") == "1"` AND `settings["computer_use_opt_in"] is True`. Both gates required.

**Integration with Phase 2:** The `ComputerUseAdapter.__init__` currently checks ONLY the env var. Phase 3 EXTENDS the check by consulting settings BEFORE constructing the adapter (lazy build site in `routes/turn.py`):

```python
# apps/api/settings.py — sketch
import os

def computer_use_enabled(settings: dict) -> bool:
    """STRICT AND-semantics per D-12. Both env AND settings must be set."""
    env_ok = os.environ.get("COMPUTER_USE_OPT_IN") == "1"
    setting_ok = bool(settings.get("computer_use_opt_in"))
    return env_ok and setting_ok

# apps/api/routes/turn.py — lazy adapter build site
async def _get_or_create_adapter(app: FastAPI, backend: str):
    if backend in app.state.adapters:
        return app.state.adapters[backend]
    if backend == "computer_use":
        if not computer_use_enabled(app.state.settings):
            raise HTTPException(
                status_code=400,
                detail=(
                    "computer-use is OFF — set COMPUTER_USE_OPT_IN=1 in env "
                    "AND enable in settings panel"
                ),
            )
        adapter = ComputerUseAdapter(app.state.keystore.get("anthropic"))
    elif backend == "claude_code":
        adapter = ClaudeCodeAdapter(app.state.keystore.get("anthropic"))
    elif backend == "openrouter":
        adapter = OpenRouterAdapter(app.state.keystore.get("openrouter"))
    else:
        raise HTTPException(status_code=400, detail=f"unknown backend {backend}")
    app.state.adapters[backend] = adapter
    return adapter
```

**Phase 2 compatibility:** The existing Phase 2 ComputerUseAdapter `__init__` still raises if env is unset. The Phase 3 gate adds the second test in front of the adapter call. The Phase 2 test (`test_optin.py`) is unchanged — Phase 3 adds new tests for the AND semantics.

### Pattern 14: Rename endpoint defensive constants (D-17)

**What:** Dedicated `POST /api/v1/threads/{id}/rename` — instantiates a fresh `OpenRouterAdapter` (NOT the cached one — defensive, single-use). Bypasses `decide()` entirely.

```python
# apps/api/routes/rename.py — sketch
from apps.api.backends.openrouter.adapter import OpenRouterAdapter
from apps.api.backends.protocol import AdapterOptions, Message as AdapterMessage
import tiktoken

RENAME_MODEL = "openai/gpt-4o-mini"   # cheap default; planner verifies current cheapest at execute time
RENAME_PROMPT_TEMPLATE = (
    "Summarize this user request in 5 words or fewer; "
    "respond with the title only, no quotes."
)
RENAME_MAX_COST_USD = 0.01
RENAME_MAX_INPUT_TOKENS = 1500   # pre-flight cap; tiktoken estimate

_ENC = tiktoken.encoding_for_model("gpt-4o-mini")

@router.post("/api/v1/threads/{thread_id}/rename")
async def rename_thread(thread_id: str, body: RenameRequest, request: Request):
    # Pre-flight token cap to prevent max_cost_usd=0.01 overrun
    estimated = len(_ENC.encode(body.first_user_message))
    if estimated > RENAME_MAX_INPUT_TOKENS:
        raise HTTPException(
            status_code=413,
            detail=f"first_user_message too long ({estimated} tokens > {RENAME_MAX_INPUT_TOKENS})",
        )
    adapter = OpenRouterAdapter(
        api_key=request.app.state.keystore.get("openrouter"),
        max_cost_usd=RENAME_MAX_COST_USD,
    )
    title_parts: list[str] = []
    async for chunk in adapter.stream(
        prompt=body.first_user_message,
        history=[AdapterMessage(role="system", content=RENAME_PROMPT_TEMPLATE)],
        options=AdapterOptions(
            model=RENAME_MODEL,
            max_cost_usd=RENAME_MAX_COST_USD,
            max_steps=1,
        ),
    ):
        if chunk.type == "text_delta":
            title_parts.append(chunk.text)
        elif chunk.type == "done":
            break
    title = "".join(title_parts).strip().strip('"').strip("'")[:60]
    await update_thread_title(request.app.state.db, thread_id, title)
    return {"title": title}
```

### Anti-Patterns to Avoid

- **DO NOT use TestClient** — D-20 explicit. TestClient is sync, uses anyio worker threads, and does NOT exercise the real async cancellation path. AsyncClient+ASGITransport is the only test client that actually drives the event loop.
- **DO NOT issue per-chunk DB writes.** STORE-05 + D-04 require buffer-and-write-once-on-Done. Per-chunk writes would saturate SQLite's single-writer lock under streaming load.
- **DO NOT call `decide()` synchronously from the async handler.** API-07 / D-16 — `decide()` calls sklearn `predict_proba` which is CPU-bound and blocks the event loop. Always wrap with `asyncio.to_thread`.
- **DO NOT eagerly construct adapters at lifespan.** D-15 explicit. Server must boot even when `ANTHROPIC_API_KEY` or `COMPUTER_USE_OPT_IN` are unset.
- **DO NOT log raw keys.** Phase 2 redaction filter is load-bearing; the settings handler MUST use `logging.getLogger(__name__)` so the filter applies. Direct `print(body.keys.openrouter)` is forbidden — covered by a regression test.
- **DO NOT silently fall back to `allow_origins=["*"]`.** OSS-05 explicit. If env unset, default to `["http://localhost:3000"]`.
- **DO NOT add `sys.path.append`.** Phase 2 D-08 anti-pattern guard still applies. Use `from apps.api.*` directly via the hatchling-packaged wheel.
- **DO NOT import FastAPI/httpx/sse-starlette from `src/routing/`.** Phase 1 D-18 import-graph guard runs in CI. Direction: `apps.api → src.routing`, never reverse.
- **DO NOT use `request.is_disconnected()` to read the request BODY.** It reads from the ASGI receive channel, which can consume body bytes. Only call it after the body has been fully parsed (FastAPI does this before the handler enters).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SSE wire framing + heartbeat + disconnect | Custom `StreamingResponse` generator with manual `: ping\n\n` writes | `sse-starlette.EventSourceResponse(content, ping=15)` (D-06) | Ping cadence + ASGI `http.disconnect` propagation + send-timeout handling are non-trivial to get right. |
| ASGI test client | Wrap `uvicorn` in a subprocess and talk to it via httpx | `httpx.AsyncClient(transport=ASGITransport(app))` (D-20) | The whole point is in-process testing without a port. |
| SSE event parsing in tests | Roll your own line-by-line parser | `httpx-sse.aconnect_sse` (already in venv) | Handles `event:`, `data:`, `id:`, `retry:`, multi-line `data:`, and `: comment` correctly. |
| Atomic JSON-file writes | `open(path, "w") + json.dump` | `tmp.write_bytes(...); tmp.replace(target)` pattern; `tmp` in same directory | Cross-filesystem rename is NOT atomic; an interrupted write corrupts settings.json. |
| SHA256-by-hash blob storage | Index files yourself by hash | `hashlib.sha256(payload).hexdigest()` + content-addressable directory `~/.prompt-optimizer/blobs/<hash>.<ext>` | Stdlib only; trivial. Race safety via tmp-then-replace. |
| Async SQLite driver | Use `sqlite3` in a thread executor | `aiosqlite>=0.20` (STORE-01) | Already pulled in; correct semantics for asyncio. |
| Foreign-key cascade DELETE | `ON DELETE CASCADE` in DDL only | DDL **plus** `PRAGMA foreign_keys=ON` on every connection (D-03) | SQLite default is FK DISABLED per connection — cascade is silently a no-op without the pragma. |
| ID generation | UUID v4 (too long for paste) | `secrets.token_urlsafe(12)` (CONTEXT discretion line 176) | ~16 chars, URL-safe base64, collision-free at single-user scale. |
| OpenAPI generation | Hand-write a spec | FastAPI auto-generates from path-op signatures + Pydantic models (D-18 Claude's Discretion) | Free. Just declare types. |
| CORS handling | Raw `OPTIONS` route + response headers | `fastapi.middleware.cors.CORSMiddleware` (OSS-05) | Battle-tested; handles preflight, origin matching, credentials, exposed headers. |
| JSON Merge Patch parsing | Walk the patch tree manually | Pydantic v2 `model_dump(exclude_unset=True)` + dict merge (D-10) | `exclude_unset` differentiates omitted-vs-null cleanly. |
| Migration runner with retries | Anything fancier than 40 LOC | Hand-rolled version walker (D-02) | No Alembic, no yoyo. Numbered SQL + `schema_meta.version` is all we need. |

**Key insight:** Phase 3's `apps/api/` builds on Phase 2's adapter contracts and Phase 1's routing brain — the heaviest libraries are already in place. The only new dependencies are `fastapi`, `uvicorn[standard]`, `sse-starlette`, and `aiosqlite`. Don't reach for a fifth.

## Project Constraints (from CLAUDE.md)

| Constraint | Source | How Phase 3 Honors It |
|------------|--------|------------------------|
| Use GSD workflow entry points; no direct edits outside GSD | `## GSD Workflow Enforcement` | Phase 3 plans are produced via `/gsd-plan-phase` after this research; executor invokes via `/gsd-execute-phase`. |
| Snake_case module files; one exception: `Feature_extractor.py` | `## Conventions / Naming Patterns` | New modules: `lifespan.py`, `paths.py`, `settings.py`, `connect.py`, `queries.py`, `migrate.py`, `blobs.py`, route modules — all snake_case. |
| `pathlib.Path(__file__).resolve().parents[N]` not `os.path` for new code | `## Architecture / Anti-Patterns` (and Phase 2 carry-forward) | Phase 3 reuses `Path(__file__).resolve().parents[2]` pattern from `apps/api/__init__.py:49`. |
| NEVER `sys.path.append` | `## Architectural Constraints` | All Phase 3 imports go through `apps.api.*` and `src.routing.*` via the hatchling wheel. |
| pytest `--import-mode=importlib`, `asyncio_mode=auto`, `markers=["live"]` | `## Testing` carry-forward | Phase 3 adds tests under `apps/api/tests/`; pytest config is already correct. |
| Saved-artifact dict shape `{model, vectorizer, scaler, label_encoder, feature_columns}` | `## Persistence Patterns` | Phase 3 reuses Phase 1's `load_joblib_artifacts` loader verbatim in the lifespan. |
| F-string formatted metrics and section header banners in scripts; printable logs | `## Logging` | Phase 3 uses `logging.getLogger(__name__)` everywhere (so the redaction filter applies), NOT `print()`. D-19 requires INFO at three turn boundaries. |

## Runtime State Inventory

**Phase 3 is greenfield for storage and service** — no rename, no refactor, no migration of existing runtime state. There is no pre-existing SQLite, no Datadog, no Task Scheduler, no SOPS secrets. **This section is intentionally minimal** because the only state Phase 3 introduces is the one it creates from scratch.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — `~/.prompt-optimizer/chat.db` is created fresh on first lifespan run | None; lifespan runs migrations to v0 on first boot. |
| Live service config | None — Phase 3 IS the new service | N/A |
| OS-registered state | None | N/A |
| Secrets/env vars | Existing: `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `COMPUTER_USE_OPT_IN` (Phase 2). NEW: `PROMPT_OPTIMIZER_HOME` (optional), `PROMPT_OPTIMIZER_CORS_ORIGINS` (optional) | Document in `.env.example` (planner verifies SECURE-03 + OSS-03). |
| Build artifacts | None — Phase 3 ships pure Python in `apps/api/`; the existing wheel layout (`packages = ["src", "apps"]`) already covers it | None. |

**Nothing else found — verified by:** scan of `apps/api/` (Phase 2 only), `~/.prompt-optimizer/` (does not yet exist on dev machine; verified via `ls`), `pyproject.toml` (no Phase 3 deps yet).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.10+ | All Phase 3 code | ✓ | venv Python 3.11.x (`uv pip list` shows 3.11 site-packages) | — |
| `uv` package manager | Adding deps + `uv sync` | ✓ | 0.11.13 (Homebrew) | `pip install` |
| `sqlite3` library (Python stdlib) | `aiosqlite` backend | ✓ | SQLite 3.51.0 (well above 3.35 floor for DROP COLUMN) | — |
| `pytest` framework | All tests | ✓ | 9.0.3 | — |
| `httpx` test transport | API-08 / D-20 | ✓ | 0.28.1 | — |
| `httpx-sse` (optional but recommended) | SSE test parsing | ✓ | 0.4.3 (pulled in via venv setup) | manual `aiter_lines()` parsing |
| `sse-starlette` | D-06 SSE primitive | ✓ | **3.4.4** (transitive via `mcp`; CONTEXT range is `>=2.1,<3.0`) | See Open Question 1. |
| `anyio` | Starlette internals + run_in_threadpool | ✓ | 4.13.0 | — |
| `starlette` | FastAPI underlay | ✓ | 1.0.0 (in venv as transitive) | — |
| `fastapi` | Phase 3 web framework | ✗ | — | Install via `pyproject.toml` — Wave 0 task. |
| `uvicorn[standard]` | ASGI server | ✗ | — | Install via `pyproject.toml` — Wave 0 task. |
| `aiosqlite` | STORE-01 driver | ✗ | — | Install via `pyproject.toml` — Wave 0 task. |
| Network egress | NLTK punkt download on first `decide()` (Phase 1 carry-forward) | depends on env | — | CI workflow already pre-fetches NLTK data; lifespan-time `decide()` smoke must work on developer machines that have already cached. |

**Missing dependencies with no fallback:** None. All three blocking items (`fastapi`, `uvicorn`, `aiosqlite`) are standard PyPI installs that the planner adds in Wave 0.

**Missing dependencies with fallback:** None — all Phase 3 features have a viable install path.

## Common Pitfalls

### Pitfall 1: `PRAGMA foreign_keys=ON` is per-connection, defaults to OFF
**What goes wrong:** Schema declares `ON DELETE CASCADE` (D-13). Tests pass (because they re-set the pragma). Production deletes silently leave orphan child rows.
**Why it happens:** SQLite default is FK enforcement DISABLED for backward compatibility. Each new connection starts with FKs off.
**How to avoid:** `apps/api/db/connect.py:open_db()` MUST `await db.execute("PRAGMA foreign_keys=ON")` on every connection (D-03). Phase 3 uses a single shared connection — so this only runs once at lifespan, but the code defensively re-runs it on every test fixture too.
**Warning signs:** `DELETE FROM threads WHERE id=?` returns success but child `messages` rows remain.

### Pitfall 2: `aiosqlite.connect(":memory:")` is per-connection — second connection sees an empty DB
**What goes wrong:** Test fixture uses `:memory:`. Second test reuses the same path string. Each test gets a fresh empty DB and previous-test data is gone.
**Why it happens:** SQLite `:memory:` databases are private to the connection. Multiple connections to `":memory:"` create multiple private DBs.
**How to avoid:** Either (a) use a single connection per test and yield from fixture, or (b) use `file::memory:?cache=shared` URI form to share. Phase 3's pattern is single shared connection → option (a) is correct.
**Warning signs:** Tests pass individually but fail when run together; or `SELECT` returns 0 rows immediately after `INSERT`.

### Pitfall 3: `executescript()` implicitly commits before running
**What goes wrong:** Migration runner runs `BEGIN; executescript(open(file).read()); COMMIT;` — but the DDL inside the file is NOT inside the BEGIN.
**Why it happens:** SQLite docs state `executescript()` commits any pending transaction before running its body. `[CITED: sqlite.org/python/sqlite3.html#executescript]`
**How to avoid:** For Phase 3's append-only migrations (CREATE TABLE, CREATE INDEX, ALTER TABLE ADD COLUMN), this is fine — partial failures are extremely rare for DDL. For destructive DDL (DROP COLUMN), split on `;` and execute each statement individually inside one explicit BEGIN/COMMIT. Document this in migrate.py docstring.
**Warning signs:** A migration with `INSERT INTO seed_data` rows partially populates; or a failed migration leaves the schema in an inconsistent state.

### Pitfall 4: `httpx.ASGITransport.stream()` hangs on infinite SSE generators
**What goes wrong:** Test does `events = [sse async for sse in event_source.aiter_sse()]` against a generator with no terminal sentinel. Test hangs forever (or until pytest-timeout kicks in).
**Why it happens:** [encode/httpx#2186](https://github.com/encode/httpx/issues/2186) — ASGITransport buffers the full body before yielding. With an infinite stream, the buffer never closes.
**How to avoid:** Phase 3 streams are ALWAYS finite (Phase 2 D-04 terminal Done invariant). Tests must consume in a finite loop and `break` on `event=done`. Apply `@pytest.mark.timeout(5)` as a belt-and-suspenders.
**Warning signs:** Test that worked yesterday hangs today after an adapter change that lost the terminal Done.

### Pitfall 5: sse-starlette `ping=15` default makes tests wait 15s
**What goes wrong:** Heartbeat test sleeps for 15s waiting for the `: ping` comment line. CI run cost balloons.
**Why it happens:** sse-starlette default `DEFAULT_PING_INTERVAL=15`. Tests can't observe a heartbeat without waiting for the timer.
**How to avoid:** Monkeypatch `sse_starlette.sse.DEFAULT_PING_INTERVAL = 0.5` in a fixture; or build a per-test app where the SSE route uses `EventSourceResponse(..., ping=1)` explicitly. The CI-friendly heartbeat-assert latency target is <2 s.
**Warning signs:** `pytest --durations=10` shows the heartbeat test as the slowest.

### Pitfall 6: `request.is_disconnected()` doesn't fire under ASGITransport
**What goes wrong:** Cancellation test expects `is_disconnected()` to return True after closing the response. It returns False forever; the upstream adapter call never aborts.
**Why it happens:** ASGITransport's ASGI receive channel does NOT inject `http.disconnect` when the consumer closes the response — it only injects on real network close. **CancelledError DOES propagate** (because the receive task gets cancelled) — but the proactive `is_disconnected()` poll is a no-op in ASGITransport tests.
**How to avoid:** In tests, drive cancellation by cancelling the asyncio task that consumes the stream (`task.cancel()`), NOT by closing the response. The Phase 2 D-19 cancellation invariant test already uses this pattern. Real-network cancellation in production is tested manually + via Playwright in Phase 6.
**Warning signs:** Cancellation test never observes the StreamError("cancelled") chunk.

### Pitfall 7: Pydantic `model_dump(exclude_unset=True)` treats `None` differently from "omitted"
**What goes wrong:** Client sends `{"keys": {"openrouter": null}}` to delete the OpenRouter key. Server `exclude_unset=True` returns `{"keys": {"openrouter": None}}` (included because set explicitly). Server interprets None as "no change" instead of "delete". Key persists.
**Why it happens:** `exclude_unset` is field-set, not value-truthy. Both `None` (explicit null) and `"sk-..."` are "set"; only "not in the request at all" is "unset".
**How to avoid:** Apply RFC 7396 semantics in the merge step: walk the patch dict and treat `None` values inside `keys.*` as a DELETE operation explicitly. Test it: send `{"keys": {"openrouter": null}}` and assert the key is gone from KeyStore.
**Warning signs:** Users complain that "remove key" silently fails.

### Pitfall 8: `app.state.adapters.clear()` doesn't disconnect in-flight streams
**What goes wrong:** User PATCHes settings while a turn is mid-stream. `app.state.adapters.clear()` empties the dict. The next turn rebuilds with new keys — but the CURRENT in-flight turn still holds a reference to the old adapter (Python doesn't drop it). That's actually correct (we want the in-flight turn to finish with the keys it started with), but operators may expect immediate disconnect.
**Why it happens:** `dict.clear()` removes the dict entry but doesn't invalidate live references. Async generators hold their own reference to the adapter via closure.
**How to avoid:** Document this in the settings endpoint's docstring. NEW keys take effect on the NEXT turn, not the CURRENT one. If a turn must be killed, the client should close the SSE response (which propagates CancelledError to the generator → adapter cleanup).
**Warning signs:** Confused operator file: "I changed my key but the broken turn still uses the old key."

### Pitfall 9: Loading joblib at lifespan inside a worker can be slow → uvicorn startup >3s
**What goes wrong:** Lifespan loads three joblib files (task_type_classifier 1.86 MB + agentic_intent_classifier ~? + model_router 4.29 MB). On a cold-cache laptop, this can run 5-10s. SC #1 says "<3s".
**Why it happens:** joblib uses pickle + numpy memory-mapping; first load reads + decompresses; later loads are mmap-cached. NLTK download for the first `decide()` call adds another 1-2s.
**How to avoid:** Pre-fetch NLTK on the developer machine (`python -c "import nltk; nltk.download('punkt_tab'); nltk.download('punkt')"`). Use `make setup` (Phase 6 OSS-02) to bake this in. For CI, the NLTK cache is already pre-fetched per Phase 1 P02 carry-forward. The actual joblib load on a warmed laptop is ~500 ms — well under budget.
**Warning signs:** First-run UAT fails the <3s SC; subsequent runs pass.

### Pitfall 10: `dotenv.load_dotenv()` at import is silent if `.env` is malformed
**What goes wrong:** Developer types `OPENROUTER_API_KEY=sk...` with a typo (missing quote on a value containing spaces); dotenv silently ignores the line; KeyStore returns None; healthz reports `missing_key`; operator chases a phantom missing key.
**Why it happens:** python-dotenv's default behavior on parse errors is to skip the bad line and continue.
**How to avoid:** Add a smoke test in healthz: if env says key is set but KeyStore returns None, log a warning (with the key redacted, of course). Or rely on the explicit healthz output that says "missing_key" — already the design.
**Warning signs:** Developer claims they set `OPENROUTER_API_KEY` and `healthz` says it's missing.

### Pitfall 11: Concurrent `tmp.replace(target)` on identical content races
**What goes wrong:** Two concurrent turns both decode a 300 KB screenshot, both hash to the same sha256, both write to `blobs/<sha>.tmp.png`, one replaces the other's tmp file mid-write → corruption.
**Why it happens:** Both writers use the same `tmp` path. On POSIX, `tmp.replace(target)` is atomic only IF nobody else is writing the tmp file.
**How to avoid:** Use a unique tmp suffix per write: `tmp = target.parent / f"{target.name}.{secrets.token_hex(4)}.tmp"`. Then `tmp.replace(target)` — if target already exists with identical content, the replace is harmless. (Better still: check `target.exists()` first, skip the write entirely.) The code in Pattern 10 does the `if not target.exists()` check explicitly.
**Warning signs:** Sporadic corrupt PNG files in `blobs/`; usually only under load.

## Code Examples

Verified patterns from official sources or directly from the existing repo:

### Example 1 — aiosqlite async context manager pattern
```python
# Source: aiosqlite docs (pypi.org/project/aiosqlite)
import aiosqlite

async with aiosqlite.connect("path/to/db") as db:
    await db.execute("INSERT INTO some_table ...")
    await db.commit()
    async with db.execute("SELECT * FROM some_table") as cursor:
        async for row in cursor:
            ...
```

Phase 3 doesn't use this `async with` pattern at the connection level (we hold the connection in `app.state.db` for the lifespan). We do use `async with db.execute(...) as cursor` for individual queries.

### Example 2 — FastAPI lifespan
```python
# Source: fastapi.tiangolo.com/advanced/events/
from contextlib import asynccontextmanager
from fastapi import FastAPI

ml_models = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    ml_models["answer_to_everything"] = lambda x: x * 42
    yield
    ml_models.clear()

app = FastAPI(lifespan=lifespan)
```

### Example 3 — httpx-sse + ASGITransport canonical test pattern
```python
# Source: github.com/florimondmanca/httpx-sse — adapted for ASGI
import httpx
from httpx_sse import aconnect_sse

async with httpx.AsyncClient(
    transport=httpx.ASGITransport(app=app),
    base_url="http://test",
) as client:
    async with aconnect_sse(
        client, "POST", "/api/v1/threads/abc/turn", json={"message": "hi"}
    ) as event_source:
        async for sse in event_source.aiter_sse():
            print(sse.event, sse.data)
            if sse.event == "done":
                break
```

### Example 4 — sse-starlette EventSourceResponse with named events
```python
# Source: github.com/sysid/sse-starlette README + apps/api/backends/chunks.py
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

async def event_stream():
    yield ServerSentEvent(event="text_delta", data='{"type":"text_delta","text":"hi"}')
    yield ServerSentEvent(event="done", data='{"type":"done"}')

return EventSourceResponse(event_stream(), ping=15)
# Wire output:
# event: text_delta\ndata: {"type":"text_delta","text":"hi"}\n\n
# event: done\ndata: {"type":"done"}\n\n
# (with ": ping\n\n" every 15s)
```

### Example 5 — Atomic JSON-file write
```python
# Source: docs.python.org/3/library/os.html#os.replace + CONTEXT discretion line 177
import json
from pathlib import Path

def write_settings_file(settings: dict, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(settings, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(target)  # atomic on POSIX + Windows when same filesystem
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| FastAPI `@app.on_event("startup")` / `@app.on_event("shutdown")` | `@asynccontextmanager async def lifespan(app)` passed to `FastAPI(lifespan=...)` | FastAPI 0.95.0 (Apr 2023); old API deprecated since | Phase 3 uses lifespan only. |
| sse-starlette 2.x APIs | sse-starlette 3.x (test isolation improvements, `shutdown_event` knob) | sse-starlette 3.0 (late 2024) | Public API `EventSourceResponse(content, ping, send_timeout)` is unchanged; 3.x just better test isolation. See Open Question 1. |
| SQLite `journal_mode=DELETE` | `journal_mode=WAL` for concurrent reads | SQLite 3.7.0 (2010); now default in many wrappers | Phase 3 sets WAL explicitly per D-03. |
| `aiosqlite.Connection` inherits from `threading.Thread` | v0.22+ standalone (must close explicitly) | aiosqlite 0.22.0 (Dec 2025) | Phase 3 closes via `await db.close()` in lifespan `finally`. |
| Pydantic v1 `model.dict(exclude_unset=True)` | Pydantic v2 `model.model_dump(exclude_unset=True)` | Pydantic 2.0 (Jun 2023) | Phase 2 already on v2; Phase 3 inherits. |
| `claude-code-sdk` package | `claude-agent-sdk` package | mid-2025 deprecation | Phase 2 already migrated; Phase 3 inherits via Phase 2 adapters. |

**Deprecated / outdated:**
- `@app.on_event` — replaced by lifespan.
- `keyring<24` — Phase 2 D-10 already pins `>=24,<26`.
- Sync `TestClient` for streaming tests — D-20 forbids; use AsyncClient+ASGITransport.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | sse-starlette public API (`EventSourceResponse(content, ping, send_timeout, ping_message_factory)`) is unchanged between 2.x and 3.x — both expose the surface Phase 3 needs. | Standard Stack + Open Question 1 | If 3.x quietly renamed a parameter we depend on, planner discovers at execute time and downgrades dep range. Mitigation: pin specific 3.4.x version in `uv.lock` after verifying smoke test passes. `[ASSUMED]` based on README and PyPI page; not exhaustively diffed against 2.4.1 source. |
| A2 | `openai/gpt-4o-mini` is still the cheapest OpenRouter-routed model suitable for thread-rename one-shots at execute time. | Pattern 14 (rename endpoint) | If OpenRouter retires `openai/gpt-4o-mini` or a cheaper alternative emerges, rename costs ≠ 0.01 budget. Mitigation: planner verifies model availability against `config/model_mapping.json` at execute time; CONTEXT discretion line 348 explicitly authorises the swap. `[ASSUMED]` from CONTEXT specifics; not freshly verified against OpenRouter `/v1/models` this session. |
| A3 | `aiosqlite.executescript()` implicitly commits any pending transaction. | Pattern 5 + Pitfall 3 | If aiosqlite's wrapper handles this differently from the underlying sqlite3, the migration BEGIN/COMMIT around it is wrong. Mitigation: planner verifies in Wave 1 by writing a test that runs two migrations and asserts both versions are present. `[CITED: sqlite.org/python/sqlite3.html#executescript]` — based on stdlib sqlite3 behaviour; aiosqlite wraps that module directly so the behaviour propagates. |
| A4 | `httpx.ASGITransport` injects `http.disconnect` only on real network close, not on `response.aclose()`. | Pitfall 6 | If newer httpx versions started injecting on aclose, the proactive `is_disconnected()` poll would actually fire and the Phase 2 cancellation contract still works in tests. Mitigation: rely on task.cancel() pattern from Phase 2 D-19 contract suite (already proven). `[ASSUMED]` from issue threads; not directly tested. |
| A5 | The Phase 1 D-18 import-graph guard test will continue to pass after Phase 3 adds FastAPI imports — because Phase 3 imports `apps.api.*` from outside `src/routing/`, and the guard walks sys.modules AFTER importing `src.routing.decide` (not after importing `apps.api.main`). | Project Constraints + Pattern 6 in §Tests | If a future refactor accidentally imports from `apps.api.*` inside `src/routing/`, the guard catches it. Mitigation: existing test stays as-is; Phase 3 plans don't touch `src/routing/`. `[VERIFIED: src/routing/tests/test_decide_smoke.py]` |

**If user confirms A1 by allowing range expansion `sse-starlette>=2.1,<4.0`:** Open Question 1 closes, A1 becomes verified.

## Open Questions

### Open Question 1 — sse-starlette version range
**What we know:** CONTEXT D-06 locks `sse-starlette>=2.1,<3.0`. The latest 2.x is 2.4.1 (July 2025). The current 3.x line (3.4.4 as of May 2026) is already in the developer's venv as a transitive of `mcp`. The 2.x→3.x changes (per README + PyPI history) are internal test-isolation improvements and a `shutdown_event` knob — the public `EventSourceResponse(content, ping=15)` + `request.is_disconnected()` + `ServerSentEvent(event=, data=)` surface that Phase 3 uses is unchanged.
**What's unclear:** Does the CONTEXT-locked `<3.0` upper bound reflect a real compatibility constraint (someone tested 3.x and saw a break), or a snapshot taken before 3.0 shipped?
**Recommendation:** Planner SHOULD widen the dep range to `sse-starlette>=2.1,<4.0` in `pyproject.toml`. Rationale: (a) the API surface we use is identical, (b) the venv already has 3.x via mcp so `<3.0` would force a downgrade that breaks mcp, (c) 3.x has the better test-isolation improvements that benefit Phase 3 tests. If the user pushes back, the alternative is to pin `sse-starlette==2.4.1` and remove mcp (a worse trade). Document the widening in the plan's deviation note.

### Open Question 2 — `schema_v1.sql` evolution choice
**What we know:** STORE-03 requires a v0 → v1 migration test (success criterion #5). `schema_v0.sql` is fully specified by D-13. CONTEXT canonical refs line 253 says "the planner picks the first non-trivial schema evolution; e.g., adding an index or a new column referenced by Phase 5".
**What's unclear:** WHICH evolution? Options:
- (a) **Add a per-thread `pinned BOOLEAN DEFAULT 0` column** — Phase 5 UI-02 could surface this. Pure ALTER TABLE ADD COLUMN; safe in all SQLite versions.
- (b) **Add `CREATE INDEX idx_messages_thread_id_created_at ON messages(thread_id, created_at)`** — improves history fetch performance; non-destructive.
- (c) **Add a `routing_feedback` table** — Phase 5 UI-15 ("wrong route" thumbs-down) needs this; would be a real new structure.
**Recommendation:** (b). Adding an index is the cheapest, most defensible evolution that DOES affect query plans (so the migration test can verify both row preservation AND that the index exists post-migration). Option (c) couples Phase 3 to Phase 5 unnecessarily; option (a) is too trivial to be a useful migration test target. Planner has discretion; document the choice in the plan.

### Open Question 3 — Single shared connection vs. per-request connection
**What we know:** D-01 says raw aiosqlite, but does NOT explicitly mandate single-vs-pool. WAL + busy_timeout=5000 (D-03) tolerates concurrent connections gracefully. Single-user local server has near-zero concurrency.
**What's unclear:** Should `app.state.db` be a single shared `aiosqlite.Connection` (simpler, but serializes all writes within the connection's worker thread), or should each request open its own (more isolation, but adds connection-open overhead and per-connection pragma re-application)?
**Recommendation:** **Single shared connection**. Single-user local server, SQLite WAL allows concurrent readers without blocking writers, single connection's worker thread serializes writes safely. Saves us from re-running pragmas on every request and avoids contention on `chat.db-shm`. The alternative (per-request) buys nothing in v1. Document explicitly in `connect.py` docstring so a future contributor doesn't change it casually.

### Open Question 4 — `routing_decisions.jsonl` write timing under high parallelism
**What we know:** D-05 appends one line per turn at decide-time. Single-user local server, but a developer could fire two turns concurrently via the test harness or a debug script.
**What's unclear:** Do we need file-locking? `pathlib.Path.write_text(mode="a")` opens-appends-closes; on POSIX, append writes are atomic up to PIPE_BUF (~4 KB). Most routing-decision lines will be < 4 KB.
**Recommendation:** Use plain `open(path, "a")` write per line; POSIX append-atomic guarantee covers our line sizes. Document the 4 KB threshold in the writer's docstring; if a future feature adds large `signals` payloads (e.g. embedding vectors), revisit. Risk: very low; mitigation: a sanity test that fires 10 concurrent turns and asserts 10 lines in the JSONL.

### Open Question 5 — Healthz schema_version read on every request
**What we know:** D-18's healthz response includes `"schema_version": 1`. Lifespan reads it once at startup.
**What's unclear:** Re-read on every healthz request (1 SELECT, ~50 µs), or cache on `app.state.schema_version`?
**Recommendation:** Cache on `app.state.schema_version` at lifespan; re-read NEVER during request handling. Migrations happen ONLY at lifespan (the only writer of `schema_meta`), so the cached value is correct for the lifetime of the process. Saves a query per healthz call from Phase 5's status-dot UI polling.

## Validation Architecture

> Phase 3 has `workflow.nyquist_validation: true` in `.planning/config.json`. This section is required.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio 1.3.0 + pytest-timeout 2.4.0 |
| Config file | `pyproject.toml [tool.pytest.ini_options]` (already configured: `--import-mode=importlib`, `asyncio_mode=auto`, `markers=["live"]`, `testpaths=["src", "apps"]`) |
| Quick run command | `uv run pytest -m 'not live' apps/api/tests -x --timeout=30` |
| Full suite command | `uv run pytest -m 'not live' -x --timeout=60` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| API-01 | Joblib artifacts load once at lifespan; not reloaded per request | unit | `pytest apps/api/tests/test_health.py::test_artifacts_loaded_once -x` | ❌ Wave 0 (new) |
| API-02 | `POST /api/v1/threads/{id}/turn` streams ChatChunk SSE | integration | `pytest apps/api/tests/test_turn_streaming.py -x --timeout=30` | ❌ Wave 4 (new) |
| API-03 | Thread CRUD (`POST/GET/PATCH/DELETE /api/v1/threads`) | integration | `pytest apps/api/tests/test_threads_crud.py -x` | ❌ Wave 3 (new) |
| API-04 | BYOK settings; keys never persisted to DB or log | integration | `pytest apps/api/tests/test_settings.py apps/api/tests/test_secure_no_key_in_logs.py -x` | ❌ Wave 3 + Wave 5 (new) |
| API-05 | 15s heartbeat during long agent run | integration | `pytest apps/api/tests/test_turn_streaming.py::test_heartbeat_emits -x` | ❌ Wave 4 (new; uses monkeypatched ping<1s) |
| API-06 | `request.is_disconnected()` cancels upstream within 2s | integration | `pytest apps/api/tests/test_turn_streaming.py::test_cancellation_within_2s -x --timeout=5` | ❌ Wave 4 (new; uses task.cancel() pattern from D-19) |
| API-07 | `decide()` wrapped in `asyncio.to_thread` (no event-loop block) | unit | `pytest apps/api/tests/test_turn_streaming.py::test_decide_runs_in_thread -x` | ❌ Wave 4 (new; asserts asyncio.to_thread call via monkeypatch) |
| API-08 | Integration tests use httpx.AsyncClient + ASGITransport (NOT TestClient) | meta | `! grep -r 'TestClient' apps/api/tests/` (negative grep) | ❌ Wave 0 (new; add CI step) |
| STORE-01 | aiosqlite 0.20+, WAL, busy_timeout=5000 on first connect | unit | `pytest apps/api/tests/test_health.py::test_pragmas_applied -x` | ❌ Wave 1 (new) |
| STORE-02 | Three-table schema (threads / messages / routing_decisions) | unit | `pytest apps/api/tests/test_migrations.py::test_schema_v0_has_all_three_tables -x` | ❌ Wave 1 (new) |
| STORE-03 | Migration v0 → v1 without data loss | integration | `pytest apps/api/tests/test_migrations.py::test_v0_to_v1_preserves_data -x` | ❌ Wave 1 (new; uses fixtures/schema_v0_seed.sql) |
| STORE-04 | Blobs ≥256 KB written to `~/.prompt-optimizer/blobs/<sha256>` | unit + integration | `pytest apps/api/tests/test_blobs_by_hash.py -x` | ❌ Wave 5 (new) |
| STORE-05 | One transaction per turn on Done (no per-chunk writes) | integration | `pytest apps/api/tests/test_turn_streaming.py::test_one_transaction_per_turn -x` | ❌ Wave 4 (new; asserts DB row counts after stream completes) |
| STORE-06 | Every decision appended to `.planning/data/routing_decisions.jsonl` | unit | `pytest apps/api/tests/test_turn_streaming.py::test_jsonl_log_appended -x` | ❌ Wave 4 (new) |
| OSS-05 | CORS explicit Next.js origin (no wildcard) | unit | `pytest apps/api/tests/test_cors.py -x` | ❌ Wave 2 (new) |

### Sampling Rate

- **Per task commit:** `uv run pytest -m 'not live' apps/api/tests -x --timeout=30` — runs only Phase 3 tests, <60s on a warm laptop. Captures regressions at task granularity.
- **Per wave merge:** `uv run pytest -m 'not live' -x --timeout=60` — runs Phase 1 + Phase 2 + Phase 3 (the whole non-live suite). Confirms no Phase 1 D-18 guard breakage and no Phase 2 adapter contract regression.
- **Phase gate:** Full suite green before `/gsd-verify-work`. Plus `uv run python -m apps.api.main --help` (or equivalent boot smoke) succeeds and `uvicorn apps.api.main:app` boots in <3 s with no errors.
- **Max feedback latency target:** <60 s for the per-task-commit suite. Achievable because every Phase 3 integration test uses `:memory:` SQLite, fake adapters via `app.state.adapters` override, monkeypatched `DEFAULT_PING_INTERVAL=0.5`.

### Wave 0 Gaps (test infrastructure to land BEFORE Wave 1 code)

- [ ] `apps/api/tests/__init__.py` — package marker.
- [ ] `apps/api/tests/conftest.py` — three core fixtures:
  - `aiosqlite_inmemory_db` — yields an `aiosqlite.Connection` to `":memory:"` with all migrations applied. Closes on teardown.
  - `asgi_client` — yields `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")`. Uses a per-test `create_app()` factory so state overrides land BEFORE startup.
  - `app_factory` — accepts `adapters_override: dict[str, BackendAdapter]`, `settings_override: dict`, `keystore_override: KeyStore` and returns a fresh FastAPI app whose lifespan honors the overrides (i.e., `app.state.adapters = adapters_override or {}`).
- [ ] `apps/api/tests/fixtures/schema_v0_seed.sql` — INSERTs 1 thread + 2 messages + 1 routing_decisions row into a fresh v0 DB; used by `test_migrations.py::test_v0_to_v1_preserves_data`.
- [ ] `apps/api/tests/fake_adapter.py` — `class FakeStreamingAdapter` implementing `BackendAdapter`; constructor takes a list of `ChatChunk` to emit + optional sleep-per-chunk for heartbeat tests. Used to drive `test_turn_streaming.py` without touching real OpenAI/Anthropic clients.
- [ ] Negative-grep CI step: `! grep -rE 'from fastapi.testclient|fastapi\.testclient\.TestClient' apps/api/tests/` to enforce API-08 / D-20.
- [ ] Framework install: `uv sync` after Wave 0 pyproject.toml edits brings in `fastapi`, `uvicorn[standard]`, `sse-starlette`, `aiosqlite`. `pytest-asyncio` + `pytest-timeout` already present.

## Security Domain

> `security_enforcement` defaults to enabled. Phase 3 surfaces BYOK keys, JSONL on-disk logs, an HTTP API surface, and SQLite persistence — all in scope.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | partial | BYOK = no app-level auth. Phase 3 just trusts the loopback; documented in Phase 6 SECURE-06 (threat model). |
| V3 Session Management | no | Stateless API on loopback; no sessions. |
| V4 Access Control | partial | Single-user local server; access control is OS-level (file permissions on `~/.prompt-optimizer/`). Document in OSS-04. |
| V5 Input Validation | yes | **Pydantic v2 models on every request body**; route signatures declare expected types; FastAPI auto-rejects malformed JSON with 422. |
| V6 Cryptography | no (storage-only) | No crypto operations Phase 3 owns; keys live in memory + optional OS keyring (Phase 2 D-10). |
| V7 Error Handling and Logging | yes | **Phase 2 RedactionFilter** (carry-forward, installed at `apps.api.__init__` import) rewrites `sk-`, `sk-ant-`, `Bearer …` BEFORE any handler. Phase 3 INFO logs at turn boundaries (D-19); per-chunk DEBUG opt-in. |
| V8 Data Protection | yes | BYOK keys NEVER persisted to SQLite or `settings.json` or any log (D-10 / D-11 / SECURE-04). PATCH /settings regression test asserts. |
| V9 Communication | partial | HTTPS is Phase 6 hosting concern (out of scope for v1 local server). |
| V13 API Security | yes | OpenAPI auto-generated, rate-limiting deferred (CONTEXT deferred line 366 — single-user). |

### Known Threat Patterns for FastAPI + aiosqlite + SSE

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via `thread_id` path param | Tampering | Parameterised queries everywhere (`db.execute("SELECT ... WHERE id = ?", (thread_id,))`); never f-string SQL. Pydantic validates path param types. |
| Path traversal via `image_ref` from a tampered DB | Tampering | `image_ref` is set by Phase 3 itself (D-14 transcoder); never user-controlled. Defensive: when reading `image_ref` for cascade-unlink (D-14), assert it starts with `BLOBS_DIR` resolved-real-path. |
| Plaintext key in error log (`logger.error(f"failed for key {k}")`) | Information Disclosure | RedactionFilter rewrites `sk-`, `sk-ant-`, `Bearer …`. Plus pre-commit hook from Phase 2 D-09 blocks the literal at commit time. |
| Plaintext key in `GET /settings` response | Information Disclosure | D-10 explicit: keys ALWAYS masked on the wire. Response model is `{provider: {present: bool, masked: str}}`. Regression test in `test_secure_no_key_in_logs.py`. |
| Plaintext key in `routing_decisions.jsonl` `signals` payload | Information Disclosure | `signals` from Phase 1 `RoutingDecision` is structured per-stage telemetry — never contains raw keys (verified by `signals` field set: `task_type`, `task_confidence`, `agentic_intent`, ...; no key-shaped strings). Defensive: a regression test grep on the JSONL. |
| Computer-use accidentally enabled in CI | Tampering / Spoofing | D-12 STRICT AND-semantics — both env AND setting required. ComputerUseAdapter `__init__` raises at construction time. |
| `request.is_disconnected()` consumes request body | Tampering | Phase 3 calls it only INSIDE the SSE generator, AFTER the body has been parsed by FastAPI. The handler signature `async def post_turn(body: TurnRequest, request: Request)` ensures body is fully consumed before generator runs. |
| Migration runner replays old `schema_v{N}.sql` overwrites newer state | Tampering | `schema_meta.version` gate skips already-applied migrations; idempotent. |
| CORS reflection attack via `Origin: evil.com` | Spoofing | Explicit allowlist (`http://localhost:3000`); no wildcard; no regex with `.*`. `[CITED: fastapi.tiangolo.com/tutorial/cors/]` |
| Settings file race (concurrent PATCH /settings) | Tampering / Repudiation | `tmp.replace(target)` atomic write; single shared connection serializes writes; single-user local server has near-zero concurrency. |

## Sources

### Primary (HIGH confidence)
- `apps/api/__init__.py` (existing codebase) — load_dotenv + install_redaction_filter + PROJECT_ROOT pathlib pattern at lines 49-59.
- `apps/api/backends/{protocol,chunks,keystore,cost,pricing}.py` — Phase 2 shared modules Phase 3 reuses.
- `apps/api/backends/{openrouter,claude_code,computer_use}/adapter.py` — Phase 2 adapters Phase 3 lazily constructs.
- `apps/api/backends/tests/test_adapter_contract.py` — D-19 6-invariant × 3-adapter parametric suite; Phase 3 cancellation tests mirror the task.cancel() pattern.
- `src/routing/decide.py` (`decide()` pure-function entry point) + `src/routing/schema.py` (`RoutingDecision`).
- `src/routing/tests/test_decide_smoke.py` — D-18 import-graph guard; Phase 3 MUST keep this green.
- `pyproject.toml` — current dep set; Phase 3 extends.
- `.planning/phases/03-fastapi-service-persistent-storage/03-CONTEXT.md` — 20 locked decisions (D-01..D-20).
- `.planning/phases/02-backend-adapters-chatchunk-contract/02-VERIFICATION.md` — Phase 2 closing state, all 22 truths verified.
- [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/events/) — `@asynccontextmanager` canonical pattern.
- [FastAPI CORS](https://fastapi.tiangolo.com/tutorial/cors/) — CORSMiddleware constructor signature.
- [sse-starlette GitHub](https://github.com/sysid/sse-starlette) — `EventSourceResponse(content, ping, send_timeout, ping_message_factory, shutdown_event)` constructor.
- [aiosqlite PyPI](https://pypi.org/project/aiosqlite/) + [aiosqlite docs](https://aiosqlite.omnilib.dev/en/latest/) — async context manager, single-threaded worker per connection.
- [SQLite Write-Ahead Logging](https://sqlite.org/wal.html) — WAL mode semantics.
- [SQLite ALTER TABLE](https://www.sqlite.org/lang_altertable.html) — DROP COLUMN support since 3.35.

### Secondary (MEDIUM confidence)
- [encode/httpx#2186 — ASGITransport does not stream responses](https://github.com/encode/httpx/issues/2186) — known issue, workaround via finite consume.
- [florimondmanca/httpx-sse#4 — aconnect_sse hangs on infinite generator](https://github.com/florimondmanca/httpx-sse/issues/4) — confirms break-on-done pattern is required.
- [sse-starlette client disconnection detection (DeepWiki)](https://deepwiki.com/sysid/sse-starlette/3.5-client-disconnection-detection) — _listen_for_disconnect + cancel_scope cancellation propagation.
- [PyPI fastapi](https://pypi.org/project/fastapi/) (0.136.1, May 2026) + [PyPI uvicorn](https://pypi.org/project/uvicorn/) (0.47.0, May 2026) + [PyPI sse-starlette](https://pypi.org/project/sse-starlette/) + [PyPI aiosqlite](https://pypi.org/project/aiosqlite/).
- [aiosqlite changelog](https://aiosqlite.omnilib.dev/en/latest/changelog.html) — v0.22 Thread inheritance removal.
- [Sentry: FastAPI run_in_executor vs run_in_threadpool](https://sentry.io/answers/fastapi-difference-between-run-in-executor-and-run-in-threadpool/) — equivalence with asyncio.to_thread.
- [RFC 7396 — JSON Merge Patch](https://datatracker.ietf.org/doc/html/rfc7396) — null-as-delete semantics for PATCH /settings.
- [FastAPI Body Updates](https://fastapi.tiangolo.com/tutorial/body-updates/) — `exclude_unset` PATCH pattern.

### Tertiary (LOW confidence — flagged for execute-time verification)
- [Patch httpx ASGITransport gist](https://gist.github.com/richardhundt/17dfccb5c1e253f798999fc2b2417d7e) — workaround if our finite-consume pattern fails. Last updated August 2025; LOW because we shouldn't need it (our streams are finite).
- Latest cheapest OpenRouter slug for rename endpoint (Assumption A2) — `openai/gpt-4o-mini` may or may not still be cheapest at execute time.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified at PyPI within ranges; CONTEXT locks each library.
- Architecture: HIGH — diagram derived directly from CONTEXT.md 20 locked decisions; no relitigation.
- Pitfalls: HIGH — six are direct citations from upstream docs/issues; five are derived from Phase 2 carry-forward + reading Phase 2 adapter code.
- Validation Architecture: HIGH — pytest config is already in place (Phase 1 + Phase 2 P00); only fixtures + test files are new.
- Security Domain: HIGH — Phase 2 RedactionFilter + KeyStore already cover most surface; Phase 3 adds settings PATCH + JSONL log + DB threat patterns.
- sse-starlette range Open Question: MEDIUM — A1 (API unchanged between 2.x and 3.x) is asserted but not exhaustively diffed against 2.4.1 source.

**Research date:** 2026-05-15
**Valid until:** 2026-06-15 (30 days; libraries are stable, but `openai/gpt-4o-mini` cheapness at Pattern 14 should be re-verified at execute time).
