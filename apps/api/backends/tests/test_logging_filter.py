# Plan 00 Task 3 — SECURE-01 RedactionFilter regression tests (Pitfall 8).
#
# Test contracts:
#   - sk-ant-… is rewritten to ***REDACTED-ANTHROPIC***.
#   - sk-… (non-ant) is rewritten to ***REDACTED-OPENAI***.
#   - Bearer <token> is rewritten to "Bearer ***REDACTED***".
#   - record.args = () clear is exercised by logging with %s
#     interpolation; otherwise the formatter would re-interpolate the
#     raw key from args after the filter cleared record.msg.
#   - install_redaction_filter() is idempotent — calling twice attaches
#     exactly one RedactionFilter to the root logger.

from __future__ import annotations

import logging


def test_redaction_replaces_anthropic_keys(caplog) -> None:
    from apps.api.backends.logging_filter import install_redaction_filter

    install_redaction_filter()
    logger = logging.getLogger("test.anthropic")
    with caplog.at_level(logging.INFO, logger="test.anthropic"):
        logger.info(
            "auth header: Bearer sk-ant-api03-XYZ1234567890ABCDEFGHIJKL"
        )
    assert "sk-ant-" not in caplog.text
    assert "***REDACTED-ANTHROPIC***" in caplog.text


def test_redaction_replaces_openai_keys(caplog) -> None:
    from apps.api.backends.logging_filter import install_redaction_filter

    install_redaction_filter()
    logger = logging.getLogger("test.openai")
    with caplog.at_level(logging.INFO, logger="test.openai"):
        logger.info("api key: sk-proj-abcdefghijklmnopqrstuvwxyz0123")
    assert "sk-proj-" not in caplog.text
    assert "***REDACTED-OPENAI***" in caplog.text


def test_redaction_replaces_bearer_tokens(caplog) -> None:
    from apps.api.backends.logging_filter import install_redaction_filter

    install_redaction_filter()
    logger = logging.getLogger("test.bearer")
    with caplog.at_level(logging.INFO, logger="test.bearer"):
        # Use a Bearer payload that does NOT start with sk- so the
        # Bearer pattern (rather than the sk- pattern) is the one
        # exercised here.
        logger.info("auth: Bearer abcdefghijklmnopqrstuvwxyz0123ABCDEF")
    assert "abcdefghijklmnopqrstuvwxyz0123ABCDEF" not in caplog.text
    assert "Bearer ***REDACTED***" in caplog.text


def test_redaction_handles_args_interpolation(caplog) -> None:
    """Pitfall 8: record.args must be cleared so the formatter does
    not re-interpolate the raw key after record.msg has been replaced."""

    from apps.api.backends.logging_filter import install_redaction_filter

    install_redaction_filter()
    logger = logging.getLogger("test.args")
    with caplog.at_level(logging.INFO, logger="test.args"):
        logger.info(
            "key=%s url=%s",
            "sk-proj-abcdefghijklmnopqrstuvwxyz0123",
            "https://api.example.com",
        )
    assert "sk-proj-" not in caplog.text
    assert "***REDACTED-OPENAI***" in caplog.text


def test_install_redaction_filter_is_idempotent() -> None:
    from apps.api.backends.logging_filter import (
        RedactionFilter,
        install_redaction_filter,
    )

    install_redaction_filter()
    install_redaction_filter()
    install_redaction_filter()
    root = logging.getLogger()
    redaction_filters = [
        f for f in root.filters if isinstance(f, RedactionFilter)
    ]
    assert len(redaction_filters) == 1


def test_redaction_does_not_drop_clean_log_lines(caplog) -> None:
    """Smoke test: a message with no secret content is preserved
    verbatim (modulo record.args clearing, which is internal)."""

    from apps.api.backends.logging_filter import install_redaction_filter

    install_redaction_filter()
    logger = logging.getLogger("test.clean")
    with caplog.at_level(logging.INFO, logger="test.clean"):
        logger.info("system is healthy")
    assert "system is healthy" in caplog.text


def test_secret_patterns_count() -> None:
    """Defensive lock: exactly 3 patterns are registered."""

    from apps.api.backends.logging_filter import SECRET_PATTERNS

    assert len(SECRET_PATTERNS) == 3
