"""ComputerUseCostTracker — per-iteration usage + char/4 output estimate.

Public surface (BACKEND-06, D-16):

    ComputerUseCostTracker(CostTracker)
        record_output_text(text)               char-count // 4 estimator
        record_iteration_usage(*, input_tokens, output_tokens,
                               cache_read=0, cache_write=0)
                                                authoritative per-iteration
                                                usage from Anthropic

Behaviour rationale:

Anthropic's tokenizer is not public, so we use ``len(text) // 4`` as a
deliberate, pessimistic estimator for output token counts (RESEARCH
line 1379 — ~4 characters per token is the documented upper-bound rule
of thumb). The estimator only matters for cost-cap short-circuit
decisions during a streamed text_delta event — by the time the
iteration's ``message_stop`` lands, the authoritative
``final_msg.usage.input_tokens`` / ``output_tokens`` numbers have
overridden the running estimate via ``record_iteration_usage``.

Two event handlers, called by the adapter:

    record_output_text(event.delta.text)
        Per ``content_block_delta`` (text_delta) event — add a char/4
        estimate to the running output-token tally so
        ``tracker.over_cap()`` trips before the next iteration spawns.

    record_iteration_usage(input_tokens=..., output_tokens=...,
                           cache_read=..., cache_write=...)
        Per ``message_stop`` / final-message — replace the running
        tally with Anthropic's authoritative numbers. ``cache_read`` and
        ``cache_write`` are tracked separately so we have visibility
        when prompt caching ships (RESEARCH Open Question 2 / 3).

Cross-refs:
    - 02-RESEARCH.md §"Pattern 5" lines 1015-1022 (per-iteration usage)
    - 02-RESEARCH.md line 1379 (char/4 estimator rationale)
    - 02-CONTEXT.md D-16 (shared CostTracker interface)
    - apps/api/backends/cost.py (CostTracker base class)
    - apps/api/backends/claude_code/cost.py (parallel implementation)
"""

from __future__ import annotations

from apps.api.backends.cost import CostTracker
from apps.api.backends.pricing import PricingTable


# Anthropic's tokenizer is closed; ~4 characters per token is the
# documented rule of thumb used across the SDK's own examples. The
# adapter only relies on this for in-stream cost-cap decisions —
# Done.cost_usd ultimately comes from the per-iteration usage override.
_CHARS_PER_TOKEN: int = 4


class ComputerUseCostTracker(CostTracker):
    """CostTracker for the Anthropic computer-use adapter.

    The base class owns the cap predicate (``over_cap``) and the
    ``_final_cost_override`` slot. This subclass adds the two
    computer-use-specific event handlers + cache-token counters.
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
        # Cache-token visibility per RESEARCH Open Question 2 / 3.
        # Not currently used to scale the cost calculation — Anthropic
        # bills cached prompt tokens at a different rate that the v1
        # ``config/pricing.json`` does not yet model. Tracked for the
        # live-smoke audit; Phase 3 may add explicit cache rates.
        self._cache_read_total: int = 0
        self._cache_write_total: int = 0

    def record_output_text(self, text: str) -> None:
        """Add ``len(text) // 4`` to the running output-token tally.

        Called once per ``content_block_delta`` (text_delta) event.
        Empty string is a no-op (records 0 tokens).
        """

        if not text:
            return
        self.record_output(len(text) // _CHARS_PER_TOKEN)

    def record_iteration_usage(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        cache_read: int = 0,
        cache_write: int = 0,
    ) -> None:
        """Override the running estimate with provider-reported usage.

        Called once per agent-loop iteration when the SDK's
        ``stream.get_final_message()`` returns a populated ``usage``
        block. ``cache_read`` / ``cache_write`` are tracked for
        visibility (RESEARCH Open Question 3) but do not currently
        adjust the cost-cap arithmetic.
        """

        self._tokens_in += int(input_tokens)
        self._tokens_out += int(output_tokens)
        self._cache_read_total += int(cache_read)
        self._cache_write_total += int(cache_write)
