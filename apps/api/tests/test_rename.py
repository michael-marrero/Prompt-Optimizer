"""Wave 6 rename endpoint tests — POST /api/v1/threads/{id}/rename.

Eight async tests covering the full D-17 rename surface:

    test_rename_happy_path
        Monkeypatch OpenRouterAdapter to a FakeStreamingAdapter that
        emits ``[TextDelta("Brief"), TextDelta(" Title"), Done()]``.
        Assert 200 + ``{"title": "Brief Title"}`` and that the DB
        thread row's ``title`` is updated.

    test_rename_tiktoken_cap_returns_413
        POST with a body exceeding 1500 tokens. Track that
        ``OpenRouterAdapter`` was NEVER instantiated (cost-overrun
        defense fires BEFORE the API call). Assert 413.

    test_rename_truncates_to_60_chars
        Monkeypatch OpenRouterAdapter to a FakeStreamingAdapter that
        emits ``[TextDelta("X" * 100), Done()]``. Assert the response
        title length is ≤60 chars.

    test_rename_bypasses_decide
        Monkeypatch ``src.routing.decide.decide`` to raise. Rename
        STILL succeeds (proves UI-14 explicit: rename never calls the
        routing brain).

    test_rename_uses_fresh_adapter_not_cached
        Pre-populate ``app.state.adapters = {"openrouter": <SENTINEL>}``.
        POST a rename. Assert the SENTINEL is STILL the entry after
        the rename returns (D-17: rename built its own fresh adapter
        and never touched the cache).

    test_rename_thread_not_found_returns_404
        POST against a non-existent thread id. Assert 404 BEFORE any
        OpenRouter call.

    test_rename_strips_quotes_from_title
        FakeStreamingAdapter emits ``[TextDelta('"Quoted Title"'),
        Done()]``. Assert the response title is ``Quoted Title``
        (leading/trailing ASCII quotes stripped).

    test_rename_returns_400_when_openrouter_key_missing
        With the KeyStore empty (and OPENROUTER_API_KEY env var
        unset), POST a rename. Assert 400 + ``OPENROUTER_API_KEY``
        in detail. Assert the OpenRouterAdapter class was NEVER
        instantiated (the pre-check fires BEFORE the constructor;
        the typed AuthenticationError never bubbles up as an opaque
        500).

All tests use ``httpx.AsyncClient + ASGITransport`` (API-08 / D-20).
Synchronous FastAPI test-client is FORBIDDEN — the negative-grep
guard in ``test_smoke.py`` enforces this.

The DB and settings land in ``tmp_path`` via the
``PROMPT_OPTIMIZER_HOME`` env override + ``importlib.reload`` chain so
every test gets an isolated filesystem location.

Cross-refs:
    - 03-CONTEXT.md D-17 (rename endpoint contract)
    - 03-CONTEXT.md UI-14 (rename bypasses the brain)
    - 03-VALIDATION.md row 3-06-02 line 64 (rename test expectation)
    - apps/api/routes/rename.py (the endpoint under test)
    - apps/api/tests/test_settings.py (_fresh_app reload chain shape
      this file mirrors)
"""

from __future__ import annotations

import importlib
import typing

import httpx
import pytest
from httpx import ASGITransport


# ---------------------------------------------------------------------
# Test helper — fresh app under tmp dir, lifespan-triggered.
# Mirrors test_settings.py:_fresh_app so the Wave 2 lifespan handles
# DB open + settings load + KeyStore + empty adapter registry exactly
# as production does.
# ---------------------------------------------------------------------


def _fresh_app(monkeypatch: pytest.MonkeyPatch, tmp_path) -> typing.Any:
    """Reload ``apps.api.paths`` under ``tmp_path`` and build a fresh app.

    Unsets ``OPENROUTER_API_KEY`` / ``ANTHROPIC_API_KEY`` so the
    KeyStore env-fallback cannot mask the in-memory cache changes
    these tests make. Reloads the path-dependent modules in
    dependency order so the rename route's logger / SETTINGS_PATH
    references are bound to the test's tmp dir.
    """

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("PROMPT_OPTIMIZER_HOME", str(tmp_path))
    import apps.api.paths

    importlib.reload(apps.api.paths)
    import apps.api.settings

    importlib.reload(apps.api.settings)
    import apps.api.routes.rename

    importlib.reload(apps.api.routes.rename)
    import apps.api.lifespan

    importlib.reload(apps.api.lifespan)
    import apps.api.main

    importlib.reload(apps.api.main)
    return apps.api.main.create_app()


async def _create_thread(client, title: str = "untitled") -> str:
    """POST /threads and return the new thread id."""

    resp = await client.post("/api/v1/threads", json={"title": title})
    assert resp.status_code == 200, (
        f"thread create failed: {resp.status_code} {resp.text}"
    )
    return resp.json()["id"]


# ---------------------------------------------------------------------
# Test 1 — happy path: TextDelta accumulator + DB persist
# ---------------------------------------------------------------------


async def test_rename_happy_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """POST /rename returns the accumulated title + persists to DB.

    Monkeypatches the rename module's ``OpenRouterAdapter`` symbol to
    a callable returning a ``FakeStreamingAdapter`` that emits a
    fixed 2-TextDelta + Done sequence. Asserts the response body has
    ``{"title": "Brief Title"}`` AND the thread row's title is
    updated in SQLite.
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)

    from apps.api.backends.chunks import Done, TextDelta
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    fake_chunks = [
        TextDelta(text="Brief"),
        TextDelta(text=" Title"),
        Done(),
    ]

    def make_fake_adapter(**kwargs):
        return FakeStreamingAdapter(fake_chunks)

    monkeypatch.setattr(
        "apps.api.routes.rename.OpenRouterAdapter", make_fake_adapter
    )

    async with app.router.lifespan_context(app):
        # Populate the keystore so the pre-check passes. The fake
        # adapter ignores the key entirely.
        app.state.keystore.set("openrouter", "sk-or-v1-FAKE0000000000000000")

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            resp = await client.post(
                f"/api/v1/threads/{thread_id}/rename",
                json={"first_user_message": "build me a finance app"},
            )

        assert resp.status_code == 200, (
            f"expected 200; got {resp.status_code}: {resp.text}"
        )
        body = resp.json()
        assert body == {"title": "Brief Title"}, (
            f"expected title 'Brief Title'; got {body!r}"
        )

        # DB scan: thread row title should be updated.
        async with app.state.db.execute(
            "SELECT title FROM threads WHERE id = ?", (thread_id,)
        ) as cur:
            row = await cur.fetchone()
        assert row is not None, "thread row missing after rename"
        assert row[0] == "Brief Title", (
            f"DB title was {row[0]!r}; expected 'Brief Title'"
        )


# ---------------------------------------------------------------------
# Test 2 — tiktoken pre-flight cap returns 413 BEFORE adapter ctor
# ---------------------------------------------------------------------


async def test_rename_tiktoken_cap_returns_413(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Oversized first_user_message returns 413 + never builds adapter.

    The body is ``"lorem ipsum " * 1500`` which encodes to ~3000+
    tokens (well over the 1500 cap). A counter on the
    OpenRouterAdapter class asserts construction was NEVER attempted
    (cost-overrun defense fires BEFORE the API call).
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)

    construction_count = {"n": 0}

    def assert_never_called(**kwargs):
        construction_count["n"] += 1
        raise AssertionError(
            "OpenRouterAdapter must not be constructed when "
            "tiktoken cap trips"
        )

    monkeypatch.setattr(
        "apps.api.routes.rename.OpenRouterAdapter", assert_never_called
    )

    async with app.router.lifespan_context(app):
        app.state.keystore.set("openrouter", "sk-or-v1-FAKE0000000000000000")

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            resp = await client.post(
                f"/api/v1/threads/{thread_id}/rename",
                json={"first_user_message": "lorem ipsum " * 1500},
            )

    assert resp.status_code == 413, (
        f"expected 413 for oversized body; got {resp.status_code}: {resp.text}"
    )
    detail = resp.json()["detail"]
    assert "too long" in detail.lower(), (
        f"expected 'too long' in detail; got {detail!r}"
    )
    assert construction_count["n"] == 0, (
        "OpenRouterAdapter was constructed despite tiktoken cap trip"
    )


# ---------------------------------------------------------------------
# Test 3 — title truncated to ≤60 chars
# ---------------------------------------------------------------------


async def test_rename_truncates_to_60_chars(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A model output >60 chars is trimmed to exactly 60 in response.

    FakeStreamingAdapter emits ``[TextDelta("X" * 200), Done()]``.
    Trim logic in the endpoint caps to 60 regardless of what the
    model returned. This protects the Phase 5 UI from layout breaks.
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)

    from apps.api.backends.chunks import Done, TextDelta
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    def make_fake_adapter(**kwargs):
        return FakeStreamingAdapter([TextDelta(text="X" * 200), Done()])

    monkeypatch.setattr(
        "apps.api.routes.rename.OpenRouterAdapter", make_fake_adapter
    )

    async with app.router.lifespan_context(app):
        app.state.keystore.set("openrouter", "sk-or-v1-FAKE0000000000000000")

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            resp = await client.post(
                f"/api/v1/threads/{thread_id}/rename",
                json={"first_user_message": "build me an app"},
            )

    assert resp.status_code == 200
    title = resp.json()["title"]
    assert len(title) <= 60, (
        f"title length {len(title)} exceeds 60 char cap; got {title!r}"
    )
    # The model output was 200 X's so we expect exactly 60 X's after
    # the trim (no whitespace / quotes to strip from the all-X input).
    assert title == "X" * 60, (
        f"expected 60 X's after trim; got {title!r}"
    )


# ---------------------------------------------------------------------
# Test 4 — rename bypasses the routing brain (UI-14 explicit)
# ---------------------------------------------------------------------


async def test_rename_bypasses_decide(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Monkeypatching the brain to raise still leaves rename happy.

    Sets ``src.routing.decide.decide`` to a function that raises
    RuntimeError. Rename should NEVER invoke it (UI-14 explicit).
    The test passes iff rename returns 200 — proving the bypass.
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)

    from apps.api.backends.chunks import Done, TextDelta
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    def raise_decide(*args, **kwargs):
        raise RuntimeError(
            "the routing brain MUST NOT be called from rename (UI-14)"
        )

    monkeypatch.setattr("src.routing.decide.decide", raise_decide)

    def make_fake_adapter(**kwargs):
        return FakeStreamingAdapter([TextDelta(text="Hello"), Done()])

    monkeypatch.setattr(
        "apps.api.routes.rename.OpenRouterAdapter", make_fake_adapter
    )

    async with app.router.lifespan_context(app):
        app.state.keystore.set("openrouter", "sk-or-v1-FAKE0000000000000000")

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            resp = await client.post(
                f"/api/v1/threads/{thread_id}/rename",
                json={"first_user_message": "hi"},
            )

    assert resp.status_code == 200, (
        f"rename failed when the routing brain was mocked to raise: "
        f"{resp.status_code} {resp.text}"
    )
    assert resp.json()["title"] == "Hello"


# ---------------------------------------------------------------------
# Test 5 — rename uses a FRESH adapter; never touches the cache
# ---------------------------------------------------------------------


async def test_rename_uses_fresh_adapter_not_cached(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A sentinel pre-populated in app.state.adapters survives rename.

    D-17 explicit: rename builds its own OpenRouterAdapter inline and
    never reads from / writes to ``app.state.adapters``. We seed the
    registry with an arbitrary sentinel object and assert it stays
    bound after the rename returns.
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)

    from apps.api.backends.chunks import Done, TextDelta
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    sentinel = object()

    def make_fake_adapter(**kwargs):
        return FakeStreamingAdapter([TextDelta(text="ok"), Done()])

    monkeypatch.setattr(
        "apps.api.routes.rename.OpenRouterAdapter", make_fake_adapter
    )

    async with app.router.lifespan_context(app):
        app.state.keystore.set("openrouter", "sk-or-v1-FAKE0000000000000000")
        app.state.adapters["openrouter"] = sentinel

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            resp = await client.post(
                f"/api/v1/threads/{thread_id}/rename",
                json={"first_user_message": "hi"},
            )

        # The cache entry must STILL be the sentinel — rename never
        # touched it (D-17).
        assert app.state.adapters.get("openrouter") is sentinel, (
            "rename mutated the adapter cache; D-17 requires a fresh "
            "per-request adapter and an untouched cache"
        )

    assert resp.status_code == 200


# ---------------------------------------------------------------------
# Test 6 — 404 for unknown thread; adapter never built
# ---------------------------------------------------------------------


async def test_rename_thread_not_found_returns_404(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """POST against a non-existent thread returns 404; no adapter call.

    The 404 fires in the pre-stream sanity step BEFORE the tiktoken
    cap and BEFORE the adapter constructor.
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)

    def assert_never_called(**kwargs):
        raise AssertionError(
            "OpenRouterAdapter must not be constructed for unknown thread"
        )

    monkeypatch.setattr(
        "apps.api.routes.rename.OpenRouterAdapter", assert_never_called
    )

    async with app.router.lifespan_context(app):
        app.state.keystore.set("openrouter", "sk-or-v1-FAKE0000000000000000")

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/threads/does-not-exist/rename",
                json={"first_user_message": "anything"},
            )

    assert resp.status_code == 404, (
        f"expected 404; got {resp.status_code}: {resp.text}"
    )
    assert "thread not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------
# Test 7 — leading/trailing quotes stripped from the model output
# ---------------------------------------------------------------------


async def test_rename_strips_quotes_from_title(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A model output of '"Quoted Title"' yields 'Quoted Title'.

    Despite the system prompt's "no quotes" instruction, models often
    emit quoted strings. The trim step strips a single leading and
    trailing ASCII double-quote OR single-quote so the response is
    UI-friendly.
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)

    from apps.api.backends.chunks import Done, TextDelta
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    def make_fake_adapter(**kwargs):
        return FakeStreamingAdapter(
            [TextDelta(text='"Quoted Title"'), Done()]
        )

    monkeypatch.setattr(
        "apps.api.routes.rename.OpenRouterAdapter", make_fake_adapter
    )

    async with app.router.lifespan_context(app):
        app.state.keystore.set("openrouter", "sk-or-v1-FAKE0000000000000000")

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            resp = await client.post(
                f"/api/v1/threads/{thread_id}/rename",
                json={"first_user_message": "hi"},
            )

    assert resp.status_code == 200
    assert resp.json()["title"] == "Quoted Title", (
        f"expected unquoted title; got {resp.json()['title']!r}"
    )


# ---------------------------------------------------------------------
# Test 8 — 400 when OPENROUTER_API_KEY missing (WARNING-fix carry-forward)
# ---------------------------------------------------------------------


async def test_rename_returns_400_when_openrouter_key_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Empty KeyStore → 400 with OPENROUTER_API_KEY in detail.

    The pre-check fires BEFORE the OpenRouterAdapter constructor so
    the typed ``openai.AuthenticationError`` never bubbles up as an
    opaque 500. The user sees a clean 400 with a remediation hint.
    A counter on the adapter class confirms it was never constructed.
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)

    construction_count = {"n": 0}

    def assert_never_called(**kwargs):
        construction_count["n"] += 1
        raise AssertionError(
            "OpenRouterAdapter must not be constructed when the key is missing"
        )

    monkeypatch.setattr(
        "apps.api.routes.rename.OpenRouterAdapter", assert_never_called
    )

    async with app.router.lifespan_context(app):
        # Pre-condition: keystore is empty (the _fresh_app helper
        # already unset the env var so the env-fallback cannot mask).
        assert app.state.keystore.get("openrouter") is None, (
            "pre-condition: keystore should be empty"
        )

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)
            resp = await client.post(
                f"/api/v1/threads/{thread_id}/rename",
                json={"first_user_message": "anything"},
            )

    assert resp.status_code == 400, (
        f"expected 400 when key missing; got {resp.status_code}: {resp.text}"
    )
    detail = resp.json()["detail"]
    assert "OPENROUTER_API_KEY" in detail, (
        f"expected OPENROUTER_API_KEY in detail; got {detail!r}"
    )
    assert construction_count["n"] == 0, (
        "OpenRouterAdapter was constructed despite missing key pre-check"
    )
