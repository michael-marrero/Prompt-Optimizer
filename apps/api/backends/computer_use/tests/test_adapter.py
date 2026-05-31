# Plan 02-03 Task 3 — Computer-use adapter unit tests
# (BACKEND-05 / BACKEND-06 / BACKEND-07 / SECURE-05).
#
# Headless default + agent loop + Screenshot emit + cancellation +
# error mapping. Every test sets COMPUTER_USE_OPT_IN=1 via monkeypatch
# (the SECURE-05 unset-env regressions live in test_optin.py).
#
# Fifteen invariants codified here:
#   T1:  happy path emits TextDelta -> Done.
#   T2:  beta.messages.stream kwargs include betas + tool spec.
#   T3:  Screenshot chunk emitted after each tool action (D-14).
#   T4:  action dispatch: left_click -> screen.left_click.
#   T5:  action dispatch: navigate -> screen.goto.
#   T6:  action dispatch: type -> screen.type_text.
#   T7:  step cap (max_steps=1) -> StreamError(step_cap_exceeded) +
#        screen.aclose_count == 1.
#   T8:  cost cap (max_cost_usd=0.000001) -> StreamError(cost_cap_exceeded).
#   T9:  cancellation within 2s calls screen.aclose; emits StreamError +
#        Done.
#   T10: AuthenticationError mid-stream -> StreamError(auth_failed).
#   T11: APIStatusError(429) mid-stream -> StreamError(rate_limited).
#   T12: APIStatusError(503) mid-stream -> StreamError(provider_unavailable).
#   T13: routing_signals passed through to Done.
#   T14: PlaywrightScreen()._headless is True (anti-pattern 1727 regression).
#   T15: ComputerUseAdapter._viewport defaults to (1280, 800).

from __future__ import annotations

import asyncio
import base64
import os
from typing import Any

import httpx
import pytest

import anthropic

from apps.api.backends.chunks import (
    Done,
    Screenshot,
    StreamError,
    TextDelta,
    ToolCall,
    ToolResult,
)
from apps.api.backends.computer_use.adapter import (
    BETA_HEADER,
    DEFAULT_VIEWPORT,
    ComputerUseAdapter,
)
from apps.api.backends.computer_use.screen import PlaywrightScreen
from apps.api.backends.computer_use.tests.fakes import (
    FakeAnthropicDelta,
    FakeAnthropicEvent,
    FakeAnthropicUsage,
    FakeAsyncAnthropic,
    FakeAsyncMessageStream,
    FakeContentBlockText,
    FakeContentBlockToolUse,
    FakeFinalMessage,
    FakePlaywrightScreen,
    make_happy_path_stream,
    make_tool_use_stream,
)
from apps.api.backends.protocol import AdapterOptions


# --------------------------------------------------------------------
# Auto-fixture: every test in this module runs with opt-in enabled.
# The SECURE-05 unset-env regressions live in test_optin.py.
# --------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _enable_opt_in(monkeypatch):
    monkeypatch.setenv("COMPUTER_USE_OPT_IN", "1")
    yield


# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------


async def _consume(
    adapter: ComputerUseAdapter,
    *,
    prompt: str = "hi",
    history: list | None = None,
    options: AdapterOptions | None = None,
) -> list:
    """Drain an async iterator into a list."""

    chunks: list = []
    options = options or AdapterOptions()
    history = history or []
    async for chunk in adapter.stream(
        prompt=prompt,
        history=history,
        options=options,
    ):
        chunks.append(chunk)
    return chunks


def _build_adapter(
    *,
    fake_screen: FakePlaywrightScreen,
    iterations: list,
    max_cost_usd: float = 0.50,
    max_steps: int = 15,
) -> tuple[ComputerUseAdapter, FakeAsyncAnthropic]:
    """Construct a ComputerUseAdapter wired to fakes for both factories."""

    fake_client = FakeAsyncAnthropic(api_key="fake", iterations=iterations)
    adapter = ComputerUseAdapter(
        api_key="fake",
        max_cost_usd=max_cost_usd,
        max_steps=max_steps,
        client_factory=lambda api_key: fake_client,
        screen_factory=lambda **kw: fake_screen,
    )
    return adapter, fake_client


# --------------------------------------------------------------------
# T1: happy path emits TextDelta -> Done.
# --------------------------------------------------------------------


async def test_happy_path_emits_textdelta_and_done(fake_screen):
    adapter, _client = _build_adapter(
        fake_screen=fake_screen,
        iterations=[make_happy_path_stream(text="hello")],
    )
    chunks = await _consume(adapter)
    assert any(isinstance(c, TextDelta) and c.text == "hello" for c in chunks)
    assert isinstance(chunks[-1], Done)
    # Screen lifecycle invariant: started once, closed once.
    assert fake_screen.start_count == 1
    assert fake_screen.aclose_count == 1


# --------------------------------------------------------------------
# T2: beta.messages.stream kwargs include betas + tool spec.
#     Regression for the BETA header (computer-use-2025-11-24) + the
#     tool type (computer_20251124) + the 1280×800 display size.
# --------------------------------------------------------------------


async def test_stream_kwargs_include_beta_and_tool_spec(fake_screen):
    adapter, client = _build_adapter(
        fake_screen=fake_screen,
        iterations=[make_happy_path_stream(text="hi")],
    )
    await _consume(adapter)

    assert len(client.beta.messages.stream_calls) == 1
    kw = client.beta.messages.stream_calls[0]
    # BETA header lock.
    assert kw["betas"] == ["computer-use-2025-11-24"]
    # Tool spec lock — type + name + display size from CONTEXT D-13.
    tools = kw["tools"]
    assert len(tools) == 1
    assert tools[0]["type"] == "computer_20251124"
    assert tools[0]["name"] == "computer"
    assert tools[0]["display_width_px"] == 1280
    assert tools[0]["display_height_px"] == 800
    # max_tokens reasonable upper bound.
    assert kw["max_tokens"] == 4096


# --------------------------------------------------------------------
# T3: Screenshot chunk emitted after each tool action (D-14).
# --------------------------------------------------------------------


async def test_screenshot_emitted_after_tool_action(fake_screen):
    """tool_use(action=screenshot) iteration 1 -> end_turn iteration 2.

    The fake yields ToolUseBlock in iteration 1; iteration 2 returns
    end_turn so the loop terminates. We expect:
        - 1 ToolCall chunk for the tool_use block
        - 1 ToolResult chunk (action narration)
        - 1 Screenshot chunk with base64 of the fake PNG
        - terminal Done
    """

    tool_use_iter = make_tool_use_stream(
        tool_id="t1",
        action="screenshot",
    )
    end_turn_iter = make_happy_path_stream(text="done")
    adapter, _client = _build_adapter(
        fake_screen=fake_screen,
        iterations=[tool_use_iter, end_turn_iter],
    )
    chunks = await _consume(adapter)

    tool_calls = [c for c in chunks if isinstance(c, ToolCall)]
    tool_results = [c for c in chunks if isinstance(c, ToolResult)]
    screenshots = [c for c in chunks if isinstance(c, Screenshot)]

    assert len(tool_calls) == 1
    assert tool_calls[0].tool_call_id == "t1"
    assert tool_calls[0].tool_name == "computer"
    assert tool_calls[0].arguments == {"action": "screenshot"}
    assert len(tool_results) == 1
    assert tool_results[0].tool_call_id == "t1"
    assert tool_results[0].is_error is False
    assert len(screenshots) == 1
    assert screenshots[0].image_format == "png"
    # The base64 of the fake's bytes should decode back to those bytes.
    assert (
        base64.b64decode(screenshots[0].image_b64)
        == FakePlaywrightScreen.DEFAULT_SCREENSHOT_BYTES
    )
    # step=1 (one increment per iteration; the screenshot is emitted
    # during iteration 1).
    assert screenshots[0].step == 1

    assert isinstance(chunks[-1], Done)


# --------------------------------------------------------------------
# T4: action dispatch: left_click -> screen.left_click.
# --------------------------------------------------------------------


async def test_action_dispatch_left_click_calls_screen(fake_screen):
    tool_use_iter = make_tool_use_stream(
        tool_id="c1",
        action="left_click",
        action_params={"coordinate": [100, 200]},
    )
    end_turn_iter = make_happy_path_stream(text="done")
    adapter, _client = _build_adapter(
        fake_screen=fake_screen,
        iterations=[tool_use_iter, end_turn_iter],
    )
    await _consume(adapter)

    assert fake_screen.click_calls == [(100, 200, None)]


# --------------------------------------------------------------------
# T5: action dispatch: navigate -> screen.goto.
# --------------------------------------------------------------------


async def test_action_dispatch_navigate_calls_screen(fake_screen):
    tool_use_iter = make_tool_use_stream(
        tool_id="n1",
        action="navigate",
        action_params={"url": "https://example.com"},
    )
    end_turn_iter = make_happy_path_stream(text="done")
    adapter, _client = _build_adapter(
        fake_screen=fake_screen,
        iterations=[tool_use_iter, end_turn_iter],
    )
    await _consume(adapter)

    assert fake_screen.goto_calls == ["https://example.com"]


# --------------------------------------------------------------------
# T6: action dispatch: type -> screen.type_text.
# --------------------------------------------------------------------


async def test_action_dispatch_type_calls_screen(fake_screen):
    tool_use_iter = make_tool_use_stream(
        tool_id="ty1",
        action="type",
        action_params={"text": "hello world"},
    )
    end_turn_iter = make_happy_path_stream(text="done")
    adapter, _client = _build_adapter(
        fake_screen=fake_screen,
        iterations=[tool_use_iter, end_turn_iter],
    )
    await _consume(adapter)

    assert fake_screen.type_calls == ["hello world"]


# --------------------------------------------------------------------
# T7: step cap (max_steps=1) -> StreamError(step_cap_exceeded).
#     With the happy-path fake terminating end_turn, after 1 iteration
#     the post-iteration step check fires.
# --------------------------------------------------------------------


async def test_step_cap_aborts_with_screen_aclose(fake_screen):
    adapter, _client = _build_adapter(
        fake_screen=fake_screen,
        iterations=[
            make_happy_path_stream(text="hi"),
            # Second iteration available in case the cap fires AFTER a
            # tool_use stop_reason (defensive — happy-path uses end_turn
            # so we never reach this).
            make_happy_path_stream(text="extra"),
        ],
        max_steps=1,
    )
    chunks = await _consume(
        adapter,
        options=AdapterOptions(max_steps=1),
    )

    step_errors = [
        c for c in chunks
        if isinstance(c, StreamError) and c.code == "step_cap_exceeded"
    ]
    assert len(step_errors) == 1
    assert step_errors[0].retriable is False
    assert isinstance(chunks[-1], Done)
    # Screen always closes (BACKEND-07 + Pitfall 5).
    assert fake_screen.aclose_count == 1


# --------------------------------------------------------------------
# T8: cost cap (max_cost_usd=0.000001) -> StreamError(cost_cap_exceeded).
#     With anthropic/claude-opus-4-7 (or _default) rates and the
#     fake's input=10/output=5 usage, the cap trips after the first
#     iteration's usage is recorded.
# --------------------------------------------------------------------


async def test_cost_cap_aborts(fake_screen):
    adapter, _client = _build_adapter(
        fake_screen=fake_screen,
        iterations=[
            make_happy_path_stream(text="hi"),
            make_happy_path_stream(text="extra"),
        ],
        max_cost_usd=0.000001,
    )
    chunks = await _consume(adapter)

    cost_errors = [
        c for c in chunks
        if isinstance(c, StreamError) and c.code == "cost_cap_exceeded"
    ]
    assert len(cost_errors) == 1
    assert cost_errors[0].retriable is False
    assert isinstance(chunks[-1], Done)
    assert fake_screen.aclose_count == 1


# --------------------------------------------------------------------
# T9: cancellation within 2s.
# --------------------------------------------------------------------


class _SlowFakeBetaMessages:
    """Inject a deliberate sleep into stream() so cancellation can race."""

    def __init__(self) -> None:
        self.stream_calls: list[dict] = []

    def stream(self, **kw):
        self.stream_calls.append(dict(kw))
        return _SlowFakeStream()


class _SlowFakeStream:
    async def __aenter__(self):
        # Sleep long enough that cancel() can race us.
        await asyncio.sleep(5.0)
        return self

    async def __aexit__(self, *_exc):
        return None

    def __aiter__(self):
        async def gen():
            return
            yield  # unreachable but makes this an async generator

        return gen()

    async def get_final_message(self):
        return FakeFinalMessage(stop_reason="end_turn")


@pytest.mark.timeout(2)
async def test_cancellation_within_2s_calls_screen_aclose(fake_screen):
    """Pattern 7 + PEP 789: CancelledError -> terminal pair + raise.

    The slow fake sleeps inside ``__aenter__`` so the adapter's
    ``async with self._client.beta.messages.stream(...)`` blocks. We
    cancel after 50 ms — the CancelledError propagates into the
    adapter's except block, which emits StreamError + Done + raise.
    The finally block calls screen.aclose() within the 2-second budget.
    """

    slow_client = type("SlowClient", (), {})()
    slow_client.beta = type("Beta", (), {})()
    slow_client.beta.messages = _SlowFakeBetaMessages()

    adapter = ComputerUseAdapter(
        api_key="fake",
        max_cost_usd=0.50,
        max_steps=15,
        client_factory=lambda api_key: slow_client,
        screen_factory=lambda **kw: fake_screen,
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

    # The contract: screen.aclose was called even though we cancelled
    # mid-stream. Chunks may or may not contain Done depending on the
    # exact race — but if any did land, the last MUST be Done.
    assert fake_screen.aclose_count == 1
    if chunks:
        assert isinstance(chunks[-1], Done)


# --------------------------------------------------------------------
# T10: AuthenticationError mid-stream -> StreamError(auth_failed).
# --------------------------------------------------------------------


def _make_auth_error() -> anthropic.AuthenticationError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status_code=401, request=request)
    return anthropic.AuthenticationError(
        message="bad key",
        response=response,
        body=None,
    )


def _make_api_status_error(status_code: int) -> anthropic.APIStatusError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status_code=status_code, request=request)
    return anthropic.APIStatusError(
        message=f"status {status_code}",
        response=response,
        body=None,
    )


async def test_auth_error_emits_auth_failed(fake_screen):
    raising_stream = FakeAsyncMessageStream(
        events=[],
        final_message=FakeFinalMessage(),
        raise_on_enter=_make_auth_error(),
    )
    adapter, _client = _build_adapter(
        fake_screen=fake_screen,
        iterations=[raising_stream],
    )
    chunks = await _consume(adapter)

    auth_errors = [
        c for c in chunks
        if isinstance(c, StreamError) and c.code == "auth_failed"
    ]
    assert len(auth_errors) == 1
    assert auth_errors[0].retriable is False
    assert isinstance(chunks[-1], Done)


# --------------------------------------------------------------------
# T11: APIStatusError(429) -> StreamError(rate_limited, retriable=True).
# --------------------------------------------------------------------


async def test_rate_limit_429_emits_retriable(fake_screen):
    raising_stream = FakeAsyncMessageStream(
        events=[],
        final_message=FakeFinalMessage(),
        raise_on_enter=_make_api_status_error(429),
    )
    adapter, _client = _build_adapter(
        fake_screen=fake_screen,
        iterations=[raising_stream],
    )
    chunks = await _consume(adapter)

    rate_errors = [
        c for c in chunks
        if isinstance(c, StreamError) and c.code == "rate_limited"
    ]
    assert len(rate_errors) == 1
    assert rate_errors[0].retriable is True
    assert isinstance(chunks[-1], Done)


# --------------------------------------------------------------------
# T12: APIStatusError(503) -> StreamError(provider_unavailable).
# --------------------------------------------------------------------


async def test_503_emits_provider_unavailable(fake_screen):
    raising_stream = FakeAsyncMessageStream(
        events=[],
        final_message=FakeFinalMessage(),
        raise_on_enter=_make_api_status_error(503),
    )
    adapter, _client = _build_adapter(
        fake_screen=fake_screen,
        iterations=[raising_stream],
    )
    chunks = await _consume(adapter)

    prov_errors = [
        c for c in chunks
        if isinstance(c, StreamError) and c.code == "provider_unavailable"
    ]
    assert len(prov_errors) == 1
    # Pattern 5 line 1094 sets retriable=(code == "rate_limited") in
    # the adapter except block — so provider_unavailable is
    # retriable=False (not retriable). The base PROVIDER_ERROR_MAP in
    # errors.py says retriable=True for APIStatusError; the adapter
    # OVERRIDES that for the 429-vs-everything-else branch (so the
    # adapter, not the map, is the authoritative source of truth for
    # the 503 case). Mirrors apps/api/backends/openrouter/adapter.py
    # line 339.
    assert prov_errors[0].retriable is False
    assert isinstance(chunks[-1], Done)


# --------------------------------------------------------------------
# T13: routing_signals passed through to Done.
# --------------------------------------------------------------------


async def test_routing_signals_passed_through(fake_screen):
    signals = {"task_type": "browse", "agentic_intent": True}
    adapter, _client = _build_adapter(
        fake_screen=fake_screen,
        iterations=[make_happy_path_stream(text="ok")],
    )
    chunks = await _consume(
        adapter,
        options=AdapterOptions(routing_signals=signals),
    )

    done = chunks[-1]
    assert isinstance(done, Done)
    assert done.routing_signals == signals


# --------------------------------------------------------------------
# T14: PlaywrightScreen()._headless is True (anti-pattern 1727 regression).
# --------------------------------------------------------------------


def test_default_headless_true():
    """Anti-pattern regression: Chromium MUST default to headless.

    A debug toggle exists in the constructor signature so a developer
    can opt in for manual inspection (headless=False), but the default
    is firmly True per RESEARCH anti-pattern line 1727.
    """

    s = PlaywrightScreen(viewport=(800, 600))
    assert s._headless is True


# --------------------------------------------------------------------
# T15: ComputerUseAdapter._viewport defaults to (1280, 800).
# --------------------------------------------------------------------


def test_default_viewport_1280_800(monkeypatch):
    """CONTEXT specifics line 262 — D-13 locks 1280×800.

    Construct via fake factories so we don't trip the real
    AsyncAnthropic / PlaywrightScreen build.
    """

    monkeypatch.setenv("COMPUTER_USE_OPT_IN", "1")
    adapter = ComputerUseAdapter(
        api_key="fake",
        client_factory=lambda api_key: object(),
        screen_factory=lambda **kw: object(),
    )
    assert adapter._viewport == (1280, 800)
    assert DEFAULT_VIEWPORT == (1280, 800)


# --------------------------------------------------------------------
# Bonus T16: BETA_HEADER module constant lock + literal recognized in
# the stream call kwargs.
# --------------------------------------------------------------------


def test_beta_header_constant_locked():
    """Regression on the literal BETA_HEADER value (BACKEND-05)."""

    assert BETA_HEADER == "computer-use-2025-11-24"


# --------------------------------------------------------------------
# Bonus T17: text_delta with empty string does NOT yield a TextDelta.
# Reduces UI noise for keep-alive deltas; consistent with the OpenRouter
# adapter's getattr(delta, "content", None) guard.
# --------------------------------------------------------------------


async def test_empty_text_delta_is_not_yielded(fake_screen):
    iter1 = FakeAsyncMessageStream(
        events=[
            FakeAnthropicEvent(
                type="content_block_delta",
                delta=FakeAnthropicDelta(type="text_delta", text=""),
            ),
        ],
        final_message=FakeFinalMessage(stop_reason="end_turn"),
    )
    adapter, _client = _build_adapter(
        fake_screen=fake_screen,
        iterations=[iter1],
    )
    chunks = await _consume(adapter)

    text_deltas = [c for c in chunks if isinstance(c, TextDelta)]
    assert text_deltas == []
    assert isinstance(chunks[-1], Done)


# --------------------------------------------------------------------
# Bonus T18: usage block is recorded (cost cap arithmetic correctness).
# --------------------------------------------------------------------


async def test_iteration_usage_recorded(fake_screen):
    """The fake's input_tokens=10 / output_tokens=5 should be tracked."""

    adapter, _client = _build_adapter(
        fake_screen=fake_screen,
        iterations=[make_happy_path_stream(text="ok")],
    )
    chunks = await _consume(adapter)

    done = chunks[-1]
    assert isinstance(done, Done)
    assert done.tokens_in == 10
    assert done.tokens_out == 5
    # cost_usd should be > 0 (rates are non-zero in pricing.json).
    assert done.cost_usd is not None and done.cost_usd > 0


# ----------------------------------------------------------------
# CR-02 regression: record_iteration_usage OVERRIDES (not accumulates)
# the running input/output token tally. Cache counters still
# accumulate.
# ----------------------------------------------------------------


def test_record_iteration_usage_overrides_running_estimate(
    pricing_table,
) -> None:
    """40 chars of text_delta -> 10 estimated output tokens.
    Then record_iteration_usage(input_tokens=10, output_tokens=5)
    MUST override the tally to (10, 5), not accumulate to (10, 15).

    Mirrors VERIFICATION.md CR-02 reproduction (Truth 22)."""

    from apps.api.backends.computer_use.cost import (
        ComputerUseCostTracker,
    )

    tracker = ComputerUseCostTracker(
        model_id="claude-opus-4-7",
        max_cost_usd=0.50,
        pricing=pricing_table,
    )

    tracker.record_output_text("x" * 40)
    # Sanity: 40 // 4 = 10 estimated output tokens, 0 input.
    assert tracker.tokens_in() == 0
    assert tracker.tokens_out() == 10

    tracker.record_iteration_usage(
        input_tokens=10,
        output_tokens=5,
    )

    # Override semantics — provider numbers REPLACE the estimate.
    assert tracker.tokens_in() == 10
    assert tracker.tokens_out() == 5


# =====================================================================
# Phase 9 Wave-0 RED test slices — DEBT-01 (wait clamp), DEBT-03
# (url scheme), DEBT-02 (cost_cap_zero)
# =====================================================================
#
# Scaffolded RED for Phase 9 (VALIDATION.md rows DEBT-01/02/03). Each
# asserts the TARGET behavior the engineering wave will land and is
# gated with an imperative ``pytest.xfail(...)`` so the slice is
# COLLECTABLE by its ``-k`` selector (wait_clamp / url_scheme /
# cost_cap_zero) and reports ``xfail`` (NOT error, NOT pass) against the
# unmodified adapter. The owning plan removes the ``pytest.xfail(...)``
# line when the fix lands.


async def test_wait_clamp_duration_ceiling(fake_screen):
    """DEBT-01 (-k wait_clamp): a computer-use ``wait`` action duration is
    clamped to a ceiling (WR-01 unbounded-sleep fix).

    Target behavior: when the model issues a ``wait`` action with a
    large/arbitrary duration, the adapter clamps it to a bounded ceiling
    before calling ``screen``. Today the duration flows through
    unbounded — a malicious/confused model could stall the turn for an
    arbitrary time.
    """

    # A tool-use stream issuing a wait with an absurd duration.
    adapter, _client = _build_adapter(
        fake_screen=fake_screen,
        iterations=[
            make_tool_use_stream(
                action="wait",
                action_params={"duration": 100_000},
            ),
            make_happy_path_stream(text="done"),
        ],
    )

    await _consume(adapter)

    # The clamped duration handed to the screen must not exceed the
    # ceiling (the exact ceiling constant lands with the fix).
    assert fake_screen.wait_calls, "expected the wait action to reach the screen"
    assert max(fake_screen.wait_calls) <= 30.0, (
        "wait duration must be clamped to a bounded ceiling (DEBT-01)"
    )


async def test_navigation_url_scheme_rejected(fake_screen):
    """DEBT-03: a navigate action to a dangerous URL scheme is rejected
    BEFORE ``screen.goto`` (WR-09 arbitrary-scheme fix).

    Target behavior: ``file://``, ``data:``, and ``chrome://`` are
    rejected; only ``http``/``https`` reach ``goto``. A rejected
    navigation surfaces a ``validation_error`` StreamError and never
    calls ``screen.goto`` with the dangerous URL.
    """

    adapter, _client = _build_adapter(
        fake_screen=fake_screen,
        iterations=[
            make_tool_use_stream(
                action="navigate",
                action_params={"url": "file:///etc/passwd"},
            ),
            make_happy_path_stream(text="blocked"),
        ],
    )

    chunks = await _consume(adapter)

    # screen.goto must NEVER be called with the file:// URL.
    assert all(
        not str(u).startswith("file://") for u in fake_screen.goto_calls
    ), "file:// navigation must be rejected before screen.goto (DEBT-03)"
    validation_errors = [
        c
        for c in chunks
        if isinstance(c, StreamError) and c.code == "validation_error"
    ]
    assert validation_errors, (
        "a rejected URL scheme must surface a validation_error StreamError"
    )


async def test_cost_cap_zero_honored(fake_screen):
    """DEBT-02 (-k cost_cap_zero, computer-use): ``max_cost_usd=0.0`` is
    HONORED, not treated as falsy and replaced by the adapter default.

    Today ``max_cost_usd = options.max_cost_usd or self._max_cost``
    means a caller-supplied ``0.0`` falls through to the 0.50 default
    (the falsy-0 bug). Target behavior: a 0.0 cap means the FIRST token
    of spend trips ``cost_cap_exceeded``.
    """

    # Default adapter cap is 0.50; pass an explicit 0.0 via options.
    adapter, _client = _build_adapter(
        fake_screen=fake_screen,
        iterations=[
            make_happy_path_stream(text="hi"),
            make_happy_path_stream(text="extra"),
        ],
        max_cost_usd=0.50,
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
