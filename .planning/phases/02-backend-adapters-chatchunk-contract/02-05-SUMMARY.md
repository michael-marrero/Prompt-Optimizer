---
phase: 02
plan: 05
subsystem: backend-adapters
gap_closure: true
tags: [claude-code, filediff, tool-use-id, regression, gap-closure, cr-01]
dependency_graph:
  requires:
    - "02-02 Plan SUMMARY — Claude Code adapter foundation (ClaudeCodeAdapter, _is_* duck-typed dispatch, FakeToolResultBlock fake, T6/T7/T8 FileDiff unit tests)"
    - "claude_agent_sdk 0.1.81 — real ToolResultBlock dataclass shape (tool_use_id + content + is_error only; verified live by 02-VERIFICATION.md Truth 21)"
    - "apps.api.backends.chunks.FileDiff (Wave 0 — tool_call_id + path + diff + operation)"
  provides:
    - "apps.api.backends.claude_code.adapter._pending_tool_calls — per-stream() dict[str, tuple[str, dict]] pairing ToolUseBlock(id) with (tool_name, input) for the matching ToolResultBlock to recover"
    - "apps.api.backends.claude_code.tests.fakes.FakeToolResultBlock — now mirrors real SDK shape exactly (three fields: tool_use_id, content, is_error)"
    - "apps.api.backends.claude_code.tests.test_adapter.test_filediff_emitted_against_real_sdk_shape — regression test that fails closed if the lookup is removed"
  affects:
    - "BACKEND-04 — FileDiff emission is now reachable in production (was dead code)"
    - "ROADMAP Success Criterion #1 — claude_code CLI can produce a FileDiff against a real Edit/Write tool call (verifiable end-to-end once live smoke runs)"
    - "Phase 5 CodeBubble UI — depends on FileDiff chunk type firing for Edit/Write tool results"
    - "02-VERIFICATION.md Truth 21 (CR-01) — flips from FAILED (gaps_found) to VERIFIED"
tech_stack:
  added: []
  patterns:
    - "Pair-up pattern for SDK shape drift: when a downstream dataclass loses a field that the upstream dataclass still carries, store the upstream side at emit-time keyed by a shared id, then pop on the matching downstream event. Local-variable dict (not self.) so concurrent stream() calls cannot share state."
    - "Fake-must-match-real-shape invariant: test fakes for SDK dataclasses MUST carry only the fields the real SDK exposes. Extra fields on the fake silently mask production bugs (this plan exists precisely because the fake had two extra fields that the real SDK never had)."
    - "TDD RED gate: write the regression test against the new (real-SDK-matching) fake shape FIRST, confirm it fails on the buggy adapter, only then implement the fix. The new test must fail without the fix in place — otherwise the fix is untested."
key_files:
  created: []
  modified:
    - "apps/api/backends/claude_code/adapter.py"
    - "apps/api/backends/claude_code/tests/fakes.py"
    - "apps/api/backends/claude_code/tests/test_adapter.py"
decisions:
  - "Local-variable _pending_tool_calls (not self._pending_tool_calls) inside the stream() async generator. Per-stream() lifetime means two concurrent stream() calls on the same adapter instance cannot interfere — each has its own dict. self. would have leaked state across turns and across cancellation/retry cycles."
  - "Default fallback ('', {}) on _pending_tool_calls.pop(tool_use_id, ('', {})). If a ToolResultBlock arrives without a preceding ToolUseBlock (defensive — never observed in practice but cannot be ruled out for SDK restart / future SDK behaviour), the recovered tool_name is '' which is not in ('Edit', 'Write'), so the adapter falls through to ToolResult emission instead of raising. Aligns with the surrounding V7 defensive-programming style."
  - "Store both name and input in one tuple per tool_use_id (not two separate dicts). Single dict-pop is atomic and cheaper than two coordinated lookups; tuple unpacking on the consumer side is a single statement: `tool_name, tool_input = _pending_tool_calls.pop(...)`."
  - "Stored side is the ToolUseBlock side (not the ToolResultBlock side) because that's where the real SDK carries the (name, input) pair. The fix matches the SDK's own data model: ToolUseBlock is the authoritative source for what Claude asked the tool to do; ToolResultBlock is the tool's reply."
  - "T8 (Bash → ToolResult) test pattern still works without code changes beyond the kwarg drop. The recovered tool_name from _pending_tool_calls.pop('t3', ('', {}))[0] is 'Bash' (from the matching ToolUseBlock), which is not in ('Edit', 'Write'), so the adapter routes to ToolResult exactly as before. T8 now tests the new code path end-to-end without any test-only fakery."
  - "Existing T6/T7/T8 kept their ToolUseBlock kwargs (name='Edit'/'Write'/'Bash', input={...}) because those fields DO exist on the real SDK ToolUseBlock dataclass. Only the ToolResultBlock kwargs (tool_name=, input=) were dropped — those did not exist on the real SDK and were the masking layer."
metrics:
  duration_minutes: 5
  task_count: 1
  files_modified: 3
  files_created: 0
  tests_added: 1
  tests_modified: 3
  commits: 2
  completed_date: "2026-05-15"
---

# Phase 02 Plan 05: Claude Code FileDiff tool_use_id Lookup Summary

One-liner: Closes CR-01 — Claude Code adapter now recovers tool_name/input via tool_use_id lookup against the ToolUseBlock side, matching the real claude_agent_sdk==0.1.81 ToolResultBlock three-field shape. FileDiff emission is now reachable in production.

## Outcome

The Claude Code adapter's `FileDiff` dispatch branch was dead code in production because it read `block.tool_name` and `block.input` off a `ToolResultBlock` — fields that do NOT exist on the real `claude_agent_sdk==0.1.81` `ToolResultBlock` dataclass (verified live by 02-VERIFICATION.md Truth 21). The existing T6 / T7 / T8 unit tests passed only because `FakeToolResultBlock` defined those fields with defaults, masking the bug.

This plan introduces a per-`stream()` `_pending_tool_calls: dict[str, tuple[str, dict]]` populated at the `ToolUseBlock` emit site (keyed by `block.id`, value `(block.name, block.input)`). On the matching `ToolResultBlock`, the adapter `pop`s the entry by `tool_use_id` and uses the recovered `tool_name` + `input` to decide whether to emit `FileDiff` (Edit/Write) or `ToolResult` (Bash/Glob/Grep/Read). The `FakeToolResultBlock` dataclass is reduced to the three real-SDK fields (`tool_use_id`, `content`, `is_error`) so the fake's shape can no longer mask the production code path.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | RED — Add failing CR-01 regression test for FileDiff against real SDK shape | `fd297a3` | apps/api/backends/claude_code/tests/test_adapter.py |
| 1 | GREEN — Recover ToolUseBlock(name,input) via tool_use_id lookup; drop fake masking fields | `2e79161` | apps/api/backends/claude_code/adapter.py, tests/fakes.py, tests/test_adapter.py |

(Task 1 was split into a RED commit and a GREEN commit per TDD discipline. The plan's `tdd="true"` flag mandates the RED gate land first and fail on the buggy code.)

## Verification

All acceptance criteria pass:

### AC #1 — Full test_adapter.py file passes (was 18, now 19 with regression)

```text
$ uv run pytest -m 'not live' apps/api/backends/claude_code/tests/test_adapter.py
...................                                                      [100%]
19 passed in 0.07s
```

### AC #2 — T6 / T7 / T8 still green after fakes field drop

```text
$ uv run pytest -m 'not live' \
    apps/api/backends/claude_code/tests/test_adapter.py::test_filediff_emitted_for_edit_tool \
    apps/api/backends/claude_code/tests/test_adapter.py::test_filediff_emitted_for_write_tool \
    apps/api/backends/claude_code/tests/test_adapter.py::test_toolresult_emitted_for_bash_tool -v
collected 3 items
apps/api/backends/claude_code/tests/test_adapter.py ...                  [100%]
3 passed in 0.01s
```

### AC #3 — D-19 invariants still green for claude_code (6/6)

```text
$ uv run pytest -m 'not live' apps/api/backends/tests/test_adapter_contract.py -k claude_code -v
collected 18 items / 12 deselected / 6 selected
apps/api/backends/tests/test_adapter_contract.py ......                  [100%]
6 passed, 12 deselected in 0.25s
```

### AC #4 — Whole apps/api/backends non-live suite exits 0 with no new failures

```text
$ uv run pytest -m 'not live' apps/api/backends -q
130 passed, 1 skipped, 3 deselected in 1.03s
```

Up exactly one from the pre-fix 129-passing baseline (the new `test_filediff_emitted_against_real_sdk_shape` regression).

### AC #5 — `_pending_tool_calls` appears at least 3 times in adapter.py (init + store + pop)

```text
$ grep -c "_pending_tool_calls" apps/api/backends/claude_code/adapter.py
5
```

Five matches (init, store, pop, plus two comment references for clarity).

### AC #6 — `tool_name: str` dataclass field is gone from FakeToolResultBlock

```text
$ grep -E "^[[:space:]]+tool_name:[[:space:]]*str" apps/api/backends/claude_code/tests/fakes.py
(no output — exit 1)
```

Zero lines match the dataclass-field regex. Docstring mentions of `tool_name` are allowed and present (calling out why the field is gone).

### AC #7 — Exactly one `input: dict` field remains (FakeToolUseBlock only)

```text
$ grep -E "^[[:space:]]+input:[[:space:]]*dict" apps/api/backends/claude_code/tests/fakes.py
    input: dict[str, Any] = field(default_factory=dict)
```

One line: the legitimate `FakeToolUseBlock.input` field. `FakeToolResultBlock.input` is gone.

### AC #8 — Phase 1 D-18 import-graph guard stays green

```text
$ uv run pytest src/routing/tests/test_decide_smoke.py -x -q
.......                                                                  [100%]
7 passed in 1.84s
```

### AC #9 — Whole-repo non-live suite exits 0

```text
$ uv run pytest -m 'not live'
230 passed, 2 skipped, 3 deselected in 68.18s (0:01:08)
```

Up exactly one from the pre-fix 229-passing baseline.

## Deviations from Plan

None — plan executed exactly as written.

The plan's `<action>` block specified each line of code change with surgical precision; no Rule 1 / Rule 2 / Rule 3 auto-fixes were needed. No Rule 4 architectural decisions arose.

## Files Modified

### `apps/api/backends/claude_code/adapter.py`

Three localised changes inside the `stream()` async generator:

1. **Init (before `client: Any = None`):** add `_pending_tool_calls: dict[str, tuple[str, dict]] = {}` as a local variable. Comment explains the per-stream() lifetime and why concurrency isolation matters.
2. **Store (inside the `elif _is_tool_use(block):` arm, after the existing `yield ToolCall(...)`):** record `(block.name, block.input)` into the dict keyed by `block.id`, guarded by `if tool_id:` to skip empty-id edge cases.
3. **Lookup (inside the `if _is_tool_result(block):` arm):** replace the four-line stale field-read pattern with `tool_name, tool_input = _pending_tool_calls.pop(tool_use_id, ("", {}))`. The rest of the branch (FileDiff vs ToolResult dispatch) is unchanged in shape — it now reads from the recovered locals instead of from non-existent block attributes.

Module-level docstring updated to spell out how the `UserMessage → ToolResultBlock` branch recovers `tool_name` / `input`.

### `apps/api/backends/claude_code/tests/fakes.py`

Two field drops on `FakeToolResultBlock` (the masking layer):

- `tool_name: str = ""` — removed (real SDK ToolResultBlock has no `tool_name`).
- `input: dict[str, Any] | None = None` — removed (real SDK ToolResultBlock has no `input`).

Docstring updated to call out the parity invariant with the real SDK and to explain why the fields were removed (referencing this plan). Module-level docstring's `Public surface` block updated.

### `apps/api/backends/claude_code/tests/test_adapter.py`

- T6 (`test_filediff_emitted_for_edit_tool`): dropped `tool_name="Edit"` and `input={"path": "src/a.py"}` from the `FakeToolResultBlock(...)` constructor call. ToolUseBlock side retains its kwargs.
- T7 (`test_filediff_emitted_for_write_tool`): dropped `tool_name="Write"` and `input={"path": "src/new.py"}` from the `FakeToolResultBlock(...)` constructor call.
- T8 (`test_toolresult_emitted_for_bash_tool`): dropped `tool_name="Bash"` from the `FakeToolResultBlock(...)` constructor call (T8 never passed `input=`).
- New test `test_filediff_emitted_against_real_sdk_shape` added at the end of the file (above the trailing newline). Documented inline as the CR-01 regression: constructs `FakeToolResultBlock` with only the three real-SDK fields, asserts the adapter emits exactly one `FileDiff` with `operation="edit"`, `path="src/a.py"`, `tool_call_id="t1"`, and a `diff` that starts with `"--- diff ---"`.
- T6 / T7 / T8 header comments at the top of the file updated to describe the new lookup-based behaviour.

## Stub Tracking

None. The `("", {})` default tuple in `_pending_tool_calls.pop(tool_use_id, ("", {}))` is intentional defensive code (handles a defensive edge case where a ToolResultBlock arrives without a preceding ToolUseBlock) — it is NOT a stub. No hardcoded UI strings, no "TODO" / "placeholder" / "coming soon" text was introduced. No data sources left unwired.

## Threat Surface

The plan's `<threat_model>` declared four threats. After this fix:

| Threat ID | Disposition | Post-fix Status |
|-----------|-------------|-----------------|
| T-02-CR01-01 (Tampering — silent contract drift) | mitigate | RESOLVED — `_pending_tool_calls` lookup always resolves `tool_name` from the ToolUseBlock side (SDK source of truth). New regression test `test_filediff_emitted_against_real_sdk_shape` constructs `FakeToolResultBlock` with the SDK's actual three-field shape, so any future regression of either the adapter or the fake fails closed. |
| T-02-CR01-02 (Information disclosure — incomplete audit trail) | mitigate (downstream) | RESOLVED — FileDiff emission re-enabled; Phase 5 CodeBubble UI's diff-rendering path is unblocked when it ships. ASVS V7 (logging & monitoring) adjacency satisfied for this surface. |
| T-02-CR01-03 (Elevation of privilege) | accept | No change — no privilege boundary crossed by this fix. |
| T-02-CR01-04 (Repudiation) | accept | No change — single-developer workflow. |

No new security-relevant surface was introduced (no new endpoints, no new auth paths, no new file access, no schema changes at trust boundaries). The threat register is unchanged in scope.

## Self-Check: PASSED

Files exist:

- `FOUND: apps/api/backends/claude_code/adapter.py`
- `FOUND: apps/api/backends/claude_code/tests/fakes.py`
- `FOUND: apps/api/backends/claude_code/tests/test_adapter.py`
- `FOUND: .planning/phases/02-backend-adapters-chatchunk-contract/02-05-SUMMARY.md` (this file)

Commits exist:

- `FOUND: fd297a3` (test(02-05): add failing CR-01 regression for FileDiff against real SDK shape)
- `FOUND: 2e79161` (fix(02-05): recover ToolUseBlock(name,input) via tool_use_id lookup (CR-01))
