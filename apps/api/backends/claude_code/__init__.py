"""Claude Code adapter package.

Side effects at import:

    1. ``os.environ.setdefault("CLAUDE_ENABLE_STREAM_WATCHDOG", "1")``
       (BACKEND-09 / CONTEXT discretion line 143) — the underlying
       Claude CLI subprocess inherits this var via ``os.environ`` and
       enables its stream-stall watchdog. ``setdefault`` (NOT
       assignment) is critical: operator preference wins. If the user
       set ``CLAUDE_ENABLE_STREAM_WATCHDOG=0`` before launching, this
       module does not overwrite it.

The ``ClaudeCodeAdapter`` re-export is deferred to the Plan 02-02 Task
2 commit — Task 1 ships this ``__init__.py`` without it so the cost /
errors / step_counter / workspace submodules are importable during
the Task 1 RED phase without an unresolved import chain. The Wave 1
OpenRouter plan used the same pattern (Plan 02-01 Decision #4).

Cross-refs:
    - 02-RESEARCH.md §"Pattern 9" lines 1456-1470 (watchdog setdefault)
    - 02-CONTEXT.md discretion line 143 (watchdog install point)
    - BACKEND-09 (subprocess inheritance of CLAUDE_ENABLE_STREAM_WATCHDOG)
"""

from __future__ import annotations

import os

# Subprocess-inherited stream-stall watchdog. setdefault (NOT
# assignment) so an operator-supplied ``CLAUDE_ENABLE_STREAM_WATCHDOG=0``
# is preserved. The Claude CLI subprocess spawned by the SDK reads this
# var from os.environ.
os.environ.setdefault("CLAUDE_ENABLE_STREAM_WATCHDOG", "1")

# NOTE: the adapter re-export lives below in Task 2 of Plan 02-02. The
# Task 1 commit deliberately omits it so this package is importable
# during the RED phase, before adapter.py exists. See Plan 02-01
# Decision #4 for the same precedent in the OpenRouter package.
