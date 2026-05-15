# Plan 02-02 Task 1 — BACKEND-09 watchdog env var regression.
#
# Two invariants:
#   1. After ``import apps.api.backends.claude_code``,
#      ``os.environ['CLAUDE_ENABLE_STREAM_WATCHDOG'] == '1'`` (the
#      side-effect ``os.environ.setdefault`` at package import time).
#   2. ``os.environ.setdefault`` semantics: a pre-existing value is
#      preserved — operator preference wins. If the env var was set to
#      ``'0'`` BEFORE the package import, it remains ``'0'`` after.

from __future__ import annotations

import importlib
import os
import sys


def test_watchdog_env_var_set_after_import() -> None:
    """Importing the package sets ``CLAUDE_ENABLE_STREAM_WATCHDOG=1``.

    The side effect lives in ``apps/api/backends/claude_code/__init__.py``.
    Use ``os.environ.setdefault`` so this never overrides operator
    preference (covered by the second test).
    """

    # Clear any prior assignment and force a fresh import path.
    os.environ.pop("CLAUDE_ENABLE_STREAM_WATCHDOG", None)
    sys.modules.pop("apps.api.backends.claude_code", None)
    import apps.api.backends.claude_code  # noqa: F401 — side-effect import

    assert os.environ.get("CLAUDE_ENABLE_STREAM_WATCHDOG") == "1"


def test_watchdog_env_var_respects_existing_value(monkeypatch) -> None:
    """If the operator pre-sets the env var to ``'0'``, the import does
    not overwrite it (``os.environ.setdefault`` not assignment)."""

    monkeypatch.setenv("CLAUDE_ENABLE_STREAM_WATCHDOG", "0")
    # Re-import the package so the module-level setdefault runs again
    # against the now-existing operator value.
    sys.modules.pop("apps.api.backends.claude_code", None)
    module = importlib.import_module("apps.api.backends.claude_code")
    assert module is not None
    assert os.environ.get("CLAUDE_ENABLE_STREAM_WATCHDOG") == "0"
