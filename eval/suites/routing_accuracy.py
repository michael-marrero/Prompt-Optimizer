"""routing_accuracy — the EVAL-02 backend-pick suite (free, deterministic, offline).

`inspect eval eval/suites/routing_accuracy.py` scores `decide()`'s backend label
against the frozen disjoint canary (Plan 02) and reports top-1 backend-pick
accuracy WITH stderr. It is the cheap half of the quality gate: it runs on every
PR with ZERO model spend.

The no-model guarantee has two layers (threat T-10-NET — wallet DoS):
    1. `route_solver` sets `state.output` directly and never invokes the generate
       callback (it scores the local joblib `decide()` in-process).
    2. A zero token limit on the Task is the belt-and-suspenders tripwire — even
       if a future edit reintroduced a model call, the suite would trip the limit
       rather than spend credits (10-RESEARCH §Pitfall 1).

The canary path is resolved relative to the repo root so the suite runs the same
whether inspect-ai's working directory is the repo root or elsewhere.

Cross-refs:
    - eval/data/canary_routing.jsonl (19 frozen rows: prompt_id/prompt/gold_backend)
    - eval/solvers/route_solver.py (non-model solver wrapping decide())
    - eval/scorers/backend_match.py (accuracy()+stderr() + per-class metrics)
    - 10-RESEARCH.md §Code Examples lines 410-435 (authoritative template)
"""

from __future__ import annotations

from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from eval.scorers.backend_match import backend_match
from eval.solvers.route_solver import route_solver

# Resolve the canary relative to the repo root (this file lives at
# eval/suites/routing_accuracy.py -> parents[2] is the repo root) so the suite
# loads the same frozen dataset regardless of inspect-ai's working directory.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_CANARY_PATH = _REPO_ROOT / "eval" / "data" / "canary_routing.jsonl"


@task
def routing_accuracy() -> Task:
    """Score decide() against the frozen canary — accuracy+stderr, zero spend."""
    return Task(
        dataset=json_dataset(
            str(_CANARY_PATH),
            FieldSpec(input="prompt", target="gold_backend", id="prompt_id"),
        ),
        solver=route_solver(),
        scorer=backend_match(),
        token_limit=0,  # tripwire: routing suite must never call a model
    )
