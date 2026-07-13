"""Per-turn ControlMailbox registry helpers (CTRL-03 substrate half).

Public surface:

    register(state, turn_id, mailbox)   Stash a mailbox keyed by
                                        ``turn_id`` in the
                                        ``app.state.control_registry``
                                        dict (created lazily).
    get(state, turn_id) -> ControlMailbox | None
                                        Look up a mailbox; returns
                                        ``None`` on an unknown/removed
                                        ``turn_id`` (never raises).
    deregister(state, turn_id)          Remove a mailbox; safe to call
                                        on a missing key (never raises).

These mirror the ``app.state.adapters`` dict lifecycle (Phase 3): the
registry is a plain ``dict[str, ControlMailbox]`` lazily created the
first time ``register`` runs. ``get``/``deregister`` use ``dict.get`` /
``dict.pop(..., None)`` so a missing key is a no-op, not an error —
Plan 02's cancellation path can ``deregister`` idempotently.

``state`` is duck-typed (the FastAPI ``app.state`` object, or any
object that carries a ``control_registry`` attribute) so this module
never imports ``fastapi`` and the D-18 import-graph guard stays green.

Cross-refs:
    - 11-01-PLAN Task 1 (behavior + action)
    - apps/api/tests/conftest.py (app.state override pattern)
    - Phase 3 lifespan ``app.state.adapters`` dict (the mirrored shape)
"""

from __future__ import annotations

from typing import Any

from apps.api.control.mailbox import ControlMailbox


def _registry(state: Any) -> dict[str, ControlMailbox]:
    """Return the ``control_registry`` dict on ``state``, creating it
    lazily on first use (mirrors the ``app.state.adapters`` pattern)."""

    registry = getattr(state, "control_registry", None)
    if registry is None:
        registry = {}
        state.control_registry = registry
    return registry


def register(state: Any, turn_id: str, mailbox: ControlMailbox) -> None:
    """Register ``mailbox`` under ``turn_id`` in ``app.state.control_registry``.

    Creates the registry dict lazily if it does not exist yet.
    Overwrites any existing entry for the same ``turn_id``.
    """

    _registry(state)[turn_id] = mailbox


def get(state: Any, turn_id: str) -> ControlMailbox | None:
    """Return the ControlMailbox for ``turn_id`` or ``None`` if absent.

    Safe on a missing registry or a missing/removed ``turn_id`` — uses
    ``dict.get`` so it never raises ``KeyError``.
    """

    registry = getattr(state, "control_registry", None)
    if registry is None:
        return None
    return registry.get(turn_id)


def deregister(state: Any, turn_id: str) -> None:
    """Remove the mailbox for ``turn_id`` if present.

    Safe to call on a missing registry or an unknown ``turn_id`` (uses
    ``dict.pop(..., None)``) so Plan 02's cancellation teardown can call
    it idempotently.
    """

    registry = getattr(state, "control_registry", None)
    if registry is None:
        return
    registry.pop(turn_id, None)
