# Plan 06 — Success Criterion #4 / D-12 — sub-threshold prompts deterministically
# route to the OpenRouter fallback and the rationale ends with the EXACT substring
# "low confidence — fallback" (en-dash U+2014, lowercase, verbatim).
#
# Tests to be implemented in Plan 06:
#   - test_fallback_rationale_ends_with_low_confidence_substring()
#       asserts decision.rationale.endswith("low confidence — fallback")
#       for gibberish, emoji-only, single-token, and multi-language prompts.

import pytest


def test_fallback_rationale_ends_with_low_confidence_substring_placeholder():
    pytest.skip("Wave 3 — implemented in Plan 06 (Success Criterion #4)")
