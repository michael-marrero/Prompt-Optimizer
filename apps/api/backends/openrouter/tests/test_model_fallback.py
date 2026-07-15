# Story 6.5 — a BYOK key that can't serve the routed model must not error the
# turn. The OpenRouter adapter retries ONCE with "openrouter/auto" (the meta-
# router, always available) when the routed model is unavailable (HTTP 400/404),
# BEFORE any chunk streams. Non-model errors (401 auth, 429, 5xx) do NOT switch
# models.

from __future__ import annotations

import httpx
import pytest
from openai import APIStatusError

from apps.api.backends.chunks import Done, StreamError, TextDelta
from apps.api.backends.openrouter.adapter import OpenRouterAdapter
from apps.api.backends.openrouter.tests.fakes import (
    FakeAsyncStream,
    FakeChoice,
    FakeChunk,
    FakeDelta,
    FakeUsage,
)
from apps.api.backends.protocol import AdapterOptions


def _status_error(code: int) -> APIStatusError:
    req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    resp = httpx.Response(status_code=code, request=req)
    return APIStatusError("model not available", response=resp, body=None)


class _FallbackCompletions:
    """create() raises the given status for the routed model; streams a canned
    response for the openrouter/auto fallback — unless ``fail_all`` is set, in
    which case even the fallback target fails (to exercise the no-loop path)."""

    def __init__(self, chunks: list[FakeChunk], status: int, fail_all: bool):
        self._chunks = chunks
        self._status = status
        self._fail_all = fail_all
        self.models_tried: list[str] = []

    async def create(self, *, model, **_kw):
        self.models_tried.append(model)
        if self._fail_all or model != "openrouter/auto":
            raise _status_error(self._status)
        return FakeAsyncStream(self._chunks)


class _FallbackClient:
    def __init__(self, chunks: list[FakeChunk], status: int, fail_all: bool = False):
        self.completions = _FallbackCompletions(chunks, status, fail_all)
        self.chat = type("Chat", (), {"completions": self.completions})()


def _ok_chunks() -> list[FakeChunk]:
    return [
        FakeChunk(choices=[FakeChoice(FakeDelta(content="hi"))]),
        FakeChunk(choices=[], usage=FakeUsage()),
    ]


@pytest.mark.asyncio
async def test_unavailable_model_falls_back_to_openrouter_auto() -> None:
    client = _FallbackClient(_ok_chunks(), status=404)
    adapter = OpenRouterAdapter(api_key="k", client_factory=lambda _k: client)
    options = AdapterOptions(model="openai/gpt-5")  # key can't serve this

    out = [c async for c in adapter.stream("hi", [], options)]

    # It tried the routed model first, then fell back to openrouter/auto.
    assert client.completions.models_tried == ["openai/gpt-5", "openrouter/auto"]
    # A real answer streamed; NO error surfaced.
    assert any(isinstance(c, TextDelta) and c.text == "hi" for c in out)
    assert isinstance(out[-1], Done)
    assert not any(isinstance(c, StreamError) for c in out)


@pytest.mark.asyncio
async def test_400_invalid_model_also_falls_back() -> None:
    client = _FallbackClient(_ok_chunks(), status=400)
    adapter = OpenRouterAdapter(api_key="k", client_factory=lambda _k: client)
    out = [c async for c in adapter.stream("hi", [], AdapterOptions(model="some/weird-model"))]
    assert client.completions.models_tried == ["some/weird-model", "openrouter/auto"]
    assert any(isinstance(c, TextDelta) for c in out)


@pytest.mark.asyncio
async def test_401_auth_does_not_switch_models() -> None:
    # A 401 is a key problem, not a model problem — do NOT fall back; surface it.
    client = _FallbackClient(_ok_chunks(), status=401)
    adapter = OpenRouterAdapter(api_key="k", client_factory=lambda _k: client)
    out = [c async for c in adapter.stream("hi", [], AdapterOptions(model="openai/gpt-5"))]
    # Only the routed model was tried — no model switch on an auth error.
    assert client.completions.models_tried == ["openai/gpt-5"]
    assert any(isinstance(c, StreamError) for c in out)
    assert isinstance(out[-1], Done)


@pytest.mark.asyncio
async def test_auto_model_failure_does_not_loop() -> None:
    # A routed model whose fallback target (openrouter/auto) ALSO 404s must not
    # retry forever — the error surfaces once via the normal handler.
    client = _FallbackClient(_ok_chunks(), status=404, fail_all=True)
    adapter = OpenRouterAdapter(api_key="k", client_factory=lambda _k: client)
    out = [c async for c in adapter.stream("hi", [], AdapterOptions(model="openai/gpt-5"))]
    # Tried the model, fell back to auto, auto also failed → surfaced (no loop).
    assert client.completions.models_tried == ["openai/gpt-5", "openrouter/auto"]
    assert any(isinstance(c, StreamError) for c in out)
