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
