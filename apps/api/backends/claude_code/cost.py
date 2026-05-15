"""ClaudeCodeCostTracker — char/4 input estimate + ResultMessage override.

Public surface (BACKEND-06, D-15 / D-16):

    ClaudeCodeCostTracker(CostTracker)
        record_output_text(text)        char-count // 4 estimator
        record_assistant_usage(usage)   override running estimate
        record_result(result)           authoritative final cost

Behaviour rationale:

The Anthropic tokenizer is not public, so we use ``len(text) // 4`` as
a deliberate, pessimistic estimator for input/output token counts
(RESEARCH line 1379 — ~4 characters per token is the documented
upper-bound rule of thumb). The estimator only matters for cost-cap
short-circuit decisions inside ``stream()`` — by the time ``Done``
lands, the authoritative ``ResultMessage.total_cost_usd`` (RESEARCH
line 1235) has already overridden the running estimate via
``record_result``.

Three event handlers, called by the adapter:

    record_output_text(block.text)
        Per-AssistantMessage TextBlock — add a char/4 estimate to the
        running output-token tally so ``tracker.over_cap()`` trips
        before the next subprocess round-trip.

    record_assistant_usage(msg.usage)
        Per-AssistantMessage usage block — replace the running tally
        with the SDK's per-iteration usage when available. Defensive
        ``getattr`` because the SDK's ``Usage`` object exposes the
        fields under different names across versions.

    record_result(result)
        Final ResultMessage — set ``_final_cost_override`` so
        ``total()`` returns the provider-authoritative cost regardless
        of the running estimate.

Cross-refs:
    - 02-RESEARCH.md §"Pattern 6" lines 1376-1379 (canonical source)
    - 02-RESEARCH.md line 1235 (ResultMessage.total_cost_usd authoritative)
    - 02-CONTEXT.md D-15 (one step = one AssistantMessage)
    - apps/api/backends/cost.py (CostTracker base class)
"""

from __future__ import annotations

from apps.api.backends.cost import CostTracker
from apps.api.backends.pricing import PricingTable


# Anthropic's tokenizer is closed; ~4 characters per token is the
# documented rule of thumb used across the SDK's own examples. The
# adapter only relies on this for in-stream cost-cap decisions —
# Done.cost_usd ultimately comes from ResultMessage.total_cost_usd.
_CHARS_PER_TOKEN: int = 4


class ClaudeCodeCostTracker(CostTracker):
    """CostTracker for the Claude Code (claude-agent-sdk) adapter.

    The base class owns the cap predicate (``over_cap``) and the
    ``_final_cost_override`` slot. This subclass adds the three
    Claude-Code-specific event handlers.
    """

    def __init__(
        self,
        *,
        model_id: str,
        max_cost_usd: float,
        pricing: PricingTable,
    ) -> None:
        super().__init__(
            model_id=model_id,
            max_cost_usd=max_cost_usd,
            pricing=pricing,
        )

    def record_output_text(self, text: str) -> None:
        """Add ``len(text) // 4`` to the running output-token tally.

        Called once per ``TextBlock`` inside an ``AssistantMessage``.
        Empty string is a no-op (records 0 tokens).
        """

        if not text:
            return
        self.record_output(len(text) // _CHARS_PER_TOKEN)

    def record_assistant_usage(self, usage: object) -> None:
        """Override the running tally with SDK-reported per-iteration usage.

        ``usage`` is the ``Usage`` namespace on an
        ``AssistantMessage`` — different SDK versions have shipped the
        token fields under ``input_tokens`` / ``output_tokens`` and
        also under ``prompt_tokens`` / ``completion_tokens``. We read
        with ``getattr`` and fall back across both names.
        """

        if usage is None:
            return
        input_tokens = getattr(usage, "input_tokens", None)
        if input_tokens is None:
            input_tokens = getattr(usage, "prompt_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)
        if output_tokens is None:
            output_tokens = getattr(usage, "completion_tokens", None)
        if input_tokens is not None:
            self._tokens_in = int(input_tokens)
        if output_tokens is not None:
            self._tokens_out = int(output_tokens)

    def record_result(self, result: object) -> None:
        """Set ``_final_cost_override`` from ``ResultMessage.total_cost_usd``.

        ``total_cost_usd`` is the authoritative final cost reported by
        the SDK for a turn — once set, ``total()`` ignores the rate-
        based calculation and returns this value directly. If the
        attribute is missing or None we leave the running estimate in
        place so the cost cap stays meaningful.
        """

        if result is None:
            return
        cost = getattr(result, "total_cost_usd", None)
        if cost is None:
            return
        try:
            self._final_cost_override = float(cost)
        except (TypeError, ValueError):
            # Defensive — leave the rate-based estimate in place.
            return

        usage = getattr(result, "usage", None)
        if usage is not None:
            self.record_assistant_usage(usage)
