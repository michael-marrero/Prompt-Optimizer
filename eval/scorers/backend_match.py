"""backend_match — exact backend-label scorer + per-class measurement metrics.

The scorer compares the backend label `decide()` chose (written into
`state.output` by `route_solver`) against the hand-labeled `gold_backend` of the
frozen canary. The headline metrics are `accuracy()` + `stderr()` — a mean WITH a
confidence interval, never a bare point estimate (RouterBench: "a single mean with
no uncertainty is not an evaluation"; threat T-10-MEAS — false confidence).

Beyond the headline, two custom `@metric`s surface the per-class inputs the CI
gate / dimension analysis needs. These are MEASUREMENT ONLY — they describe how
the router currently behaves; they do NOT change routing. The actual ROUTER-08 /
ROUTER-09 fixes are Phase 13 work (10-AI-SPEC §5):

    D2 (ROUTER-08 cost asymmetry): `router08_cheap_to_expensive_misroute_rate`
        The fraction of cheap-backend (`openrouter`) gold prompts that were
        misrouted UP to an expensive agentic backend (`claude_code` /
        `computer_use`). This is the wallet-relevant confusion-matrix cell — a
        cheap chat prompt sent to a paid agent loop is the costly mistake.

    per-backend accuracy: `per_backend_accuracy`
        accuracy conditioned on each gold backend, so a class that the router
        systematically misses is visible even when overall accuracy looks fine.

Each Score also carries the gold/predicted labels and the predicted confidence in
`Score.metadata` so a downstream metric (or the CI gate, reading the full .eval
log) can compute the D3 ECE (predicted-confidence vs correctness) without
re-running the router.

Cross-refs:
    - src/evaluation/evaluate_routing.py (per-backend P/R + confusion-matrix domain analog)
    - eval/solvers/route_solver.py (sets state.output + stashes confidence/rationale)
    - 10-RESEARCH.md §Code Examples lines 418-424 (backend_match template)
    - 10-AI-SPEC.md §5 (D2 ROUTER-08 cost asymmetry, D3 ECE — measurement, not fix)
"""

from __future__ import annotations

from inspect_ai.scorer import (
    CORRECT,
    INCORRECT,
    Score,
    SampleScore,
    Target,
    Value,
    accuracy,
    metric,
    scorer,
    stderr,
)
from inspect_ai.solver import TaskState

# Cost-tier ordering (CONTEXT D-04). `openrouter` is the cheap conversational
# backend; `claude_code` and `computer_use` are the expensive agentic loops. The
# ROUTER-08 cost-asymmetry concern is the cheap -> expensive misroute (a cheap
# chat prompt sent up to a paid agent), so `openrouter` is the only "cheap" tier.
_CHEAP_BACKENDS = frozenset({"openrouter"})
_EXPENSIVE_BACKENDS = frozenset({"claude_code", "computer_use"})


@metric
def router08_cheap_to_expensive_misroute_rate() -> "metric":
    """D2 ROUTER-08 cost-asymmetry cell (measurement only).

    Fraction of cheap-backend (`openrouter`) gold prompts that the router sent
    UP to an expensive agentic backend. Denominator is the count of cheap-gold
    samples; returns 0.0 when there are none (no cheap-gold rows -> no asymmetry
    to measure).
    """

    def metric_fn(scores: list[SampleScore]) -> Value:
        cheap_gold = 0
        misrouted_up = 0
        for sample_score in scores:
            meta = sample_score.score.metadata or {}
            gold = meta.get("gold_backend")
            predicted = meta.get("predicted_backend")
            if gold in _CHEAP_BACKENDS:
                cheap_gold += 1
                if predicted in _EXPENSIVE_BACKENDS:
                    misrouted_up += 1
        return misrouted_up / cheap_gold if cheap_gold else 0.0

    return metric_fn


@metric
def per_backend_accuracy() -> "metric":
    """Per-backend accuracy conditioned on the gold label (measurement only).

    Returns a dict keyed by `accuracy_<backend>` so a class the router
    systematically misses stays visible even when overall accuracy looks fine.
    """

    def metric_fn(scores: list[SampleScore]) -> Value:
        totals: dict[str, int] = {}
        correct: dict[str, int] = {}
        for sample_score in scores:
            meta = sample_score.score.metadata or {}
            gold = meta.get("gold_backend")
            if gold is None:
                continue
            totals[gold] = totals.get(gold, 0) + 1
            if sample_score.score.value == CORRECT:
                correct[gold] = correct.get(gold, 0) + 1
        return {
            f"accuracy_{backend}": (correct.get(backend, 0) / count if count else 0.0)
            for backend, count in totals.items()
        }

    return metric_fn


@scorer(
    metrics=[
        accuracy(),
        stderr(),
        router08_cheap_to_expensive_misroute_rate(),
        per_backend_accuracy(),
    ]
)
def backend_match():
    """Exact backend-label scorer.

    `predicted` is `decide()`'s backend label (written into `state.output` by
    route_solver); `gold` is the canary `gold_backend` target. The Score value is
    CORRECT iff they match exactly. The decision rationale is carried as the
    explanation, and the gold/predicted labels + predicted confidence are stamped
    into `Score.metadata` so the custom per-class metrics and the downstream D3
    ECE can read them.
    """

    async def score(state: TaskState, target: Target) -> Score:
        predicted = state.output.completion.strip()
        gold = target.text.strip()
        meta = state.metadata or {}
        return Score(
            value=CORRECT if predicted == gold else INCORRECT,
            answer=predicted,
            explanation=meta.get("rationale"),
            metadata={
                "predicted_backend": predicted,
                "gold_backend": gold,
                # for the D3 ECE metric (predicted-confidence vs correctness)
                "confidence": meta.get("confidence"),
                "model_or_agent": meta.get("model_or_agent"),
            },
        )

    return score
