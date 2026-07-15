"""Thread CRUD — POST/GET/PATCH/DELETE /api/v1/threads(/{id}) per API-03.

Public surface (API-03, D-09, D-13):

    router               APIRouter(prefix="/api/v1", tags=["threads"])
    ThreadCreateRequest  Pydantic v2 body for POST /threads
    ThreadUpdateRequest  Pydantic v2 body for PATCH /threads/{id}
    ThreadListResponse   Pydantic v2 envelope for GET /threads

Endpoint contract (Wave 3 truth lines 21-25 of the plan):

    POST   /api/v1/threads               body: {"title": str}
                                         → 200 {"id": str, "title": str,
                                                "created_at": str,
                                                "updated_at": str}

    GET    /api/v1/threads               → 200 {"threads": [...]}
                                         ordered by created_at DESC

    GET    /api/v1/threads/{id}          → 200 Thread | 404 {"detail": ...}

    PATCH  /api/v1/threads/{id}          body: {"title": str}
                                         → 200 Thread | 404 {"detail": ...}
                                         updated_at strictly > created_at

    DELETE /api/v1/threads/{id}          → 204 (no body) | 404
                                         FK ON DELETE CASCADE removes
                                         child messages + routing_decisions
                                         rows (D-13 + D-03 foreign_keys=ON).

**Wave 5 EXTENSION (D-14):** ``delete_single_thread`` will gain a
pre-step that walks ``messages.content_blocks`` JSON to unlink blob
files BEFORE the DB delete fires. Wave 3 ships the minimal DB-only
path; the cascade via FK + pragma is sufficient for v1 without blobs.

**T-03-SQLi (anti-pattern guard):** Route handlers NEVER build SQL
strings with f-string interpolation. Every query goes through
``apps.api.db.queries.*`` async functions, which bind parameters with
the standard ``?`` placeholder. The plan's negative-grep enforces
this at the source level so a future contributor cannot bypass the
query layer.

**T-03-Disclo (anti-pattern guard):** No key material flows through
any response body — these endpoints handle thread metadata only
(``id``, ``title``, ``created_at``, ``updated_at``).

Cross-refs:
    - 03-CONTEXT.md D-09 (/api/v1 URL namespace)
    - 03-CONTEXT.md D-13 (schema columns + ON DELETE CASCADE)
    - 03-CONTEXT.md D-14 (Wave 5 blob unlink extension — future)
    - 03-CONTEXT.md API-03 (CRUD surface gate for Phase 5 UI-02 sidebar)
    - 03-RESEARCH.md §"Pattern 8" lines 548-589 (Pydantic v2 models)
    - 03-PATTERNS.md §"Routes" line 23 (threads.py anti-pattern audit)
    - apps/api/db/queries.py (canonical async query functions)
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from apps.api.db.models import Thread
from apps.api.db.queries import (
    create_thread,
    delete_thread,
    get_thread,
    get_thread_messages_with_routing,
    list_threads,
    update_thread_title,
)


router = APIRouter(prefix="/api/v1", tags=["threads"])


# --------------------------------------------------------------------
# Pydantic request / response models — v2 with explicit field types
# --------------------------------------------------------------------


class ThreadCreateRequest(BaseModel):
    """Body of ``POST /api/v1/threads``.

    A title is required at creation time. FastAPI emits an auto-422
    response when the field is absent or not a string — no manual
    validation is needed in the route handler.
    """

    title: str


class ThreadUpdateRequest(BaseModel):
    """Body of ``PATCH /api/v1/threads/{id}``.

    Partial-update shape; ``title`` is the only mutable field today.
    When the field is absent (``{}`` body), the handler treats the
    PATCH as a no-op and returns the existing thread unchanged.
    """

    title: str | None = None


class ThreadListResponse(BaseModel):
    """Envelope for ``GET /api/v1/threads``.

    The top-level dict shape ``{"threads": [...]}`` matches the
    Phase 5 UI-02 sidebar expectation and lets us add pagination
    metadata later without breaking existing clients.
    """

    threads: list[Thread]


class RoutingSummary(BaseModel):
    """The per-assistant routing facet of ``GET /threads/{id}/messages``.

    Phase 8 D-01: the restored routing pill needs the decision's
    ``rationale`` plus whether the user manually overrode the auto
    route. ``override`` is recovered server-side from the persisted
    ``signals`` JSON (``signals.override``; the override path also sets
    ``rationale == "user override"``).

    Story 5.2: ``confidence`` carries the route's overall calibrated confidence
    (schema_v3 column) so the restored low-confidence override nudge renders
    identically to the live stream (AD-7). ``None`` on legacy rows written before
    the column existed — the client falls back to a safe high (no nudge).
    """

    rationale: str
    override: bool
    confidence: float | None = None
    # Story 6.2: the routing brain's calibrated low-confidence-fallback verdict,
    # recovered from the persisted signals JSON. This is the nudge trigger (AD-7
    # restore parity). Defaults False so legacy rows never nudge.
    low_confidence: bool = False


class MessageWithRouting(BaseModel):
    """One row of ``GET /api/v1/threads/{id}/messages`` (Phase 8 SC-1).

    Distinct from the frozen ``apps.api.db.models.Message`` for two
    reasons (RESEARCH anti-pattern — do NOT reuse ``Message`` verbatim):

      * ``content_blocks`` is the PARSED ``list[dict]`` here, not the
        raw JSON ``str`` the ``Message`` row carries (``models.py:88``);
        the query ``json.loads``'d it so the client renders chunks
        without double-parsing (Pitfall 3).
      * ``routing`` is a derived facet absent from the ``messages``
        table — present (``RoutingSummary``) for an assistant turn with
        a routing-decision JOIN match, ``None`` for user rows.

    The optional metric/metadata fields mirror the nullable columns on
    the ``messages`` table so a restored transcript can show the same
    cost / latency / token chips a live turn shows.
    """

    id: str
    role: Literal["user", "assistant"]
    text: str
    content_blocks: list[dict]  # PARSED array — NOT Message.content_blocks: str
    backend_used: str | None = None
    model_used: str | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    created_at: str
    status: Literal["complete", "error", "cancelled"] = "complete"
    routing: RoutingSummary | None = None


# --------------------------------------------------------------------
# Endpoints (all async; all take ``request: Request`` for app.state.db)
# --------------------------------------------------------------------


@router.post("/threads")
async def post_thread(
    body: ThreadCreateRequest, request: Request
) -> Thread:
    """Insert a new thread and return the persisted row.

    Generates the ID server-side via ``apps.api.db.queries._new_id``
    (``secrets.token_urlsafe(12)``) so callers cannot spoof an ID.
    """

    db = request.app.state.db
    thread = await create_thread(db, title=body.title)
    return thread


@router.get("/threads")
async def get_threads(request: Request) -> ThreadListResponse:
    """List threads ordered newest-first.

    Returns the ``{"threads": [...]}`` envelope. The query layer's
    default ``limit=100`` paginates large workspaces; pagination
    query-params can be added later without breaking the envelope
    shape.
    """

    db = request.app.state.db
    threads = await list_threads(db)
    return ThreadListResponse(threads=threads)


@router.get("/threads/{thread_id}")
async def get_single_thread(thread_id: str, request: Request) -> Thread:
    """Return one thread by id.

    Raises ``HTTPException(404, "thread not found")`` for unknown
    ids — the FastAPI default 404 body shape is ``{"detail": ...}``
    which the Phase 5 UI consumes verbatim.
    """

    db = request.app.state.db
    thread = await get_thread(db, thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    return thread


@router.get("/threads/{thread_id}/messages")
async def get_thread_messages_endpoint(
    thread_id: str, request: Request
) -> list[MessageWithRouting]:
    """Return a thread's persisted messages chronologically (Phase 8 SC-1).

    D-01: each assistant row carries its ``routing`` decision (rationale
    + manual-override flag) from the ``routing_decisions`` LEFT JOIN, so
    the client can restore the full transcript — including each routing
    pill — without a second request. ``content_blocks`` arrives parsed
    (a ``list``, not the raw DB JSON string — Pitfall 3).

    **404-ordering hazard (RESEARCH §Pattern 4):** call ``get_thread``
    FIRST and 404 on an unknown id, mirroring ``get_single_thread``. A
    real-but-EMPTY thread instead returns ``200 []`` — the empty result
    is a valid state the query returns, NOT a not-found. Ordering the
    existence check before the message query is what distinguishes the
    D-03 empty-state from a genuine 404 for the client.
    """

    db = request.app.state.db
    # Existence precheck BEFORE the message query: unknown id → 404,
    # real-but-empty thread → 200 [] (the query returns []).
    if await get_thread(db, thread_id) is None:
        raise HTTPException(status_code=404, detail="thread not found")
    return await get_thread_messages_with_routing(db, thread_id)


@router.patch("/threads/{thread_id}")
async def patch_thread(
    thread_id: str, body: ThreadUpdateRequest, request: Request
) -> Thread:
    """Rename a thread and bump ``updated_at``.

    When ``body.title`` is None (omitted from the request), this is
    a no-op — we still return the existing row (or 404 if unknown).
    Otherwise the ``update_thread_title`` query writes the new title
    AND a fresh ``_now_iso()`` timestamp so ``updated_at`` is strictly
    greater than ``created_at`` after a real rename.
    """

    db = request.app.state.db
    if body.title is None:
        existing = await get_thread(db, thread_id)
        if existing is None:
            raise HTTPException(
                status_code=404, detail="thread not found"
            )
        return existing
    updated = await update_thread_title(db, thread_id, body.title)
    if updated is None:
        raise HTTPException(status_code=404, detail="thread not found")
    return updated


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_single_thread(
    thread_id: str, request: Request
) -> Response:
    """Delete a thread (cascade to messages + routing_decisions).

    Returns 204 No Content on success. The ``FK ON DELETE CASCADE``
    (D-13) plus ``PRAGMA foreign_keys=ON`` (D-03) clean up the
    dependent rows atomically inside SQLite. Wave 5 EXTENDS this
    handler with a pre-step that walks ``messages.content_blocks``
    JSON to unlink blob files BEFORE the DB delete fires; Wave 3
    ships the minimal DB-only path.
    """

    db = request.app.state.db
    deleted = await delete_thread(db, thread_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="thread not found")
    # 204 responses MUST have no body. Returning ``Response(status_code=204)``
    # produces a content-length-0 response with no JSON body.
    return Response(status_code=204)
