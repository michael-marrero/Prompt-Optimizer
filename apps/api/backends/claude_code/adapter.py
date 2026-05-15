"""Claude Code adapter — async build-and-edit via claude_agent_sdk.ClaudeSDKClient.

Public surface (BACKEND-04 + BACKEND-06 + BACKEND-07 + BACKEND-08):

    ALLOWED_TOOLS    Final[list[str]] = ["Read", "Edit", "Write",
                                         "Bash", "Glob", "Grep"]
    class ClaudeCodeAdapter:
        __init__(api_key=None, *, max_cost_usd, max_steps, client_factory=None)
        async def stream(prompt, history, options) -> AsyncIterator[ChatChunk]

Pipeline (5 stages, all inside one top-level try/except for V7 robustness):
    1. Preflight: env-var check (ANTHROPIC_API_KEY) — typed exception
       BEFORE stream returns (D-19 invariant #6).
    2. Per-turn workspace (BACKEND-08): ``options.cwd`` opt-in OR
       ``tempfile.mkdtemp(prefix="pomu-cc-")`` (CONTEXT specifics
       line 264). ``shutil.rmtree`` in ``finally`` for the mkdtemp
       branch (T-02-05 leak mitigation).
    3. ``ClaudeSDKClient.connect() / query(prompt=...) /
       receive_response()`` (NOT the standalone ``query()`` function —
       Pitfall 2: standalone query has no interrupt()).
    4. Per-message loop:
         * ``AssistantMessage`` → steps.increment(); for each Block:
             - TextBlock → tracker.record_output_text + yield TextDelta
             - ToolUseBlock → yield ToolCall
             - ThinkingBlock → continue (v1 drops thinking)
           Then ``tracker.record_assistant_usage(msg.usage)`` if present.
         * ``UserMessage`` → for each ToolResultBlock:
             - Edit/Write tool → yield FileDiff (D-02 specialisation)
             - else → yield ToolResult
         * ``ResultMessage`` → tracker.record_result(msg); break.
         * ``SystemMessage`` and unknown → logger.debug + continue.
       After each message: cap check.
         - steps.exceeded() → StreamError(step_cap_exceeded) +
           ``await client.interrupt()`` + break (Pitfall 5: interrupt
           BEFORE break so SDK closes the generator cleanly).
         - tracker.over_cap() → StreamError(cost_cap_exceeded) +
           ``await client.interrupt()`` + break.
    5. Terminal: Done chunk carrying tokens / cost / latency / signals.

Cancellation contract (Pattern 7 + PEP 789 + BACKEND-07):
    On asyncio.CancelledError: await client.interrupt(), emit
    StreamError(code="cancelled", retriable=True) + Done, then re-
    raise. The finally block calls client.disconnect() and rmtree's
    the workspace so the wire is released within the 2-second
    cancellation budget enforced by the D-19 contract suite.

Error contract (D-06 closed vocabulary):
    ProcessError       -> "provider_unavailable", retriable=False
    ClaudeSDKError     -> "internal_error", retriable=False
    other Exception    -> "internal_error", retriable=False
    All terminal: emit StreamError + Done, do NOT re-raise (let the
    generator finish via StopAsyncIteration).

Cross-refs:
    - 02-RESEARCH.md §"Pattern 4" lines 664-868 (canonical source)
    - 02-RESEARCH.md §"Pitfall 2" lines 1777-1785 (ClaudeSDKClient vs query)
    - 02-RESEARCH.md §"Pitfall 5" lines 1808-1819 (cleanup ordering)
    - 02-CONTEXT.md D-15 (one step = one AssistantMessage)
    - 02-CONTEXT.md discretion line 142 (ALLOWED_TOOLS lock)
    - apps/api/backends/openrouter/adapter.py (parallel implementation)
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, AsyncIterator, Final

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ClaudeSDKError,
    ProcessError,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from apps.api.backends.chunks import (
    ChatChunk,
    Done,
    FileDiff,
    StreamError,
    TextDelta,
    ToolCall,
    ToolResult,
)
from apps.api.backends.claude_code.cost import ClaudeCodeCostTracker
from apps.api.backends.claude_code.step_counter import (
    DEFAULT_STEP_CAP,
    StepCounter,
)
from apps.api.backends.cost import DEFAULT_PER_TURN_COST_USD
from apps.api.backends.pricing import PricingTable
from apps.api.backends.protocol import AdapterOptions, Message

logger = logging.getLogger(__name__)


# Class-name sets for duck-typed message / block dispatch. We match
# on ``type(obj).__name__`` so test fakes (FakeAssistantMessage,
# FakeTextBlock, ...) work without monkeypatching the SDK imports
# above. The SDK's own classes match by ``isinstance`` too — both
# paths are exercised below for redundancy.
_ASSISTANT_NAMES: Final[frozenset[str]] = frozenset(
    ["AssistantMessage", "FakeAssistantMessage"]
)
_USER_NAMES: Final[frozenset[str]] = frozenset(
    ["UserMessage", "FakeUserMessage"]
)
_SYSTEM_NAMES: Final[frozenset[str]] = frozenset(
    ["SystemMessage", "FakeSystemMessage"]
)
_RESULT_NAMES: Final[frozenset[str]] = frozenset(
    ["ResultMessage", "FakeResultMessage"]
)
_TEXT_BLOCK_NAMES: Final[frozenset[str]] = frozenset(
    ["TextBlock", "FakeTextBlock"]
)
_TOOL_USE_NAMES: Final[frozenset[str]] = frozenset(
    ["ToolUseBlock", "FakeToolUseBlock"]
)
_TOOL_RESULT_NAMES: Final[frozenset[str]] = frozenset(
    ["ToolResultBlock", "FakeToolResultBlock"]
)
_THINKING_NAMES: Final[frozenset[str]] = frozenset(
    ["ThinkingBlock", "FakeThinkingBlock"]
)


def _is_assistant(msg: object) -> bool:
    return isinstance(msg, AssistantMessage) or type(msg).__name__ in _ASSISTANT_NAMES


def _is_user(msg: object) -> bool:
    return isinstance(msg, UserMessage) or type(msg).__name__ in _USER_NAMES


def _is_system(msg: object) -> bool:
    return isinstance(msg, SystemMessage) or type(msg).__name__ in _SYSTEM_NAMES


def _is_result(msg: object) -> bool:
    return isinstance(msg, ResultMessage) or type(msg).__name__ in _RESULT_NAMES


def _is_text_block(block: object) -> bool:
    return isinstance(block, TextBlock) or type(block).__name__ in _TEXT_BLOCK_NAMES


def _is_tool_use(block: object) -> bool:
    return isinstance(block, ToolUseBlock) or type(block).__name__ in _TOOL_USE_NAMES


def _is_tool_result(block: object) -> bool:
    return isinstance(block, ToolResultBlock) or type(block).__name__ in _TOOL_RESULT_NAMES


def _is_thinking(block: object) -> bool:
    return isinstance(block, ThinkingBlock) or type(block).__name__ in _THINKING_NAMES


# Locked v1 tool restriction (CONTEXT discretion line 142). The
# ``Final`` annotation makes the mutability intent explicit — type
# checkers warn on reassignment. Order mirrors RESEARCH Pattern 4 line
# 697 verbatim so the acceptance-criteria grep matches exactly.
ALLOWED_TOOLS: Final[list[str]] = ["Read", "Edit", "Write", "Bash", "Glob", "Grep"]


# Resolve config/pricing.json once at import time.
# apps/api/backends/claude_code/adapter.py -> repo root is 4 parents up.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_PRICING_PATH = _REPO_ROOT / "config" / "pricing.json"


# Lazy singleton — load the static rate table once per process.
_PRICING_TABLE: PricingTable | None = None


def _get_pricing_table() -> PricingTable:
    """Lazy singleton accessor for the shared PricingTable.

    Loading the static table is cheap (~1 ms) but happens once per
    process instead of once per adapter construction. Mirrors the
    OpenRouter adapter's pattern (Plan 02-01 Decision #3).
    """

    global _PRICING_TABLE
    if _PRICING_TABLE is None:
        _PRICING_TABLE = PricingTable.from_static(_PRICING_PATH)
    return _PRICING_TABLE


def _missing_api_key_error() -> RuntimeError:
    """Construct the typed exception for missing ANTHROPIC_API_KEY.

    Used in the constructor preflight (D-19 invariant #6) — surfaces
    BEFORE any subprocess spawn so callers don't get a half-streamed
    error chunk for a missing-key situation.
    """

    return RuntimeError(
        "ANTHROPIC_API_KEY not set "
        "(set env var or pass api_key explicitly to ClaudeCodeAdapter)."
    )


class ClaudeCodeAdapter:
    """Claude Code backend adapter (BackendAdapter Protocol implementation).

    The adapter is constructed once per backend registry entry and
    streams one turn at a time via :meth:`stream`. ``client_factory``
    enables test injection: pass ``lambda options: FakeClaudeSDKClient(...)``
    to replace the real ``ClaudeSDKClient`` with a duck-typed fake.

    The SDK reads ``ANTHROPIC_API_KEY`` from ``os.environ`` directly —
    the ``api_key`` constructor argument is accepted for parity with
    the OpenRouter adapter but stored only so the preflight check has
    something to inspect. The SDK does not honour an ``api_key=`` kwarg.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        max_cost_usd: float = DEFAULT_PER_TURN_COST_USD,
        max_steps: int = DEFAULT_STEP_CAP,
        client_factory: Any = None,
    ) -> None:
        # D-19 invariant #6: typed exception BEFORE returning so
        # missing-key situations surface synchronously, not as a half-
        # streamed StreamError chunk.
        #
        # The preflight is skipped when ``client_factory`` is provided
        # (test injection) — the factory bypasses the real SDK and
        # therefore does not consult ANTHROPIC_API_KEY. Without this
        # gate the D-19 shared contract suite cannot construct the
        # adapter (the conftest's adapter_factory passes a
        # client_factory and no api_key).
        import os

        if (
            client_factory is None
            and api_key is None
            and not os.environ.get("ANTHROPIC_API_KEY")
        ):
            raise _missing_api_key_error()

        self._api_key = api_key
        self._max_cost = max_cost_usd
        self._max_steps = max_steps
        # Default to the real SDK class; tests inject ``lambda options:
        # FakeClaudeSDKClient(...)`` to substitute a duck-typed fake.
        self._client_factory = client_factory or ClaudeSDKClient
        self._pricing = _get_pricing_table()

    async def stream(
        self,
        prompt: str,
        history: list[Message],
        options: AdapterOptions,
    ) -> AsyncIterator[ChatChunk]:
        """Yield ChatChunks for one Claude Code turn.

        Always terminates with a ``Done`` chunk (D-04). On cancellation
        the generator emits ``StreamError("cancelled")`` + ``Done`` and
        re-raises ``CancelledError`` (PEP 789). On any other exception
        the generator emits ``StreamError(...)`` + ``Done`` and lets
        the consumer terminate the iterator normally.
        """

        # ----- Stage 1: workspace setup (BACKEND-08) ----------------------
        # Inline form per RESEARCH Pattern 4 lines 722-727 — we track
        # ``cleanup_workspace`` and rmtree in the finally block. Using
        # the ``ephemeral_workspace`` context manager would also work
        # but the inline form yields cleaner exception handling around
        # the SDK calls (no nested ``async with``).
        if options.cwd:
            workspace = options.cwd
            cleanup_workspace = False
        else:
            workspace = tempfile.mkdtemp(prefix="pomu-cc-")
            cleanup_workspace = True

        # ----- Stage 2: tracker + step counter --------------------------
        max_cost_usd = options.max_cost_usd or self._max_cost
        max_steps = options.max_steps or self._max_steps
        tracker = ClaudeCodeCostTracker(
            model_id=options.model or "claude-agent-sdk",
            max_cost_usd=max_cost_usd,
            pricing=self._pricing,
        )
        steps = StepCounter(cap=max_steps)
        start_t = asyncio.get_event_loop().time()

        # ----- Stage 3: SDK client construction --------------------------
        agent_opts = ClaudeAgentOptions(
            allowed_tools=ALLOWED_TOOLS,
            cwd=workspace,
            # No permission_mode override — defaults to user-controlled.
            # Phase 5 settings UI may set "acceptEdits" via this hook.
        )
        client: Any = None
        try:
            client = self._client_factory(options=agent_opts)
            await client.connect()
            # query() on the client is the streaming-mode entry; the
            # standalone query() function has no interrupt() method
            # (Pitfall 2 — BACKEND-07 needs cancellation to propagate
            # to the subprocess within 2 s).
            await client.query(prompt=prompt)

            # ----- Stage 4: per-message loop -------------------------
            # Dispatch uses duck-typed helpers (``_is_*``) so test fakes
            # work without monkeypatching the SDK imports above. The
            # helpers fall back from ``isinstance`` to a class-name
            # check; both real SDK objects and Fake* dataclasses match.
            async for msg in client.receive_response():
                # ResultMessage marks the end of one turn. Use it as
                # the natural loop terminator so the SDK closes the
                # underlying generator cleanly (Pitfall 5).
                if _is_result(msg):
                    tracker.record_result(msg)
                    break

                if _is_assistant(msg):
                    steps.increment()  # D-15 — one step per AssistantMessage
                    for block in getattr(msg, "content", []) or []:
                        if _is_text_block(block):
                            text = getattr(block, "text", "")
                            tracker.record_output_text(text)
                            yield TextDelta(text=text)
                        elif _is_tool_use(block):
                            yield ToolCall(
                                tool_call_id=getattr(block, "id", ""),
                                tool_name=getattr(block, "name", ""),
                                arguments=getattr(block, "input", {}) or {},
                            )
                        elif _is_thinking(block):
                            # v1 surface: drop ThinkingBlocks. The UI
                            # has no rendering path for them yet.
                            continue
                    usage = getattr(msg, "usage", None)
                    if usage is not None:
                        tracker.record_assistant_usage(usage)

                elif _is_user(msg):
                    # In claude-agent-sdk, UserMessages within a turn
                    # carry tool_result blocks injected by the SDK
                    # after it executed a ToolUse on Claude's behalf
                    # (RESEARCH Pattern 4 lines 776-778).
                    for block in getattr(msg, "content", []) or []:
                        if _is_tool_result(block):
                            tool_use_id = getattr(block, "tool_use_id", "")
                            tool_name = getattr(block, "tool_name", "")
                            content = getattr(block, "content", "")
                            is_error = getattr(block, "is_error", False)
                            if tool_name in ("Edit", "Write"):
                                block_input = getattr(block, "input", None) or {}
                                path = (
                                    block_input.get("path", "")
                                    if isinstance(block_input, dict)
                                    else ""
                                )
                                yield FileDiff(
                                    tool_call_id=tool_use_id,
                                    path=path,
                                    diff=str(content),
                                    operation="edit" if tool_name == "Edit" else "create",
                                )
                            else:
                                if isinstance(content, (str, dict)):
                                    normalised = content
                                else:
                                    normalised = str(content)
                                yield ToolResult(
                                    tool_call_id=tool_use_id,
                                    content=normalised,
                                    is_error=is_error,
                                )

                elif _is_system(msg):
                    logger.debug("SystemMessage: %r", getattr(msg, "subtype", "?"))
                else:
                    logger.debug("Unknown message type: %r", type(msg).__name__)

                # ----- cap checks (after each message processed) -----
                if steps.exceeded():
                    yield StreamError(
                        code="step_cap_exceeded",
                        message=f"Step cap of {steps.cap} reached.",
                        retriable=False,
                    )
                    # Pitfall 5: interrupt BEFORE break so the SDK
                    # closes its async generator cleanly.
                    try:
                        await client.interrupt()
                    except Exception:
                        pass
                    break

                if tracker.over_cap():
                    yield StreamError(
                        code="cost_cap_exceeded",
                        message=(
                            f"Cost cap ${tracker.max_cost_usd:.6f} exceeded "
                            f"(used ${tracker.total():.6f})."
                        ),
                        retriable=False,
                    )
                    try:
                        await client.interrupt()
                    except Exception:
                        pass
                    break

            # ----- Stage 5: terminal Done ---------------------------
            latency_ms = int((asyncio.get_event_loop().time() - start_t) * 1000)
            yield Done(
                tokens_in=tracker.tokens_in(),
                tokens_out=tracker.tokens_out(),
                cost_usd=tracker.total(),
                latency_ms=latency_ms,
                routing_signals=options.routing_signals,
            )

        except asyncio.CancelledError:
            # Pattern 7 + PEP 789: interrupt the subprocess, emit the
            # terminal pair, then re-raise so the caller's task is
            # marked cancelled.
            if client is not None:
                try:
                    await client.interrupt()
                except Exception:
                    pass
            yield StreamError(
                code="cancelled",
                message="Stream cancelled by caller.",
                retriable=True,
            )
            yield Done(
                tokens_in=tracker.tokens_in(),
                tokens_out=tracker.tokens_out(),
                cost_usd=tracker.total(),
                latency_ms=int((asyncio.get_event_loop().time() - start_t) * 1000),
                routing_signals=options.routing_signals,
            )
            raise

        except ProcessError as exc:
            yield StreamError(
                code="provider_unavailable",
                message=str(exc),
                retriable=False,
            )
            yield Done(routing_signals=options.routing_signals)

        except ClaudeSDKError as exc:
            yield StreamError(
                code="internal_error",
                message=str(exc),
                retriable=False,
            )
            yield Done(routing_signals=options.routing_signals)

        except Exception as exc:  # noqa: BLE001 — V7 robustness wrapper.
            logger.exception("Claude Code adapter internal error")
            yield StreamError(
                code="internal_error",
                message=f"{type(exc).__name__}: {exc}",
                retriable=False,
            )
            yield Done(routing_signals=options.routing_signals)

        finally:
            if client is not None:
                try:
                    await client.disconnect()
                except Exception:
                    # Closing an already-closed subprocess raises; the
                    # cancellation contract only needs the disconnect
                    # to be attempted, not to succeed.
                    pass
            if cleanup_workspace:
                try:
                    shutil.rmtree(workspace, ignore_errors=True)
                except Exception:
                    pass
