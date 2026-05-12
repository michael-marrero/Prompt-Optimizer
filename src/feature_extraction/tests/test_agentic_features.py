# Plan 02 — ROUTER-01 prep — PromptFeatureExtractor gains 5 new agentic-intent
# features (imperative_verb_count, has_url, has_file_path, has_code_fence,
# has_action_keyword). All three classifiers must be retrained on the extended
# feature set per RESEARCH §Pattern 3 / Compatibility note Option A.
#
# Tests to be implemented in Plan 02:
#   - test_extract_returns_five_new_agentic_keys()
#   - test_has_url_detects_http_and_https()
#   - test_has_code_fence_detects_triple_backtick_blocks()
#   - test_imperative_verb_count_from_first_word_of_each_sentence()

import pytest


def test_extract_returns_five_new_agentic_keys_placeholder():
    pytest.skip("Wave 1 — implemented in Plan 02 (ROUTER-01 prep)")


def test_has_url_detects_http_and_https_placeholder():
    pytest.skip("Wave 1 — implemented in Plan 02 (ROUTER-01 prep)")


def test_has_code_fence_detects_triple_backtick_blocks_placeholder():
    pytest.skip("Wave 1 — implemented in Plan 02 (ROUTER-01 prep)")


def test_imperative_verb_count_from_first_word_of_each_sentence_placeholder():
    pytest.skip("Wave 1 — implemented in Plan 02 (ROUTER-01 prep)")
