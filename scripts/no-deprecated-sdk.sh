#!/usr/bin/env bash
# OSS-06 pre-commit hook: block any re-introduction of the deprecated `claude-code-sdk`
# package. The canonical Phase 2 SDK is `claude_agent_sdk` (Anthropic renamed the
# package in November 2025). Catches contributors who add the wrong import OR
# accidentally bring it back via `uv add claude-code-sdk` (uv.lock check).
set -euo pipefail

# Check 1: staged content (covers .py source).
# Two-step pipeline mirrors no-secrets.sh: first grep filters to ADDED lines
# (excluding `+++` headers via [^+]), second grep scans those lines for the
# forbidden patterns. The pattern is anchored to the line body, not the diff
# prefix, because a single-regex combination with `^\+[^+].*pattern` cannot
# match `+import ...` — the leading `[^+]` consumes the `i` of `import` and
# `.*` cannot backtrack across it (Rule 1 fix vs RESEARCH Pattern 11 line 1607).
if git diff --cached --diff-filter=AM | \
   grep -E '^\+[^+]' | \
   grep -E '(import claude_code_sdk|from claude_code_sdk|"claude-code-sdk")' > /dev/null; then
    echo "ERROR: Use 'claude_agent_sdk' (NOT the deprecated 'claude-code-sdk')."
    echo "See OSS-06 in .planning/REQUIREMENTS.md."
    exit 1
fi

# Check 2: lockfile — D-09 says: catch contributors who add the dep accidentally.
if [ -f uv.lock ] && grep -q '"claude-code-sdk"' uv.lock; then
    echo "ERROR: 'claude-code-sdk' found in uv.lock. Remove the dep and re-lock."
    exit 1
fi
exit 0
