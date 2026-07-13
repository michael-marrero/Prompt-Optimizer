"""Fake ``BackendAdapter`` for unit tests.

``FakeStreamingAdapter`` accepts a pre-built ``list[ChatChunk]`` and
yields them in order. The optional ``sleep_per_chunk`` lets heartbeat
tests stretch the stream across the monkeypatched
``DEFAULT_PING_INTERVAL`` so the ``: ping`` comment line fires.

The fake honors Phase 2 D-04 (terminal Done) by NOT synthesizing
one — every test that wants a terminal chunk MUST include a ``Done``
at the end of its chunks list. This keeps the contract surface in
the tests' hands.

Used by:
    - Wave 4 ``test_turn_streaming.py`` — happy-path streaming +
      heartbeat (``sleep_per_chunk=0.6`` with
      monkeypatched ``DEFAULT_PING_INTERVAL=0.5``) +
      ``request.is_disconnected()`` cancellation.
    - Wave 6 ``test_rename.py`` — the one-shot title-collect path
      iterates a 2-chunk list (``[TextDelta(text="…"), Done()]``).

Cross-refs:
    - ``apps/api/backends/protocol.py`` (BackendAdapter Protocol)
    - ``apps/api/backends/chunks.py`` (ChatChunk union)
    - 03-PLAN-00 Task 3 lines 339-349 (fake adapter contract)
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from apps.api.backends.chunks import ChatChunk, Done  # noqa: F401 -- Done re-exported
from apps.api.backends.protocol import AdapterOptions, BackendAdapter, Message


class FakeStreamingAdapter(BackendAdapter):
    """Pre-built ``list[ChatChunk]`` driven async adapter.

    Constructor:

        chunks            list[ChatChunk] — emitted in order. Tests
                          MUST include a terminal ``Done`` for the
                          D-04 invariant; the fake never synthesizes
                          one.
        sleep_per_chunk   float — optional ``await asyncio.sleep(...)``
                          delay BEFORE each yield. Defaults to 0.0
                          (no delay; chunks emit as fast as the
                          consumer can iterate). Set to a positive
                          value (e.g. 0.6) for heartbeat / disconnect
                          tests so the stream pauses long enough to
                          interleave with the
                          ``DEFAULT_PING_INTERVAL`` task.
    """

    def __init__(
        self,
        chunks: list[ChatChunk],
        *,
        sleep_per_chunk: float = 0.0,
        step_boundaries: int = 0,
    ) -> None:
        self._chunks = chunks
        self._sleep_per_chunk = sleep_per_chunk
        # Phase 11 (CTRL-03): how many of the leading chunks are treated as
        # D-15 "step" boundaries — BEFORE yielding each such chunk the fake
        # runs the SAME gate-and-drain the real claude_code / computer_use
        # adapters run after ``steps.increment()`` (drain only, NEVER yield a
        # ServerSentEvent). Set ``step_boundaries=N`` to exercise an
        # inter-step control gate without a live SDK client.
        self._step_boundaries = step_boundaries

    async def stream(
        self,
        prompt: str,
        history: list[Message],
        options: AdapterOptions,
    ) -> AsyncIterator[ChatChunk]:
        """Yield each pre-built chunk in order.

        The ``prompt`` / ``history`` arguments are accepted to honor the
        ``BackendAdapter`` Protocol but are ignored — tests assert on the
        produced chunk stream. ``options.control_mailbox`` IS honored when
        ``step_boundaries > 0``: the fake gate-and-drains at each of the
        first ``step_boundaries`` chunks, mirroring the agent adapters'
        D-15 boundary (CTRL-03) so the inter-step gate can be unit-tested
        without a live claude_code / computer_use SDK client.
        """

        for index, chunk in enumerate(self._chunks):
            if self._sleep_per_chunk > 0:
                await asyncio.sleep(self._sleep_per_chunk)
            # D-15 step boundary: drain the control mailbox BEFORE yielding
            # this step's chunk (the adapter drains, it NEVER emits SSE).
            if index < self._step_boundaries:
                mailbox = options.control_mailbox
                if mailbox is not None and mailbox.has_pending():
                    mailbox.drain_all()
            yield chunk
