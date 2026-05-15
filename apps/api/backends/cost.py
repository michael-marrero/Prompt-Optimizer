"""CostTracker base class — shared per-turn cost accounting.

Public surface (BACKEND-06, D-16):

    DEFAULT_PER_TURN_COST_USD   Final[float] = 0.50   # CONTEXT specifics
    CostTracker                 base counter + cap predicate

Each adapter subclasses ``CostTracker`` to know how to extract token
counts from its provider's streaming events (e.g. OpenAI's
``stream_options.include_usage`` final chunk; Anthropic's
per-iteration ``usage`` block; claude-agent-sdk's ``ResultMessage.
total_cost_usd``). The base class owns the shared state machine:

    record_input(n)         add to running input-token tally
    record_output(n)        add to running output-token tally
    tokens_in()             current input tally
    tokens_out()            current output tally
    total()                 cost in USD; provider-authoritative if set
    over_cap()              True once total() > max_cost_usd

When the provider reports an authoritative cost (Claude Code's
``ResultMessage.total_cost_usd`` or any OpenRouter ``Done`` chunk
with a final usage block), the subclass sets
``_final_cost_override``; ``total()`` returns it verbatim instead of
re-computing from rates.

Cross-refs:
    - 02-RESEARCH.md §"Pattern 6" lines 1211-1259 (canonical source)
    - 02-CONTEXT.md specifics line 260 (DEFAULT_PER_TURN_COST_USD = 0.50)
    - 02-CONTEXT.md D-16 (shared CostTracker interface contract)
"""

from __future__ import annotations

from typing import Final

from apps.api.backends.pricing import PricingTable

# 50¢ per turn — high enough to comfortably finish any single
# conversational answer; low enough to cap a runaway tool-call loop
# inside Claude Code or computer-use.
DEFAULT_PER_TURN_COST_USD: Final[float] = 0.50


class CostTracker:
    """Per-turn token + cost tracker; adapters subclass to feed it events.

    Composition over inheritance: adapters hold a tracker instance,
    feed it from their own provider-specific event handlers, and
    consult ``over_cap()`` once per emitted chunk to decide whether
    to short-circuit with a ``StreamError(code="cost_cap_exceeded")``.
    """

    def __init__(
        self,
        *,
        model_id: str,
        max_cost_usd: float,
        pricing: PricingTable,
    ):
        self.model_id = model_id
        self.max_cost_usd = max_cost_usd
        self._pricing = pricing
        self._tokens_in = 0
        self._tokens_out = 0
        # Provider-authoritative final cost (overrides the rate-based
        # calculation when set). Examples: claude-agent-sdk's
        # ResultMessage.total_cost_usd, an OpenRouter Done usage block
        # whose cost has been computed server-side.
        self._final_cost_override: float | None = None

    def record_input(self, n: int) -> None:
        self._tokens_in += n

    def record_output(self, n: int) -> None:
        self._tokens_out += n

    def tokens_in(self) -> int:
        return self._tokens_in

    def tokens_out(self) -> int:
        return self._tokens_out

    def total(self) -> float:
        if self._final_cost_override is not None:
            return self._final_cost_override
        rates = self._pricing.get(self.model_id)
        return (
            self._tokens_in * rates["input_per_mtok"] / 1_000_000
            + self._tokens_out * rates["output_per_mtok"] / 1_000_000
        )

    def over_cap(self) -> bool:
        return self.total() > self.max_cost_usd
