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
# Named fixtures across Plans 01/06/07:
#   default                — Plan 01: routing_decision + 2 text_deltas + done
#   [fixture:code-block]   — Plan 06: routing_decision + streamed fenced
#                            ```python ... ``` + done (used by no-flicker.spec.ts)
#   [fixture:slow]         — Plan 07: routing_decision + 1 text_delta every
#                            500ms for 10s + done (used by cancel-budget.spec.ts)
#   [fixture:missing-key]  — Plan 07: healthz returns missing_key until PATCH
#                            /api/v1/settings; used by first-run.spec.ts
#   [fixture:auth-failed]  — Plan 07: routing_decision + stream_error(auth_failed)
#                            + done; used by error-banner manual UAT
# ============================================================================

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from typing import Any

from fastapi import FastAPI, Request
from sse_starlette.sse import EventSourceResponse

app = FastAPI(title="mock-fastapi")

_CANNED_SIGNALS = {
    "task_type": "chat",
    "agentic_intent": False,
    "rule_fired": "default",
}


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
async def create_thread() -> dict:
    """Auto-create a default thread on app boot."""
    return {"id": f"test-thread-{uuid.uuid4().hex[:8]}", "title": "Untitled"}


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
    """Test helper — resets the module-level missing-key flag.

    Useful for local multi-spec runs where the Playwright `webServer` is
    reused across tests (reuseExistingServer=true). first-run.spec.ts hits
    this endpoint at test start to guarantee a fresh missing-key state.
    """
    global _has_openrouter_key
    _has_openrouter_key = False
    return {"reset": True}


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

    catalog = ("code-block", "slow", "missing-key", "auth-failed")
    for name in catalog:
        prefix = f"[fixture:{name}]"
        if raw.startswith(prefix):
            stripped = raw[len(prefix):].lstrip()
            return name, stripped
    return "default", raw


def _emit_routing_decision() -> dict[str, str]:
    """Common routing_decision event used by every fixture."""
    return {
        "event": "routing_decision",
        "data": json.dumps(
            {
                "backend": "openrouter",
                "model_or_agent": "openai/gpt-5",
                "rationale": "Test routing",
                "confidence": 0.92,
                "signals": _CANNED_SIGNALS,
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


# Dispatch table — fixture name → emitter function. Centralizing this
# avoids the long if/elif chain in the turn handler and makes it easy to
# add Plan 08+ fixtures without touching the handler body.
_FIXTURE_DISPATCH = {
    "code-block": _emit_code_block_fixture,
    "slow": _emit_slow_fixture,
    "auth-failed": _emit_auth_failed_fixture,
}


@app.post("/api/v1/threads/{thread_id}/turn")
async def turn(thread_id: str, request: Request) -> EventSourceResponse:  # noqa: ARG001
    """Dispatch to a named fixture (Warning 5 — body-prefix mechanism)."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    fixture_name, _stripped = _resolve_fixture(body if isinstance(body, dict) else {})

    event_stream = _FIXTURE_DISPATCH.get(fixture_name, _emit_default_fixture)
    return EventSourceResponse(event_stream(), ping=15)


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
