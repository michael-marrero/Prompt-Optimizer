# Plan 02-01 Task 3 — OpenRouter live smoke (BACKEND-03 + VALIDATION.md
# "Manual-Only Verifications"). Opt-in: requires OPENROUTER_API_KEY in env
# and the `live` pytest marker.
#
# Run with::
#
#     OPENROUTER_API_KEY=sk-or-... uv run pytest -m live apps/api/backends/openrouter/
#
# Cost-bounded by ``max_cost_usd=0.10`` — the prompt asks for a one-word
# reply so the per-turn spend stays well under a penny.

from __future__ import annotations

import os

import pytest

from apps.api.backends.chunks import Done, TextDelta
from apps.api.backends.openrouter.adapter import OpenRouterAdapter
from apps.api.backends.protocol import AdapterOptions


@pytest.mark.live
@pytest.mark.skipif(not os.getenv("OPENROUTER_API_KEY"), reason="no OPENROUTER_API_KEY in env")
@pytest.mark.asyncio
async def test_live_streams_one_word_response():
    """End-to-end: real OpenRouter, real GPT-5, real billing.

    Asserts:
        - At least one TextDelta lands (not just StreamError + Done).
        - The terminal chunk is a Done.
        - cost_usd is positive (provider reported usage) and below the cap.
    """

    api_key = os.environ["OPENROUTER_API_KEY"]
    adapter = OpenRouterAdapter(api_key=api_key, max_cost_usd=0.10)
    options = AdapterOptions(
        model="openai/gpt-5",
        max_cost_usd=0.10,
    )

    chunks: list = []
    async for chunk in adapter.stream(
        prompt="say hi in exactly one word",
        history=[],
        options=options,
    ):
        chunks.append(chunk)

    assert any(isinstance(c, TextDelta) for c in chunks), (
        "expected at least one TextDelta"
    )
    assert isinstance(chunks[-1], Done), "terminal chunk must be Done"
    done = chunks[-1]
    assert done.cost_usd is not None and done.cost_usd > 0
    assert done.cost_usd < 0.10
