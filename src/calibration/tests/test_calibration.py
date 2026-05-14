"""
Calibration regression tests (ROUTER-02 + ROUTER-03; Plan 01-05).

The full test surface (4 production tests + 1 schema test) replaces the Plan 01
RED stubs that called pytest.skip() at module load. Each test is robust to
running before its underlying artifact / data file exists — in that case
it skips cleanly from inside the test function body rather than crashing
collection (preserves the Plan 01-01 "named placeholder visible to collect-only"
contract per Plan 02 / Plan 04 precedent).

Tests:
- test_task_type_artifact_is_calibrated:        ROUTER-03 task-type joblib shape
- test_task_type_has_unknown_class:             ROUTER-02 OOD sentinel class
- test_model_router_artifact_is_calibrated:     ROUTER-03 model-router joblib shape
- test_calibrated_predict_proba_sums_to_one:    Sanity check on predict_proba
- test_baselines_json_present:                  Schema check on Plan 08's input
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import joblib
import pandas as pd
import pytest
from scipy.sparse import csr_matrix, hstack
from sklearn.calibration import CalibratedClassifierCV


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = PROJECT_ROOT / "models"
EVALUATION_DIR = PROJECT_ROOT / "evaluation"
SRC_FEATURE_EXTRACTION = PROJECT_ROOT / "src" / "feature_extraction"

TASK_TYPE_PATH = MODELS_DIR / "task_type_classifier.joblib"
MODEL_ROUTER_PATH = MODELS_DIR / "model_router.joblib"
BASELINES_JSON_PATH = EVALUATION_DIR / "baselines.json"


def _load_task_type_or_skip() -> dict:
    if not TASK_TYPE_PATH.exists():
        pytest.skip(
            f"task_type_classifier.joblib not found at {TASK_TYPE_PATH}. "
            "Run Plan 01-05 Task 4 first: "
            "`echo train | uv run python -m src.task_classifier.train_task_classifier_robust`."
        )
    return joblib.load(TASK_TYPE_PATH)


def _load_model_router_or_skip() -> dict:
    if not MODEL_ROUTER_PATH.exists():
        pytest.skip(
            f"model_router.joblib not found at {MODEL_ROUTER_PATH}. "
            "Run Plan 01-05 Task 5 first: "
            "`echo train | uv run python -m src.model_router.train_model_router`."
        )
    return joblib.load(MODEL_ROUTER_PATH)


def test_task_type_artifact_is_calibrated() -> None:
    """ROUTER-03: task-type classifier's model field is a CalibratedClassifierCV
    and the artifact preserves the canonical 5-key dict shape (Pitfall 4)."""

    artifacts = _load_task_type_or_skip()

    assert isinstance(artifacts["model"], CalibratedClassifierCV), (
        f"Expected CalibratedClassifierCV, got {type(artifacts['model']).__name__}. "
        "Plan 05 Task 4's calibration step did not run."
    )

    required = {"model", "vectorizer", "scaler", "label_encoder", "feature_columns"}
    missing = required - set(artifacts.keys())
    assert not missing, (
        f"task_type_classifier.joblib missing canonical keys: {sorted(missing)} "
        "(Pitfall 4: load_joblib_artifacts validates these exact 5 keys)."
    )


def test_task_type_has_unknown_class() -> None:
    """ROUTER-02 / D-09: task-type classifier's LabelEncoder must include the
    literal 'unknown' OOD sentinel class."""

    artifacts = _load_task_type_or_skip()

    classes = list(artifacts["label_encoder"].classes_)
    assert "unknown" in classes, (
        f"'unknown' class missing from label_encoder.classes_: {sorted(classes)}. "
        "Plan 05 Task 3 must add the OOD sentinel via build_question_type.py "
        "and synthetic OOD prompt injection."
    )


def test_model_router_artifact_is_calibrated() -> None:
    """ROUTER-03: model router's model field is a CalibratedClassifierCV and
    the artifact preserves the canonical 6-key dict shape with target_column
    (Pitfall 4)."""

    artifacts = _load_model_router_or_skip()

    assert isinstance(artifacts["model"], CalibratedClassifierCV), (
        f"Expected CalibratedClassifierCV, got {type(artifacts['model']).__name__}. "
        "Plan 05 Task 5's calibration step did not run."
    )

    required = {
        "model",
        "vectorizer",
        "scaler",
        "label_encoder",
        "feature_columns",
        "target_column",
    }
    missing = required - set(artifacts.keys())
    assert not missing, (
        f"model_router.joblib missing canonical keys: {sorted(missing)} "
        "(Pitfall 4: the router has 6 keys including target_column)."
    )


def _build_synthetic_input(artifacts: dict, prompt: str, use_router_text: bool = False) -> object:
    """
    Build a minimal synthetic input compatible with the artifact's saved
    vectorizer + scaler + hstack stack. Used by
    test_calibrated_predict_proba_sums_to_one.
    """

    # Lazy import so the module collects cleanly even if the extractor isn't
    # importable yet (Plan 02 added 5 keys; pre-Plan-02 environments would
    # still load this test module).
    if str(SRC_FEATURE_EXTRACTION) not in sys.path:
        sys.path.insert(0, str(SRC_FEATURE_EXTRACTION))
    from Feature_extractor import PromptFeatureExtractor

    extractor = PromptFeatureExtractor()

    if use_router_text:
        # Router uses the Stage-2 input format.
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.feature_extraction.text_inputs import build_router_text_input_single
        text_series = build_router_text_input_single(
            prompt=prompt,
            question_type="unknown",
            keyword_question_type="unknown",
        )
    else:
        text_series = pd.Series([prompt])

    # Numeric features — trim to the artifact's saved feature_columns.
    features = extractor.extract(prompt)
    row_df = pd.DataFrame([features])
    for col in artifacts["feature_columns"]:
        if col not in row_df.columns:
            row_df[col] = 0
    row_df = row_df[artifacts["feature_columns"]].fillna(0)

    text_features = artifacts["vectorizer"].transform(text_series)
    numeric_scaled = artifacts["scaler"].transform(row_df)
    numeric_sparse = csr_matrix(numeric_scaled)
    combined = hstack([text_features, numeric_sparse])
    return combined


def test_calibrated_predict_proba_sums_to_one() -> None:
    """For each calibrated artifact, predict_proba rows must sum to 1.0
    (within 1e-6) — the most basic sanity check on a probabilistic classifier."""

    # Task-type classifier.
    task_artifacts = _load_task_type_or_skip()
    X_task = _build_synthetic_input(task_artifacts, "what is the capital of France?")
    proba_task = task_artifacts["model"].predict_proba(X_task)
    assert proba_task.shape[0] == 1, f"expected 1 row, got {proba_task.shape}"
    row_sum_task = float(proba_task.sum(axis=1)[0])
    assert abs(row_sum_task - 1.0) <= 1e-6, (
        f"task_type_classifier predict_proba row sums to {row_sum_task}, expected 1.0"
    )

    # Model router.
    router_artifacts = _load_model_router_or_skip()
    X_router = _build_synthetic_input(
        router_artifacts,
        "explain the gradient descent algorithm",
        use_router_text=True,
    )
    proba_router = router_artifacts["model"].predict_proba(X_router)
    assert proba_router.shape[0] == 1, f"expected 1 row, got {proba_router.shape}"
    row_sum_router = float(proba_router.sum(axis=1)[0])
    assert abs(row_sum_router - 1.0) <= 1e-6, (
        f"model_router predict_proba row sums to {row_sum_router}, expected 1.0"
    )


def test_baselines_json_present() -> None:
    """ROUTER-07: evaluation/baselines.json must exist with the schema Plan 08's
    regression-guard test reads."""

    if not BASELINES_JSON_PATH.exists():
        pytest.skip(
            f"baselines.json not found at {BASELINES_JSON_PATH}. "
            "Run `uv run python -m src.evaluation.snapshot_baselines` first."
        )

    with BASELINES_JSON_PATH.open("r", encoding="utf-8") as fp:
        snapshot = json.load(fp)

    assert "task_type_classifier" in snapshot, (
        "baselines.json missing 'task_type_classifier' top-level key."
    )
    assert "model_router" in snapshot, "baselines.json missing 'model_router' top-level key."

    required_metric_keys = {"accuracy", "macro_f1", "weighted_f1", "ece", "n_test"}
    for stage in ("task_type_classifier", "model_router"):
        stage_obj = snapshot[stage]
        missing = required_metric_keys - set(stage_obj.keys())
        assert not missing, (
            f"baselines.json['{stage}'] missing metric keys: {sorted(missing)}"
        )

        # Sanity-check value ranges.
        for k in ("accuracy", "macro_f1", "weighted_f1", "ece"):
            v = stage_obj[k]
            assert isinstance(v, (int, float)), (
                f"baselines.json['{stage}']['{k}'] is {type(v).__name__}, expected number"
            )
            assert 0.0 <= float(v) <= 1.0, (
                f"baselines.json['{stage}']['{k}'] = {v}, expected in [0, 1]"
            )

        n_test = stage_obj["n_test"]
        assert isinstance(n_test, int) and n_test > 0, (
            f"baselines.json['{stage}']['n_test'] = {n_test}, expected positive int"
        )

    # Schema version + snapshot_date are present for forward-compat traceability.
    assert "schema_version" in snapshot, "baselines.json missing 'schema_version'"
    assert "snapshot_date" in snapshot, "baselines.json missing 'snapshot_date'"
