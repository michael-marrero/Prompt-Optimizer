"""Wave 4 SSE turn handler tests — POST /api/v1/threads/{id}/turn.

Nine async tests covering the full Phase 3 SSE surface
(API-02 + API-05 + API-06 + API-07 + STORE-05 + STORE-06):

    test_streams_chatchunks                The happy-path stream:
                                           text_delta events arrive
                                           in order; the last named
                                           event is ``done``;
                                           Content-Type is
                                           ``text/event-stream``.

    test_decide_runs_in_thread             Monkeypatch
                                           ``apps.api.routes.turn.asyncio.to_thread``
                                           to a counter; assert
                                           ``decide()`` was called via
                                           ``to_thread`` exactly once
                                           (API-07 / D-16).

    test_heartbeat_emits                   Override the route's
                                           EventSourceResponse to use
                                           ``ping=1`` for the test; the
                                           FakeStreamingAdapter sleeps
                                           1.5s before yielding so the
                                           heartbeat ``:`` comment line
                                           fires (API-05 / Pattern 7).

    test_cancellation_within_2s            The API-06 budget test:
                                           consumer task.cancel() must
                                           release the stream within 2s
                                           wall-clock (Pitfall 6 — uses
                                           task.cancel(), NOT
                                           ``aclose``).

    test_one_transaction_per_turn          After a full POST-turn:
                                           SELECT COUNT(*) FROM
                                           messages WHERE thread_id=?
                                           returns 2 (user + assistant);
                                           1 routing_decisions row;
                                           assistant content_blocks
                                           contains the ToolCall but
                                           NOT the TextDelta (collapsed
                                           into messages.text) — D-04 /
                                           STORE-05.

    test_jsonl_log_appended                With JSONL_LOG_PATH pointed
                                           to a tmp file; POST a turn;
                                           assert exactly 1 line with
                                           the eight canonical keys —
                                           D-05 / STORE-06.

    test_override_backend                  Monkeypatch decide() to
                                           raise; POST with
                                           ``{"override_backend":
                                           "openrouter"}``; assert the
                                           turn returns 200 (decide
                                           skipped) and the jsonl line
                                           has ``rationale="user
                                           override"`` — Pattern 11.

    test_computer_use_gated_when_opt_out   Settings.opt_in=False AND
                                           env unset; POST with
                                           ``override_backend=
                                           "computer_use"``; assert
                                           400 BEFORE the SSE response
                                           opens — D-08 + D-12.

    test_unknown_thread_returns_404        POST to a non-existent
                                           thread returns 404 — pre-
                                           stream HTTPException path.

All tests use ``httpx.AsyncClient + ASGITransport`` (D-20 / API-08).
All streaming consumes use the finite break-on-event:done pattern
(RESEARCH Pitfall 4) so ASGITransport never hangs in CI.

Cross-refs:
    - 03-CONTEXT.md API-02..07 + STORE-05/06
    - 03-RESEARCH.md §"Pattern 6" lines 457-515 (httpx + ASGITransport
      finite-consume + break-on-done)
    - 03-RESEARCH.md §"Pattern 7" lines 517-543 (heartbeat assertion)
    - 03-RESEARCH.md §"Pitfall 4" lines 935-939 (finite consume)
    - 03-RESEARCH.md §"Pitfall 5" lines 941-945 (heartbeat monkeypatch)
    - 03-RESEARCH.md §"Pitfall 6" lines 946-951 (cancellation via
      task.cancel under ASGITransport, NOT response close)
    - 03-VALIDATION.md rows 3-04-01..06 lines 55-60
    - apps/api/backends/tests/test_adapter_contract.py lines 103-130
      (Phase 2 D-19 cancellation pattern this test mirrors)
"""

from __future__ import annotations

import asyncio
import importlib
import json
import time

import httpx
import pytest
from httpx import ASGITransport
from sse_starlette.sse import EventSourceResponse


# ---------------------------------------------------------------------
# Helpers — fresh app under tmp_path; reload chain matches Wave 3.
# ---------------------------------------------------------------------


def _fresh_app(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Reload ``apps.api.paths`` under ``tmp_path`` and build a fresh app.

    Mirrors ``test_threads_crud.py:_fresh_app`` — sets
    ``PROMPT_OPTIMIZER_HOME`` so the DB lands in an isolated location,
    reloads paths + lifespan + main, then calls ``create_app()``. The
    reload chain is load-bearing because ``DB_PATH`` and friends are
    module-level constants that survive a sibling-module reload.

    **D-18 smoke-test interaction (Rule 1 robustness):** The Phase 1
    ``src/routing/tests/test_decide_smoke.py`` deletes ``starlette``,
    ``fastapi``, and friends from ``sys.modules`` to enforce the D-18
    import-graph contract. When that test runs BEFORE this file
    (e.g. with ``pytest src/ apps/``), the ``EventSourceResponse``
    class held by ``apps.api.routes.turn`` ends up inheriting from a
    STALE ``starlette.responses.Response`` while the freshly-imported
    FastAPI compares against the NEW ``Response`` class — the
    ``isinstance(result, Response)`` check fails and FastAPI falls
    through to ``jsonable_encoder`` which tries to JSON-encode an
    async generator (the visible failure). The fix: ALSO purge
    ``sse_starlette`` so the route's ``EventSourceResponse`` reload
    picks up a fresh class hierarchy bound to the current
    ``starlette.responses.Response``.
    """

    monkeypatch.setenv("PROMPT_OPTIMIZER_HOME", str(tmp_path))

    # Purge sse_starlette so its EventSourceResponse reload picks up
    # the current starlette.responses.Response identity (see docstring).
    import sys

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


async def _create_thread(client, title: str = "t1") -> str:
    """POST /threads and return the new thread id."""

    resp = await client.post("/api/v1/threads", json={"title": title})
    assert resp.status_code == 200, (
        f"thread create failed: {resp.status_code} {resp.text}"
    )
    return resp.json()["id"]


# ---------------------------------------------------------------------
# Test 1 — happy path SSE streaming
# ---------------------------------------------------------------------


async def test_streams_chatchunks(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """POST /turn streams text_delta events terminated by done.

    Builds an app with a FakeStreamingAdapter pre-registered in
    ``app.state.adapters["openrouter"]`` (Wave 0 fixture). Monkeypatch
    ``decide()`` to route to openrouter so the fake is invoked.
    Iterates ``aiter_lines()`` with the finite break-on-``event: done``
    pattern (Pitfall 4).
    """

    app = _fresh_app(monkeypatch, tmp_path)

    # Inject the fake adapter BEFORE the lifespan runs — the lifespan
    # honors pre-set app.state.adapters per the B3 pattern.
    from apps.api.backends.chunks import Done, TextDelta
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    fake = FakeStreamingAdapter(
        [
            TextDelta(text="hi"),
            TextDelta(text=" there"),
            Done(tokens_in=2, tokens_out=2, cost_usd=0.001, latency_ms=10),
        ]
    )
    app.state.adapters = {"openrouter": fake}
    app.state.settings = {
        "default_max_cost_usd": 0.50,
        "computer_use_opt_in": False,
    }

    # Pin decide() to openrouter so the route picks the fake.
    from src.routing.schema import RoutingDecision

    def fake_decide(*args, **kwargs):
        return RoutingDecision(
            backend="openrouter",
            model_or_agent="openai/gpt-5",
            rationale="test",
            confidence=0.9,
            signals={"task_type": "chat"},
        )

    monkeypatch.setattr("apps.api.routes.turn.decide", fake_decide)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            events: list[str] = []
            datas: list[str] = []
            async with client.stream(
                "POST",
                f"/api/v1/threads/{thread_id}/turn",
                json={"message": "hello"},
            ) as resp:
                assert resp.status_code == 200, (
                    f"POST returned {resp.status_code}: "
                    f"{await resp.aread()!r}"
                )
                ctype = resp.headers.get("content-type", "")
                assert ctype.startswith("text/event-stream"), (
                    f"Content-Type was {ctype!r}; expected SSE"
                )
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        events.append(line.split(":", 1)[1].strip())
                        if events[-1] == "done":
                            # Pitfall 4 finite consume.
                            break
                    elif line.startswith("data:"):
                        datas.append(line.split(":", 1)[1].strip())

    assert events[-1] == "done", f"last event was {events[-1]!r}, expected 'done'"
    assert events.count("text_delta") >= 2, (
        f"expected ≥2 text_delta events; got {events}"
    )


# ---------------------------------------------------------------------
# Test 2 — decide() runs in a thread (API-07 / D-16)
# ---------------------------------------------------------------------


async def test_decide_runs_in_thread(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Wrap asyncio.to_thread with a counter and assert exactly one call.

    The route handler calls ``await asyncio.to_thread(decide, ...)``
    exactly once per non-override turn. We replace
    ``apps.api.routes.turn.asyncio.to_thread`` with a counting wrapper
    that delegates to the real implementation.
    """

    app = _fresh_app(monkeypatch, tmp_path)

    from apps.api.backends.chunks import Done, TextDelta
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    fake = FakeStreamingAdapter([TextDelta(text="hi"), Done()])
    app.state.adapters = {"openrouter": fake}

    # Stub decide so the to_thread wrapper invokes it without sklearn.
    from src.routing.schema import RoutingDecision

    def fake_decide(*args, **kwargs):
        return RoutingDecision(
            backend="openrouter",
            model_or_agent="openai/gpt-5",
            rationale="test",
            confidence=0.9,
            signals={},
        )

    monkeypatch.setattr("apps.api.routes.turn.decide", fake_decide)

    # Counter wrapper around the REAL asyncio.to_thread.
    import apps.api.routes.turn as turn_mod

    call_count = {"n": 0}
    real_to_thread = turn_mod.asyncio.to_thread

    async def counting_to_thread(fn, *args, **kwargs):
        call_count["n"] += 1
        return await real_to_thread(fn, *args, **kwargs)

    # Replace the bound attribute on the asyncio module object the
    # route imports as ``import asyncio`` at module top.
    monkeypatch.setattr(turn_mod.asyncio, "to_thread", counting_to_thread)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            async with client.stream(
                "POST",
                f"/api/v1/threads/{thread_id}/turn",
                json={"message": "hello"},
            ) as resp:
                # Finite consume — break on event: done.
                async for line in resp.aiter_lines():
                    if line.startswith("event: done"):
                        break

    assert call_count["n"] == 1, (
        f"decide() must run via asyncio.to_thread exactly once; "
        f"got {call_count['n']} calls"
    )


# ---------------------------------------------------------------------
# Test 3 — heartbeat emits (API-05)
# ---------------------------------------------------------------------


@pytest.mark.timeout(10)
async def test_heartbeat_emits(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """The SSE ``:`` comment heartbeat fires when the stream stalls.

    Strategy: replace ``EventSourceResponse`` inside the route module
    with a subclass that overrides ``DEFAULT_PING_INTERVAL`` AND
    forces ``ping`` to a small value, so the test does not sleep the
    full 15-second production heartbeat. The FakeStreamingAdapter
    sleeps 1.0s before its first chunk so the stream stays open long
    enough for the 0.3s heartbeat to fire at least once.

    Why subclass rather than monkeypatching the constructor: in
    sse_starlette 3.x the ``ping`` constructor arg wins over
    ``DEFAULT_PING_INTERVAL`` when non-None, so we must override both
    paths to be sure the heartbeat fires fast in tests.

    **Class identity (D-18 smoke-test interaction):** Build the app
    BEFORE defining the FastPingResponse subclass and re-import
    EventSourceResponse from the route module so the subclass
    inherits from the post-purge, post-reload class hierarchy. The
    D-18 smoke test in src/routing/tests/test_decide_smoke.py may
    have already purged ``starlette``; the route reload in
    ``_fresh_app`` re-establishes the consistent class graph.
    """

    app = _fresh_app(monkeypatch, tmp_path)

    # Re-import AFTER _fresh_app so the EventSourceResponse class
    # used as the FastPingResponse parent is the CURRENT one bound
    # to the freshly-imported starlette.responses.Response.
    from apps.api.routes.turn import EventSourceResponse as RouteESR

    class FastPingResponse(RouteESR):
        DEFAULT_PING_INTERVAL = 0.3  # type: ignore[assignment]

        def __init__(self, content, *args, **kwargs):
            # Force ping to a fast value regardless of what the route
            # passes — overrides the production ping=15.
            kwargs["ping"] = 0.3  # type: ignore[arg-type]
            super().__init__(content, *args, **kwargs)

    monkeypatch.setattr(
        "apps.api.routes.turn.EventSourceResponse", FastPingResponse
    )

    from apps.api.backends.chunks import Done, TextDelta
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    # 1.0s pre-chunk sleep keeps the stream open long enough for the
    # 0.3s heartbeat to fire ≥1 time before the first text_delta.
    fake = FakeStreamingAdapter(
        [TextDelta(text="hi"), Done()], sleep_per_chunk=1.0
    )
    app.state.adapters = {"openrouter": fake}

    from src.routing.schema import RoutingDecision

    def fake_decide(*args, **kwargs):
        return RoutingDecision(
            backend="openrouter",
            model_or_agent="openai/gpt-5",
            rationale="test",
            confidence=0.9,
            signals={},
        )

    monkeypatch.setattr("apps.api.routes.turn.decide", fake_decide)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            heartbeat_count = 0
            async with client.stream(
                "POST",
                f"/api/v1/threads/{thread_id}/turn",
                json={"message": "hi"},
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith(":"):
                        heartbeat_count += 1
                    if line.startswith("event: done"):
                        break

    assert heartbeat_count >= 1, (
        f"expected ≥1 SSE comment heartbeat; got {heartbeat_count}"
    )


# ---------------------------------------------------------------------
# Test 4 — cancellation within 2s (API-06 / Pitfall 6)
# ---------------------------------------------------------------------


@pytest.mark.timeout(5)
async def test_cancellation_within_2s(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """task.cancel() releases the SSE stream within 2 seconds wall-clock.

    Pitfall 6: under ASGITransport, ````aclose```` does NOT
    inject ``http.disconnect`` so we cannot rely on the route's
    ``request.is_disconnected()`` poll. The contractual pattern is
    ``task.cancel()`` on the consumer task — Python's asyncio
    propagates the CancelledError into the ASGI app's generator,
    where the route's ``except asyncio.CancelledError`` handler
    fires the StreamError(cancelled) + Done pair and re-raises.

    The @pytest.mark.timeout(5) is belt-and-suspenders headroom; the
    inline ``elapsed < 2.0`` assertion enforces the API-06 budget
    directly.
    """

    app = _fresh_app(monkeypatch, tmp_path)

    from apps.api.backends.chunks import Done, TextDelta
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    # Slow stream — 2.0s per chunk so cancellation lands mid-stream.
    fake = FakeStreamingAdapter(
        [TextDelta(text="slow"), Done()], sleep_per_chunk=2.0
    )
    app.state.adapters = {"openrouter": fake}

    from src.routing.schema import RoutingDecision

    def fake_decide(*args, **kwargs):
        return RoutingDecision(
            backend="openrouter",
            model_or_agent="openai/gpt-5",
            rationale="test",
            confidence=0.9,
            signals={},
        )

    monkeypatch.setattr("apps.api.routes.turn.decide", fake_decide)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)

            chunks: list[str] = []

            async def consume() -> None:
                async with client.stream(
                    "POST",
                    f"/api/v1/threads/{thread_id}/turn",
                    json={"message": "hi"},
                ) as resp:
                    async for line in resp.aiter_lines():
                        chunks.append(line)

            task = asyncio.create_task(consume())
            await asyncio.sleep(0.05)  # let the request reach the handler
            t0 = time.monotonic()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            elapsed = time.monotonic() - t0

    # API-06 contractual budget: cancellation cleanup must finish in
    # under 2 seconds wall-clock. The pytest-timeout(5) provides
    # headroom for fixture setup; this assertion enforces the budget.
    assert elapsed < 2.0, (
        f"cancellation took {elapsed:.2f}s — API-06 budget is 2s"
    )


# ---------------------------------------------------------------------
# Test 5 — ONE transaction per turn (D-04 / STORE-05)
# ---------------------------------------------------------------------


async def test_one_transaction_per_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """After a full POST-turn, the DB contains 2 messages + 1 routing row.

    The assistant message's ``text`` is the collapsed TextDelta text;
    its ``content_blocks`` JSON contains the ToolCall but NOT the
    TextDelta. D-04 + STORE-05 contract: ONE BEGIN/COMMIT per turn.
    """

    app = _fresh_app(monkeypatch, tmp_path)

    from apps.api.backends.chunks import Done, TextDelta, ToolCall
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    fake = FakeStreamingAdapter(
        [
            TextDelta(text="answer"),
            ToolCall(
                tool_call_id="tc1",
                tool_name="search",
                arguments={"q": "x"},
            ),
            Done(
                tokens_in=5,
                tokens_out=10,
                cost_usd=0.002,
                latency_ms=250,
            ),
        ]
    )
    app.state.adapters = {"openrouter": fake}

    from src.routing.schema import RoutingDecision

    def fake_decide(*args, **kwargs):
        return RoutingDecision(
            backend="openrouter",
            model_or_agent="openai/gpt-5",
            rationale="test",
            confidence=0.9,
            signals={"task_type": "chat"},
        )

    monkeypatch.setattr("apps.api.routes.turn.decide", fake_decide)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            async with client.stream(
                "POST",
                f"/api/v1/threads/{thread_id}/turn",
                json={"message": "hello"},
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("event: done"):
                        break

        # Query DB via the shared app.state.db. Lifespan_context is
        # still open here (the async with above keeps it alive).
        db = app.state.db
        async with db.execute(
            "SELECT COUNT(*) FROM messages WHERE thread_id = ?",
            (thread_id,),
        ) as cur:
            msg_count = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT text, content_blocks FROM messages"
            " WHERE thread_id = ? AND role = 'assistant'",
            (thread_id,),
        ) as cur:
            row = await cur.fetchone()
        async with db.execute(
            "SELECT COUNT(*) FROM routing_decisions"
        ) as cur:
            rd_count = (await cur.fetchone())[0]

    assert msg_count == 2, (
        f"expected 2 messages (user + assistant); got {msg_count}"
    )
    assert rd_count == 1, f"expected 1 routing_decisions row; got {rd_count}"

    assistant_text, content_blocks = row
    assert assistant_text == "answer", (
        f"assistant text should be the collapsed TextDelta; "
        f"got {assistant_text!r}"
    )
    blocks = json.loads(content_blocks)
    block_types = [b.get("type") for b in blocks]
    assert "tool_call" in block_types, (
        f"ToolCall must be in content_blocks; got types {block_types}"
    )
    assert "text_delta" not in block_types, (
        f"TextDelta must NOT be in content_blocks (collapsed into text); "
        f"got types {block_types}"
    )


# ---------------------------------------------------------------------
# Test 6 — JSONL log appended BEFORE adapter dispatch (D-05 / STORE-06)
# ---------------------------------------------------------------------


async def test_jsonl_log_appended(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """One JSONL line per turn with the eight canonical keys.

    The FakeStreamingAdapter emits ONLY a terminal Done so we can
    verify the jsonl write happens BEFORE any chunks stream (D-05).
    """

    app = _fresh_app(monkeypatch, tmp_path)

    # Point JSONL_LOG_PATH to a tmp file via the module attribute the
    # writer reads at call time. The _fresh_app reload chain already
    # re-evaluated apps.api.paths under PROMPT_OPTIMIZER_HOME=tmp_path,
    # so the default landing is already inside tmp_path. We override
    # again for explicitness.
    custom_log = tmp_path / "routing.jsonl"
    monkeypatch.setattr(
        "apps.api.jsonl_log.JSONL_LOG_PATH", custom_log
    )

    from apps.api.backends.chunks import Done
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    fake = FakeStreamingAdapter([Done()])
    app.state.adapters = {"openrouter": fake}

    from src.routing.schema import RoutingDecision

    def fake_decide(*args, **kwargs):
        return RoutingDecision(
            backend="openrouter",
            model_or_agent="openai/gpt-5",
            rationale="test rationale",
            confidence=0.85,
            signals={"task_type": "chat"},
        )

    monkeypatch.setattr("apps.api.routes.turn.decide", fake_decide)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            async with client.stream(
                "POST",
                f"/api/v1/threads/{thread_id}/turn",
                json={"message": "hi"},
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("event: done"):
                        break

    assert custom_log.exists(), (
        f"jsonl file should exist at {custom_log}"
    )
    lines = custom_log.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1, f"expected 1 line; got {len(lines)}: {lines}"

    record = json.loads(lines[0])
    expected_keys = {
        "turn_id",
        "thread_id",
        "timestamp",
        "backend",
        "model_or_agent",
        "rationale",
        "confidence",
        "signals",
    }
    assert set(record.keys()) >= expected_keys, (
        f"missing keys: {expected_keys - set(record.keys())}; "
        f"got {set(record.keys())}"
    )
    assert record["backend"] == "openrouter"
    assert record["rationale"] == "test rationale"
    assert record["thread_id"] == thread_id


# ---------------------------------------------------------------------
# Test 7 — override_backend bypasses decide() (Pattern 11)
# ---------------------------------------------------------------------


async def test_override_backend(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """``override_backend`` in the body bypasses decide() entirely.

    Monkeypatch decide() to raise; the turn STILL succeeds because the
    route synthesises a RoutingDecision instead of calling decide().
    Verify via the jsonl log that the synthesised decision has
    ``rationale="user override"``.
    """

    app = _fresh_app(monkeypatch, tmp_path)

    custom_log = tmp_path / "routing.jsonl"
    monkeypatch.setattr(
        "apps.api.jsonl_log.JSONL_LOG_PATH", custom_log
    )

    from apps.api.backends.chunks import Done, TextDelta
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    fake = FakeStreamingAdapter([TextDelta(text="ok"), Done()])
    app.state.adapters = {"openrouter": fake}

    # decide() MUST NOT be called when override_backend is set.
    def raising_decide(*args, **kwargs):
        raise RuntimeError(
            "decide should not be called when override_backend is set"
        )

    monkeypatch.setattr("apps.api.routes.turn.decide", raising_decide)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            async with client.stream(
                "POST",
                f"/api/v1/threads/{thread_id}/turn",
                json={
                    "message": "hi",
                    "override_backend": "openrouter",
                },
            ) as resp:
                assert resp.status_code == 200, (
                    f"override turn should succeed; got "
                    f"{resp.status_code} {await resp.aread()!r}"
                )
                async for line in resp.aiter_lines():
                    if line.startswith("event: done"):
                        break

    assert custom_log.exists()
    record = json.loads(custom_log.read_text().strip().split("\n")[0])
    assert record["rationale"] == "user override", (
        f"synthesised rationale must be 'user override'; "
        f"got {record['rationale']!r}"
    )
    assert record["backend"] == "openrouter"
    assert record["confidence"] == 1.0


# ---------------------------------------------------------------------
# Test 8 — computer-use gated when opt-out (D-12 + D-08)
# ---------------------------------------------------------------------


async def test_computer_use_gated_when_opt_out(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """``override_backend="computer_use"`` returns 400 when opt-out.

    D-12 STRICT AND-semantics: ``computer_use_enabled`` returns False
    when EITHER the env var is unset OR the in-app toggle is off.
    The route's pre-construction gate trips, raising HTTPException(400)
    BEFORE the SSE response opens (D-08 pre-stream error).
    """

    # Belt-and-suspenders: clear the env var so the env gate trips.
    monkeypatch.delenv("COMPUTER_USE_OPT_IN", raising=False)

    app = _fresh_app(monkeypatch, tmp_path)
    # Settings opt_in=False so both gates are off.
    app.state.settings = {
        "default_max_cost_usd": 0.50,
        "computer_use_opt_in": False,
    }

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            resp = await client.post(
                f"/api/v1/threads/{thread_id}/turn",
                json={
                    "message": "hi",
                    "override_backend": "computer_use",
                },
            )

    assert resp.status_code == 400, (
        f"computer_use opt-out should return 400 BEFORE the SSE "
        f"response opens; got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert "computer-use is OFF" in body.get("detail", ""), (
        f"error detail should mention computer-use OFF; "
        f"got {body}"
    )


# ---------------------------------------------------------------------
# Test 9 — unknown thread returns 404 (pre-stream HTTPException)
# ---------------------------------------------------------------------


async def test_unknown_thread_returns_404(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """POST to an unknown thread returns 404 before any SSE opens."""

    app = _fresh_app(monkeypatch, tmp_path)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/threads/unknown/turn",
                json={"message": "hi"},
            )

    assert resp.status_code == 404, (
        f"unknown thread should return 404; got {resp.status_code}: "
        f"{resp.text}"
    )
    body = resp.json()
    assert body["detail"] == "thread not found", (
        f"detail should be 'thread not found'; got {body}"
    )


# ---------------------------------------------------------------------
# Test 10 — D-15 routing_decision SSE event (Plan 04-04 contract)
# ---------------------------------------------------------------------


async def test_routing_decision_event_arrives_first_and_matches_done(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """D-15 contract: routing_decision event arrives FIRST with the
    structured 5-key payload, and ``payload['signals']`` equals
    ``Done.routing_signals`` byte-for-byte.

    Plan 04-04 amends ``apps/api/routes/turn.py`` so the event_stream
    generator yields a ``routing_decision`` named SSE event as its FIRST
    yield, BEFORE the adapter.stream() loop. The payload is the
    STRUCTURED 5-key record sourced from ``decision``:

        {backend, model_or_agent, rationale, confidence, signals}

    The chip in Plan 05 needs ``backend`` (for color), ``model_or_agent``
    (for display_name lookup), ``rationale`` (for the chip body +
    tooltip), and ``confidence``. The ``signals`` SUB-FIELD preserves
    the byte-for-byte equality with ``Done.routing_signals`` that D-15
    (the persistence-source guarantee) requires.

    Four independent assertions:
      (a) first event on the wire is ``routing_decision``
      (b) it arrives within 500ms (ASGITransport latency bound — the
          100ms target is for real-network; ASGITransport has no
          network)
      (c) parsed payload has EXACTLY the 5 keys
          {backend, model_or_agent, rationale, confidence, signals}
          with the expected values
      (d) ``routing_payload['signals']`` equals
          ``done_payload['routing_signals']`` byte-for-byte
    """

    app = _fresh_app(monkeypatch, tmp_path)

    from apps.api.backends.chunks import Done, TextDelta
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    # decide() returns these signals; the new event's payload['signals']
    # MUST mirror them, and Done.routing_signals MUST also equal them.
    # Realistic Phase-1 signals shape (task_type / agentic_intent /
    # rule_fired) so byte-for-byte test catches any truncation.
    test_signals = {
        "task_type": "chat",
        "task_type_confidence": 0.92,
        "agentic_intent": False,
        "agentic_intent_confidence": 0.05,
        "rule_fired": "default",
    }

    # Expected 5 fields the event payload MUST carry verbatim.
    expected_backend = "openrouter"
    expected_model = "openai/gpt-5"
    expected_rationale = "test routing"
    expected_confidence = 0.9

    fake = FakeStreamingAdapter(
        [
            TextDelta(text="hi"),
            Done(
                tokens_in=1,
                tokens_out=1,
                cost_usd=0.001,
                latency_ms=10,
                routing_signals=test_signals,
            ),
        ]
    )
    app.state.adapters = {"openrouter": fake}

    from src.routing.schema import RoutingDecision

    def fake_decide(*args, **kwargs):
        return RoutingDecision(
            backend=expected_backend,
            model_or_agent=expected_model,
            rationale=expected_rationale,
            confidence=expected_confidence,
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
                assert resp.status_code == 200, (
                    f"POST returned {resp.status_code}: "
                    f"{await resp.aread()!r}"
                )
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        current_event = line.split(":", 1)[1].strip()
                        if first_event_t is None:
                            first_event_t = time.monotonic()
                    elif (
                        line.startswith("data:")
                        and current_event is not None
                    ):
                        # split(":", 1) preserves JSON colons in the
                        # data payload.
                        events.append(
                            (current_event, line.split(":", 1)[1].strip())
                        )
                        if current_event == "done":
                            # Pitfall 4 finite consume.
                            break

    # ---- Assertion (a): first event is routing_decision ----
    assert len(events) > 0, "expected at least one SSE event"
    assert events[0][0] == "routing_decision", (
        f"first event was {events[0][0]!r}, expected "
        f"'routing_decision' — D-15 amendment requires the chip data "
        f"to arrive on the wire BEFORE any text_delta or other chunk"
    )

    # ---- Assertion (b): arrived within 500ms ----
    # ASGITransport has no real network — 500ms is generous headroom
    # for monkeypatch + lifespan setup. Real-network target is 100ms.
    assert first_event_t is not None
    assert (first_event_t - t0) < 0.5, (
        f"first event landed {(first_event_t - t0) * 1000:.1f}ms after "
        f"POST; D-15 ASGITransport latency bound is 500ms"
    )

    # ---- Assertion (c): 5-key structured payload ----
    routing_payload = json.loads(events[0][1])
    assert set(routing_payload.keys()) == {
        "backend",
        "model_or_agent",
        "rationale",
        "confidence",
        "signals",
    }, (
        f"routing_decision payload must have exactly the 5 keys "
        f"{{backend, model_or_agent, rationale, confidence, signals}}; "
        f"got {set(routing_payload.keys())}"
    )
    assert routing_payload["backend"] == expected_backend, (
        f"payload['backend'] mismatch: "
        f"{routing_payload['backend']!r} vs {expected_backend!r}"
    )
    assert routing_payload["model_or_agent"] == expected_model, (
        f"payload['model_or_agent'] mismatch: "
        f"{routing_payload['model_or_agent']!r} vs {expected_model!r}"
    )
    assert routing_payload["rationale"] == expected_rationale, (
        f"payload['rationale'] mismatch: "
        f"{routing_payload['rationale']!r} vs {expected_rationale!r}"
    )
    assert routing_payload["confidence"] == expected_confidence, (
        f"payload['confidence'] mismatch: "
        f"{routing_payload['confidence']!r} vs "
        f"{expected_confidence!r}"
    )

    # ---- Assertion (d): byte-for-byte equality of signals sub-field ----
    # Done.routing_signals remains the canonical persistence source
    # (Phase 3 STORE-02). The early routing_decision event is for UX
    # freshness; this assertion proves the chip and the persisted
    # row share a single truth — no drift possible.
    done_event = next((e for e in events if e[0] == "done"), None)
    assert done_event is not None, "expected a terminal done event"
    done_payload = json.loads(done_event[1])
    assert routing_payload["signals"] == done_payload["routing_signals"], (
        f"signals sub-field must equal Done.routing_signals "
        f"byte-for-byte (D-15 canonical-persistence equality);\n"
        f"  routing_payload['signals'] = {routing_payload['signals']!r}\n"
        f"  done_payload['routing_signals'] = "
        f"{done_payload['routing_signals']!r}"
    )


# ---------------------------------------------------------------------
# Test 11 — Phase 4 UAT gap fix: missing-key adapter ctor returns 400
# ---------------------------------------------------------------------


async def test_missing_anthropic_key_returns_400_not_500(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Adapter constructor RuntimeError surfaces as pre-stream HTTPException(400).

    Phase 4 UAT (2026-05-19) surfaced a blocker: when the Phase 1 router
    picks ``claude_code`` for a code/long-form prompt and no
    ANTHROPIC_API_KEY is set, ``ClaudeCodeAdapter.__init__`` raises
    ``RuntimeError("ANTHROPIC_API_KEY not set …")``. The previous
    ``_get_or_create_adapter`` try/except only caught ``ImportError``,
    so the ``RuntimeError`` propagated as a 500 — the Phase 4 UI saw
    an opaque error, the assistant-message slot stayed empty, and the
    metrics footer was stuck on ``streaming●`` indefinitely.

    The fix mirrors the existing computer-use opt-out gate (D-12): catch
    the adapter's missing-key ``RuntimeError`` at construction and
    re-raise as ``HTTPException(400)`` with a backend-aware detail
    string the UI can render via ``StreamErrorBanner`` or a toast.

    Assertion contract:
      (a) status_code == 400 (NOT 500) — the SSE stream never opens
      (b) detail mentions both the backend name and the required env
          var name so the user knows WHICH key is missing
    """

    # Belt-and-suspenders: ensure no real env key bleeds in from the
    # caller's shell. The adapter's preflight checks os.environ in
    # addition to the explicit api_key argument.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    app = _fresh_app(monkeypatch, tmp_path)

    # No pre-registered adapter for claude_code — forces the route to
    # call _get_or_create_adapter, which constructs a real
    # ClaudeCodeAdapter (with api_key=keystore.get("anthropic") which
    # returns None for a fresh keystore), tripping the preflight.
    app.state.adapters = {}

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            resp = await client.post(
                f"/api/v1/threads/{thread_id}/turn",
                json={
                    "message": "anything",
                    "override_backend": "claude_code",
                },
            )

    assert resp.status_code == 400, (
        f"missing ANTHROPIC_API_KEY for routed claude_code backend "
        f"should return pre-stream 400, not 500 (UAT Gap #1); "
        f"got {resp.status_code}: {resp.text}"
    )
    detail = resp.json().get("detail", "")
    assert "claude_code" in detail, (
        f"error detail should name the backend; got {detail!r}"
    )
    assert "ANTHROPIC_API_KEY" in detail, (
        f"error detail should name the missing env var so the user "
        f"knows what to set; got {detail!r}"
    )


# =====================================================================
# Phase 9 Wave-0 RED test slices — RELI-01 (retry) + RELI-02 (kill-switch)
# =====================================================================
#
# These four tests are scaffolded RED for Phase 9 (VALIDATION.md
# Per-Requirement map rows RELI-01/RELI-02). They assert the TARGET
# behavior the engineering waves (Plans 02-03) will land, and are each
# gated with an imperative ``pytest.xfail(...)`` so they:
#   - are COLLECTABLE by their VALIDATION.md ``-k`` selector
#     (retry / first_token_no_retry / wall_clock / budget_exceeded), and
#   - report ``xfail`` (NOT error, NOT pass) against today's unmodified
#     turn handler.
# When the retry loop / kill-switch lands, the owning plan removes the
# ``pytest.xfail(...)`` guard line and the assertions below run for real
# (Phase-1 D named-body RED convention; NOT module-level skip).


async def test_retry_retriable_establishment_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """RELI-01 (-k retry): a retriable establishment error retries
    (≤3, full-jitter) then succeeds; the turn streams a normal Done.

    Target behavior (Plan 02-03): when the adapter's FIRST round-trip
    raises a retriable error (e.g. provider_unavailable) BEFORE any
    chunk is yielded, the turn handler retries with full-jitter backoff
    up to 3 attempts. A raise-then-succeed fake therefore still produces
    a text_delta + done stream. ``max_retries=0`` is forced for the
    non-retriable path (covered by the sibling slice).
    """

    app = _fresh_app(monkeypatch, tmp_path)

    from apps.api.backends.chunks import Done, StreamError, TextDelta
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    # Raise a retriable establishment error on attempt 1, succeed on 2.
    fake = FakeStreamingAdapter(
        [
            StreamError(
                code="provider_unavailable", message="503", retriable=True
            ),
            TextDelta(text="recovered"),
            Done(tokens_in=1, tokens_out=1, cost_usd=0.001, latency_ms=10),
        ]
    )
    app.state.adapters = {"openrouter": fake}

    from src.routing.schema import RoutingDecision

    def fake_decide(*args, **kwargs):
        return RoutingDecision(
            backend="openrouter",
            model_or_agent="openai/gpt-5",
            rationale="test",
            confidence=0.9,
            signals={},
        )

    monkeypatch.setattr("apps.api.routes.turn.decide", fake_decide)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            events: list[str] = []
            async with client.stream(
                "POST",
                f"/api/v1/threads/{thread_id}/turn",
                json={"message": "hi"},
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        events.append(line.split(":", 1)[1].strip())
                        if events[-1] == "done":
                            break

    # After a successful retry the recovered text_delta reaches the wire
    # and the stream terminates normally (no surfaced stream_error).
    assert "text_delta" in events
    assert events[-1] == "done"


async def test_first_token_no_retry(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """RELI-01 (D-01 boundary): NO retry after the first chunk streamed.

    Target behavior: once any chunk has reached the consumer, a
    subsequent mid-stream error is NOT retried (retrying would replay
    already-streamed tokens). The handler surfaces the error and a
    terminal Done; it does NOT re-invoke the adapter.
    """

    app = _fresh_app(monkeypatch, tmp_path)

    from apps.api.backends.chunks import Done, StreamError, TextDelta
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    # A chunk streams FIRST, then a retriable error: must NOT retry.
    fake = FakeStreamingAdapter(
        [
            TextDelta(text="partial"),
            StreamError(
                code="provider_unavailable", message="503", retriable=True
            ),
            Done(),
        ]
    )
    app.state.adapters = {"openrouter": fake}

    from src.routing.schema import RoutingDecision

    def fake_decide(*args, **kwargs):
        return RoutingDecision(
            backend="openrouter",
            model_or_agent="openai/gpt-5",
            rationale="test",
            confidence=0.9,
            signals={},
        )

    monkeypatch.setattr("apps.api.routes.turn.decide", fake_decide)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            text_delta_count = 0
            async with client.stream(
                "POST",
                f"/api/v1/threads/{thread_id}/turn",
                json={"message": "hi"},
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("event: text_delta"):
                        text_delta_count += 1
                    if line.startswith("event: done"):
                        break

    # Exactly ONE text_delta — a retry would have replayed the partial.
    assert text_delta_count == 1, (
        "first-token boundary: no retry may replay already-streamed tokens"
    )


@pytest.mark.timeout(10)
async def test_wall_clock_exceeded_emitted(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """RELI-02: a wall-clock deadline trip emits StreamError(wall_clock_exceeded)
    + Done, distinct from ``timeout``.

    Target behavior: the turn handler enforces a per-turn wall-clock
    deadline. When a stream runs past it, the handler emits a
    ``wall_clock_exceeded`` StreamError (one of the two D-05 codes added
    in Plan 01) followed by the terminal Done. The code is DISTINCT from
    the provider-level ``timeout`` code.
    """

    # Pin a small per-turn wall-clock so the 30s-stalling fake trips the
    # deadline well inside the @pytest.mark.timeout(10) budget. The
    # resolver reads this env knob at AdapterOptions construction (Task 1).
    monkeypatch.setenv("RELI_OPENROUTER_WALL_S", "1")

    app = _fresh_app(monkeypatch, tmp_path)

    from apps.api.backends.chunks import Done, TextDelta
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    # A stream that stalls past the (to-be-added) per-turn deadline.
    fake = FakeStreamingAdapter(
        [TextDelta(text="slow"), Done()], sleep_per_chunk=30.0
    )
    app.state.adapters = {"openrouter": fake}

    from src.routing.schema import RoutingDecision

    def fake_decide(*args, **kwargs):
        return RoutingDecision(
            backend="openrouter",
            model_or_agent="openai/gpt-5",
            rationale="test",
            confidence=0.9,
            signals={},
        )

    monkeypatch.setattr("apps.api.routes.turn.decide", fake_decide)

    codes: list[str] = []
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            async with client.stream(
                "POST",
                f"/api/v1/threads/{thread_id}/turn",
                json={"message": "hi"},
            ) as resp:
                current = None
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        current = line.split(":", 1)[1].strip()
                    elif line.startswith("data:") and current == "stream_error":
                        codes.append(json.loads(line.split(":", 1)[1])["code"])
                    if line.startswith("event: done"):
                        break

    assert "wall_clock_exceeded" in codes, (
        "a stalled turn must surface wall_clock_exceeded (distinct from timeout)"
    )
    assert "timeout" not in codes, "wall-clock trip is NOT the provider timeout code"


async def test_budget_exceeded_distinct_from_cost_cap(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """RELI-02: a USD over-cap kill-switch trip emits
    StreamError(budget_exceeded), distinct from ``cost_cap_exceeded``.

    Target behavior: the turn handler enforces a per-turn USD backstop
    independent of the adapter's own ``cost_cap_exceeded`` accounting.
    When cumulative spend crosses the backstop, the handler emits the
    ``budget_exceeded`` D-05 code (added in Plan 01) — a SEPARATE code
    from the adapter-level ``cost_cap_exceeded`` so the UI and the retry
    policy can distinguish the turn-level kill-switch from a single
    adapter's cap.
    """

    app = _fresh_app(monkeypatch, tmp_path)

    from apps.api.backends.chunks import Done, TextDelta
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    # A Done reporting spend that crosses the turn-level backstop
    # (default openrouter usd_backstop is $0.50; 999.0 >> 0.50).
    fake = FakeStreamingAdapter(
        [
            TextDelta(text="expensive"),
            Done(tokens_in=1_000_000, tokens_out=1_000_000, cost_usd=999.0),
        ]
    )
    app.state.adapters = {"openrouter": fake}

    from src.routing.schema import RoutingDecision

    def fake_decide(*args, **kwargs):
        return RoutingDecision(
            backend="openrouter",
            model_or_agent="openai/gpt-5",
            rationale="test",
            confidence=0.9,
            signals={},
        )

    monkeypatch.setattr("apps.api.routes.turn.decide", fake_decide)

    codes: list[str] = []
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            async with client.stream(
                "POST",
                f"/api/v1/threads/{thread_id}/turn",
                json={"message": "hi"},
            ) as resp:
                current = None
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        current = line.split(":", 1)[1].strip()
                    elif line.startswith("data:") and current == "stream_error":
                        codes.append(json.loads(line.split(":", 1)[1])["code"])
                    if line.startswith("event: done"):
                        break

    assert "budget_exceeded" in codes, (
        "turn-level USD backstop must surface budget_exceeded"
    )
    assert "cost_cap_exceeded" not in codes, (
        "budget_exceeded is the turn kill-switch, distinct from the "
        "adapter-level cost_cap_exceeded"
    )


# =====================================================================
# Phase 9 09-02 Task 1 — per-backend kill-switch ceiling resolver
# =====================================================================
#
# RELI-02 / D-04: AdapterOptions exposes wall_clock_s + usd_backstop with
# per-backend defaults resolved from env. Absent env var → the D-04
# starting default; present env var → its value. These assert the
# resolver wiring directly (Task 1 acceptance criterion 3).


def test_resolve_backend_ceilings_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``RELI_OPENROUTER_WALL_S=5`` resolves a 5.0s deadline; unset → 120.0."""

    from apps.api.routes.turn import _resolve_backend_ceilings

    # Unset → D-04 chat-tier defaults (120s / $0.50).
    monkeypatch.delenv("RELI_OPENROUTER_WALL_S", raising=False)
    monkeypatch.delenv("RELI_OPENROUTER_USD", raising=False)
    wall, usd = _resolve_backend_ceilings("openrouter")
    assert wall == 120.0
    assert usd == 0.50

    # Present → its value.
    monkeypatch.setenv("RELI_OPENROUTER_WALL_S", "5")
    monkeypatch.setenv("RELI_OPENROUTER_USD", "0.25")
    wall, usd = _resolve_backend_ceilings("openrouter")
    assert wall == 5.0, "RELI_OPENROUTER_WALL_S=5 must resolve a 5.0s deadline"
    assert usd == 0.25


def test_resolve_backend_ceilings_agent_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Claude Code / computer-use default to the longer D-04 agent ceilings."""

    from apps.api.routes.turn import _resolve_backend_ceilings

    for backend in ("claude_code", "computer_use"):
        monkeypatch.delenv(
            f"RELI_{backend.upper()}_WALL_S", raising=False
        )
        monkeypatch.delenv(f"RELI_{backend.upper()}_USD", raising=False)
        wall, usd = _resolve_backend_ceilings(backend)
        assert wall == 600.0, f"{backend} wall-clock default is 600s (D-04)"
        assert usd == 2.00, f"{backend} USD backstop default is $2.00 (D-04)"


def test_adapter_options_constructible_with_no_ceiling_args() -> None:
    """The frozen AdapterOptions stays constructible with no args (defaults)."""

    from apps.api.backends.protocol import AdapterOptions

    opts = AdapterOptions()
    assert opts.wall_clock_s == 120.0
    assert opts.usd_backstop == 0.50


# =====================================================================
# Phase 9 09-05 Task 1 — cancel persists the partial (RELI-03 / D-06)
# + per-backend cancellation budget (Open Question 2)
# =====================================================================
#
# RESEARCH Pitfall 5: trigger the teardown via ``task.cancel()`` on the
# task driving the SERVER-side ``event_stream`` generator — NOT a faked
# ``is_disconnected()`` (a no-op under ASGITransport). We drive the
# route handler's returned EventSourceResponse ``body_iterator`` directly
# so the CancelledError lands inside the generator after a TextDelta is
# buffered but before the adapter's Done, then assert the ``finally``
# block persisted the PARTIAL content_blocks with status='cancelled'.


class _HangAfterDeltaAdapter:
    """Yield one TextDelta, then await forever (until cancelled).

    Models the real "mid-stream client disconnect" shape: a partial
    answer has reached the buffer (one ``text_delta``) but the adapter
    has NOT yet produced its terminal ``Done`` when the cancellation
    arrives. The infinite await is what ``task.cancel()`` interrupts,
    so the route's ``except asyncio.CancelledError`` handler fires with
    a non-empty buffer (the buffered partial).
    """

    def __init__(self) -> None:
        self.teardown_ran = False

    async def stream(self, prompt, history, options):
        from apps.api.backends.chunks import TextDelta

        try:
            yield TextDelta(text="partial-answer")
            # Hang until the consumer task is cancelled — the generator's
            # GeneratorExit/CancelledError on aclose() drives this teardown.
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # The upstream adapter teardown (in_flight.close / interrupt /
            # aclose) runs here on the real adapters; record that it ran.
            self.teardown_ran = True
            raise


@pytest.mark.timeout(10)
async def test_cancel_persists_partial_with_cancelled_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A task.cancel() mid-stream persists the partial with status='cancelled'.

    D-06 keep-partial: after a buffered ``text_delta``, a cancellation
    must reach ``persist_turn`` with (a) ``status='cancelled'`` and (b)
    the buffered partial content present (the partial is NOT dropped).
    We spy on ``persist_turn`` to capture the exact ``buffer`` + ``status``
    the route handed it.
    """

    app = _fresh_app(monkeypatch, tmp_path)

    from apps.api.backends.chunks import StreamError, TextDelta
    import apps.api.routes.turn as turn_mod

    fake = _HangAfterDeltaAdapter()
    app.state.adapters = {"openrouter": fake}

    from src.routing.schema import RoutingDecision

    def fake_decide(*args, **kwargs):
        return RoutingDecision(
            backend="openrouter",
            model_or_agent="openai/gpt-5",
            rationale="test",
            confidence=0.9,
            signals={},
        )

    monkeypatch.setattr(turn_mod, "decide", fake_decide)

    # Spy on persist_turn — capture the buffer + status the route passes.
    captured: dict = {}

    async def spy_persist_turn(db, *, buffer, status, **kwargs):
        captured["buffer"] = list(buffer)
        captured["status"] = status

    monkeypatch.setattr(turn_mod, "persist_turn", spy_persist_turn)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)

        # Build a Request and call the route handler directly so we own
        # the SERVER-side generator (Pitfall 6: cancelling the httpx
        # consumer does NOT inject http.disconnect under ASGITransport).
        from fastapi import Request
        from apps.api.routes.turn import TurnRequest, post_turn

        scope = {
            "type": "http",
            "method": "POST",
            "path": f"/api/v1/threads/{thread_id}/turn",
            "headers": [],
            "query_string": b"",
            "app": app,
        }

        async def _receive():
            # Never signal disconnect — the cancellation comes from
            # task.cancel(), not the ASGI receive channel.
            return {"type": "http.request", "body": b"", "more_body": False}

        request = Request(scope, receive=_receive)
        response = await post_turn(
            thread_id, TurnRequest(message="hi"), request
        )

        # Drive the SSE generator until the partial text_delta is on the
        # wire, then cancel the driving task mid-await.
        body_iter = response.body_iterator
        saw_partial = asyncio.Event()

        async def drive() -> None:
            async for event in body_iter:
                payload = getattr(event, "data", "") or ""
                if '"partial-answer"' in payload:
                    saw_partial.set()

        task = asyncio.create_task(drive())
        await asyncio.wait_for(saw_partial.wait(), timeout=5.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    # D-06: persist_turn must have been called with the PARTIAL buffer
    # and status='cancelled'.
    assert captured.get("status") == "cancelled", (
        f"a cancelled turn must persist status='cancelled'; "
        f"got {captured.get('status')!r}"
    )
    buffer = captured.get("buffer") or []
    text_deltas = [c for c in buffer if isinstance(c, TextDelta)]
    assert text_deltas, (
        "the buffered partial (text_delta) must be persisted, not dropped "
        "— D-06 keep-partial"
    )
    assert any(c.text == "partial-answer" for c in text_deltas), (
        "the exact buffered partial content must survive into persist_turn"
    )
    # The terminal pair the handler appends must yield a 'cancelled' error.
    errors = [c for c in buffer if isinstance(c, StreamError)]
    assert errors and errors[-1].code == "cancelled", (
        "the cancellation terminal pair must carry StreamError(cancelled)"
    )
    # The upstream adapter teardown ran (no orphaned upstream work).
    assert fake.teardown_ran, (
        "the adapter's CancelledError teardown must run on cancel "
        "(no orphaned upstream spend — T-09-04)"
    )


def test_resolve_cancel_budget_per_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Open Question 2: cancel budget is per-backend (chat ~2s; agents >2s).

    Chat (openrouter) defaults to the BACKEND-07 ~2s budget; the agent
    backends (claude_code / computer_use) default to a higher ceiling so
    slow Playwright / subprocess teardown is not truncated. Each is
    overridable from a per-backend env knob (mirrors the RELI-02 ceiling
    resolver).
    """

    from apps.api.routes.turn import _resolve_cancel_budget

    # Unset → defaults: chat 2.0s, agents 5.0s.
    for backend in ("openrouter", "claude_code", "computer_use"):
        monkeypatch.delenv(f"RELI_{backend.upper()}_CANCEL_S", raising=False)
    assert _resolve_cancel_budget("openrouter") == 2.0, (
        "chat cancel budget defaults to ~2s (BACKEND-07 / API-06)"
    )
    assert _resolve_cancel_budget("claude_code") > 2.0, (
        "agent cancel budget must exceed the 2s chat ceiling (Open Question 2)"
    )
    assert _resolve_cancel_budget("computer_use") > 2.0, (
        "computer-use cancel budget must exceed the 2s chat ceiling"
    )

    # Present env knob → its value (the budget is operator-tunable).
    monkeypatch.setenv("RELI_CLAUDE_CODE_CANCEL_S", "8")
    assert _resolve_cancel_budget("claude_code") == 8.0, (
        "RELI_CLAUDE_CODE_CANCEL_S must override the agent default"
    )


def test_adapter_options_carries_cancel_budget() -> None:
    """The frozen AdapterOptions exposes cancel_budget_s with a 2s default."""

    from apps.api.backends.protocol import AdapterOptions

    opts = AdapterOptions()
    assert opts.cancel_budget_s == 2.0
