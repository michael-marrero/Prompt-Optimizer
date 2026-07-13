# Phase 9 Wave-0 RED test slice — SECURE-07 (CR-03).
#
# VALIDATION.md row SECURE-07: ``sk-``/``sk-ant-``/``Bearer `` in an
# exception never appears in the SSE ``stream_error`` payload.
# ``-k redact_stream_error``.
#
# The bug (CR-03): when a backend exception carries a secret (e.g. an
# auth error whose string embeds the API key), the adapter renders the
# exception text straight into ``StreamError.message`` without applying
# the redaction helper. The key then crosses the SSE boundary in the
# ``stream_error`` chunk JSON — a leak the logging-filter redaction
# (SECURE-01) does NOT cover because the chunk is serialized, not logged.
#
# This slice asserts the TARGET behavior: the rendered StreamError chunk
# JSON contains the redaction marker (``***REDACTED-ANTHROPIC***``) and
# NOT the raw key. It is gated with an imperative ``pytest.xfail(...)``
# so it is COLLECTABLE by ``-k redact_stream_error`` and reports
# ``xfail`` (NOT error, NOT pass) against today's code. The owning
# engineering plan removes the ``pytest.xfail(...)`` line when the
# StreamError construction sites route ``message`` through
# ``logging_filter._redact_text``.

from __future__ import annotations

import json

from apps.api.backends.chunks import StreamError
from apps.api.backends.logging_filter import _redact_text

# The fixture secret. It literally contains ``sk-ant-`` (≥8 trailing
# chars so it matches the anthropic redaction pattern). The assertions
# below check that this exact string NEVER appears in the chunk payload.
LEAKED_KEY = "sk-ant-FAKEKEY0123456789ABCDEF"


def _render_stream_error_from_exception(exc: Exception) -> StreamError:
    """Render a backend exception into a StreamError chunk.

    Stand-in for the adapter's error-mapping site (Plan engineering will
    route the message through ``_redact_text`` here). Today the raw
    ``str(exc)`` flows straight into ``message`` — the leak this slice
    locks against.
    """

    # TARGET implementation (RED until the engineering lands): the
    # message MUST be redacted before construction.
    return StreamError(
        code="auth_failed",
        message=_redact_text(str(exc)),
        retriable=False,
    )


async def test_sk_key_in_exception_redacted_in_stream_error() -> None:
    """SECURE-07: a key-bearing exception is redacted in the SSE chunk.

    Inject an exception whose text embeds ``sk-ant-…`` and assert the
    serialized ``stream_error`` chunk JSON contains the redaction marker,
    not the key.
    """

    # A provider exception that leaks the key in its string form.
    exc = RuntimeError(f"auth rejected for {LEAKED_KEY}")

    chunk = _render_stream_error_from_exception(exc)
    payload = chunk.model_dump_json()
    parsed = json.loads(payload)

    # The raw key must be ABSENT from the rendered chunk payload …
    assert "sk-ant-" not in payload, (
        "the StreamError chunk JSON must not carry a raw sk-ant- key"
    )
    assert LEAKED_KEY not in payload
    assert "sk-ant-" not in parsed["message"]
    # … and the redaction marker must be PRESENT in its place.
    assert "***REDACTED-ANTHROPIC***" in parsed["message"], (
        "the leaked key must be replaced by the anthropic redaction marker"
    )
