"""Test fakes for the Claude Code adapter — duck-typed substitutes for
``claude_agent_sdk.ClaudeSDKClient`` and its message / block dataclasses.

Public surface (Plan 02-02 Task 1):

    FakeTextBlock           ``text``
    FakeToolUseBlock        ``id`` + ``name`` + ``input``
    FakeToolResultBlock     ``tool_use_id`` + ``content`` + ``is_error``
                            (matches the real claude_agent_sdk 0.1.81
                            ToolResultBlock shape)
    FakeAssistantMessage    ``content`` (list) + optional ``usage``
    FakeUserMessage         ``content`` (list)
    FakeSystemMessage       ``subtype`` placeholder
    FakeResultMessage       ``total_cost_usd`` + optional ``usage``
    FakeUsage               ``input_tokens`` + ``output_tokens``
    FakeClaudeSDKClient     duck-typed substitute for ClaudeSDKClient
                            with ``connect_count`` / ``query_count`` /
                            ``interrupt_count`` / ``disconnect_count``
                            introspection hooks

The adapter uses duck typing on attribute access (``getattr(block, ...)``,
``getattr(msg, "content", [])``) rather than relying solely on
``isinstance`` against the SDK's class objects. Tests can therefore
inject the Fake* dataclasses directly without monkeypatching the
adapter's own SDK imports.

Cross-refs:
    - 02-RESEARCH.md §"Pattern 4" lines 664-868 (message/block shapes)
    - 02-PATTERNS.md "claude_code/tests/fakes.py" (canonical fake shape)
    - apps/api/backends/tests/conftest.py (shared D-19 fakes — same shape)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass
class FakeTextBlock:
    """Mirrors ``claude_agent_sdk.TextBlock``."""

    text: str = ""


@dataclass
class FakeToolUseBlock:
    """Mirrors ``claude_agent_sdk.ToolUseBlock``."""

    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class FakeToolResultBlock:
    """Mirrors ``claude_agent_sdk.ToolResultBlock``.

    Mirrors the real ``claude_agent_sdk==0.1.81`` ``ToolResultBlock``
    shape exactly: three fields only (``tool_use_id``, ``content``,
    ``is_error``). The adapter recovers the original ``tool_name`` and
    ``input`` by ``tool_use_id`` lookup against its own
    ``_pending_tool_calls`` map populated at ToolUseBlock emit time.

    Earlier revisions of this fake carried ``tool_name`` and ``input``
    fields, but those do NOT exist on the real SDK class — keeping
    them here masked the production bug fixed by Plan 02-05 (CR-01).
    """

    tool_use_id: str = ""
    content: Any = ""
    is_error: bool = False


@dataclass
class FakeThinkingBlock:
    """Mirrors ``claude_agent_sdk.ThinkingBlock``."""

    thinking: str = ""


@dataclass
class FakeUsage:
    """Mirrors the ``usage`` block on AssistantMessage / ResultMessage."""

    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class FakeAssistantMessage:
    """Mirrors ``claude_agent_sdk.AssistantMessage``."""

    content: list[Any] = field(default_factory=list)
    usage: Any = None


@dataclass
class FakeUserMessage:
    """Mirrors ``claude_agent_sdk.UserMessage``.

    In ``claude-agent-sdk`` UserMessages within a turn carry tool-result
    blocks that the SDK injects after executing a ToolUse on Claude's
    behalf (RESEARCH Pattern 4 lines 776-778).
    """

    content: list[Any] = field(default_factory=list)


@dataclass
class FakeSystemMessage:
    """Mirrors ``claude_agent_sdk.SystemMessage`` — the adapter logs and skips."""

    subtype: str = "system"
    content: list[Any] = field(default_factory=list)


@dataclass
class FakeResultMessage:
    """Mirrors ``claude_agent_sdk.ResultMessage``.

    ``total_cost_usd`` is the authoritative cost (D-15 / RESEARCH line
    1235); the adapter calls ``tracker.record_result(msg)`` and lets
    that override the running estimate.
    """

    total_cost_usd: float | None = 0.001
    usage: Any = None


class FakeClaudeSDKClient:
    """Duck-typed substitute for ``claude_agent_sdk.ClaudeSDKClient``.

    Tracks ``connect_count`` / ``query_count`` / ``interrupt_count`` /
    ``disconnect_count`` so tests can assert the adapter cleaned up
    correctly (Pitfall 5 regression: ``interrupt()`` BEFORE ``break``,
    ``disconnect()`` in ``finally``).

    Construct with ``response_messages=[msg, msg, ...]``; the iterator
    yields them in order. ``raise_on_receive`` lets a test simulate a
    mid-stream provider error.
    """

    def __init__(
        self,
        *,
        options: Any = None,
        response_messages: list[Any] | None = None,
        raise_on_receive: BaseException | None = None,
    ) -> None:
        self.options = options
        self._messages: list[Any] = list(response_messages or [])
        self._raise_on_receive = raise_on_receive

        # Introspection counters — tests assert on these.
        self.connect_count = 0
        self.query_count = 0
        self.interrupt_count = 0
        self.disconnect_count = 0
        self.query_prompts: list[str] = []

    async def connect(self) -> None:
        self.connect_count += 1

    async def query(self, prompt: str) -> None:
        self.query_count += 1
        self.query_prompts.append(prompt)

    async def receive_response(self) -> AsyncIterator[Any]:
        if self._raise_on_receive is not None:
            raise self._raise_on_receive
        for msg in self._messages:
            yield msg

    async def interrupt(self) -> None:
        self.interrupt_count += 1

    async def disconnect(self) -> None:
        self.disconnect_count += 1
