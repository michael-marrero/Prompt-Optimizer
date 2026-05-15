"""PricingTable — static-loaded per-Mtok rates with optional OpenRouter refresh.

Public surface (D-17):

    OPENROUTER_MODELS_URL   Public, unauthenticated models endpoint
    CACHE_TTL_SECONDS       24 h mtime-based cache invalidation
    PricingTable            from_static, get, refresh_from_openrouter

The static table is committed at ``config/pricing.json`` with 13
model entries + a ``_default`` fallback row. ``get(model_id)``
returns the matching entry or the default — adapters never see
``None`` from a missing model so cost tracking continues even when
OpenRouter introduces a model the table has never seen.

The async refresh path hits the public OpenRouter ``/api/v1/models``
endpoint (no auth required; verified live 2026-05-15). On HTTPError
the refresh logs a warning and returns silently — the in-memory
table keeps serving its static rates so a network blip never breaks
the cost cap.

The merge converts OpenRouter's per-TOKEN decimal-string pricing to
per-Mtok floats via a ``float(value) * 1_000_000`` multiplication
(Pitfall 6). Failing to apply this conversion would leave costs in
the picodollar range and the cost cap would never trip.

Cross-refs:
    - 02-RESEARCH.md §"Pattern 6" lines 1262-1330 (canonical source)
    - 02-RESEARCH.md §"Pitfall 6" (per-token vs per-Mtok mismatch)
    - 02-CONTEXT.md D-17 (pricing schema + _default mandate)
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Final

import httpx

logger = logging.getLogger(__name__)

OPENROUTER_MODELS_URL: Final[str] = "https://openrouter.ai/api/v1/models"
CACHE_TTL_SECONDS: Final[int] = 24 * 60 * 60


class PricingTable:
    """Per-model input/output USD rates in dollars-per-megatoken.

    Each row is ``{"input_per_mtok": float, "output_per_mtok": float}``.
    Adapters compute cost as ``tokens * rate / 1_000_000`` so the units
    line up with the table.

    Two-phase lifecycle:
        1. ``PricingTable.from_static("config/pricing.json")`` at
           startup (offline-safe; no network).
        2. ``await table.refresh_from_openrouter(cache_path)`` at
           background warmup or first request — overwrites stale
           per-Mtok values with current OpenRouter rates.
    """

    def __init__(self, table: dict[str, dict[str, float]]):
        # Hold a mutable reference so ``_merge_openrouter_snapshot``
        # can update in place without consumers re-loading.
        self._table: dict[str, dict[str, float]] = dict(table)

    # --- construction ---------------------------------------------------

    @classmethod
    def from_static(cls, path: str | Path) -> "PricingTable":
        """Load the static rate table committed at ``config/pricing.json``."""

        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        return cls(payload)

    # --- lookup ---------------------------------------------------------

    def get(self, model_id: str) -> dict[str, float]:
        """Return the rate row for ``model_id`` or the ``_default`` row.

        Adapters never receive ``None``; an unknown model falls back
        to the conservative ``_default`` row so cost tracking always
        works.
        """

        return self._table.get(model_id) or self._table["_default"]

    # --- refresh --------------------------------------------------------

    async def refresh_from_openrouter(self, cache_path: str | Path) -> None:
        """Refresh per-Mtok rates from ``openrouter.ai/api/v1/models``.

        Mtime-based cache: if ``cache_path`` is younger than
        ``CACHE_TTL_SECONDS`` we read the cached snapshot and skip
        the network entirely. On HTTPError the static table keeps
        serving and a warning is logged.
        """

        cache = Path(cache_path)
        if cache.exists() and (time.time() - cache.stat().st_mtime) < CACHE_TTL_SECONDS:
            try:
                with open(cache, "r", encoding="utf-8") as fh:
                    snapshot = json.load(fh)
                self._merge_openrouter_snapshot(snapshot)
                return
            except Exception:
                # Stale or corrupt cache — fall through to a fresh fetch.
                pass
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(OPENROUTER_MODELS_URL)
                resp.raise_for_status()
                snapshot = resp.json()
            cache.parent.mkdir(parents=True, exist_ok=True)
            with open(cache, "w", encoding="utf-8") as fh:
                json.dump(snapshot, fh)
            self._merge_openrouter_snapshot(snapshot)
        except httpx.HTTPError as exc:
            logger.warning(
                "OpenRouter pricing refresh failed: %s — using static table.",
                exc,
            )

    def _merge_openrouter_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Convert per-token decimal strings to per-Mtok floats (Pitfall 6)."""

        for model in snapshot.get("data", []):
            pricing = model.get("pricing") or {}
            if "prompt" not in pricing or "completion" not in pricing:
                continue
            try:
                input_per_mtok = float(pricing["prompt"]) * 1_000_000
                output_per_mtok = float(pricing["completion"]) * 1_000_000
            except (TypeError, ValueError):
                continue
            self._table[model["id"]] = {
                "input_per_mtok": input_per_mtok,
                "output_per_mtok": output_per_mtok,
            }
