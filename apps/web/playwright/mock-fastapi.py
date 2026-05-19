"""Mock FastAPI server for Playwright CI runs.

Emits a canned 4-event SSE sequence so the web-test.yml workflow can exercise
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

from __future__ import annotations

import argparse
import asyncio
import json
import uuid

from fastapi import FastAPI
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


@app.post("/api/v1/threads/{thread_id}/turn")
async def turn(thread_id: str) -> EventSourceResponse:  # noqa: ARG001
    """Emit the canned 4-event SSE sequence."""

    async def event_stream():
        yield {
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
        # Mid-stream tokens
        for chunk in ("Hello", " world"):
            await asyncio.sleep(0.01)
            yield {
                "event": "text_delta",
                "data": json.dumps({"type": "text_delta", "text": chunk}),
            }
        yield {
            "event": "done",
            "data": json.dumps(
                {
                    "type": "done",
                    "tokens_in": 3,
                    "tokens_out": 2,
                    "cost_usd": 0.0001,
                    "latency_ms": 42,
                    "routing_signals": _CANNED_SIGNALS,
                }
            ),
        }

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
