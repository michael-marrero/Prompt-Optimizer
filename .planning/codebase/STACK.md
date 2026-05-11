# Technology Stack

**Analysis Date:** 2026-05-11

## Languages

**Primary:**
- Python 3 - All training, feature extraction, routing, demo, and evaluation code under `src/`
  - Uses modern syntax features: PEP 604 union types (`dict | None`, `float | int | str | None`), `from __future__ import annotations`, dataclasses, `pathlib.Path` — implies a minimum interpreter of Python 3.10 (3.10+) even though no `.python-version` or `python_requires` marker is committed.

**Secondary:**
- JSON - Configuration (`config/model_mapping.json`) and raw benchmark records (consumed by `src/data/flatten_raw_jsons.py`)
- CSV - Processed datasets and evaluation metrics (`data_processed/*.csv`, `evaluation/*.csv`)
- Markdown - `ReadMe.md`, `evaluation_summary.md`

## Runtime

**Environment:**
- CPython 3.10+ (inferred from `dict | None` style annotations in `src/demo/demo_router.py`, `src/data/flatten_raw_jsons.py`)
- No virtual-env metadata committed (no `.python-version`, no `.venv/` in tree)

**Package Manager:**
- pip (per `ReadMe.md` "Requirements" section: `pip install pandas numpy scipy scikit-learn matplotlib joblib`)
- No lockfile present: no `requirements.txt`, `requirements-*.txt`, `pyproject.toml`, `setup.py`, `setup.cfg`, `Pipfile`, `poetry.lock`, or `environment.yml` exists at the repo root.

## Frameworks

**Core ML / Numerical:**
- scikit-learn - `LogisticRegression`, `RandomForestClassifier`, `TfidfVectorizer`, `LabelEncoder`, `StandardScaler`, `FeatureUnion`, `train_test_split`, and metrics (`accuracy_score`, `f1_score`, `classification_report`, `confusion_matrix`, `ConfusionMatrixDisplay`, `precision_recall_fscore_support`, `top_k_accuracy_score`). Imported across every training/eval file (`src/task_classifier/train_task_classifier_robust.py`, `src/model_router/train_model_router.py`, `src/model_router/train_embedding_router.py`, `src/model_router_tier/train_tier_router.py`, `src/evaluation/evaluate_baselines.py`).
- pandas - DataFrame I/O and feature shaping in every module.
- NumPy - Numeric arrays; imported in all training scripts.
- SciPy - `scipy.sparse.hstack`, `csr_matrix` for stacking TF-IDF + handcrafted features (`src/demo/demo_router.py`, `src/task_classifier/train_task_classifier_robust.py`, `src/model_router/train_model_router.py`, `src/model_router_tier/train_tier_router.py`).
- joblib - Persistence of trained models to `models/*.joblib` (see "Model Artifacts" below).
- matplotlib - Saves evaluation plots to `evaluation/plots/`, `evaluation/router_plots/`, `evaluation/model_router_plots/`, `evaluation/embedding_router_plots/`, `evaluation/comparison_plots/`.

**NLP / Text:**
- NLTK - Sentence tokenization via `nltk.tokenize.sent_tokenize` in `src/feature_extraction/Feature_extractor.py`. Downloads `punkt_tab` (NLTK 3.9+) and `punkt` lazily on first use via `_ensure_nltk_sentence_tokenizer()`.
- sentence-transformers - Embedding backbone for the experimental embedding router and baseline evaluation (`src/model_router/train_embedding_router.py`, `src/demo/demo_embedding_router.py`, `src/evaluation/evaluate_baselines.py`). Pulls `SentenceTransformer` model `sentence-transformers/all-MiniLM-L6-v2` (constant `EMBEDDING_MODEL_NAME` in `src/model_router/train_embedding_router.py:54`). This is a transitive dependency on Hugging Face Transformers and PyTorch (not imported directly).

**Testing:**
- Not detected. No `tests/` directory, no `pytest.ini`, no `tox.ini`, no test files (`*_test.py` / `test_*.py`) under `src/`.

**Build/Dev:**
- Not detected. No `Makefile`, no `pyproject.toml` build config, no `Dockerfile`. Scripts are invoked directly via `python src/...` per `ReadMe.md` "Running the Project".

## Key Dependencies

**Critical (ML pipeline):**
- pandas - Tabular data plumbing (no version pin)
- numpy - Numeric backbone (no version pin)
- scipy - Sparse matrix concatenation (no version pin)
- scikit-learn - Models, vectorizers, metrics (no version pin)
- joblib - Saves/loads `models/*.joblib` artifact dictionaries (no version pin)
- matplotlib - Evaluation plotting (no version pin)
- nltk - Sentence tokenization for `sentences_count` feature; requires `punkt_tab` resource (auto-downloaded at runtime)
- sentence-transformers - Required by embedding router and baseline evaluation; downloads `all-MiniLM-L6-v2` from the Hugging Face Hub on first run

**Infrastructure / runtime support:**
- Python standard library: `os`, `sys`, `json`, `csv`, `re`, `math`, `string`, `argparse`, `logging`, `hashlib`, `time`, `pathlib`, `dataclasses`, `typing` (all imported across `src/`).

**Not present (despite the project routing to OpenRouter):**
- No `requests`, `httpx`, `aiohttp`, `urllib3`, or `openai` SDK imports anywhere under `src/`. OpenRouter integration is currently metadata-only (see `INTEGRATIONS.md`).

## Configuration

**Environment variables:**
- None read by the codebase. `grep` for `os.environ`, `os.getenv`, `API_KEY` across `src/` returns no matches. No `.env*` files exist in the repo.

**Static config files:**
- `config/model_mapping.json` - Maps benchmark model slugs (e.g. `qwen3-235b-a22b-2507`, `gpt-5`, `deepseek-v3.1-terminus`, `OTHER`) to `{display_name, provider, tier, api_model, openrouter_verified, notes}`. 16 entries: 9 with `provider: "openrouter"` (`openrouter_verified: true`), 7 with `provider: "simulated"` (`openrouter_verified: false`). Loaded by `src/demo/demo_router.py:load_json()`.

**Build:**
- No build step. Scripts are executed directly as Python modules.

## Model Artifacts (`models/`)

All models are persisted as joblib pickles of an artifact dict containing `model`, `vectorizer`, `scaler`, `label_encoder`, `feature_columns` (plus `embedding_model_name`, `target_column`, `target_type` for the embedding router).

| File | Size | Producer |
|------|------|----------|
| `models/task_type_classifier.joblib` | 1.86 MB | `src/task_classifier/train_task_classifier_robust.py` |
| `models/tier_router.joblib` | 1.21 MB | `src/model_router_tier/train_tier_router.py` |
| `models/model_router.joblib` | 4.29 MB | `src/model_router/train_model_router.py` |
| `models/embedding_router.joblib` | 54 KB | `src/model_router/train_embedding_router.py` |

The demo (`src/demo/demo_router.py`) loads `task_type_classifier.joblib` + `model_router.joblib` + `config/model_mapping.json`. The embedding-router demo (`src/demo/demo_embedding_router.py`) loads `embedding_router.joblib`.

## Dataset Formats

**Raw benchmark input:**
- Nested JSON tree under `data_raw/<release>/<dataset>/<split>/<model_dir>/<file>.json`. Each file contains top-level metadata + a `records` array (fields: `origin_query`, `prompt`, `prediction`, `ground_truth`, `score`, `prompt_tokens`, `completion_tokens`, `cost`, `instance_id`, `index`). Flattened by `src/data/flatten_raw_jsons.py` into a single CSV.
- `data_raw/` is not committed to the repo; the user regenerates it locally.

**Processed CSVs (`data_processed/`):**
- `flat_records.csv` - Output of `flatten_raw_jsons.py`, one row per (file, record) pair (fields enumerated in `CSV_FIELDS` at `src/data/flatten_raw_jsons.py:46-69`).
- `classifier_training.csv` - Per-question best-model winner; produced by `src/data/build_classifier_dataset.py`. Only this file is committed (134 bytes, git-LFS pointer).
- `classifier_training_features.csv` - Adds handcrafted features (`src/feature_extraction/build_features.py`).
- `classifier_training_with_types.csv` - Adds keyword/dataset-derived task type (`src/task_classifier/build_question_type.py`).
- `classifier_training_cost_aware.csv` - Experimental cost-aware target (`src/data/build_classifier_dataset_cost_aware.py`).
- `router_training_dataset.csv` - Router training input (`src/model_router_tier/build_router_dataset.py`).
- `router_training_dataset_top_models.csv` - Top-N grouped model target (`src/model_router/build_top_model_datatset.py`).

**Embedding cache:**
- `data_processed/emb_router_<slug>_l2_fam[_ds_prefix][_prompt_stub].npy` - NumPy embedding cache produced by `embeddings_cache_path()` in `src/model_router/train_embedding_router.py:69-81`.

## Git-LFS Tracking

**`.gitattributes` (only line):**
```
*csv filter=lfs diff=lfs merge=lfs -text
```

Every `.csv` file in the repo is stored as a git-LFS pointer rather than its real contents. Confirmed by spot-checking `data_processed/classifier_training.csv` and `evaluation/*.csv` — each file is a tiny (~128-134 byte) `version https://git-lfs.github.com/spec/v1` pointer. Working with the real data requires `git lfs pull` (or local regeneration via the pipeline steps in `ReadMe.md`).

PNG plot files under `evaluation/*/` and joblib model files under `models/` are **not** LFS-tracked — they are committed as regular Git objects.

## Platform Requirements

**Development:**
- Python 3.10+ (inferred from union-type syntax usage)
- pip
- git + git-lfs (for cloning the CSVs)
- Internet egress on first run for:
  - NLTK `punkt`/`punkt_tab` corpus download (`Feature_extractor.py:11-18`)
  - Hugging Face Hub fetch of `sentence-transformers/all-MiniLM-L6-v2` (only when running the embedding router or baseline eval)

**Production:**
- Not applicable. The repo currently produces a local CLI demo (`python src/demo/demo_router.py`); no deployment target, server, container, or hosting config is defined.

---

*Stack analysis: 2026-05-11*
