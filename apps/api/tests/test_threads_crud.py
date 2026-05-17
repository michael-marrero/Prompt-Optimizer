"""Wave 3 thread CRUD tests — POST/GET/PATCH/DELETE /api/v1/threads.

Nine async tests covering the full thread CRUD surface
(API-03 + D-09 + D-13):

    test_post_thread                      201 happy path; body has
                                          id/title/created_at/updated_at.

    test_post_thread_missing_title_returns_422
                                          POST {} returns 422 (Pydantic
                                          required-field check).

    test_get_threads_list                 GET /threads returns
                                          {"threads": [...]} ordered
                                          newest-first (created_at DESC).

    test_get_single_thread                GET /threads/{id} returns the
                                          posted thread.

    test_get_thread_returns_404_for_unknown
                                          GET /threads/unknown returns
                                          404 + {"detail": "thread not
                                          found"}.

    test_patch_thread_renames             PATCH {"title": "Renamed"}
                                          returns the updated thread;
                                          updated_at > created_at.

    test_patch_thread_returns_404_for_unknown
                                          PATCH /threads/unknown returns
                                          404.

    test_delete_thread                    DELETE returns 204; subsequent
                                          GET returns 404.

    test_delete_thread_returns_404_for_unknown
                                          DELETE /threads/unknown returns
                                          404.

All tests use ``httpx.AsyncClient + ASGITransport`` per API-08 / D-20.
The synchronous FastAPI test-client wrapper is FORBIDDEN here (the
negative-grep guard in test_smoke.py enforces).

The DB lands in ``tmp_path`` via the ``PROMPT_OPTIMIZER_HOME`` env
override + ``importlib.reload(apps.api.paths)`` so each test gets a
fresh filesystem location. The lifespan opens the DB, runs
migrations, and inserts/queries against the isolated tmp DB —
exactly what the production boot path does.

Cross-refs:
    - 03-CONTEXT.md D-09 (/api/v1 URL namespace)
    - 03-CONTEXT.md D-13 (threads/messages schema + ON DELETE CASCADE)
    - 03-RESEARCH.md §"Pattern 6" lines 457-515 (ASGITransport)
    - 03-VALIDATION.md row 3-03-01 (thread CRUD test expectations)
    - apps/api/tests/test_health.py (lifespan-context pattern)
"""

from __future__ import annotations

import importlib

import httpx
import pytest
from httpx import ASGITransport


# ---------------------------------------------------------------------
# Test helper — fresh app under tmp dir, lifespan-triggered.
# Lifted from test_health.py to keep each test isolated to its own
# tmp DB. The Wave 2 lifespan handles the DB open + migrations + the
# 4-key artifact load + KeyStore + empty adapter registry; we only
# need to drive the routes from here.
# ---------------------------------------------------------------------


def _fresh_app(monkeypatch: pytest.MonkeyPatch, tmp_path) -> object:
    """Reload ``apps.api.paths`` under ``tmp_path`` and build a fresh app.

    Sets ``PROMPT_OPTIMIZER_HOME`` to ``tmp_path`` so the DB lands in
    a clean isolated location, then reloads ``apps.api.paths`` so the
    ``DB_PATH`` constant recomputes. The lifespan module also imports
    ``DB_PATH`` from ``apps.api.paths`` at module-top, so we reload it
    too. Finally calls ``create_app()`` to get a fresh FastAPI app
    with the up-to-date ``DB_PATH`` baked into its lifespan.
    """

    monkeypatch.setenv("PROMPT_OPTIMIZER_HOME", str(tmp_path))
    import apps.api.paths
    importlib.reload(apps.api.paths)
    import apps.api.lifespan
    importlib.reload(apps.api.lifespan)
    import apps.api.main
    importlib.reload(apps.api.main)
    return apps.api.main.create_app()


# ---------------------------------------------------------------------
# Test 1 — POST /threads happy path
# ---------------------------------------------------------------------


async def test_post_thread(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """POST /api/v1/threads with a title returns the persisted thread.

    Confirms the response body has the four canonical fields and that
    ``id`` is non-empty (server-generated via
    ``secrets.token_urlsafe(12)`` in the queries layer).
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/threads", json={"title": "T1"}
            )

    assert resp.status_code == 200, (
        f"POST returned {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert set(body.keys()) >= {
        "id",
        "title",
        "created_at",
        "updated_at",
    }, f"Missing keys in body: {body}"
    assert body["title"] == "T1"
    assert body["id"], "id must be non-empty"


# ---------------------------------------------------------------------
# Test 2 — POST /threads missing title returns 422
# ---------------------------------------------------------------------


async def test_post_thread_missing_title_returns_422(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Empty body returns 422 (Pydantic required-field validation).

    Confirms FastAPI's auto-422 path fires when ``title`` is absent —
    no custom validation lives in the route handler.
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post("/api/v1/threads", json={})

    assert resp.status_code == 422, (
        f"Expected 422 for missing title; got {resp.status_code}: "
        f"{resp.text}"
    )


# ---------------------------------------------------------------------
# Test 3 — GET /threads list, ordered newest-first
# ---------------------------------------------------------------------


async def test_get_threads_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """GET /api/v1/threads returns {"threads": [...]} newest-first.

    Posts two threads and asserts the second one (most recent) is
    first in the list. ISO 8601 ``Z``-suffixed timestamps sort
    lexicographically per UTC chronology so the string comparison
    is reliable.
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            await client.post(
                "/api/v1/threads", json={"title": "first"}
            )
            await client.post(
                "/api/v1/threads", json={"title": "second"}
            )
            resp = await client.get("/api/v1/threads")

    assert resp.status_code == 200
    body = resp.json()
    assert "threads" in body, f"Missing 'threads' envelope: {body}"
    threads = body["threads"]
    assert len(threads) == 2, f"Expected 2 threads; got {threads}"
    # Newest-first ordering. The second POST has a later created_at,
    # so it appears at index 0.
    assert threads[0]["title"] == "second"
    assert threads[1]["title"] == "first"
    assert threads[0]["created_at"] >= threads[1]["created_at"]


# ---------------------------------------------------------------------
# Test 4 — GET /threads/{id} single
# ---------------------------------------------------------------------


async def test_get_single_thread(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """GET /api/v1/threads/{id} returns the posted thread."""

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            posted = await client.post(
                "/api/v1/threads", json={"title": "single"}
            )
            thread_id = posted.json()["id"]
            resp = await client.get(f"/api/v1/threads/{thread_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == thread_id
    assert body["title"] == "single"


# ---------------------------------------------------------------------
# Test 5 — GET /threads/unknown returns 404
# ---------------------------------------------------------------------


async def test_get_thread_returns_404_for_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Unknown thread id returns 404 with the FastAPI detail body."""

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/threads/unknown")

    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"] == "thread not found"


# ---------------------------------------------------------------------
# Test 6 — PATCH /threads/{id} happy path
# ---------------------------------------------------------------------


async def test_patch_thread_renames(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """PATCH /api/v1/threads/{id} renames and bumps updated_at.

    Confirms the response body carries the new title AND that
    ``updated_at`` is strictly greater than ``created_at`` (ISO 8601
    ``Z``-suffixed string comparison is reliable for UTC ordering).
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            posted = await client.post(
                "/api/v1/threads", json={"title": "Original"}
            )
            thread_id = posted.json()["id"]
            created_at = posted.json()["created_at"]

            resp = await client.patch(
                f"/api/v1/threads/{thread_id}",
                json={"title": "Renamed"},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == thread_id
    assert body["title"] == "Renamed"
    assert body["updated_at"] > created_at, (
        f"updated_at {body['updated_at']!r} must be > "
        f"created_at {created_at!r}"
    )


# ---------------------------------------------------------------------
# Test 7 — PATCH /threads/unknown returns 404
# ---------------------------------------------------------------------


async def test_patch_thread_returns_404_for_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """PATCH on an unknown id returns 404."""

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.patch(
                "/api/v1/threads/unknown",
                json={"title": "Renamed"},
            )

    assert resp.status_code == 404


# ---------------------------------------------------------------------
# Test 8 — DELETE /threads/{id} happy path
# ---------------------------------------------------------------------


async def test_delete_thread(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """DELETE returns 204 with no body; subsequent GET returns 404."""

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            posted = await client.post(
                "/api/v1/threads", json={"title": "DeleteMe"}
            )
            thread_id = posted.json()["id"]

            delete_resp = await client.delete(
                f"/api/v1/threads/{thread_id}"
            )
            get_resp = await client.get(
                f"/api/v1/threads/{thread_id}"
            )

    assert delete_resp.status_code == 204, (
        f"DELETE returned {delete_resp.status_code}: "
        f"{delete_resp.text}"
    )
    # 204 responses MUST have an empty body.
    assert not delete_resp.content, (
        f"204 response body must be empty; got {delete_resp.content!r}"
    )
    assert get_resp.status_code == 404


# ---------------------------------------------------------------------
# Test 9 — DELETE /threads/unknown returns 404
# ---------------------------------------------------------------------


async def test_delete_thread_returns_404_for_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """DELETE on an unknown id returns 404."""

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.delete("/api/v1/threads/unknown")

    assert resp.status_code == 404
