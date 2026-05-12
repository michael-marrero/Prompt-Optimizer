# Plan 08 — ROUTER-07 — benchmark regression guard. After the calibration
# retrain in Plan 05, evaluate_baselines.py metrics on the original
# LLMRouterBench splits MUST NOT drop more than a configured tolerance from
# the snapshot in evaluation/baselines.json (a one-time committed baseline
# captured before calibration).
#
# Tests to be implemented in Plan 08:
#   - test_task_type_classifier_macro_f1_within_tolerance_of_baseline()
#   - test_model_router_top1_accuracy_within_tolerance_of_baseline()
#   - test_baselines_json_schema_intact()

import pytest


def test_task_type_classifier_macro_f1_within_tolerance_of_baseline_placeholder():
    pytest.skip("Wave 4 — implemented in Plan 08 (ROUTER-07)")


def test_model_router_top1_accuracy_within_tolerance_of_baseline_placeholder():
    pytest.skip("Wave 4 — implemented in Plan 08 (ROUTER-07)")


def test_baselines_json_schema_intact_placeholder():
    pytest.skip("Wave 4 — implemented in Plan 08 (ROUTER-07)")
