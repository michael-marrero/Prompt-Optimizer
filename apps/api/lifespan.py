"""FastAPI lifespan — D-15 + discretion line 178 startup order.

Public surface (D-15, D-18):

    lifespan(app)   @asynccontextmanager — opens DB → migrates → loads
                    joblib artifacts → loads settings → instantiates
                    KeyStore → empty adapter registry → caches
                    ``schema_version``; on teardown closes the DB
                    defensively.

The lifespan runs ONCE per process at app startup (and teardown at
shutdown). It populates ``app.state`` with the following attributes
the Wave 3-6 route handlers consume:

    app.state.db              aiosqlite.Connection  — single shared DB
                              connection (Open Question 3 resolved as
                              "shared connection")
    app.state.artifacts       dict — Phase 1 4-key canonical dict
                              ({task_type_classifier,
                              agentic_intent_classifier, model_router,
                              model_mapping}) loaded via Phase 1's
                              ``_load_default_artifacts``
    app.state.settings        dict — non-key settings from settings.json
                              (D-11)
    app.state.keystore        KeyStore — in-memory primary; optional
                              keyring (Phase 2 D-10)
    app.state.adapters        dict — EMPTY at startup; lazy-built at
                              first turn (D-15). PATCH /settings
                              clears it; next turn rebuilds with
                              fresh KeyStore values.
    app.state.schema_version  int — cached at startup, never re-read
                              (Open Question 5 resolved)

**Phase 2 fixture compatibility (B3 lazy override pattern):** The
conftest's ``app_factory`` fixture pre-populates
``app.state.adapters``, ``settings``, and ``keystore`` BEFORE this
lifespan runs. We detect those pre-set attributes via
``getattr(app.state, attr, _SENTINEL)`` and SKIP the default
initialisation for that attribute so test overrides win. The default
``app.state.db``, ``app.state.artifacts``, and
``app.state.schema_version`` paths still run (they need real DB +
artifact loads even in tests; tests can monkeypatch
``_load_default_artifacts`` to a counter for the
``test_artifacts_loaded_once`` assertion).

**D-18 import-graph contract:** We import ``_load_default_artifacts``
from ``src.routing.decide``. Direction: ``apps.api → src.routing``,
NEVER the reverse. ``src/routing/tests/test_decide_smoke.py`` asserts
``src.routing.*`` does not pull ``apps.api.*`` back in — the import is
one-directional. The discretion line 178 wording explicitly authorises
this single import.

Cross-refs:
    - 03-CONTEXT.md D-15 (lazy adapter cache + empty registry)
    - 03-CONTEXT.md D-18 (rich healthz adapter status)
    - 03-CONTEXT.md discretion line 178 (lifespan order + canonical
      loader choice — _load_default_artifacts NOT
      src.demo.demo_router.load_joblib_artifacts)
    - 03-RESEARCH.md §"Pattern 1" lines 205-244 (canonical source)
    - 03-RESEARCH.md §"Example 9" lines 442-477 (defensive teardown)
    - 03-RESEARCH.md §"Open Question 3" (single shared connection)
    - 03-RESEARCH.md §"Open Question 5" (cache schema_version once)
    - 03-PATTERNS.md §"Excerpt 9" lines 442-477 (finally cleanup)
    - apps/api/__init__.py lines 35-59 (canonical side-effect-at-import
      — Phase 3 NEVER re-installs the redaction filter; importing
      ``apps.api.*`` from this module triggers both side effects
      transitively).
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from apps.api.backends.keystore import KeyStore
from apps.api.db.connect import open_db
from apps.api.db.migrate import up_to_latest
from apps.api.db.queries import read_schema_version
from apps.api.paths import DB_PATH
from apps.api.settings import load_settings_file

# D-18 + discretion line 178: the canonical 4-key artifact loader
# (task_type_classifier, agentic_intent_classifier, model_router,
# model_mapping) — exactly the shape ``decide()`` consumes verbatim.
# Do NOT use ``src.demo.demo_router.load_joblib_artifacts`` (that
# signature loads ONE artifact and returns a single dict; wrong shape
# for ``decide()``).
from src.routing.decide import _load_default_artifacts

logger = logging.getLogger(__name__)


# Sentinel that distinguishes "test pre-set this attribute on
# app.state" from "attribute genuinely missing". The conftest
# ``app_factory`` fixture pre-sets adapters / settings / keystore
# BEFORE the lifespan runs so we honour those overrides instead of
# overwriting them.
_SENTINEL = object()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup -> yield -> shutdown for the Phase 3 FastAPI app.

    Order is LOAD-BEARING per CONTEXT discretion line 178:

        1. open DB (pragmas applied inside)
        2. run migrations (idempotent — no-op when at latest)
        3. load joblib artifacts (Phase 1 canonical loader)
        4. load settings.json
        5. instantiate KeyStore (in-memory; no keyring by default)
        6. EMPTY adapter registry (lazy build at first turn)
        7. cache schema_version (Open Question 5; never re-read)

    Steps 4-6 honour pre-set test overrides (B3 lazy fixture pattern)
    so the conftest ``app_factory`` can inject test fakes without
    needing to monkeypatch the lifespan body.

    The ``finally`` block defensively closes ``app.state.db`` — the
    close attempt is wrapped in try/except because aiosqlite raises
    on already-closed (RESEARCH Example 9 + PATTERNS Excerpt 9
    lift-source from ``apps/api/backends/openrouter/adapter.py``
    lines 352-360).
    """

    # Step 1 — open DB (pragmas applied inside open_db).
    app.state.db = await open_db(DB_PATH)

    # Step 2 — run pending migrations. Idempotent on already-migrated.
    await up_to_latest(app.state.db)

    # Step 3 — load Phase 1 canonical 4-key artifacts dict.
    # ``_load_default_artifacts`` returns {task_type_classifier,
    # agentic_intent_classifier, model_router, model_mapping} — the
    # exact shape ``decide()`` consumes. API-01 SC #1: loaded ONCE
    # at startup; never reloaded per request.
    app.state.artifacts = _load_default_artifacts()

    # Step 4 — load non-key settings from disk (D-11). Honour test
    # override via app.state.settings pre-set on the factory.
    if getattr(app.state, "settings", _SENTINEL) is _SENTINEL:
        app.state.settings = load_settings_file()

    # Step 5 — KeyStore (in-memory primary; optional keyring kept off
    # by default per D-10). Honour test override.
    if getattr(app.state, "keystore", _SENTINEL) is _SENTINEL:
        app.state.keystore = KeyStore(use_keyring=False)

    # Step 6 — EMPTY adapter registry (D-15). Lazy-built at first
    # turn in Wave 4. PATCH /settings (Wave 6) clears the registry;
    # the next turn rebuilds with fresh KeyStore values. Honour
    # test override (conftest ``app_factory`` may pre-set fakes).
    #
    # OSS-07 / D-06: ``PROMPT_OPTIMIZER_FAKE_ADAPTERS=1`` is the
    # deterministic-E2E seam — it pre-wires the REAL OpenRouterAdapter
    # to a canned fake client so the Playwright drift spec (Plan 06-03)
    # exercises the full SSE wire + sse-translate.ts + AI-SDK runtime
    # with no OpenRouter key or network. The flag is read ONLY here,
    # nests INSIDE the ``_SENTINEL`` test-override gate (so the
    # in-process conftest ``app_factory`` override still wins), and is
    # deliberately NEVER added to ``.env.example`` — it is a CI/test-only
    # flag, not a user-facing key.
    if getattr(app.state, "adapters", _SENTINEL) is _SENTINEL:
        if os.environ.get("PROMPT_OPTIMIZER_FAKE_ADAPTERS") == "1":
            from apps.api.e2e_fakes import build_fake_openrouter_adapter

            app.state.adapters = {"openrouter": build_fake_openrouter_adapter()}
            logger.info(
                "Lifespan: FAKE adapters wired (PROMPT_OPTIMIZER_FAKE_ADAPTERS=1)"
            )
        else:
            app.state.adapters = {}

    # Step 6b — EMPTY per-turn control registry (Phase 11, CTRL-01).
    # ``app.state.control_registry`` is a ``dict[str, ControlMailbox]``
    # mirroring the ``app.state.adapters`` lifecycle: empty at startup,
    # populated by ``turn.py`` (register before the try, deregister in
    # finally), read by ``routes/control.py`` to deliver a control
    # command to a live turn. Seeded unconditionally — a missing-key
    # ``registry.get`` already 404s, but seeding keeps the route's
    # ``getattr(... , "control_registry", None)`` guard a defensive
    # belt rather than load-bearing.
    app.state.control_registry = {}

    # Step 7 — cache schema_version once at startup (Open Question 5).
    # Wave 2 ``/healthz`` reads from ``app.state.schema_version``
    # directly; never re-queries SQLite per request.
    app.state.schema_version = await read_schema_version(app.state.db)

    logger.info(
        "Lifespan startup complete: schema_version=%d, artifacts_loaded=True",
        app.state.schema_version,
    )

    try:
        yield  # ← server runs
    finally:
        # Defensive close — aiosqlite raises on double-close, but
        # the lifespan only needs to ATTEMPT the close, not succeed
        # (RESEARCH Example 9 + PATTERNS Excerpt 9). A failed close
        # is fine because the process is exiting; the OS reaps the
        # fd anyway.
        try:
            await app.state.db.close()
        except Exception:  # pragma: no cover — defensive only
            pass
