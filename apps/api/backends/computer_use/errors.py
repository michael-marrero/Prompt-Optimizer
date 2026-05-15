"""Provider error → StreamError translation for the computer-use adapter.

Public surface (D-06):

    PROVIDER_ERROR_MAP        {anthropic.Exception → (code, retriable)}
    map_provider_error(exc) → (code, message, retriable)

The codes returned MUST come from the closed D-06 vocabulary defined
in ``apps/api/backends/chunks.py``'s ``StreamError.code`` ``Literal``:

    "cost_cap_exceeded", "step_cap_exceeded", "cancelled",
    "rate_limited", "auth_failed", "provider_unavailable",
    "timeout", "validation_error", "internal_error"

The adapter uses this mapping inside its ``except`` blocks to convert
``anthropic.AuthenticationError`` / ``anthropic.RateLimitError`` /
``anthropic.APITimeoutError`` / ``anthropic.APIStatusError`` (and any
other exception) into a closed-vocabulary code + retriable flag for the
terminal ``StreamError`` chunk it yields before ``Done``.

The adapter REFINES ``APIStatusError`` further: a 429 maps to
``"rate_limited"`` (retriable) while everything else maps to
``"provider_unavailable"`` (retriable). The base map below treats
``APIStatusError`` as ``"provider_unavailable"`` — the adapter's
``except APIStatusError`` block branches on ``exc.status_code`` per
RESEARCH Pattern 5 line 1093.

Lookup matches on **fully-qualified class name** in addition to
``isinstance`` so the mapping survives ``sys.modules`` deletion-and-
re-import cycles (Phase 1 D-18 guard test deliberately purges
``anthropic`` from ``sys.modules`` — afterwards the same exception
class lives at a different object id). Same pattern as
``apps/api/backends/openrouter/errors.py`` and
``apps/api/backends/claude_code/errors.py``.

Cross-refs:
    - 02-RESEARCH.md §"Pattern 5" lines 1086-1099 (mapping rationale)
    - 02-PATTERNS.md "computer_use/errors.py" (parallel to openrouter)
    - apps/api/backends/openrouter/errors.py (parallel implementation)
    - apps/api/backends/chunks.py (StreamError.code Literal)
"""

from __future__ import annotations

import anthropic


# Order matters: ``isinstance`` walks the dict in insertion order, and
# the first match wins. We list the more specific subclasses
# (AuthenticationError, RateLimitError, APITimeoutError) BEFORE the
# generic APIStatusError so a 401 is mapped to ``auth_failed`` rather
# than ``provider_unavailable``.
PROVIDER_ERROR_MAP: dict[type[BaseException], tuple[str, bool]] = {
    anthropic.AuthenticationError: ("auth_failed", False),
    anthropic.RateLimitError: ("rate_limited", True),
    anthropic.APITimeoutError: ("timeout", True),
    anthropic.APIStatusError: ("provider_unavailable", True),
}


def map_provider_error(exc: BaseException) -> tuple[str, str, bool]:
    """Return ``(code, message, retriable)`` for any anthropic exception.

    Unrecognised exception classes (any subclass not in
    ``PROVIDER_ERROR_MAP``) fall back to ``("internal_error", str(exc),
    False)`` so the adapter still emits a valid ``StreamError``.

    The lookup matches on **fully-qualified class name** in addition to
    object identity so the mapping survives ``sys.modules`` deletion-
    and-re-import cycles (e.g. the Phase 1 D-18 guard test deliberately
    purges ``anthropic`` from ``sys.modules`` to verify the routing
    brain has no transitive HTTP / SDK import — afterwards the same
    exception class lives at a different object id, so a naive
    ``isinstance`` against the import-time entry returns False).
    """

    exc_class_names = {
        f"{cls.__module__}.{cls.__qualname__}"
        for cls in type(exc).__mro__
    }
    for exc_class, (code, retriable) in PROVIDER_ERROR_MAP.items():
        canonical_name = f"{exc_class.__module__}.{exc_class.__qualname__}"
        if isinstance(exc, exc_class) or canonical_name in exc_class_names:
            return code, str(exc), retriable
    return "internal_error", str(exc), False
