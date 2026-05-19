# Phase 4: Minimal Chat UI (OpenRouter Backend) - Pattern Map

**Mapped:** 2026-05-18
**Files analyzed:** ~55 (create) + 3 (modify)
**Analogs found in repo:** 9 (direct/role match) / ~58
**External canonical references:** 11 (where no in-repo analog exists)

> **Greenfield scaffold notice.** Phase 4 introduces the first JavaScript/TypeScript surface in the repo. There is no existing `apps/web/`, no `package.json`, no `tsconfig`, no React component. Every TS/TSX file is genuinely net-new. The in-repo analogs that DO exist are exclusively on the Python side: the FastAPI routes (`apps/api/routes/*.py`) — those map to the new Next.js route handlers conceptually (same wire contract, mirror in TS), and the existing pytest tests (`apps/api/tests/*.py`) — those map to the Vitest/Playwright tests in shape. For files with NO in-repo analog, the `external_pattern` column points to a specific RESEARCH.md Pattern section (which itself cites canonical assistant-ui / AI SDK examples).
>
> **The single MODIFY** in this phase is `apps/api/routes/turn.py` (D-15 — emit `routing_decision` SSE event before adapter dispatch). The analog is the file itself; the executor reads the existing `event_stream()` generator (lines 452-590) and injects ONE additional `yield ServerSentEvent(event="routing_decision", data=json.dumps(decision.signals))` between line 446 (`options = AdapterOptions(...)`) and the existing `async for chunk in adapter.stream(...)` loop. No new function shapes; no new imports beyond `json` (already imported by transitive uses).

---

## File Classification

### Wave 0 — Workspace scaffolding (greenfield)

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `apps/web/package.json` | config | n/a | `pyproject.toml` (root) | partial — both are dependency manifests, different ecosystems |
| `apps/web/tsconfig.json` | config | n/a | none in repo | none — net-new TS toolchain |
| `apps/web/next.config.ts` | config | n/a | none | none — Next.js never existed |
| `apps/web/tailwind.config.ts` | config | n/a | none | none — Tailwind v4 prefers CSS-first, may be near-empty |
| `apps/web/postcss.config.mjs` | config | n/a | none | none |
| `apps/web/components.json` | config | n/a | `config/model_mapping.json` | partial — both are flat JSON config |
| `apps/web/.env.example` | config | n/a | repo-root `.env` (not committed) | partial — env-var pattern |
| `apps/web/.gitignore` (or root `.gitignore` additions) | config | n/a | root `.gitignore` | exact — append-only mode |
| `pnpm-workspace.yaml` (root, optional per D-01) | config | n/a | none | none — D-01 says "no workspace yet" |
| `apps/web/app/layout.tsx` | layout (server component) | request-response | none | none — root layout is React 19 server component idiom |
| `apps/web/app/page.tsx` | page (client component) | request-response + state | none | none — `"use client"` chat surface |
| `apps/web/app/globals.css` | stylesheet | n/a | none | none |

### Wave 0 — CI / build

| File | Role | Data Flow | Mode | Analog | Match Quality |
|------|------|-----------|------|--------|---------------|
| `.github/workflows/web-test.yml` | CI config | batch | CREATE | `.github/workflows/ci.yml` | role-match — same GitHub Actions shape, different tooling (pnpm vs uv) |

### Wave 0 — Test framework setup

| File | Role | Data Flow | Mode | Analog | Match Quality |
|------|------|-----------|------|--------|---------------|
| `apps/web/vitest.config.ts` | test-config | n/a | CREATE | `pyproject.toml` `[tool.pytest.ini_options]` | partial — both declare test framework config |
| `apps/web/playwright/playwright.config.ts` | test-config | n/a | CREATE | none | none — multi-server `webServer` config is Playwright-specific |
| `apps/web/tests/setup.ts` | test-config | n/a | CREATE | `apps/api/tests/conftest.py` | partial — both run before each test |

### Wave 1 — Library code (pure functions, types, schemas)

| File | Role | Data Flow | Mode | Analog | Match Quality |
|------|------|-----------|------|--------|---------------|
| `apps/web/lib/sse-translate.ts` | utility (pure function) | streaming/transform | CREATE | `apps/api/backends/chunks.py` (closed-vocabulary union) | role-match — both define wire-format contract |
| `apps/web/lib/chunk-schemas.ts` | utility (zod schemas) | validation | CREATE | `apps/api/routes/settings.py:KeyPatch`/`SettingsPatch` Pydantic models | role-match — Zod is to TS what Pydantic v2 is to Python |
| `apps/web/lib/api-client.ts` | service | request-response | CREATE | none in repo (Python side never had to call its own API client) | none — closest external is fetch-wrapper idiom |
| `apps/web/lib/types.ts` | utility (type defs) | n/a | CREATE | `src/routing/schema.py` (`RoutingDecision` dataclass) | role-match — same shape, TS interfaces |
| `apps/web/lib/thread-id.ts` | utility | request-response + state | CREATE | none | none — localStorage idiom is browser-only |
| `apps/web/lib/markdown-components.tsx` | utility (component map) | n/a | CREATE | none | none — assistant-ui-react-markdown component-map pattern |
| `apps/web/lib/cn.ts` | utility | n/a | CREATE | none | none — shadcn convention; one-liner clsx+tailwind-merge wrapper |

### Wave 1-2 — Next.js route handlers (server-side proxies)

| File | Role | Data Flow | Mode | Analog | Match Quality |
|------|------|-----------|------|--------|---------------|
| `apps/web/app/api/chat/route.ts` | route handler (proxy) | streaming SSE | CREATE | `apps/api/routes/turn.py` | role-match — the wire contract this proxies INTO. Mirror its named-event vocabulary in the inverse direction (read named events → emit AI SDK v6 chunks). |
| `apps/web/app/api/threads/route.ts` | route handler (proxy) | request-response (CRUD) | CREATE | `apps/api/routes/threads.py:post_thread` | role-match — POST creates, returns the thread; Next side wraps it |
| `apps/web/app/api/threads/[id]/route.ts` | route handler (proxy) | request-response | CREATE | `apps/api/routes/threads.py:get_single_thread` | role-match — GET passthrough with 404 propagation |
| `apps/web/app/api/settings/route.ts` | route handler (proxy) | request-response + write | CREATE | `apps/api/routes/settings.py:patch_settings` | role-match — POST `{provider,key}` translates to upstream PATCH `{keys:{provider:key}}` |
| `apps/web/app/api/health/route.ts` | route handler (proxy) | request-response | CREATE | `apps/api/routes/health.py:healthz` | role-match — pure passthrough; UI consumer is the only difference |

### Wave 2 — Hooks / state

| File | Role | Data Flow | Mode | Analog | Match Quality |
|------|------|-----------|------|--------|---------------|
| `apps/web/hooks/useChatThread.ts` | hook | event-driven | CREATE | none | none — wraps `useChat` from `@ai-sdk/react` |
| `apps/web/hooks/useFirstRunGate.ts` | hook | request-response + state | CREATE | none | none — boot-time `/api/health` poll |

### Waves 2-4 — Components (React)

| File | Role | Data Flow | Mode | Analog | Match Quality |
|------|------|-----------|------|--------|---------------|
| `apps/web/components/RoutingChip.tsx` | component | event-driven (subscribes to message part) | CREATE | none | none — pure React + assistant-ui hook |
| `apps/web/components/MetricsFooter.tsx` | component | event-driven | CREATE | none | none |
| `apps/web/components/ChatBubble.tsx` | component | event-driven + state (hover) | CREATE | none | none |
| `apps/web/components/StreamErrorBanner.tsx` | component | event-driven | CREATE | none | none |
| `apps/web/components/NetworkDownBanner.tsx` | component | state (5s poll) | CREATE | none | none |
| `apps/web/components/EmptyState.tsx` | component | n/a (static) | CREATE | none | none |
| `apps/web/components/FirstRunModal.tsx` | component | request-response (form submit) | CREATE | none | none — shadcn Dialog pattern |
| `apps/web/components/KeyForm.tsx` | component | request-response | CREATE | none | none — shared between modal + /settings |
| `apps/web/app/settings/page.tsx` | page (client component) | request-response | CREATE | none | none — wraps KeyForm in non-blocking mode |
| `apps/web/components/ui/button.tsx` | component (shadcn-installed) | n/a | CREATE (via `shadcn add`) | n/a | n/a — generated by `pnpm dlx shadcn@latest add button` |
| `apps/web/components/ui/dialog.tsx` | component (shadcn-installed) | n/a | CREATE (via `shadcn add`) | n/a | n/a |
| `apps/web/components/ui/input.tsx` | component (shadcn-installed) | n/a | CREATE (via `shadcn add`) | n/a | n/a |
| `apps/web/components/ui/sonner.tsx` | component (shadcn-installed) | n/a | CREATE (via `shadcn add`) | n/a | n/a |

### Waves 1-6 — Tests

| File | Role | Data Flow | Mode | Analog | Match Quality |
|------|------|-----------|------|--------|---------------|
| `apps/web/tests/sse-translate.test.ts` | test (Vitest unit) | n/a | CREATE | `apps/api/tests/test_turn_streaming.py:test_streams_chatchunks` | role-match — both assert SSE event order |
| `apps/web/tests/chunk-schemas.test.ts` | test (Vitest unit) | n/a | CREATE | `apps/api/tests/test_settings.py` (validates Pydantic body) | role-match — schema validation tests |
| `apps/web/tests/routing-chip.test.tsx` | test (RTL component) | n/a | CREATE | none | none — first React component test in repo |
| `apps/web/tests/metrics-footer.test.tsx` | test (RTL component) | n/a | CREATE | none | none |
| `apps/web/playwright/no-flicker.spec.ts` | test (E2E) | n/a | CREATE | none | none — first E2E test in repo |
| `apps/web/playwright/cancel-budget.spec.ts` | test (E2E) | n/a | CREATE | `apps/api/tests/test_turn_streaming.py:test_cancellation_within_2s` | partial — same 2s budget invariant on a different layer (browser vs upstream) |
| `apps/web/playwright/first-run.spec.ts` | test (E2E) | n/a | CREATE | none | none |
| `apps/web/playwright/secure-key.spec.ts` | test (E2E) | n/a | CREATE | `apps/api/tests/test_secure_no_key_in_logs.py` | role-match — same disclosure-regression invariant, different surface (browser + Next logs vs FastAPI logs) |
| `apps/web/playwright/browser-isolation.spec.ts` | test (E2E) | n/a | CREATE | none | none |
| `apps/web/playwright/routing-chip.spec.ts` | test (E2E) | n/a | CREATE | none | none |

### Phase 3 amendment — MODIFY existing files

| File | Role | Data Flow | Mode | Analog | Match Quality |
|------|------|-----------|------|--------|---------------|
| `apps/api/routes/turn.py` | route handler | streaming SSE | **MODIFY** | itself | exact — D-15 adds ONE `yield ServerSentEvent(event="routing_decision", ...)` between `decide()` and `adapter.stream()` |
| `apps/api/backends/chunks.py` | schema | n/a | **DO NOT MODIFY** | n/a | n/a — D-15 explicit: "Does NOT modify the Phase 2 ChatChunk Pydantic union" |
| `apps/api/tests/test_turn_streaming.py` | test | n/a | **MODIFY (add test)** | itself | exact — append a new test case asserting `routing_decision` event arrives first and matches `Done.routing_signals` byte-for-byte |
| `ReadMe.md` | docs | n/a | **MODIFY (append section)** | itself | exact — append "Running the chat UI" two-terminal block (CONTEXT specifics line 318-331) |
| `.gitignore` | config | n/a | **MODIFY (append lines)** | itself | exact — append `apps/web/node_modules/`, `apps/web/.next/`, `apps/web/coverage/`, `apps/web/playwright-report/`, `apps/web/test-results/` |

---

## Pattern Assignments

### Phase 3 amendment patterns (read-the-file-first)

#### `apps/api/routes/turn.py` (MODIFY — D-15 inject `routing_decision` event)

**Analog:** itself — read lines 416-446 (post-JSONL-log, pre-adapter-dispatch) and lines 452-590 (the `event_stream` generator).

**Imports already in scope** (lines 134-161):
```python
import asyncio
import logging
import secrets
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from apps.api.backends.chunks import (
    ChatChunk,
    Done,
    Screenshot,
    StreamError,
)
# ... (decide, RoutingDecision already imported)
```

**`json` is needed for the new yield** — currently NOT imported (the file uses `chunk.model_dump_json()` from Pydantic, not the stdlib `json` module directly). Add `import json` to the import block.

**Insertion point** — between line 446 (end of `options = AdapterOptions(...)`) and line 452 (the `async def event_stream():` declaration). The `decision` variable is already in scope (assigned at line 380 or 385). Per CONTEXT specifics lines 360-375 the pseudocode shape is:

```python
# Insertion goes INSIDE event_stream(), as the FIRST yield, before
# the try/except wrapping adapter.stream(). The event_stream generator
# already exists at lines 452-590 — insert just inside it.
async def event_stream():
    # NEW (D-15): emit routing_decision event BEFORE adapter dispatch
    # so the UI's chip renders within ~100ms of POST, well before the
    # first text_delta. ChatChunk union is NOT modified — this event
    # is yielded alongside, not as a chunk.
    yield ServerSentEvent(
        event="routing_decision",
        data=json.dumps(decision.signals),
    )

    buffer: list[ChatChunk] = []
    start_t = asyncio.get_event_loop().time()
    try:
        async for chunk in adapter.stream(...):
            # ... unchanged body ...
```

**Critical constraint** (from CONTEXT D-15 + specifics):
- The event's `data` payload MUST be `json.dumps(decision.signals)` — same dict as `Done.routing_signals` (which is set at line 509 / line 446 via `options.routing_signals=decision.signals`). The contract test asserts byte-for-byte equality.
- Yield happens INSIDE `event_stream()` so it ships through the same SSE pipeline. Yielding before `EventSourceResponse(event_stream(), ping=15)` would not be on the wire.
- Yield happens BEFORE the `try/except asyncio.CancelledError` block so a cancellation between adapter creation and adapter.stream() still emits the routing_decision (the chip should render even for ultra-fast cancellations).

---

#### `apps/api/tests/test_turn_streaming.py` (MODIFY — add contract test)

**Analog:** itself — read lines 176-254 (`test_streams_chatchunks` — the canonical happy-path SSE consumer using `httpx.AsyncClient + ASGITransport`).

**Mirror the existing test shape exactly:**

```python
async def test_routing_decision_event_arrives_first_and_matches_done(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """D-15 contract: routing_decision event arrives within 100ms AND
    its payload equals Done.routing_signals byte-for-byte.
    """
    app = _fresh_app(monkeypatch, tmp_path)

    from apps.api.backends.chunks import Done, TextDelta
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    # decide() returns signals that the new event MUST mirror.
    test_signals = {"task_type": "chat", "agentic_intent": False, "rule_fired": "default"}

    fake = FakeStreamingAdapter([
        TextDelta(text="hi"),
        Done(tokens_in=1, tokens_out=1, cost_usd=0.001, latency_ms=10,
             routing_signals=test_signals),
    ])
    app.state.adapters = {"openrouter": fake}

    from src.routing.schema import RoutingDecision

    def fake_decide(*a, **kw):
        return RoutingDecision(
            backend="openrouter",
            model_or_agent="openai/gpt-5",
            rationale="test",
            confidence=0.9,
            signals=test_signals,
        )
    monkeypatch.setattr("apps.api.routes.turn.decide", fake_decide)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            t0 = time.monotonic()
            first_event_t: float | None = None
            events: list[tuple[str, str]] = []  # (event, data)
            current_event: str | None = None

            async with client.stream(
                "POST",
                f"/api/v1/threads/{thread_id}/turn",
                json={"message": "hello"},
            ) as resp:
                assert resp.status_code == 200
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        current_event = line.split(":", 1)[1].strip()
                        if first_event_t is None:
                            first_event_t = time.monotonic()
                    elif line.startswith("data:") and current_event is not None:
                        events.append((current_event, line.split(":", 1)[1].strip()))
                        if current_event == "done":
                            break

    # Assertion 1: first event is routing_decision
    assert events[0][0] == "routing_decision", (
        f"first event was {events[0][0]!r}, expected 'routing_decision'"
    )

    # Assertion 2: arrived within 100ms (loose CI bound is 500ms; the
    # 100ms target is for real-network; ASGITransport has no network).
    assert (first_event_t - t0) < 0.5

    # Assertion 3: routing_decision payload === Done.routing_signals
    routing_payload = json.loads(events[0][1])
    done_event = next(e for e in events if e[0] == "done")
    done_payload = json.loads(done_event[1])
    assert routing_payload == done_payload["routing_signals"]
```

**Existing helpers to reuse:** `_fresh_app` (lines 108-158), `_create_thread` (lines 161-168), `FakeStreamingAdapter` (`apps/api/tests/fake_adapter.py`).

---

### `apps/web/app/api/chat/route.ts` (CREATE — SSE proxy + translator)

**Analog:** `apps/api/routes/turn.py` — read the entire `event_stream` generator (lines 452-590) and especially the named-event format on lines 481-484 (`event=chunk.type, data=chunk.model_dump_json()`). This IS the wire shape the proxy MUST consume.

**External canonical pattern:** RESEARCH.md §"Pattern 2" lines 470-700 (the full proxy + translator skeleton). The route handler itself is sketched at lines 642-697 of RESEARCH.md.

**Mandatory file declarations** (RESEARCH Critical Findings #3, #4 + Pitfalls 1, 2):
```typescript
export const runtime = "nodejs";        // Pitfall 1 — never Edge runtime
export const dynamic = "force-dynamic"; // never cache
```

**Body-stripping pattern (D-08)** — RESEARCH lines 651-658:
```typescript
const body = await req.json();
const lastUserMessage = [...(body.messages ?? [])].reverse().find((m: any) => m.role === "user");
const userText = lastUserMessage?.parts?.find((p: any) => p.type === "text")?.text
  ?? lastUserMessage?.content
  ?? "";
```

**Upstream fetch with abort propagation (D-09)** — RESEARCH lines 661-677:
```typescript
let upstream: Response;
try {
  upstream = await fetch(`${FASTAPI_URL}/api/v1/threads/${threadId}/turn`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: userText }),
    signal: req.signal,  // D-09 cancellation chain
  });
} catch (err: any) {
  if (err?.name === "AbortError") return new Response(null, { status: 499 });
  return new Response(
    JSON.stringify({ error: "API unavailable — is uvicorn running?" }),
    { status: 503, headers: { "Content-Type": "application/json" } },
  );
}
```

**Return-immediately-then-translate pattern (Pitfall 2)** — RESEARCH lines 686-697:
```typescript
const translated = translateNamedSSEToUIMessageStream(upstream.body);
return new Response(translated, {
  headers: {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
    "x-vercel-ai-ui-message-stream": "v1",  // Pitfall 7 — AI SDK v6 expects this
  },
});
```

---

### `apps/web/lib/sse-translate.ts` (CREATE — pure-function translator)

**Analog:** `apps/api/backends/chunks.py` (closed-vocabulary union the input mirrors) + `apps/api/routes/turn.py` lines 481-484 (the wire format being parsed).

**External canonical pattern:** RESEARCH.md §"Pattern 2" lines 510-637 — the complete `translateNamedSSEToUIMessageStream` implementation. The translation mapping table (RESEARCH lines 498-506) is the canonical contract:

| Phase 3 event | AI SDK v6 emission |
|---------------|---------------------|
| `routing_decision` | `{type: "start", messageId}` + `{type: "data-routing", data: signals}` |
| First `text_delta` | `{type: "text-start", id: "t-0"}` + `{type: "text-delta", id: "t-0", delta: text}` |
| Nth `text_delta` | `{type: "text-delta", id: "t-0", delta: text}` |
| `tool_call` / `tool_result` / `file_diff` / `screenshot` | `{type: "data-tool", data: chunk}` (Phase 5 forward-compat; Phase 4 ignores gracefully) |
| `stream_error` (code !== "cancelled") | `{type: "text-end", id: "t-0"}` + `{type: "error", errorText: <message>, code, retriable}` |
| `stream_error` (code === "cancelled") | `{type: "text-end", id: "t-0"}` + `{type: "abort", reason: "cancelled"}` |
| `done` | `{type: "text-end", id: "t-0"}` + `{type: "data-metrics", data: {...}}` + `{type: "finish"}` + literal `data: [DONE]\n\n` |

**Pure-function signature** (D-07):
```typescript
export function translateNamedSSEToUIMessageStream(
  upstream: ReadableStream<Uint8Array>,
): ReadableStream<Uint8Array>
```

**Closed-vocabulary Zod schema** — mirror Phase 2 D-01's discriminated union. Code shape from RESEARCH lines 515-524 (verbatim; the schema is the contract):

```typescript
const NamedSSEEventSchema = z.discriminatedUnion("event", [
  z.object({ event: z.literal("routing_decision"), data: z.record(z.unknown()) }),
  z.object({ event: z.literal("text_delta"),
             data: z.object({ type: z.literal("text_delta"), text: z.string() }) }),
  // ... 6 more — full set in RESEARCH lines 517-523
]);
```

---

### `apps/web/lib/chunk-schemas.ts` (CREATE — Zod schemas)

**Analog:** `apps/api/backends/chunks.py` — same closed vocabulary; TS port of the Pydantic v2 discriminated union. Excerpt from chunks.py to mirror (lines 117-139, StreamError code vocabulary):

```python
class StreamError(BaseModel):
    type: Literal["stream_error"] = "stream_error"
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
    message: str
    retriable: bool
```

TS port:
```typescript
export const StreamErrorCode = z.enum([
  "cost_cap_exceeded",
  "step_cap_exceeded",
  "cancelled",
  "rate_limited",
  "auth_failed",
  "provider_unavailable",
  "timeout",
  "validation_error",
  "internal_error",
]);
```

**Test contract:** every event variant in `chunks.py` MUST have a Zod schema that parses the JSON output of `chunk.model_dump_json()`. The `chunk-schemas.test.ts` fixtures should include one byte-for-byte sample per variant captured from a real Phase 3 SSE stream.

---

### `apps/web/lib/types.ts` (CREATE — TS interfaces matching `src/routing/schema.py`)

**Analog:** `src/routing/schema.py` lines 37-65 — `RoutingDecision` dataclass:

```python
@dataclass
class RoutingDecision:
    backend: Backend                    # Literal["openrouter", "claude_code", "computer_use"]
    model_or_agent: str
    rationale: str
    confidence: float
    signals: dict[str, Any] = field(default_factory=dict)
```

TS port:
```typescript
export type Backend = "openrouter" | "claude_code" | "computer_use";

export interface RoutingDecision {
  backend: Backend;
  model_or_agent: string;
  rationale: string;
  confidence: number;
  signals: Record<string, unknown>;
}
```

---

### `apps/web/app/api/threads/route.ts` (CREATE — thread CRUD proxy)

**Analog:** `apps/api/routes/threads.py:post_thread` (lines 118-130):
```python
@router.post("/threads")
async def post_thread(
    body: ThreadCreateRequest, request: Request
) -> Thread:
    db = request.app.state.db
    thread = await create_thread(db, title=body.title)
    return thread
```

TS proxy shape (CREATE — auto-create default thread on app boot):
```typescript
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";

export async function POST(req: Request) {
  const body = await req.json(); // {title: string}
  const upstream = await fetch(`${FASTAPI_URL}/api/v1/threads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!upstream.ok) {
    return new Response(await upstream.text(), { status: upstream.status });
  }
  return Response.json(await upstream.json());
}
```

---

### `apps/web/app/api/settings/route.ts` (CREATE — key submission proxy)

**Analog:** `apps/api/routes/settings.py:patch_settings` (lines 238-317). The Next-side route accepts `{provider, key}` for browser ergonomics and forwards as `{keys: {[provider]: key}}` (the FastAPI shape).

**External canonical pattern:** RESEARCH.md §"Pattern 8" lines 992-1023 — the full handler with D-18 belt-and-suspenders key scrub:

```typescript
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const { provider, key } = await req.json();
  if (provider !== "openrouter" && provider !== "anthropic") {
    return Response.json({ error: "unknown provider" }, { status: 400 });
  }
  try {
    const upstream = await fetch(`${FASTAPI_URL}/api/v1/settings`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keys: { [provider]: key } }),
    });
    if (!upstream.ok) {
      // D-18 belt-and-suspenders: scrub key from error body if upstream echoed it.
      const text = await upstream.text();
      const scrubbed = text.replace(key, "***");
      return new Response(scrubbed, { status: upstream.status });
    }
    return Response.json(await upstream.json());
  } catch (err: any) {
    const errMsg = String(err?.message ?? err).replace(key, "***");
    return Response.json({ error: "Could not save key", detail: errMsg }, { status: 503 });
  }
}
```

**Critical: never log `key` anywhere.** Mirror the Python comment on lines 286-291 of `settings.py`:
> "We DO NOT log the keys (defense in depth — the redaction filter already runs, but logging the body would be a foot-gun for any future key alphabet that does not match the regex)."

---

### `apps/web/app/api/health/route.ts` (CREATE — healthz passthrough)

**Analog:** `apps/api/routes/health.py:healthz` (lines 133-178). Pure passthrough — no transformation needed; the proxy preserves the rich payload shape so the UI can read `body.adapters.openrouter.status` directly.

```typescript
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const upstream = await fetch(`${FASTAPI_URL}/api/v1/healthz`);
    if (!upstream.ok) {
      return Response.json({ error: "upstream unhealthy" }, { status: upstream.status });
    }
    return Response.json(await upstream.json());
  } catch (err) {
    return Response.json(
      { error: "API unavailable — is uvicorn running?" },
      { status: 503 },
    );
  }
}
```

---

### `apps/web/components/RoutingChip.tsx` (CREATE)

**Analog:** none in repo (first React component).

**External canonical pattern:** RESEARCH.md §"Pattern 6" lines 865-888 — full component sketch. UI-SPEC §6 declares the visual contract (must match):

```tsx
"use client";
import { useThreadMessage } from "@assistant-ui/react";
import mapping from "../../../config/model_mapping.json"; // Pitfall 12 — bundled import
import { cn } from "@/lib/cn";

const chipClassByBackend = {
  openrouter: "bg-slate-100 text-slate-900 border-slate-200",
  claude_code: "bg-green-100 text-green-900 border-green-200",
  computer_use: "bg-amber-100 text-amber-900 border-amber-200",
} as const;

export function RoutingChip() {
  const message = useThreadMessage();
  const routingPart = message?.parts?.find((p: any) => p.type === "data-routing");
  if (!routingPart) return null;
  const signals = routingPart.data as {
    backend: keyof typeof chipClassByBackend;
    model_or_agent: string;
    rationale: string;
  };
  const displayName = (mapping as any)[signals.model_or_agent]?.display_name
                      ?? signals.model_or_agent;
  const colorClass = chipClassByBackend[signals.backend] ?? chipClassByBackend.openrouter;

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={`Routing decision: Routed to ${displayName}. ${signals.rationale}`}
      className={cn(
        "inline-flex items-center gap-2 px-2 py-1 rounded-md border text-[13px]",
        colorClass,
      )}
    >
      <span className="font-semibold">Routed to {displayName}</span>
      <span className="opacity-70"> · </span>
      <span>{signals.rationale}</span>
    </div>
  );
}
```

**Display-name resolution** uses bundled JSON import (Pitfall 12) — `import mapping from "../../../config/model_mapping.json"`. Verify the relative path resolves at build time; Next bundles JSON natively.

---

### `apps/web/components/MetricsFooter.tsx` (CREATE)

**Analog:** none in repo.

**External canonical pattern:** RESEARCH.md §"Pattern 7" lines 902-924 — full component sketch. UI-SPEC §7 declares the format contract (`$0.0021 · 1.4s · 312↑/847↓`).

---

### `apps/web/components/FirstRunModal.tsx` (CREATE)

**Analog:** none in repo.

**External canonical pattern:** RESEARCH.md §"Pattern 8" lines 928-989 (full boot-sequence flow + submitKey helper + handleKeySaved sequence). UI-SPEC §10 declares the visual + ARIA contract (must match):
- shadcn `Dialog` primitive (installed via `pnpm dlx shadcn@latest add dialog`)
- `onEscapeKeyDown={(e) => e.preventDefault()}` + `onPointerDownOutside={(e) => e.preventDefault()}` in blocking mode (Pitfall 9)
- Exact copy from UI-SPEC §10.2 — "Connect OpenRouter to get started", "Save & continue", `sk-or-v1-...` placeholder

---

### Component file pattern (general — for all `apps/web/components/*.tsx`)

**File header convention** — every component file is a React 19 client component (assistant-ui hooks require client tree, Pitfall 8):

```tsx
"use client";

import { /* react + lib imports */ } from "...";
import { cn } from "@/lib/cn";

// Component definition
export function ComponentName(props: Props) { ... }
```

**Class-composition idiom:** every dynamic className uses `cn(...)`. No raw template strings for conditional classes.

---

### `apps/web/playwright/playwright.config.ts` (CREATE)

**External canonical pattern:** RESEARCH.md §"Example 3" lines 1152-1164:

```typescript
import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: ".",
  webServer: [
    { command: "uvicorn apps.api.main:app --port 8000", port: 8000, cwd: "../../", reuseExistingServer: !process.env.CI },
    { command: "pnpm dev --port 3000", port: 3000, reuseExistingServer: !process.env.CI },
  ],
  use: { baseURL: "http://localhost:3000" },
});
```

---

### `apps/web/playwright/cancel-budget.spec.ts` (CREATE)

**Analog:** `apps/api/tests/test_turn_streaming.py:test_cancellation_within_2s` (line 28 of the docstring — "API-06 budget test: consumer task.cancel() must release the stream within 2s wall-clock").

**Mirror the 2s budget invariant on the browser→Next layer.** The Python test uses `task.cancel()` + `time.monotonic()` measurement; the Playwright test uses `useChat.stop()` click + `performance.now()` measurement:

```typescript
test("stop click cancels within 2s budget", async ({ page }) => {
  await page.goto("/");
  // ... send a prompt that streams for many seconds ...
  const stopButton = page.locator('[aria-label="Stop generating"]');
  await stopButton.waitFor({ state: "visible" });
  const t0 = await page.evaluate(() => performance.now());
  await stopButton.click();
  // Cancelled UI state = the bubble is finalized + cost footer shows.
  await page.locator('text=/cancelled|Stopped/').waitFor({ timeout: 2500 });
  const t1 = await page.evaluate(() => performance.now());
  expect(t1 - t0).toBeLessThan(2000);
});
```

---

### `apps/web/playwright/secure-key.spec.ts` (CREATE)

**Analog:** `apps/api/tests/test_secure_no_key_in_logs.py` — the Python disclosure-regression test that asserts a real-shaped key never appears in FastAPI logs. The TS analog covers the additional surfaces (browser storage, Next response bodies/headers, Next server stdout).

**External canonical pattern:** CONTEXT D-18 belt-and-suspenders (lines 144-145) + RESEARCH.md §"Security Test Plan" lines 1344-1349. The test asserts zero literal-key matches across:
1. Browser DevTools storage (localStorage / sessionStorage / cookies) — via `page.evaluate(() => document.cookie + JSON.stringify(localStorage) + JSON.stringify(sessionStorage))`.
2. All response bodies from `/api/settings`, `/api/health`, `/api/chat` — via `page.on('response', ...)` capture.
3. All response headers — same listener.
4. All captured Next.js server stdout / stderr — via Playwright's `webServer.stdout` capture (Playwright 1.43+).

---

### `apps/web/playwright/browser-isolation.spec.ts` (CREATE)

**Analog:** none in repo (first network-assertion test).

**External canonical pattern:** CONTEXT D-18 anti-pattern (lines 290-291) + RESEARCH.md Architecture Diagram (lines 365-371) — the invariant that the browser only opens connections to the Next.js origin, never to `localhost:8000`. Implementation: `page.on('request', req => { expect(new URL(req.url()).host).not.toBe('localhost:8000'); })`.

---

### `apps/web/playwright/no-flicker.spec.ts` (CREATE)

**External canonical pattern:** RESEARCH.md §"Pattern 5" lines 789-825 — full MutationObserver-based test:

```typescript
test("code block highlights exactly once", async ({ page }) => {
  await page.goto("/");
  await page.fill('[aria-label="Send message"]',
                  "Write a Python hello world in a fenced code block.");
  await page.keyboard.press("Enter");
  const codeEl = page.locator("pre code").first();
  await codeEl.waitFor({ state: "attached", timeout: 5_000 });

  await page.evaluate(() => {
    (window as any).__codeMutations = 0;
    const observer = new MutationObserver(() => {
      (window as any).__codeMutations += 1;
    });
    const target = document.querySelector("pre code");
    if (target) observer.observe(target, { childList: true, subtree: true });
  });

  await page.waitForSelector('[aria-label*="Turn cost"]', { timeout: 30_000 });
  await page.waitForTimeout(500);
  const mutations = await page.evaluate(() => (window as any).__codeMutations);
  const mutationsAfterDone = await page.evaluate(() => (window as any).__codeMutations);
  expect(mutationsAfterDone).toBe(mutations); // no late re-highlights
});
```

---

### `apps/web/tests/sse-translate.test.ts` (CREATE — Vitest unit test)

**Analog:** `apps/api/tests/test_turn_streaming.py:test_streams_chatchunks` (lines 176-254) — the canonical SSE consumer that iterates `aiter_lines()` and asserts event order. The TS analog tests the inverse direction: feed a fixture `ReadableStream<Uint8Array>` of named events into `translateNamedSSEToUIMessageStream` and assert the output ReadableStream emits the correct AI SDK v6 chunk sequence.

**Test shape:**
```typescript
import { describe, it, expect } from "vitest";
import { translateNamedSSEToUIMessageStream } from "@/lib/sse-translate";

function fixtureStream(events: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const e of events) controller.enqueue(encoder.encode(e));
      controller.close();
    },
  });
}

async function consumeToText(stream: ReadableStream<Uint8Array>): Promise<string> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let out = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    out += decoder.decode(value);
  }
  return out;
}

describe("translateNamedSSEToUIMessageStream", () => {
  it("emits start + data-routing on routing_decision event", async () => {
    const input = fixtureStream([
      `event: routing_decision\ndata: {"backend":"openrouter","model_or_agent":"openai/gpt-5"}\n\n`,
      `event: done\ndata: {"type":"done","cost_usd":0.001}\n\n`,
    ]);
    const out = await consumeToText(translateNamedSSEToUIMessageStream(input));
    expect(out).toContain('"type":"start"');
    expect(out).toContain('"type":"data-routing"');
    expect(out).toContain('"type":"finish"');
    expect(out).toContain('data: [DONE]');
  });

  // ... one test per Phase-3 event variant
});
```

---

### `apps/web/vitest.config.ts` (CREATE)

**Analog:** `pyproject.toml` `[tool.pytest.ini_options]` (lines 52-62) — pytest config in TOML form:
```toml
[tool.pytest.ini_options]
testpaths = ["src", "apps"]
python_files = ["test_*.py"]
addopts = "-x -q --import-mode=importlib"
asyncio_mode = "auto"
```

TS equivalent (Vitest):
```typescript
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    globals: true,
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "."),
    },
  },
});
```

---

### `apps/web/tests/setup.ts` (CREATE)

**Analog:** `apps/api/tests/conftest.py` — the pytest fixture-and-import shim. TS equivalent is the Vitest setup file:

```typescript
import "@testing-library/jest-dom/vitest";
// Optional: clean up after each test
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";
afterEach(() => { cleanup(); });
```

---

### `.github/workflows/web-test.yml` (CREATE)

**Analog:** `.github/workflows/ci.yml` (read in full — it's the canonical GitHub Actions workflow shape for this repo).

**Excerpt to mirror** (`.github/workflows/ci.yml` lines 1-30 — workflow boilerplate + setup):
```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout (with LFS for data_processed/*.csv)
        uses: actions/checkout@v4
        with:
          lfs: true
      # ... uv install + python install + sync ...
```

**TS workflow shape:**
```yaml
name: Web Tests

on:
  push:
    branches: [main]
    paths: [ "apps/web/**", "apps/api/**", ".github/workflows/web-test.yml" ]
  pull_request:
    paths: [ "apps/web/**", "apps/api/**" ]

jobs:
  web-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v3
        with:
          version: 9
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "pnpm"
          cache-dependency-path: apps/web/pnpm-lock.yaml
      # Required for E2E: spin up uvicorn alongside next dev
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --locked
      - run: pnpm --dir apps/web install --frozen-lockfile
      - run: pnpm --dir apps/web exec playwright install --with-deps chromium
      - name: Vitest
        run: pnpm --dir apps/web test
      - name: Playwright E2E
        run: pnpm --dir apps/web test:e2e
```

**Note (Phase 6 dependency):** RESEARCH §"Validation Architecture" line 1304 notes the CI workflow extension is "Wave 0 gap" but ROADMAP Phase 6 owns OSS-07 (Playwright E2E in CI). Planner decides whether the workflow ships in Phase 4 (recommended: yes, locally green from day 1) or Phase 6 (CI-only). PATTERNS marks it as Wave 0/Wave 6 deferred — planner chooses.

---

### `.gitignore` (MODIFY — append Next.js artifacts)

**Analog:** itself — read existing 30 lines. Append-only mode:
```
# Next.js (Phase 4)
apps/web/node_modules/
apps/web/.next/
apps/web/coverage/
apps/web/playwright-report/
apps/web/test-results/
apps/web/.env.local
```

Note: `.env.local` is already covered by the existing `.env*.local` rule (line 17). The explicit `apps/web/.env.local` line is documentation belt-and-suspenders (CONTEXT D-05 mentions verifying).

---

### `ReadMe.md` (MODIFY — append "Running the chat UI" section)

**Analog:** itself — append a new H2 section. Exact text from CONTEXT specifics lines 317-331:

```markdown
## Running the chat UI

Terminal 1 (FastAPI):
    uv sync
    uvicorn apps.api.main:app --reload

Terminal 2 (Next.js):
    pnpm --dir apps/web install
    pnpm --dir apps/web dev

Then open http://localhost:3000.
On first run, paste your OpenRouter key into the modal.
```

---

## Shared Patterns

### Pattern A — Closed-vocabulary discriminated union (TS port of Pydantic v2)

**Source:** `apps/api/backends/chunks.py` (the canonical Phase 2 union) + `apps/api/routes/settings.py:KeyPatch` / `SettingsPatch` (Pydantic v2 with `ConfigDict(extra="forbid")`).

**Apply to:** `apps/web/lib/chunk-schemas.ts`, `apps/web/lib/sse-translate.ts` (Zod discriminated union), `apps/web/lib/types.ts` (TS interface ports).

**Python excerpt** (`apps/api/backends/chunks.py:117-139`):
```python
class StreamError(BaseModel):
    type: Literal["stream_error"] = "stream_error"
    code: Literal[
        "cost_cap_exceeded", "step_cap_exceeded", "cancelled",
        "rate_limited", "auth_failed", "provider_unavailable",
        "timeout", "validation_error", "internal_error",
    ]
    message: str
    retriable: bool
```

**TS port:**
```typescript
export const StreamErrorSchema = z.object({
  type: z.literal("stream_error"),
  code: z.enum([
    "cost_cap_exceeded", "step_cap_exceeded", "cancelled",
    "rate_limited", "auth_failed", "provider_unavailable",
    "timeout", "validation_error", "internal_error",
  ]),
  message: z.string(),
  retriable: z.boolean(),
});
```

**Rule:** every literal vocabulary that exists on the Python side as `Literal[...]` MUST appear on the TS side as `z.enum([...])` AND as a TypeScript union type. The list contents MUST be byte-for-byte identical (the wire is the same).

---

### Pattern B — Server-only env var (no `NEXT_PUBLIC_` leak)

**Source:** UI-17 + D-18 + RESEARCH §"Security Domain" lines 1331-1339.

**Apply to:** every `apps/web/app/api/*/route.ts` file.

**Excerpt:**
```typescript
const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";
```

**Rule:** the env var is `FASTAPI_URL` (no `NEXT_PUBLIC_` prefix). This guarantees it is never exposed to the client bundle. The Playwright `browser-isolation.spec.ts` test enforces the "browser never opens connections to FastAPI" invariant.

---

### Pattern C — Route handler runtime declarations

**Source:** RESEARCH Critical Finding #3 (Edge runtime is forbidden) + RESEARCH §"Pattern 2" lines 644-649.

**Apply to:** every `apps/web/app/api/*/route.ts` file.

**Excerpt** (mandatory top-of-file):
```typescript
export const runtime = "nodejs";        // Pitfall 1 — never Edge runtime
export const dynamic = "force-dynamic"; // Pitfall: cached responses break streaming
```

---

### Pattern D — Client-component declaration

**Source:** Pitfall 8 (assistant-ui + useChat hooks require client tree).

**Apply to:** every `apps/web/components/*.tsx` file that uses React hooks or assistant-ui primitives, and `apps/web/app/page.tsx` + `apps/web/app/settings/page.tsx`.

**Excerpt** (mandatory top-of-file):
```typescript
"use client";
```

**Exception:** `apps/web/app/layout.tsx` is a SERVER component (App Router default) and MUST NOT have `"use client"` at the top. It can render the runtime provider via a child client component but the layout itself stays server-side.

---

### Pattern E — Class-composition with `cn()`

**Source:** RESEARCH "Standard Stack" `clsx + tailwind-merge` + UI-SPEC §1 (cn helper from shadcn convention).

**Apply to:** every component that has dynamic className logic.

**Excerpt:**
```typescript
// apps/web/lib/cn.ts (one-liner; the standard shadcn helper)
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
```

**Rule:** never use raw template strings for conditional classes (`\`text-${disabled ? 'gray-400' : 'slate-900'}\``). Always go through `cn()`.

---

### Pattern F — Pydantic-style validation at the wire boundary

**Source:** `apps/api/routes/settings.py:KeyPatch` + `SettingsPatch` (Pydantic v2 `ConfigDict(extra="forbid")`) + RESEARCH §"Validation Architecture" + RESEARCH Pitfall 5.

**Apply to:** `apps/web/lib/sse-translate.ts` (Zod parse before translate) and `apps/web/lib/chunk-schemas.ts` (all incoming SSE event shapes).

**Excerpt** (RESEARCH lines 567-575 — parse-then-handle-failure):
```typescript
let parsed;
try {
  parsed = NamedSSEEventSchema.parse({
    event,
    data: JSON.parse(dataLines.join("\n")),
  });
} catch (err) {
  controller.enqueue(emit({ type: "error", errorText: `Malformed upstream event: ${event}` }));
  continue; // never throw uncaught — translator must keep streaming
}
```

**Rule:** parse failures emit `{type: "error", errorText: ...}` and continue. The translator never crashes the stream over a single malformed event (DoS pitfall in RESEARCH §"Known Threat Patterns").

---

### Pattern G — Secret-scrub on every error path

**Source:** D-18 belt-and-suspenders + Pitfall 6 + RESEARCH §"Pattern 8" lines 1011-1022.

**Apply to:** `apps/web/app/api/settings/route.ts` (key scrub), any future route that handles secret material.

**Excerpt:**
```typescript
try {
  // ... fetch with key in body ...
} catch (err: any) {
  // Catch BEFORE the error message can include the key
  const errMsg = String(err?.message ?? err).replace(key, "***");
  return Response.json({ error: "Could not save key", detail: errMsg }, { status: 503 });
}
```

**Rule:** any error path inside `apps/web/app/api/settings/route.ts` MUST run `.replace(key, "***")` (or equivalent) on the response body, response headers, and any thrown error before returning. The Playwright `secure-key.spec.ts` test enforces zero literal-key matches across browser storage + response bodies + headers + Next stdout.

---

## No Analog Found

These files have no in-repo analog and rely entirely on external patterns (RESEARCH.md sections + assistant-ui canonical examples):

| File | Role | External Pattern Source |
|------|------|------------------------|
| `apps/web/app/layout.tsx` | layout (server) | Next.js App Router docs — root layout idiom (e.g., `https://nextjs.org/docs/app/getting-started/layouts-and-pages`) |
| `apps/web/app/page.tsx` | page (client) | RESEARCH §"Pattern 1" lines 437-466 (assistant-ui + AI SDK v6 runtime mounting) + assistant-ui `examples/with-ai-sdk-v6` |
| `apps/web/components/ChatBubble.tsx` | component | UI-SPEC §8 — visual contract; uses `@assistant-ui/react` `MessagePrimitive` |
| `apps/web/components/Composer.tsx` (or inline in page.tsx) | component | UI-SPEC §9 — uses `@assistant-ui/react` Composer primitive |
| `apps/web/components/StreamErrorBanner.tsx` | component | UI-SPEC §12 — code → user-friendly message catalog (UI-SPEC §12.2 table is the contract) |
| `apps/web/components/NetworkDownBanner.tsx` | component | UI-SPEC §13 + RESEARCH "Claude's Discretion" — 5s `/api/health` poll |
| `apps/web/components/EmptyState.tsx` | component | UI-SPEC §11 — centered tagline only |
| `apps/web/components/KeyForm.tsx` | component | RESEARCH §"Pattern 8" lines 980-989 (submitKey helper) + UI-SPEC §10.2 |
| `apps/web/components/MarkdownRenderer.tsx` (or `lib/markdown-components.tsx`) | utility | RESEARCH §"Pattern 4" lines 740-775 (block-memoized markdown body) |
| `apps/web/lib/markdown-components.tsx` | utility | RESEARCH §"Pattern 4" + `@assistant-ui/react-markdown` component-map convention |
| `apps/web/lib/thread-id.ts` | utility | CONTEXT "Claude's Discretion" — `POST /api/v1/threads` + `localStorage` persistence |
| `apps/web/hooks/useChatThread.ts` | hook | RESEARCH §"Pattern 1" — wraps `useChatRuntime` + `AssistantChatTransport` |
| `apps/web/hooks/useFirstRunGate.ts` | hook | RESEARCH §"Pattern 8" lines 940-956 (boot-time healthz check) |
| `apps/web/playwright/first-run.spec.ts` | E2E test | RESEARCH §"Pattern 8" + UI-SPEC §10 |
| `apps/web/playwright/routing-chip.spec.ts` | E2E test | UI-SPEC §6 visual contract + RESEARCH §"Pattern 6" |
| `apps/web/tests/chunk-schemas.test.ts` | unit test | mirror Pydantic test pattern; fixtures captured from real Phase 3 SSE wire |
| `apps/web/tests/routing-chip.test.tsx` | RTL test | first RTL test in repo — base on @testing-library/react canonical patterns |
| `apps/web/tests/metrics-footer.test.tsx` | RTL test | same |
| `apps/web/components/ui/*.tsx` (shadcn-installed) | n/a | generated by `pnpm dlx shadcn@latest add button dialog input sonner` — never hand-edit |
| `apps/web/package.json` | manifest | assistant-ui canonical `examples/with-ai-sdk-v6/package.json` — RESEARCH "Standard Stack" enumerates every dependency |
| `apps/web/tsconfig.json` | TS config | `create-next-app` default; RESEARCH "Standard Stack" notes TS 5.x stable |
| `apps/web/next.config.ts` | Next config | `create-next-app` default; may be near-empty |
| `apps/web/tailwind.config.ts` | Tailwind v4 config | minimal — Tailwind v4 prefers CSS-first config in `globals.css` |
| `apps/web/postcss.config.mjs` | PostCSS config | required to enable `@tailwindcss/postcss` plugin |
| `apps/web/components.json` | shadcn config | generated by `pnpm dlx shadcn@latest init`; style: new-york, baseColor: slate (UI-SPEC §1) |
| `apps/web/app/globals.css` | stylesheet | Tailwind v4 CSS-first — declares `@import "tailwindcss"` and theme tokens |
| `apps/web/.env.example` | env template | `FASTAPI_URL=http://localhost:8000` only |

---

## Metadata

**Analog search scope:** `apps/api/routes/`, `apps/api/backends/`, `apps/api/tests/`, `apps/api/main.py`, `src/routing/`, `config/`, `pyproject.toml`, `.github/workflows/`, `.gitignore`, `ReadMe.md`.

**Files scanned:** 9 (read in detail) + ~10 (existence-only via `ls` / `grep`).

**Stop signal:** the 5 strongest analogs are `apps/api/routes/turn.py`, `apps/api/routes/health.py`, `apps/api/routes/threads.py`, `apps/api/routes/settings.py`, and `apps/api/backends/chunks.py`. These cover every CREATE that has any in-repo precedent. The remaining ~30 React/TS files are genuinely greenfield and rely on RESEARCH.md's external pattern citations (all properly anchored to URLs in RESEARCH §"Sources").

**Pattern extraction date:** 2026-05-18

**Key invariants enforced by patterns:**
1. **Wire-format symmetry:** Pydantic `Literal[...]` on Python side ↔ Zod `z.enum([...])` on TS side. The contract test in `chunk-schemas.test.ts` will fixture against real Phase 3 SSE output.
2. **No browser-to-FastAPI direct calls:** Every `apps/web/app/api/*/route.ts` uses server-only `FASTAPI_URL` env var. Playwright `browser-isolation.spec.ts` enforces.
3. **No key leakage:** `apps/web/app/api/settings/route.ts` scrubs the key from every error path (Pattern G). Playwright `secure-key.spec.ts` enforces.
4. **Edge runtime forbidden:** Every route handler declares `export const runtime = "nodejs"` (Pattern C).
5. **D-15 chip-first invariant:** `apps/api/routes/turn.py` emits `routing_decision` BEFORE the first `text_delta`. New contract test in `test_turn_streaming.py` enforces.
