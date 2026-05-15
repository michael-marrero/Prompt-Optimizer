# Plan 02-02 Task 1 — BACKEND-08 ephemeral workspace lifecycle.
#
# Four invariants for ``ephemeral_workspace``:
#   1. cwd=None → mkdtemp(prefix='pomu-cc-'); workspace exists inside
#      the ``async with``; cleanup=True; workspace removed after exit.
#   2. cwd='/user/repo' → yields exactly that path; cleanup=False;
#      user directory untouched after exit.
#   3. cleanup runs in ``finally`` even when the body raises.
#   4. Re-cleanup tolerates a missing directory (idempotent rmtree).

from __future__ import annotations

import os

import pytest

from apps.api.backends.claude_code.workspace import ephemeral_workspace


@pytest.mark.asyncio
async def test_ephemeral_workspace_creates_and_cleans() -> None:
    """Default (cwd=None) — fresh tmpdir per invocation, removed on exit."""

    async with ephemeral_workspace(None) as (path, cleanup):
        assert isinstance(path, str)
        assert os.path.isdir(path)
        assert os.path.basename(path).startswith("pomu-cc-")
        assert cleanup is True
        captured = path

    # After context exit the tmpdir must be gone.
    assert not os.path.exists(captured)


@pytest.mark.asyncio
async def test_ephemeral_workspace_honors_cwd(tmp_path) -> None:
    """Opt-in cwd — yielded verbatim; cleanup=False; user dir survives."""

    cwd = str(tmp_path / "user_repo")
    os.makedirs(cwd)

    async with ephemeral_workspace(cwd) as (path, cleanup):
        assert path == cwd
        assert cleanup is False

    # User-provided directory must be untouched after context exit.
    assert os.path.exists(cwd)


@pytest.mark.asyncio
async def test_ephemeral_workspace_cleans_on_exception() -> None:
    """Cleanup runs in ``finally`` so an exception inside the body does
    not leak the temp directory."""

    captured: list[str] = []
    with pytest.raises(RuntimeError):
        async with ephemeral_workspace(None) as (path, _cleanup):
            captured.append(path)
            raise RuntimeError("boom")
    assert captured and not os.path.exists(captured[0])
