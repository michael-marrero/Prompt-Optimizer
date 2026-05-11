# Codebase Structure

**Analysis Date:** 2026-05-11

## Directory Layout

```
Prompt-Optimizer/
├── config/
│   └── model_mapping.json                # benchmark-model -> route metadata
│
├── data_processed/                       # tabular outputs of every pipeline stage
│   └── classifier_training.csv           # (other CSVs are regenerated locally)
│
├── data_raw/                             # (untracked) nested benchmark JSON tree
│
├── models/                               # joblib inference artifacts
│   ├── task_type_classifier.joblib
│   ├── tier_router.joblib
│   ├── model_router.joblib
│   └── embedding_router.joblib
│
├── evaluation/                           # metrics CSVs and PNG plots
│   ├── classification_metrics.csv
│   ├── misclassified_examples.csv
│   ├── tier_router_metrics.csv
│   ├── tier_router_misclassified_examples.csv
│   ├── model_router_metrics.csv
│   ├── model_router_misclassified_examples.csv
│   ├── embedding_router_metrics.csv
│   ├── embedding_router_misclassified_examples.csv
│   ├── router_comparison_summary.csv
│   ├── plots/                            # task classifier plots
│   ├── router_plots/                     # tier router plots
│   ├── model_router_plots/               # exact model router plots
│   ├── embedding_router_plots/           # embedding router plots
│   └── comparison_plots/                 # cross-router comparison plots
│
├── src/
│   ├── data/                             # CSV builders from raw JSON
│   │   ├── __init__.py
│   │   ├── flatten_raw_jsons.py
│   │   ├── build_classifier_dataset.py
│   │   └── build_classifier_dataset_cost_aware.py
│   │
│   ├── feature_extraction/               # handcrafted numeric features
│   │   ├── __init__.py                   # (empty)
│   │   ├── Feature_extractor.py          # PromptFeatureExtractor class
│   │   └── build_features.py
│   │
│   ├── task_classifier/                  # Stage 1: task type
│   │   ├── build_question_type.py        # weak labeler (dataset -> question_type)
│   │   ├── train_task_classifier_robust.py
│   │   └── train_task_classifier_simple.py
│   │
│   ├── model_router_tier/                # Stage 2a: cheap/medium/strong tier
│   │   ├── build_router_dataset.py       # applies Stage 1 -> router CSV
│   │   ├── train_tier_router.py
│   │   └── router_tier_system.py
│   │
│   ├── model_router/                     # Stage 2b: exact model
│   │   ├── build_top_model_datatset.py   # NOTE: typo in filename
│   │   ├── train_model_router.py
│   │   ├── train_embedding_router.py     # embedding-only experiment
│   │   └── model_family.py               # vendor bucket helper
│   │
│   ├── evaluation/                       # scoring & comparison
│   │   ├── evaluate_baselines.py
│   │   └── compare_router_results.py
│   │
│   └── demo/                             # interactive REPL inference
│       ├── demo_router.py                # two-stage (task -> model)
│       └── demo_embedding_router.py      # embedding-only
│
├── ReadMe.md                             # pipeline overview + run order
├── evaluation_summary.md                 # human-written evaluation notes
├── LICENSE
└── .gitattributes
```

## Directory Purposes

**`config/`:**
- Purpose: Static configuration consumed at inference time.
- Contains: One JSON mapping file.
- Key files: `config/model_mapping.json` (benchmark model name -> `display_name`, `provider`, `tier`, `api_model`, `openrouter_verified`, `notes`; includes a reserved `OTHER` fallback).

**`data_raw/`:**
- Purpose: Drop zone for the LLMRouterBench JSON tree.
- Contains: `<release>/<dataset>/<split>/<model_dir>/*.json` files (not committed).
- Key files: None tracked. See `src/data/flatten_raw_jsons.py:41` for the layout contract.

**`data_processed/`:**
- Purpose: Tabular intermediates and training datasets.
- Contains: CSV outputs of each pipeline stage. Most are regenerated locally and not committed.
- Key files: `data_processed/classifier_training.csv` (committed example). Documented full set per `ReadMe.md`: `flat_records.csv`, `classifier_training.csv`, `classifier_training_cost_aware.csv`, `classifier_training_features.csv`, `classifier_training_with_types.csv`, `router_training_dataset.csv`, `router_training_dataset_top_models.csv`, plus `*_features.csv` siblings produced by `src/feature_extraction/build_features.py`.

**`models/`:**
- Purpose: Trained inference artifacts loaded by demos and evaluation.
- Contains: One `joblib` file per trained router/classifier.
- Key files: `models/task_type_classifier.joblib`, `models/tier_router.joblib`, `models/model_router.joblib`, `models/embedding_router.joblib`.

**`evaluation/`:**
- Purpose: Outputs of training/evaluation runs — per-class metrics CSVs, misclassification CSVs, and grouped PNG plots.
- Contains: Top-level metrics CSVs plus five plot subdirectories.
- Key files:
  - Metrics CSVs: `evaluation/classification_metrics.csv`, `evaluation/tier_router_metrics.csv`, `evaluation/model_router_metrics.csv`, `evaluation/embedding_router_metrics.csv`, `evaluation/router_comparison_summary.csv`.
  - Misclassification CSVs: `evaluation/misclassified_examples.csv`, `evaluation/tier_router_misclassified_examples.csv`, `evaluation/model_router_misclassified_examples.csv`, `evaluation/embedding_router_misclassified_examples.csv`.
  - Plot dirs: `evaluation/plots/`, `evaluation/router_plots/`, `evaluation/model_router_plots/`, `evaluation/embedding_router_plots/`, `evaluation/comparison_plots/`.

**`src/`:**
- Purpose: All Python source organized by pipeline role.
- Contains: Six pipeline subpackages plus the demo subpackage (see below).

**`src/data/`:**
- Purpose: Raw-data ingestion and best-model aggregation.
- Contains: `__init__.py` (one-line docstring), `flatten_raw_jsons.py`, `build_classifier_dataset.py`, `build_classifier_dataset_cost_aware.py`.

**`src/feature_extraction/`:**
- Purpose: Handcrafted numeric feature extraction shared by every TF-IDF router and the demo.
- Contains: `__init__.py` (empty), `Feature_extractor.py` (class `PromptFeatureExtractor`), `build_features.py` (batch driver).

**`src/task_classifier/`:**
- Purpose: Stage 1 — predict task `question_type`. Includes weak labeler and two trainer variants.
- Contains: `build_question_type.py`, `train_task_classifier_robust.py` (production), `train_task_classifier_simple.py` (RandomForest baseline).
- No `__init__.py`.

**`src/model_router_tier/`:**
- Purpose: Stage 2a — predict a coarse model tier (`cheap`, `medium`, `strong`).
- Contains: `build_router_dataset.py` (applies the saved Stage 1 model), `train_tier_router.py`, `router_tier_system.py`.
- No `__init__.py`.

**`src/model_router/`:**
- Purpose: Stage 2b — predict an exact model class (top 15 + `OTHER`), plus the embedding-router experiment.
- Contains: `build_top_model_datatset.py` (note typo), `train_model_router.py`, `train_embedding_router.py`, `model_family.py`.
- No `__init__.py`.

**`src/evaluation/`:**
- Purpose: Compare saved routers against simple baselines and aggregate per-class metric CSVs into plots.
- Contains: `evaluate_baselines.py`, `compare_router_results.py`.
- No `__init__.py`.

**`src/demo/`:**
- Purpose: Interactive REPL inference demos that load saved artifacts and route one prompt at a time.
- Contains: `demo_router.py` (two-stage), `demo_embedding_router.py` (embedding-only).
- No `__init__.py`.

**`.planning/codebase/`:**
- Purpose: GSD codebase mapping outputs (this document and siblings).
- Contains: `ARCHITECTURE.md`, `STRUCTURE.md`.

## Key File Locations

**Entry Points (interactive):**
- `src/demo/demo_router.py`: Two-stage routing demo (task classifier -> model router -> mapped route).
- `src/demo/demo_embedding_router.py`: Single-stage embedding-based routing demo.

**Entry Points (training scripts, in run order):**
- `src/data/flatten_raw_jsons.py`: Step 1 — flatten `data_raw/` JSON to `data_processed/flat_records.csv`.
- `src/data/build_classifier_dataset.py`: Step 2 — aggregate best model per question -> `classifier_training.csv`.
- `src/data/build_classifier_dataset_cost_aware.py`: Step 2 alt — `best_value_model` band variant -> `classifier_training_cost_aware.csv`.
- `src/task_classifier/build_question_type.py`: Step 3 — weak labeler adds `question_type`.
- `src/feature_extraction/build_features.py`: Step 4 — adds handcrafted feature columns to every CSV.
- `src/task_classifier/train_task_classifier_robust.py`: Step 5 — train Stage 1.
- `src/model_router_tier/build_router_dataset.py`: Step 6 — apply Stage 1, write `router_training_dataset.csv`.
- `src/model_router/build_top_model_datatset.py`: Step 7 — keep top 15 model labels, group rest into `OTHER`.
- `src/model_router_tier/train_tier_router.py`: Train Stage 2a tier router.
- `src/model_router/train_model_router.py`: Step 8 — train Stage 2b exact model router.
- `src/model_router/train_embedding_router.py`: Train embedding-router experiment.

**Configuration:**
- `config/model_mapping.json`: Benchmark-model -> route metadata, used by `src/demo/demo_router.py:choose_final_route`.

**Core Logic:**
- `src/feature_extraction/Feature_extractor.py`: `PromptFeatureExtractor` (shared feature contract).
- `src/task_classifier/train_task_classifier_robust.py`: Stage 1 trainer (`train_task_type_classifier`).
- `src/model_router_tier/train_tier_router.py`: Stage 2a trainer (`train_tier_router`).
- `src/model_router/train_model_router.py`: Stage 2b trainer.
- `src/model_router/train_embedding_router.py`: Embedding-router trainer.
- `src/model_router/model_family.py`: `infer_model_vendor_family` helper.
- `src/demo/demo_router.py`: `route_prompt` orchestrator and `predict_task_type` / `predict_best_model` / `choose_final_route`.

**Testing:**
- No `tests/` directory and no `*_test.py` / `test_*.py` files. Quality is validated through evaluation CSVs and plots written under `evaluation/`.

## Naming Conventions

**Files:**
- Python files: `snake_case.py`.
  - Exception: `src/feature_extraction/Feature_extractor.py` uses a CamelCase module name (load-bearing — every importer does `from Feature_extractor import PromptFeatureExtractor`).
  - Typo: `src/model_router/build_top_model_datatset.py` is the on-disk filename. Documentation refers to `build_top_model_dataset.py` but the actual file has the extra `t`.
- Training scripts: `train_<thing>.py` (e.g. `train_tier_router.py`, `train_model_router.py`, `train_embedding_router.py`).
- Dataset builders: `build_<thing>.py` (e.g. `build_classifier_dataset.py`, `build_router_dataset.py`, `build_top_model_datatset.py`, `build_question_type.py`, `build_features.py`).
- Demos: `demo_<thing>.py`.

**Directories:**
- `snake_case/` throughout `src/` and at the repo root (`data_processed/`, `data_raw/`).
- `_plots/` suffix for per-router PNG subdirectories under `evaluation/`: `plots/`, `router_plots/`, `model_router_plots/`, `embedding_router_plots/`, `comparison_plots/`.

**Saved model artifacts:**
- `models/<router_name>.joblib`. Current set: `task_type_classifier.joblib`, `tier_router.joblib`, `model_router.joblib`, `embedding_router.joblib`.

**Metrics CSVs:**
- `evaluation/<router_name>_metrics.csv` for per-class precision/recall/F1/support tables.
- `evaluation/<router_name>_misclassified_examples.csv` for rows the router got wrong.
- `evaluation/router_comparison_summary.csv` for cross-router summaries.
- `evaluation/classification_metrics.csv` and `evaluation/misclassified_examples.csv` (no router prefix) belong to the Stage 1 task classifier.

**Plots:**
- Under `evaluation/<router_name>_plots/`, files use a `<router_name>_<plot_kind>.png` pattern, e.g. `tier_router_confusion_matrix.png`, `model_router_top_class_f1.png`, `embedding_router_prediction_confidence.png`.
- Stage 1 plots live under `evaluation/plots/` with un-prefixed names (`class_distribution.png`, `confusion_matrix.png`, `per_class_f1.png`, ...).
- Cross-router bars live under `evaluation/comparison_plots/` as `router_<metric>_comparison.png`.

**CSV columns:**
- Snake-case throughout. Stable column names shared across stages: `question_id`, `dataset`, `split`, `origin_query`, `prompt`, `best_model`, `best_score`, `best_cost`, `n_models_compared`, `models_evaluated`, `question_type`, `keyword_question_type`, `question_type_confidence`, `best_model_tier`, `best_value_model`, `best_value_score`, `best_value_cost`, `best_model_top15`.

**Python:**
- `snake_case` for functions and locals.
- `PascalCase` for classes (`PromptFeatureExtractor`, `BestCandidate`, `WalkStats`).
- `UPPER_SNAKE_CASE` for path constants and CLI defaults (`PROJECT_ROOT`, `DATA_PROCESSED_DIR`, `MODELS_DIR`, `INPUT_CSV`, `MODEL_PATH`, `EMBEDDING_MODEL_NAME`).

## Where to Add New Code

**New router (similar to tier / model router):**
- Trainer: `src/model_router/<train_new_router>.py` or `src/model_router_tier/<train_new_router>.py` depending on whether the target is exact-model or coarse tier.
- Saved artifact: `models/<new_router>.joblib` with the standard `{"model", "vectorizer", "scaler", "label_encoder", "feature_columns", "target_column"}` keys so demos can load it via `load_joblib_artifacts` (`src/demo/demo_router.py:35`).
- Metrics CSV: `evaluation/<new_router>_metrics.csv`.
- Plots: new subdirectory `evaluation/<new_router>_plots/` with `<new_router>_<plot_kind>.png` filenames.
- Add the per-class metrics file to `src/evaluation/compare_router_results.py` so it shows up in the comparison.
- If the router needs a Stage 1 signal, build its training CSV by extending `src/model_router_tier/build_router_dataset.py` or copy the pattern into a sibling builder.

**New data preprocessing stage:**
- Script: `src/data/<verb>_<noun>.py`. Follow the pattern in `src/data/build_classifier_dataset.py` (argparse, `_setup_logging`, `PROJECT_ROOT = Path(__file__).resolve().parents[2]`).
- Output: a new CSV under `data_processed/<descriptive_name>.csv`. Keep `question_id` as the join key.
- Update `ReadMe.md` "Running the Project" run order.

**New handcrafted feature:**
- Implementation: add a `_<kind>_features` method on `PromptFeatureExtractor` in `src/feature_extraction/Feature_extractor.py` and call it from `extract`.
- The new feature columns will automatically appear in every CSV produced by `src/feature_extraction/build_features.py` and will be picked up by `get_numeric_feature_columns` in each trainer (because that helper accepts any numeric column not in the explicit removal list).

**New evaluation / baseline:**
- Script: `src/evaluation/<eval_thing>.py`. Read saved artifacts from `models/`, write CSV outputs to `evaluation/`, write plots to `evaluation/comparison_plots/` (or a new `evaluation/<thing>_plots/`).
- Register the resulting CSV in `src/evaluation/compare_router_results.py` if it should be part of the cross-router table.

**New demo / front-end:**
- Script: `src/demo/<demo_name>.py`. Mirror `src/demo/demo_router.py`'s path setup so it can be run with `python src/demo/<demo_name>.py`.
- Load artifacts via `joblib.load`, instantiate `PromptFeatureExtractor` once, and wrap each prompt in `try/except Exception` inside the REPL loop.

**Shared utilities:**
- There is no dedicated `src/utils/` or `src/common/`. New shared helpers should go in `src/feature_extraction/` (if feature-related) or a new module that you also wire into the importing scripts. Prefer making `src/` a proper package and importing via `python -m` rather than expanding the `sys.path` injection pattern.

**Config:**
- Static lookup tables (model metadata, dataset -> task type) should live as JSON under `config/`. Update `src/demo/demo_router.py:choose_final_route` if the route schema changes.

## Special Directories

**`data_raw/`:**
- Purpose: Source-of-truth benchmark JSON tree (LLMRouterBench).
- Generated: No (manually populated from the benchmark).
- Committed: No (large; mentioned in `ReadMe.md` as regenerated locally).

**`data_processed/`:**
- Purpose: Intermediate CSVs produced by `src/data/*`, `src/task_classifier/build_question_type.py`, `src/feature_extraction/build_features.py`, and the router dataset builders.
- Generated: Yes (every file except possibly `classifier_training.csv`).
- Committed: Partial — only `classifier_training.csv` is currently tracked; everything else is expected to be regenerated.

**`models/`:**
- Purpose: Joblib inference artifacts.
- Generated: Yes (by training scripts).
- Committed: Yes (the four `.joblib` files are tracked so the demos work out of the box).

**`evaluation/`:**
- Purpose: Metric CSVs and PNG plots produced by training and evaluation scripts.
- Generated: Yes.
- Committed: Yes (so reviewers can see results without rerunning training). Subdirectories follow the `<router>_plots/` convention.

**`.planning/`:**
- Purpose: GSD planning artifacts (codebase maps, phase plans).
- Generated: Yes (by GSD commands).
- Committed: Yes (so other contributors can reuse the maps).

**`.claude/`, `.idea/`:**
- Purpose: Editor / agent settings.
- Generated: Yes.
- Committed: Partial (`.claude/settings.local.json` is present; `.idea/*` is partially tracked).

---

*Structure analysis: 2026-05-11*
