"""FastAPI app constructor — mounts CORS + lifespan + routers.

Public surface (D-09, D-15, OSS-05):

    create_app()    -> FastAPI — factory; tests call this per-test
                                  to build a fresh app with the
                                  current env (PROMPT_OPTIMIZER_CORS_ORIGINS
                                  is read at this call).
    app             FastAPI       — module-level binding for
                                  ``uvicorn apps.api.main:app``.

The factory:

    1. Constructs ``FastAPI(lifespan=lifespan, title=...)`` so the
       Wave 2 lifespan runs at app startup.
    2. Adds ``CORSMiddleware`` with the OSS-05 explicit-origin
       allowlist (default ``http://localhost:3000``; overridable via
       ``PROMPT_OPTIMIZER_CORS_ORIGINS`` env). NEVER wildcards.
    3. Mounts the Wave 2 ``health.router`` (``GET /api/v1/healthz``).

Wave 3-6 plans grow the ``include_router`` list (threads, settings,
turn, rename). Phase 4-5 consumes the SSE wire format from the
``turn`` router unchanged.

**CORS / OSS-05 contract:**

    - The default allowlist is ``["http://localhost:3000"]`` (Next.js
      dev port). Any other origin is REJECTED by the browser.
    - The env override is comma-separated:
      ``PROMPT_OPTIMIZER_CORS_ORIGINS=http://a.com,http://b.com``.
    - ``allow_credentials=True`` is mandatory for the cookie-bearing
      session calls Phase 5 will add. With ``allow_credentials=True``,
      ``allow_origins=["*"]`` is FORBIDDEN by the CORS spec (browsers
      reject the configuration). The negative-grep guard in the plan
      enforces this at the source level too.
    - ``allow_methods`` enumerates the verbs the Wave 3-6 routes need
      (GET, POST, PATCH, DELETE) plus OPTIONS for preflight.
    - ``allow_headers`` includes ``Last-Event-ID`` so SSE reconnects
      from the browser pass preflight (Phase 4 streaming).

**Why import routes inside the factory:** Importing routes at module
top would create a circular import risk if any route ever imports
``from apps.api.main import app`` (it shouldn't, but the factory-level
import isolates this). Putting the import inside ``create_app`` also
keeps the module-load order: ``apps.api.lifespan`` first (which
imports ``src.routing.decide._load_default_artifacts`` and friends),
then ``apps.api.main`` calls ``create_app`` which pulls in the routes.

Cross-refs:
    - 03-CONTEXT.md D-09 (/api/v1 URL namespace)
    - 03-CONTEXT.md D-15 (lazy adapter cache via lifespan)
    - 03-CONTEXT.md discretion line 175 (CORS env override default)
    - 03-REQUIREMENTS.md OSS-05 (no wildcard CORS)
    - 03-RESEARCH.md §"Pattern 9" lines 593-631 (canonical source)
    - 03-PATTERNS.md Routes section lines 22-26 (route conventions)
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.lifespan import lifespan

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Build a fresh FastAPI app with CORS + lifespan + routers.

    Called once at module import to produce the canonical ``app``
    binding for ``uvicorn apps.api.main:app``. Tests call this
    directly per-test to get a fresh app that picks up the current
    ``PROMPT_OPTIMIZER_CORS_ORIGINS`` env (typical CORS env-override
    test pattern: ``monkeypatch.setenv`` → ``importlib.reload`` →
    ``create_app`` returns the new app with the new allowlist).
    """

    app = FastAPI(
        lifespan=lifespan,
        title="Prompt-Optimizer API",
        version="0.1.0",
    )

    # CORS allowlist (OSS-05). Default to the Next.js dev port
    # (CONTEXT discretion line 175). The env override is
    # comma-separated; empty entries are filtered so a trailing
    # comma doesn't introduce an empty allowlist entry.
    #
    # NEVER fall back to ``["*"]`` (OSS-05 explicit; the
    # negative-grep guard in acceptance criteria enforces).
    origins_env = os.environ.get(
        "PROMPT_OPTIMIZER_CORS_ORIGINS",
        "http://localhost:3000",
    )
    origins = [o.strip() for o in origins_env.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Last-Event-ID",
        ],
        expose_headers=["X-Request-Id"],
        max_age=600,
    )

    # Routes — Wave 2 mounted only ``health``; Wave 3 grew this list
    # with ``threads`` (CRUD) and ``settings`` (masked GET + PATCH).
    # Wave 4-6 plans extend it further (turn / rename). Imported
    # inside the factory (not at module top) to avoid a circular-
    # import surface area if a future route ever pulls from
    # ``apps.api.main``.
    from apps.api.routes import health, rename, settings, threads, turn

    app.include_router(health.router)
    app.include_router(threads.router)
    app.include_router(settings.router)
    app.include_router(turn.router)
    app.include_router(rename.router)

    return app


# Module-level binding for ``uvicorn apps.api.main:app``.
# This is the production server entry point per ROADMAP Phase 3 SC #1.
app = create_app()
