"""``apps.api.control`` — backend-internal control-substrate primitives.

Phase 11 / Wave 0 (CTRL-02 storage half + CTRL-03 substrate half).

Public surface (re-exported for convenient import):

    ControlMessage      Pydantic v2 model — the D-01 closed-verb control
                        command (``kind`` Literal + opaque ``payload``).
    ControlMailbox      ``asyncio.Queue`` wrapper — per-turn FIFO inbox
                        with ``enqueue`` / ``has_pending`` / ``drain_all``
                        (D-03 drain-all-at-gate semantics).

The per-turn registry helpers (``register`` / ``get`` / ``deregister``)
live in ``apps.api.control.registry`` and operate over a
``dict[str, ControlMailbox]`` stashed at ``app.state.control_registry``
(mirrors the ``app.state.adapters`` lifecycle).

No ``turn.py``, route, or adapter wiring lives here — Plan 02 consumes
these fixed contracts. This package is dependency-free beyond Pydantic
and the stdlib ``asyncio`` module so the D-18 import-graph guard stays
trivially green.
"""

from __future__ import annotations

from apps.api.control.mailbox import ControlMailbox, ControlMessage

__all__ = ["ControlMailbox", "ControlMessage"]
