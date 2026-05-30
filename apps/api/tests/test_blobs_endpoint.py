"""Phase 5 Wave 0 — RED tests for GET /api/v1/blobs/{hash} (UI-10, STORE-04, T-blob-traversal).

ComputerUseBubble renders large screenshots (>=256KB) that the adapter
externalized to the blob store as ``image_ref``. The bubble's thumbnail src is
``/api/blobs/{hash}`` → Next proxy → ``GET /api/v1/blobs/{hash}`` on FastAPI.
No byte-serving GET endpoint exists yet (apps/api/blobs.py is transcoder-only,
no GET handler, no static mount in main.py) — these tests are RED until 05-02
builds the endpoint.

RED mechanism: the route does not exist, so GET returns 404 from FastAPI's
default router for the *happy-path* test (which expects 200 with bytes) →
FAILS. The path-traversal + unknown-hash tests expect 4xx and would pass
trivially against "no route" but the happy-path test guarantees the file is RED
overall until the endpoint is built. The endpoint MUST reuse
``apps/api/blobs.py:_is_inside_blobs_dir`` for the traversal guard.

What this asserts:
    - GET /api/v1/blobs/{hash} returns the stored bytes with the correct
      content-type for a written blob.
    - A hash containing path-traversal (``../`` and encoded variants) is
      rejected (404/400) via the ``_is_inside_blobs_dir`` guard.
    - An unknown hash returns 404.

All tests use httpx.AsyncClient + ASGITransport (API-08 / D-20).

Cross-refs:
    - 05-PATTERNS.md "No Analog Found" → GET /api/v1/blobs/{hash}
    - apps/api/blobs.py:_is_inside_blobs_dir + _maybe_externalize_screenshot
    - apps/api/paths.py:BLOBS_DIR
    - apps/api/tests/test_blobs_by_hash.py (transcoder domain this extends)
"""

from __future__ import annotations

import hashlib
import importlib
import typing

import httpx
import pytest
from httpx import ASGITransport


def _fresh_app(monkeypatch: pytest.MonkeyPatch, tmp_path) -> typing.Any:
    monkeypatch.setenv("PROMPT_OPTIMIZER_HOME", str(tmp_path))
    import apps.api.paths

    importlib.reload(apps.api.paths)
    import apps.api.lifespan

    importlib.reload(apps.api.lifespan)
    import apps.api.main

    importlib.reload(apps.api.main)
    return apps.api.main.create_app()


def _write_blob(content: bytes, ext: str = "png") -> str:
    """Write a content-addressed blob to BLOBS_DIR; return its sha256 hash."""

    import apps.api.paths

    sha = hashlib.sha256(content).hexdigest()
    apps.api.paths.BLOBS_DIR.mkdir(parents=True, exist_ok=True)
    (apps.api.paths.BLOBS_DIR / f"{sha}.{ext}").write_bytes(content)
    return sha


# A tiny valid PNG (1x1 transparent pixel) for content-type assertions.
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def test_blob_get_returns_stored_bytes_and_content_type(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A written blob is served back verbatim with an image content-type."""

    app = _fresh_app(monkeypatch, tmp_path)
    sha = _write_blob(PNG_BYTES, "png")

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/v1/blobs/{sha}")

    assert resp.status_code == 200, (
        f"expected 200 for a stored blob, got {resp.status_code} {resp.text}"
    )
    assert resp.content == PNG_BYTES, "served bytes do not match the stored blob"
    assert resp.headers["content-type"].startswith("image/"), (
        f"expected an image content-type, got {resp.headers.get('content-type')!r}"
    )


async def test_blob_get_rejects_path_traversal_hash(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A traversal-shaped hash is rejected via _is_inside_blobs_dir (T-blob-traversal)."""

    app = _fresh_app(monkeypatch, tmp_path)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Raw and percent-encoded traversal variants.
            for bad in (
                "../../../../etc/passwd",
                "..%2f..%2f..%2fetc%2fpasswd",
                "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
            ):
                resp = await client.get(f"/api/v1/blobs/{bad}")
                assert resp.status_code in (400, 404), (
                    f"T-blob-traversal BREACH: {bad!r} returned {resp.status_code}"
                )
                # The endpoint must never leak file content for a traversal.
                assert b"root:" not in resp.content, (
                    f"T-blob-traversal BREACH: /etc/passwd content leaked for {bad!r}"
                )


async def test_blob_get_unknown_hash_returns_404(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A well-formed but unknown hash returns 404 (not 500)."""

    app = _fresh_app(monkeypatch, tmp_path)
    unknown = "0" * 64  # valid sha256 shape, never written
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/v1/blobs/{unknown}")
    assert resp.status_code == 404, (
        f"expected 404 for unknown hash, got {resp.status_code}"
    )
