# Coding Conventions

**Analysis Date:** 2026-05-11

## Naming Patterns

**Files:**
- Module files are `snake_case.py`: `train_task_classifier_robust.py`, `train_model_router.py`, `train_embedding_router.py`, `train_tier_router.py`, `build_features.py`, `model_family.py`, `demo_router.py`.
- One legacy exception uses PascalCase: `src/feature_extraction/Feature_extractor.py` (note the leading capital "F"). All other modules follow snake_case. Match the surrounding module when adding new files.
- Top-level training entry points are named `train_<artifact_name>.py`. Demo entry points are named `demo_<artifact_name>.py`. Dataset builders are named `build_<artifact_name>_dataset.py` or `build_<feature_name>.py`.
- Saved model artifacts are `<artifact_name>.joblib` (e.g., `task_type_classifier.joblib`, `model_router.joblib`, `tier_router.joblib`, `embedding_router.joblib`) inside `models/`.

**Functions:**
- Public functions: `snake_case`, verb-led (e.g., `train_task_type_classifier`, `predict_user_input`, `save_router_artifacts`, `load_router_artifacts`, `get_target_column`, `build_text_input`, `plot_confusion_matrix`).
- Internal helpers are prefixed with a single underscore: `_safe_text`, `_ensure_nltk_sentence_tokenizer`, `_basic_text_features`, `_symbol_features`, `_keyword_features`, `_complexity_features`, `_constraint_features`, `_data_dir`, `_build_paths`, `_raise_csv_field_limit`.
- Plot functions are named `plot_<thing>` (`plot_class_distribution`, `plot_confusion_matrix`, `plot_top_class_f1`, `plot_prediction_confidence`). CSV report functions are named `save_<thing>_csv` or `save_<thing>_examples`.
- Use keyword-only arguments (`*,`) when a helper has many boolean flags. Example: `embeddings_cache_path(*, embedding_model_name, prepend_dataset, prepend_prompt_stub)` and `save_embedding_router_artifacts(..., *, prepend_dataset_to_query, prepend_prompt_stub, classifier_type, output_path=...)` in `src/model_router/train_embedding_router.py`.

**Variables:**
- Locals and parameters: `snake_case` (`feature_columns`, `text_data`, `numeric_features`, `label_encoder`, `target_column`, `y_pred`, `y_test`, `df_valid`, `keep_mask`).
- sklearn-conventional names are preserved: `X_train`, `X_test`, `y_train`, `y_pred`, `X_train_combined`, `X_test_num_sparse`. Capital `X` for feature matrices, lowercase `y` for targets — do not snake-case these.
- Module-level constants are `SCREAMING_SNAKE_CASE`: `CURRENT_DIR`, `PROJECT_ROOT`, `DATA_PROCESSED_DIR`, `MODELS_DIR`, `EVALUATION_DIR`, `PLOTS_DIR`, `ROUTER_PLOTS_DIR`, `EMBEDDING_PLOTS_DIR`, `INPUT_CSV`, `MODEL_PATH`, `MODEL_ROUTER_PATH`, `EMBEDDING_ROUTER_MODEL_PATH`, `EMBEDDING_MODEL_NAME`, `MIN_CLASS_SAMPLES`.
- Module-private constants use a leading underscore: `_TEXT_COLUMN`, `_SKIP_INPUT_NAMES`, `_NLTK_PUNKT_READY`, `_ROUTER_DIR`, `_MODEL_ROUTER_DIR`.

**Types:**
- Type-annotated functions use lowercase built-in/Generic forms: `list`, `dict`, `str`, `pd.DataFrame`, `pd.Series`. `dict | None` style PEP 604 unions appear in `src/demo/demo_router.py` (`extra_values: dict | None = None`).
- A single class is defined: `PromptFeatureExtractor` in `src/feature_extraction/Feature_extractor.py` (PascalCase). A single dataclass: `BestCandidate` in `src/data/build_classifier_dataset.py`.

## Code Style

**Formatting:**
- No automated formatter configured. No `pyproject.toml`, `setup.cfg`, `.pre-commit-config.yaml`, `black`, `ruff`, `flake8`, or `isort` config file exists in the repo.
- Indentation is 4 spaces, PEP 8 aligned. Files use trailing newlines and Unix line endings.
- Long sklearn metric imports are wrapped in parenthesized multi-line `from ... import (...)` blocks. Example, `src/task_classifier/train_task_classifier_robust.py` lines 12-19:
  ```python
  from sklearn.metrics import (
      accuracy_score,
      f1_score,
      classification_report,
      confusion_matrix,
      ConfusionMatrixDisplay,
      precision_recall_fscore_support,
  )
  ```
- Multi-argument calls with >3 arguments are reformatted one-per-line with a trailing comma, e.g., `LogisticRegression(max_iter=1500, class_weight="balanced", solver="saga", C=2.0, n_jobs=-1)`.
- Section headers are written as wide ASCII comment banners. This is a repeated, deliberate pattern — use it when adding new sections in training scripts:
  ```python
  # ------------------------------------------------------------
  # Path setup
  # ------------------------------------------------------------
  ```

**Linting:**
- No linter is configured. Some files include explicit `# noqa: E402` comments where path-injection requires imports after `sys.path` mutation: see `src/evaluation/evaluate_baselines.py` lines 24-25. This implies awareness of PEP 8 but no enforced toolchain.

## Import Organization

**Order:**
1. Standard library imports grouped first: `import os`, `import sys`, `import re`, `import math`, `import string`, `import json`, `import time`, `import argparse`, `import csv`, `import logging`.
2. Blank line, then third-party scientific stack: `import joblib`, `import numpy as np`, `import pandas as pd`, `import matplotlib.pyplot as plt`.
3. Blank line, then specialized third-party: `from scipy.sparse import hstack, csr_matrix`, `from sentence_transformers import SentenceTransformer`, `import nltk`.
4. Blank line, then sklearn imports grouped together: `from sklearn.feature_extraction.text import TfidfVectorizer`, `from sklearn.linear_model import LogisticRegression`, `from sklearn.model_selection import train_test_split`, `from sklearn.metrics import (...)`, `from sklearn.preprocessing import LabelEncoder, StandardScaler`, `from sklearn.pipeline import FeatureUnion`.
5. Blank line, then local first-party imports (often after a `sys.path.insert` shim): `from Feature_extractor import PromptFeatureExtractor`, `from model_family import infer_model_vendor_family`.

**Path Aliases:**
- No path aliases or package-style imports (no installed package). Local imports rely on runtime `sys.path` mutation. Pattern, used in `src/task_classifier/train_task_classifier_robust.py` (lines 45-48), `src/model_router/train_embedding_router.py` (lines 24-26), `src/demo/demo_router.py` (lines 25-26), `src/evaluation/evaluate_baselines.py` (lines 19-22):
  ```python
  if SRC_DIR not in sys.path:
      sys.path.append(SRC_DIR)
  from Feature_extractor import PromptFeatureExtractor
  ```
- `src/feature_extraction/__init__.py` exists but is effectively empty (1 line, no exports). Cross-module imports do not go through the package — they go through `sys.path` injection. When adding cross-module imports, follow the existing shim pattern.
- All filesystem paths are built with `os.path.join` from `PROJECT_ROOT` (computed via `os.path.dirname(os.path.abspath(__file__))` then `..` traversal). One newer module, `src/feature_extraction/build_features.py`, uses `pathlib.Path` instead and walks parents with `Path(__file__).resolve().parents`. `os.path.join` is the dominant convention; do not migrate existing modules to `pathlib` unless explicitly requested.

## How scikit-learn / pandas / numpy Are Used

**scikit-learn pipeline pattern (repeated across all three TF-IDF routers):**
- TF-IDF features come from a `FeatureUnion` of a word-level `TfidfVectorizer` and a char-level `TfidfVectorizer(analyzer="char_wb")`. Word ngrams `(1, 2)`, char ngrams `(3, 5)`. Char TF-IDF is justified inline (`# Char TF-IDF helps with code-like text, symbols, short tokens, and wording patterns.` in `src/task_classifier/train_task_classifier_robust.py:377-378`).
- Numeric handcrafted features are scaled with `StandardScaler` then converted with `scipy.sparse.csr_matrix` and combined with the TF-IDF sparse output via `scipy.sparse.hstack`. This sparse-stack pattern is the canonical feature combiner — see `src/task_classifier/train_task_classifier_robust.py:396-409`, `src/model_router/train_model_router.py:603-614`, `src/model_router_tier/train_tier_router.py:554-565`. Reuse this exact ordering: `fit_transform` on train, `transform` on test, then `hstack`.
- `LabelEncoder` is fitted on string labels; `inverse_transform` is used everywhere predictions are reported. When some classes are too small to stratify, the code refits `LabelEncoder` after pruning rare classes (see `src/model_router/train_model_router.py:543-564`).
- The classifier is `LogisticRegression` in every training script. Standard hyperparameters: `max_iter=1500`, `class_weight="balanced"`, `solver="saga"`, `C=2.0`, `n_jobs=-1` for TF-IDF routers. The embedding router uses `solver="lbfgs"`, `C=4.0`, `max_iter=2000`, `random_state=42` (no `n_jobs`) because dense embeddings fit faster with L-BFGS — explained in the inline comment at `src/model_router/train_embedding_router.py:607-608`.
- `train_test_split` is always called with `test_size=0.2`, `random_state=42`, `stratify=y`. The dataframe `df_valid` is passed as a parallel split target so misclassified rows can be saved with their original columns.
- Metrics reported in every training script: `accuracy_score`, `f1_score(..., average='macro')`, `f1_score(..., average='weighted')`, and `classification_report` with `target_names=label_encoder.classes_` and `zero_division=0`. Per-class metrics use `precision_recall_fscore_support` with `labels=np.arange(len(labels))` and `zero_division=0`.
- The embedding router additionally reports `top_k_accuracy_score` for k=3 and k=5 when there are enough classes (`src/model_router/train_embedding_router.py:634-655`).

**pandas usage:**
- CSVs are read with `pd.read_csv(INPUT_CSV)` (no `dtype` argument). Outputs are written with `df.to_csv(output_path, index=False)`.
- Text columns are always coerced with `.fillna("").astype(str)` (or `.fillna("unknown").astype(str)` for label-side text). Numeric features are coerced with `.fillna(0)`.
- Numeric feature selection uses `pd.api.types.is_numeric_dtype(df[col])` plus an explicit `columns_to_remove` deny-list. Pattern is duplicated across three modules: `src/task_classifier/train_task_classifier_robust.py:65-85`, `src/model_router/train_model_router.py:74-122`, `src/model_router_tier/train_tier_router.py:70-118`. When extending features, update each list separately — they are not centralized.
- Mask-based row filtering is preferred over `.query()`. Boolean masks are built with `pd.Series(...).isin(...).to_numpy()` and applied with `.iloc[keep_mask]` (after `.reset_index(drop=True)`).

**numpy usage:**
- `np.arange(len(labels))` is the standard way to enumerate label indices for sklearn metric calls.
- Embeddings are persisted as `.npy` via `np.save` / `np.load` and validated with a row-count check. See `src/model_router/train_embedding_router.py:170-203`.

## Model Training Patterns

**Standard training-script skeleton (followed by all four trainers):**
1. Module-level `# Path setup` block: compute `CURRENT_DIR`, `PROJECT_ROOT`, all data/model/evaluation/plots directories, then `os.makedirs(..., exist_ok=True)` for each writable directory.
2. Module-level constants for input CSV path and output joblib path.
3. Section: target-column helper (`get_target_column`) and feature-column helper (`get_numeric_feature_columns`).
4. Section: text-input builder (`build_text_input`) when combining `origin_query` with classifier-generated `question_type` and `keyword_question_type`. The string format is duplicated literally: `origin_query + " task_type_" + question_type + " keyword_type_" + keyword_question_type`. This format is repeated in `src/demo/demo_router.py:build_model_router_text_input` and must stay in sync.
5. Section: evaluation plots (each plot is its own function, saves a 300 dpi PNG with `plt.tight_layout`, closes the figure with `plt.close()`, and prints the output path).
6. Section: evaluation CSV writers (`save_metrics_csv`, `save_misclassified_examples`).
7. Section: artifact save/load (`save_router_artifacts`, `load_router_artifacts`).
8. Section: single-prompt prediction (`predict_user_input`).
9. Section: training function (`train_<thing>`).
10. Section: `main()` interactive loop that prompts the user for `train` / `load` mode, then enters a `while True` REPL.
11. `if __name__ == "__main__": main()` at the bottom.

**Tooling repeated in every router:**
- Plots are saved at `dpi=300`. Figure sizes vary by chart type (commonly `figsize=(8, 6)`, `(12, 6)`, or `(14, 7)` for top-N family charts). Always `plt.tight_layout()` and `plt.close()`.
- Confusion matrices for high-cardinality outputs (e.g., 100+ models) are truncated to the top N classes by support before plotting — see `plot_top_confusion_matrix` in `src/model_router/train_model_router.py:244-296` and `src/model_router/train_embedding_router.py:317-367`.
- After splitting, label counts <2 (or `< MIN_CLASS_SAMPLES = 25` in the embedding router) are pruned so `stratify=y` works.

## Persistence Patterns

**joblib for model artifacts:**
- All trained artifacts are persisted with `joblib.dump(artifacts, output_path)` where `artifacts` is a plain `dict` containing every object needed for inference. Loaded via `joblib.load(model_path)`.
- The standard artifact dictionary for TF-IDF routers contains the keys: `"model"`, `"vectorizer"`, `"scaler"`, `"label_encoder"`, `"feature_columns"`, and (for routers) `"target_column"`. See `save_router_artifacts` in `src/model_router/train_model_router.py:370-391` and `src/model_router_tier/train_tier_router.py:342-363`.
- The embedding router uses a richer artifact dict with descriptive flags (`"uses_task_classifier"`, `"uses_handcrafted_features"`, `"uses_tfidf"`, `"target_type"`, `"classifier_type"`, `"embedding_vectors_are_normalized"`, `"prepend_dataset_to_query"`, `"prepend_prompt_stub"`). It also stores `"scaler": None` for shape consistency. See `src/model_router/train_embedding_router.py:445-477`.
- Every loader checks `os.path.exists(model_path)` and raises `FileNotFoundError` with a multi-line message telling the user to run the training script. Loaders also validate `required_keys` and raise `KeyError(f"... is missing required key: {key}")` for any missing key.
- The `models/` directory holds: `task_type_classifier.joblib`, `model_router.joblib`, `tier_router.joblib`, `embedding_router.joblib`.

**Other persistence:**
- Embedding caches are saved with `np.save(embeddings_path, embeddings)` to `.npy` files in `data_processed/`. Cache filenames are slugified from the embedding model name and toggle flags (`embeddings_cache_path` in `src/model_router/train_embedding_router.py:69-81`) so toggle changes never collide with a stale cache.
- Configuration (model mapping) is loaded via plain `json.load(open(path, "r", encoding="utf-8"))` in `src/demo/demo_router.py:63-74`.

## Error Handling

**Validation errors:**
- Pre-flight column checks raise `ValueError` with a concrete message. Example, `src/task_classifier/train_task_classifier_robust.py:346-350`:
  ```python
  if "origin_query" not in df.columns:
      raise ValueError("CSV must contain an 'origin_query' column.")
  ```
- Target-column resolvers raise `ValueError` if no acceptable column is found (`get_target_column` in `src/model_router/train_model_router.py:48-69` and `src/model_router_tier/train_tier_router.py:48-63`).

**File-not-found errors:**
- Every artifact loader raises `FileNotFoundError` with a user-facing remediation hint. Example, `src/model_router/train_model_router.py:399-403`:
  ```python
  raise FileNotFoundError(
      f"No saved exact model router found at:\n{model_path}\n\n"
      "Run this script in 'train' mode first."
  )
  ```
- Same pattern in `src/data/build_classifier_dataset.py:220-221` which logs the error and exits with code 1.

**Defensive try/except:**
- The demo loop wraps `route_prompt(...)` in `try/except Exception as error` and prints the error rather than crashing (`src/demo/demo_router.py:459-472`).
- User input parsing falls back silently: `except ValueError: question_type_confidence = 0.0` in `src/model_router/train_model_router.py:738-741` and `src/model_router_tier/train_tier_router.py:690-693`.
- The embedding router's metrics block wraps `predict_proba` in `try/except AttributeError` (`src/model_router/train_embedding_router.py:644-655`).
- `src/data/build_classifier_dataset.py:42-48` iterates downward on `csv.field_size_limit` to handle Windows' overflow gracefully.

## Logging

**Two coexisting strategies:**

**`print()` for training/inference scripts.** All four training scripts and the demo rely on `print()` for progress and results. The training scripts each contain 30+ `print` calls (`train_task_classifier_robust.py`: 32, `train_model_router.py`: 46, `train_tier_router.py`: 43, `train_embedding_router.py`: 57). The convention is:
- Print a section header `print("\nExact Model Router Results")` then a dashed underline `print("--------------------------")`.
- F-string formatted metrics: `print(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")`.
- After every saved file, print `Saved <thing> to: <path>`.

**`logging` module for data pipeline scripts only.** `src/data/build_classifier_dataset.py`, `src/data/build_classifier_dataset_cost_aware.py`, and `src/data/flatten_raw_jsons.py` use the `logging` module via `logging.basicConfig(...)` and `logging.info(...)`, `logging.debug(...)`, `logging.error(...)`. These scripts are long-running CSV processors with `--verbose`/`--quiet` argparse flags that map to logging levels.

**Guideline for new code:**
- For training/inference/demo scripts, follow the surrounding files and use `print()`.
- For data pipeline scripts that ingest raw files and need progress reporting, follow the data-module pattern and use the `logging` module with `logging.basicConfig(level=...)` configurable via CLI flags.

## Type Hints

**Partial annotations.** Hints are used where they aid readability but are not enforced everywhere:
- Public helpers usually annotate parameters and return types: `def get_numeric_feature_columns(df: pd.DataFrame) -> list:`, `def build_text_input(df: pd.DataFrame) -> pd.Series:`, `def get_target_column(df: pd.DataFrame) -> str:`, `def extract(self, text: str) -> dict:`, `def infer_model_vendor_family(model_name: str) -> str:`.
- Internal helpers may omit return types (`def predict_user_input(...)` returns a tuple but is not annotated).
- The newer `src/feature_extraction/build_features.py` uses `from __future__ import annotations` and PEP 585 generics (`list[Path]`, `list[str]`). This is the most thoroughly typed module — older modules predate it.
- No `mypy.ini` or `pyrightconfig.json` exists; type hints are documentation, not enforced.

**Guideline:** Annotate parameters and return types on new public functions. Use `pd.DataFrame`, `pd.Series`, `list`, `dict`, `str`, `int`, `float`, `bool`, and `dict | None` for optionals. Do not bother annotating sklearn return tuples — none are annotated in the codebase.

## Docstring Style

**Plain-text triple-quoted docstrings.** No formal style (no Google, NumPy, or Sphinx markers — no `Args:`, `Returns:`, `Parameters`, `:param:`). Docstrings sit between the `def` line and the function body, with a blank line after them. Examples:

```python
def train_task_type_classifier(df: pd.DataFrame):
    """
    Train a task type classifier using:
    - Word-level TF-IDF features from origin_query
    - Character-level TF-IDF features from origin_query
    - Handcrafted numeric features from the feature extractor output
    """
```

```python
def get_target_column(df: pd.DataFrame) -> str:
    """
    Prefer cost-aware value tier if available.
    Fall back to absolute best model tier if needed.
    """
```

- Use bulleted lists with leading `- ` to enumerate inputs and outputs.
- Module-level docstrings (when present) describe how to invoke the script from the repo root, e.g., `src/feature_extraction/build_features.py:1-10` and `src/data/build_classifier_dataset.py:1-22`.
- Module docstrings inside `model_family.py` (`src/model_router/model_family.py:1-5`) state purpose in 1-2 sentences and end without a usage example.
- Some short single-purpose helpers (e.g., the inner plotting helpers) have no docstring — only a comment block above the function. This is acceptable when the function name is self-describing.

## Function Design

**Size:** Most functions are 10-60 lines. Training functions are the largest (130-180 lines) and intentionally contain the full sequential pipeline rather than being split into micro-functions. Plot/CSV helpers are 15-50 lines each.

**Parameters:**
- Heavy use of keyword arguments at call sites. Example, `save_router_artifacts(model=model, vectorizer=vectorizer, scaler=scaler, label_encoder=label_encoder, feature_columns=feature_columns, target_column=target_column)` in `src/model_router/train_model_router.py:653-660`.
- Default values are provided when a sensible default exists, especially for path arguments: `output_path=MODEL_ROUTER_PATH`.
- Keyword-only arguments (`*,`) gate boolean flags in newer helpers (`embeddings_cache_path`, `save_embedding_router_artifacts`).
- Single-prompt prediction functions accept long parameter lists with defaults to make them easy to call from the demo (`predict_user_input(model, vectorizer, scaler, label_encoder, feature_columns, text, question_type="unknown", keyword_question_type="unknown", question_type_confidence=0.0)`).

**Return Values:**
- Training functions return tuples of every object the caller needs (e.g., `return model, vectorizer, scaler, label_encoder, feature_columns, target_column`). The demo and `main()` block-unpack them.
- Predictors return `(prediction_label, confidence_table)` or `(prediction_label, confidence, confidence_table)`. `confidence_table` is always a list of `(label, probability)` tuples, sorted by probability descending. Reuse this shape in any new predictor.

## Module Design

**Exports:**
- No `__all__` lists. Public surface is implicit — anything not prefixed with `_` is considered public.
- `src/feature_extraction/__init__.py` is empty. `src/data/__init__.py` exists. No re-exports through package init files. Cross-module imports use direct file-name imports plus `sys.path` injection (see Import Organization above).

**Barrel Files:**
- None. There are no aggregator/barrel modules — each consumer imports the specific module it needs.

**Script vs library:**
- Every training script ends with `if __name__ == "__main__": main()` and is runnable directly. Almost every module is dual-purpose: importable for its functions and runnable as a script.
- Data pipeline scripts (`src/data/build_classifier_dataset.py`, `src/data/build_classifier_dataset_cost_aware.py`, `src/data/flatten_raw_jsons.py`) document their CLI in the module docstring and use `argparse` for flags. Training scripts do **not** use `argparse` — they prompt for `train` / `load` mode via `input()`. Follow the existing pattern when adding a new module: pipeline tools take CLI flags, training/demo tools take interactive `input()`.

---

*Convention analysis: 2026-05-11*
