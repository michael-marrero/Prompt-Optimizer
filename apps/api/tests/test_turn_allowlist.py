"""Phase 5 Wave 0 — RED tests for the D-05 routing allowlist filter (UI-12/D-05..D-07).

Net-new server seam: ``decide()`` is post-filtered in ``apps/api/routes/turn.py``
so a turn whose auto-routed decision picks a *disabled* backend is silently
rerouted to the best *enabled* backend (OpenRouter is the floor). The filter:
    - D-05: never dispatches to a backend disabled in ``settings.backends_enabled``.
    - D-07: the reroute is silent — the chip rationale must NOT contain "disabled"
      or "user override" (it reads as a normal auto-route for the backend used).
    - Pitfall 7 / D-01: an explicit ``override_backend`` turn is NEVER rerouted —
      the user's manual pick wins even if that backend is disabled.
    - D-06: computer_use stays unreachable on an auto turn unless env
      ``COMPUTER_USE_OPT_IN=1`` AND ``settings.computer_use_opt_in`` are BOTH true.

The allowlist filter does not exist yet — these tests are RED until 05-02 wires
it into turn.py. RED mechanism: the assertions describe the post-filter behavior;
against the current turn.py (no filter) a claude_code decision dispatches to a
missing claude_code adapter / is logged with backend=claude_code, so the
reroute-to-openrouter assertions FAIL.

All tests use httpx.AsyncClient + ASGITransport (API-08 / D-20) and consume the
SSE stream with the finite break-on-``event: done`` pattern (Pitfall 4).

Cross-refs:
    - 05-PATTERNS.md "apps/api/routes/turn.py (extend: D-05 allowlist)"
    - apps/api/settings.py:computer_use_enabled (D-06 STRICT-AND helper)
    - apps/api/tests/test_turn_streaming.py (turn harness this mirrors)
    - 05-CONTEXT.md D-05/D-06/D-07 + Pitfall 7
"""

from __future__ import annotations

import importlib
import json
import sys
import typing

import httpx
import pytest
from httpx import ASGITransport


def _fresh_app(monkeypatch: pytest.MonkeyPatch, tmp_path) -> typing.Any:
    """Reload paths + turn + main under tmp_path; purge sse_starlette (Wave 4
    reload-chain interaction with the D-18 smoke test)."""

    monkeypatch.setenv("PROMPT_OPTIMIZER_HOME", str(tmp_path))
    for name in list(sys.modules):
        if name.startswith("sse_starlette"):
            del sys.modules[name]

    import apps.api.paths

    importlib.reload(apps.api.paths)
    import apps.api.jsonl_log

    importlib.reload(apps.api.jsonl_log)
    import apps.api.lifespan

    importlib.reload(apps.api.lifespan)
    import apps.api.routes.turn

    importlib.reload(apps.api.routes.turn)
    import apps.api.main

    importlib.reload(apps.api.main)
    return apps.api.main.create_app()


def _pin_decide(monkeypatch, backend: str) -> None:
    """Force decide() to return a decision for ``backend``."""

    from src.routing.schema import RoutingDecision

    def fake_decide(*args, **kwargs):
        return RoutingDecision(
            backend=backend,
            model_or_agent=backend if backend != "openrouter" else "openai/gpt-5",
            rationale="auto-routed pick",
            confidence=0.9,
            signals={"task_type": "coding" if backend == "claude_code" else "chat"},
        )

    monkeypatch.setattr("apps.api.routes.turn.decide", fake_decide)


def _fake_adapters():
    """Two distinguishable fakes so we can tell which backend was dispatched."""

    from apps.api.backends.chunks import Done, TextDelta
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    def make(tag: str):
        return FakeStreamingAdapter(
            [
                TextDelta(text=f"{tag}-response"),
                Done(tokens_in=1, tokens_out=1, cost_usd=0.001, latency_ms=5),
            ]
        )

    return {"openrouter": make("openrouter"), "claude_code": make("claude_code")}


async def _create_thread(client) -> str:
    resp = await client.post("/api/v1/threads", json={"title": "allow"})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def _read_jsonl_backend(tmp_path) -> str:
    """Return the backend recorded in the latest routing_decisions.jsonl row."""

    import apps.api.paths

    path = apps.api.paths.JSONL_LOG_PATH
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return json.loads(lines[-1])


async def test_disabled_backend_auto_turn_rerouted_to_openrouter(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """D-05/D-07: auto decision=claude_code with claude_code disabled →
    silently rerouted to openrouter; rationale has no 'disabled'/'user override'."""

    app = _fresh_app(monkeypatch, tmp_path)
    _pin_decide(monkeypatch, "claude_code")
    app.state.adapters = _fake_adapters()
    app.state.settings = {
        "default_max_cost_usd": 0.50,
        "backends_enabled": {
            "openrouter": True,
            "claude_code": False,
            "computer_use": False,
        },
        "computer_use_opt_in": False,
    }

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            async with client.stream(
                "POST",
                f"/api/v1/threads/{thread_id}/turn",
                json={"message": "build me a finance app"},
            ) as resp:
                assert resp.status_code == 200, resp.text
                async for line in resp.aiter_lines():
                    if line.startswith("event: done"):
                        break

        row = await _read_jsonl_backend(tmp_path)

    # D-05: the recorded backend is the enabled floor, NOT the disabled pick.
    assert row["backend"] == "openrouter", (
        f"D-05 BREACH: dispatched to disabled backend: {row['backend']}"
    )
    # D-07: the reroute is silent — rationale reads as a normal auto-route.
    rationale = str(row.get("rationale", "")).lower()
    assert "disabled" not in rationale, f"D-07 BREACH: noisy rationale {rationale!r}"
    assert "user override" not in rationale, (
        f"D-07 BREACH: reroute mislabeled as override: {rationale!r}"
    )


async def test_override_backend_not_rerouted_even_when_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Pitfall 7: an explicit override_backend=claude_code is NEVER rerouted,
    even with claude_code disabled in settings (the user's manual pick wins)."""

    app = _fresh_app(monkeypatch, tmp_path)
    # decide() must NOT run on an override turn — make it explode if called.
    def boom(*args, **kwargs):  # pragma: no cover - asserts it is not called
        raise AssertionError("decide() ran on an override turn")

    monkeypatch.setattr("apps.api.routes.turn.decide", boom)
    app.state.adapters = _fake_adapters()
    app.state.settings = {
        "default_max_cost_usd": 0.50,
        "backends_enabled": {
            "openrouter": True,
            "claude_code": False,
            "computer_use": False,
        },
        "computer_use_opt_in": False,
    }

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            async with client.stream(
                "POST",
                f"/api/v1/threads/{thread_id}/turn",
                json={"message": "build me a finance app", "override_backend": "claude_code"},
            ) as resp:
                assert resp.status_code == 200, resp.text
                async for line in resp.aiter_lines():
                    if line.startswith("event: done"):
                        break

        row = await _read_jsonl_backend(tmp_path)

    assert row["backend"] == "claude_code", (
        f"Pitfall 7 BREACH: override pick was rerouted to {row['backend']}"
    )


async def test_computer_use_unreachable_on_auto_turn_without_strict_and(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """D-06 STRICT-AND: an auto decision=computer_use is unreachable unless env
    COMPUTER_USE_OPT_IN=1 AND settings.computer_use_opt_in. With both false the
    auto turn reroutes to the enabled floor (openrouter), never computer_use."""

    monkeypatch.delenv("COMPUTER_USE_OPT_IN", raising=False)
    app = _fresh_app(monkeypatch, tmp_path)
    _pin_decide(monkeypatch, "computer_use")
    app.state.adapters = _fake_adapters()  # no computer_use adapter registered
    app.state.settings = {
        "default_max_cost_usd": 0.50,
        "backends_enabled": {
            "openrouter": True,
            "claude_code": True,
            "computer_use": True,  # enabled in the toggle, but env gate is OFF
        },
        "computer_use_opt_in": False,  # settings gate OFF → STRICT-AND fails
    }

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            async with client.stream(
                "POST",
                f"/api/v1/threads/{thread_id}/turn",
                json={"message": "open this URL and check the price"},
            ) as resp:
                assert resp.status_code == 200, resp.text
                async for line in resp.aiter_lines():
                    if line.startswith("event: done"):
                        break

        row = await _read_jsonl_backend(tmp_path)

    assert row["backend"] != "computer_use", (
        "D-06 BREACH: computer_use reachable on auto turn without STRICT-AND"
    )
    assert row["backend"] == "openrouter", (
        f"D-06: expected reroute to openrouter floor, got {row['backend']}"
    )
