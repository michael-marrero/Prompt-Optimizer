"""Control-substrate behaviour tests (Phase 11 / Wave 0, CTRL-02/CTRL-03).

Task-1 behaviour coverage (this plan):

    - ControlMessage closed-Literal ``kind`` + ``extra="forbid"`` +
      opaque ``payload`` (D-01).
    - ControlMailbox enqueue / has_pending / drain_all FIFO + no-strand
      drain semantics (D-03).
    - registry register / get / deregister round-trip keyed by turn_id,
      missing-key safety.

Plan-02 INTEGRATION placeholders (this file is the scaffold Plan 02
EXTENDS): the six named ``test_*`` functions at the bottom call
``pytest.skip()`` IN THEIR BODY (NOT a module-level skip) so they stay
visible to ``pytest --collect-only`` while reporting as skipped in a
normal run — the same RED-stub contract Phase 1 Plan 01 locked.

Cross-refs:
    - 11-01-PLAN Task 1 (behavior + action + acceptance criteria)
    - apps/api/tests/conftest.py (app.state override pattern)
    - apps/api/control/mailbox.py / registry.py (modules under test)
"""

from __future__ import annotations

import importlib
import typing

import httpx
import pytest
from httpx import ASGITransport
from pydantic import ValidationError

from apps.api.control import ControlMailbox, ControlMessage
from apps.api.control import registry


# --------------------------------------------------------------------
# ControlMessage — D-01 closed Literal + extra="forbid" + opaque payload
# --------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind",
    ["approve", "reject", "pause", "resume", "take_over"],
)
def test_control_message_accepts_every_closed_verb(kind: str) -> None:
    """All 5 D-01 verbs construct cleanly."""

    msg = ControlMessage(kind=kind)
    assert msg.kind == kind
    assert msg.payload is None


def test_control_message_rejects_unknown_kind() -> None:
    """A verb outside the closed Literal raises ValidationError."""

    with pytest.raises(ValidationError):
        ControlMessage(kind="foo")


def test_control_message_rejects_extra_field() -> None:
    """``extra="forbid"`` rejects an unknown top-level field."""

    with pytest.raises(ValidationError):
        ControlMessage(kind="approve", smuggled="x")


def test_control_message_payload_none_and_json() -> None:
    """``payload`` is opaque: accepts None and an arbitrary JSON object."""

    assert ControlMessage(kind="approve", payload=None).payload is None
    msg = ControlMessage(kind="pause", payload={"any": "json", "n": 1})
    assert msg.payload == {"any": "json", "n": 1}


# --------------------------------------------------------------------
# ControlMailbox — enqueue / has_pending / drain_all FIFO (D-03)
# --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mailbox_has_pending_lifecycle() -> None:
    """has_pending: False fresh -> True after enqueue -> False after drain."""

    mailbox = ControlMailbox()
    assert mailbox.has_pending() is False

    await mailbox.enqueue(ControlMessage(kind="approve"))
    assert mailbox.has_pending() is True

    mailbox.drain_all()
    assert mailbox.has_pending() is False


@pytest.mark.asyncio
async def test_mailbox_drain_all_fifo_and_empties() -> None:
    """drain_all returns messages in FIFO order and strands nothing."""

    mailbox = ControlMailbox()
    await mailbox.enqueue(ControlMessage(kind="pause"))
    await mailbox.enqueue(ControlMessage(kind="resume"))

    drained = mailbox.drain_all()
    assert [m.kind for m in drained] == ["pause", "resume"]
    assert mailbox.has_pending() is False
    # A second drain on an empty mailbox returns an empty list (no strand).
    assert mailbox.drain_all() == []


# --------------------------------------------------------------------
# registry — register / get / deregister round-trip + missing-key safety
# --------------------------------------------------------------------


class _FakeState:
    """Stand-in for FastAPI ``app.state`` (a bare attribute bag)."""


def test_registry_round_trip() -> None:
    """register then get returns the same mailbox; deregister removes it."""

    state = _FakeState()
    mailbox = ControlMailbox()

    registry.register(state, "turn_abc", mailbox)
    assert registry.get(state, "turn_abc") is mailbox

    registry.deregister(state, "turn_abc")
    assert registry.get(state, "turn_abc") is None


def test_registry_get_unknown_returns_none() -> None:
    """get on a fresh state (no registry yet) returns None, never raises."""

    assert registry.get(_FakeState(), "never_registered") is None


def test_registry_deregister_missing_is_safe() -> None:
    """deregister on an unknown turn_id (and a fresh state) does not raise."""

    state = _FakeState()
    registry.deregister(state, "never_registered")  # fresh state, no-op
    registry.register(state, "turn_x", ControlMailbox())
    registry.deregister(state, "turn_x")
    registry.deregister(state, "turn_x")  # double-deregister is a no-op


# --------------------------------------------------------------------
# Plan-02 INTEGRATION tests — the route + Seam-A wiring (this plan).
#
# These drive the real FastAPI app via httpx.ASGITransport (API-08 /
# D-20 — never the synchronous test-client). ``PROMPT_OPTIMIZER_HOME``
# redirects DB_PATH under tmp_path so the lifespan opens a throwaway
# migrated DB and ``control_events`` row counts are isolated per test.
# --------------------------------------------------------------------


def _fresh_control_app(monkeypatch: pytest.MonkeyPatch, tmp_path) -> typing.Any:
    """Reload paths under tmp_path and build a fresh app.

    Mirrors ``test_turn_streaming.py::_fresh_app``: monkeypatch
    ``PROMPT_OPTIMIZER_HOME`` so DB_PATH lands under ``tmp_path``, purge
    ``sse_starlette`` (so the route's ``EventSourceResponse`` reload picks
    up the current ``starlette.responses.Response`` identity — the D-18
    smoke-test interaction), then reload paths + jsonl_log + lifespan +
    the turn route + main so the lifespan opens a fresh migrated DB and
    the turn handler closes over the fresh paths.
    """

    monkeypatch.setenv("PROMPT_OPTIMIZER_HOME", str(tmp_path))

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


async def _count_control_events(db) -> int:
    """Return the number of rows in ``control_events`` (D-07 audit)."""

    async with db.execute("SELECT COUNT(*) FROM control_events") as cur:
        row = await cur.fetchone()
    return int(row[0])


async def test_post_control_202_on_live_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A directly-seeded live mailbox → 202 + enqueue + exactly one row (D-04/D-07)."""

    app = _fresh_control_app(monkeypatch, tmp_path)
    async with app.router.lifespan_context(app):
        # Directly seed a live mailbox for a known turn_id (the turn loop
        # registers it in production; here we register it by hand to prove
        # the route's 202 path in isolation).
        mailbox = ControlMailbox()
        app.state.control_registry["turn_live"] = mailbox

        before = await _count_control_events(app.state.db)

        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/turns/turn_live/control",
                json={"kind": "approve", "payload": {"note": "ok"}},
            )

        assert resp.status_code == 202, resp.text
        assert resp.json() == {"status": "accepted", "turn_id": "turn_live"}
        # The message landed in the mailbox (enqueue happened).
        assert mailbox.has_pending() is True
        drained = mailbox.drain_all()
        assert [m.kind for m in drained] == ["approve"]
        # Exactly one control_events row persisted (D-07 persist-only-on-202).
        after = await _count_control_events(app.state.db)
        assert after == before + 1


async def test_post_control_404_unknown_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """An unknown turn_id → 404 with NO control_events row written (D-07)."""

    app = _fresh_control_app(monkeypatch, tmp_path)
    async with app.router.lifespan_context(app):
        before = await _count_control_events(app.state.db)

        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/turns/never_registered/control",
                json={"kind": "approve"},
            )

        assert resp.status_code == 404, resp.text
        # No persistence on the 404 path (D-07).
        after = await _count_control_events(app.state.db)
        assert after == before


async def test_post_control_422_on_unknown_kind(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """An unknown ``kind`` outside the closed Literal → 422 (no row written)."""

    app = _fresh_control_app(monkeypatch, tmp_path)
    async with app.router.lifespan_context(app):
        # Seed a LIVE mailbox so the 422 is provably from the closed Literal
        # (Pydantic body validation), not the 404 unknown-turn path.
        app.state.control_registry["turn_live"] = ControlMailbox()
        before = await _count_control_events(app.state.db)

        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/turns/turn_live/control",
                json={"kind": "definitely_not_a_verb"},
            )

        assert resp.status_code == 422, resp.text
        after = await _count_control_events(app.state.db)
        assert after == before


async def test_post_control_413_on_oversize_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """An oversize opaque payload → 413 BEFORE enqueue/persist (T-11-06)."""

    app = _fresh_control_app(monkeypatch, tmp_path)
    async with app.router.lifespan_context(app):
        mailbox = ControlMailbox()
        app.state.control_registry["turn_live"] = mailbox
        before = await _count_control_events(app.state.db)

        # Payload whose json.dumps length exceeds the 16384-char cap.
        oversize = {"blob": "x" * 20000}

        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/turns/turn_live/control",
                json={"kind": "approve", "payload": oversize},
            )

        assert resp.status_code == 413, resp.text
        # Rejected before enqueue (nothing queued) and before persist.
        assert mailbox.has_pending() is False
        after = await _count_control_events(app.state.db)
        assert after == before


# --------------------------------------------------------------------
# Plan-02 INTEGRATION placeholders for Tasks 2-3 (filled later in this plan).
# --------------------------------------------------------------------


def _pin_decide_to(monkeypatch: pytest.MonkeyPatch, backend: str) -> None:
    """Pin ``decide()`` to a fixed backend so a fake adapter is invoked."""

    from src.routing.schema import RoutingDecision

    def fake_decide(*args, **kwargs):
        return RoutingDecision(
            backend=backend,
            model_or_agent="test-model",
            rationale="test",
            confidence=0.9,
            signals={"task_type": "chat"},
        )

    monkeypatch.setattr("apps.api.routes.turn.decide", fake_decide)


async def _create_thread(client) -> str:
    resp = await client.post("/api/v1/threads", json={"title": "t"})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def test_awaiting_approval_event_fires_midturn(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A control POST mid-stream makes ``awaiting_approval`` appear on the wire.

    Uses a GATED adapter that yields a first ``text_delta`` then BLOCKS on
    an ``asyncio.Event`` until the test enqueues a control message into the
    live turn's mailbox (directly — deterministic, no httpx-buffering
    race). The gate then opens; the generator's Seam-A inter-chunk check
    sees the pending message, emits ``awaiting_approval`` (D-06/D-08), and
    drains the mailbox so the no-op consumer continues to a terminal
    ``done``. The mailbox is then deregistered in the finally (RELI-03).
    """

    import asyncio
    import json as _json
    from typing import AsyncIterator

    from apps.api.backends.chunks import ChatChunk, Done, TextDelta
    from apps.api.backends.protocol import AdapterOptions, Message
    from apps.api.control import ControlMessage

    app = _fresh_control_app(monkeypatch, tmp_path)

    first_yielded = asyncio.Event()
    release = asyncio.Event()

    class GatedAdapter:
        async def stream(
            self,
            prompt: str,
            history: list[Message],
            options: AdapterOptions,
        ) -> AsyncIterator[ChatChunk]:
            yield TextDelta(text="one")
            first_yielded.set()
            # Block until the test has enqueued a control message so the
            # Seam-A gate has something pending on the NEXT chunk.
            await release.wait()
            yield TextDelta(text="two")
            yield Done(tokens_in=1, tokens_out=2, cost_usd=0.001, latency_ms=5)

    app.state.adapters = {"openrouter": GatedAdapter()}
    app.state.settings = {
        "default_max_cost_usd": 0.50,
        "computer_use_opt_in": False,
    }
    _pin_decide_to(monkeypatch, "openrouter")

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)

            events: list[str] = []
            turn_id_holder: dict[str, str] = {}

            async def consume() -> None:
                current_event: str | None = None
                async with client.stream(
                    "POST",
                    f"/api/v1/threads/{thread_id}/turn",
                    json={"message": "hello"},
                ) as resp:
                    assert resp.status_code == 200, await resp.aread()
                    async for line in resp.aiter_lines():
                        if line.startswith("event:"):
                            current_event = line.split(":", 1)[1].strip()
                            events.append(current_event)
                            if current_event == "done":
                                break
                        elif (
                            line.startswith("data:")
                            and current_event == "turn_start"
                        ):
                            turn_id_holder["id"] = _json.loads(
                                line.split(":", 1)[1].strip()
                            )["turn_id"]

            task = asyncio.create_task(consume())

            # Wait until the adapter has yielded its first chunk — the turn
            # is now live and its mailbox is registered server-side.
            await asyncio.wait_for(first_yielded.wait(), timeout=5)
            # Resolve the live turn_id from the registry (single live turn).
            for _ in range(50):
                if app.state.control_registry:
                    break
                await asyncio.sleep(0.02)
            assert app.state.control_registry, "mailbox never registered"
            turn_id = next(iter(app.state.control_registry))
            mailbox = app.state.control_registry[turn_id]

            # Enqueue a pending control message directly, THEN open the gate
            # so the next inter-chunk Seam-A check fires awaiting_approval.
            await mailbox.enqueue(ControlMessage(kind="approve"))
            release.set()

            await asyncio.wait_for(task, timeout=5)

            assert "turn_start" in events
            assert "awaiting_approval" in events, (
                f"awaiting_approval never fired; events={events}"
            )
            assert events[-1] == "done", f"turn did not complete; events={events}"
            # Seam A drained the mailbox; the finally deregistered it.
            assert app.state.control_registry.get(turn_id) is None


async def test_mailbox_deregistered_on_cancel(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A cancelled turn deregisters its mailbox; a later control POST 404s (RELI-03).

    A gated adapter yields one chunk then blocks indefinitely so the turn
    is genuinely mid-stream. The consumer task is cancelled (Pitfall 6 —
    ``task.cancel()`` under ASGITransport, not response close); the turn's
    ``finally`` runs the deregistration, after which a control POST 404s.
    """

    import asyncio
    from typing import AsyncIterator

    from apps.api.backends.chunks import ChatChunk, TextDelta
    from apps.api.backends.protocol import AdapterOptions, Message

    app = _fresh_control_app(monkeypatch, tmp_path)

    first_yielded = asyncio.Event()
    blocked = asyncio.Event()  # never set — the adapter blocks forever

    class BlockingAdapter:
        async def stream(
            self,
            prompt: str,
            history: list[Message],
            options: AdapterOptions,
        ) -> AsyncIterator[ChatChunk]:
            yield TextDelta(text="slow")
            first_yielded.set()
            await blocked.wait()  # block until the turn is cancelled

    app.state.adapters = {"openrouter": BlockingAdapter()}
    app.state.settings = {
        "default_max_cost_usd": 0.50,
        "computer_use_opt_in": False,
    }
    _pin_decide_to(monkeypatch, "openrouter")

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)

            async def consume() -> None:
                async with client.stream(
                    "POST",
                    f"/api/v1/threads/{thread_id}/turn",
                    json={"message": "hello"},
                ) as resp:
                    async for _line in resp.aiter_lines():
                        pass

            task = asyncio.create_task(consume())

            # Wait until the adapter yielded its first chunk — the turn is
            # live and its mailbox is registered server-side.
            await asyncio.wait_for(first_yielded.wait(), timeout=5)
            for _ in range(50):
                if app.state.control_registry:
                    break
                await asyncio.sleep(0.02)
            assert app.state.control_registry, "mailbox never registered"
            turn_id = next(iter(app.state.control_registry))

            # Cancel the consumer task → propagates CancelledError into the
            # turn generator → its finally runs the deregistration.
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            for _ in range(100):
                if app.state.control_registry.get(turn_id) is None:
                    break
                await asyncio.sleep(0.02)

            # A control POST after cancellation 404s — the mailbox was
            # deregistered in turn.py's finally (RELI-03 / T-11-08).
            r = await client.post(
                f"/api/v1/turns/{turn_id}/control",
                json={"kind": "approve"},
            )
            assert r.status_code == 404, r.text


def test_gate_drain_claude_code() -> None:
    pytest.skip("Plan 02 Task 3: control gate drains the mailbox on the Claude Code path")


def test_gate_drain_computer_use() -> None:
    pytest.skip("Plan 02 Task 3: control gate drains the mailbox on the computer-use path")
