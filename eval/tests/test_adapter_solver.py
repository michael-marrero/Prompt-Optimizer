"""Mock-adapter unit tests for the agentic adapter_solver (Plan 10-04, Task 1).

These tests drive `eval.solvers.adapter_solver.adapter_solver` against a
duck-typed mock adapter whose `stream(...)` is an async generator yielding real
`apps.api.backends.chunks` instances. NO network, NO real provider, NO key — the
solver consumes the streaming contract in-process so all five <behavior> cases
are exercised key-free.

CRITICAL chunk-shape contract (10-PATTERNS.md §adapter_solver.py, which
SUPERSEDES the RESEARCH §Pattern 2 sketch):
    - FileDiff carries `.path` — the deterministic artifact handle.
    - Screenshot carries `.image_ref` (a file path or object key), NOT `.path`.
      The Screenshot case below asserts capture from `.image_ref` and MUST NEVER
      assert `.path` — doing so would re-encode the superseded RESEARCH error.

Cross-refs:
    - eval/solvers/adapter_solver.py (the solver under test)
    - apps/api/backends/chunks.py (TextDelta/FileDiff/Screenshot/StreamError/Done)
    - eval/solvers/route_solver.py (the sibling non-model solver pattern)
    - 10-PATTERNS.md §eval/solvers/adapter_solver.py (authoritative chunk shapes)
"""

from __future__ import annotations

from typing import Any, AsyncIterator

import pytest

from apps.api.backends.chunks import (
    ChatChunk,
    Done,
    FileDiff,
    Screenshot,
    StreamError,
    TextDelta,
)
from inspect_ai.model import ModelOutput
from inspect_ai.solver import TaskState

from eval.solvers.adapter_solver import adapter_solver


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _MockAdapter:
    """Duck-typed BackendAdapter whose stream() replays a fixed chunk list.

    Mirrors the real `BackendAdapter` Protocol's single `async def stream(...)`
    method (apps/api/backends/protocol.py:114). It captures nothing from the
    provider — it just yields the pre-baked chunks so the solver's dispatch is
    exercised without a network round-trip.
    """

    def __init__(self, chunks: list[ChatChunk]) -> None:
        self._chunks = chunks
        self.seen_prompt: str | None = None

    async def stream(
        self, prompt: str, history: Any, options: Any
    ) -> AsyncIterator[ChatChunk]:
        self.seen_prompt = prompt
        for chunk in self._chunks:
            yield chunk


def _make_state(goal: str = "do the thing") -> TaskState:
    """Build a minimal TaskState carrying the task_spec the solver reads."""
    state = TaskState(
        model="test/mock",
        sample_id="t1",
        epoch=0,
        input=goal,
        messages=[],
        metadata={"task_spec": {"goal": goal, "max_cost_usd": 0.5, "max_steps": 10}},
    )
    # Seed an empty output so assertions on .completion are well-defined.
    state.output = ModelOutput.from_content(model="test/mock", content="")
    return state


async def _run_solver(state: TaskState, adapter: _MockAdapter) -> TaskState:
    """Invoke the solver's inner solve() with an injected mock adapter."""
    solve = adapter_solver(backend="claude_code", adapter_factory=lambda backend: adapter)
    # generate is never called by this solver (no network); pass a sentinel.
    async def _generate(state: TaskState, **kwargs: Any) -> TaskState:  # pragma: no cover
        raise AssertionError("adapter_solver must NOT invoke generate()")

    return await solve(state, _generate)


# ---------------------------------------------------------------------------
# <behavior> case 1 — TextDelta then Done(cost_usd=0.05)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_textdelta_then_done_captures_completion_cost_and_terminal_state() -> None:
    adapter = _MockAdapter([TextDelta(text="hi"), Done(cost_usd=0.05)])
    state = await _run_solver(_make_state(), adapter)

    assert "hi" in state.output.completion
    assert state.metadata["adapter_usage_usd"] == 0.05
    assert state.metadata["terminal_state"] == "done"


# ---------------------------------------------------------------------------
# <behavior> case 2 — FileDiff(path=...) then Done -> artifact_path captured
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filediff_captures_artifact_path() -> None:
    adapter = _MockAdapter(
        [
            FileDiff(
                tool_call_id="tc_abc123",
                path="out.txt",
                diff="+hello",
                operation="create",
            ),
            Done(cost_usd=0.01),
        ]
    )
    state = await _run_solver(_make_state(), adapter)

    assert state.metadata["artifact_path"] == "out.txt"
    assert state.metadata["terminal_state"] == "done"


# ---------------------------------------------------------------------------
# <behavior> case 3 — Screenshot(image_ref=...) then Done -> captured from
# .image_ref (NOT .path). This case MUST NOT assert .path.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screenshot_captures_image_ref_not_path() -> None:
    adapter = _MockAdapter(
        [Screenshot(image_ref="blob:abc", step=1), Done(cost_usd=0.02)]
    )
    state = await _run_solver(_make_state(), adapter)

    # The Screenshot artifact handle is image_ref (PATTERNS.md supersedes the
    # RESEARCH §Pattern 2 sketch). A Screenshot has NO `.path` attribute.
    assert state.metadata["artifact_ref"] == "blob:abc"
    assert not hasattr(Screenshot(step=1), "path")


# ---------------------------------------------------------------------------
# <behavior> case 4 — StreamError then Done -> terminal_state == "error"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_error_sets_terminal_state_error() -> None:
    adapter = _MockAdapter(
        [
            StreamError(code="provider_unavailable", message="boom", retriable=True),
            Done(),
        ]
    )
    state = await _run_solver(_make_state(), adapter)

    assert state.metadata["terminal_state"] == "error"


# ---------------------------------------------------------------------------
# <behavior> case 5 — Done(cost_usd=None) contributes 0.0 (no crash)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_done_cost_none_is_zero_safe() -> None:
    adapter = _MockAdapter([TextDelta(text="ok"), Done(cost_usd=None)])
    state = await _run_solver(_make_state(), adapter)

    assert state.metadata["adapter_usage_usd"] == 0.0
    assert state.metadata["terminal_state"] == "done"
