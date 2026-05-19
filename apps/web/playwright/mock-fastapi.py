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


@app.get("/api/v1/healthz")
async def healthz() -> dict:
    """Stub adapter-status endpoint — mirrors apps/api/routes/health.py shape."""
    return {
        "ok": True,
        "adapters": {
            "openrouter": {"status": "ready"},
            "claude_code": {"status": "missing_key"},
            "computer_use": {"status": "opt_out"},
        },
    }


@app.post("/api/v1/threads")
async def create_thread() -> dict:
    """Auto-create a default thread on app boot."""
    return {"id": f"test-thread-{uuid.uuid4().hex[:8]}", "title": "Untitled"}


@app.patch("/api/v1/settings")
async def patch_settings() -> dict:
    """Pretend the key save worked; return only the masked form."""
    return {
        "keys": {
            "openrouter": {"present": True, "masked": "sk-or-…ABC"},
        }
    }


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


@app.post("/api/v1/threads/{thread_id}/turn")
async def turn(thread_id: str, request: Request) -> EventSourceResponse:  # noqa: ARG001
    """Dispatch to a named fixture (Warning 5 — body-prefix mechanism)."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    fixture_name, _stripped = _resolve_fixture(body if isinstance(body, dict) else {})

    if fixture_name == "code-block":
        event_stream = _emit_code_block_fixture
    else:
        event_stream = _emit_default_fixture

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
