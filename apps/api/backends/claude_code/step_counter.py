"""StepCounter — per-iteration step cap for the Claude Code adapter.

Public surface (BACKEND-06, D-15):

    DEFAULT_STEP_CAP    Final[int] = 25      CONTEXT specifics line 261
    StepCounter         increment / exceeded / value / cap

One step = one ``AssistantMessage`` from
``claude_agent_sdk.ClaudeSDKClient.receive_response()`` (D-15). The
adapter ``stream`` method calls ``steps.increment()`` once per
AssistantMessage and ``steps.exceeded()`` once per loop iteration. On
exhaustion the adapter emits ``StreamError(code="step_cap_exceeded",
retriable=False)`` + ``Done`` and calls ``await client.interrupt()``
BEFORE ``break`` (Pitfall 5 cleanup ordering — the SDK closes the
underlying async generator cleanly when interrupted, not when the
caller bare-``break``s out of the loop).

Cross-refs:
    - 02-CONTEXT.md specifics line 261 (DEFAULT_STEP_CAP = 25)
    - 02-CONTEXT.md D-15 (one step = one AssistantMessage)
    - 02-PATTERNS.md "claude_code/step_counter.py" lines 738-761
    - 02-RESEARCH.md §"Pitfall 5" lines 1808-1819 (cleanup ordering)
"""

from __future__ import annotations

import logging
from typing import Final

logger = logging.getLogger(__name__)


# 25 per CONTEXT specifics line 261; D-15 locks the "one step = one
# AssistantMessage" interpretation.
DEFAULT_STEP_CAP: Final[int] = 25


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
