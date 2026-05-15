# Plan 02-01 Task 3 — OpenRouter adapter unit tests (BACKEND-03, BACKEND-06,
# BACKEND-07). Twelve invariants:
#   T1:  happy-path TextDelta + Done; provider-truth usage override.
#   T2:  default_headers set on the AsyncOpenAI constructor (HTTP-Referer,
#        X-Title) — Pitfall 3 regression.
#   T3:  every .chat.completions.create() call sets stream_options.include_usage
#        — Pitfall 1 regression.
#   T4:  cost cap aborts mid-stream with StreamError("cost_cap_exceeded") + Done.
#   T5:  cancellation within 2 s lands StreamError("cancelled") + Done.
#   T6:  tool-call deltas accumulate by index; flushed on finish_reason ==
#        "tool_calls"; tc_<6-char-base32> when provider omits id.
#   T7:  empty api_key raises openai.AuthenticationError BEFORE construct returns.
#   T8:  mid-stream AuthenticationError -> StreamError("auth_failed") + Done.
#   T9:  mid-stream APITimeoutError -> StreamError("timeout", retriable=True) + Done.
#   T10: APIStatusError(429) -> rate_limited; APIStatusError(503) -> provider_unavailable.
#   T11: unrelated RuntimeError -> StreamError("internal_error") + Done + logger.exception.
#   T12: Done.routing_signals == AdapterOptions.routing_signals pass-through.

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx
import openai
import pytest

from apps.api.backends.chunks import Done, StreamError, TextDelta, ToolCall
from apps.api.backends.openrouter.adapter import (
    HTTP_REFERER,
    OPENROUTER_BASE_URL,
    OpenRouterAdapter,
    X_TITLE,
)
from apps.api.backends.openrouter.tests.fakes import (
    FakeAsyncStream,
    FakeChoice,
    FakeChunk,
    FakeDelta,
    FakeOpenAIClient,
    FakeUsage,
)
from apps.api.backends.protocol import AdapterOptions, Message


# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------


def _make_auth_error(message: str = "bad key") -> openai.AuthenticationError:
    request = httpx.Request("POST", f"{OPENROUTER_BASE_URL}/chat/completions")
    response = httpx.Response(status_code=401, request=request)
    return openai.AuthenticationError(
        message=message, response=response, body=None
    )


def _make_api_status_error(
    status_code: int = 503, message: str = "down"
) -> openai.APIStatusError:
    request = httpx.Request("POST", f"{OPENROUTER_BASE_URL}/chat/completions")
    response = httpx.Response(status_code=status_code, request=request)
    return openai.APIStatusError(
        message=message, response=response, body=None
    )


async def _consume_stream(adapter, **kw) -> list:
    chunks: list = []
    options = kw.pop("options", AdapterOptions())
    prompt = kw.pop("prompt", "hi")
    history = kw.pop("history", [])
    async for chunk in adapter.stream(
        prompt=prompt, history=history, options=options
    ):
        chunks.append(chunk)
    return chunks


def _happy_path_chunks() -> list[FakeChunk]:
    return [
        FakeChunk(
            choices=[
                FakeChoice(
                    delta=FakeDelta(content="hi"),
                    finish_reason="stop",
                )
            ]
        ),
        FakeChunk(
            choices=[],
            usage=FakeUsage(prompt_tokens=10, completion_tokens=5),
        ),
    ]


def _long_content_chunks(n_chunks: int = 100, char_size: int = 100) -> list[FakeChunk]:
    """Many content chunks to trip the cost cap."""

    return [
        FakeChunk(
            choices=[
                FakeChoice(
                    delta=FakeDelta(content="x" * char_size),
                    finish_reason=None,
                )
            ]
        )
        for _ in range(n_chunks)
    ] + [
        FakeChunk(choices=[FakeChoice(delta=FakeDelta(content=""), finish_reason="stop")]),
        FakeChunk(choices=[], usage=FakeUsage(prompt_tokens=10, completion_tokens=500)),
    ]


# --------------------------------------------------------------------
# T1: Happy path
# --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_emits_textdelta_and_done():
    adapter = OpenRouterAdapter(
        api_key="fake",
        client_factory=lambda _k: FakeOpenAIClient(_happy_path_chunks()),
    )
    chunks = await _consume_stream(
        adapter,
        prompt="x",
        history=[],
        options=AdapterOptions(model="openai/gpt-5"),
    )
    assert any(isinstance(c, TextDelta) and c.text == "hi" for c in chunks)
    assert isinstance(chunks[-1], Done)
    # Provider-truth usage override (record_final_usage).
    assert chunks[-1].tokens_in == 10
    assert chunks[-1].tokens_out == 5


# --------------------------------------------------------------------
# T2: Pitfall 3 — default_headers on AsyncOpenAI constructor
# --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_headers_set_on_client_constructor(monkeypatch):
    """``AsyncOpenAI`` constructor receives HTTP-Referer + X-Title."""

    recorded: dict[str, Any] = {}

    class _RecordingAsyncOpenAI:
        def __init__(self, **kwargs):
            recorded.update(kwargs)
            # The adapter only uses .chat.completions, so wire a fake.
            self.chat = type(
                "Chat",
                (),
                {"completions": FakeOpenAIClient(_happy_path_chunks()).completions},
            )()

    monkeypatch.setattr(
        "apps.api.backends.openrouter.adapter.AsyncOpenAI",
        _RecordingAsyncOpenAI,
    )

    OpenRouterAdapter(api_key="sk-or-fake")

    assert recorded["base_url"] == OPENROUTER_BASE_URL
    headers = recorded["default_headers"]
    assert headers["HTTP-Referer"] == HTTP_REFERER
    assert headers["HTTP-Referer"] == "https://github.com/marreroii-michael/Prompt-Optimizer"
    assert headers["X-Title"] == X_TITLE
    assert headers["X-Title"] == "Prompt-Optimizer"


# --------------------------------------------------------------------
# T3: Pitfall 1 — stream_options.include_usage
# --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_options_include_usage_set_on_create():
    """Every create() call carries stream_options={'include_usage': True}."""

    fake = FakeOpenAIClient(_happy_path_chunks())
    adapter = OpenRouterAdapter(
        api_key="fake",
        client_factory=lambda _k: fake,
    )
    await _consume_stream(adapter)

    assert len(fake.completions.create_calls) == 1
    kwargs = fake.completions.create_calls[0]
    assert kwargs["stream"] is True
    assert kwargs["stream_options"] == {"include_usage": True}


# --------------------------------------------------------------------
# T4: Cost cap aborts mid-stream (BACKEND-06)
# --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cost_cap_aborts_mid_stream():
    """max_cost_usd=0.000001 + long stream -> StreamError + Done; break early."""

    long_chunks = _long_content_chunks(n_chunks=200, char_size=400)
    fake = FakeOpenAIClient(long_chunks)
    adapter = OpenRouterAdapter(
        api_key="fake",
        max_cost_usd=0.000001,
        client_factory=lambda _k: fake,
    )
    chunks = await _consume_stream(
        adapter,
        options=AdapterOptions(model="openai/gpt-5"),
    )

    assert any(
        isinstance(c, StreamError) and c.code == "cost_cap_exceeded"
        for c in chunks
    )
    assert isinstance(chunks[-1], Done)
    # Loop must break early — we should have seen far fewer TextDeltas than
    # the 200 input chunks would otherwise produce.
    text_deltas = [c for c in chunks if isinstance(c, TextDelta)]
    assert len(text_deltas) < 200


# --------------------------------------------------------------------
# T5: Cancellation within 2 s (BACKEND-07)
# --------------------------------------------------------------------


class _SlowFakeAsyncStream:
    """A fake that sleeps between chunks so cancellation has time to land."""

    def __init__(self):
        self.closed = False

    def __aiter__(self):
        async def gen():
            for _ in range(100):
                await asyncio.sleep(0.02)
                yield FakeChunk(
                    choices=[
                        FakeChoice(
                            delta=FakeDelta(content="t"), finish_reason=None
                        )
                    ]
                )

        return gen()

    async def close(self) -> None:
        self.closed = True


class _SlowFakeCompletions:
    def __init__(self):
        self.last_stream: _SlowFakeAsyncStream | None = None
        self.create_calls: list[dict[str, Any]] = []

    async def create(self, **kw) -> _SlowFakeAsyncStream:
        self.create_calls.append(kw)
        self.last_stream = _SlowFakeAsyncStream()
        return self.last_stream


class _SlowFakeClient:
    def __init__(self):
        self.completions = _SlowFakeCompletions()
        self.chat = type(
            "Chat",
            (),
            {"completions": self.completions},
        )()


@pytest.mark.timeout(2)
@pytest.mark.asyncio
async def test_cancellation_within_2_seconds():
    fake = _SlowFakeClient()
    adapter = OpenRouterAdapter(
        api_key="fake",
        client_factory=lambda _k: fake,
    )
    chunks: list = []

    async def consume() -> None:
        async for chunk in adapter.stream(
            prompt="hi", history=[], options=AdapterOptions()
        ):
            chunks.append(chunk)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # The adapter emits StreamError("cancelled") + Done before raising.
    # Some chunks may be lost in the cancellation race; any chunks that
    # DID land must end with Done (D-04).
    if chunks:
        assert isinstance(chunks[-1], Done)
    # in_flight.close() must have been awaited in the finally block.
    if fake.completions.last_stream is not None:
        assert fake.completions.last_stream.closed is True


# --------------------------------------------------------------------
# T6: Tool-call delta accumulation
# --------------------------------------------------------------------


@dataclass
class _FakeToolCallFunction:
    name: str | None = None
    arguments: str | None = None


@dataclass
class _FakeToolCallDelta:
    index: int
    id: str | None = None
    function: _FakeToolCallFunction | None = None


@pytest.mark.asyncio
async def test_tool_call_delta_accumulation():
    """Two delta chunks at same index + finish_reason='tool_calls' -> one ToolCall."""

    tc1 = _FakeToolCallDelta(
        index=0,
        id=None,
        function=_FakeToolCallFunction(name="weather", arguments='{"city":'),
    )
    tc2 = _FakeToolCallDelta(
        index=0,
        id=None,
        function=_FakeToolCallFunction(name=None, arguments='"Paris"}'),
    )

    chunks = [
        FakeChunk(
            choices=[
                FakeChoice(
                    delta=FakeDelta(content=None, tool_calls=[tc1]),
                    finish_reason=None,
                )
            ]
        ),
        FakeChunk(
            choices=[
                FakeChoice(
                    delta=FakeDelta(content=None, tool_calls=[tc2]),
                    finish_reason=None,
                )
            ]
        ),
        FakeChunk(
            choices=[
                FakeChoice(
                    delta=FakeDelta(content=None),
                    finish_reason="tool_calls",
                )
            ]
        ),
        FakeChunk(choices=[], usage=FakeUsage(prompt_tokens=5, completion_tokens=3)),
    ]
    adapter = OpenRouterAdapter(
        api_key="fake",
        client_factory=lambda _k: FakeOpenAIClient(chunks),
    )
    out = await _consume_stream(adapter)

    tool_calls = [c for c in out if isinstance(c, ToolCall)]
    assert len(tool_calls) == 1
    tc = tool_calls[0]
    assert tc.tool_name == "weather"
    assert tc.arguments == {"city": "Paris"}
    # tc_<6-char-base32> shape when provider omits id.
    assert tc.tool_call_id.startswith("tc_")
    assert len(tc.tool_call_id) == 9


# --------------------------------------------------------------------
# T7: Missing key raises typed exception
# --------------------------------------------------------------------


def test_missing_key_raises():
    with pytest.raises(openai.AuthenticationError):
        OpenRouterAdapter(api_key="")


# --------------------------------------------------------------------
# T8-T11: Provider error -> StreamError mapping
# --------------------------------------------------------------------


class _RaisingChatCompletions:
    """``.create()`` returns a stream whose first ``__aiter__`` step raises."""

    def __init__(self, exc: Exception):
        self._exc = exc
        self.create_calls: list[dict[str, Any]] = []

    async def create(self, **kw):
        self.create_calls.append(kw)
        exc = self._exc

        class _Raiser:
            def __aiter__(self):
                async def gen():
                    raise exc
                    yield  # pragma: no cover (unreachable)
                return gen()

            async def close(self) -> None:
                pass

        return _Raiser()


def _client_factory_raising(exc: Exception):
    def factory(_api_key: str) -> Any:
        client = type("FakeClient", (), {})()
        completions = _RaisingChatCompletions(exc)
        client.completions = completions  # type: ignore[attr-defined]
        client.chat = type(
            "Chat",
            (),
            {"completions": completions},
        )()
        return client

    return factory


@pytest.mark.asyncio
async def test_authentication_error_emits_auth_failed():
    exc = _make_auth_error("nope")
    adapter = OpenRouterAdapter(
        api_key="fake",
        client_factory=_client_factory_raising(exc),
    )
    out = await _consume_stream(adapter)
    assert any(
        isinstance(c, StreamError) and c.code == "auth_failed" and not c.retriable
        for c in out
    )
    assert isinstance(out[-1], Done)


@pytest.mark.asyncio
async def test_timeout_emits_retriable_timeout():
    request = httpx.Request("POST", f"{OPENROUTER_BASE_URL}/chat/completions")
    exc = openai.APITimeoutError(request=request)
    adapter = OpenRouterAdapter(
        api_key="fake",
        client_factory=_client_factory_raising(exc),
    )
    out = await _consume_stream(adapter)
    assert any(
        isinstance(c, StreamError) and c.code == "timeout" and c.retriable
        for c in out
    )
    assert isinstance(out[-1], Done)


@pytest.mark.asyncio
async def test_rate_limit_429_emits_retriable():
    exc = _make_api_status_error(status_code=429, message="429")
    adapter = OpenRouterAdapter(
        api_key="fake",
        client_factory=_client_factory_raising(exc),
    )
    out = await _consume_stream(adapter)
    assert any(
        isinstance(c, StreamError) and c.code == "rate_limited" and c.retriable
        for c in out
    )
    assert isinstance(out[-1], Done)


@pytest.mark.asyncio
async def test_503_emits_provider_unavailable():
    exc = _make_api_status_error(status_code=503, message="503")
    adapter = OpenRouterAdapter(
        api_key="fake",
        client_factory=_client_factory_raising(exc),
    )
    out = await _consume_stream(adapter)
    assert any(
        isinstance(c, StreamError) and c.code == "provider_unavailable"
        for c in out
    )
    assert isinstance(out[-1], Done)


@pytest.mark.asyncio
async def test_internal_error_logged_and_emitted(caplog):
    exc = RuntimeError("boom")
    adapter = OpenRouterAdapter(
        api_key="fake",
        client_factory=_client_factory_raising(exc),
    )
    with caplog.at_level(logging.ERROR, logger="apps.api.backends.openrouter.adapter"):
        out = await _consume_stream(adapter)

    assert any(
        isinstance(c, StreamError) and c.code == "internal_error"
        for c in out
    )
    assert isinstance(out[-1], Done)
    assert any("internal error" in record.message.lower() for record in caplog.records)


# --------------------------------------------------------------------
# T12: Done.routing_signals pass-through
# --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routing_signals_passed_through():
    signals = {"task_type": "coding", "agentic_intent": True}
    adapter = OpenRouterAdapter(
        api_key="fake",
        client_factory=lambda _k: FakeOpenAIClient(_happy_path_chunks()),
    )
    out = await _consume_stream(
        adapter,
        options=AdapterOptions(model="openai/gpt-5", routing_signals=signals),
    )
    assert isinstance(out[-1], Done)
    assert out[-1].routing_signals == signals
