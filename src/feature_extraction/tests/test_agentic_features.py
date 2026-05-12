# Plan 02 — ROUTER-01 prep — PromptFeatureExtractor gains 5 new agentic-intent
# features (imperative_verb_count, has_url, has_file_path, has_code_fence,
# has_action_keyword) per CONTEXT D-08.
#
# Implementation reference: 01-RESEARCH.md §Pattern 3 lines 461-501.
# Security: input bounded to 50_000 chars before regex (RESEARCH §Security line 1231).

import os
import sys
import time

import pytest

# The extractor lives at src/feature_extraction/Feature_extractor.py — but the
# legacy CamelCase filename is not importable as `src.feature_extraction.Feature_extractor`
# without adding it to sys.path (CLAUDE.md "Architectural Constraints — sys.path injection
# of src/feature_extraction"). The existing call sites do this; we replicate.
_FEATURE_EXTRACTION_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
if _FEATURE_EXTRACTION_DIR not in sys.path:
    sys.path.insert(0, _FEATURE_EXTRACTION_DIR)

from Feature_extractor import PromptFeatureExtractor  # noqa: E402


# Module-level fixture: instantiating the extractor does NOT trigger an NLTK
# download (the lazy guard fires only inside _basic_text_features / _agentic_features
# on first extract() call). Safe to construct at module scope.
EXTRACTOR = PromptFeatureExtractor()


# The 5 new agentic-intent feature keys (locked per D-08).
AGENTIC_KEYS = {
    "imperative_verb_count",
    "has_url",
    "has_file_path",
    "has_code_fence",
    "has_action_keyword",
}


def test_extract_returns_five_new_agentic_keys():
    """Test 1+6: All 5 new keys are always present, even on the simplest input."""
    result = EXTRACTOR.extract("hello")
    missing = AGENTIC_KEYS - set(result)
    assert not missing, f"Missing agentic keys: {missing}"
    # On 'hello' all values are falsy/zero
    assert result["imperative_verb_count"] == 0
    assert result["has_url"] == 0
    assert result["has_file_path"] == 0
    assert result["has_code_fence"] == 0
    assert result["has_action_keyword"] == 0


def test_imperative_verb_first_word_counts():
    """Test 1: 'write a Python function for fizzbuzz' has imperative 'write' as first word."""
    result = EXTRACTOR.extract("write a Python function for fizzbuzz")
    assert result["imperative_verb_count"] >= 1


def test_explain_is_not_imperative():
    """Test 2: 'explain' is NOT in the D-08-locked imperative-verb set."""
    result = EXTRACTOR.extract("explain how OAuth works")
    assert result["imperative_verb_count"] == 0


def test_has_url_detects_http_and_https():
    """Test 3 (partial): has_url fires on http and https URLs."""
    result_http = EXTRACTOR.extract("open http://example.com and click subscribe")
    result_https = EXTRACTOR.extract("open https://example.com and click subscribe")
    assert result_http["has_url"] == 1
    assert result_https["has_url"] == 1
    assert result_https["has_action_keyword"] == 1
    assert result_https["imperative_verb_count"] >= 1


def test_has_file_path_detects_unix_path():
    """Test 4: has_file_path fires on a Unix-style absolute path."""
    result = EXTRACTOR.extract("see /usr/local/bin/foo for details")
    assert result["has_file_path"] == 1


def test_has_code_fence_detects_triple_backtick_blocks():
    """Test 5: has_code_fence fires on triple-backtick fences."""
    result = EXTRACTOR.extract("```python\nprint(1)\n```")
    assert result["has_code_fence"] == 1


def test_extract_handles_empty_and_none():
    """Test 7: extract('') and extract(None) both return all 5 new keys, no exception (V7)."""
    for prompt in ("", None):
        result = EXTRACTOR.extract(prompt)
        missing = AGENTIC_KEYS - set(result)
        assert not missing, f"Missing keys for input {prompt!r}: {missing}"
        assert result["imperative_verb_count"] == 0
        assert result["has_url"] == 0
        assert result["has_file_path"] == 0
        assert result["has_code_fence"] == 0
        assert result["has_action_keyword"] == 0


def test_long_input_is_bounded_for_redos_safety():
    """Test 8: 100k-char input completes in under 1 second (ReDoS mitigation via 50k cap)."""
    big = "a" * 100_000
    start = time.perf_counter()
    result = EXTRACTOR.extract(big)
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"extract on 100k chars took {elapsed:.3f}s (expected <1s)"
    # All 5 keys still present
    missing = AGENTIC_KEYS - set(result)
    assert not missing


def test_addition_is_purely_additive_does_not_remove_old_keys():
    """Test 9: regression — extract still returns all previously-existing keys."""
    result = EXTRACTOR.extract("hello world this is a test prompt with some words")
    # Spot-check one representative key from each of the 5 existing helper groups
    existing_keys_sample = {
        "char_count",          # _basic_text_features
        "question_mark_count", # _symbol_features
        "code_keyword_count",  # _keyword_features
        "complexity_score",    # _complexity_features
        "constraint_count",    # _constraint_features
    }
    missing = existing_keys_sample - set(result)
    assert not missing, f"Pre-existing keys disappeared: {missing}"
