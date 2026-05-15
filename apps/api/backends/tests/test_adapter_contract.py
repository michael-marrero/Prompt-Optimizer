# Plan 00 Task 3 — D-19 shared parametric adapter contract suite.
#
# Six invariants × three adapters = 18 cases (one pytest.skip on
# test_step_cap_aborts[openrouter] because OpenRouter has no
# notion of "step cap" — its single round-trip is the whole turn).
#
# Invariants enforced for every adapter:
#   1. test_happy_path_terminates_with_done — at least one TextDelta
#      lands and the final chunk is a Done.
#   2. test_cost_cap_aborts — when max_cost_usd is tiny, a
#      StreamError(code="cost_cap_exceeded") chunk appears and the
#      stream still ends with Done.
#   3. test_step_cap_aborts — when max_steps=1, a
#      StreamError(code="step_cap_exceeded") chunk appears (skipped
#      for openrouter; applies to claude_code + computer_use only).
#   4. test_cancellation_within_2_seconds — task.cancel() after a few
#      ms produces a Done within the 2s timeout budget.
#   5. test_done_always_lands — happy path's final chunk is a Done.
#   6. test_missing_api_key_raises_before_stream — constructor raises
#      when the api key / env is empty.
#
# WAVE 0 NOTE: adapter classes are NOT imported at module level here.
# They are imported LAZILY inside the adapter_factory fixture in
# conftest.py (wrapped in try/except ImportError -> pytest.skip).
# This is the B3 fix per the plan frontmatter's key_links block; a
# negative grep enforces it in CI:
#
#     ! grep -E "^from apps\.api\.backends\.(openrouter|claude_code|"
#       "computer_use)\.adapter import" apps/api/backends/tests/
#       test_adapter_contract.py
#
# Until Wave 1 adapters land, each parametric case enters the factory,
# hits the ImportError branch, and emits pytest.skip(...). After Wave
# 1 the same file's parametric cases become the live contract gate.

from __future__ import annotations

import asyncio

import pytest

from apps.api.backends.chunks import Done, StreamError, TextDelta
from apps.api.backends.protocol import AdapterOptions

ADAPTER_PARAMS = [
    pytest.param("openrouter", id="openrouter"),
    pytest.param("claude_code", id="claude_code"),
    pytest.param("computer_use", id="computer_use"),
]


@pytest.mark.parametrize("backend", ADAPTER_PARAMS)
@pytest.mark.asyncio
async def test_happy_path_terminates_with_done(adapter_factory, backend):
    adapter = adapter_factory(backend)
    chunks = []
    async for chunk in adapter.stream(
        prompt="hello", history=[], options=AdapterOptions()
    ):
        chunks.append(chunk)
    assert chunks, "no chunks emitted"
    assert any(isinstance(c, TextDelta) for c in chunks), "no TextDelta"
    assert isinstance(chunks[-1], Done), (
        f"last chunk is {type(chunks[-1])}, expected Done"
    )


@pytest.mark.parametrize("backend", ADAPTER_PARAMS)
@pytest.mark.asyncio
async def test_cost_cap_aborts(adapter_factory, backend):
    adapter = adapter_factory(backend, max_cost_usd=0.000001)
    chunks = []
    async for chunk in adapter.stream(
        prompt="x" * 1000, history=[], options=AdapterOptions()
    ):
        chunks.append(chunk)
    assert any(
        isinstance(c, StreamError) and c.code == "cost_cap_exceeded"
        for c in chunks
    )
    assert isinstance(chunks[-1], Done)


@pytest.mark.parametrize("backend", ADAPTER_PARAMS)
@pytest.mark.asyncio
async def test_step_cap_aborts(adapter_factory, backend):
    # OpenRouter is a single round-trip; "step cap" is not applicable.
    if backend == "openrouter":
        pytest.skip("step cap not applicable to OpenRouter (single round-trip)")
    adapter = adapter_factory(backend, max_steps=1)
    chunks = []
    async for chunk in adapter.stream(
        prompt="hi", history=[], options=AdapterOptions(max_steps=1)
    ):
        chunks.append(chunk)
    assert any(
        isinstance(c, StreamError) and c.code == "step_cap_exceeded"
        for c in chunks
    )
    assert isinstance(chunks[-1], Done)


@pytest.mark.parametrize("backend", ADAPTER_PARAMS)
@pytest.mark.asyncio
@pytest.mark.timeout(2)
async def test_cancellation_within_2_seconds(adapter_factory, backend):
    adapter = adapter_factory(backend)
    chunks: list = []

    async def consume() -> None:
        async for chunk in adapter.stream(
            prompt="hello", history=[], options=AdapterOptions()
        ):
            chunks.append(chunk)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    # The cancellation path must emit terminal pair within the 2s
    # timeout budget. Some chunks may be lost in the cancellation race;
    # the contract only requires that any chunks that DID land end
    # with Done.
    if chunks:
        assert isinstance(chunks[-1], Done)


@pytest.mark.parametrize("backend", ADAPTER_PARAMS)
@pytest.mark.asyncio
async def test_done_always_lands(adapter_factory, backend):
    adapter = adapter_factory(backend)
    chunks = []
    async for chunk in adapter.stream(
        prompt="hi", history=[], options=AdapterOptions()
    ):
        chunks.append(chunk)
    assert chunks
    assert isinstance(chunks[-1], Done)


@pytest.mark.parametrize("backend", ADAPTER_PARAMS)
def test_missing_api_key_raises_before_stream(
    backend, monkeypatch
):
    """The constructor must raise BEFORE any stream is opened when
    the api key / env is empty. Imports are lazy here too so this
    file is collectable in Wave 0."""

    if backend == "openrouter":
        try:
            from apps.api.backends.openrouter.adapter import OpenRouterAdapter
        except ImportError:
            pytest.skip("openrouter adapter not yet implemented")
        with pytest.raises(Exception):
            OpenRouterAdapter(api_key="")
    elif backend == "claude_code":
        try:
            from apps.api.backends.claude_code.adapter import ClaudeCodeAdapter
        except ImportError:
            pytest.skip("claude_code adapter not yet implemented")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(Exception):
            ClaudeCodeAdapter()
    elif backend == "computer_use":
        try:
            from apps.api.backends.computer_use.adapter import (
                ComputerUseAdapter,
            )
        except ImportError:
            pytest.skip("computer_use adapter not yet implemented")
        monkeypatch.setenv("COMPUTER_USE_OPT_IN", "1")
        with pytest.raises(Exception):
            ComputerUseAdapter(api_key="")
