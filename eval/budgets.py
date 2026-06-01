"""CI-gate budget constants + the disjointness tuning-file set (EVAL-04).

This module is the budget / success-band substrate for the EVAL-04 CI gate.
It is a PURE-CONFIG module: SCREAMING_SNAKE_CASE module constants only, no
`print()`, and — critically — it imports NO eval-only heavy dependency (in
particular not the inspect harness package). Keeping it import-light lets
Layer-0 tests read every gate constant key-free and preserves the D-18 one-way
arrow (eval/ -> src/routing) plus threat T-10-01 (no eval-only heavy dep is
reachable from a path src/ could import).

Conventions copied from `src/routing/config.py` (SCREAMING_SNAKE_CASE module
constants) and `apps/api/backends/pricing.py` (per-Mtok USD price-table shape).

Cross-refs:
    - src/routing/config.py (module-constant convention)
    - apps/api/backends/pricing.py (USD price-table shape)
    - 10-PATTERNS.md §eval/budgets.py (Open Question 1 exclusion)
    - 10-RESEARCH.md §Package Legitimacy / §Pinned judge model
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Per-suite USD ceilings (EVAL-04 cost guard)
# ---------------------------------------------------------------------------
# The routing suite is fully key-free (it calls `decide()` locally, makes no
# provider calls), so its spend ceiling is exactly $0.00. The agentic suite
# runs model-graded tasks against real backends; the ceiling bounds a 3-epoch
# run of ~10-20 tasks. $15.00 leaves headroom over the D-04 per-turn ceilings
# (OpenRouter $0.50 / Claude Code $2.00 / computer-use $2.00) while staying a
# low double-digit-dollar guard the CI gate can hard-stop on.
SUITE_USD_CEILING: dict[str, float] = {
    "routing": 0.0,
    "agentic": 15.00,
}

# ---------------------------------------------------------------------------
# Per-suite success bands (EVAL-04 quality gate)
# ---------------------------------------------------------------------------
# BAND_LOW = hard floor (below this the gate FAILS). BAND_TARGET = aspirational
# pass bar. Routing floors are anchored to the existing 42-row canary baseline
# (Phase 1 Plan 07: backend_accuracy ~= 0.9048); band_low is set conservatively
# below that observed value, band_target at the observed level. Agentic bands
# are PLACEHOLDERS to be tuned once the multi-epoch agentic suite has real runs.
BAND_LOW: dict[str, float] = {
    "routing": 0.80,
    "agentic": 0.50,  # placeholder — tune with epochs
}
BAND_TARGET: dict[str, float] = {
    "routing": 0.90,
    "agentic": 0.70,  # placeholder — tune with epochs
}

# ---------------------------------------------------------------------------
# Judge model price table (USD per million tokens)
# ---------------------------------------------------------------------------
# The agentic suite grades with the pinned judge `anthropic/claude-sonnet-4-6`
# (10-PATTERNS.md §model_graded_qa). Rates are USD per 1M tokens, mirroring the
# per-Mtok shape of apps/api/backends/pricing.py. Used to estimate judge spend
# against SUITE_USD_CEILING before a run.
JUDGE_PRICE_PER_MTOK: dict[str, float] = {
    # anthropic/claude-sonnet-4-6 — documented Sonnet-class rate
    "input_per_mtok": 3.00,
    "output_per_mtok": 15.00,
}

# ---------------------------------------------------------------------------
# Disjointness tuning-file set (EVAL-02 substrate, Open Question 1)
# ---------------------------------------------------------------------------
# The canary eval set MUST be hash-disjoint from the *tuning* CSVs in
# data_processed/. `routing_decision_eval.csv` is EXCLUDED from the scan: it is
# itself an eval set (the 42-row canary), not tuning data, so including it would
# guarantee a false-positive overlap. This exclusion is documented in-code so a
# future edit cannot silently re-include it and break the disjointness check
# (threat T-10-02). The set below is the explicit, locked list of files the
# disjointness scan hashes.
DISJOINTNESS_TUNING_FILES: frozenset[str] = frozenset(
    {
        "agentic_intent_negatives.csv",
        "agentic_intent_seeds.csv",
        "agentic_intent_synthesized.csv",
        "agentic_intent_training.csv",
        "classifier_training_features.csv",
        "classifier_training_with_types.csv",
        "classifier_training.csv",
        "router_training_dataset_top_models.csv",
        "router_training_dataset.csv",
        # NOTE: routing_decision_eval.csv is DELIBERATELY ABSENT — it is an eval
        # set, not tuning data (Open Question 1). Do not re-add it.
    }
)

# Files explicitly excluded from the disjointness scan (documented exclusions).
TUNING_CSV_GLOB_EXCLUDE: frozenset[str] = frozenset(
    {
        "routing_decision_eval.csv",  # eval set, not tuning data (Open Question 1)
    }
)
