"""ControlMessage model + ControlMailbox (asyncio.Queue wrapper).

Public surface (D-01, D-03):

    ControlMessage      Pydantic v2 model. ``model_config =
                        ConfigDict(extra="forbid")`` (T-05-style closed
                        body), ``kind: Literal[...]`` over the D-01
                        closed verb set (exactly 5 strings), and an
                        OPAQUE ``payload: dict | None`` the substrate
                        never interprets.
    ControlMailbox      Thin wrapper around a private ``asyncio.Queue``.
                        ``enqueue`` (async put), ``has_pending`` (cheap
                        non-empty check), and ``drain_all`` (FIFO
                        get_nowait loop until empty — the D-03
                        drain-all-at-gate semantics so NOTHING is
                        stranded when the turn loop reaches a control
                        gate).

Design notes:

    - The closed ``kind`` Literal mirrors the ``control_events.kind``
      DB-level ``CHECK`` constraint in ``schema_v2.sql`` so an unknown
      verb is rejected at BOTH the model boundary (here) and the
      storage boundary (the audit table) — T-11-03 spoofing mitigation.
    - ``payload`` is opaque (D-01): the mailbox/registry never inspect
      it; Plan 02's route layer owns any payload-shape validation and
      the deferred size cap (T-11-04 accept disposition).
    - ``drain_all`` uses ``get_nowait()`` in a loop rather than draining
      via ``await get()`` so it never blocks at the gate — it returns
      whatever is currently queued and leaves the queue empty.

Cross-refs:
    - 11-01-PLAN Task 1 (behavior + action)
    - apps/api/routes/feedback.py (extra="forbid" + Literal precedent)
    - apps/api/routes/turn.py ~line 1550 (asyncio.Queue Compare-path)
    - apps/api/db/migrations/schema_v2.sql (the kind CHECK mirror)
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

# D-01 closed verb set — EXACTLY these 5 strings. Mirrors the
# ``CHECK (kind IN (...))`` constraint on ``control_events.kind`` in
# ``schema_v2.sql`` so a forged/unknown verb is rejected at both the
# model and storage layers (T-11-03).
ControlKind = Literal["approve", "reject", "pause", "resume", "take_over"]


class ControlMessage(BaseModel):
    """A single backend-internal control command (D-01).

    ``extra="forbid"`` rejects any unknown top-level field with a
    ``ValidationError`` (closed body). ``kind`` is a closed Literal —
    an unknown verb like ``"foo"`` raises. ``payload`` is OPAQUE: the
    substrate never interprets it; it round-trips ``None`` or any JSON
    object verbatim.
    """

    model_config = ConfigDict(extra="forbid")

    kind: ControlKind
    payload: dict[str, Any] | None = None


class ControlMailbox:
    """Per-turn FIFO control inbox backed by a private ``asyncio.Queue``.

    The mailbox is the CTRL-03 substrate half: the route layer (Plan
    02) ``enqueue``s control messages from a concurrent request while
    the turn loop polls ``has_pending`` and, at a control gate, calls
    ``drain_all`` to consume everything currently queued in one shot
    (D-03 drain-all-at-gate — nothing stranded).
    """

    def __init__(self) -> None:
        # Private queue — callers interact only through the three
        # methods below so the FIFO/drain semantics stay enforced.
        self._queue: asyncio.Queue[ControlMessage] = asyncio.Queue()

    async def enqueue(self, message: ControlMessage) -> None:
        """Append ``message`` to the tail of the FIFO queue."""

        await self._queue.put(message)

    def has_pending(self) -> bool:
        """Return ``True`` iff at least one message is currently queued.

        Cheap, non-blocking — the turn loop polls this between steps to
        decide whether to reach a control gate.
        """

        return not self._queue.empty()

    def drain_all(self) -> list[ControlMessage]:
        """Return all currently-queued messages in FIFO order, emptying
        the queue.

        Uses ``get_nowait()`` in a loop so it never blocks: it consumes
        exactly what is queued at call time and leaves ``has_pending()``
        ``False`` (D-03 — nothing stranded). Messages enqueued AFTER the
        drain begins are simply picked up by the next drain.
        """

        drained: list[ControlMessage] = []
        while True:
            try:
                drained.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return drained
