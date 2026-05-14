# Plan 04 — ROUTER-01 — train_agentic_intent.py persists a binary classifier
# to models/agentic_intent_classifier.joblib using the canonical 5-key artifact
# dict shape ({model, vectorizer, scaler, label_encoder, feature_columns}) so
# load_joblib_artifacts() in src/demo/demo_router.py accepts it unmodified.
#
# These tests require BOTH Plan 03's CSV
# (data_processed/agentic_intent_training.csv) AND Plan 04's trained joblib
# (models/agentic_intent_classifier.joblib). If either is missing, the
# corresponding test calls pytest.skip() with a remediation hint pointing
# at the training script — never pytest.skip() at module level (Plan 01-01
# RED-stub contract).

import os
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from scipy.sparse import hstack, csr_matrix
from sklearn.metrics import f1_score
from sklearn.model_selection import train_test_split


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TRAINING_CSV = PROJECT_ROOT / "data_processed" / "agentic_intent_training.csv"
ARTIFACT_PATH = PROJECT_ROOT / "models" / "agentic_intent_classifier.joblib"

# Make `Feature_extractor` importable from src/feature_extraction/ — same
# sys.path injection pattern used by every other src/<pkg>/*.py file.
_SRC_FE_DIR = PROJECT_ROOT / "src" / "feature_extraction"
if str(_SRC_FE_DIR) not in sys.path:
    sys.path.append(str(_SRC_FE_DIR))


_ARTIFACT_MISSING_HINT = (
    "models/agentic_intent_classifier.joblib not built yet. Run "
    "`uv run python -m src.task_classifier.train_agentic_intent` first."
)


def _load_artifact_or_skip() -> dict:
    """Helper used by Plan 04 tests to skip cleanly if the artifact is missing."""
    if not ARTIFACT_PATH.exists():
        pytest.skip(_ARTIFACT_MISSING_HINT)
    return joblib.load(ARTIFACT_PATH)


# --------------------------------------------------------------------------- #
# Plan 03 — dataset-shape contract (REQUIREMENT-ID: ROUTER-01 prerequisite)   #
# --------------------------------------------------------------------------- #


def test_dataset_csv_well_formed() -> None:
    """data_processed/agentic_intent_training.csv satisfies the locked schema.

    Mirrors `build_agentic_dataset.py --check`:
      - 4 columns exactly: text, label, source, dataset
      - >= 800 rows (target ~1000)
      - label cardinality is exactly {agentic, conversational}
      - balance is within [0.45, 0.55] for the agentic class
      - no NaN in label column
      - no duplicate (text, label) rows
    """
    if not TRAINING_CSV.exists():
        pytest.skip(
            "data_processed/agentic_intent_training.csv not built yet. "
            "Run `uv run python -m src.task_classifier.build_agentic_dataset` first."
        )

    df = pd.read_csv(TRAINING_CSV)

    expected_columns = {"text", "label", "source", "dataset"}
    assert set(df.columns) == expected_columns, (
        f"Columns {sorted(df.columns)} != expected {sorted(expected_columns)}"
    )

    n = len(df)
    assert 800 <= n <= 1100, f"Row count {n} outside [800, 1100]"

    assert df["label"].notna().all(), "Found NaN in label column"

    labels = set(df["label"].unique())
    assert labels == {"agentic", "conversational"}, (
        f"Label cardinality {sorted(labels)} != {{'agentic', 'conversational'}}"
    )

    n_ag = int((df["label"] == "agentic").sum())
    ag_ratio = n_ag / n
    assert 0.45 <= ag_ratio <= 0.55, (
        f"Class balance out of bounds: agentic={n_ag}/{n} = {ag_ratio:.3f}; "
        f"required 0.45 <= ratio <= 0.55"
    )

    dupes = df.duplicated(subset=["text", "label"]).sum()
    assert dupes == 0, f"Found {dupes} duplicate (text, label) rows"


# --------------------------------------------------------------------------- #
# Plan 04 — calibrated binary classifier contract (ROUTER-01)                 #
# --------------------------------------------------------------------------- #


def test_artifact_loads_with_canonical_5_keys() -> None:
    """models/agentic_intent_classifier.joblib has exactly the canonical 5 keys.

    Asserts:
      - All 5 canonical keys present: model, vectorizer, scaler, label_encoder,
        feature_columns (Pitfall 4 regression guard).
      - `target_column` is NOT in keys — binary head; absence is the contract
        so load_joblib_artifacts() validator at src/demo/demo_router.py:35
        accepts it unmodified.
      - LabelEncoder classes sorted alphabetically as ['agentic', 'conversational'].
    """
    artifacts = _load_artifact_or_skip()

    required = {"model", "vectorizer", "scaler", "label_encoder", "feature_columns"}
    missing = required - set(artifacts.keys())
    assert not missing, f"agentic_intent_classifier.joblib missing keys: {missing}"

    assert "target_column" not in artifacts, (
        "Binary head must NOT have a target_column key — the canonical 5-key "
        "shape is the contract for load_joblib_artifacts() at src/demo/demo_router.py:35"
    )

    label_encoder = artifacts["label_encoder"]
    classes = list(label_encoder.classes_)
    assert classes == ["agentic", "conversational"], (
        f"LabelEncoder classes {classes} != ['agentic', 'conversational']"
    )


def test_calibrated_predict_proba_shape() -> None:
    """`model.predict_proba(X)` returns a calibrated (1, 2) row that sums to ~1.

    Builds a single-prompt feature matrix using the same TF-IDF + scaled-numeric
    + hstack pipeline used by training (mirrors src/demo/demo_router.py's
    predict_task_type for a single prompt). Asserts:

      - predict_proba shape == (1, 2)
      - row sums to ~1.0 (±0.01)
      - for an obviously-agentic prompt, P(agentic) > 0.5 (soft assertion;
        a failure here signals a training-data quality issue from Plan 03)
    """
    from Feature_extractor import PromptFeatureExtractor

    artifacts = _load_artifact_or_skip()
    model = artifacts["model"]
    vectorizer = artifacts["vectorizer"]
    scaler = artifacts["scaler"]
    label_encoder = artifacts["label_encoder"]
    feature_columns = artifacts["feature_columns"]

    extractor = PromptFeatureExtractor()

    prompt = "build me a CLI tool"

    text_features = vectorizer.transform(pd.Series([prompt]))

    extracted = extractor.extract(prompt)
    feature_df = pd.DataFrame([extracted])
    for col in feature_columns:
        if col not in feature_df.columns:
            feature_df[col] = 0
    feature_df = feature_df[feature_columns].fillna(0)

    numeric_scaled = scaler.transform(feature_df)
    numeric_sparse = csr_matrix(numeric_scaled)

    combined = hstack([text_features, numeric_sparse])

    proba = model.predict_proba(combined)

    assert proba.shape == (1, 2), f"predict_proba shape {proba.shape} != (1, 2)"

    row_sum = float(proba[0].sum())
    assert abs(row_sum - 1.0) <= 0.01, (
        f"predict_proba row does not sum to ~1.0 (got {row_sum:.6f})"
    )

    agentic_idx = int(label_encoder.transform(["agentic"])[0])
    p_agentic = float(proba[0, agentic_idx])
    assert p_agentic > 0.5, (
        f"P(agentic | 'build me a CLI tool') = {p_agentic:.4f} <= 0.5. "
        "This is a soft assertion — failure signals a training-data quality "
        "issue from Plan 03 or a feature-stack regression."
    )


def test_held_out_macro_f1_meets_soft_target() -> None:
    """Soft regression guard: held-out macro-F1 >= 0.75 (RESEARCH §Pattern 3 soft floor).

    The target is 0.80 per the plan's `<must_haves>`; the test bar is set at
    0.75 to absorb cross-platform floating-point drift in TF-IDF / scaler /
    calibration. A failure here signals either:
      - a training-data quality issue from Plan 03 (mislabeled cluster, drift)
      - a feature-stack regression (extractor output changed shape)
      - a calibration wrapper mis-fit
    """
    from Feature_extractor import PromptFeatureExtractor

    if not TRAINING_CSV.exists():
        pytest.skip(
            "data_processed/agentic_intent_training.csv not built yet. "
            "Run `uv run python -m src.task_classifier.build_agentic_dataset` first."
        )

    artifacts = _load_artifact_or_skip()
    model = artifacts["model"]
    vectorizer = artifacts["vectorizer"]
    scaler = artifacts["scaler"]
    label_encoder = artifacts["label_encoder"]
    feature_columns = artifacts["feature_columns"]

    extractor = PromptFeatureExtractor()

    df = pd.read_csv(TRAINING_CSV)
    df = df.copy()
    df["text"] = df["text"].fillna("").astype(str)
    df = df[df["text"].str.len() > 0]
    df = df[df["label"].notna()]
    df = df.reset_index(drop=True)

    y = label_encoder.transform(df["label"].astype(str))

    # Re-run the same deterministic split used in train_agentic_intent.py.
    # We only need indices to slice the test rows for prediction.
    indices = np.arange(len(df))
    _, test_idx, _, y_test = train_test_split(
        indices,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )

    test_df = df.iloc[test_idx].reset_index(drop=True)
    text_series = test_df["text"].fillna("").astype(str)

    text_features = vectorizer.transform(text_series)

    numeric_rows = []
    for raw in text_series.tolist():
        numeric_rows.append(extractor.extract(raw))
    numeric_df = pd.DataFrame(numeric_rows).fillna(0)
    for col in feature_columns:
        if col not in numeric_df.columns:
            numeric_df[col] = 0
    numeric_df = numeric_df[feature_columns].fillna(0)

    numeric_scaled = scaler.transform(numeric_df)
    numeric_sparse = csr_matrix(numeric_scaled)

    combined = hstack([text_features, numeric_sparse])

    y_pred = model.predict(combined)
    macro_f1 = f1_score(y_test, y_pred, average="macro")

    if macro_f1 < 0.75:
        pytest.fail(
            f"macro-F1 {macro_f1:.4f} below 0.75 floor — "
            "check training data quality (Plan 03) and feature-stack integrity (Plan 02)"
        )
