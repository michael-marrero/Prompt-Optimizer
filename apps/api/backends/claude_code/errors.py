"""Provider error → StreamError translation for the Claude Code adapter.

Public surface (D-06):

    PROVIDER_ERROR_MAP        {claude_agent_sdk.Exception → (code, retriable)}
    map_provider_error(exc) → (code, message, retriable)

The codes returned MUST come from the closed D-06 vocabulary defined
in ``apps/api/backends/chunks.py``'s ``StreamError.code`` ``Literal``:

    "cost_cap_exceeded", "step_cap_exceeded", "cancelled",
    "rate_limited", "auth_failed", "provider_unavailable",
    "timeout", "validation_error", "internal_error"

The adapter uses this mapping inside its ``except`` blocks to convert
``ProcessError`` / ``ClaudeSDKError`` (and any other exception) into a
closed-vocabulary code + retriable flag for the terminal
``StreamError`` chunk it yields before ``Done``.

Lookup matches on **fully-qualified class name** in addition to
``isinstance`` so the mapping survives ``sys.modules`` deletion-and-
re-import cycles (Phase 1 D-18 guard test deliberately purges
``claude_agent_sdk`` from ``sys.modules`` — afterwards the same
exception class lives at a different object id). Same pattern as
``apps/api/backends/openrouter/errors.py`` (Plan 02-01 Decision #2).

Cross-refs:
    - 02-PATTERNS.md "claude_code/errors.py" lines 765-770 (canonical shape)
    - apps/api/backends/openrouter/errors.py (parallel implementation)
    - apps/api/backends/chunks.py (StreamError.code Literal)
"""

from __future__ import annotations

# Defensive SDK import — when the optional dependency is absent (e.g.
# tooling environments that only import the fakes), fall back to the
# Exception base so the module is still loadable. The adapter itself
# imports ``ProcessError`` and ``ClaudeSDKError`` directly and will
# raise ``ImportError`` if the SDK is missing — that surface area is
# already covered.
try:
    from claude_agent_sdk import ClaudeSDKError, ProcessError  # type: ignore
except ImportError:  # pragma: no cover — tests run with the SDK installed.
    class ClaudeSDKError(Exception):  # type: ignore
        pass

    class ProcessError(ClaudeSDKError):  # type: ignore
        pass


# Order matters: more specific subclasses BEFORE the generic base so
# the iteration sees them first.
PROVIDER_ERROR_MAP: dict[type[BaseException], tuple[str, bool]] = {
    ProcessError: ("provider_unavailable", False),
    ClaudeSDKError: ("internal_error", False),
}


def map_provider_error(exc: BaseException) -> tuple[str, str, bool]:
    """Return ``(code, message, retriable)`` for any claude-agent-sdk exception.

    Unrecognised exception classes fall back to ``("internal_error",
    str(exc), False)`` so the adapter still emits a valid
    ``StreamError`` chunk.
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
