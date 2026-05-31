# Phase 9 Wave-0 RED test slice — DEBT-02 (OpenRouter).
#
# VALIDATION.md row DEBT-02: ``max_cost_usd=0.0`` honored (not
# falsy-fallback) at all 3 adapters. ``-k cost_cap_zero``.
#
# The bug: ``apps/api/backends/openrouter/adapter.py`` does
# ``max_cost_usd = options.max_cost_usd or self._max_cost`` — a
# caller-supplied ``0.0`` is falsy, so it falls through to the
# adapter's default (DEFAULT_PER_TURN_COST_USD, e.g. 0.50) and the cost
# cap NEVER trips for a deliberate zero-budget turn.
#
# This slice asserts the TARGET behavior (0.0 honored → cost_cap_exceeded
# trips on the first token of spend) and is gated with an imperative
# ``pytest.xfail(...)`` so it is COLLECTABLE by ``-k cost_cap_zero`` and
# reports ``xfail`` (NOT error, NOT pass) against today's adapter. The
# owning engineering plan removes the ``pytest.xfail(...)`` line when the
# ``or`` is replaced with an explicit ``None`` check.

from __future__ import annotations

import pytest

from apps.api.backends.chunks import Done, StreamError
from apps.api.backends.openrouter.adapter import OpenRouterAdapter
from apps.api.backends.protocol import AdapterOptions


async def _consume(adapter: OpenRouterAdapter, **kwargs) -> list:
    chunks: list = []
    async for chunk in adapter.stream(
        prompt=kwargs.get("prompt", "hi"),
        history=kwargs.get("history", []),
        options=kwargs.get("options", AdapterOptions()),
    ):
        chunks.append(chunk)
    return chunks


async def test_max_cost_usd_zero_honored(fake_openai_factory) -> None:
    """DEBT-02 (OpenRouter): an explicit ``max_cost_usd=0.0`` is honored.

    Default adapter cap is the high backstop; the caller passes 0.0 via
    options. Target: the zero cap means any spend trips
    ``cost_cap_exceeded`` before a clean Done.
    """

    pytest.xfail(
        "Wave 0 RED — DEBT-02 falsy-0 cost cap not yet fixed (openrouter)"
    )

    # Construct with the default high cap; the 0.0 arrives via options.
    adapter = OpenRouterAdapter(
        api_key="fake",
        max_cost_usd=0.50,
        client_factory=fake_openai_factory,
    )

    chunks = await _consume(
        adapter, options=AdapterOptions(max_cost_usd=0.0)
    )

    cost_errors = [
        c
        for c in chunks
        if isinstance(c, StreamError) and c.code == "cost_cap_exceeded"
    ]
    assert len(cost_errors) == 1, (
        "max_cost_usd=0.0 must be honored (cost cap trips), not replaced "
        "by the adapter default (DEBT-02 falsy-0 bug)"
    )
    assert isinstance(chunks[-1], Done)
