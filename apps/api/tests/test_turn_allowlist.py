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


# ---------------------------------------------------------------------------
# Story 1.1 (DEF-1a) — guard the ``rerouted_from`` breadcrumb.
#
# The reroute at ``turn.py::_synthesize_reroute_decision`` already preserves the
# brain's original pick in ``signals`` so the offline retrain dataset (Epic 3)
# can reconstruct the route the brain WANTED, not just the one dispatched. These
# tests lock that behavior in both sinks (JSONL + DB) so it cannot silently
# regress — without them, deleting the breadcrumb line keeps every test above
# green.
# ---------------------------------------------------------------------------


async def _read_db_signals() -> dict:
    """Return the parsed ``signals`` JSON of the latest routing_decisions row.

    Reads the module-global ``apps.api.paths.DB_PATH`` (repointed under the
    per-test tmp home by ``_fresh_app``), so no path argument is needed.
    """

    import sqlite3

    import apps.api.paths

    con = sqlite3.connect(str(apps.api.paths.DB_PATH))
    try:
        cur = con.execute(
            "SELECT signals FROM routing_decisions ORDER BY rowid DESC LIMIT 1"
        )
        found = cur.fetchone()
    finally:
        con.close()
    assert found is not None, "no routing_decisions row was persisted"
    return json.loads(found[0])


async def test_reroute_preserves_original_pick_in_signals(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """DEF-1a: an allowlist reroute must preserve the brain's original pick —
    ``rerouted_from`` (backend) + ``rerouted_from_model`` (model) plus the
    original per-stage telemetry — in BOTH the JSONL sink and the DB signals
    column, and must NOT set ``override`` (a reroute is a neutral auto-route,
    D-07)."""

    app = _fresh_app(monkeypatch, tmp_path)
    # Original brain pick: claude_code backend with a DISTINCT model, so the
    # guard proves rerouted_from (backend) and rerouted_from_model (model) are
    # captured SEPARATELY — a copy-paste regression to original.backend fails.
    # Seed ``override`` so the ``"override" not in signals`` assertions below
    # actually exercise the ``signals.pop("override")`` strip in
    # _synthesize_reroute_decision (D-07) — without it those asserts are vacuous.
    from src.routing.schema import RoutingDecision

    def _fake_decide(*args, **kwargs):
        return RoutingDecision(
            backend="claude_code",
            model_or_agent="anthropic/claude-sonnet-4-5",
            rationale="auto-routed pick",
            confidence=0.9,
            signals={"task_type": "coding", "override": True},
        )

    monkeypatch.setattr("apps.api.routes.turn.decide", _fake_decide)
    app.state.adapters = _fake_adapters()
    app.state.settings = {
        "default_max_cost_usd": 0.50,
        "backends_enabled": {
            "openrouter": True,
            "claude_code": False,  # brain's pick is disabled → reroute fires
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

        jsonl_record = await _read_jsonl_backend(tmp_path)
        db_signals = await _read_db_signals()

    # Sanity: the reroute actually happened (dispatched = enabled floor).
    assert jsonl_record["backend"] == "openrouter"

    # AC #2 — the offline JSONL sink carries the original pick.
    jsonl_signals = jsonl_record["signals"]
    assert jsonl_signals.get("rerouted_from") == "claude_code", (
        f"DEF-1a BREACH: original backend not recoverable from JSONL: {jsonl_signals!r}"
    )
    assert jsonl_signals.get("rerouted_from_model") == "anthropic/claude-sonnet-4-5", (
        f"DEF-1a BREACH: original model not recoverable from JSONL: {jsonl_signals!r}"
    )
    assert jsonl_signals.get("task_type") == "coding", (
        "DEF-1a BREACH: original per-stage telemetry lost on reroute"
    )
    assert "override" not in jsonl_signals, "D-07 BREACH: reroute mislabeled as override"

    # AC #1 — the DB signals column carries the same breadcrumb (mirror the
    # full JSONL assertion set: backend, distinct model, telemetry, no override).
    assert db_signals.get("rerouted_from") == "claude_code", (
        f"DEF-1a BREACH: original backend not recoverable from DB: {db_signals!r}"
    )
    assert db_signals.get("rerouted_from_model") == "anthropic/claude-sonnet-4-5", (
        f"DEF-1a BREACH: original model not recoverable from DB: {db_signals!r}"
    )
    assert db_signals.get("task_type") == "coding", (
        "DEF-1a BREACH: original per-stage telemetry lost from DB signals"
    )
    assert "override" not in db_signals, "D-07 BREACH: reroute mislabeled as override in DB"


async def test_no_reroute_leaves_no_breadcrumb(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """AC #3: when the brain's pick IS enabled (no reroute), no ``rerouted_from``
    breadcrumb is added — the breadcrumb marks an actual reroute only."""

    app = _fresh_app(monkeypatch, tmp_path)
    _pin_decide(monkeypatch, "openrouter")  # enabled → no reroute
    app.state.adapters = _fake_adapters()
    app.state.settings = {
        "default_max_cost_usd": 0.50,
        "backends_enabled": {
            "openrouter": True,
            "claude_code": True,
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
                json={"message": "tell me a joke"},
            ) as resp:
                assert resp.status_code == 200, resp.text
                async for line in resp.aiter_lines():
                    if line.startswith("event: done"):
                        break

        jsonl_record = await _read_jsonl_backend(tmp_path)

    assert jsonl_record["backend"] == "openrouter"
    assert "rerouted_from" not in jsonl_record["signals"], (
        "false breadcrumb: rerouted_from present on a non-reroute turn"
    )
    assert "rerouted_from_model" not in jsonl_record["signals"]


# ---------------------------------------------------------------------------
# Story 6.1 — BYOK degradation when the routed backend's Anthropic key is
# absent. AUTO turns only (mirrors the D-05 allowlist gating): coding
# degrades to a real OpenRouter answer; browse returns a targeted guidance
# turn (a chat model cannot fake live browsing). Explicit override turns keep
# their existing missing-key 400 (Pitfall 7 — see
# test_turn_streaming.py::test_missing_anthropic_key_returns_400_not_500).
# ---------------------------------------------------------------------------


async def _collect_sse_events(resp) -> list[tuple[str, str]]:
    """Read an SSE response into a list of (event, data) pairs (finite —
    stops after the terminal ``done`` event, Pitfall 4)."""

    events: list[tuple[str, str]] = []
    event = None
    async for line in resp.aiter_lines():
        if line.startswith("event: "):
            event = line[len("event: ") :]
        elif line.startswith("data: "):
            events.append((event or "", line[len("data: ") :]))
            if event == "done":
                break
    return events


def _pin_decide_with_model(monkeypatch, backend: str, model: str) -> None:
    """Force decide() to return a decision for ``backend`` with a DISTINCT
    ``model`` so the degraded_from_model breadcrumb is provably captured."""

    from src.routing.schema import RoutingDecision

    def fake_decide(*args, **kwargs):
        return RoutingDecision(
            backend=backend,
            model_or_agent=model,
            rationale="auto-routed pick",
            confidence=0.9,
            signals={"task_type": "coding"},
        )

    monkeypatch.setattr("apps.api.routes.turn.decide", fake_decide)


async def test_missing_anthropic_key_degrades_claude_code_to_openrouter(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """AC #1–3: auto decision=claude_code with NO Anthropic key (but
    claude_code enabled, so the allowlist does NOT pre-reroute) degrades to
    OpenRouter, streams a real answer, and records honest degraded_from*
    breadcrumbs in both sinks — distinct from the D-05 rerouted_from key."""

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app = _fresh_app(monkeypatch, tmp_path)
    _pin_decide_with_model(monkeypatch, "claude_code", "anthropic/claude-sonnet-4-5")
    app.state.adapters = _fake_adapters()  # fake openrouter answers the degrade
    app.state.settings = {
        "default_max_cost_usd": 0.50,
        "backends_enabled": {
            "openrouter": True,
            "claude_code": True,  # ENABLED → allowlist won't reroute; 6.1 must
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
                json={"message": "write me a mergesort with tests"},
            ) as resp:
                assert resp.status_code == 200, resp.text
                events = await _collect_sse_events(resp)

        jsonl_record = await _read_jsonl_backend(tmp_path)
        db_signals = await _read_db_signals()

    # AC #1 — dispatched to openrouter and streamed a real answer.
    assert jsonl_record["backend"] == "openrouter", (
        f"6.1 BREACH: coding did not degrade to openrouter: {jsonl_record['backend']}"
    )
    text = "".join(
        json.loads(d)["text"] for e, d in events if e == "text_delta"
    )
    assert "openrouter-response" in text, (
        f"6.1 BREACH: no real answer streamed after degrade; got {text!r}"
    )

    # AC #2 — honest breadcrumbs in BOTH sinks, distinct from rerouted_from.
    for label, sig in (("JSONL", jsonl_record["signals"]), ("DB", db_signals)):
        assert sig.get("degraded_from") == "claude_code", f"{label}: {sig!r}"
        assert sig.get("degraded_from_model") == "anthropic/claude-sonnet-4-5", (
            f"{label}: degraded_from_model not captured: {sig!r}"
        )
        assert sig.get("degradation_reason") == "missing_anthropic_key", (
            f"{label}: {sig!r}"
        )
        # A key-degradation is NOT an allowlist reroute — do not mislabel it.
        assert "rerouted_from" not in sig, f"{label}: mislabeled as reroute {sig!r}"

    # AC #2 — rationale is honest about the missing key.
    assert "anthropic key absent" in str(jsonl_record["rationale"]).lower()

    # AC #3 — the degraded route resolves to a task-appropriate OpenRouter
    # target (openrouter/auto — OpenRouter's own router picks the model).
    assert jsonl_record["model_or_agent"] == "openrouter/auto", jsonl_record

    # AC #1 — the SSE stream opens with a routing_decision event carrying the
    # degraded backend so the chip renders openrouter, not claude_code.
    rd = next(
        (json.loads(d) for e, d in events if e == "routing_decision"), None
    )
    assert rd is not None and rd["backend"] == "openrouter", rd


async def test_missing_anthropic_key_computer_use_returns_guidance_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """AC #4: auto decision=computer_use with NO Anthropic key returns a
    successful guidance turn (not a 400, not a chat answer, no provider call).
    backend stays computer_use with a block breadcrumb; the assistant message
    is the fixed guidance string; cost is 0."""

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Strict-AND must PASS (env + settings) so computer_use survives the D-05
    # allowlist and reaches the 6.1 key check — otherwise it would reroute to
    # openrouter as a disabled backend (that opted-out path is D-06's test).
    monkeypatch.setenv("COMPUTER_USE_OPT_IN", "1")
    app = _fresh_app(monkeypatch, tmp_path)
    _pin_decide(monkeypatch, "computer_use")
    # NO computer_use adapter registered — a guidance turn must never build or
    # call one. If the canned path regressed, dispatch would 400/500 here.
    app.state.adapters = {"openrouter": _fake_adapters()["openrouter"]}
    app.state.settings = {
        "default_max_cost_usd": 0.50,
        "backends_enabled": {
            "openrouter": True,
            "claude_code": True,
            "computer_use": True,
        },
        "computer_use_opt_in": True,
    }

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            async with client.stream(
                "POST",
                f"/api/v1/threads/{thread_id}/turn",
                json={"message": "go to bloomberg.com and give me the top 3 headlines"},
            ) as resp:
                assert resp.status_code == 200, resp.text
                events = await _collect_sse_events(resp)

        jsonl_record = await _read_jsonl_backend(tmp_path)
        db_signals = await _read_db_signals()

    # backend stays computer_use on the record, with a block breadcrumb in
    # BOTH sinks (mirror the coding test's two-sink check).
    assert jsonl_record["backend"] == "computer_use", jsonl_record
    for label, sig in (("JSONL", jsonl_record["signals"]), ("DB", db_signals)):
        assert sig.get("block_reason") == "missing_anthropic_key", f"{label}: {sig!r}"
        assert sig.get("blocked_backend") == "computer_use", f"{label}: {sig!r}"

    # The assistant message is the fixed guidance string (not a chat answer).
    text = "".join(
        json.loads(d)["text"] for e, d in events if e == "text_delta"
    )
    assert "computer-use" in text.lower() and "anthropic api key" in text.lower(), (
        f"6.1 BREACH: expected browse guidance, got {text!r}"
    )
    assert "openrouter-response" not in text, "browse must NOT be faked by a chat model"

    # Terminal done with zero cost (no provider call was billed).
    done = next((json.loads(d) for e, d in events if e == "done"), None)
    assert done is not None and done.get("cost_usd") == 0.0, done


async def test_present_anthropic_key_does_not_degrade(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """AC #5: with the Anthropic key present, an auto claude_code turn
    dispatches to claude_code unchanged — no degradation path fires."""

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-present")
    app = _fresh_app(monkeypatch, tmp_path)
    _pin_decide(monkeypatch, "claude_code")
    app.state.adapters = _fake_adapters()  # fake claude_code answers directly
    app.state.settings = {
        "default_max_cost_usd": 0.50,
        "backends_enabled": {
            "openrouter": True,
            "claude_code": True,
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
                json={"message": "write me a mergesort with tests"},
            ) as resp:
                assert resp.status_code == 200, resp.text
                async for line in resp.aiter_lines():
                    if line.startswith("event: done"):
                        break

        jsonl_record = await _read_jsonl_backend(tmp_path)

    assert jsonl_record["backend"] == "claude_code", (
        f"6.1 BREACH: degraded despite a present key: {jsonl_record['backend']}"
    )
    assert "degraded_from" not in jsonl_record["signals"], jsonl_record


async def test_coding_degrade_blocked_when_openrouter_also_keyless_still_400(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """AC #6: if a coding turn degrades to openrouter but openrouter ALSO has
    no key, the failure stays a clean pre-stream 400 (not a 500, not a silent
    wrong answer)."""

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    app = _fresh_app(monkeypatch, tmp_path)
    _pin_decide(monkeypatch, "claude_code")
    app.state.adapters = {}  # no fakes → real adapter build trips the pre-check
    app.state.settings = {
        "default_max_cost_usd": 0.50,
        "backends_enabled": {
            "openrouter": True,
            "claude_code": True,
            "computer_use": False,
        },
        "computer_use_opt_in": False,
    }

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            resp = await client.post(
                f"/api/v1/threads/{thread_id}/turn",
                json={"message": "write me a mergesort with tests"},
            )

    assert resp.status_code == 400, (
        f"AC #6 BREACH: openrouter-also-keyless degrade should be a clean 400, "
        f"got {resp.status_code}: {resp.text}"
    )
    detail = resp.json().get("detail", "")
    assert "openrouter" in detail and "OPENROUTER_API_KEY" in detail, detail


async def test_degrade_skipped_when_openrouter_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Code-review (Blind Hunter, Med): the coding degrade must NOT dispatch
    to openrouter when the user has DISABLED it. With openrouter disabled but
    claude_code enabled and no Anthropic key, the turn must not silently
    answer from the turned-off backend (D-05 invariant) — it falls through to
    the honest claude_code missing-key 400."""

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app = _fresh_app(monkeypatch, tmp_path)
    _pin_decide(monkeypatch, "claude_code")
    # ONLY a fake openrouter adapter is registered (no claude_code fake): if
    # the degrade wrongly fired, it would dispatch to this openrouter fake and
    # return 200 — this test would catch that. With the guard, claude_code
    # stays and its real adapter build trips the missing-key pre-check → 400.
    app.state.adapters = {"openrouter": _fake_adapters()["openrouter"]}
    app.state.settings = {
        "default_max_cost_usd": 0.50,
        "backends_enabled": {
            "openrouter": False,  # user turned openrouter OFF
            "claude_code": True,
            "computer_use": False,
        },
        "computer_use_opt_in": False,
    }

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            resp = await client.post(
                f"/api/v1/threads/{thread_id}/turn",
                json={"message": "write me a mergesort with tests"},
            )

    # Must NOT be a 200 streamed from the disabled openrouter backend.
    assert resp.status_code == 400, (
        f"D-05 BREACH: degraded to a DISABLED backend instead of a clean 400; "
        f"got {resp.status_code}: {resp.text}"
    )
    detail = resp.json().get("detail", "")
    assert "claude_code" in detail and "ANTHROPIC_API_KEY" in detail, detail
