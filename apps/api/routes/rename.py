"""POST /api/v1/threads/{id}/rename — one-shot OpenRouter title summariser.

Public surface (D-17, UI-14 forward-wire):

    router                 APIRouter(prefix="/api/v1", tags=["threads"])
    RenameRequest          Pydantic v2 body — ``first_user_message: str``.
    RENAME_MODEL           Final[str] — cheapest GPT-class OpenRouter slug
                           (``"openai/gpt-4o-mini"``) per CONTEXT specifics
                           line 348 + Assumption A2.
    RENAME_MAX_COST_USD    Final[float] — $0.01 cap on the one-shot call.
    RENAME_MAX_INPUT_TOKENS
                           Final[int] — 1500-token pre-flight cap to
                           prevent the $0.01 budget being blown by an
                           oversized first_user_message.
    RENAME_PROMPT_TEMPLATE Final[str] — the canonical system prompt
                           (CONTEXT specifics line 348).

Endpoint contract:

    POST   /api/v1/threads/{thread_id}/rename
        body: {"first_user_message": str}
        →  200 {"title": "<≤60 chars>"}     — happy path
        →  400 {"detail": "OPENROUTER_API_KEY not set; ..."}
                                            — pre-check when the keystore
                                              has no openrouter entry
        →  404 {"detail": "thread not found"}
                                            — unknown thread_id
        →  413 {"detail": "first_user_message too long (... > 1500)"}
                                            — tiktoken pre-flight cap fires

Why a separate endpoint (not part of /turn):

    The Phase 5 UI auto-renames a freshly created thread from the
    first user message (UI-14). Rename runs OUTSIDE the routing brain
    — a 5-word summary does not benefit from the brain's task-type
    classifier; it just needs a cheap, fast GPT-class completion. The
    plan locks this in D-17 explicit ("bypass the brain entirely").

Why a FRESH OpenRouterAdapter (NOT the cached one on ``app.state``):

    D-17 calls for defense in depth: if the cached adapter held a key
    from BEFORE a missed PATCH /settings cache invalidation, the
    cached client would use stale credentials. The per-request cost
    of constructing a new adapter is negligible compared to the
    ``$0.01`` budget. The cached registry stays untouched.

Why a tiktoken pre-flight cap:

    Cost-overrun defense. ``max_cost_usd=0.01`` is a real cap inside
    the adapter, but the pre-flight token count rejects an obviously
    oversized input BEFORE we contact OpenRouter. The cap is sized
    so that 1500 input tokens × $0.15 / 1M tokens (gpt-4o-mini) ~=
    $0.000225 — well under the $0.01 ceiling even before the
    completion budget.

Why ≤60 char trim:

    The Phase 5 sidebar (UI-02) displays the title in a single line;
    >60 chars wraps in the UI and looks bad. The model is instructed
    to return ≤5 words, but defense in depth: we cap to 60 chars
    after stripping any leading/trailing quotes the model emits
    despite the "no quotes" instruction.

Why this module NEVER calls the routing brain:

    UI-14 explicit. Rename is the bypass route per D-17. The plan's
    acceptance criteria includes a negative grep for the brain's
    function name as a hard guard.

Why this module NEVER returns SSE:

    D-17 explicit. The completion is one short string; streaming
    adds latency without UX value. Plain JSON.

Cross-refs:
    - 03-CONTEXT.md D-17 (rename endpoint contract)
    - 03-CONTEXT.md specifics line 348 (defensive constants + system prompt)
    - 03-CONTEXT.md Assumption A2 (cheapest GPT slug — gpt-4o-mini)
    - 03-RESEARCH.md §"Pattern 14" lines 785-834 (canonical source —
      defensive constants, tiktoken pre-flight, fresh adapter, trim)
    - 03-RESEARCH.md §"Excerpt 10" lines 481-520 (one-shot adapter consume)
    - 03-PATTERNS.md §"Routes" line 26 (rename.py role + anti-patterns)
    - apps/api/backends/openrouter/__main__.py lines 30-80 (canonical
      "consume an adapter once, accumulate, stop" pattern this mirrors)
    - apps/api/db/queries.py — ``get_thread`` / ``update_thread_title``
"""

from __future__ import annotations

import logging
from typing import Final

import tiktoken
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from apps.api.backends.openrouter.adapter import OpenRouterAdapter
from apps.api.backends.protocol import AdapterOptions
from apps.api.backends.protocol import Message as AdapterMessage
from apps.api.db.queries import get_thread, update_thread_title

# ``__name__`` resolves to ``apps.api.routes.rename`` so the Phase 2
# RedactionFilter (installed on the root logger at apps/api/__init__.py
# import time) catches every record we emit. NEVER use ``print(...)``.
logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1", tags=["threads"])


# --------------------------------------------------------------------
# Defensive constants — locked at module load (D-17 + CONTEXT line 348)
# --------------------------------------------------------------------


# Cheapest GPT-class OpenRouter slug at this writing per CONTEXT
# Assumption A2 (LOW confidence). The planner verifies the cheapest
# slug at execute time; swap here if pricing.json reveals a cheaper
# GPT slug. Phase 5 UI-14 hook does NOT bind the slug; this is the
# Phase 3 default.
RENAME_MODEL: Final[str] = "openai/gpt-4o-mini"

# $0.01 cap on the one-shot rename completion. Sized for the worst
# case of 1500 input + 50 output tokens at gpt-4o-mini rates
# ($0.15 / $0.60 per 1M tokens) ~ $0.000225 + $0.00003 ~ $0.000255
# so we have 40x headroom inside the cap.
RENAME_MAX_COST_USD: Final[float] = 0.01

# Pre-flight token cap. The full body is rejected BEFORE the adapter
# constructor when the encoded length exceeds this value, so an
# adversarial first_user_message cannot consume the $0.01 budget on
# input tokens alone. 1500 tokens ~ 6000 chars of mixed English; the
# UI never sends a first message that long.
RENAME_MAX_INPUT_TOKENS: Final[int] = 1500

# Canonical system prompt per CONTEXT specifics line 348. The model
# is explicitly told to return the title only (no quotes); the
# response trim still strips leading/trailing ASCII quotes defensively.
RENAME_PROMPT_TEMPLATE: Final[str] = (
    "Summarize this user request in 5 words or fewer; "
    "respond with the title only, no quotes."
)


# Tiktoken encoder. ``encoding_for_model("gpt-4o-mini")`` resolves to
# the ``o200k_base`` encoding under the hood (verified at execute
# time: ``tiktoken.encoding_for_model('gpt-4o-mini').name ==
# 'o200k_base'``). The encoder is loaded once at module import; loading
# is ~50 ms cold which is acceptable inside the Phase 3 boot budget.
# If a future tiktoken version stops recognising the slug, fall back
# to ``tiktoken.get_encoding("o200k_base")`` directly.
try:
    _ENC = tiktoken.encoding_for_model("gpt-4o-mini")
except KeyError:  # pragma: no cover — defensive only; current tiktoken supports the slug
    _ENC = tiktoken.get_encoding("o200k_base")


# --------------------------------------------------------------------
# Pydantic v2 request model
# --------------------------------------------------------------------


class RenameRequest(BaseModel):
    """Body of ``POST /api/v1/threads/{thread_id}/rename``.

    Fields:
        first_user_message: The user's first message in the thread.
            The model is asked to summarise this into a 5-word title.
            Empty strings are technically valid (the model returns
            a generic title); the pre-flight tiktoken cap rejects
            >1500-token inputs with a 413.
    """

    first_user_message: str


# --------------------------------------------------------------------
# Endpoint — POST /api/v1/threads/{thread_id}/rename
# --------------------------------------------------------------------


@router.post("/threads/{thread_id}/rename")
async def rename_thread(
    thread_id: str, body: RenameRequest, request: Request
) -> dict:
    """Generate a ≤60-char title via one OpenRouter completion.

    Pre-stream pipeline (clean error paths — never opens an adapter
    if any of these fail):

        1. 404 — ``thread_id`` is unknown.
        2. 413 — ``first_user_message`` exceeds the tiktoken cap.
        3. 400 — KeyStore has no ``openrouter`` entry.

    Stream pipeline (no SSE — D-17 plain JSON):

        4. Build a FRESH OpenRouterAdapter (NOT the cached one — D-17).
        5. Consume the one-shot stream: accumulate TextDelta text;
           break on Done.
        6. Trim the accumulated text: ``strip()`` + strip ASCII quotes
           + ``[:60]`` — never returns more than 60 chars regardless
           of model output.
        7. Persist via ``update_thread_title`` (Wave 1 helper, owns
           its own commit).
        8. Return ``{"title": "..."}`` as plain JSON.

    The body content is NEVER logged (the title is — but the title
    is short, model-synthesised, and post-trim, so it cannot smuggle
    a key shape past the RedactionFilter; defense in depth covers
    that anyway).
    """

    db = request.app.state.db

    # Step 1 — 404 if thread is unknown. We do this BEFORE the token
    # cap so an oversized body against a non-existent thread returns
    # 404 (the more specific error). The order is intentional and
    # consistent with the /turn handler.
    thread = await get_thread(db, thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")

    # Step 2 — tiktoken pre-flight cap. Defense against cost-overrun:
    # estimate input tokens locally BEFORE we contact OpenRouter. An
    # oversized body returns 413 without any upstream API call.
    estimated = len(_ENC.encode(body.first_user_message))
    if estimated > RENAME_MAX_INPUT_TOKENS:
        detail = (
            f"first_user_message too long "
            f"({estimated} tokens > {RENAME_MAX_INPUT_TOKENS}); "
            "shorten the message before rename"
        )
        raise HTTPException(status_code=413, detail=detail)

    # Step 3 — OpenRouter key pre-check. Without this, the typed
    # ``openai.AuthenticationError`` from the adapter constructor
    # bubbles up as an opaque 500. The pre-check returns a clean 400
    # with a remediation hint instead.
    key = request.app.state.keystore.get("openrouter")
    if not key:
        detail = (
            "OPENROUTER_API_KEY not set; rename requires an "
            "OpenRouter key (set it via PATCH /api/v1/settings "
            "or the OPENROUTER_API_KEY env var)"
        )
        raise HTTPException(status_code=400, detail=detail)

    # Step 4 — FRESH adapter per D-17. NEVER touch the cached adapter
    # registry on ``app.state``; rename's <$0.01 budget makes per-
    # request adapter construction negligible.
    adapter = OpenRouterAdapter(api_key=key, max_cost_usd=RENAME_MAX_COST_USD)

    # Step 5 — consume the one-shot stream. The history carries the
    # system prompt; the user prompt is the body's first_user_message.
    # We break on Done (the D-04 terminal-chunk invariant) so the
    # generator exits cleanly even if the adapter emits a StreamError
    # before the Done (we keep what TextDelta we collected, the trim
    # caps the length anyway).
    options = AdapterOptions(
        model=RENAME_MODEL,
        max_cost_usd=RENAME_MAX_COST_USD,
        max_steps=1,
    )
    title_parts: list[str] = []
    async for chunk in adapter.stream(
        prompt=body.first_user_message,
        history=[AdapterMessage(role="system", content=RENAME_PROMPT_TEMPLATE)],
        options=options,
    ):
        chunk_type = getattr(chunk, "type", None)
        if chunk_type == "text_delta":
            title_parts.append(getattr(chunk, "text", ""))
        elif chunk_type == "done":
            break

    # Step 6 — trim. ``strip()`` removes leading/trailing whitespace;
    # the dual quote-strip handles both `"Title"` and `'Title'` shapes
    # despite the system prompt's "no quotes" instruction. ``[:60]``
    # caps the final length regardless of model output.
    title = (
        "".join(title_parts)
        .strip()
        .strip('"')
        .strip("'")
        .strip()
    )[:60]

    # Step 7 — persist. ``update_thread_title`` owns its own commit
    # and returns the updated Thread (or None for unknown id; we
    # already 404'd in step 1 so the None branch is unreachable in
    # normal flow).
    await update_thread_title(db, thread_id, title)

    # The synthesised title is short (≤60 chars) and entirely model-
    # produced; logging it is safe. The body itself is NEVER logged.
    logger.info(
        "rename complete thread_id=%s title_len=%d", thread_id, len(title)
    )

    # Step 8 — plain JSON. D-17 explicit: NEVER SSE.
    return {"title": title}
