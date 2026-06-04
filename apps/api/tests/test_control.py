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

    Mirrors ``test_feedback.py::_fresh_app``: monkeypatch
    ``PROMPT_OPTIMIZER_HOME`` so DB_PATH lands under ``tmp_path``, then
    reload ``apps.api.paths`` (and the lifespan/main modules that close
    over it) so the lifespan opens a fresh migrated DB per test.
    """

    monkeypatch.setenv("PROMPT_OPTIMIZER_HOME", str(tmp_path))
    import apps.api.paths

    importlib.reload(apps.api.paths)

    import apps.api.lifespan

    importlib.reload(apps.api.lifespan)
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


def test_awaiting_approval_event_fires_midturn() -> None:
    pytest.skip("Plan 02 Task 2: awaiting_approval SSE event fires mid-turn")


def test_gate_drain_claude_code() -> None:
    pytest.skip("Plan 02 Task 3: control gate drains the mailbox on the Claude Code path")


def test_gate_drain_computer_use() -> None:
    pytest.skip("Plan 02 Task 3: control gate drains the mailbox on the computer-use path")


def test_mailbox_deregistered_on_cancel() -> None:
    pytest.skip("Plan 02 Task 2: mailbox is deregistered when the turn is cancelled")
