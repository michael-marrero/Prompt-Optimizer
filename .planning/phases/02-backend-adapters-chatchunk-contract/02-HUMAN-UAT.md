---
status: partial
phase: 02-backend-adapters-chatchunk-contract
source: [02-VERIFICATION.md]
started: 2026-05-15T21:50:00Z
updated: 2026-05-15T21:50:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. End-to-end OpenRouter live smoke against the real API
expected: `OPENROUTER_API_KEY=… uv run pytest -m live apps/api/backends/openrouter/tests/test_live.py -x` produces at least one TextDelta and a terminal Done with `cost_usd > 0`. BACKEND-03 / ROADMAP SC #1.
result: [pending]

### 2. End-to-end Claude Code live smoke (build hello.py in tmp workspace)
expected: `ANTHROPIC_API_KEY=… uv run pytest -m live apps/api/backends/claude_code/tests/test_live.py -x` produces at least one FileDiff and a terminal Done with `total_cost_usd > 0`. BACKEND-04 / ROADMAP SC #1. Plan 02-05 (CR-01) closure makes this branch reachable in production for the first time — this is the canonical live confirmation.
result: [pending]

### 3. End-to-end computer-use live smoke (navigate https://example.com)
expected: `COMPUTER_USE_OPT_IN=1 ANTHROPIC_API_KEY=… uv run pytest -m live apps/api/backends/computer_use/tests/test_live.py -x` produces at least one Screenshot and a ToolCall and a terminal Done with `cost_usd > 0`. BACKEND-05 / ROADMAP SC #1.
result: [pending]

### 4. Pre-commit deliberate-paste live block (refresh after CR-04 closure)
expected: Three staged-secret reproductions are now BLOCKED end-to-end via the real `git commit` flow: (a) `sk-ant-AAAAAAAAAAAAAAAAAAAA`, (b) `sk-AAAAA_AAAAAAAAAAAAAAAAAA` (CR-04 underscore-bearing OpenAI), (c) `Bearer\t<token>` (CR-04 tab-separated header). SECURE-02. Plan 02-07 (CR-04) SUMMARY records the bash-level outcomes; this human-verification item confirms the full pre-commit hook still wires through.
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
