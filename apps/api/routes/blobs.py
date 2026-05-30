"""GET /api/v1/blobs/{hash} — byte-serving endpoint for externalized blobs.

Public surface (UI-10, STORE-04, T-blob-traversal):

    router    APIRouter(prefix="/api/v1", tags=["blobs"])

Why this endpoint exists (RESEARCH resolved open question #1):

    ``apps/api/blobs.py`` is a transcoder + traversal guard only. When a
    screenshot (or, forward-compat, a diff) is >=256KB it is externalized
    by ``_maybe_externalize_screenshot`` to ``BLOBS_DIR / f"{sha}.{ext}"``
    and the SSE/content_blocks payload carries ``image_b64=None`` plus an
    ``image_ref``. Without an HTTP endpoint to serve those bytes,
    ComputerUseBubble (UI-10) renders large screenshots blank. This module
    is the missing serving seam — the (small) third server seam UI-SPEC
    §8.2 assumed but CONTEXT did not enumerate.

Endpoint contract:

    GET /api/v1/blobs/{hash}
        →  200  + raw bytes + image/* content-type   — blob found
        →  404                                        — unknown hash,
                                                        traversal-shaped
                                                        hash, or a hash that
                                                        resolves outside
                                                        BLOBS_DIR

The blob filename layout is ``<sha256>.<ext>`` (see
``apps/api/blobs.py:_maybe_externalize_screenshot`` line ~162). The
``{hash}`` path segment is the bare ``<sha>`` stem; the stored extension
is discovered by globbing ``BLOBS_DIR / f"{hash}.*"`` because the wire
shape carries only the externalized ``image_ref`` (a full path) while the
browser-facing proxy URL is content-keyed by sha alone.

Security (T-05-02-TRAV — Tampering, V4 access control):

    The ``{hash}`` path component is UNTRUSTED. BEFORE any filesystem read:
        1. Reject any ``hash`` containing a path separator or ``..`` up
           front (404). FastAPI does not URL-decode ``%2f`` into a path
           separator inside a single path segment, but ``..`` and literal
           separators are still rejected defensively.
        2. Resolve the candidate file path and call
           ``apps.api.blobs._is_inside_blobs_dir(resolved)`` — the SAME
           boundary-safe ``resolve()`` + ``relative_to()`` guard used by
           the cascade-unlink path. A path that escapes BLOBS_DIR
           (``../``, encoded variants, symlink tricks, sibling dirs like
           ``BLOBS_DIR_evil``) returns False and we 404 — the read never
           runs, so ``/etc/passwd`` content can never leak.

    The guard is REUSED, never reinvented (key_link to apps/api/blobs.py).

Why the browser never reaches this directly (T-05-02-PROXY, UI-17):

    The ComputerUseBubble sets ``<img src="/api/blobs/{hash}">`` which hits
    the Next proxy ``apps/web/app/api/blobs/[hash]/route.ts``; the proxy is
    the only caller of this FastAPI endpoint. ``browser-isolation.spec.ts``
    (extended in 05-06) enforces zero direct browser→FastAPI blob calls.

Registration:

    This module only EXPORTS ``router``. 05-01 owns ``main.py`` and mounts
    it via ``app.include_router``. The end-to-end RED test
    (``apps/api/tests/test_blobs_endpoint.py``) goes green once 05-01
    registers the router.

Cross-refs:
    - 05-RESEARCH.md Pitfall 1 (Option A — guarded GET endpoint) + Security
      Domain (path-traversal mitigation)
    - apps/api/blobs.py:_is_inside_blobs_dir (the reused guard) +
      _maybe_externalize_screenshot (the ``<sha>.<ext>`` layout)
    - apps/api/paths.py:BLOBS_DIR (store root)
    - apps/api/routes/rename.py (router shell + HTTPException style)
"""

from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

import apps.api.paths
from apps.api.blobs import _is_inside_blobs_dir

# ``__name__`` resolves to ``apps.api.routes.blobs`` so the Phase 2
# RedactionFilter on the root logger catches every record. NEVER print().
logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1", tags=["blobs"])


# Map blob file extensions to image content-types. ``mimetypes`` covers
# png/jpeg/gif/webp on every platform we support; we keep an explicit
# fallback so an unknown extension still serves with a safe, generic type
# rather than raising.
_FALLBACK_CONTENT_TYPE = "application/octet-stream"


def _content_type_for(path: Path) -> str:
    """Best-effort content-type from a blob file extension."""

    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or _FALLBACK_CONTENT_TYPE


@router.get("/blobs/{blob_hash}")
async def get_blob(blob_hash: str) -> Response:
    """Serve the bytes of a stored ``<sha>.<ext>`` blob from BLOBS_DIR.

    ``blob_hash`` is the bare sha256 stem (IN-01: renamed from ``hash``
    to avoid shadowing the ``hash()`` builtin). The stored extension is
    discovered by globbing ``BLOBS_DIR / f"{blob_hash}.*"``. The
    traversal guard runs on the resolved candidate path BEFORE any read;
    an unknown or out-of-bounds hash returns 404.
    """

    # ----------------------------------------------------------------
    # V4 / T-05-02-TRAV up-front rejection: a legitimate sha256 stem is
    # hex-only and contains no path separators or ``..`` segments. Reject
    # anything that smells like traversal BEFORE we touch the filesystem.
    # ----------------------------------------------------------------
    if (
        not blob_hash
        or "/" in blob_hash
        or "\\" in blob_hash
        or ".." in blob_hash
        or os.sep in blob_hash
        or (os.altsep and os.altsep in blob_hash)
    ):
        logger.warning("rejected traversal-shaped blob hash: %r", blob_hash)
        raise HTTPException(status_code=404, detail="blob not found")

    # Discover the stored ``<hash>.<ext>`` file. The store is content-
    # addressed so at most one extension exists per sha; glob and take the
    # first match. ``BLOBS_DIR.glob`` confines the search to the store
    # directory; combined with the guard below, no escape is possible.
    # Read ``BLOBS_DIR`` dynamically off the live ``apps.api.paths``
    # module (rather than a value bound at import) so the
    # ``PROMPT_OPTIMIZER_HOME`` override picked up by an
    # ``importlib.reload(apps.api.paths)`` in tests is honored here —
    # the route is constructed inside ``create_app()`` which may run
    # before or after the reload, and binding the path at import time
    # would otherwise pin the store to the pre-override location.
    blobs_dir = apps.api.paths.BLOBS_DIR
    try:
        candidates = sorted(blobs_dir.glob(f"{blob_hash}.*"))
    except (OSError, ValueError):
        candidates = []

    candidate: Path | None = None
    for c in candidates:
        # Defense in depth: confirm the resolved path is inside BLOBS_DIR
        # via the REUSED boundary-safe guard BEFORE any read. A symlink
        # inside the store pointing outside it is rejected here.
        if _is_inside_blobs_dir(c) and c.is_file():
            candidate = c
            break

    if candidate is None:
        raise HTTPException(status_code=404, detail="blob not found")

    try:
        data = candidate.read_bytes()
    except OSError as error:
        logger.warning("failed to read blob %s: %s", candidate.name, error)
        raise HTTPException(status_code=404, detail="blob not found") from error

    return Response(content=data, media_type=_content_type_for(candidate))
