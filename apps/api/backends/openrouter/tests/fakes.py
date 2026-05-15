"""Test fakes for the OpenRouter adapter — duck-typed substitutes for
``openai.AsyncOpenAI`` and ``ChatCompletionChunk``.

Public surface (Plan 02-01 Task 1):

    FakeDelta            content + tool_calls
    FakeChoice           delta + finish_reason
    FakeUsage            prompt_tokens + completion_tokens
    FakeChunk            choices + optional usage
    FakeAsyncStream      ``__aiter__`` over chunks + no-op ``close()``
    FakeChatCompletions  ``async def create(**_kw) -> FakeAsyncStream``
    FakeOpenAIClient     ``.chat.completions`` attribute access

The adapter expects an object exposing
``.chat.completions.create(**kw) -> stream`` where stream yields objects
shaped like OpenAI's ``ChatCompletionChunk``. This module gives every
test in this package and the D-19 shared contract suite the same
canonical fake — DO NOT inline duplicates anywhere else.

Cross-refs:
    - 02-RESEARCH.md §"Common Operation 3" lines 1916-1979 (canonical source)
    - apps/api/backends/tests/conftest.py (shared session fakes — same shape)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeDelta:
    """Mirrors ``openai.types.chat.ChatCompletionChunk.choices[0].delta``."""

    content: str | None = None
    tool_calls: list[Any] | None = None


@dataclass
class FakeChoice:
    """Mirrors ``openai.types.chat.ChatCompletionChunk.choices[0]``."""

    delta: FakeDelta
    finish_reason: str | None = None


@dataclass
class FakeUsage:
    """Mirrors ``openai.types.CompletionUsage`` on the final chunk."""

    prompt_tokens: int = 10
    completion_tokens: int = 5


@dataclass
class FakeChunk:
    """Mirrors ``openai.types.chat.ChatCompletionChunk``.

    The final-usage chunk has ``choices=[]`` and ``usage=FakeUsage(...)``.
    All other chunks carry ``choices=[FakeChoice(...)]`` and
    ``usage=None``.
    """

    choices: list[FakeChoice] = field(default_factory=list)
    usage: FakeUsage | None = None


class FakeAsyncStream:
    """Async iterator over a static list of ``FakeChunk`` instances.

    The adapter uses ``async for chunk in stream:`` so ``__aiter__``
    returns an async generator. ``close()`` is a no-op because there
    is no underlying httpx connection.
    """

    def __init__(self, chunks: list[FakeChunk]):
        self._chunks = chunks

    def __aiter__(self):
        async def gen():
            for chunk in self._chunks:
                yield chunk

        return gen()

    async def close(self) -> None:
        pass


class FakeChatCompletions:
    """Duck-typed ``client.chat.completions``."""

    def __init__(self, chunks: list[FakeChunk]):
        self._chunks = chunks
        # Records the kwargs the adapter passes to ``create``. Tests
        # assert ``stream_options={"include_usage": True}`` is present.
        self.create_calls: list[dict[str, Any]] = []

    async def create(self, **kw) -> FakeAsyncStream:
        self.create_calls.append(kw)
        return FakeAsyncStream(self._chunks)


class FakeOpenAIClient:
    """Duck-typed ``openai.AsyncOpenAI`` substitute.

    Exposes ``.chat.completions`` via the ``type("Chat", (), {...})()``
    shape so the adapter can do ``self._client.chat.completions.create``
    without a real OpenAI install.
    """

    def __init__(self, chunks: list[FakeChunk]):
        self.completions = FakeChatCompletions(chunks)
        # The adapter accesses ``self._client.chat.completions.create``.
        # We expose ``self.chat.completions`` as an attribute namespace
        # backed by ``self.completions`` so a test can also reach the
        # ``create_calls`` list via ``client.completions.create_calls``.
        self.chat = type(
            "Chat",
            (),
            {"completions": self.completions},
        )()
