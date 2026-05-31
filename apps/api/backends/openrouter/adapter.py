"""OpenRouter adapter — async streaming via OpenAI SDK v2.36+.

Public surface (BACKEND-02 + BACKEND-03 + BACKEND-06 + BACKEND-07):

    class OpenRouterAdapter:
        __init__(api_key, *, max_cost_usd, client_factory=None)
        async def stream(prompt, history, options) -> AsyncIterator[ChatChunk]

Pipeline (6 stages, all inside one top-level try/except for V7 robustness):
    1. Pre-flight: tiktoken input estimate; cost tracker init.
    2. client.chat.completions.create(..., stream=True,
       stream_options={"include_usage": True})  -- include_usage is the
       ONLY way to get final usage chunk for OpenAI-compatible APIs.
    3. Per chunk: emit TextDelta, accumulate tool_call deltas by index,
       check tracker.over_cap() after every emit.
    4. On finish_reason == "tool_calls": flush accumulated ToolCall
       chunks (one per index slot). Generate tool_call_id with the
       tc_<6-char-base32> shape when the provider omits one.
    5. On final usage chunk: override tracker with provider truth.
    6. Terminal: Done chunk carrying tokens / cost / latency / signals.

Cancellation contract (Pattern 7 + PEP 789):
    On asyncio.CancelledError: emit StreamError("cancelled") + Done,
    THEN re-raise. The finally block aborts the underlying httpx
    stream via in_flight.close() so the wire is released within the
    2-second cancellation budget enforced by the D-19 contract suite.

Error contract (D-06 closed vocabulary):
    AuthenticationError -> "auth_failed", retriable=False
    APITimeoutError     -> "timeout", retriable=True
    APIStatusError@429  -> "rate_limited", retriable=True
    APIStatusError      -> "provider_unavailable", retriable=True
    other Exception     -> "internal_error", retriable=False
    All terminal: emit StreamError + Done, do NOT re-raise (let the
    generator finish via StopAsyncIteration).

Cross-refs:
    - 02-RESEARCH.md §"Pattern 3" lines 472-655 (canonical source)
    - 02-RESEARCH.md §"Pattern 7" lines 1381-1418 (cancellation)
    - 02-RESEARCH.md §"Pitfall 1" lines 1767-1775 (include_usage)
    - 02-RESEARCH.md §"Pitfall 3" lines 1787-1795 (default_headers)
    - 02-CONTEXT.md D-04 / D-06 / D-19 (closed vocabulary + invariants)
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
from openai import (
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
)

from apps.api.backends.chunks import (
    ChatChunk,
    Done,
    StreamError,
    TextDelta,
    ToolCall,
)
from apps.api.backends.cost import DEFAULT_PER_TURN_COST_USD
from apps.api.backends.logging_filter import _redact_text
from apps.api.backends.openrouter.cost import OpenRouterCostTracker
from apps.api.backends.pricing import PricingTable
from apps.api.backends.protocol import AdapterOptions, Message

logger = logging.getLogger(__name__)

# Module-level constants. The attribution headers identify the project
# in OpenRouter's per-app dashboard (BACKEND-03 + CONTEXT discretion).
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
HTTP_REFERER = "https://github.com/marreroii-michael/Prompt-Optimizer"
X_TITLE = "Prompt-Optimizer"

# Resolve config/pricing.json once at import time.
# apps/api/backends/openrouter/adapter.py -> repo root is 4 parents up.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_PRICING_PATH = _REPO_ROOT / "config" / "pricing.json"


# Allow re-binding for the rare case the constructor wants to override
# the cached path; tests pin the path via the singleton below.
_PRICING_TABLE: PricingTable | None = None


def _get_pricing_table() -> PricingTable:
    """Lazy singleton accessor for the shared PricingTable.

    Loading the static table is cheap (~1 ms) but happens once per
    process instead of once per adapter construction.
    """

    global _PRICING_TABLE
    if _PRICING_TABLE is None:
        _PRICING_TABLE = PricingTable.from_static(_PRICING_PATH)
    return _PRICING_TABLE


def _gen_tool_call_id() -> str:
    """Generate ``tc_<6-char-base32>`` per CONTEXT specifics line 257.

    The alphabet is RFC 4648 base32 lowercased. ``secrets.choice``
    pulls from the OS CSPRNG; 6 chars over a 32-char alphabet gives
    ~30 bits of entropy which is plenty for de-duplicating tool calls
    within a single turn.
    """

    alphabet = "abcdefghijklmnopqrstuvwxyz234567"
    return "tc_" + "".join(secrets.choice(alphabet) for _ in range(6))


def _build_missing_key_error() -> AuthenticationError:
    """Build an AuthenticationError compatible with openai SDK 2.x.

    openai SDK 2.36 dereferences ``response.request`` inside the
    AuthenticationError constructor, so the older ``response=None``
    pattern in RESEARCH Pattern 3 line 514 raises AttributeError.
    We construct a minimal valid httpx.Response bound to a real
    Request so the typed exception surfaces correctly.
    """

    request = httpx.Request("POST", f"{OPENROUTER_BASE_URL}/chat/completions")
    response = httpx.Response(status_code=401, request=request)
    return AuthenticationError(
        message="OPENROUTER_API_KEY not set",
        response=response,
        body=None,
    )


class OpenRouterAdapter:
    """OpenRouter backend adapter (BackendAdapter Protocol implementation).

    The adapter is constructed once per backend registry entry and
    streams one turn at a time via :meth:`stream`. ``client_factory``
    enables test injection: pass ``lambda key: FakeOpenAIClient(...)``
    to replace the real ``AsyncOpenAI`` with a duck-typed fake.
    """

    def __init__(
        self,
        api_key: str,
        *,
        max_cost_usd: float = DEFAULT_PER_TURN_COST_USD,
        client_factory: Any = None,
    ):
        # D-19 invariant #6: typed exception BEFORE the constructor returns.
        if not api_key:
            raise _build_missing_key_error()

        factory = client_factory or self._default_client_factory
        self._client = factory(api_key)
        self._max_cost = max_cost_usd
        self._pricing = _get_pricing_table()

    @staticmethod
    def _default_client_factory(api_key: str) -> AsyncOpenAI:
        """Build the real AsyncOpenAI client.

        ``default_headers`` is set on the constructor (Pitfall 3) so
        every call carries ``HTTP-Referer`` and ``X-Title`` for the
        OpenRouter per-app attribution dashboard.
        """

        return AsyncOpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=api_key,
            # RELI-01 / RESEARCH Pitfall 1: pin the SDK retry budget to
            # zero so the application-level retry loop in turn.py is the
            # SOLE retry authority. The openai SDK default is
            # max_retries=2 with its own exponential backoff; left unset
            # it silently stacks under the D-02 3-attempt loop (up to ~9
            # upstream calls against a hard-down provider, shattering the
            # ~10-15s worst-case budget). Adapters stay single-attempt.
            max_retries=0,
            default_headers={
                "HTTP-Referer": HTTP_REFERER,
                "X-Title": X_TITLE,
            },
        )

    async def stream(
        self,
        prompt: str,
        history: list[Message],
        options: AdapterOptions,
    ) -> AsyncIterator[ChatChunk]:
        """Yield ChatChunks for a single turn.

        Always terminates with a Done chunk (D-04). On cancellation
        the generator emits StreamError("cancelled") + Done and
        re-raises CancelledError (PEP 789). On any other exception
        the generator emits StreamError(...) + Done and lets the
        consumer terminate the iterator normally.
        """

        model_id = options.model or "openai/gpt-5"
        # DEBT-02: honor an explicit 0.0 as a hard "spend nothing" cap.
        # ``or`` would treat 0.0 as falsy and silently fall back to the
        # adapter default; an explicit ``is not None`` check mirrors the
        # turn.py request->cap ladder (CR-02).
        max_cost_usd = (
            options.max_cost_usd
            if options.max_cost_usd is not None
            else self._max_cost
        )
        tracker = OpenRouterCostTracker(
            model_id=model_id,
            max_cost_usd=max_cost_usd,
            pricing=self._pricing,
        )
        tracker.record_input_estimate(prompt=prompt, history=history)

        messages: list[dict[str, str]] = [
            {"role": m.role, "content": m.content} for m in history
        ]
        messages.append({"role": "user", "content": prompt})

        in_flight = None
        start_t = asyncio.get_event_loop().time()
        try:
            in_flight = await self._client.chat.completions.create(
                model=model_id,
                messages=messages,
                stream=True,
                stream_options={"include_usage": True},
            )

            # Tool-call streaming is delta-indexed; accumulate by index.
            tool_calls: dict[int, dict[str, Any]] = {}

            async for chunk in in_flight:
                # Final usage chunk has empty choices + populated usage.
                if getattr(chunk, "usage", None) is not None:
                    tracker.record_final_usage(
                        prompt_tokens=chunk.usage.prompt_tokens,
                        completion_tokens=chunk.usage.completion_tokens,
                    )
                    continue

                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                finish_reason = chunk.choices[0].finish_reason

                if getattr(delta, "content", None):
                    tracker.record_output_delta(delta.content)
                    yield TextDelta(text=delta.content)

                if getattr(delta, "tool_calls", None):
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        slot = tool_calls.setdefault(
                            idx,
                            {"id": "", "name": "", "arguments": ""},
                        )
                        if getattr(tc_delta, "id", None):
                            slot["id"] = tc_delta.id
                        fn = getattr(tc_delta, "function", None)
                        if fn is not None:
                            if getattr(fn, "name", None):
                                slot["name"] = fn.name
                            if getattr(fn, "arguments", None):
                                slot["arguments"] += fn.arguments

                if finish_reason == "tool_calls":
                    for slot in tool_calls.values():
                        try:
                            args = (
                                json.loads(slot["arguments"])
                                if slot["arguments"]
                                else {}
                            )
                        except json.JSONDecodeError:
                            args = {"_raw": slot["arguments"]}
                        yield ToolCall(
                            tool_call_id=slot["id"] or _gen_tool_call_id(),
                            tool_name=slot["name"],
                            arguments=args,
                        )
                    tool_calls.clear()

                if tracker.over_cap():
                    yield StreamError(
                        code="cost_cap_exceeded",
                        message=_redact_text(
                            f"Cost cap ${tracker.max_cost_usd:.6f} exceeded "
                            f"(used ${tracker.total():.6f})."
                        ),
                        retriable=False,
                    )
                    break

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
            # Pattern 7: emit terminal pair, then re-raise (PEP 789).
            yield StreamError(
                code="cancelled",
                message=_redact_text("Stream cancelled by caller."),
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
                message=_redact_text(str(exc)),
                retriable=False,
            )
            yield Done(routing_signals=options.routing_signals)

        except APITimeoutError as exc:
            yield StreamError(
                code="timeout",
                message=_redact_text(str(exc)),
                retriable=True,
            )
            yield Done(routing_signals=options.routing_signals)

        except APIStatusError as exc:
            code = (
                "rate_limited"
                if exc.status_code == 429
                else "provider_unavailable"
            )
            yield StreamError(
                code=code,
                message=_redact_text(str(exc)),
                retriable=(code == "rate_limited"),
            )
            yield Done(routing_signals=options.routing_signals)

        except Exception as exc:  # noqa: BLE001 — V7 robustness wrapper.
            logger.exception("OpenRouter adapter internal error")
            yield StreamError(
                code="internal_error",
                message=_redact_text(f"{type(exc).__name__}: {exc}"),
                retriable=False,
            )
            yield Done(routing_signals=options.routing_signals)

        finally:
            if in_flight is not None:
                try:
                    await in_flight.close()
                except Exception:
                    # Closing an already-closed httpx stream raises; the
                    # cancellation contract only needs the close to be
                    # attempted, not to succeed.
                    pass
