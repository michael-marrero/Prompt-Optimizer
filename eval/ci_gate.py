"""eval.ci_gate — the EVAL-04 merge gate (eval_set runner + tri-state exit code).

`python -m eval.ci_gate --suites routing` runs the selected suite(s) under
`inspect_ai.eval_set()` (resumable, auto-retry), reads each `.eval` log back
with `read_eval_log(..., header_only=False)`, and enforces the dual-layer cost
ceiling + multi-run success band, emitting the tri-state exit code:

    0   pass    — within the suite's USD ceiling AND accuracy >= BAND_TARGET
    78  warn    — within the ceiling but accuracy in [BAND_LOW, BAND_TARGET)
    1   block   — over the USD ceiling OR accuracy < BAND_LOW OR eval_set !success
                  OR an unrecognized @task name (fail-closed)

Per-suite correctness (BLOCKER fix — threat T-10-MISBKT): each EvalLog is scored
against ITS OWN suite's budget. The suite key is derived deterministically from
the log's `@task` name (`log.eval.task`) via the explicit `TASK_NAME_TO_SUITE`
map — NEVER from log order / a positional zip. The routing log is therefore
never measured against the agentic budget, nor the agentic log against the
routing budget. An unrecognized task name fails closed (exit 1).

Cost accounting (threat T-10-CEIL — wallet DoS): the total per-suite spend is
the SUM of two sources, because the agent's spend is NOT in `log.stats`:
    - judge USD : `log.stats.model_usage` x JUDGE_PRICE_PER_MTOK
                  (`ModelUsage.total_cost` when present; token-math fallback when
                  absent — 10-RESEARCH §Pitfall 4).
    - agent USD : summed per-sample `state.metadata["adapter_usage_usd"]`
                  (set by adapter_solver; 10-RESEARCH §Pitfall 5 — this requires
                  the FULL log, so we always read with header_only False).

This is an argparse CLI: `main(argv) -> int`; `if __name__ == "__main__":
sys.exit(main())`; print()-based output (no logging), matching the CLI shape of
apps/api/backends/claude_code/__main__.py and src/routing/__main__.py.

Cross-refs:
    - eval/budgets.py (SUITE_USD_CEILING / BAND_LOW / BAND_TARGET / JUDGE_PRICE_PER_MTOK)
    - eval/suites/routing_accuracy.py (@task routing_accuracy — key-free, free)
    - eval/suites/agentic_completion.py (@task agentic_completion — real-spend, BYOK)
    - eval/solvers/adapter_solver.py (state.metadata["adapter_usage_usd"])
    - 10-RESEARCH.md §Pattern 4 / §Pitfall 4 / §Pitfall 5
    - 10-AI-SPEC.md §5 Eval Tooling CI/CD (exit-code contract 0/1/78)
"""

from __future__ import annotations

import argparse
import sys

from inspect_ai import eval_set
from inspect_ai.log import read_eval_log

from eval.budgets import (
    BAND_LOW,
    BAND_TARGET,
    JUDGE_PRICE_PER_MTOK,
    SUITE_USD_CEILING,
)
from eval.suites.agentic_completion import agentic_completion
from eval.suites.routing_accuracy import routing_accuracy

# Exit-code contract (10-AI-SPEC.md §5). Named so all three are reachable and
# greppable in source.
EXIT_PASS = 0
EXIT_BLOCK = 1
EXIT_WARN = 78

# Pinned judge model (10-PATTERNS.md §model_graded_qa). The routing suite ignores
# it (token_limit=0, non-model solver); the agentic suite grades with it.
_JUDGE_MODEL = "anthropic/claude-sonnet-4-6"

# Where eval_set writes resumable .eval logs (logs/ is already gitignored).
_LOG_DIR = "logs/ci-run"

# Deterministic @task-name -> budgets.py suite-key map (threat T-10-MISBKT).
# The keys are the inspect-ai registered @task function names; the values are the
# eval.budgets dict keys. NEVER infer the suite from log order.
TASK_NAME_TO_SUITE: dict[str, str] = {
    "routing_accuracy": "routing",
    "agentic_completion": "agentic",
}

# Map a CLI suite selector to its @task callable.
_SUITE_TASKS = {
    "routing": routing_accuracy,
    "agentic": agentic_completion,
}


def _task_name(log) -> str:
    """Return the bare @task function name from an EvalLog.

    `log.eval.task` is the registered @task name (e.g. "routing_accuracy"). It
    may be module-qualified in some inspect-ai versions (e.g.
    "eval.suites.routing_accuracy@routing_accuracy" or a dotted path) — strip any
    module/registry prefix to the bare function name before the dict lookup so
    the suite-key resolution is stable across inspect-ai builds.
    """

    raw = log.eval.task or ""
    # Strip a registry prefix ("module@name") then any dotted path ("a.b.name").
    bare = raw.split("@")[-1]
    bare = bare.split(".")[-1]
    return bare


def _accuracy(log) -> float:
    """Read the reduced `accuracy` metric value from an EvalLog.

    The suites' scorers report `accuracy` (backend_match / artifact_or_judge).
    inspect-ai exposes it under `log.results.scores[*].metrics["accuracy"]`. We
    scan every score group so the lookup is robust to the scorer name.
    """

    results = getattr(log, "results", None)
    if results is None:
        raise ValueError("EvalLog has no results — cannot read accuracy")
    for score in results.scores or []:
        metric = (score.metrics or {}).get("accuracy")
        if metric is not None:
            return float(metric.value)
    raise ValueError("EvalLog results carry no 'accuracy' metric")


def _judge_usd(log) -> float:
    """Estimate judge USD from `log.stats.model_usage` (None-safe).

    Prefer `ModelUsage.total_cost` when the provider reported it; otherwise fall
    back to token-math against JUDGE_PRICE_PER_MTOK (10-RESEARCH §Pitfall 4). The
    routing suite has an empty model_usage, so this returns 0.0 for it.
    """

    in_rate = JUDGE_PRICE_PER_MTOK["input_per_mtok"]
    out_rate = JUDGE_PRICE_PER_MTOK["output_per_mtok"]
    total = 0.0
    usage = (getattr(log.stats, "model_usage", None) or {})
    for u in usage.values():
        if getattr(u, "total_cost", None) is not None:
            total += float(u.total_cost)
        else:
            total += (u.input_tokens or 0) / 1e6 * in_rate
            total += (u.output_tokens or 0) / 1e6 * out_rate
    return total


def _agent_usd(log) -> float:
    """Sum per-sample adapter spend from `state.metadata["adapter_usage_usd"]`.

    This value is NOT in `log.stats` — adapter_solver stashes it per sample, so
    the FULL log (header_only=False) is required (10-RESEARCH §Pitfall 5).
    """

    total = 0.0
    for sample in (log.samples or []):
        meta = sample.metadata or {}
        total += float(meta.get("adapter_usage_usd", 0.0) or 0.0)
    return total


def _gate_one_log(log, success: bool) -> int:
    """Score ONE full EvalLog against ITS OWN suite's budget; return its exit code.

    Resolves the suite key from the log's @task name (fail-closed on an
    unrecognized name), sums judge + agent USD, compares against that suite's
    ceiling/band, prints a suite-labeled breakdown, and returns 0 / 78 / 1.
    """

    name = _task_name(log)
    suite = TASK_NAME_TO_SUITE.get(name)
    if suite is None:
        # Fail closed — never silently apply the wrong suite's budget.
        print(
            f"[ci_gate] BLOCK: unrecognized @task name {name!r} "
            f"(log.eval.task={log.eval.task!r}); cannot resolve a suite budget. "
            f"Known: {sorted(TASK_NAME_TO_SUITE)}"
        )
        return EXIT_BLOCK

    ceiling = SUITE_USD_CEILING[suite]
    band_low = BAND_LOW[suite]
    band_target = BAND_TARGET[suite]

    judge_usd = _judge_usd(log)
    agent_usd = _agent_usd(log)
    total_usd = judge_usd + agent_usd
    acc = _accuracy(log)

    over_ceiling = total_usd > ceiling
    below_floor = acc < band_low
    in_warn_zone = band_low <= acc < band_target

    if over_ceiling or below_floor or not success:
        verdict = EXIT_BLOCK
    elif in_warn_zone:
        verdict = EXIT_WARN
    else:
        verdict = EXIT_PASS

    # Per-suite-labeled cost breakdown (threat T-10-MISBKT debuggability).
    print(f"[ci_gate] suite={suite!r} (@task {name!r})")
    print(
        f"          accuracy={acc:.4f}  "
        f"band_low={band_low:.4f}  band_target={band_target:.4f}"
    )
    print(
        f"          judge_usd=${judge_usd:.4f}  agent_usd=${agent_usd:.4f}  "
        f"total_usd=${total_usd:.4f}  ceiling=${ceiling:.4f}"
    )
    reasons = []
    if not success:
        reasons.append("eval_set reported failure")
    if over_ceiling:
        reasons.append(f"over ceiling (${total_usd:.4f} > ${ceiling:.4f})")
    if below_floor:
        reasons.append(f"below band_low ({acc:.4f} < {band_low:.4f})")
    if in_warn_zone and verdict == EXIT_WARN:
        reasons.append(f"warn zone ({acc:.4f} < band_target {band_target:.4f})")
    label = {EXIT_PASS: "PASS", EXIT_WARN: "WARN", EXIT_BLOCK: "BLOCK"}[verdict]
    detail = ("; ".join(reasons)) if reasons else "within ceiling and at/above band_target"
    print(f"          verdict={label} (exit {verdict}) — {detail}")
    return verdict


def main(argv: list[str] | None = None) -> int:
    """Argparse entry point — returns the tri-state process exit code (0/1/78)."""

    parser = argparse.ArgumentParser(
        prog="python -m eval.ci_gate",
        description=(
            "EVAL-04 merge gate: run the selected eval suite(s) under eval_set, "
            "then enforce each suite's own USD ceiling + success band and emit "
            "the tri-state exit code (0 pass / 78 warn / 1 block)."
        ),
    )
    parser.add_argument(
        "--suites",
        nargs="+",
        choices=sorted(_SUITE_TASKS),
        default=["routing"],
        help="Suite selector(s): routing, agentic, or both (default: routing).",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=3,
        help="Epochs per task for multi-run variance reduction (default: 3).",
    )
    args = parser.parse_args(argv)

    # De-dup while preserving order so `--suites routing routing` is harmless.
    selected = list(dict.fromkeys(args.suites))
    tasks = [_SUITE_TASKS[name]() for name in selected]

    # The judge model is ONLY needed by the agentic suite. Passing it for a
    # routing-only run would eagerly resolve the Anthropic provider (which needs
    # a key / a newer anthropic package), breaking the key-free guarantee of the
    # routing gate. So we pass the judge model only when an agentic suite is in
    # the selection; the routing suite ignores any model anyway (token_limit=0).
    model = _JUDGE_MODEL if "agentic" in selected else None

    print(
        f"[ci_gate] running suites={selected} epochs={args.epochs} "
        f"model={model!r} under eval_set (log_dir={_LOG_DIR!r})"
    )

    # eval_set is the resumable / auto-retry runner.
    eval_set_kwargs = {"tasks": tasks, "log_dir": _LOG_DIR, "epochs": args.epochs}
    if model is not None:
        eval_set_kwargs["model"] = model
    success, logs = eval_set(**eval_set_kwargs)

    if not logs:
        print("[ci_gate] BLOCK: eval_set produced no logs")
        return EXIT_BLOCK

    # Gate on the eval_set success bool PLUS per-suite metric/cost assertions,
    # never on a bare process exit code. Re-read each log FULL (header_only=False)
    # so per-sample adapter_usage_usd is available (Pitfall 5).
    worst = EXIT_PASS
    for header_log in logs:
        full_log = read_eval_log(header_log.location, header_only=False)
        code = _gate_one_log(full_log, success)
        # BLOCK (1) dominates WARN (78) dominates PASS (0).
        if code == EXIT_BLOCK:
            worst = EXIT_BLOCK
        elif code == EXIT_WARN and worst != EXIT_BLOCK:
            worst = EXIT_WARN

    label = {EXIT_PASS: "PASS", EXIT_WARN: "WARN", EXIT_BLOCK: "BLOCK"}[worst]
    print(f"[ci_gate] overall verdict={label} (exit {worst})")
    return worst


if __name__ == "__main__":
    sys.exit(main())
