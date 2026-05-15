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
        # No Bearer prefix — exercise the sk-ant- branch directly.
        # After the CR-05 reorder (Bearer pattern FIRST), a Bearer-
        # prefixed sk-ant-... rewrites to `Bearer ***REDACTED***`
        # rather than `***REDACTED-ANTHROPIC***`; see
        # test_bearer_prefixed_sk_ant_redacts_as_bearer_unit for that
        # branch.
        logger.info(
            "api auth: sk-ant-api03-XYZ1234567890ABCDEFGHIJKL"
        )
    assert "sk-ant-" not in caplog.text
    assert "***REDACTED-ANTHROPIC***" in caplog.text


def test_bearer_prefixed_sk_ant_redacts_as_bearer_unit(caplog) -> None:
    """CR-05 regression: canonical Authorization: Bearer sk-ant-…
    form MUST redact to `Bearer ***REDACTED***` as a single unit,
    NOT `Bearer ***REDACTED-ANTHROPIC***`. Downstream scrubbers
    anchor on the former."""

    from apps.api.backends.logging_filter import install_redaction_filter

    install_redaction_filter()
    logger = logging.getLogger("test.bearer_anthropic")
    with caplog.at_level(logging.INFO, logger="test.bearer_anthropic"):
        logger.info(
            "Authorization: Bearer sk-ant-api03-XYZ1234567890ABCDEFGHIJKL"
        )
    # The key is gone.
    assert "sk-ant-api03-XYZ" not in caplog.text
    # The Bearer-branch marker landed.
    assert "Bearer ***REDACTED***" in caplog.text
    # The anthropic-branch marker did NOT land — Bearer wraps the
    # whole substring.
    assert "***REDACTED-ANTHROPIC***" not in caplog.text
    # No raw "Bearer " literal followed by an anthropic marker.
    assert "Bearer ***REDACTED-ANTHROPIC***" not in caplog.text


def test_logging_filter_and_no_secrets_regex_parity() -> None:
    """SECURE-01 + SECURE-02 contract: the runtime SECRET_PATTERNS
    and the pre-commit hook regex set in scripts/no-secrets.sh
    encode the same three pattern alphabets. Drift here defeats
    one of the two controls — see VERIFICATION.md CR-04 for the
    live reproduction."""

    from pathlib import Path
    import re as _re

    from apps.api.backends.logging_filter import SECRET_PATTERNS

    # 4 ups: apps/api/backends/tests/test_logging_filter.py
    #        -> repo root.
    repo_root = Path(__file__).resolve().parents[4]
    script_path = repo_root / "scripts" / "no-secrets.sh"
    script_src = script_path.read_text(encoding="utf-8")

    # Find the second `grep -E` body (the pattern-match grep,
    # not the diff-header filter). The alternation lives between
    # the outermost `(` and `)` on that line.
    match = _re.search(
        r"grep -E '\((?P<body>[^']+)\)'",
        script_src,
    )
    assert match is not None, (
        "Could not locate the grep -E pattern in scripts/no-secrets.sh — "
        "did the script layout change?"
    )
    shell_alternation = match.group("body")
    shell_subpatterns = shell_alternation.split("|")
    assert len(shell_subpatterns) == 3, (
        f"Expected 3 sub-patterns in shell regex; got "
        f"{len(shell_subpatterns)}: {shell_subpatterns!r}"
    )

    # Translate bash POSIX `[[:space:]]+` -> python `\s+` so the
    # tokens are directly comparable.
    shell_subpatterns = [
        sp.replace("[[:space:]]+", r"\s+") for sp in shell_subpatterns
    ]

    python_patterns = [p.pattern for (p, _r) in SECRET_PATTERNS]

    for shell_sp in shell_subpatterns:
        # Each shell sub-pattern MUST appear verbatim as a
        # substring of one of the SECRET_PATTERNS source
        # strings (allowing for the python-side `\.` vs bash-
        # side `.` escape difference, which we normalise).
        normalised = shell_sp.replace(r".-", r".\-")
        if not any(
            shell_sp in py or normalised in py
            for py in python_patterns
        ):
            raise AssertionError(
                "scripts/no-secrets.sh contains pattern "
                f"{shell_sp!r} which is NOT present in "
                f"logging_filter.SECRET_PATTERNS "
                f"{python_patterns!r}. The two regex sets must "
                "remain synchronised — see "
                ".planning/phases/02-backend-adapters-"
                "chatchunk-contract/02-VERIFICATION.md CR-04."
            )


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
