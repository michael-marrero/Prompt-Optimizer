"""Routing-brain configuration constants.

All tunables live here so Plan 07's evaluator can sweep them without
touching `decide.py`. SCREAMING_SNAKE_CASE per CLAUDE.md Naming Patterns.

Locked by CONTEXT D-04 / D-10 / D-11 / D-12 / D-18:

    DEFAULT_TASK_TYPE_TAU       = 0.35   # 10+ task-type classes; broad bins
    DEFAULT_AGENTIC_INTENT_TAU  = 0.55   # binary head; expect crisp probs
    DEFAULT_MODEL_ROUTER_TAU    = 0.20   # 16-class router; lower floor

    FALLBACK_BACKEND            = "openrouter"
    FALLBACK_MODEL_OR_AGENT     = "openrouter/auto"
    FALLBACK_RATIONALE_SUFFIX   = "low confidence — fallback"  # U+2014 dash

    CLAUDE_CODE_SENTINEL        = "claude-agent-sdk"
    COMPUTER_USE_SENTINEL       = "computer-use-2025-11-24"

    BUILD_KEYWORDS              = {build, write, edit, refactor, fix,
                                   implement, create}  # D-01 verbatim
    BROWSE_KEYWORDS             = {open, browse, url, click, navigate,
                                   visit, fill, submit}  # D-01 verbatim

This module imports ONLY stdlib (`os`) so it does not introduce any
forbidden module into the `src.routing.*` import graph (D-18).
"""

from __future__ import annotations

import os

# ----------------------------------------------------------------------
# Path discovery preamble (canonical CLAUDE.md / 01-PATTERNS.md pattern)
# ----------------------------------------------------------------------

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")


# ----------------------------------------------------------------------
# Per-stage confidence thresholds (CONTEXT D-10)
# ----------------------------------------------------------------------

# Task-type classifier (10+ classes including the literal `unknown` OOD
# sentinel from D-09). Bins are broad so a 0.35 floor catches near-ties
# without being too aggressive about the fallback path.
DEFAULT_TASK_TYPE_TAU: float = 0.35

# Agentic-intent binary classifier. Calibrated head with ECE = 0.0364
# (Plan 04). 0.55 chosen because Platt-scaled binary probabilities are
# sharp and a 0.55 floor still admits clearly-agentic prompts.
DEFAULT_AGENTIC_INTENT_TAU: float = 0.55

# Model router (16-class head over the top-N benchmark slugs + OTHER).
# Higher cardinality => lower floor by design; 0.20 lets the top-1 win
# unless the distribution is genuinely flat.
DEFAULT_MODEL_ROUTER_TAU: float = 0.20


# ----------------------------------------------------------------------
# Fallback sentinels (CONTEXT D-11 + D-12)
# ----------------------------------------------------------------------

# Fallback ALWAYS routes to OpenRouter (D-12: never silently fall back to
# Claude Code or computer-use). The api_model `openrouter/auto` is
# OpenRouter's own meta-router which gives broad coverage.
FALLBACK_BACKEND: str = "openrouter"
FALLBACK_MODEL_OR_AGENT: str = "openrouter/auto"

# The exact substring a fallback decision's `rationale` MUST end with.
# Locked by ROADMAP Phase 1 success criterion #4 and asserted by the
# unit tests in src/routing/tests/test_uncertainty_fallback.py.
#
# Character codes (25 chars total): the dash is U+2014 (EM DASH; the
# plan text calls it "en-dash" but the locked character code is 8212
# which is U+2014 EM DASH — the byte is what matters for the substring
# check, not the Unicode name).
FALLBACK_RATIONALE_SUFFIX: str = "low confidence — fallback"


# ----------------------------------------------------------------------
# Backend sentinels for Claude Code + computer-use (CONTEXT D-04)
# ----------------------------------------------------------------------

# Plan 06's contract: adapters consume the string in `model_or_agent`
# directly. These two sentinels are the canonical identifiers for the
# non-OpenRouter backends.
CLAUDE_CODE_SENTINEL: str = "claude-agent-sdk"
COMPUTER_USE_SENTINEL: str = "computer-use-2025-11-24"


# ----------------------------------------------------------------------
# Rule-cascade keyword sets (CONTEXT D-01)
# ----------------------------------------------------------------------

# Build / edit verbs that, when combined with agentic_intent=True, route
# to Claude Code. Verbatim from D-01.
BUILD_KEYWORDS: frozenset[str] = frozenset({
    "build", "write", "edit", "refactor", "fix", "implement", "create",
})

# Browse / interact verbs that, when combined with agentic_intent=True,
# route to computer-use. The first row is the D-01 verbatim set; the second
# row is Story 6.3's conservative extension — high-precision browse phrases
# only. Ambiguous single words ("read"/"check"/"search"/"find") are
# deliberately EXCLUDED — a URL/web-domain (WEB_TLDS + the policy matcher) is
# the disambiguator for those. Substring-matched, so multi-word phrases work.
BROWSE_KEYWORDS: frozenset[str] = frozenset({
    "open", "browse", "url", "click", "navigate", "visit", "fill", "submit",
})
# Story 6.3 NOTE: a keyword expansion (headlines/log in/sign in/…) was trialled
# and REJECTED in code review — substring matching bled across word boundaries
# ("sign in" ⊂ "de-sign in the figma file", "log in" ⊂ "cata-log in-formation")
# and generic verbs over-captured coding prompts. The URL/web-domain matcher
# (WEB_TLDS below + policy._contains_url_or_domain) is the sole 6.3 signal; the
# D-01 verbatim keyword set above is unchanged.

# Story 6.3 — curated web TLDs for URL / bare-domain browse detection (the
# D-15 "URL -> computer-use" signal, finally implemented). A website named in
# an agentic prompt (with no competing coding signal — see policy.py) is a
# high-precision browse signal. This list EXCLUDES source-code file extensions
# (py, js, ts, go, rs, md, json, …) so "app.py" never reads as a domain, and
# EXCLUDES short word-like TLDs (me, to, so, ly, tv, …) that collide with
# ordinary prose ("read.me", "note.to"). The policy matcher additionally
# rejects numbers ("3.14"), initialisms ("U.S."), and email domains ("a@b.com").
WEB_TLDS: frozenset[str] = frozenset({
    "com", "org", "net", "io", "gov", "edu", "co", "ai", "dev", "app", "news",
})


# ----------------------------------------------------------------------
# Quality-first cost tiebreaker (ROUTER-06)
# ----------------------------------------------------------------------

# Tier ranks for the cost tiebreaker — lower rank == lower cost == picked
# when multiple model-router predictions tie on confidence.
TIER_RANK: dict[str, int] = {"cheap": 0, "medium": 1, "strong": 2}

# Confidence delta below which two predictions are considered "tied" and
# the tier ranking breaks the tie. 0.02 chosen per RESEARCH §Pattern 6
# (Plan 06 default; Plan 07 can sweep it).
DEFAULT_EPSILON: float = 0.02


# ----------------------------------------------------------------------
# Default artifact paths (used by _load_default_artifacts in decide.py)
# ----------------------------------------------------------------------

DEFAULT_ARTIFACT_PATHS: dict[str, str] = {
    "task_type_classifier": os.path.join(MODELS_DIR, "task_type_classifier.joblib"),
    "agentic_intent_classifier": os.path.join(MODELS_DIR, "agentic_intent_classifier.joblib"),
    "model_router": os.path.join(MODELS_DIR, "model_router.joblib"),
}

DEFAULT_MODEL_MAPPING_PATH: str = os.path.join(CONFIG_DIR, "model_mapping.json")


# ----------------------------------------------------------------------
# Calibration coverage contract (DEF-3 / Story 2.1)
# ----------------------------------------------------------------------

# Declarative single source of truth for which routing heads MUST be
# calibrated (vs. may use raw predict_proba) and each head's ECE ceiling.
# Keys mirror DEFAULT_ARTIFACT_PATHS above — the heads decide.py loads for
# the live cascade. Story 2.2 enforces this at artifact-load time; Story
# 2.3 consumes the per-head ece_threshold in the eval gate (replacing the
# lone global evaluate_routing.ECE_THRESHOLD = 0.10).
#
# ece_threshold defaults to 0.10 for every head — the value of today's
# single global gate — so this declaration changes NO thresholds; it only
# makes coverage explicit and per-head-tunable later.
#
# tier_router and embedding_router are intentionally EXCLUDED: neither is
# loaded by decide.py (both are experimental / off the live path) and
# tier_router was deliberately left uncalibrated (Plan 05). If either is
# ever promoted onto the live path it MUST be added here — the consistency
# test in tests/test_calibration_coverage.py fails otherwise.
CALIBRATION_COVERAGE: dict[str, dict[str, object]] = {
    "task_type_classifier": {"required_calibrated": True, "ece_threshold": 0.10},
    "agentic_intent_classifier": {"required_calibrated": True, "ece_threshold": 0.10},
    "model_router": {"required_calibrated": True, "ece_threshold": 0.10},
}


def required_calibrated_heads() -> list[str]:
    """Return the sorted head names the contract requires to be calibrated.

    Single source of truth for Story 2.2 (load-time enforcement) and Story
    2.3 (eval gate) — neither should re-hardcode the head list.
    """
    return sorted(
        head
        for head, record in CALIBRATION_COVERAGE.items()
        if record["required_calibrated"]
    )


def ece_threshold_for(head: str) -> float:
    """Return the per-head ECE threshold the contract sets for `head`.

    Companion accessor to `required_calibrated_heads()`; single source of
    truth for Story 2.3's eval gate so it never re-hardcodes 0.10. Raises
    KeyError if `head` is not in the manifest (a required head always is).
    """
    return float(CALIBRATION_COVERAGE[head]["ece_threshold"])


# ----------------------------------------------------------------------
# Task-type labels that count as "coding/instruction-following" for the
# D-01 cascade. CONTEXT D-01 spells the second one with a hyphen
# ("instruction-following") but the existing label_encoder uses the
# underscore form. Cover both so the cascade is robust to either
# spelling.
# ----------------------------------------------------------------------

CODING_TASK_TYPES: frozenset[str] = frozenset({
    "coding",
    "instruction_following",
    "instruction-following",
})
