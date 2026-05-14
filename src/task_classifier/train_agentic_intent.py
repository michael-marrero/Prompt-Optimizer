"""
Train a calibrated binary agentic-intent classifier (ROUTER-01).

Reuses the canonical sklearn TF-IDF + handcrafted-feature stack from
`train_task_classifier_robust.py` (per CLAUDE.md and 01-PATTERNS.md), and
wraps the fitted base classifier in `CalibratedClassifierCV(FrozenEstimator(...))`
for calibrated probabilities (per ROUTER-03 + RESEARCH §Pattern 1, the
post-sklearn-1.6 idiom).

Persists `models/agentic_intent_classifier.joblib` in the canonical 5-key
dict shape `{model, vectorizer, scaler, label_encoder, feature_columns}`
so the existing `load_joblib_artifacts()` validator at
`src/demo/demo_router.py:35` accepts it unmodified.

Imperative-verb set (locked, 26 verbs, RESEARCH §Pattern 3 lines 472-478)
and action-keyword set (locked, 7 verbs, RESEARCH §Pattern 3 line 491) are
defined inside `PromptFeatureExtractor._agentic_features` (Plan 01-02).

Usage:
    uv run python -m src.task_classifier.train_agentic_intent
"""

import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from scipy.sparse import hstack, csr_matrix

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    classification_report,
    confusion_matrix,
    ConfusionMatrixDisplay,
    precision_recall_fscore_support,
)
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.pipeline import FeatureUnion
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
import joblib


# ------------------------------------------------------------
# Path setup
# ------------------------------------------------------------

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

SRC_DIR = os.path.join(PROJECT_ROOT, "src", "feature_extraction")
DATA_PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data_processed")

EVALUATION_DIR = os.path.join(PROJECT_ROOT, "evaluation")
PLOTS_DIR = os.path.join(EVALUATION_DIR, "agentic_intent_plots")

os.makedirs(EVALUATION_DIR, exist_ok=True)
os.makedirs(PLOTS_DIR, exist_ok=True)

MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
os.makedirs(MODELS_DIR, exist_ok=True)

MODEL_PATH = os.path.join(MODELS_DIR, "agentic_intent_classifier.joblib")
if SRC_DIR not in sys.path:
    sys.path.append(SRC_DIR)

from Feature_extractor import PromptFeatureExtractor


INPUT_CSV = os.path.join(DATA_PROCESSED_DIR, "agentic_intent_training.csv")


# ------------------------------------------------------------
# Feature column helper
# ------------------------------------------------------------

def get_numeric_feature_columns(df: pd.DataFrame) -> list:
    """
    Return only numeric handcrafted feature columns.

    Drops the string columns from the agentic-intent training CSV
    (text, label, source, dataset) and keeps every numeric-dtype column,
    including the 5 new agentic-intent features added in Plan 01-02
    (imperative_verb_count, has_url, has_file_path, has_code_fence,
    has_action_keyword).
    """

    columns_to_remove = [
        "text",
        "label",
        "source",
        "dataset",
    ]

    feature_columns = []

    for col in df.columns:
        if col not in columns_to_remove:
            if pd.api.types.is_numeric_dtype(df[col]):
                feature_columns.append(col)

    return feature_columns


# ------------------------------------------------------------
# Text + numeric feature builders
# ------------------------------------------------------------

def build_text_input(df: pd.DataFrame) -> pd.Series:
    """
    Return the text column for TF-IDF.

    No Stage-2 router smuggling format here — this is a binary head trained
    on raw prompts.
    """

    return df["text"].fillna("").astype(str)


def build_numeric_features(
    df: pd.DataFrame,
    extractor: PromptFeatureExtractor,
) -> pd.DataFrame:
    """
    Apply PromptFeatureExtractor.extract() to every row's text.

    Plan 01-02 extended the extractor to emit 5 new agentic-intent keys
    on every call, so every row of the returned DataFrame contains the
    same numeric column set.
    """

    rows = []
    for raw_text in df["text"].fillna("").astype(str).tolist():
        features = extractor.extract(raw_text)
        rows.append(features)

    feature_df = pd.DataFrame(rows).fillna(0)

    return feature_df


# ------------------------------------------------------------
# Evaluation plots
# ------------------------------------------------------------

def plot_confusion_matrix_for_agentic(y_test, y_pred, label_encoder):
    """
    Save a raw-count confusion matrix for the binary agentic-intent classifier.
    """

    labels = label_encoder.classes_
    cm = confusion_matrix(y_test, y_pred)

    fig, ax = plt.subplots(figsize=(8, 6))
    display = ConfusionMatrixDisplay(
        confusion_matrix=cm,
        display_labels=labels
    )

    display.plot(
        ax=ax,
        xticks_rotation=0,
        values_format="d",
        colorbar=True
    )

    ax.set_title("Agentic Intent Classifier Confusion Matrix")
    plt.tight_layout()

    output_path = os.path.join(PLOTS_DIR, "confusion_matrix.png")
    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"Saved confusion matrix to: {output_path}")


def plot_reliability_diagram(model, X_test_combined, y_test, label_encoder):
    """
    Save a reliability diagram (calibration curve) for the calibrated binary
    classifier. The agentic class is treated as the positive class.

    Buckets predicted probability into 10 bins and plots fraction-of-positives
    vs. mean-predicted-probability per bin. A perfectly calibrated classifier
    lies on the y=x line.
    """

    from sklearn.calibration import calibration_curve

    # Identify the agentic class index in the LabelEncoder.
    classes = list(label_encoder.classes_)
    if "agentic" in classes:
        positive_idx = classes.index("agentic")
    else:
        positive_idx = 0

    proba = model.predict_proba(X_test_combined)[:, positive_idx]
    y_true_binary = (y_test == positive_idx).astype(int)

    frac_pos, mean_pred = calibration_curve(
        y_true_binary,
        proba,
        n_bins=10,
        strategy="uniform",
    )

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot([0, 1], [0, 1], linestyle="--", label="Perfectly calibrated")
    ax.plot(mean_pred, frac_pos, marker="o", label="Agentic Intent Classifier")

    ax.set_xlabel("Mean predicted probability (agentic)")
    ax.set_ylabel("Fraction of positives")
    ax.set_title("Agentic Intent Classifier Reliability Diagram")
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.0)
    ax.legend(loc="best")

    plt.tight_layout()

    output_path = os.path.join(PLOTS_DIR, "reliability_diagram.png")
    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"Saved reliability diagram to: {output_path}")


# ------------------------------------------------------------
# Calibration error helper (16-line ECE; RESEARCH §"Don't Hand-Roll" — sklearn
# deliberately does not ship this; netcal rejected for Phase 1 dep weight)
# ------------------------------------------------------------

def expected_calibration_error(
    y_true: np.ndarray,
    proba: np.ndarray,
    n_bins: int = 10,
) -> float:
    """
    ECE on max-class probability for a multiclass classifier.

    For the binary head this collapses to the standard ECE on
    `proba[:, 1]` since max-prob equals positive-prob whenever the
    classifier predicts the positive class and 1 - positive-prob otherwise.
    """

    pred_class = proba.argmax(axis=1)
    confidences = proba.max(axis=1)
    accuracies = (pred_class == y_true).astype(float)

    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = len(y_true)
    if n == 0:
        return 0.0

    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        # Right edge inclusive on the last bin so a confidence of 1.0 counts.
        if i == n_bins - 1:
            mask = (confidences >= lo) & (confidences <= hi)
        else:
            mask = (confidences >= lo) & (confidences < hi)
        if mask.sum() == 0:
            continue
        bin_acc = accuracies[mask].mean()
        bin_conf = confidences[mask].mean()
        ece += (mask.sum() / n) * abs(bin_acc - bin_conf)

    return float(ece)


# ------------------------------------------------------------
# Training
# ------------------------------------------------------------

def train_agentic_intent_classifier(
    df: pd.DataFrame,
    extractor: PromptFeatureExtractor,
):
    """
    Train a calibrated binary agentic-intent classifier.

    Pipeline:
    - Word + char TF-IDF on the raw `text` column
    - StandardScaler on handcrafted numeric features from PromptFeatureExtractor
    - LogisticRegression (max_iter=1500, class_weight="balanced", solver="saga",
      C=2.0, n_jobs=-1) fitted on a 0.2-stratified train/test split
    - CalibratedClassifierCV(FrozenEstimator(model), method="sigmoid")
      fitted on a fresh 0.25 calibration slice carved from the training
      set so the calibrator never sees test data and the base classifier
      is not refit (RESEARCH §Pattern 1 — sklearn 1.6+ idiom)

    Returns:
        (calibrated, vectorizer, scaler, label_encoder, feature_columns)
    """

    if "text" not in df.columns:
        raise ValueError("CSV must contain a 'text' column.")

    if "label" not in df.columns:
        raise ValueError("CSV must contain a 'label' column.")

    # Drop rows with empty text or missing label.
    df = df.copy()
    df["text"] = df["text"].fillna("").astype(str)
    df = df[df["text"].str.len() > 0]
    df = df[df["label"].notna()]
    df = df.reset_index(drop=True)

    text_data = build_text_input(df)
    numeric_features = build_numeric_features(df, extractor)
    feature_columns = get_numeric_feature_columns(numeric_features)

    print("\nUsing numeric feature columns:")
    print(feature_columns)
    print(f"\nTotal numeric features: {len(feature_columns)}")

    numeric_features = numeric_features[feature_columns].fillna(0)

    labels = df["label"].astype(str)
    label_encoder = LabelEncoder()
    y = label_encoder.fit_transform(labels)

    X_text_train, X_text_test, X_num_train, X_num_test, y_train, y_test = train_test_split(
        text_data,
        numeric_features,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
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

    # Base classifier — fitted on the DISJOINT train slice (X_train_only)
    # after the calibration split below, so FrozenEstimator wraps a model
    # that never saw X_calib (Pitfall 3 — fixes CR-01 from 01-REVIEW.md).
    model = LogisticRegression(
        max_iter=1500,
        class_weight="balanced",
        solver="saga",
        C=2.0,
        n_jobs=-1,
    )

    # ------------------------------------------------------------
    # Calibration step (RESEARCH §Pattern 1; sklearn 1.6+ FrozenEstimator)
    # Carve a fresh calibration slice FROM the training data only —
    # never from the held-out test split (Pitfall 3). The base is then
    # fit on X_train_only (the disjoint complement) so the calibrator
    # sees out-of-sample predictions.
    # FrozenEstimator wraps the fitted base; CalibratedClassifierCV does
    # NOT refit the base — it only fits the calibration head on the slice.
    # ------------------------------------------------------------
    X_train_only, X_calib, y_train_only, y_calib = train_test_split(
        X_train_combined,
        y_train,
        test_size=0.25,
        random_state=42,
        stratify=y_train,
    )

    # Fit base on the disjoint train slice, NOT the full X_train_combined.
    model.fit(X_train_only, y_train_only)

    calibrated = CalibratedClassifierCV(
        FrozenEstimator(model),
        method="sigmoid",
    )
    calibrated.fit(X_calib, y_calib)

    y_pred = calibrated.predict(X_test_combined)

    # ------------------------------------------------------------
    # Metrics + plots
    # ------------------------------------------------------------
    plot_confusion_matrix_for_agentic(y_test, y_pred, label_encoder)
    plot_reliability_diagram(calibrated, X_test_combined, y_test, label_encoder)

    test_proba = calibrated.predict_proba(X_test_combined)
    ece = expected_calibration_error(y_test, test_proba, n_bins=10)

    print("\nAgentic Intent Classifier Results")
    print("---------------------------------")
    print(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")
    print(f"Macro F1: {f1_score(y_test, y_pred, average='macro'):.4f}")
    print(f"Weighted F1: {f1_score(y_test, y_pred, average='weighted'):.4f}")
    print(f"Expected Calibration Error (10 bins): {ece:.4f}")

    print("\nClassification Report:")
    print(
        classification_report(
            y_test,
            y_pred,
            target_names=label_encoder.classes_,
            zero_division=0,
        )
    )

    return calibrated, vectorizer, scaler, label_encoder, feature_columns


# ------------------------------------------------------------
# Persistence
# ------------------------------------------------------------

def save_classifier_artifacts(
    *,
    model,
    vectorizer,
    scaler,
    label_encoder,
    feature_columns,
    output_path=MODEL_PATH,
):
    """
    Save all trained classifier artifacts needed for later prediction.

    Writes the canonical 5-key dict so that `load_joblib_artifacts()` at
    src/demo/demo_router.py:35 accepts the file unmodified.
    """

    artifacts = {
        "model": model,
        "vectorizer": vectorizer,
        "scaler": scaler,
        "label_encoder": label_encoder,
        "feature_columns": feature_columns,
    }

    joblib.dump(artifacts, output_path)

    print(f"\nSaved agentic intent classifier artifacts to:\n{output_path}")


def load_classifier_artifacts(model_path=MODEL_PATH):
    """
    Load trained classifier artifacts from disk.

    Mirrors the canonical loader: FileNotFoundError with a remediation hint
    if the artifact is missing; KeyError per missing required key.
    """

    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"No saved model found at {model_path}.\n"
            f"Run this script in 'train' mode first:\n"
            f"  uv run python -m src.task_classifier.train_agentic_intent"
        )

    artifacts = joblib.load(model_path)

    required_keys = [
        "model",
        "vectorizer",
        "scaler",
        "label_encoder",
        "feature_columns",
    ]

    for key in required_keys:
        if key not in artifacts:
            raise KeyError(
                f"agentic_intent_classifier.joblib is missing required key: {key}"
            )

    model = artifacts["model"]
    vectorizer = artifacts["vectorizer"]
    scaler = artifacts["scaler"]
    label_encoder = artifacts["label_encoder"]
    feature_columns = artifacts["feature_columns"]

    print(f"\nLoaded agentic intent classifier artifacts from: {model_path}")

    return model, vectorizer, scaler, label_encoder, feature_columns


# ------------------------------------------------------------
# Main test loop
# ------------------------------------------------------------

def main():
    extractor = PromptFeatureExtractor()

    print("\nAgentic Intent Classifier")
    print("-------------------------")
    print("Type 'train' to train and save a new model.")
    print("Type 'load' to load the existing saved model.")
    mode = input("\nMode: ").strip().lower()

    if mode == "train":
        df = pd.read_csv(INPUT_CSV)

        (
            model,
            vectorizer,
            scaler,
            label_encoder,
            feature_columns,
        ) = train_agentic_intent_classifier(df, extractor)

        save_classifier_artifacts(
            model=model,
            vectorizer=vectorizer,
            scaler=scaler,
            label_encoder=label_encoder,
            feature_columns=feature_columns,
        )

    elif mode == "load":
        (
            model,
            vectorizer,
            scaler,
            label_encoder,
            feature_columns,
        ) = load_classifier_artifacts()

        print(f"\nLabel classes: {list(label_encoder.classes_)}")
        print(f"Numeric feature count: {len(feature_columns)}")

    else:
        print("Invalid mode. Please choose 'train' or 'load'.")
        return


if __name__ == "__main__":
    main()
