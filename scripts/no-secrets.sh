#!/usr/bin/env bash
# SECURE-02 pre-commit hook: block staged content containing what looks like an API key
# or bearer token. The regex set intentionally MATCHES
# apps/api/backends/logging_filter.py::SECRET_PATTERNS (SECURE-01 + SECURE-02 contract).
# Three locked patterns:
#   sk-ant-[A-Za-z0-9_-]{8,}                Anthropic-style keys
#   sk-[A-Za-z0-9_-]{20,}                   OpenAI-style keys (alphabet incl. _-)
#   Bearer[[:space:]]+[A-Za-z0-9_.-]{20,}   Generic bearer tokens (any whitespace)
# The pytest parity test
# apps/api/backends/tests/test_logging_filter.py::test_logging_filter_and_no_secrets_regex_parity
# enforces the equivalence at CI time — do NOT edit one regex set without updating the
# other. See .planning/phases/02-backend-adapters-chatchunk-contract/02-VERIFICATION.md
# CR-04 for the live reproduction (`sk-AAAAA_AAAA…` and `Bearer<tab><key>` previously
# slipped through unblocked).
#
# Match lines being ADDED in staged content (lines starting with `+`, excluding `+++`
# header lines emitted by `git diff`). Use `--diff-filter=AM` so deletions are ignored.
set -euo pipefail

if git diff --cached --diff-filter=AM | \
   grep -E '^\+[^+]' | \
   grep -E '(sk-ant-[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9_-]{20,}|Bearer[[:space:]]+[A-Za-z0-9_.-]{20,})' > /dev/null; then
    echo "ERROR: Staged content contains what looks like an API key or bearer token."
    echo "If this is a false positive, remove the literal and use an env-var reference."
    exit 1
fi
exit 0
