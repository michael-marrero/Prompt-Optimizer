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
from pathlib import Path

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


# ---------------------------------------------------------------------
# Test 10 — DELETE cascades to blob files (Wave 5 / STORE-04 / D-14)
# ---------------------------------------------------------------------


async def test_delete_unlinks_blobs(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Canonical STORE-04 cascade test: DELETE removes blob files first.

    Round-trip:
        1. POST /threads to create a thread.
        2. POST /threads/{id}/turn with a FakeStreamingAdapter that
           emits a >=256KB Screenshot — the route's
           ``_maybe_externalize_screenshot`` writes the file to
           ``<BLOBS_DIR>/<sha>.png`` and stores the ``image_ref`` in
           the assistant message's ``content_blocks`` JSON.
        3. DELETE /threads/{id} — the extended ``delete_thread`` walks
           the assistant's ``content_blocks``, unlinks the blob file
           BEFORE the DB cascade (D-14 order), then deletes the
           thread row (FK CASCADE removes messages +
           routing_decisions).

    Invariants verified:
        - Blob file exists on disk immediately after the turn.
        - After DELETE, the blob file is GONE.
        - GET /threads/{id} returns 404 (DB rows cascaded).
        - SELECT COUNT(*) FROM messages WHERE thread_id = ? returns 0
          (FK cascade).

    This is the integration counterpart to the unit-level
    ``test_blobs_by_hash.py`` sub-tests; the two together exercise
    every node of the STORE-04 + D-14 surface.
    """

    import base64
    import json
    import sys
    import importlib

    monkeypatch.setenv("PROMPT_OPTIMIZER_HOME", str(tmp_path))

    # Same purge/reload chain as test_turn_streaming.py:_fresh_app —
    # the Phase 1 D-18 smoke test invalidates cached class identities
    # when this file runs after src/routing/tests/.
    for name in list(sys.modules):
        if name.startswith("sse_starlette"):
            del sys.modules[name]

    import apps.api.paths

    importlib.reload(apps.api.paths)
    import apps.api.blobs

    importlib.reload(apps.api.blobs)
    import apps.api.jsonl_log

    importlib.reload(apps.api.jsonl_log)
    import apps.api.db.queries

    importlib.reload(apps.api.db.queries)
    import apps.api.lifespan

    importlib.reload(apps.api.lifespan)
    import apps.api.routes.turn

    importlib.reload(apps.api.routes.turn)
    import apps.api.main

    importlib.reload(apps.api.main)
    app = apps.api.main.create_app()

    from apps.api.backends.chunks import Done, Screenshot
    from apps.api.paths import BLOBS_DIR
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    raw = b"P" * (300 * 1024)
    b64 = base64.b64encode(raw).decode("ascii")
    fake = FakeStreamingAdapter(
        [Screenshot(step=1, image_b64=b64), Done()]
    )
    app.state.adapters = {"openrouter": fake}

    from src.routing.schema import RoutingDecision

    def fake_decide(*args, **kwargs):
        return RoutingDecision(
            backend="openrouter",
            model_or_agent="openai/gpt-5",
            rationale="test",
            confidence=0.9,
            signals={"task_type": "browse"},
        )

    monkeypatch.setattr("apps.api.routes.turn.decide", fake_decide)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Step 1 — create the thread.
            create_resp = await client.post(
                "/api/v1/threads", json={"title": "with-blob"}
            )
            assert create_resp.status_code == 200
            thread_id = create_resp.json()["id"]

            # Step 2 — POST a turn that emits the large Screenshot.
            image_ref: str | None = None
            async with client.stream(
                "POST",
                f"/api/v1/threads/{thread_id}/turn",
                json={"message": "browse"},
            ) as resp:
                assert resp.status_code == 200, (
                    f"turn failed: {resp.status_code} {await resp.aread()!r}"
                )
                current_event: str | None = None
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        current_event = line.split(":", 1)[1].strip()
                        if current_event == "done":
                            break
                    elif line.startswith("data:") and current_event == "screenshot":
                        payload = json.loads(line.split(":", 1)[1].strip())
                        image_ref = payload.get("image_ref")

            assert image_ref is not None, (
                "Screenshot event must carry image_ref for >=256KB payload"
            )
            # BL-01: image_ref is the bare content key (`<sha>.<ext>`),
            # not an absolute path. Re-anchor to BLOBS_DIR.
            assert "/" not in image_ref and "\\" not in image_ref, (
                f"image_ref must be the bare content key, not a path; "
                f"got {image_ref!r}"
            )
            ref_path = BLOBS_DIR / image_ref
            assert ref_path.exists(), (
                f"blob file must exist on disk at {ref_path} after turn"
            )
            assert str(ref_path).startswith(str(BLOBS_DIR)), (
                f"blob path must be under BLOBS_DIR; got {ref_path}"
            )

            # Step 3 — DELETE the thread; cascade must remove the blob
            # BEFORE the DB rows.
            delete_resp = await client.delete(
                f"/api/v1/threads/{thread_id}"
            )
            assert delete_resp.status_code == 204, (
                f"DELETE returned {delete_resp.status_code}: "
                f"{delete_resp.text}"
            )

            # D-14 invariant: blob file is GONE after cascade.
            assert not ref_path.exists(), (
                f"blob file must be unlinked by cascade delete; "
                f"still present at {ref_path}"
            )

            # FK CASCADE: thread row + dependent messages all gone.
            get_resp = await client.get(f"/api/v1/threads/{thread_id}")
            assert get_resp.status_code == 404, (
                f"GET after delete must return 404; got {get_resp.status_code}"
            )

            db = app.state.db
            async with db.execute(
                "SELECT COUNT(*) FROM messages WHERE thread_id = ?",
                (thread_id,),
            ) as cur:
                msg_count = (await cur.fetchone())[0]
            assert msg_count == 0, (
                f"FK CASCADE must remove all messages; got {msg_count}"
            )
