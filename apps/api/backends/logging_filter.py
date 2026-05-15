"""Logging redaction filter — rewrites BYOK secrets out of log records.

Public surface (SECURE-01):

    SECRET_PATTERNS         Ordered list of (compiled regex, replacement)
    RedactionFilter         logging.Filter subclass — mutates record in-place
    install_redaction_filter()  Idempotent install on the root logger

The filter is attached to the ROOT logger so it cascades to every
named logger (Python's logging propagation default). It ALSO attaches
to every existing handler as belt-and-suspenders — handlers that
were configured with their own filter list before the redaction
filter installs would otherwise skip the root's filters.

A subtle but mandatory detail: the filter mutates ``record.msg`` AND
clears ``record.args``. Leaving ``record.args`` populated means the
formatter re-interpolates the original ``%s`` arguments after the
filter has run — re-introducing the raw secret. Pitfall 8 documents
this; the regression test in ``tests/test_logging_filter.py`` enforces
it explicitly with an ``%s``-interpolation log call.

The three patterns intentionally MATCH the pre-commit hook in Plan 04
(``scripts/no-secrets.sh``). Keeping the regex set in sync means the
unit-test coverage for one path also protects the other.

Cross-refs:
    - 02-RESEARCH.md §"Pattern 10" lines 1472-1525 (canonical source)
    - 02-RESEARCH.md §"Pitfall 8" (record.args mandate)
"""

from __future__ import annotations

import logging
import re
from typing import Final

# Ordered: more-specific patterns first so partial overlaps resolve
# predictably. ``sk-ant-…`` is a strict prefix of ``sk-…`` so the
# anthropic-specific replacement must fire first.
SECRET_PATTERNS: Final[list[tuple[re.Pattern[str], str]]] = [
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}"), "***REDACTED-ANTHROPIC***"),
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "***REDACTED-OPENAI***"),
    (re.compile(r"Bearer\s+[A-Za-z0-9_.\-]{20,}"), "Bearer ***REDACTED***"),
]


class RedactionFilter(logging.Filter):
    """``logging.Filter`` that rewrites secret-looking substrings.

    Filters run BEFORE handlers (per Python's logging model), so a
    handler-side leak surface is closed even for handlers that bypass
    the root's standard formatter (e.g. a custom JSON handler).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # ``getMessage`` runs the ``record.msg % record.args``
        # interpolation. Wrapping in try/except prevents formatter bugs
        # from dropping records — defense in depth.
        try:
            msg = record.getMessage()
        except Exception:
            return True

        for pattern, replacement in SECRET_PATTERNS:
            msg = pattern.sub(replacement, msg)

        # Crucial: reset BOTH msg and args. Leaving args populated
        # makes subsequent ``record.getMessage()`` calls re-interpolate
        # the original (unredacted) values — Pitfall 8.
        record.msg = msg
        record.args = ()
        return True


def install_redaction_filter() -> None:
    """Attach a ``RedactionFilter`` to the root logger and every handler.

    Idempotent — a second call is a no-op. Safe to call from
    ``apps/api/__init__.py`` at every process import.
    """

    root = logging.getLogger()
    for existing in root.filters:
        if isinstance(existing, RedactionFilter):
            return
    root.addFilter(RedactionFilter())
    # Belt-and-suspenders: also attach to every existing handler in
    # case a handler was installed without inheriting the root's filter
    # list.
    for handler in root.handlers:
        for existing in handler.filters:
            if isinstance(existing, RedactionFilter):
                break
        else:
            handler.addFilter(RedactionFilter())
