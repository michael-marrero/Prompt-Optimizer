# Plan 07 — ROUTER-04 / Success Criterion #3 — evaluate_routing.py runs the
# canary CSV through decide() and emits backend_accuracy.csv, per_backend_pr.csv,
# confusion_matrix.csv + .png, ece_per_stage.csv, low_confidence_rate.txt, and
# one reliability_diagram_<stage>.png per calibrated head.
#
# Tests to be implemented in Plan 07:
#   - test_evaluate_routing_writes_all_metric_files()
#   - test_backend_accuracy_above_threshold()           # success criterion #3
#   - test_ece_per_stage_below_threshold()              # Pattern 1 outcome
#   - test_check_flag_exits_nonzero_when_below_threshold()

import pytest


def test_evaluate_routing_writes_all_metric_files_placeholder():
    pytest.skip("Wave 4 — implemented in Plan 07 (ROUTER-04)")


def test_backend_accuracy_above_threshold_placeholder():
    pytest.skip("Wave 4 — implemented in Plan 07 (Success Criterion #3)")


def test_ece_per_stage_below_threshold_placeholder():
    pytest.skip("Wave 4 — implemented in Plan 07 (Success Criterion #3)")


def test_check_flag_exits_nonzero_when_below_threshold_placeholder():
    pytest.skip("Wave 4 — implemented in Plan 07 (ROUTER-04 CI gate)")
