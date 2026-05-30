"""Settings endpoints — GET (masked) + PATCH (JSON Merge Patch).

Public surface (D-10, D-11, D-15):

    router               APIRouter(prefix="/api/v1", tags=["settings"])
    KeyPatch             Pydantic v2 body — provider-keyed key map
                         (extra="forbid"); ``None`` means delete.
    SettingsPatch        Pydantic v2 body — top-level partial settings
                         shape (extra="forbid"); ``None`` field values
                         are TREATED AS UNSET via ``exclude_unset``.
    _mask_key            Internal — masks plaintext key to ``sk-or-…ABC``
    _mask_settings_for_response
                         Internal — builds the GET-shape dict with
                         keys ALWAYS masked.

Endpoint contract (Wave 3 truth lines 26-29 of the plan):

    GET   /api/v1/settings    → 200 with body:
        {
          "keys": {
            "openrouter": {"present": bool, "masked"?: str},
            "anthropic":  {"present": bool, "masked"?: str}
          },
          "backends_enabled": dict,
          "computer_use_opt_in": bool,
          "default_max_cost_usd": float
        }
        Keys are ALWAYS masked. Plaintext is NEVER on the wire (D-10).

    PATCH /api/v1/settings    body: partial settings (JSON Merge Patch
        semantics via Pydantic v2 ``exclude_unset``).
        - ``{"keys": {"openrouter": "sk-or-v1-..."}}`` sets a key.
        - ``{"keys": {"openrouter": null}}`` DELETES the key (Pitfall 7).
        - Non-key fields (``backends_enabled``, ``computer_use_opt_in``,
          ``default_max_cost_usd``) merge into the in-memory settings
          AND are persisted atomically to settings.json (D-11).
        - Unknown top-level fields raise 422 (``extra="forbid"``).
        Returns 200 with the same masked response shape as GET.

**D-10 SECURE-04 boundary:**
    - Plaintext keys are WRITE-ONLY on the wire — the PATCH request
      can carry them; the PATCH response NEVER does.
    - Keys land in ``app.state.keystore`` (in-memory; optionally
      keyring-persisted when the user opted into the extra) — NEVER
      in ``settings.json`` (the file is non-key fields only).
    - The masked form ``sk-or-…ABC`` reveals only the leading provider
      prefix + last 3 chars so the user can verify which key is
      installed without exposing the secret.

**D-11 atomic write:**
    - Non-key settings flow through ``write_settings_file`` which
      writes ``tmp = settings.json.tmp`` then ``tmp.replace(target)``
      — atomic on POSIX (single-filesystem rename) and Windows
      (``MoveFileEx`` with ``MOVEFILE_REPLACE_EXISTING``).

**D-15 lazy adapter cache invalidation:**
    - After EVERY successful PATCH, ``app.state.adapters.clear()``
      empties the lazy adapter registry. The next turn rebuilds
      each adapter against the fresh ``KeyStore`` values.
    - Pitfall 8 acknowledged: in-flight streams retain their
      adapter reference, so the new keys take effect on the NEXT
      turn, not the CURRENT one. This is intentional — we never
      mid-stream rotate credentials.

**D-19 logging contract:**
    - This module uses ``logger = logging.getLogger(__name__)`` so
      the Phase 2 ``RedactionFilter`` installed at
      ``apps/api/__init__.py`` import time applies to every record
      emitted from here. Defense in depth: NEVER log the PATCH body
      content (an unmatched future key shape could slip past the
      regex). The Wave 6 ``test_secure_no_key_in_logs.py`` is the
      canonical full disclosure-regression test for API-04 / SECURE-04;
      this plan's ``test_patch_settings_does_not_log_plaintext_keys``
      is a partial pre-wire.

Cross-refs:
    - 03-CONTEXT.md D-09 (/api/v1 URL namespace)
    - 03-CONTEXT.md D-10 (PATCH bulk; GET masked; ``sk-…ABC`` form)
    - 03-CONTEXT.md D-11 (settings.json never carries keys; atomic)
    - 03-CONTEXT.md D-15 (clear adapter cache AFTER write, BEFORE return)
    - 03-CONTEXT.md D-19 (handler uses logger=__name__; no print)
    - 03-RESEARCH.md §"Pattern 8" lines 546-591 (Pydantic v2 + merge)
    - 03-RESEARCH.md §"Pitfall 7" lines 952-957 (None-as-delete)
    - 03-PATTERNS.md §"Routes" line 24 (settings.py anti-pattern audit)
    - apps/api/__init__.py (RedactionFilter install at import time)
    - apps/api/backends/keystore.py (KeyStore.set / KeyStore.get)
    - apps/api/settings.py (write_settings_file + _default_settings)
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from apps.api.settings import _default_settings, write_settings_file

# ``__name__`` resolves to ``apps.api.routes.settings`` so the
# Phase 2 RedactionFilter (installed on the root logger at
# ``apps/api/__init__.py`` import) catches every record we emit.
# NEVER use ``print(...)`` here — the filter does not apply to
# raw stdout writes (D-19 anti-pattern guard).
logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1", tags=["settings"])


# --------------------------------------------------------------------
# Pydantic v2 request models — extra="forbid" rejects unknown fields
# --------------------------------------------------------------------


class KeyPatch(BaseModel):
    """Body shape for the ``keys`` sub-dict of ``PATCH /settings``.

    Each provider field accepts either a plaintext key string (sets
    the key) or ``null`` (Pitfall 7 — deletes the key). Unknown
    providers raise 422 via ``extra="forbid"`` so a typo like
    ``{"keys": {"openroter": "sk-..."}}`` cannot silently land
    plaintext in a future provider slot.
    """

    model_config = ConfigDict(extra="forbid")

    openrouter: str | None = None
    anthropic: str | None = None


class SettingsPatch(BaseModel):
    """Body shape for ``PATCH /api/v1/settings``.

    Every field defaults to ``None``; ``exclude_unset=True`` on the
    dump differentiates "field omitted from the request" from
    "field explicitly set to None". The combination implements
    JSON Merge Patch semantics:

      - omitted field        → leave existing value alone
      - explicit ``null``    → delete (for keys) / overwrite with None
                               (not used for non-key fields today)
      - concrete value       → overwrite

    ``extra="forbid"`` rejects unknown top-level keys (e.g.
    ``{"unknown_field": 42}``) with a 422 — the negative-grep
    acceptance test enforces.
    """

    model_config = ConfigDict(extra="forbid")

    keys: KeyPatch | None = None
    backends_enabled: dict[str, bool] | None = None
    computer_use_opt_in: bool | None = None
    default_max_cost_usd: float | None = None
    # Phase 7 (07-07) routing preferences — non-secret; JSON-Merge-Patched and
    # persisted to settings.json, then threaded into decide() (ROUTER-06,
    # quality-first). Constrained to the locked enum / booleans so a client
    # cannot smuggle an arbitrary priority (extra="forbid" still rejects unknown
    # top-level keys with 422).
    priority: Literal["quality", "balanced", "speed", "cost"] | None = None
    cost_aware_fallback: bool | None = None
    zero_data_retention: bool | None = None


# --------------------------------------------------------------------
# Helpers — key masking + response shape
# --------------------------------------------------------------------


def _mask_key(key: str) -> str:
    """Return a masked rendering of ``key`` for safe display.

    Format: ``<first6>…<last3>`` so ``"sk-or-v1-XXXXXXXXXX"`` renders
    as ``"sk-or-…XXX"`` — keeps the leading provider prefix visible so
    the user can verify which key is installed, hides the body. Very
    short keys (``len <= 6``) lose the leading prefix entirely so we
    can never accidentally show 100% of a short malformed key.
    """

    if len(key) <= 6:
        return "…" + key[-3:]
    return key[:6] + "…" + key[-3:]


def _mask_settings_for_response(settings: dict, keystore: Any) -> dict:
    """Build the GET-shape dict with every key ALWAYS masked.

    Iterates the closed provider set ``("openrouter", "anthropic")``
    so a typo'd provider slot in KeyStore never leaks into the
    response. Each entry is one of:

        {"present": False}                         (no key)
        {"present": True, "masked": "sk-or-…ABC"}  (key set)

    Non-key fields flow through verbatim from the settings dict,
    falling back to ``_default_settings()`` when the in-memory
    settings dict is incomplete.
    """

    defaults = _default_settings()
    keys_block: dict[str, dict[str, Any]] = {}
    for provider in ("openrouter", "anthropic"):
        key = keystore.get(provider)
        if key:
            keys_block[provider] = {
                "present": True,
                "masked": _mask_key(key),
            }
        else:
            keys_block[provider] = {"present": False}

    return {
        "keys": keys_block,
        "backends_enabled": settings.get(
            "backends_enabled", defaults["backends_enabled"]
        ),
        "computer_use_opt_in": settings.get(
            "computer_use_opt_in", defaults["computer_use_opt_in"]
        ),
        "default_max_cost_usd": settings.get(
            "default_max_cost_usd", defaults["default_max_cost_usd"]
        ),
        # Phase 7 routing preferences (non-secret; round-trip in GET/PATCH).
        "priority": settings.get("priority", defaults.get("priority", "quality")),
        "cost_aware_fallback": settings.get(
            "cost_aware_fallback", defaults.get("cost_aware_fallback", False)
        ),
        "zero_data_retention": settings.get(
            "zero_data_retention", defaults.get("zero_data_retention", False)
        ),
    }


# --------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------


@router.get("/settings")
async def get_settings(request: Request) -> dict:
    """Return the masked settings shape.

    Read-only — touches ``request.app.state.{settings,keystore}`` only.
    Plaintext keys NEVER appear in the response body (D-10). Polled
    by the Phase 5 settings panel (UI-12) on mount.
    """

    return _mask_settings_for_response(
        request.app.state.settings, request.app.state.keystore
    )


@router.patch("/settings")
async def patch_settings(
    body: SettingsPatch, request: Request
) -> dict:
    """Apply a partial-update PATCH and return the masked settings.

    Step 1 — partial dump via ``exclude_unset`` (RESEARCH Pattern 8):
        ``patch = body.model_dump(exclude_unset=True)`` differentiates
        "field omitted" from "field set to None". The Pydantic v2
        primitive is the canonical JSON Merge Patch differentiator.

    Step 2 — keys first (D-10 SECURE-04):
        Keys NEVER hit settings.json. For each provider in
        ``patch["keys"]``:
          - ``None`` value → delete from KeyStore (Pitfall 7).
          - concrete value → set in KeyStore.
        After processing the keys sub-dict we ``pop`` it from the
        patch so the file writer never sees it.

    Step 3 — non-key merge (D-11):
        Shallow-merge the remaining 3 top-level fields into the
        in-memory settings dict and write atomically via
        ``write_settings_file`` (tmp + replace).

    Step 4 — cache invalidation (D-15):
        ``app.state.adapters.clear()`` runs AFTER the file is rewritten
        and BEFORE the response is returned. The next turn rebuilds
        every adapter against the fresh KeyStore.

    Step 5 — masked response (D-10):
        Return the same shape as GET so the UI can refresh its view
        with one request.
    """

    # Step 1 — partial dump (Pydantic v2 exclude_unset is the canonical
    # JSON Merge Patch differentiator). NOTE: ``mode="python"`` is the
    # default; the dict keeps Python types so we can compare to ``None``
    # directly in step 2.
    patch = body.model_dump(exclude_unset=True)

    # Step 2 — keys first, never persisted to settings.json.
    if "keys" in patch and patch["keys"] is not None:
        # ``patch["keys"]`` is the dump of ``KeyPatch``. Iterating its
        # items lets a single PATCH set OR delete multiple providers.
        # We DO NOT log the keys (defense in depth — the redaction
        # filter already runs, but logging the body would be a foot-gun
        # for any future key alphabet that does not match the regex).
        for provider, key in patch["keys"].items():
            if key is None:
                # Pitfall 7: explicit None means delete.
                # Pop from the internal cache directly because
                # ``KeyStore.set(provider, None)`` would cache a
                # type-invalid value (the public ``set`` accepts ``str``).
                request.app.state.keystore._memory.pop(provider, None)
            else:
                request.app.state.keystore.set(provider, key)
        patch.pop("keys", None)

    # Step 3 — non-key merge. Settings.json never receives keys.
    if patch:
        current = dict(request.app.state.settings)
        current.update(patch)
        request.app.state.settings = current
        write_settings_file(current)

    # Step 4 — cache invalidation (D-15). Runs AFTER the file is
    # rewritten and BEFORE the response is returned. An exception
    # inside ``write_settings_file`` aborts the handler with the
    # adapters cache intact, so a partial state never lands.
    request.app.state.adapters.clear()
    # The message body intentionally describes the effect (cache
    # cleared) but NEVER the input — never log the body itself.
    logger.info("settings updated; adapter cache cleared")

    # Step 5 — masked response (D-10). The handler returns the same
    # shape as GET so the Phase 5 UI can refresh from the PATCH
    # response without a follow-up GET.
    return _mask_settings_for_response(
        request.app.state.settings, request.app.state.keystore
    )
