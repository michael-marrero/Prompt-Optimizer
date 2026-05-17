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
import logging
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
from apps.api.backends.protocol import AdapterOptions
from apps.api.backends.protocol import Message as AdapterMessage
from apps.api.blobs import _maybe_externalize_screenshot
from apps.api.db.queries import (
    get_thread,
    get_thread_messages,
    persist_turn,
)
from apps.api.jsonl_log import append_routing_decisions_jsonl
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


def _synthesize_override_decision(backend: str) -> RoutingDecision:
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
    """

    model_or_agent = _OVERRIDE_DEFAULTS[backend]
    return RoutingDecision(
        backend=backend,  # type: ignore[arg-type] — Literal check at body
        model_or_agent=model_or_agent,
        rationale="user override",
        confidence=1.0,
        signals={"override": True},
    )


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
    max_cost_usd = (
        body.max_cost_usd
        or app.state.settings.get("default_max_cost_usd")
        or DEFAULT_PER_TURN_COST_USD
    )

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

        buffer: list[ChatChunk] = []
        start_t = asyncio.get_event_loop().time()
        try:
            async for chunk in adapter.stream(
                body.message, adapter_history, options
            ):
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
                buffer.append(chunk)
                yield ServerSentEvent(
                    event=chunk.type,
                    data=chunk.model_dump_json(),
                )
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
        except asyncio.CancelledError:
            # Pattern 7 + PEP 789: emit terminal pair into the buffer
            # AND the wire so the client + persistence both see the
            # cancellation, THEN re-raise so the upstream adapter's
            # CancelledError handler closes the provider connection
            # within the 2-second BACKEND-07 / API-06 budget.
            err = StreamError(
                code="cancelled",
                message="Stream cancelled by caller.",
                retriable=True,
            )
            buffer.append(err)
            yield ServerSentEvent(event=err.type, data=err.model_dump_json())
            done = Done(routing_signals=decision.signals)
            buffer.append(done)
            yield ServerSentEvent(
                event=done.type, data=done.model_dump_json()
            )
            raise
        finally:
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
