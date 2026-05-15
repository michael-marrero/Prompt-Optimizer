---
phase: 02-backend-adapters-chatchunk-contract
reviewed: 2026-05-15T17:30:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - .github/workflows/ci.yml
  - apps/api/backends/claude_code/adapter.py
  - apps/api/backends/claude_code/tests/fakes.py
  - apps/api/backends/claude_code/tests/test_adapter.py
  - apps/api/backends/computer_use/cost.py
  - apps/api/backends/computer_use/tests/test_adapter.py
  - apps/api/backends/logging_filter.py
  - apps/api/backends/tests/test_logging_filter.py
  - scripts/no-secrets.sh
findings:
  critical: 1
  warning: 6
  info: 4
  total: 11
status: issues_found
---

# Phase 2 (Gap-Closure): Code Review Report

**Reviewed:** 2026-05-15T17:30:00Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

This adversarial review covers the gap-closure run for Phase 02 — three plans (02-05, 02-06, 02-07) that landed on `main` to close CR-01 (Claude Code FileDiff `tool_use_id` lookup), CR-02 (`ComputerUseCostTracker` override semantics), and CR-04+CR-05 (logging_filter ↔ no-secrets.sh regex parity + Bearer ordering).

**Gap-closure verification:**

- **CR-01 (Claude Code FileDiff via tool_use_id lookup):** Correctly implemented. The `_pending_tool_calls` map is function-local (no cross-call interference), populated at `ToolUseBlock` emit, and drained at `ToolResultBlock` consumption via `dict.pop()`. The fake `FakeToolResultBlock` now mirrors the real SDK shape (three fields). However, I found one **Critical correctness bug** in the `FileDiff/ToolResult` content handling that the lookup fix surfaces but does not address (see CR-01 below).

- **CR-02 (ComputerUseCostTracker override):** Correctly implemented. `_tokens_in` / `_tokens_out` now use assignment; cache counters still accumulate. Docstring matches behavior. Multi-iteration semantics need attention (see WR-02 below).

- **CR-04+CR-05 (regex parity + Bearer ordering):** Bearer pattern is first in the python list; `Authorization: Bearer sk-ant-…` now redacts to a single `Bearer ***REDACTED***` unit. The CI parity step fails the build via `pytest -x`. However, the parity test is **asymmetric** (only verifies shell ⊆ python, never the reverse) and uses substring matching rather than tokenisation — both of which leave drift windows (see WR-01).

Findings: 1 Critical, 6 Warnings, 4 Info. The Critical finding is a new bug exposed during inspection of the CR-01 fix; it is not a regression from the gap-closure plans but should be addressed before this code ships to the Phase 3 SSE integration.

## Critical Issues

### CR-01: `ToolResultBlock.content` is `str | list[dict] | None` but the adapter only handles `str | dict`

**File:** `apps/api/backends/claude_code/adapter.py:395-421`
**Issue:** The real `claude_agent_sdk==0.1.81` `ToolResultBlock.content` is typed `str | list[dict[str, Any]] | None` (verified at `.venv/lib/python3.11/site-packages/claude_agent_sdk/types.py:945`). The adapter reads `content = getattr(block, "content", "")` (default `""`), then for the FileDiff branch passes `diff=str(content)` (line 409), and for the ToolResult branch normalises `if isinstance(content, (str, dict))` (line 413).

For the typical SDK case where `content` is a `list[dict]` (e.g. `[{"type": "text", "text": "diff body"}]`):

1. **FileDiff branch (Edit/Write):** `diff=str(content)` produces a Python repr like `"[{'type': 'text', 'text': '--- a/foo\\n+++ b/foo\\n...'}]"` — not a real diff. Downstream consumers (Phase 3 SSE, the chat UI) get a stringified Python list, not the unified-diff text they expect. The unit test `test_filediff_emitted_for_edit_tool` uses `content="--- a/src/a.py\\n+++ b/src/a.py\\n@@ ..."` (a bare `str`), so it never exercises the `list[dict]` branch — the bug is fully uncovered.
2. **ToolResult branch (Bash/Glob/Grep/Read):** `isinstance(content, (str, dict))` is False for `list[dict]`, so it falls through to `str(content)` (line 416) — same Python-repr leak. `ToolResult.content` ends up being a stringified list of SDK blocks instead of the human-readable tool output.

Confirmed against the SDK source:

```python
# .venv/lib/python3.11/site-packages/claude_agent_sdk/types.py:943-947
class ToolResultBlock:
    """Tool result content block."""
    tool_use_id: str
    content: str | list[dict[str, Any]] | None = None
    is_error: bool | None = None
```

The live smoke test will surface a stringified `[{...}]` in the FileDiff `diff` field. The CR-01 lookup fix is correct in isolation, but the content normalisation immediately downstream of the lookup still assumes a shape the SDK does not always emit.

**Fix:** Normalise `list[dict]` to a flat string before yielding:

```python
def _flatten_tool_result_content(content: Any) -> str:
    """Reduce ToolResultBlock.content (str | list[dict] | None) to text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                # SDK convention: {"type": "text", "text": "..."}
                text = item.get("text") or item.get("content") or ""
                parts.append(str(text))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)

# At the FileDiff site (line 406-411):
yield FileDiff(
    tool_call_id=tool_use_id,
    path=path,
    diff=_flatten_tool_result_content(content),
    operation="edit" if tool_name == "Edit" else "create",
)

# At the ToolResult site (line 413-421):
flat = _flatten_tool_result_content(content)
yield ToolResult(
    tool_call_id=tool_use_id,
    content=flat,
    is_error=is_error,
)
```

Add a regression test with `FakeToolResultBlock(content=[{"type": "text", "text": "--- a/foo\\n+++ b/foo\\n@@ ..."}])` and assert the emitted `FileDiff.diff` is the unified-diff string, NOT a Python `repr` of the list.

## Warnings

### WR-01: Regex parity test is asymmetric and uses fragile substring matching

**File:** `apps/api/backends/tests/test_logging_filter.py:62-124`
**Issue:** The parity test enforces only **shell ⊆ python** — for every shell sub-pattern, assert there exists a python pattern containing it as a substring. It never enforces **python ⊆ shell**. Two failure modes follow:

1. **Silent python-only additions:** If a fourth pattern is added to `SECRET_PATTERNS` without a corresponding shell update, the parity test still passes (the existing three shell patterns are still found in python). The companion `test_secret_patterns_count` happens to catch this specific case (it asserts `len(SECRET_PATTERNS) == 3`) — but the count check is **separate** and easy to bump in lockstep without anyone catching the drift.
2. **Substring false positives:** `shell_sp in py` accepts any case where the shell pattern is a *strict substring* of a wider python pattern. Toy example: shell `sk-X` would "match" python `sk-X[A-Z]` even though the semantics differ. Today's patterns happen to be exact equals so this works, but the test does not enforce that they remain equal — it allows the python side to silently widen without failing CI.

The current contract is "shell is a subset of python" — not the symmetric equivalence the docstring at `logging_filter.py:31-32` claims ("The three patterns intentionally MATCH the pre-commit hook").

**Fix:** Tokenise both sides into normalised forms and assert set-equality:

```python
def _normalise(p: str) -> str:
    return (
        p.replace("[[:space:]]+", r"\s+")
         .replace(r".\-", ".-")   # collapse python escapes
    )

shell_set = {_normalise(p) for p in shell_subpatterns}
python_set = {_normalise(p) for p in python_patterns}
assert shell_set == python_set, (
    f"Drift detected.\n  shell-only: {shell_set - python_set}\n  python-only: {python_set - shell_set}"
)
```

Add a unit test that demonstrates the drift — e.g. add a fake fourth python pattern and confirm the parity assertion fires.

### WR-02: Computer-use multi-iteration tokens are overwritten, not accumulated

**File:** `apps/api/backends/computer_use/cost.py:122-125`; `apps/api/backends/computer_use/adapter.py:391-409`
**Issue:** The CR-02 fix is correct for the single-iteration happy path (the test exercises one iteration with `end_turn`). However, the computer-use adapter runs a `while True` loop (Pattern 5 / D-12) with multiple iterations. Each iteration calls `record_iteration_usage(input_tokens=…, output_tokens=…)`, which now ASSIGNS rather than accumulates. The behaviour:

- Iteration 1: `input=100, output=50` → tracker now reports (100, 50).
- Iteration 2: `input=80, output=30` → tracker now reports (80, 30) — iteration 1's tokens are gone.
- Done chunk: reports (80, 30) — undercounting the turn's actual usage.

If Anthropic's `final_msg.usage` is cumulative-across-iterations, this is correct. If it is per-iteration, the Done chunk under-reports tokens. The unit test does not distinguish — only `test_iteration_usage_recorded` runs, and it uses a single iteration (`stop_reason="end_turn"`).

I cannot confirm Anthropic's exact semantics from the code under review (the SDK does not document it inline). Two safe options:

**Fix Option A (assume per-iteration):** Accumulate `_tokens_in` and `_tokens_out` across iterations by snapshotting them before each iteration:

```python
def record_iteration_usage(self, *, input_tokens, output_tokens, cache_read=0, cache_write=0):
    # Per-iteration: add to running totals.
    self._tokens_in += int(input_tokens)
    self._tokens_out += int(output_tokens)
    self._cache_read_total += int(cache_read)
    self._cache_write_total += int(cache_write)
```

…but then the char/4 estimate that `record_output_text` produces during the iteration is also added on top. Reset the estimate at the start of each iteration:

```python
def reset_iteration_estimate(self) -> None:
    """Adapter calls this at the top of each agent-loop iteration."""
    # Snapshot the current totals so within-iteration char/4 estimates
    # don't double-count after record_iteration_usage replaces them.
    self._iteration_baseline_out = self._tokens_out

def record_iteration_usage(...):
    # Override the within-iteration estimate, then accumulate.
    self._tokens_out = self._iteration_baseline_out + int(output_tokens)
    ...
```

**Fix Option B (assume cumulative):** Confirm via live-smoke or Anthropic docs that `final_msg.usage` is cumulative across iterations, then leave the override semantics and add a documentation comment + a multi-iteration regression test that asserts the contract.

Either way, add a regression test that runs the adapter with two `tool_use` iterations (e.g. `make_tool_use_stream(...)` × 2 then `end_turn`) and asserts the final `Done.tokens_out` reflects the intended semantics.

### WR-03: Adapter still uses deprecated `asyncio.get_event_loop()` for wall-clock time

**File:** `apps/api/backends/claude_code/adapter.py:307, 459, 486`
**Issue:** Three calls to `asyncio.get_event_loop().time()` for latency measurement. Since Python 3.10 `asyncio.get_event_loop()` emits a `DeprecationWarning` when called outside a running coroutine and is scheduled for removal in a future release. While the calls here are inside `stream()` (a coroutine), the idiomatic Python 3.10+ replacement is `asyncio.get_running_loop()` (inside coroutines) or `time.monotonic()` (for plain wall-clock latency). `time.monotonic()` is the standard idiom and decouples latency tracking from the event loop.

This was already noted in the prior review (WR-04). The gap-closure plans did not touch it; flagging again because it remains in the focus scope (`adapter.py`).

**Fix:**

```python
import time

# Top of stream():
start_t = time.monotonic()

# At each measurement point:
latency_ms = int((time.monotonic() - start_t) * 1000)
```

### WR-04: Workspace `mkdtemp` runs outside `try/finally` → directory leaks if construction raises

**File:** `apps/api/backends/claude_code/adapter.py:295, 327, 516-529`
**Issue:** `workspace = tempfile.mkdtemp(prefix="pomu-cc-")` runs at line 295. The `try:` block does not begin until line 327, with several constructions in between:

- `ClaudeCodeCostTracker(...)` (line 301-305) — can raise if `pricing` lookup fails
- `StepCounter(cap=max_steps)` (line 306) — can raise on invalid `max_steps`
- `asyncio.get_event_loop().time()` (line 307) — can raise `RuntimeError: no current event loop`
- `ClaudeAgentOptions(...)` (line 310-315) — SDK construction can raise on invalid options

Any exception in lines 296-326 leaves the temp dir orphaned because the `finally` block (line 516) is bound to the `try:` at line 327 and is never reached. The previous review noted this; the gap-closure plans did not address it.

**Fix:** Wrap `mkdtemp` immediately in a try block, or push the workspace setup inside the existing try block and use the `ephemeral_workspace` context manager that already exists in `apps/api/backends/claude_code/workspace.py`:

```python
try:
    if options.cwd:
        workspace = options.cwd
        cleanup_workspace = False
    else:
        workspace = tempfile.mkdtemp(prefix="pomu-cc-")
        cleanup_workspace = True

    tracker = ClaudeCodeCostTracker(...)
    # ... rest of the setup
    client = self._client_factory(...)
    # ... rest of the body
finally:
    if cleanup_workspace and workspace:
        shutil.rmtree(workspace, ignore_errors=True)
    # ... rest of the existing finally
```

### WR-05: Bearer redaction regex matches across newlines — single-line guarantee unenforced

**File:** `apps/api/backends/logging_filter.py:66`
**Issue:** The Bearer pattern `re.compile(r"Bearer\s+[A-Za-z0-9_.\-]{20,}")` uses `\s+`, which Python's regex engine treats as "any whitespace character including `\n` and `\t`". On a multi-line log message such as `"Bearer\nsk-XYZABCDEFGHIJKLMNOPQRSTUVWXYZ0123"`, the pattern matches across the newline and redacts as `"Bearer ***REDACTED***"` — collapsing two lines into one (and accidentally consuming the newline). This is unlikely in practice (log records are typically single-line) but it is also unguarded; a multi-line log message with a leading "Bearer" token would silently mangle the second line.

The companion `Bearer[[:space:]]+` in `scripts/no-secrets.sh` also matches across whitespace, including tabs and (in some bash builds) newlines, so the shell hook has the same behaviour. This is consistent but undocumented.

**Fix:** Restrict to horizontal whitespace using `[ \t]+` (or `[^\S\r\n]+` to match the spirit of `\s` without newlines):

```python
(re.compile(r"Bearer[ \t]+[A-Za-z0-9_.\-]{20,}"), "Bearer ***REDACTED***"),
```

And in the shell script:

```bash
Bearer[[:blank:]]+[A-Za-z0-9_.-]{20,}
```

If the cross-line behaviour is intentional (e.g. the hook is meant to catch a Bearer split across diff context lines), keep `\s+` / `[[:space:]]+` but document why and add a regression test asserting both files agree.

### WR-06: `Bearer sk-XXX` (non-anthropic) coverage is implicit — no regression test

**File:** `apps/api/backends/tests/test_logging_filter.py:37-59`
**Issue:** The CR-05 regression test (`test_bearer_prefixed_sk_ant_redacts_as_bearer_unit`) covers `Bearer sk-ant-…` and asserts the Bearer unit redaction. There is no equivalent test for `Bearer sk-…` (non-anthropic), even though the Bearer-first ordering needs to win against the OpenAI `sk-` pattern too. The implementation works (Bearer pattern fires first), but the contract is uncovered by the test suite. A future reorder (Bearer below sk-) would only fail one test, not two.

**Fix:** Add a parallel test:

```python
def test_bearer_prefixed_sk_openai_redacts_as_bearer_unit(caplog) -> None:
    install_redaction_filter()
    logger = logging.getLogger("test.bearer_openai")
    with caplog.at_level(logging.INFO, logger="test.bearer_openai"):
        logger.info("Authorization: Bearer sk-proj-abcdefghijklmnopqrstuvwxyz0123")
    assert "sk-proj-" not in caplog.text
    assert "Bearer ***REDACTED***" in caplog.text
    assert "***REDACTED-OPENAI***" not in caplog.text
```

## Info

### IN-01: `_pending_tool_calls` silently emits `ToolResult` if `ToolResultBlock` arrives before its `ToolUseBlock`

**File:** `apps/api/backends/claude_code/adapter.py:397-399`
**Issue:** If the SDK ever emits a `ToolResultBlock` before the matching `ToolUseBlock` (out-of-order delivery, or a buggy provider replaying an older state), `_pending_tool_calls.pop(tool_use_id, ("", {}))` returns the default — `tool_name = ""`, `tool_input = {}`. The empty `tool_name` falls through to the `ToolResult` branch (line 412+). No logging fires, no error chunk is emitted. The user sees a `ToolResult` chunk for what should have been a `FileDiff`. This is a silent semantic downgrade.

Out-of-order delivery is unlikely with the streaming SDK but not impossible (e.g. error recovery paths). Adding a `logger.warning(...)` would make this debuggable without changing behaviour:

```python
tool_name, tool_input = _pending_tool_calls.pop(tool_use_id, ("", {}))
if not tool_name:
    logger.warning("ToolResultBlock for unknown tool_use_id=%r (out-of-order or missed ToolUseBlock)", tool_use_id)
```

### IN-02: `FakeToolResultBlock.content` default is `""` but the real SDK default is `None`

**File:** `apps/api/backends/claude_code/tests/fakes.py:70-72`
**Issue:** The fake defaults `content: Any = ""`, but the real SDK's `ToolResultBlock.content` defaults to `None`. The adapter's `getattr(block, "content", "")` masks the difference (both yield falsy values), but if a future change uses `block.content is None` to detect "no content yet", the fake would mismatch. Cosmetic; mark the fake's default to match the SDK so the duck-type stays exact:

```python
@dataclass
class FakeToolResultBlock:
    tool_use_id: str = ""
    content: Any = None        # matches the real SDK default
    is_error: bool = False
```

Adjust any test that explicitly passes `content=""` to either leave the default or pass an empty string deliberately.

### IN-03: CI parity step has no timeout — a hanging pytest blocks the whole job

**File:** `.github/workflows/ci.yml:34-38`
**Issue:** The "Regex parity check" step has no `timeout-minutes` setting. The default GitHub Actions step timeout (360 minutes) applies. If a future test in `test_logging_filter.py` accidentally hangs (e.g. a regex with catastrophic backtracking on a test input), the entire CI job stalls for six hours before being cancelled. Add a tight bound:

```yaml
- name: Regex parity check (SECURE-01 + SECURE-02 contract)
  timeout-minutes: 2
  run: |
    uv run pytest -m 'not live' \
      apps/api/backends/tests/test_logging_filter.py::test_logging_filter_and_no_secrets_regex_parity \
      -x -q
```

The full Phase-2 test step (line 56) should also have a timeout. Not gating because pytest itself rarely hangs, but worth a brief audit pass.

### IN-04: `no-secrets.sh` does not handle `git diff` returning non-zero (e.g. broken pipe)

**File:** `scripts/no-secrets.sh:18, 20-22`
**Issue:** With `set -o pipefail`, the pipeline `git diff --cached --diff-filter=AM | grep -E '^\+[^+]' | grep -E '(...)'` aborts on the first non-zero exit code. The middle `grep -E '^\+[^+]'` returns 1 if the diff has no `+` lines (e.g. a pure delete commit), which makes the whole pipeline return 1, which under `set -e` aborts the script BEFORE the `if` decides. The `if`'s pipeline return-code is what gets evaluated, so this is actually fine for the `if` branch — but `pipefail` makes the script exit 0 only when no grep ever returned 1 in the chain.

Trace: a pure-delete commit (only `-` lines) produces empty output from the first grep, exit code 1. With `pipefail`, the second grep sees no stdin, exits 1 too. `if pipeline; then ...` then evaluates the final exit code (1) and skips the `then` branch — so the script falls through to `exit 0`. This is correct.

However, if a future change adds another grep or processing step after the pipeline (outside the `if`), `set -e` + `pipefail` would abort. Comment the script to document the expected exit-code behaviour, or wrap the pipeline in `|| true` if the contract is "grep returning empty is not an error":

```bash
if git diff --cached --diff-filter=AM 2>/dev/null \
   | grep -E '^\+[^+]' \
   | grep -E '(...)' > /dev/null 2>&1
then
    echo "ERROR: ..."
    exit 1
fi
exit 0
```

The current script works but is fragile to future edits.

---

_Reviewed: 2026-05-15T17:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
