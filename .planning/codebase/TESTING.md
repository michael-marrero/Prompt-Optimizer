# Testing Patterns

**Analysis Date:** 2026-05-11

## Test Framework

**There are no automated tests in this repository.**

A full scan of the working tree turned up zero hits for any of:

- `test_*.py` (pytest convention)
- `*_test.py` (alternative pytest / Go-style naming)
- `tests/` or `test/` directories anywhere under the repo root
- `conftest.py` (pytest fixture entry point)
- `pytest.ini`, `tox.ini`, `setup.cfg`, `pyproject.toml` (no test runner config of any kind)
- `unittest.TestCase` subclasses
- `nose`, `nose2`, `hypothesis`, `doctest`, or any other testing framework imports
- `.github/`, `.gitlab-ci.yml`, `circleci/`, `azure-pipelines.yml`, or any other CI configuration directory or file

The only `*.yml`/`*.yaml` files in the tree are PyCharm IDE artifacts under `.idea/` (none are CI definitions). There is no `requirements.txt`, no `requirements-dev.txt`, and no `pyproject.toml`, so there is also no declared `pytest`, `coverage`, or `mock` dependency. There is no `Makefile` or test runner entry point.

**Runner:** None.
**Assertion Library:** None.
**Run Commands:** None — there is nothing to run.

## Test File Organization

**Location:** Not applicable. No test files exist.

**Naming:** Not applicable.

**Structure:** Not applicable.

## Test Structure

Not applicable. No suite, fixture, setup/teardown, or assertion patterns exist in this codebase.

## Mocking

Not applicable. No mocks, patches, or test doubles exist. The codebase does not import `unittest.mock`, `pytest-mock`, `responses`, `vcrpy`, `freezegun`, or any other test-double library.

## Fixtures and Factories

Not applicable. There are no test fixtures, factory functions, or sample-data helpers wired into a test framework. The closest thing to fixture data is the production CSVs under `data_processed/`, which are consumed by the training scripts directly, not by tests.

## Coverage

**Requirements:** None enforced. No coverage tool (`coverage.py`, `pytest-cov`) is installed or referenced.

**View Coverage:** Not applicable.

## Test Types

**Unit Tests:** None.

**Integration Tests:** None.

**E2E Tests:** None.

## What Serves as Validation Instead

Because there is no automated test suite, the repository relies on a combination of **evaluation artifacts, interactive demo scripts, and inline runtime checks** to validate behavior. These should be treated as the current "test surface" — they are the only feedback loop available before code reaches `main`.

### 1. Evaluation CSVs in `evaluation/`

Every training script writes a per-class metrics CSV and a misclassified-examples CSV to `evaluation/` after the test split is scored. These files are the primary regression signal — comparing a new run's CSV against the prior committed run is how the team detects accuracy regressions.

| File | Produced by | Contents |
|------|-------------|----------|
| `evaluation/classification_metrics.csv` | `src/task_classifier/train_task_classifier_robust.py` (`save_classification_metrics_csv`) | per `question_type` precision/recall/f1/support |
| `evaluation/misclassified_examples.csv` | `src/task_classifier/train_task_classifier_robust.py` (`save_misclassified_examples`) | rows the task classifier got wrong |
| `evaluation/model_router_metrics.csv` | `src/model_router/train_model_router.py` (`save_metrics_csv`) | per-model precision/recall/f1/support |
| `evaluation/model_router_misclassified_examples.csv` | `src/model_router/train_model_router.py` (`save_misclassified_examples`) | router mistakes with true/predicted model |
| `evaluation/embedding_router_metrics.csv` | `src/model_router/train_embedding_router.py` (`save_metrics_csv`) | per-family precision/recall/f1/support |
| `evaluation/embedding_router_misclassified_examples.csv` | `src/model_router/train_embedding_router.py` (`save_misclassified_examples`) | embedding router mistakes |
| `evaluation/tier_router_metrics.csv` | `src/model_router_tier/train_tier_router.py` (`save_metrics_csv`) | per-tier precision/recall/f1/support |
| `evaluation/tier_router_misclassified_examples.csv` | `src/model_router_tier/train_tier_router.py` (`save_misclassified_examples`) | tier router mistakes |
| `evaluation/router_comparison_summary.csv` | `src/evaluation/compare_router_results.py` | side-by-side comparison across router variants |

### 2. Evaluation plots (PNG)

Each training script also dumps diagnostic plots at 300 dpi. These exist purely as a visual sanity check — there are no automated assertions over their contents. The plots are checked in to git so a reviewer can eyeball the change between branches.

- `evaluation/plots/` — task classifier diagnostics: `class_distribution.png`, `confusion_matrix.png`, `confusion_matrix_normalized.png`, `per_class_f1.png`, `precision_recall_f1.png`, `prediction_confidence.png`.
- `evaluation/model_router_plots/` — exact model router: `model_router_target_distribution.png`, `model_router_top_class_f1.png`, `model_router_top_confusion_matrix.png`, `model_router_prediction_confidence.png`.
- `evaluation/embedding_router_plots/` — embedding router: `embedding_router_target_distribution.png`, `embedding_router_top_class_f1.png`, `embedding_router_top_confusion_matrix.png`, `embedding_router_top_probability.png`, `embedding_router_prediction_confidence.png`.
- `evaluation/router_plots/` — tier router: `tier_router_confusion_matrix.png`, `tier_router_confusion_matrix_normalized.png`, `router_target_distribution.png`, plus `tier_router_precision_recall_f1.png` and `tier_router_prediction_confidence.png` when produced.
- `evaluation/comparison_plots/` — cross-router macro F1 / precision / recall / weighted F1 comparisons produced by `src/evaluation/compare_router_results.py`.

### 3. Baseline evaluation script

`src/evaluation/evaluate_baselines.py` re-loads saved joblib artifacts and re-scores them against the dataset using `sklearn.metrics.accuracy_score` and `f1_score`. This stands in for an end-to-end integration check: if a refactor breaks the inference path or invalidates a saved artifact, this script fails. There is no pass/fail threshold — humans read the printed metrics.

`src/evaluation/compare_router_results.py` aggregates router metric CSVs into a comparison summary CSV plus comparison plots. Treat it as the "regression report" generator.

### 4. Stdout printouts in training runs

Every training script prints metrics directly to the terminal at the end of training. This is the fastest feedback loop and the primary signal during local development. Pattern in `src/task_classifier/train_task_classifier_robust.py:433-447`:

```text
Task Type Classifier Results
----------------------------
Accuracy: 0.xxxx
Macro F1: 0.xxxx
Weighted F1: 0.xxxx

Classification Report:
              precision    recall  f1-score   support
...
```

The same skeleton appears in `train_model_router.py`, `train_tier_router.py`, and `train_embedding_router.py`. A reviewer paste-compares this block against the previous run's logs.

### 5. Interactive demo REPLs

The demo scripts function as smoke tests against saved artifacts:

- `src/demo/demo_router.py` — loads `task_type_classifier.joblib` and `model_router.joblib` plus `config/model_mapping.json`, then drops into a `while True` `input()` loop that runs a full prompt through both stages and prints the route. The main loop wraps `route_prompt` in `try/except Exception as error` (lines 459-472) so that a runtime error in any stage prints a message instead of crashing — this is the closest thing to an error-path test in the repo.
- `src/demo/demo_embedding_router.py` — interactive smoke test for the embedding router.

These are how humans verify that a freshly trained model actually works end-to-end on novel prompts.

### 6. Inline runtime validation (the closest thing to assertions)

Several modules contain runtime guards that raise on bad input. These guards run during normal pipeline execution, not under a test runner, but they serve as the codebase's defensive checks:

- Column existence: `if "origin_query" not in df.columns: raise ValueError(...)` — `src/task_classifier/train_task_classifier_robust.py:346-350`, `src/model_router/train_model_router.py:514-515`, `src/model_router_tier/train_tier_router.py:486-487`, `src/model_router/train_embedding_router.py:84-101` (`validate_input_columns`).
- Target column resolution: `get_target_column` raises `ValueError` if no acceptable target column is found — `src/model_router/train_model_router.py:48-69`, `src/model_router_tier/train_tier_router.py:48-63`.
- Artifact integrity: every `load_*_artifacts` function checks `os.path.exists(model_path)` then validates a `required_keys` list and raises `KeyError` on any missing key — `src/model_router/train_model_router.py:394-430`, `src/model_router_tier/train_tier_router.py:366-402`, `src/model_router/train_embedding_router.py:480-503`, `src/demo/demo_router.py:35-60`.
- Embedding cache consistency: `if len(embeddings) != len(texts): raise ValueError(...)` — `src/model_router/train_embedding_router.py:176-181`.
- Single-class guard: `if labels.nunique() < 2: raise ValueError(...)` — `src/model_router/train_embedding_router.py:585-588`.

## Common Patterns

**Async Testing:** Not applicable. No async code in the repo.

**Error Testing:** Not applicable in a test-framework sense. Runtime error handling is described above under "Inline runtime validation" and "Defensive try/except" in `CONVENTIONS.md`.

## Recommendation for Adding Tests

If a future phase introduces a test suite, the natural shape would be:

1. Add `pytest` and `pytest-cov` to a new `requirements-dev.txt` (or to a `pyproject.toml` if migrating off the current loose-script layout).
2. Place tests under a top-level `tests/` directory mirroring `src/` (`tests/feature_extraction/test_feature_extractor.py`, `tests/model_router/test_model_family.py`, etc.). Co-locating tests next to source would conflict with the `sys.path` injection pattern already in use.
3. The lowest-effort, highest-value first tests would target pure, deterministic functions:
   - `infer_model_vendor_family` in `src/model_router/model_family.py` (pure string mapping, trivial table-driven test).
   - `PromptFeatureExtractor.extract` in `src/feature_extraction/Feature_extractor.py` (deterministic feature dict for a fixed input string).
   - `get_target_column` and `get_numeric_feature_columns` in the three router training modules (deterministic given a small synthetic DataFrame).
4. Joblib round-trip integration tests on a tiny synthetic dataset would catch regressions in `save_*_artifacts` / `load_*_artifacts`.
5. CI would be a GitHub Actions workflow under `.github/workflows/` running `pytest` on push/PR.

None of this exists today.

---

*Testing analysis: 2026-05-11*
