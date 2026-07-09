"""SSE turn handler — POST /api/v1/threads/{thread_id}/turn (HEART of Phase 3).

Public surface (API-02 + API-05 + API-06 + API-07 + STORE-05 + STORE-06):

    router                     APIRouter(prefix="/api/v1", tags=["threads"])
    TurnRequest                Pydantic v2 body: message + optional
                               override_backend + max_cost_usd.
    @router.post("/threads/{thread_id}/turn")
                               EventSourceResponse(event_stream(), ping=15).
    _synthesize_override_decision
                               Internal — synthesise a RoutingDecision
                               when the caller passed override_backend
                               (Pattern 11 + CONTEXT discretion line 179).
    _get_or_create_adapter     Internal — D-15 lazy adapter cache +
                               D-12 STRICT AND gate for computer_use.

Per-turn lifecycle (the route handler's contract):

    1. Pre-stream sanity (D-08 HTTPException path):
       - 404 if ``thread_id`` is unknown (``get_thread`` returns None).
       - 422 if the body is malformed (FastAPI auto via Pydantic).
       - 400 if ``override_backend == "computer_use"`` AND
         ``computer_use_enabled(settings) is False`` (D-12 STRICT AND).

    2. Routing decision:
       - Override path: ``_synthesize_override_decision(backend)``
         (rationale="user override", confidence=1.0). decide() is
         SKIPPED — CONTEXT discretion line 179.
       - Default path: ``await asyncio.to_thread(decide, prompt,
         history, app.state.artifacts, app.state.settings)`` —
         NEVER synchronous (API-07 + D-16). The decide() call walks
         sklearn predict_proba which holds the GIL; the to_thread
         wrap keeps the event loop responsive for concurrent turns
         and the SSE heartbeat.

    3. JSONL log (D-05 + STORE-06):
       - ``await append_routing_decisions_jsonl(decision, thread_id,
         turn_id)`` runs AFTER decide() returns and BEFORE the adapter
         is dispatched. Captures EVERY decision the brain emitted —
         including turns the user cancels mid-stream — so the
         offline-analysis dataset is complete.

    4. Adapter (D-15 lazy cache):
       - ``_get_or_create_adapter(app, decision.backend)`` returns the
         cached instance or constructs one on first use. computer_use
         enforces the D-12 STRICT AND gate BEFORE construction so an
         opt-out caller never sees the adapter's RuntimeError path.

    5. SSE event_stream (D-06 + D-07 + D-08 mid-stream):
       - ``EventSourceResponse(event_stream(), ping=15)`` wraps the
         async generator. ping=15 is the 15-second heartbeat that
         satisfies API-05 even when the underlying adapter takes
         minutes to produce its first chunk (Claude Code multi-tool
         workflow, computer-use multi-screenshot loop).
       - Each chunk is serialised as a named SSE event keyed by
         ``chunk.type``: ``event: text_delta\\ndata: <model_dump_json>\\n\\n``
         (D-07 — never bare ``data:`` lines).
       - The generator buffers every ChatChunk in memory. On terminal
         Done it commits ONE BEGIN/COMMIT writing the user message +
         the assistant message (collapsed text + content_blocks JSON) +
         the routing_decisions row (D-04 + STORE-05 via
         ``db.queries.persist_turn``).
       - ``request.is_disconnected()`` is polled per chunk as a
         defense-in-depth proactive cancellation check; sse-starlette's
         own ``_listen_for_disconnect`` task handles the real-network
         case. Under ASGITransport (test path) both polls are no-ops
         per RESEARCH Pitfall 6; tests use ``task.cancel()``.

    6. Cancellation (Pattern 7 + PEP 789):
       - ``except asyncio.CancelledError`` emits a terminal
         ``StreamError(cancelled)`` + ``Done`` pair THEN re-raises so
         upstream adapters' CancelledError handlers fire (which close
         provider connections within the 2-second budget from
         BACKEND-07 / API-06). The buffered ``Done`` ensures the
         ``finally`` block's ``persist_turn`` call still lands.

    7. D-19 logging:
       - ``turn_start thread_id=... user_msg_len=... turn_id=...``
         (INFO at handler entry).
       - ``routing_decision backend=... model=... rationale='...'
         confidence=... turn_id=...`` (INFO after decide / synthesise).
       - ``turn_done thread_id=... backend=... cost_usd=... tokens_in=...
         tokens_out=... latency_ms=... status=... turn_id=...`` (INFO
         in the ``finally`` block after persist_turn). DEBUG (off by
         default) for per-chunk shape — never INFO per chunk.

**Anti-patterns explicitly forbidden in this module:**
    - NEVER call ``decide()`` synchronously (D-16 + API-07).
    - NEVER write to SQLite per chunk (D-04 + STORE-05).
    - NEVER skip the JSONL log (STORE-06).
    - NEVER use a query-param for ``override_backend`` (body field only).
    - NEVER construct adapters in healthz (D-18 anti-pattern).
    - NEVER duplicate ``dotenv.load_dotenv()`` or
      ``install_redaction_filter()`` (both run at ``apps.api.__init__``
      import time and are idempotent).
    - NEVER use a bare ``data:`` SSE line (D-07 — events MUST be
      named with the ``event: <chunk.type>`` header).
    - NEVER use the synchronous FastAPI test-client wrapper (D-20 /
      API-08; the negative-grep guard enforces).

Cross-refs:
    - 03-CONTEXT.md API-02 (SSE ChatChunk stream)
    - 03-CONTEXT.md API-05 (15s heartbeat)
    - 03-CONTEXT.md API-06 (2-second cancellation budget)
    - 03-CONTEXT.md API-07 (asyncio.to_thread for decide)
    - 03-CONTEXT.md D-04 (one transaction per turn on Done)
    - 03-CONTEXT.md D-05 (jsonl BEFORE adapter dispatch)
    - 03-CONTEXT.md D-06 (sse-starlette EventSourceResponse ping=15)
    - 03-CONTEXT.md D-07 (named SSE events keyed by chunk.type)
    - 03-CONTEXT.md D-08 (HTTPException pre-stream; StreamError+Done
      mid-stream)
    - 03-CONTEXT.md D-12 (computer-use STRICT AND env+settings)
    - 03-CONTEXT.md D-15 (lazy adapter cache)
    - 03-CONTEXT.md D-16 (asyncio.to_thread anti-pattern guard)
    - 03-CONTEXT.md D-19 (turn_start + routing_decision + turn_done
      INFO logs)
    - 03-CONTEXT.md discretion line 179 (override_backend body field)
    - 03-RESEARCH.md §"Pattern 2" lines 246-309 (SSE generator + buffer
      + persist canonical source)
    - 03-RESEARCH.md §"Pattern 7" lines 517-543 (heartbeat assertion)
    - 03-RESEARCH.md §"Pattern 11" lines 672-697 (override synthesis)
    - 03-RESEARCH.md §"Pattern 13" lines 742-783 (lazy adapter +
      computer-use AND gate)
    - 03-RESEARCH.md §"Pitfall 6" lines 946-951 (cancellation under
      ASGITransport — task.cancel(), not response.aclose())
    - 03-PATTERNS.md §"Excerpt 2" lines 158-228 (lift-source from
      apps/api/backends/openrouter/adapter.py:stream)
    - apps/api/backends/openrouter/adapter.py:181-360 (the canonical
      streaming-generator structure this handler mirrors)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import secrets
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from apps.api.backends.chunks import (
    ChatChunk,
    Done,
    Screenshot,
    StreamError,
)
from apps.api.backends.cost import DEFAULT_PER_TURN_COST_USD
from apps.api.backends.logging_filter import _redact_text
from apps.api.backends.protocol import AdapterOptions
from apps.api.control.mailbox import ControlMailbox
from apps.api.backends.protocol import Message as AdapterMessage
from apps.api.blobs import _maybe_externalize_screenshot
from apps.api.db.queries import (
    get_thread,
    get_thread_messages,
    persist_turn,
)
from apps.api.jsonl_log import append_routing_decisions_jsonl
from apps.api.paths import PROJECT_ROOT
from apps.api.settings import computer_use_enabled
from src.routing.decide import decide
from src.routing.schema import RoutingDecision

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["threads"])


# --------------------------------------------------------------------
# Pydantic v2 request model
# --------------------------------------------------------------------


class TurnRequest(BaseModel):
    """Body of ``POST /api/v1/threads/{thread_id}/turn``.

    Fields:
      message:          The user's prompt. Required. Empty strings
                        are passed through to ``decide()`` which has
                        its own V5 short-circuit (Plan 06 / Phase 1).
      override_backend: Optional caller-supplied backend that BYPASSES
                        ``decide()`` (CONTEXT discretion line 179).
                        Used by the Phase 5 UI-05 model picker.
      max_cost_usd:     Optional per-turn cost cap override; falls back
                        to ``settings.default_max_cost_usd`` then to
                        ``DEFAULT_PER_TURN_COST_USD`` (50¢).

    The closed ``Literal[...]`` on ``override_backend`` mirrors the
    Phase 1 ``Backend`` literal so a typo at the wire surface (e.g.
    ``"computer-use"`` with a hyphen) returns 422 instead of silently
    landing on a fallback. Mirrors the Phase 1 + Phase 2 string set
    exactly (``openrouter`` / ``claude_code`` / ``computer_use``).
    """

    message: str
    override_backend: Literal[
        "openrouter", "claude_code", "computer_use"
    ] | None = None
    max_cost_usd: float | None = None


# --------------------------------------------------------------------
# Override synthesis — Pattern 11 + CONTEXT discretion line 179
# --------------------------------------------------------------------


# Per-backend sensible-default model_or_agent. Mirrors the Phase 1
# fallback choices (config.FALLBACK_MODEL_OR_AGENT for openrouter is
# ``openrouter/auto``; Phase 2 adapters consume the strings below as
# their canonical sentinels).
_OVERRIDE_DEFAULTS: dict[str, str] = {
    "openrouter": "openrouter/auto",
    "claude_code": "claude-agent-sdk",
    "computer_use": "computer-use-2025-11-24",
}


# --------------------------------------------------------------------
# RELI-01 retry-loop constants (D-02) + RELI-02 per-backend ceilings (D-04)
# --------------------------------------------------------------------


# D-02: up to 3 total attempts (2 retries), base 0.5s, cap 8s, full
# jitter. Worst-case ~10-15s before a graceful terminal error keeps
# interactive chat responsive. Implemented with stdlib ``random`` —
# no library (RESEARCH State of the Art: full-jitter is
# random.uniform(0, min(cap, base*2**attempt))).
RETRY_BASE_S: float = 0.5
RETRY_CAP_S: float = 8.0
RETRY_MAX_ATTEMPTS: int = 3


# Per-backend wall-clock + USD kill-switch ceilings (RELI-02, D-04).
# Starting defaults: OpenRouter chat is short-lived (120s / $0.50);
# Claude Code + computer-use agents run longer multi-step workflows
# (600s / $2.00). The ``usd_backstop`` is a SEPARATE, higher ceiling
# than the per-turn ``max_cost_usd`` cost cap — it is the runaway-spend
# backstop that surfaces ``budget_exceeded`` (D-05), NOT
# ``cost_cap_exceeded``. Each is overridable from env per A5/D-04.
_BACKEND_CEILING_DEFAULTS: dict[str, tuple[float, float]] = {
    # backend: (wall_clock_s, usd_backstop)
    "openrouter": (120.0, 0.50),
    "claude_code": (600.0, 2.00),
    "computer_use": (600.0, 2.00),
}

# Env knob names per backend (planner's discretion per D-04/A5). Absent
# env var → the D-04 starting default; present env var → its value.
_BACKEND_CEILING_ENV: dict[str, tuple[str, str]] = {
    # backend: (wall_clock_env, usd_env)
    "openrouter": ("RELI_OPENROUTER_WALL_S", "RELI_OPENROUTER_USD"),
    "claude_code": ("RELI_CLAUDE_CODE_WALL_S", "RELI_CLAUDE_CODE_USD"),
    "computer_use": ("RELI_COMPUTER_USE_WALL_S", "RELI_COMPUTER_USE_USD"),
}


# RELI-03 / D-06 (Open Question 2): per-backend CANCELLATION budget — the
# teardown window honored on a client disconnect. Chat is a single socket
# close (~2s, the BACKEND-07 / API-06 budget); the agent backends drive a
# subprocess interrupt (Claude Code) or a Playwright page close
# (computer-use) that legitimately needs a few seconds, so a flat 2s
# ceiling would TRUNCATE slow agent teardown. Distinct from the wall-clock
# kill-switch above (which bounds the live turn, not the teardown).
_BACKEND_CANCEL_BUDGET_DEFAULTS: dict[str, float] = {
    "openrouter": 2.0,
    "claude_code": 5.0,
    "computer_use": 5.0,
}

# Env knob names per backend for the cancel budget (mirrors the ceiling
# resolver convention). Absent → the default above; present → its value.
_BACKEND_CANCEL_BUDGET_ENV: dict[str, str] = {
    "openrouter": "RELI_OPENROUTER_CANCEL_S",
    "claude_code": "RELI_CLAUDE_CODE_CANCEL_S",
    "computer_use": "RELI_COMPUTER_USE_CANCEL_S",
}


def _resolve_env_float(name: str, default: float) -> float:
    """Return ``float(os.environ[name])`` or ``default`` when unset/invalid.

    A malformed env value (non-numeric) falls back to the D-04 default
    rather than crashing the turn — the ceiling is a safety backstop, so
    a typo in a knob must never take the kill-switch offline.
    """

    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning(
            "ignoring non-numeric %s=%r — using default %s",
            name,
            raw,
            default,
        )
        return default


def _resolve_backend_ceilings(backend: str) -> tuple[float, float]:
    """Resolve ``(wall_clock_s, usd_backstop)`` for ``backend`` (RELI-02).

    Reads the per-backend env knobs (``RELI_<BACKEND>_WALL_S`` /
    ``RELI_<BACKEND>_USD``); each falls back to the D-04 starting default
    (``_BACKEND_CEILING_DEFAULTS``) when its env var is unset. An unknown
    backend (unreachable in normal flow — the Backend literal constrains
    the value) falls back to the conservative chat-tier defaults.
    """

    wall_default, usd_default = _BACKEND_CEILING_DEFAULTS.get(
        backend, (120.0, 0.50)
    )
    wall_env, usd_env = _BACKEND_CEILING_ENV.get(
        backend, ("RELI_OPENROUTER_WALL_S", "RELI_OPENROUTER_USD")
    )
    wall_clock_s = _resolve_env_float(wall_env, wall_default)
    usd_backstop = _resolve_env_float(usd_env, usd_default)
    return wall_clock_s, usd_backstop


def _resolve_cancel_budget(backend: str) -> float:
    """Resolve the per-backend cancellation budget (RELI-03 / D-06, OQ2).

    Reads the per-backend env knob (``RELI_<BACKEND>_CANCEL_S``); falls
    back to ``_BACKEND_CANCEL_BUDGET_DEFAULTS`` when unset (chat 2.0s,
    agents 5.0s). An unknown backend (unreachable — the Backend literal
    constrains the value) falls back to the conservative chat budget so a
    teardown can never block the re-raise indefinitely.

    This is the window ``turn.py`` waits for the upstream adapter's
    CancelledError teardown (socket close / subprocess interrupt /
    Playwright page close) before letting the re-raise propagate — slow
    agent teardown gets its full budget; a hung teardown cannot wedge the
    cancellation past it.
    """

    default = _BACKEND_CANCEL_BUDGET_DEFAULTS.get(backend, 2.0)
    env_name = _BACKEND_CANCEL_BUDGET_ENV.get(
        backend, "RELI_OPENROUTER_CANCEL_S"
    )
    return _resolve_env_float(env_name, default)


# --------------------------------------------------------------------
# RELI-02 kill-switch terminal-pair emitters (SECURE-07 redacted)
# --------------------------------------------------------------------


def _kill_switch_pair(
    buffer: list[ChatChunk],
    decision: RoutingDecision,
    *,
    code: str,
    message: str,
) -> list[ServerSentEvent]:
    """Build + buffer a redacted ``StreamError(code) + Done`` terminal pair.

    Shared by the wall-clock and USD kill-switches. ``message`` is ALWAYS
    routed through ``_redact_text`` (SECURE-07) so no kill-switch reason
    can carry an unredacted secret across the SSE boundary. Both chunks
    are appended to ``buffer`` (so ``persist_turn`` records the terminal
    Done + the error status) and returned as the two SSE events the
    caller must yield, in order.
    """

    err = StreamError(
        code=code,  # type: ignore[arg-type] — closed D-05 vocabulary
        message=_redact_text(message),
        retriable=False,
    )
    buffer.append(err)
    done = Done(routing_signals=decision.signals)
    buffer.append(done)
    return [
        ServerSentEvent(event=err.type, data=err.model_dump_json()),
        ServerSentEvent(event=done.type, data=done.model_dump_json()),
    ]


def _wall_clock_kill(
    buffer: list[ChatChunk],
    decision: RoutingDecision,
    options: AdapterOptions,
) -> list[ServerSentEvent]:
    """Terminal pair for a wall-clock deadline trip (RELI-02, D-05).

    ``code="wall_clock_exceeded"`` is DISTINCT from the provider-level
    ``timeout`` (D-05 anti-pattern: do not reuse ``timeout`` for the
    wall-clock kill). The reason is plain-English and redacted.
    """

    return _kill_switch_pair(
        buffer,
        decision,
        code="wall_clock_exceeded",
        message=(
            f"Stopped — this turn hit its {int(options.wall_clock_s)}s limit."
        ),
    )


def _budget_kill(
    buffer: list[ChatChunk],
    decision: RoutingDecision,
    options: AdapterOptions,
) -> list[ServerSentEvent]:
    """Terminal pair for a USD backstop trip (RELI-02, D-05).

    ``code="budget_exceeded"`` is DISTINCT from the adapter-level
    ``cost_cap_exceeded`` — this is the turn-level runaway-spend
    kill-switch sitting above the per-turn cost cap. The reason is
    plain-English and redacted.
    """

    return _kill_switch_pair(
        buffer,
        decision,
        code="budget_exceeded",
        message=(
            "Stopped — this turn reached its "
            "${:.2f} budget.".format(options.usd_backstop)
        ),
    )


def _synthesize_override_decision(
    backend: str, model_or_agent: str | None = None
) -> RoutingDecision:
    """Return a ``RoutingDecision`` for the caller-supplied backend.

    Pattern 11: skips the ``decide()`` brain entirely and emits a
    synthesised decision so the UI's model-picker override flows
    through the same persistence + SSE pipeline as a real routed
    turn. ``rationale="user override"`` is the literal string the
    Wave 6 ``test_override_backend`` regression test asserts on.
    ``confidence=1.0`` reflects user-supplied intent (no model
    uncertainty); ``signals={"override": True}`` marks the row in
    the routing_decisions table so offline analysis can filter
    override rows out cleanly.

    ``model_or_agent`` (Phase 7 Plan 07-08 — Compare lanes): when
    provided, FORCE this exact provider-ready identifier instead of the
    per-backend default. The Compare path forces a specific OpenRouter
    slug per lane (e.g. ``"openai/gpt-5"``) so each column's
    ``routing_decision`` echoes the model the lane streamed from. The
    caller MUST have validated the slug against the allowlist first
    (``_compare_model_allowlist`` — T-07-16 SSRF/over-fetch guard);
    this function does NOT re-validate. When ``None`` (the Phase 5
    UI-05 override path), fall back to the per-backend default.
    """

    # IN-03: ``.get`` with a safe fallback rather than a bare subscript.
    # Callers constrain ``backend`` to the three known values today, so
    # this is unreachable now — but a future caller passing an out-of-set
    # backend gets a valid model identifier instead of an unhandled
    # KeyError mid-stream.
    resolved_model = model_or_agent or _OVERRIDE_DEFAULTS.get(
        backend, "openrouter/auto"
    )
    return RoutingDecision(
        backend=backend,  # type: ignore[arg-type] — Literal check at body
        model_or_agent=resolved_model,
        rationale="user override",
        confidence=1.0,
        signals={"override": True},
    )


# --------------------------------------------------------------------
# Compare forced-model allowlist — Phase 7 Plan 07-08 (Seam A, T-07-16)
# --------------------------------------------------------------------


# The two models that DEFAULT the Compare lanes (RESEARCH Open Question 1).
# Choice: two strong OpenRouter chat models — GPT-5 (lane 0) + Claude
# Sonnet 4.5 (lane 1). GPT-5 is the auto-router's frequent strong-tier
# pick (it is a verified ``api_model`` in config/model_mapping.json);
# Claude Sonnet 4.5 is the strong alternate the UI-SPEC §Copywriting
# Compare-card example names ("Claude Sonnet 4.5 · 1.84s · $0.0042").
# Both are on the OpenRouter aggregator, so each lane dispatches through
# the single ``openrouter`` adapter with the slug forced per lane.
_COMPARE_DEFAULT_MODELS: tuple[str, str] = (
    "openai/gpt-5",
    "anthropic/claude-sonnet-4.5",
)


def _compare_model_allowlist() -> frozenset[str]:
    """Return the set of model IDs a Compare lane may force (SSRF guard).

    T-07-16: a Compare request supplies two model IDs that select which
    upstream model each lane calls — a forced-model / over-fetch surface.
    The client must NOT be able to name an arbitrary upstream model, so
    this allowlist gates every requested slug BEFORE dispatch; anything
    off-list is rejected (422) by ``post_compare``.

    The allowlist is the UNION of:

      - Every verified OpenRouter ``api_model`` slug in
        ``config/model_mapping.json`` (provider == "openrouter" with a
        non-null ``api_model``). These are the slugs the routing brain
        itself resolves to, so the Compare path can force any of them.
      - The two ``_COMPARE_DEFAULT_MODELS`` lane defaults. Claude Sonnet
        4.5 is the locked default alternate (UI-SPEC) but is not a
        benchmark-dataset slug in model_mapping.json, so it is added
        explicitly here rather than silently widening the mapping.

    Read from disk on each call (cheap — a single small JSON file) so a
    user editing ``config/model_mapping.json`` to add an OpenRouter model
    sees it in Compare without a server restart. Mirrors how
    ``decide()`` reloads the mapping via its artifacts dict.
    """

    allow: set[str] = set(_COMPARE_DEFAULT_MODELS)
    mapping_path = PROJECT_ROOT / "config" / "model_mapping.json"
    try:
        with open(mapping_path, "r", encoding="utf-8") as fh:
            mapping = json.load(fh)
    except (OSError, ValueError):
        # Missing / malformed mapping → fall back to the locked defaults
        # only. The guard stays CLOSED (never opens to arbitrary slugs)
        # so a damaged config can never turn into an SSRF hole.
        return frozenset(allow)

    for entry in mapping.values():
        if not isinstance(entry, dict):
            continue
        if entry.get("provider") != "openrouter":
            continue
        api_model = entry.get("api_model")
        if isinstance(api_model, str) and api_model:
            allow.add(api_model)
    return frozenset(allow)


# --------------------------------------------------------------------
# D-05 allowlist reroute synthesis (Phase 5 — NOT the override synth)
# --------------------------------------------------------------------


# Neutral auto-route rationale for a silent reroute (D-07). This reads
# like a normal route to the fallback backend — it deliberately carries
# NO "X disabled" / "rerouted" visible-noise text (D-07 rejects that)
# so the UI's RoutingChip renders the plain "Routed to …" chip, not the
# OverrideChip and not a noisy reroute banner.
_REROUTE_RATIONALE: str = "routed to the best available backend"


def _synthesize_reroute_decision(
    backend: str, original: RoutingDecision
) -> RoutingDecision:
    """Return a silent auto-route ``RoutingDecision`` for the fallback ``backend``.

    Distinct from ``_synthesize_override_decision``: that synth marks the
    row as a user override (``rationale="user override"``,
    ``signals={"override": True}``) which is WRONG for a D-05/D-07 silent
    reroute. This synth produces a neutral auto-route-style decision:

      - ``rationale`` is the neutral ``_REROUTE_RATIONALE`` — no
        "disabled" / "rerouted" noise (D-07).
      - ``signals.override`` is ABSENT (so RoutingChip renders the normal
        "Routed to …" chip, not the OverrideChip). The original decision's
        telemetry signals are preserved for offline analysis and a
        ``rerouted_from`` breadcrumb is added so the offline dataset can
        still reconstruct what the brain originally picked.
      - ``confidence`` carries the original decision's confidence forward
        (the reroute does not invent a new uncertainty estimate; the
        top-class confidence the brain reported still describes how sure
        the brain was about the prompt's intent).

    The ``model_or_agent`` for the fallback backend reuses the same
    per-backend default ``decide()``/the override path would emit (the
    ``_OVERRIDE_DEFAULTS`` table — ``openrouter`` → ``openrouter/auto``)
    so the rerouted turn dispatches with a valid model identifier.
    """

    # IN-03: guarded lookup — see ``_synthesize_override_decision``.
    model_or_agent = _OVERRIDE_DEFAULTS.get(backend, "openrouter/auto")

    # Preserve the original telemetry signals (never key material — Phase
    # 1 composes signals from stage telemetry only) and add a breadcrumb.
    # ``override`` is intentionally NOT set so the chip stays neutral.
    signals = dict(getattr(original, "signals", None) or {})
    signals.pop("override", None)
    signals["rerouted_from"] = original.backend
    # DEF-1a: also record the original *model* so the offline dataset can
    # reconstruct the brain's full pick (backend + model), not just backend.
    signals["rerouted_from_model"] = original.model_or_agent

    return RoutingDecision(
        backend=backend,  # type: ignore[arg-type] — Backend literal
        model_or_agent=model_or_agent,
        rationale=_REROUTE_RATIONALE,
        confidence=original.confidence,
        signals=signals,
    )


def _enabled_backends(settings: dict) -> list[str]:
    """Compute the ordered set of dispatch-eligible backends (D-05/D-06).

    - Reads ``settings["backends_enabled"]`` (shape:
      ``{"openrouter": True, "claude_code": True, "computer_use": False}``).
    - Removes ``computer_use`` unless the D-06 STRICT-AND gate passes
      (``computer_use_enabled(settings)`` — env flag AND in-app toggle).
    - Floors the result at ``["openrouter"]`` so an all-disabled settings
      blob never produces an empty allowlist dead-end.

    Order is preserved with ``openrouter`` first when enabled so the
    reroute target selection is deterministic.
    """

    backends_enabled = settings.get("backends_enabled") or {}
    enabled: list[str] = []
    for backend in ("openrouter", "claude_code", "computer_use"):
        if not backends_enabled.get(backend):
            continue
        if backend == "computer_use" and not computer_use_enabled(settings):
            # D-06 STRICT-AND: the toggle alone is not enough; the env
            # flag must also be set. computer_use stays unreachable on
            # auto turns unless BOTH gates are on.
            continue
        enabled.append(backend)

    # Floor — openrouter is always reachable so a turn never dead-ends.
    if not enabled:
        enabled = ["openrouter"]
    return enabled


# --------------------------------------------------------------------
# Lazy adapter cache — D-15 + D-12 STRICT AND gate for computer_use
# --------------------------------------------------------------------


async def _get_or_create_adapter(app: Any, backend: str) -> Any:
    """Return a cached adapter for ``backend`` or build it on demand.

    Pattern 13: ``app.state.adapters`` is empty at lifespan startup
    (D-15). The first turn that routes to a backend instantiates the
    matching adapter and caches it; every subsequent turn to the same
    backend reuses the cached instance. PATCH /settings (Wave 3) calls
    ``app.state.adapters.clear()`` so the next turn rebuilds with
    fresh KeyStore values.

    For ``computer_use``: enforce the D-12 STRICT AND gate
    (``computer_use_enabled(settings)`` requires BOTH the env var
    AND the in-app toggle) BEFORE construction. The gate fires as a
    pre-stream ``HTTPException(400)`` so the caller sees a clean
    error body instead of the adapter's ``RuntimeError`` propagating
    through a half-opened SSE stream.

    Lazy adapter import (B3 pattern from Phase 2): the adapter class
    is imported inside this function rather than at module top so the
    server can boot even when an adapter package has a transient
    import-time defect. The ImportError surfaces as a 500 with a
    crisp message; the other two adapters remain functional.
    """

    if backend in app.state.adapters:
        return app.state.adapters[backend]

    # D-12 STRICT AND gate — fires BEFORE adapter construction so an
    # opt-out caller never trips the adapter's internal RuntimeError.
    if backend == "computer_use" and not computer_use_enabled(
        app.state.settings
    ):
        raise HTTPException(status_code=400, detail="computer-use is OFF — set COMPUTER_USE_OPT_IN=1 in env AND enable in settings panel")

    keystore = app.state.keystore

    try:
        if backend == "openrouter":
            from apps.api.backends.openrouter import OpenRouterAdapter

            adapter = OpenRouterAdapter(api_key=keystore.get("openrouter"))
        elif backend == "claude_code":
            from apps.api.backends.claude_code import ClaudeCodeAdapter

            adapter = ClaudeCodeAdapter(api_key=keystore.get("anthropic"))
        elif backend == "computer_use":
            from apps.api.backends.computer_use import ComputerUseAdapter

            adapter = ComputerUseAdapter(api_key=keystore.get("anthropic"))
        else:
            # Unreachable in normal flow — the Phase 1 Backend literal
            # constrains the value upstream — but defense in depth.
            raise HTTPException(
                status_code=500,
                detail=f"unknown backend: {backend}",
            )
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"{backend} adapter not available: {exc}",
        )
    except RuntimeError as exc:
        # Adapter constructors raise RuntimeError when their required
        # API key is missing (e.g., ClaudeCodeAdapter.__init__ trips
        # _missing_api_key_error() when ANTHROPIC_API_KEY is unset).
        # Convert to a clean pre-stream HTTPException(400) so the Phase
        # 4 UI receives a usable error response instead of the SSE
        # stream hanging on a 500 (D-08 HTTPException path; mirrors the
        # computer-use opt-out gate above).
        key_label = {
            "openrouter": "OPENROUTER_API_KEY",
            "claude_code": "ANTHROPIC_API_KEY",
            "computer_use": "ANTHROPIC_API_KEY",
        }.get(backend, "API key")
        raise HTTPException(
            status_code=400,
            detail=(
                f"{backend} backend requires {key_label} — "
                f"add it via PATCH /api/v1/settings or set the env var"
            ),
        )

    app.state.adapters[backend] = adapter
    return adapter


# --------------------------------------------------------------------
# The endpoint — POST /api/v1/threads/{thread_id}/turn
# --------------------------------------------------------------------


@router.post("/threads/{thread_id}/turn", response_model=None)
async def post_turn(
    thread_id: str, body: TurnRequest, request: Request
) -> EventSourceResponse:
    """Stream one assistant turn back to the caller as SSE.

    Pre-stream errors (D-08 HTTPException path):
      - 404 thread not found.
      - 400 computer-use opt-out (D-12 STRICT AND gate trips inside
        ``_get_or_create_adapter`` BEFORE the SSE response opens).

    Mid-stream errors (D-08 StreamError+Done path):
      - Adapter-level exceptions surface as ChatChunk StreamError
        followed by a terminal Done (Phase 2 D-04 + D-06 invariant).
      - The buffered terminal Done triggers the persist_turn call in
        the finally block so even error turns persist (status="error"
        or "cancelled" per the StreamError code).

    See the module docstring for the full lifecycle narrative.
    """

    app = request.app
    db = app.state.db

    # ----------------------------------------------------------------
    # Pre-stream sanity (D-08 HTTPException path)
    # ----------------------------------------------------------------

    thread = await get_thread(db, thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")

    history_rows = await get_thread_messages(db, thread_id)

    # Phase 1 ``decide()`` expects a ``list[dict]`` history; Phase 2
    # adapters expect a ``list[Message]`` (frozen dataclass). Build
    # both shapes at the boundary so each consumer gets the shape it
    # wants without runtime adaptation deeper in the stack.
    history = [{"role": m.role, "content": m.text} for m in history_rows]
    adapter_history = [
        AdapterMessage(role=m.role, content=m.text) for m in history_rows
    ]

    turn_id = secrets.token_urlsafe(12)

    # Phase 11 (CTRL-01, D-05/RELI-03): mint + register the per-turn
    # ControlMailbox BEFORE the streaming generator runs so a concurrent
    # ``POST /turns/{turn_id}/control`` can find a live mailbox by
    # ``turn_id`` (registry.get → 202) the moment this turn is addressable.
    # Registered here (route scope) so it is guaranteed present before the
    # event_stream generator's ``try``; the generator's ``finally``
    # deregisters it on EVERY exit (happy / cancelled / kill / error) so
    # the registry never leaks a dead turn (RELI-03 — a post-finish control
    # POST then 404s). ``app.state.control_registry`` is seeded in lifespan.
    mailbox = ControlMailbox()
    app.state.control_registry[turn_id] = mailbox

    # D-19 INFO log #1 — turn_start. user_msg_len bounds the log
    # surface (the message body itself is never logged so the
    # RedactionFilter never sees prompt content).
    logger.info(
        "turn_start thread_id=%s user_msg_len=%d turn_id=%s",
        thread_id,
        len(body.message),
        turn_id,
    )

    # ----------------------------------------------------------------
    # Routing decision (override OR asyncio.to_thread(decide))
    # ----------------------------------------------------------------

    if body.override_backend is not None:
        # Pattern 11: skip decide() and synthesise a decision so the
        # UI's manual model picker flows through the same persistence
        # + SSE pipeline as a real routed turn.
        decision = _synthesize_override_decision(body.override_backend)
    else:
        # API-07 + D-16: decide() is synchronous (sklearn predict_proba
        # holds the GIL). asyncio.to_thread keeps the event loop
        # responsive for concurrent turns and the SSE heartbeat task.
        decision = await asyncio.to_thread(
            decide,
            body.message,
            history,
            app.state.artifacts,
            app.state.settings,
        )

        # ------------------------------------------------------------
        # D-05 allowlist post-filter (RESEARCH Option B — post-filter,
        # smallest blast radius; src/routing/decide.py untouched).
        # ------------------------------------------------------------
        #
        # GATED on the override path being absent: this branch only runs
        # for AUTO turns. Explicit ``override_backend`` turns are handled
        # in the ``if`` branch above and are NEVER rerouted (Pitfall 7 —
        # the user's manual pick wins even when that backend is disabled;
        # the existing computer-use 400 guard already validates override
        # turns).
        #
        # If the brain's pick is not in the enabled set, silently re-map
        # to the best enabled backend (prefer openrouter, else the first
        # enabled) with a NEUTRAL auto-route rationale (D-07) — never the
        # override synth.
        enabled = _enabled_backends(app.state.settings)
        if decision.backend not in enabled:
            fallback = "openrouter" if "openrouter" in enabled else enabled[0]
            logger.info(
                "allowlist_reroute from=%s to=%s turn_id=%s",
                decision.backend,
                fallback,
                turn_id,
            )
            decision = _synthesize_reroute_decision(fallback, decision)

    # D-19 INFO log #2 — routing_decision. The rationale is bounded
    # by the Phase 1 fallback suffix locked string + the per-stage
    # signal strings (task_type / agentic_intent / rule_fired); it
    # never embeds user prompt content. Defense in depth: the
    # RedactionFilter applies if a future signals-shape change ever
    # smuggled a key-shaped string in.
    logger.info(
        "routing_decision backend=%s model=%s rationale='%s'"
        " confidence=%.3f turn_id=%s",
        decision.backend,
        decision.model_or_agent,
        decision.rationale,
        decision.confidence,
        turn_id,
    )

    # ----------------------------------------------------------------
    # JSONL log (D-05 + STORE-06) — BEFORE adapter dispatch
    # ----------------------------------------------------------------

    # Capture EVERY decision the brain emitted — including turns the
    # user cancels mid-stream. The write is bounded by PIPE_BUF append
    # atomicity (RESEARCH Open Question 4).
    await append_routing_decisions_jsonl(decision, thread_id, turn_id)

    # ----------------------------------------------------------------
    # Adapter (D-15 lazy cache + D-12 STRICT AND for computer_use)
    # ----------------------------------------------------------------

    # The D-12 gate fires inside _get_or_create_adapter and raises
    # HTTPException(400) BEFORE we open the SSE response — clean
    # error path per D-08.
    adapter = await _get_or_create_adapter(app, decision.backend)

    # Per-turn cost cap precedence: request body > settings >
    # DEFAULT_PER_TURN_COST_USD (50¢).
    # CR-02: distinguish "absent" (None) from an explicit zero. A caller
    # setting `max_cost_usd: 0.0` (a hard "spend nothing" cap) must NOT
    # collapse to the default via a falsy `or` — that silently ignores a
    # legitimate budget, the opposite of the user's intent. Same hazard
    # for `default_max_cost_usd: 0` in settings.
    default_cap = app.state.settings.get("default_max_cost_usd")
    if body.max_cost_usd is not None:
        max_cost_usd = body.max_cost_usd
    elif default_cap is not None:
        max_cost_usd = default_cap
    else:
        max_cost_usd = DEFAULT_PER_TURN_COST_USD

    # RELI-02: resolve the per-backend wall-clock + USD kill-switch
    # ceilings from env (D-04 defaults when unset). These are SEPARATE,
    # higher ceilings than ``max_cost_usd`` — the turn-level runaway
    # backstop that surfaces wall_clock_exceeded / budget_exceeded, NOT
    # the adapter's own cost_cap_exceeded.
    wall_clock_s, usd_backstop = _resolve_backend_ceilings(decision.backend)

    # RELI-03 / D-06 (Open Question 2): resolve the per-backend
    # cancellation budget — chat ~2s, agents ~5s — so slow agent teardown
    # (subprocess interrupt / Playwright close) is not truncated by the
    # chat-tier 2s ceiling on a client disconnect.
    cancel_budget_s = _resolve_cancel_budget(decision.backend)

    options = AdapterOptions(
        model=decision.model_or_agent,
        max_cost_usd=max_cost_usd,
        # max_steps=None → each adapter picks its own default cap
        # (25 for claude_code; 15 for computer_use; N/A for
        # openrouter which is single-round-trip).
        max_steps=None,
        # cwd=None → Wave 5 adds per-thread workspace for claude_code;
        # Phase 2 default tmpdir is fine for v1.
        cwd=None,
        routing_signals=decision.signals,
        wall_clock_s=wall_clock_s,
        usd_backstop=usd_backstop,
        cancel_budget_s=cancel_budget_s,
        # Phase 11 (CTRL-03): thread the per-turn mailbox into the AGENT
        # backends only so each adapter can gate-and-drain at its D-15 step
        # boundary. ``None`` for openrouter — the single-round-trip chat
        # path is never gated (no inter-step boundary to gate at).
        control_mailbox=(
            mailbox
            if decision.backend in ("claude_code", "computer_use")
            else None
        ),
    )

    # ----------------------------------------------------------------
    # SSE event_stream — the streaming generator
    # ----------------------------------------------------------------

    async def event_stream():
        """Yield ServerSentEvent chunks, buffer for persist_turn.

        Buffers every ChatChunk in memory; on terminal Done emits ONE
        BEGIN/COMMIT writing user msg + assistant msg + routing
        decision via ``persist_turn`` (D-04 + STORE-05).

        Cancellation: emits StreamError(cancelled) + Done into the
        buffer THEN re-raises so the upstream adapter's CancelledError
        handler closes the provider connection (Pattern 7 + PEP 789).
        """

        # D-15 (Phase 4): emit routing_decision event BEFORE adapter dispatch
        # so the UI chip renders within ~100ms of POST, well before the
        # first text_delta. ChatChunk union is NOT modified — this event
        # is yielded alongside ChatChunks via the same SSE pipeline.
        # Payload is the structured 5-key record {backend, model_or_agent,
        # rationale, confidence, signals}; payload['signals'] equals
        # Done.routing_signals byte-for-byte (contract test in
        # test_turn_streaming.py::test_routing_decision_event...).
        # Yield happens BEFORE the try/except so a cancellation between
        # adapter creation and adapter.stream() still ships the chip data.
        #
        # Phase 11 (D-05): emit the ``turn_start`` named SSE event as the
        # generator's VERY FIRST yield — it carries the ``turn_id`` so the
        # client knows the capability to address a later control POST at
        # ``POST /turns/{turn_id}/control``. It is a named SIBLING event
        # (Seam A): the frozen 7-variant ChatChunk union is NOT extended,
        # so the chunks.py contract + the Zod port stay byte-for-byte
        # unchanged. Emitted before routing_decision so turn_id is on the
        # wire first.
        yield ServerSentEvent(
            event="turn_start",
            data=json.dumps({"turn_id": turn_id}),
        )

        payload = {
            "backend": decision.backend,
            "model_or_agent": decision.model_or_agent,
            "rationale": decision.rationale,
            "confidence": decision.confidence,
            "signals": decision.signals,
        }
        yield ServerSentEvent(
            event="routing_decision",
            data=json.dumps(payload),
        )

        buffer: list[ChatChunk] = []
        start_t = asyncio.get_event_loop().time()
        # RELI-01 (D-01/D-02/D-03): pre-first-token retry loop. ``attempt``
        # counts establishment tries; ``first_chunk_seen`` is the D-01 gate
        # — once any non-terminal chunk has reached the wire, a later drop
        # is TERMINAL (no retry: retrying would replay already-streamed
        # tokens / re-run side-effecting agent steps; RESEARCH Pitfall 6).
        # The adapters SWALLOW provider errors and yield a terminal
        # ``StreamError + Done`` themselves, so the retry decision inspects
        # the buffered StreamError's ``retriable`` flag (the inherited
        # classification — D-03; no new code→bool table here) BEFORE
        # forwarding it. A retriable pre-first-token StreamError is
        # swallowed (along with the failed attempt's trailing Done) and the
        # stream is re-established after a full-jitter backoff.
        attempt = 0
        first_chunk_seen = False
        # RELI-03 / D-06 (Open Question 2): the live adapter generator, so
        # the cancellation handler can drive + BOUND its teardown
        # (in_flight.close / interrupt / aclose) by the per-backend
        # ``cancel_budget_s``. Hoisted out of the inner loop so the
        # ``except asyncio.CancelledError`` block can reach the active one.
        active_stream_iter: Any = None
        try:
            while True:
                # ``retrying`` marks that THIS attempt already hit a
                # retriable pre-first-token StreamError; its trailing Done
                # (the adapter's terminal pair) must be swallowed too,
                # never forwarded as a successful completion.
                retrying = False
                # RELI-02 kill-switch terminates the WHOLE turn (not just
                # this attempt); ``killed`` propagates the break past the
                # retry loop.
                killed = False
                # Manual iteration (not ``async for``) so each pull can be
                # bounded by ``asyncio.wait_for`` — a provider that hangs
                # BEFORE yielding any chunk (Pitfall 4) must still trip the
                # wall-clock deadline. ``asyncio.timeout()`` is 3.11+; the
                # per-pull ``wait_for`` is the 3.10-safe equivalent
                # (RESEARCH State of the Art).
                stream_iter = adapter.stream(
                    body.message, adapter_history, options
                ).__aiter__()
                active_stream_iter = stream_iter
                while True:
                    # Remaining wall-clock budget bounds this pull. A
                    # non-positive remainder means the deadline already
                    # passed → trip immediately rather than waiting.
                    remaining = (
                        options.wall_clock_s
                        - (asyncio.get_event_loop().time() - start_t)
                    )
                    if remaining <= 0:
                        for ev in _wall_clock_kill(
                            buffer, decision, options
                        ):
                            yield ev
                        killed = True
                        break
                    try:
                        chunk = await asyncio.wait_for(
                            stream_iter.__anext__(), timeout=remaining
                        )
                    except StopAsyncIteration:
                        # Generator exhausted naturally — leave the inner
                        # loop (retry/terminal decision below).
                        break
                    except asyncio.TimeoutError:
                        # Pitfall 4: a pull that out-ran the deadline (e.g.
                        # a hang before the first chunk) is a wall-clock
                        # trip, NOT the provider ``timeout`` code (D-05).
                        for ev in _wall_clock_kill(
                            buffer, decision, options
                        ):
                            yield ev
                        killed = True
                        break

                    # RELI-01 retry gate: a StreamError seen BEFORE the
                    # first real chunk is an establishment failure. If it
                    # is retriable and we have attempts left, DON'T forward
                    # it — swallow it, back off (full jitter), and
                    # re-establish. (D-01: only applies while
                    # ``not first_chunk_seen``.)
                    if (
                        isinstance(chunk, StreamError)
                        and not first_chunk_seen
                        and chunk.retriable
                        and attempt + 1 < RETRY_MAX_ATTEMPTS
                    ):
                        # Full jitter (D-02): sleep in
                        # [0, min(cap, base * 2**attempt)).
                        backoff = min(
                            RETRY_CAP_S, RETRY_BASE_S * (2 ** attempt)
                        )
                        await asyncio.sleep(random.uniform(0, backoff))
                        attempt += 1
                        retrying = True
                        # Swallow this attempt's terminal pair: skip the
                        # rest of THIS generator (its trailing Done lands
                        # next and is dropped by the guard below) and
                        # re-enter the while loop for a fresh attempt.
                        continue
                    # While retrying, drop the failed attempt's trailing
                    # Done so it is never persisted as a success. This only
                    # fires for a Done arriving with NO intervening real
                    # chunk (the adapter's terminal pair after a swallowed
                    # StreamError). The moment a real chunk is forwarded
                    # below, ``retrying`` is cleared so the NEXT Done is the
                    # genuine terminal one.
                    if retrying and isinstance(chunk, Done):
                        continue

                    # RELI-02 wall-clock kill-switch (per-chunk monotonic
                    # check). Catches a stream that produces MANY fast
                    # chunks past the deadline (the per-pull wait_for above
                    # only bounds an inter-chunk hang). The code is DISTINCT
                    # from the provider ``timeout`` (D-05 anti-pattern: do
                    # NOT reuse ``timeout`` for the wall-clock kill).
                    elapsed = asyncio.get_event_loop().time() - start_t
                    if elapsed > options.wall_clock_s:
                        for ev in _wall_clock_kill(buffer, decision, options):
                            yield ev
                        killed = True
                        break

                    # RELI-02 USD kill-switch (D-05). A SEPARATE, higher
                    # ceiling than the adapter's own ``cost_cap_exceeded``
                    # accounting: when the cumulative provider-reported
                    # spend for this turn crosses ``usd_backstop``, emit
                    # ``budget_exceeded`` (NOT ``cost_cap_exceeded``). The
                    # adapters report authoritative cost on the terminal
                    # Done (and may report running cost on chunks); read it
                    # off the chunk and compare to the backstop, mirroring
                    # CostTracker.over_cap()'s ``total() > ceiling`` predicate.
                    chunk_cost = getattr(chunk, "cost_usd", None)
                    if (
                        chunk_cost is not None
                        and chunk_cost > options.usd_backstop
                    ):
                        for ev in _budget_kill(buffer, decision, options):
                            yield ev
                        killed = True
                        break

                    # STORE-04 + D-14: externalize Screenshot chunks
                    # >=256KB BEFORE buffer.append AND BEFORE the SSE yield
                    # so both the wire and the persisted content_blocks
                    # JSON see the image_ref shape. <256KB chunks pass
                    # through unchanged (return-unchanged from the
                    # transcoder). The interception lives here — the
                    # SSE generator is the only callsite per RESEARCH
                    # Pattern 10 lines 635-637.
                    if isinstance(chunk, Screenshot):
                        chunk = _maybe_externalize_screenshot(chunk)
                    # D-01: the first FORWARDED chunk flips the gate. A
                    # terminal StreamError forwarded here (non-retriable,
                    # or attempts exhausted, or post-first-token) does not
                    # need the gate, but setting it is harmless and keeps
                    # the invariant simple: past the first yield, no retry.
                    first_chunk_seen = True
                    # A real chunk reached the wire — this attempt is the
                    # winning one; the next Done is the genuine terminal.
                    retrying = False
                    buffer.append(chunk)
                    yield ServerSentEvent(
                        event=chunk.type,
                        data=chunk.model_dump_json(),
                    )
                    # Phase 11 Seam A (D-03/D-06/D-08): if a control message
                    # is pending in this turn's mailbox, emit the
                    # ``awaiting_approval`` named SSE event (D-08 — emit ONLY
                    # when a message is pending) then drain the mailbox so
                    # the no-op consumer continues. This is the Seam-A owner:
                    # the SSE event is emitted ONLY here by the generator, a
                    # named SIBLING of the frozen ChatChunk union (the
                    # adapters NEVER yield ServerSentEvent — Pitfall 1). The
                    # body fields beyond turn_id+correlation_id are
                    # discretionary (the contract test freezes only the
                    # ChatChunk union, not this event's shape).
                    if mailbox.has_pending():
                        yield ServerSentEvent(
                            event="awaiting_approval",
                            data=json.dumps(
                                {
                                    "turn_id": turn_id,
                                    "correlation_id": secrets.token_urlsafe(
                                        12
                                    ),
                                }
                            ),
                        )
                        mailbox.drain_all()
                    if isinstance(chunk, Done):
                        # D-04 terminal-Done invariant — break so the
                        # finally block fires persist_turn.
                        break
                    # Defense-in-depth proactive disconnect check.
                    # sse-starlette's own ``_listen_for_disconnect``
                    # handles the real-network case. Under ASGITransport
                    # both polls are no-ops per RESEARCH Pitfall 6;
                    # tests use ``task.cancel()`` to trigger cleanup.
                    if await request.is_disconnected():
                        break

                # Inner stream ended. A kill-switch trip (wall-clock / USD)
                # terminated the whole turn — never retry it. Otherwise, if
                # this attempt was abandoned for a retry (retriable
                # pre-first-token failure), re-establish; else the stream
                # completed (or was forwarded terminal) — leave the loop.
                if killed:
                    break
                if retrying and not first_chunk_seen:
                    continue
                break
        except asyncio.CancelledError:
            # Pattern 7 + PEP 789: emit terminal pair into the buffer
            # AND the wire so the client + persistence both see the
            # cancellation, THEN re-raise so the upstream adapter's
            # CancelledError handler closes the provider connection.
            #
            # D-06 keep-partial: the buffer already carries every chunk
            # forwarded before the cancel (the partial ``text_delta``s),
            # so appending the terminal pair here means the ``finally``
            # block's ``persist_turn`` writes the PARTIAL content_blocks
            # with status='cancelled' — the stopped turn survives reload.
            err = StreamError(
                code="cancelled",
                # SECURE-07 uniformity: every StreamError.message
                # constructed in turn.py routes through _redact_text, even
                # this static string, so no construction site can ever
                # carry an unredacted secret.
                message=_redact_text("Stream cancelled by caller."),
                retriable=True,
            )
            buffer.append(err)
            yield ServerSentEvent(event=err.type, data=err.model_dump_json())
            done = Done(routing_signals=decision.signals)
            buffer.append(done)
            yield ServerSentEvent(
                event=done.type, data=done.model_dump_json()
            )
            # RELI-03 / D-06 (Open Question 2): drive the upstream adapter's
            # CancelledError teardown (OpenRouter in_flight.close / Claude
            # Code interrupt+disconnect / computer-use Playwright aclose)
            # and BOUND it by the PER-BACKEND ``cancel_budget_s`` — chat
            # ~2s, agents ~5s. ``aclose()`` throws GeneratorExit into the
            # adapter generator, running its teardown; ``shield`` lets that
            # teardown finish even though THIS task is being cancelled,
            # while ``wait_for`` caps the wait so a hung teardown can never
            # block the re-raise past the budget (slow agent teardown gets
            # its full window; it is NOT truncated to the 2s chat ceiling).
            if active_stream_iter is not None:
                aclose = getattr(active_stream_iter, "aclose", None)
                if aclose is not None:
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(aclose()),
                            timeout=options.cancel_budget_s,
                        )
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        # Budget exhausted (or this task re-cancelled mid
                        # teardown): stop waiting and let the re-raise
                        # propagate. The shielded aclose keeps running to
                        # completion in the background so the provider
                        # connection still closes — we simply do not block
                        # the cancellation past the budget.
                        pass
                    except Exception:
                        # A teardown that raises (e.g. closing an already
                        # closed subprocess) must never mask the
                        # cancellation; swallow and re-raise below.
                        pass
            raise
        finally:
            # Phase 11 (RELI-03, T-11-08): deregister the per-turn mailbox
            # on EVERY exit — happy path, client cancel, wall-clock / USD
            # kill, or any error. This runs FIRST in the finally (before
            # persist_turn) so the registry never leaks a dead turn even if
            # persistence raises. A control POST after this point 404s
            # (registry.get → None), proving the turn is no longer
            # addressable (test_mailbox_deregistered_on_cancel). ``pop(...,
            # None)`` is idempotent — safe even if the turn was never fully
            # registered.
            app.state.control_registry.pop(turn_id, None)

            # STORE-05 + D-04: ONE BEGIN/COMMIT on Done.
            #
            # The Phase 2 D-04 terminal-Done invariant guarantees the
            # buffer's last chunk is a Done at this point — happy path
            # (adapter yields its natural Done), cancellation (handler
            # above appends StreamError+Done), or any provider-error
            # path that the adapter handled with StreamError+Done.
            if buffer and isinstance(buffer[-1], Done):
                # Derive status from the buffer's last StreamError.
                last_error = next(
                    (c for c in buffer if isinstance(c, StreamError)),
                    None,
                )
                if last_error is None:
                    status = "complete"
                elif last_error.code == "cancelled":
                    status = "cancelled"
                else:
                    status = "error"

                user_message_id = secrets.token_urlsafe(12)
                assistant_message_id = secrets.token_urlsafe(12)
                routing_decision_id = secrets.token_urlsafe(12)
                try:
                    await persist_turn(
                        db,
                        thread_id=thread_id,
                        user_text=body.message,
                        user_message_id=user_message_id,
                        assistant_message_id=assistant_message_id,
                        routing_decision_id=routing_decision_id,
                        buffer=buffer,
                        decision=decision,
                        status=status,
                    )
                except Exception:
                    # T-03-Persist-failure: a persist_turn raise is
                    # rare in single-user local mode (DB lock
                    # contention is essentially impossible with one
                    # writer). The SSE stream still terminated
                    # cleanly so the user got the response; the
                    # turn just isn't persisted. logger.exception
                    # captures the failure for operator inspection.
                    logger.exception(
                        "persist_turn failed for turn_id=%s", turn_id
                    )

                # D-19 INFO log #3 — turn_done. Pull usage off the
                # terminal Done (may be None on early-error paths).
                done_chunk = buffer[-1]
                latency_ms = getattr(done_chunk, "latency_ms", None)
                if latency_ms is None:
                    latency_ms = int(
                        (asyncio.get_event_loop().time() - start_t)
                        * 1000
                    )
                logger.info(
                    "turn_done thread_id=%s backend=%s cost_usd=%s"
                    " tokens_in=%s tokens_out=%s latency_ms=%s"
                    " status=%s turn_id=%s",
                    thread_id,
                    decision.backend,
                    getattr(done_chunk, "cost_usd", None),
                    getattr(done_chunk, "tokens_in", None),
                    getattr(done_chunk, "tokens_out", None),
                    latency_ms,
                    status,
                    turn_id,
                )

    # D-06: ping=15 for the 15-second heartbeat that satisfies API-05.
    # Tests monkeypatch ``sse_starlette.sse.DEFAULT_PING_INTERVAL``
    # to <1s so the heartbeat fires within the test budget without
    # the test sleeping 15s in CI.
    return EventSourceResponse(event_stream(), ping=15)


# --------------------------------------------------------------------
# Compare (Seam A) — POST /api/v1/threads/{thread_id}/compare
# --------------------------------------------------------------------
#
# Phase 7 Plan 07-08 (L5 + ROADMAP parallel-completions note). One prompt
# rendered side-by-side across two candidate models: the endpoint forces
# each lane's model through the SAME ``_synthesize_override_decision``
# path the Phase 5 UI-05 override uses, runs both lanes CONCURRENTLY
# through the existing single-adapter streaming stack, and multiplexes
# their chunks into ONE SSE response where every event carries a ``lane``
# discriminator (0 / 1) so the 2-up UI (and the Next /compare proxy) can
# demux. Reuses ``EventSourceResponse(ping=15)``, the per-turn cost cap
# (T-07-17), and the cancellation path (T-07-19).


class CompareRequest(BaseModel):
    """Body of ``POST /api/v1/threads/{thread_id}/compare``.

    Fields:
      message:      The shared user prompt streamed to BOTH lanes.
      models:       Exactly two model IDs — one per Compare column. Each
                    is validated against ``_compare_model_allowlist()``
                    BEFORE dispatch (T-07-16 SSRF/over-fetch guard); an
                    off-list or wrong-cardinality list returns 422.
      max_cost_usd: Optional PER-LANE cost cap override; falls back to
                    ``settings.default_max_cost_usd`` then
                    ``DEFAULT_PER_TURN_COST_USD`` — identical precedence
                    to the single-turn path so Compare never bypasses the
                    cost cap (T-07-17). The cap applies to EACH lane.
    """

    message: str
    models: list[str]
    max_cost_usd: float | None = None


def _compare_lane_payload(lane: int, chunk: ChatChunk) -> dict[str, Any]:
    """Serialise a ChatChunk for a Compare lane, tagging it with ``lane``.

    The single-turn path yields ``chunk.model_dump_json()`` verbatim; for
    Compare we splice a ``lane`` key into the same payload so the client
    can demux the interleaved 0/1 streams without a separate framing
    channel (the SSE ``event:`` name still keys the chunk type).
    """

    payload = chunk.model_dump()
    payload["lane"] = lane
    return payload


@router.post("/threads/{thread_id}/compare", response_model=None)
async def post_compare(
    thread_id: str, body: CompareRequest, request: Request
) -> EventSourceResponse:
    """Stream two labeled completion lanes for one prompt as SSE.

    Pre-stream errors (D-08 HTTPException path — BEFORE the SSE opens):
      - 404 thread not found.
      - 422 if ``models`` is not exactly two ids, or if EITHER id is not
        in ``_compare_model_allowlist()`` (T-07-16 — the client cannot
        force an arbitrary upstream model).

    Per lane (0 and 1), the multiplexed stream carries:
        routing_decision (forced-model echo) → >=1 text_delta → done
    each event's data payload tagged with ``lane: 0|1``.

    The two lanes run CONCURRENTLY (``asyncio`` tasks feeding a shared
    queue) so this is a genuine parallel-completions path; on client
    disconnect / cancellation BOTH lane tasks are cancelled (T-07-19).
    """

    app = request.app
    db = app.state.db

    # ----------------------------------------------------------------
    # Pre-stream sanity (D-08 HTTPException path)
    # ----------------------------------------------------------------

    thread = await get_thread(db, thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")

    # Exactly two models — the handoff Compare view is 2-up only
    # (RESEARCH Deferred: Compare across >2 models is out of scope).
    if len(body.models) != 2:
        raise HTTPException(
            status_code=422,
            detail="compare requires exactly two model ids",
        )

    # T-07-16 SSRF/over-fetch guard: BOTH forced model ids must be in the
    # known allowlist. Reject off-list ids (422) BEFORE any dispatch so a
    # client can never force an arbitrary upstream model.
    allowlist = _compare_model_allowlist()
    off_list = [m for m in body.models if m not in allowlist]
    if off_list:
        raise HTTPException(
            status_code=422,
            detail=(
                "compare model(s) not in the allowed set: "
                f"{', '.join(off_list)}"
            ),
        )

    turn_id = secrets.token_urlsafe(12)
    logger.info(
        "compare_start thread_id=%s user_msg_len=%d models=%s turn_id=%s",
        thread_id,
        len(body.message),
        body.models,
        turn_id,
    )

    history_rows = await get_thread_messages(db, thread_id)
    adapter_history = [
        AdapterMessage(role=m.role, content=m.text) for m in history_rows
    ]

    # Per-lane forced-model decisions via the reused override synth. Both
    # allowlisted slugs are OpenRouter aggregator models, so each lane
    # dispatches through the single ``openrouter`` adapter with its slug
    # forced. (Compare bypasses decide() ranking — the user picked the two
    # models explicitly — but still goes through _enabled_backends below.)
    lane_decisions: list[RoutingDecision] = [
        _synthesize_override_decision("openrouter", body.models[0]),
        _synthesize_override_decision("openrouter", body.models[1]),
    ]

    # _enabled_backends floors at ["openrouter"] so the Compare backend is
    # always reachable; the lazy adapter cache + key/import error handling
    # is reused verbatim. The adapter is shared across both lanes (one
    # OpenRouter adapter instance), which is safe — each .stream() call is
    # an independent async generator.
    enabled = _enabled_backends(app.state.settings)
    if "openrouter" not in enabled:
        # Defensive: the floor guarantees this is unreachable, but keep a
        # clean error rather than a half-opened stream if it ever changes.
        raise HTTPException(
            status_code=400,
            detail="openrouter backend is required for compare",
        )
    adapter = await _get_or_create_adapter(app, "openrouter")

    # Per-lane cost cap — identical precedence to the single-turn path
    # (T-07-17): body > settings > DEFAULT_PER_TURN_COST_USD. Applied to
    # EACH lane so two parallel completions never bypass the cap.
    default_cap = app.state.settings.get("default_max_cost_usd")
    if body.max_cost_usd is not None:
        max_cost_usd = body.max_cost_usd
    elif default_cap is not None:
        max_cost_usd = default_cap
    else:
        max_cost_usd = DEFAULT_PER_TURN_COST_USD

    async def lane_stream(
        lane: int, decision: RoutingDecision, queue: asyncio.Queue
    ) -> None:
        """Drive one lane's adapter stream, pushing lane-tagged events.

        Emits the routing_decision event FIRST (so the column can label
        itself before the first token), then forwards each adapter chunk
        as a lane-tagged SSE event, stopping on the terminal Done. A
        per-lane StreamError+Done pair is emitted on cancellation or
        adapter failure so each column terminates cleanly and the
        consumer's done-count reaches two.
        """

        options = AdapterOptions(
            model=decision.model_or_agent,
            max_cost_usd=max_cost_usd,
            max_steps=None,
            cwd=None,
            routing_signals=decision.signals,
        )

        # routing_decision FIRST — echo the forced model id per lane so
        # the 2-up UI labels each column (test_compare_echoes_forced_model).
        await queue.put(
            ServerSentEvent(
                event="routing_decision",
                data=json.dumps(
                    {
                        "lane": lane,
                        "backend": decision.backend,
                        "model_or_agent": decision.model_or_agent,
                        "rationale": decision.rationale,
                        "confidence": decision.confidence,
                        "signals": decision.signals,
                    }
                ),
            )
        )
        try:
            async for chunk in adapter.stream(
                body.message, adapter_history, options
            ):
                if isinstance(chunk, Screenshot):
                    chunk = _maybe_externalize_screenshot(chunk)
                await queue.put(
                    ServerSentEvent(
                        event=chunk.type,
                        data=json.dumps(_compare_lane_payload(lane, chunk)),
                    )
                )
                if isinstance(chunk, Done):
                    return
        except asyncio.CancelledError:
            # T-07-19: client disconnect cancels both lanes. Emit a
            # terminal pair so the consumer sees the lane close, THEN
            # re-raise so the adapter's own CancelledError handler closes
            # the provider connection within the cancellation budget.
            err = StreamError(
                code="cancelled",
                # SECURE-07 uniformity: redact every turn.py StreamError
                # message at construction, even static ones, so no site
                # can ever carry an unredacted secret.
                message=_redact_text("Compare lane cancelled by caller."),
                retriable=True,
            )
            await queue.put(
                ServerSentEvent(
                    event=err.type,
                    data=json.dumps(_compare_lane_payload(lane, err)),
                )
            )
            done = Done(routing_signals=decision.signals)
            await queue.put(
                ServerSentEvent(
                    event=done.type,
                    data=json.dumps(_compare_lane_payload(lane, done)),
                )
            )
            raise
        except Exception as exc:  # noqa: BLE001 — surface as StreamError
            # An adapter-level failure on one lane must not abort the
            # other. Emit StreamError + terminal Done for THIS lane so the
            # column renders an error and the consumer's done-count still
            # reaches two.
            logger.warning(
                "compare lane %d failed turn_id=%s: %s", lane, turn_id, exc
            )
            err = StreamError(
                code="internal_error",
                # SECURE-07 uniformity (see lane-cancel site above).
                message=_redact_text("Compare lane failed."),
                retriable=True,
            )
            await queue.put(
                ServerSentEvent(
                    event=err.type,
                    data=json.dumps(_compare_lane_payload(lane, err)),
                )
            )

        # Natural end without a terminal Done (defensive — adapters honor
        # the D-04 terminal-Done invariant, but a custom fake might not):
        # synthesise one so the lane closes and the consumer unblocks.
        done = Done(routing_signals=decision.signals)
        await queue.put(
            ServerSentEvent(
                event=done.type,
                data=json.dumps(_compare_lane_payload(lane, done)),
            )
        )

    async def compare_stream():
        """Multiplex the two concurrent lanes into one SSE stream.

        A shared ``asyncio.Queue`` collects lane-tagged events from both
        lane tasks; this generator drains the queue until both lanes have
        emitted their terminal Done. On cancellation both lane tasks are
        cancelled (T-07-19).
        """

        queue: asyncio.Queue = asyncio.Queue()
        tasks = [
            asyncio.ensure_future(lane_stream(0, lane_decisions[0], queue)),
            asyncio.ensure_future(lane_stream(1, lane_decisions[1], queue)),
        ]
        done_lanes = 0
        try:
            while done_lanes < 2:
                # Drain queued events; stop once both lanes have signalled
                # their terminal Done. Use a short timeout so a stalled
                # lane cannot wedge the drain loop forever while the other
                # lane is still producing.
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    if all(t.done() for t in tasks):
                        break
                    continue
                yield event
                if event.event == "done":
                    done_lanes += 1
            # Flush any events the lane tasks enqueued between the final
            # ``done`` dequeue and loop exit (terminal Done is always last
            # per lane, so this is normally empty).
            while not queue.empty():
                yield queue.get_nowait()
        except asyncio.CancelledError:
            # Propagate cancellation to BOTH lanes (T-07-19) then re-raise.
            for t in tasks:
                t.cancel()
            raise
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()
            # Await the lane tasks so their CancelledError handlers (which
            # close provider connections) run before the response closes.
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info(
                "compare_done thread_id=%s turn_id=%s lanes_completed=%d",
                thread_id,
                turn_id,
                done_lanes,
            )

    return EventSourceResponse(compare_stream(), ping=15)
