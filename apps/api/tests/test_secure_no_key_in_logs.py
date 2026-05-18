"""API-04 / SECURE-04 canonical disclosure regression.

BYOK keys NEVER appear in logs, SQLite, settings.json, or
routing_decisions.jsonl. Defense-in-depth gate on top of Phase 2's
``RedactionFilter`` (installed at ``apps/api/__init__.py`` import
time) and Wave 3's handler discipline (``logger =
logging.getLogger(__name__)``).

Four sub-tests, each isolating one disclosure surface:

    test_secure_no_key_in_logs_after_patch_settings
        THE CANONICAL TEST. Capture ALL log records at DEBUG level
        across the entire lifespan + PATCH request. Submit a
        realistic-shape ``sk-or-v1-XXXX…`` key. Assert ZERO matches
        in the captured log text. Then scan EVERY string column in
        threads / messages / routing_decisions / schema_meta for the
        key shape (ZERO matches). Then read ``SETTINGS_PATH`` and
        ``JSONL_LOG_PATH`` and assert the same — keys NEVER land on
        disk.

    test_secure_no_key_in_logs_after_turn_via_keystore
        Different shape: ``sk-or-v1-TURNKEY…``. Set the key directly
        in the KeyStore, then POST a turn via FakeStreamingAdapter
        (the real adapter would refuse a fake key). Run the same
        4-surface scan. The turn handler writes to SQLite via
        persist_turn — confirms the routing-decision row, content
        blocks, and message rows never carry the key.

    test_secure_no_anthropic_key_in_logs
        Anthropic shape ``sk-ant-XXXX…``. The RedactionFilter has a
        dedicated ``***REDACTED-ANTHROPIC***`` pattern; this test
        asserts it catches the key on the PATCH boundary.

    test_secure_no_bearer_token_in_logs
        ``Authorization: Bearer sk-or-v1-…`` shape. The filter's
        Bearer pattern (ordered FIRST in SECRET_PATTERNS) rewrites
        the whole unit as ``Bearer ***REDACTED***`` — protecting
        proxy-header-style log lines (CR-05 carry-forward).

All tests use ``httpx.AsyncClient + ASGITransport`` (API-08 / D-20).
The DB + settings + jsonl files land in ``tmp_path`` via the
``PROMPT_OPTIMIZER_HOME`` env override + ``importlib.reload`` chain.

Cross-refs:
    - 03-CONTEXT.md D-19 (SECURE-04 regression scope)
    - 03-CONTEXT.md D-11 (settings.json never carries keys)
    - 03-VALIDATION.md row 3-06-01 line 63 (test expectation)
    - .planning/REQUIREMENTS.md API-04 (keys held in-process only)
    - apps/api/backends/logging_filter.py (SECRET_PATTERNS source)
    - apps/api/backends/tests/test_logging_filter.py (Phase 2 unit
      regression this end-to-end test extends)
"""

from __future__ import annotations

import importlib
import logging
import typing

import httpx
import pytest
from httpx import ASGITransport


# Realistic-shape key bodies. Each is 28 chars total (provider prefix +
# ≥20 alphanumeric body — matches the RedactionFilter alphabet
# constraints) so the regex patterns in
# ``apps.api.backends.logging_filter.SECRET_PATTERNS`` would fire if
# the value ever flowed through ``logging.getLogger().info(...)``.
OPENROUTER_KEY = "sk-or-v1-XXXXXXXXXXXXXXXXXXXX"
OPENROUTER_KEY_PREFIX = "sk-or-v1"
TURN_KEY = "sk-or-v1-TURNKEYAAAAAAAAAAAA"
ANTHROPIC_KEY = "sk-ant-XXXXXXXXXXXXXXXXXXXX"
ANTHROPIC_KEY_PREFIX = "sk-ant"
BEARER_KEY = "sk-or-v1-BEARERAAAAAAAAAAAAAA"


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _fresh_app(monkeypatch: pytest.MonkeyPatch, tmp_path) -> typing.Any:
    """Reload ``apps.api.paths`` under ``tmp_path`` and build a fresh app.

    The reload chain matches the other Wave 6 helpers: every module
    that caches a ``PROMPT_OPTIMIZER_HOME``-derived path constant gets
    reloaded in dependency order so SETTINGS_PATH and JSONL_LOG_PATH
    point inside ``tmp_path`` for the duration of the test.
    """

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("PROMPT_OPTIMIZER_HOME", str(tmp_path))
    import apps.api.paths

    importlib.reload(apps.api.paths)
    import apps.api.settings

    importlib.reload(apps.api.settings)
    import apps.api.jsonl_log

    importlib.reload(apps.api.jsonl_log)
    import apps.api.routes.settings as routes_settings_mod

    importlib.reload(routes_settings_mod)
    import apps.api.routes.rename

    importlib.reload(apps.api.routes.rename)
    import apps.api.routes.turn

    importlib.reload(apps.api.routes.turn)
    import apps.api.lifespan

    importlib.reload(apps.api.lifespan)
    import apps.api.main

    importlib.reload(apps.api.main)
    return apps.api.main.create_app()


async def _scan_db_for_substring(db, needle: str) -> list[tuple[str, str, str]]:
    """Walk EVERY text column in threads / messages / routing_decisions
    / schema_meta and return any (table, column, value) hit where
    ``needle`` is a substring of the value.

    Returns an empty list when the key shape is absent everywhere —
    the success condition for the SECURE-04 regression. Any non-empty
    return value is the API-04 leak we are looking for.
    """

    hits: list[tuple[str, str, str]] = []

    # threads — text columns: id, title, created_at, updated_at
    async with db.execute(
        "SELECT id, title, created_at, updated_at FROM threads"
    ) as cur:
        async for row in cur:
            for col_name, val in zip(
                ("id", "title", "created_at", "updated_at"), row
            ):
                if isinstance(val, str) and needle in val:
                    hits.append(("threads", col_name, val))

    # messages — text columns: id, thread_id, role, content_blocks,
    # text, backend_used, model_used, created_at, status
    async with db.execute(
        "SELECT id, thread_id, role, content_blocks, text,"
        " backend_used, model_used, created_at, status FROM messages"
    ) as cur:
        async for row in cur:
            for col_name, val in zip(
                (
                    "id",
                    "thread_id",
                    "role",
                    "content_blocks",
                    "text",
                    "backend_used",
                    "model_used",
                    "created_at",
                    "status",
                ),
                row,
            ):
                if isinstance(val, str) and needle in val:
                    hits.append(("messages", col_name, val))

    # routing_decisions — text columns: id, message_id, task_type,
    # agentic_intent, predicted_model, rationale, signals, decided_at
    async with db.execute(
        "SELECT id, message_id, task_type, agentic_intent,"
        " predicted_model, rationale, signals, decided_at"
        " FROM routing_decisions"
    ) as cur:
        async for row in cur:
            for col_name, val in zip(
                (
                    "id",
                    "message_id",
                    "task_type",
                    "agentic_intent",
                    "predicted_model",
                    "rationale",
                    "signals",
                    "decided_at",
                ),
                row,
            ):
                if isinstance(val, str) and needle in val:
                    hits.append(("routing_decisions", col_name, val))

    # schema_meta — text columns: (only version is INTEGER but defensive)
    async with db.execute("SELECT * FROM schema_meta") as cur:
        async for row in cur:
            for idx, val in enumerate(row):
                if isinstance(val, str) and needle in val:
                    hits.append(("schema_meta", f"col{idx}", val))

    return hits


# ---------------------------------------------------------------------
# Test 1 — CANONICAL: PATCH /settings carries a key; nothing leaks
# ---------------------------------------------------------------------


async def test_secure_no_key_in_logs_after_patch_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path, caplog
) -> None:
    """The CANONICAL API-04 regression.

    1. Capture all DEBUG-level log records via caplog.
    2. PATCH the settings endpoint with a realistic openrouter key.
    3. Assert the key (full + prefix-only) does NOT appear in
       caplog.text.
    4. Scan threads / messages / routing_decisions / schema_meta
       for the key shape; ZERO matches.
    5. Read ``SETTINGS_PATH``; the key shape MUST NOT appear (D-11:
       keys never enter settings.json).
    6. Read ``JSONL_LOG_PATH`` if it exists; same scan.
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)

    with caplog.at_level(logging.DEBUG):
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                resp = await client.patch(
                    "/api/v1/settings",
                    json={"keys": {"openrouter": OPENROUTER_KEY}},
                )

            # 1. Status check.
            assert resp.status_code == 200, (
                f"PATCH /settings failed: {resp.status_code} {resp.text}"
            )

            # 2. caplog scan — full key AND prefix-only.
            assert OPENROUTER_KEY not in caplog.text, (
                "API-04 BREACH: openrouter key appears in captured "
                f"logs: {caplog.text!r}"
            )
            # Defense in depth: even the provider prefix should be
            # redacted because the filter rewrites any sk-[A-Za-z0-9_-]{20,}
            # substring as ***REDACTED-OPENAI*** — leaving the prefix
            # alone would smuggle 8 chars of recognisable secret.
            assert OPENROUTER_KEY_PREFIX not in caplog.text, (
                "API-04 BREACH (prefix): the sk-or-v1 prefix should "
                f"be redacted; got {caplog.text!r}"
            )

            # 3. DB scan via shared connection.
            hits = await _scan_db_for_substring(
                app.state.db, OPENROUTER_KEY_PREFIX
            )
            assert hits == [], (
                f"API-04 BREACH: openrouter key prefix found in DB: {hits!r}"
            )

            # 4. settings.json file scan (D-11 explicit).
            import apps.api.paths

            if apps.api.paths.SETTINGS_PATH.exists():
                content = apps.api.paths.SETTINGS_PATH.read_text(
                    encoding="utf-8"
                )
                assert OPENROUTER_KEY_PREFIX not in content, (
                    f"D-11 BREACH: key prefix in settings.json: {content!r}"
                )

            # 5. routing_decisions.jsonl scan (STORE-06).
            if apps.api.paths.JSONL_LOG_PATH.exists():
                jsonl_content = apps.api.paths.JSONL_LOG_PATH.read_text(
                    encoding="utf-8"
                )
                assert OPENROUTER_KEY_PREFIX not in jsonl_content, (
                    "STORE-06 BREACH: key prefix in jsonl: "
                    f"{jsonl_content!r}"
                )


# ---------------------------------------------------------------------
# Test 2 — turn via keystore: persist_turn path; nothing leaks to DB
# ---------------------------------------------------------------------


async def test_secure_no_key_in_logs_after_turn_via_keystore(
    monkeypatch: pytest.MonkeyPatch, tmp_path, caplog
) -> None:
    """Run a full POST /turn with a key in the keystore; nothing leaks.

    The turn handler writes to SQLite via ``persist_turn`` — the
    routing decision row, the assistant message's content_blocks
    JSON, and the message text columns all flow through. A
    well-shaped FakeStreamingAdapter takes the place of the real
    OpenRouterAdapter so we never contact the network.

    Confirms the key NEVER appears in:
      - caplog.text (RedactionFilter does its job)
      - the four DB tables (no handler writes the key to SQLite)
      - the jsonl log (D-05 row shape never includes key fields)
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)

    from apps.api.backends.chunks import Done, TextDelta
    from apps.api.tests.fake_adapter import FakeStreamingAdapter
    from src.routing.schema import RoutingDecision

    fake = FakeStreamingAdapter(
        [
            TextDelta(text="response"),
            Done(tokens_in=5, tokens_out=3, cost_usd=0.001, latency_ms=10),
        ]
    )

    def fake_decide(*args, **kwargs):
        return RoutingDecision(
            backend="openrouter",
            model_or_agent="openai/gpt-5",
            rationale="test",
            confidence=0.9,
            signals={"task_type": "chat"},
        )

    monkeypatch.setattr("apps.api.routes.turn.decide", fake_decide)

    with caplog.at_level(logging.DEBUG):
        async with app.router.lifespan_context(app):
            # Inject the key + the fake adapter BEFORE the request.
            app.state.keystore.set("openrouter", TURN_KEY)
            app.state.adapters = {"openrouter": fake}

            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                # Create a thread first.
                t_resp = await client.post(
                    "/api/v1/threads", json={"title": "turn-test"}
                )
                assert t_resp.status_code == 200
                thread_id = t_resp.json()["id"]

                # POST a turn — consume the SSE stream to completion.
                async with client.stream(
                    "POST",
                    f"/api/v1/threads/{thread_id}/turn",
                    json={"message": "hello"},
                ) as resp:
                    assert resp.status_code == 200
                    async for line in resp.aiter_lines():
                        if line.startswith("event: done"):
                            break

            # 1. caplog scan.
            assert TURN_KEY not in caplog.text, (
                f"API-04 BREACH (turn path): key in logs: {caplog.text!r}"
            )
            assert OPENROUTER_KEY_PREFIX not in caplog.text, (
                f"prefix leaked into turn logs: {caplog.text!r}"
            )

            # 2. DB scan — the prefix should not appear in any text
            # column across the four tables.
            hits = await _scan_db_for_substring(
                app.state.db, OPENROUTER_KEY_PREFIX
            )
            assert hits == [], (
                "API-04 BREACH (turn path): key prefix in DB: "
                f"{hits!r}"
            )

            # 3. JSONL scan — D-05 row shape never includes key fields.
            import apps.api.paths

            if apps.api.paths.JSONL_LOG_PATH.exists():
                jsonl_content = apps.api.paths.JSONL_LOG_PATH.read_text(
                    encoding="utf-8"
                )
                assert OPENROUTER_KEY_PREFIX not in jsonl_content, (
                    "STORE-06 BREACH (turn path): key prefix in jsonl: "
                    f"{jsonl_content!r}"
                )


# ---------------------------------------------------------------------
# Test 3 — Anthropic key shape; ***REDACTED-ANTHROPIC*** branch
# ---------------------------------------------------------------------


async def test_secure_no_anthropic_key_in_logs(
    monkeypatch: pytest.MonkeyPatch, tmp_path, caplog
) -> None:
    """The RedactionFilter's anthropic branch catches sk-ant-… keys.

    Pattern ordering in ``SECRET_PATTERNS`` puts ``sk-ant-…`` BEFORE
    ``sk-…`` so a key starting with ``sk-ant-`` is rewritten to
    ``***REDACTED-ANTHROPIC***`` (more specific) instead of
    ``***REDACTED-OPENAI***``. This test confirms the dedicated
    branch fires at the PATCH boundary just like the openrouter
    branch.
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)

    with caplog.at_level(logging.DEBUG):
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                resp = await client.patch(
                    "/api/v1/settings",
                    json={"keys": {"anthropic": ANTHROPIC_KEY}},
                )

            assert resp.status_code == 200, (
                f"PATCH failed: {resp.status_code} {resp.text}"
            )

            assert ANTHROPIC_KEY not in caplog.text, (
                "API-04 BREACH (anthropic): key in logs: "
                f"{caplog.text!r}"
            )
            assert ANTHROPIC_KEY_PREFIX not in caplog.text, (
                "API-04 BREACH (anthropic prefix): "
                f"{caplog.text!r}"
            )

            # DB scan — same surface.
            hits = await _scan_db_for_substring(
                app.state.db, ANTHROPIC_KEY_PREFIX
            )
            assert hits == [], (
                f"API-04 BREACH (anthropic DB): {hits!r}"
            )

            # settings.json scan — D-11 explicit.
            import apps.api.paths

            if apps.api.paths.SETTINGS_PATH.exists():
                content = apps.api.paths.SETTINGS_PATH.read_text(
                    encoding="utf-8"
                )
                assert ANTHROPIC_KEY_PREFIX not in content, (
                    "D-11 BREACH (anthropic settings.json): "
                    f"{content!r}"
                )


# ---------------------------------------------------------------------
# Test 4 — Bearer prefix: the filter's Bearer-FIRST rule fires
# ---------------------------------------------------------------------


async def test_secure_no_bearer_token_in_logs(
    monkeypatch: pytest.MonkeyPatch, tmp_path, caplog
) -> None:
    """A logged ``Authorization: Bearer <key>`` becomes ``Bearer ***REDACTED***``.

    SECRET_PATTERNS lists the Bearer rule FIRST so the entire header
    body is consumed as one redacted unit. Without this ordering, the
    ``sk-`` rule would fire on the body alone and leave the ``Bearer ``
    literal exposed — CR-05 carry-forward.

    We exercise the path manually because no production code path
    currently emits Bearer headers; the filter still needs the
    regression to stay green for the inevitable future contributor
    that logs a request header.
    """

    # Build the app so apps.api.__init__ runs and installs the
    # redaction filter on the root logger.
    _ = _fresh_app(monkeypatch, tmp_path)

    log = logging.getLogger("apps.api.tests.test_secure_no_key_in_logs")

    with caplog.at_level(logging.DEBUG):
        # The literal substring we are testing the filter against.
        log.info("Authorization: Bearer %s", BEARER_KEY)

    # The filter must have rewritten the captured text:
    assert BEARER_KEY not in caplog.text, (
        f"API-04 BREACH (Bearer): raw bearer in logs: {caplog.text!r}"
    )
    # And the canonical replacement string must be present:
    assert "Bearer ***REDACTED***" in caplog.text, (
        "Expected 'Bearer ***REDACTED***' replacement; "
        f"got {caplog.text!r}"
    )
