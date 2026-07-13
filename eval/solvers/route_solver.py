"""Non-model routing solver — scores `decide()` without calling a network model.

This is the "key trick" of the routing-accuracy suite (10-RESEARCH §Pattern 1).
A normal inspect-ai solver awaits the generate callback, which dispatches the
sample to a real LLM and spends credits. The router under test, however, is a
*local* calibrated joblib cascade (`src.routing.decide.decide`) that runs in
microseconds and is fully deterministic — there is nothing to generate. So this
solver sets `state.output` DIRECTLY via `ModelOutput.from_content(...)` and never
invokes the generate callback. Combined with `token_limit=0` on the Task (see
`eval/suites/routing_accuracy.py`), the routing suite can never cross the
network-model trust boundary (threat T-10-NET — wallet DoS).

D-18 one-way import (threat T-10-D18b): the router is imported as a pure library
from the `decide` module (the import line below) — the function lives in that
module and `src/routing/__init__.py` is empty, so importing it from the package
root would NOT bind the callable. The arrow is eval/ -> src/routing, never the reverse;
`src/routing/tests/test_decide_smoke.py` keeps the brain layer free of HTTP/SDK
imports.

Cross-refs:
    - src/routing/decide.py:296-301  (decide(prompt, history, artifacts, settings) -> RoutingDecision)
    - src/routing/schema.py:36-55    (frozen RoutingDecision: backend/model_or_agent/rationale/confidence/signals)
    - src/routing/tests/test_decide_smoke.py:59-71 (canonical in-process decide() caller)
    - 10-RESEARCH.md §Pattern 1 lines 211-231 (non-model solver; corrected import + labels)
"""

from __future__ import annotations

from inspect_ai.model import ModelOutput
from inspect_ai.solver import Generate, TaskState, solver

# D-18 one-way import — the function lives in the `decide` module
# (src/routing/__init__.py is empty), so it must be imported from the module,
# not the package root.
from src.routing.decide import decide


@solver
def route_solver():
    """A non-model solver that scores `decide()` in-process.

    Calls `decide(state.input_text)` synchronously (microseconds, deterministic
    joblib inference) and writes the chosen backend label into `state.output`.
    It deliberately does NOT invoke the generate callback — that would dispatch
    the prompt to a paid model and measure the wrong thing. `decide()` is
    CPU-bound and synchronous, so a direct call inside the async `solve` is
    correct; it is NOT wrapped in any nested event-loop runner (we are already
    inside inspect-ai's event loop).

    The rationale, confidence, and model_or_agent are stashed into
    `state.metadata` so the backend_match scorer / CI gate can surface the
    D2 per-backend ROUTER-08 misroute breakdown and the D3 ECE
    (predicted-confidence vs correctness) — all measurement, no router change.
    """

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        # Synchronous, in-process, no network. decision is a frozen RoutingDecision.
        decision = decide(state.input_text)

        # Write the backend label directly into the output — the non-model trick
        # (no generate callback is invoked).
        # decision.backend ∈ {"openrouter", "claude_code", "computer_use"}.
        state.output = ModelOutput.from_content(
            model="router/decide", content=decision.backend
        )

        # Stash the rest of the decision for downstream D2/D3 metrics.
        state.metadata["rationale"] = decision.rationale
        state.metadata["confidence"] = decision.confidence  # for the D3 ECE metric
        state.metadata["model_or_agent"] = decision.model_or_agent

        return state

    return solve
