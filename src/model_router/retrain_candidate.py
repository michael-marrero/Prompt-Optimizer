"""
STEP 3.2 - Retrain a candidate model_router into a STAGING dir (never live models/).

Reads Story 3.1's `data_processed/retraining_dataset.csv`, keeps only `up`-rated
rows, and retrains the model_router with `original_model` (the route the brain
WANTED — Epic 1) as the target. Writes a self-contained, calibrated candidate
bundle to `models/staging/model_router.joblib` for Story 3.3 to gate. The live
`models/*.joblib` are never touched.

Only the model_router is retrainable from feedback: task_type/agentic heads need
labels (`question_type`, binary agentic) that the feedback signal doesn't carry.

Feature/serve-parity note (Story 3.2 D4): the production router text input carries
Stage-1 `task_type`/`keyword_type` tokens; the 3.1 dataset omits them, so
`build_router_text_input_series` emits the neutral `task_type_unknown` token. This
is an accepted dry-run gap (Story 3.3 promotes nothing at 0 feedback); the close-out
(projecting the captured `decision.signals.task_type`) is tracked in deferred-work.md.

Mirrors the train_model_router pipeline (FeatureUnion word+char TF-IDF ⊕ scaled
numerics ⊕ LogisticRegression ⊕ CalibratedClassifierCV(FrozenEstimator, sigmoid))
but without its plot/print side-effects, and adds ECE reporting.

Run from the repo root:

    python -m src.model_router.retrain_candidate \
        --dataset data_processed/retraining_dataset.csv \
        --staging-dir models/staging
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, hstack
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import FeatureUnion
from sklearn.preprocessing import LabelEncoder, StandardScaler

from src.feature_extraction.text_inputs import build_router_text_input_series
from src.model_router.train_model_router import get_numeric_feature_columns, save_router_artifacts

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = PROJECT_ROOT / "data_processed" / "retraining_dataset.csv"
DEFAULT_STAGING_DIR = PROJECT_ROOT / "models" / "staging"
LIVE_MODELS_DIR = PROJECT_ROOT / "models"

TARGET_COLUMN = "original_model"  # the route the brain wanted (Epic-1 breadcrumb)
POSITIVE_LABEL = "up"             # only up-rated turns are positive training rows (D3)
MIN_PER_CLASS = 2                 # stratify floor, mirrors train_model_router.py:568
TOP_N = 15                        # top-15+OTHER label space (AC #4, build_top_model_datatset.py)
OTHER_LABEL = "OTHER"
REQUIRED_COLUMNS = ("label", TARGET_COLUMN, "origin_query")

logger = logging.getLogger(__name__)


class InsufficientData(Exception):
    """Raised when the up-rated rows can't support a stratified retrain."""


def _expected_calibration_error(y_true: np.ndarray, proba: np.ndarray, n_bins: int = 10) -> float:
    """ECE on max-class probability (10 uniform bins). Lifted from
    src/evaluation/snapshot_baselines.py to avoid a cross-package import (AD-8)."""
    pred = proba.argmax(axis=1)
    conf = proba.max(axis=1)
    acc = (pred == y_true).astype(float)
    n = len(y_true)
    if n == 0:
        return 0.0
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (conf > lo) & (conf <= hi)
        if mask.sum() == 0:
            continue
        ece += (mask.sum() / n) * abs(acc[mask].mean() - conf[mask].mean())
    return float(ece)


def build_training_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only `up`-rated rows with a non-empty target. Logs the drop counts."""
    total = len(df)
    up = df[df["label"].astype(str) == POSITIVE_LABEL].copy()
    up[TARGET_COLUMN] = up[TARGET_COLUMN].fillna("").astype(str)
    up = up[up[TARGET_COLUMN] != ""]
    logger.info("Kept %d/%d rows (%s); dropped %d non-up / empty-target rows.",
                len(up), total, POSITIVE_LABEL, total - len(up))
    return up


def _collapse_to_top_models(frame: pd.DataFrame) -> pd.DataFrame:
    """Map the target to the top-TOP_N models + OTHER (mirrors build_top_model_datatset.py:82-92)
    so the candidate's label space matches production: bounded cardinality, and tail models fold
    into the OTHER fallback route instead of being dropped."""
    counts = frame[TARGET_COLUMN].value_counts()
    top_models = set(counts.head(TOP_N).index)
    frame = frame.copy()
    frame[TARGET_COLUMN] = frame[TARGET_COLUMN].where(frame[TARGET_COLUMN].isin(top_models), OTHER_LABEL)
    return frame


def _prune_rare_classes(frame: pd.DataFrame) -> pd.DataFrame:
    counts = frame[TARGET_COLUMN].value_counts()
    keep = counts[counts >= MIN_PER_CLASS].index
    return frame[frame[TARGET_COLUMN].isin(keep)].copy()


def retrain_candidate(df: pd.DataFrame) -> tuple[dict, dict]:
    """Fit + calibrate a candidate model_router. Returns (artifacts, metrics).

    Raises InsufficientData if there aren't >=2 model classes with >=MIN_PER_CLASS
    up-rated rows (a valid dry-run outcome — the caller reports and stages nothing).
    """
    frame = _prune_rare_classes(_collapse_to_top_models(build_training_frame(df)))
    if frame[TARGET_COLUMN].nunique() < 2 or len(frame) < 2 * MIN_PER_CLASS:
        raise InsufficientData(
            f"need >=2 model classes with >={MIN_PER_CLASS} up-rated rows; "
            f"got {frame[TARGET_COLUMN].nunique()} class(es), {len(frame)} rows"
        )

    feature_columns = get_numeric_feature_columns(frame, TARGET_COLUMN)
    if not feature_columns:
        raise InsufficientData("no numeric feature columns present in dataset")
    text_data = build_router_text_input_series(frame)
    numeric_features = frame[feature_columns].fillna(0)
    label_encoder = LabelEncoder()
    y = label_encoder.fit_transform(frame[TARGET_COLUMN].astype(str))

    try:
        X_text_tr, X_text_te, X_num_tr, X_num_te, y_tr, y_te = train_test_split(
            text_data, numeric_features, y, test_size=0.2, random_state=42, stratify=y,
        )
    except ValueError as exc:  # too few per class for a stratified split
        raise InsufficientData(f"stratified split failed on thin data: {exc}") from exc

    vectorizer = FeatureUnion([
        ("word_tfidf", TfidfVectorizer(lowercase=True, ngram_range=(1, 2), min_df=1, max_df=0.95, max_features=10000)),
        ("char_tfidf", TfidfVectorizer(lowercase=True, analyzer="char_wb", ngram_range=(3, 5), min_df=1, max_features=8000)),
    ])
    try:  # thin/degenerate text can prune the whole vocabulary under max_df
        X_text_tr_v = vectorizer.fit_transform(X_text_tr)
        X_text_te_v = vectorizer.transform(X_text_te)
    except ValueError as exc:
        raise InsufficientData(f"TF-IDF vocabulary empty on thin/degenerate text: {exc}") from exc

    scaler = StandardScaler()
    X_num_tr_s = csr_matrix(scaler.fit_transform(X_num_tr))
    X_num_te_s = csr_matrix(scaler.transform(X_num_te))

    X_tr = hstack([X_text_tr_v, X_num_tr_s])
    X_te = hstack([X_text_te_v, X_num_te_s])

    base = LogisticRegression(max_iter=1500, class_weight="balanced", solver="saga", C=2.0, n_jobs=-1)

    # Calibration: fit base on a disjoint slice, freeze, sigmoid-calibrate on the rest.
    try:
        X_fit, X_calib, y_fit, y_calib = train_test_split(
            X_tr, y_tr, test_size=0.25, random_state=42, stratify=y_tr,
        )
    except ValueError as exc:
        raise InsufficientData(f"calibration split failed on thin data: {exc}") from exc
    base.fit(X_fit, y_fit)
    model = CalibratedClassifierCV(FrozenEstimator(base), method="sigmoid")
    model.fit(X_calib, y_calib)

    y_pred = model.predict(X_te)
    classes = label_encoder.classes_
    train_support = {str(classes[i]): int((y_tr == i).sum()) for i in range(len(classes))}
    metrics = {
        "n_train": int(len(y_tr)),
        "n_test": int(len(y_te)),
        "n_classes": int(len(classes)),
        "accuracy": float(accuracy_score(y_te, y_pred)),
        "macro_f1": float(f1_score(y_te, y_pred, average="macro")),
        "weighted_f1": float(f1_score(y_te, y_pred, average="weighted")),
        "ece": _expected_calibration_error(y_te, model.predict_proba(X_te)),
        "train_support": train_support,
    }
    artifacts = {
        "model": model,
        "vectorizer": vectorizer,
        "scaler": scaler,
        "label_encoder": label_encoder,
        "feature_columns": feature_columns,
    }
    return artifacts, metrics


def _setup_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity >= 2:
        level = logging.DEBUG
    elif verbosity >= 1:
        level = logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", "-i", type=Path, default=DEFAULT_DATASET,
                        help=f"Story 3.1 retraining CSV (default: {DEFAULT_DATASET}).")
    parser.add_argument("--staging-dir", "-s", type=Path, default=DEFAULT_STAGING_DIR,
                        help=f"Staging dir for the candidate (default: {DEFAULT_STAGING_DIR}).")
    parser.add_argument("-v", "--verbose", action="count", default=1, help="-v info, -vv debug.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _setup_logging(args.verbose)

    if not args.dataset.exists():
        logger.error("Retraining dataset not found: %s", args.dataset)
        return 2

    # Guard: never write into the live models/ root — staging only. samefile() catches
    # case-insensitive (macOS) and symlink aliases that a resolved-path == would miss.
    same_live = args.staging_dir.resolve() == LIVE_MODELS_DIR.resolve() or (
        args.staging_dir.exists() and os.path.samefile(args.staging_dir, LIVE_MODELS_DIR)
    )
    if same_live:
        logger.error("Refusing to write candidates into the live models/ dir: %s", args.staging_dir)
        return 2

    df = pd.read_csv(args.dataset)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        logger.error("Dataset %s is missing required column(s): %s", args.dataset, ", ".join(missing))
        return 2
    try:
        artifacts, metrics = retrain_candidate(df)
    except InsufficientData as exc:
        logger.warning("Insufficient data to retrain — candidate NOT produced: %s", exc)
        print(f"Insufficient data — no candidate staged ({exc}).")
        return 0

    args.staging_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.staging_dir / "model_router.joblib"
    save_router_artifacts(
        model=artifacts["model"],
        vectorizer=artifacts["vectorizer"],
        scaler=artifacts["scaler"],
        label_encoder=artifacts["label_encoder"],
        feature_columns=artifacts["feature_columns"],
        target_column=TARGET_COLUMN,
        output_path=str(out_path),
    )

    print(f"Staged candidate model_router to: {out_path}")
    print(
        f"  rows train/test={metrics['n_train']}/{metrics['n_test']} classes={metrics['n_classes']} "
        f"accuracy={metrics['accuracy']:.4f} macroF1={metrics['macro_f1']:.4f} "
        f"weightedF1={metrics['weighted_f1']:.4f} ECE={metrics['ece']:.4f}"
    )
    support = ", ".join(f"{slug}={n}" for slug, n in sorted(metrics["train_support"].items()))
    print(f"  per-class train support: {support}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
