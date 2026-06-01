"""Key-free unit tests for the hybrid artifact_or_judge scorer (Plan 10-04, Task 2).

Covers, with NO network / NO real model / NO key:
    - check_artifact for all three deterministic types (file-present, dom-or-text,
      terminal-state), True and False branches.
    - artifact_or_judge routing: deterministic check runs (judge NEVER invoked)
      when an artifact handle exists; the judge runs only when none does.
    - judge: a valid JudgeVerdict scores; a malformed verdict triggers the
      3-attempt validate-or-retry loop; after 3 failures the judge returns
      INCORRECT with a "judge schema failure" explanation and flags the sample
      (it never silently passes).

The judge is driven by an inspect-ai `mockllm` Model with scripted outputs, so
the retry/fail path is fully exercised key-free. Any test that hits a real
provider would carry @pytest.mark.live (none here — all paths are mocked).

Cross-refs:
    - eval/scorers/artifact_checks.py (check_artifact + artifact_or_judge)
    - eval/scorers/judge.py (the pinned judge + retry loop)
    - eval/schemas.py (JudgeVerdict)
    - eval/tests/test_adapter_solver.py (sibling mock-driven solver test)
"""

from __future__ import annotations

from typing import Any

import pytest

from inspect_ai.model import ModelOutput, get_model
from inspect_ai.scorer import CORRECT, INCORRECT, Target
from inspect_ai.solver import TaskState

from eval.scorers.artifact_checks import (
    artifact_or_judge,
    check_artifact,
    has_checkable_artifact,
)
from eval.scorers.judge import judge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state(
    *,
    task_spec: dict[str, Any],
    completion: str = "",
    artifact_path: str | None = None,
    artifact_ref: str | None = None,
    terminal_state: str = "done",
) -> TaskState:
    state = TaskState(
        model="test/mock",
        sample_id="s1",
        epoch=0,
        input=task_spec.get("goal", "do the thing"),
        messages=[],
        metadata={
            "task_spec": task_spec,
            "artifact_path": artifact_path,
            "artifact_ref": artifact_ref,
            "terminal_state": terminal_state,
        },
    )
    state.output = ModelOutput.from_content(model="test/mock", content=completion)
    return state


def _verdict_json(verdict: str = "pass", confidence: float = 0.9) -> str:
    crit = "null" if verdict == "pass" else '"some criterion"'
    return (
        f'{{"verdict":"{verdict}","confidence":{confidence},'
        f'"reasoning":"ok","failing_criterion":{crit}}}'
    )


def _mock_model(outputs: list[str]):
    return get_model(
        "mockllm/model",
        custom_outputs=[
            ModelOutput.from_content(model="mockllm/model", content=o) for o in outputs
        ],
    )


# ---------------------------------------------------------------------------
# Deterministic check: file-present
# ---------------------------------------------------------------------------


def test_check_artifact_file_present_true(tmp_path) -> None:
    f = tmp_path / "out.txt"
    f.write_text("hello")
    state = _state(
        task_spec={"goal": "make out.txt", "artifact_spec": {"type": "file-present"}},
        artifact_path=str(f),
    )
    assert check_artifact(state, Target("")) is True


def test_check_artifact_file_present_false_when_missing(tmp_path) -> None:
    state = _state(
        task_spec={"goal": "make it", "artifact_spec": {"type": "file-present"}},
        artifact_path=str(tmp_path / "nope.txt"),
    )
    assert check_artifact(state, Target("")) is False


# ---------------------------------------------------------------------------
# Deterministic check: dom-or-text
# ---------------------------------------------------------------------------


def test_check_artifact_dom_or_text_substring_present() -> None:
    state = _state(
        task_spec={
            "goal": "say hi",
            "artifact_spec": {"type": "dom-or-text", "expected_substring": "hello"},
        },
        completion="well hello there",
    )
    assert check_artifact(state, Target("")) is True


def test_check_artifact_dom_or_text_substring_absent() -> None:
    state = _state(
        task_spec={
            "goal": "say hi",
            "artifact_spec": {"type": "dom-or-text", "expected_substring": "goodbye"},
        },
        completion="well hello there",
    )
    assert check_artifact(state, Target("")) is False


# ---------------------------------------------------------------------------
# Deterministic check: terminal-state
# ---------------------------------------------------------------------------


def test_check_artifact_terminal_state_match() -> None:
    state = _state(
        task_spec={
            "goal": "finish",
            "artifact_spec": {"type": "terminal-state", "expected_terminal_state": "done"},
        },
        terminal_state="done",
    )
    assert check_artifact(state, Target("")) is True


def test_check_artifact_terminal_state_mismatch() -> None:
    state = _state(
        task_spec={
            "goal": "finish",
            "artifact_spec": {"type": "terminal-state", "expected_terminal_state": "done"},
        },
        terminal_state="error",
    )
    assert check_artifact(state, Target("")) is False


# ---------------------------------------------------------------------------
# artifact_or_judge routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_artifact_or_judge_uses_deterministic_check_and_skips_judge(tmp_path) -> None:
    f = tmp_path / "out.txt"
    f.write_text("ok")
    state = _state(
        task_spec={"goal": "make out.txt", "artifact_spec": {"type": "file-present"}},
        artifact_path=str(f),
    )

    async def _exploding_judge(state: TaskState, target: Target):  # pragma: no cover
        raise AssertionError("judge must NOT be invoked when an artifact exists")

    score_fn = artifact_or_judge(judge_scorer=_exploding_judge)
    score = await score_fn(state, Target(""))
    assert score.value == CORRECT
    assert score.metadata["scored_by"] == "artifact"


@pytest.mark.asyncio
async def test_artifact_or_judge_falls_back_to_judge_when_no_artifact() -> None:
    state = _state(
        task_spec={"goal": "write a poem", "judge_scored": True},
        completion="a lovely poem",
    )
    assert has_checkable_artifact(state) is False

    judge_fn = judge(model=_mock_model([_verdict_json("pass")]))
    score_fn = artifact_or_judge(judge_scorer=judge_fn)
    score = await score_fn(state, Target("the poem is lovely"))
    assert score.value == CORRECT
    assert score.metadata["scored_by"] == "judge"


# ---------------------------------------------------------------------------
# judge: valid verdict, retry, and total failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_judge_valid_verdict_first_attempt() -> None:
    state = _state(task_spec={"goal": "g", "judge_scored": True}, completion="t")
    score_fn = judge(model=_mock_model([_verdict_json("fail")]))
    score = await score_fn(state, Target("gold"))
    assert score.value == INCORRECT
    assert score.answer == "fail"


@pytest.mark.asyncio
async def test_judge_retries_then_succeeds() -> None:
    # First output is malformed JSON; second is valid -> retry loop recovers.
    state = _state(task_spec={"goal": "g", "judge_scored": True}, completion="t")
    score_fn = judge(model=_mock_model(["NOT JSON", _verdict_json("pass")]))
    score = await score_fn(state, Target("gold"))
    assert score.value == CORRECT
    # The first failed attempt is logged for forensics.
    assert state.metadata.get("judge_failed_attempts")
    assert len(state.metadata["judge_failed_attempts"]) == 1


@pytest.mark.asyncio
async def test_judge_three_failures_returns_incorrect_and_flags() -> None:
    state = _state(task_spec={"goal": "g", "judge_scored": True}, completion="t")
    score_fn = judge(model=_mock_model(["bad1", "bad2", "bad3"]))
    score = await score_fn(state, Target("gold"))
    assert score.value == INCORRECT
    assert "judge schema failure" in (score.explanation or "")
    assert state.metadata.get("judge_schema_failure") is True
    assert len(state.metadata["judge_failed_attempts"]) == 3
