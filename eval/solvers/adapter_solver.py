"""Agentic streaming solver — drives the EXISTING apps.api.backends adapters.

Unlike `route_solver` (which scores the local joblib `decide()` in-process with
no network), this solver consumes a real streaming agent loop: it builds one of
the concrete `apps.api.backends` adapters, calls its single
`async def stream(prompt, history, options) -> AsyncIterator[ChatChunk]`
contract, accumulates the transcript, captures the deterministic artifact handle,
and sums the terminal `Done.cost_usd` into `state.metadata`. It NEVER invokes the
inspect-ai generate callback — there is no separate model to grade; the agent
loop IS the thing under test.

CRITICAL chunk-shape contract (10-PATTERNS.md §adapter_solver.py, which
SUPERSEDES the RESEARCH §Pattern 2 sketch's `getattr(chunk, "path", None)` for a
screenshot):
    - FileDiff carries `.path` — the deterministic file-mutation handle
      (apps/api/backends/chunks.py:94-98).
    - Screenshot carries `.image_ref` (a file path or object key set by
      STORE-04), NEVER `.path` (apps/api/backends/chunks.py:101-114). The
      image_ref may be a bare blob KEY resolved later by artifact_checks via
      apps/api/blobs.py.
    - Done carries an OPTIONAL `.cost_usd` (apps/api/backends/chunks.py:166-172)
      summed here (None-safe); it is NOT available in inspect-ai log.stats.
    - StreamError signals a structured mid-stream failure before the terminal
      Done (apps/api/backends/chunks.py:117-146).

Adapter construction (10-PATTERNS.md §adapter_solver.py — Analog: the live-run
recipe in turn.py:663-722, but the harness has no FastAPI `app.state`, so the
adapter is built directly from env keys like claude_code/__main__.py:51). The
D-12 STRICT-AND gate (env `COMPUTER_USE_OPT_IN=1` AND the in-app toggle) is
enforced BEFORE constructing the computer_use adapter (turn.py:668-671); the
ComputerUseAdapter constructor itself re-checks the env opt-in (adapter.py:228).

Cross-refs:
    - apps/api/backends/protocol.py:114 (the `stream(...)` Protocol + AdapterOptions)
    - apps/api/backends/chunks.py (TextDelta/FileDiff/Screenshot/StreamError/Done)
    - apps/api/backends/claude_code/__main__.py:51-82 (stream-consumer template)
    - apps/api/routes/turn.py:982-1117 (production chunk-dispatch + cost extraction)
    - eval/solvers/route_solver.py (the sibling non-model solver)
    - 10-PATTERNS.md §eval/solvers/adapter_solver.py (AUTHORITATIVE chunk shapes)
"""

from __future__ import annotations

import os
from typing import Any, Callable

from inspect_ai.model import ModelOutput
from inspect_ai.solver import Generate, TaskState, solver

from apps.api.backends.chunks import Done, FileDiff, Screenshot, StreamError, TextDelta
from apps.api.backends.protocol import AdapterOptions

# Bound the transcript handed to the LLM-judge so a runaway agent loop cannot
# overflow the judge's context window (threat T-10-INJ: keep the judge surface
# small). Last-8000-chars is the locked window (PLAN Task 1 <action>).
_JUDGE_TRANSCRIPT_CHARS = 8000


def _default_adapter_factory(backend: str) -> Any:
    """Build a concrete adapter for a live run from env keys (BYOK).

    Mirrors the live-run construction recipe (turn.py:679-687) but reads the
    API key from `os.environ` instead of the FastAPI keystore (the harness has
    no `app.state`). Imports are lazy so merely importing this module — e.g. for
    a key-free mock-adapter unit test that injects its own factory — never pulls
    in the heavyweight provider SDKs.

    For `computer_use`, the D-12 STRICT-AND gate is enforced here BEFORE
    construction (turn.py:668-671); the ComputerUseAdapter constructor itself
    re-asserts `COMPUTER_USE_OPT_IN=1` (adapter.py:228), so this is the
    belt-and-suspenders outer check that surfaces the actionable message early.
    """

    if backend == "claude_code":
        from apps.api.backends.claude_code.adapter import ClaudeCodeAdapter

        return ClaudeCodeAdapter(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    if backend == "computer_use":
        # D-12 STRICT-AND outer gate (turn.py:668-671). The in-app toggle is
        # not available in the harness, so the env opt-in is the gate the
        # operator controls; the adapter constructor enforces it as well.
        if os.environ.get("COMPUTER_USE_OPT_IN") != "1":
            raise RuntimeError(
                "computer-use is OFF — set COMPUTER_USE_OPT_IN=1 to enable the "
                "computer-use agentic branch (D-12 STRICT-AND gate)."
            )
        from apps.api.backends.computer_use.adapter import ComputerUseAdapter

        return ComputerUseAdapter(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    if backend == "openrouter":
        from apps.api.backends.openrouter.adapter import OpenRouterAdapter

        return OpenRouterAdapter(api_key=os.environ.get("OPENROUTER_API_KEY"))

    raise ValueError(f"unknown backend: {backend!r}")


@solver
def adapter_solver(
    backend: str,
    *,
    adapter_factory: Callable[[str], Any] | None = None,
):
    """Drive an apps.api.backends streaming adapter and score its artifacts.

    `backend` selects which concrete adapter to build (claude_code /
    computer_use / openrouter). `adapter_factory` is an injection seam: tests
    pass a factory returning a mock adapter whose `stream(...)` replays a fixed
    chunk list, so all five <behavior> cases are exercised key-free with NO
    network. The live path uses `_default_adapter_factory`, which builds the
    real adapter from env BYOK keys.

    The solver reads the per-task spec from `state.metadata["task_spec"]`
    (seeded by the suite's record_to_sample), builds `AdapterOptions` with the
    per-task caps, consumes the stream, and stashes:
        - state.output.completion : the bounded transcript (for the judge)
        - state.metadata["adapter_usage_usd"] : summed Done.cost_usd (None-safe)
        - state.metadata["artifact_path"] : FileDiff.path (deterministic file)
        - state.metadata["artifact_ref"] : Screenshot.image_ref (NOT .path)
        - state.metadata["terminal_state"] : "done" | "error"

    It NEVER awaits the generate callback and NEVER spins a nested event loop
    runner — it is already inside inspect-ai's event loop, and the agent loop IS
    the thing under test (no separate model to grade).
    """

    factory = adapter_factory or _default_adapter_factory

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        spec = state.metadata.get("task_spec", {}) if state.metadata else {}
        adapter = factory(backend)

        options = AdapterOptions(
            model=spec.get("model"),
            max_cost_usd=spec.get("max_cost_usd"),
            max_steps=spec.get("max_steps"),
        )

        text_parts: list[str] = []
        usage_usd = 0.0
        artifact_path: str | None = None
        artifact_ref: str | None = None
        terminal_state = "done"

        async for chunk in adapter.stream(
            spec.get("goal", state.input_text),
            history=[],
            options=options,
        ):
            if isinstance(chunk, TextDelta):
                text_parts.append(chunk.text)
            elif isinstance(chunk, FileDiff):
                # FileDiff DOES carry .path — the deterministic artifact handle.
                artifact_path = chunk.path
            elif isinstance(chunk, Screenshot):
                # CORRECTION (PATTERNS.md supersedes RESEARCH §Pattern 2): a
                # Screenshot has NO .path — its handle is .image_ref (a file
                # path or blob object key resolved later via apps/api/blobs.py).
                artifact_ref = chunk.image_ref
            elif isinstance(chunk, StreamError):
                terminal_state = "error"
            elif isinstance(chunk, Done):
                # Sum the terminal USD here (None-safe). This is the ONLY place
                # the per-sample adapter spend is captured — it is not present
                # in inspect-ai's log.stats (PLAN Task 1 <action>).
                usage_usd += chunk.cost_usd or 0.0
                if terminal_state != "error":
                    terminal_state = "done"

        # Bound the transcript so the judge window cannot overflow (T-10-INJ).
        completion = "".join(text_parts)[-_JUDGE_TRANSCRIPT_CHARS:]
        state.output = ModelOutput.from_content(model=backend, content=completion)

        state.metadata["adapter_usage_usd"] = usage_usd
        state.metadata["artifact_path"] = artifact_path
        state.metadata["artifact_ref"] = artifact_ref
        state.metadata["terminal_state"] = terminal_state
        return state

    return solve
