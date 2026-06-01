"""agentic_completion — the EVAL-03 self-hosted agentic task-completion suite.

`inspect eval eval/suites/agentic_completion.py` drives the EXISTING
`apps.api.backends` streaming adapters against a self-hosted, contamination-free
task set (`eval/data/agentic_tasks.jsonl`) and scores each task with the hybrid
`artifact_or_judge` scorer (deterministic artifact check first; pinned LLM-judge
only when no artifact is checkable). It measures whether the Claude Code /
computer-use backends actually FINISH representative end-to-end tasks — the
"live demo-safe" bar (RELI-05).

The real-spend path is `live`/BYOK: a real run requires `ANTHROPIC_API_KEY`
(and `COMPUTER_USE_OPT_IN=1` for the computer_use tasks). The deterministic PR
gate never runs this suite — Plan 05's eval-gate.yml secret-gates it +
`workflow_dispatch`.

Runaway-spend defense is dual-layer (threat T-10-SPEND):
    - INNER fuse (here): per-sample hard caps token_limit/message_limit/
      time_limit + cost_limit (this inspect-ai build, 0.3.232, supports
      Task(cost_limit=...)) raise LimitExceededError so a single task cannot
      drain credits.
    - OUTER gate (Plan 05 ci_gate): the aggregate per-suite USD ceiling
      (eval.budgets.SUITE_USD_CEILING["agentic"]).

`epochs=Epochs(3, "mode")` runs each task three times and reduces to the modal
pass/fail (variance reduction → a stable verdict). `fail_on_error=0.2` tolerates
up to 20% sample errors so one flaky task does not abort the run.

Contamination is manual-authorship-by-design (EVAL-03 self-hosted scope): the
tasks are self-authored and reference NO public benchmark (SWE-bench / WebArena /
OSWorld / GAIA). Unlike the routing canary's hash-disjointness check, the
agentic guard is a grep-for-benchmark-names check only (benchmark prompts are
not in data_processed/, so a hash check is not applicable) — documented
Manual-Only in 10-VALIDATION.md.

Cross-refs:
    - eval/data/agentic_tasks.jsonl (self-hosted contamination-free task set)
    - eval/solvers/adapter_solver.py (per-task backend dispatch + Done.cost_usd sum)
    - eval/scorers/artifact_checks.py (artifact_or_judge hybrid scorer)
    - apps/api/routes/turn.py:982-1117 (the production stream loop the tasks mirror)
    - 10-RESEARCH.md §Pattern 3 (per-task caps, Epochs, fail_on_error)
    - 10-PATTERNS.md §eval/suites/agentic_completion.py
"""

from __future__ import annotations

from pathlib import Path

from inspect_ai import Epochs, Task, task
from inspect_ai.dataset import Sample, json_dataset

from eval.scorers.artifact_checks import artifact_or_judge
from eval.solvers.adapter_solver import adapter_solver

# Resolve the dataset relative to the repo root (this file lives at
# eval/suites/agentic_completion.py -> parents[2] is the repo root) so the suite
# loads the same task set regardless of inspect-ai's working directory.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_TASKS_PATH = _REPO_ROOT / "eval" / "data" / "agentic_tasks.jsonl"

# Per-sample hard caps (10-RESEARCH §Pattern 3 — the inner runaway-spend fuse).
_TOKEN_LIMIT = 200_000
_MESSAGE_LIMIT = 60
_TIME_LIMIT = 600  # seconds
# Per-sample USD ceiling (Task cost_limit is supported in inspect-ai 0.3.232).
# Sized above the per-task max_cost_usd in the dataset (<=1.00) with headroom
# for the judge call; the aggregate suite ceiling is enforced by Plan 05.
_COST_LIMIT = 2.00
_FAIL_ON_ERROR = 0.2  # tolerate <=20% sample errors


def agentic_record_to_sample(record: dict) -> Sample:
    """Map one agentic_tasks.jsonl record into an inspect-ai Sample.

    The full task spec is carried in `metadata["task_spec"]` so `adapter_solver`
    can read the per-task `backend`, caps (`max_cost_usd`/`max_steps`), and
    `goal`, and `artifact_or_judge` can read the `artifact_spec` (or the
    `judge_scored` marker). The Sample target is the gold criterion (used by the
    judge for judge-scored tasks; deterministic tasks ignore it).
    """

    return Sample(
        id=record["id"],
        input=record["goal"],
        target=record.get("gold_criterion", ""),
        metadata={"task_spec": record},
    )


@task
def agentic_completion() -> Task:
    """Self-hosted agentic suite: per-task backend dispatch + hybrid scoring.

    Runs the streaming adapters under per-sample hard caps and 3-epoch modal
    reduction. The real-spend path is `live`/BYOK — a real run needs
    `ANTHROPIC_API_KEY` (+ `COMPUTER_USE_OPT_IN=1` for computer_use tasks):

        ANTHROPIC_API_KEY=... inspect eval eval/suites/agentic_completion.py --epochs 1
    """

    return Task(
        dataset=json_dataset(str(_TASKS_PATH), agentic_record_to_sample),
        # adapter_solver dispatches the per-task backend from task_spec["backend"];
        # the default below is the fallback when a record omits a backend.
        solver=adapter_solver(backend="claude_code"),
        scorer=artifact_or_judge(),
        epochs=Epochs(3, "mode"),
        token_limit=_TOKEN_LIMIT,
        message_limit=_MESSAGE_LIMIT,
        time_limit=_TIME_LIMIT,
        cost_limit=_COST_LIMIT,
        fail_on_error=_FAIL_ON_ERROR,
    )
