"""OSS-07 / D-06 — regression guard for the lifespan fake-adapter seam.

These three tests pin the three behaviors of the
``PROMPT_OPTIMIZER_FAKE_ADAPTERS`` branch added to ``apps/api/lifespan.py``
Step 6 (the single genuinely-new code seam for OSS-07):

    1. flag ON, no in-process override → ``app.state.adapters`` gets a REAL
       ``OpenRouterAdapter`` under the ``"openrouter"`` key (the fake-wired
       adapter the Playwright drift spec, Plan 06-03, streams against).
    2. flag OFF (default) → the registry starts empty (``{}``) exactly as
       before; production behavior is unchanged.
    3. flag ON **and** an in-process override pre-set on ``app.state`` →
       the override survives (the ``_SENTINEL`` outer gate beats the env
       flag), proving the Phase 3 D-20 pytest ``app_factory`` path still wins.

Project pytest conventions (pyproject ``[tool.pytest.ini_options]``):
``asyncio_mode = auto`` (so ``async def test_*`` needs no decorator) and
``--import-mode=importlib``. The lifespan is driven via
``async with app.router.lifespan_context(app):`` — the same mechanism the
existing ``apps/api/tests/test_turn_allowlist.py`` uses (RESEARCH Sources).

``PROMPT_OPTIMIZER_HOME`` is pointed at ``tmp_path`` and the
paths→lifespan→e2e_fakes→main reload chain is replayed (mirroring
``test_turn_allowlist._fresh_app``) so the lifespan's unconditional Steps 1-3
(open DB, migrate, load real ``models/*.joblib``) write to a throwaway dir
instead of the user's real ``~/.prompt-optimizer/`` home.
"""

from __future__ import annotations

import importlib
import sys
import typing

import pytest


def _fresh_app(monkeypatch: pytest.MonkeyPatch, tmp_path) -> typing.Any:
    """Reload paths + lifespan + e2e_fakes + main under tmp_path.

    Mirrors ``test_turn_allowlist._fresh_app`` so the lifespan's real DB +
    artifact loads (Steps 1-3, which run unconditionally even under the fake
    seam) are redirected to a throwaway ``PROMPT_OPTIMIZER_HOME``. Purges
    ``sse_starlette`` to avoid the Wave 4 reload-chain interaction with the
    D-18 smoke test. Returns a FRESH app via ``create_app()`` — which does NOT
    pre-set ``app.state.adapters``, so the ``_SENTINEL`` gate genuinely falls
    through to the env-flag branch under test.
    """

    monkeypatch.setenv("PROMPT_OPTIMIZER_HOME", str(tmp_path))
    for name in list(sys.modules):
        if name.startswith("sse_starlette"):
            del sys.modules[name]

    import apps.api.paths

    importlib.reload(apps.api.paths)
    import apps.api.jsonl_log

    importlib.reload(apps.api.jsonl_log)
    import apps.api.e2e_fakes

    importlib.reload(apps.api.e2e_fakes)
    import apps.api.lifespan

    importlib.reload(apps.api.lifespan)
    import apps.api.routes.turn

    importlib.reload(apps.api.routes.turn)
    import apps.api.main

    importlib.reload(apps.api.main)
    return apps.api.main.create_app()


async def test_flag_on_wires_openrouter_fake(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Flag ON + no override → the openrouter fake adapter is wired."""

    monkeypatch.setenv("PROMPT_OPTIMIZER_FAKE_ADAPTERS", "1")
    app = _fresh_app(monkeypatch, tmp_path)

    async with app.router.lifespan_context(app):
        assert "openrouter" in app.state.adapters
        assert type(app.state.adapters["openrouter"]).__name__ == "OpenRouterAdapter"


async def test_flag_off_leaves_empty_registry(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Flag OFF (default) + no override → the registry starts empty."""

    monkeypatch.delenv("PROMPT_OPTIMIZER_FAKE_ADAPTERS", raising=False)
    app = _fresh_app(monkeypatch, tmp_path)

    async with app.router.lifespan_context(app):
        assert app.state.adapters == {}


async def test_inprocess_override_still_wins(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Flag ON + an in-process override → the override survives.

    The ``_SENTINEL`` outer gate beats the env flag: a pre-set
    ``app.state.adapters`` (the Phase 3 D-20 ``app_factory`` path) is honored
    verbatim, so the registry contains ``"sentinel"`` and NOT ``"openrouter"``.
    """

    monkeypatch.setenv("PROMPT_OPTIMIZER_FAKE_ADAPTERS", "1")
    app = _fresh_app(monkeypatch, tmp_path)
    # Pre-set an override on app.state BEFORE the lifespan runs (same as the
    # conftest app_factory's adapters_override path).
    app.state.adapters = {"sentinel": object()}

    async with app.router.lifespan_context(app):
        assert "sentinel" in app.state.adapters
        assert "openrouter" not in app.state.adapters
