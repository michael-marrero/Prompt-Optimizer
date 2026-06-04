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

import pytest
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
# Plan-02 INTEGRATION placeholders — named, body-level pytest.skip()
# (visible to --collect-only, reported as skipped in a normal run).
# Plan 02 EXTENDS this file by replacing these bodies with real tests.
# --------------------------------------------------------------------


def test_post_control_202_on_live_turn() -> None:
    pytest.skip("Plan 02: POST /control returns 202 on a live turn")


def test_post_control_404_unknown_turn() -> None:
    pytest.skip("Plan 02: POST /control returns 404 for an unknown turn")


def test_awaiting_approval_event_fires_midturn() -> None:
    pytest.skip("Plan 02: awaiting_approval SSE event fires mid-turn")


def test_gate_drain_claude_code() -> None:
    pytest.skip("Plan 02: control gate drains the mailbox on the Claude Code path")


def test_gate_drain_computer_use() -> None:
    pytest.skip("Plan 02: control gate drains the mailbox on the computer-use path")


def test_mailbox_deregistered_on_cancel() -> None:
    pytest.skip("Plan 02: mailbox is deregistered when the turn is cancelled")
