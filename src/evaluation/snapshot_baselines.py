"""
Snapshot pre-calibration baseline metrics for the task-type classifier and model router.

Loads the uncalibrated joblib artifacts backed up to ``models/uncalibrated/`` and runs
them against the canonical 0.2 stratified test split (random_state=42) on the same
training CSVs they were originally trained on. Writes the captured metrics to
``evaluation/baselines.json`` so Plan 08's regression-guard test (ROUTER-07) can read
them as a known-good "before" snapshot.

Pre-calibration metrics captured per classifier:
- accuracy
- macro_f1
- weighted_f1
- ece (Expected Calibration Error, 10 uniform bins, on max-class probability)
- n_test (held-out sample count)
- classes (sorted label list, for traceability)

Run from the repo root:

    uv run python -m src.evaluation.snapshot_baselines

The script is a one-time pipeline tool — Plan 08 reads its output, never regenerates it.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, hstack
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split

# ------------------------------------------------------------
# Path setup
# ------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_PROCESSED_DIR = PROJECT_ROOT / "data_processed"
MODELS_DIR = PROJECT_ROOT / "models"
UNCALIBRATED_DIR = MODELS_DIR / "uncalibrated"
EVALUATION_DIR = PROJECT_ROOT / "evaluation"
SRC_FEATURE_EXTRACTION_DIR = PROJECT_ROOT / "src" / "feature_extraction"

EVALUATION_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_OUTPUT = EVALUATION_DIR / "baselines.json"
TASK_TYPE_BACKUP = UNCALIBRATED_DIR / "task_type_classifier.joblib"
MODEL_ROUTER_BACKUP = UNCALIBRATED_DIR / "model_router.joblib"
TASK_TYPE_CSV = DATA_PROCESSED_DIR / "classifier_training_with_types.csv"
MODEL_ROUTER_CSV = DATA_PROCESSED_DIR / "router_training_dataset_top_models.csv"

# WR-08 fix: sidecar metadata written by scripts/inject_unknown_class_rows.py
# Read here to record provenance ("includes_unknown_class": True/False)
# in baselines.json so an unexpected ordering of the pipeline (e.g., the
# operator ran inject before snapshot) is visible at snapshot time
# rather than silently changing the baseline.
TASK_TYPE_CSV_META = DATA_PROCESSED_DIR / "classifier_training_with_types.meta.json"

# Set up sys.path so we can load the centralized text-input helper.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.feature_extraction.text_inputs import build_router_text_input_series  # noqa: E402


# ------------------------------------------------------------
# Logging
# ------------------------------------------------------------

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


# ------------------------------------------------------------
# Provenance sidecar reader (WR-08 fix)
#
# Reads the optional classifier_training_with_types.meta.json written by
# scripts/inject_unknown_class_rows.py. Returns a dict suitable for
# recording in baselines.json. If the sidecar is missing, returns
# {"includes_unknown_class": False, "sidecar_present": False} so the
# absence is captured explicitly rather than assumed.
# ------------------------------------------------------------

def _read_provenance_sidecar(meta_path: Path) -> dict:
    """Read the inject_unknown_class_rows.py sidecar metadata or return
    a stub if absent. Never raises — provenance is best-effort.
    """
    if not meta_path.exists():
        return {
            "sidecar_present": False,
            "includes_unknown_class": False,
            "sidecar_path": str(meta_path),
        }
    try:
        with meta_path.open("r", encoding="utf-8") as fp:
            meta = json.load(fp)
    except (OSError, json.JSONDecodeError) as exc:
        logging.warning(
            "Failed to read provenance sidecar at %s: %s", meta_path, exc
        )
        return {
            "sidecar_present": False,
            "includes_unknown_class": False,
            "sidecar_path": str(meta_path),
            "read_error": str(exc),
        }
    meta["sidecar_present"] = True
    meta["sidecar_path"] = str(meta_path)
    return meta


# ------------------------------------------------------------
# ECE helper (16-line; RESEARCH §"Don't Hand-Roll" — sklearn deliberately
# does not ship this; netcal rejected for Phase 1 dep weight)
# ------------------------------------------------------------

def expected_calibration_error(
    y_true: np.ndarray,
    proba: np.ndarray,
    n_bins: int = 10,
) -> float:
    """
    ECE on max-class probability for a multiclass classifier.

    For each bin, accumulate |accuracy - confidence| weighted by the
    fraction of samples in that bin. Returns 0 for empty inputs.
    """

    if len(y_true) == 0:
        return 0.0

    pred_class = proba.argmax(axis=1)
    confidences = proba.max(axis=1)
    accuracies = (pred_class == y_true).astype(float)

    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = len(y_true)

    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
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
# Per-classifier scoring helpers
# ------------------------------------------------------------

def _score_task_type_classifier(artifact_path: Path, csv_path: Path) -> dict:
    """
    Score the uncalibrated task-type classifier on its held-out 0.2 stratified
    test split (random_state=42), using only the columns the artifact was
    originally trained on (artifact["feature_columns"]).
    """

    logging.info("Loading task-type artifact from %s", artifact_path)
    artifacts = joblib.load(artifact_path)

    model = artifacts["model"]
    vectorizer = artifacts["vectorizer"]
    scaler = artifacts["scaler"]
    label_encoder = artifacts["label_encoder"]
    feature_columns = artifacts["feature_columns"]

    logging.info(
        "Artifact uses %d numeric feature columns; classes=%s",
        len(feature_columns),
        list(label_encoder.classes_),
    )

    logging.info("Loading task-type training CSV from %s", csv_path)
    df = pd.read_csv(csv_path)
    logging.info("Loaded %d rows", len(df))

    # Match the original training pipeline: text + numeric features + LabelEncoder + test split.
    text_data = df["origin_query"].fillna("").astype(str)

    # Trim numeric features to the artifact's saved column list (Plan 02 added 5 new
    # cols that the OLD artifact never saw — silently drop them).
    numeric_features = df[feature_columns].fillna(0)
    labels = df["question_type"].fillna("general").astype(str)

    # Only keep rows whose label is in the artifact's class set (defensive — a regenerated
    # CSV could in principle have a label the old artifact never saw, although in practice
    # the keyword-based weak labeler used here is the same one that produced the original
    # training data).
    known_mask = labels.isin(label_encoder.classes_)
    dropped = (~known_mask).sum()
    if dropped > 0:
        logging.warning("Dropping %d rows with labels outside the artifact's class set", dropped)
    text_data = text_data[known_mask].reset_index(drop=True)
    numeric_features = numeric_features[known_mask].reset_index(drop=True)
    labels = labels[known_mask].reset_index(drop=True)

    y = label_encoder.transform(labels)

    X_text_train, X_text_test, X_num_train, X_num_test, y_train, y_test = train_test_split(
        text_data,
        numeric_features,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )

    # Reuse the saved vectorizer + scaler (transform only — never refit).
    X_test_tfidf = vectorizer.transform(X_text_test)
    X_test_num_scaled = scaler.transform(X_num_test)
    X_test_num_sparse = csr_matrix(X_test_num_scaled)
    X_test_combined = hstack([X_test_tfidf, X_test_num_sparse])

    y_pred = model.predict(X_test_combined)
    proba = model.predict_proba(X_test_combined)

    accuracy = float(accuracy_score(y_test, y_pred))
    macro_f1 = float(f1_score(y_test, y_pred, average="macro", zero_division=0))
    weighted_f1 = float(f1_score(y_test, y_pred, average="weighted", zero_division=0))
    ece = expected_calibration_error(y_test, proba, n_bins=10)

    return {
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "weighted_f1": weighted_f1,
        "ece": ece,
        "n_test": int(len(y_test)),
        "n_features": int(len(feature_columns)),
        "classes": sorted(label_encoder.classes_.tolist()),
    }


def _score_model_router(artifact_path: Path, csv_path: Path) -> dict:
    """
    Score the uncalibrated model router on its held-out 0.2 stratified
    test split (random_state=42), using the artifact's saved feature_columns
    and the canonical Stage-2 text-input format from build_router_text_input_series.
    """

    logging.info("Loading model-router artifact from %s", artifact_path)
    artifacts = joblib.load(artifact_path)

    model = artifacts["model"]
    vectorizer = artifacts["vectorizer"]
    scaler = artifacts["scaler"]
    label_encoder = artifacts["label_encoder"]
    feature_columns = artifacts["feature_columns"]
    target_column = artifacts["target_column"]

    logging.info(
        "Artifact uses %d numeric feature columns; target=%s; %d classes",
        len(feature_columns),
        target_column,
        len(label_encoder.classes_),
    )

    logging.info("Loading model-router training CSV from %s", csv_path)
    df = pd.read_csv(csv_path)
    logging.info("Loaded %d rows", len(df))

    if target_column not in df.columns:
        raise ValueError(
            f"model_router target column '{target_column}' not found in {csv_path}"
        )

    text_data = build_router_text_input_series(df)
    numeric_features = df[feature_columns].fillna(0)
    labels = df[target_column].fillna("unknown").astype(str)

    valid_mask = labels != "unknown"
    text_data = text_data[valid_mask].reset_index(drop=True)
    numeric_features = numeric_features[valid_mask].reset_index(drop=True)
    labels = labels[valid_mask].reset_index(drop=True)

    # Drop rows whose label is outside the artifact's class set (Plan 04's data
    # pipeline could have produced a different top-15 set; defensive).
    known_mask = labels.isin(label_encoder.classes_)
    dropped = (~known_mask).sum()
    if dropped > 0:
        logging.warning("Dropping %d rows with labels outside the artifact's class set", dropped)
    text_data = text_data[known_mask].reset_index(drop=True)
    numeric_features = numeric_features[known_mask].reset_index(drop=True)
    labels = labels[known_mask].reset_index(drop=True)

    y = label_encoder.transform(labels)

    # Stratified split with the same seed used at training time.
    X_text_train, X_text_test, X_num_train, X_num_test, y_train, y_test = train_test_split(
        text_data,
        numeric_features,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )

    X_test_tfidf = vectorizer.transform(X_text_test)
    X_test_num_scaled = scaler.transform(X_num_test)
    X_test_num_sparse = csr_matrix(X_test_num_scaled)
    X_test_combined = hstack([X_test_tfidf, X_test_num_sparse])

    y_pred = model.predict(X_test_combined)
    proba = model.predict_proba(X_test_combined)

    accuracy = float(accuracy_score(y_test, y_pred))
    macro_f1 = float(f1_score(y_test, y_pred, average="macro", zero_division=0))
    weighted_f1 = float(f1_score(y_test, y_pred, average="weighted", zero_division=0))
    ece = expected_calibration_error(y_test, proba, n_bins=10)

    return {
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "weighted_f1": weighted_f1,
        "ece": ece,
        "n_test": int(len(y_test)),
        "n_features": int(len(feature_columns)),
        "target_column": target_column,
        "classes": sorted(label_encoder.classes_.tolist()),
    }


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Path to write the baselines JSON snapshot (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--task-type-artifact",
        type=Path,
        default=TASK_TYPE_BACKUP,
        help=f"Path to the uncalibrated task-type classifier (default: {TASK_TYPE_BACKUP}).",
    )
    parser.add_argument(
        "--model-router-artifact",
        type=Path,
        default=MODEL_ROUTER_BACKUP,
        help=f"Path to the uncalibrated model router (default: {MODEL_ROUTER_BACKUP}).",
    )
    parser.add_argument(
        "--task-type-csv",
        type=Path,
        default=TASK_TYPE_CSV,
        help=f"Path to the task-type training CSV (default: {TASK_TYPE_CSV}).",
    )
    parser.add_argument(
        "--model-router-csv",
        type=Path,
        default=MODEL_ROUTER_CSV,
        help=f"Path to the model-router training CSV (default: {MODEL_ROUTER_CSV}).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=1,
        help="-v info, -vv debug.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _setup_logging(args.verbose)

    # Pre-flight: every input must exist.
    for input_path, label in [
        (args.task_type_artifact, "task-type artifact"),
        (args.model_router_artifact, "model-router artifact"),
        (args.task_type_csv, "task-type CSV"),
        (args.model_router_csv, "model-router CSV"),
    ]:
        if not input_path.exists():
            logging.error("Required %s not found at: %s", label, input_path)
            return 2

    task_type_metrics = _score_task_type_classifier(args.task_type_artifact, args.task_type_csv)
    logging.info("task_type_classifier metrics: %s", task_type_metrics)

    model_router_metrics = _score_model_router(args.model_router_artifact, args.model_router_csv)
    logging.info("model_router metrics: %s", model_router_metrics)

    # WR-08 fix: capture sidecar metadata provenance for the task-type CSV.
    # If the sidecar is missing, record includes_unknown_class=False so
    # the absence is recorded (not assumed). This lets test_no_regression
    # confirm the baseline was captured against the expected input.
    csv_provenance = _read_provenance_sidecar(TASK_TYPE_CSV_META)

    snapshot = {
        "schema_version": 1,
        "snapshot_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "description": (
            "Pre-calibration baseline metrics captured from models/uncalibrated/. "
            "Used by Plan 08's regression-guard test (ROUTER-07). "
            "Each classifier was scored on its canonical 0.2 stratified test split "
            "(random_state=42) using only the feature_columns saved in the artifact. "
            "ECE is computed on max-class probability with 10 uniform bins."
        ),
        "task_type_csv_provenance": csv_provenance,
        "task_type_classifier": task_type_metrics,
        "model_router": model_router_metrics,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as fp:
        json.dump(snapshot, fp, indent=2, sort_keys=False)
        fp.write("\n")

    print(f"Saved pre-calibration baselines to: {args.output}")
    print(f"task_type_classifier: accuracy={task_type_metrics['accuracy']:.4f} "
          f"macro_f1={task_type_metrics['macro_f1']:.4f} "
          f"ece={task_type_metrics['ece']:.4f} "
          f"n_test={task_type_metrics['n_test']}")
    print(f"model_router:         accuracy={model_router_metrics['accuracy']:.4f} "
          f"macro_f1={model_router_metrics['macro_f1']:.4f} "
          f"ece={model_router_metrics['ece']:.4f} "
          f"n_test={model_router_metrics['n_test']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
