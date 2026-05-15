"""``ephemeral_workspace`` async context manager — BACKEND-08 lifecycle.

Public surface (BACKEND-08, CONTEXT specifics line 264):

    ephemeral_workspace(cwd: str | None)
        async context manager yielding ``(workspace_path, must_cleanup)``.

Behaviour:

    cwd = None   → mkdtemp(prefix='pomu-cc-')   cleanup=True
    cwd != None  → workspace = cwd              cleanup=False

The Claude CLI subprocess can read / write inside the workspace dir.
By default we isolate it to a fresh ``tempfile.mkdtemp`` per turn so
the user's repo is untouched. The opt-in ``options.cwd`` flag (set
from the Phase 5 UI settings panel) points the subprocess at the
user's repository for build-and-edit work; ``cleanup=False`` in that
branch leaves the user-supplied directory alone.

The ``pomu-cc-`` prefix (CONTEXT specifics line 264) makes leaked
workspaces grep-able under ``/tmp`` so they can be batched-cleaned by
operators after a crash.

Cross-refs:
    - 02-RESEARCH.md §"Pattern 8" lines 1430-1454 (canonical source)
    - 02-CONTEXT.md specifics line 264 (mkdtemp prefix)
    - 02-PATTERNS.md "claude_code/workspace.py" lines 714-732
    - T-02-05 (workspace leak threat — mitigated by finally-rmtree)
"""

from __future__ import annotations

import contextlib
import shutil
import tempfile
from typing import AsyncIterator


@contextlib.asynccontextmanager
async def ephemeral_workspace(
    cwd: str | None,
) -> AsyncIterator[tuple[str, bool]]:
    """Yield ``(workspace_path, must_cleanup)`` for one adapter turn.

    The caller passes ``options.cwd`` from ``AdapterOptions``; when it
    is None we mkdtemp a fresh per-turn workspace. The ``must_cleanup``
    flag tells the caller whether to rmtree on exit; the cleanup also
    runs here in the ``finally`` block as belt-and-suspenders so an
    early-return path can't leak the directory.
    """

    if cwd is None:
        workspace = tempfile.mkdtemp(prefix="pomu-cc-")
        cleanup = True
    else:
        workspace = cwd
        cleanup = False

    try:
        yield workspace, cleanup
    finally:
        if cleanup:
            # ignore_errors=True keeps the finally idempotent even if a
            # subprocess raced us to delete a file or the directory is
            # already gone.
            shutil.rmtree(workspace, ignore_errors=True)
