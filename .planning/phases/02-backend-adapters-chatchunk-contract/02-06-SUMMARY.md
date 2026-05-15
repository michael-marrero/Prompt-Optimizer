---
phase: 02
plan: 06
subsystem: backend-adapters
gap_closure: true
tags: [computer-use, cost-tracker, arithmetic-fix, cost-cap, regression, gap-closure, cr-02]
dependency_graph:
  requires:
    - "02-03 Plan SUMMARY — Computer-use adapter foundation (ComputerUseAdapter + ComputerUseCostTracker + agent loop + cost-cap arithmetic)"
    - "02-00 Plan SUMMARY — CostTracker base class with override semantics contract (apps/api/backends/cost.py)"
    - "config/pricing.json — _default + claude-opus-4-7 rate rows that drive the cap arithmetic"
  provides:
    - "apps.api.backends.computer_use.cost.ComputerUseCostTracker.record_iteration_usage — corrected to OVERRIDE (=) _tokens_in / _tokens_out, matching its docstring contract and the parallel OpenRouterCostTracker.record_final_usage / ClaudeCodeCostTracker.record_result patterns"
    - "apps.api.backends.computer_use.tests.test_adapter.test_record_iteration_usage_overrides_running_estimate — regression test that fails closed if the override semantics are ever undone"
  affects:
    - "BACKEND-06 — per-turn USD cap arithmetic is now correct; Done.tokens_out reflects authoritative provider numbers (not inflated by per-event text_delta estimates)"
    - "ROADMAP Success Criterion #2 — cap arithmetic correctness restored; operator-set $0.50 default cap fires at the right cost, not 1.5×–2× early"
    - "SECURE-04 adjacency — the cap is the denial-of-service control for runaway computer-use agents; the bug fix prevents false-positive cap fires AND prevents downstream cost-report inflation"
    - "02-VERIFICATION.md Truth 22 (CR-02) — flips from FAILED (gaps_found) to VERIFIED"
tech_stack:
  added: []
  patterns:
    - "Override-vs-accumulate discipline for provider-authoritative usage: when the SDK emits a final, single source of truth (Anthropic's stream.get_final_message().usage block; OpenRouter's stream_options.include_usage chunk; claude-agent-sdk's ResultMessage.total_cost_usd), the per-event pre-flight estimator MUST be REPLACED, not added to. Mixing `+=` with a value designed to be the authoritative truth produces a sum that is meaningless (estimate + truth)."
    - "Counter-purpose audit: in the same dataclass, some counters can be running totals (cache counters: visibility across iterations) while others MUST be single-iteration overrides (input/output tokens: authoritative billing). Mark the contrast explicitly in the docstring so future maintainers don't homogenize the assignment style."
    - "Single-character regression class: this whole gap was two `+=` → `=` edits. The regression test for it is correspondingly simple — a non-async unit test against the cost tracker class itself, no adapter or async machinery needed. Match the test surface to the bug surface."
key_files:
  created: []
  modified:
    - "apps/api/backends/computer_use/cost.py"
    - "apps/api/backends/computer_use/tests/test_adapter.py"
decisions:
  - "Two-character literal edit, exactly as VERIFICATION.md CR-02 missing item 1 demanded: `self._tokens_in += int(input_tokens)` → `self._tokens_in = int(input_tokens)` and the same for `_tokens_out`. No structural refactor — the bug is purely an assignment-operator typo against the documented contract."
  - "Cache counters (`_cache_read_total` / `_cache_write_total`) PRESERVED as `+=`. The docstring at lines 78–84 explicitly says cache numbers are 'tracked separately ... not currently used to scale the cost calculation' (RESEARCH Open Question 2/3). They are visibility-only running totals across iterations of a session-level cache resource — changing them to `=` would lose multi-iteration cache statistics. The plan explicitly forbade touching them."
  - "Docstring tightened in the same commit to make the contrast explicit: 'Replaces (not accumulates) the running input_tokens / output_tokens tally ... Mirrors the override semantics in OpenRouterCostTracker.record_final_usage and ClaudeCodeCostTracker.record_result. Cache counters accumulate across iterations because the cache is a session-level resource.' This is the kind of comment that prevents the same bug from being re-introduced by a future maintainer 'cleaning up' the inconsistency."
  - "RED gate landed first (commit 43b40ab) — regression test asserts `tokens_out() == 5`, not the buggy `15`. Confirmed to fail on the buggy adapter (the test output captured `assert 15 == 5` on AssertionError). GREEN landed in commit a95617a; same test now passes. TDD discipline matched the parallel Plan 02-05 (CR-01 gap closure) cadence."
  - "Regression test built against the cost tracker class IN ISOLATION — no adapter, no fake provider, no event-loop machinery. The cost tracker is a pure synchronous class; an async test would have added 50+ lines of fixture setup for a 2-line bug. Mirrors VERIFICATION.md's own reproduction recipe verbatim ('text=\"x\"*40 then record_iteration_usage(input_tokens=10, output_tokens=5), assert tokens_in == 10 and tokens_out == 5')."
  - "Test placed at the end of test_adapter.py (after T18 'iteration usage recorded') even though it is non-async. The acceptance criterion in the plan called out that location specifically; matching it keeps the file's per-test comment-banner pattern coherent and keeps the CR-02 regression visible right alongside the T18 cap-arithmetic happy-path test it complements."
metrics:
  duration_minutes: 5
  task_count: 1
  files_modified: 2
  files_created: 0
  tests_added: 1
  tests_modified: 0
  commits: 2
  completed_date: "2026-05-15"
---

# Phase 02 Plan 06: ComputerUseCostTracker Override Arithmetic Summary

One-liner: Closes CR-02 — `ComputerUseCostTracker.record_iteration_usage` now OVERRIDES (`=`) the running token tally instead of accumulating (`+=`), restoring ROADMAP SC #2 cap arithmetic correctness. Parallel to OpenRouter and Claude Code trackers.

## Outcome

`ComputerUseCostTracker.record_iteration_usage` was documented at line 105 as "Override the running estimate with provider-reported usage" but its implementation summed (`+=`) the per-event `record_output_text` char/4 estimate with the authoritative Anthropic `stream.get_final_message().usage` block. Net effect: `Done.tokens_out` inflated by the estimate, and the `over_cap()` arithmetic that drives `cost_cap_exceeded` short-circuit decisions fired too early relative to the operator-set per-turn USD cap (default $0.50).

Two `+=` → `=` edits in `apps/api/backends/computer_use/cost.py` (lines 114–115, now 122–123 after the docstring tightening) bring the implementation in line with the docstring contract AND with the parallel `OpenRouterCostTracker.record_final_usage` (lines 92–93) and `ClaudeCodeCostTracker.record_result` (lines 119–120) patterns. The cache counters (`_cache_read_total` / `_cache_write_total`, lines 124–125) intentionally keep `+=` — they are visibility-only running totals across iterations of a session-level cache resource, not single-iteration authoritative values.

A new non-async unit test (`test_record_iteration_usage_overrides_running_estimate`) directly asserts the override semantics on a real `ComputerUseCostTracker` instance, using the exact reproduction recipe recorded in 02-VERIFICATION.md (`text="x"*40` then `record_iteration_usage(input_tokens=10, output_tokens=5)`, assert `tokens_in() == 10` and `tokens_out() == 5`). Without the fix, the test fails with `assert 15 == 5`.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | RED — Add failing regression for ComputerUseCostTracker override semantics | `43b40ab` | apps/api/backends/computer_use/tests/test_adapter.py |
| 1 | GREEN — Override (=) _tokens_in / _tokens_out; preserve += on cache counters | `a95617a` | apps/api/backends/computer_use/cost.py |

(Task 1 was split into RED and GREEN commits per the plan's `tdd="true"` flag. The RED commit alone fails the new regression test on the buggy adapter; GREEN passes it.)

## Verification

All 11 acceptance criteria pass:

### AC #1 — New regression test passes

```text
$ uv run pytest -m 'not live' apps/api/backends/computer_use/tests/test_adapter.py::test_record_iteration_usage_overrides_running_estimate -x -v
collected 1 item
apps/api/backends/computer_use/tests/test_adapter.py .                   [100%]
1 passed in 0.01s
```

### AC #2 — Full computer_use suite ≥23 tests passing (was 22 + 1 new)

```text
$ uv run pytest -m 'not live' apps/api/backends/computer_use/tests/ -q
.......................                                                  [100%]
23 passed
```

### AC #3 — D-19 invariants stay green for computer_use (6/6)

```text
$ uv run pytest -m 'not live' apps/api/backends/tests/test_adapter_contract.py -k computer_use -v
collected 18 items / 12 deselected / 6 selected
apps/api/backends/tests/test_adapter_contract.py ......                  [100%]
6 passed, 12 deselected in 0.29s
```

### AC #4, #6 — Override-form grep assertions present

```text
$ grep -n "self._tokens_in = int" apps/api/backends/computer_use/cost.py
122:        self._tokens_in = int(input_tokens)

$ grep -n "self._tokens_out = int" apps/api/backends/computer_use/cost.py
123:        self._tokens_out = int(output_tokens)
```

### AC #5, #7 — Accumulate-form grep assertions absent

```text
$ grep -cn "self._tokens_in += int" apps/api/backends/computer_use/cost.py
0
$ grep -cn "self._tokens_out += int" apps/api/backends/computer_use/cost.py
0
```

### AC #8, #9 — Cache counter `+=` form PRESERVED

```text
$ grep -n "_cache_read_total += int\|_cache_write_total += int" apps/api/backends/computer_use/cost.py
124:        self._cache_read_total += int(cache_read)
125:        self._cache_write_total += int(cache_write)
```

### AC #10 — Phase 1 D-18 import-graph guard stays green

```text
$ uv run pytest src/routing/tests/test_decide_smoke.py -x -q
.......                                                                  [100%]
7 passed
```

### AC #11 — Whole-repo non-live suite exits 0

```text
$ uv run pytest -m 'not live'
231 passed, 2 skipped, 3 deselected in 67.69s
```

Plus phase-2-scope verification per the plan's `<verification>` block:

```text
$ uv run pytest -m 'not live' apps/api/backends -q
131 passed, 1 skipped, 3 deselected in 1.04s
```

(Plan called for ≥130 passed; observed 131.)

## RED→GREEN evidence (TDD gate)

Before the fix (commit 43b40ab, test only, cost.py unchanged):

```text
$ uv run pytest -m 'not live' apps/api/backends/computer_use/tests/test_adapter.py::test_record_iteration_usage_overrides_running_estimate -x -v
...
>       assert tracker.tokens_out() == 5
E       assert 15 == 5
E        +  where 15 = tokens_out()
E        +    where tokens_out = <apps.api.backends.computer_use.cost.ComputerUseCostTracker object at 0x10af3bf10>.tokens_out
FAILED apps/api/backends/computer_use/tests/test_adapter.py::test_record_iteration_usage_overrides_running_estimate
============================== 1 failed in 0.08s ===============================
```

After the fix (commit a95617a, cost.py edited):

```text
1 passed in 0.01s
```

## Deviations from Plan

None — plan executed exactly as written. The two literal edits in `cost.py` and the new test in `test_adapter.py` match the plan's `<action>` block verbatim. The docstring tightening was suggested as "optional" in the plan and was applied (it adds two short paragraphs documenting the override-vs-accumulate contrast).

## Cross-Refs to VERIFICATION.md

- VERIFICATION.md Truth 22 (CR-02): expected to flip from `FAILED — record_iteration_usage uses += (accumulate) instead of = (override) on lines 114-115` to `VERIFIED — override semantics restored; regression test test_record_iteration_usage_overrides_running_estimate codifies the contract`.
- Plan 02-VERIFICATION.md "missing" item 1 ("change `+=` to `=` on cost.py lines 114-115") — DONE.
- Plan 02-VERIFICATION.md "missing" item 2 ("add regression test asserting tracker.tokens_in() == 10 and tokens_out() == 5 after the recipe") — DONE.

## Self-Check: PASSED

Files modified (exist on disk):
- `apps/api/backends/computer_use/cost.py` — FOUND.
- `apps/api/backends/computer_use/tests/test_adapter.py` — FOUND.

Commits (resolvable via `git log`):
- `43b40ab` (RED) — FOUND.
- `a95617a` (GREEN) — FOUND.

Threat surface scan: no new network endpoints, no new auth paths, no new file-access patterns, no new schema changes. The fix is a pure arithmetic correction inside an existing class; no new threat-flagged surface.
