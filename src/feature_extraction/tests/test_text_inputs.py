# Plan 01-02 Task 2 — tests for the centralized Stage-2 router text-input helpers
# in src/feature_extraction/text_inputs.py. Lifted from the duplicated code at:
#   - src/model_router/train_model_router.py:125-155 (DataFrame form)
#   - src/demo/demo_router.py:110-129 (single-prompt form)
#
# These tests are the RED step before text_inputs.py exists.

import pandas as pd
import pytest

from src.feature_extraction.text_inputs import (
    build_router_text_input_series,
    build_router_text_input_single,
)


def test_single_prompt_with_all_three_args():
    """Test 1: single-prompt form concatenates with the exact canonical format."""
    result = build_router_text_input_single("write code", "coding", "code")
    assert isinstance(result, pd.Series)
    assert len(result) == 1
    assert result.iloc[0] == "write code task_type_coding keyword_type_code"


def test_single_prompt_default_keyword_question_type_unknown():
    """Test 2: keyword_question_type defaults to 'unknown'."""
    result = build_router_text_input_single("hi", "general")
    assert result.iloc[0] == "hi task_type_general keyword_type_unknown"


def test_series_form_with_full_dataframe():
    """Test 3: DataFrame form produces one row per input with the canonical format."""
    df = pd.DataFrame(
        {
            "origin_query": ["a", "b"],
            "question_type": ["coding", "math"],
            "keyword_question_type": ["code", "math"],
        }
    )
    expected = pd.Series(
        ["a task_type_coding keyword_type_code", "b task_type_math keyword_type_math"]
    )
    result = build_router_text_input_series(df)
    pd.testing.assert_series_equal(result, expected)


def test_series_form_missing_columns_fallback_to_unknown():
    """Test 4: missing question_type / keyword_question_type columns default to 'unknown'."""
    df = pd.DataFrame({"origin_query": ["x"]})
    expected = pd.Series(["x task_type_unknown keyword_type_unknown"])
    result = build_router_text_input_series(df)
    pd.testing.assert_series_equal(result, expected)


def test_series_form_nan_handling():
    """Test 5: NaN in origin_query becomes empty string; NaN in question_type becomes 'unknown'."""
    df = pd.DataFrame(
        {
            "origin_query": [None],
            "question_type": [None],
        }
    )
    result = build_router_text_input_series(df)
    assert result.iloc[0] == " task_type_unknown keyword_type_unknown"
