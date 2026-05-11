# Phase 1: Router Brain Foundation - Research

**Researched:** 2026-05-11
**Domain:** Calibrated multi-stage scikit-learn classifier composition behind a pure-function `decide()` API, packaged with `uv` for an open-source local CLI/SDK module — predecessor to FastAPI in Phase 3.
**Confidence:** HIGH for sklearn calibration, OOD strategy, `uv` migration, pytest, and CI; HIGH for the artifact-compatibility plan against the existing `joblib` shape; MEDIUM for the agentic-intent dataset assembly because positive examples are LLM-synthesized and require human spot-audit.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Backend Decision Policy**
- **D-01: Composition is a hard-coded rule cascade**, not a score blend.
  - `if agentic_intent == True AND (task_type in {coding, instruction-following} OR keyword in {build, write, edit, refactor, fix, implement, create}) -> backend="claude_code"`
  - `elif agentic_intent == True AND keyword in {open, browse, url, click, navigate, visit, fill, submit} -> backend="computer_use"`
  - `else -> backend="openrouter"`
- **D-02: Inside the OpenRouter branch, `model_or_agent` comes from the existing `model_router` prediction**, resolved via `config/model_mapping.json`. Unverified slugs fall through to `OTHER` → `openrouter/auto`. Reuses `choose_final_route` (`src/demo/demo_router.py:245`).
- **D-03: `RoutingDecision` carries BOTH a short human `rationale` AND a structured `signals` dict.**
- **D-04: `model_or_agent` is a concrete provider-ready string.**
  - OpenRouter → resolved `api_model` (e.g., `"openai/gpt-5"`, `"openrouter/auto"`).
  - Claude Code → fixed sentinel `"claude-agent-sdk"`.
  - Computer-use → fixed sentinel `"computer-use-2025-11-24"`.

**Agentic-Intent Classifier**
- **D-05: Positives are LLM-synthesized from ~30 hand-written seeds** (anchored to README golden-path examples), expanded to ~500.
- **D-06: Negatives are mined from LLMRouterBench non-tool-use rows.**
- **D-07: Target ~1,000 prompts, balanced 500 / 500.**
- **D-08: Feature stack matches existing classifiers (TF-IDF + handcrafted) PLUS 3–5 new agentic-specific handcrafted features:** `imperative_verb_count`, `has_url`, `has_file_path`, `has_code_fence`, `has_action_keyword`. Added to `PromptFeatureExtractor`. Saved artifact follows canonical dict shape `{model, vectorizer, scaler, label_encoder, feature_columns}`.

**Low-Confidence Fallback & OOD Policy**
- **D-09: OOD detection is belt-and-suspenders.** Literal `unknown` class trained on rows where `build_question_type.py` returns no keyword match, PLUS per-stage probability threshold at inference.
- **D-10: Per-stage thresholds in `settings`, defaults shipped in code:** `task_type_tau=0.35`, `agentic_intent_tau=0.55`, `model_router_tau=0.20`.
- **D-11: Fallback target is `openrouter/auto`** (already in `config/model_mapping.json`).
- **D-12: Fallback is ALWAYS the OpenRouter backend.** Rationale string MUST end with the EXACT substring `"low confidence — fallback"` (en-dash, lowercase).

**Routing Canary Eval**
- **D-13: Balanced thirds + dedicated fallback bucket** — ~42 prompts: ~12 OpenRouter / ~12 Claude Code / ~12 computer-use / ~6 fallback.
- **D-14: Hand-written + license-checked adversarial slice from public sets.** Every public-set row cited; non-redistributable rows paraphrased.
- **D-15: Four guaranteed edge-case categories** (~8 of 42): haiku-vs-code, explain-vs-build, informational-URL, low-confidence trap.
- **D-16: `python -m src.evaluation.evaluate_routing` prints the full metric stack** — overall backend-pick accuracy, per-classifier ECE, per-backend P/R, intended-vs-actual confusion matrix, `low_confidence_rate`. Outputs under `evaluation/routing/`.

**Module & CLI Surface**
- **D-17: `python -m src.routing.decide "<prompt>"` is a first-class CLI entry point** that prints `RoutingDecision` JSON to stdout. Existing `src/demo/demo_router.py` REPL is updated to call `decide()` internally.
- **D-18: `decide()` does NOT import FastAPI, httpx, requests, anthropic, openai.** Enforced by smoke test asserting absence in `sys.modules`.

### Claude's Discretion

- Calibration method (`sigmoid` vs `isotonic`) and CV k-fold count.
- `src/routing/` internal module layout (single file vs split into `decide.py` + `policy.py` + `schema.py` + `config.py`).
- `RoutingDecision` runtime form (`@dataclass` recommended; `TypedDict` or `pydantic.BaseModel` acceptable if justified).
- Whether to centralize path constants in `src/paths.py` opportunistically.
- Exact list of agentic / browse keywords for the rule cascade.
- Whether to script the `models/uncalibrated/` one-time backup or do it manually.
- Pre-commit / pytest scaffolding choices (no test framework exists today).

### Deferred Ideas (OUT OF SCOPE)

- File renames flagged as anti-patterns in ARCHITECTURE.md (`Feature_extractor.py`, `build_top_model_datatset.py`).
- Cost-aware classifier integration as a tiebreaker mechanism — preserved as a baseline only per PROJECT.md.
- Logging redaction filter, pre-commit hook for `sk-` prefixes — Phase 2 deliverables.
- `make setup` / NLTK + SentenceTransformer pre-fetch — Phase 6 deliverable.
- v2 router items (per-stage confidence UI panel, model fallback chain, cross-backend handoff, live retraining loop).
- HTTP/FastAPI/UI/database — Phase 3+ work.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ROUTER-01 | Trained binary `agentic_intent_classifier.joblib` distinguishes conversational from agentic prompts, persisted alongside existing classifiers | §"Standard Stack" + §"Pattern 3: Agentic-Intent Classifier (new head)" + §"Don't Hand-Roll" (use existing TF-IDF stack) |
| ROUTER-02 | Task-type classifier extended with OOD/unknown sentinel class that triggers safe-default route on low confidence | §"Pattern 2: OOD via dual signal" + §"Common Pitfalls — Pitfall 2" |
| ROUTER-03 | Existing classifiers wrapped in `CalibratedClassifierCV` so `predict_proba` is meaningful | §"Pattern 1: Calibration via FrozenEstimator" + §"State of the Art" (sklearn 1.6 deprecation) |
| ROUTER-04 | Hand-labeled routing canary eval set (30-50 real-chat prompts) measures backend-pick accuracy, distinct from LLMRouterBench split | §"Pattern 5: Canary eval CSV schema" + §"Validation Architecture" |
| ROUTER-05 | Pure-function `src/routing/decide(...) -> RoutingDecision` returns `{backend, model_or_agent, rationale, confidence}`, importable without FastAPI | §"Pattern 4: `decide()` API surface" + §"Architecture Patterns — System Architecture Diagram" |
| ROUTER-06 | Quality-first within budget — when multiple backends pass quality threshold, cost is the tiebreaker | §"Pattern 6: Quality-first cost tiebreaker" — implemented via `tier` lookup in `model_mapping.json`, NOT cost-aware classifier |
| ROUTER-07 | Existing CLI demo updated to call `src/routing/decide()`; regression check confirms no degradation on benchmark eval | §"Pattern 7: Demo integration + benchmark regression guard" |
| OSS-01 | Root `pyproject.toml` + `uv.lock` replace missing requirements lockfile; `uv sync` produces a working environment | §"Pattern 8: `uv` migration" + §"Standard Stack — Build & Packaging" |
| SECURE-03 | Root `.gitignore` excludes `.env`, `*.db`, `*.db-journal`, `*.db-wal`, `__pycache__/`, `.venv/`, `chat.db` from first commit that touches key handling | §"Security Domain" + §"Pattern 8" (gitignore template) |
</phase_requirements>

## Summary

Phase 1 is a **pure-Python** brownfield extension. Every concrete decision is already pinned by CONTEXT.md (D-01 through D-18); the research's job is to surface (a) the **scikit-learn 1.6+ change** that makes the obvious calibration approach (`CalibratedClassifierCV(base, cv="prefit")`) **deprecated** in favor of `FrozenEstimator`, (b) the exact compatibility plan so the existing `load_joblib_artifacts()` validator at `src/demo/demo_router.py:35` continues to work after the calibrated artifacts overwrite the uncalibrated ones, (c) a recommended `uv` migration with verified package versions, and (d) the validation architecture (pytest layout + CI workflow + canary CSV schema + ECE computation) that proves Success Criteria 1–5 are all TRUE before phase exit.

The most consequential technical finding: `cv="prefit"` was deprecated in sklearn 1.6 (released late 2024) — the canonical 2026 pattern is `CalibratedClassifierCV(FrozenEstimator(base_clf), method="sigmoid").fit(X_calib, y_calib)` on a held-out calibration split that is disjoint from the original training data. Plans that recommend `cv="prefit"` will trigger DeprecationWarnings and break in a future sklearn release. [VERIFIED: scikit-learn 1.8.0 docs] The existing `models/*.joblib` artifacts must be regenerated against the same train/test split that was used originally; calibration must use a fresh held-out slice that the original `LogisticRegression` never saw, otherwise calibration is biased optimistic.

The second-most consequential finding: **`uv` is NOT installed on the developer's machine** (verified by `which uv` → "uv not found") **and Python 3.10+ is also not installed** (system Python is 3.9.6). The plan must include an explicit `uv` install step and a Python toolchain step, otherwise the very first `uv sync` will fail before any Phase 1 code runs.

**Primary recommendation:** Build `src/routing/` as a small package (4 files: `__init__.py`, `schema.py`, `config.py`, `decide.py`) with a sibling `src/routing/tests/` directory; use `pytest 9.0+` with `conftest.py` that loads the joblib artifacts once per session via a fixture; calibrate with `FrozenEstimator + CalibratedClassifierCV(method="sigmoid", cv=5)`; compute ECE via a 16-line helper that wraps `sklearn.calibration.calibration_curve` (no new dependency); add `pyproject.toml` with explicit version pins captured from a working local `pip freeze` snapshot; ship a GitHub Actions workflow that runs `uv sync --locked --all-extras --dev && pytest -q && python -m src.evaluation.evaluate_routing --check`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Prompt feature extraction | Pure Python (`src/feature_extraction`) | — | Existing class; new agentic-intent fields extend it in place |
| Task-type classification (Stage 1) | Pure Python sklearn (`models/task_type_classifier.joblib`) | — | Existing artifact; calibrated in place, gains `unknown` class |
| Agentic-intent classification (new) | Pure Python sklearn (`models/agentic_intent_classifier.joblib`) | — | New artifact; same shape as existing |
| Model-class prediction (Stage 2) | Pure Python sklearn (`models/model_router.joblib`) | — | Existing artifact; calibrated in place |
| Backend-decision rule cascade | Pure Python (`src/routing/decide.py`) | — | Hard-coded rules per D-01; no ML |
| Backend → `model_or_agent` resolution | Pure Python + JSON config (`config/model_mapping.json`) | — | Existing mapping reused per D-02 |
| Canary evaluation | Pure Python pipeline script (`src/evaluation/evaluate_routing.py`) | — | argparse CLI; reads CSV; writes CSV/PNG |
| CLI entry point | Pure Python (`src/routing/decide.py:main` + `src/demo/demo_router.py`) | — | `python -m` invocations only; no HTTP |
| Build / packaging | Build tooling (`pyproject.toml` + `uv.lock`) | CI runtime (GitHub Actions) | Replaces missing lockfile per OSS-01 |
| Tests | Pure Python (`src/routing/tests/`) | CI runtime | pytest, no fixtures requiring network |
| Secret hygiene | `.gitignore` only in this phase | Phase 2 (redaction filter, pre-commit hook) | SECURE-03 is the gitignore line; SECURE-01/02/04 are deferred |

**Key insight:** Every responsibility for Phase 1 lives in **a single tier** (Pure Python, in-process). No HTTP, no DB, no UI, no async. The "Architectural Responsibility Map" exists primarily to make explicit that the FastAPI / SQLite / Next.js columns are intentionally empty in this phase. Mis-assignments to those tiers (e.g., "let's just stand up a thin FastAPI wrapper for the eval script") are scope creep and must be rejected by the planner.

## Standard Stack

### Core (already installed; preserve compatibility)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | **3.11** target (min 3.10) | Runtime | CLAUDE.md mandates 3.10+; `dict \| None` syntax is in use; 3.11 is the conservative production choice in 2026 [VERIFIED: project STACK.md] |
| scikit-learn | **1.7.x** | LogisticRegression, TF-IDF, CalibratedClassifierCV, FrozenEstimator, calibration_curve | Existing classifiers; `FrozenEstimator` is the post-1.6 calibration pattern [VERIFIED: scikit-learn 1.8.0 docs] |
| pandas | latest 2.x | DataFrame I/O | Used everywhere [VERIFIED: existing imports] |
| scipy | latest 1.x | `sparse.hstack`, `csr_matrix` | Canonical sparse-stack TF-IDF + handcrafted feature combiner [VERIFIED: CLAUDE.md "How scikit-learn / pandas / numpy Are Used"] |
| joblib | latest | `dump` / `load` artifact dicts | Existing `models/*.joblib` shape [VERIFIED: `src/demo/demo_router.py:46`] |
| matplotlib | latest 3.x | Reliability diagram + confusion-matrix plots | Existing pattern; `dpi=300`, `tight_layout`, `close` [VERIFIED: CLAUDE.md "Model Training Patterns"] |
| nltk | latest 3.9+ | `sent_tokenize` via `punkt_tab` | Existing `_ensure_nltk_sentence_tokenizer` global [VERIFIED: `src/feature_extraction/Feature_extractor.py:11`] |

### New (added by Phase 1)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| **uv** | **0.5+** (latest 2026 release recommended) | Python package + project manager; replaces `pip` from ReadMe.md | "10–100× faster than pip"; canonical lockfile in 2026; `setup-uv` GitHub Action is the documented CI path [CITED: docs.astral.sh/uv/guides/integration/github] |
| **pytest** | **9.0.x** (current latest 9.0.3, 2026-04-07) | Test framework; `src/routing/tests/` and `src/evaluation/tests/` | No test framework today; pytest is the unanimous community default; v9 requires Python 3.10+ which we already require [VERIFIED: PyPI 9.0.3 release date 2026-04-07] |
| **pytest-cov** | latest | Optional coverage reporting | Common pairing; nice-to-have for CI summary [CITED: PyPI pytest-cov] |

### Supporting (use only if needed; preferred is to avoid)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `netcal` | latest 1.x | Pre-built ECE/MCE/ACE + reliability-regression diagram | ONLY if planner concludes a 16-line custom ECE helper isn't enough; adds a dependency for a small surface area. Recommended NOT to add — see "Don't Hand-Roll" below for inverted reasoning [CITED: PyPI netcal] |
| `python-dotenv` | latest | Read `.env` for future BYOK keys | NOT in Phase 1 — `.env` keys are Phase 2/4. Mentioned only because `.gitignore` excludes `.env` per SECURE-03; the file itself doesn't exist yet |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `CalibratedClassifierCV` with `FrozenEstimator` | Train calibration head separately (Platt sigmoid by hand) | Custom code is ~30 lines but easy to get wrong on multiclass; sklearn handles One-vs-Rest internally [CITED: sklearn 1.16. Probability calibration] |
| `pytest` | `unittest` (stdlib, no new dep) | `unittest` is acceptable but pytest is dramatically less ceremony for fixtures; the project will grow a fuller test suite in Phase 2+, so pay the dep cost now [ASSUMED] |
| `uv` | `pip-tools` (pip-compile) or `poetry` | uv is faster, single-binary, has `setup-uv` GitHub Action, and is the current de-facto standard [CITED: docs.astral.sh/uv] |
| `dataclass` for `RoutingDecision` | `TypedDict` or `pydantic.BaseModel` | Stdlib `dataclass` adds no dep; pydantic doesn't arrive until Phase 3; `TypedDict` lacks runtime validation. CONTEXT.md `<deferred>` recommends dataclass — concur. [VERIFIED: CONTEXT.md] |
| Custom ECE | `netcal.confidence.ECE` | Custom 16-line helper has zero new deps and matches the project's "don't add libraries for one function" pattern; netcal is overkill [CITED: GitHub scikit-learn issue #18268 confirms sklearn intentionally does NOT ship ECE] |

### Installation (proposed `pyproject.toml` skeleton)

```toml
[project]
name = "prompt-optimizer"
version = "0.1.0"
description = "Quality-first prompt router with calibrated classifiers"
readme = "ReadMe.md"
requires-python = ">=3.10"
license = { text = "MIT" }
dependencies = [
  "scikit-learn>=1.7,<2.0",
  "pandas>=2.0,<3.0",
  "numpy>=1.26,<3.0",
  "scipy>=1.11,<2.0",
  "joblib>=1.4,<2.0",
  "matplotlib>=3.8,<4.0",
  "nltk>=3.9,<4.0",
  "sentence-transformers>=3.0,<4.0",  # existing embedding router
]

[project.optional-dependencies]
dev = [
  "pytest>=9.0,<10.0",
  "pytest-cov>=5.0,<7.0",
]

[project.scripts]
route-decide = "src.routing.decide:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src"]
```

**Version verification:** Each version range above was set as the latest stable major minus the previous one. The planner MUST run `npm view`-equivalent for Python (`pip index versions <pkg>` or `uv pip compile`) at plan-execution time and snap the lower bound to whatever the developer's local environment actually has installed, then commit `uv.lock`. Training-data versions (e.g., `scikit-learn 1.7`) may be months stale by execution time.

[ASSUMED] hatchling as build backend (vs. `uv_build` or `setuptools`). Defensible defaults: hatchling is lightweight, fully PEP 621 compliant, the most-recommended for new projects, and works with `pip install -e .` for editing existing scripts. [CITED: medium.com Python Build Backends in 2025]

## Architecture Patterns

### System Architecture Diagram

```
                       ┌──────────────────────────────────┐
                       │  USER INPUT (one of two paths)   │
                       │  - python -m src.routing.decide  │
                       │    "<prompt>"                    │
                       │  - python src/demo/demo_router.py│
                       │    (REPL, calls decide())        │
                       └─────────────────┬────────────────┘
                                         │ prompt: str
                                         │ history: list (optional, ignored in v1)
                                         │ artifacts: dict[str, joblib_dict]
                                         │ settings: dict (taus, fallback model)
                                         ▼
              ┌──────────────────────────────────────────────────┐
              │              src/routing/decide.py               │
              │              (PURE FUNCTION, no HTTP)            │
              │                                                  │
              │  1. PromptFeatureExtractor.extract(prompt)       │
              │     ↓ (numeric feature dict + raw text)          │
              │                                                  │
              │  2. task_type_classifier.predict_proba(features) │
              │     ↓ (label, confidence, full probability vec)  │
              │     ↓                                            │
              │     IF max_prob < settings.task_type_tau          │
              │     OR predicted_label == "unknown"              │
              │     ↓ → fallback path (skip remaining stages)    │
              │                                                  │
              │  3. agentic_intent_classifier.predict_proba(features) │
              │     ↓ (P(agentic), P(conversational))            │
              │     IF max_prob < settings.agentic_intent_tau     │
              │     ↓ → fallback path                            │
              │                                                  │
              │  4. RULE CASCADE (D-01)                          │
              │     IF agentic AND (task in {coding,instruction} │
              │     OR keyword in BUILD_KEYWORDS)                │
              │     ↓ backend = "claude_code"                    │
              │     model_or_agent = "claude-agent-sdk"          │
              │                                                  │
              │     ELIF agentic AND keyword in BROWSE_KEYWORDS  │
              │     ↓ backend = "computer_use"                   │
              │     model_or_agent = "computer-use-2025-11-24"   │
              │                                                  │
              │     ELSE                                         │
              │     ↓ backend = "openrouter"                     │
              │     5. model_router.predict_proba(features)      │
              │        ↓ (predicted_slug, confidence)            │
              │        IF max_prob < settings.model_router_tau    │
              │        ↓ → fallback                              │
              │        ELSE: model_or_agent =                    │
              │           model_mapping[slug].api_model          │
              │           (or "openrouter/auto" via OTHER)       │
              │                                                  │
              │  6. Build RoutingDecision (dataclass)            │
              │     - backend                                    │
              │     - model_or_agent                             │
              │     - rationale (str)                            │
              │     - confidence (float; min of stage confs)     │
              │     - signals (dict)                             │
              │                                                  │
              │  Fallback path (any stage triggered):            │
              │     backend = "openrouter"                       │
              │     model_or_agent = "openrouter/auto"           │
              │     rationale ends in "low confidence — fallback"│
              └─────────────────┬────────────────────────────────┘
                                │ RoutingDecision
                                ▼
                       ┌────────────────────────┐
                       │  CALLER (CLI prints    │
                       │  JSON; demo prints     │
                       │  pretty; future        │
                       │  FastAPI dispatches    │
                       │  to backend adapter)   │
                       └────────────────────────┘

OFFLINE EVAL PATH (decoupled, runs the same decide() against canary CSV):

  data_processed/routing_decision_eval.csv
    │ (prompt, expected_backend, ...)
    ▼
  src/evaluation/evaluate_routing.py
    │ for row in csv:
    │   actual = decide(row.prompt, ...)
    │   compare actual.backend vs expected_backend
    │   collect probabilities for ECE per stage
    ▼
  evaluation/routing/*.csv + *.png
    - backend_accuracy.csv
    - per_backend_pr.csv
    - confusion_matrix.csv + .png
    - ece_per_stage.csv
    - low_confidence_rate.txt
    - reliability_diagram_{stage}.png  (one per calibrated classifier)
```

### Recommended Project Structure

```
src/
├── routing/                              # NEW package — Phase 1 deliverable
│   ├── __init__.py                       # exports decide, RoutingDecision
│   ├── schema.py                         # @dataclass RoutingDecision; type aliases
│   ├── config.py                         # default thresholds, fallback constants, keyword lists
│   ├── decide.py                         # decide() pure function + main() CLI entry
│   ├── policy.py                         # rule cascade helper (D-01); kept separate for testability
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py                   # session-scope fixture loading joblib artifacts
│       ├── test_decide_smoke.py          # pure-import smoke test (D-18)
│       ├── test_fallback.py              # asserts "low confidence — fallback" rationale (success #4)
│       ├── test_rule_cascade.py          # exhaustive policy.py branch coverage
│       └── test_artifact_compat.py       # asserts existing joblib loads still work post-calibration
│
├── feature_extraction/
│   ├── Feature_extractor.py              # EXTENDED: +5 agentic-intent features
│   └── text_inputs.py                    # NEW (planner discretion): centralizes the
│                                         #   "<query> task_type_X keyword_type_Y" format
│
├── task_classifier/
│   ├── train_task_classifier_robust.py   # EXTENDED: adds "unknown" class + Calibrated wrapper
│   └── build_question_type.py            # MODIFIED: emits "unknown" for unmatched rows
│
├── agentic_intent/                       # NEW package — Phase 1 deliverable
│   ├── __init__.py
│   ├── build_seeds.py                    # ~30 hand-written agentic seeds + manual review
│   ├── synthesize_dataset.py             # offline LLM-call OR document-only step;
│   │                                     #   produces data_processed/agentic_intent_training.csv
│   ├── mine_negatives.py                 # filter LLMRouterBench non-tool-use rows
│   └── train_agentic_intent.py           # mirrors train_task_classifier_robust.py shape
│
├── model_router/
│   └── train_model_router.py             # EXTENDED: Calibrated wrapper added; artifact dict unchanged
│
├── evaluation/
│   ├── evaluate_routing.py               # NEW — D-16 metric stack
│   └── tests/
│       └── test_evaluate_routing.py      # asserts script runs end-to-end on a tiny canary
│
└── demo/
    └── demo_router.py                    # EXTENDED: route_prompt() now calls decide()

data_processed/
├── agentic_intent_training.csv           # NEW — 1,000 rows, balanced
├── routing_decision_eval.csv             # NEW — ~42 hand-labeled canary
└── classifier_training_with_types.csv    # MODIFIED: "unknown" rows added

models/
├── task_type_classifier.joblib           # OVERWRITTEN — calibrated, +unknown class
├── model_router.joblib                   # OVERWRITTEN — calibrated
├── tier_router.joblib                    # UNCHANGED (not used by decide() in v1)
├── embedding_router.joblib               # UNCHANGED
├── agentic_intent_classifier.joblib      # NEW
└── uncalibrated/                         # NEW backup directory (one-time)
    ├── task_type_classifier.joblib
    └── model_router.joblib

evaluation/
└── routing/                              # NEW subdirectory for canary outputs
    ├── backend_accuracy.csv
    ├── per_backend_pr.csv
    ├── confusion_matrix.csv
    ├── confusion_matrix.png
    ├── ece_per_stage.csv
    ├── low_confidence_rate.txt
    └── reliability_diagram_{stage}.png   # one per calibrated head

(repo root)
├── pyproject.toml                        # NEW — OSS-01
├── uv.lock                               # NEW — committed; regenerated by uv sync
├── .gitignore                            # NEW or EXTENDED — SECURE-03
├── .github/
│   └── workflows/
│       └── ci.yml                        # NEW — runs uv sync + pytest + evaluate_routing
└── ReadMe.md                             # MODIFIED — pip → uv
```

### Pattern 1: Calibration via FrozenEstimator (sklearn 1.6+)

**What:** Wrap an already-fitted classifier in `FrozenEstimator`, then pass to `CalibratedClassifierCV` with a held-out calibration split.

**When to use:** ALL three classifiers in this phase. The existing `task_type_classifier.joblib` and `model_router.joblib` were trained on the full `data_processed/*.csv` files — calibration must use a fresh held-out slice that the original `LogisticRegression` never saw.

**Why this pattern (not the obvious one):** `cv="prefit"` is **deprecated as of scikit-learn 1.6** (released 2024). Plans that still recommend `CalibratedClassifierCV(base, cv="prefit")` will work today but emit DeprecationWarning and break in a future release. [VERIFIED: scikit-learn 1.8.0 CalibratedClassifierCV docs]

**Example:**

```python
# Source: https://scikit-learn.org/stable/auto_examples/frozen/plot_frozen_examples.html
# Source: https://scikit-learn.org/stable/modules/generated/sklearn.calibration.CalibratedClassifierCV.html

from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.model_selection import train_test_split
import joblib

# 1. Load existing artifact (artifact["model"] is the trained LogisticRegression)
artifacts = joblib.load("models/task_type_classifier.joblib")
base_clf = artifacts["model"]

# 2. Re-prepare the SAME train split that produced base_clf, then carve a calibration slice
#    from what was previously the training data. The existing held-out test set MUST stay
#    held-out for downstream metric reporting — do NOT calibrate on it.
X_train_combined, y_train = ...  # rebuild via the existing pipeline (TF-IDF + handcrafted)
X_train_only, X_calib, y_train_only, y_calib = train_test_split(
    X_train_combined, y_train,
    test_size=0.2, random_state=42, stratify=y_train,
)
# (Note: the original base_clf was fit on the full X_train_combined; that's fine because
#  FrozenEstimator means we are NOT refitting it. We only need the calibration slice.)

# 3. Wrap in FrozenEstimator + CalibratedClassifierCV
calibrated = CalibratedClassifierCV(
    FrozenEstimator(base_clf),
    method="sigmoid",  # Platt scaling — appropriate for LogisticRegression with sufficient data
    # cv parameter is ignored when wrapping FrozenEstimator (auto-detected since 1.6)
)
calibrated.fit(X_calib, y_calib)

# 4. Replace ONLY the "model" field; preserve all other keys verbatim
artifacts["model"] = calibrated
joblib.dump(artifacts, "models/task_type_classifier.joblib")

# 5. The existing load_joblib_artifacts() validator at src/demo/demo_router.py:35 still passes
#    because it checks for "model" / "vectorizer" / "scaler" / "label_encoder" / "feature_columns"
#    — all of which are still present.
```

**Calibration method choice (Claude's discretion):**

| Method | When | Tradeoff |
|--------|------|----------|
| `method="sigmoid"` (Platt) | LogisticRegression already produces near-Platt-shape probabilities; small N (1k–10k); 2-class or balanced multiclass | Simpler, less prone to overfitting; default recommendation |
| `method="isotonic"` | Larger N (>10k); strongly miscalibrated base; multiclass with imbalance | More flexible but needs more calibration data; can overfit small slices [CITED: sklearn calibration docs] |

**Recommendation:** `method="sigmoid"` for all three classifiers. The existing training datasets are in the low-thousands range; isotonic risks overfitting on the calibration slice. If post-eval ECE on a stage exceeds 0.10, the planner can switch THAT stage to isotonic in a follow-up commit.

### Pattern 2: OOD via dual signal (D-09)

**What:** Two independent signals trigger the fallback path:
1. **Literal `unknown` class** in the task-type classifier's `LabelEncoder`. Trained on rows where `build_question_type.py` returns no keyword match (currently those rows get bucketed into `"general"` — the trick is to add a new `"unknown"` return path for *truly* unmatched dataset names AND emit it at training time).
2. **Per-stage probability threshold** at inference: `max(predict_proba) < tau` for any of the three stages → fallback regardless of which class won.

**Why two signals:** Each catches a failure mode the other misses.
- The `unknown` class catches OOD prompts whose features look like the synthetic OOD training distribution (very short, emoji-only, gibberish, multi-language).
- The probability threshold catches the case where the prompt is "kind of like" multiple in-distribution classes — the classifier confidently predicts the wrong one because no class is dominant. MSP (Maximum Softmax Probability) is the established baseline for this. [CITED: arxiv.org/pdf/1610.02136 "A Baseline for Detecting Misclassified and Out-of-Distribution Examples"]

**OOD method considered and rejected:**

| Method | Why not in Phase 1 |
|--------|---------------------|
| Mahalanobis distance on embeddings | Strongest in literature [CITED: Springer Discover Data 2025], but requires a separate embedding pipeline (already exists for embedding_router) AND covariance estimation per class. Adds complexity for marginal gain over MSP+unknown for v1. Defer to v2. |
| Energy score | Best for deep nets; LogisticRegression's logits aren't sharp enough to benefit. |
| OECC (Outlier Exposure with Confidence Control) | Requires an explicit outlier-exposure dataset; we don't have one. The `unknown` class is a poor-man's outlier exposure that reuses what's already in `build_question_type.py`. |

**Threshold defaults (from CONTEXT.md D-10, copied verbatim into `src/routing/config.py`):**

```python
# Source: CONTEXT.md D-10 (locked decision)
DEFAULT_TASK_TYPE_TAU = 0.35       # 10 task-type classes; broad bins
DEFAULT_AGENTIC_INTENT_TAU = 0.55  # binary head; expect crisp probabilities
DEFAULT_MODEL_ROUTER_TAU = 0.20    # 16 model classes; lower max-prob floor by design
```

These thresholds are reasonable initial values but [ASSUMED] until empirically validated against the canary CSV. The plan MUST include a "tune thresholds" task that runs `evaluate_routing.py` against the canary, prints reliability diagrams + low-confidence rate per stage, and adjusts taus if the low-confidence rate is wildly off-target (>30% → too aggressive, <5% → too lax).

### Pattern 3: Agentic-Intent Classifier (new head)

**What:** Binary `LogisticRegression` (agentic vs. conversational) using the existing TF-IDF + handcrafted feature stack PLUS 5 new features.

**Feature additions to `PromptFeatureExtractor` (D-08):**

```python
# New helper method on PromptFeatureExtractor
def _agentic_features(self, text: str) -> dict:
    text_lower = text.lower()

    # Imperative verbs at sentence start (rough heuristic — first word of each sentence)
    imperative_verbs = {
        "build", "make", "create", "write", "edit", "refactor", "fix",
        "implement", "add", "remove", "delete", "update", "rewrite",
        "open", "browse", "click", "navigate", "visit", "fill", "submit",
        "scrape", "fetch", "download", "install", "run",
    }
    sentences = sent_tokenize(text)
    imperative_count = sum(
        1 for s in sentences
        if s.strip().split() and s.strip().split()[0].lower() in imperative_verbs
    )

    # Surface signals
    has_url = 1 if re.search(r"https?://\S+", text) else 0
    has_file_path = 1 if re.search(r"(/\S+)+|\\\\?[A-Za-z]:\\\\", text) else 0
    has_code_fence = 1 if "```" in text else 0
    has_action_keyword = 1 if any(
        kw in text_lower
        for kw in ("build", "open", "scrape", "fill", "click", "edit", "refactor")
    ) else 0

    return {
        "imperative_verb_count": imperative_count,
        "has_url": has_url,
        "has_file_path": has_file_path,
        "has_code_fence": has_code_fence,
        "has_action_keyword": has_action_keyword,
    }
```

**Critical compatibility note:** Adding fields to `PromptFeatureExtractor.extract()` changes the dict shape returned. The existing `task_type_classifier.joblib` and `model_router.joblib` artifacts each store a `feature_columns` list that defines exactly which columns they were trained on. After feature addition:

1. The new agentic-intent classifier trains on the FULL extended feature set (its `feature_columns` includes the 5 new fields).
2. The existing classifiers continue to work because their `feature_columns` lists do NOT include the new fields, and `build_numeric_features()` at `src/demo/demo_router.py:101` already trims `feature_df` to `feature_df[feature_columns]` — so the extra columns are silently dropped during inference. [VERIFIED: `src/demo/demo_router.py:101-105`]
3. **However**, when the existing classifiers are RETRAINED for calibration (Pattern 1), they will now see the new features in their training input. Two options:
   - **Option A (recommended):** Re-train task_type and model_router on the EXTENDED feature set, accept that `feature_columns` grows by 5. Better long-term.
   - **Option B (faster):** Keep training input unchanged for the existing two; only the new agentic-intent classifier sees the new features. The new fields then become "agentic-intent only" features.

Recommendation: **Option A**. The 5 new features are general-purpose enough that the task-type and model-router heads might benefit from them, and consolidating on one feature shape avoids future divergence.

**Training data assembly (D-05, D-06, D-07):**

```
Step 1: Hand-write seed prompts (researcher/planner)
  ~30 high-quality agentic prompts anchored to README golden-path examples.
  Cover the three backends in roughly equal proportion:
    - 10 build/edit prompts → Claude Code intent
    - 10 browse/click prompts → computer-use intent
    - 10 multi-step prompts → either, but clearly agentic
  Save to: data_processed/agentic_intent_seeds.csv (committed to git)

Step 2: LLM expansion (offline, one-time, manual)
  Prompt a strong LLM (e.g., GPT-5 or Claude Opus 4.7 via OpenRouter from a personal key
  OUTSIDE this codebase — there is no live LLM call in the routing brain) to generate
  ~470 paraphrastic variations covering verb diversity, length range (5-tok to 200-tok),
  multi-step phrasings, and domain spread.
  Save to: data_processed/agentic_intent_synthesized.csv (committed to git)

  [ASSUMED] The "offline LLM" step is a one-time manual operation by the developer
  using their own API key, not a runtime dependency. The CSV is committed; the
  generation script logs the prompt template used so others can regenerate.

Step 3: Hand-audit
  Researcher reviews 100% of synthesized rows; deletes off-topic / mislabeled.
  Drop count expected: 5-15% per Anthropic synthetic-data norms [ASSUMED].

Step 4: Mine 500 negatives from LLMRouterBench (D-06)
  Filter data_processed/flat_records.csv (already in pipeline) for:
    - dataset NOT in {tau2, tau, tool, agent, humaneval, livecodebench, mbpp, swe-bench}
    - AND dataset IN {gsm8k, math, mmlu, mmlu_pro, simpleqa, arenahard_creative_writing, ...}
  Sample 500 with stratification across remaining datasets to avoid math-only bias.
  Save: data_processed/agentic_intent_negatives.csv

Step 5: Concatenate, shuffle, save
  data_processed/agentic_intent_training.csv with columns:
    text, label (agentic|conversational), source (seed|synthesized|llmbench), dataset
```

**Training script shape (mirrors `train_task_classifier_robust.py`):**

The new `src/agentic_intent/train_agentic_intent.py` follows the canonical pattern:
- Load CSV, build TF-IDF FeatureUnion (`word(1,2)` + `char_wb(3,5)`)
- Build numeric features via extended `PromptFeatureExtractor`
- `StandardScaler` on numeric, `csr_matrix`, `hstack` with TF-IDF
- `LabelEncoder` on `label` column → 0/1
- `train_test_split(test_size=0.2, random_state=42, stratify=y)`
- `LogisticRegression(max_iter=1500, class_weight="balanced", solver="saga", C=2.0, n_jobs=-1)`
- Wrap in `CalibratedClassifierCV(FrozenEstimator(lr), method="sigmoid")` after fit on a 60/20/20 split (60 train / 20 calibrate / 20 test) [VERIFIED: pattern in train_task_classifier_robust.py extended with calibration step]
- Save `joblib.dump({"model": calibrated, "vectorizer": fu, "scaler": ss, "label_encoder": le, "feature_columns": cols}, "models/agentic_intent_classifier.joblib")`
- Print precision/recall/F1 per class (success criterion #2)

### Pattern 4: `decide()` API surface (D-17, D-18)

**Signature (locked by ROUTER-05):**

```python
# src/routing/schema.py

from dataclasses import dataclass, field, asdict
from typing import Literal, Any
import json

Backend = Literal["openrouter", "claude_code", "computer_use"]

@dataclass(frozen=True)
class RoutingDecision:
    backend: Backend
    model_or_agent: str        # "openai/gpt-5", "claude-agent-sdk", "computer-use-2025-11-24", or "openrouter/auto"
    rationale: str             # one-line; ends in "low confidence — fallback" if fallback fired
    confidence: float          # min of stage confidences; in [0.0, 1.0]
    signals: dict[str, Any] = field(default_factory=dict)  # structured per D-03

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


# src/routing/decide.py

def decide(
    prompt: str,
    history: list | None = None,           # ignored in v1; reserved for v2 multi-turn context
    artifacts: dict | None = None,         # if None, load default artifacts from models/
    settings: dict | None = None,          # if None, use defaults from src/routing/config.py
) -> RoutingDecision:
    """Pure-function routing brain. No HTTP, no provider SDKs, no I/O beyond joblib loads."""
    ...

def main() -> None:
    """CLI entry point: python -m src.routing.decide '<prompt>'."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt")
    args = parser.parse_args()
    decision = decide(args.prompt)
    print(decision.to_json())
```

**Forbidden imports (D-18, enforced by smoke test):**

```python
# src/routing/tests/test_decide_smoke.py
import sys

def test_no_forbidden_modules_imported_after_decide():
    # Pre-clear known offenders if any caller already imported them
    forbidden = {"fastapi", "httpx", "requests", "aiohttp", "anthropic", "openai"}
    for name in list(sys.modules):
        if name.split(".")[0] in forbidden:
            del sys.modules[name]

    # Importing the routing module should not pull in any HTTP/SDK
    import src.routing.decide  # noqa: F401

    leaked = {name.split(".")[0] for name in sys.modules} & forbidden
    assert not leaked, f"src.routing.decide leaked imports: {sorted(leaked)}"
```

### Pattern 5: Canary eval CSV schema (D-13, D-14, D-15)

**Path:** `data_processed/routing_decision_eval.csv` (committed to git)

**Columns (per CONTEXT.md `<specifics>`):**

| Column | Type | Notes |
|--------|------|-------|
| `prompt` | str | The text fed to `decide()` |
| `expected_backend` | str | One of `openrouter`, `claude_code`, `computer_use`, `fallback` (sentinel — actual fallback prompts have `expected_backend = "openrouter"` AND `is_fallback_expected = true`) |
| `expected_model_or_agent_substring` | str | E.g., `"openrouter/auto"` for fallback rows; allows partial match because real prediction may shift between minor model versions |
| `is_fallback_expected` | bool | TRUE for the ~6 low-confidence-trap rows |
| `edge_case_category` | str | One of `haiku-vs-code`, `explain-vs-build`, `informational-url`, `low-confidence-trap`, `golden-path`, or `""` |
| `source` | str | `hand-written`, `humaneval`, `mmlu`, `webarena`, or `paraphrase-of-X` |
| `license` | str | `mit`, `apache-2.0`, `cc-by-sa`, or `paraphrase-of-X` (for non-redistributable origins) |

**Distribution target (D-13):** ~12 OpenRouter / ~12 Claude Code / ~12 computer-use / ~6 fallback = ~42 prompts.

**Edge-case slot allocation (D-15, ≥8 of the ~42):**

```
Haiku-vs-code (2 prompts):
  - "write a haiku about recursion"           → openrouter (creative)
  - "write a Python function for fizzbuzz"     → openrouter (chat coding model, NOT claude_code)

Explain-vs-build (2 prompts):
  - "explain how OAuth works"                  → openrouter (chat)
  - "build me a login flow with OAuth"         → claude_code (imperative + agentic)

Informational-URL (2 prompts):
  - "summarize https://example.com/article"     → openrouter (URL but action is summarize)
  - "open https://example.com and click subscribe" → computer_use (URL + action verb)

Low-confidence trap (2+ prompts):
  - "🌶️🌶️🌶️"                                   → fallback (emoji-only)
  - "asdfgh"                                    → fallback (gibberish)
  - "yes"                                       → fallback (single token)
  - (planner may add a multi-language one if budget allows)
```

The remaining ~34 rows fill the three backend buckets with realistic golden-path-style prompts plus license-checked snippets from HumanEval / MMLU / WebArena (cited and license-tagged in the `source` and `license` columns).

### Pattern 6: Quality-first cost tiebreaker (ROUTER-06)

**What:** When the rule cascade lands in the OpenRouter branch and the model_router predicts a slug, apply quality-first selection. Cost is consulted ONLY as a tiebreaker when two predictions are within an epsilon of each other on confidence.

**Where the cost signal lives:** `config/model_mapping.json[<slug>]["tier"]` — `cheap` < `medium` < `strong`. The cost-aware classifier from CONTEXT.md `<deferred>` is NOT used.

**Implementation sketch:**

```python
# src/routing/policy.py

TIER_RANK = {"cheap": 0, "medium": 1, "strong": 2}

def quality_first_pick(top_k_predictions, model_mapping, epsilon: float = 0.02):
    """Among top-K model_router predictions, return the cheapest tier
    whose probability is within `epsilon` of the top probability.
    Quality first: top probability dominates. Cost tiebreaker: cheapest tier wins ties."""
    top_prob = top_k_predictions[0][1]
    contenders = [(slug, prob) for slug, prob in top_k_predictions if top_prob - prob <= epsilon]
    if len(contenders) == 1:
        return contenders[0][0]
    # tiebreaker: cheapest tier
    return min(
        contenders,
        key=lambda sp: TIER_RANK.get(model_mapping.get(sp[0], {}).get("tier", "medium"), 1),
    )[0]
```

[ASSUMED] `epsilon = 0.02`. The planner may tune this based on the canary's `low_confidence_rate` and per-backend P/R. A sensible alternative is to use the model_router's own ECE-bin width.

### Pattern 7: Demo integration + benchmark regression guard (ROUTER-07)

**What:** `src/demo/demo_router.py` is updated so its `route_prompt()` becomes a thin wrapper over `src.routing.decide()`. The existing benchmark eval (`src/evaluation/evaluate_baselines.py`) continues to work and produces the same baseline numbers as before (within tolerance).

**Update sketch (`src/demo/demo_router.py`):**

```python
# Before (current, lines 291-341): two-stage pipeline inside route_prompt()
# After:

from src.routing.decide import decide
from src.routing.schema import RoutingDecision

def route_prompt(prompt, task_artifacts, model_router_artifacts, model_mapping, extractor):
    """Thin wrapper: delegates to src.routing.decide so the demo and the SDK share one path."""
    decision: RoutingDecision = decide(
        prompt=prompt,
        artifacts={
            "task_type_classifier": task_artifacts,
            "model_router": model_router_artifacts,
            "agentic_intent_classifier": load_joblib_artifacts(
                AGENTIC_INTENT_PATH, "agentic_intent_classifier.joblib"
            ),
            "model_mapping": model_mapping,
        },
    )
    # Adapt RoutingDecision back to the demo's existing dict shape so print_route_result
    # can stay unchanged for backwards compatibility.
    return _decision_to_legacy_dict(decision)
```

**Regression guard:**

The existing `src/evaluation/evaluate_baselines.py` and the per-router metric CSVs in `evaluation/` represent baseline numbers. After calibration:
- `task_type_classifier.joblib` post-calibration accuracy on its held-out test split MUST NOT drop below `(baseline accuracy - 0.02)`.
- `model_router.joblib` post-calibration accuracy MUST NOT drop below `(baseline - 0.02)`.
- ECE on each calibrated classifier MUST IMPROVE (lower) compared to the uncalibrated baseline.

These thresholds are checked by a new test in `src/evaluation/tests/test_no_regression.py` that loads the cached baseline numbers from `evaluation/baselines.json` (a one-time committed snapshot of the current numbers) and compares them to fresh outputs.

### Pattern 8: `uv` migration (OSS-01) + `.gitignore` (SECURE-03)

**`uv` installation (developer + CI):**

```bash
# Developer (one-time)
curl -LsSf https://astral.sh/uv/install.sh | sh
# Or: brew install uv (macOS)

# Then, from repo root:
uv python install 3.11           # downloads CPython 3.11 if missing (replaces pyenv)
uv sync                          # creates .venv, installs dependencies, generates uv.lock
uv run python src/demo/demo_router.py   # runs in the project venv
```

**`pyproject.toml`:** see "Standard Stack — Installation" above for the full skeleton.

**`uv.lock`:** Auto-generated by `uv sync`; committed to git. Cross-platform; should not be hand-edited.

**`.gitignore` (root, new file or extended):**

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
*.egg-info/
.pytest_cache/

# Virtual environments
.venv/
venv/
env/

# Environment / secrets
.env
.env.local
.env.*.local

# Local databases (Phase 3 lands these; this list is forward-compatible per SECURE-03)
*.db
*.db-journal
*.db-wal
*.db-shm
chat.db

# IDE
.idea/
.vscode/

# macOS
.DS_Store

# Already-committed paths to LEAVE alone
# (this file does NOT exclude data_processed/, models/, evaluation/ — those are LFS-tracked)
```

[ASSUMED] The current `.gitignore` does not exist or is minimal — `ls -la` at repo root showed only `.gitattributes`. Plan must verify before overwriting.

**GitHub Actions CI (`.github/workflows/ci.yml`):**

```yaml
# Source: https://docs.astral.sh/uv/guides/integration/github/
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          lfs: true   # data_processed/*.csv are LFS pointers

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true

      - name: Set up Python
        run: uv python install 3.11

      - name: Sync dependencies
        run: uv sync --locked --all-extras --dev

      - name: Lint smoke (no FastAPI in routing)
        run: uv run pytest src/routing/tests/test_decide_smoke.py -x

      - name: Unit tests
        run: uv run pytest src/ -q

      - name: Routing canary eval
        run: uv run python -m src.evaluation.evaluate_routing --check
        # --check exits non-zero if backend_accuracy < threshold or any ECE > threshold

      - name: Benchmark regression guard
        run: uv run pytest src/evaluation/tests/test_no_regression.py -q
```

[CITED: docs.astral.sh/uv/guides/integration/github] for the `setup-uv@v3` and `uv sync --locked` flags.

### Anti-Patterns to Avoid

- **Do NOT use `cv="prefit"` with `CalibratedClassifierCV`.** Deprecated in sklearn 1.6; use `FrozenEstimator` instead. [VERIFIED]
- **Do NOT calibrate on the existing held-out test split.** Carve a fresh calibration slice from the training data; otherwise post-calibration metrics on the test split are biased optimistic.
- **Do NOT re-implement the Stage-2 text-input format `"<query> task_type_X keyword_type_Y"` in `src/routing/`.** Lift into a shared helper (CONTEXT.md `<code_context>` Anti-Patterns explicitly calls this out). [VERIFIED: CONTEXT.md]
- **Do NOT add another `sys.path.append(SRC_DIR)` site.** Make `src/routing/` a proper importable package; require `python -m src.routing.decide` invocation. [VERIFIED: CONTEXT.md]
- **Do NOT silently fall back to Claude Code or computer-use.** Per D-12, fallback is ALWAYS OpenRouter, full stop.
- **Do NOT introduce HTTP libraries.** D-18 enforces this via the smoke test; the test must run in CI.
- **Do NOT put per-stage thresholds inside `decide.py` as bare numeric literals.** Defaults live in `src/routing/config.py` as named constants; runtime overrides come from the `settings` dict argument.
- **Do NOT rename `Feature_extractor.py`** or `build_top_model_datatset.py` (typo'd) inside this phase. CONTEXT.md `<deferred>` lists them as anti-patterns to defer to a dedicated cleanup phase.
- **Do NOT skip the `models/uncalibrated/` backup before overwriting** the existing two artifacts. The calibration retrain is destructive; a one-time copy makes it reversible.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Probability calibration | Custom Platt/isotonic implementation | `sklearn.calibration.CalibratedClassifierCV` + `FrozenEstimator` | One line; battle-tested; handles multiclass One-vs-Rest; respects sklearn's CV semantics [CITED: scikit-learn 1.16. Probability calibration] |
| Reliability diagram bins | Custom binning + matplotlib | `sklearn.calibration.calibration_curve` for the curve; matplotlib for the plot | sklearn's binning is the reference implementation; everyone in the literature uses it [CITED: scikit-learn calibration_curve docs] |
| TF-IDF + handcrafted feature combiner | Custom sparse stacker | Existing `FeatureUnion` + `scipy.sparse.hstack` pattern | Already in 5 places in this repo; calibration changes nothing about the feature pipeline [VERIFIED: CLAUDE.md "How scikit-learn / pandas / numpy Are Used"] |
| Project lockfile | Hand-curated `requirements.txt` | `uv` with `pyproject.toml` + `uv.lock` | Cross-platform deterministic resolution; `setup-uv` GitHub Action ships out of the box [CITED: docs.astral.sh/uv] |
| Test discovery | Custom test runner | `pytest 9.0+` | Industry default; fixtures > unittest.TestCase boilerplate [VERIFIED: PyPI 9.0.3] |
| Sentence tokenization | Custom regex | Existing `nltk.sent_tokenize` via `_ensure_nltk_sentence_tokenizer()` | Already in `PromptFeatureExtractor`; reused in `_agentic_features` [VERIFIED] |
| Imperative-verb detection | Custom NLP / dependency parsing | First-word-of-sentence + closed verb list | Phase 1 doesn't justify spaCy; the closed list is auditable and matches the 16 keywords already in D-01 |
| URL / file-path / code-fence detection | Heuristic-laden custom function | Two-line `re` patterns | Standard idiom; minimal surface area |
| ECE computation | Whole new dependency (`netcal`) | 16-line helper around `calibration_curve` | Issue #18268 on sklearn confirms ECE is a small helper most teams write inline; no value in a new dependency for this surface area [CITED: GitHub scikit-learn issue #18268] |

**Key insight:** The "don't hand-roll" advice in this domain is mostly about **NOT reinventing what sklearn already provides**. The notable exception is ECE itself — sklearn deliberately doesn't ship it (per their issue tracker), and `netcal` is a heavier dependency than warranted. A 16-line helper is the right answer.

```python
# Source: derived from https://towardsdatascience.com/expected-calibration-error-ece-...
# (see "Sources" below)

from sklearn.calibration import calibration_curve
import numpy as np

def expected_calibration_error(y_true, y_prob_max, n_bins: int = 10) -> float:
    """ECE on max-class probability for a multiclass classifier.

    For each bin: |accuracy_in_bin - mean_confidence_in_bin| weighted by bin count.
    """
    bin_boundaries = np.linspace(0.0, 1.0, n_bins + 1)
    bin_lowers, bin_uppers = bin_boundaries[:-1], bin_boundaries[1:]
    n = len(y_true)
    ece = 0.0
    for lo, hi in zip(bin_lowers, bin_uppers):
        in_bin = (y_prob_max > lo) & (y_prob_max <= hi)
        if in_bin.sum() == 0:
            continue
        accuracy_in_bin = y_true[in_bin].mean()  # y_true must be {0,1}: was prediction correct?
        mean_confidence_in_bin = y_prob_max[in_bin].mean()
        ece += (in_bin.sum() / n) * abs(accuracy_in_bin - mean_confidence_in_bin)
    return float(ece)
```

## Common Pitfalls

### Pitfall 1: `cv="prefit"` deprecation surprise

**What goes wrong:** Plan recommends `CalibratedClassifierCV(base_clf, cv="prefit", method="sigmoid")` because that's the textbook 2022-era pattern. Code works today, emits DeprecationWarning, breaks silently when CI moves to a future sklearn major.

**Why it happens:** Training data and most online tutorials predate sklearn 1.6's deprecation.

**How to avoid:** Use `FrozenEstimator` from `sklearn.frozen`. Add a smoke test that asserts no `DeprecationWarning` is raised during the calibration retrain (capture warnings with `pytest.warns` or `warnings.catch_warnings`).

**Warning signs:** `DeprecationWarning: The "prefit" option is deprecated in 1.6 and will be removed in 1.8` in CI logs; sklearn version pin in `pyproject.toml` capped to `<1.8` "for now".

### Pitfall 2: `unknown` class trains on a poisoned distribution

**What goes wrong:** "Unknown" rows are simply rows where the dataset name didn't match any keyword group. But many of those rows are *valid* prompts in well-defined task categories whose dataset names just don't include the expected substring (e.g., a creative-writing dataset named `"poetry_v2"` matches NEITHER `arenahard_creative_writing` NOR `creative_writing` NOR `writing` because of the `_v2` suffix). The `unknown` class then absorbs lots of in-distribution data and the OOD signal becomes noise.

**Why it happens:** `build_question_type.py` substring matching is fragile. Look at the existing `general_datasets = ["arenahard"]` mapping — anything *starting with* `arenahard_<something else>` falls into `general` not because it's general but because of substring precedence.

**How to avoid:**
1. Before merging the `unknown` class, dump the actual dataset names that fall through to `unknown` and have a human spot-check that they really are OOD vs. just mis-keyworded.
2. If many in-distribution datasets land in `unknown`, fix `build_question_type.py` keyword groups FIRST, then re-derive the `unknown` set.
3. Optionally: synthetically inject obvious OOD prompts (emoji-only, gibberish, single-token) into the `unknown` class so it has a strong distributional signal beyond just "I didn't match."

**Warning signs:** `unknown` class accounts for >15% of training data; `unknown` precision/recall on the held-out test split is <0.40 (the class is too noisy to learn); fallback rate on the canary's golden-path prompts is >5% (in-distribution prompts are being mistaken for OOD).

### Pitfall 3: Calibration on the wrong split → optimistic ECE

**What goes wrong:** Plan calibrates on the same data the base classifier was trained on. ECE looks fantastic (≈0) because the calibrator memorizes training-set behavior. Real-world ECE is unchanged from the uncalibrated baseline.

**Why it happens:** Convenience. The held-out test split feels like the right place because it's already there.

**How to avoid:** Three-way split: 60% train (already used to fit base classifier) / 20% calibrate (new) / 20% test (existing held-out). The calibration slice is **disjoint from both** the original training data AND the test split. The test split must remain held-out so post-calibration metrics on it are honest.

**Warning signs:** Post-calibration ECE on the held-out test set is identical or better than ECE on the calibration slice (it should be slightly worse on the test set if calibration is honest); model accuracy increases mysteriously after calibration (calibration should not change argmax predictions, only confidences; accuracy should be unchanged).

### Pitfall 4: Existing artifact validator silently rejects calibrated artifacts

**What goes wrong:** `load_joblib_artifacts()` at `src/demo/demo_router.py:35` requires the keys `model`, `vectorizer`, `scaler`, `label_encoder`, `feature_columns`. Plan accidentally renames `model` to `calibrated_model` for clarity, breaking the validator.

**Why it happens:** It's tempting to "improve" the schema while you're already touching the artifact.

**How to avoid:** Calibration replaces ONLY the `model` field; all other keys preserved verbatim. Add a regression test (`test_artifact_compat.py`) that loads each calibrated artifact through the existing `load_joblib_artifacts()` and asserts no exception. The test should fail loudly if any key shape changes.

**Warning signs:** `KeyError: ... is missing required key: model`; `predict_proba` shape changes (e.g., for multiclass, calibrated returns `(n_samples, n_classes)` same as before — but make sure the order of `label_encoder.classes_` matches `calibrated.classes_`).

### Pitfall 5: NLTK download surprises in CI

**What goes wrong:** `_ensure_nltk_sentence_tokenizer()` calls `nltk.download("punkt_tab")` lazily. CI has no NLTK data cached; first test run downloads from NLTK's public host; CI fails intermittently when the host is slow / down.

**Why it happens:** `_NLTK_PUNKT_READY` is a process-level guard but doesn't survive across CI jobs.

**How to avoid:** Pre-download in CI before pytest runs:

```yaml
- name: Pre-fetch NLTK data
  run: uv run python -c "import nltk; nltk.download('punkt_tab', quiet=True); nltk.download('punkt', quiet=True)"
```

Or cache `~/nltk_data/` between CI runs via the `actions/cache@v4` action.

**Warning signs:** Intermittent CI failures with `LookupError: Resource punkt_tab not found`; tests pass locally but fail on a fresh CI runner.

### Pitfall 6: `models/uncalibrated/` backup forgotten → calibration is irreversible

**What goes wrong:** Calibration retrain overwrites `models/task_type_classifier.joblib` and `models/model_router.joblib` in place. If the calibrated artifact is broken (Pitfall 4), the demo is dead and there's no easy way to revert beyond `git restore` — which doesn't work on git-LFS files if the LFS pointer is fine but the actual blob is no longer fetched.

**Why it happens:** "I'll back it up later."

**How to avoid:** First commit of the calibration retrain task: copy current `models/task_type_classifier.joblib` and `models/model_router.joblib` to `models/uncalibrated/`. Commit. Then run the calibration retrain in a separate commit. Reverting becomes a `cp` away.

**Warning signs:** No `models/uncalibrated/` directory in the diff for the calibration commit.

## Code Examples

Verified patterns from official sources (see "Sources" for URLs).

### Example 1: Calibrate an already-fitted classifier (sklearn 1.6+)

```python
# Source: https://scikit-learn.org/stable/auto_examples/frozen/plot_frozen_examples.html
from sklearn.frozen import FrozenEstimator
from sklearn.calibration import CalibratedClassifierCV
from sklearn.naive_bayes import GaussianNB
from sklearn.model_selection import train_test_split

X_train, X_calib, y_train, y_calib = train_test_split(X, y, random_state=42)
base_clf = GaussianNB().fit(X_train, y_train)
calibrated = CalibratedClassifierCV(FrozenEstimator(base_clf), method="sigmoid")
calibrated.fit(X_calib, y_calib)
```

### Example 2: Reliability diagram with `calibration_curve`

```python
# Source: https://scikit-learn.org/stable/modules/generated/sklearn.calibration.calibration_curve.html
import matplotlib.pyplot as plt
from sklearn.calibration import calibration_curve

prob_true, prob_pred = calibration_curve(y_true_binary, y_prob, n_bins=10, strategy="uniform")

fig, ax = plt.subplots(figsize=(8, 6))
ax.plot([0, 1], [0, 1], "k--", label="Perfectly calibrated")
ax.plot(prob_pred, prob_true, "o-", label="Calibrated classifier")
ax.set_xlabel("Mean predicted probability")
ax.set_ylabel("Fraction of positives")
ax.set_title("Reliability Diagram")
ax.legend()
plt.tight_layout()
plt.savefig("evaluation/routing/reliability_diagram_task_type.png", dpi=300)
plt.close(fig)
```

### Example 3: pytest fixture loading joblib artifacts once per session

```python
# src/routing/tests/conftest.py
import os
import pytest
import joblib

REPO_ROOT = os.path.abspath(os.path.join(__file__, "..", "..", "..", ".."))
MODELS_DIR = os.path.join(REPO_ROOT, "models")

@pytest.fixture(scope="session")
def task_artifacts():
    return joblib.load(os.path.join(MODELS_DIR, "task_type_classifier.joblib"))

@pytest.fixture(scope="session")
def model_router_artifacts():
    return joblib.load(os.path.join(MODELS_DIR, "model_router.joblib"))

@pytest.fixture(scope="session")
def agentic_intent_artifacts():
    return joblib.load(os.path.join(MODELS_DIR, "agentic_intent_classifier.joblib"))
```

### Example 4: Asserting the exact fallback rationale phrase

```python
# src/routing/tests/test_fallback.py
from src.routing.decide import decide

def test_fallback_rationale_phrase(task_artifacts, model_router_artifacts, agentic_intent_artifacts):
    """Success Criterion #4: sub-threshold prompts emit 'low confidence — fallback'."""
    artifacts = {
        "task_type_classifier": task_artifacts,
        "model_router": model_router_artifacts,
        "agentic_intent_classifier": agentic_intent_artifacts,
        "model_mapping": {...},  # loaded
    }
    # Force fallback: gibberish prompt
    decision = decide(prompt="asdfgh", artifacts=artifacts)
    assert decision.backend == "openrouter"
    assert decision.model_or_agent == "openrouter/auto"
    assert decision.rationale.endswith("low confidence — fallback"), (
        f"Expected rationale to end with 'low confidence — fallback' (en-dash), got: {decision.rationale!r}"
    )
```

### Example 5: GitHub Actions workflow with uv

```yaml
# Source: https://docs.astral.sh/uv/guides/integration/github/
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { lfs: true }
      - uses: astral-sh/setup-uv@v3
        with: { enable-cache: true }
      - run: uv python install 3.11
      - run: uv sync --locked --all-extras --dev
      - run: uv run pytest -q
      - run: uv run python -m src.evaluation.evaluate_routing --check
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `CalibratedClassifierCV(base, cv="prefit")` | `CalibratedClassifierCV(FrozenEstimator(base))` | sklearn 1.6 (late 2024) | Plans recommending the old pattern emit DeprecationWarning; will break in sklearn 1.8+ [VERIFIED] |
| `pip install -r requirements.txt` | `uv sync` against `pyproject.toml` + `uv.lock` | uv hit production stability July 2025; canonical in 2026 [CITED: AppSignal blog, docs.astral.sh] | New project standard; `uv` is 10–100× faster and the lockfile is cross-platform |
| `claude-code-sdk` | `claude-agent-sdk` | March 2026 rename [VERIFIED: existing `.planning/research/STACK.md`] | Not relevant in Phase 1 (no SDK calls) but relevant when Phase 2 lands; mention here so the planner doesn't accidentally pin the deprecated name in `pyproject.toml` |
| Custom `requirements.txt` per-script | Single `pyproject.toml` at repo root with `[project.optional-dependencies]` for dev | PEP 621 standardized 2021; tooling caught up 2024-2025 | Cleaner; works with all modern Python tools |
| `unittest.TestCase` | `pytest` | pytest has been dominant since ~2018; in 2026 it's near-universal | Easier fixtures, less boilerplate |

**Deprecated/outdated:**

- **`cv="prefit"`** in `CalibratedClassifierCV`: deprecated sklearn 1.6, removal target sklearn 1.8.
- **`pip install pandas numpy ...`** ad-hoc instructions in ReadMe.md: replace with `uv sync`.
- **`requirements.txt`** as the source of truth: replace with `pyproject.toml` + `uv.lock`. (Optional: emit `requirements.txt` via `uv export --format requirements-txt` for consumers that need it.)

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Hatchling is the right build backend for this project | Standard Stack — Installation | Low. `uv_build` and `setuptools` would also work; switching is a 4-line `[build-system]` edit |
| A2 | `epsilon = 0.02` for the quality-first cost tiebreaker | Pattern 6 | Medium. Too small → tiebreaker rarely fires (cost rarely respected); too large → cheap models picked over higher-quality ones. Tunable via canary metrics. |
| A3 | The "offline LLM expansion" for agentic-intent positives is a one-time manual step using the developer's own LLM API key from outside the codebase | Pattern 3, Step 2 | Medium. If the planner instead wants this scripted as part of training, a new (Phase-deferred) HTTP dependency leaks into the pipeline. Recommend keeping it manual. |
| A4 | 5–15% of synthesized agentic prompts will be hand-deleted in the audit step | Pattern 3, Step 3 | Low. Anthropic's published synthetic-data norms suggest this range; actual depends on prompt quality. Doesn't affect plan structure. |
| A5 | Current `.gitignore` is missing or minimal | Pattern 8 | Low. `ls -la` confirmed only `.gitattributes` exists; planner verifies. |
| A6 | sklearn 1.7.x is the version available when the plan executes | Standard Stack | Low. The `>=1.7,<2.0` range catches 1.7 and 1.8; if 1.9 ships before plan execution and breaks something, lockfile regeneration handles it |
| A7 | Per-stage thresholds (`task_type_tau=0.35`, `agentic_intent_tau=0.55`, `model_router_tau=0.20`) are reasonable starting values | Pattern 2 | Medium. CONTEXT.md D-10 pinned these as defaults but flagged they may need tuning. The plan must include a "tune thresholds against canary" task. |
| A8 | The existing CI hosting (or absence thereof) is GitHub Actions | Pattern 8 | Low. INTEGRATIONS.md says "No CI Pipeline" today; GitHub Actions is the assumed target because the repo is on GitHub. A different CI (CircleCI, etc.) requires translating the workflow file. |
| A9 | NLTK pre-download in CI is the right way to handle the lazy-download anti-pattern | Pitfall 5 | Low. Alternative (cache `~/nltk_data/`) also works; the YAML differs only slightly |
| A10 | The "Architectural Responsibility Map" intentionally has no FastAPI / SQLite / UI rows because Phase 1 has no such surface | Architectural Responsibility Map | Zero — this is a documentation-only artifact for the planner |
| A11 | `epsilon`, threshold tuning, and dataset audit are tasks for the executor (not deferred to Phase 2) | Multiple | Low. They are part of "phase exit" criteria; the plan must surface them as explicit tasks |

## Open Questions

1. **Calibration method per stage: sigmoid for all three, or isotonic for the 16-class model_router?**
   - What we know: Sigmoid is the conservative default; isotonic is more flexible but needs more calibration data; the model_router has 16 classes which makes One-vs-Rest sigmoid harder.
   - What's unclear: Whether the 16-class router has enough calibration data per class to support isotonic without overfitting.
   - Recommendation: Start sigmoid for all three. Re-evaluate if `model_router` ECE > 0.10 on the canary; switch only that stage to isotonic in a follow-up commit.

2. **Should the 5 new agentic-intent features be added to the existing two classifiers' training inputs (Option A) or kept agentic-only (Option B)?**
   - What we know: `feature_columns` lists are stored per-artifact; existing `build_numeric_features()` silently drops extra fields, so inference is fine either way. The question is about training.
   - What's unclear: Whether the new features actually improve task-type or model-router accuracy.
   - Recommendation: **Option A** (re-train the two existing heads on the extended feature set as part of the calibration retrain). One artifact shape, no future divergence. If accuracy regresses, switch to Option B in a follow-up.

3. **Where does the "offline LLM expansion" for agentic-intent positives actually run?**
   - What we know: D-05 says "prompt a strong chat LLM to generate ~500 paraphrastic variations." There is no live LLM in the routing brain.
   - What's unclear: Is this a manual one-time operation by the developer using their own API key, or is there a script in `src/agentic_intent/synthesize_dataset.py` that calls the LLM (which would mean a new dependency)?
   - Recommendation: Manual one-time. Commit the resulting CSV. Include the prompt template used as a comment in `synthesize_dataset.py` (which then reads from an existing CSV, not from a live LLM). This keeps the routing brain dependency-free.

4. **Does the planner centralize path constants in `src/paths.py` opportunistically?**
   - What we know: ARCHITECTURE.md flags duplicated `PROJECT_ROOT` discovery as an anti-pattern; the new `src/routing/` package is a natural place to extract it.
   - What's unclear: Whether it's worth touching every existing entry script in this phase.
   - Recommendation: Create `src/paths.py` with `REPO_ROOT`, `MODELS_DIR`, `CONFIG_DIR`, `DATA_PROCESSED_DIR`, `EVALUATION_DIR` constants. New `src/routing/` and `src/agentic_intent/` import from it. Existing scripts MAY migrate opportunistically but are NOT required to (defer the broad rewrite to a dedicated cleanup phase).

5. **What is the `epsilon` value for quality-first cost tiebreaker?**
   - What we know: `0.02` was assumed; it should be tunable.
   - What's unclear: The actual confidence-gap distribution on real prompts.
   - Recommendation: Plan task to dump the top-K confidence gaps observed during the canary eval and pick `epsilon` so that the tiebreaker fires on ~10–20% of OpenRouter routes (enough to matter, not so much that quality is sacrificed).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `uv` | OSS-01 (`uv sync`), CI workflow, all Phase 1 commands | ✗ | — | Install via `curl -LsSf https://astral.sh/uv/install.sh \| sh` or `brew install uv`. Plan MUST include a setup step or the developer cannot proceed. |
| Python 3.10+ | All Phase 1 code (`dict \| None` syntax in existing files; pyproject `requires-python = ">=3.10"`) | ✗ | system has Python 3.9.6 only | `uv python install 3.11` (uv can install Python interpreters; this is the recommended path). Otherwise: `brew install python@3.11`. |
| pip / scikit-learn / pandas / etc. | Existing pipeline | ✗ on this machine | — | Auto-installed by `uv sync` once `pyproject.toml` lands. |
| `git lfs` | `data_processed/*.csv` are LFS pointers | ? | not probed (sandbox) | `brew install git-lfs && git lfs install`. Required for the canary CSV to be checked out as the actual file. |
| `pytest` | New test suite (`src/routing/tests/`) | ✗ | — | Auto-installed via `pyproject.toml` `[project.optional-dependencies] dev`. |
| Internet egress (one-time) | NLTK `punkt_tab` download; HuggingFace SentenceTransformer cache (existing) | ✓ assumed | — | Pre-fetch in CI step (see Pitfall 5); developer's first run also requires it. |
| GitHub Actions | CI workflow | ✓ assumed | — | If repo isn't on GitHub or uses a different CI, translate `.github/workflows/ci.yml` to that platform's syntax. |

**Missing dependencies with no fallback:**

- None — every dependency listed has either a fallback path or is auto-installable.

**Missing dependencies with fallback:**

- `uv` and Python 3.10+ are MISSING on the developer's machine. The plan's Wave 0 task list MUST include explicit installation steps before any other work; `uv sync` will fail without them.

## Validation Architecture

> Phase config: `workflow.nyquist_validation: true` (verified in `.planning/config.json`). This section is REQUIRED for Dimension 8 plan-checking.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | **pytest 9.0.x** (current latest 9.0.3, requires Python 3.10+) [VERIFIED: PyPI] |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` block (no separate `pytest.ini`) |
| Quick run command | `uv run pytest src/routing/tests -q` (≈ <30s expected; loads joblib once via session fixture) |
| Full suite command | `uv run pytest -q` (runs all `src/**/tests/`) |
| Coverage (optional) | `uv run pytest --cov=src/routing --cov=src/agentic_intent --cov-report=term-missing` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ROUTER-01 | `agentic_intent_classifier.joblib` exists, loads via canonical validator, reports P/R on held-out test | unit | `pytest src/agentic_intent/tests/test_train_smoke.py -x` | ❌ Wave 0 |
| ROUTER-02 | Task-type classifier has `unknown` class; OOD prompts route to `unknown` OR sub-threshold triggers fallback | unit | `pytest src/routing/tests/test_ood.py -x` | ❌ Wave 0 |
| ROUTER-03 | Calibrated classifiers' `predict_proba` is well-calibrated (ECE improves vs. uncalibrated baseline) | integration | `pytest src/evaluation/tests/test_calibration_improves.py -x` | ❌ Wave 0 |
| ROUTER-04 | Canary CSV exists at `data_processed/routing_decision_eval.csv`, has ~42 rows + required columns + 4 edge-case categories | unit | `pytest src/evaluation/tests/test_canary_schema.py -x` | ❌ Wave 0 |
| ROUTER-05 | `decide()` returns a `RoutingDecision` with required fields; CLI prints JSON | unit + smoke | `pytest src/routing/tests/test_decide_smoke.py -x` AND `python -m src.routing.decide "test" \| jq .backend` | ❌ Wave 0 |
| ROUTER-06 | When two model_router predictions are within `epsilon`, the cheaper-tier wins | unit | `pytest src/routing/tests/test_cost_tiebreaker.py -x` | ❌ Wave 0 |
| ROUTER-07 | `route_prompt()` in `demo_router.py` delegates to `decide()`; benchmark eval shows no regression > 0.02 | integration | `pytest src/evaluation/tests/test_no_regression.py -x` | ❌ Wave 0 |
| OSS-01 | `uv sync` completes against `pyproject.toml` + `uv.lock`; `python -m src.routing.decide "..."` runs in the venv | manual + CI | `uv sync --locked && uv run python -m src.routing.decide "test"` | ❌ Wave 0 |
| SECURE-03 | `.gitignore` excludes the 7 specified patterns | unit | `pytest src/routing/tests/test_gitignore.py -x` (greps the file) | ❌ Wave 0 |
| Success #4 | Fallback rationale ends in exact substring `"low confidence — fallback"` (en-dash) | unit | `pytest src/routing/tests/test_fallback.py::test_fallback_rationale_phrase -x` | ❌ Wave 0 |
| D-18 | `decide()` import does not pull in fastapi / httpx / requests / aiohttp / anthropic / openai | unit | `pytest src/routing/tests/test_decide_smoke.py::test_no_forbidden_modules_imported_after_decide -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest src/routing/tests -q` (fast subset, <30s)
- **Per wave merge:** `uv run pytest -q` (full suite)
- **Phase gate:** Full suite green AND `python -m src.evaluation.evaluate_routing --check` green AND benchmark regression test green before `/gsd-verify-work`

### Wave 0 Gaps

All test infrastructure must be created in Wave 0 (none exists today):

- [ ] `pyproject.toml` with `[project.optional-dependencies] dev = ["pytest>=9", "pytest-cov>=5"]` and `[tool.pytest.ini_options]` block
- [ ] `src/routing/__init__.py` and `src/routing/tests/__init__.py`
- [ ] `src/routing/tests/conftest.py` — session-scope fixtures for joblib artifacts and model_mapping
- [ ] `src/routing/tests/test_decide_smoke.py` — covers ROUTER-05 + D-18
- [ ] `src/routing/tests/test_fallback.py` — covers Success Criterion #4
- [ ] `src/routing/tests/test_rule_cascade.py` — covers D-01 (every branch)
- [ ] `src/routing/tests/test_ood.py` — covers ROUTER-02
- [ ] `src/routing/tests/test_cost_tiebreaker.py` — covers ROUTER-06
- [ ] `src/routing/tests/test_gitignore.py` — covers SECURE-03
- [ ] `src/routing/tests/test_artifact_compat.py` — covers Pitfall 4
- [ ] `src/agentic_intent/tests/__init__.py` and `test_train_smoke.py` — covers ROUTER-01
- [ ] `src/evaluation/tests/__init__.py`, `test_canary_schema.py`, `test_calibration_improves.py`, `test_no_regression.py`, `test_evaluate_routing_runs.py` — covers ROUTER-03, ROUTER-04, ROUTER-07
- [ ] `evaluation/baselines.json` — one-time committed snapshot of pre-calibration metrics for the regression guard
- [ ] `.github/workflows/ci.yml` — runs `uv sync --locked` + `pytest -q` + `evaluate_routing --check` + regression guard
- [ ] Framework install: `uv add --dev pytest pytest-cov` then `uv sync` to materialize the lock
- [ ] NLTK pre-download step in CI (Pitfall 5)

## Security Domain

> `security_enforcement` is not explicitly disabled in `.planning/config.json`, so this section is REQUIRED.

### Applicable ASVS Categories

Phase 1 has a **narrow** security surface — no HTTP, no DB, no key handling beyond `.gitignore`. Most ASVS categories are deferred to later phases.

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Deferred to Phase 3 (BYOK key entry endpoint) |
| V3 Session Management | no | No sessions in Phase 1 |
| V4 Access Control | no | Single-user CLI / SDK; no auth boundary |
| V5 Input Validation | partial — yes for `decide(prompt: str)` | The `prompt` argument is treated as untrusted text. `PromptFeatureExtractor` already handles `None`, NaN, and non-string via `_safe_text()`. New agentic-intent features (`re.search` patterns) MUST be regex-DoS-safe — bound input length and use simple patterns. |
| V6 Cryptography | no | No keys / secrets in Phase 1 |
| V7 Error Handling | yes | `decide()` MUST NOT crash on any input (including empty / multi-MB / non-UTF8). Existing demo wraps `route_prompt` in try/except; replicate. |
| V8 Data Protection | partial | `.gitignore` (SECURE-03) prevents `.env`, `*.db`, `chat.db`, etc. from being committed. No data-at-rest in Phase 1 beyond joblib artifacts (which are not secrets). |
| V14 Configuration | yes | `pyproject.toml` MUST pin sklearn ≥1.7 (FrozenEstimator availability) and Python ≥3.10. `uv.lock` ensures reproducible builds. |

### Known Threat Patterns for `src/routing/`

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Regex DoS in new `_agentic_features` (URL / file-path detection) | Denial of Service | Bound `prompt` length to e.g. 50,000 chars before regex; use simple non-backtracking patterns; reject pathological inputs early in `decide()` |
| Pickle deserialization attack via untrusted `joblib` artifact | Tampering | Phase 1's joblib artifacts are produced and consumed by the same codebase; add a CI smoke test that asserts artifact SHA256 hashes match expected values when models change. Document that users MUST NOT load joblib files from untrusted sources. |
| Secret leakage via committed `.env` or `chat.db` | Information disclosure | SECURE-03's `.gitignore` covers this; pre-commit hook for `sk-` prefixes is Phase 2 (SECURE-02). |
| Confused-deputy: `model_or_agent` string used by Phase 2 adapters as if it were a validated identifier | Tampering | Phase 1 documents that `model_or_agent` is one of three sentinels OR a valid OpenRouter `api_model` slug from `config/model_mapping.json`. Phase 2 adapters MUST validate against an allowlist before passing to provider SDK. |

**Threat-model entries for the planner's `<threat_model>` block (use verbatim):**

```
T1 — Untrusted prompt input: decide(prompt) accepts arbitrary user text. Mitigation:
     length bound (50k chars); non-backtracking regex; safe text coercion via
     _safe_text(); try/except around end-to-end decide() call in callers.

T2 — Regex DoS in agentic-intent features: new _agentic_features uses re.search for
     URLs and file paths. Mitigation: simple anchored patterns; input length bound;
     no nested quantifiers.

T3 — Joblib pickle deserialization: decide() unpickles models/*.joblib at startup.
     Mitigation: artifacts are produced by this repo's own training scripts only;
     CI hash-check on artifact contents; documented warning against loading
     third-party joblib files.

T4 — Premature secret commit: developer might commit a .env or chat.db while
     prototyping Phase 2 adapters. Mitigation: SECURE-03 .gitignore + this phase's
     test_gitignore.py asserts the 7 required patterns.

T5 — Phase 2 confused deputy: model_or_agent strings emitted by decide() are
     trusted as-is by Phase 2 adapters. Mitigation: documented invariant
     (one of three sentinels OR an api_model from model_mapping.json);
     Phase 2 plan is responsible for the allowlist enforcement.
```

## Sources

### Primary (HIGH confidence)

- **scikit-learn 1.8.0 docs — CalibratedClassifierCV** — https://scikit-learn.org/stable/modules/generated/sklearn.calibration.CalibratedClassifierCV.html — verified `cv="prefit"` deprecated in 1.6, `FrozenEstimator` is the replacement
- **scikit-learn 1.8.0 docs — Probability Calibration** — https://scikit-learn.org/stable/modules/calibration.html — sigmoid vs isotonic guidance
- **scikit-learn 1.8.0 docs — calibration_curve** — https://scikit-learn.org/stable/modules/generated/sklearn.calibration.calibration_curve.html — reliability diagram primitive
- **scikit-learn 1.8.0 example — FrozenEstimator** — https://scikit-learn.org/stable/auto_examples/frozen/plot_frozen_examples.html — canonical calibration-of-already-fitted-model recipe
- **uv documentation — GitHub Actions integration** — https://docs.astral.sh/uv/guides/integration/github/ — `setup-uv@v3` and `uv sync --locked --all-extras --dev` pattern
- **uv documentation — Project init / build backends** — https://docs.astral.sh/uv/concepts/projects/init/ — Hatchling and other backend choices
- **PyPI — pytest 9.0.3** — https://pypi.org/project/pytest/ — current latest version, requires Python 3.10+
- **CONTEXT.md (D-01 through D-18)** — `.planning/phases/01-router-brain-foundation/01-CONTEXT.md` — locked decisions
- **REQUIREMENTS.md** — `.planning/REQUIREMENTS.md` — ROUTER-01..07, OSS-01, SECURE-03 verbatim
- **CLAUDE.md** — project conventions, sklearn patterns, joblib artifact shape
- **`src/demo/demo_router.py`** — existing `load_joblib_artifacts()` validator at line 35; `choose_final_route()` at line 245
- **`src/feature_extraction/Feature_extractor.py`** — extension point for agentic-intent features
- **`config/model_mapping.json`** — 16-entry slug → api_model mapping; `openrouter` entry is the fallback target

### Secondary (MEDIUM confidence — WebSearch verified against an official source)

- **Towards Data Science — ECE step-by-step** — https://towardsdatascience.com/expected-calibration-error-ece-a-step-by-step-visual-explanation-with-python-code-c3e9aa12937d/ — referenced for the 16-line ECE helper recipe; cross-checked against sklearn issue #18268 confirming sklearn deliberately doesn't ship ECE
- **GitHub scikit-learn issue #18268** — https://github.com/scikit-learn/scikit-learn/issues/18268 — confirms ECE is intentionally a small helper, not a stdlib function
- **PyPI — netcal** — https://pypi.org/project/netcal/ — alternative ECE library (rejected for Phase 1 due to dep weight)
- **AppSignal — Switching from Pip to uv (Sep 2025)** — https://blog.appsignal.com/2025/09/24/switching-from-pip-to-uv-in-python-a-comprehensive-guide.html — uv production-stable in 2025
- **Springer Discover Data 2025 — OOD detection in text** — https://link.springer.com/article/10.1007/s44248-025-00091-x — Mahalanobis vs MSP comparison; informed the decision to defer Mahalanobis to v2
- **arXiv 1610.02136 — A Baseline for Detecting Misclassified and Out-of-Distribution Examples** — https://arxiv.org/pdf/1610.02136 — MSP as the canonical OOD baseline

### Tertiary (LOW confidence — single source, flagged for validation)

- **Medium — Python Build Backends in 2025 (Hatchling vs uv_build)** — https://medium.com/@dynamicy/python-build-backends-in-2025-what-to-use-and-why-uv-build-vs-hatchling-vs-poetry-core-94dd6b92248f — used to inform A1 (hatchling choice); planner may pick differently
- **Medium — 2026 Golden Path with uv** — https://medium.com/@diwasb54/the-2026-golden-path-building-and-publishing-python-packages-with-a-single-tool-uv-b19675e02670 — secondary confirmation of uv-as-default

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — sklearn / pytest / uv versions verified against PyPI and official docs
- Architecture: HIGH — pure-Python, single-tier, every responsibility maps to existing or trivially extensible patterns
- Calibration approach: HIGH — `FrozenEstimator` pattern verified against current sklearn docs; the `cv="prefit"` deprecation is a strong, easy-to-miss finding
- OOD strategy: MEDIUM — dual-signal approach is sound but depends on clean `unknown` class data (Pitfall 2 is the primary risk)
- Agentic-intent dataset: MEDIUM — depends on a one-time manual LLM expansion step that can't be fully verified until executed; threshold defaults will likely need post-canary tuning
- Pitfalls: HIGH — every pitfall is sourced either from observed code-shape compatibility issues or from documented sklearn changes
- Validation architecture: HIGH — pytest is uncontroversial; the test map covers all 9 Phase 1 requirements + 2 success criteria with explicit commands
- Security: HIGH — narrow surface; `.gitignore` is the only Phase 1 SECURE deliverable; future-phase threats documented for the planner

**Research date:** 2026-05-11
**Valid until:** 2026-06-11 (30 days). Re-verify if the plan executes after that — particularly sklearn version, uv version, pytest version, and `setup-uv` GitHub Action major version.
