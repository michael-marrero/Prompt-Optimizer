"""Test fakes for the computer-use adapter — duck-typed substitutes for
``anthropic.AsyncAnthropic`` (``client.beta.messages.stream(...)``) and
``apps.api.backends.computer_use.screen.PlaywrightScreen``.

Public surface (Plan 02-03 Task 1):

    FakePlaywrightScreen        ``start_count``, ``aclose_count``,
                                ``click_calls``, ``type_calls``,
                                ``key_calls``, ``goto_calls``,
                                ``scroll_calls``, configurable
                                ``screenshot_bytes``
    FakeAnthropicDelta          ``type`` + ``text``
    FakeAnthropicEvent          ``type`` + optional ``delta`` /
                                ``content_block``
    FakeContentBlockToolUse     ``type`` + ``id`` + ``name`` + ``input``
    FakeContentBlockText        ``type`` + ``text``
    FakeAnthropicUsage          ``input_tokens`` + ``output_tokens``
                                + optional cache fields
    FakeFinalMessage            ``usage`` + ``stop_reason`` + ``content``
    FakeAsyncMessageStream      async context manager + iterator + final
                                message accessor
    FakeBetaMessages            ``stream(**kw)`` records kwargs into
                                ``stream_calls: list[dict]`` so unit
                                tests can assert tool spec + beta header
    FakeAsyncAnthropic          ``beta.messages = FakeBetaMessages(...)``;
                                construct via factory callable

The adapter uses duck typing on attribute access (``event.delta.type``,
``event.content_block.type``, ``msg.usage``, ``msg.content``) rather
than relying on ``isinstance`` against the SDK's class objects. Tests
can therefore inject the Fake* dataclasses directly without
monkeypatching the adapter's own SDK imports.

Cross-refs:
    - 02-RESEARCH.md §"Pattern 5" lines 990-1025 (event/block shapes)
    - 02-PATTERNS.md "computer_use/tests/fakes.py" (canonical fake shape)
    - apps/api/backends/tests/conftest.py (shared D-19 fakes — same shape)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, AsyncIterator


# --------------------------------------------------------------------
# Playwright fake — records every action so tests can assert dispatch
# --------------------------------------------------------------------


class FakePlaywrightScreen:
    """Duck-typed substitute for ``PlaywrightScreen``.

    Tracks lifecycle counters and per-action call lists so tests can
    assert the adapter dispatched correctly. ``screenshot()`` returns a
    fixed PNG byte sequence (RFC-tracked 8-byte PNG magic + payload)
    so ``base64.b64encode`` of the returned bytes is deterministic.

    Constructor accepts ``viewport`` and ``headless`` kwargs for
    parity with the real ``PlaywrightScreen`` — the adapter calls
    ``screen_factory(viewport=...)`` and the duck-typed fake silently
    accepts and discards them.
    """

    DEFAULT_SCREENSHOT_BYTES: bytes = b"\x89PNG\r\n\x1a\nfake-screenshot-bytes"

    def __init__(
        self,
        *,
        viewport: tuple[int, int] = (1280, 800),
        headless: bool = True,
        screenshot_bytes: bytes | None = None,
    ) -> None:
        self.viewport = viewport
        self.headless = headless
        self._screenshot_bytes = screenshot_bytes or self.DEFAULT_SCREENSHOT_BYTES
        # Lifecycle counters — tests assert these are 1 after a normal
        # stream completes.
        self.start_count: int = 0
        self.aclose_count: int = 0
        # Per-action call lists — tests assert specific entries.
        self.click_calls: list[tuple[int, int, str | None]] = []
        self.type_calls: list[str] = []
        self.key_calls: list[str] = []
        self.goto_calls: list[str] = []
        self.scroll_calls: list[tuple[int, int, str, int]] = []
        # DEBT-01: records the (clamped) duration the adapter hands to
        # ``wait`` so the wait-clamp slice can assert the ceiling.
        self.wait_calls: list[float] = []
        self.screenshot_count: int = 0

    async def start(self) -> None:
        self.start_count += 1

    async def screenshot(self) -> bytes:
        self.screenshot_count += 1
        return self._screenshot_bytes

    async def left_click(
        self,
        x: int,
        y: int,
        *,
        modifier: str | None = None,
    ) -> None:
        self.click_calls.append((x, y, modifier))

    async def type_text(self, text: str) -> None:
        self.type_calls.append(text)

    async def press_key(self, key: str) -> None:
        self.key_calls.append(key)

    async def scroll(
        self,
        x: int,
        y: int,
        direction: str,
        amount: int,
    ) -> None:
        self.scroll_calls.append((x, y, direction, amount))

    async def goto(self, url: str) -> None:
        self.goto_calls.append(url)

    async def wait(self, duration: float) -> None:
        # DEBT-01: capture the clamped duration instead of actually
        # sleeping so the test runs fast.
        self.wait_calls.append(duration)

    async def aclose(self) -> None:
        self.aclose_count += 1


# --------------------------------------------------------------------
# Anthropic event / block fakes — mirror the SDK's streaming shapes
# --------------------------------------------------------------------


@dataclass
class FakeAnthropicDelta:
    """Mirrors the ``delta`` field of a streaming event.

    ``type`` is one of ``"text_delta"`` (carries ``text``) or
    ``"input_json_delta"`` (the adapter ignores those — see Pitfall 4).
    """

    type: str = "text_delta"
    text: str = ""


@dataclass
class FakeContentBlockText:
    """Mirrors an Anthropic text content block."""

    text: str = ""
    type: str = "text"


@dataclass
class FakeContentBlockToolUse:
    """Mirrors an Anthropic tool_use content block.

    ``input`` is the parsed JSON object (the SDK accumulates the partial
    json across ``input_json_delta`` events and exposes it fully-parsed
    on ``content_block_stop`` — Pitfall 4).
    """

    id: str = ""
    name: str = "computer"
    input: dict[str, Any] = field(default_factory=dict)
    type: str = "tool_use"


@dataclass
class FakeAnthropicEvent:
    """Mirrors the streaming envelope.

    ``content_block`` is set on ``content_block_stop`` events; ``delta``
    is set on ``content_block_delta`` events. Other event types
    (``message_start``, ``message_delta``, ``message_stop``) carry
    neither — the adapter ignores them.
    """

    type: str
    delta: FakeAnthropicDelta | None = None
    content_block: Any | None = None


@dataclass
class FakeAnthropicUsage:
    """Mirrors the ``usage`` block on the final message.

    Cache fields default to 0; the adapter passes them through to
    ``tracker.record_iteration_usage(cache_read=..., cache_write=...)``
    where they are tracked for visibility (RESEARCH Open Question 3).
    """

    input_tokens: int = 10
    output_tokens: int = 5
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class FakeFinalMessage:
    """Mirrors ``stream.get_final_message()`` return shape.

    ``content`` is the assistant message's content blocks list (text +
    tool_use blocks). ``stop_reason`` is one of Anthropic's documented
    terminators: ``"end_turn"`` (agent says done), ``"tool_use"`` (more
    tool calls coming), ``"max_tokens"`` (token cap), ``"stop_sequence"``
    (custom stop sequence hit).
    """

    usage: FakeAnthropicUsage = field(default_factory=FakeAnthropicUsage)
    stop_reason: str = "end_turn"
    content: list[Any] = field(default_factory=list)


# --------------------------------------------------------------------
# AsyncMessageStream fake — async context manager + iterator
# --------------------------------------------------------------------


class FakeAsyncMessageStream:
    """Duck-typed substitute for ``anthropic.BetaAsyncMessageStream``.

    Used inside an ``async with self._client.beta.messages.stream(...) as
    stream:`` block. Iterable as ``async for event in stream``. The
    final message accessor is ``await stream.get_final_message()``.

    ``raise_on_iter`` lets a test simulate a mid-stream provider
    exception (e.g. an APIStatusError) by raising the configured
    exception during the first ``__anext__`` call.
    """

    def __init__(
        self,
        events: list[FakeAnthropicEvent],
        final_message: FakeFinalMessage,
        *,
        raise_on_iter: BaseException | None = None,
        raise_on_enter: BaseException | None = None,
    ) -> None:
        self._events = list(events)
        self._final_message = final_message
        self._raise_on_iter = raise_on_iter
        self._raise_on_enter = raise_on_enter

    async def __aenter__(self) -> "FakeAsyncMessageStream":
        if self._raise_on_enter is not None:
            raise self._raise_on_enter
        return self

    async def __aexit__(self, *_exc) -> None:
        return None

    def __aiter__(self) -> AsyncIterator[FakeAnthropicEvent]:
        events = self._events
        raise_on_iter = self._raise_on_iter

        async def gen() -> AsyncIterator[FakeAnthropicEvent]:
            if raise_on_iter is not None:
                raise raise_on_iter
            for event in events:
                yield event

        return gen()

    async def get_final_message(self) -> FakeFinalMessage:
        return self._final_message


# --------------------------------------------------------------------
# beta.messages.stream(...) fake — records kwargs for tool-spec asserts
# --------------------------------------------------------------------


class FakeBetaMessages:
    """Duck-typed substitute for ``client.beta.messages``.

    Constructed with a list of ``FakeAsyncMessageStream`` instances —
    one per agent-loop iteration. Each call to ``stream(**kw)`` pops
    the next stream off the list AND records the kwargs so tests can
    assert ``betas=["computer-use-2025-11-24"]`` and the tool spec.

    The ``stream_calls`` list is the canonical introspection hook for
    Test 6 (BETA + tool spec assertion).
    """

    def __init__(self, iterations: list[FakeAsyncMessageStream]) -> None:
        # Reverse so we can ``pop()`` from the end for O(1) per call.
        self._iterations: list[FakeAsyncMessageStream] = list(reversed(iterations))
        self.stream_calls: list[dict[str, Any]] = []

    def stream(self, **kw: Any) -> FakeAsyncMessageStream:
        # Record EVERY kwarg the adapter passes — tools list, beta
        # header, model, max_tokens, messages, ...
        self.stream_calls.append(dict(kw))
        if not self._iterations:
            # The adapter asked for one more iteration than we provided
            # — surface that as a deliberate test misconfiguration so
            # tests don't silently pass on an unexpected loop count.
            raise AssertionError(
                "FakeBetaMessages exhausted: adapter requested another "
                "iteration but the fake only provided "
                f"{len(self.stream_calls) - 1}."
            )
        return self._iterations.pop()


class FakeAsyncAnthropic:
    """Duck-typed substitute for ``anthropic.AsyncAnthropic``.

    Exposes ``self.beta.messages`` as a ``FakeBetaMessages`` instance so
    the adapter's ``self._client.beta.messages.stream(...)`` call
    resolves against the fake.
    """

    def __init__(
        self,
        *,
        api_key: str = "fake",
        iterations: list[FakeAsyncMessageStream] | None = None,
    ) -> None:
        self.api_key = api_key
        messages = FakeBetaMessages(iterations or [])
        self.beta = SimpleNamespace(messages=messages)


# --------------------------------------------------------------------
# Convenience constructors — happy path + tool-use path
# --------------------------------------------------------------------


def make_happy_path_stream(text: str = "hello") -> FakeAsyncMessageStream:
    """Build a single-iteration stream that emits one TextDelta + end_turn.

    Yields:
        - ``content_block_delta`` with text_delta(``text``)
        - ``content_block_stop`` (no content_block — adapter skips)

    Final message: ``stop_reason="end_turn"`` (loop terminates after 1
    iteration). Usage: 10 in / 5 out.
    """

    events = [
        FakeAnthropicEvent(
            type="content_block_delta",
            delta=FakeAnthropicDelta(type="text_delta", text=text),
        ),
        # content_block_stop with NO content_block — adapter must
        # tolerate missing attribute (RESEARCH Pattern 5 conditional).
        FakeAnthropicEvent(type="content_block_stop"),
    ]
    return FakeAsyncMessageStream(
        events=events,
        final_message=FakeFinalMessage(
            stop_reason="end_turn",
            content=[FakeContentBlockText(text=text)],
        ),
    )


def make_tool_use_stream(
    *,
    tool_id: str = "t1",
    action: str = "screenshot",
    action_params: dict[str, Any] | None = None,
) -> FakeAsyncMessageStream:
    """Build a single-iteration stream that emits one ToolUseBlock.

    Yields:
        - ``content_block_stop`` carrying a ``tool_use`` ``content_block``

    Final message: ``stop_reason="tool_use"`` (agent wants another
    iteration after we execute the action).
    """

    params: dict[str, Any] = {"action": action}
    if action_params:
        params.update(action_params)
    tool_use = FakeContentBlockToolUse(
        id=tool_id,
        name="computer",
        input=params,
    )
    events = [
        FakeAnthropicEvent(type="content_block_stop", content_block=tool_use),
    ]
    return FakeAsyncMessageStream(
        events=events,
        final_message=FakeFinalMessage(
            stop_reason="tool_use",
            content=[tool_use],
        ),
    )
