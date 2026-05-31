"""BackendAdapter Protocol + Message and AdapterOptions dataclasses.

Public surface (BACKEND-02):

    Backend            Literal type alias for the three sentinels.
    Message            Frozen dataclass — conversation history element.
    AdapterOptions     Frozen dataclass — per-turn knobs (model, caps).
    BackendAdapter     ``typing.Protocol`` with one ``async def stream``.

This module mirrors the Phase 1 ``src/routing/schema.py`` convention:
stdlib-only imports plus an internal package import for the
``ChatChunk`` return-type alias. The Protocol is intentionally
single-method so adapters are structurally typed; no inheritance
required, no abstract base class to keep in sync.

``AdapterOptions`` is intentionally minimal — Phase 2 only needs
``model``, ``max_cost_usd``, ``max_steps``, ``cwd``, and
``routing_signals``. UI / settings additions in Phase 4 / 5 add
fields without breaking the existing Protocol because dataclasses
accept extra fields by adding them with defaults.

Cross-refs:
    - 02-RESEARCH.md §"Pattern 2" lines 425-465 (canonical source)
    - 02-CONTEXT.md D-04 (Backend literal mirrors Phase 1 schema)
    - src/routing/schema.py:33 (Backend literal — same string set)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal, Protocol

from apps.api.backends.chunks import ChatChunk

# Mirrors src/routing/schema.py:33 verbatim so Phase 1 RoutingDecision
# values flow directly into the adapter registry without translation.
Backend = Literal["openrouter", "claude_code", "computer_use"]


@dataclass(frozen=True)
class Message:
    """Conversation history element.

    Frozen so adapters can share a history list by reference without
    fearing mutation by another consumer. ``content`` is the
    already-rendered text — Phase 2 does not preserve content blocks
    (tool calls, images) across turns; that lives in Phase 3 storage.
    """

    role: str
    content: str


@dataclass(frozen=True)
class AdapterOptions:
    """Per-turn adapter options.

    Locked-decision defaults live next to the consumer:
    ``DEFAULT_PER_TURN_COST_USD`` in ``cost.py`` and per-backend step
    caps inside each adapter package. ``None`` here means "use the
    default" — the adapter's ``stream`` is responsible for picking the
    fallback.

    ``wall_clock_s`` / ``usd_backstop`` (Phase 9, RELI-02) are the
    per-backend kill-switch ceilings enforced by the ``turn.py``
    orchestration loop, NOT by the adapters. They are SEPARATE, higher
    ceilings than ``max_cost_usd`` — ``usd_backstop`` is the turn-level
    runaway-spend backstop that surfaces ``budget_exceeded`` (D-05),
    distinct from the adapter's own ``cost_cap_exceeded`` accounting.
    The dataclass-level defaults here are the chat-tier D-04 starting
    values (120s / $0.50); ``turn.py``'s per-backend resolver overrides
    them from env (agents default 600s / $2.00). They carry defaults so
    the frozen dataclass stays constructible with no args.

    ``cancel_budget_s`` (Phase 9, RELI-03 / D-06, Open Question 2) is
    the per-backend cancellation budget: the maximum time the upstream
    adapter's ``CancelledError`` teardown (OpenRouter ``in_flight.close()``;
    Claude Code ``client.interrupt()`` + ``disconnect()`` + rmtree;
    computer-use Playwright ``screen.aclose()``) is allowed to run after
    a client disconnect before ``turn.py`` stops waiting and lets the
    re-raise propagate. It is PER-BACKEND because chat teardown is a
    single socket close (~2s, the BACKEND-07 / API-06 budget) while
    agent teardown drives a subprocess interrupt or a Playwright page
    close that legitimately needs a few seconds — a flat 2s ceiling
    would truncate slow agent teardown. The chat-tier default below is
    2.0s; ``turn.py``'s resolver raises it to 5.0s for the agent
    backends (and reads per-backend env knobs).
    """

    model: str | None = None
    max_cost_usd: float | None = None
    max_steps: int | None = None
    cwd: str | None = None
    routing_signals: dict[str, Any] | None = None
    # RELI-02 per-backend kill-switch ceilings (resolved per turn in
    # turn.py from env knobs; D-04 chat-tier defaults below).
    wall_clock_s: float = 120.0
    usd_backstop: float = 0.50
    # RELI-03 / D-06 (Open Question 2) per-backend cancellation budget —
    # the teardown window honored on a client disconnect (resolved per
    # turn in turn.py; chat-tier 2.0s default below, agents 5.0s).
    cancel_budget_s: float = 2.0


class BackendAdapter(Protocol):
    """Single-method async-iterator contract for every backend.

    Implementations live in Wave 1 plans
    (``apps.api.backends.openrouter``, ``apps.api.backends.claude_code``,
    ``apps.api.backends.computer_use``). Phase 3's FastAPI lifespan
    stores them in ``adapters: dict[Backend, BackendAdapter]``.
    """

    async def stream(
        self,
        prompt: str,
        history: list[Message],
        options: AdapterOptions,
    ) -> AsyncIterator[ChatChunk]: ...
