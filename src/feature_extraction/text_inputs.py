"""Centralized Stage-2 router text input format.

Lifted from src/model_router/train_model_router.py:125-155 and
src/demo/demo_router.py:110-129 to eliminate duplication. Both call sites
are updated by Plan 01-02 Task 3 to import from here. Future routing-brain
code (Plan 06: src/routing/decide.py) imports from here as the third
consumer, preventing a third copy of the format string.

The canonical format is:

    "<origin_query> task_type_<question_type> keyword_type_<keyword_question_type>"

This format is load-bearing: the existing model_router.joblib vectorizer's
token vocabulary includes the `task_type_<X>` and `keyword_type_<X>` tokens
produced by training-time concatenation. Changing the format invalidates
the vectorizer.
"""

import pandas as pd


def build_router_text_input_series(df: pd.DataFrame) -> pd.Series:
    """DataFrame form. Used during training.

    Combine original prompt text with Stage 1 labels so the router learns from:
    - raw query wording
    - classifier-generated question type
    - old keyword question type, if available

    Missing question_type / keyword_question_type columns fall back to the
    literal string "unknown". NaN in origin_query is replaced with "".
    """
    origin_query = df["origin_query"].fillna("").astype(str)

    if "question_type" in df.columns:
        question_type = df["question_type"].fillna("unknown").astype(str)
    else:
        question_type = pd.Series(["unknown"] * len(df), index=df.index)

    if "keyword_question_type" in df.columns:
        keyword_question_type = df["keyword_question_type"].fillna("unknown").astype(str)
    else:
        keyword_question_type = pd.Series(["unknown"] * len(df), index=df.index)

    return (
        origin_query
        + " task_type_"
        + question_type
        + " keyword_type_"
        + keyword_question_type
    )


def build_router_text_input_single(
    prompt: str,
    question_type: str,
    keyword_question_type: str = "unknown",
) -> pd.Series:
    """Single-prompt form. Used during inference.

    Wraps a single concatenated string in a length-1 pd.Series so the
    existing vectorizer.transform(...) call site can consume it without
    a shape change.
    """
    combined_text = (
        str(prompt)
        + " task_type_"
        + str(question_type)
        + " keyword_type_"
        + str(keyword_question_type)
    )
    return pd.Series([combined_text])
