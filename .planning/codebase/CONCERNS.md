# Codebase Concerns

**Analysis Date:** 2026-05-11

## Tech Debt

**No dependency manifest (HIGH):**
- Issue: The repo has no `requirements.txt`, `pyproject.toml`, `setup.py`, `setup.cfg`, `Pipfile`, `Pipfile.lock`, `poetry.lock`, `environment.yml`, or any other dependency manifest. A new collaborator has no canonical list of packages and no version pins.
- Files: repo root (verified absent via `ls` and `find -maxdepth 3`)
- Impact: Non-reproducible environment. Source code transitively imports `pandas`, `numpy`, `scipy`, `scikit-learn`, `matplotlib`, `joblib`, `nltk`, and `sentence-transformers` (`src/feature_extraction/Feature_extractor.py:5`, `src/model_router/train_embedding_router.py:9`, `src/demo/demo_embedding_router.py:7`, etc.). Versions are unspecified, so artifacts trained on one sklearn/scipy combination may break on another.
- Fix approach: Add a `requirements.txt` (or `pyproject.toml`) with at least the top-level imports pinned to the versions actually used to train the committed `models/*.joblib`. Add a `python-version` constraint (`__pycache__` mixes `cpython-38` and `cpython-312` artifacts — see below).

**Trained model artifacts committed to git (MEDIUM):**
- Issue: All four `*.joblib` model artifacts are stored in-repo, not in LFS or an artifact store.
- Files: `models/embedding_router.joblib` (54 KB), `models/model_router.joblib` (4.1 MB), `models/task_type_classifier.joblib` (1.8 MB), `models/tier_router.joblib` (1.2 MB)
- Impact: ~7 MB of binary blobs bloat the git history every retrain. They are not LFS-tracked (`.gitattributes` only configures `*csv filter=lfs`). Joblib artifacts are also tightly coupled to specific scikit-learn / numpy / scipy versions — without a pinned environment (see above) they may silently fail or produce different predictions.
- Fix approach: Either move `models/*.joblib` behind git-LFS by extending `.gitattributes` (`*.joblib filter=lfs diff=lfs merge=lfs -text`), or publish them via GitHub Releases / an S3 bucket and add a `make download-models` step. Pair this with a pinned dependency manifest so artifacts remain loadable.

**Inconsistent `sys.path` hacks across modules (MEDIUM):**
- Issue: Multiple scripts manually inject relative paths into `sys.path` because there is no installable package layout. Two styles coexist — `os.path.abspath(...)` with `PROJECT_ROOT` and a bare relative `sys.path.append("../feature_extraction")`.
- Files:
  - `src/demo/demo_router.py:25-26`
  - `src/model_router_tier/build_router_dataset.py:24-25`
  - `src/evaluation/evaluate_baselines.py:21-22`
  - `src/task_classifier/train_task_classifier_robust.py:45-46`
  - `src/task_classifier/train_task_classifier_simple.py:8` (the only one using a CWD-dependent relative path)
  - `src/model_router/train_embedding_router.py:25-26`
- Impact: Scripts only work when launched from specific working directories. The relative `sys.path.append("../feature_extraction")` in `train_task_classifier_simple.py` silently does the wrong thing if invoked from the repo root. There is no `pyproject.toml`/`setup.py`, so `src.` is not a real package.
- Fix approach: Add a minimal `pyproject.toml` with `src/` as a package layout (or use `python -m`), remove all `sys.path.append` lines, and use ordinary intra-package imports.

**Duplicate / near-duplicate training scripts (MEDIUM):**
- Issue: `src/model_router_tier/router_tier_system.py` (503 lines) and `src/model_router_tier/train_tier_router.py` (716 lines) share the bulk of their content with a 596-line diff between them. Both define their own `MODELS_DIR`, `INPUT_CSV`, `ROUTER_MODEL_PATH`, plotting helpers, and have a `__main__` block. They are two slightly different forks of the same trainer living next to each other.
- Files: `src/model_router_tier/router_tier_system.py`, `src/model_router_tier/train_tier_router.py`
- Impact: Changes must be made in two places; users cannot tell which script is canonical (README does not disambiguate). Similar duplication exists between `src/task_classifier/train_task_classifier_simple.py` (226 lines) and `src/task_classifier/train_task_classifier_robust.py` (609 lines).
- Fix approach: Consolidate to a single trainer per router with `--mode {simple,robust}` flags, or clearly delete the one no longer in use.

**Hardcoded relative CSV paths in some scripts (LOW-MEDIUM):**
- Issue: A subset of scripts use shell-style relative CSV paths instead of the `PROJECT_ROOT`-anchored pattern used elsewhere.
- Files:
  - `src/task_classifier/build_question_type.py:5-6` — `INPUT_CSV = "../../data_processed/classifier_training_features.csv"`
  - `src/task_classifier/train_task_classifier_simple.py:12` — `INPUT_CSV = "../../data_processed/classifier_training_with_types.csv"`
- Impact: These scripts only work when run from inside their own directory; running from the repo root fails. Contradicts the `os.path.abspath(__file__)`-based pattern used by `train_task_classifier_robust.py:34-51`, `train_tier_router.py:32-41`, `train_model_router.py`, `demo_router.py:14-23`, etc.
- Fix approach: Normalize on the `PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))` pattern in the two outliers.

**`__pycache__/` directories committed to git (LOW):**
- Issue: 13 `.pyc` files under `src/**/__pycache__/` are tracked in git. They include compiled bytecode for both `cpython-38` and `cpython-312` runtimes (e.g. `src/data/__pycache__/build_classifier_dataset_cost_aware.cpython-38.pyc` and `src/data/__pycache__/build_classifier_dataset.cpython-312.pyc`).
- Files (verified via `git ls-files | grep __pycache__`): 13 entries under `src/data/__pycache__/`, `src/demo/__pycache__/`, `src/evaluation/__pycache__/`, `src/feature_extraction/__pycache__/`, `src/model_router/__pycache__/`
- Impact: Bytecode is version-specific and host-specific; committing it produces noisy diffs and may shadow updated `.py` files. The mix of `cpython-38` and `cpython-312` artifacts also indicates the project has been developed on at least two Python versions with no enforced target.
- Fix approach: Add a root `.gitignore` with `__pycache__/`, `*.pyc`, `*.pyo`, then `git rm -r --cached src/**/__pycache__`. Add a `.python-version` or `pyproject.toml` `requires-python` to pick one runtime.

**Typo-named empty placeholder file (LOW):**
- Issue: `evulation_summary.md` (note the missing "a") is a 0-byte file committed alongside the real `evaluation_summary.md` (258 lines).
- Files: `evulation_summary.md` (empty), `evaluation_summary.md`
- Impact: Search noise; confuses readers expecting docs. Easy to update the wrong file.
- Fix approach: `git rm evulation_summary.md`.

**Typo in module filename (LOW):**
- Issue: `src/model_router/build_top_model_datatset.py` — "datatset" should be "dataset". The module is referenced as a script via `__main__`, so no import currently breaks, but any future `from .build_top_model_dataset import ...` will fail.
- Files: `src/model_router/build_top_model_datatset.py`
- Fix approach: Rename to `build_top_model_dataset.py` and update any references.

**Stale path reference in error messages (LOW):**
- Issue: Two scripts tell the user to "Run src/model_router/build_router_dataset.py" but that file does not exist — the actual location is `src/model_router_tier/build_router_dataset.py`.
- Files:
  - `src/model_router_tier/train_tier_router.py:633`
  - `src/model_router/train_model_router.py:681`
- Impact: User following the error message will hit a "no such file" error.
- Fix approach: Update both error strings to point at the real path.

## Known Bugs

**LFS-tracked CSVs are committed as unresolved pointers (HIGH — blocks training):**
- Symptoms: All CSVs in `data_processed/` and `evaluation/` are 130-byte git-LFS pointer files rather than real CSV content. Example, `data_processed/classifier_training.csv` is literally:
  ```
  version https://git-lfs.github.com/spec/v1
  oid sha256:1f2a490475d82c7cc24cf6cbda4f8ad1ce08f635bd81126b6fa245f6191d22bb
  size 124609128
  ```
- Files: `data_processed/classifier_training.csv` and every `evaluation/*.csv` (verified via head/xxd). `git-lfs` is **not installed** on the current machine (`git lfs` returns "lfs is not a git command"), so `git clone` left the pointers in place.
- Trigger: Any `pd.read_csv(...)` call in the pipeline. For example `src/model_router_tier/train_tier_router.py:639` does `pd.read_csv(INPUT_CSV)` against `data_processed/router_training_dataset.csv` — which would either be missing (only `classifier_training.csv` is tracked) or, for the one that is tracked, parsed as a 3-line CSV containing `version`, `oid`, `size`.
- Workaround: Install git-lfs (`brew install git-lfs && git lfs install && git lfs pull`) before running anything.
- Fix approach: Document the git-lfs prerequisite in README. Better: regenerate the CSVs from `data_raw/` (which is not committed) and treat them as build artifacts.

**Missing intermediate datasets referenced by trainers (HIGH):**
- Symptoms: The training pipeline expects `data_processed/router_training_dataset.csv`, `classifier_training_with_types.csv`, `classifier_training_features.csv`, and `flat_records.csv`, but only `classifier_training.csv` is committed (and even that is an LFS pointer).
- Files referencing missing inputs:
  - `src/model_router_tier/train_tier_router.py:40` (`router_training_dataset.csv`)
  - `src/model_router_tier/router_tier_system.py:41` (same)
  - `src/task_classifier/train_task_classifier_robust.py:51` (`classifier_training_with_types.csv`)
  - `src/evaluation/evaluate_baselines.py:67-69` (`flat_records.csv`)
- Trigger: Running any trainer end-to-end against a fresh clone.
- Workaround: Run the upstream pipeline (`flatten_raw_jsons.py` → `build_classifier_dataset.py` → `build_question_type.py` → `build_features.py` → `build_router_dataset.py`) — but `data_raw/` is not in git, so the chain cannot start from a fresh clone.
- Fix approach: Either ship a smaller "demo" dataset in-repo, or document where to obtain `data_raw/` (the README mentions `LLMRouterBench` but does not give a fetch command).

## Security Considerations

**No secrets detected in source / config (PASS):**
- Risk: Hardcoded API keys, tokens, or passwords.
- Files audited: full `src/` tree and `config/model_mapping.json` were grepped for `sk-`, `api_key`, `secret`, `token`, `password`, `bearer`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`.
- Result: **No hits.** There is also no `.env` file in the repo root, and `.gitignore` does not need to ignore one because none exists yet.
- Current mitigation: The router is purely offline (no `requests`/`httpx`/`openai`/`anthropic` imports anywhere in `src/`). `demo_router.py` only *prints* an "api model available" flag — it never makes a real HTTP call.
- Recommendations: When a live OpenRouter call is added, load the key from `os.environ["OPENROUTER_API_KEY"]` and add `.env` to `.gitignore` proactively.

**`joblib.load` on committed artifacts (MEDIUM):**
- Risk: `joblib.load` deserializes pickled Python objects and can execute arbitrary code at load time. The demo scripts call `joblib.load(...)` on whatever is in `models/`.
- Files: `src/demo/demo_router.py:46`, `src/demo/demo_embedding_router.py:40`, `src/evaluation/evaluate_baselines.py:242`, `src/model_router_tier/train_tier_router.py:377`, `src/task_classifier/train_task_classifier_robust.py:536`, `src/model_router/train_embedding_router.py:487`, `src/model_router/train_model_router.py:405`, `src/model_router_tier/build_router_dataset.py:49`.
- Current mitigation: Artifacts are produced by this same repo; the trust boundary is "the contributor who pushed last".
- Recommendations: Note this trust model in README; if model artifacts ever come from third parties, switch to a safer format (skops, ONNX, or hand-rolled JSON for sklearn coefficients).

**Silent `nltk.download(...)` on import path (LOW):**
- Risk: First-time use of the feature extractor reaches out to the network to fetch `punkt` / `punkt_tab` resources.
- Files: `src/feature_extraction/Feature_extractor.py:11-17`, `src/feature_extraction/Feature_extractor.py:130-131`
- Current mitigation: `quiet=True`; downloads are idempotent and cached in `~/nltk_data`.
- Recommendations: Bundle the resources or fail loudly when offline, so air-gapped CI does not hang.

## Performance Bottlenecks

**Embedding model loaded per script invocation (LOW):**
- Problem: Every script that needs embeddings calls `SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")` at startup. There is no caching layer beyond Hugging Face's own disk cache.
- Files: `src/model_router/train_embedding_router.py:54,188,697`, `src/demo/demo_embedding_router.py:159`, `src/evaluation/evaluate_baselines.py:273`
- Cause: First load downloads weights (~90 MB) and initializes torch; subsequent loads still pay ~1-3 s startup cost.
- Improvement path: For batch/CLI workflows this is fine. For an interactive demo, refactor `demo_embedding_router.py` to keep the model resident across prompts.

**Single-process training, no batching knobs (LOW):**
- Problem: Trainers use defaults across `LogisticRegression` / `RandomForestClassifier` / sklearn pipelines with no `n_jobs` parameter exposed.
- Files: `src/model_router/train_embedding_router.py:602-614`, `src/model_router_tier/train_tier_router.py:532`, `src/task_classifier/train_task_classifier_simple.py:121-127`
- Improvement path: Expose `n_jobs=-1` for tree ensembles and document expected wall-clock on the LLMRouterBench dataset size.

**Print-based logging across long-running trainers (LOW):**
- Problem: 354 `print(...)` calls across `src/` vs. only three files importing `logging` (`flatten_raw_jsons.py`, `build_classifier_dataset.py`, `build_classifier_dataset_cost_aware.py`). Progress in trainers is not timestamp-tagged or routable to a file.
- Improvement path: Standardize on the `logging` module already used by the data pipeline.

## Fragile Areas

**Model mapping: 7 of 16 entries are unverified / simulated (MEDIUM):**
- Files: `config/model_mapping.json`
- Why fragile: 7 of 16 model labels are marked `"provider": "simulated"` with `"openrouter_verified": false` and `"api_model": null`. These are: `internlm3-8b-instruct`, `granite-3.3-8b-instruct`, `glm-4-9b-chat`, `MiniCPM4.1-8B`, `cogito-v1-preview-llama-8B`, `OpenThinker3-7B`, and the sentinel class `OTHER`. The notes field says "Dataset model name. I did not find an exact current OpenRouter model ID for this slug." This means **for ~44% of the router's prediction classes there is no real model to route to** — the demo simply prints "simulated/unverified route" (`src/demo/demo_router.py:394`).
- Safe modification: Before adding a live API call, either map these to real OpenRouter slugs or have the router fall back to a verified model in the same tier.
- Test coverage: None (see below).

**No test suite (HIGH):**
- What's not tested: Everything. `find . -name "test_*.py" -o -name "*_test.py" -o -name "tests"` returns zero matches. There is no `pytest`, `unittest`, or CI config.
- Files: n/a (absence)
- Risk: Refactors and dependency bumps (especially sklearn / scipy version drift, see Tech Debt) can silently change predictions. The two near-duplicate tier-router scripts can drift further apart. The pickled `*.joblib` artifacts can stop loading without anyone noticing.
- Priority: HIGH for a regression-test on the demo path (load each `.joblib`, route a fixed prompt, assert predicted label is stable); MEDIUM for unit tests on `PromptFeatureExtractor` and the CSV-aggregation helpers in `src/data/build_classifier_dataset.py`.

**Two-stage router dependence on stage-1 confidence (MEDIUM):**
- Files: `src/demo/demo_router.py:330-340` (`route_prompt` uses `question_type` from stage 1 as a feature for stage 2)
- Why fragile: A misclassification in `task_type_classifier.joblib` becomes an input to `model_router.joblib`. The README's own evaluation summary admits "exact model routing was significantly harder than tier routing" (`evaluation_summary.md` "3. Exact Model Router" section, accuracy 0.21 / macro F1 0.17), so the upstream signal is noisy.
- Safe modification: Document this coupling. Consider passing top-k task predictions instead of argmax.

**Hugging Face / NLTK resource downloads at runtime (LOW):**
- Files: `src/feature_extraction/Feature_extractor.py:11-17`, anywhere `SentenceTransformer(...)` is called
- Why fragile: First run requires internet. CI without network access will hang or fail.
- Safe modification: Pre-warm in a setup script.

## Scaling Limits

**Single-host, in-memory training (MEDIUM):**
- Current capacity: `pd.read_csv(...)` loads the full `router_training_dataset.csv` into memory in every trainer (e.g. `src/model_router_tier/train_tier_router.py:639`). The upstream LLMRouterBench data is documented as a large benchmark; the pointer file claims a 124 MB source CSV.
- Limit: Bounded by host RAM. No chunked / out-of-core training.
- Scaling path: The data-prep step at `src/data/build_classifier_dataset.py:90-130` already streams row-by-row via `csv.DictReader`. Apply the same streaming approach in training, or downsample explicitly.

## Dependencies at Risk

**Unpinned scikit-learn / scipy / joblib (HIGH — combined with committed artifacts):**
- Risk: Joblib artifacts saved with one sklearn version often refuse to load under another (especially across 1.x major bumps). Without a `requirements.txt`, the `.joblib` files in `models/` are time-bombs.
- Impact: A fresh `pip install scikit-learn` six months from now may break `joblib.load("models/model_router.joblib")`.
- Migration plan: Pin sklearn / scipy / numpy versions and add a CI smoke test that loads each artifact.

**`sentence-transformers` is pinned to a specific public model:**
- Risk: `EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"` (`src/model_router/train_embedding_router.py:54`) — hardcoded model identifier. The artifact also stores `embedding_model_name` (`src/model_router/train_embedding_router.py:461`) so prediction-time consistency is ok, but a model removal upstream would break re-training.

## Missing Critical Features

**No HTTP/API client despite OpenRouter framing:**
- Problem: README and `model_mapping.json` describe routing to OpenRouter, but no module in `src/` imports `requests`, `httpx`, `aiohttp`, `urllib`, `openai`, or `anthropic`. `demo_router.py` only computes which model *would* be called (`get_api_model_for_real_call`, `src/demo/demo_router.py:276-284`) — there is no actual outbound call.
- Blocks: End-to-end demo against real LLMs. Cost/latency telemetry. The "Real API model available: None, simulated/unverified route" branch is the only one that fires for 7 of 16 classes.

**No CLI/UI entry point:**
- Problem: All scripts are `python -m src.xxx` invocations with a `__main__` block; there is no top-level `cli.py`, `main.py`, or web demo. The README describes the "long-term routing idea" but the user-facing surface is "edit a hardcoded prompt at the bottom of `demo_router.py`".

**No `.gitignore` at the repo root:**
- Problem: Only `.idea/.gitignore` exists. The repo root has none, which is how `__pycache__/` ended up tracked and why `.env` (if it appeared) would not be auto-ignored.
- Impact: Easy for contributors to accidentally commit `__pycache__/`, virtualenvs, IDE files, or future `.env` secrets.

## Test Coverage Gaps

**Zero tests in the repository:**
- What's not tested: Every code path. Confirmed by `find . -name "test_*.py" -o -name "*_test.py" -o -name tests -type d` returning no results.
- Files: n/a
- Risk: Cannot detect dependency drift, prediction drift, or pipeline regressions. Especially relevant given (a) `.joblib` artifacts are committed without pinned deps, (b) two near-duplicate tier-router trainers can silently diverge, and (c) the model mapping has unverified entries.
- Priority: HIGH

**No artifact-vs-script-version check:**
- What's not tested: That the committed `models/*.joblib` were produced by the *current* `train_*.py` scripts. All four artifacts have an `mtime` of `May 11 09:22:08 2026` (which is the clone time, not the training time), and git history shows training scripts were modified across commits `4c7a0b6`, `929b99a`, `a68173a`, and `77698cd` — all on 2026-05-10. The artifacts were committed in `77698cd "model trained"`, but later commits to the trainers would not be visible here.
- Risk: A reader cannot tell whether the demo's predictions reflect the latest trainer code.
- Priority: MEDIUM — embed a `training_script_git_sha` field in the saved `artifacts` dict and assert against it on load.

---

*Concerns audit: 2026-05-11*
