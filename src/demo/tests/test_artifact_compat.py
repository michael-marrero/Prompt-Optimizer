# Plan 08 — Pitfall 4 — load_joblib_artifacts() in src/demo/demo_router.py is
# the canonical artifact-dict validator. It enforces required_keys =
#   {model, vectorizer, scaler, label_encoder, feature_columns}.
# After the Plan 05 calibration retrain, only the "model" field is replaced
# (with the CalibratedClassifierCV wrapper). All four other keys MUST be
# preserved verbatim. This regression guard exists so a future refactor of
# the artifact dict shape cannot break the demo silently.
#
# Tests to be implemented in Plan 08:
#   - test_existing_task_type_classifier_passes_validator()
#   - test_existing_model_router_passes_validator()
#   - test_new_agentic_intent_classifier_passes_validator()
#   - test_calibrated_model_field_is_calibrated_classifier_cv()

import pytest


def test_existing_task_type_classifier_passes_validator_placeholder():
    pytest.skip("Wave 4 — implemented in Plan 08 (Pitfall 4)")


def test_existing_model_router_passes_validator_placeholder():
    pytest.skip("Wave 4 — implemented in Plan 08 (Pitfall 4)")


def test_new_agentic_intent_classifier_passes_validator_placeholder():
    pytest.skip("Wave 4 — implemented in Plan 08 (Pitfall 4)")


def test_calibrated_model_field_is_calibrated_classifier_cv_placeholder():
    pytest.skip("Wave 4 — implemented in Plan 08 (Plan 05 hand-off)")
