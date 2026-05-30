"""``apps.api.paths`` — single source of path constants for Phase 3.

Public surface (CONTEXT canonical refs line 242):

    PROJECT_ROOT       Path — repo root, used by JSONL log layout.
    USER_HOME          Path — per-user storage root; honors
                       ``PROMPT_OPTIMIZER_HOME`` env override and
                       falls back to ``~/.prompt-optimizer/``.
    DB_PATH            Path — SQLite database file inside ``USER_HOME``.
    BLOBS_DIR          Path — content-addressed blob store (STORE-04).
    SETTINGS_PATH      Path — JSON settings file (D-11 non-key fields).
    WORKSPACES_DIR     Path — per-thread Claude Code workspaces.
    JSONL_LOG_PATH     Path — offline routing-decisions log (STORE-06).

Every Phase 3 module that needs a filesystem path imports from here.
The constants are evaluated at module import time so a single
canonical answer exists per process — re-importing this module
returns the same paths.

The ``PROMPT_OPTIMIZER_HOME`` env override is read once at import
time. Tests that need to flip the override must monkeypatch
``os.environ`` AND ``importlib.reload`` this module so the constants
recompute.

Cross-refs:
    - 03-CONTEXT.md canonical refs line 242 (paths.py role)
    - 03-CONTEXT.md Storage Layout lines 262-273
    - 03-PATTERNS.md Excerpt 1 lines 126-156 (lift-source)
    - 02-CONTEXT.md / ``apps/api/__init__.py`` line 49 (PROJECT_ROOT
      convention — ``parents[2]`` lands at the repo root because this
      file is two levels below it, same depth as ``__init__.py``).

This module never mutates ``sys.path`` (anti-pattern per CLAUDE.md
`## Conventions / Import Organization` and 03-CONTEXT.md) and
never builds paths via stringly-typed concatenation (Phase 2
``pathlib`` convention carry-forward).
"""

from __future__ import annotations

import os
from pathlib import Path

# ``apps/api/paths.py`` is two levels below the repo root:
# ``<repo>/apps/api/paths.py`` -> parents[0] = ``<repo>/apps/api``,
# parents[1] = ``<repo>/apps``, parents[2] = ``<repo>``. This matches
# ``apps/api/__init__.py:49`` exactly so downstream code can use either
# module's ``PROJECT_ROOT`` interchangeably.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

# ``USER_HOME`` defaults to ``~/.prompt-optimizer/``; tests and
# advanced users override via the ``PROMPT_OPTIMIZER_HOME`` env var
# (CONTEXT specifics line 324). ``Path.home()`` is OS-aware so this
# works on macOS / Linux / Windows without branching.
USER_HOME: Path = Path(
    os.environ.get("PROMPT_OPTIMIZER_HOME")
    or (Path.home() / ".prompt-optimizer")
)

# Per-user data files inside ``USER_HOME``.
DB_PATH: Path = USER_HOME / "chat.db"
BLOBS_DIR: Path = USER_HOME / "blobs"
SETTINGS_PATH: Path = USER_HOME / "settings.json"
WORKSPACES_DIR: Path = USER_HOME / "workspaces"

# Repo-relative offline-analysis log (STORE-06). Gitignored by
# ``.gitignore``'s ``.planning/data/`` rule so per-turn routing
# decisions never enter git history.
JSONL_LOG_PATH: Path = PROJECT_ROOT / ".planning" / "data" / "routing_decisions.jsonl"

# Routing-feedback log (D-14). The browser cannot write the
# filesystem, so ``POST /api/v1/feedback`` appends the D-12
# full-context row here (UI-15, D-11..D-14).
#
# Anchored on ``USER_HOME`` (not ``PROJECT_ROOT``) so the
# ``PROMPT_OPTIMIZER_HOME`` env override redirects the feedback log the
# same way it redirects the DB / blobs / settings. ``JSONL_LOG_PATH``
# is repo-relative because the routing-decisions log is a developer
# offline-analysis artifact tied to the checkout; the feedback log is
# per-user runtime data (it travels with the user's home, and tests
# that set ``PROMPT_OPTIMIZER_HOME`` expect the file under that
# override — see ``test_feedback.py::test_feedback_home_override_redirects_file``).
# A ``.planning/data`` subpath is kept so the gitignore rule and the
# D-14 "sibling of routing_decisions" naming both still read true.
FEEDBACK_LOG_PATH: Path = USER_HOME / ".planning" / "data" / "routing_feedback.jsonl"
