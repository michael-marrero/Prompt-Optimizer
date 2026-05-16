# Phase 3: FastAPI Service & Persistent Storage — Pattern Map

**Mapped:** 2026-05-15
**Files analyzed:** 33 new files + 3 modifications
**Analogs found:** 24 / 33 (with strong analogs); 9 marked NEW PATTERN (cite RESEARCH.md)

## File-to-Analog Map

### Application Entry / Lifespan / Paths

| New File | Role | Closest Analog | Key Lift-Pattern | Anti-Pattern Risk |
|----------|------|----------------|------------------|-------------------|
| `apps/api/main.py` | app_main | `apps/api/__init__.py` (side-effect-at-import) + RESEARCH Pattern 9 | `pathlib.Path(__file__).resolve().parents[N]`, `create_app() -> FastAPI`, attach `CORSMiddleware`, `include_router(...)` per route module | NO wildcard CORS (OSS-05). NO `sys.path.append`. Imports must trigger `apps.api.__init__` side effects (load_dotenv + install_redaction_filter). |
| `apps/api/lifespan.py` | lifespan/startup | `apps/api/__init__.py` (idempotent import-time side effects) + RESEARCH Pattern 1 | `@asynccontextmanager`, ordered init (open DB → migrate → pragmas → artifacts → settings → KeyStore), set `app.state.adapters = {}` | NO eager adapter construction (D-15). NO duplicate `load_dotenv()` / `install_redaction_filter()` — already in `apps/api/__init__.py`. |
| `apps/api/paths.py` | paths_constants | `apps/api/__init__.py` lines 44-50 (`PROJECT_ROOT = Path(__file__).resolve().parents[2]`) + `apps/api/backends/openrouter/adapter.py` lines 83-85 (`_REPO_ROOT = Path(__file__).resolve().parents[4]`) | `USER_HOME = Path(os.environ.get("PROMPT_OPTIMIZER_HOME") or Path.home() / ".prompt-optimizer")`, derive `DB_PATH`, `BLOBS_DIR`, `SETTINGS_PATH`, `JSONL_LOG_PATH`, `WORKSPACES_DIR` | NO `os.path.join` chains for new code (use `pathlib`). NO hard-coded absolute paths. |
| `apps/api/settings.py` | settings_io | `apps/api/backends/pricing.py:from_static()` (JSON load) + `apps/api/backends/keystore.py` (env-var-aware reads) + RESEARCH Pattern 8 / Pattern 13 / Example 5 | `load_settings_file()`, `write_settings_file()` with `tmp.write_text + tmp.replace(target)` atomic pattern, `computer_use_enabled(settings)` STRICT AND-semantics | D-12 STRICT AND — env AND settings (both gates). NO single-gate fallback. |

### Routes

| New File | Role | Closest Analog | Key Lift-Pattern | Anti-Pattern Risk |
|----------|------|----------------|------------------|-------------------|
| `apps/api/routes/health.py` | route_handler | NEW PATTERN — no FastAPI routes exist yet. Cite RESEARCH Pattern 12. Closest stylistic analog: `apps/api/backends/keystore.py:get()` (read-only env+memory inspect). | `@router.get("/api/v1/healthz")`, read-only KeyStore + settings + `app.state.schema_version` lookup, never construct adapters | NO adapter construction in healthz. NO live network calls. Status literal vocabulary closed: `Literal["ready","missing_key","opt_out","error"]`. |
| `apps/api/routes/threads.py` | route_handler (CRUD) | NEW PATTERN for route shape; cite RESEARCH Pattern 8 (Pydantic models). Closest stylistic analog: `apps/api/backends/keystore.py:KeyStore.get/set` (typed in/out). | `@router.post/get/patch/delete`, Pydantic request/response models, async query function calls, `secrets.token_urlsafe(12)` ID gen | NO raw SQL in route handler — call `db/queries.py` async functions. NO key material in any response. |
| `apps/api/routes/settings.py` | route_handler | RESEARCH Pattern 8 (JSON Merge Patch with `model_dump(exclude_unset=True)`) | `KeyPatch + SettingsPatch` Pydantic v2 models with `model_config = ConfigDict(extra="forbid")`, masked response shape (`{present: bool, masked: str}`), `app.state.adapters.clear()` on success | NO plaintext keys in response. NO `print(body.keys.*)` — use `logging.getLogger(__name__)`. NO sync disk write blocking the loop. |
| `apps/api/routes/turn.py` | route_handler (streaming SSE) | `apps/api/backends/openrouter/adapter.py:stream()` lines 181-360 (canonical streaming generator + try/except CancelledError + finally cleanup) + RESEARCH Pattern 2 + Pattern 3 | `async def event_stream()` generator yielding `ServerSentEvent(event=chunk.type, data=chunk.model_dump_json())`, `await asyncio.to_thread(decide, ...)`, buffer accumulation, ONE BEGIN/COMMIT on terminal Done | NO synchronous `decide()` call (D-16). NO per-chunk DB writes (STORE-05/D-04). NO `is_disconnected()` before body parsed. NO query-param `override_backend`. |
| `apps/api/routes/rename.py` | route_handler | RESEARCH Pattern 14 + `apps/api/backends/openrouter/__main__.py` lines 53-67 (fresh adapter, accumulate `TextDelta`, break on `done`) | Fresh `OpenRouterAdapter(...)` per request (NOT cached), hardcoded `RENAME_MODEL="openai/gpt-4o-mini"`, `RENAME_MAX_COST_USD=0.01`, `max_steps=1`, tiktoken pre-flight cap, trim to ≤60 chars | NO SSE response — returns plain JSON `{"title": "..."}`. NO call into `decide()` (UI-14 explicit). NO use of cached adapter. |

### Database Layer

| New File | Role | Closest Analog | Key Lift-Pattern | Anti-Pattern Risk |
|----------|------|----------------|------------------|-------------------|
| `apps/api/db/connect.py` | db_connect | NEW PATTERN — first aiosqlite use. Cite RESEARCH Pattern 4 + Pitfall 1. Closest analog for the "module-level constant + lazy singleton" pattern: `apps/api/backends/openrouter/adapter.py` lines 82-103 (`_get_pricing_table()`). | `async def open_db(path: Path) -> aiosqlite.Connection`, `path.parent.mkdir(parents=True, exist_ok=True)`, ordered pragmas `journal_mode=WAL → synchronous=NORMAL → busy_timeout=5000 → foreign_keys=ON`, single `await db.commit()` after | `foreign_keys=ON` is REQUIRED (Pitfall 1). NO connection pool. NO per-request connection. |
| `apps/api/db/queries.py` | db_query | NEW PATTERN — first async DB module. Cite RESEARCH Pattern 3. Closest stylistic analog: `apps/api/backends/pricing.py` (typed methods returning dicts) + `apps/api/backends/keystore.py` (typed get/set). | ~10-12 `async def` functions, each takes `db: aiosqlite.Connection + typed args + returns Pydantic model`, parameterised `?` placeholders, ONE BEGIN/COMMIT for the per-turn write triple | NO f-string SQL (parameterised only). NO per-chunk writes from this module — only `persist_turn(...)` is called once. |
| `apps/api/db/migrate.py` | db_migration | NEW PATTERN. Cite RESEARCH Pattern 5 + Pitfall 3. Closest stylistic analog: `apps/api/backends/pricing.py:from_static()` (path-discovery + idempotent loader). | `async def up_to_latest(db)`, glob `schema_v*.sql`, sort by version int, single `await db.execute("BEGIN") → executescript → UPDATE schema_meta → await db.commit()` per migration | NO Alembic / yoyo. Docstring MUST flag Pitfall 3 (`executescript` implicit commit). |
| `apps/api/db/migrations/schema_v0.sql` | schema_sql | NEW PATTERN. Cite CONTEXT D-13 (canonical DDL block). | CREATE TABLE threads/messages/routing_decisions with `ON DELETE CASCADE` FKs, `CHECK (role IN ('user','assistant'))`, `CHECK (status IN (...))`, INSERT INTO schema_meta version 0 | NO cascade-without-pragma assumption — `connect.py:open_db()` enforces. NO redundant ROWID columns. |
| `apps/api/db/migrations/schema_v1.sql` | schema_sql | NEW PATTERN. Cite RESEARCH Open Question 2 — recommendation (b): `CREATE INDEX idx_messages_thread_id_created_at ON messages(thread_id, created_at)`. | One non-trivial evolution; planner picks (b) index OR (a) `pinned BOOLEAN` column on `threads` (UI-02 hook). | NO destructive DDL in v0→v1 (forward-only per CONTEXT deferred). |
| `apps/api/db/models.py` | db_model | `apps/api/backends/protocol.py:Message` + `AdapterOptions` (frozen dataclasses for read paths) and `apps/api/backends/chunks.py` (Pydantic v2 BaseModel for write paths) | Pydantic v2 `BaseModel` with `model_config = ConfigDict(frozen=True)` for `Thread`, `Message`, `RoutingDecision` read shapes; non-frozen models for inserts | NO mixing read/write shapes in one class. |
| `apps/api/blobs.py` | utility | RESEARCH Pattern 10 + Example 5 (atomic write). Closest stylistic analog: `apps/api/backends/keystore.py` (single-purpose stdlib-only module). | `INLINE_THRESHOLD_BYTES = 256 * 1024`, `_maybe_externalize_screenshot(chunk)` returns `chunk.model_copy(update={...})`, `tmp = target.parent / f"{target.name}.{secrets.token_hex(4)}.tmp"`, then `tmp.replace(target)` | NO `os.rename()` across filesystems. NO collision via shared tmp name (Pitfall 11 — unique tmp suffix). |

### Tests

| New File | Role | Closest Analog | Key Lift-Pattern | Anti-Pattern Risk |
|----------|------|----------------|------------------|-------------------|
| `apps/api/tests/conftest.py` | test_fixture | `apps/api/backends/tests/conftest.py` (canonical fixture shape) lines 1-376 | `aiosqlite_inmemory_db` fixture, `asgi_client` fixture via `httpx.AsyncClient(transport=ASGITransport(app=app))`, `app_factory(adapters_override=...)` with lazy adapter import (try/except ImportError + `pytest.skip`) | NO `TestClient` (D-20). LAZY adapter imports (see Phase 2 B3 fix in `apps/api/backends/tests/conftest.py:319-375`). |
| `apps/api/tests/fake_adapter.py` | test_fake_adapter | `apps/api/backends/tests/conftest.py:FakeOpenAIClient` lines 106-134 (constructor takes pre-built chunk list + duck-typed `.chat.completions.create`) + `FakeAnthropicStream` lines 219-245 (async iterator) | `class FakeStreamingAdapter` implements `BackendAdapter` Protocol, constructor takes `list[ChatChunk]` + optional `sleep_per_chunk` for heartbeat tests | NO real provider clients in tests. Honor terminal `Done` invariant (Pitfall 4). |
| `apps/api/tests/fixtures/schema_v0_seed.sql` | test_seed_sql | NEW PATTERN. Cite CONTEXT specifics line 346. | INSERT 1 thread + 2 messages + 1 routing_decisions row directly via SQL into a fresh v0 DB | NO references to v1 columns (would break the test). |
| `apps/api/tests/test_threads_crud.py` | test_integration | `apps/api/backends/tests/test_adapter_contract.py` lines 52-100 (parametric pytest pattern) | `@pytest.mark.parametrize`, `@pytest.mark.asyncio`, `httpx.AsyncClient(transport=ASGITransport(...))` calls, assert status codes + JSON body shape | NO `TestClient`. NO file I/O — use in-memory DB fixture. |
| `apps/api/tests/test_turn_streaming.py` | test_integration | `apps/api/backends/tests/test_adapter_contract.py` (6-invariant suite, esp. lines 103-128 cancellation pattern with `pytest.mark.timeout(2)`) + RESEARCH Pattern 6 / Pattern 7 | `async with client.stream("POST", ...) as resp`, iterate `aiter_lines()` with `break` on `event: done`, monkeypatch `sse_starlette.sse.DEFAULT_PING_INTERVAL=0.5` for heartbeat test, `task.cancel()` pattern for cancellation | NO infinite consume (Pitfall 4). NO `response.aclose()` for cancellation (Pitfall 6 — use `task.cancel()`). |
| `apps/api/tests/test_settings.py` | test_integration | `apps/api/backends/tests/test_adapter_contract.py` (parametric shape) + RESEARCH Pattern 8 | Send `{"keys": {"openrouter": "sk-or-v1-..."}}` PATCH, GET response asserts `{"present": true, "masked": "sk-…XYZ"}`, send `{"keys": {"openrouter": null}}` and assert key deleted from KeyStore | NO plaintext key in any response or log. SECURE-04 regression. |
| `apps/api/tests/test_health.py` | test_integration | `apps/api/backends/tests/test_adapter_contract.py` (parametric across backends) + RESEARCH Pattern 12 | Three sub-tests: env+key set → "ready"; env unset → "missing_key"; both set + setting off → "opt_out". `app.state.schema_version` assertion. | NO real adapter construction in healthz path. |
| `apps/api/tests/test_rename.py` | test_integration | `apps/api/backends/openrouter/tests/` pattern (test the one-shot streaming pattern via fake) + RESEARCH Pattern 14 | Inject `FakeStreamingAdapter` that emits `TextDelta("My title")` then `Done`, assert response `{"title": "My title"}`, trim test for >60 chars | NO call into `decide()`. NO use of cached adapter. |
| `apps/api/tests/test_migrations.py` | test_integration | NEW PATTERN. Cite RESEARCH Pattern 5 + CONTEXT specifics line 346. | Use `fixtures/schema_v0_seed.sql`, call `migrate.up_to_latest()`, assert `schema_meta.version == 1` AND seeded rows still present AND v1 evolution applied (index exists OR new column present with default) | NO assumption that `executescript` is atomic (Pitfall 3 — explicit BEGIN/COMMIT). |
| `apps/api/tests/test_secure_no_key_in_logs.py` | test_integration | `apps/api/backends/tests/test_logging_filter.py` (existing redaction filter regression pattern) | PATCH `/api/v1/settings` with realistic `sk-or-v1-XXXX...` key, capture logs with `caplog`, assert `"sk-or-v1" not in caplog.text` | NO raw key in any log line. Phase 2 redaction filter must apply. |
| `apps/api/tests/test_cors.py` | test_unit | NEW PATTERN. Cite RESEARCH Pattern 9 (`CORSMiddleware` config). | OPTIONS preflight from `http://localhost:3000` → 200; OPTIONS from `http://evil.example` → CORS reject; env override `PROMPT_OPTIMIZER_CORS_ORIGINS=...` honored | NO `allow_origins=["*"]` fallback when env unset. |
| `apps/api/tests/test_blobs_by_hash.py` | test_unit | NEW PATTERN. Cite RESEARCH Pattern 10 + Pitfall 11. | Pass 300 KB fake image → `image_b64=None + image_ref=<path>` written; pass 100 KB → `image_b64` preserved; concurrent identical content races safely | NO hash collisions undetected. NO race on shared tmp name. |

### Configuration & Distribution

| Modified File | Role | Closest Analog | Key Lift-Pattern | Anti-Pattern Risk |
|---------------|------|----------------|------------------|-------------------|
| `pyproject.toml` | pyproject_change | `pyproject.toml` lines 8-26 (existing `dependencies` array) + lines 28-35 (`[project.optional-dependencies]`) + lines 47-58 (`[tool.pytest.ini_options]`) | Append `"fastapi>=0.115,<1.0"`, `"uvicorn[standard]>=0.30,<1.0"`, `"sse-starlette>=2.1,<4.0"` (RESEARCH Open Question 1 widens upper bound), `"aiosqlite>=0.20,<1.0"`. Add `"httpx-sse>=0.4,<1.0"` to `[project.optional-dependencies].dev`. | NO new test framework. NO version pin without upper bound. `packages = ["src", "apps"]` already covers Phase 3. |
| `.env.example` | dotenv_config | NEW FILE — no `.env.example` exists. Cite CONTEXT canonical refs line 257. | Enumerate `OPENROUTER_API_KEY=`, `ANTHROPIC_API_KEY=`, `COMPUTER_USE_OPT_IN=0`, `PROMPT_OPTIMIZER_HOME=` (optional), `PROMPT_OPTIMIZER_CORS_ORIGINS=` (optional). Comment headers describe each. | NO real key values. NO leaving env vars undocumented. |
| `.gitignore` | gitignore_entry | Existing `.gitignore` lines 22-26 (chat.db patterns already present) | Add `.planning/data/` (verify Phase 1 SECURE-03 coverage). `chat.db`-pattern entries already exist. | NO un-gitignored `.planning/data/routing_decisions.jsonl`. |
| `apps/api/routes/__init__.py` | (package marker) | `apps/api/backends/__init__.py` lines 1-15 (docstring + minimal exports) | One-line docstring; no exports (routers are imported by `main.py`). | — |
| `apps/api/db/__init__.py` | (package marker) | `apps/api/backends/__init__.py` | One-line docstring. | — |
| `apps/api/tests/__init__.py` | (package marker) | `apps/api/backends/tests/__init__.py` (59 bytes — minimal) | Minimal package marker. | — |

## Carry-Forward Import Inventory

Phase 3 modules MUST use these imports verbatim. The `from apps.api.*` and `from src.routing.*` paths are the public contract.

### From Phase 1 (`src/routing/`)

```python
from src.routing.decide import decide
from src.routing.schema import RoutingDecision, Backend
# Optional / advanced:
from src.routing.config import FALLBACK_MODEL_OR_AGENT
```

### From Phase 2 (`apps/api/backends/`)

```python
# Adapter contracts
from apps.api.backends.protocol import (
    BackendAdapter,
    AdapterOptions,
    Message as AdapterMessage,
)
from apps.api.backends.chunks import (
    ChatChunk,
    chat_chunk_adapter,
    TextDelta,
    ToolCall,
    ToolResult,
    FileDiff,
    Screenshot,
    StreamError,
    Done,
)

# Concrete adapters — imported lazily inside _get_or_create_adapter
from apps.api.backends.openrouter import OpenRouterAdapter
from apps.api.backends.claude_code import ClaudeCodeAdapter
from apps.api.backends.computer_use import ComputerUseAdapter

# Auxiliary
from apps.api.backends.keystore import KeyStore
from apps.api.backends.cost import DEFAULT_PER_TURN_COST_USD
from apps.api.backends.pricing import PricingTable
# NOTE: apps.api.backends.logging_filter is consumed indirectly via
# apps.api.__init__'s install_redaction_filter() side effect at import.
# Phase 3 NEVER re-imports it.
```

### Auto-applied side effects (NEVER duplicate)

When ANY module imports from `apps.api.*`, `apps/api/__init__.py` runs:
1. `dotenv.load_dotenv()` — populates `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `COMPUTER_USE_OPT_IN`, `PROMPT_OPTIMIZER_HOME`, `PROMPT_OPTIMIZER_CORS_ORIGINS` from `./.env`.
2. `install_redaction_filter()` — installs `RedactionFilter` + record factory on the root logger; idempotent.

Phase 3 modules MUST NOT call either function themselves.

## Code Excerpts

### Excerpt 1 — Path discovery (`apps/api/paths.py` lift-source)

From `apps/api/__init__.py` lines 44-50:

```python
# Path discovery — apps/api/__init__.py is two levels below the repo
# root, so ``parents[1]`` lands at ``<repo>/apps`` and ``parents[2]``
# at the repo root itself. We use ``parents[2]`` so downstream code
# referring to ``PROJECT_ROOT`` matches the layout the Phase 1
# ``src/routing/config.py`` uses.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
CONFIG_DIR: Path = PROJECT_ROOT / "config"
```

**Phase 3 adaptation** for `apps/api/paths.py` (apps/api/paths.py is also two levels below repo root → `parents[2]`):

```python
from pathlib import Path
import os

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
USER_HOME: Path = Path(
    os.environ.get("PROMPT_OPTIMIZER_HOME")
    or (Path.home() / ".prompt-optimizer")
)
DB_PATH: Path = USER_HOME / "chat.db"
BLOBS_DIR: Path = USER_HOME / "blobs"
SETTINGS_PATH: Path = USER_HOME / "settings.json"
WORKSPACES_DIR: Path = USER_HOME / "workspaces"
JSONL_LOG_PATH: Path = PROJECT_ROOT / ".planning" / "data" / "routing_decisions.jsonl"
```

### Excerpt 2 — Streaming generator + cancellation + finally cleanup (`routes/turn.py` lift-source)

From `apps/api/backends/openrouter/adapter.py` lines 181-360 — the canonical streaming pattern Phase 3's SSE generator should mirror:

```python
async def stream(self, prompt, history, options) -> AsyncIterator[ChatChunk]:
    in_flight = None
    start_t = asyncio.get_event_loop().time()
    try:
        in_flight = await self._client.chat.completions.create(
            model=model_id,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in in_flight:
            # ... emit TextDelta / ToolCall / etc.
            if tracker.over_cap():
                yield StreamError(code="cost_cap_exceeded", ...)
                break
        yield Done(tokens_in=..., tokens_out=..., cost_usd=..., ...)

    except asyncio.CancelledError:
        # Pattern 7: emit terminal pair, then re-raise (PEP 789).
        yield StreamError(code="cancelled", message="Stream cancelled by caller.", retriable=True)
        yield Done(...)
        raise

    except AuthenticationError as exc:
        yield StreamError(code="auth_failed", message=str(exc), retriable=False)
        yield Done(routing_signals=options.routing_signals)
    # ... other typed exception branches ...
    except Exception as exc:  # noqa: BLE001 — V7 robustness wrapper.
        logger.exception("OpenRouter adapter internal error")
        yield StreamError(code="internal_error", ...)
        yield Done(routing_signals=options.routing_signals)

    finally:
        if in_flight is not None:
            try:
                await in_flight.close()
            except Exception:
                pass
```

**Phase 3 adaptation** for `routes/turn.py:event_stream()` — wraps the adapter's stream and persists on terminal Done:

```python
async def event_stream():
    buffer: list[ChatChunk] = []
    try:
        async for chunk in adapter.stream(body.message, history, options):
            # STORE-04 transcode BEFORE buffer + yield
            if isinstance(chunk, Screenshot):
                chunk = _maybe_externalize_screenshot(chunk)
            buffer.append(chunk)
            yield ServerSentEvent(
                event=chunk.type,
                data=chunk.model_dump_json(),
            )
            if isinstance(chunk, Done):
                break
            # Pitfall 6: only useful under real network; under
            # ASGITransport CancelledError propagates via task.cancel().
            if await request.is_disconnected():
                break
    finally:
        # STORE-05 + D-04: ONE transaction on Done
        if buffer and isinstance(buffer[-1], Done):
            await persist_turn(db, thread_id, body.message, buffer, decision)
```

### Excerpt 3 — Pydantic v2 frozen models for DB read paths (`db/models.py` lift-source)

From `apps/api/backends/protocol.py` lines 40-69 — frozen dataclass for immutable value objects (write-path analogue):

```python
@dataclass(frozen=True)
class Message:
    role: str
    content: str

@dataclass(frozen=True)
class AdapterOptions:
    model: str | None = None
    max_cost_usd: float | None = None
    max_steps: int | None = None
    cwd: str | None = None
    routing_signals: dict[str, Any] | None = None
```

From `apps/api/backends/chunks.py` lines 49-157 — Pydantic v2 BaseModel for serializable shapes:

```python
class TextDelta(BaseModel):
    type: Literal["text_delta"] = "text_delta"
    text: str

class Done(BaseModel):
    type: Literal["done"] = "done"
    tokens_in: int | None = None
    tokens_out: int | None = None
    # ...
```

**Phase 3 adaptation** for `apps/api/db/models.py`:

```python
from pydantic import BaseModel, ConfigDict
from typing import Literal

class Thread(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    title: str
    created_at: str   # ISO 8601 UTC
    updated_at: str

class Message(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    thread_id: str
    role: Literal["user", "assistant"]
    content_blocks: str   # JSON
    text: str
    backend_used: str | None = None
    model_used: str | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    created_at: str
    status: Literal["complete", "error", "cancelled"] = "complete"
```

### Excerpt 4 — Closed-vocabulary `Literal[...]` (health.py status, settings.py keys)

From `apps/api/backends/protocol.py` line 37 (Phase 1 `Backend` sentinel set):

```python
Backend = Literal["openrouter", "claude_code", "computer_use"]
```

From `apps/api/backends/chunks.py` lines 127-137 (Phase 2 closed error vocabulary):

```python
code: Literal[
    "cost_cap_exceeded",
    "step_cap_exceeded",
    "cancelled",
    "rate_limited",
    "auth_failed",
    "provider_unavailable",
    "timeout",
    "validation_error",
    "internal_error",
]
```

**Phase 3 adaptation** for `routes/health.py` (D-18 healthz adapter status):

```python
AdapterStatus = Literal["ready", "missing_key", "opt_out", "error"]
```

### Excerpt 5 — Module-import-time side effects (NEVER duplicate)

From `apps/api/__init__.py` lines 35-59:

```python
from __future__ import annotations
from pathlib import Path
from dotenv import load_dotenv
from apps.api.backends.logging_filter import install_redaction_filter

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
CONFIG_DIR: Path = PROJECT_ROOT / "config"

# Side effect #1
load_dotenv()
# Side effect #2 (idempotent)
install_redaction_filter()
```

**Phase 3 contract:** `apps/api/main.py` and every Phase 3 module imports from `apps.api.*` — this auto-triggers BOTH side effects exactly once. **Phase 3 modules MUST NOT call `load_dotenv()` or `install_redaction_filter()` themselves.**

### Excerpt 6 — D-19 parametric test pattern (`tests/test_threads_crud.py` lift-source)

From `apps/api/backends/tests/test_adapter_contract.py` lines 45-128 (parametrize + asyncio + timeout pattern):

```python
import pytest

ADAPTER_PARAMS = [
    pytest.param("openrouter", id="openrouter"),
    pytest.param("claude_code", id="claude_code"),
    pytest.param("computer_use", id="computer_use"),
]

@pytest.mark.parametrize("backend", ADAPTER_PARAMS)
@pytest.mark.asyncio
async def test_happy_path_terminates_with_done(adapter_factory, backend):
    adapter = adapter_factory(backend)
    chunks = []
    async for chunk in adapter.stream(
        prompt="hello", history=[], options=AdapterOptions()
    ):
        chunks.append(chunk)
    assert chunks, "no chunks emitted"
    assert any(isinstance(c, TextDelta) for c in chunks), "no TextDelta"
    assert isinstance(chunks[-1], Done), (
        f"last chunk is {type(chunks[-1])}, expected Done"
    )

@pytest.mark.parametrize("backend", ADAPTER_PARAMS)
@pytest.mark.asyncio
@pytest.mark.timeout(2)
async def test_cancellation_within_2_seconds(adapter_factory, backend):
    adapter = adapter_factory(backend)
    chunks: list = []
    async def consume() -> None:
        async for chunk in adapter.stream(...):
            chunks.append(chunk)
    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    if chunks:
        assert isinstance(chunks[-1], Done)
```

**Phase 3 adaptation** for `tests/test_turn_streaming.py` — same parametrize + timeout pattern, but via `httpx.AsyncClient + ASGITransport` instead of direct adapter calls.

### Excerpt 7 — Lazy adapter import inside fixture (`tests/conftest.py` lift-source)

From `apps/api/backends/tests/conftest.py` lines 319-375 — the B3 fix: imports MUST be lazy inside the factory so the conftest is collectable before route modules exist:

```python
@pytest.fixture
def adapter_factory(request, fake_openai, ...):
    def factory(backend: str, *, max_cost_usd: float = 0.50, ...) -> object:
        if backend == "openrouter":
            try:
                from apps.api.backends.openrouter.adapter import OpenRouterAdapter
            except ImportError:
                pytest.skip("openrouter adapter not yet implemented")
            return OpenRouterAdapter(...)
        # ... claude_code, computer_use branches ...
    return factory
```

**Phase 3 application:** `apps/api/tests/conftest.py`'s `app_factory` fixture lazy-imports `apps.api.main:create_app` and `apps.api.routes.*` inside the factory so Wave 0 (pyproject + conftest landing first) doesn't fail at collection time before Wave 1-5 modules exist.

### Excerpt 8 — Idempotent install + opt-in gate (settings.py `computer_use_enabled` lift-source)

From `apps/api/backends/computer_use/adapter.py` lines 210-223 — the Phase 2 single-gate check Phase 3 extends:

```python
if os.environ.get("COMPUTER_USE_OPT_IN") != "1":
    raise RuntimeError(
        "computer-use is OFF — set COMPUTER_USE_OPT_IN=1 to enable. "
        "This gates browser automation behind an explicit opt-in to "
        "prevent accidental enable of an agent that can navigate the "
        "open web."
    )
```

**Phase 3 D-12 STRICT AND extension** in `apps/api/settings.py`:

```python
import os

def computer_use_enabled(settings: dict) -> bool:
    """STRICT AND-semantics per D-12. BOTH env AND settings required."""
    env_ok = os.environ.get("COMPUTER_USE_OPT_IN") == "1"
    setting_ok = bool(settings.get("computer_use_opt_in"))
    return env_ok and setting_ok
```

The adapter's existing single-gate check stays — Phase 3 adds a SECOND gate in `routes/turn.py:_get_or_create_adapter()` that consults `computer_use_enabled(app.state.settings)` BEFORE constructing the `ComputerUseAdapter`. The Phase 2 test suite is unchanged; new Phase 3 tests cover the AND semantics.

### Excerpt 9 — Defensive cleanup in `finally` (lifespan teardown lift-source)

From `apps/api/backends/openrouter/adapter.py` lines 352-360 (defensive close that tolerates already-closed):

```python
finally:
    if in_flight is not None:
        try:
            await in_flight.close()
        except Exception:
            # Closing an already-closed httpx stream raises; the
            # cancellation contract only needs the close to be
            # attempted, not to succeed.
            pass
```

**Phase 3 adaptation** for `apps/api/lifespan.py`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = await open_db(DB_PATH)
    await up_to_latest(app.state.db)
    app.state.artifacts = _load_default_artifacts()
    app.state.settings = load_settings_file()
    app.state.keystore = KeyStore(use_keyring=False)
    app.state.adapters = {}
    # Cache schema version once (Open Question 5)
    app.state.schema_version = await _read_schema_version(app.state.db)
    try:
        yield
    finally:
        try:
            await app.state.db.close()
        except Exception:
            pass
```

### Excerpt 10 — One-shot adapter consume (rename.py lift-source)

From `apps/api/backends/openrouter/__main__.py` lines 53-67 — the canonical "consume an adapter once, print JSON lines, stop" pattern:

```python
adapter = OpenRouterAdapter(api_key=api_key, max_cost_usd=max_cost_usd)
options = AdapterOptions(model=model, max_cost_usd=max_cost_usd, max_steps=max_steps)
async for chunk in adapter.stream(
    prompt=prompt,
    history=[],
    options=options,
):
    print(chunk.model_dump_json(), flush=True)
return 0
```

**Phase 3 adaptation** for `routes/rename.py` — same shape, but collect `TextDelta.text` instead of printing, break on `Done`:

```python
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

## Anti-Pattern Audit

The planner MUST surface each anti-pattern as an explicit "DO NOT" in the relevant plan(s). Source-of-record in parentheses.

- **NO `sys.path.append`.** Use `from apps.api.*` and `from src.routing.*` via the hatchling wheel only. (CONTEXT anti-pattern block / Phase 2 D-08 / CLAUDE.md `## Architectural Constraints`.) Applies to: `main.py`, `lifespan.py`, `paths.py`, every route, every test.
- **NO `fastapi` / `httpx` / `sse-starlette` / `aiosqlite` imports inside `src/routing/`.** D-18 import-graph guard test is live in `src/routing/tests/test_decide_smoke.py`. Direction is one-way: `apps.api → src.routing`. (CONTEXT anti-pattern block / Phase 1 D-18 / RESEARCH §"Project Constraints".)
- **NO `from fastapi.testclient import TestClient`.** Negative grep enforced by CI: `! grep -rE 'from fastapi.testclient|fastapi\.testclient\.TestClient' apps/api/tests/`. Use `httpx.AsyncClient(transport=ASGITransport(app=app))` only. (API-08 / D-20 / RESEARCH Pattern 6.) Applies to: every test under `apps/api/tests/`.
- **NO per-chunk SQLite writes.** Buffer in memory, ONE BEGIN/COMMIT on terminal `Done`. (STORE-05 / D-04 / RESEARCH Pattern 3.) Applies to: `routes/turn.py:event_stream()`.
- **NO synchronous `decide()` call from an async handler.** Always wrap with `await asyncio.to_thread(decide, ...)`. (API-07 / D-16 / RESEARCH "Anti-Patterns to Avoid".) Applies to: `routes/turn.py`. Phase 3 also updates REQUIREMENTS.md API-07 wording (per D-16) to match.
- **NO raw key material in any log line or response body.** Use `logging.getLogger(__name__)` so the Phase 2 `RedactionFilter` applies. Never `print(body.keys.*)`. GET `/settings` returns `{present: bool, masked: str}` only. (SECURE-04 / D-10 / D-11 / D-19.) Applies to: `routes/settings.py`, `tests/test_secure_no_key_in_logs.py`.
- **NO `allow_origins=["*"]` and NO silent wildcard fallback.** Default to `["http://localhost:3000"]` when `PROMPT_OPTIMIZER_CORS_ORIGINS` is unset. Strip whitespace; honor comma-separated list. (OSS-05 / RESEARCH Pattern 9.) Applies to: `main.py:create_app()`.
- **NO eager adapter construction at lifespan startup.** `app.state.adapters = {}`. First turn that resolves to a backend instantiates lazily via `_get_or_create_adapter`. Server boots even when `ANTHROPIC_API_KEY` or `COMPUTER_USE_OPT_IN` are unset. (D-15 / RESEARCH Pattern 1.) Applies to: `lifespan.py`, `routes/turn.py`.
- **NO env-only computer-use gate.** Phase 3 STRICT AND-semantics: `os.environ["COMPUTER_USE_OPT_IN"] == "1"` AND `settings["computer_use_opt_in"] is True`. UI toggle alone is not enough; env alone is not enough. (D-12 / RESEARCH Pattern 13.) Applies to: `apps/api/settings.py:computer_use_enabled`, `routes/turn.py` (pre-construction gate), `routes/health.py` (status detection).
- **NO query-param `override_backend` on SSE.** Use the body field only (per CONTEXT deferred line 370 — intermediate proxies cache query params on text/event-stream responses in unexpected ways). (CONTEXT deferred / RESEARCH Pattern 11.) Applies to: `routes/turn.py` request model.
- **NO `os.path.join` chains in new modules.** Use `pathlib.Path(__file__).resolve().parents[N]` (CLAUDE.md `## Conventions / Import Organization` + Phase 2 carry-forward). Applies to: every new module. The Phase 1 `src/routing/` legacy `os.path.join` stays.
- **NO duplicate `dotenv.load_dotenv()` or `install_redaction_filter()` calls.** These run once at `apps/api/__init__.py` import. Phase 3 modules MUST NOT call them. (CONTEXT canonical refs line 233 / Phase 2 D-11.)
- **NO infinite SSE consume in tests.** Always `break` on `event: done`. Apply `@pytest.mark.timeout(5)` belt-and-suspenders. (RESEARCH Pitfall 4 — `httpx.ASGITransport.stream()` hangs on infinite generators.)
- **NO `response.aclose()` for cancellation tests.** Use `task.cancel()` because `ASGITransport` does NOT inject `http.disconnect` on consumer-side close. (RESEARCH Pitfall 6.) Applies to: `tests/test_turn_streaming.py::test_cancellation_within_2_seconds`.
- **NO shared tmp suffix for blob writes.** Use unique per-write tmp: `tmp = target.parent / f"{target.name}.{secrets.token_hex(4)}.tmp"`. (RESEARCH Pitfall 11 / Pattern 10.) Applies to: `apps/api/blobs.py`.
- **NO destructive DDL in v0→v1.** Forward-only migrations. (CONTEXT deferred line 369.)
- **NO f-string SQL.** Always parameterised `?` placeholders. (RESEARCH §Security Domain.) Applies to: `apps/api/db/queries.py`.

## Pattern Coverage Summary

Per file: every new/modified file from CONTEXT §"### New Files Phase 3 Creates" has a mapped analog OR an explicit "NEW PATTERN — cite RESEARCH.md §X" justification.

| Coverage Class | Count | Files |
|----------------|-------|-------|
| **Exact analog (Phase 2 file, same role + flow)** | 6 | `lifespan.py` ← `__init__.py`; `paths.py` ← `__init__.py` + `openrouter/adapter.py`; `db/models.py` ← `protocol.py` + `chunks.py`; `tests/conftest.py` ← `backends/tests/conftest.py`; `tests/fake_adapter.py` ← `FakeOpenAIClient`; `tests/test_*.py` ← `test_adapter_contract.py` |
| **Role-match analog (Phase 2 file, same role; different flow)** | 6 | `routes/turn.py` ← `openrouter/adapter.py` (streaming generator); `routes/rename.py` ← `openrouter/__main__.py` (one-shot consume); `routes/settings.py` ← `keystore.py` + RESEARCH Pattern 8; `apps/api/settings.py` ← `pricing.py` + `keystore.py`; `apps/api/blobs.py` ← `keystore.py` (stdlib-only utility); `pyproject.toml` ← existing array shape |
| **Stylistic / convention analog only (new functional domain, but old style)** | 5 | `routes/health.py` ← `keystore.py` (read-only inspect); `routes/threads.py` ← `keystore.py` get/set shape; `db/queries.py` ← `pricing.py` + `keystore.py`; `db/connect.py` ← lazy-singleton from `openrouter/adapter.py`; `db/migrate.py` ← `pricing.py:from_static()` path-discovery |
| **NEW PATTERN — no analog; cited RESEARCH §** | 9 | `db/migrations/schema_v0.sql` (CONTEXT D-13); `db/migrations/schema_v1.sql` (RESEARCH Open Question 2); `tests/fixtures/schema_v0_seed.sql` (CONTEXT specifics 346); `tests/test_migrations.py` (RESEARCH Pattern 5); `tests/test_blobs_by_hash.py` (RESEARCH Pattern 10); `tests/test_cors.py` (RESEARCH Pattern 9); `.env.example` (CONTEXT canonical refs 257); `routes/__init__.py` (Phase 2 minimal package marker); `db/__init__.py` (Phase 2 minimal package marker) |

**Total mapped:** 17 of 26 distinct content files have a concrete Phase 2 analog. 9 are justified as NEW PATTERN with explicit RESEARCH.md citations. Package-marker `__init__.py` files reuse the `apps/api/backends/__init__.py` 1-2 line docstring shape.

Every file the planner adds traces to (a) a concrete Phase 2 code excerpt that can be lifted directly, OR (b) a RESEARCH.md pattern with section number. No file is left without a pattern map.

---

**Metadata**

- **Analog search scope:** `apps/api/` (Phase 2), `src/routing/` (Phase 1, READ-only via the import-graph guard), `pyproject.toml`, `.gitignore`, project root.
- **Files scanned:** ~30 (full read of `apps/api/__init__.py`, `apps/api/backends/{chunks,protocol,cost,keystore,pricing,logging_filter}.py`, `apps/api/backends/openrouter/{__init__,__main__,adapter}.py`, `apps/api/backends/claude_code/adapter.py` (first 120 lines), `apps/api/backends/computer_use/adapter.py` (first 80 + opt-in block), `apps/api/backends/tests/{conftest,test_adapter_contract}.py`, `src/routing/{schema,decide}.py`, `src/demo/demo_router.py` (first 100 lines), `pyproject.toml`, `.gitignore`). Targeted reads of `.planning/phases/03-fastapi-service-persistent-storage/03-CONTEXT.md` (full) and `03-RESEARCH.md` (lines 1-400, 400-800, 800-1200).
- **Pattern extraction date:** 2026-05-15
