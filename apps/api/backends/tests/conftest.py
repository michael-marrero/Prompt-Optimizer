"""Shared pytest fixtures for the Phase 2 backend test suite.

Session-scoped fixtures (``pricing_table``, ``key_store``) construct
expensive-to-build objects once per test session. Function-scoped
fake fixtures (``fake_openai``, ``fake_claude_sdk_client``,
``fake_anthropic``, ``fake_screen``) hand each test a fresh stub so
state from one test never leaks into the next.

The ``adapter_factory`` fixture is the heart of the D-19 contract
suite: it returns a callable that builds an adapter for any of the
three backends with every fake already wired in. Adapter classes are
imported LAZILY inside the factory (try/except ImportError →
``pytest.skip(...)``) so the conftest is collectable in Wave 0
BEFORE the Wave 1 adapter modules exist — see the plan's B3 fix.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import pytest

from apps.api.backends.keystore import KeyStore
from apps.api.backends.pricing import PricingTable

REPO_ROOT = os.path.abspath(os.path.join(__file__, "..", "..", "..", "..", ".."))
PRICING_PATH = os.path.join(REPO_ROOT, "config", "pricing.json")


# --------------------------------------------------------------------
# Shared single-object fixtures
# --------------------------------------------------------------------


@pytest.fixture(scope="session")
def pricing_table() -> PricingTable:
    """Loaded once per session — pure data, no mutation expected."""

    return PricingTable.from_static(PRICING_PATH)


@pytest.fixture(scope="session")
def key_store() -> KeyStore:
    """Default in-memory KeyStore (no keyring extra required)."""

    return KeyStore()


# --------------------------------------------------------------------
# OpenAI / OpenRouter fakes — modelled on RESEARCH Common Operation 3
# (lines 1916-1979). Adapter expects an object exposing
# ``.chat.completions.create(**kw) -> stream`` where stream yields
# objects shaped like OpenAI's ChatCompletionChunk.
# --------------------------------------------------------------------


@dataclass
class FakeDelta:
    content: str | None = None
    tool_calls: list | None = None


@dataclass
class FakeChoice:
    delta: FakeDelta
    finish_reason: str | None = None


@dataclass
class FakeUsage:
    prompt_tokens: int = 10
    completion_tokens: int = 5


@dataclass
class FakeChunk:
    choices: list[FakeChoice]
    usage: FakeUsage | None = None


class FakeAsyncStream:
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
    def __init__(self, chunks: list[FakeChunk]):
        self._chunks = chunks

    async def create(self, **_kw) -> FakeAsyncStream:
        return FakeAsyncStream(self._chunks)


class FakeOpenAIClient:
    def __init__(self, chunks: list[FakeChunk]):
        self.chat = type(
            "Chat",
            (),
            {"completions": FakeChatCompletions(chunks)},
        )()


@pytest.fixture
def fake_openai() -> FakeOpenAIClient:
    """Two-chunk fake: one TextDelta, then a usage chunk."""

    chunks = [
        FakeChunk(
            choices=[
                FakeChoice(
                    delta=FakeDelta(content="hello"),
                    finish_reason="stop",
                )
            ],
            usage=None,
        ),
        FakeChunk(
            choices=[],
            usage=FakeUsage(prompt_tokens=10, completion_tokens=5),
        ),
    ]
    return FakeOpenAIClient(chunks)


# --------------------------------------------------------------------
# Claude Code (claude-agent-sdk) fakes
# --------------------------------------------------------------------


@dataclass
class FakeTextBlock:
    text: str = "hello"


@dataclass
class FakeAssistantMessage:
    content: list = field(default_factory=lambda: [FakeTextBlock()])


@dataclass
class FakeResultMessage:
    total_cost_usd: float = 0.001
    is_error: bool = False


class FakeClaudeSDKClient:
    """Duck-typed substitute for ``claude_agent_sdk.ClaudeSDKClient``."""

    def __init__(self) -> None:
        self.connect_calls = 0
        self.query_calls: list[str] = []
        self.interrupt_called = False
        self.disconnect_called = False

    async def connect(self) -> None:
        self.connect_calls += 1

    async def query(self, prompt: str) -> None:
        self.query_calls.append(prompt)

    async def receive_response(self):
        yield FakeAssistantMessage()
        yield FakeResultMessage()

    async def interrupt(self) -> None:
        self.interrupt_called = True

    async def disconnect(self) -> None:
        self.disconnect_called = True


@pytest.fixture
def fake_claude_sdk_client() -> FakeClaudeSDKClient:
    return FakeClaudeSDKClient()


# --------------------------------------------------------------------
# Anthropic computer-use fakes — beta.messages.stream(...) context manager
# --------------------------------------------------------------------


@dataclass
class FakeAnthropicDelta:
    type: str = "text_delta"
    text: str = "hi"


@dataclass
class FakeAnthropicEvent:
    type: str
    delta: FakeAnthropicDelta | None = None


@dataclass
class FakeAnthropicUsage:
    input_tokens: int = 10
    output_tokens: int = 5


@dataclass
class FakeFinalMessage:
    usage: FakeAnthropicUsage = field(default_factory=FakeAnthropicUsage)
    stop_reason: str = "end_turn"
    content: list = field(default_factory=list)


class FakeAnthropicStream:
    """Anthropic AsyncMessageStream stand-in.

    Used inside an ``async with`` block; iterable as ``async for event``.
    """

    def __init__(self) -> None:
        self._events = [
            FakeAnthropicEvent(type="content_block_delta", delta=FakeAnthropicDelta()),
            FakeAnthropicEvent(type="content_block_stop"),
        ]

    async def __aenter__(self) -> "FakeAnthropicStream":
        return self

    async def __aexit__(self, *_exc) -> None:
        return None

    def __aiter__(self):
        async def gen():
            for event in self._events:
                yield event

        return gen()

    async def get_final_message(self) -> FakeFinalMessage:
        return FakeFinalMessage()


class FakeAnthropicMessages:
    def stream(self, **_kw) -> FakeAnthropicStream:
        return FakeAnthropicStream()


class FakeAnthropicBeta:
    def __init__(self) -> None:
        self.messages = FakeAnthropicMessages()


class FakeAnthropicClient:
    def __init__(self) -> None:
        self.beta = FakeAnthropicBeta()


@pytest.fixture
def fake_anthropic() -> FakeAnthropicClient:
    return FakeAnthropicClient()


# --------------------------------------------------------------------
# Playwright Screen fake — minimal duck type
# --------------------------------------------------------------------


class FakePlaywrightScreen:
    def __init__(self) -> None:
        self.started = False
        self.closed = False
        self.actions: list[tuple[str, Any]] = []

    async def start(self) -> None:
        self.started = True

    async def screenshot(self) -> bytes:
        return b"\x89PNG\r\n" + b"fake-bytes"

    async def left_click(self, x: int, y: int) -> None:
        self.actions.append(("left_click", (x, y)))

    async def type_text(self, t: str) -> None:
        self.actions.append(("type_text", t))

    async def press_key(self, k: str) -> None:
        self.actions.append(("press_key", k))

    async def scroll(self, *args, **kwargs) -> None:
        self.actions.append(("scroll", (args, kwargs)))

    async def goto(self, url: str) -> None:
        self.actions.append(("goto", url))

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def fake_screen() -> FakePlaywrightScreen:
    return FakePlaywrightScreen()


# --------------------------------------------------------------------
# Parametric adapter factory (D-19 contract suite)
#
# CRITICAL (B3 fix per the plan frontmatter key_links): adapter
# classes are imported LAZILY here, NOT at module level. This is what
# lets the conftest and the test_adapter_contract.py file be
# collectable in Wave 0 before Wave 1 adapter modules exist.
# --------------------------------------------------------------------


@pytest.fixture
def adapter_factory(
    request,
    fake_openai,
    fake_claude_sdk_client,
    fake_anthropic,
    fake_screen,
    monkeypatch,
):
    """Build an adapter with every fake injected.

    Returns a ``factory(backend, *, max_cost_usd, max_steps)`` callable
    that the parametric contract tests call once each.
    """

    def factory(
        backend: str,
        *,
        max_cost_usd: float = 0.50,
        max_steps: int = 25,
    ) -> object:
        if backend == "openrouter":
            try:
                from apps.api.backends.openrouter.adapter import OpenRouterAdapter
            except ImportError:
                pytest.skip("openrouter adapter not yet implemented")
            return OpenRouterAdapter(
                api_key="fake",
                max_cost_usd=max_cost_usd,
                client_factory=lambda _key: fake_openai,
            )
        if backend == "claude_code":
            try:
                from apps.api.backends.claude_code.adapter import ClaudeCodeAdapter
            except ImportError:
                pytest.skip("claude_code adapter not yet implemented")
            return ClaudeCodeAdapter(
                max_cost_usd=max_cost_usd,
                max_steps=max_steps,
                client_factory=lambda options: fake_claude_sdk_client,
            )
        if backend == "computer_use":
            try:
                from apps.api.backends.computer_use.adapter import ComputerUseAdapter
            except ImportError:
                pytest.skip("computer_use adapter not yet implemented")
            monkeypatch.setenv("COMPUTER_USE_OPT_IN", "1")
            return ComputerUseAdapter(
                api_key="fake",
                max_cost_usd=max_cost_usd,
                max_steps=max_steps,
                client_factory=lambda api_key: fake_anthropic,
                screen_factory=lambda **kw: fake_screen,
            )
        raise ValueError(f"unknown backend: {backend}")

    return factory
