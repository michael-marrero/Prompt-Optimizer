"""Shared pytest fixtures for the Phase 3 FastAPI / storage suite.

This conftest authors three core fixtures that Waves 1-6 reuse:

    aiosqlite_inmemory_db   async, function-scoped — opens
                            ``aiosqlite.connect(":memory:")``, applies
                            every migration via ``up_to_latest``, and
                            yields the connection. Closes on teardown.
                            Function-scoped (NOT session) per Pitfall 2:
                            multiple connections to ``":memory:"`` are
                            separate DBs, but a SINGLE connection per
                            test is correct.

    asgi_client             async context-manager fixture — yields
                            ``httpx.AsyncClient(transport=
                            httpx.ASGITransport(app=app),
                            base_url="http://test")``. **API-08 /
                            D-20:** NEVER uses
                            ``fastapi.testclient.TestClient``; the
                            negative-grep guard in CI enforces this.

    app_factory             synchronous factory fixture — returns a
                            callable
                            ``factory(adapters_override=None,
                            settings_override=None,
                            keystore_override=None) -> FastAPI`` that
                            builds a fresh app and pre-populates
                            ``app.state`` with the overrides BEFORE
                            startup so the lifespan honors them.

**B3 lazy-import pattern (Phase 2 Plan 00 carry-forward).** Every
producer module from Wave 1-6 is imported INSIDE the fixture body,
wrapped in ``try: ... except ImportError: pytest.skip(...)`` so this
conftest is collectable in Wave 0 BEFORE any of:

    - ``apps.api.main:create_app`` (Wave 2)
    - ``apps.api.lifespan`` (Wave 2)
    - ``apps.api.db.connect.open_db`` (Wave 1)
    - ``apps.api.db.migrate.up_to_latest`` (Wave 1)

… exist on disk. The B3 fix matches Phase 2 P00's
``adapter_factory`` fixture (``apps/api/backends/tests/conftest.py``
lines 319-375) which lazy-loads the OpenRouter / Claude Code /
computer-use adapter classes inside the factory body.

Cross-refs:
    - 03-RESEARCH.md §"Pattern 4" lines 364-383 (in-memory DB rationale)
    - 03-RESEARCH.md §"Pattern 6" lines 457-515 (ASGITransport pattern)
    - 03-PATTERNS.md §"Excerpt 7" lines 394-412 (B3 lazy import)
    - 03-VALIDATION.md §"Wave 0 Requirements" lines 69-79
    - 02-PLAN-00 Task 3 lines 319-375 (B3 fix source)
"""

from __future__ import annotations

import os
from typing import Any

import aiosqlite
import httpx
import pytest

from apps.api.backends.keystore import KeyStore

# Path to the repo root. Same shape as
# ``apps/api/backends/tests/conftest.py`` line 28-29:
# ``<repo>/apps/api/tests/conftest.py`` is FOUR ``..`` away from the
# repo root.
REPO_ROOT = os.path.abspath(os.path.join(__file__, "..", "..", "..", ".."))


# --------------------------------------------------------------------
# Fixture 1: aiosqlite_inmemory_db
# --------------------------------------------------------------------


@pytest.fixture
async def aiosqlite_inmemory_db():
    """Yield an ``aiosqlite.Connection`` to ``":memory:"`` with all
    migrations applied.

    Function-scoped (Pitfall 2): every test gets a fresh DB so state
    from one test never leaks to the next. ``open_db`` applies the
    canonical pragmas (WAL, busy_timeout=5000, foreign_keys=ON,
    synchronous=NORMAL); ``up_to_latest`` runs every numbered
    migration in order.

    LAZY-import producer modules per B3: if Wave 1 hasn't authored
    ``apps.api.db.connect`` / ``apps.api.db.migrate`` yet, the fixture
    skips the test rather than raising at collection time.
    """

    try:
        from apps.api.db.connect import open_db  # type: ignore[import-not-found]
    except ImportError:
        pytest.skip("Wave 1 apps.api.db.connect not yet implemented")
    try:
        from apps.api.db.migrate import up_to_latest  # type: ignore[import-not-found]
    except ImportError:
        pytest.skip("Wave 1 apps.api.db.migrate not yet implemented")

    # ``open_db`` accepts a path-or-URI; ``:memory:`` is the canonical
    # in-memory marker. The Wave 1 implementation will route this to
    # ``aiosqlite.connect(":memory:")`` under the hood and apply the
    # D-03 pragmas before returning.
    conn = await open_db(":memory:")
    try:
        await up_to_latest(conn)
        yield conn
    finally:
        try:
            await conn.close()
        except Exception:
            # Closing an already-closed aiosqlite connection raises;
            # the fixture only needs to attempt the close, not succeed.
            pass


# --------------------------------------------------------------------
# Fixture 2: asgi_client
# --------------------------------------------------------------------


@pytest.fixture
async def asgi_client(request):
    """Yield an ``httpx.AsyncClient`` wired to the test app via
    ``httpx.ASGITransport``.

    Usage from a test:

        async def test_x(app_factory, asgi_client):
            app = app_factory()
            async with asgi_client(app) as client:
                resp = await client.get("/api/v1/healthz")

    The returned callable takes a FastAPI ``app`` and returns an
    ``async with`` context manager. Tests MUST consume the response
    stream to completion before exiting the context (Pitfall 4 in
    RESEARCH §"Pattern 6") — otherwise ``ASGITransport`` may leave
    the server task in an indeterminate state.

    **API-08 / D-20:** This fixture deliberately uses
    ``httpx.AsyncClient + httpx.ASGITransport``. NEVER
    ``fastapi.testclient.TestClient`` — the negative-grep guard in CI
    blocks ``from fastapi.testclient`` anywhere under
    ``apps/api/tests/``.
    """

    def _factory(app: Any) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        )

    return _factory


# --------------------------------------------------------------------
# Fixture 3: app_factory
# --------------------------------------------------------------------


@pytest.fixture
def app_factory():
    """Return a factory callable that builds a fresh FastAPI app.

    The factory honors three overrides that bypass real lifespan
    side effects (joblib artifact load, settings file read, etc.):

        adapters_override   dict[str, BackendAdapter] | None
        settings_override   dict[str, Any]            | None
        keystore_override   KeyStore                  | None

    LAZY-import ``apps.api.main:create_app`` per B3: if Wave 2
    hasn't authored ``main.py`` yet, the factory skips the test.

    The factory assigns the overrides to ``app.state.*`` BEFORE the
    lifespan runs so the lifespan honors them instead of computing
    fresh values. Concretely, the Wave 2 lifespan will check
    ``getattr(app.state, "adapters", None)`` first and only build
    fresh adapter instances when the attribute is missing.
    """

    def _factory(
        adapters_override: dict[str, Any] | None = None,
        settings_override: dict[str, Any] | None = None,
        keystore_override: KeyStore | None = None,
    ) -> Any:
        try:
            from apps.api.main import create_app  # type: ignore[import-not-found]
        except ImportError:
            pytest.skip("Wave 2 apps.api.main:create_app not yet implemented")

        app = create_app()
        # Stash the overrides on app.state BEFORE the lifespan runs.
        # The Wave 2 lifespan inspects these attributes and skips its
        # default initialisation when an override is present.
        app.state.adapters = adapters_override or {}
        app.state.settings = settings_override or {
            "default_max_cost_usd": 0.50,
            "computer_use_opt_in": False,
        }
        app.state.keystore = keystore_override or KeyStore()
        return app

    return _factory


# --------------------------------------------------------------------
# Helper marker re-export — aiosqlite import-time check
#
# Keep ``aiosqlite`` as a real module-level import so collection
# errors surface immediately when the dep is missing. This is the
# ONLY producer-module import allowed at module level; everything
# else MUST be inside a fixture body wrapped in try/except.
# --------------------------------------------------------------------

__all__ = ["aiosqlite_inmemory_db", "asgi_client", "app_factory"]

# Reference ``aiosqlite`` once so the import isn't pruned by linters
# even if no fixture currently uses the symbol directly. The Wave 1
# ``open_db`` returns an ``aiosqlite.Connection`` so type-checkers
# benefit from this import being present.
_ = aiosqlite.connect
