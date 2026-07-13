"""Wave 0 sanity test — Phase 3 scaffolding.

Confirms five things at one breath:

    1. The 4 new Phase 3 deps + 1 dev dep (``fastapi``, ``uvicorn``,
       ``aiosqlite``, ``sse_starlette``, ``httpx_sse``) import cleanly.
    2. ``apps.api.paths`` constants are well-formed and end with the
       expected filename suffixes.
    3. ``PROMPT_OPTIMIZER_HOME`` env override re-routes ``USER_HOME``
       (via ``importlib.reload``).
    4. ``FakeStreamingAdapter`` yields the pre-built chunks list,
       terminating on ``Done``.
    5. **API-08 / D-20 negative-grep guard** — runs the canonical
       check via ``subprocess`` so the assertion fails if a future
       executor introduces a synchronous FastAPI test-client import.

The guard test deliberately uses ``subprocess + grep`` rather than
importing the forbidden symbol just to assert its absence — even
an absent-assertion import would match the very pattern this guard
forbids. For the same reason, the regex itself is constructed at
runtime from separate string fragments so the source file does
not contain a literal match for its own pattern.

Cross-refs:
    - 03-PLAN-00 Task 4 lines 404-457
    - 03-VALIDATION.md rows 3-00-01, 3-00-02 lines 45-46
    - 03-PATTERNS.md anti-pattern audit lines 522-543
"""

from __future__ import annotations

import importlib
import os
import subprocess
from pathlib import Path

import pytest


def test_phase_3_deps_importable() -> None:
    """Confirm the 4 Phase 3 deps + 1 dev dep import without error.

    A failure here means ``uv sync`` did not bring in the new
    dependencies (e.g., someone ran ``uv lock`` but skipped
    ``uv sync``). The assertion is implicit — the ``import`` lines
    raise ``ImportError`` on miss.
    """

    import aiosqlite  # noqa: F401
    import fastapi  # noqa: F401
    import uvicorn  # noqa: F401
    from httpx_sse import aconnect_sse  # noqa: F401
    from sse_starlette.sse import EventSourceResponse  # noqa: F401


def test_paths_constants_well_formed() -> None:
    """Inspect every path constant for the expected filename suffix.

    The constants are formed inside ``apps/api/paths.py``; this test
    is a tripwire if someone refactors the path layout (e.g., moves
    ``chat.db`` to a sub-directory). The ``PROJECT_ROOT.is_dir()``
    check confirms the ``parents[2]`` lift is anchored at the repo
    root, not some sub-directory caused by a future file relocation.
    """

    from apps.api.paths import (
        BLOBS_DIR,
        DB_PATH,
        JSONL_LOG_PATH,
        PROJECT_ROOT,
        SETTINGS_PATH,
        USER_HOME,
        WORKSPACES_DIR,
    )

    assert PROJECT_ROOT.is_dir()
    # Sanity-check the repo-root computation by looking for a
    # marker file that lives only at the repo root.
    assert (PROJECT_ROOT / "pyproject.toml").is_file()
    assert str(DB_PATH).endswith("chat.db")
    assert str(BLOBS_DIR).endswith("blobs")
    assert str(SETTINGS_PATH).endswith("settings.json")
    assert str(WORKSPACES_DIR).endswith("workspaces")
    assert str(JSONL_LOG_PATH).endswith(".planning/data/routing_decisions.jsonl")
    # USER_HOME is the parent of every per-user data file.
    assert DB_PATH.parent == USER_HOME
    assert BLOBS_DIR.parent == USER_HOME
    assert SETTINGS_PATH.parent == USER_HOME
    assert WORKSPACES_DIR.parent == USER_HOME
    # JSONL_LOG_PATH (routing-decisions log) is anchored on USER_HOME too
    # (AD-12), co-located with the DB / feedback log under a single
    # ``PROMPT_OPTIMIZER_HOME`` root. The subpath is
    # ``<USER_HOME>/.planning/data/routing_decisions.jsonl`` so the home
    # root is parents[2].
    assert JSONL_LOG_PATH.parents[2] == USER_HOME


def test_paths_honors_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """``PROMPT_OPTIMIZER_HOME`` env override re-routes ``USER_HOME``.

    Forces a reload of ``apps.api.paths`` so the module re-reads
    ``os.environ`` at import time. ``monkeypatch`` rolls the env
    back after the test, then a final reload restores the
    ``USER_HOME`` constant to its non-override default for any
    later test in the same session.
    """

    import apps.api.paths as paths_module

    monkeypatch.setenv("PROMPT_OPTIMIZER_HOME", "/tmp/po-test")
    importlib.reload(paths_module)
    assert paths_module.USER_HOME == Path("/tmp/po-test")
    # Cleanup: drop the env var so the next reload picks the default.
    monkeypatch.delenv("PROMPT_OPTIMIZER_HOME", raising=False)
    importlib.reload(paths_module)


async def test_fake_streaming_adapter_yields_chunks() -> None:
    """``FakeStreamingAdapter`` yields the pre-built chunks list.

    Confirms the Protocol's async-iterator contract is honored and
    that the terminal chunk is the ``Done`` instance the test
    provided. The fake never synthesizes a ``Done`` of its own
    (Phase 2 D-04 contract is the caller's responsibility).
    """

    from apps.api.backends.chunks import Done, TextDelta
    from apps.api.backends.protocol import AdapterOptions
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    adapter = FakeStreamingAdapter([TextDelta(text="hi"), Done()])
    chunks = [c async for c in adapter.stream("prompt", [], AdapterOptions())]
    assert len(chunks) == 2
    assert chunks[0].type == "text_delta"
    assert chunks[-1].type == "done"


def test_no_testclient_imports_under_apps_api_tests() -> None:
    """**API-08 / D-20** — negative-grep guard.

    Asserts ``grep`` finds NO match for the synchronous FastAPI
    test-client import path anywhere under ``apps/api/tests/``.
    ``grep -E`` exits with code 1 when no matches are found; we
    invert that into a pass.

    This test deliberately uses ``subprocess`` to run the same
    regex CI enforces. The pattern is BUILT AT RUNTIME from
    fragments so this source file does not itself match the
    pattern (which would falsely fail the guard).
    """

    repo_root = Path(__file__).resolve().parents[3]
    tests_dir = repo_root / "apps" / "api" / "tests"
    assert tests_dir.is_dir(), tests_dir

    # Build the forbidden regex at runtime from fragments so this
    # source file does NOT contain the literal pattern.
    forbidden_module = "fastapi" + "." + "testclient"
    forbidden_class = "Test" + "Client"
    pattern = (
        "from " + forbidden_module
        + "|"
        + forbidden_module.replace(".", r"\.") + r"\." + forbidden_class
    )

    result = subprocess.run(
        [
            "grep",
            "-rE",
            "--include=*.py",
            "--include=*.sql",
            pattern,
            str(tests_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    # grep exit code 1 == "no matches found" (what we want).
    # exit code 0 == matches were found (failure).
    # exit code 2+ == grep error (also failure).
    assert result.returncode == 1, (
        "API-08 violated — forbidden imports found under apps/api/tests/:\n"
        + result.stdout
    )
