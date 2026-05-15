"""Provider error -> StreamError translation for the OpenRouter adapter.

Public surface (D-06):

    PROVIDER_ERROR_MAP    {openai.Exception -> (code, retriable)}
    map_provider_error(exc) -> (code, message, retriable)

The codes returned MUST come from the closed D-06 vocabulary defined in
``apps/api/backends/chunks.py``'s ``StreamError.code`` ``Literal``:

    "cost_cap_exceeded", "step_cap_exceeded", "cancelled", "rate_limited",
    "auth_failed", "provider_unavailable", "timeout", "validation_error",
    "internal_error"

The adapter uses this mapping inside its ``except`` blocks to convert
``openai.AuthenticationError`` / ``openai.RateLimitError`` /
``openai.APITimeoutError`` / ``openai.APIStatusError`` (and anything
else) into the right closed-vocabulary code + retriable flag for the
terminal ``StreamError`` chunk it yields before ``Done``.

Cross-refs:
    - 02-PATTERNS.md "openrouter/errors.py" lines 612-633 (canonical shape)
    - apps/api/backends/chunks.py (StreamError.code Literal)
"""

from __future__ import annotations

import openai

# Order matters: ``isinstance`` walks the dict in insertion order, and
# the first match wins. We list the more specific subclasses
# (AuthenticationError, RateLimitError, APITimeoutError) BEFORE the
# generic APIStatusError so a 401 is mapped to ``auth_failed`` rather
# than ``provider_unavailable``.
PROVIDER_ERROR_MAP: dict[type[Exception], tuple[str, bool]] = {
    openai.AuthenticationError: ("auth_failed", False),
    openai.RateLimitError: ("rate_limited", True),
    openai.APITimeoutError: ("timeout", True),
    openai.APIStatusError: ("provider_unavailable", True),
}


def map_provider_error(exc: Exception) -> tuple[str, str, bool]:
    """Return ``(code, message, retriable)`` for any ``openai.*`` exception.

    Unrecognised exception classes (any subclass not in
    ``PROVIDER_ERROR_MAP``) fall back to ``("internal_error", str(exc),
    False)`` so the adapter still emits a valid ``StreamError``.

    The lookup matches on **fully-qualified class name** rather than
    object identity so the mapping survives ``sys.modules`` deletion-
    and-re-import cycles (e.g. the Phase 1 D-18 guard test deliberately
    purges ``openai`` from ``sys.modules`` to verify the routing brain
    has no transitive HTTP / SDK import — afterwards the same exception
    class lives at a different object id, so a naive ``isinstance``
    against the import-time entry returns False).
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
