# Phase 10: Quality Eval Harness - Research

**Researched:** 2026-05-31
**Domain:** Eval engineering for an LLM-router + agentic backends — `inspect-ai` harness wired into CI as a non-regression gate
**Confidence:** HIGH (inspect-ai API verified against the live 0.3.x docs and pinned version; codebase wiring verified by direct file reads)

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EVAL-01 | Top-level `eval/` harness imports `decide()` as a library on `inspect-ai`, preserving the D-18 import-graph guard (eval not under `src/routing/`) | §Standard Stack (inspect-ai 0.3.232 verified), §Architecture Patterns (non-model solver, D-18-safe import arrow), §Don't Hand-Roll. Verified: `decide()` lives at `src/routing/decide.py`, returns frozen `RoutingDecision(backend, model_or_agent, rationale, confidence, signals)`; existing D-18 guard is `src/routing/tests/test_decide_smoke.py`. |
| EVAL-02 | Routing-accuracy suite scores backend-pick accuracy against a labeled set provably disjoint from tuning data (tune ∩ canary = ∅) | §Architecture Pattern "Hash-disjointness pre-flight", §Code Examples. Verified: tuning rows live in `data_processed/*.csv` (git-LFS, 124MB), prompt column is `origin_query`/`prompt`; existing routing canary precedent at `data_processed/routing_decision_eval.csv` with columns `prompt, expected_backend, …`. |
| EVAL-03 | Self-hosted agentic task-completion suite measures end-to-end finish, uncontaminated by public benchmarks | §Architecture Pattern "Adapter-driving solver", §Don't Hand-Roll. Verified: adapters live under `apps/api/backends/{claude_code,computer_use}` (NOT `src/adapters`) and expose `async def stream(...) -> AsyncIterator[ChatChunk]`; the terminal `Done` chunk carries `cost_usd/tokens_in/tokens_out`. |
| EVAL-04 | CI runs the harness as a regression gate with multi-run success-band thresholds + per-suite cost ceiling | §Architecture Pattern "CI gate algorithm", §Code Examples. Verified: `eval_set()` returns `tuple[bool, list[EvalLog]]`; `Task` supports `cost_limit/token_limit/time_limit/message_limit/working_limit`; `Epochs(n, reducer)` with `mode/mean/at_least_k/pass_at_k`. CI runs on `uv sync --locked`. |
</phase_requirements>

## User Constraints

> No `10-CONTEXT.md` exists yet (`has_context: false`). The binding constraints below are the **locked design decisions from `10-AI-SPEC.md`** (user, 2026-05-31) plus CLAUDE.md and the REQUIREMENTS Out-of-Scope table. Treat the AI-SPEC's locked decisions with the same authority as CONTEXT.md decisions.

### Locked Decisions (from 10-AI-SPEC.md §"Locked design decisions")
- **Framework:** `inspect-ai` (UK AISI Inspect) — constraint-locked by EVAL-01, not an open question. Pin `inspect-ai>=0.3.224,<0.4`.
- **Agentic scoring (EVAL-03):** **Hybrid** — deterministic code scorers wherever a machine-checkable artifact exists (downloaded file / DOM-or-text match / terminal state); LLM-judge (`model_graded_qa`) ONLY for goals with no checkable artifact.
- **Observability:** **Self-hosted** Arize Phoenix (default) or Langfuse — fully local, BYOK-safe, no hosted SaaS. **OPTIONAL** sidecar, imported only inside `eval/`.
- **EVAL-04 CI gate:** **Both (defense in depth)** — per-task USD/token budget inside the harness AND a CI-side aggregate per-suite cost ceiling + multi-run success-band exit-code gate.
- **EVAL-02 disjointness:** **CI-asserted hash disjointness** — frozen canary file in `eval/`; a CI test hashes prompts and asserts ∅ overlap with `data_processed/` tuning rows, failing the build on leakage.
- **Exit codes (from ROADMAP §Eval Tooling):** `0` = pass (merge allowed); `1` = below band OR over ceiling (block merge); `78` = warn-zone (`band_low..band_target`) — annotate PR, do not block.

### Claude's Discretion
- Exact `eval/` sub-module file names (suites/scorers/solvers split), the concrete hashing/normalization function for disjointness, the price-table mechanism for judge USD, and the specific success-band numbers (`band_low`/`band_target`) — set by the planner, subject to the locked structure above.
- Whether to reuse the existing `data_processed/routing_decision_eval.csv` 42-row canary as a *seed* for the new `eval/data/canary_routing.jsonl` (the AI-SPEC notes the canary expands from real production misroutes over time). NOTE: the new canary MUST be disjoint from `data_processed/` — see Open Question 1.

### Deferred Ideas (OUT OF SCOPE)
- promptfoo / hosted eval SaaS (LangSmith, Braintrust) — vendor conflict + local-only violation (REQUIREMENTS Out-of-Scope).
- LangChain / agent frameworks — framework sprawl against the framework-free `decide()`/adapter contract.
- Online/live retraining of routing heads — training stays offline against `data_processed/`.
- The ROUTER-08/09/10 *fixes* (recalibration, misroute reduction) — those land in **Phase 13**, gated *behind* this phase's eval. Phase 10 builds the gate; it does not change the router. (The harness MAY surface ROUTER-08 misroute rate and ROUTER-09 ECE as metrics — measurement, not fixing.)

## Project Constraints (from CLAUDE.md)
- **GSD workflow enforcement:** all edits go through a GSD command (this is a planned phase).
- **snake_case module files**; one legacy exception (`Feature_extractor.py`). New `eval/` modules use snake_case.
- **`os.path.join` from a `__file__`-derived PROJECT_ROOT** is the dominant path convention; the newer `apps/` subtree uses `pathlib.Path(__file__).resolve().parents[N]`. The `eval/` package is top-level (sibling of `src/`), so derive root as `Path(__file__).resolve().parents[1]` from `eval/<module>.py`.
- **`print()`-based logging** for non-data scripts (training/demo/CLI); `logging` module only for data-pipeline ingest scripts. `ci_gate.py` is a CLI → use `print()`.
- **No enforced formatter** (no black/ruff config). Match surrounding style; 4-space indent, PEP 8.
- **pytest `--import-mode=importlib`** is set in `pyproject.toml` (`addopts = "-x -q --import-mode=importlib"`, `asyncio_mode = "auto"`). New tests under `eval/tests/` must place any `conftest.py` inside that dir, and bare `tests` package-name collisions are handled by importlib mode. `testpaths = ["src", "apps"]` — **eval/ is NOT currently in testpaths; the planner must add `"eval"` to testpaths or invoke pytest with an explicit path.**
- **`live` pytest marker** exists for tests that hit real provider APIs (skipped by default). The agentic suite's real-spend path should be marked `live` so the deterministic PR gate stays free.

## Summary

This phase builds a top-level `eval/` package (sibling of `src/`, NOT under `src/routing/`) on `inspect-ai` 0.3.232. It has two suites: (1) a **routing-accuracy** suite that imports `decide()` in-process and scores its `.backend` label against a frozen, disjoint canary with zero network calls; and (2) an **agentic task-completion** suite that drives the project's own Claude Code / computer-use adapters (under `apps/api/backends/`), captures the transcript + artifact + adapter-reported USD, and scores it with a hybrid of deterministic artifact checks and an LLM-judge. A CI workflow (`eval-gate.yml`) runs a free Layer-0 pre-flight (hash-disjointness + import-graph guard), then runs both suites under `eval_set()` and applies a dual-layer cost ceiling + multi-run success-band gate with tri-state exit codes (0/1/78).

The framework is constraint-locked and the AI-SPEC's API sketch is **mostly correct** — but two wiring claims in the AI-SPEC are **wrong against this codebase and must be corrected by the planner**: (a) `from src.adapters import run_agent_task` — there is no `src/adapters`; adapters live at `apps/api/backends/{claude_code,computer_use}/adapter.py` and expose a *streaming* `async def stream(prompt, history, options) -> AsyncIterator[ChatChunk]`, not a single-call `run_agent_task() -> result`; and (b) the AI-SPEC's "introduce a pyproject" framing is stale — a root `pyproject.toml` + `uv.lock` already exist and CI runs `uv sync --locked --all-extras`. The `eval` optional-dependency group must be added to the *existing* pyproject and the lockfile re-synced.

**Primary recommendation:** Add an `[project.optional-dependencies] eval = ["inspect-ai>=0.3.224,<0.4"]` group to the existing root `pyproject.toml`, re-sync `uv.lock`, and build the `eval/` package with a non-model `route_solver` (no network) for the routing suite and an `adapter_solver` that consumes the existing `apps.api.backends` streaming adapters and sums the `Done.cost_usd` chunk for the agentic suite. Keep the D-18 arrow one-directional (`eval/` imports `src.routing`/`apps.api.backends`, never the reverse) and add a `test_import_graph.py` that asserts no `src/` module imports `eval` or `inspect_ai`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Routing-accuracy scoring (`decide()` → backend label) | **Eval harness (top-level `eval/`)** | Routing brain (`src/routing`, imported as library) | `decide()` is a local joblib classifier; the harness scores it in-process with zero network. The harness owns the scoring; `src/routing` is a pure dependency it never knows about. |
| Agentic task execution | **Project adapters (`apps/api/backends/{claude_code,computer_use}`)** | Eval harness (orchestrates + scores) | inspect-ai does NOT execute the agent — the project's own adapters run the Claude Code SDK / Playwright computer-use loop. inspect-ai hands the spec to the adapter and scores the result. |
| LLM-judge model call | **Eval harness (`inspect_ai.model` / `model_graded_qa`)** | — | The ONLY place inspect-ai itself calls a generative model. Pinned, low-temp, structured-output. |
| Cost accounting | **Eval harness (`ci_gate.py`)** | Adapters (report USD via `Done.cost_usd`) + inspect-ai (`log.stats.model_usage`) | Judge tokens are in `log.stats`; adapter-execution USD is NOT — it must be summed separately from the `Done` chunk. The gate combines both. |
| Hash-disjointness assertion | **Eval harness (`eval/tests/`)** | `data_processed/` (read-only source of tuning prompts) | A cheap stdlib pre-flight; reads tuning CSVs and the canary, hashes prompts, asserts ∅ overlap. No inspect-ai dependency. |
| Import-graph guard (D-18) | **Eval harness (`eval/tests/`)** + existing `src/routing/tests/test_decide_smoke.py` | — | Two directions: existing test asserts `src.routing.decide` pulls no HTTP/SDK; new test asserts no `src/` module imports `eval`/`inspect_ai`. |
| Observability traces (optional) | **Phoenix sidecar (`eval/observability.py`)** | OpenInference instrumentors on Anthropic/OpenAI SDKs | inspect-ai has NO native OTLP exporter; Phoenix sees only the underlying SDK calls (judge + adapter), never inspect-ai's scoring graph. Import only inside `eval/`. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `inspect-ai` | `>=0.3.224,<0.4` (latest `0.3.232`, 2026-05-31) `[CITED: pypi.org/project/inspect-ai]` | Eval framework: `Task`/`@task`, `Solver`/`Scorer`, `eval_set`, `.eval` logs, multi-run epochs, per-task limits | Constraint-locked by EVAL-01; pure-Python, local-first, BYOK, model-agnostic, native cost/token accounting and `.eval` provenance logs. `[ASSUMED]` package legitimacy (slopcheck unavailable — see audit) |
| `pydantic` | `>=2.6,<3.0` (already a core dep) | `JudgeVerdict` + score-record schemas; inspect-ai uses pydantic internally | Already in `pyproject.toml` core deps. Do NOT re-pin. |

### Supporting (OPTIONAL — observability sidecar only)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `arize-phoenix` | latest `[ASSUMED]` | Local self-hosted trace UI (`http://localhost:6006`) | Only when a maintainer wants trace drill-down; never imported by CI gate or `src/`. |
| `openinference-instrumentation-anthropic` | latest `[ASSUMED]` | Emits OpenInference spans for Anthropic SDK calls (judge + computer-use) | With Phoenix only. |
| `openinference-instrumentation-openai` | latest `[ASSUMED]` | Emits spans for OpenAI-shaped calls | With Phoenix only. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `inspect-ai` | hand-rolled pytest scorer harness | Only constraint-compatible fallback if inspect-ai were disqualified; forfeits logging/viewer/cost accounting. Not recommended (AI-SPEC §2). |
| `inspect-ai` | promptfoo / LangChain / LangSmith / Braintrust | All explicitly OUT OF SCOPE (REQUIREMENTS Out-of-Scope: vendor conflict / local-only violation / framework sprawl). |
| Arize Phoenix | Langfuse (self-hosted) | AI-SPEC accepts Langfuse as an alternative; Phoenix is the default. Either is fine — both local, BYOK-safe. |

**Installation:**
```bash
# Add to the EXISTING root pyproject.toml (do NOT create a new one):
#   [project.optional-dependencies]
#   eval = ["inspect-ai>=0.3.224,<0.4"]
# Then re-sync the lockfile (CI runs `uv sync --locked --all-extras`):
uv add --optional eval "inspect-ai>=0.3.224,<0.4"   # writes pyproject + uv.lock
uv sync --locked --all-extras --dev
inspect --version                                    # expect >= 0.3.224
```

**Version verification:** `inspect-ai` latest is `0.3.232` (released 2026-05-31) `[CITED: pypi.org/project/inspect-ai]`. The AI-SPEC's pinned floor `>=0.3.224,<0.4` is valid and current. `pydantic>=2.6,<3.0` is already a verified core dependency in `pyproject.toml`. Note: pydantic is in the D-18 FORBIDDEN set for `src/routing` — but the eval suites are NOT in that import graph, so eval importing pydantic is fine.

## Package Legitimacy Audit

> slopcheck and `pip` are **not available** in this research environment (sandbox). Per the Package Legitimacy Gate graceful-degradation rule, every package below is tagged `[ASSUMED]` and the planner MUST gate each install behind a `checkpoint:human-verify` task before adding it to `pyproject.toml` / `uv.lock`.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `inspect-ai` | PyPI | ~2 yrs (UK AISI) | high (institutional) | github.com/UKGovernmentBEIS/inspect_ai | unavailable | `[ASSUMED]` — verify before install. Strong provenance: official docs at inspect.aisi.org.uk, UK AI Security Institute. |
| `arize-phoenix` | PyPI | est. ~2 yrs | high | github.com/Arize-ai/phoenix | unavailable | `[ASSUMED]` — OPTIONAL; verify before install. |
| `openinference-instrumentation-anthropic` | PyPI | est. ~1.5 yrs | medium | github.com/Arize-ai/openinference | unavailable | `[ASSUMED]` — OPTIONAL; verify before install. |
| `openinference-instrumentation-openai` | PyPI | est. ~1.5 yrs | medium | github.com/Arize-ai/openinference | unavailable | `[ASSUMED]` — OPTIONAL; verify before install. |

**Packages removed due to slopcheck [SLOP] verdict:** none (slopcheck unavailable).
**Packages flagged as suspicious [SUS]:** none (slopcheck unavailable).

*All packages above are tagged `[ASSUMED]` because slopcheck could not run. The planner must add a `checkpoint:human-verify` task before each install. Verification command for the executor: `uv pip index versions inspect-ai` and confirm the source repo `github.com/UKGovernmentBEIS/inspect_ai` matches the docs at inspect.aisi.org.uk.*

## Architecture Patterns

### System Architecture Diagram

```
                         ┌─────────────────────────────────────────────┐
   CI trigger (PR        │                eval-gate.yml                 │
   touching src/routing, │                                             │
   apps/api/backends,    │  Layer 0 (FREE, runs first, no API spend):  │
   or eval/)  ──────────▶│   pytest eval/tests/test_canary_disjoint.py │──┐
                         │   pytest eval/tests/test_import_graph.py    │  │ red ⇒ exit 1
                         └──────────────────┬──────────────────────────┘  │ (block merge)
                                            │ green                        │
                                            ▼                              │
                         ┌─────────────────────────────────────────────┐  │
                         │      python -m eval.ci_gate (eval_set)       │  │
                         │                                             │  │
        ┌────────────────┤  ┌───────────────────┐ ┌──────────────────┐│  │
        │                │  │ routing_accuracy   │ │ agentic_completion││ │
        │                │  │   @task            │ │   @task           ││ │
        │                │  └─────────┬──────────┘ └────────┬─────────┘│  │
        │                └────────────┼─────────────────────┼──────────┘  │
        │                             ▼                      ▼             │
        │            ┌────────────────────────┐  ┌──────────────────────┐ │
        │ canary     │ route_solver (NO net)  │  │ adapter_solver       │ │
        │ JSONL  ───▶│  decide(input_text)    │  │  await stream(...)   │ │
        │ (frozen,   │  → state.output =      │  │  consume ChatChunks, │ │
        │  disjoint) │    decision.backend    │  │  capture artifact +  │ │
        │            └───────────┬────────────┘  │  Done.cost_usd       │ │
        │                        ▼               └──────────┬───────────┘ │
        │            ┌────────────────────────┐             ▼             │
        │            │ backend_match scorer   │  ┌──────────────────────┐ │
        │            │  predicted == gold ?   │  │ artifact_or_judge    │ │
        │            │  accuracy()+stderr()   │  │  artifact? → det chk │ │
        │            └───────────┬────────────┘  │  else → model_graded │ │
        │                        │               │       _qa (LLM judge)│ │
        │   imports              │               └──────────┬───────────┘ │
        ▼  (one-way, D-18)       ▼                          ▼             │
  src.routing.decide      .eval log (logs/)          .eval log + Done USD │
  (joblib classifiers)          │                          │             │
                                └──────────┬───────────────┘             │
                                           ▼                             │
                         ┌─────────────────────────────────────────────┐ │
                         │ ci_gate.py reads .eval logs:                 │ │
                         │  judge USD = log.stats.model_usage × price   │ │
                         │  agent USD = Σ adapter Done.cost_usd         │ │
                         │  reduced acc (Epochs mode) vs band_low       │ │
                         │  → exit 0 / 1 / 78                           │─┘
                         └─────────────────────────────────────────────┘
```

### Recommended Project Structure
```
repo-root/
├── src/routing/decide.py        # production router — NEVER imports eval/ (D-18)
├── apps/api/backends/           # existing adapters (Claude Code SDK + computer-use)
│   ├── claude_code/adapter.py   #   async def stream(...) -> AsyncIterator[ChatChunk]
│   ├── computer_use/adapter.py
│   ├── chunks.py                #   ChatChunk union; Done carries cost_usd/tokens_in/out
│   └── protocol.py              #   BackendAdapter Protocol, AdapterOptions
├── eval/                        # TOP-LEVEL, sibling of src/ (D-18 guard)
│   ├── __init__.py
│   ├── suites/
│   │   ├── routing_accuracy.py  # @task — in-process decide(), no network, token_limit=0
│   │   └── agentic_completion.py# @task — drives apps.api.backends adapters
│   ├── scorers/
│   │   ├── backend_match.py     # exact backend-label scorer + per-class metrics
│   │   ├── artifact_checks.py   # deterministic: file-present / DOM-or-text / terminal-state
│   │   └── judge.py             # model_graded_qa wrapper (calibrated, pinned, temp 0)
│   ├── solvers/
│   │   ├── route_solver.py      # wraps decide()
│   │   └── adapter_solver.py    # consumes apps.api.backends streaming adapter
│   ├── data/
│   │   ├── canary_routing.jsonl # frozen labeled canary (gold_backend per prompt)
│   │   └── agentic_tasks.jsonl  # self-hosted agentic task specs + gold artifacts
│   ├── schemas.py               # JudgeVerdict + RoutingScoreRecord pydantic models
│   ├── budgets.py               # per-suite USD ceilings, band_low/band_target, judge price table
│   ├── ci_gate.py               # eval_set runner + read_eval_log cost/score assertions; exit 0/1/78
│   ├── observability.py         # OPTIONAL Phoenix sidecar (import only here)
│   └── tests/
│       ├── conftest.py          # (importlib mode — keep here, not at repo root)
│       ├── test_canary_disjoint.py  # hashes prompts, asserts canary ∩ data_processed/ = ∅
│       └── test_import_graph.py     # asserts no src/ module imports eval/ or inspect_ai
├── logs/                        # .eval logs (add to .gitignore; inspect view target)
└── pyproject.toml               # [project.optional-dependencies] eval = ["inspect-ai..."]
```

### Pattern 1: Non-model routing solver (the key trick)
**What:** A `@solver` that sets `state.output` directly via `ModelOutput.from_content(...)` WITHOUT calling `await generate(...)`. This lets inspect-ai *score* `decide()` without invoking any network model.
**When to use:** the routing-accuracy suite — `decide()` is a local joblib classifier, microseconds, deterministic.
**Verified API:** `Score(value=CORRECT/INCORRECT)` where `CORRECT="C"`/`INCORRECT="I"` → `accuracy()` maps to 1.0/0.0 `[CITED: inspect.aisi.org.uk/scorers.html]`.
```python
# eval/solvers/route_solver.py
# Source: inspect.aisi.org.uk/solvers.html (non-model solver pattern, verified 2026-05-31)
from inspect_ai.solver import solver, TaskState, Generate
from inspect_ai.model import ModelOutput
from src.routing.decide import decide        # one-way D-18 import

@solver
def route_solver():
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        decision = decide(state.input_text)               # frozen RoutingDecision
        state.output = ModelOutput.from_content(
            model="router/decide", content=decision.backend
        )                                                  # decision.backend ∈ {openrouter, claude_code, computer_use}
        state.metadata["rationale"] = decision.rationale
        state.metadata["confidence"] = decision.confidence # for D3 ECE metric
        state.metadata["model_or_agent"] = decision.model_or_agent
        return state
    return solve
```
**CORRECTION vs AI-SPEC sketch:** the AI-SPEC uses `from src.routing import decide` — the verified import is `from src.routing.decide import decide` (the function lives in the `decide` module, and `src/routing/__init__.py` is empty). Also `decision.backend` values are `openrouter` (NOT `openrouter_chat`), `claude_code`, `computer_use` — verified in `src/routing/schema.py:33` and `test_decide_smoke.py`. The AI-SPEC `schemas.py` uses `openrouter_chat`, which is WRONG for this codebase.

### Pattern 2: Adapter-driving agentic solver (streaming consumption)
**What:** A `@solver` that calls the project's *streaming* adapter and accumulates chunks into a final transcript + artifact + summed USD.
**When to use:** the agentic suite. inspect-ai orchestrates+scores; the adapter executes.
**Critical correction:** there is NO `src.adapters.run_agent_task`. The real contract (`apps/api/backends/protocol.py`) is `async def stream(prompt, history, options: AdapterOptions) -> AsyncIterator[ChatChunk]`. The solver must consume the async iterator and read the terminal `Done` chunk (`chunks.py:149`) for usage:
```python
# eval/solvers/adapter_solver.py — CORRECTED for this codebase
from inspect_ai.solver import solver, TaskState, Generate
from inspect_ai.model import ModelOutput
from apps.api.backends.protocol import AdapterOptions, Message
# adapter instances: build the same way apps/api/lifespan.py does, OR import the
# concrete adapter class from apps.api.backends.{claude_code,computer_use}.adapter
from apps.api.backends.claude_code.adapter import ClaudeCodeAdapter  # verify class name in plan

@solver
def adapter_solver(backend: str):
    adapter = ...  # construct the backend's adapter (see apps/api/lifespan.py precedent)
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        spec = state.metadata["task_spec"]
        opts = AdapterOptions(max_cost_usd=spec.get("max_cost_usd"),
                              max_steps=spec.get("max_steps"))
        text_parts, total_usd, terminal_state, artifact_path = [], 0.0, None, None
        async for chunk in adapter.stream(spec["goal"], history=[], options=opts):
            if chunk.type == "text_delta":
                text_parts.append(chunk.text)
            elif chunk.type == "screenshot":
                artifact_path = getattr(chunk, "path", None) or artifact_path
            elif chunk.type == "file_diff":
                artifact_path = getattr(chunk, "path", None) or artifact_path
            elif chunk.type == "done":
                total_usd += chunk.cost_usd or 0.0          # adapter USD — NOT in log.stats
                terminal_state = "done"
            elif chunk.type == "stream_error":
                terminal_state = "error"
        state.output = ModelOutput.from_content(
            model=backend, content="".join(text_parts)[-8000:]  # bounded for the judge
        )
        state.metadata["adapter_usage_usd"] = total_usd
        state.metadata["artifact_path"] = artifact_path
        state.metadata["terminal_state"] = terminal_state
        return state
    return solve
```
> The exact `ChatChunk` artifact-carrying fields (does `Screenshot`/`FileDiff` carry a `path`?) need a one-line confirmation by the planner against `apps/api/backends/chunks.py` lines 86-117 — see Open Question 3. Also confirm how the adapter wants to be constructed (it needs a `KeyStore`/keys for a real run — that path is `live`-marked and BYOK).

### Pattern 3: Hybrid artifact-or-judge scorer
**What:** route scoring by whether a machine-checkable artifact exists (locked decision). Deterministic check when it does; `model_graded_qa` LLM-judge only when it doesn't.
**Verified:** `model_graded_qa(template, instructions, partial_credit, model, ...)` `[CITED: inspect.aisi.org.uk/scorers.html]`.
```python
# eval/scorers/judge.py + artifact_or_judge — Source: inspect.aisi.org.uk/scorers.html
from inspect_ai.scorer import scorer, Score, Target, accuracy, stderr, CORRECT, INCORRECT, model_graded_qa
from inspect_ai.solver import TaskState

@scorer(metrics=[accuracy(), stderr()])
def artifact_or_judge(judge=model_graded_qa()):
    async def score(state: TaskState, target: Target) -> Score:
        meta = state.metadata
        if meta.get("artifact_path"):
            ok = check_artifact(meta["artifact_path"], target)   # deterministic file/DOM/terminal check
            return Score(value=CORRECT if ok else INCORRECT, answer=meta["artifact_path"])
        return await judge(state, target)                        # only when no artifact
    return score
```

### Pattern 4: CI gate with tri-state exit + dual cost layer
**What:** `eval_set()` (resumable, auto-retry) → read `.eval` logs → enforce band + ceiling → exit 0/1/78.
**Verified:** `eval_set()` returns `tuple[bool, list[EvalLog]]`; `read_eval_log(..., header_only=True)`; `log.stats.model_usage: dict[str, ModelUsage]` where `ModelUsage` has `input_tokens/output_tokens/total_tokens/total_cost` `[CITED: inspect.aisi.org.uk/reference/inspect_ai.model.html, inspect_ai.log.html, inspect_ai.html]`.
```python
# eval/ci_gate.py (excerpt) — Source: inspect.aisi.org.uk/eval-sets.html + eval-logs.html
import sys
from inspect_ai import eval_set
from inspect_ai.log import read_eval_log
from eval.budgets import SUITE_USD_CEILING, BAND_LOW, BAND_TARGET, JUDGE_PRICE_PER_MTOK

success, logs = eval_set(
    tasks=["eval/suites/routing_accuracy.py", "eval/suites/agentic_completion.py"],
    model="anthropic/claude-sonnet-4-6",   # JUDGE only; routing suite ignores it (no generate)
    log_dir="logs/ci-run",                 # resumable: re-run resumes, no re-burn of ceiling
    epochs=3,
)
exit_code = 0
for log in logs:
    log = read_eval_log(log.location, header_only=True)
    acc = log.results.metrics["accuracy"].value if log.results else 0.0
    # judge USD: ModelUsage.total_cost if present, else tokens × price table
    judge_usd = sum((u.total_cost or
                     (u.input_tokens + u.output_tokens) / 1_000_000 * JUDGE_PRICE_PER_MTOK)
                    for u in (log.stats.model_usage or {}).values())
    # agent USD: summed from per-sample state.metadata["adapter_usage_usd"]
    agent_usd = sum(s.metadata.get("adapter_usage_usd", 0.0) for s in (log.samples or []))
    total_usd = judge_usd + agent_usd
    if total_usd > SUITE_USD_CEILING or acc < BAND_LOW or not success:
        exit_code = 1                       # block merge
    elif acc < BAND_TARGET and exit_code == 0:
        exit_code = 78                      # warn-zone — annotate PR, don't block
sys.exit(exit_code)
```
> NOTE on the agent-USD read: with `header_only=True` the `samples` list is NOT loaded. The planner must EITHER read the full log (`header_only=False`) to sum per-sample `adapter_usage_usd`, OR have `adapter_solver` aggregate suite USD into a custom metric/reducer so it lands in `log.results`. Reading full logs for a 10-30 sample suite is cheap — prefer that. (See Open Question 2.)

### Pattern 5: Multi-run success band via Epochs
**Verified reducers:** `mean, median, mode, max, pass_at_{k}, pass_k_{k}, at_least_{k}` `[CITED: inspect.aisi.org.uk/scorers.html#reducing-epochs]`. Constructor `Epochs(count, reducer: str | list[str])`.
```python
from inspect_ai import Epochs
# pass/fail judge variance reduction:
epochs=Epochs(3, "mode")            # most-common per-sample verdict
# or stability band: epochs=Epochs(5, ["at_least_2", "pass_at_5"])
```

### Anti-Patterns to Avoid
- **Calling `await generate(state)` in the routing solver.** Spends API credits on a deterministic function and measures the wrong thing. Set `state.output` directly; set `token_limit=0` on the routing `Task` as a tripwire (AI-SPEC Pitfall #1).
- **`asyncio.run()` / `loop.run_until_complete()` inside a solver/scorer.** You are already inside inspect-ai's event loop → `RuntimeError: this event loop is already running`. `await` your async work directly (AI-SPEC §4b Async).
- **Any `src/` module importing `eval/` or `inspect_ai`.** D-18 violation — couples the production router to the eval-only stack. The arrow is one-way (AI-SPEC Pitfall #2).
- **Counting only judge tokens for the cost ceiling.** Adapter-execution USD is the real cost center and is NOT in `log.stats` — it lives in the `Done.cost_usd` chunk the adapter emits.
- **Gating on a single LLM-judge run.** Use `Epochs(n>=3)` + a reducer + a band, not a point threshold (AI-SPEC Pitfall #4 / Failure Mode #4).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Eval orchestration, sample fan-out, concurrency | Custom asyncio runner over the canary | `inspect_ai.eval` / `eval_set` | inspect-ai owns the loop, `max_samples`/`max_tasks` concurrency, retries, resumability. |
| Multi-run variance reduction | Manual N-run loop + custom mode/mean math | `Epochs(n, reducer)` | Verified reducers (`mode`/`at_least_k`/`pass_at_k`) are built in. |
| Result provenance / cost log | Custom JSON result writer | `.eval` logs + `read_eval_log` | Binary `.eval` carries per-sample transcript, `log.stats.model_usage`, `log.results.metrics`, pinned versions — the audit trail the responsible-eval norms require. |
| Per-task runaway-spend fuse | Custom token counter + abort | `Task(token_limit/message_limit/time_limit/cost_limit)` → `LimitExceededError` | All five are verified `Task` params in 0.3.232. |
| LLM-judge scaffolding | Custom grader prompt + parser | `model_graded_qa` + `ResponseSchema(JudgeVerdict)` | Built-in grader with templates, partial-credit, majority-vote; structured output constrains the verdict. |
| Adapter agent execution | New agent runner in `eval/` | Existing `apps.api.backends.{claude_code,computer_use}.adapter.stream` | The project's own adapters already run the Claude Code SDK + Playwright loop with cost caps; duplicating them is the AI-SPEC's "do NOT declare inspect-ai @tools/sandbox" warning. |
| Hash-disjointness | A bespoke dedup framework | stdlib `hashlib` + normalize + set-intersection in a pytest | It is a ~30-line cheap pre-flight; no library needed. |

**Key insight:** the harness's job is to *score systems it does not execute*. inspect-ai provides the scoring/logging/cost spine; `decide()` and the existing adapters provide the systems-under-test. Almost everything else is glue — resist rebuilding agent execution or eval orchestration.

## Runtime State Inventory

> This is a greenfield additive phase (a new `eval/` package + a new CI workflow). No rename/refactor of existing runtime state. The categories below are answered for completeness because the phase touches `pyproject.toml`/`uv.lock` and CI.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — the canary/agentic datasets are NEW frozen files in `eval/data/`. The existing `data_processed/routing_decision_eval.csv` (42 rows) is READ-ONLY input to the disjointness check and an optional seed. | None (additive). |
| Live service config | None — no UI/DB-stored config carries an eval string. CI secrets: `OPENROUTER_API_KEY` already configured in repo secrets (used by `live-smoke.yml`); the agentic suite needs `ANTHROPIC_API_KEY` + `COMPUTER_USE_OPT_IN=1` for real runs (BYOK, `live`-marked). | Planner: confirm `ANTHROPIC_API_KEY` repo secret exists OR keep the agentic real-spend job manual/`workflow_dispatch` like `live-smoke.yml`. |
| OS-registered state | None. | None. |
| Secrets/env vars | `PROMPT_OPTIMIZER_FAKE_ADAPTERS` (fake-adapter seam, per MEMORY) and `OPENROUTER_API_KEY` exist. The eval gate's free Layer-0 + routing suite need NO keys; the agentic suite needs real keys. | Planner: the routing suite + disjointness + import-graph tests run key-free on every PR; gate the agentic real-spend behind a secret check (`if: secrets.ANTHROPIC_API_KEY != ''`) mirroring `live-smoke.yml`. |
| Build artifacts | `uv.lock` will change when the `eval` optional group is added. `models/*.joblib` are loaded by `decide()` (regular git objects, not LFS). `data_processed/*.csv` are git-LFS (124MB) — CI must `lfs: true` for the disjointness check to read real prompts. | Planner: re-sync `uv.lock`; `eval-gate.yml` must `checkout` with `lfs: true` (mirrors `ci.yml`). |

## Common Pitfalls

### Pitfall 1: AI-SPEC import paths are wrong for this codebase
**What goes wrong:** Following the AI-SPEC sketch verbatim — `from src.adapters import run_agent_task` and `from src.routing import decide` and `Backend = Literal["openrouter_chat", ...]` — produces `ImportError` / wrong labels.
**Why it happens:** the AI-SPEC was written before the codebase was inspected; adapters are at `apps/api/backends/`, the function is `src.routing.decide.decide`, the backend label is `openrouter` (not `openrouter_chat`), and adapters stream chunks rather than return a result object.
**How to avoid:** use the corrected imports in Patterns 1-2. Gold backend labels in the canary MUST be `{openrouter, claude_code, computer_use}` — matching `src/routing/schema.py:33`.
**Warning signs:** any plan that references `src/adapters`, `openrouter_chat`, or a non-streaming `run_agent_task`.

### Pitfall 2: LFS pointers in CI make disjointness silently skip
**What goes wrong:** `data_processed/*.csv` are git-LFS (124MB). Without `lfs: true` on checkout, the disjointness test reads a 134-byte pointer instead of real prompts and the ∅-overlap assertion passes vacuously (false confidence — the exact contamination failure mode).
**Why it happens:** the existing `test_canary_schema.py` *skips* on an unmaterialized LFS pointer (`_is_lfs_pointer()`). A disjointness test that skips is worse than useless here.
**How to avoid:** `eval-gate.yml` checkout uses `lfs: true` (like `ci.yml`); `test_canary_disjoint.py` must **FAIL (not skip)** if the tuning CSV is an unmaterialized LFS pointer — a skipped disjointness check must never be green.
**Warning signs:** disjointness test passes on a fresh clone without `git lfs pull`.

### Pitfall 3: pyproject already exists; testpaths excludes eval/
**What goes wrong:** treating this as "introduce a pyproject" (AI-SPEC framing) creates a conflicting second file; and `pytest.ini_options.testpaths = ["src", "apps"]` means `pytest` won't collect `eval/tests/` by default, so the disjointness/import-graph tests never run.
**Why it happens:** stale AI-SPEC assumption + the existing pytest config predates `eval/`.
**How to avoid:** EDIT the existing `pyproject.toml` (add the `eval` optional group); add `"eval"` to `testpaths` OR run `pytest eval/` with an explicit path in CI. Keep `--import-mode=importlib` and put `conftest.py` inside `eval/tests/`.
**Warning signs:** a new top-level `pyproject.toml`; eval tests not appearing in `pytest --collect-only`.

### Pitfall 4: 0.3.x API drift on cost_limit / response_schema / eval_set
**What goes wrong:** A field assumed present may be absent in an older pinned build.
**Why it happens:** the `0.3.x` series is pre-1.0; signatures move between minors.
**How to avoid (verified for `0.3.232`):** `Task(cost_limit=..., working_limit=...)` ARE present `[CITED: inspect_ai.html]`; `eval_set()` returns `tuple[bool, list[EvalLog]]` `[CITED: inspect_ai.html]`; `ResponseSchema(name, json_schema, strict)` is present with `strict` OpenAI/Mistral-only `[CITED: inspect_ai.model.html]`. Re-confirm with `inspect --version` after `uv sync`. If the resolved build predates `cost_limit`, fall back to enforcing USD via `log.stats` token math in `ci_gate.py` (already the dual-layer design).
**Warning signs:** `TypeError: unexpected keyword argument 'cost_limit'` at task construction.

### Pitfall 5: header_only drops the samples needed for adapter USD
**What goes wrong:** `read_eval_log(..., header_only=True)` skips `log.samples`, so `state.metadata["adapter_usage_usd"]` per-sample is unavailable and agent spend reads as 0.
**How to avoid:** read full logs for the small agentic suite, OR emit a custom suite-USD metric/reducer that lands in `log.results`. See Open Question 2.

### Pitfall 6: judge variance / too-few-epoch bands (domain failure mode)
**What goes wrong:** single-run pass@1 varies 2.2-6.0pp even at temp 0 (arxiv 2602.07150, cited in AI-SPEC §1b); a band set from 1-2 runs encodes noise.
**How to avoid:** `Epochs(n>=3)` + reducer; set `band_low`/`band_target` with enough epochs for statistical power; gate on a band, not a point. Judge must be calibrated to ≥~0.7 human correlation BEFORE it may gate (D7).

## Code Examples

### Routing-accuracy task (verified symbols)
```python
# eval/suites/routing_accuracy.py — Source: inspect.aisi.org.uk/datasets.html + scorers.html
from inspect_ai import Task, task
from inspect_ai.dataset import json_dataset, FieldSpec
from inspect_ai.scorer import scorer, Score, Target, accuracy, stderr, CORRECT, INCORRECT
from inspect_ai.solver import TaskState
from eval.solvers.route_solver import route_solver

@scorer(metrics=[accuracy(), stderr()])
def backend_match():
    async def score(state: TaskState, target: Target) -> Score:
        predicted = state.output.completion.strip()
        return Score(value=CORRECT if predicted == target.text.strip() else INCORRECT,
                     answer=predicted, explanation=state.metadata.get("rationale"))
    return score

@task
def routing_accuracy() -> Task:
    return Task(
        dataset=json_dataset("eval/data/canary_routing.jsonl",
                             FieldSpec(input="prompt", target="gold_backend", id="prompt_id")),
        solver=route_solver(),
        scorer=backend_match(),
        token_limit=0,        # tripwire: routing suite must never call a model
    )
```

### Hash-disjointness pre-flight (EVAL-02)
```python
# eval/tests/test_canary_disjoint.py — stdlib only, no inspect-ai
import csv, glob, hashlib, json, pathlib, pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
LFS_MARK = "version https://git-lfs.github.com/spec/"

def _norm(p: str) -> str:                       # normalize before hashing
    return " ".join(p.strip().lower().split())

def _h(p: str) -> str:
    return hashlib.sha256(_norm(p).encode("utf-8")).hexdigest()

def _tuning_hashes() -> set[str]:
    hs = set()
    for csv_path in glob.glob(str(ROOT / "data_processed" / "*.csv")):
        with open(csv_path, encoding="utf-8") as fh:
            head = fh.readline()
            if head.startswith(LFS_MARK):
                pytest.fail(f"{csv_path} is an unmaterialized LFS pointer — run `git lfs pull`; "
                            "a SKIPPED disjointness check must never be green (Pitfall 2)")
            fh.seek(0)
            for row in csv.DictReader(fh):
                for col in ("origin_query", "prompt"):
                    if row.get(col):
                        hs.add(_h(row[col]))
    return hs

def test_canary_disjoint_from_tuning():
    canary = [json.loads(l) for l in (ROOT / "eval/data/canary_routing.jsonl")
              .read_text(encoding="utf-8").splitlines() if l.strip()]
    canary_h = {_h(r["prompt"]) for r in canary}
    overlap = canary_h & _tuning_hashes()
    assert not overlap, f"EVAL-02 violation: {len(overlap)} canary prompt(s) overlap data_processed/ tuning rows"
```

### Import-graph guard (D-18, eval direction)
```python
# eval/tests/test_import_graph.py — assert no src/ module imports eval or inspect_ai
import ast, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]

def test_no_src_module_imports_eval_or_inspect():
    offenders = []
    for py in (ROOT / "src").rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                    else [node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            for m in mods:
                if m and (m.split(".")[0] in {"eval", "inspect_ai"}):
                    offenders.append(f"{py}: imports {m}")
    assert not offenders, "D-18 violation (eval direction):\n" + "\n".join(offenders)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single-run pass@1 as the gate score | Multi-run `Epochs` + reducer + success band | arxiv 2602.07150 (60k SWE-Bench trajectories) | A 2-3pp delta at temp 0 is eval noise, not signal — gate on a band. |
| Agent self-narration ("I completed it") as success | Deterministic machine-checkable artifact, LLM-judge only when none exists | Agentic-benchmark best practices (arxiv 2507.02825, BenchJack 2605.12673) | Locked hybrid scoring (EVAL-03). |
| Public benchmarks (SWE-bench/WebArena/OSWorld/GAIA) | Self-hosted contamination-free task set | Gold-answer leakage audits | EVAL-03 requires a private task set. |
| Bare accuracy mean | accuracy **+ stderr** + disjointness proof | RouterBench (2403.12031) | "A single mean with no uncertainty is not an evaluation." |

**Deprecated/outdated:**
- AI-SPEC's `from src.adapters import run_agent_task` and `openrouter_chat` label — never matched this codebase (see Pitfall 1).
- AI-SPEC's "introduce a pyproject" framing — a root `pyproject.toml` + `uv.lock` already exist.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | All eval packages tagged `[ASSUMED]` (slopcheck/pip unavailable in sandbox) | Package Legitimacy Audit | LOW — inspect-ai has strong UK AISI provenance; planner gates installs behind a verify checkpoint. |
| A2 | The `Done` ChatChunk's `cost_usd` is populated by all three adapters at stream end and is the authoritative per-turn adapter spend | Pattern 2, ci_gate | MEDIUM — if an adapter emits `Done(cost_usd=None)` on some paths, agent USD under-counts; planner must confirm each adapter populates it (verified field exists at `chunks.py:169`; population per-adapter not exhaustively verified). |
| A3 | `Screenshot`/`FileDiff` chunks carry a filesystem `path` usable as the deterministic artifact handle | Pattern 2, Open Q3 | MEDIUM — if artifacts are blobs-by-hash rather than paths, `artifact_checks.py` must resolve via the blob store. |
| A4 | Judge model `anthropic/claude-sonnet-4-6` slug is valid for inspect-ai's Anthropic provider | Pattern 4, AI-SPEC §4 | LOW — taken from AI-SPEC; planner confirms the live slug at run time (BYOK). |
| A5 | Adding `"eval"` to `testpaths` (or explicit path) is the right pytest wiring | Pitfall 3 | LOW — verified `testpaths=["src","apps"]` excludes eval today. |

## Open Questions

1. **Canary seed vs disjointness conflict.** The existing `data_processed/routing_decision_eval.csv` (42 hand-labeled rows) is the natural seed for `eval/data/canary_routing.jsonl` — but it LIVES IN `data_processed/`, the exact directory the disjointness check scans. If the new canary reuses those prompts verbatim AND the disjointness check hashes every `data_processed/*.csv`, the build fails by construction.
   - What we know: the disjointness target is the *tuning rows* (`classifier_training*.csv`, `router_training_dataset*.csv`, `agentic_intent_*.csv`), not necessarily the eval canary CSV.
   - What's unclear: whether `routing_decision_eval.csv` counts as "tuning data" (it does not — it is itself an eval set) and should be EXCLUDED from the disjointness scan.
   - Recommendation: the disjointness check should scan only the *training* CSVs (exclude `routing_decision_eval.csv` by name), OR move the new canary's prompts to be genuinely novel. Planner must lock the exact tuning-file set in `budgets.py`/the test. **High-stakes — this is EVAL-02's correctness.**

2. **Agent USD aggregation across the `header_only` boundary.** `header_only=True` is fast but drops `log.samples`; agent USD lives in per-sample metadata.
   - Recommendation: read full logs for the small (10-30 sample) agentic suite, OR add a custom inspect-ai metric/reducer that sums `adapter_usage_usd` into `log.results.metrics` so the header carries it. Planner picks one.

3. **Artifact handle shape.** Does the `Screenshot`/`FileDiff`/`Done` chunk surface a filesystem path, or a blob hash (the repo has `apps/api/db` blobs-by-hash, per `test_blobs_by_hash.py`)?
   - Recommendation: one-line read of `apps/api/backends/chunks.py:86-117` during planning to lock how `artifact_checks.py` resolves a downloaded-file / screenshot artifact.

4. **Adapter construction for a `live` run.** The adapters need a `KeyStore` + real keys (BYOK) and `COMPUTER_USE_OPT_IN=1`. How does `apps/api/lifespan.py` build them, and can `adapter_solver` reuse that builder without importing FastAPI (which would be fine for `eval/` but should be minimal)?
   - Recommendation: planner reads `apps/api/lifespan.py` (lines ~664-721 reference `app.state.adapters[backend]`) to mirror the construction; keep the agentic suite `live`-marked.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `inspect-ai` | both suites, CI gate | ✗ (not installed) | — | Install via `uv add --optional eval`; no fallback (EVAL-01 mandates it). |
| `uv` + `uv.lock` | CI dependency sync | ✓ | uv.lock present (810KB) | — |
| Python 3.11 | CI | ✓ | 3.11 (CI uses `uv python install 3.11`); 3.10+ supported | — |
| `pydantic>=2` | schemas, judge | ✓ | `>=2.6,<3.0` core dep | — |
| `decide()` + `models/*.joblib` | routing suite | ✓ | `src/routing/decide.py`, joblib artifacts present | — |
| `apps.api.backends` adapters | agentic suite | ✓ | `claude_code`, `computer_use`, `openrouter` adapters present | — |
| git-LFS (`data_processed/*.csv`) | disjointness check | ✓ (LFS-tracked; CI must `lfs: true`) | 124MB pointer | FAIL the test if pointer unmaterialized (Pitfall 2). |
| `OPENROUTER_API_KEY` secret | (judge via OpenRouter? / live) | ✓ in repo secrets | — | routing suite needs no key. |
| `ANTHROPIC_API_KEY` secret | agentic real-run + judge | ✗ unverified | — | Gate agentic real-spend behind `if: secrets.ANTHROPIC_API_KEY != ''` like `live-smoke.yml`; deterministic PR gate runs key-free. |
| `arize-phoenix` + instrumentors | optional observability | ✗ | — | OPTIONAL — sidecar only; harness works without it. |

**Missing dependencies with no fallback:** `inspect-ai` (must be installed — the whole phase).
**Missing dependencies with fallback:** `ANTHROPIC_API_KEY` (agentic real-run gated behind secret check; routing suite + Layer-0 run key-free); Phoenix (optional).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest>=9.0,<10.0` + `pytest-asyncio>=0.24` (`asyncio_mode=auto`), `pytest-timeout` `[CITED: pyproject.toml]` |
| Config file | root `pyproject.toml` `[tool.pytest.ini_options]` — `addopts="-x -q --import-mode=importlib"`, `testpaths=["src","apps"]` (**eval/ NOT yet included**), `markers=["live: …"]` |
| Quick run command | `uv run pytest -q eval/tests/` (Layer-0: disjointness + import-graph, key-free, ~seconds) |
| Full suite command | `uv run pytest -q eval/ && uv run python -m eval.ci_gate --suites routing agentic --epochs 3` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EVAL-01 | `eval/` imports `decide()` with no FastAPI/HTTP/SDK in `src/routing` graph | unit (import-graph) | `uv run pytest eval/tests/test_import_graph.py -x` AND existing `uv run pytest src/routing/tests/test_decide_smoke.py -x` | ❌ Wave 0 (new); ✅ smoke exists |
| EVAL-01 | routing suite scores `decide()` in-process, no network | smoke (inspect eval) | `inspect eval eval/suites/routing_accuracy.py --no-log-realtime` (token_limit=0 tripwire) | ❌ Wave 0 |
| EVAL-02 | canary ∩ data_processed tuning rows = ∅ | unit (hash) | `uv run pytest eval/tests/test_canary_disjoint.py -x` | ❌ Wave 0 |
| EVAL-02 | backend-pick accuracy reported with stderr on disjoint canary | code metric | `inspect eval eval/suites/routing_accuracy.py` → `log.results.metrics["accuracy"]` + `stderr` | ❌ Wave 0 |
| EVAL-03 | agentic finish rate from private task set, hybrid scoring | integration (`live`) | `inspect eval eval/suites/agentic_completion.py --epochs 1` (marked `live`, BYOK) | ❌ Wave 0 |
| EVAL-04 | CI blocks below-band / over-ceiling; tri-state exit | integration (gate) | `uv run python -m eval.ci_gate --suites routing agentic --epochs 3` → exit 0/1/78 | ❌ Wave 0 |
| EVAL-04 | per-task fuse fires (LimitExceededError) | unit | test that an unbounded mock task hits `token_limit`/`time_limit` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest -q eval/tests/` (Layer-0 disjointness + import-graph; key-free; sub-second) — Nyquist-adequate because these are the highest-stakes, cheapest checks.
- **Per wave merge:** `uv run pytest -q eval/` + `inspect eval eval/suites/routing_accuracy.py` (routing suite is free, no network).
- **Phase gate:** full `eval.ci_gate` run (3 epochs) green within the cost ceiling before `/gsd-verify-work`; the agentic `live` slice run at least once with real BYOK keys (bounded by per-task `cost_limit`).

### Wave 0 Gaps
- [ ] `eval/tests/test_canary_disjoint.py` — covers EVAL-02 (hash disjointness; FAIL on LFS pointer)
- [ ] `eval/tests/test_import_graph.py` — covers EVAL-01 (no `src/` imports `eval`/`inspect_ai`)
- [ ] `eval/tests/conftest.py` — shared fixtures (importlib mode, place inside dir)
- [ ] `eval/data/canary_routing.jsonl` — frozen disjoint canary (gold_backend ∈ {openrouter, claude_code, computer_use}; ≥10/backend per existing canary precedent; include ROUTER-08 haiku/fizzbuzz rows)
- [ ] `eval/data/agentic_tasks.jsonl` — 10-20 self-hosted tasks + gold artifact specs
- [ ] `eval/budgets.py` — `SUITE_USD_CEILING`, `BAND_LOW`, `BAND_TARGET`, judge price table, tuning-file set for disjointness
- [ ] pyproject edit: add `eval` optional group + add `"eval"` to `testpaths`; re-sync `uv.lock`
- [ ] `.github/workflows/eval-gate.yml` — Layer-0 free checks then `ci_gate` (lfs: true; secret-gated agentic)
- [ ] Framework install: `uv add --optional eval "inspect-ai>=0.3.224,<0.4"` (gate behind verify checkpoint per audit)

## Security Domain

> `security_enforcement` config not located in init context; treated as enabled (absent = enabled). This is an internal, local, BYOK eval harness with no PII and no regulated vertical (AI-SPEC §1b confirms "None identified" for compliance). The relevant controls are key-handling, import-isolation, and runaway-spend.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth surface — local CLI/CI tool. |
| V3 Session Management | no | Stateless eval runs. |
| V4 Access Control | partial | D-18 import-graph guard is an architectural access-control analogue (eval-only deps must not reach `src/routing`). |
| V5 Input Validation | yes | Canary/agentic JSONL are frozen, version-tracked, schema-checked (pydantic + disjointness test). |
| V6 Cryptography | partial | `hashlib.sha256` for disjointness only (integrity, not secrecy) — never hand-roll a hash. |
| V7 Error/Logging (secrets) | yes | `apps/api/backends/logging_filter.py` RedactionFilter + SECURE-07 must cover any keys appearing in adapter transcripts the judge sees / `.eval` logs persist. |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Canary contamination (false-confidence score) | Tampering / Repudiation | CI-asserted hash disjointness (EVAL-02), FAIL-not-skip on LFS pointer. |
| Runaway agent spend draining BYOK credits | Denial of Service (wallet) | Dual-layer: per-task `cost_limit`/`token_limit`/`time_limit` (`LimitExceededError`) + CI aggregate per-suite USD ceiling. |
| Eval-only deps (`inspect_ai`) leaking into production router | Elevation of (dependency) Privilege | D-18 one-way import arrow + `test_import_graph.py`. |
| BYOK key leakage into `.eval` logs / judge transcript / Phoenix spans | Information Disclosure | Reuse `logging_filter` redaction (SECURE-07); bound what the judge sees; Phoenix is local-only (no SaaS). |
| Indirect prompt injection via agentic task content into the LLM-judge | Tampering | Judge rubric pinned in system prompt; structured `JudgeVerdict` output; deterministic-artifact-first (judge skipped when artifact checkable). |

## Sources

### Primary (HIGH confidence)
- inspect-ai reference (`Task` limits, `eval`/`eval_set` return types, `Epochs`) — https://inspect.aisi.org.uk/reference/inspect_ai.html (verified 2026-05-31)
- inspect-ai scorers (`@scorer`, `Score`, `CORRECT`/`INCORRECT`, `accuracy`/`stderr`, `model_graded_qa`, epoch reducers) — https://inspect.aisi.org.uk/scorers.html (verified 2026-05-31)
- inspect-ai eval logs (`read_eval_log`, `header_only`, `EvalStats.model_usage`, `EvalResults`) — https://inspect.aisi.org.uk/eval-logs.html , https://inspect.aisi.org.uk/reference/inspect_ai.log.html (verified 2026-05-31)
- inspect-ai model reference (`ModelUsage` fields incl. `total_cost`, `GenerateConfig`, `ResponseSchema`) — https://inspect.aisi.org.uk/reference/inspect_ai.model.html (verified 2026-05-31)
- inspect-ai version `0.3.232` (2026-05-31) — https://pypi.org/project/inspect-ai/ (verified 2026-05-31)
- Codebase (verified by direct read): `src/routing/decide.py`, `src/routing/schema.py`, `src/routing/tests/test_decide_smoke.py` (D-18 guard), `apps/api/backends/protocol.py`, `apps/api/backends/chunks.py`, `apps/api/backends/__init__.py`, `pyproject.toml`, `.github/workflows/{ci,live-smoke}.yml`, `src/evaluation/tests/test_canary_schema.py`, `data_processed/` listing
- `10-AI-SPEC.md` (locked decisions, framework quick reference, evaluation strategy)
- `.planning/REQUIREMENTS.md` (EVAL-01..04, Out-of-Scope), `.planning/ROADMAP.md` (Phase 10), `.planning/STATE.md` (D-18 history)

### Secondary (MEDIUM confidence)
- Domain-research citations carried from AI-SPEC §1b (RouterBench 2403.12031; agentic randomness 2602.07150; BenchJack 2605.12673; agentic best-practices 2507.02825) — used for rubric grounding, not API claims.

### Tertiary (LOW confidence)
- Per-adapter population of `Done.cost_usd` and artifact-chunk `path` shape (assumptions A2/A3) — flagged for planner verification.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — inspect-ai version + every cited API symbol verified against the live 0.3.x docs; pyproject/uv.lock confirmed present.
- Architecture / wiring: HIGH — `decide()` signature, adapter `stream()` contract, `Done.cost_usd`, D-18 guard, CI conventions all verified by direct file reads; the two AI-SPEC import errors are corrected with evidence.
- Pitfalls: HIGH — derived from verified codebase facts (LFS pointers, testpaths exclusion, label mismatch) + AI-SPEC's verified-source domain failure modes.
- Open questions (canary seed/disjointness, USD aggregation, artifact shape, adapter construction): MEDIUM — identified precisely; each has a concrete recommendation and a one-line verification path for the planner.

**Research date:** 2026-05-31
**Valid until:** 2026-06-14 (14 days — inspect-ai 0.3.x ships ~daily; re-verify `Task`/`eval_set`/`cost_limit` against `inspect --version` at plan time).
