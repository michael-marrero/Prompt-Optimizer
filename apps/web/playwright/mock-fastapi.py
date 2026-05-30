"""Mock FastAPI server for Playwright CI runs.

Emits a canned SSE sequence so the web-test.yml workflow can exercise
the full proxy + UI without an OpenRouter key (threat T-04-03 mitigation).

Run:
    python apps/web/playwright/mock-fastapi.py --port 8001

Wire contract (mirrors Phase 3 D-07 named-event SSE format):
    event: routing_decision
    data: {"backend":"openrouter","model_or_agent":"openai/gpt-5","rationale":"Test routing","confidence":0.92,"signals":{"task_type":"chat","agentic_intent":false,"rule_fired":"default"}}

    event: text_delta
    data: {"type":"text_delta","text":"Hello"}

    event: text_delta
    data: {"type":"text_delta","text":" world"}

    event: done
    data: {"type":"done","tokens_in":3,"tokens_out":2,"cost_usd":0.0001,"latency_ms":42,"routing_signals":{"task_type":"chat","agentic_intent":false,"rule_fired":"default"}}
"""

# ============================================================================
# CANONICAL FIXTURE CATALOG (mock-fastapi.py)
# ----------------------------------------------------------------------------
# Tests select named fixtures via a body-prefix mechanism:
#   body.message.startswith("[fixture:NAME]")  →  dispatch to fixture NAME
# The prefix is stripped before the fixture handler sees the rest of the
# message. Adding new fixtures: extend `_resolve_fixture(body)` below; the
# fixture name MUST be added to this catalog comment so future contributors
# do not invent a second selection mechanism (e.g. query params).
#
# Named fixtures across Plans 01/06/07 (and Plan 06-04 screenshots):
#   default                — Plan 01: routing_decision (backend openrouter) + 2
#                            text_deltas + done
#   [fixture:code-block]   — Plan 06: routing_decision + streamed fenced
#                            ```python ... ``` + done (used by no-flicker.spec.ts)
#   [fixture:slow]         — Plan 07: routing_decision + 1 text_delta every
#                            500ms for 10s + done (used by cancel-budget.spec.ts)
#   [fixture:missing-key]  — Plan 07: healthz returns missing_key until PATCH
#                            /api/v1/settings; used by first-run.spec.ts
#   [fixture:auth-failed]  — Plan 07: routing_decision + stream_error(auth_failed)
#                            + done; used by error-banner manual UAT
#   [fixture:claude-code]  — Plan 06-04: routing_decision (backend claude_code) +
#                            tool_call + file_diff + summary text + done. Drives
#                            MessageBubble -> CodeBubble (data-testid code-bubble)
#                            so capture-screenshots.capture.ts can shoot the GREEN
#                            Claude Code chip + diff. NO real keys.
#   [fixture:computer-use] — Plan 06-04: routing_decision (backend computer_use) +
#                            narration text + screenshot (inline 1x1 image_b64) +
#                            done. Drives MessageBubble -> ComputerUseBubble
#                            (data-testid computer-use-bubble) so the capture
#                            script can shoot the AMBER computer-use chip + strip.
# ============================================================================

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

app = FastAPI(title="mock-fastapi")

_CANNED_SIGNALS = {
    "task_type": "chat",
    "agentic_intent": False,
    "rule_fired": "default",
}


# ============================================================================
# Plan 08-04 — IN-MEMORY thread + messages store (Open Q2 resolution: option b)
# ----------------------------------------------------------------------------
# SC-4 (thread-history restore) needs a PERSISTENT backend: selecting a thread
# fetches GET /api/v1/threads/{id}/messages and the rows must survive a
# `browser.newContext()` close+reopen WITHIN one spec. The real uvicorn backend
# (the default playwright.config.ts branch) persists to SQLite but needs an
# OpenRouter key OR NLTK-seeded routing — not CI-portable / key-free.
#
# 08-RESEARCH §"Open Questions" Q2 + §"Pitfall 6" leave this to the planner and
# recommend option (b) for CI portability: extend THIS mock with a tiny
# in-memory thread+messages store + a `GET /messages` route mirroring the real
# `MessageWithRouting` JSON shape. The store is module-level state on the
# long-lived mock process, so it DOES survive `context.close()` + a fresh
# `browser.newContext()` within a single spec (Assumption A3) — that is exactly
# what SC-4's "reopen" path exercises. It does NOT survive a mock PROCESS
# restart (no SQLite), which SC-4 does not require.
#
# Shape contract (must mirror apps/api/routes/threads.py `MessageWithRouting`
# and apps/web/lib/chunk-schemas.ts `MessageRowSchema` EXACTLY) so the client
# reconstruction path (reconstructUIMessages) is byte-identical to the real
# backend: one row per message with {id, role, text, content_blocks(parsed list),
# backend_used, model_used, cost_usd, latency_ms, tokens_in, tokens_out,
# created_at, status, routing:{rationale, override}|null}.
# ============================================================================

# thread_id -> {"id", "title", "created_at", "updated_at"}
_THREADS: dict[str, dict[str, Any]] = {}
# thread_id -> ordered list of MessageWithRouting-shaped dicts (oldest-first)
_MESSAGES: dict[str, list[dict[str, Any]]] = {}


def _now_iso() -> str:
    """Monotonic-ish ISO-8601 timestamp. We append a microsecond counter so
    chronological order is deterministic even for same-instant inserts (the
    real backend orders by created_at; the spec asserts the restored order)."""
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + f".{time.time_ns() % 1_000_000:06d}Z"


def _ensure_thread(thread_id: str, title: str = "Untitled") -> dict[str, Any]:
    """Idempotently register a thread in the store (the /turn handler may be
    the first to see a thread id when the spec sends a turn into a freshly
    auto-created thread)."""
    if thread_id not in _THREADS:
        ts = _now_iso()
        _THREADS[thread_id] = {
            "id": thread_id,
            "title": title,
            "created_at": ts,
            "updated_at": ts,
        }
        _MESSAGES.setdefault(thread_id, [])
    return _THREADS[thread_id]


# ----------------------------------------------------------------------------
# Plan 07 [fixture:missing-key] — module-level state flag.
#
# missing-key is conceptually a HEALTHZ-state fixture, not a turn-body fixture.
# The body-prefix mechanism applies to /turn fixtures (slow + auth-failed); for
# first-run.spec.ts we simply boot the mock with NO key set (initial False)
# and the healthz handler reports openrouter.status="missing_key" until a
# PATCH /api/v1/settings arrives with any non-empty openrouter key. Then we
# flip the flag and subsequent healthz polls report "ready" — which lets the
# Next /api/health proxy return success and useFirstRunGate flips needsKey
# to false (D-19 post-entry unblock).
#
# NOTE: this is in-process module state. Playwright workers=1 + the
# reuseExistingServer:false config (CI path) ensures one test does NOT see
# another test's state. For multi-spec local runs we add a reset endpoint
# below so each spec can explicitly clear the state at its start.
# ----------------------------------------------------------------------------
_has_openrouter_key = False


@app.get("/api/v1/healthz")
async def healthz() -> dict:
    """Adapter-status endpoint — mirrors apps/api/routes/health.py shape.

    Plan 07 [fixture:missing-key] state machine: openrouter.status reflects
    the module-level _has_openrouter_key flag. The other adapters are
    pinned to their Plan 01 defaults (claude_code missing, computer_use
    opt_out) since Phase 4 only exercises openrouter.
    """
    openrouter_status: dict[str, str]
    if _has_openrouter_key:
        openrouter_status = {"status": "ready"}
    else:
        openrouter_status = {
            "status": "missing_key",
            "reason": "OPENROUTER_API_KEY not set",
        }
    return {
        "status": "ok" if _has_openrouter_key else "degraded",
        "adapters": {
            "openrouter": openrouter_status,
            "claude_code": {"status": "missing_key"},
            "computer_use": {"status": "opt_out"},
        },
    }


@app.post("/api/v1/threads")
async def create_thread(request: Request) -> dict:
    """Auto-create a default thread on app boot / New chat.

    Plan 08-04: persist the new thread into the in-memory store so it appears
    in the GET /threads list and can carry restorable messages. Honors an
    optional {title} body (useThreads.createThread posts a title)."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    title = "Untitled"
    if isinstance(body, dict) and isinstance(body.get("title"), str) and body["title"]:
        title = body["title"]
    thread_id = f"test-thread-{uuid.uuid4().hex[:8]}"
    thread = _ensure_thread(thread_id, title)
    # Return the FULL thread shape (id + title + created_at + updated_at) to match
    # the real `post_thread` (threads.py:170-181). The sidebar sorts the optimistic
    # row by `updated_at.localeCompare` (AppSidebar.tsx:41); a missing field would
    # crash the client on the next render.
    return {
        "id": thread["id"],
        "title": thread["title"],
        "created_at": thread["created_at"],
        "updated_at": thread["updated_at"],
    }


@app.get("/api/v1/threads")
async def list_threads() -> list[dict]:
    """Sidebar thread-list source (UI-02). Newest-first by updated_at — mirrors
    the real `GET /api/v1/threads` ordering so the reopen path finds seeded
    threads in the sidebar."""
    threads = sorted(
        _THREADS.values(), key=lambda t: t["updated_at"], reverse=True
    )
    return [
        {
            "id": t["id"],
            "title": t["title"],
            "created_at": t["created_at"],
            "updated_at": t["updated_at"],
        }
        for t in threads
    ]


@app.get("/api/v1/threads/{thread_id}")
async def get_single_thread(thread_id: str) -> dict:
    """Single-thread lookup (404 on unknown) — mirrors the real handler so the
    sidebar/select path resolves a seeded thread."""
    thread = _THREADS.get(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    return {
        "id": thread["id"],
        "title": thread["title"],
        "created_at": thread["created_at"],
        "updated_at": thread["updated_at"],
    }


@app.patch("/api/v1/threads/{thread_id}/rename")
async def rename_thread(thread_id: str, request: Request) -> dict:
    """Auto-rename (UI-14) target. The switch-path test matches thread A's row
    by its first-prompt fragment, so honoring the rename keeps the sidebar
    title aligned with the prompt. 404 on unknown thread (real contract)."""
    if thread_id not in _THREADS:
        raise HTTPException(status_code=404, detail="thread not found")
    try:
        body = await request.json()
    except Exception:
        body = {}
    if isinstance(body, dict) and isinstance(body.get("title"), str) and body["title"]:
        _THREADS[thread_id]["title"] = body["title"]
        _THREADS[thread_id]["updated_at"] = _now_iso()
    return {
        "id": thread_id,
        "title": _THREADS[thread_id]["title"],
    }


@app.get("/api/v1/threads/{thread_id}/messages")
async def get_thread_messages(thread_id: str) -> list[dict]:
    """Plan 08-04 restore read (SC-4 / D-01). Returns the seeded rows in
    chronological order, mirroring the real `MessageWithRouting` shape so the
    client `reconstructUIMessages` path is identical. 404 on unknown thread
    (so the client distinguishes not-found from a real-but-empty `200 []` —
    the 404-ordering hazard in 08-RESEARCH §Pattern 4)."""
    if thread_id not in _THREADS:
        raise HTTPException(status_code=404, detail="thread not found")
    return _MESSAGES.get(thread_id, [])


@app.patch("/api/v1/settings")
async def patch_settings(request: Request) -> dict:
    """Pretend the key save worked; flip the missing-key state flag.

    Plan 07: any non-empty openrouter key in the request body flips the
    module-level _has_openrouter_key flag to True, so subsequent
    /api/v1/healthz polls report adapters.openrouter.status="ready" and
    the first-run modal closes.
    """
    global _has_openrouter_key
    try:
        body = await request.json()
    except Exception:
        body = {}
    if isinstance(body, dict):
        keys = body.get("keys") if isinstance(body.get("keys"), dict) else {}
        openrouter_value = keys.get("openrouter") if isinstance(keys, dict) else None
        if isinstance(openrouter_value, str) and openrouter_value:
            _has_openrouter_key = True
    return {
        "keys": {
            "openrouter": {"present": True, "masked": "sk-or-…ABC"},
        }
    }


@app.post("/__reset")
async def reset_state() -> dict:
    """Test helper — resets the module-level missing-key flag AND the Plan
    08-04 in-memory thread/messages store.

    Useful for local multi-spec runs where the Playwright `webServer` is
    reused across tests (reuseExistingServer=true). first-run.spec.ts hits
    this endpoint at test start to guarantee a fresh missing-key state;
    thread-restore.spec.ts hits it so each run starts with an empty store.
    """
    global _has_openrouter_key
    _has_openrouter_key = False
    _THREADS.clear()
    _MESSAGES.clear()
    return {"reset": True}


def _persist_turn(
    thread_id: str,
    *,
    user_text: str,
    backend: str,
    model_or_agent: str,
    rationale: str,
    assistant_text: str,
    content_blocks: list[dict[str, Any]] | None,
    override: bool,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    latency_ms: int,
) -> None:
    """Plan 08-04 — append a user row + an assistant row to the in-memory store
    so the turn is RESTORABLE. Mirrors the real `persist_turn` write shape in
    reverse: the assistant row carries backend/model/metrics + a `routing`
    sub-object (D-01), and content_blocks is the PARSED list of non-text chunks.
    Rows match `MessageWithRouting` / `MessageRowSchema` field-for-field."""
    _ensure_thread(thread_id)
    rows = _MESSAGES.setdefault(thread_id, [])
    rows.append(
        {
            "id": f"msg-{uuid.uuid4().hex[:12]}",
            "role": "user",
            "text": user_text,
            "content_blocks": [],
            "backend_used": None,
            "model_used": None,
            "cost_usd": None,
            "latency_ms": None,
            "tokens_in": None,
            "tokens_out": None,
            "created_at": _now_iso(),
            "status": "complete",
            "routing": None,
        }
    )
    rows.append(
        {
            "id": f"msg-{uuid.uuid4().hex[:12]}",
            "role": "assistant",
            "text": assistant_text,
            "content_blocks": content_blocks or [],
            "backend_used": backend,
            "model_used": model_or_agent,
            "cost_usd": cost_usd,
            "latency_ms": latency_ms,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "created_at": _now_iso(),
            "status": "complete",
            "routing": {"rationale": rationale, "override": override},
        }
    )
    _THREADS[thread_id]["updated_at"] = _now_iso()


def _resolve_fixture(body: dict[str, Any]) -> tuple[str, str]:
    """Return (fixture_name, stripped_message).

    Selection mechanism: body.message.startswith("[fixture:NAME]"). When
    a prefix matches, the prefix is stripped before downstream handlers
    see the message; otherwise the fixture name is "default" and the
    message is returned unchanged.

    Future Plan 07 contributions follow the SAME mechanism — see the
    CANONICAL FIXTURE CATALOG comment at the top of this file (Warning 5
    lock-in for the body-prefix convention).
    """
    raw = body.get("message") or ""
    if not isinstance(raw, str):
        return "default", ""

    catalog = (
        "code-block",
        "slow",
        "missing-key",
        "auth-failed",
        "claude-code",
        "computer-use",
    )
    for name in catalog:
        prefix = f"[fixture:{name}]"
        if raw.startswith(prefix):
            stripped = raw[len(prefix):].lstrip()
            return name, stripped
    return "default", raw


def _emit_routing_decision(
    *,
    backend: str = "openrouter",
    model_or_agent: str = "openai/gpt-5",
    rationale: str = "Test routing",
    confidence: float = 0.92,
    signals: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Common routing_decision event used by every fixture.

    Defaults reproduce the Plan 01 openrouter chip verbatim so every existing
    fixture keeps its current behaviour. The keyword-only ``backend`` /
    ``model_or_agent`` / ``rationale`` overrides let the Plan 06-04 claude-code
    + computer-use fixtures emit the matching backend so MessageBubble dispatches
    to the CodeBubble / ComputerUseBubble renderers (and their GREEN / AMBER
    chips) for the screenshot capture. The 5-key payload shape is unchanged
    (chunk-schemas.ts RoutingDecisionDataSchema).
    """
    return {
        "event": "routing_decision",
        "data": json.dumps(
            {
                "backend": backend,
                "model_or_agent": model_or_agent,
                "rationale": rationale,
                "confidence": confidence,
                "signals": signals if signals is not None else _CANNED_SIGNALS,
            }
        ),
    }


def _emit_done(tokens_in: int = 3, tokens_out: int = 2, cost_usd: float = 0.0001, latency_ms: int = 42) -> dict[str, str]:
    """Common done event used by every fixture."""
    return {
        "event": "done",
        "data": json.dumps(
            {
                "type": "done",
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd": cost_usd,
                "latency_ms": latency_ms,
                "routing_signals": _CANNED_SIGNALS,
            }
        ),
    }


async def _emit_default_fixture():
    """Plan 01 fixture — 2 text_deltas + done."""
    yield _emit_routing_decision()
    for chunk in ("Hello", " world"):
        await asyncio.sleep(0.01)
        yield {
            "event": "text_delta",
            "data": json.dumps({"type": "text_delta", "text": chunk}),
        }
    yield _emit_done()


async def _emit_code_block_fixture():
    """Plan 06 fixture — routing_decision + streamed fenced ```python``` + done.

    The chunks are emitted with 50ms inter-chunk sleeps so the
    no-flicker.spec.ts MutationObserver has time to install BEFORE the
    closing fence arrives. The closing fence (chunk 6) is what triggers
    StreamingCodeBlock's one-shot shiki highlight; chunks 1-5 should
    render as plain <pre><code> with no shiki tokens.
    """
    yield _emit_routing_decision()
    chunks = (
        "Here is a Python hello world:\n\n",
        "```python\n",
        "def hello():\n",
        "    print('Hello, world!')\n",
        "\nhello()\n",
        "```\n",
    )
    for text in chunks:
        await asyncio.sleep(0.05)
        yield {
            "event": "text_delta",
            "data": json.dumps({"type": "text_delta", "text": text}),
        }
    yield _emit_done(tokens_in=7, tokens_out=30, cost_usd=0.0005, latency_ms=200)


async def _emit_slow_fixture():
    """Plan 07 fixture — slow stream for cancel-budget.spec.ts.

    Emits one text_delta every 500ms for up to 10 seconds, then Done.
    The slow path MUST honor client disconnect — the surrounding
    try/except asyncio.CancelledError lets Playwright's abort
    propagate cleanly so cancel-budget.spec.ts can measure the full
    chain (Phase 3 D-09: 2s budget end-to-end across browser → Next →
    upstream).

    Uses the STRUCTURED 5-key routing_decision payload (Plan 04 D-15).
    """
    yield _emit_routing_decision()
    try:
        for i in range(20):  # 20 * 500ms = 10 seconds max
            await asyncio.sleep(0.5)
            yield {
                "event": "text_delta",
                "data": json.dumps(
                    {"type": "text_delta", "text": f"chunk-{i} "}
                ),
            }
        yield _emit_done(
            tokens_in=5, tokens_out=20, cost_usd=0.001, latency_ms=10000
        )
    except asyncio.CancelledError:
        # Client (Next proxy) disconnected — stop emitting. Re-raise so
        # the EventSourceResponse closes the connection cleanly. This is
        # the server-side half of the AbortController chain Plan 03 wired.
        raise


async def _emit_auth_failed_fixture():
    """Plan 07 fixture — auth_failed StreamError for error-banner UAT.

    Emits routing_decision then a stream_error chunk with the
    closed-vocabulary D-06 code="auth_failed", which StreamErrorBanner
    catalog maps to "OpenRouter rejected the key. Update it in settings
    and try again." The Done frame still fires so the AI SDK runtime
    transitions the message to terminal state.
    """
    yield _emit_routing_decision()
    yield {
        "event": "stream_error",
        "data": json.dumps(
            {
                "type": "stream_error",
                "code": "auth_failed",
                "message": "OpenRouter rejected the key",
                "retriable": False,
            }
        ),
    }
    yield _emit_done(
        tokens_in=0, tokens_out=0, cost_usd=0.0, latency_ms=50
    )


# Signal dicts for the non-openrouter backends (Plan 06-04). The shape mirrors
# _CANNED_SIGNALS; only the backend-discriminating values differ. signals is a
# free-form Record per chunk-schemas.ts RoutingDecisionDataSchema, so any extra
# keys are tolerated by the chip.
_CLAUDE_CODE_SIGNALS = {
    "task_type": "coding",
    "agentic_intent": True,
    "rule_fired": "coding_task",
}
_COMPUTER_USE_SIGNALS = {
    "task_type": "agentic",
    "agentic_intent": True,
    "rule_fired": "browse_keyword",
}

# Smallest valid PNG (1x1 transparent pixel), base64-encoded. Inlined as the
# screenshot fixture's image_b64 so ComputerUseBubble.screenshotSrc resolves to
# a data: URI and the thumbnail strip renders WITHOUT any blob-proxy backend
# (the real GET /api/v1/blobs/{hash} is not served by this mock). No real
# capture data — a deterministic placeholder pixel only.
_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


async def _emit_claude_code_fixture():
    """Plan 06-04 fixture — claude_code chip + tool_call + file_diff + summary.

    Drives MessageBubble's per-backend dispatch to CodeBubble (UI-SPEC §16:
    backend == "claude_code" -> data-testid="code-bubble") so the GREEN Claude
    Code routing chip renders above a bubble that actually shows a collapsed
    tool-call chip + a red/green unified diff (CodeBubble reads data-named
    "tool_call" / "file_diff" parts off useMessage().content). Every event is a
    NAMED SSE event whose payload matches chunk-schemas.ts (ToolCallSchema /
    FileDiffSchema), so sse-translate.ts forwards each as data-<event>.
    """
    yield _emit_routing_decision(
        backend="claude_code",
        model_or_agent="claude-code",
        rationale="build-and-edit task",
        confidence=0.94,
        signals=_CLAUDE_CODE_SIGNALS,
    )
    tool_call_id = "call_finance_tracker_1"
    # tool_call (ToolCallSchema: tool_call_id + tool_name + arguments).
    yield {
        "event": "tool_call",
        "data": json.dumps(
            {
                "type": "tool_call",
                "tool_call_id": tool_call_id,
                "tool_name": "write_file",
                "arguments": {"path": "app/tracker.py", "mode": "create"},
            }
        ),
    }
    await asyncio.sleep(0.02)
    # file_diff (FileDiffSchema: tool_call_id + path + diff + operation). A full
    # unified diff WITH a @@ hunk header so CodeBubble's hand-rolled classifier
    # renders the red/green + neutral-header palette (CodeBubble.tsx:94-115).
    diff_text = (
        "--- /dev/null\n"
        "+++ b/app/tracker.py\n"
        "@@ -0,0 +1,4 @@\n"
        "+def add_expense(amount: float, category: str) -> None:\n"
        '+    """Record a single expense in the finance tracker."""\n'
        "+    expenses.append({\"amount\": amount, \"category\": category})\n"
        "+    save()\n"
    )
    yield {
        "event": "file_diff",
        "data": json.dumps(
            {
                "type": "file_diff",
                "tool_call_id": tool_call_id,
                "path": "app/tracker.py",
                "diff": diff_text,
                "operation": "create",
            }
        ),
    }
    await asyncio.sleep(0.02)
    # Terminal summary text part (CodeBubble §7.1 #3 markdown summary).
    yield {
        "event": "text_delta",
        "data": json.dumps(
            {
                "type": "text_delta",
                "text": "Created a small finance tracker with an add_expense helper.",
            }
        ),
    }
    yield _emit_done(tokens_in=18, tokens_out=64, cost_usd=0.0021, latency_ms=420)


async def _emit_computer_use_fixture():
    """Plan 06-04 fixture — computer_use chip + narration + screenshot strip.

    Drives MessageBubble's dispatch to ComputerUseBubble (UI-SPEC §16: backend
    == "computer_use" -> data-testid="computer-use-bubble") so the AMBER
    computer-use chip renders above a bubble that shows narration + a screenshot
    thumbnail. The screenshot event carries an INLINE image_b64 (1x1 PNG) so
    ComputerUseBubble.screenshotSrc returns a data: URI and the strip renders
    with no blob proxy. The done frame lands a metrics part so the bubble swaps
    "still working…" for the metrics footer (a stable shot, no live timer).
    Every event is a NAMED SSE event matching chunk-schemas.ts (ScreenshotSchema).
    """
    yield _emit_routing_decision(
        backend="computer_use",
        model_or_agent="computer-use",
        rationale="browse-and-act task",
        confidence=0.91,
        signals=_COMPUTER_USE_SIGNALS,
    )
    # Action-narration text part (ComputerUseBubble §8.1 #1).
    yield {
        "event": "text_delta",
        "data": json.dumps(
            {
                "type": "text_delta",
                "text": "Opening the page and reading the listed price…",
            }
        ),
    }
    await asyncio.sleep(0.02)
    # screenshot (ScreenshotSchema: step + image_b64 + image_format). Inline b64
    # so the thumbnail renders without the blob proxy.
    yield {
        "event": "screenshot",
        "data": json.dumps(
            {
                "type": "screenshot",
                "step": 1,
                "image_b64": _TINY_PNG_B64,
                "image_format": "png",
            }
        ),
    }
    await asyncio.sleep(0.02)
    yield _emit_done(tokens_in=22, tokens_out=18, cost_usd=0.0034, latency_ms=900)


# Dispatch table — fixture name → emitter function. Centralizing this
# avoids the long if/elif chain in the turn handler and makes it easy to
# add Plan 08+ fixtures without touching the handler body.
_FIXTURE_DISPATCH = {
    "code-block": _emit_code_block_fixture,
    "slow": _emit_slow_fixture,
    "auth-failed": _emit_auth_failed_fixture,
    "claude-code": _emit_claude_code_fixture,
    "computer-use": _emit_computer_use_fixture,
}


# Plan 08-04 — per-fixture persisted-turn shape. After a fixture finishes
# streaming, the turn is written to the in-memory store with the SAME
# backend/model/rationale/metrics/content_blocks the stream emitted, so a
# restore (GET /messages → reconstructUIMessages) reproduces the live render.
# Keyed by fixture name; "default" covers the openrouter golden path the SC-4
# spec sends. content_blocks mirrors the stored `chunk.model_dump()` shape
# (non-text chunks only — text is collapsed into `text`).
_PERSIST_SPEC: dict[str, dict[str, Any]] = {
    "default": {
        "backend": "openrouter",
        "model_or_agent": "openai/gpt-5",
        "rationale": "Test routing",
        "assistant_text": "Hello world",
        "content_blocks": [],
        "override": False,
        "tokens_in": 3,
        "tokens_out": 2,
        "cost_usd": 0.0001,
        "latency_ms": 42,
    },
    "claude-code": {
        "backend": "claude_code",
        "model_or_agent": "claude-code",
        "rationale": "build-and-edit task",
        "assistant_text": "Created a small finance tracker with an add_expense helper.",
        "content_blocks": [
            {
                "type": "tool_call",
                "tool_call_id": "call_finance_tracker_1",
                "tool_name": "write_file",
                "arguments": {"path": "app/tracker.py", "mode": "create"},
            },
            {
                "type": "file_diff",
                "tool_call_id": "call_finance_tracker_1",
                "path": "app/tracker.py",
                "diff": (
                    "--- /dev/null\n+++ b/app/tracker.py\n@@ -0,0 +1,4 @@\n"
                    "+def add_expense(amount: float, category: str) -> None:\n"
                ),
                "operation": "create",
            },
        ],
        "override": False,
        "tokens_in": 18,
        "tokens_out": 64,
        "cost_usd": 0.0021,
        "latency_ms": 420,
    },
    "computer-use": {
        "backend": "computer_use",
        "model_or_agent": "computer-use",
        "rationale": "browse-and-act task",
        "assistant_text": "Opening the page and reading the listed price…",
        "content_blocks": [
            {
                "type": "screenshot",
                "step": 1,
                "image_b64": _TINY_PNG_B64,
                "image_format": "png",
            }
        ],
        "override": False,
        "tokens_in": 22,
        "tokens_out": 18,
        "cost_usd": 0.0034,
        "latency_ms": 900,
    },
}


@app.post("/api/v1/threads/{thread_id}/turn")
async def turn(thread_id: str, request: Request) -> EventSourceResponse:
    """Dispatch to a named fixture (Warning 5 — body-prefix mechanism), then
    persist the turn into the in-memory store (Plan 08-04) so it is restorable.

    The persistence wraps the fixture generator: rows are written AFTER the
    stream is fully consumed (mirrors the real `persist_turn` on the terminal
    Done frame), so the restore read returns a complete turn."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    fixture_name, stripped = _resolve_fixture(body if isinstance(body, dict) else {})

    # The user prompt text (post-prefix-strip) is the persisted user row text.
    user_text = stripped if stripped else (
        body.get("message", "") if isinstance(body, dict) else ""
    )
    if not isinstance(user_text, str):
        user_text = ""

    event_stream = _FIXTURE_DISPATCH.get(fixture_name, _emit_default_fixture)
    spec = _PERSIST_SPEC.get(fixture_name)

    async def _stream_then_persist():
        async for event in event_stream():
            yield event
        # Persist only for fixtures with a known restorable shape (the
        # default/claude-code/computer-use happy paths). Error/slow/missing-key
        # fixtures are not persisted — they have no terminal complete turn.
        if spec is not None:
            _persist_turn(
                thread_id,
                user_text=user_text,
                backend=spec["backend"],
                model_or_agent=spec["model_or_agent"],
                rationale=spec["rationale"],
                assistant_text=spec["assistant_text"],
                content_blocks=spec["content_blocks"],
                override=spec["override"],
                tokens_in=spec["tokens_in"],
                tokens_out=spec["tokens_out"],
                cost_usd=spec["cost_usd"],
                latency_ms=spec["latency_ms"],
            )

    return EventSourceResponse(_stream_then_persist(), ping=15)


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
