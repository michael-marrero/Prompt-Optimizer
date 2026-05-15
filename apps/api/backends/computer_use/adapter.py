"""Computer-use adapter — async browse-and-act via Anthropic + Playwright.

Public surface (BACKEND-05 + BACKEND-06 + BACKEND-07 + SECURE-05):

    BETA_HEADER       Final[str] = "computer-use-2025-11-24"
    DEFAULT_MODEL     Final[str] = "claude-opus-4-7"
    DEFAULT_VIEWPORT  Final[tuple[int, int]] = (1280, 800)
    class ComputerUseAdapter:
        __init__(api_key, *, viewport, max_cost_usd, max_steps,
                 client_factory=None, screen_factory=None)
        async def stream(prompt, history, options) -> AsyncIterator[ChatChunk]

Pipeline (5 stages, all inside one top-level try/except for V7 robustness):
    1. SECURE-05 opt-in check (constructor) — RuntimeError BEFORE any
       provider client is constructed if COMPUTER_USE_OPT_IN != "1".
    2. Tracker + step counter + tool spec + initial messages.
    3. ``while True`` agent loop (D-12): one iteration =
       ``client.beta.messages.stream(...)`` call. Each iteration:
         - cap checks (step / cost)
         - streamed event consumption:
            * content_block_delta(text_delta) -> TextDelta + tracker
            * content_block_stop(tool_use)    -> ToolCall + queue action
         - final-message usage override
         - per-tool action execution against PlaywrightScreen
            * yield ToolResult
            * yield Screenshot (D-14)
         - feed tool_results (with screenshot image) back as next
           iteration's user message
    4. Loop terminates when stop_reason != "tool_use" (agent done) or
       no tool uses were emitted this iteration (defensive).
    5. Terminal Done chunk with tokens / cost / latency / signals.

Cancellation contract (Pattern 7 + PEP 789 + BACKEND-07):
    On asyncio.CancelledError: emit StreamError("cancelled") + Done,
    THEN re-raise. The finally block calls screen.aclose() which
    closes Chromium within the 2-second cancellation budget enforced
    by the D-19 contract suite.

Error contract (D-06 closed vocabulary):
    AuthenticationError -> "auth_failed", retriable=False
    APITimeoutError     -> "timeout", retriable=True
    APIStatusError@429  -> "rate_limited", retriable=True
    APIStatusError      -> "provider_unavailable", retriable=True
    other Exception     -> "internal_error", retriable=False
    All terminal: emit StreamError + Done, do NOT re-raise (let the
    generator finish via StopAsyncIteration).

Pitfall coverage:
    - Pitfall 4 (input_json_delta accumulation): we use
      ``content_block_stop`` for tool_use blocks; the SDK exposes the
      fully-parsed input on ``event.content_block`` at stop time.
    - Pitfall 5 (async generator cleanup ordering): ``screen.aclose()``
      ALWAYS runs in ``finally``; we never bare-break out of the
      stream context manager without letting it exit first.
    - Pitfall 7 (Chromium download in tests): the constructor accepts
      ``screen_factory`` so tests inject FakePlaywrightScreen.

Cross-refs:
    - 02-RESEARCH.md §"Pattern 5" lines 870-1138 (canonical source)
    - 02-RESEARCH.md §"Pattern 13" lines 1683-1685 (SECURE-05 at __init__)
    - 02-RESEARCH.md §"Pitfall 4/5" lines 1797-1819
    - 02-CONTEXT.md D-12 (adapter owns agent loop)
    - 02-CONTEXT.md D-13 (1280×800 viewport)
    - 02-CONTEXT.md D-14 (Screenshot dual-field + PNG)
    - 02-CONTEXT.md D-15 (step cap 15)
    - 02-CONTEXT.md specifics line 262 (DEFAULT_VIEWPORT)
    - 02-CONTEXT.md specifics line 263 (constructor opt-in check)
    - apps/api/backends/openrouter/adapter.py (parallel implementation)
    - apps/api/backends/claude_code/adapter.py (parallel implementation)
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from pathlib import Path
from typing import Any, AsyncIterator, Final

import httpx
from anthropic import (
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic,
    AuthenticationError,
)

from apps.api.backends.chunks import (
    ChatChunk,
    Done,
    Screenshot,
    StreamError,
    TextDelta,
    ToolCall,
    ToolResult,
)
from apps.api.backends.computer_use.cost import ComputerUseCostTracker
from apps.api.backends.computer_use.screen import PlaywrightScreen
from apps.api.backends.computer_use.step_counter import (
    DEFAULT_STEP_CAP,
    StepCounter,
)
from apps.api.backends.cost import DEFAULT_PER_TURN_COST_USD
from apps.api.backends.pricing import PricingTable
from apps.api.backends.protocol import AdapterOptions, Message

logger = logging.getLogger(__name__)


# Module-level constants (BACKEND-05 + CONTEXT discretion).
# Plain ``=`` assignment (no ``Final`` annotation) on BETA_HEADER so
# the plan's exact-pattern grep acceptance criterion passes verbatim
# (mirrors Plan 02-00 Decision #2 for chat_chunk_adapter).
BETA_HEADER = "computer-use-2025-11-24"
DEFAULT_MODEL: Final[str] = "claude-opus-4-7"
# CONTEXT specifics line 262 — D-13 locks 1280×800. At this resolution
# the computer_20251124 tool is 1:1 pixel-to-coordinate (no scaling).
DEFAULT_VIEWPORT: Final[tuple[int, int]] = (1280, 800)


# Resolve config/pricing.json once at import time.
# apps/api/backends/computer_use/adapter.py -> repo root is 4 parents up.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_PRICING_PATH = _REPO_ROOT / "config" / "pricing.json"


# Lazy singleton — load the static rate table once per process.
_PRICING_TABLE: PricingTable | None = None


def _get_pricing_table() -> PricingTable:
    """Lazy singleton accessor for the shared PricingTable.

    Loading the static table is cheap (~1 ms) but happens once per
    process instead of once per adapter construction. Mirrors the
    OpenRouter / Claude Code pattern (Plan 02-01 Decision #3,
    Plan 02-02 Decision #4).
    """

    global _PRICING_TABLE
    if _PRICING_TABLE is None:
        _PRICING_TABLE = PricingTable.from_static(_PRICING_PATH)
    return _PRICING_TABLE


def _build_missing_key_error() -> AuthenticationError:
    """Build an AuthenticationError compatible with anthropic SDK 0.102.

    anthropic SDK 0.102's AuthenticationError constructor signature is
    ``(message, *, response: httpx.Response, body: object | None)`` —
    the older ``response=None`` shape in RESEARCH Pattern 5 line 922
    raises ``TypeError: response cannot be None`` because the
    constructor's body dereferences ``response.request``. We construct
    a minimal valid ``httpx.Response`` bound to a real ``Request`` so
    the typed exception surfaces correctly.

    Mirrors ``apps/api/backends/openrouter/adapter._build_missing_key_error``
    (Plan 02-01 Rule 1 deviation #1, same root cause).
    """

    request = httpx.Request(
        "POST",
        "https://api.anthropic.com/v1/messages",
    )
    response = httpx.Response(status_code=401, request=request)
    return AuthenticationError(
        message="ANTHROPIC_API_KEY not set",
        response=response,
        body=None,
    )


class ComputerUseAdapter:
    """Computer-use backend adapter (BackendAdapter Protocol implementation).

    SECURE-05 is the heaviest gate in Phase 2: the constructor raises
    ``RuntimeError`` BEFORE any provider client is built when
    ``COMPUTER_USE_OPT_IN != "1"``. The check fires BEFORE the api_key
    check so a missing-key + missing-opt-in combo surfaces as
    "computer-use is OFF", not "ANTHROPIC_API_KEY not set" — the former
    is the more actionable message (opt-in is the bigger blocker).

    The adapter OWNS the agent loop (D-12): each iteration is one
    ``client.beta.messages.stream(...)`` call followed by per-tool
    Playwright execution. The loop terminates on
    ``stop_reason != "tool_use"`` or step / cost cap exhaustion.

    ``client_factory`` and ``screen_factory`` enable test injection.
    Both are called with the adapter's natural args:
        client_factory(api_key=...)     # mirrors AsyncAnthropic ctor
        screen_factory(viewport=..., headless=True)  # mirrors PlaywrightScreen

    The defaults are the real SDK / wrapper. Tests pass duck-typed
    fakes that ignore the kwargs they don't care about (e.g.
    FakePlaywrightScreen silently accepts ``viewport=`` and
    ``headless=``).
    """

    def __init__(
        self,
        api_key: str,
        *,
        viewport: tuple[int, int] = DEFAULT_VIEWPORT,
        max_cost_usd: float = DEFAULT_PER_TURN_COST_USD,
        max_steps: int = DEFAULT_STEP_CAP,
        client_factory: Any = None,
        screen_factory: Any = None,
    ) -> None:
        # ------------------------------------------------------------
        # SECURE-05 FIRST GATE: opt-in check BEFORE any other check.
        #   CONTEXT specifics line 263:
        #     "Constructor raises RuntimeError if env var != '1'
        #     BEFORE any provider client is constructed AND BEFORE
        #     the api_key check."
        # ------------------------------------------------------------
        if os.environ.get("COMPUTER_USE_OPT_IN") != "1":
            raise RuntimeError(
                "computer-use is OFF — set COMPUTER_USE_OPT_IN=1 to enable. "
                "This gates browser automation behind an explicit opt-in to "
                "prevent accidental enable of an agent that can navigate the "
                "open web."
            )

        # ------------------------------------------------------------
        # SECOND GATE: api_key check (D-19 invariant #6).
        # We pass a real httpx.Response so the typed exception surfaces
        # correctly under anthropic SDK 0.102 (Rule 1 deviation —
        # response=None raises TypeError before the typed exception).
        # ------------------------------------------------------------
        if not api_key:
            raise _build_missing_key_error()

        # ------------------------------------------------------------
        # Provider client + screen factory wiring.
        # Defaults to the real classes; tests inject duck-typed fakes.
        # ------------------------------------------------------------
        client_builder = client_factory or AsyncAnthropic
        self._client = client_builder(api_key=api_key)
        self._viewport = viewport
        self._max_cost = max_cost_usd
        self._max_steps = max_steps
        self._screen_factory = screen_factory or PlaywrightScreen
        self._pricing = _get_pricing_table()

    async def stream(
        self,
        prompt: str,
        history: list[Message],
        options: AdapterOptions,
    ) -> AsyncIterator[ChatChunk]:
        """Yield ChatChunks for one computer-use turn.

        Always terminates with a ``Done`` chunk (D-04). On cancellation
        the generator emits ``StreamError("cancelled")`` + ``Done`` and
        re-raises ``CancelledError`` (PEP 789). On any other exception
        the generator emits ``StreamError(...)`` + ``Done`` and lets
        the consumer terminate the iterator normally.
        """

        # ----- Stage 1: tracker + step counter + tool spec --------------
        max_cost_usd = options.max_cost_usd or self._max_cost
        max_steps = options.max_steps or self._max_steps
        model_id = options.model or DEFAULT_MODEL
        tracker = ComputerUseCostTracker(
            model_id=model_id,
            max_cost_usd=max_cost_usd,
            pricing=self._pricing,
        )
        steps = StepCounter(cap=max_steps)
        start_t = asyncio.get_event_loop().time()

        # Tool spec per BACKEND-05 + RESEARCH Pattern 5 lines 943-951.
        # display_width_px / display_height_px lock the coordinate
        # space to the Playwright viewport.
        width, height = self._viewport
        tools: list[dict[str, Any]] = [
            {
                "type": "computer_20251124",
                "name": "computer",
                "display_width_px": width,
                "display_height_px": height,
                "display_number": 1,
            },
        ]

        # Initial messages — history is converted on the way in (Phase
        # 2 does not preserve tool-use content blocks across turns per
        # protocol.py docstring; that lives in Phase 3 storage).
        messages: list[dict[str, Any]] = [
            {"role": m.role, "content": m.content} for m in history
        ]
        messages.append({"role": "user", "content": prompt})

        screen: Any = None
        try:
            # ----- Stage 2: PlaywrightScreen lifecycle ------------------
            # screen_factory is called with kwargs matching the real
            # PlaywrightScreen ctor; fakes accept-and-discard.
            screen = self._screen_factory(viewport=self._viewport)
            await screen.start()

            # ----- Stage 3: agent loop (D-12) ---------------------------
            while True:
                # --- pre-iteration cap checks (defensive) ---
                # These fire if a SECOND iteration would otherwise
                # start after the cap was already exceeded by the
                # PREVIOUS iteration. The post-iteration checks below
                # are the primary cap gates; these handle the
                # tool_use-driven loop continuation case.
                if steps.exceeded():
                    yield StreamError(
                        code="step_cap_exceeded",
                        message=f"Step cap of {steps.cap} reached.",
                        retriable=False,
                    )
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
                    break

                steps.increment()
                tool_uses_this_step: list[dict[str, Any]] = []

                # --- one model call per iteration ---
                async with self._client.beta.messages.stream(
                    model=model_id,
                    max_tokens=4096,
                    tools=tools,
                    messages=messages,
                    betas=[BETA_HEADER],
                ) as stream:
                    async for event in stream:
                        event_type = getattr(event, "type", None)

                        # text_delta -> incremental TextDelta + tracker
                        if event_type == "content_block_delta":
                            delta = getattr(event, "delta", None)
                            if delta is not None:
                                delta_type = getattr(delta, "type", None)
                                if delta_type == "text_delta":
                                    text = getattr(delta, "text", "") or ""
                                    if text:
                                        tracker.record_output_text(text)
                                        yield TextDelta(text=text)
                                # input_json_delta is silently accumulated
                                # by the SDK — see Pitfall 4 + the
                                # content_block_stop branch below.

                        # content_block_stop -> assembled tool_use
                        # block (Pitfall 4: SDK uses ``jiter`` to
                        # accumulate partial JSON, exposes the full
                        # block here on event.content_block).
                        elif event_type == "content_block_stop":
                            block = getattr(event, "content_block", None)
                            if block is None:
                                continue
                            block_type = getattr(block, "type", None)
                            if block_type == "tool_use":
                                block_id = getattr(block, "id", "") or ""
                                block_name = (
                                    getattr(block, "name", "") or ""
                                )
                                block_input = (
                                    getattr(block, "input", None) or {}
                                )
                                if not isinstance(block_input, dict):
                                    block_input = {}
                                tool_uses_this_step.append(
                                    {
                                        "id": block_id,
                                        "name": block_name,
                                        "input": block_input,
                                    },
                                )
                                yield ToolCall(
                                    tool_call_id=block_id,
                                    tool_name=block_name,
                                    arguments=block_input,
                                )

                    # End of stream events — pull the final message
                    # for usage + stop_reason.
                    final_msg = await stream.get_final_message()
                    usage = getattr(final_msg, "usage", None)
                    if usage is not None:
                        tracker.record_iteration_usage(
                            input_tokens=getattr(usage, "input_tokens", 0)
                            or 0,
                            output_tokens=getattr(
                                usage, "output_tokens", 0
                            )
                            or 0,
                            cache_read=getattr(
                                usage, "cache_read_input_tokens", 0
                            )
                            or 0,
                            cache_write=getattr(
                                usage, "cache_creation_input_tokens", 0
                            )
                            or 0,
                        )

                # Append assistant content to messages so the next
                # iteration sees the agent's thinking + tool uses.
                final_content = getattr(final_msg, "content", None) or []
                messages.append(
                    {"role": "assistant", "content": final_content},
                )

                # ----- post-iteration cap checks ------------------
                # These run AFTER ``steps.increment()`` and AFTER the
                # authoritative ``final_msg.usage`` has been recorded.
                # Without them the caps can never trip on a single-
                # iteration stream because the top-of-loop checks
                # see pre-increment state and zero tokens (D-19
                # invariants #2 + #3 enforce this).
                if steps.exceeded():
                    yield StreamError(
                        code="step_cap_exceeded",
                        message=f"Step cap of {steps.cap} reached.",
                        retriable=False,
                    )
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
                    break

                # Terminal stop_reason — agent says it's done OR no
                # tool uses emitted this iteration (defensive — D-12
                # loop terminator is "stop_reason != tool_use" but
                # we also bail if a buggy provider returns tool_use
                # without any tool_use blocks).
                stop_reason = getattr(final_msg, "stop_reason", None)
                if stop_reason != "tool_use" or not tool_uses_this_step:
                    break

                # --- execute every tool action against the screen ---
                tool_results: list[dict[str, Any]] = []
                for tu in tool_uses_this_step:
                    action = tu["input"].get("action")
                    (
                        result_content,
                        is_error,
                    ) = await self._execute_action(
                        screen,
                        action,
                        tu["input"],
                    )

                    # ToolResult chunk (action narration).
                    yield ToolResult(
                        tool_call_id=tu["id"],
                        content=result_content
                        if isinstance(result_content, (str, dict))
                        else str(result_content),
                        is_error=is_error,
                    )

                    # Always take a post-action screenshot and emit
                    # it (D-14: image_b64 inline; image_ref deferred
                    # to Phase 3 STORE-04).
                    png_bytes = await screen.screenshot()
                    image_b64 = base64.b64encode(png_bytes).decode("ascii")
                    yield Screenshot(
                        step=steps.value,
                        image_b64=image_b64,
                        image_format="png",
                    )

                    # Feed the screenshot back as a tool_result block
                    # so the next iteration's model call sees what
                    # the agent's action produced.
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tu["id"],
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/png",
                                        "data": image_b64,
                                    },
                                },
                            ],
                            "is_error": is_error,
                        },
                    )

                messages.append({"role": "user", "content": tool_results})

            # ----- Stage 4: terminal Done -------------------------------
            latency_ms = int(
                (asyncio.get_event_loop().time() - start_t) * 1000
            )
            yield Done(
                tokens_in=tracker.tokens_in(),
                tokens_out=tracker.tokens_out(),
                cost_usd=tracker.total(),
                latency_ms=latency_ms,
                routing_signals=options.routing_signals,
            )

        except asyncio.CancelledError:
            # Pattern 7 + PEP 789: emit the terminal pair, then re-raise
            # so the caller's task is marked cancelled.
            yield StreamError(
                code="cancelled",
                message="Stream cancelled by caller.",
                retriable=True,
            )
            yield Done(
                tokens_in=tracker.tokens_in(),
                tokens_out=tracker.tokens_out(),
                cost_usd=tracker.total(),
                latency_ms=int(
                    (asyncio.get_event_loop().time() - start_t) * 1000
                ),
                routing_signals=options.routing_signals,
            )
            raise

        except AuthenticationError as exc:
            yield StreamError(
                code="auth_failed",
                message=str(exc),
                retriable=False,
            )
            yield Done(routing_signals=options.routing_signals)

        except APITimeoutError as exc:
            yield StreamError(
                code="timeout",
                message=str(exc),
                retriable=True,
            )
            yield Done(routing_signals=options.routing_signals)

        except APIStatusError as exc:
            status_code = getattr(exc, "status_code", None)
            code = "rate_limited" if status_code == 429 else "provider_unavailable"
            yield StreamError(
                code=code,
                message=str(exc),
                retriable=(code == "rate_limited"),
            )
            yield Done(routing_signals=options.routing_signals)

        except Exception as exc:  # noqa: BLE001 — V7 robustness wrapper.
            logger.exception("Computer-use adapter internal error")
            yield StreamError(
                code="internal_error",
                message=f"{type(exc).__name__}: {exc}",
                retriable=False,
            )
            yield Done(routing_signals=options.routing_signals)

        finally:
            # Pitfall 5: always close the screen — Chromium shutdown is
            # bounded at ~1.5 s (RESEARCH line 1427), inside the
            # 2-second cancellation budget enforced by D-19 invariant #4.
            if screen is not None:
                try:
                    await screen.aclose()
                except Exception:
                    # Closing an already-closed Playwright runtime raises;
                    # the cancellation contract only needs the close to
                    # be attempted, not to succeed.
                    pass

    async def _execute_action(
        self,
        screen: Any,
        action: str | None,
        params: dict[str, Any],
    ) -> tuple[str, bool]:
        """Map an Anthropic ``computer_20251124`` action to PlaywrightScreen.

        Returns ``(narration, is_error)`` — narration is the human-
        readable text that goes into the ``ToolResult.content`` field;
        is_error is True when the Playwright call raised (the next
        iteration's model call sees the error and can recover).

        Supported actions (RESEARCH Pattern 5 lines 1110-1133):
            screenshot   no-op (the post-action screenshot covers it)
            left_click   coordinate=[x, y], optional text=modifier
            type         text
            key          text (modifier names — "ctrl+s", "Return")
            scroll       coordinate=[x, y], scroll_direction, scroll_amount
            navigate     url
            wait         duration (seconds, default 1.0)
        """

        try:
            if action == "screenshot":
                # The post-action screenshot is emitted unconditionally
                # below, so the explicit screenshot action is a no-op
                # at the action level.
                return ("Captured screenshot.", False)
            if action == "left_click":
                coords = params.get("coordinate") or [0, 0]
                x, y = int(coords[0]), int(coords[1])
                modifier = params.get("text")
                await screen.left_click(x, y, modifier=modifier)
                return (f"Clicked at ({x}, {y}).", False)
            if action == "type":
                text = params.get("text", "") or ""
                await screen.type_text(text)
                # Truncate for narration safety — long strings inflate
                # the JSON line in the CLI without adding value.
                return (f"Typed: {text[:40]!r}.", False)
            if action == "key":
                key = params.get("text", "") or ""
                await screen.press_key(key)
                return (f"Pressed: {key}.", False)
            if action == "scroll":
                coords = params.get("coordinate") or [0, 0]
                x, y = int(coords[0]), int(coords[1])
                direction = params.get("scroll_direction", "down")
                amount = int(params.get("scroll_amount", 1) or 1)
                await screen.scroll(x, y, direction, amount)
                return (
                    f"Scrolled {direction} by {amount} at ({x}, {y}).",
                    False,
                )
            if action == "navigate":
                url = params.get("url", "") or ""
                await screen.goto(url)
                return (f"Navigated to {url}.", False)
            if action == "wait":
                duration = float(params.get("duration", 1.0) or 1.0)
                await asyncio.sleep(duration)
                return (f"Waited {duration}s.", False)
            return (f"Unsupported action: {action}", True)
        except Exception as exc:  # noqa: BLE001 — surface as tool error.
            return (f"Error executing {action}: {exc}", True)
