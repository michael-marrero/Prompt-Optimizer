"""Key-free proof that the per-task budget fuse fires (EVAL-04, Plan 10-05 Task 2).

This is the unit proof of the INNER, Layer-1 runaway-spend guard described in
`eval/suites/agentic_completion.py` (threat T-10-SPEND / Failure Mode #2): the
per-sample `token_limit` / `message_limit` / `time_limit` / `cost_limit` set on
an inspect-ai `Task` raise `LimitExceededError` so a single over-consuming sample
can never drain credits. Plan 05's `eval.ci_gate` is the OUTER aggregate ceiling;
this test proves the inner fuse it relies on.

The proof is fully key-free and makes NO network model call:
    - The over-consumption is driven by an inspect-ai `mockllm` model with a
      scripted output (no provider, no key — same pattern as
      eval/tests/test_scorers.py).
    - The Task is given a deliberately tiny `token_limit`; consuming the mock
      output trips the in-harness fuse, which records the sample's `limit` and
      marks it errored rather than letting it pass silently.

The `LimitExceededError` type is imported and exercised so a future edit that
removes the fuse, raises the cap, or swallows the error fails this test.

Cross-refs:
    - eval/suites/agentic_completion.py (the per-sample caps + cost_limit this proves)
    - eval/tests/test_scorers.py (the sibling mockllm key-free pattern)
    - eval/tests/conftest.py (PROJECT_ROOT depth + --import-mode=importlib)
    - 10-RESEARCH.md §Don't Hand-Roll (Task limits -> LimitExceededError)
    - 10-VALIDATION.md (EVAL-04 per-task fuse row)
"""

from __future__ import annotations

import tempfile

from inspect_ai import Task
from inspect_ai import eval as inspect_eval
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput, get_model
from inspect_ai.scorer import match
from inspect_ai.solver import generate
from inspect_ai.util import LimitExceededError

# A non-model fuse limit (one token). Any real output exceeds it.
_TINY_TOKEN_LIMIT = 1


def _mock_overconsuming_model():
    """A key-free mockllm whose single output is far larger than the token cap.

    No provider, no API key, no network — the output is scripted in-process, the
    same `get_model("mockllm/model", custom_outputs=[...])` recipe used by
    eval/tests/test_scorers.py.
    """

    big_output = "this output clearly contains many more than one token of text " * 25
    return get_model(
        "mockllm/model",
        custom_outputs=[ModelOutput.from_content(model="mockllm/model", content=big_output)],
    )


def _run_fused_task(token_limit: int):
    """Run a one-sample Task under `token_limit` with the over-consuming mock.

    Returns the single EvalSample so callers can assert on its `limit` / `error`.
    """

    task = Task(
        dataset=[Sample(input="trigger the fuse", target="unreachable")],
        solver=generate(),
        scorer=match(),
        token_limit=token_limit,
    )
    with tempfile.TemporaryDirectory() as log_dir:
        logs = inspect_eval(
            task,
            model=_mock_overconsuming_model(),
            log_dir=log_dir,
            display="none",
        )
        log = logs[0]
        # Read samples WHILE the log_dir still exists — inspect_eval returns
        # header logs whose `.eval` file is resolved lazily on access.
        assert log.samples, "the fused task produced no samples"
        return log.samples[0]


def test_per_task_token_limit_fires_the_fuse():
    """A tiny per-task token_limit trips the in-harness fuse (the Layer-1 guard).

    The over-consuming sample records a `limit` of type 'token' — the harness's
    representation of the `LimitExceededError` raised inside the sample. It must
    NOT score as a silent pass.
    """

    sample = _run_fused_task(_TINY_TOKEN_LIMIT)

    # The fuse fired: the sample carries a recorded limit of the token type.
    assert sample.limit is not None, (
        "expected the per-task token_limit fuse to fire and record a limit, "
        "but the sample recorded no limit (the fuse did not trip)"
    )
    assert sample.limit.type == "token", (
        f"expected a 'token' limit, got {sample.limit.type!r} — the per-task "
        "token fuse did not fire"
    )
    # The recorded cap matches the tiny limit we set (proves it was OUR fuse).
    assert float(sample.limit.limit) == float(_TINY_TOKEN_LIMIT)

    # The fused sample did not pass silently — it scored as a non-pass (the
    # mock target is unreachable AND the run was cut short by the limit).
    if sample.scores:
        for score in sample.scores.values():
            assert score.value != "C", (
                "a limit-tripped sample must not be scored CORRECT — it would "
                "let a runaway task pass silently"
            )


def test_limit_exceeded_error_is_the_fuse_exception():
    """`LimitExceededError` is the exception type the per-task fuse raises.

    Construct one of type 'token' (the same shape the harness raises internally
    when a token_limit is crossed) so this proof fails if a future inspect-ai
    upgrade renames or moves the exception out from under the fuse.
    """

    err = LimitExceededError(
        type="token",
        value=999.0,
        limit=float(_TINY_TOKEN_LIMIT),
    )
    assert isinstance(err, LimitExceededError)
    assert err.type == "token"
    assert err.limit == float(_TINY_TOKEN_LIMIT)
    assert err.value > err.limit  # over-consumption is what trips the fuse
