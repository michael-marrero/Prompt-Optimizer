"""Screenshot/diff blob transcoder — STORE-04 sha256 by-hash filesystem store.

Public surface (STORE-04 + D-14):

    INLINE_THRESHOLD_BYTES         Final[int] = 256 * 1024 (256 KiB).
    _maybe_externalize_screenshot  Convert a >=256KB Screenshot to its
                                   image_ref form and write the bytes to
                                   ``<BLOBS_DIR>/<sha256>.<ext>``.
                                   Returns <256KB chunks unchanged.
    _collect_blob_refs_from_content_blocks
                                   JSON-walk a stored ``content_blocks``
                                   array and return every ``image_ref`` +
                                   ``diff_ref`` Path.
    _is_inside_blobs_dir           Path-traversal defense: True iff a
                                   resolved Path lives inside
                                   ``BLOBS_DIR.resolve()``.

Where the conversion happens (RESEARCH §"Pattern 10" lines 635-637):
``routes/turn.py``'s ``event_stream`` generator calls
``_maybe_externalize_screenshot`` BEFORE ``buffer.append(chunk)`` AND
BEFORE ``yield ServerSentEvent(...)`` so both the SSE wire and the
persisted ``content_blocks`` JSON see the externalized ``image_ref``
shape for large screenshots.

Atomic write recipe (RESEARCH Pattern 10 + Pitfall 11):

    1. Compute sha256 of the decoded bytes.
    2. target = BLOBS_DIR / f"{sha}.{ext}"  ← deterministic by content.
    3. If target.exists(): short-circuit (idempotent). Two concurrent
       turns producing identical content land at the same target;
       whichever finishes second sees the file already on disk.
    4. Otherwise write to a UNIQUE tmp path
       ``target.parent / f"{target.name}.{secrets.token_hex(4)}.tmp"``
       (Pitfall 11 — sharing the tmp name across two concurrent writes
       of identical content corrupts the in-flight tmp file).
    5. tmp.replace(target) — atomic on POSIX + Windows when the tmp
       and target share a filesystem (which they always do here:
       both live under BLOBS_DIR).

Cascade unlink semantics (D-14):
    ``routes/threads.py:DELETE /threads/{id}`` (via
    ``db.queries.delete_thread``) walks every message's
    ``content_blocks`` JSON BEFORE the DB DELETE, collects every
    ``image_ref`` + ``diff_ref`` path, then unlinks each file (T-03-Path
    defense skips paths outside BLOBS_DIR). Order matters: BLOBS FIRST
    so an interrupted delete leaves orphan blobs (recoverable by a
    future ``make gc-blobs``) rather than stale DB rows pointing to
    missing files.

**Anti-patterns explicitly forbidden:**
    - NEVER the stdlib ``os`` rename function across filesystems (use
      ``Path.replace`` — cross-platform-safe atomic move on the same
      filesystem).
    - NEVER share a tmp name across writes (Pitfall 11 — race on
      identical content).
    - NEVER unlink a path without the ``_is_inside_blobs_dir`` guard
      (T-03-Path defense against tampered DB ``content_blocks``).
    - NEVER use stringly-typed path joins from ``os`` (Phase 2
      ``pathlib`` convention).
    - NEVER mutate ``sys.path``.

Cross-refs:
    - 03-CONTEXT.md D-14 (Screenshot dual image_b64 / image_ref +
      cascade unlink semantics)
    - 03-RESEARCH.md §"Pattern 10" lines 633-668 (canonical source)
    - 03-RESEARCH.md §"Pitfall 11" lines 977-980 (unique tmp suffix)
    - 03-RESEARCH.md §"Security Domain" lines 1198-1200 (path-traversal
      defense at unlink time)
    - 03-PATTERNS.md §"Database Layer" line 38 (blobs.py role +
      anti-pattern guidance)
    - apps/api/paths.py (BLOBS_DIR source of truth)
    - apps/api/backends/chunks.py (Screenshot model definition)
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
from pathlib import Path
from typing import Final

from apps.api.backends.chunks import Screenshot
from apps.api.paths import BLOBS_DIR

logger = logging.getLogger(__name__)


# 256 KiB threshold per STORE-04. Wire-level base64 sizes are ~33% over
# raw byte sizes; the threshold applies to the DECODED byte length so
# the inline/ref boundary tracks the actual filesystem footprint, not
# the wire payload size.
INLINE_THRESHOLD_BYTES: Final[int] = 256 * 1024


def _is_inside_blobs_dir(path: Path) -> bool:
    """Return True iff ``path`` resolves inside ``BLOBS_DIR``.

    T-03-Path defense. A tampered DB row could try to redirect
    ``image_ref`` to ``/etc/passwd`` to trigger arbitrary file deletion
    during cascade unlink. The guard resolves the path (collapses
    ``..`` and symlinks) and asserts containment with a boundary-safe
    prefix check (the trailing-separator handling stops sibling
    directories like ``BLOBS_DIR_evil`` from accidentally satisfying a
    naive ``startswith``).
    """

    # Read ``BLOBS_DIR`` off the live ``apps.api.paths`` module rather
    # than the value bound at import so a ``PROMPT_OPTIMIZER_HOME``
    # override applied via ``importlib.reload(apps.api.paths)`` in tests
    # is honored. Falls back to the import-time module global if the
    # dynamic lookup ever fails (it never does in practice).
    try:
        import apps.api.paths as _paths

        blobs_dir = _paths.BLOBS_DIR
    except Exception:
        blobs_dir = BLOBS_DIR

    try:
        resolved = Path(path).resolve()
        blobs_resolved = blobs_dir.resolve()
    except Exception:
        # ``resolve()`` raises on certain malformed paths on Windows.
        # Defensively bail to "not inside" so the unlink does not run.
        return False

    # Boundary-safe prefix check: ``"/a/b"`` is inside ``"/a"`` but
    # ``"/a/bc"`` is NOT. We split with the OS separator to make the
    # comparison work on both POSIX and Windows.
    try:
        resolved.relative_to(blobs_resolved)
        return True
    except ValueError:
        return False


def _maybe_externalize_screenshot(chunk: Screenshot) -> Screenshot:
    """Convert a >=256KB Screenshot to its image_ref form.

    Behaviour:
        - ``chunk.image_b64 is None``: return chunk unchanged (already
          externalized or empty payload).
        - decoded byte length < ``INLINE_THRESHOLD_BYTES``: return chunk
          unchanged (stays inline as base64 in ``content_blocks``).
        - decoded byte length >= ``INLINE_THRESHOLD_BYTES``: compute
          sha256, atomically write bytes to
          ``BLOBS_DIR / f"{sha}.{ext}"``, return a new ``Screenshot``
          with ``image_b64=None`` and ``image_ref=f"{sha}.{ext}"`` (the
          bare content KEY, NOT the absolute path — BL-01).

    Atomicity (RESEARCH Pattern 10 + Pitfall 11):
        - Idempotent: if the target already exists (same sha256), skip
          the write entirely. The content is content-addressed so a
          pre-existing file is byte-identical by definition.
        - Per-write unique tmp suffix via ``secrets.token_hex(4)`` so
          two concurrent writes of identical content land on distinct
          ``.tmp`` paths and never corrupt each other's in-flight
          write. The final ``tmp.replace(target)`` race is benign —
          both writes produced the same bytes; whichever finishes last
          wins, file content is correct either way.
    """

    if chunk.image_b64 is None:
        return chunk

    raw = base64.b64decode(chunk.image_b64)
    if len(raw) < INLINE_THRESHOLD_BYTES:
        return chunk

    sha = hashlib.sha256(raw).hexdigest()
    ext = chunk.image_format
    target = BLOBS_DIR / f"{sha}.{ext}"

    if not target.exists():
        BLOBS_DIR.mkdir(parents=True, exist_ok=True)
        # Pitfall 11: unique tmp suffix per write. Two concurrent
        # writes of identical content MUST land on distinct .tmp
        # paths so neither corrupts the other's in-flight bytes.
        tmp = target.parent / f"{target.name}.{secrets.token_hex(4)}.tmp"
        tmp.write_bytes(raw)
        # ``Path.replace`` is the cross-platform-safe atomic move.
        # The stdlib rename function is an anti-pattern per
        # PATTERNS.md — fails across filesystems on POSIX and lacks
        # Windows-overwrite semantics.
        tmp.replace(target)
        logger.debug(
            "externalized screenshot sha=%s size=%d bytes path=%s",
            sha,
            len(raw),
            target,
        )

    # BL-01: store the bare content KEY (``<sha>.<ext>``), not the
    # absolute filesystem path. The blob-serving endpoint
    # (``routes/blobs.py:get_blob``) and the React bubble
    # (``ComputerUseBubble.screenshotSrc``) both contract on the bare
    # sha stem; an absolute path here interpolated into ``/api/blobs/...``
    # produces a traversal-shaped URL that the endpoint rejects with a
    # 404, so every >=256KB screenshot rendered blank. The single
    # canonical representation is the filename; the cascade-unlink path
    # in ``db.queries.delete_thread`` re-anchors it to ``BLOBS_DIR``.
    return chunk.model_copy(
        update={"image_ref": f"{sha}.{ext}", "image_b64": None}
    )


def _collect_blob_refs_from_content_blocks(
    content_blocks_json: str,
) -> list[Path]:
    """JSON-walk ``content_blocks`` and return every blob-ref Path.

    Used by ``db.queries.delete_thread`` to cascade-unlink blob files
    BEFORE the DB DELETE (D-14). Returns Paths for both ``image_ref``
    (Screenshot — v1) and ``diff_ref`` (FileDiff — forward-compat;
    the v1 adapters do not currently emit >256KB diffs but the column
    is already in the wire shape so future externalization works
    without a schema change).

    Defensive: malformed JSON returns an empty list. The route
    handler must NEVER raise on a corrupted ``content_blocks`` row —
    the cascade delete should still succeed; we just skip the unlink
    for the unparseable row.

    Representation (BL-01): ``image_ref`` / ``diff_ref`` are stored as
    the bare content KEY (``<sha>.<ext>``) rather than an absolute path.
    A relative key is re-anchored to ``BLOBS_DIR`` here so the
    cascade-unlink resolves to the real file on disk. Absolute paths
    (legacy rows written before BL-01, or hand-built test fixtures) are
    passed through verbatim so the ``_is_inside_blobs_dir`` guard still
    decides their fate.
    """

    try:
        blocks = json.loads(content_blocks_json)
    except (json.JSONDecodeError, TypeError):
        logger.warning(
            "failed to parse content_blocks JSON; skipping blob walk"
        )
        return []

    if not isinstance(blocks, list):
        return []

    # Read ``BLOBS_DIR`` off the live module (honoring a test-time
    # ``importlib.reload(apps.api.paths)`` override) — same pattern as
    # ``_is_inside_blobs_dir``.
    try:
        import apps.api.paths as _paths

        blobs_dir = _paths.BLOBS_DIR
    except Exception:
        blobs_dir = BLOBS_DIR

    def _to_path(ref: str) -> Path:
        # Bare content key (``<sha>.<ext>``) → re-anchor under BLOBS_DIR.
        # Absolute legacy paths are returned unchanged.
        p = Path(ref)
        if p.is_absolute():
            return p
        return blobs_dir / ref

    refs: list[Path] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        image_ref = block.get("image_ref")
        if isinstance(image_ref, str) and image_ref:
            refs.append(_to_path(image_ref))
        diff_ref = block.get("diff_ref")
        if isinstance(diff_ref, str) and diff_ref:
            refs.append(_to_path(diff_ref))
    return refs
