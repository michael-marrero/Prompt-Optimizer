# Plan 06 Task 1 — policy.py rule-cascade tests (D-01 + ROUTER-06).
#
# Covers behavior tests 7-12 from the plan:
#   7.  decide_backend(agentic + coding task) -> claude_code.
#   8.  decide_backend(agentic + browse keywords) -> computer_use.
#   9.  decide_backend(non-agentic) -> openrouter (resolver runs upstream).
#   10. choose_final_route('gpt-5', mapping) -> api_model 'openai/gpt-5'.
#   11. choose_final_route('never-heard-of-this-model', mapping) -> OTHER entry.
#   12. quality_first_pick picks the cheaper tier when confidence ties.

from __future__ import annotations

import json
import os

import pytest

REPO_ROOT = os.path.abspath(os.path.join(__file__, "..", "..", "..", ".."))
MODEL_MAPPING_PATH = os.path.join(REPO_ROOT, "config", "model_mapping.json")


@pytest.fixture(scope="module")
def model_mapping() -> dict:
    with open(MODEL_MAPPING_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ----------------------------------------------------------------------
# decide_backend — D-01 cascade
# ----------------------------------------------------------------------


def test_decide_backend_agentic_coding_routes_to_claude_code() -> None:
    from src.routing.policy import decide_backend
    from src.routing.config import CLAUDE_CODE_SENTINEL

    backend, sentinel, reason = decide_backend(
        agentic_intent=True,
        agentic_confidence=0.9,
        task_type="coding",
        prompt="write a python parser",
    )
    assert backend == "claude_code"
    assert sentinel == CLAUDE_CODE_SENTINEL
    assert isinstance(reason, str) and len(reason) > 0


def test_decide_backend_agentic_instruction_following_routes_to_claude_code() -> None:
    # CONTEXT D-01 says "instruction-following" (dash); the label_encoder
    # may use the underscore form. policy.py must accept both.
    from src.routing.policy import decide_backend

    for label in ("instruction_following", "instruction-following"):
        backend, sentinel, _ = decide_backend(
            agentic_intent=True,
            agentic_confidence=0.9,
            task_type=label,
            prompt="follow these steps and produce a report",
        )
        assert backend == "claude_code", f"task_type={label!r} should match"


def test_decide_backend_agentic_build_keyword_routes_to_claude_code() -> None:
    from src.routing.policy import decide_backend

    backend, _, _ = decide_backend(
        agentic_intent=True,
        agentic_confidence=0.8,
        task_type="general",
        prompt="build me a finance app",
    )
    assert backend == "claude_code"


def test_decide_backend_agentic_browse_keywords_routes_to_computer_use() -> None:
    from src.routing.policy import decide_backend
    from src.routing.config import COMPUTER_USE_SENTINEL

    backend, sentinel, reason = decide_backend(
        agentic_intent=True,
        agentic_confidence=0.85,
        task_type="general",
        prompt="open https://x.com and click subscribe",
    )
    assert backend == "computer_use"
    assert sentinel == COMPUTER_USE_SENTINEL
    assert reason  # non-empty


def test_decide_backend_non_agentic_routes_to_openrouter() -> None:
    from src.routing.policy import decide_backend

    backend, sentinel, reason = decide_backend(
        agentic_intent=False,
        agentic_confidence=0.7,
        task_type="factual_qa",
        prompt="what is the capital of France",
    )
    assert backend == "openrouter"
    # OpenRouter branch returns None for the sentinel — the caller resolves
    # the concrete model via the model_router prediction + choose_final_route.
    assert sentinel is None
    assert reason


def test_decide_backend_agentic_no_keywords_no_coding_falls_to_openrouter() -> None:
    """Agentic-intent alone is NOT enough — the cascade also needs either a
    coding/instruction-following task type OR a build/browse keyword. A bare
    agentic conversational ask falls back to OpenRouter, matching the
    "every branch is debuggable from the rationale" principle of D-01."""
    from src.routing.policy import decide_backend

    backend, _, _ = decide_backend(
        agentic_intent=True,
        agentic_confidence=0.9,
        task_type="reasoning",  # not coding / not instruction-following
        prompt="please reason through this puzzle for me",  # no build/browse kw
    )
    assert backend == "openrouter"


# ----------------------------------------------------------------------
# choose_final_route — lifted from demo_router.py:224-250
# ----------------------------------------------------------------------


def test_choose_final_route_known_slug_returns_api_model(model_mapping: dict) -> None:
    from src.routing.policy import choose_final_route

    info = choose_final_route("gpt-5", model_mapping)
    assert info["api_model"] == "openai/gpt-5"
    assert info["source"] == "model_router"
    assert info["provider"] == "openrouter"
    assert info["openrouter_verified"] is True


def test_choose_final_route_unknown_slug_falls_to_other(model_mapping: dict) -> None:
    from src.routing.policy import choose_final_route

    info = choose_final_route("never-heard-of-this-model", model_mapping)
    assert info["api_model"] is None
    assert info["source"] == "fallback_other"
    assert info["original_prediction"] == "never-heard-of-this-model"
    assert info["openrouter_verified"] is False


def test_choose_final_route_no_other_in_mapping_returns_sentinel() -> None:
    from src.routing.policy import choose_final_route

    tiny_mapping = {"only-one-model": {"display_name": "Only", "api_model": "x"}}
    info = choose_final_route("missing-slug", tiny_mapping)
    assert info["source"] == "unmapped_prediction"
    assert info["api_model"] is None
    assert info["openrouter_verified"] is False


# ----------------------------------------------------------------------
# quality_first_pick — ROUTER-06 cost tiebreaker
# ----------------------------------------------------------------------


def test_quality_first_pick_tiebreak_prefers_cheaper_tier(model_mapping: dict) -> None:
    from src.routing.policy import quality_first_pick

    # gpt-5 (strong) and gemini-2.5-flash (medium) are within epsilon=0.02.
    # ROUTER-06 says when quality ties, pick the lower-cost tier — medium
    # ranks lower than strong, so gemini-2.5-flash wins.
    top_k = [
        ("gpt-5", 0.50),
        ("gemini-2.5-flash", 0.49),
        ("kimi-k2-0905", 0.30),
    ]
    chosen = quality_first_pick(top_k, model_mapping, epsilon=0.02)
    assert chosen == "gemini-2.5-flash"


def test_quality_first_pick_no_tie_returns_top(model_mapping: dict) -> None:
    from src.routing.policy import quality_first_pick

    # gap > epsilon: no tiebreak fires.
    top_k = [
        ("gpt-5", 0.80),
        ("gemini-2.5-flash", 0.40),
        ("kimi-k2-0905", 0.10),
    ]
    chosen = quality_first_pick(top_k, model_mapping, epsilon=0.02)
    assert chosen == "gpt-5"


def test_quality_first_pick_singleton(model_mapping: dict) -> None:
    from src.routing.policy import quality_first_pick

    chosen = quality_first_pick([("gpt-5", 0.99)], model_mapping, epsilon=0.02)
    assert chosen == "gpt-5"


def test_quality_first_pick_unknown_slug_treated_as_medium_tier(
    model_mapping: dict,
) -> None:
    """A model name not in mapping uses tier 'medium' (rank 1) per the
    quality_first_pick default. This keeps the tiebreaker deterministic
    even when the model_router predicts something that the mapping
    hasn't enumerated."""
    from src.routing.policy import quality_first_pick

    # Both unknown -> both rank 1 -> stable choice is the first
    top_k = [("unknown-a", 0.50), ("unknown-b", 0.49)]
    chosen = quality_first_pick(top_k, model_mapping, epsilon=0.02)
    assert chosen in {"unknown-a", "unknown-b"}
