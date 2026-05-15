"""OpenRouterCostTracker — tiktoken-based pre-flight estimation + provider override.

Public surface (BACKEND-06):

    OpenRouterCostTracker     CostTracker subclass for OpenRouter calls.
        record_input_estimate(prompt, history)        tiktoken pre-flight
        record_output_delta(text)                     per-delta increment
        record_final_usage(prompt_tokens, completion_tokens)
                                                      override estimate

Behaviour rationale:

The OpenRouter (= OpenAI-compatible) streaming protocol does not emit
usage information per chunk; the final ``stream_options.include_usage``
chunk carries the authoritative ``prompt_tokens`` / ``completion_tokens``
totals. The adapter calls ``record_input_estimate`` BEFORE the request
goes out (so a long prompt trips the cost cap before billing) and
``record_final_usage`` once on the final chunk to replace the estimate
with provider truth for the ``Done`` chunk.

``tiktoken.encoding_for_model("gpt-4")`` is the canonical OpenAI BPE
tokenizer; we use it for every OpenRouter slug ([ASSUMED] A6 in
02-RESEARCH.md: gpt-4 encoder is close enough for non-OpenAI slugs
pre-flight; the final usage override corrects any drift).

Cross-refs:
    - 02-RESEARCH.md §"Pattern 6" lines 1355-1379 (canonical source)
    - 02-RESEARCH.md §"Pitfall 1" lines 1767-1775 (stream_options.include_usage)
    - apps/api/backends/cost.py (CostTracker base class)
"""

from __future__ import annotations

import tiktoken

from apps.api.backends.cost import CostTracker
from apps.api.backends.pricing import PricingTable
from apps.api.backends.protocol import Message


class OpenRouterCostTracker(CostTracker):
    """CostTracker for OpenRouter — tiktoken pre-flight + provider override.

    The ``gpt-4`` tokenizer is bound at class definition time so the
    encoder is shared across every instance — ``tiktoken.encoding_for_model``
    is not free (loads BPE merges from disk on first call).
    """

    _ENCODING = tiktoken.encoding_for_model("gpt-4")

    def __init__(
        self,
        *,
        model_id: str,
        max_cost_usd: float,
        pricing: PricingTable,
    ):
        super().__init__(
            model_id=model_id,
            max_cost_usd=max_cost_usd,
            pricing=pricing,
        )

    def record_input_estimate(
        self,
        prompt: str,
        history: list[Message],
    ) -> None:
        """Estimate input tokens via tiktoken on the joined conversation text."""

        joined = prompt + "\n".join(m.content for m in history)
        self.record_input(len(self._ENCODING.encode(joined)))

    def record_output_delta(self, text: str) -> None:
        """Add per-delta tiktoken-encoded length to the running output tally."""

        self.record_output(len(self._ENCODING.encode(text)))

    def record_final_usage(
        self,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        """Override the running estimate with provider-reported usage.

        This is called once when the OpenRouter ``include_usage`` chunk
        arrives (final chunk with empty ``choices`` and a populated
        ``usage`` block). The ``Done`` chunk in the adapter then reports
        provider-truth tokens / cost.
        """

        self._tokens_in = prompt_tokens
        self._tokens_out = completion_tokens
