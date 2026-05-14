"""
Plan 08 — Pitfall 4 regression guard for canonical joblib artifact dict shape.

`load_joblib_artifacts()` in src/demo/demo_router.py is the canonical
artifact-dict validator. It enforces required_keys =
  {model, vectorizer, scaler, label_encoder, feature_columns}.

After the Plan 05 calibration retrain only the "model" field changes
(LogisticRegression -> CalibratedClassifierCV); every other key in the
artifact dict MUST be preserved verbatim. This regression guard exists
so a future refactor of the artifact dict shape cannot break the demo
or downstream consumers silently.

The model_router additionally carries a 6th key, `target_column`
(Pitfall 4 covers the "additional keys are allowed" rule). The
embedding_router uses a different shape entirely (descriptive flags
per RESEARCH lines 28-30) and is intentionally NOT covered here.

Tests (filling the 4 RED stubs scaffolded in Plan 01-01 + 2 added
guards for Pitfall 6 — uncalibrated/ backup presence and the
explicit "no renamed model field" check):

- test_task_type_classifier_loads_with_5_keys
- test_model_router_loads_with_6_keys
- test_agentic_intent_classifier_loads_with_5_keys
- test_tier_router_unchanged
- test_no_renamed_model_field
- test_uncalibrated_backups_exist
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import joblib
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = PROJECT_ROOT / "models"
UNCALIBRATED_DIR = MODELS_DIR / "uncalibrated"

TASK_TYPE_PATH = MODELS_DIR / "task_type_classifier.joblib"
MODEL_ROUTER_PATH = MODELS_DIR / "model_router.joblib"
AGENTIC_INTENT_PATH = MODELS_DIR / "agentic_intent_classifier.joblib"
TIER_ROUTER_PATH = MODELS_DIR / "tier_router.joblib"


# ----------------------------------------------------------------------
# Helper: import load_joblib_artifacts from src.demo.demo_router.
#
# We import lazily inside each test so a fresh checkout that hasn't yet
# run Plans 04/05 still collects this module cleanly. The import itself
# does NOT trigger the REPL because main() is guarded behind
# `if __name__ == "__main__":`.
# ----------------------------------------------------------------------


def _load_validator():
    """Import load_joblib_artifacts from the demo module."""
    # Ensure project root is on sys.path so `src.routing` etc resolve.
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from src.demo.demo_router import load_joblib_artifacts
    return load_joblib_artifacts


# ----------------------------------------------------------------------
# 5-key canonical validator tests (Pitfall 4)
# ----------------------------------------------------------------------


def test_task_type_classifier_loads_with_5_keys() -> None:
    """task_type_classifier.joblib loads via the canonical 5-key validator.

    Also asserts ROUTER-02 (unknown OOD class in label_encoder.classes_)
    and ROUTER-03 (model field is a CalibratedClassifierCV) — the two
    Plan 05 ratchets. If a future refactor breaks the canonical shape,
    this test catches it immediately.
    """
    if not TASK_TYPE_PATH.exists():
        pytest.skip(
            f"task_type_classifier.joblib not found at {TASK_TYPE_PATH}. "
            "Run Plan 01-05 Task 4 first."
        )

    load_joblib_artifacts = _load_validator()
    artifacts = load_joblib_artifacts(str(TASK_TYPE_PATH), "task_type_classifier.joblib")

    required = {"model", "vectorizer", "scaler", "label_encoder", "feature_columns"}
    assert required <= set(artifacts.keys()), (
        f"task_type_classifier.joblib missing keys: {sorted(required - set(artifacts.keys()))}"
    )

    # ROUTER-02 — OOD sentinel class.
    classes = list(artifacts["label_encoder"].classes_)
    assert "unknown" in classes, (
        f"'unknown' class missing from label_encoder.classes_: {sorted(classes)} "
        "(ROUTER-02 ratchet from Plan 05)."
    )

    # ROUTER-03 — calibrated.
    from sklearn.calibration import CalibratedClassifierCV
    assert isinstance(artifacts["model"], CalibratedClassifierCV), (
        f"task_type_classifier model is {type(artifacts['model']).__name__}, "
        "expected CalibratedClassifierCV (ROUTER-03 ratchet from Plan 05)."
    )


def test_model_router_loads_with_6_keys() -> None:
    """model_router.joblib loads via the canonical validator (5-key minimum)
    and additionally carries the 6th `target_column` key from Plan 05.

    Pitfall 4: the validator only requires the 5-key minimum; extra keys
    are permitted but the canonical 5 must be intact verbatim. The
    model_router has always carried target_column (set to
    'best_model_top15') alongside the 5-key minimum.
    """
    if not MODEL_ROUTER_PATH.exists():
        pytest.skip(
            f"model_router.joblib not found at {MODEL_ROUTER_PATH}. "
            "Run Plan 01-05 Task 5 first."
        )

    load_joblib_artifacts = _load_validator()
    artifacts = load_joblib_artifacts(str(MODEL_ROUTER_PATH), "model_router.joblib")

    required = {"model", "vectorizer", "scaler", "label_encoder", "feature_columns", "target_column"}
    assert required <= set(artifacts.keys()), (
        f"model_router.joblib missing keys: {sorted(required - set(artifacts.keys()))}"
    )

    from sklearn.calibration import CalibratedClassifierCV
    assert isinstance(artifacts["model"], CalibratedClassifierCV), (
        f"model_router model is {type(artifacts['model']).__name__}, "
        "expected CalibratedClassifierCV (ROUTER-03 ratchet from Plan 05)."
    )


def test_agentic_intent_classifier_loads_with_5_keys() -> None:
    """agentic_intent_classifier.joblib loads via the canonical 5-key validator.

    Plan 04 produced this artifact as a CalibratedClassifierCV with the
    binary {agentic, conversational} label set. The 5-key shape and the
    binary class set are both load-bearing for decide() in Plan 06.
    """
    if not AGENTIC_INTENT_PATH.exists():
        pytest.skip(
            f"agentic_intent_classifier.joblib not found at {AGENTIC_INTENT_PATH}. "
            "Run Plan 01-04 first."
        )

    load_joblib_artifacts = _load_validator()
    artifacts = load_joblib_artifacts(
        str(AGENTIC_INTENT_PATH),
        "agentic_intent_classifier.joblib",
    )

    required = {"model", "vectorizer", "scaler", "label_encoder", "feature_columns"}
    assert required <= set(artifacts.keys()), (
        f"agentic_intent_classifier.joblib missing keys: "
        f"{sorted(required - set(artifacts.keys()))}"
    )

    classes = sorted(artifacts["label_encoder"].classes_.tolist())
    assert classes == ["agentic", "conversational"], (
        f"Expected binary {{agentic, conversational}} classes, got: {classes}"
    )

    from sklearn.calibration import CalibratedClassifierCV
    assert isinstance(artifacts["model"], CalibratedClassifierCV), (
        f"agentic_intent_classifier model is {type(artifacts['model']).__name__}, "
        "expected CalibratedClassifierCV (Plan 04 calibration)."
    )


def test_tier_router_unchanged() -> None:
    """tier_router.joblib was NOT calibrated in Plan 05 — sanity-check it
    still loads as before through the canonical 5-key validator.

    The tier router is an experimental coarse-grained router from Phase 0
    that the routing brain doesn't use today (Plan 06 doesn't import
    tier_router); Phase 2+ may revisit. This test ensures the artifact
    survives unmodified across the calibration retrain.
    """
    if not TIER_ROUTER_PATH.exists():
        pytest.skip(
            f"tier_router.joblib not found at {TIER_ROUTER_PATH}. "
            "Run src/model_router_tier/train_tier_router.py first."
        )

    load_joblib_artifacts = _load_validator()
    artifacts = load_joblib_artifacts(str(TIER_ROUTER_PATH), "tier_router.joblib")

    required = {"model", "vectorizer", "scaler", "label_encoder", "feature_columns"}
    assert required <= set(artifacts.keys()), (
        f"tier_router.joblib missing keys: {sorted(required - set(artifacts.keys()))}"
    )


# ----------------------------------------------------------------------
# Pitfall 4 explicit guard — no renamed model field
# ----------------------------------------------------------------------


def test_no_renamed_model_field() -> None:
    """Pitfall 4 explicit regression guard.

    A common bad refactor is to rename the `model` key to something
    like `calibrated_model` after calibration. The canonical validator
    only checks for the literal `model` key — if the field is renamed,
    every downstream consumer (the demo REPL, decide(), the regression
    guard tests) silently breaks. This test asserts the field stays
    named `model` AND no `calibrated_model` field is introduced.
    """
    for path in (TASK_TYPE_PATH, MODEL_ROUTER_PATH, AGENTIC_INTENT_PATH):
        if not path.exists():
            pytest.skip(f"{path.name} not found at {path}")

    for path in (TASK_TYPE_PATH, MODEL_ROUTER_PATH, AGENTIC_INTENT_PATH):
        artifacts = joblib.load(path)
        assert "model" in artifacts, (
            f"{path.name} is missing the canonical 'model' field — "
            "Pitfall 4 violation. The calibrated estimator MUST be stored "
            "under the 'model' key, not renamed."
        )
        assert "calibrated_model" not in artifacts, (
            f"{path.name} introduced a 'calibrated_model' field. "
            "Pitfall 4 violation — calibration MUST overwrite the existing "
            "'model' field, not add a new key."
        )


# ----------------------------------------------------------------------
# Pitfall 6 guard — uncalibrated backups must remain on disk
# ----------------------------------------------------------------------


def test_uncalibrated_backups_exist() -> None:
    """Pitfall 6: the `models/uncalibrated/` backup directory established
    in Plan 05 Task 1 must remain present. If the calibrated artifacts
    are ever discovered to be broken, `cp models/uncalibrated/*.joblib
    models/` is the documented reversal command — but only if the
    backups still exist.
    """
    backup_task_type = UNCALIBRATED_DIR / "task_type_classifier.joblib"
    backup_model_router = UNCALIBRATED_DIR / "model_router.joblib"

    assert UNCALIBRATED_DIR.exists(), (
        f"models/uncalibrated/ directory missing at {UNCALIBRATED_DIR}. "
        "Pitfall 6 violation — Plan 05 Task 1's backup directory must persist."
    )
    assert backup_task_type.exists(), (
        f"Pre-calibration backup missing at {backup_task_type}. "
        "Re-create via Plan 05 Task 1 before deleting models/task_type_classifier.joblib."
    )
    assert backup_model_router.exists(), (
        f"Pre-calibration backup missing at {backup_model_router}. "
        "Re-create via Plan 05 Task 1 before deleting models/model_router.joblib."
    )
