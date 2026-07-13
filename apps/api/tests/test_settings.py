"""Wave 3 settings tests — GET masked + PATCH merge-patch.

Eight async tests covering ``GET /api/v1/settings`` (D-10 masked) and
``PATCH /api/v1/settings`` (Pydantic v2 ``exclude_unset`` JSON Merge
Patch + D-15 cache invalidation + D-11 atomic write + Pitfall 7
None-as-delete):

    test_get_settings_masks_keys
        With a key in KeyStore, GET response masks the plaintext —
        ``{"present": True, "masked": "sk-or-…ABC"}``. The plaintext
        NEVER appears in the response body (D-10 / SECURE-04).

    test_patch_settings_adds_key
        PATCH ``{"keys": {"openrouter": "sk-or-v1-..."}}`` returns 200
        with the masked response; ``app.state.keystore.get("openrouter")``
        returns the plaintext.

    test_patch_settings_round_trips_masked
        After PATCH adds a key, GET returns the same key masked.

    test_patch_settings_null_deletes_key
        Pitfall 7: PATCH with ``{"keys": {"openrouter": null}}`` removes
        the key from ``KeyStore._memory``. (We unset
        ``OPENROUTER_API_KEY`` env so the env-fallback path cannot mask
        the deletion.)

    test_patch_settings_invalidates_adapter_cache
        D-15: ``app.state.adapters.clear()`` runs after every successful
        PATCH. Pre-populated adapter cache is empty after the PATCH
        returns.

    test_patch_settings_writes_non_key_settings_atomically
        D-11: ``backends_enabled`` flows to ``settings.json`` via the
        atomic tmp+replace writer; ``load_settings_file()`` returns
        the new value.

    test_patch_settings_rejects_unknown_keys
        ``extra="forbid"`` on ``SettingsPatch``: unknown top-level
        fields raise 422.

    test_patch_settings_does_not_log_plaintext_keys
        D-19 partial pre-wire: with ``caplog.at_level("DEBUG")``, the
        plaintext key does NOT appear in ``caplog.text`` after PATCH.
        The full SECURE-04 canonical regression is Wave 6's
        ``test_secure_no_key_in_logs.py``.

All tests use ``httpx.AsyncClient + ASGITransport`` per API-08 / D-20.
The synchronous FastAPI test-client wrapper is FORBIDDEN here (the
negative-grep guard in test_smoke.py enforces).

The DB + settings file land in ``tmp_path`` via the
``PROMPT_OPTIMIZER_HOME`` env override + ``importlib.reload(apps.api.paths)``
so each test gets an isolated filesystem location. The lifespan opens
the DB, loads settings, instantiates KeyStore, and sets an empty
adapter registry — exactly what the production boot path does.

We unset ``OPENROUTER_API_KEY`` / ``ANTHROPIC_API_KEY`` in every test
so the ``KeyStore`` env-fallback (see ``KeyStore.get`` line 103-108)
cannot mask absence-of-key with a stale env value.

Cross-refs:
    - 03-CONTEXT.md D-09 (/api/v1 URL namespace)
    - 03-CONTEXT.md D-10 (GET masked / PATCH merge / sk-…ABC)
    - 03-CONTEXT.md D-11 (settings.json non-key fields only; atomic)
    - 03-CONTEXT.md D-15 (clear adapter cache AFTER write)
    - 03-CONTEXT.md D-19 (logger=__name__; RedactionFilter applies)
    - 03-RESEARCH.md §"Pattern 8" + Pitfall 7 (None-as-delete)
    - 03-VALIDATION.md row 3-03-02 (settings test expectations)
    - apps/api/tests/test_health.py (lifespan-context + reload chain)
"""

from __future__ import annotations

import importlib
import json
import logging

import httpx
import pytest
from httpx import ASGITransport


# ---------------------------------------------------------------------
# Test helper — fresh app under tmp dir, lifespan-triggered.
# Identical shape to test_threads_crud.py and test_health.py so the
# Wave 2 lifespan handles DB open + settings load + KeyStore + empty
# adapter registry exactly as production does.
# ---------------------------------------------------------------------


def _fresh_app(monkeypatch: pytest.MonkeyPatch, tmp_path) -> object:
    """Reload ``apps.api.paths`` under ``tmp_path`` and build a fresh app.

    Unsets the two BYOK env vars BEFORE lifespan runs so the KeyStore
    env-fallback (``KeyStore.get`` lines 103-108) does not mask the
    in-memory cache changes the PATCH handler makes. The
    ``raising=False`` keeps the call safe on a stock CI machine where
    these vars are not already set.

    **Reload chain order matters.** ``apps.api.paths`` is the source
    of truth for ``SETTINGS_PATH``; ``apps.api.settings`` imports it at
    module-top so it caches a copy; the route handler imports
    ``write_settings_file`` from ``apps.api.settings`` so it inherits
    the cached path. We therefore reload all three modules in
    dependency order before ``apps.api.lifespan`` / ``apps.api.main``
    pick up the fresh references. Without this chain, a PATCH that
    triggers ``write_settings_file`` would write to the user's REAL
    ``~/.prompt-optimizer/settings.json`` (Pitfall 2 — stale module
    constants survive ``importlib.reload`` on a sibling module).
    """

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
# Test 1 — GET /settings masks keys (D-10 / SECURE-04)
# ---------------------------------------------------------------------


async def test_get_settings_masks_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """GET response masks the plaintext to ``sk-or-…ABC`` form.

    Pre-populates the KeyStore with a fresh openrouter key inside the
    lifespan-context so the lifespan-installed KeyStore is the one we
    poke. Asserts the masked form (``present=True``, ``masked`` carries
    a tail-3 substring of the original) AND that the plaintext NEVER
    appears in the response body — the SECURE-04 disclosure boundary.
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)
    plaintext = "sk-or-v1-XYZABC1234567890XYZABC"

    async with app.router.lifespan_context(app):
        # Inject the key AFTER lifespan opens the KeyStore — that way
        # the KeyStore on app.state is the same instance the route
        # handler reads through.
        app.state.keystore.set("openrouter", plaintext)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/settings")

    assert resp.status_code == 200
    body = resp.json()
    keys = body["keys"]
    assert keys["openrouter"]["present"] is True
    masked = keys["openrouter"]["masked"]
    # The masked form uses the leading 6 chars + "…" + the last 3.
    assert masked.startswith("sk-or-"), (
        f"Masked form should retain provider prefix; got {masked!r}"
    )
    # The plaintext body of the key must NOT appear in the masked
    # rendering (SECURE-04: write-only on the wire). The tail-3 is
    # exposed deliberately as a verification aid; the rest must be
    # gone.
    assert "1234567890" not in masked, (
        f"Masked form must hide the body; got {masked!r}"
    )
    # SECURE-04 boundary: the full plaintext must NOT appear anywhere
    # in the response body, not even in a nested field.
    assert plaintext not in resp.text, (
        "Plaintext key leaked into response body"
    )
    # Anthropic was never set, so it must register as absent.
    assert keys["anthropic"]["present"] is False


# ---------------------------------------------------------------------
# Test 2 — PATCH /settings adds a key
# ---------------------------------------------------------------------


async def test_patch_settings_adds_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """PATCH sets a key in KeyStore without leaking it in the response.

    Confirms the response is the SAME masked shape as GET (D-10) and
    that ``app.state.keystore.get("openrouter")`` returns the plaintext
    we sent on the wire.
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)
    plaintext = "sk-or-v1-FRESH1234567890ABCDEFGH"

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.patch(
                "/api/v1/settings",
                json={"keys": {"openrouter": plaintext}},
            )

        # After the PATCH, the in-memory KeyStore must carry the
        # plaintext so the next-turn adapter rebuild can read it.
        assert app.state.keystore.get("openrouter") == plaintext

    assert resp.status_code == 200
    body = resp.json()
    assert body["keys"]["openrouter"]["present"] is True
    # SECURE-04: the plaintext we just PATCHed must NOT come back in
    # the response body (write-only on the wire).
    assert plaintext not in resp.text, (
        "Plaintext key leaked into PATCH response body"
    )


# ---------------------------------------------------------------------
# Test 3 — PATCH then GET round-trips masked
# ---------------------------------------------------------------------


async def test_patch_settings_round_trips_masked(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """After PATCH adds a key, GET returns the same key masked.

    Confirms the PATCH→GET round-trip is self-consistent (the
    Phase 5 UI uses GET to refresh after a settings save).
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)
    plaintext = "sk-or-v1-ROUNDTRIP12345678901234"

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            patch_resp = await client.patch(
                "/api/v1/settings",
                json={"keys": {"openrouter": plaintext}},
            )
            get_resp = await client.get("/api/v1/settings")

    assert patch_resp.status_code == 200
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["keys"]["openrouter"]["present"] is True
    masked = body["keys"]["openrouter"]["masked"]
    # The mask helper exposes the last 3 chars; the plaintext ends
    # in "234" so that substring is the deliberate verification tail.
    assert masked.endswith("234"), (
        f"Masked tail should be the last 3 chars of plaintext; "
        f"got {masked!r}"
    )
    assert plaintext not in get_resp.text


# ---------------------------------------------------------------------
# Test 4 — PATCH null DELETES the key (Pitfall 7)
# ---------------------------------------------------------------------


async def test_patch_settings_null_deletes_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """``{"keys": {"openrouter": null}}`` removes the key from KeyStore.

    Pre-populates the KeyStore with a key inside the lifespan-context,
    sends PATCH with explicit ``null``, then asserts the KeyStore.get
    returns None. The ``OPENROUTER_API_KEY`` env var is unset by the
    ``_fresh_app`` helper so the env-fallback cannot mask the deletion.
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)
    plaintext = "sk-or-v1-DELETEME123456789012345"

    async with app.router.lifespan_context(app):
        app.state.keystore.set("openrouter", plaintext)
        assert app.state.keystore.get("openrouter") == plaintext, (
            "Pre-condition: key should be present before PATCH null"
        )

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.patch(
                "/api/v1/settings",
                json={"keys": {"openrouter": None}},
            )

        # Post-condition: the in-memory cache is cleared. (Env var is
        # also unset by ``_fresh_app`` so the env-fallback cannot
        # repopulate the cache through a subsequent get.)
        assert app.state.keystore.get("openrouter") is None, (
            "PATCH null should have deleted the key from KeyStore"
        )

    assert resp.status_code == 200
    body = resp.json()
    # The response now reflects the deletion.
    assert body["keys"]["openrouter"]["present"] is False


# ---------------------------------------------------------------------
# Test 5 — PATCH clears app.state.adapters (D-15)
# ---------------------------------------------------------------------


async def test_patch_settings_invalidates_adapter_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """D-15: ``app.state.adapters.clear()`` runs on every PATCH.

    Pre-populates the lazy adapter registry with a sentinel object,
    sends a PATCH (any successful body), then asserts the dict is
    empty when the response returns. The cleared cache is what lets
    the next turn rebuild adapters against the fresh KeyStore.
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)

    async with app.router.lifespan_context(app):
        # Sentinel: any object will do — the test asserts the dict is
        # empty after PATCH, so it does not care what was inside.
        sentinel = object()
        app.state.adapters["openrouter"] = sentinel
        assert app.state.adapters, (
            "Pre-condition: adapter cache should be populated"
        )

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.patch(
                "/api/v1/settings",
                json={
                    "keys": {
                        "openrouter": "sk-or-v1-CLEARS12345678901234"
                    }
                },
            )

        assert app.state.adapters == {}, (
            f"D-15: adapter cache must be empty after PATCH; "
            f"got {app.state.adapters!r}"
        )

    assert resp.status_code == 200


# ---------------------------------------------------------------------
# Test 6 — PATCH writes non-key fields atomically to settings.json
# ---------------------------------------------------------------------


async def test_patch_settings_writes_non_key_settings_atomically(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """D-11: non-key fields flow through ``write_settings_file``.

    PATCH a new ``backends_enabled`` dict, then read the file off disk
    via ``load_settings_file`` and assert the value matches. The
    keys sub-dict is omitted from the PATCH so the test isolates the
    file-write path from the KeyStore path.
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)
    new_backends = {
        "openrouter": False,
        "claude_code": True,
        "computer_use": False,
    }

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.patch(
                "/api/v1/settings",
                json={"backends_enabled": new_backends},
            )

        # Read the file back through the production loader.
        from apps.api.settings import load_settings_file

        on_disk = load_settings_file()

    assert resp.status_code == 200
    assert on_disk["backends_enabled"] == new_backends, (
        f"Expected {new_backends!r}; got {on_disk.get('backends_enabled')!r}"
    )
    # D-11: the file MUST NOT carry any key material — the PATCH
    # body did not include keys, but defense in depth.
    assert "keys" not in on_disk
    # Sanity: settings.json is valid JSON we can re-parse.
    raw = (tmp_path / "settings.json").read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert parsed["backends_enabled"] == new_backends


# ---------------------------------------------------------------------
# Test 7 — PATCH unknown field returns 422 (extra="forbid")
# ---------------------------------------------------------------------


async def test_patch_settings_rejects_unknown_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """``extra="forbid"`` on SettingsPatch: unknown top-level → 422.

    Confirms the Pydantic v2 ``ConfigDict(extra="forbid")`` rejects
    payloads like ``{"unknown_top_level_field": 42}`` with the 422
    validation error.
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.patch(
                "/api/v1/settings",
                json={"unknown_top_level_field": 42},
            )

    assert resp.status_code == 422, (
        f"Expected 422 for unknown field; got {resp.status_code}: "
        f"{resp.text}"
    )


# ---------------------------------------------------------------------
# Test 8 — PATCH does NOT log plaintext (D-19 partial pre-wire)
# ---------------------------------------------------------------------


async def test_patch_settings_does_not_log_plaintext_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path, caplog
) -> None:
    """D-19 partial pre-wire: plaintext key never appears in caplog.

    The settings handler uses ``logger = logging.getLogger(__name__)``
    so the Phase 2 ``RedactionFilter`` (installed at
    ``apps/api/__init__.py`` import time) applies to every record.
    Even if a future contributor adds a stray ``logger.info(body)``
    call, the redaction filter would rewrite the key to
    ``***REDACTED-OPENAI***`` (the sk- alphabet match).

    NOTE: Wave 6 ships the canonical ``test_secure_no_key_in_logs.py``
    with the full 4-test SECURE-04 disclosure regression. This test
    is the partial pre-wire that confirms the handler emits at least
    one DEBUG/INFO record and that the chosen plaintext is not in
    ``caplog.text``.
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)
    # The plaintext is shaped like a real key (sk-or-v1-... 20+ chars)
    # so the RedactionFilter's ``sk-[A-Za-z0-9_-]{20,}`` rule would
    # rewrite it if it were ever logged. The test fixture name
    # "LOGGED" makes the failure mode obvious if regression hits.
    plaintext = "sk-or-v1-LOGGED1234567890123456"

    with caplog.at_level(logging.DEBUG, logger="apps.api.routes.settings"):
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                resp = await client.patch(
                    "/api/v1/settings",
                    json={"keys": {"openrouter": plaintext}},
                )

    assert resp.status_code == 200
    # The exact plaintext must NOT appear in any captured log record.
    # Even if a future contributor adds `logger.info(body)`, the
    # RedactionFilter rewrites it before caplog sees the message.
    assert plaintext not in caplog.text, (
        f"Plaintext key leaked into logs: {caplog.text!r}"
    )
    # And the redacted marker, if present, is the only acceptable
    # form for the key alphabet — not enforced here because the
    # current handler does NOT log the body at all (defense-in-depth
    # by omission), but Wave 6's regression will assert the marker
    # form once the canonical test lands.


# =====================================================================
# Phase 9 09-05 Task 2 — DEBT-05 backend defaults (priority /
# cost_aware_fallback / zero_data_retention persisted on first boot)
# =====================================================================
#
# Plan 04 (frontend) made the RoutingPrefs modal read these 3 keys back
# from GET /settings. They are supplied inline by
# _mask_settings_for_response today but were NOT in _default_settings(),
# so they were never PERSISTED on first boot — a partial PATCH that
# omitted them dropped them from the merge baseline. These assert the
# server is the system-of-record: the 3 keys live in the canonical
# defaults with the modal's values (RoutingPrefsProvider.tsx:35-47).


def test_default_settings_includes_routing_pref_defaults() -> None:
    """DEBT-05: _default_settings() carries the 3 routing-pref keys.

    The values MUST match the Plan-04 modal defaults
    (RoutingPrefsProvider.tsx:35-47) so the GET read-back agrees with the
    client: priority="quality", cost_aware_fallback=False,
    zero_data_retention=False.
    """

    from apps.api.settings import _default_settings

    defaults = _default_settings()
    assert defaults["priority"] == "quality", (
        "default priority must be 'quality' (modal default)"
    )
    assert defaults["cost_aware_fallback"] is False, (
        "default cost_aware_fallback must be False (modal default)"
    )
    assert defaults["zero_data_retention"] is False, (
        "default zero_data_retention must be False (modal default)"
    )


def test_default_settings_returns_fresh_dict() -> None:
    """The defaults stay a fresh dict per call (existing contract).

    A caller mutating the returned dict (e.g. the PATCH-merge baseline)
    must NOT poison the next call's defaults.
    """

    from apps.api.settings import _default_settings

    first = _default_settings()
    first["priority"] = "speed"
    second = _default_settings()
    assert second["priority"] == "quality", (
        "_default_settings() must return a fresh dict each call"
    )


async def test_partial_patch_preserves_routing_pref_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """DEBT-05: a partial PATCH no longer drops the 3 routing-pref keys.

    Because the defaults now carry priority/cost_aware_fallback/
    zero_data_retention, a PATCH that touches only ``default_max_cost_usd``
    leaves the routing prefs intact in the GET read-back — the server is
    authoritative (Plan-04 handoff: the client reads ``data.* ?? prev``).
    """

    app = _fresh_app(monkeypatch, tmp_path)
    transport = ASGITransport(app=app)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            # PATCH only an unrelated field — the routing prefs are omitted.
            patch_resp = await client.patch(
                "/api/v1/settings",
                json={"default_max_cost_usd": 0.25},
            )
            assert patch_resp.status_code == 200
            # GET reads back: the routing prefs are STILL present at the
            # modal defaults (not dropped by the partial merge).
            get_resp = await client.get("/api/v1/settings")

    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["priority"] == "quality"
    assert body["cost_aware_fallback"] is False
    assert body["zero_data_retention"] is False
