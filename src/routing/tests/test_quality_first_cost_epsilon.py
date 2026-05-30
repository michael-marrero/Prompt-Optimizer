# Plan 07-09 — within-OpenRouter quality-first regression guard (CR-01).
#
# Locks the BLOCKER from 07-VERIFICATION.md (CR-01 / Observable Truth #23 /
# ROUTING-PREFS-03): the Stage-5 quality-tied epsilon band in
# src/routing/decide.py must stay fixed at DEFAULT_EPSILON (0.02) and must
# NEVER widen when cost_aware_fallback=True or priority in {"cost", "speed"}.
#
# An earlier revision widened the band to as much as 0.12 (capped 0.25),
# letting quality_first_pick treat a model up to 12 points below the top-1
# router pick as "quality-tied" and select it on cost. That violated the
# LOCKED PROJECT.md constraint ("never optimize cost at the expense of
# expected answer quality") and ROUTER-06. This file makes the invariant a
# deterministic test so the band can never silently re-widen.
#
# Three tests:
#   A. quality_first_pick holds the top-1 pick across a >DEFAULT_EPSILON gap
#      (and the documented OLD 0.12 band WOULD have flipped it). Deterministic
#      — no joblib / no NLTK.
#   B. enabling cost prefs does not change decide().model_or_agent on the
#      OpenRouter path (the ROUTER-06 contract through decide()).
#   C. decide().signals["cost_epsilon"] <= DEFAULT_EPSILON for priority in
#      {"cost", "speed"} with cost_aware_fallback=True (the ceiling guard).
#
# stdlib + pytest only; no HTTP / SDK imports (keeps the D-18 import-graph
# guard green). Tests B/C carry an env-robustness skip for the artifact /
# NLTK-dependent path so they never produce a false RED on a machine without
# the joblib models; Test A carries the invariant unconditionally.

from __future__ import annotations

import json
import os

import pytest

from src.routing.config import DEFAULT_EPSILON
from src.routing.policy import quality_first_pick

REPO_ROOT = os.path.abspath(os.path.join(__file__, "..", "..", "..", ".."))
MODEL_MAPPING_PATH = os.path.join(REPO_ROOT, "config", "model_mapping.json")


@pytest.fixture(scope="module")
def model_mapping() -> dict:
    with open(MODEL_MAPPING_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ----------------------------------------------------------------------
# Test A — within-OpenRouter invariant via quality_first_pick (deterministic)
# ----------------------------------------------------------------------


def test_quality_first_pick_holds_top1_across_gap_at_default_epsilon(
    model_mapping: dict,
) -> None:
    """The quality pick holds when the top-1 leads the runner-up by MORE than
    DEFAULT_EPSILON, even though the runner-up is a strictly cheaper tier.

    gpt-5 is tier 'strong'; granite-3.3-8b-instruct is tier 'cheap'. The gap
    (0.72 - 0.60 = 0.12) is far wider than DEFAULT_EPSILON (0.02), so cost
    cannot win — quality_first_pick must return the top-1, gpt-5. The second
    assertion demonstrates the OLD widened band (0.12) WOULD have flipped the
    pick to the cheap tier, which is exactly the CR-01 regression this test
    guards against: 0.12 is the broken behavior, 0.02 is the fix."""
    top_k = [("gpt-5", 0.72), ("granite-3.3-8b-instruct", 0.60)]

    # The fix: at DEFAULT_EPSILON the >0.02 gap means no tie — quality holds.
    assert (
        quality_first_pick(top_k, model_mapping, epsilon=DEFAULT_EPSILON) == "gpt-5"
    )

    # The documented broken behavior: the old 0.12 band admitted the cheaper
    # tier as "tied on quality" and flipped the pick. This proves WHY the
    # ceiling matters — re-widening to 0.12 would re-introduce the violation.
    assert (
        quality_first_pick(top_k, model_mapping, epsilon=0.12)
        == "granite-3.3-8b-instruct"
    )


# ----------------------------------------------------------------------
# Test B — pick unchanged by cost prefs through decide() (ROUTER-06 contract)
# ----------------------------------------------------------------------


def test_cost_prefs_do_not_change_openrouter_pick_through_decide() -> None:
    """Enabling priority='cost' + cost_aware_fallback=True must NOT change the
    chosen model on a non-agentic OpenRouter prompt. A plain factual ask
    ("What is the capital of France?") routes through Stage 5 to OpenRouter
    (it does NOT short-circuit at the Stage-3 agentic cascade), so Stage 5 — the
    band logic under test — actually fires.

    Mirrors the env-robustness guard from apps/api/tests/test_routing_prefs.py
    Test 4: the import and the decide() calls are wrapped so the test skips
    cleanly (never a false RED) if the routing artifacts or NLTK data are
    unavailable in the environment. The deterministic invariant lives in
    Test A and runs unconditionally."""
    try:
        from src.routing.decide import decide

        prompt = "What is the capital of France?"
        baseline = decide(prompt)
        with_cost_prefs = decide(
            prompt,
            settings={"priority": "cost", "cost_aware_fallback": True},
        )
    except Exception as exc:  # noqa: BLE001 — artifacts/NLTK may be unavailable
        pytest.skip(f"routing artifacts / NLTK unavailable: {exc!r}")

    # The factual prompt routes to OpenRouter on both runs.
    assert baseline.backend == "openrouter"
    assert with_cost_prefs.backend == "openrouter"

    # ROUTER-06: enabling the cost prefs did NOT change the chosen model.
    assert with_cost_prefs.model_or_agent == baseline.model_or_agent


# ----------------------------------------------------------------------
# Test C — cost_epsilon ceiling guard (the locked decision)
# ----------------------------------------------------------------------


@pytest.mark.parametrize("priority", ["cost", "speed"])
def test_cost_epsilon_never_exceeds_default_epsilon(priority: str) -> None:
    """decide().signals['cost_epsilon'] must never exceed DEFAULT_EPSILON for
    the OpenRouter path, for any cost-leaning preference combination — the
    band can never widen. Reuses the same artifact-availability skip guard as
    Test B; if a run short-circuits before Stage 5 (so 'cost_epsilon' is absent
    from signals), the ceiling assertion is skipped for that run rather than
    failing."""
    try:
        from src.routing.decide import decide

        decision = decide(
            "What is the capital of France?",
            settings={"priority": priority, "cost_aware_fallback": True},
        )
    except Exception as exc:  # noqa: BLE001 — artifacts/NLTK may be unavailable
        pytest.skip(f"routing artifacts / NLTK unavailable: {exc!r}")

    if "cost_epsilon" not in decision.signals:
        pytest.skip(
            "prompt short-circuited before Stage 5 — no cost_epsilon recorded"
        )

    assert decision.signals["cost_epsilon"] <= DEFAULT_EPSILON
