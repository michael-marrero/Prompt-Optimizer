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
# route to computer-use. Verbatim from D-01.
BROWSE_KEYWORDS: frozenset[str] = frozenset({
    "open", "browse", "url", "click", "navigate", "visit", "fill", "submit",
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
