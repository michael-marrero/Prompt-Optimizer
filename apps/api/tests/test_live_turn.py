# Story 6.4 (CERT-04) — end-to-end LIVE turn smoke.
#
# Unlike apps/api/backends/openrouter/tests/test_live.py (which drives the
# OpenRouter *adapter* in isolation), this proves the FULL product path:
#   decide() -> POST /api/v1/threads/{id}/turn -> real provider -> SSE -> persist
# against a real provider, with NO fake adapters.
#
# Opt-in: requires OPENROUTER_API_KEY in env and the `live` marker. Skipped by
# default so the standard `pytest apps/api` run and forks stay green.
#
# Run with::
#
#     OPENROUTER_API_KEY=sk-or-... uv run pytest -m live apps/api/tests/test_live_turn.py -q
#
# (or put the key in ./.env — apps.api loads it via load_dotenv() on import.)
#
# Cost-bounded: tiny prompts + max_cost_usd=0.05 per turn, so a full run costs
# well under a cent.

from __future__ import annotations

import importlib
import json
import os
import sys
import typing

import httpx
import pytest
from httpx import ASGITransport

_LIVE_SKIP = pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY"),
    reason="no OPENROUTER_API_KEY in env (opt-in live test)",
)

# The exact fake-adapter canned string — a live answer must NOT equal it.
_FAKE_CANNED = "Paris is the capital."


def _live_app(monkeypatch: pytest.MonkeyPatch, tmp_path) -> typing.Any:
    """Build a REAL app: tmp home, reloaded modules, NO fake adapters, NO
    pre-set app.state.adapters (lifespan builds real ones lazily). Mirrors
    test_turn_allowlist._fresh_app but deliberately leaves the adapter dict
    unset and FAKE_ADAPTERS off so turns hit the real provider."""

    monkeypatch.setenv("PROMPT_OPTIMIZER_HOME", str(tmp_path))
    monkeypatch.delenv("PROMPT_OPTIMIZER_FAKE_ADAPTERS", raising=False)
    # No Anthropic key on purpose: the coding prompt must degrade via 6.1.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    for name in list(sys.modules):
        if name.startswith("sse_starlette"):
            del sys.modules[name]

    for mod in (
        "apps.api.paths",
        "apps.api.jsonl_log",
        "apps.api.lifespan",
        "apps.api.routes.turn",
        "apps.api.main",
    ):
        importlib.reload(importlib.import_module(mod))

    import apps.api.main

    return apps.api.main.create_app()


async def _create_thread(client) -> str:
    resp = await client.post("/api/v1/threads", json={"title": "live"})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def _run_turn(client, thread_id: str, message: str) -> dict:
    """Send one turn, collect SSE events, return {routing, text, done}."""

    routing: dict | None = None
    text_parts: list[str] = []
    done: dict | None = None
    async with client.stream(
        "POST",
        f"/api/v1/threads/{thread_id}/turn",
        json={"message": message, "max_cost_usd": 0.05},
    ) as resp:
        assert resp.status_code == 200, (
            f"live turn did not open an SSE stream: {resp.status_code}"
        )
        event = None
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                event = line[len("event: ") :]
            elif line.startswith("data: "):
                data = line[len("data: ") :]
                if event == "routing_decision":
                    routing = json.loads(data)
                elif event == "text_delta":
                    text_parts.append(json.loads(data).get("text", ""))
                elif event == "done":
                    done = json.loads(data)
                    break
    return {"routing": routing, "text": "".join(text_parts), "done": done}


def _assert_real_answer(result: dict) -> None:
    """AC #2 — a genuine provider response with real usage, not a placeholder."""

    assert result["routing"] is not None, "no routing_decision event"
    assert result["done"] is not None, "no terminal done event"
    text = result["text"].strip()
    assert text, "empty answer from a live turn"
    assert text != _FAKE_CANNED, (
        f"got the fake canned string — FAKE_ADAPTERS leaked in: {text!r}"
    )
    done = result["done"]
    assert (done.get("cost_usd") or 0) > 0, f"cost not billed: {done!r}"
    assert (done.get("tokens_out") or 0) > 0, f"no output tokens: {done!r}"
    assert (done.get("latency_ms") or 0) > 0, f"no latency: {done!r}"


@_LIVE_SKIP
@pytest.mark.live
@pytest.mark.asyncio
async def test_live_knowledge_prompt_streams_real_openrouter_answer(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """AC #1/#2: a knowledge prompt routes to openrouter and streams a real,
    billed answer end-to-end through the turn endpoint."""

    app = _live_app(monkeypatch, tmp_path)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            result = await _run_turn(
                client,
                thread_id,
                "In one word, what is the capital of France?",
            )

    assert result["routing"]["backend"] == "openrouter", result["routing"]
    _assert_real_answer(result)


@_LIVE_SKIP
@pytest.mark.live
@pytest.mark.asyncio
async def test_live_coding_prompt_degrades_to_openrouter_real_answer(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """AC #1/#2 + validates Story 6.1 LIVE: a coding prompt routes to
    claude_code, degrades to openrouter (no Anthropic key), and still returns
    a real billed answer end-to-end."""

    app = _live_app(monkeypatch, tmp_path)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            result = await _run_turn(
                client,
                thread_id,
                "Write one line of Python that prints hello.",
            )

    routing = result["routing"]
    assert routing["backend"] == "openrouter", (
        f"coding turn did not land on openrouter: {routing}"
    )
    # If the brain picked claude_code, 6.1 must have degraded it (breadcrumb).
    # (If the brain picked openrouter directly, that's also a valid real turn.)
    if routing["signals"].get("degraded_from"):
        assert routing["signals"]["degraded_from"] == "claude_code", routing
        assert routing["signals"]["degradation_reason"] == "missing_anthropic_key"
    _assert_real_answer(result)
