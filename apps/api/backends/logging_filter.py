"""Logging redaction filter — rewrites BYOK secrets out of log records.

Public surface (SECURE-01):

    SECRET_PATTERNS         Ordered list of (compiled regex, replacement)
    RedactionFilter         logging.Filter subclass — mutates record in-place
    install_redaction_filter()  Idempotent install on the root logger
                              + record factory hook

The redaction runs on every ``LogRecord`` at CREATION time via
``logging.setLogRecordFactory``. This is more defensive than the
``Filter``-on-root-logger approach RESEARCH Pattern 10 originally
sketched: in Python's logging model, filters attached to a logger
are NOT consulted when a child logger's record propagates upward to a
parent handler (only the handler's own filter list runs). A redaction
filter installed only on the root logger therefore misses any record
that propagates from a named logger to a parent's handler — including
the handler pytest's ``caplog`` fixture installs. Mutating the record
at creation time eliminates that gap and also covers the handler-side
``Filter`` we still attach to the root logger and its handlers, which
acts as belt-and-suspenders for code paths that instantiate
``LogRecord`` directly.

Pitfall 8 still applies: after mutating ``record.msg``, ``record.args``
MUST be cleared so any subsequent ``record.getMessage()`` call does
not re-interpolate the original (unredacted) ``%s`` arguments. Both
the factory and the ``RedactionFilter`` do this.

The three patterns intentionally MATCH the pre-commit hook in Plan 04
(``scripts/no-secrets.sh``). Keeping the regex set in sync means the
unit-test coverage for one path also protects the other.

Cross-refs:
    - 02-RESEARCH.md §"Pattern 10" lines 1472-1525 (original recipe)
    - 02-RESEARCH.md §"Pitfall 8" (record.args mandate)
    - Plan 00 Task 3 deviation note: factory hook supplements the
      filter so caplog-based regression tests assert the right
      behavior contract.
"""

from __future__ import annotations

import logging
from typing import Final
import re

# Ordered: more-specific patterns first so partial overlaps resolve
# predictably. ``sk-ant-…`` is a strict prefix of ``sk-…`` so the
# anthropic-specific replacement must fire first.
SECRET_PATTERNS: Final[list[tuple[re.Pattern[str], str]]] = [
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}"), "***REDACTED-ANTHROPIC***"),
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "***REDACTED-OPENAI***"),
    (re.compile(r"Bearer\s+[A-Za-z0-9_.\-]{20,}"), "Bearer ***REDACTED***"),
]


def _redact_text(text: str) -> str:
    """Apply every SECRET_PATTERN substitution in order."""

    for pattern, replacement in SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class RedactionFilter(logging.Filter):
    """``logging.Filter`` that rewrites secret-looking substrings.

    Defensive layer (belt-and-suspenders) on top of the record factory
    installed by ``install_redaction_filter``. This filter still runs
    when a handler explicitly attaches it, catching any record that
    bypassed the factory (e.g. a ``LogRecord`` instantiated directly
    by third-party code that does not go through
    ``logging.getLogger(...).info(...)``).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True

        msg = _redact_text(msg)

        # Pitfall 8: reset BOTH msg and args.
        record.msg = msg
        record.args = ()
        return True


# Module-level guard so installs are idempotent across re-imports.
_RECORD_FACTORY_INSTALLED = False
_ORIGINAL_FACTORY = logging.getLogRecordFactory()


def _redacting_factory(*args, **kwargs) -> logging.LogRecord:
    """Wrap the underlying factory to redact ``msg`` at creation time."""

    record = _ORIGINAL_FACTORY(*args, **kwargs)
    try:
        msg = record.getMessage()
    except Exception:
        return record
    redacted = _redact_text(msg)
    if redacted != msg or record.args:
        record.msg = redacted
        record.args = ()
    return record


def install_redaction_filter() -> None:
    """Attach the redaction filter + record factory hook.

    Idempotent — a second call is a no-op. Safe to call from
    ``apps/api/__init__.py`` at every process import.
    """

    global _RECORD_FACTORY_INSTALLED

    # 1. Record-factory hook (defense in depth): every new LogRecord
    #    is redacted at creation, regardless of which handler later
    #    emits it (or which filters that handler runs).
    if not _RECORD_FACTORY_INSTALLED:
        logging.setLogRecordFactory(_redacting_factory)
        _RECORD_FACTORY_INSTALLED = True

    # 2. Root-logger filter (legacy belt-and-suspenders): kept so the
    #    test contract `len(root.filters where isinstance Redaction) == 1`
    #    still holds and so callers that bypass logging.getLogger()
    #    (e.g. direct LogRecord construction) still hit the filter.
    root = logging.getLogger()
    for existing in root.filters:
        if isinstance(existing, RedactionFilter):
            return
    root.addFilter(RedactionFilter())
    for handler in root.handlers:
        for existing in handler.filters:
            if isinstance(existing, RedactionFilter):
                break
        else:
            handler.addFilter(RedactionFilter())
