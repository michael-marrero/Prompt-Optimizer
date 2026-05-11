<!-- GSD:project-start source:PROJECT.md -->
## Project

**Prompt-Optimizer**

A quality-first prompt router behind a multi-turn chat UI. The user types into a single chat box and the system silently routes the prompt to the most efficient LLM or agent for the task — Claude Sonnet/GPT-5/Gemini via OpenRouter for conversational work, Claude Code SDK for build-and-edit coding tasks, Anthropic computer-use for browse-and-act tasks — and streams the response back. The goal is "no more manual model picking": every prompt goes to the right backend automatically. Comet/Perplexity-style auto-routing with a transparent rationale shown alongside each answer.

**Core Value:** Every prompt routes to the LLM or agent best suited to deliver a high-quality answer, with no manual model selection from the user.

### Constraints

- **Tech stack — Python pipeline:** Python 3.10+ with scikit-learn / pandas / scipy / joblib / sentence-transformers / nltk (existing — preserve compatibility with saved artifacts).
- **Tech stack — Web stack:** Next.js (TypeScript) front-end + FastAPI (Python) back-end. FastAPI is mandatory because it must load and call the existing `joblib` routing models in-process.
- **Distribution:** Open-source, runnable locally. No hosted backend, no shared infra.
- **Key handling:** Bring-your-own-keys (OpenRouter, Anthropic, optional Google). Keys never leave the user's local instance.
- **Optimization target:** Quality first, cost as tiebreaker — never optimize cost at the expense of expected answer quality.
- **Dependencies on third parties:** OpenRouter, Anthropic Claude Code SDK, Anthropic computer-use. Each adds an availability / pricing dependency outside our control.
- **No fine-tuning of generative LLMs** — we only train the small routing heads.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3 - All training, feature extraction, routing, demo, and evaluation code under `src/`
- JSON - Configuration (`config/model_mapping.json`) and raw benchmark records (consumed by `src/data/flatten_raw_jsons.py`)
- CSV - Processed datasets and evaluation metrics (`data_processed/*.csv`, `evaluation/*.csv`)
- Markdown - `ReadMe.md`, `evaluation_summary.md`
## Runtime
- CPython 3.10+ (inferred from `dict | None` style annotations in `src/demo/demo_router.py`, `src/data/flatten_raw_jsons.py`)
- No virtual-env metadata committed (no `.python-version`, no `.venv/` in tree)
- pip (per `ReadMe.md` "Requirements" section: `pip install pandas numpy scipy scikit-learn matplotlib joblib`)
- No lockfile present: no `requirements.txt`, `requirements-*.txt`, `pyproject.toml`, `setup.py`, `setup.cfg`, `Pipfile`, `poetry.lock`, or `environment.yml` exists at the repo root.
## Frameworks
- scikit-learn - `LogisticRegression`, `RandomForestClassifier`, `TfidfVectorizer`, `LabelEncoder`, `StandardScaler`, `FeatureUnion`, `train_test_split`, and metrics (`accuracy_score`, `f1_score`, `classification_report`, `confusion_matrix`, `ConfusionMatrixDisplay`, `precision_recall_fscore_support`, `top_k_accuracy_score`). Imported across every training/eval file (`src/task_classifier/train_task_classifier_robust.py`, `src/model_router/train_model_router.py`, `src/model_router/train_embedding_router.py`, `src/model_router_tier/train_tier_router.py`, `src/evaluation/evaluate_baselines.py`).
- pandas - DataFrame I/O and feature shaping in every module.
- NumPy - Numeric arrays; imported in all training scripts.
- SciPy - `scipy.sparse.hstack`, `csr_matrix` for stacking TF-IDF + handcrafted features (`src/demo/demo_router.py`, `src/task_classifier/train_task_classifier_robust.py`, `src/model_router/train_model_router.py`, `src/model_router_tier/train_tier_router.py`).
- joblib - Persistence of trained models to `models/*.joblib` (see "Model Artifacts" below).
- matplotlib - Saves evaluation plots to `evaluation/plots/`, `evaluation/router_plots/`, `evaluation/model_router_plots/`, `evaluation/embedding_router_plots/`, `evaluation/comparison_plots/`.
- NLTK - Sentence tokenization via `nltk.tokenize.sent_tokenize` in `src/feature_extraction/Feature_extractor.py`. Downloads `punkt_tab` (NLTK 3.9+) and `punkt` lazily on first use via `_ensure_nltk_sentence_tokenizer()`.
- sentence-transformers - Embedding backbone for the experimental embedding router and baseline evaluation (`src/model_router/train_embedding_router.py`, `src/demo/demo_embedding_router.py`, `src/evaluation/evaluate_baselines.py`). Pulls `SentenceTransformer` model `sentence-transformers/all-MiniLM-L6-v2` (constant `EMBEDDING_MODEL_NAME` in `src/model_router/train_embedding_router.py:54`). This is a transitive dependency on Hugging Face Transformers and PyTorch (not imported directly).
- Not detected. No `tests/` directory, no `pytest.ini`, no `tox.ini`, no test files (`*_test.py` / `test_*.py`) under `src/`.
- Not detected. No `Makefile`, no `pyproject.toml` build config, no `Dockerfile`. Scripts are invoked directly via `python src/...` per `ReadMe.md` "Running the Project".
## Key Dependencies
- pandas - Tabular data plumbing (no version pin)
- numpy - Numeric backbone (no version pin)
- scipy - Sparse matrix concatenation (no version pin)
- scikit-learn - Models, vectorizers, metrics (no version pin)
- joblib - Saves/loads `models/*.joblib` artifact dictionaries (no version pin)
- matplotlib - Evaluation plotting (no version pin)
- nltk - Sentence tokenization for `sentences_count` feature; requires `punkt_tab` resource (auto-downloaded at runtime)
- sentence-transformers - Required by embedding router and baseline evaluation; downloads `all-MiniLM-L6-v2` from the Hugging Face Hub on first run
- Python standard library: `os`, `sys`, `json`, `csv`, `re`, `math`, `string`, `argparse`, `logging`, `hashlib`, `time`, `pathlib`, `dataclasses`, `typing` (all imported across `src/`).
- No `requests`, `httpx`, `aiohttp`, `urllib3`, or `openai` SDK imports anywhere under `src/`. OpenRouter integration is currently metadata-only (see `INTEGRATIONS.md`).
## Configuration
- None read by the codebase. `grep` for `os.environ`, `os.getenv`, `API_KEY` across `src/` returns no matches. No `.env*` files exist in the repo.
- `config/model_mapping.json` - Maps benchmark model slugs (e.g. `qwen3-235b-a22b-2507`, `gpt-5`, `deepseek-v3.1-terminus`, `OTHER`) to `{display_name, provider, tier, api_model, openrouter_verified, notes}`. 16 entries: 9 with `provider: "openrouter"` (`openrouter_verified: true`), 7 with `provider: "simulated"` (`openrouter_verified: false`). Loaded by `src/demo/demo_router.py:load_json()`.
- No build step. Scripts are executed directly as Python modules.
## Model Artifacts (`models/`)
| File | Size | Producer |
|------|------|----------|
| `models/task_type_classifier.joblib` | 1.86 MB | `src/task_classifier/train_task_classifier_robust.py` |
| `models/tier_router.joblib` | 1.21 MB | `src/model_router_tier/train_tier_router.py` |
| `models/model_router.joblib` | 4.29 MB | `src/model_router/train_model_router.py` |
| `models/embedding_router.joblib` | 54 KB | `src/model_router/train_embedding_router.py` |
## Dataset Formats
- Nested JSON tree under `data_raw/<release>/<dataset>/<split>/<model_dir>/<file>.json`. Each file contains top-level metadata + a `records` array (fields: `origin_query`, `prompt`, `prediction`, `ground_truth`, `score`, `prompt_tokens`, `completion_tokens`, `cost`, `instance_id`, `index`). Flattened by `src/data/flatten_raw_jsons.py` into a single CSV.
- `data_raw/` is not committed to the repo; the user regenerates it locally.
- `flat_records.csv` - Output of `flatten_raw_jsons.py`, one row per (file, record) pair (fields enumerated in `CSV_FIELDS` at `src/data/flatten_raw_jsons.py:46-69`).
- `classifier_training.csv` - Per-question best-model winner; produced by `src/data/build_classifier_dataset.py`. Only this file is committed (134 bytes, git-LFS pointer).
- `classifier_training_features.csv` - Adds handcrafted features (`src/feature_extraction/build_features.py`).
- `classifier_training_with_types.csv` - Adds keyword/dataset-derived task type (`src/task_classifier/build_question_type.py`).
- `classifier_training_cost_aware.csv` - Experimental cost-aware target (`src/data/build_classifier_dataset_cost_aware.py`).
- `router_training_dataset.csv` - Router training input (`src/model_router_tier/build_router_dataset.py`).
- `router_training_dataset_top_models.csv` - Top-N grouped model target (`src/model_router/build_top_model_datatset.py`).
- `data_processed/emb_router_<slug>_l2_fam[_ds_prefix][_prompt_stub].npy` - NumPy embedding cache produced by `embeddings_cache_path()` in `src/model_router/train_embedding_router.py:69-81`.
## Git-LFS Tracking
## Platform Requirements
- Python 3.10+ (inferred from union-type syntax usage)
- pip
- git + git-lfs (for cloning the CSVs)
- Internet egress on first run for:
- Not applicable. The repo currently produces a local CLI demo (`python src/demo/demo_router.py`); no deployment target, server, container, or hosting config is defined.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Module files are `snake_case.py`: `train_task_classifier_robust.py`, `train_model_router.py`, `train_embedding_router.py`, `train_tier_router.py`, `build_features.py`, `model_family.py`, `demo_router.py`.
- One legacy exception uses PascalCase: `src/feature_extraction/Feature_extractor.py` (note the leading capital "F"). All other modules follow snake_case. Match the surrounding module when adding new files.
- Top-level training entry points are named `train_<artifact_name>.py`. Demo entry points are named `demo_<artifact_name>.py`. Dataset builders are named `build_<artifact_name>_dataset.py` or `build_<feature_name>.py`.
- Saved model artifacts are `<artifact_name>.joblib` (e.g., `task_type_classifier.joblib`, `model_router.joblib`, `tier_router.joblib`, `embedding_router.joblib`) inside `models/`.
- Public functions: `snake_case`, verb-led (e.g., `train_task_type_classifier`, `predict_user_input`, `save_router_artifacts`, `load_router_artifacts`, `get_target_column`, `build_text_input`, `plot_confusion_matrix`).
- Internal helpers are prefixed with a single underscore: `_safe_text`, `_ensure_nltk_sentence_tokenizer`, `_basic_text_features`, `_symbol_features`, `_keyword_features`, `_complexity_features`, `_constraint_features`, `_data_dir`, `_build_paths`, `_raise_csv_field_limit`.
- Plot functions are named `plot_<thing>` (`plot_class_distribution`, `plot_confusion_matrix`, `plot_top_class_f1`, `plot_prediction_confidence`). CSV report functions are named `save_<thing>_csv` or `save_<thing>_examples`.
- Use keyword-only arguments (`*,`) when a helper has many boolean flags. Example: `embeddings_cache_path(*, embedding_model_name, prepend_dataset, prepend_prompt_stub)` and `save_embedding_router_artifacts(..., *, prepend_dataset_to_query, prepend_prompt_stub, classifier_type, output_path=...)` in `src/model_router/train_embedding_router.py`.
- Locals and parameters: `snake_case` (`feature_columns`, `text_data`, `numeric_features`, `label_encoder`, `target_column`, `y_pred`, `y_test`, `df_valid`, `keep_mask`).
- sklearn-conventional names are preserved: `X_train`, `X_test`, `y_train`, `y_pred`, `X_train_combined`, `X_test_num_sparse`. Capital `X` for feature matrices, lowercase `y` for targets — do not snake-case these.
- Module-level constants are `SCREAMING_SNAKE_CASE`: `CURRENT_DIR`, `PROJECT_ROOT`, `DATA_PROCESSED_DIR`, `MODELS_DIR`, `EVALUATION_DIR`, `PLOTS_DIR`, `ROUTER_PLOTS_DIR`, `EMBEDDING_PLOTS_DIR`, `INPUT_CSV`, `MODEL_PATH`, `MODEL_ROUTER_PATH`, `EMBEDDING_ROUTER_MODEL_PATH`, `EMBEDDING_MODEL_NAME`, `MIN_CLASS_SAMPLES`.
- Module-private constants use a leading underscore: `_TEXT_COLUMN`, `_SKIP_INPUT_NAMES`, `_NLTK_PUNKT_READY`, `_ROUTER_DIR`, `_MODEL_ROUTER_DIR`.
- Type-annotated functions use lowercase built-in/Generic forms: `list`, `dict`, `str`, `pd.DataFrame`, `pd.Series`. `dict | None` style PEP 604 unions appear in `src/demo/demo_router.py` (`extra_values: dict | None = None`).
- A single class is defined: `PromptFeatureExtractor` in `src/feature_extraction/Feature_extractor.py` (PascalCase). A single dataclass: `BestCandidate` in `src/data/build_classifier_dataset.py`.
## Code Style
- No automated formatter configured. No `pyproject.toml`, `setup.cfg`, `.pre-commit-config.yaml`, `black`, `ruff`, `flake8`, or `isort` config file exists in the repo.
- Indentation is 4 spaces, PEP 8 aligned. Files use trailing newlines and Unix line endings.
- Long sklearn metric imports are wrapped in parenthesized multi-line `from ... import (...)` blocks. Example, `src/task_classifier/train_task_classifier_robust.py` lines 12-19:
- Multi-argument calls with >3 arguments are reformatted one-per-line with a trailing comma, e.g., `LogisticRegression(max_iter=1500, class_weight="balanced", solver="saga", C=2.0, n_jobs=-1)`.
- Section headers are written as wide ASCII comment banners. This is a repeated, deliberate pattern — use it when adding new sections in training scripts:
- No linter is configured. Some files include explicit `# noqa: E402` comments where path-injection requires imports after `sys.path` mutation: see `src/evaluation/evaluate_baselines.py` lines 24-25. This implies awareness of PEP 8 but no enforced toolchain.
## Import Organization
- No path aliases or package-style imports (no installed package). Local imports rely on runtime `sys.path` mutation. Pattern, used in `src/task_classifier/train_task_classifier_robust.py` (lines 45-48), `src/model_router/train_embedding_router.py` (lines 24-26), `src/demo/demo_router.py` (lines 25-26), `src/evaluation/evaluate_baselines.py` (lines 19-22):
- `src/feature_extraction/__init__.py` exists but is effectively empty (1 line, no exports). Cross-module imports do not go through the package — they go through `sys.path` injection. When adding cross-module imports, follow the existing shim pattern.
- All filesystem paths are built with `os.path.join` from `PROJECT_ROOT` (computed via `os.path.dirname(os.path.abspath(__file__))` then `..` traversal). One newer module, `src/feature_extraction/build_features.py`, uses `pathlib.Path` instead and walks parents with `Path(__file__).resolve().parents`. `os.path.join` is the dominant convention; do not migrate existing modules to `pathlib` unless explicitly requested.
## How scikit-learn / pandas / numpy Are Used
- TF-IDF features come from a `FeatureUnion` of a word-level `TfidfVectorizer` and a char-level `TfidfVectorizer(analyzer="char_wb")`. Word ngrams `(1, 2)`, char ngrams `(3, 5)`. Char TF-IDF is justified inline (`# Char TF-IDF helps with code-like text, symbols, short tokens, and wording patterns.` in `src/task_classifier/train_task_classifier_robust.py:377-378`).
- Numeric handcrafted features are scaled with `StandardScaler` then converted with `scipy.sparse.csr_matrix` and combined with the TF-IDF sparse output via `scipy.sparse.hstack`. This sparse-stack pattern is the canonical feature combiner — see `src/task_classifier/train_task_classifier_robust.py:396-409`, `src/model_router/train_model_router.py:603-614`, `src/model_router_tier/train_tier_router.py:554-565`. Reuse this exact ordering: `fit_transform` on train, `transform` on test, then `hstack`.
- `LabelEncoder` is fitted on string labels; `inverse_transform` is used everywhere predictions are reported. When some classes are too small to stratify, the code refits `LabelEncoder` after pruning rare classes (see `src/model_router/train_model_router.py:543-564`).
- The classifier is `LogisticRegression` in every training script. Standard hyperparameters: `max_iter=1500`, `class_weight="balanced"`, `solver="saga"`, `C=2.0`, `n_jobs=-1` for TF-IDF routers. The embedding router uses `solver="lbfgs"`, `C=4.0`, `max_iter=2000`, `random_state=42` (no `n_jobs`) because dense embeddings fit faster with L-BFGS — explained in the inline comment at `src/model_router/train_embedding_router.py:607-608`.
- `train_test_split` is always called with `test_size=0.2`, `random_state=42`, `stratify=y`. The dataframe `df_valid` is passed as a parallel split target so misclassified rows can be saved with their original columns.
- Metrics reported in every training script: `accuracy_score`, `f1_score(..., average='macro')`, `f1_score(..., average='weighted')`, and `classification_report` with `target_names=label_encoder.classes_` and `zero_division=0`. Per-class metrics use `precision_recall_fscore_support` with `labels=np.arange(len(labels))` and `zero_division=0`.
- The embedding router additionally reports `top_k_accuracy_score` for k=3 and k=5 when there are enough classes (`src/model_router/train_embedding_router.py:634-655`).
- CSVs are read with `pd.read_csv(INPUT_CSV)` (no `dtype` argument). Outputs are written with `df.to_csv(output_path, index=False)`.
- Text columns are always coerced with `.fillna("").astype(str)` (or `.fillna("unknown").astype(str)` for label-side text). Numeric features are coerced with `.fillna(0)`.
- Numeric feature selection uses `pd.api.types.is_numeric_dtype(df[col])` plus an explicit `columns_to_remove` deny-list. Pattern is duplicated across three modules: `src/task_classifier/train_task_classifier_robust.py:65-85`, `src/model_router/train_model_router.py:74-122`, `src/model_router_tier/train_tier_router.py:70-118`. When extending features, update each list separately — they are not centralized.
- Mask-based row filtering is preferred over `.query()`. Boolean masks are built with `pd.Series(...).isin(...).to_numpy()` and applied with `.iloc[keep_mask]` (after `.reset_index(drop=True)`).
- `np.arange(len(labels))` is the standard way to enumerate label indices for sklearn metric calls.
- Embeddings are persisted as `.npy` via `np.save` / `np.load` and validated with a row-count check. See `src/model_router/train_embedding_router.py:170-203`.
## Model Training Patterns
- Plots are saved at `dpi=300`. Figure sizes vary by chart type (commonly `figsize=(8, 6)`, `(12, 6)`, or `(14, 7)` for top-N family charts). Always `plt.tight_layout()` and `plt.close()`.
- Confusion matrices for high-cardinality outputs (e.g., 100+ models) are truncated to the top N classes by support before plotting — see `plot_top_confusion_matrix` in `src/model_router/train_model_router.py:244-296` and `src/model_router/train_embedding_router.py:317-367`.
- After splitting, label counts <2 (or `< MIN_CLASS_SAMPLES = 25` in the embedding router) are pruned so `stratify=y` works.
## Persistence Patterns
- All trained artifacts are persisted with `joblib.dump(artifacts, output_path)` where `artifacts` is a plain `dict` containing every object needed for inference. Loaded via `joblib.load(model_path)`.
- The standard artifact dictionary for TF-IDF routers contains the keys: `"model"`, `"vectorizer"`, `"scaler"`, `"label_encoder"`, `"feature_columns"`, and (for routers) `"target_column"`. See `save_router_artifacts` in `src/model_router/train_model_router.py:370-391` and `src/model_router_tier/train_tier_router.py:342-363`.
- The embedding router uses a richer artifact dict with descriptive flags (`"uses_task_classifier"`, `"uses_handcrafted_features"`, `"uses_tfidf"`, `"target_type"`, `"classifier_type"`, `"embedding_vectors_are_normalized"`, `"prepend_dataset_to_query"`, `"prepend_prompt_stub"`). It also stores `"scaler": None` for shape consistency. See `src/model_router/train_embedding_router.py:445-477`.
- Every loader checks `os.path.exists(model_path)` and raises `FileNotFoundError` with a multi-line message telling the user to run the training script. Loaders also validate `required_keys` and raise `KeyError(f"... is missing required key: {key}")` for any missing key.
- The `models/` directory holds: `task_type_classifier.joblib`, `model_router.joblib`, `tier_router.joblib`, `embedding_router.joblib`.
- Embedding caches are saved with `np.save(embeddings_path, embeddings)` to `.npy` files in `data_processed/`. Cache filenames are slugified from the embedding model name and toggle flags (`embeddings_cache_path` in `src/model_router/train_embedding_router.py:69-81`) so toggle changes never collide with a stale cache.
- Configuration (model mapping) is loaded via plain `json.load(open(path, "r", encoding="utf-8"))` in `src/demo/demo_router.py:63-74`.
## Error Handling
- Pre-flight column checks raise `ValueError` with a concrete message. Example, `src/task_classifier/train_task_classifier_robust.py:346-350`:
- Target-column resolvers raise `ValueError` if no acceptable column is found (`get_target_column` in `src/model_router/train_model_router.py:48-69` and `src/model_router_tier/train_tier_router.py:48-63`).
- Every artifact loader raises `FileNotFoundError` with a user-facing remediation hint. Example, `src/model_router/train_model_router.py:399-403`:
- Same pattern in `src/data/build_classifier_dataset.py:220-221` which logs the error and exits with code 1.
- The demo loop wraps `route_prompt(...)` in `try/except Exception as error` and prints the error rather than crashing (`src/demo/demo_router.py:459-472`).
- User input parsing falls back silently: `except ValueError: question_type_confidence = 0.0` in `src/model_router/train_model_router.py:738-741` and `src/model_router_tier/train_tier_router.py:690-693`.
- The embedding router's metrics block wraps `predict_proba` in `try/except AttributeError` (`src/model_router/train_embedding_router.py:644-655`).
- `src/data/build_classifier_dataset.py:42-48` iterates downward on `csv.field_size_limit` to handle Windows' overflow gracefully.
## Logging
- Print a section header `print("\nExact Model Router Results")` then a dashed underline `print("--------------------------")`.
- F-string formatted metrics: `print(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")`.
- After every saved file, print `Saved <thing> to: <path>`.
- For training/inference/demo scripts, follow the surrounding files and use `print()`.
- For data pipeline scripts that ingest raw files and need progress reporting, follow the data-module pattern and use the `logging` module with `logging.basicConfig(level=...)` configurable via CLI flags.
## Type Hints
- Public helpers usually annotate parameters and return types: `def get_numeric_feature_columns(df: pd.DataFrame) -> list:`, `def build_text_input(df: pd.DataFrame) -> pd.Series:`, `def get_target_column(df: pd.DataFrame) -> str:`, `def extract(self, text: str) -> dict:`, `def infer_model_vendor_family(model_name: str) -> str:`.
- Internal helpers may omit return types (`def predict_user_input(...)` returns a tuple but is not annotated).
- The newer `src/feature_extraction/build_features.py` uses `from __future__ import annotations` and PEP 585 generics (`list[Path]`, `list[str]`). This is the most thoroughly typed module — older modules predate it.
- No `mypy.ini` or `pyrightconfig.json` exists; type hints are documentation, not enforced.
## Docstring Style
- Use bulleted lists with leading `- ` to enumerate inputs and outputs.
- Module-level docstrings (when present) describe how to invoke the script from the repo root, e.g., `src/feature_extraction/build_features.py:1-10` and `src/data/build_classifier_dataset.py:1-22`.
- Module docstrings inside `model_family.py` (`src/model_router/model_family.py:1-5`) state purpose in 1-2 sentences and end without a usage example.
- Some short single-purpose helpers (e.g., the inner plotting helpers) have no docstring — only a comment block above the function. This is acceptable when the function name is self-describing.
## Function Design
- Heavy use of keyword arguments at call sites. Example, `save_router_artifacts(model=model, vectorizer=vectorizer, scaler=scaler, label_encoder=label_encoder, feature_columns=feature_columns, target_column=target_column)` in `src/model_router/train_model_router.py:653-660`.
- Default values are provided when a sensible default exists, especially for path arguments: `output_path=MODEL_ROUTER_PATH`.
- Keyword-only arguments (`*,`) gate boolean flags in newer helpers (`embeddings_cache_path`, `save_embedding_router_artifacts`).
- Single-prompt prediction functions accept long parameter lists with defaults to make them easy to call from the demo (`predict_user_input(model, vectorizer, scaler, label_encoder, feature_columns, text, question_type="unknown", keyword_question_type="unknown", question_type_confidence=0.0)`).
- Training functions return tuples of every object the caller needs (e.g., `return model, vectorizer, scaler, label_encoder, feature_columns, target_column`). The demo and `main()` block-unpack them.
- Predictors return `(prediction_label, confidence_table)` or `(prediction_label, confidence, confidence_table)`. `confidence_table` is always a list of `(label, probability)` tuples, sorted by probability descending. Reuse this shape in any new predictor.
## Module Design
- No `__all__` lists. Public surface is implicit — anything not prefixed with `_` is considered public.
- `src/feature_extraction/__init__.py` is empty. `src/data/__init__.py` exists. No re-exports through package init files. Cross-module imports use direct file-name imports plus `sys.path` injection (see Import Organization above).
- None. There are no aggregator/barrel modules — each consumer imports the specific module it needs.
- Every training script ends with `if __name__ == "__main__": main()` and is runnable directly. Almost every module is dual-purpose: importable for its functions and runnable as a script.
- Data pipeline scripts (`src/data/build_classifier_dataset.py`, `src/data/build_classifier_dataset_cost_aware.py`, `src/data/flatten_raw_jsons.py`) document their CLI in the module docstring and use `argparse` for flags. Training scripts do **not** use `argparse` — they prompt for `train` / `load` mode via `input()`. Follow the existing pattern when adding a new module: pipeline tools take CLI flags, training/demo tools take interactive `input()`.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## System Overview
```text
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
- Each pipeline stage is a standalone Python script that reads a CSV under `data_processed/`, writes a new CSV, and (for training scripts) writes a `joblib` artifact under `models/` plus evaluation plots/CSVs under `evaluation/`.
- Training and inference share one feature contract: `PromptFeatureExtractor` from `src/feature_extraction/Feature_extractor.py`. Saved `joblib` files carry the `feature_columns` list so inference can reproduce the exact training feature matrix.
- TF-IDF stack is consistent across Stage-1 and Stage-2 TF-IDF routers: `FeatureUnion([word_tfidf(1-2gram), char_tfidf(3-5gram)])` ⊕ scaled handcrafted numerics ⊕ `LogisticRegression(class_weight="balanced", solver="saga")`.
- The embedding router is a parallel branch that bypasses TF-IDF and handcrafted features entirely (`sentence-transformers/all-MiniLM-L6-v2`).
- No web framework, no DB, no API client — everything is local CSV/joblib/JSON I/O. The demo is a `while True: input(...)` REPL.
## Layers
- Purpose: Convert raw benchmark JSON into tabular CSVs and aggregate per-question best-model labels.
- Location: `src/data/`
- Contains: `flatten_raw_jsons.py`, `build_classifier_dataset.py`, `build_classifier_dataset_cost_aware.py`
- Depends on: filesystem (`data_raw/`), `csv`, `json`, `pathlib`
- Used by: feature extraction, weak labeling
- Purpose: Compute deterministic numeric features from prompt strings.
- Location: `src/feature_extraction/`
- Contains: `Feature_extractor.py` (`PromptFeatureExtractor`), `build_features.py`
- Depends on: `nltk` (punkt/punkt_tab), `pandas`, `re`
- Used by: every Stage-1 and Stage-2 TF-IDF training script and `src/demo/demo_router.py`
- Purpose: Predict broad task type (coding, math, writing, ...).
- Location: `src/task_classifier/`
- Contains: `build_question_type.py` (weak labeler), `train_task_classifier_robust.py` (production), `train_task_classifier_simple.py` (baseline)
- Depends on: feature extraction layer, scikit-learn, joblib
- Used by: router dataset builder, two-stage demo
- Purpose: Predict either an exact model class or a coarse tier from prompt + Stage 1 signal.
- Location: `src/model_router/`, `src/model_router_tier/`
- Contains: dataset builders, three trainers (`train_tier_router.py`, `train_model_router.py`, `train_embedding_router.py`)
- Depends on: Stage 1 artifact (`models/task_type_classifier.joblib`), feature extraction layer, scikit-learn, sentence-transformers (embedding router only)
- Used by: evaluation comparison, demo routers
- Purpose: Score the saved routers against baselines, write metrics CSVs and comparison plots.
- Location: `src/evaluation/`
- Contains: `evaluate_baselines.py`, `compare_router_results.py`
- Depends on: saved routers and metric CSVs produced by training scripts
- Used by: `evaluation_summary.md` (manual aggregation)
- Purpose: Interactive CLI that loads saved artifacts and routes one prompt at a time.
- Location: `src/demo/`
- Contains: `demo_router.py` (full two-stage), `demo_embedding_router.py` (semantic single-stage)
- Depends on: `models/*.joblib`, `config/model_mapping.json`, `src/feature_extraction/Feature_extractor.py` (added to `sys.path` at runtime)
- Used by: end user (interactive REPL)
## Data Flow
### Primary Request Path (Training)
### Primary Request Path (Inference / Demo)
### Embedding Demo Flow
- All state is on disk. Each script is idempotent over its outputs and reloads artifacts on every run.
- Demos hold the loaded artifacts + `PromptFeatureExtractor` instance in local function scope for the REPL session.
## Key Abstractions
- Purpose: Single class that produces the canonical numeric feature dict for every prompt.
- Examples: `src/feature_extraction/Feature_extractor.py:30`.
- Pattern: One `extract(text) -> dict` method composed of `_basic_text_features`, `_symbol_features`, `_keyword_features`, `_complexity_features`, `_constraint_features`. Keyword groups stored on the instance.
- Purpose: Self-contained inference bundle.
- Examples: `models/task_type_classifier.joblib`, `models/tier_router.joblib`, `models/model_router.joblib`.
- Pattern: `joblib.dump({"model", "vectorizer", "scaler", "label_encoder", "feature_columns", [optional "target_column"]}, path)`. Loaders validate required keys (see `load_joblib_artifacts` in `src/demo/demo_router.py:35`).
- Purpose: Embedding-only inference bundle.
- Examples: `models/embedding_router.joblib`.
- Pattern: `{"model", "scaler", "label_encoder", "target_column", "embedding_model_name", ...}` (see `load_embedding_router_artifacts` in `src/demo/demo_embedding_router.py:29`).
- Purpose: Smuggle Stage 1 prediction into the TF-IDF input as token suffixes.
- Examples: `build_text_input` in `src/model_router_tier/train_tier_router.py:121`; `build_model_router_text_input` in `src/demo/demo_router.py:110`.
- Pattern: `"<origin_query> task_type_<question_type> keyword_type_<keyword_question_type>"`.
- Purpose: Dataset-name -> `question_type` mapping used to bootstrap training labels.
- Examples: `map_dataset_to_question_type` in `src/task_classifier/build_question_type.py:8`; `rule_based_question_type` in `src/task_classifier/train_task_classifier_simple.py:14`.
- Pattern: Ordered keyword lists, first-match wins, with most-specific categories first.
- Purpose: Coarse vendor target used by the embedding router and baseline evaluation.
- Examples: `infer_model_vendor_family` in `src/model_router/model_family.py:8`.
- Pattern: Substring matching on model name (qwen, deepseek, gpt, gemini, llama, claude, ...).
- Purpose: Translate benchmark model labels into a display / provider / tier / api_model record with an `OTHER` fallback.
- Pattern: Flat JSON dict keyed by benchmark model name, with one reserved `OTHER` entry used by `choose_final_route`.
## Entry Points
- Location: `src/demo/demo_router.py`
- Triggers: `python src/demo/demo_router.py`
- Responsibilities: Load saved artifacts + mapping, run interactive task -> model -> route loop.
- Location: `src/demo/demo_embedding_router.py`
- Triggers: `python src/demo/demo_embedding_router.py`
- Responsibilities: Load embedding router artifacts + SentenceTransformer, run interactive embedding -> model loop.
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
### Path setup duplicated in every script
### Per-script `sys.path` injection
### Hard-coded relative paths in `build_question_type.py`
### Inconsistent module casing
### Filename typo in canonical pipeline step
## Error Handling
- `load_joblib_artifacts` (`src/demo/demo_router.py:35`) raises `FileNotFoundError` with remediation text and `KeyError` for missing required keys.
- Training scripts check `os.path.exists(INPUT_CSV)` and raise with explicit "Run <prerequisite>.py first" hints (e.g. `src/model_router_tier/train_tier_router.py:630`).
- Data flattener uses `logging.warning` and skips malformed JSON files rather than aborting (`src/data/flatten_raw_jsons.py:103`).
- Demo loop wraps `route_prompt` in `try/except Exception` and prints the error to keep the REPL alive (`src/demo/demo_router.py:470`).
## Cross-Cutting Concerns
- Data scripts use the `logging` module with timestamped formatting (`src/data/flatten_raw_jsons.py:80`).
- Training and demo scripts use plain `print(...)`.
- Saved-artifact loaders enforce required-key lists.
- Training scripts validate required columns (e.g. `if "origin_query" not in df.columns: raise ValueError`).
- `_to_float` / `_coerce_number` helpers in `src/data/build_classifier_dataset.py:94` and `src/data/flatten_raw_jsons.py:119` defensively parse messy CSV cells.
- Not applicable. The demo simulates routing; `config/model_mapping.json` records whether an OpenRouter `api_model` is `openrouter_verified`, but no live API call is made.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
