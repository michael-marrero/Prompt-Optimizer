"""Boot smoke — ``from apps.api.main import app`` under 3 s on warm cache.

ROADMAP Phase 3 SC #1: ``uvicorn apps.api.main:app starts in under
3 seconds`` on a developer laptop. The wall-clock budget is on a
warm cache — Pitfall 9 documents the cold-cache first run (joblib
mmap + NLTK punkt) which can take 5-10 s. The test suite always runs
warm because earlier tests already imported the dependency graph,
so the 3-second budget is realistic for the in-suite measurement.

Three sub-tests covering the boot surface:

    test_boot_under_3_seconds
        ``subprocess.run([sys.executable, "-c", "from apps.api.main
        import app"])`` in a fresh Python process to avoid module-
        cache short-circuits. Wall-clock measured via
        ``time.perf_counter``; assert <3.0 s.

    test_app_module_attribute_is_fastapi_instance
        In-process: ``from apps.api.main import app``. Confirms
        ``app`` is the FastAPI singleton (not a callable factory) and
        carries the canonical ``title``.

    test_all_phase_3_routes_mounted
        Walks ``app.routes`` and asserts every Phase 3 endpoint path
        is present (healthz, threads CRUD, turn, rename, settings).

NEVER uses the synchronous FastAPI test-client wrapper (API-08 / D-20).

Cross-refs:
    - 03-CONTEXT.md ROADMAP Phase 3 SC #1
    - 03-RESEARCH.md §"Pitfall 9" lines 965-969 (cold vs warm cache)
    - 03-VALIDATION.md row 3-06-03 line 65 (boot smoke expectation)
"""

from __future__ import annotations

import subprocess
import sys
import time

import pytest


@pytest.mark.timeout(60)
def test_boot_under_3_seconds() -> None:
    """A fresh Python process imports the app in <3.0 s.

    Strategy: spawn a clean Python subprocess via
    ``[sys.executable, "-c", ...]`` and measure wall-clock around
    the spawn. The fresh process has no in-memory sklearn / NLTK /
    joblib state — but the OS file-page cache from the surrounding
    pytest suite keeps the loads cheap (warm cache).

    The 60-second pytest-timeout absorbs the cold-cache worst case
    (5-10 s on a stock laptop, Pitfall 9) so a fresh-machine CI run
    produces a useful failure message instead of pytest's generic
    timeout. The actual assertion is a 3.0 s budget which is the
    ROADMAP SC.
    """

    start = time.perf_counter()
    result = subprocess.run(
        [sys.executable, "-c", "from apps.api.main import app; print('ok')"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    elapsed = time.perf_counter() - start

    assert result.returncode == 0, (
        f"boot subprocess failed (rc={result.returncode}): "
        f"stderr={result.stderr!r} stdout={result.stdout!r}"
    )
    assert "ok" in result.stdout, (
        f"boot subprocess did not print 'ok'; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert elapsed < 3.0, (
        f"boot took {elapsed:.2f}s (>3.0 s budget per ROADMAP "
        f"Phase 3 SC #1); stdout={result.stdout!r}"
    )


def test_app_module_attribute_is_fastapi_instance() -> None:
    """``apps.api.main.app`` is a FastAPI instance with the canonical title.

    In-process import; the suite has already paid the cold-cache cost
    elsewhere so this is essentially free. The class-name check is
    string-based so we do not depend on ``fastapi`` being importable
    at the test module top.
    """

    from apps.api.main import app

    # The class name is "FastAPI" — string-compare to avoid an
    # extra ``import fastapi`` at the test module top.
    assert app.__class__.__name__ == "FastAPI", (
        f"expected FastAPI instance; got {app.__class__.__name__}"
    )
    assert app.title == "Prompt-Optimizer API", (
        f"unexpected title: {app.title!r}"
    )


def test_all_phase_3_routes_mounted() -> None:
    """Every Phase 3 route path is mounted on the module-level ``app``.

    Walk ``app.routes`` and collect each route's ``path`` attribute.
    Assert the following paths are present:

        /api/v1/healthz                   GET   (Wave 2)
        /api/v1/threads                   POST / GET (Wave 3)
        /api/v1/threads/{thread_id}       GET / PATCH / DELETE (Wave 3)
        /api/v1/threads/{thread_id}/turn  POST (Wave 4)
        /api/v1/threads/{thread_id}/rename
                                          POST (Wave 6)
        /api/v1/settings                  GET / PATCH (Wave 3)

    This is the structural confirmation that the final wave's
    ``include_router`` call landed; if rename were missing from
    ``main.py``, the rename path would be absent here.
    """

    from apps.api.main import app

    paths: set[str] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            paths.add(path)

    expected = {
        "/api/v1/healthz",
        "/api/v1/threads",
        "/api/v1/threads/{thread_id}",
        "/api/v1/threads/{thread_id}/turn",
        "/api/v1/threads/{thread_id}/rename",
        "/api/v1/settings",
    }

    missing = expected - paths
    assert not missing, (
        f"Phase 3 paths missing from app.routes: {missing!r}; "
        f"got {sorted(paths)!r}"
    )
