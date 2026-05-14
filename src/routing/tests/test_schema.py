# Plan 06 Task 1 — schema.py + config.py contract tests.
#
# Covers behavior tests 1-6 from the plan:
#   1. RoutingDecision.to_json() produces a JSON string with the 5 expected keys.
#   2. RoutingDecision is frozen — mutation raises FrozenInstanceError.
#   3. src.routing.config exposes the three D-10 tau defaults verbatim.
#   4. config.FALLBACK_RATIONALE_SUFFIX is the EXACT 25-character string
#      "low confidence — fallback" with U+2014 at the correct position
#      (the plan acceptance text has a minor off-by-two on the dash
#      position; we assert against the canonical position 15 / -10).
#   5. config.BUILD_KEYWORDS verbatim from CONTEXT D-01.
#   6. config.BROWSE_KEYWORDS verbatim from CONTEXT D-01.

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest


def test_routing_decision_to_json_exposes_five_keys() -> None:
    from src.routing.schema import RoutingDecision

    decision = RoutingDecision(
        backend="openrouter",
        model_or_agent="openai/gpt-5",
        rationale="picked gpt-5",
        confidence=0.85,
    )
    payload = decision.to_json()
    assert isinstance(payload, str)
    parsed = json.loads(payload)
    assert set(parsed.keys()) == {
        "backend",
        "model_or_agent",
        "rationale",
        "confidence",
        "signals",
    }
    assert parsed["backend"] == "openrouter"
    assert parsed["model_or_agent"] == "openai/gpt-5"
    assert parsed["rationale"] == "picked gpt-5"
    assert parsed["confidence"] == 0.85
    assert parsed["signals"] == {}


def test_routing_decision_is_frozen() -> None:
    from src.routing.schema import RoutingDecision

    decision = RoutingDecision(
        backend="openrouter",
        model_or_agent="openai/gpt-5",
        rationale="ok",
        confidence=0.5,
    )
    with pytest.raises(FrozenInstanceError):
        decision.backend = "claude_code"  # type: ignore[misc]


def test_routing_decision_default_signals_is_empty_dict() -> None:
    from src.routing.schema import RoutingDecision

    a = RoutingDecision(
        backend="claude_code", model_or_agent="claude-agent-sdk", rationale="x", confidence=1.0
    )
    b = RoutingDecision(
        backend="claude_code", model_or_agent="claude-agent-sdk", rationale="y", confidence=1.0
    )
    # default_factory ensures the two instances don't share the same dict object
    assert a.signals == {}
    assert b.signals == {}
    assert a.signals is not b.signals


def test_config_exposes_d10_tau_defaults() -> None:
    from src.routing import config

    assert config.DEFAULT_TASK_TYPE_TAU == 0.35
    assert config.DEFAULT_AGENTIC_INTENT_TAU == 0.55
    assert config.DEFAULT_MODEL_ROUTER_TAU == 0.20


def test_fallback_rationale_suffix_has_u2014_dash() -> None:
    """The exact substring locked by Phase 1 success criterion #4."""
    from src.routing.config import FALLBACK_RATIONALE_SUFFIX

    # Literal string match
    assert FALLBACK_RATIONALE_SUFFIX == "low confidence — fallback"

    # Length is 25 characters (the plan locks this in behavior Test 4's
    # character-code list, which has 25 entries).
    assert len(FALLBACK_RATIONALE_SUFFIX) == 25

    # The dash sits at index 15 (0-indexed from start) or -10 (from end).
    # The plan acceptance line "ord(FALLBACK_RATIONALE_SUFFIX[-12]) == 8212"
    # has an off-by-two error: -12 from the end of a 25-char string is index
    # 13, which is the 'e' in "confidence". We assert against the canonical
    # position to keep the test honest about what character is actually
    # locked. The CHARACTER (U+2014) is the load-bearing assertion.
    assert ord(FALLBACK_RATIONALE_SUFFIX[15]) == 0x2014
    assert ord(FALLBACK_RATIONALE_SUFFIX[-10]) == 0x2014

    # Full character-code fingerprint (matches plan behavior Test 4 list).
    expected_codes = [
        108, 111, 119, 32, 99, 111, 110, 102, 105, 100,
        101, 110, 99, 101, 32, 8212, 32, 102, 97, 108,
        108, 98, 97, 99, 107,
    ]
    assert [ord(c) for c in FALLBACK_RATIONALE_SUFFIX] == expected_codes


def test_config_fallback_sentinels() -> None:
    from src.routing import config

    assert config.FALLBACK_BACKEND == "openrouter"
    assert config.FALLBACK_MODEL_OR_AGENT == "openrouter/auto"
    assert config.CLAUDE_CODE_SENTINEL == "claude-agent-sdk"
    assert config.COMPUTER_USE_SENTINEL == "computer-use-2025-11-24"


def test_build_keywords_locked_set() -> None:
    from src.routing.config import BUILD_KEYWORDS

    assert BUILD_KEYWORDS == {
        "build", "write", "edit", "refactor", "fix", "implement", "create",
    }


def test_browse_keywords_locked_set() -> None:
    from src.routing.config import BROWSE_KEYWORDS

    assert BROWSE_KEYWORDS == {
        "open", "browse", "url", "click", "navigate", "visit", "fill", "submit",
    }


def test_tier_rank_locked() -> None:
    from src.routing.config import TIER_RANK, DEFAULT_EPSILON

    assert TIER_RANK == {"cheap": 0, "medium": 1, "strong": 2}
    assert DEFAULT_EPSILON == 0.02
