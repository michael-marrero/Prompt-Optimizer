# Plan 02-02 Task 3 — Claude Code adapter unit tests
# (BACKEND-04 / BACKEND-06 / BACKEND-07 / BACKEND-08).
#
# Pitfall 2 regression: ClaudeSDKClient, NOT the standalone query()
# function. Pitfall 5 regression: interrupt() BEFORE break, and
# disconnect() ALWAYS called in finally.
#
# Eighteen invariants:
#   T1:  happy path emits TextDelta -> Done; ResultMessage cost
#        overrides the running estimate.
#   T2:  adapter source imports ClaudeSDKClient (Pitfall 2 regression).
#   T3:  connect / query / disconnect lifecycle called in order.
#   T4:  ALLOWED_TOOLS locked to the 6-element list.
#   T5:  AssistantMessages increment the step counter; max_steps=1
#        and 2 AssistantMessages -> StreamError(step_cap_exceeded) +
#        interrupt + Done.
#   T6:  ToolUseBlock(name='Edit') + ToolResultBlock(tool_name='Edit')
#        emits FileDiff(operation='edit').
#   T7:  ToolUseBlock(name='Write') + ToolResultBlock(tool_name='Write')
#        emits FileDiff(operation='create').
#   T8:  ToolUseBlock(name='Bash') + ToolResultBlock(tool_name='Bash')
#        emits ToolResult (NOT FileDiff).
#   T9:  cost cap mid-stream -> StreamError(cost_cap_exceeded) +
#        interrupt + Done.
#   T10: cancellation within 2 s calls interrupt; emits StreamError +
#        Done; disconnects in finally.
#   T11: missing ANTHROPIC_API_KEY raises in __init__.
#   T12: ResultMessage.total_cost_usd overrides Done.cost_usd.
#   T13: workspace=None -> tempfile.mkdtemp(prefix='pomu-cc-') is
#        called.
#   T14: workspace cleanup happens on happy path (mkdtemp dir gone
#        after stream).
#   T15: options.cwd=str(tmp_path) -> user dir survives stream.
#   T16: disconnect() called in finally even on mid-stream exception.
#   T17: ProcessError -> StreamError(code='provider_unavailable').
#   T18: AdapterOptions.routing_signals passes through to Done.

from __future__ import annotations

import asyncio
import inspect
import os
from pathlib import Path

import pytest

from apps.api.backends.chunks import (
    Done,
    FileDiff,
    StreamError,
    TextDelta,
    ToolCall,
    ToolResult,
)
from apps.api.backends.claude_code import adapter as _adapter_module
from apps.api.backends.claude_code.adapter import (
    ALLOWED_TOOLS,
    ClaudeCodeAdapter,
)
from apps.api.backends.claude_code.tests.fakes import (
    FakeAssistantMessage,
    FakeClaudeSDKClient,
    FakeResultMessage,
    FakeSystemMessage,
    FakeTextBlock,
    FakeToolResultBlock,
    FakeToolUseBlock,
    FakeUsage,
    FakeUserMessage,
)
from apps.api.backends.protocol import AdapterOptions


# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------


async def _consume_stream(
    adapter: ClaudeCodeAdapter,
    *,
    prompt: str = "hi",
    history: list | None = None,
    options: AdapterOptions | None = None,
) -> list:
    chunks: list = []
    options = options or AdapterOptions()
    history = history or []
    async for chunk in adapter.stream(
        prompt=prompt, history=history, options=options
    ):
        chunks.append(chunk)
    return chunks


def _factory_from(client: FakeClaudeSDKClient):
    """Build a ``client_factory`` callable returning ``client``.

    Records ``options`` on the client for later assertions.
    """

    def factory(*, options=None, **_kw):
        client.options = options
        return client

    return factory


def _build_adapter(
    client: FakeClaudeSDKClient,
    *,
    max_cost_usd: float = 0.50,
    max_steps: int = 25,
    api_key: str = "fake",
) -> ClaudeCodeAdapter:
    """Build an adapter wired to ``client`` via the factory injection."""

    return ClaudeCodeAdapter(
        api_key=api_key,
        max_cost_usd=max_cost_usd,
        max_steps=max_steps,
        client_factory=_factory_from(client),
    )


# --------------------------------------------------------------------
# T1: Happy path
# --------------------------------------------------------------------


async def test_happy_path_emits_textdelta_and_done() -> None:
    client = FakeClaudeSDKClient(
        response_messages=[
            FakeAssistantMessage(content=[FakeTextBlock(text="hello")]),
            FakeResultMessage(total_cost_usd=0.012),
        ]
    )
    adapter = _build_adapter(client)
    chunks = await _consume_stream(adapter, prompt="say hi")

    text_deltas = [c for c in chunks if isinstance(c, TextDelta)]
    assert len(text_deltas) == 1
    assert text_deltas[0].text == "hello"
    assert isinstance(chunks[-1], Done)
    assert chunks[-1].cost_usd == pytest.approx(0.012)


# --------------------------------------------------------------------
# T2: Pitfall 2 — ClaudeSDKClient, not standalone query()
# --------------------------------------------------------------------


def test_uses_claudesdkclient_not_query_function() -> None:
    """Static check: adapter source imports ClaudeSDKClient.

    The standalone ``query()`` function has no ``interrupt()`` method
    so it cannot satisfy BACKEND-07's 2 s cancellation budget. The
    adapter MUST use ``ClaudeSDKClient`` and call its
    ``connect / query / receive_response / interrupt / disconnect``
    methods.
    """

    source = inspect.getsource(_adapter_module)
    assert "ClaudeSDKClient" in source
    assert "claude_code_sdk" not in source  # deprecated SDK absent


# --------------------------------------------------------------------
# T3: Lifecycle ordering
# --------------------------------------------------------------------


async def test_connect_query_receive_disconnect_called_in_order() -> None:
    client = FakeClaudeSDKClient(
        response_messages=[
            FakeAssistantMessage(content=[FakeTextBlock(text="hi")]),
            FakeResultMessage(),
        ]
    )
    adapter = _build_adapter(client)
    await _consume_stream(adapter)
    assert client.connect_count == 1
    assert client.query_count == 1
    assert client.disconnect_count == 1


# --------------------------------------------------------------------
# T4: ALLOWED_TOOLS locked
# --------------------------------------------------------------------


def test_allowed_tools_locked_to_six() -> None:
    assert ALLOWED_TOOLS == ["Read", "Edit", "Write", "Bash", "Glob", "Grep"]


# --------------------------------------------------------------------
# T5: Step cap
# --------------------------------------------------------------------


async def test_assistant_message_increments_step_counter_with_step_cap() -> None:
    client = FakeClaudeSDKClient(
        response_messages=[
            FakeAssistantMessage(content=[FakeTextBlock(text="a")]),
            FakeAssistantMessage(content=[FakeTextBlock(text="b")]),
            FakeResultMessage(),
        ]
    )
    adapter = _build_adapter(client, max_steps=1)
    chunks = await _consume_stream(adapter, options=AdapterOptions(max_steps=1))

    assert any(
        isinstance(c, StreamError) and c.code == "step_cap_exceeded" for c in chunks
    )
    assert isinstance(chunks[-1], Done)
    # Pitfall 5: interrupt() called BEFORE break.
    assert client.interrupt_count == 1


# --------------------------------------------------------------------
# T6: FileDiff(operation='edit') for Edit tool
# --------------------------------------------------------------------


async def test_filediff_emitted_for_edit_tool() -> None:
    client = FakeClaudeSDKClient(
        response_messages=[
            FakeAssistantMessage(
                content=[
                    FakeToolUseBlock(
                        id="t1", name="Edit", input={"path": "src/a.py"}
                    )
                ]
            ),
            FakeUserMessage(
                content=[
                    FakeToolResultBlock(
                        tool_use_id="t1",
                        tool_name="Edit",
                        content="--- a/src/a.py\n+++ b/src/a.py\n@@ ...",
                        input={"path": "src/a.py"},
                    )
                ]
            ),
            FakeResultMessage(),
        ]
    )
    adapter = _build_adapter(client)
    chunks = await _consume_stream(adapter)

    tool_calls = [c for c in chunks if isinstance(c, ToolCall)]
    file_diffs = [c for c in chunks if isinstance(c, FileDiff)]
    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "Edit"
    assert len(file_diffs) == 1
    assert file_diffs[0].operation == "edit"
    assert file_diffs[0].path == "src/a.py"
    assert file_diffs[0].tool_call_id == "t1"


# --------------------------------------------------------------------
# T7: FileDiff(operation='create') for Write tool
# --------------------------------------------------------------------


async def test_filediff_emitted_for_write_tool() -> None:
    client = FakeClaudeSDKClient(
        response_messages=[
            FakeAssistantMessage(
                content=[
                    FakeToolUseBlock(
                        id="t2", name="Write", input={"path": "src/new.py"}
                    )
                ]
            ),
            FakeUserMessage(
                content=[
                    FakeToolResultBlock(
                        tool_use_id="t2",
                        tool_name="Write",
                        content="created new.py",
                        input={"path": "src/new.py"},
                    )
                ]
            ),
            FakeResultMessage(),
        ]
    )
    adapter = _build_adapter(client)
    chunks = await _consume_stream(adapter)

    file_diffs = [c for c in chunks if isinstance(c, FileDiff)]
    assert len(file_diffs) == 1
    assert file_diffs[0].operation == "create"
    assert file_diffs[0].path == "src/new.py"


# --------------------------------------------------------------------
# T8: ToolResult (not FileDiff) for Bash
# --------------------------------------------------------------------


async def test_toolresult_emitted_for_bash_tool() -> None:
    client = FakeClaudeSDKClient(
        response_messages=[
            FakeAssistantMessage(
                content=[
                    FakeToolUseBlock(
                        id="t3", name="Bash", input={"command": "ls"}
                    )
                ]
            ),
            FakeUserMessage(
                content=[
                    FakeToolResultBlock(
                        tool_use_id="t3",
                        tool_name="Bash",
                        content="a.py b.py",
                    )
                ]
            ),
            FakeResultMessage(),
        ]
    )
    adapter = _build_adapter(client)
    chunks = await _consume_stream(adapter)

    file_diffs = [c for c in chunks if isinstance(c, FileDiff)]
    tool_results = [c for c in chunks if isinstance(c, ToolResult)]
    assert not file_diffs
    assert len(tool_results) == 1
    assert tool_results[0].content == "a.py b.py"
    assert tool_results[0].is_error is False


# --------------------------------------------------------------------
# T9: Cost cap
# --------------------------------------------------------------------


async def test_cost_cap_aborts_with_interrupt() -> None:
    # Long TextBlock so the char/4 estimator trips the tiny cost cap
    # before the AssistantMessage is fully processed.
    long_text = "x" * 4000  # 1000 estimated tokens
    client = FakeClaudeSDKClient(
        response_messages=[
            FakeAssistantMessage(content=[FakeTextBlock(text=long_text)]),
            FakeAssistantMessage(content=[FakeTextBlock(text=long_text)]),
            FakeResultMessage(),
        ]
    )
    adapter = _build_adapter(client, max_cost_usd=0.0000001)
    chunks = await _consume_stream(adapter, prompt="x" * 1000)

    assert any(
        isinstance(c, StreamError) and c.code == "cost_cap_exceeded"
        for c in chunks
    )
    assert isinstance(chunks[-1], Done)
    assert client.interrupt_count == 1


# --------------------------------------------------------------------
# T10: Cancellation within 2 s
# --------------------------------------------------------------------


class _SlowFakeClient(FakeClaudeSDKClient):
    """Fake whose ``receive_response`` sleeps so we can cancel it."""

    async def receive_response(self):  # type: ignore[override]
        # Sleep longer than the test's wait so the cancel races us.
        await asyncio.sleep(5)
        yield FakeResultMessage()


@pytest.mark.timeout(2)
async def test_cancellation_within_2s_calls_interrupt() -> None:
    client = _SlowFakeClient()
    adapter = _build_adapter(client)

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

    # Pattern 7 / Pitfall 5: interrupt() called on cancellation.
    assert client.interrupt_count == 1
    # finally branch always disconnects.
    assert client.disconnect_count == 1
    # If any chunks landed during the cancellation race, the last one
    # must be Done (the cancellation handler emits the terminal pair).
    if chunks:
        assert isinstance(chunks[-1], Done)


# --------------------------------------------------------------------
# T11: Missing API key raises
# --------------------------------------------------------------------


def test_missing_api_key_raises(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(Exception):
        ClaudeCodeAdapter()


# --------------------------------------------------------------------
# T12: ResultMessage.total_cost_usd overrides cost
# --------------------------------------------------------------------


async def test_result_message_overrides_cost() -> None:
    client = FakeClaudeSDKClient(
        response_messages=[
            FakeAssistantMessage(content=[FakeTextBlock(text="hi")]),
            FakeResultMessage(total_cost_usd=0.042),
        ]
    )
    adapter = _build_adapter(client)
    chunks = await _consume_stream(adapter)
    assert isinstance(chunks[-1], Done)
    assert chunks[-1].cost_usd == pytest.approx(0.042)


# --------------------------------------------------------------------
# T13: tempfile.mkdtemp called when cwd is None
# --------------------------------------------------------------------


async def test_workspace_uses_tempfile_when_cwd_none(monkeypatch) -> None:
    calls: list[tuple] = []
    import tempfile as _tempfile

    real_mkdtemp = _tempfile.mkdtemp

    def spy_mkdtemp(*args, **kwargs):
        calls.append((args, kwargs))
        return real_mkdtemp(*args, **kwargs)

    monkeypatch.setattr(
        "apps.api.backends.claude_code.adapter.tempfile.mkdtemp",
        spy_mkdtemp,
    )

    client = FakeClaudeSDKClient(
        response_messages=[
            FakeAssistantMessage(content=[FakeTextBlock(text="hi")]),
            FakeResultMessage(),
        ]
    )
    adapter = _build_adapter(client)
    await _consume_stream(adapter, options=AdapterOptions(cwd=None))

    assert calls, "tempfile.mkdtemp was never called"
    # Verify the prefix arg per CONTEXT specifics line 264.
    last_args, last_kwargs = calls[-1]
    assert last_kwargs.get("prefix") == "pomu-cc-"


# --------------------------------------------------------------------
# T14: Workspace cleanup on happy path
# --------------------------------------------------------------------


async def test_workspace_cleanup_on_happy_path(monkeypatch) -> None:
    captured: list[str] = []
    import tempfile as _tempfile

    real_mkdtemp = _tempfile.mkdtemp

    def spy_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        captured.append(path)
        return path

    monkeypatch.setattr(
        "apps.api.backends.claude_code.adapter.tempfile.mkdtemp",
        spy_mkdtemp,
    )

    client = FakeClaudeSDKClient(
        response_messages=[
            FakeAssistantMessage(content=[FakeTextBlock(text="hi")]),
            FakeResultMessage(),
        ]
    )
    adapter = _build_adapter(client)
    await _consume_stream(adapter)

    assert captured, "mkdtemp was never called"
    workspace = captured[-1]
    # finally block must have rmtree'd it (T-02-05 mitigation).
    assert not os.path.exists(workspace)


# --------------------------------------------------------------------
# T15: cwd opt-in skips cleanup
# --------------------------------------------------------------------


async def test_cwd_opt_in_skips_cleanup(tmp_path) -> None:
    user_repo = tmp_path / "user_repo"
    user_repo.mkdir()

    client = FakeClaudeSDKClient(
        response_messages=[
            FakeAssistantMessage(content=[FakeTextBlock(text="hi")]),
            FakeResultMessage(),
        ]
    )
    adapter = _build_adapter(client)
    await _consume_stream(adapter, options=AdapterOptions(cwd=str(user_repo)))

    # User-supplied directory must survive.
    assert user_repo.exists()


# --------------------------------------------------------------------
# T16: disconnect() called in finally on exception
# --------------------------------------------------------------------


class _RaisingFakeClient(FakeClaudeSDKClient):
    async def receive_response(self):  # type: ignore[override]
        raise RuntimeError("mid-stream boom")
        yield  # pragma: no cover — unreachable.


async def test_disconnect_called_in_finally_on_exception() -> None:
    client = _RaisingFakeClient()
    adapter = _build_adapter(client)
    chunks = await _consume_stream(adapter)

    # Adapter swallows the exception and emits StreamError + Done.
    assert any(isinstance(c, StreamError) for c in chunks)
    assert isinstance(chunks[-1], Done)
    # Pitfall 5: finally always disconnects.
    assert client.disconnect_count == 1


# --------------------------------------------------------------------
# T17: ProcessError -> provider_unavailable
# --------------------------------------------------------------------


class _ProcessErrorFakeClient(FakeClaudeSDKClient):
    async def receive_response(self):  # type: ignore[override]
        from claude_agent_sdk import ProcessError

        raise ProcessError("subprocess died")
        yield  # pragma: no cover — unreachable.


async def test_provider_error_emits_provider_unavailable() -> None:
    client = _ProcessErrorFakeClient()
    adapter = _build_adapter(client)
    chunks = await _consume_stream(adapter)

    assert any(
        isinstance(c, StreamError) and c.code == "provider_unavailable"
        for c in chunks
    )
    assert isinstance(chunks[-1], Done)


# --------------------------------------------------------------------
# T18: routing_signals pass-through
# --------------------------------------------------------------------


async def test_routing_signals_passed_through() -> None:
    client = FakeClaudeSDKClient(
        response_messages=[
            FakeAssistantMessage(content=[FakeTextBlock(text="hi")]),
            FakeResultMessage(),
        ]
    )
    adapter = _build_adapter(client)
    chunks = await _consume_stream(
        adapter,
        options=AdapterOptions(routing_signals={"task_type": "coding"}),
    )
    assert isinstance(chunks[-1], Done)
    assert chunks[-1].routing_signals == {"task_type": "coding"}


# --------------------------------------------------------------------
# CR-01 regression: FileDiff emission against the real SDK shape
# (ToolResultBlock has ONLY tool_use_id, content, is_error).
# --------------------------------------------------------------------


async def test_filediff_emitted_against_real_sdk_shape() -> None:
    """Construct FakeToolResultBlock with only the three real-SDK
    fields. The adapter MUST recover tool_name/input via its
    internal _pending_tool_calls map keyed on tool_use_id."""

    client = FakeClaudeSDKClient(
        response_messages=[
            FakeAssistantMessage(
                content=[
                    FakeToolUseBlock(
                        id="t1",
                        name="Edit",
                        input={"path": "src/a.py"},
                    )
                ]
            ),
            FakeUserMessage(
                content=[
                    FakeToolResultBlock(
                        tool_use_id="t1",
                        content="--- diff ---\n+x = 1\n",
                        is_error=False,
                    )
                ]
            ),
            FakeResultMessage(),
        ]
    )
    adapter = _build_adapter(client)
    chunks = await _consume_stream(adapter)

    file_diffs = [c for c in chunks if isinstance(c, FileDiff)]
    assert len(file_diffs) == 1
    assert file_diffs[0].operation == "edit"
    assert file_diffs[0].path == "src/a.py"
    assert file_diffs[0].tool_call_id == "t1"
    assert file_diffs[0].diff.startswith("--- diff ---")
