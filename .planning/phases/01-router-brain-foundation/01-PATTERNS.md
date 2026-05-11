# Phase 1: Router Brain Foundation - Pattern Map

**Mapped:** 2026-05-11
**Files analyzed:** 28 new/modified files
**Analogs found:** 24 / 28 (4 files are net-new infrastructure with no in-tree analog)

This document maps every file the Phase 1 planner will touch to its closest existing analog in the codebase, with concrete code excerpts the executor should copy verbatim. The excerpts capture the canonical joblib artifact shape, sklearn `Pipeline`/`FeatureUnion` stack, sparse-stack `hstack` ordering, `LogisticRegression` hyperparameters, the multi-line `FileNotFoundError`/`KeyError` validators, the `_NLTK_PUNKT_READY` lazy-download guard, the path-discovery preamble, the `sys.path` injection convention, the `try/except` REPL wrapper, and the `argparse` vs `input()` mode-toggle conventions documented in CLAUDE.md.

---

## File Classification

### `src/routing/` package (NEW — Phase 1 core deliverable)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/routing/__init__.py` | package init | n/a | `src/feature_extraction/__init__.py` (empty) | exact |
| `src/routing/schema.py` | dataclass / type aliases | request-response | none — net-new (see RESEARCH §Pattern 4) | no analog (use stdlib `dataclasses`) |
| `src/routing/config.py` | constants module | n/a | constants block in `src/task_classifier/train_task_classifier_robust.py:29-51` | role-match (constants only) |
| `src/routing/policy.py` | rule-cascade helper | transform | `choose_final_route` + `get_api_model_for_real_call` in `src/demo/demo_router.py:245-284` | exact role + data flow |
| `src/routing/decide.py` | pure-function inference module + CLI entry | request-response | `route_prompt` in `src/demo/demo_router.py:291-341` (legacy two-stage) | exact |
| `src/routing/tests/__init__.py` | test package init | n/a | none (no tests in repo today) | no analog |
| `src/routing/tests/conftest.py` | pytest session fixtures | n/a | none (no pytest in repo today) | no analog (RESEARCH §Example 3 supplies template) |
| `src/routing/tests/test_decide_smoke.py` | unit test (D-18 import-graph guard) | n/a | none (no tests in repo today) | no analog (RESEARCH §Pattern 4 supplies template) |
| `src/routing/tests/test_uncertainty_fallback.py` | unit test (success criterion #4) | n/a | none | no analog (RESEARCH §Example 4 supplies template) |

### `src/calibration/` (NEW — wrapper module)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/calibration/__init__.py` | package init | n/a | `src/feature_extraction/__init__.py` | exact |
| `src/calibration/calibrate.py` (or inline in train scripts) | training script | batch transform | `train_task_type_classifier` in `src/task_classifier/train_task_classifier_robust.py:338-449` (the surrounding pipeline pattern) | role-match |
| `src/calibration/tests/test_calibration.py` | integration test | n/a | none | no analog (RESEARCH §Example 1 + §Example 2 supply template) |

### `src/task_classifier/` extensions

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/task_classifier/build_agentic_dataset.py` | data builder | batch / file I/O | `src/data/build_classifier_dataset.py` (argparse-driven streaming aggregator) | exact role + data flow |
| `src/task_classifier/train_agentic_intent.py` | training script | batch | `src/task_classifier/train_task_classifier_robust.py` (full file — TF-IDF + handcrafted + LogReg + persistence) | exact |
| `src/task_classifier/tests/__init__.py` | test package init | n/a | none | no analog |
| `src/task_classifier/tests/test_agentic_intent.py` | training smoke test | n/a | none | no analog |
| `src/task_classifier/build_question_type.py` (MODIFIED — emit `"unknown"` for unmatched rows) | weak labeler | transform | file itself, `src/task_classifier/build_question_type.py:8-150` | self (extension) |
| `src/task_classifier/train_task_classifier_robust.py` (MODIFIED — `unknown` class + Calibrated wrapper) | training script | batch | self | self (extension) |

### `src/feature_extraction/` extensions

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/feature_extraction/Feature_extractor.py` (MODIFIED — +5 agentic features) | feature extractor class | transform | self, `src/feature_extraction/Feature_extractor.py:30-360` | self (extension; mirror `_keyword_features` / `_complexity_features` pattern) |
| `src/feature_extraction/tests/__init__.py` | test package init | n/a | none | no analog |
| `src/feature_extraction/tests/test_agentic_features.py` | unit test | n/a | none | no analog |
| `src/feature_extraction/text_inputs.py` (NEW — planner discretion, lifts Stage-2 input format) | utility | transform | `build_text_input` in `src/model_router/train_model_router.py:125-155` AND `build_model_router_text_input` in `src/demo/demo_router.py:110-129` | exact (consolidates duplication) |

### `src/model_router/` extensions

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/model_router/train_model_router.py` (MODIFIED — Calibrated wrapper added, artifact dict unchanged) | training script | batch | self | self (extension) |

### `src/evaluation/` extensions

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/evaluation/evaluate_routing.py` | pipeline / eval script | batch + file I/O | `src/evaluation/evaluate_baselines.py` (load artifacts, run predictions over a CSV, write results to `evaluation/`) | exact role + data flow |
| `src/evaluation/tests/__init__.py` | test package init | n/a | none | no analog |
| `src/evaluation/tests/test_evaluate_routing.py` | unit test | n/a | none | no analog |

### `src/demo/` extensions

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/demo/demo_router.py` (MODIFIED — call `src.routing.decide`) | inference CLI / REPL | request-response | self, `src/demo/demo_router.py:291-341` (`route_prompt`) and `:421-472` (`main` loop) | self (extension) |
| `src/demo/tests/__init__.py` | test package init | n/a | none | no analog |
| `src/demo/tests/test_artifact_compat.py` | regression guard (Pitfall 4) | n/a | none — but the validator under test is `load_joblib_artifacts` at `src/demo/demo_router.py:35-60` | exact (target-only) |

### Data + artifact files

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `evaluation/routing_decision_eval.csv` (canary, ~42 rows) | CSV dataset | file I/O | `data_processed/classifier_training.csv` schema (one row per question) | role-match (schema differs — see RESEARCH §Pattern 5) |
| `data_processed/agentic_intent_training.csv` | CSV dataset | file I/O | `data_processed/classifier_training_with_types.csv` schema | role-match |
| `models/agentic_intent_classifier.joblib` | sklearn artifact dict | persistence | `models/task_type_classifier.joblib` (same dict shape) | exact |
| `models/uncalibrated/*.joblib` | one-time backup directory | file I/O | none (net-new convention) | no analog |

### Project infrastructure (NEW — OSS-01 + SECURE-03)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `pyproject.toml` (root) | build config | n/a | none — first lockfile in repo | no analog (RESEARCH §Standard Stack supplies skeleton) |
| `uv.lock` (root) | lockfile | n/a | none | no analog (auto-generated by `uv sync`) |
| `.gitignore` (root) | VCS config | n/a | none — `ls` confirmed only `.gitattributes` exists | no analog (RESEARCH §Pattern 8 supplies template) |
| `.github/workflows/ci.yml` | CI config | n/a | none — INTEGRATIONS.md confirms "No CI Pipeline" today | no analog (RESEARCH §Example 5 supplies template) |

---

## Pattern Assignments

### `src/routing/decide.py` (inference module, request-response)

**Analog:** `src/demo/demo_router.py` — specifically `route_prompt` (lines 291-341), `predict_task_type` (lines 136-179), and `predict_best_model` (lines 186-238).

**Path-discovery preamble** (copy verbatim from `src/demo/demo_router.py:1-28`):

```python
import os
import sys
import json
import joblib
import pandas as pd

from scipy.sparse import hstack, csr_matrix

# ------------------------------------------------------------
# Path setup
# ------------------------------------------------------------

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

SRC_DIR = os.path.join(PROJECT_ROOT, "src", "feature_extraction")
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")

TASK_CLASSIFIER_PATH = os.path.join(MODELS_DIR, "task_type_classifier.joblib")
MODEL_ROUTER_PATH = os.path.join(MODELS_DIR, "model_router.joblib")
MODEL_MAPPING_PATH = os.path.join(CONFIG_DIR, "model_mapping.json")

if SRC_DIR not in sys.path:
    sys.path.append(SRC_DIR)

from Feature_extractor import PromptFeatureExtractor
```

**ANTI-PATTERN to avoid:** RESEARCH §"Anti-Patterns to Avoid" line 854 (and CONTEXT §`<code_context>` line 151) say: "Do NOT add another `sys.path.append(SRC_DIR)` site." For `src/routing/decide.py`, the executor SHOULD prefer `from src.feature_extraction.Feature_extractor import PromptFeatureExtractor` and require `python -m src.routing.decide "<prompt>"` invocation. If the planner decides this breaks too much in v1, the `sys.path` injection above is the documented fallback — but it MUST be flagged as a known anti-pattern carried over.

**Stage-1 prediction pattern** (copy from `src/demo/demo_router.py:136-179` — keep the variable names verbatim so the saved-artifact key contract matches):

```python
def predict_task_type(
    prompt: str,
    task_artifacts: dict,
    extractor: PromptFeatureExtractor
):
    model = task_artifacts["model"]
    vectorizer = task_artifacts["vectorizer"]
    scaler = task_artifacts["scaler"]
    label_encoder = task_artifacts["label_encoder"]
    feature_columns = task_artifacts["feature_columns"]

    text_series = pd.Series([prompt])
    text_features = vectorizer.transform(text_series)

    numeric_df = build_numeric_features(
        prompt=prompt,
        feature_columns=feature_columns,
        extractor=extractor
    )

    numeric_scaled = scaler.transform(numeric_df)
    numeric_sparse = csr_matrix(numeric_scaled)

    combined_features = hstack([text_features, numeric_sparse])

    prediction_encoded = model.predict(combined_features)[0]
    prediction_label = label_encoder.inverse_transform([prediction_encoded])[0]

    probabilities = model.predict_proba(combined_features)[0]

    confidence_table = []
    for label, probability in zip(label_encoder.classes_, probabilities):
        confidence_table.append((label, probability))
    confidence_table.sort(key=lambda item: item[1], reverse=True)

    confidence = confidence_table[0][1]
    return prediction_label, confidence, confidence_table
```

**Stage-2 prediction pattern** (copy from `src/demo/demo_router.py:186-238`). The same `vectorizer / scaler / label_encoder / feature_columns` order MUST be preserved. The Stage-2 caller passes `question_type_confidence` via `extra_values={"question_type_confidence": question_type_confidence}` — see `:214-216`. The Stage-2 text input uses the format `"<query> task_type_<qt> keyword_type_<kqt>"` from `build_model_router_text_input` at `:110-129`.

**ANTI-PATTERN to avoid:** RESEARCH §"Anti-Patterns to Avoid" line 853 (and CONTEXT §`<code_context>` line 150) say: "Do NOT re-implement the Stage-2 text-input format in `src/routing/`." The executor MUST lift `build_model_router_text_input` into a shared helper (e.g., `src/feature_extraction/text_inputs.py`) and import it from both `train_model_router.py` and `decide.py`. The function body to lift:

```python
# Currently duplicated in two places:
#   - src/demo/demo_router.py:110-129 (build_model_router_text_input)
#   - src/model_router/train_model_router.py:125-155 (build_text_input)
# Lift into src/feature_extraction/text_inputs.py:

def build_router_text_input(
    prompt: str,
    question_type: str,
    keyword_question_type: str = "unknown"
) -> pd.Series:
    combined_text = (
        str(prompt)
        + " task_type_"
        + str(question_type)
        + " keyword_type_"
        + str(keyword_question_type)
    )
    return pd.Series([combined_text])
```

**Numeric-feature DataFrame contract** (copy from `src/demo/demo_router.py:81-107`):

```python
def build_numeric_features(
    prompt: str,
    feature_columns: list,
    extractor: PromptFeatureExtractor,
    extra_values: dict | None = None
) -> pd.DataFrame:
    extracted_features = extractor.extract(prompt)

    row = {}
    row.update(extracted_features)
    if extra_values:
        row.update(extra_values)

    feature_df = pd.DataFrame([row])

    for col in feature_columns:
        if col not in feature_df.columns:
            feature_df[col] = 0

    feature_df = feature_df[feature_columns].fillna(0)
    return feature_df
```

This block is load-bearing for the agentic-features compatibility plan from RESEARCH §Pattern 3, step 2: extra columns in the extractor output are silently dropped because `feature_df = feature_df[feature_columns]` trims to whatever the saved artifact was trained on.

**CLI `main()` entry point** (the new `python -m src.routing.decide "<prompt>"` command from D-17). The argparse pattern to mirror is from `src/data/build_classifier_dataset.py:191-228` (NOT the `input()` REPL pattern — that one is for training scripts):

```python
# src/routing/decide.py — main() at bottom of file
def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Route a single prompt and print RoutingDecision as JSON.",
    )
    parser.add_argument("prompt", help="The prompt text to route.")
    args = parser.parse_args()

    decision = decide(prompt=args.prompt)
    print(decision.to_json())
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

---

### `src/routing/schema.py` (dataclass, n/a)

**Analog:** stdlib `dataclasses`; closest in-tree pattern is `BestCandidate` at `src/data/build_classifier_dataset.py:73-91`:

```python
@dataclass
class BestCandidate:
    """Running best-model record for a single question_id."""

    dataset: str = ""
    split: str = ""
    origin_query: str = ""
    prompt: str = ""
    best_model: str = ""
    best_score: float = -math.inf
    best_cost: float = math.inf
    models_seen: set[str] = field(default_factory=set)
```

Mirror this exactly for `RoutingDecision`: use `@dataclass` from stdlib (CONTEXT §`<deferred>` line 179: "Default to stdlib `@dataclass` (no new deps)"), defaults via `field(default_factory=dict)` for the `signals` dict, and a `.to_json()` helper (see RESEARCH §Pattern 4 lines 577-586 for the full signature).

---

### `src/routing/policy.py` (rule cascade, transform)

**Analog:** `choose_final_route` in `src/demo/demo_router.py:245-271`:

```python
def choose_final_route(predicted_model: str, model_mapping: dict):
    if predicted_model in model_mapping:
        model_info = model_mapping[predicted_model].copy()
        model_info["source"] = "model_router"
        return model_info

    if "OTHER" in model_mapping:
        model_info = model_mapping["OTHER"].copy()
        model_info["source"] = "fallback_other"
        model_info["original_prediction"] = predicted_model
        return model_info

    return {
        "display_name": predicted_model,
        "provider": "simulated",
        "tier": "unknown",
        "api_model": None,
        "openrouter_verified": False,
        "source": "unmapped_prediction",
        "notes": "Predicted model was not found in model_mapping.json."
    }
```

The hard-coded rule-cascade from D-01 should follow this same shape (small pure function, dict-returning) but emit a tuple `(backend, model_or_agent, rule_fired)` rather than the dict. Keyword lists go in `src/routing/config.py` per CONTEXT §`<decisions>` line 56.

---

### `src/routing/config.py` (constants module, n/a)

**Analog:** Constants block at the top of `src/task_classifier/train_task_classifier_robust.py:29-51`:

```python
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

SRC_DIR = os.path.join(PROJECT_ROOT, "src", "feature_extraction")
DATA_PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data_processed")

EVALUATION_DIR = os.path.join(PROJECT_ROOT, "evaluation")
PLOTS_DIR = os.path.join(EVALUATION_DIR, "plots")

os.makedirs(EVALUATION_DIR, exist_ok=True)
os.makedirs(PLOTS_DIR, exist_ok=True)

MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
os.makedirs(MODELS_DIR, exist_ok=True)

MODEL_PATH = os.path.join(MODELS_DIR, "task_type_classifier.joblib")
```

Threshold constants must be `SCREAMING_SNAKE_CASE` per CLAUDE.md Naming Patterns. Verbatim from CONTEXT D-10 / RESEARCH lines 452-457:

```python
# src/routing/config.py
DEFAULT_TASK_TYPE_TAU = 0.35       # 10 task-type classes; broad bins
DEFAULT_AGENTIC_INTENT_TAU = 0.55  # binary head; expect crisp probabilities
DEFAULT_MODEL_ROUTER_TAU = 0.20    # 16 model classes; lower max-prob floor by design

FALLBACK_BACKEND = "openrouter"
FALLBACK_MODEL_OR_AGENT = "openrouter/auto"
FALLBACK_RATIONALE_SUFFIX = "low confidence — fallback"  # en-dash, lowercase, verbatim

CLAUDE_CODE_SENTINEL = "claude-agent-sdk"
COMPUTER_USE_SENTINEL = "computer-use-2025-11-24"

BUILD_KEYWORDS = {"build", "write", "edit", "refactor", "fix", "implement", "create"}
BROWSE_KEYWORDS = {"open", "browse", "url", "click", "navigate", "visit", "fill", "submit"}
```

---

### `src/calibration/calibrate.py` (or modifications to existing train scripts) — training script

**Analog:** `train_task_type_classifier` in `src/task_classifier/train_task_classifier_robust.py:338-449` (the full sklearn training pattern).

**Canonical TF-IDF + handcrafted feature stack** (copy verbatim from `src/task_classifier/train_task_classifier_robust.py:367-417`):

```python
X_text_train, X_text_test, X_num_train, X_num_test, y_train, y_test = train_test_split(
    text_data,
    numeric_features,
    y,
    test_size=0.2,
    random_state=42,
    stratify=y
)

# Word TF-IDF learns meaningful terms and short phrases.
# Char TF-IDF helps with code-like text, symbols, short tokens, and wording patterns.
vectorizer = FeatureUnion([
    ("word_tfidf", TfidfVectorizer(
        lowercase=True,
        stop_words=None,
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.95,
        max_features=10000
    )),
    ("char_tfidf", TfidfVectorizer(
        lowercase=True,
        analyzer="char_wb",
        ngram_range=(3, 5),
        min_df=2,
        max_features=6000
    ))
])

X_train_tfidf = vectorizer.fit_transform(X_text_train)
X_test_tfidf = vectorizer.transform(X_text_test)

# Scale numeric handcrafted features.
scaler = StandardScaler()
X_train_num_scaled = scaler.fit_transform(X_num_train)
X_test_num_scaled = scaler.transform(X_num_test)

X_train_num_sparse = csr_matrix(X_train_num_scaled)
X_test_num_sparse = csr_matrix(X_test_num_scaled)

# Combine TF-IDF + handcrafted features.
X_train_combined = hstack([X_train_tfidf, X_train_num_sparse])
X_test_combined = hstack([X_test_tfidf, X_test_num_sparse])

model = LogisticRegression(
    max_iter=1500,
    class_weight="balanced",
    solver="saga",
    C=2.0,
    n_jobs=-1
)
model.fit(X_train_combined, y_train)
```

This is the canonical stack: `FeatureUnion([word_tfidf(1-2gram), char_tfidf(3-5gram)])` ⊕ `csr_matrix(StandardScaler().transform(numeric))` ⊕ `LogisticRegression(max_iter=1500, class_weight="balanced", solver="saga", C=2.0, n_jobs=-1)`. Reuse VERBATIM in `train_agentic_intent.py` and in the calibration retrains for `task_type_classifier` and `model_router`.

**Calibration wrapper** (NEW pattern from RESEARCH §Pattern 1 / §Example 1; this is the post-1.6 sklearn idiom):

```python
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.model_selection import train_test_split

# Step 1: base classifier is already fitted on X_train_combined (existing pattern above).
# Step 2: carve a calibration slice from training data (NOT from the held-out test split).
X_train_only, X_calib, y_train_only, y_calib = train_test_split(
    X_train_combined, y_train,
    test_size=0.2, random_state=42, stratify=y_train,
)

# Step 3: wrap and fit on the calibration slice.
calibrated = CalibratedClassifierCV(
    FrozenEstimator(model),
    method="sigmoid",  # Platt scaling — see RESEARCH §Pattern 1 method-choice table
)
calibrated.fit(X_calib, y_calib)

# Step 4: REPLACE ONLY the "model" field in the artifact dict.
artifacts["model"] = calibrated
joblib.dump(artifacts, output_path)
```

**ANTI-PATTERN to avoid:** RESEARCH §"Anti-Patterns to Avoid" line 851: "Do NOT use `cv='prefit'`". Use `FrozenEstimator` instead — `cv='prefit'` is deprecated in sklearn 1.6 and slated for removal in 1.8.

**ANTI-PATTERN to avoid:** RESEARCH §Pitfall 3 lines 928-936: do NOT calibrate on the held-out test split. Carve a fresh calibration slice from the training data only.

---

### `src/task_classifier/train_agentic_intent.py` (training script)

**Analog:** `src/task_classifier/train_task_classifier_robust.py` — full file (609 lines), every section maps 1-to-1:

- **Path setup** (lines 25-51): copy block, change `INPUT_CSV` and `MODEL_PATH` constants.
- **`get_numeric_feature_columns`** (lines 58-85): copy, then add the 5 new agentic columns explicitly to the keep-list OR just trust the numeric-dtype filter (the deny-list is the canonical pattern — extend `columns_to_remove` rather than allow-list). The deny-list to mirror:

  ```python
  columns_to_remove = [
      "dataset", "split", "origin_query", "prompt",
      "best_model", "best_score", "best_cost",
      "n_models_compared", "models_evaluated",
      "question_type",
  ]
  ```

  For the agentic-intent dataset, replace `"question_type"` with `"label"` (the new binary target column) and drop the benchmark-only fields.

- **`train_*` function** (lines 338-449): mirror exactly. Change function name to `train_agentic_intent_classifier`, target column to `label` (binary), and add the `CalibratedClassifierCV(FrozenEstimator(...))` wrapper before persistence.
- **Plot helpers** (lines 92-331): copy ALL plot functions verbatim; they save to `evaluation/plots/`. The agentic-intent classifier should save to `evaluation/agentic_intent_plots/` instead — mirror the `MODEL_ROUTER_PATH` / `ROUTER_PLOTS_DIR` naming convention from `src/model_router/train_model_router.py:34`.
- **`save_classifier_artifacts` / `load_classifier_artifacts`** (lines 502-546): copy verbatim. Save path → `MODELS_DIR / "agentic_intent_classifier.joblib"`. Required keys: same 5 (`model`, `vectorizer`, `scaler`, `label_encoder`, `feature_columns`).
- **`main()` train/load REPL** (lines 553-607): copy verbatim — CLAUDE.md "Module Design" says "training/demo tools take interactive `input()`."

**Standard sklearn metrics block** (copy verbatim from `:433-447`):

```python
print("\nTask Type Classifier Results")
print("----------------------------")
print(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")
print(f"Macro F1: {f1_score(y_test, y_pred, average='macro'):.4f}")
print(f"Weighted F1: {f1_score(y_test, y_pred, average='weighted'):.4f}")

print("\nClassification Report:")
print(
    classification_report(
        y_test,
        y_pred,
        target_names=label_encoder.classes_,
        zero_division=0
    )
)
```

---

### `src/task_classifier/build_agentic_dataset.py` (data builder)

**Analog:** `src/data/build_classifier_dataset.py` (full file, 232 lines) — the canonical argparse-driven CSV pipeline.

**Argparse pattern** (copy from `src/data/build_classifier_dataset.py:191-228`):

```python
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Path of the input CSV (default: {DEFAULT_INPUT}).",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Path to write the output CSV (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument("-v", "--verbose", action="count", default=1, help="-v info, -vv debug.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _setup_logging(args.verbose)

    if not args.input.exists():
        logging.error("Input CSV not found: %s", args.input)
        return 2
    # ...
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Logging setup** (copy from `:104-114`):

```python
def _setup_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )
```

**Module docstring with CLI invocation** (copy template from `:1-22`):

```python
"""
Build the agentic-intent training CSV from seeds + synthesized + mined negatives.

Output schema: text, label (agentic|conversational), source, dataset

Run from the repo root:

    python -m src.task_classifier.build_agentic_dataset \\
        --seeds-input    data_processed/agentic_intent_seeds.csv \\
        --synthesized-input data_processed/agentic_intent_synthesized.csv \\
        --negatives-input data_processed/agentic_intent_negatives.csv \\
        --output         data_processed/agentic_intent_training.csv
"""
```

**`PROJECT_ROOT` discovery via `pathlib.Path`** (newer pattern, from `:54-56`):

```python
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "data_processed" / "flat_records.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "data_processed" / "classifier_training.csv"
```

**ANTI-PATTERN to avoid:** CLAUDE.md "Import Organization" line: "Do not migrate existing modules to `pathlib` unless explicitly requested." Pipeline scripts (`src/data/*.py`, `src/feature_extraction/build_features.py`) already use `pathlib`; training/demo scripts use `os.path.join`. New `build_agentic_dataset.py` is a pipeline script — use `pathlib`. New `train_agentic_intent.py` is a training script — use `os.path.join`.

---

### `src/feature_extraction/Feature_extractor.py` (MODIFIED — +5 agentic features)

**Analog:** Self — the file itself. The new `_agentic_features` method must mirror the existing `_keyword_features` / `_complexity_features` / `_constraint_features` style.

**Pattern to mirror — `_keyword_features` structure** (`Feature_extractor.py:194-269`):

```python
def _keyword_features(self, text: str) -> dict:
    text = text.lower()

    code_keyword_count = 0
    # ... (one counter per group)

    for keyword in self.code_keywords:
        if keyword in text:
            code_keyword_count += 1
    # ... (one loop per group)

    return {
        "has_code_keywords": 1 if code_keyword_count > 0 else 0,
        "code_keyword_count": code_keyword_count,
        # ... (has_<group> binary + <group>_count integer pairs)
    }
```

**Pattern to mirror — the NLTK lazy-download guard** (`Feature_extractor.py:8-18`):

```python
_NLTK_PUNKT_READY = False


def _ensure_nltk_sentence_tokenizer() -> None:
    """NLTK 3.9+ expects ``punkt_tab`` for ``sent_tokenize``; older installs used ``punkt`` only."""
    global _NLTK_PUNKT_READY
    if _NLTK_PUNKT_READY:
        return
    for package in ("punkt_tab", "punkt"):
        nltk.download(package, quiet=True)
    _NLTK_PUNKT_READY = True
```

`_agentic_features` calls `sent_tokenize()` for the imperative-verb-count feature; it MUST call `_ensure_nltk_sentence_tokenizer()` first, exactly like `_basic_text_features` does at line 130.

**Pattern to mirror — `_safe_text` coercion** (`Feature_extractor.py:21-28`):

```python
def _safe_text(text) -> str:
    if text is None:
        return ""
    if isinstance(text, float) and math.isnan(text):
        return ""
    return str(text).strip()
```

Called from `extract(self, text: str)` at line 102 BEFORE any sub-feature method runs.

**`extract()` orchestration** (`Feature_extractor.py:101-109`):

```python
def extract(self, text: str) -> dict:
    text = _safe_text(text)
    features = {}
    features.update(self._basic_text_features(text))
    features.update(self._symbol_features(text))
    features.update(self._keyword_features(text))
    features.update(self._complexity_features(text))
    features.update(self._constraint_features(text))
    return features
```

Insertion point: add `features.update(self._agentic_features(text))` after `_constraint_features`. RESEARCH §Pattern 3 lines 466-501 supplies the full `_agentic_features` body to drop in.

**RESEARCH §"Compatibility note" (line 503-511):** When `_agentic_features` is added, the dict returned by `extract()` grows by 5 fields. The existing classifiers' `feature_columns` lists do NOT include the new fields. `build_numeric_features` at `src/demo/demo_router.py:101-105` already trims to `feature_df[feature_columns]` so the extra columns are silently dropped during inference. RESEARCH recommends Option A: re-train ALL THREE heads on the extended feature set. Option B (agentic-only features) is acceptable if Option A regresses on Stage-1 or Stage-2 metrics.

---

### `src/feature_extraction/text_inputs.py` (NEW — planner discretion)

**Analog:** Two duplicate sites:
- `src/model_router/train_model_router.py:125-155` — `build_text_input(df: pd.DataFrame) -> pd.Series` (DataFrame-side)
- `src/demo/demo_router.py:110-129` — `build_model_router_text_input(prompt, question_type, keyword_question_type)` (single-prompt-side)

**Code to lift** (preserve both signatures; the new module re-exports them):

```python
# src/feature_extraction/text_inputs.py

import pandas as pd


def build_router_text_input_series(df: pd.DataFrame) -> pd.Series:
    """DataFrame form. Used during training. Lifted from train_model_router.py:125-155."""
    origin_query = df["origin_query"].fillna("").astype(str)

    if "question_type" in df.columns:
        question_type = df["question_type"].fillna("unknown").astype(str)
    else:
        question_type = pd.Series(["unknown"] * len(df), index=df.index)

    if "keyword_question_type" in df.columns:
        keyword_question_type = df["keyword_question_type"].fillna("unknown").astype(str)
    else:
        keyword_question_type = pd.Series(["unknown"] * len(df), index=df.index)

    return (
        origin_query
        + " task_type_"
        + question_type
        + " keyword_type_"
        + keyword_question_type
    )


def build_router_text_input_single(
    prompt: str,
    question_type: str,
    keyword_question_type: str = "unknown",
) -> pd.Series:
    """Single-prompt form. Used during inference. Lifted from demo_router.py:110-129."""
    combined_text = (
        str(prompt)
        + " task_type_"
        + str(question_type)
        + " keyword_type_"
        + str(keyword_question_type)
    )
    return pd.Series([combined_text])
```

Then update both call sites to import from here. RESEARCH §"Anti-Patterns to Avoid" line 853 mandates this consolidation.

---

### `src/evaluation/evaluate_routing.py` (NEW canary eval runner)

**Analog:** `src/evaluation/evaluate_baselines.py` (full file, 436 lines).

**Path setup + artifact loaders** (copy verbatim from `:1-90`):

```python
import os
import sys
import joblib
import numpy as np
import pandas as pd

from sklearn.metrics import accuracy_score, f1_score

# ------------------------------------------------------------
# Path setup
# ------------------------------------------------------------

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

DATA_PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data_processed")
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
EVALUATION_DIR = os.path.join(PROJECT_ROOT, "evaluation")

os.makedirs(EVALUATION_DIR, exist_ok=True)
```

New: `evaluation/routing/` subdirectory (per CONTEXT §`<code_context>` line 145). Add:

```python
ROUTING_EVAL_DIR = os.path.join(EVALUATION_DIR, "routing")
os.makedirs(ROUTING_EVAL_DIR, exist_ok=True)

CANARY_CSV = os.path.join(DATA_PROCESSED_DIR, "routing_decision_eval.csv")
```

**Required-columns guard** (mirror `evaluate_baselines.py:102-109`):

```python
required_columns = [
    "origin_query",
    "best_model",
]

for col in required_columns:
    if col not in df.columns:
        raise ValueError(f"classifier_training.csv is missing required column: {col}")
```

For the canary, required columns are (from RESEARCH §Pattern 5 lines 636-644):
`prompt`, `expected_backend`, `expected_model_or_agent_substring`, `is_fallback_expected`, `edge_case_category`, `source`, `license`.

**Per-strategy `evaluate_predictions` shape** (copy from `:203-224`):

```python
def evaluate_predictions(
    name,
    y_true,
    y_pred,
    cost_df=None,
    notes="",
    evaluation_target="best_model",
):
    return {
        "strategy": name,
        "evaluation_target": evaluation_target,
        "target": evaluation_target,
        "accuracy": accuracy_score(y_true, y_pred),
        "macro_f1": f1_score(y_true, y_pred, average="macro", zero_division=0),
        "weighted_f1": f1_score(y_true, y_pred, average="weighted", zero_division=0),
        "estimated_avg_cost": get_average_cost_for_predictions(y_pred, cost_df),
        "notes": notes,
    }
```

**Main eval loop entry point** (mirror `evaluate_baselines.py:300-433` for shape; `evaluate_routing.py` adds the per-stage ECE + reliability diagram + confusion-matrix outputs per CONTEXT D-16). The metric stack to output:
- `evaluation/routing/backend_accuracy.csv`
- `evaluation/routing/per_backend_pr.csv`
- `evaluation/routing/confusion_matrix.csv` + `.png`
- `evaluation/routing/ece_per_stage.csv`
- `evaluation/routing/low_confidence_rate.txt`
- `evaluation/routing/reliability_diagram_<stage>.png` (one per calibrated head)

**ECE helper** (16-line custom, no new dep — from RESEARCH lines 877-901):

```python
from sklearn.calibration import calibration_curve
import numpy as np


def expected_calibration_error(y_true, y_prob_max, n_bins: int = 10) -> float:
    """ECE on max-class probability for a multiclass classifier."""
    bin_boundaries = np.linspace(0.0, 1.0, n_bins + 1)
    bin_lowers, bin_uppers = bin_boundaries[:-1], bin_boundaries[1:]
    n = len(y_true)
    ece = 0.0
    for lo, hi in zip(bin_lowers, bin_uppers):
        in_bin = (y_prob_max > lo) & (y_prob_max <= hi)
        if in_bin.sum() == 0:
            continue
        accuracy_in_bin = y_true[in_bin].mean()
        mean_confidence_in_bin = y_prob_max[in_bin].mean()
        ece += (in_bin.sum() / n) * abs(accuracy_in_bin - mean_confidence_in_bin)
    return float(ece)
```

**CLI argparse** (NOT `input()` REPL — this is a pipeline script per CLAUDE.md "Module Design"). Copy the argparse pattern from `build_classifier_dataset.py:191-228` and add a `--check` flag that exits non-zero when `backend_accuracy < threshold OR any ECE > threshold` (per RESEARCH line 841).

---

### `src/demo/demo_router.py` (MODIFIED — call `decide()`)

**Analog:** Self.

**`main()` REPL boot pattern to PRESERVE** (`demo_router.py:421-472`):

```python
def main():
    print("\nPrompt Optimizer Demo Router")
    print("----------------------------")
    print("Pipeline: task classifier -> model router")
    print("Loading saved models and route mappings...")

    task_artifacts = load_joblib_artifacts(
        TASK_CLASSIFIER_PATH,
        "task_type_classifier.joblib"
    )
    model_router_artifacts = load_joblib_artifacts(
        MODEL_ROUTER_PATH,
        "model_router.joblib"
    )
    model_mapping = load_json(MODEL_MAPPING_PATH, "model_mapping.json")
    extractor = PromptFeatureExtractor()

    print("\nLoaded successfully.")
    print("Type a prompt to route.")
    print("Type 'quit' to stop.")

    while True:
        prompt = input("\nPrompt: ").strip()

        if prompt.lower() in ["quit", "exit", "q"]:
            print("Goodbye.")
            break

        if not prompt:
            print("Please enter a prompt.")
            continue

        try:
            result = route_prompt(
                prompt=prompt,
                task_artifacts=task_artifacts,
                model_router_artifacts=model_router_artifacts,
                model_mapping=model_mapping,
                extractor=extractor
            )
            print_route_result(result)

        except Exception as error:
            print("\nRouting failed.")
            print(f"Error: {error}")
```

**Modification to make:** `route_prompt` at `:291-341` becomes a thin wrapper that calls `src.routing.decide.decide()` then adapts the `RoutingDecision` back into the legacy dict shape consumed by `print_route_result` at `:359-414`. RESEARCH §Pattern 7 lines 706-731 supplies the sketch.

The `try/except Exception` REPL wrapper at `:459-472` is the canonical "REPL doesn't crash on bad input" pattern (V7 Error Handling in RESEARCH §Security). Keep it intact.

---

### Loader / validator pattern (SHARED — applies to all artifact-consuming code)

**Analog:** `load_joblib_artifacts` in `src/demo/demo_router.py:35-60`:

```python
def load_joblib_artifacts(path: str, artifact_name: str):
    """Load a saved joblib artifact dictionary."""

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{artifact_name} not found at:\n{path}\n\n"
            f"Train/save {artifact_name} first."
        )

    artifacts = joblib.load(path)

    required_keys = [
        "model",
        "vectorizer",
        "scaler",
        "label_encoder",
        "feature_columns",
    ]

    for key in required_keys:
        if key not in artifacts:
            raise KeyError(f"{artifact_name} is missing required key: {key}")

    return artifacts
```

This is the canonical loader. RESEARCH §Pitfall 4 lines 938-946 calls it out as load-bearing for the calibration plan: the calibrated artifact MUST keep these exact 5 keys. The new `agentic_intent_classifier.joblib` MUST also satisfy this validator unmodified. The variant in `src/model_router/train_model_router.py:394-430` (`load_router_artifacts`) adds a sixth key `"target_column"` — that one is for routers (Stage-2 heads), and the agentic-intent head does NOT need it (it's a binary head, not a multi-target router).

**ANTI-PATTERN to avoid:** RESEARCH §Pitfall 4 line 944 mandates: "Calibration replaces ONLY the `model` field; all other keys preserved verbatim." Do not rename `model` to `calibrated_model` or any other refactor — the existing demo validator will fail.

---

### `save_router_artifacts` (SHARED — applies to all training scripts that persist artifacts)

**Analog:** `save_router_artifacts` in `src/model_router/train_model_router.py:370-391`:

```python
def save_router_artifacts(
    model,
    vectorizer,
    scaler,
    label_encoder,
    feature_columns,
    target_column,
    output_path=MODEL_ROUTER_PATH
):
    artifacts = {
        "model": model,
        "vectorizer": vectorizer,
        "scaler": scaler,
        "label_encoder": label_encoder,
        "feature_columns": feature_columns,
        "target_column": target_column,
    }

    joblib.dump(artifacts, output_path)

    print("\nSaved exact model router artifacts to:")
    print(output_path)
```

For the binary agentic-intent head, drop the `target_column` parameter (matches the 5-key shape of `task_type_classifier.joblib`). Use keyword arguments at the call site (CLAUDE.md "Function Design" line: "Heavy use of keyword arguments at call sites").

---

## Shared Patterns

### Path discovery via `__file__`

**Source:** `src/task_classifier/train_task_classifier_robust.py:29-30` (and ~15 other entry-script files):

```python
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
```

**Apply to:** Every new training / inference / eval entry point in `src/routing/`, `src/calibration/`, `src/task_classifier/train_agentic_intent.py`, `src/evaluation/evaluate_routing.py`.

**ANTI-PATTERN to avoid:** RESEARCH §Open Question 4 line 1133 and CLAUDE.md Anti-Patterns line "Path setup duplicated in every script" — the new `src/routing/` is a natural place to extract `src/paths.py`. CONTEXT §`<deferred>` line 180 says "may land opportunistically inside Phase 1 if `src/routing/` would otherwise duplicate, but not required by any success criterion." Planner's call.

### Error handling — `FileNotFoundError` with remediation hint

**Source:** Repeated 6+ times across the codebase. Canonical examples:

- `src/demo/demo_router.py:40-44`:
  ```python
  raise FileNotFoundError(
      f"{artifact_name} not found at:\n{path}\n\n"
      f"Train/save {artifact_name} first."
  )
  ```
- `src/model_router/train_model_router.py:399-403`:
  ```python
  raise FileNotFoundError(
      f"No saved exact model router found at:\n{model_path}\n\n"
      "Run this script in 'train' mode first."
  )
  ```
- `src/model_router_tier/build_router_dataset.py:42-47`:
  ```python
  raise FileNotFoundError(
      f"No saved task classifier found at:\n{model_path}\n\n"
      "Run train_task_classifier_robust.py first and make sure it saves "
      "models/task_type_classifier.joblib."
  )
  ```

**Apply to:** Every loader in `src/routing/`, `src/calibration/`, `src/task_classifier/train_agentic_intent.py`. Always include the remediation hint as the second paragraph.

### Required-key validation — `KeyError` per missing key

**Source:** `src/demo/demo_router.py:56-58`:

```python
for key in required_keys:
    if key not in artifacts:
        raise KeyError(f"{artifact_name} is missing required key: {key}")
```

**Apply to:** Every loader. The agentic-intent artifact loader uses required_keys = `["model", "vectorizer", "scaler", "label_encoder", "feature_columns"]` (NO `target_column`).

### Required-column validation in training scripts

**Source:** `src/task_classifier/train_task_classifier_robust.py:346-350`:

```python
if "origin_query" not in df.columns:
    raise ValueError("CSV must contain an 'origin_query' column.")

if "question_type" not in df.columns:
    raise ValueError("CSV must contain a 'question_type' column.")
```

**Apply to:** `train_agentic_intent.py` (input: `text`, `label`), `build_agentic_dataset.py` (input columns vary by source CSV), `evaluate_routing.py` (canary CSV: `prompt`, `expected_backend`, etc.).

### Metric reporting block

**Source:** `src/task_classifier/train_task_classifier_robust.py:433-447`:

```python
print("\nTask Type Classifier Results")
print("----------------------------")
print(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")
print(f"Macro F1: {f1_score(y_test, y_pred, average='macro'):.4f}")
print(f"Weighted F1: {f1_score(y_test, y_pred, average='weighted'):.4f}")

print("\nClassification Report:")
print(
    classification_report(
        y_test,
        y_pred,
        target_names=label_encoder.classes_,
        zero_division=0
    )
)
```

**Apply to:** `train_agentic_intent.py`, calibration retraining scripts, `evaluate_routing.py` (plus ECE + per-backend P/R extensions).

### Plotting conventions

**Source:** `src/task_classifier/train_task_classifier_robust.py:117-145` (and every other plot helper in the file):

```python
fig, ax = plt.subplots(figsize=(12, 10))
display = ConfusionMatrixDisplay(
    confusion_matrix=cm,
    display_labels=labels
)
display.plot(ax=ax, xticks_rotation=45, values_format="d", colorbar=True)

ax.set_title("Task Type Classifier Confusion Matrix")
plt.tight_layout()

output_path = os.path.join(PLOTS_DIR, "confusion_matrix.png")
plt.savefig(output_path, dpi=300)
plt.close()

print(f"Saved confusion matrix to: {output_path}")
```

**Apply to:** All plot helpers in `evaluate_routing.py` (confusion matrix, reliability diagrams, per-backend P/R). Always: `dpi=300`, `tight_layout()`, `plt.close()`, and a `print(f"Saved {thing} to: {path}")` confirmation.

### Training-script `main()` train/load mode toggle

**Source:** `src/task_classifier/train_task_classifier_robust.py:553-580`:

```python
def main():
    extractor = PromptFeatureExtractor()

    print("\nTask Type Classifier")
    print("--------------------")
    print("Type 'train' to train and save a new model.")
    print("Type 'load' to load the existing saved model.")
    mode = input("\nMode: ").strip().lower()

    if mode == "train":
        df = pd.read_csv(INPUT_CSV)
        model, vectorizer, scaler, label_encoder, feature_columns = train_task_type_classifier(df)
        save_classifier_artifacts(
            model=model,
            vectorizer=vectorizer,
            scaler=scaler,
            label_encoder=label_encoder,
            feature_columns=feature_columns
        )

    elif mode == "load":
        model, vectorizer, scaler, label_encoder, feature_columns = load_classifier_artifacts()

    else:
        print("Invalid mode. Please choose 'train' or 'load'.")
        return
```

**Apply to:** `train_agentic_intent.py`. Mirrors the same pattern at `train_model_router.py:669-707` and `train_tier_router.py:621-655`.

**ANTI-PATTERN to avoid:** CLAUDE.md "Module Design" — training scripts use `input()`; pipeline / eval scripts use `argparse`. Do not mix.

### REPL `try/except` wrapper

**Source:** `src/demo/demo_router.py:459-472`:

```python
while True:
    prompt = input("\nPrompt: ").strip()

    if prompt.lower() in ["quit", "exit", "q"]:
        print("Goodbye.")
        break

    if not prompt:
        print("Please enter a prompt.")
        continue

    try:
        result = route_prompt(...)
        print_route_result(result)

    except Exception as error:
        print("\nRouting failed.")
        print(f"Error: {error}")
```

**Apply to:** Keep verbatim when modifying `demo_router.py`. This is the V7 "decide() MUST NOT crash on any input" mitigation from RESEARCH §Security.

### NLTK lazy-download guard

**Source:** `src/feature_extraction/Feature_extractor.py:8-18` (full code in §`src/feature_extraction/Feature_extractor.py` analog block above).

**Apply to:** Anywhere `_agentic_features` calls `sent_tokenize()`. Mirror the existing call site at `:130-131`:

```python
_ensure_nltk_sentence_tokenizer()
sentences_count = len(sent_tokenize(text))
```

### Test session fixture pattern (NEW — pytest)

**Source:** None in-tree (no pytest today). RESEARCH §Example 3 lines 1018-1037 supplies the canonical template:

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

**Apply to:** All `src/**/tests/conftest.py` files. Session scope is critical — loading the joblib artifacts is expensive (5MB+ each) and they're read-only across all tests.

### Forbidden-import smoke test (NEW — D-18 enforcement)

**Source:** RESEARCH §Pattern 4 lines 613-628:

```python
# src/routing/tests/test_decide_smoke.py
import sys

def test_no_forbidden_modules_imported_after_decide():
    forbidden = {"fastapi", "httpx", "requests", "aiohttp", "anthropic", "openai"}
    for name in list(sys.modules):
        if name.split(".")[0] in forbidden:
            del sys.modules[name]

    import src.routing.decide  # noqa: F401

    leaked = {name.split(".")[0] for name in sys.modules} & forbidden
    assert not leaked, f"src.routing.decide leaked imports: {sorted(leaked)}"
```

**Apply to:** `src/routing/tests/test_decide_smoke.py`. The exact substring set is locked: `{"fastapi", "httpx", "requests", "aiohttp", "anthropic", "openai"}` (CONTEXT §`<specifics>` line 168).

### Fallback-rationale assertion (NEW — success criterion #4)

**Source:** RESEARCH §Example 4 lines 1041-1060. The EXACT substring is `"low confidence — fallback"` (en-dash U+2014, lowercase). Per CONTEXT §`<specifics>` line 160 this is locked.

```python
def test_fallback_rationale_phrase(task_artifacts, model_router_artifacts, agentic_intent_artifacts):
    artifacts = {
        "task_type_classifier": task_artifacts,
        "model_router": model_router_artifacts,
        "agentic_intent_classifier": agentic_intent_artifacts,
        "model_mapping": {...},
    }
    decision = decide(prompt="asdfgh", artifacts=artifacts)
    assert decision.backend == "openrouter"
    assert decision.model_or_agent == "openrouter/auto"
    assert decision.rationale.endswith("low confidence — fallback"), (
        f"Expected rationale to end with 'low confidence — fallback' (en-dash), got: {decision.rationale!r}"
    )
```

**Apply to:** `src/routing/tests/test_uncertainty_fallback.py`. Multiple gibberish / emoji-only / single-token prompts should each assert this same suffix.

### `model_mapping.json` lookup contract

**Source:** `config/model_mapping.json` — the OpenRouter fallback entry (lines 26-33):

```json
"openrouter": {
  "display_name": "OpenRouter Auto Router",
  "provider": "openrouter",
  "tier": "medium",
  "api_model": "openrouter/auto",
  "openrouter_verified": true,
  "notes": "Verified OpenRouter auto-router model ID."
}
```

And the `OTHER` fallback (lines 122-129):

```json
"OTHER": {
  "display_name": "Other Model",
  "provider": "simulated",
  "tier": "medium",
  "api_model": null,
  "openrouter_verified": false,
  "notes": "Fallback route for models outside the top-model target set."
}
```

**Apply to:** `src/routing/decide.py` MUST resolve the OpenRouter fallback via `model_mapping["openrouter"]["api_model"]` → `"openrouter/auto"` (CONTEXT §`<specifics>` line 161). The `OTHER` entry is the catch-all for unverified model_router predictions; `choose_final_route` at `:245-271` already implements this.

---

## No Analog Found

Files genuinely net-new in the repository with no in-tree analog. Planner should use RESEARCH.md patterns directly.

| File | Role | Data Flow | Reason | RESEARCH Reference |
|------|------|-----------|--------|---------------------|
| `pyproject.toml` | build config | n/a | First lockfile in the repo (`ls` confirmed missing) | RESEARCH §Standard Stack lines 152-187 supplies full skeleton |
| `uv.lock` | lockfile | n/a | Generated by `uv sync`; never hand-edited | RESEARCH §Pattern 8 lines 750-758 |
| `.gitignore` | VCS config | n/a | `ls -la` confirmed only `.gitattributes` exists | RESEARCH §Pattern 8 lines 762-799 supplies full template |
| `.github/workflows/ci.yml` | CI config | n/a | INTEGRATIONS.md says "No CI Pipeline" today | RESEARCH §Example 5 lines 1062-1080 supplies full workflow |
| `src/routing/schema.py` | dataclass | request-response | First domain dataclass in the project | RESEARCH §Pattern 4 lines 569-608 supplies signature; closest in-tree shape is `BestCandidate` at `src/data/build_classifier_dataset.py:73-91` (use stdlib `@dataclass`) |
| Any `src/**/tests/` test file | unit / integration test | n/a | No tests exist in the repo today; pytest is a new dependency | RESEARCH §Validation Architecture lines 1167-1217 lists required tests; §Examples 3-4 supply fixture + assertion templates |
| `models/uncalibrated/` directory | one-time backup | file I/O | New convention; one-time `cp` before calibration overwrite | RESEARCH §Pitfall 6 lines 965-973 |
| `evaluation/baselines.json` | regression-guard snapshot | file I/O | One-time committed snapshot of pre-calibration metrics | RESEARCH §Pattern 7 line 740 |

---

## Anti-Patterns to AVOID (consolidated from CLAUDE.md + CONTEXT + RESEARCH)

| Anti-Pattern | Source | Why It Matters in Phase 1 |
|--------------|--------|----------------------------|
| Renaming `Feature_extractor.py` → `feature_extractor.py` | CLAUDE.md Constraints + CONTEXT `<code_context>` line 152 + RESEARCH line 858 | Four importers break (`demo_router.py:28`, `train_task_classifier_robust.py:48`, `build_router_dataset.py:27`, `build_features.py:18`); planner must defer the rename to a dedicated cleanup phase |
| Renaming `build_top_model_datatset.py` (typo'd) | CLAUDE.md Constraints + CONTEXT `<code_context>` line 153 + RESEARCH line 858 | Churns ReadMe.md run order without delivering routing value; defer |
| Re-shaping the standard 5-key joblib artifact dict (`model`, `vectorizer`, `scaler`, `label_encoder`, `feature_columns`) | RESEARCH §Pitfall 4 lines 938-946 + CONTEXT §`<specifics>` line 167 | `load_joblib_artifacts` at `src/demo/demo_router.py:35` validates exact keys; renaming `model` to `calibrated_model` (or anything) breaks the demo |
| Using `CalibratedClassifierCV(base, cv="prefit")` | RESEARCH §Pattern 1 line 378 + §Anti-Patterns line 851 + §Pitfall 1 lines 905-914 | Deprecated in sklearn 1.6 (late 2024), slated for removal in 1.8; use `FrozenEstimator` instead |
| Calibrating on the held-out test split | RESEARCH §Pitfall 3 lines 928-936 | Test split must stay disjoint for honest post-calibration metrics; carve a fresh calibration slice from training data |
| Duplicating the Stage-2 text input format `"<query> task_type_X keyword_type_Y"` in `src/routing/` | RESEARCH §Anti-Patterns line 853 + CONTEXT §`<code_context>` line 150 + CLAUDE.md Anti-Patterns "Stage-2 text input format is duplicated by string concatenation" | Lift `build_text_input` + `build_model_router_text_input` into a shared helper in `src/feature_extraction/text_inputs.py` |
| Adding another `sys.path.append(SRC_DIR)` site | RESEARCH §Anti-Patterns line 854 + CONTEXT §`<code_context>` line 151 + CLAUDE.md Anti-Patterns "Per-script `sys.path` injection" | Make `src/routing/` a proper package; use `python -m src.routing.decide` invocation; import `from src.feature_extraction.Feature_extractor import PromptFeatureExtractor` |
| Silently falling back to Claude Code or computer-use | RESEARCH §Anti-Patterns line 855 + CONTEXT D-12 line 60 | Fallback is ALWAYS OpenRouter (`openrouter/auto`), no exceptions |
| Introducing HTTP libraries (`fastapi`, `httpx`, `requests`, `aiohttp`, `anthropic`, `openai`) into the routing brain | RESEARCH §Anti-Patterns line 856 + CONTEXT D-18 line 80 + RESEARCH §Pattern 4 lines 610-628 | Enforced by smoke test in `src/routing/tests/test_decide_smoke.py`; the test runs in CI |
| Hard-coding per-stage thresholds inside `decide.py` as bare numeric literals | RESEARCH §Anti-Patterns line 857 + CONTEXT D-10 lines 54-58 | Defaults live in `src/routing/config.py` as named constants (`DEFAULT_TASK_TYPE_TAU` etc.); runtime overrides via the `settings` dict argument |
| Skipping the `models/uncalibrated/` backup before overwriting | RESEARCH §Pitfall 6 lines 965-973 + §Anti-Patterns line 859 | Calibration retrain is destructive; one-time `cp` makes it reversible |
| Migrating existing `os.path.join` modules to `pathlib` opportunistically | CLAUDE.md "Import Organization" | `pathlib` is conventional in `src/data/*.py` and `src/feature_extraction/build_features.py`; everywhere else uses `os.path.join`. Match the surrounding file. |
| Modifying `Feature_extractor.py` line 8 `_NLTK_PUNKT_READY` global guard | RESEARCH §Pitfall 5 lines 948-963 + CLAUDE.md "Cross-Cutting Concerns" | Lazy download is a process-level flag; CI must pre-fetch NLTK data before pytest runs. Don't refactor the guard. |
| Using `argparse` for training-script `main()` | CLAUDE.md "Module Design" "training/demo tools take interactive `input()`" | Mismatch with `train_task_classifier_robust.py:560`, `train_model_router.py:675`, `train_tier_router.py:627`. New `train_agentic_intent.py` uses `input()`; new `build_agentic_dataset.py` and `evaluate_routing.py` use `argparse`. |

---

## Metadata

**Analog search scope:**
- `src/feature_extraction/` (2 files + `__init__.py`)
- `src/task_classifier/` (3 files)
- `src/model_router/` (4 files)
- `src/model_router_tier/` (3 files)
- `src/data/` (3 files + `__init__.py`)
- `src/demo/` (2 files)
- `src/evaluation/` (2 files)
- `config/` (1 file)
- `models/` (4 artifacts)
- Repo root (verified absence of `.gitignore`, `pyproject.toml`, `.github/`)

**Files scanned in full:** 9 (`demo_router.py`, `Feature_extractor.py`, `train_task_classifier_robust.py`, `build_question_type.py`, `build_features.py`, `build_classifier_dataset.py`, `evaluate_baselines.py`, `model_mapping.json`, `01-CONTEXT.md`)

**Files scanned partially (targeted ranges):** 5 (`train_model_router.py` lines 1-170 + 370-491, `build_router_dataset.py`, `build_top_model_datatset.py`, `flatten_raw_jsons.py` lines 1-150, `01-RESEARCH.md` chunks)

**Pattern extraction date:** 2026-05-11

**Confidence breakdown:**
- Saved-artifact joblib dict shape: HIGH (verified across 4 existing `models/*.joblib` and 2 loaders)
- TF-IDF + handcrafted feature stack: HIGH (verified pattern repeated verbatim in 3 training scripts)
- Path-discovery preamble: HIGH (verified pattern in ~12 entry-script files)
- Error-handling style: HIGH (verified pattern in 6+ loader functions)
- pytest fixture + test conventions: MEDIUM (no in-tree pytest; relying on RESEARCH §Example 3-4 templates)
- `pyproject.toml` / `uv.lock` / `.gitignore` / CI yaml: MEDIUM (no in-tree analog; relying on RESEARCH §Pattern 8 + §Example 5)
- `RoutingDecision` dataclass shape: MEDIUM (no in-tree multi-field dataclass with `to_json`; closest is `BestCandidate` + stdlib `@dataclass` recommendation from CONTEXT §`<deferred>`)
