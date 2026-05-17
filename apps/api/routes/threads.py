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

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from apps.api.db.models import Thread
from apps.api.db.queries import (
    create_thread,
    delete_thread,
    get_thread,
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
