# Plan 07 — ROUTER-04 — routing_decision_eval.csv schema guard. The canary CSV
# MUST have columns:
#   prompt, expected_backend, expected_model_or_agent_substring,
#   is_fallback_expected, edge_case_category, source, license
# expected_backend ∈ {openrouter, claude_code, computer_use, fallback}.
# Edge-case categories include haiku-vs-code, explain-vs-build,
# informational-URL, low-confidence-trap (D-15 — 8 slots minimum).
#
# Tests to be implemented in Plan 07:
#   - test_canary_csv_has_required_columns()
#   - test_expected_backend_values_are_in_allowed_set()
#   - test_edge_case_categories_each_have_at_least_one_row()
#   - test_total_row_count_within_30_to_50_envelope()

import pytest


def test_canary_csv_has_required_columns_placeholder():
    pytest.skip("Wave 4 — implemented in Plan 07 (ROUTER-04)")


def test_expected_backend_values_are_in_allowed_set_placeholder():
    pytest.skip("Wave 4 — implemented in Plan 07 (ROUTER-04)")


def test_edge_case_categories_each_have_at_least_one_row_placeholder():
    pytest.skip("Wave 4 — implemented in Plan 07 (D-15)")


def test_total_row_count_within_30_to_50_envelope_placeholder():
    pytest.skip("Wave 4 — implemented in Plan 07 (ROUTER-04)")
