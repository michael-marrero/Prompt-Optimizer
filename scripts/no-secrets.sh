#!/usr/bin/env bash
# SECURE-02 pre-commit hook: block staged content containing what looks like an API key
# or bearer token. The regex is the locked D-09 wording — three patterns:
#   sk-ant-[A-Za-z0-9_-]{8,}     Anthropic-style keys
#   sk-[A-Za-z0-9]{20,}          OpenAI-style keys
#   Bearer [A-Za-z0-9_.-]{20,}   Generic bearer tokens
#
# Match lines being ADDED in staged content (lines starting with `+`, excluding `+++`
# header lines emitted by `git diff`). Use `--diff-filter=AM` so deletions are ignored.
set -euo pipefail

if git diff --cached --diff-filter=AM | \
   grep -E '^\+[^+]' | \
   grep -E '(sk-ant-[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9]{20,}|Bearer [A-Za-z0-9_.-]{20,})' > /dev/null; then
    echo "ERROR: Staged content contains what looks like an API key or bearer token."
    echo "If this is a false positive, remove the literal and use an env-var reference."
    exit 1
fi
exit 0
