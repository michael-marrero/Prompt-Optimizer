"""Phase 5 Wave 0 — RED tests for the feedback append endpoint (UI-15, D-11..D-14).

The browser cannot write the filesystem, so a new FastAPI endpoint
``POST /api/v1/feedback`` accepts a D-12 feedback row and appends it to
``FEEDBACK_LOG_PATH`` (``.planning/data/routing_feedback.jsonl``) using the
``apps/api/jsonl_log.py`` append pattern (async append, dir auto-create,
``PROMPT_OPTIMIZER_HOME`` override honored). Neither the route nor
``FEEDBACK_LOG_PATH`` exists yet — these tests are RED until 05-01/05-02 ship.

RED mechanism: the route module / ``FEEDBACK_LOG_PATH`` constant is imported
lazily inside ``_fresh_app``; if the producer is missing the test SKIPS
(``pytest.skip``) which the Wave-0 verify gate counts as RED. Once the route
exists the behavioral assertions run and must pass.

What this asserts (mirrors test_secure_no_key_in_logs.py for the key grep):
    - POST a D-12 row (sentiment up AND down) appends exactly ONE line per call.
    - The appended line carries a server-side ISO-8601-Z ``timestamp``.
    - ``PROMPT_OPTIMIZER_HOME`` override redirects the file under tmp_path.
    - A grep over the written file finds NO sk-/sk-ant-/Bearer key-shaped
      strings even when ``signals`` is fed a key-shaped value
      (T-feedback-key-smuggle).
    - ``extra="forbid"`` rejects unknown body fields with 422.

All tests use httpx.AsyncClient + ASGITransport (API-08 / D-20) — never the
synchronous FastAPI test-client wrapper.

Cross-refs:
    - 05-PATTERNS.md "apps/api/routes/feedback.py" + "JSONL append writer"
    - apps/api/jsonl_log.py:append_routing_decisions_jsonl (writer template)
    - apps/api/tests/test_secure_no_key_in_logs.py (no-key-in-log grep mirror)
    - .planning/phases/05-feature-complete-chat-ui/05-CONTEXT.md D-11..D-14
"""

from __future__ import annotations

import importlib
import json
import re
import typing

import httpx
import pytest
from httpx import ASGITransport

# A key-shaped value smuggled into the feedback row's signals dict. The writer
# must NEVER emit a recognisable key shape to disk (T-feedback-key-smuggle).
SMUGGLED_KEY = "sk-or-v1-FEEDBACKSMUGGLEAAAAAAA"
# Regex catching sk- / sk-ant- / Bearer key shapes (mirrors the SECRET_PATTERNS
# alphabet in apps/api/backends/logging_filter.py).
KEY_SHAPE = re.compile(r"sk-(?:ant-)?[A-Za-z0-9_-]{20,}|Bearer\s+\S+")


def _row(sentiment: str, *, smuggle: bool = False) -> dict:
    """Build a D-12 feedback row. The client never sends a timestamp — the
    server stamps it. ``smuggle`` injects a key-shaped value into signals."""

    signals: dict = {"task_type": "chat", "agentic_intent": False}
    if smuggle:
        signals["leaked"] = SMUGGLED_KEY
    return {
        "sentiment": sentiment,
        "thread_id": "t-1",
        "message_id": "m-1",
        "prompt": "What is the capital of France?",
        "decision": {
            "backend": "openrouter",
            "model_or_agent": "openai/gpt-5",
            "rationale": "Strong reasoning fit",
            "confidence": 0.9,
            "signals": signals,
        },
    }


def _fresh_app(monkeypatch: pytest.MonkeyPatch, tmp_path) -> typing.Any:
    """Reload paths under tmp_path and build a fresh app — RED-safe.

    LAZY-import the Wave 1+ producers (the feedback route, FEEDBACK_LOG_PATH).
    If they are absent the test SKIPS so this file is collectable in Wave 0
    while still reporting RED (skipped) until the feature lands.
    """

    monkeypatch.setenv("PROMPT_OPTIMIZER_HOME", str(tmp_path))
    import apps.api.paths

    importlib.reload(apps.api.paths)
    if not hasattr(apps.api.paths, "FEEDBACK_LOG_PATH"):
        pytest.skip("Phase 5 FEEDBACK_LOG_PATH not yet added to apps.api.paths")

    import apps.api.jsonl_log

    importlib.reload(apps.api.jsonl_log)

    try:
        import apps.api.routes.feedback as feedback_mod  # type: ignore[import-not-found]

        importlib.reload(feedback_mod)
    except ImportError:
        pytest.skip("Phase 5 apps.api.routes.feedback not yet implemented")

    import apps.api.lifespan

    importlib.reload(apps.api.lifespan)
    import apps.api.main

    importlib.reload(apps.api.main)
    return apps.api.main.create_app()


def _feedback_log_path():
    import apps.api.paths

    return apps.api.paths.FEEDBACK_LOG_PATH


async def test_feedback_appends_one_line_per_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Each POST appends exactly one line; up and down both log (D-11)."""

    app = _fresh_app(monkeypatch, tmp_path)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r1 = await client.post("/api/v1/feedback", json=_row("down"))
            assert r1.status_code in (200, 201), r1.text
            r2 = await client.post("/api/v1/feedback", json=_row("up"))
            assert r2.status_code in (200, 201), r2.text

    path = _feedback_log_path()
    assert path.exists(), "feedback log was not created"
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2, f"expected 2 appended rows, got {len(lines)}"
    sentiments = [json.loads(ln)["sentiment"] for ln in lines]
    assert sentiments == ["down", "up"]


async def test_feedback_row_has_server_side_iso_z_timestamp(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """The server stamps an ISO-8601-Z timestamp (client clock untrusted)."""

    app = _fresh_app(monkeypatch, tmp_path)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/v1/feedback", json=_row("down"))
            assert resp.status_code in (200, 201), resp.text

    line = _feedback_log_path().read_text(encoding="utf-8").splitlines()[0]
    record = json.loads(line)
    assert "timestamp" in record, "feedback row missing server-side timestamp"
    assert record["timestamp"].endswith("Z"), (
        f"timestamp not ISO-8601-Z: {record['timestamp']!r}"
    )


async def test_feedback_home_override_redirects_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """PROMPT_OPTIMIZER_HOME redirects FEEDBACK_LOG_PATH under tmp_path."""

    app = _fresh_app(monkeypatch, tmp_path)
    path = _feedback_log_path()
    # The redirected path must live under tmp_path (or the repo-relative
    # .planning/data dir anchored on the override — both acceptable).
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/v1/feedback", json=_row("down"))
            assert resp.status_code in (200, 201), resp.text
    assert str(tmp_path) in str(path), (
        f"FEEDBACK_LOG_PATH did not honor PROMPT_OPTIMIZER_HOME: {path}"
    )
    assert path.exists()


def test_decisions_log_home_override_redirects(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """PROMPT_OPTIMIZER_HOME redirects JSONL_LOG_PATH under tmp_path (AD-12).

    The routing-decisions log is written by the turn path (not POST
    /feedback), so this test asserts the constant directly after a
    reload rather than driving a route. It mirrors
    ``test_feedback_home_override_redirects_file`` for the feedback log:
    a single ``PROMPT_OPTIMIZER_HOME`` value must co-locate the decisions
    log, the feedback log, and the DB under one root.
    """

    monkeypatch.setenv("PROMPT_OPTIMIZER_HOME", str(tmp_path))
    import apps.api.paths

    importlib.reload(apps.api.paths)
    try:
        assert str(tmp_path) in str(apps.api.paths.JSONL_LOG_PATH), (
            "JSONL_LOG_PATH did not honor PROMPT_OPTIMIZER_HOME: "
            f"{apps.api.paths.JSONL_LOG_PATH}"
        )
        # Decisions log and feedback log share the same override root.
        assert str(tmp_path) in str(apps.api.paths.FEEDBACK_LOG_PATH)
        assert apps.api.paths.JSONL_LOG_PATH.parents[2] == apps.api.paths.USER_HOME
    finally:
        # Cleanup: drop the override and reload so later tests see the
        # default (mirror test_smoke.py::test_paths_honors_env_override).
        monkeypatch.delenv("PROMPT_OPTIMIZER_HOME", raising=False)
        importlib.reload(apps.api.paths)


async def test_feedback_no_key_shape_in_written_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """T-feedback-key-smuggle: a key-shaped signals value never lands on disk.

    Mirrors test_secure_no_key_in_logs.py's grep. Even though feedback rows
    legitimately carry the routing decision's signals, a key-shaped string
    smuggled there must be redacted before the append (or rejected)."""

    app = _fresh_app(monkeypatch, tmp_path)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/feedback", json=_row("down", smuggle=True)
            )
            # Either the row is accepted with the key redacted, or rejected —
            # both are acceptable; what is NOT acceptable is a raw key on disk.
            assert resp.status_code in (200, 201, 422), resp.text

    path = _feedback_log_path()
    if path.exists():
        content = path.read_text(encoding="utf-8")
        assert SMUGGLED_KEY not in content, (
            "T-feedback-key-smuggle BREACH: raw key in feedback log"
        )
        assert not KEY_SHAPE.search(content), (
            f"T-feedback-key-smuggle BREACH: key-shaped string in log: {content!r}"
        )


async def test_feedback_rejects_unknown_fields_422(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """extra='forbid' on the body model rejects unknown fields with 422."""

    app = _fresh_app(monkeypatch, tmp_path)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            bad = _row("down")
            bad["bogus_field"] = "nope"
            resp = await client.post("/api/v1/feedback", json=bad)
            assert resp.status_code == 422, (
                f"expected 422 for extra field, got {resp.status_code}"
            )
