"""Wave 5 blob transcoder + cascade-unlink tests — STORE-04 + D-14.

Nine sub-tests covering the full blob storage surface
(STORE-04 + D-14 + Pitfall 11 + T-03-Path):

    test_small_screenshot_stays_inline
                                       <256KB Screenshot returns
                                       unchanged from
                                       ``_maybe_externalize_screenshot``;
                                       image_b64 preserved, image_ref
                                       still None.

    test_large_screenshot_becomes_ref
                                       >=256KB Screenshot converts to
                                       image_ref shape: image_b64=None,
                                       image_ref="<sha>.png" (bare content
                                       KEY, BL-01 — not an absolute path);
                                       file exists on disk under BLOBS_DIR
                                       with the decoded bytes.

    test_identical_content_is_idempotent
                                       Calling twice with the same payload
                                       writes the same file; the second
                                       call short-circuits via
                                       ``target.exists()``.

    test_unique_tmp_suffix_prevents_race
                                       Pitfall 11: each write uses a
                                       per-call ``secrets.token_hex(4)``
                                       suffix on its .tmp name so two
                                       concurrent writes of identical
                                       content do NOT collide.

    test_jpeg_extension_honoured       ``image_format="jpeg"`` produces
                                       ``<sha>.jpeg`` on disk.

    test_collect_blob_refs_from_content_blocks
                                       JSON-walk a content_blocks array
                                       and return every image_ref +
                                       diff_ref in order.

    test_is_inside_blobs_dir           Path-traversal defense
                                       (T-03-Path): True for paths
                                       under BLOBS_DIR; False for
                                       /etc/passwd; False for
                                       ``BLOBS_DIR / ".." / "etc"``
                                       (resolves outside BLOBS_DIR).

    test_screenshot_chunk_externalized_in_stream
                                       Integration: POST /turn with a
                                       large Screenshot lands the
                                       externalized form in both the
                                       SSE wire AND the DB
                                       content_blocks JSON.

    test_small_screenshot_chunk_stays_inline_in_stream
                                       Integration: POST /turn with a
                                       small Screenshot preserves
                                       image_b64 in both the SSE wire
                                       AND the DB content_blocks JSON;
                                       no file written to BLOBS_DIR.

All async integration tests use ``httpx.AsyncClient + ASGITransport``
per API-08 / D-20. Pure-function tests use sync ``def``; only the
SSE pipeline tests are ``async def``.

Cross-refs:
    - 03-CONTEXT.md D-14 (Screenshot dual image_b64 / image_ref +
      cascade unlink semantics)
    - 03-RESEARCH.md §"Pattern 10" lines 633-668 (transcoder canonical
      source) + §"Pitfall 11" lines 977-980 (unique tmp suffix)
    - 03-RESEARCH.md §"Security Domain" lines 1198-1200 (path-traversal
      defense at unlink time)
    - 03-VALIDATION.md rows 3-05-01 / 3-05-02 lines 61-62
    - apps/api/tests/test_turn_streaming.py (Wave 4 SSE test pattern
      this file extends for the integration cases)
"""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from httpx import ASGITransport


# ---------------------------------------------------------------------
# Reload helpers — match test_turn_streaming.py _fresh_app pattern.
# ---------------------------------------------------------------------


def _reload_paths_and_blobs(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Point ``PROMPT_OPTIMIZER_HOME`` to ``tmp_path`` and reload paths + blobs.

    The pure-function tests below only need the module-level
    ``BLOBS_DIR`` constant to resolve under ``tmp_path``; no FastAPI
    app build needed.
    """

    monkeypatch.setenv("PROMPT_OPTIMIZER_HOME", str(tmp_path))
    import apps.api.paths

    importlib.reload(apps.api.paths)
    import apps.api.blobs

    importlib.reload(apps.api.blobs)


def _fresh_app(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Reload paths/blobs/lifespan/main under ``tmp_path`` and build a fresh app.

    Mirrors ``test_turn_streaming.py:_fresh_app`` — includes the
    ``sse_starlette`` purge so the class-identity break introduced by
    the Phase 1 D-18 smoke test does not bite when the suite is run
    as ``pytest src/ apps/``. See Wave 4 SUMMARY decisions for the
    full rationale.
    """

    monkeypatch.setenv("PROMPT_OPTIMIZER_HOME", str(tmp_path))

    # Purge sse_starlette so its EventSourceResponse reload picks up
    # the current starlette.responses.Response identity.
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
    return apps.api.main.create_app()


async def _create_thread(client, title: str = "t1") -> str:
    """POST /threads and return the new thread id."""

    resp = await client.post("/api/v1/threads", json={"title": title})
    assert resp.status_code == 200, (
        f"thread create failed: {resp.status_code} {resp.text}"
    )
    return resp.json()["id"]


# ---------------------------------------------------------------------
# Test 1 — small Screenshot stays inline (<256 KB threshold)
# ---------------------------------------------------------------------


def test_small_screenshot_stays_inline(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A <256KB Screenshot returns unchanged from the transcoder.

    100KB of raw bytes encodes to ~133KB of base64 — well under the
    256KB byte-level threshold. The transcoder decodes the b64 and
    measures raw byte length; the chunk is returned unchanged.
    """

    _reload_paths_and_blobs(monkeypatch, tmp_path)
    from apps.api.backends.chunks import Screenshot
    from apps.api.blobs import _maybe_externalize_screenshot

    small_raw = b"X" * (100 * 1024)
    small_b64 = base64.b64encode(small_raw).decode("ascii")
    chunk = Screenshot(step=1, image_b64=small_b64)
    result = _maybe_externalize_screenshot(chunk)

    assert result.image_b64 == small_b64, (
        "image_b64 must be preserved for <256KB payload"
    )
    assert result.image_ref is None, (
        f"image_ref must remain None for <256KB payload; got {result.image_ref!r}"
    )
    assert result.step == 1, "step must be preserved"


# ---------------------------------------------------------------------
# Test 2 — large Screenshot becomes a ref (>=256 KB)
# ---------------------------------------------------------------------


def test_large_screenshot_becomes_ref(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A >=256KB Screenshot is rewritten to ``image_ref`` shape.

    300KB raw bytes -> sha256 hex -> ``<BLOBS_DIR>/<sha>.png`` on
    disk; ``image_b64`` cleared; ``image_ref`` set to the bare content
    KEY ``<sha>.png`` (BL-01 — NOT the absolute path; the serving
    endpoint and React bubble both contract on the bare key/stem).
    """

    _reload_paths_and_blobs(monkeypatch, tmp_path)
    from apps.api.backends.chunks import Screenshot
    from apps.api.blobs import _maybe_externalize_screenshot
    from apps.api.paths import BLOBS_DIR

    raw = b"Y" * (300 * 1024)
    b64 = base64.b64encode(raw).decode("ascii")
    chunk = Screenshot(step=2, image_b64=b64)
    result = _maybe_externalize_screenshot(chunk)

    assert result.image_b64 is None, "image_b64 must be cleared for >=256KB"
    assert result.image_ref is not None, "image_ref must be set for >=256KB"

    sha = hashlib.sha256(raw).hexdigest()
    # BL-01: image_ref is the bare content key, not an absolute path.
    assert result.image_ref == f"{sha}.png", (
        f"image_ref must be the bare key {sha}.png; got {result.image_ref}"
    )
    expected = BLOBS_DIR / f"{sha}.png"
    assert expected.exists(), f"blob file must exist at {expected}"
    assert expected.read_bytes() == raw, (
        "blob file contents must equal the decoded base64 bytes"
    )
    assert result.step == 2, "step must be preserved"


# ---------------------------------------------------------------------
# Test 3 — identical content is idempotent
# ---------------------------------------------------------------------


def test_identical_content_is_idempotent(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Calling the transcoder twice with the same payload writes ONCE.

    Same sha256 -> same target path -> second call sees
    ``target.exists()`` and short-circuits the write step. The file
    mtime is unchanged on the second call.
    """

    _reload_paths_and_blobs(monkeypatch, tmp_path)
    from apps.api.backends.chunks import Screenshot
    from apps.api.blobs import _maybe_externalize_screenshot
    from apps.api.paths import BLOBS_DIR

    raw = b"Z" * (300 * 1024)
    b64 = base64.b64encode(raw).decode("ascii")
    chunk = Screenshot(step=1, image_b64=b64)

    result1 = _maybe_externalize_screenshot(chunk)
    # BL-01: image_ref is the bare content key — re-anchor to BLOBS_DIR.
    target = BLOBS_DIR / result1.image_ref
    mtime_after_first = target.stat().st_mtime_ns

    # Second call must short-circuit (target already exists).
    result2 = _maybe_externalize_screenshot(chunk)
    mtime_after_second = target.stat().st_mtime_ns

    assert result1.image_ref == result2.image_ref, (
        "idempotent calls must return the same image_ref"
    )
    assert mtime_after_first == mtime_after_second, (
        "second call must NOT re-write the file (mtime preserved)"
    )


# ---------------------------------------------------------------------
# Test 4 — unique tmp suffix prevents race (Pitfall 11)
# ---------------------------------------------------------------------


def test_unique_tmp_suffix_prevents_race(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Each write uses a fresh ``secrets.token_hex(4)`` tmp suffix.

    Pitfall 11: when two turns concurrently emit identical content
    (same sha256 -> same target path), they MUST land on distinct
    ``.tmp`` paths so neither corrupts the other's in-flight write.
    The final ``tmp.replace(target)`` race is benign because both
    writes produced byte-identical content.

    We force the idempotent short-circuit (``target.exists()``) to
    not fire by patching it to always return False, then capture
    every tmp Path passed to ``Path.write_bytes``.
    """

    _reload_paths_and_blobs(monkeypatch, tmp_path)
    from apps.api.backends.chunks import Screenshot
    from apps.api.blobs import _maybe_externalize_screenshot

    raw = b"W" * (300 * 1024)
    b64 = base64.b64encode(raw).decode("ascii")

    captured_tmp_paths: list[Path] = []

    real_write_bytes = Path.write_bytes
    real_replace = Path.replace
    real_exists = Path.exists

    def fake_write_bytes(self: Path, data: bytes) -> int:
        # Capture every tmp path written so we can assert uniqueness.
        if ".tmp" in self.name:
            captured_tmp_paths.append(self)
        return real_write_bytes(self, data)

    def fake_exists(self: Path) -> bool:
        # Force the idempotent short-circuit to never fire so the
        # write path runs on both calls.
        if self.name.endswith(".png") and "." in self.name:
            sha_part = self.name.rsplit(".", 1)[0]
            if len(sha_part) == 64:  # sha256 hex length
                return False
        return real_exists(self)

    with patch.object(Path, "write_bytes", fake_write_bytes), patch.object(
        Path, "exists", fake_exists
    ):
        chunk = Screenshot(step=1, image_b64=b64)
        _maybe_externalize_screenshot(chunk)
        _maybe_externalize_screenshot(chunk)

    assert len(captured_tmp_paths) >= 2, (
        f"expected ≥2 tmp paths captured; got {captured_tmp_paths}"
    )
    # Pitfall 11: the two captured tmp paths MUST differ — that is the
    # entire point of the per-write token_hex(4) suffix.
    tmp_names = [p.name for p in captured_tmp_paths[:2]]
    assert tmp_names[0] != tmp_names[1], (
        f"tmp names must be unique per write (Pitfall 11); got {tmp_names}"
    )


# ---------------------------------------------------------------------
# Test 5 — jpeg extension is honoured
# ---------------------------------------------------------------------


def test_jpeg_extension_honoured(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """``image_format="jpeg"`` produces ``<sha>.jpeg`` on disk."""

    _reload_paths_and_blobs(monkeypatch, tmp_path)
    from apps.api.backends.chunks import Screenshot
    from apps.api.blobs import _maybe_externalize_screenshot
    from apps.api.paths import BLOBS_DIR

    raw = b"J" * (300 * 1024)
    b64 = base64.b64encode(raw).decode("ascii")
    chunk = Screenshot(step=3, image_b64=b64, image_format="jpeg")
    result = _maybe_externalize_screenshot(chunk)

    assert result.image_ref is not None
    assert result.image_ref.endswith(".jpeg"), (
        f"jpeg format must produce a .jpeg file extension; got {result.image_ref}"
    )
    # BL-01: image_ref is the bare content key — re-anchor to BLOBS_DIR.
    assert (BLOBS_DIR / result.image_ref).exists()


# ---------------------------------------------------------------------
# Test 6 — collect blob refs from content_blocks JSON
# ---------------------------------------------------------------------


def test_collect_blob_refs_from_content_blocks(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """JSON-walk a content_blocks array and return every image_ref + diff_ref.

    Non-screenshot blocks (tool_call) are skipped. Order is preserved.
    Malformed JSON returns an empty list (defensive).
    """

    _reload_paths_and_blobs(monkeypatch, tmp_path)
    from apps.api.blobs import _collect_blob_refs_from_content_blocks

    cb = json.dumps(
        [
            {"type": "screenshot", "step": 1, "image_ref": "/tmp/foo.png"},
            {
                "type": "tool_call",
                "tool_call_id": "tc1",
                "tool_name": "search",
                "arguments": {},
            },
            {"type": "screenshot", "step": 2, "image_ref": "/tmp/bar.png"},
        ]
    )
    refs = _collect_blob_refs_from_content_blocks(cb)
    assert refs == [Path("/tmp/foo.png"), Path("/tmp/bar.png")], (
        f"refs must be the two image_ref Paths in order; got {refs}"
    )

    # Forward-compat: diff_ref also collected for future large-diff
    # externalization (D-14 mentions diff_ref).
    cb_with_diff = json.dumps(
        [
            {"type": "file_diff", "diff_ref": "/tmp/big.diff"},
            {"type": "screenshot", "image_ref": "/tmp/baz.png"},
        ]
    )
    refs_with_diff = _collect_blob_refs_from_content_blocks(cb_with_diff)
    assert refs_with_diff == [
        Path("/tmp/big.diff"),
        Path("/tmp/baz.png"),
    ], f"diff_ref must be collected alongside image_ref; got {refs_with_diff}"

    # Malformed JSON returns []. Defensive — never raise.
    assert _collect_blob_refs_from_content_blocks("not json") == []
    assert _collect_blob_refs_from_content_blocks("") == []


# ---------------------------------------------------------------------
# Test 7 — _is_inside_blobs_dir path-traversal defense (T-03-Path)
# ---------------------------------------------------------------------


def test_is_inside_blobs_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """``_is_inside_blobs_dir`` blocks paths outside ``BLOBS_DIR``.

    T-03-Path defense: a tampered DB row could try to redirect
    ``image_ref`` to ``/etc/passwd`` to trigger arbitrary file
    deletion. The guard resolves the path and asserts the result is
    inside ``BLOBS_DIR.resolve()`` before unlinking.
    """

    _reload_paths_and_blobs(monkeypatch, tmp_path)
    from apps.api.blobs import _is_inside_blobs_dir
    from apps.api.paths import BLOBS_DIR

    # Inside — happy path.
    assert _is_inside_blobs_dir(BLOBS_DIR / "abc.png") is True, (
        "path under BLOBS_DIR must return True"
    )

    # Absolute outside — must fail.
    assert _is_inside_blobs_dir(Path("/etc/passwd")) is False, (
        "/etc/passwd must NOT resolve inside BLOBS_DIR"
    )

    # Path-traversal attempt — must resolve outside BLOBS_DIR.
    assert _is_inside_blobs_dir(BLOBS_DIR / ".." / "etc" / "passwd") is False, (
        "BLOBS_DIR/../etc/passwd resolves above BLOBS_DIR — must return False"
    )

    # Path-traversal back-and-forth — still inside if resolved
    # path stays under BLOBS_DIR.
    assert _is_inside_blobs_dir(BLOBS_DIR / "sub" / ".." / "abc.png") is True, (
        "path traversal that resolves back inside must return True"
    )


# ---------------------------------------------------------------------
# Test 8 — integration: large Screenshot externalized in SSE stream
# ---------------------------------------------------------------------


async def test_screenshot_chunk_externalized_in_stream(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A >=256KB Screenshot is externalized BEFORE wire + DB persist.

    The route's ``event_stream`` calls ``_maybe_externalize_screenshot``
    BEFORE both ``buffer.append`` AND ``yield ServerSentEvent`` so the
    wire and the persisted ``content_blocks`` JSON both see the
    externalized ``image_ref`` shape.
    """

    app = _fresh_app(monkeypatch, tmp_path)
    from apps.api.backends.chunks import Done, Screenshot
    from apps.api.paths import BLOBS_DIR
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    raw = b"S" * (300 * 1024)
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

    sse_screenshot_data: list[str] = []
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            async with client.stream(
                "POST",
                f"/api/v1/threads/{thread_id}/turn",
                json={"message": "browse"},
            ) as resp:
                assert resp.status_code == 200, (
                    f"POST returned {resp.status_code}: "
                    f"{await resp.aread()!r}"
                )
                current_event: str | None = None
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        current_event = line.split(":", 1)[1].strip()
                        if current_event == "done":
                            break
                    elif line.startswith("data:") and current_event == "screenshot":
                        sse_screenshot_data.append(
                            line.split(":", 1)[1].strip()
                        )

            # SSE wire assertions — the screenshot event MUST carry
            # image_ref and NOT image_b64.
            assert sse_screenshot_data, (
                "expected at least one screenshot event in the SSE stream"
            )
            sse_payload = json.loads(sse_screenshot_data[0])
            assert sse_payload.get("image_b64") is None, (
                f"SSE wire image_b64 must be None for >=256KB; "
                f"got {sse_payload.get('image_b64')!r}"
            )
            assert sse_payload.get("image_ref") is not None, (
                "SSE wire image_ref must be set for >=256KB"
            )

            # BL-01: image_ref is the bare content key (`<sha>.<ext>`),
            # NOT an absolute path. It must NOT contain a path separator.
            image_ref = sse_payload["image_ref"]
            assert "/" not in image_ref and "\\" not in image_ref, (
                f"image_ref must be the bare content key, not a path; "
                f"got {image_ref!r}"
            )

            # Blob file lives on disk under BLOBS_DIR (re-anchor the key).
            ref_path = BLOBS_DIR / image_ref
            assert ref_path.exists(), f"blob file must exist at {ref_path}"
            assert ref_path.read_bytes() == raw, (
                "blob file contents must equal the decoded base64 bytes"
            )

            # DB assertion — the assistant message's content_blocks
            # JSON must also carry the externalized ref shape.
            db = app.state.db
            async with db.execute(
                "SELECT content_blocks FROM messages"
                " WHERE thread_id = ? AND role = 'assistant'",
                (thread_id,),
            ) as cur:
                row = await cur.fetchone()
            assert row is not None, "assistant message must persist"
            db_blocks = json.loads(row[0])
            screenshot_blocks = [
                b for b in db_blocks if b.get("type") == "screenshot"
            ]
            assert screenshot_blocks, (
                "assistant content_blocks must contain the screenshot"
            )
            assert screenshot_blocks[0].get("image_b64") is None, (
                "DB content_blocks image_b64 must be None for >=256KB"
            )
            assert screenshot_blocks[0].get("image_ref") == image_ref, (
                f"DB content_blocks image_ref must match SSE ref; "
                f"got {screenshot_blocks[0].get('image_ref')}"
            )


# ---------------------------------------------------------------------
# Test 9 — integration: small Screenshot stays inline in SSE stream
# ---------------------------------------------------------------------


async def test_small_screenshot_chunk_stays_inline_in_stream(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A <256KB Screenshot preserves ``image_b64`` end-to-end.

    The wire and the DB both see the inline shape; no file is written
    under ``BLOBS_DIR``.
    """

    app = _fresh_app(monkeypatch, tmp_path)
    from apps.api.backends.chunks import Done, Screenshot
    from apps.api.paths import BLOBS_DIR
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    small_raw = b"s" * (100 * 1024)
    small_b64 = base64.b64encode(small_raw).decode("ascii")
    fake = FakeStreamingAdapter(
        [Screenshot(step=1, image_b64=small_b64), Done()]
    )
    app.state.adapters = {"openrouter": fake}

    from src.routing.schema import RoutingDecision

    def fake_decide(*args, **kwargs):
        return RoutingDecision(
            backend="openrouter",
            model_or_agent="openai/gpt-5",
            rationale="test",
            confidence=0.9,
            signals={},
        )

    monkeypatch.setattr("apps.api.routes.turn.decide", fake_decide)

    sse_screenshot_data: list[str] = []
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            async with client.stream(
                "POST",
                f"/api/v1/threads/{thread_id}/turn",
                json={"message": "ok"},
            ) as resp:
                current_event: str | None = None
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        current_event = line.split(":", 1)[1].strip()
                        if current_event == "done":
                            break
                    elif line.startswith("data:") and current_event == "screenshot":
                        sse_screenshot_data.append(
                            line.split(":", 1)[1].strip()
                        )

            assert sse_screenshot_data
            sse_payload = json.loads(sse_screenshot_data[0])
            assert sse_payload.get("image_b64") == small_b64, (
                "SSE wire image_b64 must be preserved for <256KB"
            )
            assert sse_payload.get("image_ref") is None, (
                f"SSE wire image_ref must be None for <256KB; "
                f"got {sse_payload.get('image_ref')!r}"
            )

            # No file written to BLOBS_DIR for inline screenshots.
            if BLOBS_DIR.exists():
                blob_files = list(BLOBS_DIR.iterdir())
                assert not blob_files, (
                    f"BLOBS_DIR must be empty for <256KB; got {blob_files}"
                )

            # DB content_blocks also preserves the inline shape.
            db = app.state.db
            async with db.execute(
                "SELECT content_blocks FROM messages"
                " WHERE thread_id = ? AND role = 'assistant'",
                (thread_id,),
            ) as cur:
                row = await cur.fetchone()
            assert row is not None
            db_blocks = json.loads(row[0])
            screenshot_blocks = [
                b for b in db_blocks if b.get("type") == "screenshot"
            ]
            assert screenshot_blocks
            assert screenshot_blocks[0].get("image_b64") == small_b64, (
                "DB content_blocks image_b64 must be preserved for <256KB"
            )
            assert screenshot_blocks[0].get("image_ref") is None
