# Plan 00 Task 3 — D-17 PricingTable tests (Pitfall 6 per-Mtok conversion).
#
# Test contracts:
#   - PricingTable.from_static('config/pricing.json') loads the static
#     table without error.
#   - .get('openai/gpt-5') returns input_per_mtok=2.50.
#   - .get('unknown-slug') falls back to _default (input=5.00).
#   - _merge_openrouter_snapshot converts decimal-string per-token
#     pricing to per-Mtok floats (Pitfall 6).
#   - Async refresh_from_openrouter uses cache when fresh (no HTTP call).

from __future__ import annotations

import json
import os
import time

import pytest

REPO_ROOT = os.path.abspath(
    os.path.join(__file__, "..", "..", "..", "..", "..")
)
PRICING_PATH = os.path.join(REPO_ROOT, "config", "pricing.json")


def test_from_static_loads_without_error() -> None:
    from apps.api.backends.pricing import PricingTable

    table = PricingTable.from_static(PRICING_PATH)
    assert table is not None


def test_get_returns_gpt5_rates() -> None:
    from apps.api.backends.pricing import PricingTable

    table = PricingTable.from_static(PRICING_PATH)
    entry = table.get("openai/gpt-5")
    assert entry["input_per_mtok"] == 2.50
    assert entry["output_per_mtok"] == 10.00


def test_get_returns_anthropic_rates() -> None:
    from apps.api.backends.pricing import PricingTable

    table = PricingTable.from_static(PRICING_PATH)
    entry = table.get("anthropic/claude-opus-4-7")
    assert entry["input_per_mtok"] == 5.00
    assert entry["output_per_mtok"] == 25.00


def test_get_falls_back_to_default_for_unknown_slug() -> None:
    """D-17: unknown model IDs return the _default row, never None."""

    from apps.api.backends.pricing import PricingTable

    table = PricingTable.from_static(PRICING_PATH)
    entry = table.get("definitely/not-a-real-slug")
    assert entry["input_per_mtok"] == 5.00
    assert entry["output_per_mtok"] == 20.00


def test_default_entry_is_conservative_upper_bound() -> None:
    from apps.api.backends.pricing import PricingTable

    table = PricingTable.from_static(PRICING_PATH)
    default_entry = table.get("_default")
    # CONTEXT specifics line 266 — _default is 5.00 / 20.00.
    assert default_entry == {"input_per_mtok": 5.00, "output_per_mtok": 20.00}


def test_merge_openrouter_snapshot_converts_per_token_to_per_mtok() -> None:
    """Pitfall 6 regression: OpenRouter pricing.prompt='0.0000025' must
    translate to input_per_mtok=2.5 (multiply by 1_000_000)."""

    from apps.api.backends.pricing import PricingTable

    table = PricingTable.from_static(PRICING_PATH)
    table._merge_openrouter_snapshot(
        {
            "data": [
                {
                    "id": "openai/gpt-5",
                    "pricing": {"prompt": "0.0000025", "completion": "0.00001"},
                }
            ]
        }
    )
    assert table.get("openai/gpt-5") == {
        "input_per_mtok": 2.5,
        "output_per_mtok": 10.0,
    }


def test_merge_openrouter_snapshot_skips_entries_without_pricing() -> None:
    from apps.api.backends.pricing import PricingTable

    table = PricingTable.from_static(PRICING_PATH)
    before = dict(table.get("openai/gpt-5"))
    table._merge_openrouter_snapshot(
        {"data": [{"id": "openai/gpt-5", "pricing": {}}]}
    )
    # Missing prompt/completion -> the entry is left untouched.
    assert table.get("openai/gpt-5") == before


def test_merge_openrouter_snapshot_skips_non_numeric_pricing() -> None:
    from apps.api.backends.pricing import PricingTable

    table = PricingTable.from_static(PRICING_PATH)
    before = dict(table.get("openai/gpt-5"))
    table._merge_openrouter_snapshot(
        {
            "data": [
                {
                    "id": "openai/gpt-5",
                    "pricing": {"prompt": "not-a-number", "completion": "0"},
                }
            ]
        }
    )
    assert table.get("openai/gpt-5") == before


def test_merge_openrouter_snapshot_adds_new_models() -> None:
    """Snapshot may introduce models the static table has never seen."""

    from apps.api.backends.pricing import PricingTable

    table = PricingTable.from_static(PRICING_PATH)
    table._merge_openrouter_snapshot(
        {
            "data": [
                {
                    "id": "vendor/brand-new-model",
                    "pricing": {"prompt": "0.000001", "completion": "0.000002"},
                }
            ]
        }
    )
    entry = table.get("vendor/brand-new-model")
    assert entry == {"input_per_mtok": 1.0, "output_per_mtok": 2.0}


@pytest.mark.asyncio
async def test_refresh_from_openrouter_uses_cache_when_fresh(tmp_path, monkeypatch) -> None:
    """Mtime-based cache: fresh cache means no HTTP call."""

    from apps.api.backends import pricing as pricing_mod
    from apps.api.backends.pricing import PricingTable

    cache_path = tmp_path / "cache.json"
    snapshot = {
        "data": [
            {
                "id": "openai/gpt-5",
                "pricing": {"prompt": "0.0000050", "completion": "0.00002"},
            }
        ]
    }
    cache_path.write_text(json.dumps(snapshot))
    # Cache mtime is "now" -> within CACHE_TTL_SECONDS.
    os.utime(cache_path, (time.time(), time.time()))

    # If httpx.AsyncClient is instantiated, the test fails — record
    # any call to its constructor.
    http_calls: list[bool] = []

    class _ShouldNotBeCalled:
        def __init__(self, *args, **kwargs) -> None:
            http_calls.append(True)
            raise AssertionError(
                "refresh_from_openrouter must not call httpx.AsyncClient "
                "when the cache is fresh"
            )

    monkeypatch.setattr(pricing_mod.httpx, "AsyncClient", _ShouldNotBeCalled)

    table = PricingTable.from_static(PRICING_PATH)
    await table.refresh_from_openrouter(cache_path)
    assert http_calls == []
    # And the cached snapshot was merged: gpt-5 input is now 5.0 per Mtok.
    assert table.get("openai/gpt-5") == {
        "input_per_mtok": 5.0,
        "output_per_mtok": 20.0,
    }


def test_openrouter_models_url_constant() -> None:
    from apps.api.backends.pricing import OPENROUTER_MODELS_URL

    assert OPENROUTER_MODELS_URL == "https://openrouter.ai/api/v1/models"


def test_cache_ttl_seconds_is_24h() -> None:
    from apps.api.backends.pricing import CACHE_TTL_SECONDS

    assert CACHE_TTL_SECONDS == 24 * 60 * 60
