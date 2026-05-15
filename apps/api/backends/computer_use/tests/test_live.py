# Plan 02-03 Task 3 — Computer-use live smoke (BACKEND-05 + SECURE-05 +
# VALIDATION.md "Manual-Only Verifications"). Double opt-in: requires
# BOTH ANTHROPIC_API_KEY in env AND COMPUTER_USE_OPT_IN=1 AND the
# ``live`` pytest marker.
#
# Run with::
#
#     COMPUTER_USE_OPT_IN=1 ANTHROPIC_API_KEY=sk-ant-... \
#         uv run pytest -m live apps/api/backends/computer_use
#
# Cost-bounded by ``max_cost_usd=0.30`` — the prompt asks Claude to
# navigate to https://example.com and take a screenshot so the per-turn
# spend stays well under 30¢. Step-bounded by ``max_steps=5`` for
# defense in depth — example.com is a one-page site, two iterations
# should suffice.
#
# Pitfall 7 reminder: this test does spawn a real Chromium binary via
# Playwright. It is gated by ``@pytest.mark.live`` so the default CI
# run (``pytest -m 'not live'``) skips it. A live-mode CI workflow
# must run ``playwright install chromium`` before this test.

from __future__ import annotations

import os

import pytest

from apps.api.backends.chunks import Done, Screenshot, ToolCall
from apps.api.backends.protocol import AdapterOptions


@pytest.mark.live
@pytest.mark.skipif(
    not (
        os.getenv("ANTHROPIC_API_KEY")
        and os.getenv("COMPUTER_USE_OPT_IN") == "1"
    ),
    reason="no ANTHROPIC_API_KEY or COMPUTER_USE_OPT_IN!=1",
)
@pytest.mark.asyncio
async def test_live_open_example_com() -> None:
    """End-to-end: real Anthropic, real Playwright, real billing.

    Asserts:
        - At least one ``ToolCall`` chunk arrives (the agent must invoke
          the computer tool).
        - At least one ``Screenshot`` chunk arrives (D-14 post-action
          screenshot emission).
        - The terminal chunk is a ``Done``.
        - ``cost_usd`` is positive (provider reported) and below the cap.
        - ``screenshot_count <= max_steps`` (cap enforced).
    """

    # Import inside the test so the adapter module is only loaded when
    # the live test is actually running (Pitfall 7 — keeps the default
    # ``pytest -m 'not live'`` run from importing the real
    # AsyncAnthropic / Playwright stack at collection time).
    from apps.api.backends.computer_use.adapter import ComputerUseAdapter

    api_key = os.environ["ANTHROPIC_API_KEY"]
    max_cost_usd = 0.30
    max_steps = 5

    adapter = ComputerUseAdapter(
        api_key=api_key,
        max_cost_usd=max_cost_usd,
        max_steps=max_steps,
    )
    options = AdapterOptions(
        model="claude-opus-4-7",
        max_cost_usd=max_cost_usd,
        max_steps=max_steps,
    )

    chunks: list = []
    async for chunk in adapter.stream(
        prompt=(
            "Navigate to https://example.com and capture a screenshot. "
            "Confirm the page heading reads 'Example Domain'."
        ),
        history=[],
        options=options,
    ):
        chunks.append(chunk)

    tool_calls = [c for c in chunks if isinstance(c, ToolCall)]
    screenshots = [c for c in chunks if isinstance(c, Screenshot)]
    assert tool_calls, "expected at least one ToolCall chunk"
    assert screenshots, "expected at least one Screenshot chunk"
    assert len(screenshots) <= max_steps, (
        f"expected at most {max_steps} screenshots, got {len(screenshots)}"
    )

    assert isinstance(chunks[-1], Done), "terminal chunk must be Done"
    done = chunks[-1]
    assert done.cost_usd is not None and done.cost_usd > 0
    assert done.cost_usd < max_cost_usd
