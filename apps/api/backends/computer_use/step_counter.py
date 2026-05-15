"""StepCounter — per-iteration step cap for the computer-use adapter.

Public surface (BACKEND-06, D-15):

    DEFAULT_STEP_CAP    Final[int] = 15      CONTEXT specifics line 261
    StepCounter         increment / exceeded / value / cap

One step = one agent-loop iteration (D-15). The adapter ``stream``
method calls ``steps.increment()`` once per iteration and
``steps.exceeded()`` once at the top of each iteration. On exhaustion
the adapter emits ``StreamError(code="step_cap_exceeded",
retriable=False)`` + ``Done`` and ``break``s the agent loop.

Computer-use's cap (15) is tighter than Claude Code's (25) because
computer-use iterations are more expensive — each iteration involves
both a model call AND a screenshot encoding (D-15 cost rationale).

This is a SIBLING module to ``apps.api.backends.claude_code.step_counter``
per D-08: do NOT import from claude_code. The two modules diverge ONLY in
the value of ``DEFAULT_STEP_CAP``; the class shape is intentionally
identical so a future plan can promote it to a shared module if needed.

Cross-refs:
    - 02-CONTEXT.md specifics line 261 (DEFAULT_STEP_CAP = 15)
    - 02-CONTEXT.md D-15 (one step = one agent-loop iteration)
    - 02-PATTERNS.md "computer_use/step_counter.py" (sibling of claude_code)
    - apps/api/backends/claude_code/step_counter.py (parallel implementation)
"""

from __future__ import annotations

import logging
from typing import Final

logger = logging.getLogger(__name__)


# 15 per CONTEXT specifics line 261; D-15 locks "one step = one
# agent-loop iteration". Tighter than Claude Code's 25 because
# computer-use iterations include both a model call and a screenshot.
DEFAULT_STEP_CAP: Final[int] = 15


class StepCounter:
    """Bounded counter — value reaches but never exceeds ``cap``.

    ``increment`` returns the post-increment value; ``exceeded`` is True
    once value is at or above the cap. Initial state is value=0,
    exceeded=False.
    """

    def __init__(self, cap: int = DEFAULT_STEP_CAP) -> None:
        # Defensive: a non-positive cap means "no cap" semantically;
        # but the SDK / adapter never passes that. Coerce to at least 1
        # so ``exceeded`` is well-defined.
        if cap < 1:
            cap = 1
        self._cap = cap
        self._value = 0

    def increment(self) -> int:
        """Add 1 to the step counter and return the new value."""

        self._value += 1
        return self._value

    def exceeded(self) -> bool:
        """True once the step counter has met or surpassed the cap."""

        return self._value >= self._cap

    @property
    def value(self) -> int:
        """Current step count (post-construction = 0; monotonically nondecreasing)."""

        return self._value

    @property
    def cap(self) -> int:
        """Configured step cap (immutable post-construction)."""

        return self._cap
