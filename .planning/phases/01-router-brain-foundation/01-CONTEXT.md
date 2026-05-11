# Phase 1: Router Brain Foundation - Context

**Gathered:** 2026-05-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver a **framework-free** pure-function module `src/routing/decide(prompt, history, artifacts, settings) -> RoutingDecision` that is callable from the existing CLI demo today and from any future FastAPI process tomorrow, with zero FastAPI dependency in the import graph.

The brain composes four signals into one decision:

1. **Calibrated task-type classifier** (extended with an `unknown` OOD class) — `models/task_type_classifier.joblib`
2. **Calibrated model router** (16 model classes, existing) — `models/model_router.joblib`
3. **New calibrated agentic-intent binary classifier** — `models/agentic_intent_classifier.joblib`
4. **Hand-labeled routing canary eval** (~42 prompts, distinct from LLMRouterBench) — `data_processed/routing_decision_eval.csv`

A new offline eval script (`src/evaluation/evaluate_routing.py`) reports backend-pick accuracy + ECE + per-backend P/R + a confusion matrix + `low_confidence_rate` against the canary set, and the existing CLI demo (`src/demo/demo_router.py`) is updated to call `decide()` so the simulated route is now produced by the same code path that Phase 2's adapters will consume.

Adjacent infrastructure that lands in this same phase per ROADMAP success criteria: root `pyproject.toml` + `uv.lock` (OSS-01) and `.gitignore` entries for `.env`, `*.db*`, `__pycache__/`, `.venv/`, `chat.db` (SECURE-03).

**Not in scope (deferred to later phases):** any HTTP server, any live OpenRouter / Claude Code SDK / computer-use call, any UI, any database, any cost-cap enforcement, any key handling beyond `.gitignore` lines.
</domain>

<decisions>
## Implementation Decisions

### Backend Decision Policy
- **D-01: Composition is a hard-coded rule cascade**, not a score blend.
  - `if agentic_intent == True AND (task_type in {coding, instruction-following} OR keyword in {build, write, edit, refactor, fix, implement, create}) -> backend="claude_code"`
  - `elif agentic_intent == True AND keyword in {open, browse, url, click, navigate, visit, fill, submit} -> backend="computer_use"`
  - `else -> backend="openrouter"`
  - Every branch is debuggable from the rationale string; no magic weights.
- **D-02: Inside the OpenRouter branch, `model_or_agent` comes from the existing `model_router` prediction**, resolved via `config/model_mapping.json`. Unverified slugs fall through to the `OTHER` bucket which maps to `openrouter/auto`. Preserves all 16-class training work; reuses the existing `choose_final_route` mechanism from `src/demo/demo_router.py:245`.
- **D-03: `RoutingDecision` carries BOTH a short human `rationale` AND a structured `signals` dict.**
  - `rationale` (str): one-line sentence used by the Phase 4/5 UI chip — e.g., `"agentic build-task keywords → Claude Code"` or `"low confidence — fallback"`.
  - `signals` (dict): structured key=value carrying `task_type`, `task_confidence`, `agentic_intent`, `agentic_confidence`, `predicted_model`, `model_router_confidence`, `rule_fired`, plus any per-stage threshold check results. Persistable to `routing_decisions` SQLite row later (STORE-02).
- **D-04: `model_or_agent` is a concrete provider-ready string.**
  - OpenRouter backend → the resolved `api_model` field from the mapping (e.g., `"openai/gpt-5"`, `"openrouter/auto"`).
  - Claude Code backend → fixed sentinel `"claude-agent-sdk"`.
  - Computer-use backend → fixed sentinel `"computer-use-2025-11-24"` (matches the beta header from BACKEND-05).
  - Adapters consume the string directly; no second resolution step.

### Agentic-Intent Classifier
- **D-05: Positives are LLM-synthesized from a small hand-written seed.** Hand-write ~30 high-quality seed agentic prompts (anchored to the README golden-path examples: build apps, edit files, open URLs, fill forms, scrape pages). Then prompt a strong chat LLM to generate ~500 paraphrastic variations covering verb diversity, length range, multi-step phrasings, and domain spread.
- **D-06: Negatives are mined from LLMRouterBench non-tool-use rows** (math, factual QA, writing, affective, instruction-following without imperatives). Already in the offline pipeline — no new ingest path required.
- **D-07: Target ~1,000 prompts, balanced 500 agentic / 500 conversational.** Enough for `CalibratedClassifierCV` to actually calibrate; small enough that the human researcher can spot-audit every row.
- **D-08: Feature stack matches the existing classifiers (TF-IDF + handcrafted) PLUS 3–5 new handcrafted features specific to agentic intent.** New features: `imperative_verb_count`, `has_url`, `has_file_path`, `has_code_fence`, `has_action_keyword`. Added to `PromptFeatureExtractor` so they are also available to the task classifier and model router. Saved artifact follows the canonical dict shape `{model, vectorizer, scaler, label_encoder, feature_columns}` so `load_joblib_artifacts()` in `src/demo/demo_router.py:35` loads it with no changes.

### Low-Confidence Fallback & OOD Policy
- **D-09: OOD detection is belt-and-suspenders.**
  - The task-type classifier gains a literal `unknown` class in its label encoder. Training data for it comes from rows in `classifier_training_with_types.csv` where the weak labeler `src/task_classifier/build_question_type.py` returns no keyword match — these become the "unknown" bucket (estimated cardinality is documented as part of the training script's stdout).
  - Separately, at inference time, `decide()` applies a probability threshold on each stage's `max(predict_proba)`. Sub-threshold → fallback regardless of which class won. Two independent OOD signals.
- **D-10: Confidence thresholds are per-stage, stored in `settings`, with defaults shipped in code.**
  - `settings.task_type_tau = 0.35` (10 task-type classes, broad bins)
  - `settings.agentic_intent_tau = 0.55` (binary head, expect crisp probabilities)
  - `settings.model_router_tau = 0.20` (16 model classes, lower max-prob floor by design)
  - All three are overridable per call via the `settings` argument; defaults are constants in `src/routing/decide.py` or a `src/routing/config.py` (planner's call).
- **D-11: Fallback target is `openrouter/auto`** (already in `config/model_mapping.json`: slug `"openrouter"`, `api_model: "openrouter/auto"`, `tier: "medium"`, `openrouter_verified: true`). OpenRouter's own meta-router becomes the safe default — cheap, broad coverage, requires no new mapping entry.
- **D-12: Fallback is ALWAYS the OpenRouter backend.** Never silently fall back to Claude Code or computer-use, regardless of which stage triggered. Rationale string for any fallback decision MUST end with the exact substring `"low confidence — fallback"` to satisfy ROADMAP Phase 1 success criterion #4 and provide a stable string for the unit test in `src/routing/tests/`.

### Routing Canary Eval
- **D-13: Distribution is balanced thirds plus a dedicated fallback bucket.** ~42 prompts total: ~12 OpenRouter / ~12 Claude Code / ~12 computer-use / ~6 should-be-fallback. Sits inside the 30–50 envelope from ROUTER-04 and gives each backend first-class coverage so per-backend P/R is statistically meaningful.
- **D-14: Sourcing is hand-written + a small license-checked adversarial slice from public sets.** Hand-written prompts anchored to the README golden-path examples and their variations. Adversarial slice: a few HumanEval-style code requests, MMLU-style factual questions, WebArena-style agentic-tool prompts. Every public-set row MUST be cited (source URL + license) before commit; rows from licenses that prohibit redistribution are paraphrased.
- **D-15: Four edge-case categories are guaranteed slots (~8 of the ~42 prompts).**
  - **Haiku-vs-code:** `"write a haiku about recursion"` (chat) vs `"write a Python function for fizzbuzz"` (chat → coding model). Tests that chat vs. code-request both stay on OpenRouter.
  - **Explain-vs-build:** `"explain how OAuth works"` (chat) vs `"build me a login flow with OAuth"` (Claude Code). Tests the imperative-verb signal.
  - **Informational-URL:** `"summarize https://example.com/article"` (chat — URL present but action is summarization) vs `"open https://example.com and click subscribe"` (computer-use — URL + action verb). Tests that `has_url` alone is not sufficient to trigger computer-use.
  - **Low-confidence trap:** gibberish, emoji-only, single-token prompts, multi-language prompts — must route to fallback. Tests the OOD path.
- **D-16: `python -m src.evaluation.evaluate_routing` prints the full metric stack.**
  - Overall backend-pick accuracy
  - Per-classifier reliability-diagram ECE for `task_type_classifier`, `agentic_intent_classifier`, `model_router` (matches success criterion #3)
  - Per-backend precision/recall table
  - Intended-vs-actual backend confusion matrix
  - `low_confidence_rate` (% of canary prompts that hit the fallback path)
  - Output CSVs go under `evaluation/routing/` so they live alongside the existing per-router metric CSVs

### Module & CLI Surface
- **D-17: `python -m src.routing.decide "<prompt>"` is a first-class CLI entry point** that prints a `RoutingDecision` JSON to stdout. Satisfies success criterion #1 directly. The existing `src/demo/demo_router.py` REPL is updated to call `decide()` internally rather than calling `predict_task_type` / `predict_best_model` directly — the in-tree CLI demo and the new module-level CLI share one code path.
- **D-18: `decide()` does NOT import FastAPI, httpx, requests, or any provider SDK.** Pure Python + sklearn + the saved joblib artifacts. Enforced by a smoke test that imports `src.routing.decide` and asserts neither `fastapi` nor `anthropic` nor `openai` shows up in `sys.modules` afterward.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner, executor) MUST read these before planning or implementing.**

### Phase Scope & Requirements
- `.planning/ROADMAP.md` §"Phase 1: Router Brain Foundation" — goal, dependencies, requirement mapping, 5 success criteria. Phase boundary is FIXED.
- `.planning/REQUIREMENTS.md` — read ROUTER-01 through ROUTER-07, OSS-01, SECURE-03 (the 9 requirements assigned to Phase 1). v2 ROUTER-V2-* items are explicitly deferred.
- `.planning/PROJECT.md` — Core Value ("quality first, cost as tiebreaker"), constraints (no fine-tuning, BYOK, single-process Python), and the "Active" requirement bullet list.

### Existing Codebase Maps (read before touching `src/`)
- `.planning/codebase/ARCHITECTURE.md` — pipeline diagram, layer responsibilities, anti-patterns (especially "Stage-2 text input format is duplicated by string concatenation" and "Path setup duplicated in every script" — the new `src/routing/` module is the chance to centralize).
- `.planning/codebase/STACK.md` — Python 3.10+, sklearn / pandas / scipy / joblib / sentence-transformers / nltk; no test framework configured (planner will need to add one or use plain unittest).
- `.planning/codebase/STRUCTURE.md` — module layout conventions, where `src/routing/` should live, `sys.path` injection patterns to avoid.
- `.planning/codebase/CONVENTIONS.md` — `snake_case` modules (except legacy `Feature_extractor.py`), saved-artifact dict shape, keyword-only args for boolean flags, sklearn metric reporting conventions.
- `.planning/codebase/INTEGRATIONS.md` — exact `config/model_mapping.json` schema, the 16 mapped slugs, and the `openrouter/auto` entry that becomes the fallback target.

### Source Code That Must Stay Compatible
- `src/feature_extraction/Feature_extractor.py` — `PromptFeatureExtractor.extract()` is the canonical feature contract; the new agentic-intent classifier extends it with 3–5 new fields; the existing classifiers' `joblib` artifacts already store the `feature_columns` list so adding columns requires retraining all three heads in lockstep.
- `src/task_classifier/build_question_type.py` — weak-label keyword groups are the data source for the new `unknown` task-type class (rows that match nothing become unknown training examples).
- `src/task_classifier/train_task_classifier_robust.py` — Stage-1 training pattern to extend with the `unknown` class and `CalibratedClassifierCV` wrapper.
- `src/model_router/train_model_router.py` — Stage-2 training pattern + 16-class artifact dict shape; calibrate without breaking artifact compatibility.
- `src/model_router_tier/train_tier_router.py` — alternate Stage-2 head; not used by `decide()` in v1 but the artifact must keep loading (CLI eval still references it).
- `src/demo/demo_router.py` — the file being updated to call `decide()`; `load_joblib_artifacts()` at line 35 is the canonical artifact-dict validator that the new `agentic_intent_classifier.joblib` must pass through unmodified.
- `config/model_mapping.json` — single source of truth for benchmark-slug → `api_model` resolution; the `OTHER` and `openrouter` entries are load-bearing for the fallback path.

### Data Files & Artifacts
- `data_processed/classifier_training_with_types.csv` — input to the extended task-type classifier training (the `unknown` class is added here).
- `data_processed/router_training_dataset_top_models.csv` — input to the model-router calibration retrain.
- `models/task_type_classifier.joblib`, `models/model_router.joblib`, `models/tier_router.joblib` — existing artifacts; calibrated versions overwrite in place (with a one-time pre-commit backup of the originals to `models/uncalibrated/` so the swap is reversible).
- New: `models/agentic_intent_classifier.joblib`, `data_processed/agentic_intent_training.csv`, `data_processed/routing_decision_eval.csv`.

### Open-Source / Distribution
- `ReadMe.md` — "Requirements" + "Running the Project" sections must be updated when `uv sync` replaces `pip install`. Limitations note ("simulates routing decisions") is no longer accurate once Phase 1 lands — the routing decision is real even if Phase 2's API call is not yet wired.
- `evaluation_summary.md` — existing baseline numbers; the routing eval extends, not replaces.
- No external ADRs exist in this repo; CONTEXT.md decisions D-01 through D-18 are the canonical "ADR" for Phase 1.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`PromptFeatureExtractor`** (`src/feature_extraction/Feature_extractor.py:30`) — single canonical text/numeric feature producer. New agentic features (D-08) extend this class; every classifier in the project reuses it via `extract(prompt) -> dict`.
- **Saved-artifact dict schema** — `{model, vectorizer, scaler, label_encoder, feature_columns, [target_column]}`. The new `agentic_intent_classifier.joblib` reuses this shape so `load_joblib_artifacts()` in `src/demo/demo_router.py:35` loads it without modification. Calibrated classifiers also reuse this shape: the calibrator replaces the `model` field; everything else is unchanged.
- **`build_question_type.py` keyword-group weak labeler** (`src/task_classifier/build_question_type.py:8`) — the rule-based dataset-to-`question_type` mapper. Rows that fail every keyword group become the `unknown` training class for the OOD sentinel (D-09).
- **`choose_final_route()`** (`src/demo/demo_router.py:245`) — already maps benchmark slug → `display_name/provider/tier/api_model`. Lift into `src/routing/` and reuse for D-02.
- **TF-IDF FeatureUnion stack** — `FeatureUnion([word_tfidf(1-2gram), char_tfidf(3-5gram)])` ⊕ scaled handcrafted numerics ⊕ `LogisticRegression(class_weight="balanced", solver="saga", C=2.0, max_iter=1500, n_jobs=-1)`. Reuse verbatim for the new agentic-intent head (D-08).
- **`config/model_mapping.json` `openrouter` entry** — `{api_model: "openrouter/auto", tier: "medium", openrouter_verified: true}` is the fallback target (D-11). Already present; no schema change required.

### Established Patterns
- **Path discovery via `__file__`** — every entry script computes `PROJECT_ROOT = os.path.abspath(os.path.join(__file__, "..", ".."))`. New `src/routing/` modules must follow the same depth pattern so the constant resolves correctly. ARCHITECTURE.md flags this duplication as an anti-pattern; planner may choose to centralize in `src/paths.py` as part of this phase or defer.
- **CLI mode toggle in training scripts** — training scripts prompt `train` / `load` via `input()`. Pipeline / data scripts use `argparse`. The new `src/evaluation/evaluate_routing.py` is a pipeline-style script → use `argparse`.
- **Module-style execution** — `python -m src.<package>.<module>` is the documented form; the new `python -m src.routing.decide "<prompt>"` (D-17) follows this.
- **Sklearn metric reporting** — every training script prints `accuracy_score`, `f1_score(average='macro')`, `f1_score(average='weighted')`, `classification_report` with `zero_division=0`. New routing evaluator (D-16) prints the same surface plus the routing-specific additions.
- **Persisting artifacts with `joblib.dump(dict, path)` + `joblib.load(path)` with required-key validation** — `load_joblib_artifacts()` raises `FileNotFoundError` with a "run X.py first" remediation hint and `KeyError` for missing required keys. New artifacts inherit this loader pattern.

### Integration Points
- `src/demo/demo_router.py:421` `main` — the REPL boot. After Phase 1, this calls `decide()` instead of `predict_task_type` + `predict_best_model` directly. The existing `route_prompt` (line 291) and `print_route_result` either move into `src/routing/` or call into it.
- `models/` directory — new artifact `agentic_intent_classifier.joblib` lands here alongside the three existing ones.
- `data_processed/` directory — new CSVs `agentic_intent_training.csv` and `routing_decision_eval.csv` land here alongside the existing per-stage training CSVs.
- `evaluation/` directory — new subdirectory `evaluation/routing/` for the new evaluator's CSVs and plots. Keeps the existing `evaluation/router_plots/`, `evaluation/model_router_plots/`, `evaluation/embedding_router_plots/` separation intact.
- `pyproject.toml` (new) at repo root — replaces the missing requirements lockfile (OSS-01). Pin existing transitive ranges captured from the local env; declare `[project.scripts] route-decide = "src.routing.decide:main"` as an optional convenience.
- `.gitignore` (new lines) — `.env`, `*.db`, `*.db-journal`, `*.db-wal`, `__pycache__/`, `.venv/`, `chat.db` (SECURE-03). First commit in this phase that touches key handling must include these.

### Anti-Patterns to AVOID (from ARCHITECTURE.md)
- Do NOT duplicate the Stage-2 text input format `"<origin_query> task_type_<qt> keyword_type_<kqt>"` in `src/routing/`. Lift into a shared helper (e.g., `src/feature_extraction/text_inputs.py`) and import from both training and `decide()`.
- Do NOT add another `sys.path.append(SRC_DIR)` site. Make `src/routing/` a proper package and use `from src.feature_extraction.Feature_extractor import PromptFeatureExtractor` after a `python -m` invocation.
- Do NOT rename `Feature_extractor.py` (camelCase legacy filename) without updating all four importers; or, if the planner chooses to rename it, do it as a dedicated atomic commit.
- Do NOT rename `src/model_router/build_top_model_datatset.py` (typo'd) inside this phase — it would churn the run-order docs in ReadMe.md without delivering Phase 1's goal.

</code_context>

<specifics>
## Specific Ideas

- The rationale string for any fallback decision MUST end with the EXACT substring `"low confidence — fallback"` (en-dash, lowercase). Phase 1 success criterion #4 unit test asserts this exact phrase.
- The OpenRouter fallback's `model_or_agent` is the literal string `"openrouter/auto"` — taken straight from `config/model_mapping.json` `openrouter` entry's `api_model` field.
- Claude Code backend sentinel: `"claude-agent-sdk"` (matches the SDK package name from BACKEND-04, NOT the deprecated `claude-code-sdk`).
- Computer-use backend sentinel: `"computer-use-2025-11-24"` (matches the beta header string from BACKEND-05).
- The four guaranteed canary edge cases (haiku-vs-code, explain-vs-build, informational-URL, low-confidence trap) are EACH represented by at least one prompt pair in the canary CSV. Eight slots minimum.
- Per-stage threshold defaults are constants in `src/routing/` (planner picks the file), overridable via `settings.task_type_tau`, `settings.agentic_intent_tau`, `settings.model_router_tau`.
- Canary CSV path: `data_processed/routing_decision_eval.csv`. Columns: `prompt`, `expected_backend`, `expected_model_or_agent_substring`, `is_fallback_expected`, `edge_case_category`, `source` (hand-written | humaneval | mmlu | webarena | other), `license` (mit | apache-2.0 | cc-by-sa | paraphrase-of-X).
- Backwards compatibility: every existing `joblib` artifact MUST still load with the demo's current `load_joblib_artifacts()` after calibration. Plan the calibration retrain so the new `model` field is a `CalibratedClassifierCV` instance, with the same `vectorizer/scaler/label_encoder/feature_columns` keys preserved verbatim.
- The smoke test for "no FastAPI in the import graph" (D-18) should also assert absence of `httpx`, `requests`, `aiohttp`, `anthropic`, `openai` — anything that would imply a live API call has leaked back into the brain layer.

</specifics>

<deferred>
## Deferred Ideas

These came up implicitly during discussion or are flagged by the codebase maps; downstream agents (researcher / planner) should treat them as out-of-scope for Phase 1 unless they re-surface as blockers.

- **Calibration method choice** (`sigmoid` Platt vs `isotonic`) and CV k-fold count — researcher recommends, planner pins. No user preference yet.
- **`src/routing/` module layout** — single `decide.py` vs `decide.py` + `policy.py` + `schema.py` + `config.py` — planner decides based on file size and testability.
- **`RoutingDecision` runtime form** — `@dataclass`, `TypedDict`, or `pydantic.BaseModel`. Default to stdlib `@dataclass` (no new deps) unless the planner has a reason. Pydantic doesn't arrive until Phase 3.
- **Path-constants centralization** (`src/paths.py`) — flagged as an anti-pattern in ARCHITECTURE.md. May land opportunistically inside Phase 1 if `src/routing/` would otherwise duplicate, but not required by any success criterion.
- **Rename `Feature_extractor.py` → `feature_extractor.py`** and `build_top_model_datatset.py` → `build_top_model_dataset.py` — flagged anti-patterns. Defer to a dedicated cleanup phase; renaming inside Phase 1 churns four importers without delivering routing value.
- **Pre-fetch SentenceTransformer + NLTK data in `make setup`** — OSS-02 territory; lands in Phase 6.
- **Logging redaction filter** (SECURE-01) — Phase 2 deliverable; the brain layer does no logging of keys.
- **Pre-commit hook blocking `sk-` / `sk-ant-`** (SECURE-02) — Phase 2 deliverable.
- **`models/uncalibrated/` backup directory** — a one-time safety copy of the three existing artifacts before the calibration retrain overwrites them. Planner decides whether to script this or do it manually.
- **v2 routing items** — per-stage confidence panel, model fallback chain, cross-backend handoff, live retraining loop. All in REQUIREMENTS.md v2 section.
- **Cost-aware target as a tiebreaker mechanism** — the existing `classifier_training_cost_aware.csv` pipeline is preserved as a baseline (PROJECT.md "Out of Scope" line). When `decide()` needs cost as a tiebreaker between two equal-quality OpenRouter models, look up the `tier` field in `config/model_mapping.json` rather than the cost-aware classifier output. Implementation detail for the planner.

</deferred>

---

*Phase: 1-router-brain-foundation*
*Context gathered: 2026-05-11*
