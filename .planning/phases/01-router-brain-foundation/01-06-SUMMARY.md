---
phase: 01-router-brain-foundation
plan: 06
subsystem: routing
tags: [router-05, router-06, routing-brain, framework-free, decide, frozen-dataclass, d-01-cascade, d-10-thresholds, d-11-fallback, d-12-fallback, d-17-cli, d-18-import-graph, rule-2-deviation]

# Dependency graph
requires:
  - "01-01 (uv toolchain + pytest scaffolding + src/routing/__init__.py + RED stubs at src/routing/tests/test_decide_smoke.py and test_uncertainty_fallback.py)"
  - "01-02 (src/feature_extraction/text_inputs.py build_router_text_input_single — Stage-2 input format; PromptFeatureExtractor extended with 5 agentic features)"
  - "01-04 (models/agentic_intent_classifier.joblib — CalibratedClassifierCV(FrozenEstimator(LogReg)) binary head)"
  - "01-05 (models/task_type_classifier.joblib calibrated with `unknown` OOD class + models/model_router.joblib calibrated; both 5/6-key joblib dict shape)"
provides:
  - "src/routing/schema.py — RoutingDecision frozen @dataclass with .to_json() (ROUTER-05 contract)"
  - "src/routing/config.py — D-10 taus, D-11/D-12 fallback constants, D-01 keyword sets, D-04 backend sentinels, ROUTER-06 tier-rank + epsilon, default artifact paths"
  - "src/routing/policy.py — decide_backend (D-01 cascade with browse-keyword priority), choose_final_route (lifted verbatim from demo_router.py:224-250), quality_first_pick (ROUTER-06)"
  - "src/routing/decide.py — public decide(prompt, history, artifacts, settings) -> RoutingDecision; 6-stage calibrated pipeline; CLI main() entry"
  - "src/routing/__main__.py — `python -m src.routing` fallback invocation (D-17)"
  - "22 passing tests in test_schema.py + test_rule_cascade.py (Task 1 RED→GREEN)"
  - "18 passing tests in test_decide_smoke.py + test_uncertainty_fallback.py (Task 3; D-18 + Success Criterion #4)"
affects: [01-07, 01-08, all-phase-2-onward-plans]

# Tech tracking
tech-stack:
  added: []  # No new packages — only stdlib + scipy + joblib + pandas + sklearn already in uv.lock.
  patterns:
    - "Frozen @dataclass with .to_json(ensure_ascii=False) preserves U+2014 em-dash in stdout"
    - "Pure-function inference module: artifact-load → predict_proba → rule cascade → RoutingDecision (no shared mutable state across calls; PromptFeatureExtractor singleton is lazy)"
    - "Top-level try/except Exception wrapper around decide() body returns a fallback RoutingDecision (V7 robustness — decide() NEVER raises)"
    - "D-18 import-graph guard implemented as a runtime sys.modules walk (test_decide_smoke.py) — catches transitive HTTP / SDK pulls statically"
    - "Empty/whitespace prompt fast-path returns fallback before any classifier runs (V5 input validation)"
    - "Browse-keyword priority over coding-task in policy.decide_backend (Rule 2 deviation from D-01 literal `if/elif`; the calibrated task classifier sometimes labels short browse prompts as 'coding')"

key-files:
  created:
    - "src/routing/schema.py"
    - "src/routing/config.py"
    - "src/routing/policy.py"
    - "src/routing/decide.py"
    - "src/routing/__main__.py"
    - "src/routing/tests/test_schema.py"
    - "src/routing/tests/test_rule_cascade.py"
  modified:
    - "src/routing/tests/test_decide_smoke.py (RED stubs → 7 real tests including the D-18 runtime guard)"
    - "src/routing/tests/test_uncertainty_fallback.py (1 RED stub → 11 real tests covering 5 sub-threshold prompt categories + 3 settings overrides + determinism + JSON serialization + signals telemetry)"

key-decisions:
  - "decide_backend ordering = browse-keyword FIRST, then coding-task/build-keyword. Rule 2 deviation from D-01's literal `if/elif` order — the calibrated task classifier sometimes mis-classifies short browse prompts as 'coding' (LLMRouterBench has zero browse data), and CONTEXT D-15 'Informational-URL' explicitly says 'URL + action verb -> computer-use'. With the original `if/elif` order, the plan's Task 2 acceptance Test 6 (open https://... and click...) would route to claude_code instead of computer_use. The cascade is otherwise identical to D-01."
  - "Task-type tau gate moved to AFTER the cascade (high-precision keyword path bypasses it). D-01's keyword branches require only the agentic-intent signal, not the task_type signal; gating Stage 1 first would force fallback on clear 'build me X' prompts because the calibrated task classifier is under-confident on short inputs (Plan 05 SUMMARY documented this: task_type ECE 0.116→0.142). The OpenRouter branch still gates on the task-tau because the model_router prediction depends on a well-defined task_type."
  - "Empty/whitespace prompt → fallback short-circuit BEFORE any classifier runs. V5 input validation: the calibrated classifier on '' produces a 'confident' prediction by sheer prior (top-1 reasoning), and routing a blank prompt is wrong. Satisfies Plan 06 Task 2 behavior Test 11 + Task 3 test_fallback_rationale_phrase_empty."
  - "Fallback rationale format = '{stage_prefix} - {FALLBACK_RATIONALE_SUFFIX}' with a literal ' - ' joiner. The 25-character locked suffix 'low confidence — fallback' (U+2014 dash) appears at the literal end of the rationale string regardless of which stage tripped, and `_build_fallback_decision` asserts `endswith` at construction time as belt-and-suspenders for the unit tests."
  - "PromptFeatureExtractor singleton via module-level _EXTRACTOR_SINGLETON + _get_extractor() lazy initializer. Avoids re-running the constructor (and the NLTK lazy-download guard) on every decide() call; critical for batch usage in Plan 07's eval runner."
  - "choose_final_route lifted VERBATIM from demo_router.py:224-250 into src/routing/policy.py (not imported from src.demo). Rationale: importing src.demo would pull in the REPL helpers + sys.path injection from the demo file, and would couple the routing brain to the demo's startup behavior. Verbatim lift is a documented anti-pattern fix (RESEARCH §Pattern 7) but it's the cleanest dependency boundary in v1."
  - "settings dict carries per-stage tau overrides + epsilon. Settings keys: task_type_tau, agentic_intent_tau, model_router_tau, epsilon. Plan 07's evaluation can sweep them without touching decide.py — verified by Task 3 tests test_settings_override_forces_fallback and test_settings_override_with_*_tau."
  - "TIER_RANK = {cheap:0, medium:1, strong:2} hardcoded in config.py. Unknown tiers default to medium=1 so the picker is deterministic when the model_router predicts something the mapping doesn't enumerate."

patterns-established:
  - "Routing-brain module structure: schema → config → policy → decide → __main__. Each module imports only stdlib + the modules to its LEFT, so the import graph is a strict DAG with `schema` at the root. Any future additions to src/routing/ should preserve this ordering."
  - "Fallback rationale construction: always pass a `rationale_prefix` describing WHICH stage tripped (e.g., 'task confidence 0.30 below 0.35') so Plan 07 can extract per-stage failure counts from the log. The suffix is appended in _build_fallback_decision; no caller hand-writes the literal 'low confidence — fallback' string."
  - "Test pattern for runtime import-graph guards: pre-clear forbidden modules from sys.modules, then `import src.routing.decide`, then walk sys.modules and assert no forbidden top-level-package names leaked in. Robust against pollution from earlier tests in the same pytest session."

requirements-completed: [ROUTER-05, ROUTER-06]

# Metrics
duration: 51m
completed: 2026-05-14
---

# Phase 1 Plan 06: Routing Brain (`src/routing/decide`) Summary

**Built the framework-free routing brain (`src/routing/{schema,config,policy,decide,__main__}.py`) that composes Plan 04's agentic-intent head + Plan 05's calibrated task-type and model-router heads into a 6-stage `decide(prompt, history, artifacts, settings) -> RoutingDecision` pipeline with the D-01 hard-coded rule cascade, D-10 per-stage tau gates, D-11/D-12 `openrouter/auto` fallback (rationale ENDS with the locked "low confidence — fallback" suffix containing U+2014), ROUTER-06 quality-first cost tiebreaker, D-17 CLI (`python -m src.routing.decide '<prompt>'` prints one-line JSON), and D-18 import-graph guard (zero HTTP / LLM SDK leakage). 70 passing / 15 skipped (was 30 / 18 at Plan 05 baseline). ROUTER-05 + ROUTER-06 closed; Phase 1 success criteria #1 and #4 delivered in full.**

## Performance

- **Duration:** 51 min wall-clock (commit-timestamp delta from RED test commit `96e28ee` at 01:05:06 → final test commit `5785d0b` at 01:55:48)
- **Started:** 2026-05-14T01:05:06-04:00 (RED test commit)
- **Completed:** 2026-05-14T01:55:48-04:00 (last task commit)
- **Tasks:** 3 (all `type="auto"`; Tasks 1 and 2 followed RED→GREEN TDD)
- **Files created:** 5 source + 2 new test files = 7
- **Files modified:** 3 (decide.py post-RED fix, both Task-3 test files)
- **Commits:** 4 (1 RED + 3 GREEN)

## Task Commits

| Task | RED commit | GREEN/REFACTOR commit | What landed |
| ---- | ---------- | --------------------- | ----------- |
| 1: schema.py + config.py + policy.py | `96e28ee` (test) | `674213d` (feat) | Frozen RoutingDecision, D-10 tau defaults + locked fallback constants, decide_backend cascade + choose_final_route lift + quality_first_pick ROUTER-06 tiebreaker |
| 2: decide.py + __main__.py + CLI | — | `7e09782` (feat) | 6-stage decide() pipeline + argparse CLI; smoke-tested all 4 branches via `python -m src.routing.decide`; embedded the Rule 2 cascade-ordering deviation |
| 3: test_decide_smoke.py + test_uncertainty_fallback.py | — | `5785d0b` (test) | Replaced 3 RED stubs with 18 real tests including the D-18 runtime sys.modules walk + 5 sub-threshold prompt categories + 3 settings-tau overrides + determinism + JSON-serialization |

**Plan metadata commit:** pending after this SUMMARY is written.

## Accomplishments

### Task 1: foundation modules (schema + config + policy)

**`src/routing/schema.py`** — 56 lines. Single `@dataclass(frozen=True) class RoutingDecision` with 5 fields:

```python
@dataclass(frozen=True)
class RoutingDecision:
    backend: Backend                          # "openrouter" | "claude_code" | "computer_use"
    model_or_agent: str
    rationale: str
    confidence: float
    signals: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)
```

Stdlib-only imports (`dataclasses`, `typing`, `json`). `ensure_ascii=False` is load-bearing for the U+2014 em-dash in fallback rationales — `json.dumps` would otherwise escape it to `—`.

**`src/routing/config.py`** — 158 lines. All tunables that Plan 07's evaluator can sweep:

- `DEFAULT_TASK_TYPE_TAU = 0.35`, `DEFAULT_AGENTIC_INTENT_TAU = 0.55`, `DEFAULT_MODEL_ROUTER_TAU = 0.20` (D-10 verbatim)
- `FALLBACK_BACKEND = "openrouter"`, `FALLBACK_MODEL_OR_AGENT = "openrouter/auto"`
- `FALLBACK_RATIONALE_SUFFIX = "low confidence — fallback"` (25 chars, U+2014 at index 15)
- `CLAUDE_CODE_SENTINEL = "claude-agent-sdk"`, `COMPUTER_USE_SENTINEL = "computer-use-2025-11-24"`
- `BUILD_KEYWORDS` (frozenset of 7 verbs from D-01), `BROWSE_KEYWORDS` (frozenset of 8 verbs from D-01)
- `TIER_RANK = {cheap:0, medium:1, strong:2}` + `DEFAULT_EPSILON = 0.02` (ROUTER-06)
- `DEFAULT_ARTIFACT_PATHS` (dict of 3 joblib paths) + `DEFAULT_MODEL_MAPPING_PATH`
- `CODING_TASK_TYPES = {"coding", "instruction_following", "instruction-following"}` so the cascade matches both spellings the label_encoder might emit

**`src/routing/policy.py`** — 226 lines. Three pure functions:

1. `decide_backend(agentic_intent, agentic_confidence, task_type, prompt, ...)` → `(backend, sentinel_or_None, rule_fired_reason)`. Implements the D-01 cascade with **Rule 2 deviation**: browse-keyword fires BEFORE coding-task. Documented inline in the function body.
2. `choose_final_route(predicted_model, model_mapping)` → dict. Lifted VERBATIM from `src/demo/demo_router.py:224-250` to avoid pulling in the demo's sys.path injection.
3. `quality_first_pick(top_k_predictions, model_mapping, epsilon)` → str (picked slug). ROUTER-06 cost tiebreaker: when multiple predictions are within `epsilon` confidence, prefer the lowest-cost tier.

### Task 2: decide() pipeline + CLI

**`src/routing/decide.py`** — 487 lines. Six-stage pipeline:

```python
def decide(prompt, history=None, artifacts=None, settings=None) -> RoutingDecision:
    try:
        # V5: empty/whitespace -> fallback fast-path
        # Stage 1: task_type predict_proba (no gate yet)
        # Stage 2: agentic_intent predict_proba (gate: tau_agentic)
        # Stage 3a: D-01 cascade. If keyword path fires (browse / build /
        #            coding-task + agentic) -> emit RoutingDecision now.
        # Stage 3b: OpenRouter branch needs task_type tau gate (D-09 OOD).
        # Stage 4: model_router predict_proba (gate: tau_router)
        # Stage 5: quality_first_pick + choose_final_route
        # Stage 6: emit RoutingDecision (min of stage confs as overall)
    except Exception as exc:  # V7 robustness wrapper
        return _build_fallback_decision(...)
```

Imports the canonical 5/6-key joblib artifact dict via `_load_one_artifact` (validates required keys per Pitfall 4). Numeric features built via `_build_numeric_features` (lifted from `demo_router.py:81-107`). Stage-2 input string built via `src.feature_extraction.text_inputs.build_router_text_input_single` (Plan 02's centralized helper — no third copy of the format string).

**`src/routing/__main__.py`** — 11 lines. Module entry-point alias so `python -m src.routing` works in addition to `python -m src.routing.decide`. D-17 satisfied either way.

### Task 3: D-18 import-graph guard + fallback rationale tests

**`src/routing/tests/test_decide_smoke.py`** — 116 lines, 7 tests:

| Test | Asserts |
| ---- | ------- |
| `test_no_forbidden_modules_imported_after_decide` | Walks sys.modules post-import and asserts none of `{fastapi, httpx, requests, aiohttp, anthropic, openai}` appear. **D-18 runtime guard.** |
| `test_decide_returns_routing_decision` | ROUTER-05 shape contract on "what is the capital of France?" |
| `test_decide_returns_routing_decision_for_clearly_agentic_build_prompt` | "build me a Streamlit dashboard" → claude_code / claude-agent-sdk |
| `test_decide_returns_routing_decision_for_clearly_agentic_browse_prompt` | "open https://news.ycombinator.com and click ..." → computer_use / computer-use-2025-11-24 |
| `test_decide_robust_against_empty_input` | "" → fallback (V7) |
| `test_decide_robust_against_huge_input` | 100k chars → does not raise (V7) |
| `test_decide_does_not_run_at_module_import_time` | Module is import-cheap (lazy `_EXTRACTOR_SINGLETON`) |

**`src/routing/tests/test_uncertainty_fallback.py`** — 173 lines, 11 tests:

| Test | Asserts |
| ---- | ------- |
| `test_fallback_rationale_phrase_gibberish` | "asdfgh" → fallback contract |
| `test_fallback_rationale_phrase_emoji_only` | "🌶️🌶️🌶️" → fallback contract |
| `test_fallback_rationale_phrase_single_token` | "yes" → fallback contract |
| `test_fallback_rationale_phrase_empty` | "" → fallback contract |
| `test_fallback_rationale_phrase_punctuation_only` | "?!!.,?!" → fallback contract |
| `test_settings_override_forces_fallback` | task_type_tau=0.999 + non-keyword prompt → fallback |
| `test_settings_override_with_agentic_intent_tau` | agentic_intent_tau=0.99999 → fallback via Stage 2 gate |
| `test_settings_override_with_model_router_tau` | model_router_tau=0.99 → fallback via Stage 4 gate |
| `test_fallback_is_deterministic` | 3× decide("asdfgh") returns identical decisions |
| `test_fallback_decision_is_json_serializable` | to_json() round-trips through `json.loads` |
| `test_fallback_signals_record_diagnostic_telemetry` | fallback signals carry the failed-gate measurement |

### Test counts

| File | Tests before | Tests after | Delta |
| ---- | -----------: | ----------: | -----:|
| `src/routing/tests/test_schema.py` | 0 (NEW) | 9 | +9 |
| `src/routing/tests/test_rule_cascade.py` | 0 (NEW) | 13 | +13 |
| `src/routing/tests/test_decide_smoke.py` | 2 RED | 7 | +5 passing, -2 skipped |
| `src/routing/tests/test_uncertainty_fallback.py` | 1 RED | 11 | +10 passing, -1 skipped |
| **Total in this plan** | **3 skip** | **40 passing** | **+40 passing / -3 skip** |

Full project suite: **70 passed, 15 skipped** (was 30 passed, 18 skipped at the Plan 05 baseline).

## The Exact Rationale Strings (per PLAN.md `<output>` requirement #1)

Plan 07's canary eval will assert against `rationale` text. The exact strings emitted today:

### Happy-path OpenRouter (knowledge / chat)

```
task=knowledge | agentic=conversational | model_router=internlm3-8b-instruct | chosen=internlm3-8b-instruct | conversational (non-agentic) -> OpenRouter
```

### Claude Code (build keyword)

```
task=general | agentic=agentic | agentic + build/edit keyword -> Claude Code
```

### Claude Code (coding task)

```
task=coding | agentic=agentic | agentic + coding task (coding) -> Claude Code
```

### Computer Use (browse keyword)

```
task=coding | agentic=agentic | agentic + browse/interact keyword -> computer-use
```

### Fallback — task_type tau

```
task confidence 0.30 below 0.35 - low confidence — fallback
```

### Fallback — agentic_intent tau

```
agentic-intent confidence 0.30 below 0.55 - low confidence — fallback
```

### Fallback — model_router tau

```
model-router confidence 0.15 below 0.20 - low confidence — fallback
```

### Fallback — empty prompt

```
empty prompt - low confidence — fallback
```

### Fallback — internal error (V7)

```
internal error: <ExceptionType> - low confidence — fallback
```

All fallback rationales end with the locked 25-char substring `"low confidence — fallback"` (U+2014 dash at index 15 / -10) — verified character-by-character in `test_schema.py::test_fallback_rationale_suffix_has_u2014_dash` and at runtime by `test_fallback_rationale_phrase_*` in `test_uncertainty_fallback.py`.

## quality_first_pick / tier_tiebreaker_fired observation (per PLAN.md `<output>` requirement #2)

**During CLI smoke-testing, the tiebreaker did NOT fire.** Observation from the canonical happy-path prompt:

| Prompt | top-1 | top-2 | top-3 | Gap (top1 - top2) | Tiebreaker fired? |
| ------ | ----- | ----- | ----- | ----------------: | :---------------- |
| "what is the capital of France?" | internlm3-8b-instruct (0.364) | qwen3-235b-a22b-2507 (0.289) | OTHER (0.105) | 0.075 | No (>> epsilon=0.02) |

This is **expected behavior**: the model_router was calibrated with sigmoid, which produces sharp top-1 predictions when the prompt is well-classified. The 0.02 epsilon is tight by design — Plan 07's canary set will exercise edge cases where the top-2 gap is genuinely small (e.g., prompts that lie on the boundary between two similar-tier models).

**Recommendation for Plan 07's planner:**
- Add canary prompts that the calibrated model_router is genuinely uncertain about — these will exercise the tiebreaker.
- Sweep `epsilon` from {0.01, 0.02, 0.05, 0.10} via the `settings` dict; the canary's confusion matrix will show whether 0.02 is too tight or too loose.
- The `signals["tier_tiebreaker_fired"]` field is populated on every OpenRouter-branch decision so the eval can compute "tiebreaker activation rate" as a metric.

## label_encoder.classes_ confirmed at runtime (per PLAN.md `<output>` requirement #3)

From the loaded joblibs at decide()-time:

```
task_type_classifier.label_encoder.classes_ = [
    'agentic', 'coding', 'emotion', 'factual', 'general',
    'knowledge', 'math', 'medical', 'reasoning', 'unknown', 'writing'
]

agentic_intent_classifier.label_encoder.classes_ = ['agentic', 'conversational']

model_router.label_encoder.classes_ = [
    'MiniCPM4.1-8B', 'OTHER', 'OpenThinker3-7B',
    'cogito-v1-preview-llama-8B', 'deepseek-v3-0324',
    'deepseek-v3.1-terminus', 'gemini-2.5-flash', 'glm-4-9b-chat',
    'gpt-5', 'gpt-5-chat', 'granite-3.3-8b-instruct',
    'internlm3-8b-instruct', 'kimi-k2-0905', 'openrouter',
    'qwen3-235b-a22b-2507', 'qwen3-235b-a22b-thinking-2507'
]
```

**Implications for Plan 07's canary CSV `expected_backend` values:**

- `task_type_classifier` can emit any of these 11 labels. The D-01 cascade's coding-task branch matches `coding` (and falls back to `instruction_following` / `instruction-following` if the labeler ever evolves to include it — currently it does NOT). Plan 07's canary should use prompts that the trained classifier actually predicts as `coding` — `general` is the most common label for short build prompts and the cascade fires on the keyword path, NOT the task-type path, in that case.
- `agentic_intent_classifier` emits `agentic` or `conversational` (alphabetical). Plan 06 reads `agentic_label == "agentic"` rather than hardcoding index 0 — robust to label-encoder re-orderings.
- `model_router` includes the literal `openrouter` slug as a class. When the router predicts `openrouter`, `choose_final_route` resolves it to `api_model="openrouter/auto"` — same string as the fallback target. So `signals["chosen_slug"] == "openrouter"` is a happy-path "auto" route, distinct from the fallback path which sets `model_or_agent` via the `FALLBACK_MODEL_OR_AGENT` constant.

## Forbidden imports observed during development (per PLAN.md `<output>` requirement #4)

**Zero forbidden imports leaked at any point during this plan.** The `src/routing/` package was built clean against D-18 from the first commit:

- `schema.py`: imports `dataclasses`, `typing`, `json` (stdlib only)
- `config.py`: imports `os` (stdlib only)
- `policy.py`: imports `typing` + `src.routing.config`
- `decide.py`: imports `argparse`, `json`, `os`, `sys`, `typing` (stdlib); `joblib`, `pandas`, `scipy.sparse` (existing project deps from uv.lock); `src.routing.{schema,config,policy}` (local); `src.feature_extraction.text_inputs.build_router_text_input_single` (Plan 02); `Feature_extractor.PromptFeatureExtractor` (via sys.path injection — the documented anti-pattern from CLAUDE.md).
- `__main__.py`: imports `src.routing.decide.main` (local).

The runtime D-18 guard test in `test_decide_smoke.py::test_no_forbidden_modules_imported_after_decide` confirms the import-graph stays clean even with the sys.path injection: after `import src.routing.decide`, `sys.modules` contains zero `{fastapi, httpx, requests, aiohttp, anthropic, openai}` top-level packages. **Phase 2 / Phase 3 planners can rely on this: anything they import into `src/routing/` MUST also keep the graph clean, or this test will trip in CI.**

## Decisions Made

1. **Browse-keyword priority over coding-task in `decide_backend`** (Rule 2 deviation from D-01 literal `if/elif`). See Rule 2 deviation in the Deviations section.
2. **Task-type tau gate moved to AFTER the cascade.** D-01's keyword branches need only the agentic signal; gating Stage 1 first would force fallback on clear "build me X" / "open URL" prompts because the calibrated task classifier is deliberately under-confident on short inputs. Documented inline in `decide.py` at the Stage 3a/3b boundary.
3. **Empty/whitespace prompt → fallback fast-path.** V5 input validation. The calibrated heads would otherwise return a "confident" prediction on "" by sheer prior.
4. **Fallback rationale joiner = ` - ` (literal space-hyphen-space).** The 25-char locked suffix is appended in `_build_fallback_decision` with an assert-endswith belt-and-suspenders.
5. **PromptFeatureExtractor singleton.** Module-level `_EXTRACTOR_SINGLETON = None` + `_get_extractor()` lazy initializer. Avoids re-running the constructor (and the NLTK lazy-download guard) on every decide() call.
6. **choose_final_route lifted VERBATIM from demo_router.py:224-250** rather than imported. Keeps the routing brain decoupled from the demo's sys.path injection + REPL helpers.
7. **CLI = argparse with a single positional `prompt`.** No `--settings` / `--artifacts` flags in v1 — Plan 07's eval driver constructs the settings dict in Python and passes it to `decide()` directly, not via the CLI.
8. **`sys.path.append(SRC_DIR)` for `Feature_extractor` import.** Documented anti-pattern carried over per CONTEXT `<code_context>` line 151. The D-18 smoke test verifies that even with this sys.path manipulation, no forbidden modules leak in.

## Deviations from Plan

### Rule 2 — Auto-add missing critical functionality

**1. [Rule 2 — Cascade ordering: browse-keyword priority over coding-task]**

- **Found during:** Task 2 CLI smoke-test of `"open https://news.ycombinator.com and click the top story"`.
- **Issue:** D-01 lists the cascade as `if claude_code elif computer_use`, which is first-match-wins on coding-task. The calibrated task-type classifier predicts `coding` (prob 0.347) for the browse prompt — likely because the URL token and short imperative verbs overlap with the LLMRouterBench coding distribution (LLMRouterBench has no browse data). The literal D-01 cascade would route this to claude_code, contradicting Plan 06 Task 2 acceptance Test 6 and CONTEXT D-15 "Informational-URL" ("URL + action verb -> computer-use").
- **Fix:** Reordered `policy.decide_backend` so the browse-keyword branch fires BEFORE the coding-task branch. The cascade is otherwise identical:
  1. agentic + browse_keyword → computer_use (most specific)
  2. agentic + (coding-task OR build_keyword) → claude_code
  3. otherwise → openrouter
- **Files modified:** `src/routing/policy.py`
- **Verification:** All four CLI branches now route correctly:
  - "what is the capital of France?" → openrouter / openrouter/auto
  - "build me a Streamlit dashboard" → claude_code / claude-agent-sdk
  - "open https://news.ycombinator.com and click the top story" → computer_use / computer-use-2025-11-24
  - "asdfgh" → openrouter / openrouter/auto (fallback)
- **Committed in:** `7e09782` (Task 2 commit)

**2. [Rule 2 — Task-type tau gate moved to after the cascade]**

- **Found during:** Task 2 first CLI smoke-test (before the cascade reordering).
- **Issue:** The plan's Action step 7 (Stage 1 — task_type) places the task-tau gate BEFORE Stage 2 (agentic_intent). Under this ordering, the calibrated task classifier's under-confidence (top-1 prob 0.32 for "build me a Streamlit dashboard") would force fallback BEFORE the cascade could see the build keyword. Plan 06 Task 2 acceptance Test 5 expects this prompt to route to claude_code at the default tau.
- **Fix:** Reordered `decide()` so:
  - Stage 1: run task_type classifier (no gate yet)
  - Stage 2: run agentic_intent classifier (gate on tau_agentic)
  - Stage 3a: D-01 rule cascade. If keyword path fires (browse / build / coding-task + agentic), emit decision immediately — bypassing Stage 1's tau gate.
  - Stage 3b: OpenRouter branch (the only path that depends on task_type for the model_router input) gates on task_type_tau here.
- **Files modified:** `src/routing/decide.py`
- **Verification:** All four CLI branches now route correctly; full suite stays green.
- **Committed in:** `7e09782` (Task 2 commit)

**3. [Rule 2 — Empty/whitespace prompt fast-path]**

- **Found during:** Task 3 `test_fallback_rationale_phrase_empty` initially failed.
- **Issue:** An empty string "" can pass the calibrated heads with `task=reasoning prob=0.41 agentic=agentic prob=0.86 router=internlm3-8b-instruct prob=0.39` — all above the default taus. The model_router then resolves to `internlm3-8b-instruct` whose `api_model=null`, falling through to `openrouter/auto` via the unverified-slug branch. The result is `(openrouter, openrouter/auto)` but with a HAPPY-PATH rationale, NOT the locked fallback suffix. Test 11 + Test 3 in PLAN.md `<behavior>` both expect "" to produce a fallback rationale.
- **Fix:** Added an empty/whitespace check at the top of `decide()`: if `not prompt or not prompt.strip()`, short-circuit to `_build_fallback_decision("empty prompt", ...)` BEFORE any classifier runs. V5 input validation.
- **Files modified:** `src/routing/decide.py`
- **Verification:** `test_fallback_rationale_phrase_empty` passes; all other fallback tests unaffected.
- **Committed in:** `5785d0b` (Task 3 commit)

**Total deviations:** 3 Rule 2 (auto-add missing critical functionality). No Rule 1 (bugs), no Rule 3 (blockers), no Rule 4 (architectural). All three were necessary for the plan's acceptance criteria to pass on the current calibrated models.

### Pitfall observations (documented for traceability)

- **Plan acceptance criterion's off-by-two en-dash check** (PLAN.md Task 1 acceptance line "ord(FALLBACK_RATIONALE_SUFFIX[-12]) == 8212") points at index `-12` from the end of the 25-char string, which is the `'e'` in "confidence" (`ord = 101`), not the U+2014 dash. The dash is at index `15` (or `-10`). My test asserts against the correct positions (`[15]` and `[-10]`) AND against the full 25-element character-code fingerprint listed in the plan's `<behavior>` Test 4. The CHARACTER (U+2014 = 8212) is the load-bearing assertion; the exact position is mechanical.

## Issues Encountered

- **Calibrated task classifier under-confidence on short prompts.** Inherited from Plan 05 (which documented training-set ECE 0.116→0.142 regression). Forced the Rule 2 deviation #2 above. Plan 07 should compute canary-set ECE; if it's > 0.10, the Open Question 1 escape hatch (switch to `method="isotonic"`) flips one line in `src/task_classifier/train_task_classifier_robust.py`.
- **The model_router predicts `internlm3-8b-instruct` (api_model=null, unverified) as top-1 for "what is the capital of France?".** The `unverified` slug branch in `choose_final_route` resolves to OTHER with `api_model=null`; `decide()` then falls through to `FALLBACK_MODEL_OR_AGENT = "openrouter/auto"`. Confidence happens to be 0.36 which barely clears `tau_router=0.20`. This is intended behavior (D-02: "Unverified slugs fall through to the OTHER bucket which maps to openrouter/auto"), but it means the CLI smoke prompt produces the same `model_or_agent` ("openrouter/auto") as the fallback path despite NOT being a fallback. Rationale string makes the distinction clear: happy-path includes `task=knowledge | agentic=conversational | model_router=internlm3-8b-instruct | chosen=internlm3-8b-instruct | conversational (non-agentic) -> OpenRouter`, while fallback ends with the locked suffix.
- **pytest output truncation in the harness.** Same issue Plans 01-02 / 01-03 / 01-05 documented. Workaround: write pytest output to `/private/tmp/claude-*/.../tasks/*.output` then read it back. Final counts: 70 passed, 15 skipped (counted via the final summary line which the harness preserves on the longer run).

## Threat Surface Scan

No new threat surface introduced beyond the plan's `<threat_model>` block. Per-threat status:

- **T-01-02 (information disclosure via rationale/signals):** mitigated. `decide()` takes NO API keys; settings only carries thresholds. Smoke test confirms no HTTP / SDK library imports.
- **T-01-04 (framework-free import graph):** mitigated. `test_no_forbidden_modules_imported_after_decide` enforces this at every CI run.
- **T-01-05 (joblib pickle deserialization):** accepted for Phase 1; ReadMe.md security advisory lands in Phase 6 OSS-04.
- **T-01-RB-V5 (input validation):** mitigated. _agentic_features 50,000-char bound (Plan 02) + decide()'s empty-prompt fast-path + try/except wrapper. Tests `test_decide_robust_against_empty_input` and `test_decide_robust_against_huge_input` cover the edges.
- **T-01-RB-V7 (error handling):** mitigated. Top-level try/except in `decide()` returns a fallback RoutingDecision on any exception. The internal-error rationale ends with the locked suffix and signals carry `error_type` + `error_msg[:500]`. Tests `test_decide_robust_against_*` and the determinism test exercise this.

No new `threat_flag:` rows. No new auth paths, file-access patterns, or schema changes at trust boundaries.

## Known Stubs

None. Every code path is fully wired:
- `decide()` loads real joblibs, runs real `predict_proba`, applies the real cascade, returns a real `RoutingDecision`.
- All test fixtures load real artifacts from `models/*.joblib`.
- No mock data, no placeholder constants, no TODO comments.

The `_EXTRACTOR_SINGLETON` module-level cache starts as `None` — that's a lazy-initialization pattern, NOT a stub. The first `decide()` call materializes it via `_get_extractor()`.

## TDD Gate Compliance

This plan is `type: execute`. Task 1 and Task 2 are `tdd="true"`. Task 3 is `type="auto"` (test-implementation only).

**Task 1 gate sequence verified in git log:**
- RED: `96e28ee` test(01-06): add RED tests for schema, config, policy
- GREEN: `674213d` feat(01-06): add routing schema, config, policy

**Task 2 gate sequence:** Task 2's smoke test was the CLI invocation rather than a separate RED commit (the plan's `<verify>` block is a CLI pipeline, not a pytest run). Task 2's commit `7e09782` is a single GREEN that includes the policy.py reorder fix discovered during smoke testing — documented under Rule 2 deviation #1.

**Task 3 was a test-only commit** (`5785d0b`) — replacing 3 RED placeholder stubs from Plan 01-01 with 18 real tests. No new source code in Task 3 except the empty-prompt fast-path patch to `decide.py`, which is documented as Rule 2 deviation #3.

## Files Created/Modified — full list

### Created (7 files)

| File | Lines | Purpose |
| ---- | ----: | ------- |
| `src/routing/schema.py` | 56 | RoutingDecision frozen @dataclass with .to_json() |
| `src/routing/config.py` | 158 | D-10 taus, D-04 sentinels, D-11/D-12 fallback constants, D-01 keyword sets, ROUTER-06 TIER_RANK + epsilon |
| `src/routing/policy.py` | 226 | decide_backend cascade + choose_final_route lift + quality_first_pick (ROUTER-06) |
| `src/routing/decide.py` | 487 | 6-stage pipeline + CLI main() (D-17) |
| `src/routing/__main__.py` | 11 | `python -m src.routing` fallback alias |
| `src/routing/tests/test_schema.py` | 124 | 9 tests covering schema + config |
| `src/routing/tests/test_rule_cascade.py` | 199 | 13 tests covering D-01 cascade + ROUTER-06 |

### Modified (3 files)

| File | Change |
| ---- | ------ |
| `src/routing/tests/test_decide_smoke.py` | 2 RED stubs → 7 real tests including the D-18 runtime guard |
| `src/routing/tests/test_uncertainty_fallback.py` | 1 RED stub → 11 real tests covering 5 sub-threshold prompt categories + 3 settings overrides + determinism + JSON-serialization |
| `src/routing/decide.py` | Cascade-ordering fix + task-tau-after-cascade reorder + empty-prompt fast-path (all Rule 2 deviations, applied in Task 2 and Task 3 commits) |

## Next Phase Readiness

**Ready for Plan 07 (Wave 3 — canary eval + evaluate_routing.py):**

- `decide()` is importable from anywhere (`from src.routing.decide import decide`) and returns a `RoutingDecision` whose 5 fields are sufficient for the canary's expected-vs-actual comparison.
- The CLI `python -m src.routing.decide '<prompt>'` prints one-line JSON suitable for piping into Plan 07's batch eval runner.
- Per-stage threshold sweep enabled via the `settings` dict (`task_type_tau`, `agentic_intent_tau`, `model_router_tau`, `epsilon`) — no decide.py changes needed.
- `signals` carries the per-stage telemetry Plan 07 needs for the metric stack:
  - `task_type`, `task_confidence`, `task_top3`
  - `agentic_intent`, `agentic_confidence`
  - `rule_fired` (the D-01 branch reason string)
  - `predicted_model`, `model_router_confidence`, `model_router_top3`
  - `chosen_slug`, `tier_tiebreaker_fired`, `route_source`, `route_tier`, `openrouter_verified`
  - On fallback: `error_type` + `error_msg` (V7) or the failed gate's measurement
- **Open Question 1 escape hatch flagged** (carry-forward from Plan 05): training-set ECE on both calibrated heads regressed mildly (task_type 0.116→0.142; model_router 0.063→0.074). Plan 07 should compute canary-set ECE; if > 0.10 for either stage, the one-line switch from `method="sigmoid"` to `method="isotonic"` in `src/task_classifier/train_task_classifier_robust.py` / `src/model_router/train_model_router.py` retrains the affected head.

**Ready for Plan 08 (Wave 4 — demo integration + regression guard):**

- `src/demo/demo_router.py` can now have its `route_prompt()` function replaced with a thin wrapper that calls `src.routing.decide.decide()` and adapts the RoutingDecision into the legacy dict shape consumed by `print_route_result()`. The existing CLI demo + REPL boot pattern stays intact; Pitfall 4 regression guard test (`src/demo/tests/test_artifact_compat.py`) continues to pass because Plan 06 does NOT touch any joblib's dict shape.
- `evaluation/baselines.json` from Plan 05 remains the regression-guard "before" snapshot. Plan 08's `test_no_regression` is unaffected by Plan 06 (which adds inference glue, not training).

**Ready for Phase 2 (Wave-X — backend adapters):**

- Adapters consume `RoutingDecision.model_or_agent` directly. The four possible values are:
  - `"openrouter/auto"` (fallback OR unverified-slug branch)
  - any of the 16 model_router classes that are verified (e.g., `"openai/gpt-5"`, `"qwen/qwen3-235b-a22b-2507"`, etc.) — resolved via `config/model_mapping.json`
  - `"claude-agent-sdk"` (Claude Code backend sentinel)
  - `"computer-use-2025-11-24"` (computer-use backend sentinel)
- `RoutingDecision.signals["chosen_slug"]` carries the model_router's exact prediction even when `model_or_agent` is `"openrouter/auto"` — adapters can log this for observability without touching the model_or_agent dispatch.

**Ready for Phase 3 (Wave-X — FastAPI process):**

- `decide()` is import-safe from any Python process. D-18 guarantees zero FastAPI dependency in `src.routing.*`. The FastAPI request handler in Phase 3 will `from src.routing.decide import decide` at module-load time and call it inside the request body.
- The 50,000-char input bound (Plan 02) + V7 try/except wrapper means `decide()` is also robust against adversarial HTTP request bodies.

**No blockers.** Plan 07 can start immediately.

## Carries Forward (from prior plans)

- **Open Question 1 (calibration method)**: Plan 05 SUMMARY flagged training-set ECE regression on both calibrated heads (task_type 0.116→0.142; model_router 0.063→0.074). Plan 06 doesn't act on this; Plan 07's canary-set ECE is the canonical signal.
- **Drop rate during Plan 03's hand-audit was 0%** vs. RESEARCH-expected 5-15%. Plan 06 doesn't act on this; Plan 07's per-edge-case precision/recall on the canary will surface any mislabeled clusters.
- **Tier-router family (`src/model_router_tier/*`) still duplicates the Stage-2 text input format.** Plan 02 deferred the migration; Plan 06 didn't need to migrate them because `decide()` doesn't use the tier router. Deferred to a future cleanup phase.

## Self-Check

Verification of all claims:

- **File existence:**
  - `src/routing/schema.py` — verified via direct Read (56 lines, 2917 bytes).
  - `src/routing/config.py` — verified (6490 bytes, 158 lines).
  - `src/routing/policy.py` — verified (11324 bytes, 226 lines).
  - `src/routing/decide.py` — verified (21206 bytes, 487 lines).
  - `src/routing/__main__.py` — verified (409 bytes, 11 lines).
  - `src/routing/tests/test_schema.py` — verified (5048 bytes).
  - `src/routing/tests/test_rule_cascade.py` — verified (7823 bytes).
  - `src/routing/tests/test_decide_smoke.py` — verified (5124 bytes).
  - `src/routing/tests/test_uncertainty_fallback.py` — verified (6292 bytes).

- **Commit existence:**
  - `git log --oneline cf3c2ca..HEAD` shows 4 task commits in order:
    - `96e28ee` test(01-06): add RED tests for schema, config, policy
    - `674213d` feat(01-06): add routing schema, config, policy
    - `7e09782` feat(01-06): implement decide() and CLI
    - `5785d0b` test(01-06): implement D-18 import-graph guard + fallback rationale tests

- **Forbidden imports check:**
  - `grep -E "^(import|from) (fastapi|httpx|requests|aiohttp|anthropic|openai)\b" src/routing/{schema,config,policy,decide,__main__}.py` returns nothing.
  - Runtime D-18 guard `test_no_forbidden_modules_imported_after_decide` passes.

- **CLI smoke-test:** `uv run python -m src.routing.decide "what is the capital of France?"` exits 0 and prints valid JSON with the 5 RoutingDecision keys. Same for "asdfgh" / "build me a Streamlit dashboard" / "open https://news.ycombinator.com and click the top story" — all four branches verified.

- **En-dash sanity:** `uv run python -c "from src.routing.config import FALLBACK_RATIONALE_SUFFIX; assert chr(0x2014) in FALLBACK_RATIONALE_SUFFIX"` exits 0.

- **Test results:**
  - `uv run pytest src/routing/tests/ -q` → 40 passed, 0 skipped from this plan's slice (was 30 passed, 3 skipped at Plan 05 baseline within `src/routing/tests/`).
  - `uv run pytest -q` → 70 passed, 15 skipped (was 30 passed, 18 skipped at Plan 05 baseline). Net +40 passes, -3 skips (the 3 RED stubs now implemented).

- **No regressions outside this plan:** the 15 remaining skips are all in `src/calibration/tests/` (none — 0 skips), `src/demo/tests/test_artifact_compat.py` (4 placeholders), `src/evaluation/tests/test_canary_schema.py` (4), `test_evaluate_routing.py` (4), `test_no_regression.py` (3), `src/task_classifier/tests/test_agentic_intent.py` (0). Plans 07 / 08 fill these.

## Self-Check: PASSED

---
*Phase: 01-router-brain-foundation*
*Completed: 2026-05-14*
