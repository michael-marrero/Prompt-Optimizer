# Plan 05 — ROUTER-02 / ROUTER-03 — calibrate task_type_classifier and
# model_router with CalibratedClassifierCV(FrozenEstimator(base)) instead of
# the deprecated cv="prefit" idiom. Original artifacts back up to
# models/uncalibrated/ before overwrite. Add an "unknown" OOD class to the
# task-type label encoder.
#
# Tests to be implemented in Plan 05:
#   - test_calibrated_artifact_loads_via_existing_load_joblib_artifacts()
#   - test_ece_decreases_after_calibration_on_held_out_test_split()
#   - test_no_deprecation_warning_raised_during_calibration()  # Pitfall 1
#   - test_task_type_label_encoder_includes_unknown_class()    # ROUTER-02

import pytest


def test_calibrated_artifact_loads_via_existing_load_joblib_artifacts_placeholder():
    pytest.skip("Wave 2 — implemented in Plan 05 (ROUTER-02 / ROUTER-03)")


def test_ece_decreases_after_calibration_on_held_out_test_split_placeholder():
    pytest.skip("Wave 2 — implemented in Plan 05 (ROUTER-03)")


def test_no_deprecation_warning_raised_during_calibration_placeholder():
    pytest.skip("Wave 2 — implemented in Plan 05 (Pitfall 1)")


def test_task_type_label_encoder_includes_unknown_class_placeholder():
    pytest.skip("Wave 2 — implemented in Plan 05 (ROUTER-02)")
