"""Wave 2 CORS tests — OSS-05 explicit-origin allowlist.

Three async tests:

    test_cors_preflight_allowed_for_localhost
        OPTIONS /api/v1/healthz with Origin: http://localhost:3000
        returns 200 with Access-Control-Allow-Origin:
        http://localhost:3000.

    test_cors_preflight_rejected_for_evil
        OPTIONS /api/v1/healthz with Origin: http://evil.example
        returns a response that does NOT include
        Access-Control-Allow-Origin: http://evil.example. The
        browser's CORS check fails on the missing header.

    test_cors_env_override
        With PROMPT_OPTIMIZER_CORS_ORIGINS=http://a.com,http://b.com
        set + reloaded app, OPTIONS with Origin: http://a.com returns
        that origin in the response.

All tests use ``httpx.AsyncClient + ASGITransport`` per API-08 / D-20.
The CORS middleware is configured INSIDE ``create_app()`` (read of
``PROMPT_OPTIMIZER_CORS_ORIGINS`` happens at construction time), so the
env-override test reloads ``apps.api.main`` BEFORE calling
``create_app()``.

The negative case (evil origin) deliberately asserts the absence of
the offending header rather than expecting a non-200 status — CORS
preflight is a server-side advisory: the server returns headers, the
browser enforces. Some test servers may return 200 for any OPTIONS
request and rely on the missing ``Access-Control-Allow-Origin`` header
to reject. Starlette's CORSMiddleware DOES short-circuit unknown
origins by NOT setting the header.

Cross-refs:
    - 03-CONTEXT.md OSS-05 (no wildcard CORS)
    - 03-CONTEXT.md discretion line 175 (env override)
    - 03-RESEARCH.md §"Pattern 9" lines 593-631 (canonical source)
    - 03-VALIDATION.md row 3-02-03 line 52 (CORS test expectations)
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
    """Reload apps.api.{paths,lifespan,main} and build a fresh app.

    Mirrors ``test_health.py:_fresh_app``. We reload ``apps.api.main``
    so the ``PROMPT_OPTIMIZER_CORS_ORIGINS`` env override is observed
    at ``create_app()`` time. The lifespan/paths reload keeps the DB
    pointing at ``tmp_path`` so each test has a clean isolated DB.
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
# Test 1 — preflight from the canonical Next.js dev origin succeeds
# ---------------------------------------------------------------------


async def test_cors_preflight_allowed_for_localhost(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Preflight with Origin: http://localhost:3000 succeeds.

    Default allowlist is ``["http://localhost:3000"]`` (OSS-05 +
    CONTEXT discretion line 175). The browser's preflight is an
    OPTIONS request with the three standard CORS headers
    (``Origin``, ``Access-Control-Request-Method``, often
    ``Access-Control-Request-Headers``). Starlette's CORSMiddleware
    returns 200 plus the matching ``Access-Control-Allow-Origin``
    header when the origin is in the allowlist.
    """

    # No env override — exercise the default allowlist.
    monkeypatch.delenv("PROMPT_OPTIMIZER_CORS_ORIGINS", raising=False)
    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.options(
                "/api/v1/healthz",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "Content-Type",
                },
            )

    assert resp.status_code == 200, resp.text
    assert (
        resp.headers.get("access-control-allow-origin")
        == "http://localhost:3000"
    ), (
        f"Expected Access-Control-Allow-Origin: http://localhost:3000; "
        f"got {resp.headers.get('access-control-allow-origin')!r}"
    )


# ---------------------------------------------------------------------
# Test 2 — preflight from an unknown origin is rejected via missing header
# ---------------------------------------------------------------------


async def test_cors_preflight_rejected_for_evil(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Preflight with Origin: http://evil.example does NOT echo it.

    CORS is a browser-side protocol: the server's job is to return
    (or not return) the ``Access-Control-Allow-Origin`` header. If
    the server omits the header for the requested origin, the
    browser blocks the cross-origin response. We assert the absence
    of the offending origin in the response header.
    """

    monkeypatch.delenv("PROMPT_OPTIMIZER_CORS_ORIGINS", raising=False)
    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.options(
                "/api/v1/healthz",
                headers={
                    "Origin": "http://evil.example",
                    "Access-Control-Request-Method": "GET",
                },
            )

    # The middleware MUST NOT echo an evil origin in the header.
    assert (
        resp.headers.get("access-control-allow-origin")
        != "http://evil.example"
    ), (
        "CORS middleware echoed an unknown origin "
        "(http://evil.example) in Access-Control-Allow-Origin — "
        "OSS-05 violated."
    )


# ---------------------------------------------------------------------
# Test 3 — PROMPT_OPTIMIZER_CORS_ORIGINS env override is honoured
# ---------------------------------------------------------------------


async def test_cors_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """``PROMPT_OPTIMIZER_CORS_ORIGINS`` sets the allowlist at create_app().

    With env ``http://a.com,http://b.com``, the allowlist becomes
    ``["http://a.com", "http://b.com"]``. A preflight from
    ``http://a.com`` must echo back ``http://a.com``.
    """

    monkeypatch.setenv(
        "PROMPT_OPTIMIZER_CORS_ORIGINS",
        "http://a.com,http://b.com",
    )
    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.options(
                "/api/v1/healthz",
                headers={
                    "Origin": "http://a.com",
                    "Access-Control-Request-Method": "GET",
                },
            )

    assert resp.status_code == 200, resp.text
    assert (
        resp.headers.get("access-control-allow-origin") == "http://a.com"
    ), (
        f"Expected Access-Control-Allow-Origin: http://a.com; "
        f"got {resp.headers.get('access-control-allow-origin')!r}"
    )
