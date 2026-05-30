"""Phase 7 Plan 07-01 Wave 0 — NEW RED test: routing-prefs persistence + reach decide().

07-VALIDATION.md row: "Routing-prefs persistence + reach decide() | D-03 | backend".

RED-by-design: ``SettingsPatch`` (apps/api/routes/settings.py) currently accepts
only ``keys`` / ``backends_enabled`` / ``computer_use_opt_in`` and is locked with
``extra="forbid"`` — so PATCHing the three NEW routing-pref keys
(``priority`` / ``cost_aware_fallback`` / ``zero_data_retention``) returns 422
today. Persisting them + threading ``priority`` / ``cost_aware_fallback`` /
``zero_data_retention`` into ``decide()`` lands in Plan 07-06. Until then the
PATCH/GET assertions fail for "field not accepted / not persisted" reasons — the
correct Wave-0 RED state, NOT a malformed-test failure.

Mirrors apps/api/tests/test_settings.py (the ``_fresh_app`` reload chain +
httpx.AsyncClient + ASGITransport, D-20 / API-08). Adds a direct ``decide()``
guard for the quality-first invariant (ROUTER-06): with ``priority="cost"`` and
``cost_aware_fallback=True`` a clearly-agentic / complex prompt must NOT be
downgraded below its quality pick.

Cross-refs:
    - apps/api/tests/test_settings.py (the PATCH/GET pattern this mirrors)
    - apps/api/routes/settings.py (SettingsPatch — extra="forbid"; RED target)
    - src/routing/decide.py lines 296-339 (the settings dict decide() reads)
    - 07-CONTEXT.md D-03 (Routing Preferences modal: priority / cost-aware / ZDR)
    - PROJECT.md "quality first, cost as tiebreaker" (ROUTER-06 invariant)
"""

from __future__ import annotations

import importlib

import httpx
import pytest
from httpx import ASGITransport


# ---------------------------------------------------------------------
# Helper — fresh app under tmp_path. Identical reload chain to
# test_settings.py:_fresh_app (paths → settings → routes.settings →
# lifespan → main) so a PATCH that writes settings.json targets tmp_path.
# ---------------------------------------------------------------------


def _fresh_app(monkeypatch: pytest.MonkeyPatch, tmp_path) -> object:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("PROMPT_OPTIMIZER_HOME", str(tmp_path))
    import apps.api.paths

    importlib.reload(apps.api.paths)
    import apps.api.settings

    importlib.reload(apps.api.settings)
    import apps.api.routes.settings

    importlib.reload(apps.api.routes.settings)
    import apps.api.lifespan

    importlib.reload(apps.api.lifespan)
    import apps.api.main

    importlib.reload(apps.api.main)
    return apps.api.main.create_app()


# ---------------------------------------------------------------------
# Test 1 — PATCH the three routing-pref keys, GET reflects them
# ---------------------------------------------------------------------


async def test_patch_routing_prefs_persists_and_round_trips(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """PATCH {priority, cost_aware_fallback, zero_data_retention} → GET reflects.

    RED until Plan 07-06 adds these fields to ``SettingsPatch`` and the GET
    response shape. Today the PATCH returns 422 (``extra="forbid"``).
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)
    prefs = {
        "priority": "quality",
        "cost_aware_fallback": True,
        "zero_data_retention": True,
    }

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            patch_resp = await client.patch("/api/v1/settings", json=prefs)
            get_resp = await client.get("/api/v1/settings")

    assert patch_resp.status_code == 200, (
        f"PATCH of routing prefs should succeed once 07-06 adds the fields; "
        f"got {patch_resp.status_code}: {patch_resp.text}"
    )
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body.get("priority") == "quality", (
        f"GET must reflect persisted priority; got {body.get('priority')!r}"
    )
    assert body.get("cost_aware_fallback") is True, (
        f"GET must reflect cost_aware_fallback; got {body.get('cost_aware_fallback')!r}"
    )
    assert body.get("zero_data_retention") is True, (
        f"GET must reflect zero_data_retention; got {body.get('zero_data_retention')!r}"
    )


# ---------------------------------------------------------------------
# Test 2 — each routing-pref field persists independently (merge-patch)
# ---------------------------------------------------------------------


async def test_patch_priority_only_is_merge_patch(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A PATCH carrying only ``priority`` persists it without clobbering others.

    Pydantic v2 ``exclude_unset`` JSON Merge Patch (same contract as the keys /
    backends_enabled fields). RED until 07-06 recognizes ``priority``.
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.patch(
                "/api/v1/settings", json={"priority": "speed"}
            )
            get_resp = await client.get("/api/v1/settings")

    assert resp.status_code == 200, (
        f"single-field routing-pref PATCH should succeed; "
        f"got {resp.status_code}: {resp.text}"
    )
    assert get_resp.json().get("priority") == "speed"


# ---------------------------------------------------------------------
# Test 3 — routing prefs never echo key material (SECURE-04 boundary)
# ---------------------------------------------------------------------


async def test_routing_prefs_get_never_echoes_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """GET after a routing-pref PATCH carries no plaintext key material.

    Defense-in-depth: even with a key in the KeyStore, the settings GET masks
    it (D-10), and the routing-pref fields must not smuggle any key into the
    response body.
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)
    plaintext = "sk-or-v1-PREFSNOLEAK1234567890ABCD"

    async with app.router.lifespan_context(app):
        app.state.keystore.set("openrouter", plaintext)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            await client.patch(
                "/api/v1/settings",
                json={"priority": "balanced", "zero_data_retention": False},
            )
            get_resp = await client.get("/api/v1/settings")

    assert get_resp.status_code == 200
    # SECURE-04: the full plaintext key must NOT appear anywhere in the body.
    assert plaintext not in get_resp.text, (
        "Plaintext key leaked into settings GET response body"
    )


# ---------------------------------------------------------------------
# Test 4 — quality-first invariant in decide() (ROUTER-06)
# ---------------------------------------------------------------------


async def test_decide_cost_priority_does_not_downgrade_agentic_pick(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """``priority="cost"`` + ``cost_aware_fallback=True`` must not downgrade a
    clearly-agentic prompt below its quality pick (ROUTER-06).

    PROJECT.md locks "quality first, cost as tiebreaker — never optimize cost at
    the expense of expected answer quality." A multi-file build/edit request is
    an agentic coding task whose quality backend is ``claude_code``; the
    cost-aware knob may pick a cheaper *model within a tier*, but it must NOT
    reroute the task to a non-agentic chat backend.

    This guard pins the invariant that Plan 07-06 must preserve when it threads
    ``priority`` / ``cost_aware_fallback`` into ``decide()``. If the routing
    artifacts cannot load in the current environment (no models / no NLTK data),
    the test skips rather than producing a false RED — the PATCH/GET tests above
    are the deterministic RED signal for this file.
    """

    try:
        from src.routing.decide import decide
    except Exception as exc:  # pragma: no cover - import guard
        pytest.skip(f"src.routing.decide unavailable in this env: {exc!r}")

    agentic_prompt = (
        "Build me a small finance-tracker web app: scaffold the project, create "
        "the database models, edit the existing routes, and wire up the React "
        "frontend so I can run it locally."
    )

    try:
        baseline = decide(agentic_prompt)
        cost_biased = decide(
            agentic_prompt,
            settings={"priority": "cost", "cost_aware_fallback": True},
        )
    except Exception as exc:  # pragma: no cover - runtime artifact/NLTK guard
        pytest.skip(f"decide() could not run in this env: {exc!r}")

    # The baseline agentic pick is the quality backend for a build/edit task.
    assert baseline.backend in {"claude_code", "computer_use"}, (
        f"sanity: an agentic build/edit prompt should pick an agent backend; "
        f"baseline picked {baseline.backend!r}"
    )
    # ROUTER-06: the cost-biased decision must NOT downgrade the agent task to a
    # cheaper non-agentic chat backend.
    assert cost_biased.backend == baseline.backend, (
        f"quality-first violated: priority=cost downgraded the agentic pick "
        f"from {baseline.backend!r} to {cost_biased.backend!r}"
    )
    assert cost_biased.backend != "openrouter", (
        "quality-first violated: an agentic task was rerouted to the cheaper "
        "openrouter chat backend under priority=cost"
    )
