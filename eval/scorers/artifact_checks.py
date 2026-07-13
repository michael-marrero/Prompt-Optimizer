"""Deterministic artifact checks + the artifact-first hybrid scorer (EVAL-03).

The hybrid scoring decision is LOCKED (PLAN Task 2): run a deterministic
machine-checkable artifact check WHEREVER a checkable artifact handle exists, and
fall back to the pinned LLM-judge ONLY when none does. Deterministic-first keeps
the judge window small and shrinks the indirect-prompt-injection surface
(threat T-10-INJ).

Three check types, keyed by the task spec's `artifact_spec.type`:
    - "file-present"   : the expected file exists at the captured artifact path.
                         A FileDiff path is a filesystem path; a Screenshot
                         image_ref may be a bare blob KEY (`<sha>.<ext>`), which
                         is resolved under apps/api/paths.BLOBS_DIR (the same
                         re-anchoring apps/api/blobs.py does — image_ref is NOT
                         assumed to be a filesystem path).
    - "dom-or-text"    : the expected substring is present in the captured
                         transcript (state.output.completion).
    - "terminal-state" : state.metadata["terminal_state"] matches the expected
                         terminal state ("done" | "error").

`check_artifact(state, target) -> bool` is the pure (network-free) predicate the
unit tests exercise directly. `artifact_or_judge()` is the inspect-ai @scorer that
routes: deterministic check when an artifact handle exists, judge otherwise.

Cross-refs:
    - apps/api/blobs.py (blob-by-key resolution under BLOBS_DIR — image_ref keys)
    - apps/api/backends/chunks.py:86-114 (FileDiff.path / Screenshot.image_ref)
    - eval/solvers/adapter_solver.py (stashes artifact_path/artifact_ref/terminal_state)
    - eval/scorers/judge.py (the fallback pinned judge)
    - 10-RESEARCH.md §Pattern 3 (artifact_or_judge routing)
    - 10-PATTERNS.md §eval/scorers/artifact_checks.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from inspect_ai.scorer import (
    CORRECT,
    INCORRECT,
    Score,
    Target,
    accuracy,
    scorer,
    stderr,
)
from inspect_ai.solver import TaskState


def _resolve_artifact_file(handle: str) -> Path:
    """Resolve a captured artifact handle to a filesystem Path.

    A FileDiff `.path` is already a filesystem path. A Screenshot `.image_ref`
    may be a bare content KEY (`<sha>.<ext>`, BL-01) rather than an absolute
    path; re-anchor a relative key under `apps.api.paths.BLOBS_DIR` exactly as
    `apps/api/blobs._collect_blob_refs_from_content_blocks._to_path` does, so a
    blob key resolves to the real file on disk. Absolute paths pass through
    verbatim.
    """

    p = Path(handle)
    if p.is_absolute():
        return p
    try:
        import apps.api.paths as _paths

        return _paths.BLOBS_DIR / handle
    except Exception:
        # No FastAPI paths module available (pure unit test) — treat the handle
        # as a repo-relative / cwd-relative filesystem path.
        return p


def check_artifact(state: TaskState, target: Target) -> bool:
    """Deterministic machine-checkable artifact predicate (network-free).

    Reads the task spec's `artifact_spec` from `state.metadata["task_spec"]` and
    dispatches on its `type`. Returns False (not an exception) for an unknown
    type or a missing handle so the scorer degrades to a clean INCORRECT rather
    than crashing the run.
    """

    meta = state.metadata or {}
    spec = meta.get("task_spec", {}) or {}
    artifact_spec = spec.get("artifact_spec", {}) or {}
    check_type = artifact_spec.get("type")

    if check_type == "file-present":
        handle = meta.get("artifact_path") or meta.get("artifact_ref")
        if not handle:
            return False
        return _resolve_artifact_file(handle).exists()

    if check_type == "dom-or-text":
        expected = artifact_spec.get("expected_substring", "")
        if not expected:
            return False
        transcript = state.output.completion if state.output else ""
        return expected in transcript

    if check_type == "terminal-state":
        expected = artifact_spec.get("expected_terminal_state")
        return meta.get("terminal_state") == expected

    return False


def has_checkable_artifact(state: TaskState) -> bool:
    """True iff a deterministic artifact check is applicable to this sample.

    An artifact is checkable when the task spec declares an `artifact_spec.type`
    AND (for file/text checks) the corresponding handle/expectation is present.
    A judge-scored task (no `artifact_spec`, or an explicit `judge_scored: true`
    marker) returns False so `artifact_or_judge` falls back to the judge.
    """

    meta = state.metadata or {}
    spec = meta.get("task_spec", {}) or {}
    if spec.get("judge_scored"):
        return False
    artifact_spec = spec.get("artifact_spec", {}) or {}
    check_type = artifact_spec.get("type")
    if check_type == "file-present":
        return bool(meta.get("artifact_path") or meta.get("artifact_ref"))
    if check_type == "dom-or-text":
        return bool(artifact_spec.get("expected_substring"))
    if check_type == "terminal-state":
        return artifact_spec.get("expected_terminal_state") is not None
    return False


@scorer(metrics=[accuracy(), stderr()])
def artifact_or_judge(judge_scorer: Any = None):
    """Hybrid scorer: deterministic artifact check first, pinned judge fallback.

    When `has_checkable_artifact(state)` is True the deterministic
    `check_artifact` Score is returned and the judge is NEVER invoked (small
    judge window + reduced injection surface, T-10-INJ). Otherwise the judge
    scores the sample.

    `judge_scorer` is injected so tests can verify the routing without a live
    model; the live wiring (eval/suites/agentic_completion.py) passes
    `judge()`. The judge is imported lazily inside the default path so importing
    this module stays light for the deterministic-only unit tests.
    """

    _judge = judge_scorer

    async def score(state: TaskState, target: Target) -> Score:
        if has_checkable_artifact(state):
            ok = check_artifact(state, target)
            return Score(
                value=CORRECT if ok else INCORRECT,
                answer=state.output.completion if state.output else "",
                explanation=(
                    "deterministic artifact check "
                    f"({(state.metadata or {}).get('task_spec', {}).get('artifact_spec', {}).get('type')})"
                ),
                metadata={"scored_by": "artifact"},
            )

        judge_fn = _judge
        if judge_fn is None:
            from eval.scorers.judge import judge

            judge_fn = judge()
        result = await judge_fn(state, target)
        # Stamp the routing decision without clobbering the judge's metadata.
        merged = dict(result.metadata or {})
        merged.setdefault("scored_by", "judge")
        return Score(
            value=result.value,
            answer=result.answer,
            explanation=result.explanation,
            metadata=merged,
        )

    return score
