<!-- refreshed: 2026-05-11 -->
# Architecture

**Analysis Date:** 2026-05-11

## System Overview

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                       OFFLINE TRAINING PIPELINE                          │
│                                                                          │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────────────┐  │
│  │  data_raw/   │───▶│ src/data/        │───▶│  data_processed/     │  │
│  │  (JSON tree) │    │ flatten_raw_     │    │  flat_records.csv    │  │
│  │              │    │ jsons.py         │    │  classifier_training │  │
│  │              │    │ build_classifier │    │  .csv                │  │
│  │              │    │ _dataset[_*].py  │    │  *_cost_aware.csv    │  │
│  └──────────────┘    └──────────────────┘    └──────────┬───────────┘  │
│                                                          │              │
│                                                          ▼              │
│                  ┌──────────────────────────────────────────────────┐  │
│                  │  src/task_classifier/build_question_type.py      │  │
│                  │    (weak label dataset -> question_type)         │  │
│                  └──────────────────┬───────────────────────────────┘  │
│                                     ▼                                   │
│                  ┌──────────────────────────────────────────────────┐  │
│                  │  src/feature_extraction/build_features.py        │  │
│                  │    + Feature_extractor.PromptFeatureExtractor    │  │
│                  │    (handcrafted numeric prompt features)         │  │
│                  └──────────────────┬───────────────────────────────┘  │
│                                     ▼                                   │
│      ┌──────────────────────────────────────────────────────────────┐  │
│      │            STAGE 1: TASK TYPE CLASSIFIER                      │  │
│      │  src/task_classifier/train_task_classifier_robust.py          │  │
│      │  word+char TF-IDF  ⊕  StandardScaler(numeric)                 │  │
│      │  -> LogisticRegression (class_weight="balanced")              │  │
│      │  artifacts:  models/task_type_classifier.joblib               │  │
│      │  plots:      evaluation/plots/                                │  │
│      └──────────────────┬───────────────────────────────────────────┘  │
│                         ▼                                               │
│      ┌──────────────────────────────────────────────────────────────┐  │
│      │     ROUTER DATASET BUILDERS (apply Stage 1 to data)           │  │
│      │  src/model_router_tier/build_router_dataset.py                │  │
│      │    -> data_processed/router_training_dataset.csv              │  │
│      │  src/model_router/build_top_model_datatset.py                 │  │
│      │    -> data_processed/router_training_dataset_top_models.csv   │  │
│      └──────────┬───────────────────┬────────────────────────────────┘  │
│                 │                   │                                   │
│                 ▼                   ▼                                   │
│  ┌─────────────────────────┐  ┌─────────────────────────┐               │
│  │  STAGE 2a: TIER ROUTER  │  │  STAGE 2b: MODEL ROUTER │               │
│  │  model_router_tier/     │  │  model_router/          │               │
│  │  train_tier_router.py   │  │  train_model_router.py  │               │
│  │  models/tier_router     │  │  models/model_router    │               │
│  │  .joblib                │  │  .joblib                │               │
│  └─────────────────────────┘  └─────────────────────────┘               │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  EXPERIMENT: EMBEDDING ROUTER  (parallel branch)                 │   │
│  │  src/model_router/train_embedding_router.py                      │   │
│  │  SentenceTransformer(all-MiniLM-L6-v2) -> LogisticRegression     │   │
│  │  models/embedding_router.joblib                                  │   │
│  │  evaluation/embedding_router_plots/                              │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  EVALUATION / COMPARISON                                         │   │
│  │  src/evaluation/evaluate_baselines.py   (oracle / cheapest /     │   │
│  │                                          gpt-5 / embedding)      │   │
│  │  src/evaluation/compare_router_results.py (router metric plots)  │   │
│  │  -> evaluation/*.csv, evaluation/comparison_plots/               │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       INFERENCE / DEMO LAYER                             │
│                                                                          │
│  User Prompt (stdin)                                                    │
│      │                                                                   │
│      ▼                                                                   │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │  src/demo/demo_router.py    (two-stage routed demo)             │    │
│  │   load task_type_classifier.joblib + model_router.joblib +      │    │
│  │        config/model_mapping.json                                │    │
│  │   PromptFeatureExtractor() -> Stage 1 predict_task_type()       │    │
│  │                            -> Stage 2 predict_best_model()      │    │
│  │                            -> choose_final_route()              │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │  src/demo/demo_embedding_router.py   (single-stage demo)        │    │
│  │   load embedding_router.joblib + SentenceTransformer            │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│                                  │                                       │
│                                  ▼                                       │
│           Simulated route metadata (display_name / provider /            │
│           tier / api_model / openrouter_verified)                        │
└─────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Raw flattener | Walk nested benchmark JSON tree and emit one row per (file, record) | `src/data/flatten_raw_jsons.py` |
| Best-model aggregator | Pick `best_model` per `question_id` (highest score, then lowest cost) | `src/data/build_classifier_dataset.py` |
| Cost-aware aggregator | Pick `best_value_model` (cheapest model within a score tolerance band) | `src/data/build_classifier_dataset_cost_aware.py` |
| Weak labeler | Map `dataset` -> `question_type` (coding / math / writing / ...) | `src/task_classifier/build_question_type.py` |
| Feature extractor | Compute handcrafted numeric features from raw prompt text | `src/feature_extraction/Feature_extractor.py` |
| Feature batch builder | Apply extractor to every CSV with `origin_query` and write `*_features.csv` | `src/feature_extraction/build_features.py` |
| Task type classifier (Stage 1) | word+char TF-IDF + numeric features -> question_type | `src/task_classifier/train_task_classifier_robust.py` |
| Simple baseline classifier | RandomForest+rule fallback baseline for Stage 1 (experimental) | `src/task_classifier/train_task_classifier_simple.py` |
| Router dataset builder | Apply saved task classifier to dataset, add `question_type_confidence` and `best_model_tier` | `src/model_router_tier/build_router_dataset.py` |
| Top-model dataset builder | Keep top 15 model labels, group rest into `OTHER` | `src/model_router/build_top_model_datatset.py` |
| Tier router (Stage 2a) | Predict cheap/medium/strong tier from prompt+task signal | `src/model_router_tier/train_tier_router.py` |
| Tier router system (alt) | Alternate tier-routing script | `src/model_router_tier/router_tier_system.py` |
| Model router (Stage 2b) | Predict exact model class (top 15 + OTHER) | `src/model_router/train_model_router.py` |
| Embedding router (experiment) | Sentence-embedding -> LogisticRegression model picker | `src/model_router/train_embedding_router.py` |
| Vendor family helper | Map model name to coarse vendor bucket (qwen / gpt / deepseek / ...) | `src/model_router/model_family.py` |
| Baseline evaluator | Oracle / Always-Cheapest / Always-GPT-5 / Embedding-Router comparison | `src/evaluation/evaluate_baselines.py` |
| Router metric comparator | Aggregate per-class metric CSVs into comparison plots | `src/evaluation/compare_router_results.py` |
| Two-stage demo | Interactive prompt -> task -> model -> mapped route | `src/demo/demo_router.py` |
| Embedding demo | Interactive prompt -> embedding -> model | `src/demo/demo_embedding_router.py` |
| Route mapping | Benchmark model name -> display/provider/tier/api metadata | `config/model_mapping.json` |

## Pattern Overview

**Overall:** Offline scikit-learn ML pipeline with `joblib`-serialized artifacts and a thin CLI inference demo.

**Key Characteristics:**
- Each pipeline stage is a standalone Python script that reads a CSV under `data_processed/`, writes a new CSV, and (for training scripts) writes a `joblib` artifact under `models/` plus evaluation plots/CSVs under `evaluation/`.
- Training and inference share one feature contract: `PromptFeatureExtractor` from `src/feature_extraction/Feature_extractor.py`. Saved `joblib` files carry the `feature_columns` list so inference can reproduce the exact training feature matrix.
- TF-IDF stack is consistent across Stage-1 and Stage-2 TF-IDF routers: `FeatureUnion([word_tfidf(1-2gram), char_tfidf(3-5gram)])` ⊕ scaled handcrafted numerics ⊕ `LogisticRegression(class_weight="balanced", solver="saga")`.
- The embedding router is a parallel branch that bypasses TF-IDF and handcrafted features entirely (`sentence-transformers/all-MiniLM-L6-v2`).
- No web framework, no DB, no API client — everything is local CSV/joblib/JSON I/O. The demo is a `while True: input(...)` REPL.

## Layers

**Data layer (`src/data/`, `data_raw/`, `data_processed/`):**
- Purpose: Convert raw benchmark JSON into tabular CSVs and aggregate per-question best-model labels.
- Location: `src/data/`
- Contains: `flatten_raw_jsons.py`, `build_classifier_dataset.py`, `build_classifier_dataset_cost_aware.py`
- Depends on: filesystem (`data_raw/`), `csv`, `json`, `pathlib`
- Used by: feature extraction, weak labeling

**Feature extraction layer (`src/feature_extraction/`):**
- Purpose: Compute deterministic numeric features from prompt strings.
- Location: `src/feature_extraction/`
- Contains: `Feature_extractor.py` (`PromptFeatureExtractor`), `build_features.py`
- Depends on: `nltk` (punkt/punkt_tab), `pandas`, `re`
- Used by: every Stage-1 and Stage-2 TF-IDF training script and `src/demo/demo_router.py`

**Stage 1 classifier layer (`src/task_classifier/`):**
- Purpose: Predict broad task type (coding, math, writing, ...).
- Location: `src/task_classifier/`
- Contains: `build_question_type.py` (weak labeler), `train_task_classifier_robust.py` (production), `train_task_classifier_simple.py` (baseline)
- Depends on: feature extraction layer, scikit-learn, joblib
- Used by: router dataset builder, two-stage demo

**Stage 2 router layer (`src/model_router/`, `src/model_router_tier/`):**
- Purpose: Predict either an exact model class or a coarse tier from prompt + Stage 1 signal.
- Location: `src/model_router/`, `src/model_router_tier/`
- Contains: dataset builders, three trainers (`train_tier_router.py`, `train_model_router.py`, `train_embedding_router.py`)
- Depends on: Stage 1 artifact (`models/task_type_classifier.joblib`), feature extraction layer, scikit-learn, sentence-transformers (embedding router only)
- Used by: evaluation comparison, demo routers

**Evaluation layer (`src/evaluation/`, `evaluation/`):**
- Purpose: Score the saved routers against baselines, write metrics CSVs and comparison plots.
- Location: `src/evaluation/`
- Contains: `evaluate_baselines.py`, `compare_router_results.py`
- Depends on: saved routers and metric CSVs produced by training scripts
- Used by: `evaluation_summary.md` (manual aggregation)

**Inference / demo layer (`src/demo/`):**
- Purpose: Interactive CLI that loads saved artifacts and routes one prompt at a time.
- Location: `src/demo/`
- Contains: `demo_router.py` (full two-stage), `demo_embedding_router.py` (semantic single-stage)
- Depends on: `models/*.joblib`, `config/model_mapping.json`, `src/feature_extraction/Feature_extractor.py` (added to `sys.path` at runtime)
- Used by: end user (interactive REPL)

## Data Flow

### Primary Request Path (Training)

1. Drop benchmark JSON files into `data_raw/<release>/<dataset>/<split>/<model_dir>/*.json`.
2. Flatten into one CSV (`src/data/flatten_raw_jsons.py:307` `main`) -> `data_processed/flat_records.csv`.
3. Aggregate best model per question (`src/data/build_classifier_dataset.py:215` `main`) -> `data_processed/classifier_training.csv`.
4. (Optional) Build cost-aware variant (`src/data/build_classifier_dataset_cost_aware.py`) -> `data_processed/classifier_training_cost_aware.csv`.
5. Weak-label question type from dataset name (`src/task_classifier/build_question_type.py:153` `main`) -> `data_processed/classifier_training_with_types.csv`.
6. Add handcrafted features to every CSV with `origin_query` (`src/feature_extraction/build_features.py:48` `main`) -> `*_features.csv`.
7. Train Stage 1 task classifier (`src/task_classifier/train_task_classifier_robust.py:338` `train_task_type_classifier`) -> `models/task_type_classifier.joblib`, `evaluation/plots/`, `evaluation/classification_metrics.csv`, `evaluation/misclassified_examples.csv`.
8. Build router dataset using Stage 1 predictions (`src/model_router_tier/build_router_dataset.py:187` `build_router_dataset`) -> `data_processed/router_training_dataset.csv`.
9. Build top-model variant (`src/model_router/build_top_model_datatset.py:43` `build_top_model_router_dataset`) -> `data_processed/router_training_dataset_top_models.csv`.
10. Train Stage 2a tier router (`src/model_router_tier/train_tier_router.py:470` `train_tier_router`) -> `models/tier_router.joblib` + `evaluation/router_plots/` + `evaluation/tier_router_metrics.csv`.
11. Train Stage 2b model router (`src/model_router/train_model_router.py`) -> `models/model_router.joblib` + `evaluation/model_router_plots/` + `evaluation/model_router_metrics.csv`.
12. Train embedding router experiment (`src/model_router/train_embedding_router.py`) -> `models/embedding_router.joblib` + `evaluation/embedding_router_plots/` + `evaluation/embedding_router_metrics.csv`.
13. Compare routers (`src/evaluation/compare_router_results.py`) -> `evaluation/router_comparison_summary.csv`, `evaluation/comparison_plots/`.

### Primary Request Path (Inference / Demo)

1. User runs `python src/demo/demo_router.py`.
2. `main` (`src/demo/demo_router.py:421`) loads `task_type_classifier.joblib`, `model_router.joblib`, `config/model_mapping.json`, instantiates `PromptFeatureExtractor`.
3. REPL loop reads `prompt` from stdin.
4. `route_prompt` (`src/demo/demo_router.py:291`) runs:
   - `predict_task_type` (line 136): TF-IDF + scaled numeric features -> LogisticRegression -> `question_type`, `confidence`.
   - `predict_best_model` (line 186): combined text input (`"<prompt> task_type_<qt> keyword_type_unknown"`) + numeric features incl. `question_type_confidence` -> LogisticRegression -> `predicted_model`.
   - `choose_final_route` (line 245): map prediction via `config/model_mapping.json`, fall back to `OTHER`.
5. `print_route_result` writes the simulated route, including any `api_model` if `openrouter_verified=true`.

### Embedding Demo Flow

1. `python src/demo/demo_embedding_router.py`.
2. `main` (`src/demo/demo_embedding_router.py:146`) loads `embedding_router.joblib`, instantiates `SentenceTransformer(artifacts["embedding_model_name"])`.
3. `predict_prompt` (line 64): encode prompt with normalized embeddings, optional scaler, classifier -> predicted model + confidence table.

**State Management:**
- All state is on disk. Each script is idempotent over its outputs and reloads artifacts on every run.
- Demos hold the loaded artifacts + `PromptFeatureExtractor` instance in local function scope for the REPL session.

## Key Abstractions

**`PromptFeatureExtractor`:**
- Purpose: Single class that produces the canonical numeric feature dict for every prompt.
- Examples: `src/feature_extraction/Feature_extractor.py:30`.
- Pattern: One `extract(text) -> dict` method composed of `_basic_text_features`, `_symbol_features`, `_keyword_features`, `_complexity_features`, `_constraint_features`. Keyword groups stored on the instance.

**Saved-router artifact dict (Stage 1, tier router, model router):**
- Purpose: Self-contained inference bundle.
- Examples: `models/task_type_classifier.joblib`, `models/tier_router.joblib`, `models/model_router.joblib`.
- Pattern: `joblib.dump({"model", "vectorizer", "scaler", "label_encoder", "feature_columns", [optional "target_column"]}, path)`. Loaders validate required keys (see `load_joblib_artifacts` in `src/demo/demo_router.py:35`).

**Saved-embedding-router artifact dict:**
- Purpose: Embedding-only inference bundle.
- Examples: `models/embedding_router.joblib`.
- Pattern: `{"model", "scaler", "label_encoder", "target_column", "embedding_model_name", ...}` (see `load_embedding_router_artifacts` in `src/demo/demo_embedding_router.py:29`).

**Task-informed text input (Stage 2 TF-IDF routers):**
- Purpose: Smuggle Stage 1 prediction into the TF-IDF input as token suffixes.
- Examples: `build_text_input` in `src/model_router_tier/train_tier_router.py:121`; `build_model_router_text_input` in `src/demo/demo_router.py:110`.
- Pattern: `"<origin_query> task_type_<question_type> keyword_type_<keyword_question_type>"`.

**Weak labeler / rule fallback:**
- Purpose: Dataset-name -> `question_type` mapping used to bootstrap training labels.
- Examples: `map_dataset_to_question_type` in `src/task_classifier/build_question_type.py:8`; `rule_based_question_type` in `src/task_classifier/train_task_classifier_simple.py:14`.
- Pattern: Ordered keyword lists, first-match wins, with most-specific categories first.

**Model family bucket:**
- Purpose: Coarse vendor target used by the embedding router and baseline evaluation.
- Examples: `infer_model_vendor_family` in `src/model_router/model_family.py:8`.
- Pattern: Substring matching on model name (qwen, deepseek, gpt, gemini, llama, claude, ...).

**Route mapping (`config/model_mapping.json`):**
- Purpose: Translate benchmark model labels into a display / provider / tier / api_model record with an `OTHER` fallback.
- Pattern: Flat JSON dict keyed by benchmark model name, with one reserved `OTHER` entry used by `choose_final_route`.

## Entry Points

**Two-stage demo (`src/demo/demo_router.py:421`):**
- Location: `src/demo/demo_router.py`
- Triggers: `python src/demo/demo_router.py`
- Responsibilities: Load saved artifacts + mapping, run interactive task -> model -> route loop.

**Embedding-only demo (`src/demo/demo_embedding_router.py:146`):**
- Location: `src/demo/demo_embedding_router.py`
- Triggers: `python src/demo/demo_embedding_router.py`
- Responsibilities: Load embedding router artifacts + SentenceTransformer, run interactive embedding -> model loop.

**Training scripts:**
- `python -m src.data.flatten_raw_jsons` (`src/data/flatten_raw_jsons.py:307`)
- `python -m src.data.build_classifier_dataset` (`src/data/build_classifier_dataset.py:215`)
- `python -m src.data.build_classifier_dataset_cost_aware` (`src/data/build_classifier_dataset_cost_aware.py`)
- `python src/task_classifier/build_question_type.py` (`src/task_classifier/build_question_type.py:153`)
- `python -m src.feature_extraction.build_features` (`src/feature_extraction/build_features.py:48`)
- `python src/task_classifier/train_task_classifier_robust.py` (`src/task_classifier/train_task_classifier_robust.py:553`)
- `python src/model_router_tier/build_router_dataset.py` (`src/model_router_tier/build_router_dataset.py:273`)
- `python src/model_router/build_top_model_datatset.py` (`src/model_router/build_top_model_datatset.py:117`)
- `python src/model_router_tier/train_tier_router.py` (`src/model_router_tier/train_tier_router.py:621`)
- `python src/model_router/train_model_router.py`
- `python src/model_router/train_embedding_router.py`

**Evaluation scripts:**
- `python src/evaluation/evaluate_baselines.py`
- `python src/evaluation/compare_router_results.py`

## Architectural Constraints

- **Single-process, single-thread:** Every script is a synchronous CLI. `LogisticRegression(n_jobs=-1)` is the only parallelism. No async, no servers.
- **Filesystem is the database:** Pipeline stages communicate exclusively through CSVs in `data_processed/`, `joblib` files in `models/`, and JSON in `config/`. There is no message bus, ORM, or remote store.
- **Path discovery via `__file__`:** Every training and demo script resolves `PROJECT_ROOT = os.path.abspath(os.path.join(__file__, "..", ".."))` (e.g. `src/demo/demo_router.py:14`). This couples scripts to the `src/<package>/<file>.py` directory depth — moving a script up or down a level breaks all path constants.
- **`sys.path` injection of `src/feature_extraction`:** Multiple scripts append `SRC_DIR = .../src/feature_extraction` to `sys.path` and then do `from Feature_extractor import PromptFeatureExtractor` (see `src/demo/demo_router.py:25`, `src/model_router_tier/build_router_dataset.py:24`, `src/task_classifier/train_task_classifier_robust.py:45`). Treat `Feature_extractor` as a module imported by name, not via package path.
- **No top-level package:** `src/` has no `__init__.py`. `src/data/__init__.py` and `src/feature_extraction/__init__.py` exist (the latter is empty), but the rest of the subpackages do not declare themselves as Python packages. Module-style execution (`python -m src.data.flatten_raw_jsons`) is what the docstrings recommend, but most scripts also work as bare scripts because of the `sys.path` and `PROJECT_ROOT` tricks.
- **Mixed file casing:** `src/feature_extraction/Feature_extractor.py` uses a CamelCase module name. Importers must use `from Feature_extractor import PromptFeatureExtractor` exactly.
- **Typo'd filename:** `src/model_router/build_top_model_datatset.py` (note `datatset`) is the canonical path. Do not rename without updating the run order in `ReadMe.md`.
- **Stage 1 must exist before Stage 2 dataset build:** `src/model_router_tier/build_router_dataset.py` hard-fails if `models/task_type_classifier.joblib` is missing.
- **NLTK punkt download at runtime:** `PromptFeatureExtractor._basic_text_features` triggers `nltk.download("punkt_tab")` and `nltk.download("punkt")` on first use (see `_ensure_nltk_sentence_tokenizer` at `src/feature_extraction/Feature_extractor.py:11`). Air-gapped environments must pre-seed NLTK data.
- **Global mutable state:** `_NLTK_PUNKT_READY` module-level flag in `src/feature_extraction/Feature_extractor.py:8` guards download. The `PromptFeatureExtractor` itself is not thread-safe across processes that share the NLTK cache directory.
- **CSV field-size limit raised globally:** `src/data/build_classifier_dataset.py:36` `_raise_csv_field_limit` increases `csv.field_size_limit` to `sys.maxsize` to handle long prompts. Importing this module mutates a process-wide setting.

## Anti-Patterns

### Stage-2 text input format is duplicated by string concatenation

**What happens:** The string `"<origin_query> task_type_<qt> keyword_type_<kqt>"` is constructed independently in `src/model_router_tier/train_tier_router.py:121` `build_text_input`, the Stage-2 model router training script, and `src/demo/demo_router.py:110` `build_model_router_text_input`.
**Why it's wrong:** A change to the input format in one site silently desyncs the demo from the saved vectorizer (e.g. swapping the order of `task_type_` and `keyword_type_` would change which tokens hit the TF-IDF vocabulary).
**Do this instead:** Move the format into a shared helper (e.g. `src/feature_extraction/text_inputs.py`) and import it from both training and demo paths.

### Path setup duplicated in every script

**What happens:** Every entry script recomputes `CURRENT_DIR`, `PROJECT_ROOT`, `DATA_PROCESSED_DIR`, `MODELS_DIR`, `EVALUATION_DIR` (see `src/task_classifier/train_task_classifier_robust.py:29`, `src/model_router_tier/train_tier_router.py:28`, `src/model_router/train_embedding_router.py:35`, `src/demo/demo_router.py:14`).
**Why it's wrong:** Adding a new directory or renaming `data_processed/` requires editing 10+ files. Easy to miss one and create stale outputs.
**Do this instead:** Centralize project paths in `src/paths.py` (or a `src/__init__.py`) and import them.

### Per-script `sys.path` injection

**What happens:** `src/demo/demo_router.py:25`, `src/model_router_tier/build_router_dataset.py:24`, `src/task_classifier/train_task_classifier_robust.py:45`, and `src/model_router/train_embedding_router.py:25` each append a directory to `sys.path` before importing.
**Why it's wrong:** Breaks IDE refactors and obscures the import graph. Renaming `Feature_extractor.py` would silently fail at runtime.
**Do this instead:** Make `src/feature_extraction/` a proper package (it already has `__init__.py`) and import as `from src.feature_extraction.Feature_extractor import PromptFeatureExtractor` after running scripts with `python -m`.

### Hard-coded relative paths in `build_question_type.py`

**What happens:** `src/task_classifier/build_question_type.py:4-5` defines `INPUT_CSV = "../../data_processed/classifier_training_features.csv"` (relative). All neighbouring scripts use absolute paths derived from `__file__`.
**Why it's wrong:** Running the script from anywhere other than `src/task_classifier/` errors out, and it diverges from the project's own convention.
**Do this instead:** Recompute paths from `__file__` like every other script in the repo.

### Inconsistent module casing

**What happens:** `Feature_extractor.py` uses a CamelCase module name while every other file is `snake_case`.
**Why it's wrong:** Imports look unidiomatic (`from Feature_extractor import ...`) and break on case-insensitive filesystems if renamed.
**Do this instead:** Rename to `feature_extractor.py` and update the four importers.

### Filename typo in canonical pipeline step

**What happens:** `src/model_router/build_top_model_datatset.py` is the file actually invoked, but documentation and natural reading expect `build_top_model_dataset.py`.
**Why it's wrong:** Auto-complete and grep miss the file; the `ReadMe.md` even references the non-typo name.
**Do this instead:** Rename the file and update any references; or alias via a small shim file.

## Error Handling

**Strategy:** Defensive file-existence checks at entry points; raise `FileNotFoundError` / `ValueError` / `KeyError` with messages that point at the missing artifact and which script to run first. Inside the demo REPL, exceptions are caught per-prompt so the loop continues.

**Patterns:**
- `load_joblib_artifacts` (`src/demo/demo_router.py:35`) raises `FileNotFoundError` with remediation text and `KeyError` for missing required keys.
- Training scripts check `os.path.exists(INPUT_CSV)` and raise with explicit "Run <prerequisite>.py first" hints (e.g. `src/model_router_tier/train_tier_router.py:630`).
- Data flattener uses `logging.warning` and skips malformed JSON files rather than aborting (`src/data/flatten_raw_jsons.py:103`).
- Demo loop wraps `route_prompt` in `try/except Exception` and prints the error to keep the REPL alive (`src/demo/demo_router.py:470`).

## Cross-Cutting Concerns

**Logging:**
- Data scripts use the `logging` module with timestamped formatting (`src/data/flatten_raw_jsons.py:80`).
- Training and demo scripts use plain `print(...)`.

**Validation:**
- Saved-artifact loaders enforce required-key lists.
- Training scripts validate required columns (e.g. `if "origin_query" not in df.columns: raise ValueError`).
- `_to_float` / `_coerce_number` helpers in `src/data/build_classifier_dataset.py:94` and `src/data/flatten_raw_jsons.py:119` defensively parse messy CSV cells.

**Authentication:**
- Not applicable. The demo simulates routing; `config/model_mapping.json` records whether an OpenRouter `api_model` is `openrouter_verified`, but no live API call is made.

---

*Architecture analysis: 2026-05-11*
