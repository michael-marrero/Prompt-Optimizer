---
phase: 02-backend-adapters-chatchunk-contract
plan: 02
subsystem: backend-adapters
tags: [claude-code, claude-agent-sdk, async-streaming, cost-tracking, step-cap, cancellation, workspace, chatchunk, watchdog]
dependency_graph:
  requires:
    - "apps.api.backends.chunks (Wave 0 — TextDelta, ToolCall, ToolResult, FileDiff, StreamError, Done)"
    - "apps.api.backends.protocol (Wave 0 — BackendAdapter, Message, AdapterOptions)"
    - "apps.api.backends.cost (Wave 0 — CostTracker, DEFAULT_PER_TURN_COST_USD)"
    - "apps.api.backends.pricing (Wave 0 — PricingTable)"
    - "config/pricing.json (Wave 0 — 14 model rows incl. claude-agent-sdk + _default fallback)"
    - "claude_agent_sdk 0.1.81 (Phase 2 Wave 0 base dep)"
  provides:
    - "apps.api.backends.claude_code.ClaudeCodeAdapter (BackendAdapter Protocol impl)"
    - "apps.api.backends.claude_code.adapter.ALLOWED_TOOLS (locked 6-element list)"
    - "apps.api.backends.claude_code.cost.ClaudeCodeCostTracker (char/4 + ResultMessage override)"
    - "apps.api.backends.claude_code.step_counter.StepCounter + DEFAULT_STEP_CAP=25"
    - "apps.api.backends.claude_code.workspace.ephemeral_workspace (async context manager)"
    - "apps.api.backends.claude_code.errors.map_provider_error / PROVIDER_ERROR_MAP"
    - "apps.api.backends.claude_code CLI: `python -m apps.api.backends.claude_code --prompt '...' [--cwd ...]`"
    - "side-effect at package import: os.environ.setdefault('CLAUDE_ENABLE_STREAM_WATCHDOG', '1') (BACKEND-09)"
    - "apps.api.backends.claude_code.tests.fakes.FakeClaudeSDKClient + FakeAssistantMessage etc."
  affects:
    - "Wave 1 Plan 03 (computer-use adapter) — same module-layout convention (now confirmed twice)"
    - "Wave 2 Plan 04 (live smoke harness) — consumes test_live.py marker"
    - "Phase 3 FastAPI adapter registry — imports ClaudeCodeAdapter directly"
tech_stack:
  added:
    - "claude_agent_sdk 0.1.81 ClaudeSDKClient lifecycle: connect/query/receive_response/interrupt/disconnect"
    - "tempfile.mkdtemp(prefix='pomu-cc-') for ephemeral per-turn workspace (BACKEND-08)"
    - "CLAUDE_ENABLE_STREAM_WATCHDOG=1 subprocess inherited env var (BACKEND-09)"
  patterns:
    - "Duck-typed message/block dispatch via `_is_*` helpers (isinstance + class-name fallback) so test fakes work without monkeypatching the SDK imports"
    - "client_factory dependency injection bypasses the constructor's ANTHROPIC_API_KEY preflight (test-injection escape valve)"
    - "Inline workspace lifecycle (mkdtemp + cleanup flag in try/finally) — RESEARCH Pattern 4 lines 722-727 verbatim"
    - "Interrupt-before-break in cap-exhausted paths (Pitfall 5 — SDK closes its async generator cleanly when interrupted, not when caller bare-breaks)"
    - "Canonical-class-name fallback in PROVIDER_ERROR_MAP — inherited from Plan 02-01 Decision #2 (D-18 sys.modules purge robustness)"
key_files:
  created:
    - "apps/api/backends/claude_code/__init__.py"
    - "apps/api/backends/claude_code/__main__.py"
    - "apps/api/backends/claude_code/adapter.py"
    - "apps/api/backends/claude_code/cost.py"
    - "apps/api/backends/claude_code/errors.py"
    - "apps/api/backends/claude_code/step_counter.py"
    - "apps/api/backends/claude_code/workspace.py"
    - "apps/api/backends/claude_code/tests/__init__.py"
    - "apps/api/backends/claude_code/tests/conftest.py"
    - "apps/api/backends/claude_code/tests/fakes.py"
    - "apps/api/backends/claude_code/tests/test_adapter.py"
    - "apps/api/backends/claude_code/tests/test_workspace.py"
    - "apps/api/backends/claude_code/tests/test_watchdog_env.py"
    - "apps/api/backends/claude_code/tests/test_live.py"
  modified: []
decisions:
  - "Switched from raw isinstance dispatch to a duck-typed `_is_assistant/_is_user/_is_text_block/...` helper pair (isinstance + class-name fallback) so the Fake* dataclasses in tests/fakes.py work without monkeypatching the adapter's SDK imports. The plan's Task 1 fakes block (line 251) explicitly anticipated this choice — 'recommended: duck-typed dispatch on attributes, not isinstance on SDK types'. Real SDK objects still match via the isinstance leg of each helper."
  - "Constructor preflight (ANTHROPIC_API_KEY check) is SKIPPED when `client_factory` is provided. The D-19 shared contract suite's adapter_factory fixture passes a client_factory and no api_key — without this gate the contract suite cannot construct the adapter. The standalone `test_missing_api_key_raises_before_stream` invariant (no factory, no env var) still raises correctly."
  - "ClaudeCodeAdapter re-export in `__init__.py` deferred to Task 2 commit (same pattern Plan 02-01 used in Decision #4 for OpenRouter). Task 1 commit ships an `__init__.py` with only the watchdog setdefault so the cost/errors/step_counter/workspace submodules are importable during the Task 1 RED phase without an unresolved import chain."
  - "PricingTable is loaded once per process via `_get_pricing_table()` singleton (Path(__file__).resolve().parents[4] / 'config' / 'pricing.json'). Each ClaudeCodeAdapter instance reuses the cached table (parallel to Plan 02-01 Decision #3)."
  - "step_cap_aborts contract test actually PASSES for claude_code (unlike openrouter's pytest.skip 'N/A single round-trip'). The Fake response sequence yields >1 AssistantMessage, the StepCounter trips on the second one, the adapter emits StreamError(step_cap_exceeded) + Done and calls interrupt(). All 6 D-19 invariants are real passes."
metrics:
  duration_min: 29
  tasks_completed: 3
  files_created: 14
  files_modified: 0
  unit_tests_pass: 23
  contract_tests_pass: 6
  contract_tests_skipped: 0
  d18_guard_state: green
  whole_repo_test_state: "201 passed, 8 skipped"
  completed_at: "2026-05-15"
---

# Phase 02 Plan 02: Claude Code Adapter Summary

**Implements `ClaudeCodeAdapter` — async build-and-edit backend using `claude_agent_sdk.ClaudeSDKClient` (NOT the deprecated `claude-code-sdk` package and NOT the standalone `query()` function — Pitfall 2). Streams `TextDelta`/`ToolCall`/`ToolResult`/`FileDiff` chunks per tool the agent executes, enforces per-iteration step cap (default 25) + per-turn USD cost cap, propagates cancellation via `client.interrupt()` within a 2-second budget, runs in a per-thread `tempfile.mkdtemp(prefix="pomu-cc-")` workspace (opt-in `options.cwd` override per BACKEND-08), and sets `CLAUDE_ENABLE_STREAM_WATCHDOG=1` via `os.environ.setdefault` at package import (BACKEND-09).**

## Performance

- **Duration:** 29 min
- **Started:** 2026-05-15T15:34:39Z
- **Completed:** 2026-05-15T16:04:17Z
- **Tasks:** 3
- **Files created:** 14
- **Files modified:** 0 (all paths in the plan's `files_modified` frontmatter were CREATED, not modified — the directory tree did not exist before this plan)

## Accomplishments

- Wave 1 second-of-three backend adapters lands; D-19 shared contract suite now passes 11/12 invariants on the openrouter + claude_code parameterizations (only the openrouter `step_cap_aborts` skip remains, which is intentional per N/A semantics — claude_code passes that case as a real positive).
- Phase 2 Success Criterion #1 satisfied for Claude Code: `python -m apps.api.backends.claude_code --prompt "..."` streams one JSON line per ChatChunk to stdout with the last line carrying `"type":"done"` (D-04 invariant), and the CLI accepts all five flags (`--prompt`, `--model`, `--max-cost-usd`, `--max-steps`, `--cwd`).
- All three locked Pitfalls from `02-RESEARCH.md` covered with explicit regression:
  - **Pitfall 2** (ClaudeSDKClient vs standalone query): `test_uses_claudesdkclient_not_query_function` (`inspect.getsource` check on the adapter module) + `test_connect_query_receive_disconnect_called_in_order` (lifecycle method counters on FakeClaudeSDKClient).
  - **Pitfall 5** (cleanup ordering — `interrupt()` BEFORE `break`; `disconnect()` ALWAYS in `finally`): regressions in `test_assistant_message_increments_step_counter_with_step_cap`, `test_cost_cap_aborts_with_interrupt`, `test_cancellation_within_2s_calls_interrupt`, `test_disconnect_called_in_finally_on_exception`.
  - **OSS-06** (deprecated SDK absent): `grep -c "claude_code_sdk" apps/api/backends/claude_code/*.py` returns 0; one match in `tests/test_adapter.py` is the positive enforcement assertion `assert "claude_code_sdk" not in source`.
- Cancellation contract (BACKEND-07 / PEP 789): `try / except asyncio.CancelledError / await client.interrupt() / yield StreamError + Done / raise` plus `finally: await client.disconnect(); shutil.rmtree(workspace)`. Empirically enforced via `@pytest.mark.timeout(2)` on the cancellation test.
- Phase 1 D-18 import-graph guard remains green — Phase 2's `claude_agent_sdk` additions do not leak into `src.routing.decide`'s `sys.modules` graph.

## Task Commits

Each task was committed atomically:

1. **Task 1: Watchdog env, step counter, workspace, cost, errors, fakes** — `6d2a3ec` (test)
2. **Task 2: Implement ClaudeCodeAdapter (step cap + cancellation + FileDiff)** — `890bf1b` (feat)
3. **Task 3: Adapter tests + CLI + live smoke + D-19 verification** — `f247e40` (test)

## Files Created (14)

### Source (7)

| Path | Purpose |
| ---- | ------- |
| `apps/api/backends/claude_code/__init__.py` | Sets `CLAUDE_ENABLE_STREAM_WATCHDOG=1` via `os.environ.setdefault` (BACKEND-09 subprocess inheritance). Re-exports `ClaudeCodeAdapter`; `__all__ = ["ClaudeCodeAdapter"]`. |
| `apps/api/backends/claude_code/__main__.py` | CLI: `python -m apps.api.backends.claude_code --prompt '...' [--model claude-agent-sdk] [--max-cost-usd 0.50] [--max-steps 25] [--cwd /path]` (Phase 2 SC #1 + BACKEND-08 opt-in flag). Lazy adapter import + `_entrypoint` indirection (WR-07). |
| `apps/api/backends/claude_code/adapter.py` | `ClaudeCodeAdapter` class implementing `BackendAdapter` Protocol. Module constants `ALLOWED_TOOLS: Final[list[str]] = ["Read", "Edit", "Write", "Bash", "Glob", "Grep"]`. `_default` factory uses `claude_agent_sdk.ClaudeSDKClient`. `stream()` is a 5-stage async generator: workspace setup → tracker + step counter → `ClaudeSDKClient.connect/query` → per-message loop with FileDiff/ToolResult dispatch + cap checks → terminal Done. Full V7-style exception handling for `ProcessError`, `ClaudeSDKError`, generic `Exception`, and `asyncio.CancelledError` (re-raised after terminal pair). `finally` block disconnects client and rmtrees workspace. |
| `apps/api/backends/claude_code/cost.py` | `ClaudeCodeCostTracker(CostTracker)` with `record_output_text` (char/4 estimator per RESEARCH line 1379), `record_assistant_usage` (defensive `getattr` over `input_tokens`/`prompt_tokens` field name drift), `record_result` (authoritative `ResultMessage.total_cost_usd` override via `_final_cost_override`). |
| `apps/api/backends/claude_code/errors.py` | `PROVIDER_ERROR_MAP: {ProcessError → ("provider_unavailable", False), ClaudeSDKError → ("internal_error", False)}` + `map_provider_error(exc) → (code, message, retriable)` with canonical-class-name fallback (D-18 sys.modules purge robustness). |
| `apps/api/backends/claude_code/step_counter.py` | `DEFAULT_STEP_CAP: Final[int] = 25` (CONTEXT specifics line 261) + `class StepCounter` with `increment()` / `exceeded()` / `.value` / `.cap`. D-15: one step = one AssistantMessage. |
| `apps/api/backends/claude_code/workspace.py` | `@contextlib.asynccontextmanager async def ephemeral_workspace(cwd) -> AsyncIterator[tuple[str, bool]]` yielding `(workspace_path, must_cleanup)`. `tempfile.mkdtemp(prefix="pomu-cc-")` when `cwd is None`; `shutil.rmtree` in `finally` (T-02-05 leak mitigation). |

### Tests (7)

| Path | Coverage |
| ---- | -------- |
| `apps/api/backends/claude_code/tests/__init__.py` | Empty package marker. |
| `apps/api/backends/claude_code/tests/conftest.py` | Session-scoped `pricing_table` fixture (6-up path resolution: `apps/api/backends/claude_code/tests/conftest.py` → repo root). Function-scoped `fake_claude_sdk_client` (happy-path 2-message) + `fake_client_factory` (callable). |
| `apps/api/backends/claude_code/tests/fakes.py` | `FakeTextBlock`, `FakeToolUseBlock`, `FakeToolResultBlock`, `FakeAssistantMessage`, `FakeUserMessage`, `FakeSystemMessage`, `FakeResultMessage`, `FakeUsage`, `FakeThinkingBlock` dataclasses + `FakeClaudeSDKClient` with `connect_count` / `query_count` / `interrupt_count` / `disconnect_count` introspection hooks. |
| `apps/api/backends/claude_code/tests/test_watchdog_env.py` | 2 tests — env var set after import (BACKEND-09 regression); `setdefault` respects existing operator value. |
| `apps/api/backends/claude_code/tests/test_workspace.py` | 3 tests — mkdtemp + cleanup (BACKEND-08); cwd opt-in preserved; cleanup on exception. |
| `apps/api/backends/claude_code/tests/test_adapter.py` | 18 unit tests (T1-T18). See "Test Coverage Matrix" below. |
| `apps/api/backends/claude_code/tests/test_live.py` | One opt-in `@pytest.mark.live` test against the real Anthropic API. Asks Claude Code to create `hello.py` in a tmp workspace with `max_cost_usd=0.20`; asserts ≥ 1 `FileDiff` with `path.endswith('hello.py')` and `operation in ('create', 'edit')`, final `Done` with `0 < cost_usd < 0.20`, and the file exists on disk after the stream. |

## Test Coverage Matrix (test_adapter.py, 18 tests)

| Test | Invariant |
| ---- | --------- |
| T1 | Happy path emits TextDelta → Done; ResultMessage cost overrides estimate. |
| T2 | Adapter source imports ClaudeSDKClient; deprecated SDK absent (Pitfall 2). |
| T3 | connect/query/disconnect lifecycle called in order. |
| T4 | ALLOWED_TOOLS locked to the 6-element list. |
| T5 | max_steps=1 with 2 AssistantMessages → StreamError(step_cap_exceeded) + interrupt + Done (Pitfall 5). |
| T6 | ToolUseBlock(Edit) + ToolResultBlock(Edit) → FileDiff(operation='edit'). |
| T7 | ToolUseBlock(Write) + ToolResultBlock(Write) → FileDiff(operation='create'). |
| T8 | ToolUseBlock(Bash) + ToolResultBlock(Bash) → ToolResult (D-02 — non-edit tools never emit FileDiff). |
| T9 | Cost cap mid-stream → StreamError(cost_cap_exceeded) + interrupt + Done. |
| T10 | Cancellation within 2 s: interrupt called, disconnect called, terminal chunk Done. |
| T11 | Missing ANTHROPIC_API_KEY raises in `__init__`. |
| T12 | ResultMessage.total_cost_usd=0.042 → Done.cost_usd == 0.042. |
| T13 | cwd=None → `tempfile.mkdtemp(prefix='pomu-cc-')` called. |
| T14 | Workspace cleanup on happy path (mkdtemp dir gone after stream). |
| T15 | cwd=str(tmp_path) → user directory survives stream. |
| T16 | disconnect() called in finally even on mid-stream exception. |
| T17 | ProcessError → StreamError(code='provider_unavailable'). |
| T18 | AdapterOptions.routing_signals passes through to Done.routing_signals. |

## ALLOWED_TOOLS Lock

```python
ALLOWED_TOOLS: Final[list[str]] = ["Read", "Edit", "Write", "Bash", "Glob", "Grep"]
```

Confirmed via `grep -q 'ALLOWED_TOOLS: Final\[list\[str\]\] = \["Read", "Edit", "Write", "Bash", "Glob", "Grep"\]' apps/api/backends/claude_code/adapter.py`. CONTEXT discretion line 142.

## BACKEND-09 Watchdog Env Var Verification

```
$ uv run python -c "import apps.api.backends.claude_code; import os; \
    assert os.environ['CLAUDE_ENABLE_STREAM_WATCHDOG'] == '1'; print('OK')"
OK
```

The package-level `os.environ.setdefault("CLAUDE_ENABLE_STREAM_WATCHDOG", "1")` runs on import. The `setdefault` semantic (NOT assignment) is verified by `test_watchdog_env_var_respects_existing_value` — setting the var to `"0"` BEFORE import preserves `"0"`.

## D-19 Invariant Pass Count for claude_code

```
$ uv run pytest -m 'not live' apps/api/backends/tests/test_adapter_contract.py -k claude_code -v
collected 18 items / 12 deselected / 6 selected
apps/api/backends/tests/test_adapter_contract.py ......                  [100%]
======================= 6 passed, 12 deselected in 3.32s =======================
```

- ✓ `test_happy_path_terminates_with_done[claude_code]`
- ✓ `test_cost_cap_aborts[claude_code]`
- ✓ `test_step_cap_aborts[claude_code]` — **real pass** (not skip; the openrouter variant skips with "N/A single round-trip", but claude_code has a per-iteration step cap and the fake response sequence trips it).
- ✓ `test_cancellation_within_2_seconds[claude_code]`
- ✓ `test_done_always_lands[claude_code]`
- ✓ `test_missing_api_key_raises_before_stream[claude_code]`

## Live Test Instructions

```bash
ANTHROPIC_API_KEY=sk-ant-... uv run pytest -m live apps/api/backends/claude_code/
```

Without the key the test is skipped (still collectable). The test ceiling-checks `cost_usd < 0.20` so it cannot accidentally bill a real account more than ~20¢. The workspace uses `tmp_path` (cwd opt-in) so the created `hello.py` is inspectable after the stream.

## Decisions Made

1. **Duck-typed message / block dispatch via `_is_*` helpers.** Raw `isinstance(msg, AssistantMessage)` checks fail when tests inject `FakeAssistantMessage` (different class object). The plan's Task 1 fakes block (line 251) anticipated this choice and recommended duck-typed dispatch. Implementation: a single `_is_assistant(msg)` helper that returns `isinstance(msg, AssistantMessage) or type(msg).__name__ in {"AssistantMessage", "FakeAssistantMessage"}` (and the same shape for User/System/Result/TextBlock/ToolUse/ToolResult/Thinking). Real SDK objects match via the `isinstance` leg; Fake* objects match via the class-name leg.

2. **`client_factory` bypasses the constructor's `ANTHROPIC_API_KEY` preflight.** The D-19 shared contract suite's `adapter_factory` fixture passes `client_factory=lambda options: fake` and no `api_key=`. Without a bypass the contract suite couldn't construct the adapter. The standalone `test_missing_api_key_raises_before_stream` invariant (no factory, no env var) still raises correctly because both gates must be open for the preflight to pass.

3. **Inline workspace lifecycle (not the `ephemeral_workspace` context manager).** RESEARCH Pattern 4 lines 722-727 use an inline `if/else` (mkdtemp + cleanup flag, rmtree in `finally`) for cleaner exception handling around the SDK calls. The standalone `ephemeral_workspace` async context manager remains in `workspace.py` because the plan's `<files>` block requires it and `test_workspace.py` exercises it directly. Both paths share the same `pomu-cc-` prefix and ignore-errors rmtree contract.

4. **`ClaudeCodeAdapter` re-export deferred to Task 2 commit.** Mirrors Plan 02-01 Decision #4. Writing `from .adapter import ClaudeCodeAdapter` at Task 1 commit time would have made the package unimportable (no `adapter.py` yet). Task 1 commit ships an `__init__.py` with only the watchdog setdefault; Task 2 commit replaces it with the canonical re-export.

5. **`step_cap_aborts` D-19 contract test passes as a real positive for claude_code.** The openrouter variant skips this case ("single round-trip"); the claude_code adapter has a per-AssistantMessage step counter and the conftest's fake yields multiple AssistantMessages, so the cap trips on the second one. All 6 D-19 invariants are real passes — there is no `pytest.skip` for claude_code in the contract suite.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking issue] `isinstance` dispatch incompatible with test fakes**

- **Found during:** Task 3 (first run of `test_happy_path_emits_textdelta_and_done`).
- **Issue:** RESEARCH Pattern 4's literal source uses `isinstance(msg, AssistantMessage)` against the SDK's class objects. When tests inject `FakeAssistantMessage` (a separate dataclass in `tests/fakes.py`), the `isinstance` check returns False and the message dispatch silently drops every block. The first happy-path test reported `len(text_deltas) == 0` against an expected 1.
- **Fix:** Introduced eight duck-typed helper pairs (`_is_assistant`, `_is_user`, `_is_system`, `_is_result`, `_is_text_block`, `_is_tool_use`, `_is_tool_result`, `_is_thinking`). Each returns `isinstance(obj, RealSDKClass) or type(obj).__name__ in _NAME_SET`. Real SDK objects still match via the `isinstance` leg (the live test will exercise this path); Fake* objects match via the class-name leg. The plan's Task 1 fakes block (line 251) explicitly anticipated this choice and recommended duck-typed dispatch.
- **Files modified:** `apps/api/backends/claude_code/adapter.py` (helper-pair additions + dispatch site swaps).
- **Verification:** All 18 unit tests + 6 D-19 invariants pass.
- **Committed in:** `f247e40` (Task 3 — bundled with the test files that exposed the bug, per the TDD GREEN cycle).
- **Why this is a Rule 3 fix and not a Rule 4 architectural change:** The behavior contract (every AssistantMessage emits one ChatChunk per TextBlock/ToolUseBlock; every UserMessage(ToolResultBlock) emits one ToolResult or FileDiff) is unchanged. Only the dispatch mechanism is updated to satisfy the contract under both production-SDK and test-fake call patterns. The change is reversible and does not introduce a new public API.

**2. [Rule 3 — Blocking issue] Constructor preflight breaks D-19 `adapter_factory` fixture**

- **Found during:** Task 3 (first run of `test_happy_path_terminates_with_done[claude_code]`).
- **Issue:** The constructor's `ANTHROPIC_API_KEY` preflight (D-19 invariant #6) raises `RuntimeError` when no `api_key` is passed AND `ANTHROPIC_API_KEY` is absent from the env. The D-19 shared contract suite's `adapter_factory` fixture in `apps/api/backends/tests/conftest.py:354-359` constructs the adapter with `client_factory=lambda options: fake_claude_sdk_client` and NO `api_key=`. There is no `ANTHROPIC_API_KEY` in the test environment. Result: every claude_code D-19 contract case raised `RuntimeError` before yielding any chunk, and 5/6 contract tests failed.
- **Fix:** Skip the preflight when `client_factory` is provided. The factory is the test-injection escape valve — when present, the real SDK is bypassed, so the `ANTHROPIC_API_KEY` check is meaningless. The standalone `test_missing_api_key_raises_before_stream[claude_code]` invariant (which constructs `ClaudeCodeAdapter()` with no factory and no env var) still raises correctly because BOTH gates must be open.
- **Files modified:** `apps/api/backends/claude_code/adapter.py` (constructor — added `client_factory is None` to the preflight condition).
- **Verification:** All 6 D-19 invariants pass for claude_code; `test_missing_api_key_raises` in our own suite still raises.
- **Committed in:** `f247e40` (Task 3).
- **Why this is a Rule 3 fix and not a Rule 4 architectural change:** The behavior contract (missing key surfaces as a typed exception BEFORE the first stream chunk in production) is unchanged. Only the test-injection path is unblocked. Production code does not pass `client_factory` so the preflight always runs.

---

**Total deviations:** 2 Rule-3 blocking-issue fixes (both surfaced during the Task 3 RED phase and committed alongside the test files that exposed them, per TDD GREEN cycle).

**Impact on plan:** Both fixes preserve the behavior contracts named in the plan (D-02 FileDiff dispatch; D-19 invariant #6 typed-exception missing-key surfacing). Neither change introduces new public APIs, new dependencies, or new architectural surface. No scope creep.

## Authentication Gates

None. All work in this plan ran offline against fakes. The opt-in live test is preserved for when the user supplies `ANTHROPIC_API_KEY` per the BYOK contract.

## Verification Commands Re-run at Completion

```bash
# 1. claude_code unit + watchdog/workspace/adapter tests.
$ uv run pytest -m 'not live' apps/api/backends/claude_code/tests/ -q
.......................                                                  [100%]
23 passed in 0.41s

# 2. D-19 shared contract suite for claude_code parameterization (6/6).
$ uv run pytest -m 'not live' apps/api/backends/tests/test_adapter_contract.py -k claude_code -v
collected 18 items / 12 deselected / 6 selected
apps/api/backends/tests/test_adapter_contract.py ......                  [100%]
======================= 6 passed, 12 deselected in 3.32s =======================

# 3. Phase 1 D-18 import-graph guard (no regression).
$ uv run pytest src/routing/tests/test_decide_smoke.py -x -q
.......                                                                  [100%]

# 4. CLI help — accepts --prompt, --model, --max-cost-usd, --max-steps, --cwd.
$ uv run python -m apps.api.backends.claude_code --help
usage: python -m apps.api.backends.claude_code [-h] --prompt PROMPT
                                               [--model MODEL]
                                               [--max-cost-usd MAX_COST_USD]
                                               [--max-steps MAX_STEPS]
                                               [--cwd CWD]
...

# 5. BACKEND-09 watchdog env-var side effect.
$ uv run python -c "import apps.api.backends.claude_code; import os; \
    assert os.environ['CLAUDE_ENABLE_STREAM_WATCHDOG'] == '1'; print('OK')"
OK

# 6. OSS-06 deprecated SDK absent (the one match is a positive
#    enforcement assertion in test_adapter.py).
$ grep -r "claude_code_sdk" apps/ | wc -l
1

# 7. Whole-repo test pass (no regressions in src/* or apps/*).
$ uv run pytest -m 'not live'
.............................s.......................................... [ 34%]
........................................................................ [ 68%]
......s..ss.s..s..s..s...........................................        [100%]
201 passed, 8 skipped, 2 deselected in 71.01s
```

## Next Plan Readiness

Wave 1 Plan 03 (computer-use adapter) can now follow the locked module layout — second confirmation after Plan 02-01:

- `apps/api/backends/<backend>/__init__.py` (re-export `XxxAdapter`).
- `apps/api/backends/<backend>/__main__.py` (CLI mirror, parametrized on backend).
- `apps/api/backends/<backend>/adapter.py` (BackendAdapter Protocol impl).
- `apps/api/backends/<backend>/cost.py` (CostTracker subclass).
- `apps/api/backends/<backend>/errors.py` (PROVIDER_ERROR_MAP + map_provider_error).
- `apps/api/backends/<backend>/tests/{__init__,conftest,fakes,test_adapter,test_live}.py`.
- For backends with substate (workspace, screen): add a dedicated `<state>.py` module + matching `tests/test_<state>.py` (claude_code added `workspace.py` + `step_counter.py`).

Plan 03's computer_use adapter will need its own `screen.py` (Playwright lifecycle), `coords.py` (1280×720 normalization), and `recovery.py` (W-04 stuck-loop bailout). The D-19 shared contract suite at `apps/api/backends/tests/test_adapter_contract.py` activates automatically when Plan 03's adapter lands — `conftest.adapter_factory` already has the `try/except ImportError → pytest.skip` lazy import for `computer_use.adapter.ComputerUseAdapter`.

## Self-Check: PASSED

All 14 files claimed in the SUMMARY exist; all 3 task commits exist in the git log.

```
$ for f in apps/api/backends/claude_code/__init__.py \
          apps/api/backends/claude_code/__main__.py \
          apps/api/backends/claude_code/adapter.py \
          apps/api/backends/claude_code/cost.py \
          apps/api/backends/claude_code/errors.py \
          apps/api/backends/claude_code/step_counter.py \
          apps/api/backends/claude_code/workspace.py \
          apps/api/backends/claude_code/tests/__init__.py \
          apps/api/backends/claude_code/tests/conftest.py \
          apps/api/backends/claude_code/tests/fakes.py \
          apps/api/backends/claude_code/tests/test_adapter.py \
          apps/api/backends/claude_code/tests/test_workspace.py \
          apps/api/backends/claude_code/tests/test_watchdog_env.py \
          apps/api/backends/claude_code/tests/test_live.py; do
    [ -f "$f" ] && echo "FOUND: $f" || echo "MISSING: $f"
done

$ git log --oneline --all | grep -E "6d2a3ec|890bf1b|f247e40"
f247e40 test(02-02): add Claude Code adapter tests, CLI, live smoke, D-19 pass
890bf1b feat(02-02): implement ClaudeCodeAdapter with step cap + cancellation + FileDiff
6d2a3ec test(02-02): add Claude Code watchdog env, step counter, workspace, cost, errors
```

All 14 created files present; all 3 task commits present.

---

*Phase: 02-backend-adapters-chatchunk-contract*
*Plan: 02*
*Completed: 2026-05-15*
