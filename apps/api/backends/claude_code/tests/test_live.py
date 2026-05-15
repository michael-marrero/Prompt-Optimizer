# Plan 02-02 Task 3 — Claude Code live smoke (BACKEND-04 + VALIDATION.md
# "Manual-Only Verifications"). Opt-in: requires ANTHROPIC_API_KEY in env
# and the ``live`` pytest marker.
#
# Run with::
#
#     ANTHROPIC_API_KEY=sk-ant-... uv run pytest -m live apps/api/backends/claude_code
#
# Cost-bounded by ``max_cost_usd=0.20`` — the prompt asks Claude to
# create a one-line hello.py so the per-turn spend stays well under
# 20¢. The test uses ``tmp_path`` as the workspace so the file is
# inspectable after the stream (cwd opt-in -> no cleanup).

from __future__ import annotations

import os
from pathlib import Path

import pytest

from apps.api.backends.chunks import Done, FileDiff
from apps.api.backends.claude_code.adapter import ClaudeCodeAdapter
from apps.api.backends.protocol import AdapterOptions


@pytest.mark.live
@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"), reason="no ANTHROPIC_API_KEY in env"
)
@pytest.mark.asyncio
async def test_live_create_hello_py(tmp_path: Path) -> None:
    """End-to-end: real Claude Code, real subprocess, real billing.

    Asserts:
        - At least one FileDiff chunk arrives with ``path`` ending in
          ``hello.py`` (Edit or Write operation).
        - The terminal chunk is a Done.
        - cost_usd is positive (provider reported) and below the cap.
        - ``hello.py`` exists in the workspace after the stream.
    """

    api_key = os.environ["ANTHROPIC_API_KEY"]
    cwd = str(tmp_path)

    adapter = ClaudeCodeAdapter(api_key=api_key, max_cost_usd=0.20)
    options = AdapterOptions(
        model="claude-agent-sdk",
        max_cost_usd=0.20,
        max_steps=25,
        cwd=cwd,
    )

    chunks: list = []
    async for chunk in adapter.stream(
        prompt=(
            "Create a file named hello.py in the current directory "
            "containing exactly the line: print('hello world')"
        ),
        history=[],
        options=options,
    ):
        chunks.append(chunk)

    file_diffs = [c for c in chunks if isinstance(c, FileDiff)]
    assert file_diffs, "expected at least one FileDiff chunk"
    assert any(
        c.path.endswith("hello.py") and c.operation in ("create", "edit")
        for c in file_diffs
    )

    assert isinstance(chunks[-1], Done), "terminal chunk must be Done"
    done = chunks[-1]
    assert done.cost_usd is not None and done.cost_usd > 0
    assert done.cost_usd < 0.20

    # The user-supplied cwd should still exist (cwd opt-in -> no
    # cleanup) and contain hello.py.
    assert (tmp_path / "hello.py").exists()
