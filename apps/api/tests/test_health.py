"""Wave 2 health tests — lifespan startup, pragmas, healthz status dots.

Five async tests:

    test_artifacts_loaded_once        Monkeypatches
                                      ``apps.api.lifespan._load_default_artifacts``
                                      to a counter; asserts the
                                      counter is 1 after two requests
                                      (API-01 SC #1 — joblib loaded
                                      ONCE at lifespan; never reloaded).

    test_pragmas_applied              After lifespan runs, asserts
                                      ``PRAGMA foreign_keys=1``,
                                      ``PRAGMA busy_timeout=5000``,
                                      ``PRAGMA synchronous=1`` on
                                      ``app.state.db`` (STORE-01
                                      carry-forward via lifespan).

    test_healthz_returns_200_with_required_keys
                                      GET /api/v1/healthz returns 200
                                      with the D-18 payload keys.

    test_healthz_status_dots          With OPENROUTER_API_KEY set,
                                      Anthropic key + COMPUTER_USE_OPT_IN
                                      unset → openrouter ready,
                                      claude_code missing_key,
                                      computer_use opt_out, overall
                                      degraded (D-18).

    test_healthz_never_constructs_adapters
                                      Monkeypatch every adapter
                                      constructor to raise — healthz
                                      STILL returns 200 (D-18 anti-
                                      pattern guard).

All tests use ``httpx.AsyncClient + ASGITransport`` per API-08 / D-20.
The synchronous FastAPI test-client wrapper is FORBIDDEN here (the
negative-grep guard in test_smoke.py enforces).
Lifespan is triggered manually via FastAPI's
``app.router.lifespan_context(app)`` — without that, ASGITransport
does NOT run the lifespan (it only handles ``http.request`` events,
not ``lifespan.startup``).

The DB lands in ``tmp_path`` via the ``PROMPT_OPTIMIZER_HOME`` env
override + ``importlib.reload(apps.api.paths)`` so each test gets a
fresh filesystem location. The lifespan opens the DB, runs
migrations, and caches schema_version — exactly what the production
boot path does, just under a tmp dir.

Cross-refs:
    - 03-CONTEXT.md D-15 + D-18 (lifespan + healthz)
    - 03-RESEARCH.md §"Pattern 6" lines 457-515 (ASGITransport)
    - 03-VALIDATION.md rows 3-02-01 / 3-02-02 / 3-02-03 lines 50-52
    - apps/api/tests/test_smoke.py::test_no_testclient_imports... (CI guard)
"""

from __future__ import annotations

import importlib

import httpx
import pytest
from httpx import ASGITransport


# ---------------------------------------------------------------------
# Test helper — fresh app under tmp dir, lifespan-triggered.
# ---------------------------------------------------------------------


def _fresh_app(monkeypatch: pytest.MonkeyPatch, tmp_path) -> object:
    """Reload apps.api.paths under tmp_path and build a fresh app.

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
# Test 1 — artifacts loaded once (API-01 SC #1)
# ---------------------------------------------------------------------


async def test_artifacts_loaded_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Lifespan calls ``_load_default_artifacts`` exactly once.

    Monkeypatches the lifespan-local reference to a counter that
    returns the canonical 4-key sentinel dict. After two GET requests
    to ``/api/v1/healthz``, the counter must read 1 — confirming that
    the lifespan runs ONCE per app instance and subsequent requests
    reuse ``app.state.artifacts`` (API-01: "FastAPI process loads all
    joblib artifacts once at lifespan startup; never reloaded per
    request").
    """

    app = _fresh_app(monkeypatch, tmp_path)

    call_count = {"n": 0}

    def _counting_loader() -> dict:
        call_count["n"] += 1
        return {
            "task_type_classifier": {},
            "agentic_intent_classifier": {},
            "model_router": {},
            "model_mapping": {},
        }

    import apps.api.lifespan
    monkeypatch.setattr(
        apps.api.lifespan, "_load_default_artifacts", _counting_loader
    )

    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp1 = await client.get("/api/v1/healthz")
            resp2 = await client.get("/api/v1/healthz")

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert call_count["n"] == 1, (
        f"Expected artifacts loaded exactly once; got {call_count['n']}"
    )


# ---------------------------------------------------------------------
# Test 2 — pragmas applied via lifespan path (STORE-01 carry-forward)
# ---------------------------------------------------------------------


async def test_pragmas_applied(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """D-03 pragmas land on ``app.state.db`` after lifespan startup.

    Confirms ``foreign_keys=1``, ``busy_timeout=5000``,
    ``synchronous=1`` (NORMAL) on the lifespan-opened connection.
    ``journal_mode`` is relaxed because the production DB lives on
    disk (WAL mode); the lifespan-opened DB-on-disk should show WAL.
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            # Touch the app to ensure lifespan startup completed.
            resp = await client.get("/api/v1/healthz")
            assert resp.status_code == 200

            db = app.state.db
            async with db.execute("PRAGMA foreign_keys") as cur:
                fk = (await cur.fetchone())[0]
            async with db.execute("PRAGMA busy_timeout") as cur:
                busy = (await cur.fetchone())[0]
            async with db.execute("PRAGMA synchronous") as cur:
                sync = (await cur.fetchone())[0]

    assert fk == 1, f"Expected foreign_keys=1; got {fk}"
    assert busy == 5000, f"Expected busy_timeout=5000; got {busy}"
    # synchronous=NORMAL is value 1 in PRAGMA output
    assert sync == 1, f"Expected synchronous=NORMAL (1); got {sync}"


# ---------------------------------------------------------------------
# Test 3 — healthz returns 200 with the D-18 payload keys
# ---------------------------------------------------------------------


async def test_healthz_returns_200_with_required_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """GET /api/v1/healthz returns 200 and the D-18 payload shape."""

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/healthz")

    assert resp.status_code == 200
    body = resp.json()
    required_top = {
        "status",
        "artifacts_loaded",
        "db_ok",
        "schema_version",
        "adapters",
        "version",
    }
    assert required_top <= set(body.keys()), (
        f"Missing keys in healthz payload: {required_top - set(body.keys())}"
    )
    required_adapters = {"openrouter", "claude_code", "computer_use"}
    assert required_adapters <= set(body["adapters"].keys()), (
        f"Missing adapter entries: {required_adapters - set(body['adapters'].keys())}"
    )


# ---------------------------------------------------------------------
# Test 4 — per-adapter status dots (D-18 vocabulary)
# ---------------------------------------------------------------------


async def test_healthz_status_dots(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """D-18 closed-vocabulary status per backend.

    With:
      - OPENROUTER_API_KEY set
      - ANTHROPIC_API_KEY unset
      - COMPUTER_USE_OPT_IN unset

    Expect:
      - openrouter  -> ready
      - claude_code -> missing_key
      - computer_use -> opt_out
      - overall status -> degraded
    """

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("COMPUTER_USE_OPT_IN", raising=False)

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/healthz")

    assert resp.status_code == 200
    body = resp.json()
    assert body["adapters"]["openrouter"]["status"] == "ready"
    assert body["adapters"]["claude_code"]["status"] == "missing_key"
    assert body["adapters"]["computer_use"]["status"] == "opt_out"
    assert body["status"] == "degraded"


# ---------------------------------------------------------------------
# Test 5 — healthz never constructs an adapter (D-18 anti-pattern guard)
# ---------------------------------------------------------------------


async def test_healthz_never_constructs_adapters(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """D-18 — read-only precheck even when adapter constructors raise.

    Monkeypatches each adapter class constructor to raise
    ``RuntimeError``. The /healthz endpoint must STILL return 200
    because the precheck is read-only (KeyStore presence + env +
    settings — no constructor invocation).

    The monkeypatch is wrapped in try/except so future adapter
    relocations don't break the test — it skips that arm rather
    than failing on import.
    """

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("COMPUTER_USE_OPT_IN", "1")

    # Patch constructors to raise — if healthz were calling them, the
    # request would 500. We expect 200 because the precheck never
    # touches these classes.
    try:
        from apps.api.backends.openrouter.adapter import OpenRouterAdapter

        def _raise_or(*args, **kwargs):
            raise RuntimeError("Should not be called by healthz")

        monkeypatch.setattr(
            OpenRouterAdapter, "__init__", _raise_or
        )
    except ImportError:  # pragma: no cover
        pass
    try:
        from apps.api.backends.claude_code.adapter import ClaudeCodeAdapter

        def _raise_cc(*args, **kwargs):
            raise RuntimeError("Should not be called by healthz")

        monkeypatch.setattr(
            ClaudeCodeAdapter, "__init__", _raise_cc
        )
    except ImportError:  # pragma: no cover
        pass
    try:
        from apps.api.backends.computer_use.adapter import ComputerUseAdapter

        def _raise_cu(*args, **kwargs):
            raise RuntimeError("Should not be called by healthz")

        monkeypatch.setattr(
            ComputerUseAdapter, "__init__", _raise_cu
        )
    except ImportError:  # pragma: no cover
        pass

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/healthz")

    # The status_code is the only invariant we care about — if
    # healthz had touched any adapter constructor, the patched
    # RuntimeError would have surfaced as a 500.
    assert resp.status_code == 200, (
        f"Healthz returned {resp.status_code} when adapter constructors "
        f"were patched to raise — D-18 violated (healthz must be read-only)."
    )
