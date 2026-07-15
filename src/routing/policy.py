"""Pure routing-policy helpers — D-01 rule cascade + cost tiebreaker.

This module is deliberately framework-free and side-effect-free (D-18).
It imports ONLY stdlib + `src.routing.config` so the import-graph guard
in `test_decide_smoke.py` never trips on a transitive HTTP / SDK pull.

Three public functions:

  decide_backend(agentic_intent, agentic_confidence, task_type, prompt, ...)
      -> (backend, sentinel_or_none, rule_fired_reason)

      Hard-coded D-01 cascade. Returns the backend label, the concrete
      `model_or_agent` sentinel for non-OpenRouter backends (None for
      OpenRouter — the caller resolves the concrete model via the
      model-router prediction + choose_final_route), and a short
      reason string suitable for embedding in RoutingDecision.rationale.

  choose_final_route(predicted_model, model_mapping)
      -> dict

      Lifted verbatim from src/demo/demo_router.py:224-250. Translates
      a model_router prediction (e.g. "gpt-5") into a route info dict
      with display_name / provider / tier / api_model / source.
      Unmapped predictions fall through to the OTHER bucket (D-02);
      mappings without an OTHER entry get the synthetic sentinel.

  quality_first_pick(top_k_predictions, model_mapping, epsilon=DEFAULT_EPSILON)
      -> str (the picked slug)

      ROUTER-06 quality-first cost tiebreaker. When two or more
      predictions are within `epsilon` confidence of the top, pick the
      lowest-cost tier. This is the "quality first, cost as tiebreaker"
      policy from PROJECT.md verbatim — we never trade quality for
      cost, only break exact-or-near-exact ties on cost.

D-01 cascade reference (verbatim from 01-CONTEXT.md lines 29-33):

    if agentic_intent == True AND (task_type in {coding, instruction-following}
                                   OR keyword in BUILD_KEYWORDS)
        -> backend="claude_code"
    elif agentic_intent == True AND keyword in BROWSE_KEYWORDS
        -> backend="computer_use"
    else
        -> backend="openrouter"
"""

from __future__ import annotations

import re
from typing import Optional

from src.routing.config import (
    BROWSE_KEYWORDS,
    BUILD_KEYWORDS,
    CLAUDE_CODE_SENTINEL,
    CODING_TASK_TYPES,
    COMPUTER_USE_SENTINEL,
    DEFAULT_EPSILON,
    TIER_RANK,
    WEB_TLDS,
)

# Story 6.3 — URL / bare-domain browse signal (implements the D-15
# "URL -> computer-use" intent). Matches either an explicit http(s):// scheme
# (unambiguous) OR a bare hostname whose FINAL label is a curated web TLD
# (WEB_TLDS). Requiring a real TLD keeps it off code filenames ("app.py" — "py"
# not a TLD), numbers ("3.14"), and initialisms ("u.s.").
#
# Hardening from code review:
#   - Bounded quantifiers ({1,63} label, {0,4} subdomains) — DNS-realistic AND
#     they defeat the O(n^2) backtracking a dot-chain ("a.a.a…") caused on the
#     50k-char input bound (measured 5.7s at 32k before the bound).
#   - Negative lookbehind (?<![@\w.]) — the bare-domain host must not follow '@'
#     (email: "a@b.com" is a reference, not a browse target) or a word char / dot
#     (mid-token). Operates on the already-lowercased prompt.
# ponytail: one bounded regex over curated TLDs — no URL-parsing lib.
_TLD_ALT = "|".join(sorted(WEB_TLDS))
_URL_OR_DOMAIN_RE = re.compile(
    r"https?://\S+"
    r"|(?<![@\w.])[a-z0-9-]{1,63}(?:\.[a-z0-9-]{1,63}){0,4}\.(?:" + _TLD_ALT + r")\b"
)


def _contains_url_or_domain(prompt_lower: str) -> bool:
    """True if the prompt names a URL or a web domain (curated-TLD host)."""
    return _URL_OR_DOMAIN_RE.search(prompt_lower) is not None


# ----------------------------------------------------------------------
# D-01 rule cascade
# ----------------------------------------------------------------------


def _contains_any_keyword(prompt_lower: str, keywords) -> bool:
    """Return True if any keyword appears as a substring of prompt_lower.

    Substring match (not whole-word) because the build/browse keywords
    are short, distinctive verbs whose substring forms rarely produce
    false positives in conversational prompts. The 50,000-char input
    bound is enforced upstream in _agentic_features (Plan 02).
    """
    return any(kw in prompt_lower for kw in keywords)


def decide_backend(
    agentic_intent: bool,
    agentic_confidence: float,
    task_type: str,
    prompt: str,
    build_keywords=BUILD_KEYWORDS,
    browse_keywords=BROWSE_KEYWORDS,
    claude_code_sentinel: str = CLAUDE_CODE_SENTINEL,
    computer_use_sentinel: str = COMPUTER_USE_SENTINEL,
    coding_task_types=CODING_TASK_TYPES,
) -> tuple[str, Optional[str], str]:
    """Hard-coded D-01 rule cascade.

    Args:
      agentic_intent: True if the agentic-intent head predicted agentic.
      agentic_confidence: Calibrated max-prob from the agentic head.
        Currently unused by the cascade logic itself (the threshold
        check happens upstream in decide.py), but included in the
        signature so future policy refinements can use it without
        breaking the caller.
      task_type: Argmax label from the task-type classifier.
      prompt: Raw user prompt (for keyword extraction).
      build_keywords / browse_keywords / coding_task_types: Configurable
        keyword sets; defaults come from src.routing.config so tests
        and Plan 07 evaluations can pass custom sets without re-importing.
      claude_code_sentinel / computer_use_sentinel: Backend identifiers
        from src.routing.config.

    Returns:
      Tuple of (backend, model_or_agent_or_None, rule_fired_reason).
      For backend == "openrouter" the second element is None — the
      caller resolves the concrete model via the model_router head and
      choose_final_route below.
    """
    prompt_lower = (prompt or "").lower()
    has_build_keyword = _contains_any_keyword(prompt_lower, build_keywords)
    has_browse_keyword = _contains_any_keyword(prompt_lower, browse_keywords)
    is_coding_task = task_type in coding_task_types
    # Story 6.3: a URL/web-domain is a browse signal on its own (D-15). "return
    # the top headlines on bloomberg.com" has no browse VERB but is clearly a
    # browse task; the agentic gate upstream suppresses conversational domain
    # mentions. BUT a URL defers to a competing coding signal — "refactor the
    # client for api.stripe.com" / "clone github.com/x and fix the bug" name a
    # domain yet are coding tasks — so a bare URL only counts as browse when no
    # build keyword / coding task is present (an explicit browse keyword still
    # wins outright, e.g. "open github.com and click login"). This also mops up
    # domain-shaped code tokens (java.io, asp.net, self.app) that ride in coding
    # prompts. Code-review fix (over-capture).
    has_url = _contains_url_or_domain(prompt_lower)
    url_is_browse = has_url and not (has_build_keyword or is_coding_task)

    # ------------------------------------------------------------------
    # Branch ordering note (Rule 2 deviation from D-01 literal `elif`):
    #
    # D-01 spells the cascade as `if claude_code elif computer_use`,
    # which is first-match-wins on coding-task. In practice the
    # calibrated task-type classifier sometimes mis-classifies short
    # browse prompts (e.g. "open https://x.com and click subscribe")
    # as `coding` because URL tokens and short imperative verbs
    # overlap with the LLMRouterBench coding distribution. CONTEXT D-15
    # "Informational-URL" edge case explicitly says
    # `URL + action verb -> computer-use`, so when BOTH branches could
    # match we prefer the more specific browse-keyword branch.
    #
    # Concretely, the cascade is:
    #   1. agentic + browse_keyword -> computer_use  (most specific)
    #   2. agentic + (coding-task OR build_keyword) -> claude_code
    #   3. otherwise -> openrouter
    # ------------------------------------------------------------------

    # Branch 1 — agentic + browse keyword OR (URL/domain with no coding signal)
    if agentic_intent and (has_browse_keyword or url_is_browse):
        reason = (
            "agentic + URL/domain -> computer-use"
            if url_is_browse and not has_browse_keyword
            else "agentic + browse/interact keyword -> computer-use"
        )
        return ("computer_use", computer_use_sentinel, reason)

    # Branch 2 — agentic + (coding/instruction-following OR build kw)
    if agentic_intent and (is_coding_task or has_build_keyword):
        if is_coding_task and has_build_keyword:
            reason = "agentic + coding task + build keyword -> Claude Code"
        elif is_coding_task:
            reason = f"agentic + coding task ({task_type}) -> Claude Code"
        else:
            reason = "agentic + build/edit keyword -> Claude Code"
        return ("claude_code", claude_code_sentinel, reason)

    # ------------------------------------------------------------------
    # Branch 3 — everything else (conversational OR agentic-but-no-
    # build/browse signal) routes through OpenRouter. The concrete
    # model slug is resolved by the caller via the model_router head
    # and choose_final_route.
    # ------------------------------------------------------------------
    if agentic_intent:
        reason = "agentic without coding/build/browse signal -> OpenRouter"
    else:
        reason = "conversational (non-agentic) -> OpenRouter"
    return ("openrouter", None, reason)


# ----------------------------------------------------------------------
# choose_final_route — lifted verbatim from src/demo/demo_router.py:224-250
# ----------------------------------------------------------------------


def choose_final_route(predicted_model: str, model_mapping: dict) -> dict:
    """Convert a model-router prediction into a route-info dict.

    Lifted verbatim from `choose_final_route` at
    `src/demo/demo_router.py:224-250` (per 01-PATTERNS.md lines
    282-303). The function is duplicated here — rather than imported
    from `src.demo.demo_router` — because Plan 06's routing brain must
    NOT import from `src.demo` (the demo carries its own sys.path
    injection plus REPL helpers that the brain doesn't need).

    Behavior:
      - Known slug in mapping -> return its info dict + source="model_router".
      - Unknown slug + "OTHER" in mapping -> OTHER entry +
        source="fallback_other" + original_prediction=<slug>.
      - Unknown slug + no "OTHER" entry -> synthetic sentinel info dict
        with provider="simulated", api_model=None,
        source="unmapped_prediction".
    """
    if predicted_model in model_mapping:
        model_info = model_mapping[predicted_model].copy()
        model_info["source"] = "model_router"
        return model_info

    if "OTHER" in model_mapping:
        model_info = model_mapping["OTHER"].copy()
        model_info["source"] = "fallback_other"
        model_info["original_prediction"] = predicted_model
        return model_info

    return {
        "display_name": predicted_model,
        "provider": "simulated",
        "tier": "unknown",
        "api_model": None,
        "openrouter_verified": False,
        "source": "unmapped_prediction",
        "notes": "Predicted model was not found in model_mapping.json.",
    }


# ----------------------------------------------------------------------
# quality_first_pick — ROUTER-06 cost tiebreaker
# ----------------------------------------------------------------------


def quality_first_pick(
    top_k_predictions: list[tuple[str, float]],
    model_mapping: dict,
    epsilon: float = DEFAULT_EPSILON,
) -> str:
    """Pick the cheapest tier among predictions within `epsilon` of the top.

    ROUTER-06 + PROJECT.md "quality first, cost as tiebreaker":

      - The top-1 by probability is the QUALITY pick.
      - When the second-best (and possibly third-best) prediction is
        within `epsilon` confidence of the top, treat them as tied on
        quality and prefer the lower-cost tier.
      - Cost tier comes from model_mapping[slug]["tier"]; unknown tiers
        default to "medium" rank=1 so the picker stays deterministic.

    Args:
      top_k_predictions: List of (slug, probability) sorted by
        probability descending. Length 1 is allowed (no tie possible).
      model_mapping: The loaded config/model_mapping.json dict.
      epsilon: Confidence delta within which predictions are considered
        tied. Default 0.02 from src.routing.config.DEFAULT_EPSILON.

    Returns:
      The picked slug (string).

    Notes:
      We deliberately do NOT down-rank "strong" tier models below
      "cheap" or "medium" — the contract is: when QUALITY ties, fall
      back to COST. The top-1's tier is irrelevant unless it ties with
      a lower-tier alternative.
    """
    if not top_k_predictions:
        raise ValueError("quality_first_pick called with empty top_k_predictions")

    top_prob = top_k_predictions[0][1]
    contenders = [
        (slug, prob)
        for slug, prob in top_k_predictions
        if top_prob - prob <= epsilon
    ]

    if len(contenders) == 1:
        return contenders[0][0]

    # Break the tie by tier rank (lower rank == cheaper == preferred).
    # Unknown slug or missing tier defaults to medium=1 so the picker
    # is stable even when the model_router predicts something the
    # mapping doesn't enumerate.
    def _tier_rank(slug_and_prob: tuple[str, float]) -> int:
        slug = slug_and_prob[0]
        info = model_mapping.get(slug, {})
        tier = info.get("tier", "medium") if isinstance(info, dict) else "medium"
        return TIER_RANK.get(tier, 1)

    chosen_slug, _ = min(contenders, key=_tier_rank)
    return chosen_slug
