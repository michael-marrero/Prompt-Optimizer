# Plan 02-01 Task 1 — OpenRouterCostTracker + errors.map_provider_error tests.
# Eight invariants (per plan behavior block):
#   T1: record_input_estimate adds tiktoken-encoded length to tokens_in.
#   T2: record_output_delta adds tiktoken-encoded length to tokens_out.
#   T3: record_final_usage overrides the running estimate.
#   T4: over_cap False at construction; True once cost > max_cost_usd.
#   T5: AuthenticationError -> ("auth_failed", msg, False).
#   T6: RateLimitError -> ("rate_limited", msg, True).
#   T7: Unrelated exception -> ("internal_error", msg, False).
#   T8: FakeOpenAIClient.chat.completions.create -> async iterator chunks.

from __future__ import annotations

import asyncio

import httpx
import openai
import pytest


def _make_auth_error(message: str = "bad key") -> openai.AuthenticationError:
    """Construct ``openai.AuthenticationError`` with a real httpx.Response.

    openai SDK 2.x's ``__init__`` requires a non-None ``response`` (it
    dereferences ``response.request``), so ``response=None`` no longer
    works as suggested in RESEARCH Pattern 3. Construct a minimal real
    Response bound to a real Request.
    """

    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(status_code=401, request=request)
    return openai.AuthenticationError(message=message, response=response, body=None)


def _make_rate_limit_error(message: str = "429") -> openai.RateLimitError:
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(status_code=429, request=request)
    return openai.RateLimitError(message=message, response=response, body=None)


def _make_api_status_error(status_code: int = 503, message: str = "down") -> openai.APIStatusError:
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(status_code=status_code, request=request)
    return openai.APIStatusError(message=message, response=response, body=None)


# --------------------------------------------------------------------
# OpenRouterCostTracker tests
# --------------------------------------------------------------------


def test_record_input_estimate_increments_tokens_in(pricing_table):
    from apps.api.backends.openrouter.cost import OpenRouterCostTracker

    tracker = OpenRouterCostTracker(
        model_id="openai/gpt-5",
        max_cost_usd=0.50,
        pricing=pricing_table,
    )
    assert tracker.tokens_in() == 0
    tracker.record_input_estimate(prompt="hello", history=[])
    # tiktoken's gpt-4 encoder produces 1 token for "hello".
    assert tracker.tokens_in() == 1


def test_record_output_delta_increments_tokens_out(pricing_table):
    from apps.api.backends.openrouter.cost import OpenRouterCostTracker

    tracker = OpenRouterCostTracker(
        model_id="openai/gpt-5",
        max_cost_usd=0.50,
        pricing=pricing_table,
    )
    assert tracker.tokens_out() == 0
    tracker.record_output_delta(text="world")
    assert tracker.tokens_out() == 1


def test_record_final_usage_overrides_estimate(pricing_table):
    from apps.api.backends.openrouter.cost import OpenRouterCostTracker

    tracker = OpenRouterCostTracker(
        model_id="openai/gpt-5",
        max_cost_usd=0.50,
        pricing=pricing_table,
    )
    # Build up bogus pre-flight estimates.
    tracker.record_input_estimate(prompt="long prompt here", history=[])
    tracker.record_output_delta(text="response chunk one ")
    tracker.record_output_delta(text="response chunk two")
    # Override with provider truth.
    tracker.record_final_usage(prompt_tokens=100, completion_tokens=50)
    assert tracker.tokens_in() == 100
    assert tracker.tokens_out() == 50


def test_over_cap_false_at_construction_true_after_exceeding(pricing_table):
    from apps.api.backends.openrouter.cost import OpenRouterCostTracker

    tracker = OpenRouterCostTracker(
        model_id="openai/gpt-5",
        max_cost_usd=0.000001,
        pricing=pricing_table,
    )
    assert tracker.over_cap() is False
    # 10_000 input tokens at $2.50/Mtok = $0.025 — well over 0.000001.
    tracker.record_input(10_000)
    assert tracker.over_cap() is True


# --------------------------------------------------------------------
# errors.map_provider_error tests
# --------------------------------------------------------------------


def test_map_provider_error_auth_failed():
    from apps.api.backends.openrouter.errors import map_provider_error

    exc = _make_auth_error("bad key")
    code, message, retriable = map_provider_error(exc)
    assert code == "auth_failed"
    assert "bad key" in message
    assert retriable is False


def test_map_provider_error_rate_limited():
    from apps.api.backends.openrouter.errors import map_provider_error

    exc = _make_rate_limit_error("429")
    code, message, retriable = map_provider_error(exc)
    assert code == "rate_limited"
    assert "429" in message
    assert retriable is True


def test_map_provider_error_timeout():
    from apps.api.backends.openrouter.errors import map_provider_error

    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    exc = openai.APITimeoutError(request=request)
    code, message, retriable = map_provider_error(exc)
    assert code == "timeout"
    assert retriable is True


def test_map_provider_error_unrelated_returns_internal_error():
    from apps.api.backends.openrouter.errors import map_provider_error

    code, message, retriable = map_provider_error(ValueError("unrelated"))
    assert code == "internal_error"
    assert message == "unrelated"
    assert retriable is False


def test_provider_error_map_has_all_four_classes():
    from apps.api.backends.openrouter.errors import PROVIDER_ERROR_MAP

    classes = set(PROVIDER_ERROR_MAP.keys())
    assert openai.AuthenticationError in classes
    assert openai.RateLimitError in classes
    assert openai.APITimeoutError in classes
    assert openai.APIStatusError in classes


# --------------------------------------------------------------------
# FakeOpenAIClient tests
# --------------------------------------------------------------------


def test_fake_openai_client_async_iteration():
    from apps.api.backends.openrouter.tests.fakes import (
        FakeChoice,
        FakeChunk,
        FakeDelta,
        FakeOpenAIClient,
        FakeUsage,
    )

    chunks = [
        FakeChunk(
            choices=[FakeChoice(delta=FakeDelta(content="hi"), finish_reason="stop")]
        ),
        FakeChunk(
            choices=[],
            usage=FakeUsage(prompt_tokens=2, completion_tokens=1),
        ),
    ]
    client = FakeOpenAIClient(chunks)

    async def consume() -> list:
        stream = await client.chat.completions.create(stream=True)
        seen = []
        async for chunk in stream:
            seen.append(chunk)
        await stream.close()
        return seen

    result = asyncio.run(consume())
    assert len(result) == 2
    assert result[0].choices[0].delta.content == "hi"
    assert result[1].usage.prompt_tokens == 2


def test_fake_openai_client_records_create_kwargs():
    from apps.api.backends.openrouter.tests.fakes import FakeOpenAIClient

    client = FakeOpenAIClient(chunks=[])

    async def call() -> None:
        await client.chat.completions.create(
            model="openai/gpt-5",
            stream=True,
            stream_options={"include_usage": True},
        )

    asyncio.run(call())
    # ``completions.create_calls`` is the canonical record list.
    assert len(client.completions.create_calls) == 1
    kwargs = client.completions.create_calls[0]
    assert kwargs["stream"] is True
    assert kwargs["stream_options"] == {"include_usage": True}
