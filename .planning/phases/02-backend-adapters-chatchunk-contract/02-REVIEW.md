---
phase: 02-backend-adapters-chatchunk-contract
reviewed: 2026-05-15T18:30:00Z
depth: standard
files_reviewed: 23
files_reviewed_list:
  - .github/workflows/ci.yml
  - .github/workflows/live-smoke.yml
  - apps/api/backends/chunks.py
  - apps/api/backends/claude_code/adapter.py
  - apps/api/backends/claude_code/cost.py
  - apps/api/backends/claude_code/errors.py
  - apps/api/backends/claude_code/step_counter.py
  - apps/api/backends/claude_code/workspace.py
  - apps/api/backends/computer_use/adapter.py
  - apps/api/backends/computer_use/cost.py
  - apps/api/backends/computer_use/errors.py
  - apps/api/backends/computer_use/screen.py
  - apps/api/backends/computer_use/step_counter.py
  - apps/api/backends/cost.py
  - apps/api/backends/keystore.py
  - apps/api/backends/logging_filter.py
  - apps/api/backends/openrouter/adapter.py
  - apps/api/backends/openrouter/cost.py
  - apps/api/backends/openrouter/errors.py
  - apps/api/backends/pricing.py
  - apps/api/backends/protocol.py
  - scripts/no-deprecated-sdk.sh
  - scripts/no-secrets.sh
findings:
  critical: 5
  warning: 9
  info: 7
  total: 21
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-05-15T18:30:00Z
**Depth:** standard
**Files Reviewed:** 23
**Status:** issues_found

## Summary

Phase 2 ships three async backend adapters (OpenRouter / Claude Code / computer-use), a shared `ChatChunk` Pydantic union, `KeyStore`, `RedactionFilter`, `PricingTable`, `CostTracker`, and CI enforcement. The architecture is well thought out — SECURE-05 opt-in is verified at constructor time, cancellation paths emit the terminal `StreamError`+`Done` pair before re-raising, and the D-19 shared contract suite parametrizes across all three adapters.

However, adversarial review surfaced **five Critical bugs** that ship breaking or near-breaking behaviour:

1. **`ClaudeCodeAdapter` reads `tool_name`/`input` from `ToolResultBlock`, fields that do not exist on the real `claude_agent_sdk.ToolResultBlock`** (verified against installed `claude_agent_sdk==0.1.81`). The live smoke test cannot pass — `FileDiff` will never be emitted in production.
2. **`ComputerUseCostTracker.record_iteration_usage` uses `+=` while its docstring claims "Override the running estimate"**, causing per-iteration provider tokens to be double-counted with the char/4 running estimate.
3. **`StreamError.message` carries `str(exc)` unredacted through SSE to the client** — provider SDK exceptions can contain echoed API keys or full request URLs and bypass the `RedactionFilter` entirely.
4. **`scripts/no-secrets.sh` regex set is OUT OF SYNC with `logging_filter.SECRET_PATTERNS`** despite the docstring asserting "The three patterns intentionally MATCH the pre-commit hook." Both the OpenAI alphabet and Bearer whitespace differ.
5. **`Bearer sk-…` style headers are mis-redacted** because the OpenAI regex `sk-[A-Za-z0-9_-]{20,}` fires before the Bearer regex, leaving the literal "Bearer " prefix attached to a redacted body.

Nine Warnings + seven Info items round out the report. The Critical findings should be fixed before this code ships; the Warnings should be addressed before Phase 3 wires the adapters into FastAPI SSE.

## Critical Issues

### CR-01: Claude Code adapter reads non-existent fields from `ToolResultBlock`

**File:** `apps/api/backends/claude_code/adapter.py:362-372`
**Issue:** The adapter consumes `getattr(block, "tool_name", "")` and `getattr(block, "input", None)` from a `ToolResultBlock`, then branches on `tool_name in ("Edit", "Write")` to emit `FileDiff` instead of `ToolResult`. The installed `claude_agent_sdk==0.1.81` defines `ToolResultBlock` with only three fields: `tool_use_id`, `content`, and `is_error` (see `.venv/lib/python3.11/site-packages/claude_agent_sdk/types.py:943-949`). The adapter's reliance on `tool_name`/`input` works ONLY because `FakeToolResultBlock` in `tests/fakes.py:55-67` adds them as test-only fields. On the real SDK these `getattr` calls return their defaults (`""` and `None`), the `tool_name in ("Edit", "Write")` branch never fires, and every tool result emits a `ToolResult` chunk instead of `FileDiff`. The live smoke test `test_live_create_hello_py` asserts `file_diffs, "expected at least one FileDiff chunk"` and will fail.

**Fix:** Track `tool_use_id → (tool_name, input)` at the `ToolUseBlock` emit site, then look it up on the matching `ToolResultBlock`. Example:

```python
# In stream():
tool_use_index: dict[str, tuple[str, dict]] = {}  # id -> (name, input)

# When yielding ToolCall (AssistantMessage branch):
if _is_tool_use(block):
    tool_id = getattr(block, "id", "")
    tool_name = getattr(block, "name", "")
    tool_input = getattr(block, "input", {}) or {}
    tool_use_index[tool_id] = (tool_name, tool_input)
    yield ToolCall(tool_call_id=tool_id, tool_name=tool_name, arguments=tool_input)

# When handling ToolResultBlock (UserMessage branch):
if _is_tool_result(block):
    tool_use_id = getattr(block, "tool_use_id", "")
    content = getattr(block, "content", "")
    is_error = getattr(block, "is_error", False)
    tool_name, tool_input = tool_use_index.get(tool_use_id, ("", {}))
    if tool_name in ("Edit", "Write"):
        path = tool_input.get("path", "") if isinstance(tool_input, dict) else ""
        yield FileDiff(
            tool_call_id=tool_use_id,
            path=path,
            diff=str(content),
            operation="edit" if tool_name == "Edit" else "create",
        )
    else:
        # ... existing ToolResult branch
```

Update `FakeToolResultBlock` to drop the `tool_name`/`input` fields so the tests exercise the same lookup path. Add a unit test that verifies `FileDiff` emission works against a `FakeToolResultBlock` that does NOT carry `tool_name`/`input`.

### CR-02: `ComputerUseCostTracker.record_iteration_usage` accumulates instead of overriding

**File:** `apps/api/backends/computer_use/cost.py:97-117`
**Issue:** The method docstring (line 105) states "Override the running estimate with provider-reported usage" but the implementation uses `+=` (lines 114-115):

```python
self._tokens_in += int(input_tokens)
self._tokens_out += int(output_tokens)
```

Per-iteration the adapter calls `record_output_text` for every `text_delta` event (line 351 in `adapter.py`), accumulating char/4 estimates into `_tokens_out`. Then `record_iteration_usage` adds the authoritative output tokens ON TOP of those estimates rather than replacing them. The net `_tokens_out` reported in `Done.tokens_out` and used by `over_cap()` is `running_estimate + authoritative_count`, inflating both the displayed token count and the cap arithmetic. The base `Claude_code` and `openrouter` trackers correctly use assignment (`self._tokens_in = ...`).

The bug is masked in `test_iteration_usage_recorded` because the happy-path stream uses `text="ok"` (length 2), and `len("ok") // 4 = 0` — no running estimate is recorded, so the test cannot distinguish `+=` from `=`.

**Fix:** Either replace `+=` with `=` to match the docstring (cleanest), OR clear the running estimate before applying:

```python
def record_iteration_usage(
    self,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read: int = 0,
    cache_write: int = 0,
) -> None:
    # Override per docstring — authoritative SDK counts replace the
    # char/4 running estimate accumulated from text_delta events.
    self._tokens_in = int(input_tokens)
    self._tokens_out = int(output_tokens)
    self._cache_read_total += int(cache_read)
    self._cache_write_total += int(cache_write)
```

If multi-iteration accumulation is the actual intent, fix the docstring and add a separate reset hook the adapter calls before each iteration's `record_output_text` loop. Add a regression test using `text="x" * 40` (10 char/4 tokens) plus `input_tokens=10, output_tokens=5` and assert `done.tokens_out == 5` (not 15).

### CR-03: `StreamError.message` passes unredacted SDK exception text through SSE

**File:** `apps/api/backends/openrouter/adapter.py:317, 325, 338, 347`; `apps/api/backends/claude_code/adapter.py:461, 469, 478`; `apps/api/backends/computer_use/adapter.py:543, 551, 561, 570`
**Issue:** The adapter passes `message=str(exc)` directly into the `StreamError` chunk, which is serialised via `chunk.model_dump_json()` and forwarded to the user's chat UI. `_redact_text`/`RedactionFilter` only run on `logging.LogRecord` instances (see `logging_filter.py:65-87`) — they do NOT touch `ChatChunk` payloads. `openai.APIStatusError` and `anthropic.APIStatusError` both expose `__str__` that includes the request URL and may include the response body. If the provider echoes the API key in an error body (some providers do, e.g. "invalid auth header: Bearer sk-…") or if the request URL contains a token, the key lands in the user-visible `StreamError`. The SECURE-01 logs-redaction guarantee does not extend to SSE chunks.

**Fix:** Apply `_redact_text` to every `StreamError.message` before yielding:

```python
# At the top of each adapter:
from apps.api.backends.logging_filter import _redact_text

# In every except block:
except AuthenticationError as exc:
    yield StreamError(
        code="auth_failed",
        message=_redact_text(str(exc)),
        retriable=False,
    )
```

OR (more conservative): produce a constant operator-friendly message and log the full `str(exc)` separately:

```python
except AuthenticationError as exc:
    logger.warning("OpenRouter auth failed: %s", exc)  # gets redacted
    yield StreamError(
        code="auth_failed",
        message="Authentication failed — check your API key.",  # constant
        retriable=False,
    )
```

The internal-error path (`message=f"{type(exc).__name__}: {exc}"`) is the highest risk and should be redacted unconditionally.

### CR-04: Pre-commit `no-secrets.sh` regex set drifts from `logging_filter.SECRET_PATTERNS`

**File:** `scripts/no-secrets.sh:14`; `apps/api/backends/logging_filter.py:50-54`
**Issue:** `logging_filter.py:31-32` documents: "The three patterns intentionally MATCH the pre-commit hook in Plan 04 (`scripts/no-secrets.sh`). Keeping the regex set in sync means the unit-test coverage for one path also protects the other." The actual regex sets disagree on two of three patterns:

| Pattern | logging_filter.py | scripts/no-secrets.sh |
|---|---|---|
| Anthropic | `sk-ant-[A-Za-z0-9_-]{8,}` | `sk-ant-[A-Za-z0-9_-]{8,}` (matches) |
| OpenAI | `sk-[A-Za-z0-9_-]{20,}` (incl. `_-`) | `sk-[A-Za-z0-9]{20,}` (alphanumeric only) |
| Bearer | `Bearer\s+[A-Za-z0-9_.\-]{20,}` (`\s+` = any whitespace) | `Bearer [A-Za-z0-9_.-]{20,}` (literal space) |

Consequences:
- An OpenAI key containing `_` or `-` after `sk-` (e.g. `sk-proj_abcdef...20chars`) is NOT caught by the pre-commit hook but IS redacted by the filter — and vice versa: a token with `_` would pass `commit` but be redacted at runtime, an inconsistent contract.
- A `Bearer\t<token>` (tab) or `Bearer  <token>` (multiple spaces) is redacted by the filter but passes the pre-commit hook unchanged.

**Fix:** Synchronise both regex sets. Recommended unified set:

```bash
# scripts/no-secrets.sh
grep -E '(sk-ant-[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9_-]{20,}|Bearer[[:space:]]+[A-Za-z0-9_.-]{20,})'
```

```python
# apps/api/backends/logging_filter.py — already correct, ensure both
# files reference a shared regex source. Consider lifting the patterns
# into config/secrets-patterns.txt or a Python module that the shell
# script reads via `grep -f`.
```

Add a CI step that loads both regex sets and asserts equivalence so future drift fails the build.

### CR-05: Anthropic-style Bearer headers leave the "Bearer " prefix dangling

**File:** `apps/api/backends/logging_filter.py:50-54`
**Issue:** `SECRET_PATTERNS` runs in order:
1. `sk-ant-…` → `***REDACTED-ANTHROPIC***`
2. `sk-…` → `***REDACTED-OPENAI***`
3. `Bearer\s+…` → `Bearer ***REDACTED***`

When a log line contains `Bearer sk-ant-api03-XYZ1234567890ABCDEFGHIJKL` (e.g. the actual `Authorization` header the Anthropic SDK constructs), the FIRST pattern matches the body and rewrites it to `Bearer ***REDACTED-ANTHROPIC***`. The result leaks the structure of the auth scheme:

```
"auth header: Bearer ***REDACTED-ANTHROPIC***"
```

The literal word `Bearer` is preserved verbatim in the log. While this does NOT leak the key, it leaks the fact that an auth header existed, and downstream regex-scrubbers checking for `Bearer ***REDACTED***` (the Bearer-pattern result) will not match. The unit test `test_redaction_replaces_bearer_tokens` deliberately uses a non-`sk-` payload (line 51) to dodge this case — the failure mode is uncovered.

**Fix:** Either reverse the pattern order (Bearer first, then sk-/sk-ant-), OR change the sk-/sk-ant- replacements to swallow an optional leading `Bearer `:

```python
SECRET_PATTERNS: Final[list[tuple[re.Pattern[str], str]]] = [
    # Bearer first so Bearer-prefixed keys redact as a unit.
    (re.compile(r"Bearer\s+sk-ant-[A-Za-z0-9_-]{8,}"), "Bearer ***REDACTED-ANTHROPIC***"),
    (re.compile(r"Bearer\s+sk-[A-Za-z0-9_-]{20,}"), "Bearer ***REDACTED-OPENAI***"),
    (re.compile(r"Bearer\s+[A-Za-z0-9_.\-]{20,}"), "Bearer ***REDACTED***"),
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}"), "***REDACTED-ANTHROPIC***"),
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "***REDACTED-OPENAI***"),
]
```

Add a regression test: `logger.info("Authorization: Bearer sk-ant-api03-XYZ1234567890ABCDEFGHIJKL")` then assert `"Bearer" not in caplog.text` (or just `"sk-ant-" not in caplog.text` AND `"***REDACTED-ANTHROPIC***" in caplog.text` AND the unredacted "Bearer" prefix is rewritten to a single redaction marker).

## Warnings

### WR-01: Unbounded `asyncio.sleep` in the `wait` action

**File:** `apps/api/backends/computer_use/adapter.py:647-650`
**Issue:** The `wait` action does `duration = float(params.get("duration", 1.0) or 1.0)` then `await asyncio.sleep(duration)`. There is no upper bound. A model can pass `duration=86400` and pin the stream for 24 hours. The `max_cost_usd` cap does not help (no tokens are consumed during sleep). The `max_steps` cap does not help (this is inside a single step). Only client-side cancellation breaks out.

**Fix:** Clamp to a sane upper bound:

```python
if action == "wait":
    raw = float(params.get("duration", 1.0) or 1.0)
    duration = min(max(raw, 0.0), 30.0)  # cap at 30 s
    await asyncio.sleep(duration)
    return (f"Waited {duration}s.", False)
```

### WR-02: `max_cost_usd=0.0` and `max_steps=0` silently fall back to defaults

**File:** `apps/api/backends/openrouter/adapter.py:197`; `apps/api/backends/claude_code/adapter.py:294-295`; `apps/api/backends/computer_use/adapter.py:262-263`
**Issue:** All three adapters use `or` to default missing options:

```python
max_cost_usd = options.max_cost_usd or self._max_cost
max_steps = options.max_steps or self._max_steps
```

The `or` operator treats `0.0` (and `0`) as falsy. A caller who wants a zero-cap "dry run" (e.g. emit a `cost_cap_exceeded` immediately to verify wiring) gets the constructor default `0.50` USD instead. This is a footgun for an explicit-control safety knob.

**Fix:** Use `is None` checks:

```python
max_cost_usd = self._max_cost if options.max_cost_usd is None else options.max_cost_usd
max_steps = self._max_steps if options.max_steps is None else options.max_steps
```

### WR-03: `errors.py` modules are dead code — adapters never call `map_provider_error`

**File:** `apps/api/backends/openrouter/errors.py`; `apps/api/backends/claude_code/errors.py`; `apps/api/backends/computer_use/errors.py`
**Issue:** Every adapter inlines its provider-exception → `StreamError` mapping inside `except` blocks. The shared `map_provider_error` function and `PROVIDER_ERROR_MAP` table are tested in `tests/test_cost_and_errors.py` but NEVER imported by the adapter modules themselves. Each adapter could regress its error mapping without the tests noticing (the tests prove the *mapping module* works, not that the adapter *uses* it).

```bash
$ grep -rn "from apps.api.backends.openrouter.errors\|from apps.api.backends.claude_code.errors\|from apps.api.backends.computer_use.errors" /apps/api/
# Only matches in test files — never in adapter.py.
```

**Fix:** Pick one approach:

1. **Wire the adapters to use `map_provider_error`:**

```python
# In adapter.py except blocks:
except (AuthenticationError, APITimeoutError, APIStatusError) as exc:
    code, message, retriable = map_provider_error(exc)
    # ... refine 429-vs-other inside the APIStatusError branch
    yield StreamError(code=code, message=message, retriable=retriable)
```

2. **Or delete `errors.py` and update the tests** to exercise the adapter's inline mapping directly.

The status quo leaves a maintenance trap.

### WR-04: `asyncio.get_event_loop()` is deprecated since Python 3.10

**File:** `apps/api/backends/openrouter/adapter.py:211, 286, 308`; `apps/api/backends/claude_code/adapter.py:302, 426, 453`; `apps/api/backends/computer_use/adapter.py:271, 511, 534`
**Issue:** Every adapter uses `asyncio.get_event_loop().time()` for latency measurement. Since Python 3.10, `asyncio.get_event_loop()` emits a `DeprecationWarning` when called from outside a coroutine and was scheduled for removal. The intended replacement when inside a running coroutine is `asyncio.get_running_loop()`. For wall-clock time, `time.monotonic()` is the standard idiom and doesn't couple latency tracking to the event loop.

**Fix:**

```python
import time

# At stream() top:
start_t = time.monotonic()

# At each measurement point:
latency_ms = int((time.monotonic() - start_t) * 1000)
```

This removes the deprecation entirely.

### WR-05: `permission_mode=None` defaults to interactive prompts in non-TTY environments

**File:** `apps/api/backends/claude_code/adapter.py:305-310`
**Issue:** `ClaudeAgentOptions` is built without `permission_mode`, with the comment "defaults to user-controlled". On the installed `claude_agent_sdk==0.1.81`, `permission_mode` defaults to `"default"` (`types.py:1628`), which on the Claude CLI subprocess produces interactive permission prompts for tool invocations. In a Phase 3 FastAPI server context (no TTY, no stdin), the prompt hangs the subprocess until the watchdog or step cap fires. Phase 2 happens to work because the live smoke test runs against a developer's terminal with Claude CLI already configured, but Phase 3 will regress.

**Fix:** Either pin `permission_mode="acceptEdits"` for production (auto-accept Edit/Write within the allowed-tools sandbox), or expose `permission_mode` as an `AdapterOptions` field with a documented default. Add a non-TTY regression test that spawns the adapter with stdin closed and asserts the stream terminates within `max_steps × 5 s`.

### WR-06: `PricingTable.get` returns the mutable underlying dict

**File:** `apps/api/backends/pricing.py:80-88`
**Issue:** `get()` returns `self._table.get(model_id) or self._table["_default"]` — both branches return the actual dict reference inside `self._table`. Callers can mutate the table:

```python
rates = table.get("openai/gpt-5")
rates["input_per_mtok"] = 0.0  # poisons every future tracker call
```

`CostTracker.total()` uses `rates["input_per_mtok"]` directly. A buggy or malicious caller could disable the cost cap by setting both rates to 0.

**Fix:** Return a copy:

```python
def get(self, model_id: str) -> dict[str, float]:
    row = self._table.get(model_id) or self._table["_default"]
    return dict(row)  # defensive copy
```

### WR-07: `_merge_openrouter_snapshot` crashes on entries missing `id`

**File:** `apps/api/backends/pricing.py:138`
**Issue:** Line 138 uses `model["id"]` directly. Earlier in the loop (line 130) `pricing = model.get("pricing") or {}` uses defensive `get`, but the `id` lookup is not guarded. A malformed snapshot entry without `id` raises `KeyError`, which is NOT caught by the surrounding `try/except (TypeError, ValueError)` (lines 133-137). The result is the entire merge aborts mid-stream and the table is left in an inconsistent partial state.

**Fix:**

```python
def _merge_openrouter_snapshot(self, snapshot: dict[str, Any]) -> None:
    for model in snapshot.get("data", []):
        model_id = model.get("id")
        if not model_id:
            continue
        pricing = model.get("pricing") or {}
        if "prompt" not in pricing or "completion" not in pricing:
            continue
        try:
            input_per_mtok = float(pricing["prompt"]) * 1_000_000
            output_per_mtok = float(pricing["completion"]) * 1_000_000
        except (TypeError, ValueError):
            continue
        self._table[model_id] = {
            "input_per_mtok": input_per_mtok,
            "output_per_mtok": output_per_mtok,
        }
```

### WR-08: `ephemeral_workspace` context manager exists but is unused

**File:** `apps/api/backends/claude_code/workspace.py`; `apps/api/backends/claude_code/adapter.py:286-291`
**Issue:** `workspace.py` defines `ephemeral_workspace` (and `test_workspace.py` tests it), but the adapter inlines the same mkdtemp/rmtree logic (lines 286-291 and 492-496) with the comment "the inline form yields cleaner exception handling around the SDK calls." Two divergent code paths for the same lifecycle. Future fixes (e.g. CR-04 leak when an exception happens between mkdtemp and the try-block) will likely be applied to only one path. The adapter's inline form lacks the `try/finally` guarantee the context manager provides.

**Fix:** Either:
1. Delete `workspace.py` + `test_workspace.py` and document the inline form as canonical.
2. Refactor the adapter to use `async with ephemeral_workspace(options.cwd) as (workspace, cleanup_workspace):` and lift the SDK try/except inside the async-with body. The comment about "cleaner exception handling" is no longer accurate — the nested `try/except` is identical either way.

### WR-09: Computer-use `navigate` action allows arbitrary URL schemes

**File:** `apps/api/backends/computer_use/adapter.py:643-646`; `apps/api/backends/computer_use/screen.py:181-185`
**Issue:** `screen.goto(url)` passes any string straight to `Page.goto()`. Playwright accepts `file:///etc/passwd`, `chrome://settings`, `data:text/html,…`, and other non-`http(s)` schemes. SECURE-05 (opt-in) is the only gate — once the operator opts in, the model can read arbitrary local files via `file://` navigation + a screenshot. While the model has no `read_file` tool, the screenshot DOES return the rendered file contents as a PNG.

**Fix:** Add a scheme allow-list in `screen.goto`:

```python
async def goto(self, url: str) -> None:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"Navigation blocked: only http/https URLs allowed (got '{parsed.scheme}')"
        )
    assert self._page is not None, "goto called before start()"
    await self._page.goto(url)
```

Add a regression test that asserts `goto("file:///etc/passwd")` raises `ValueError`.

## Info

### IN-01: `validation_error` is in the D-06 closed vocabulary but never emitted

**File:** `apps/api/backends/chunks.py:135`
**Issue:** The `StreamError.code` literal includes `"validation_error"`, but no adapter ever yields it. Either reserved for Phase 3 (in which case document it in a comment), or dead code.

**Fix:** Add a comment line above the literal: `# "validation_error" is reserved for Phase 3 input validation in FastAPI.`

### IN-02: `secrets.choice` over a 32-char alphabet × 6 = 30 bits of entropy

**File:** `apps/api/backends/openrouter/adapter.py:106-116`
**Issue:** The docstring says "30 bits of entropy which is plenty for de-duplicating tool calls within a single turn." A single turn might have ≤10 tool calls, so 30 bits is overkill. But the inline comment + docstring are accurate. No bug — just an observation that the entropy budget is generous.

**Fix:** No action required. Optionally drop to 4 characters (20 bits) if you want shorter IDs in the UI; OpenAI's own tool-call IDs are typically 24+ characters so 9-char `tc_xxxxxx` is fine.

### IN-03: `Final[list[str]]` annotation does not prevent mutation

**File:** `apps/api/backends/claude_code/adapter.py:175`
**Issue:** `ALLOWED_TOOLS: Final[list[str]] = ["Read", "Edit", "Write", "Bash", "Glob", "Grep"]` — `Final` prevents reassignment of the *name*, not mutation of the *list*. A future plugin could do `ALLOWED_TOOLS.append("WebSearch")` without a type-checker complaint and silently extend the v1 tool surface. The comment "the `Final` annotation makes the mutability intent explicit" overstates what `Final` provides.

**Fix:** Use a tuple instead — tuples are immutable:

```python
ALLOWED_TOOLS: Final[tuple[str, ...]] = ("Read", "Edit", "Write", "Bash", "Glob", "Grep")
```

The `claude_agent_sdk.ClaudeAgentOptions.allowed_tools` field accepts any sequence so a tuple works.

### IN-04: `import os` inside `__init__` (claude_code adapter)

**File:** `apps/api/backends/claude_code/adapter.py:248`
**Issue:** `os` is imported inside `ClaudeCodeAdapter.__init__` at line 248 even though the surrounding module does not import `os` at the top level. PEP 8 prefers top-of-module imports; the inline import is presumably to defer the lookup until construct time, but `os` is already loaded by the dotenv side-effect in `apps/api/__init__.py:55`.

**Fix:** Move `import os` to the top of `adapter.py` alongside the other stdlib imports.

### IN-05: Comment claims `key.replace` only handles known cases

**File:** `apps/api/backends/computer_use/screen.py:144-152`
**Issue:** `normalized = key.replace("ctrl", "Control").replace("super", "Meta")` is a naive substring replace. The string `"alt+ctrlw"` would yield `"alt+Controlw"` (unlikely to come from Anthropic, but possible from a malicious prompt that influences the tool args). Also misses `cmd` → `Meta` mapping that some platforms use.

**Fix:** Word-boundary or token-split replacement:

```python
def _normalize_key(key: str) -> str:
    parts = key.split("+")
    mapping = {"ctrl": "Control", "super": "Meta", "cmd": "Meta", "alt": "Alt", "shift": "Shift"}
    return "+".join(mapping.get(p.lower(), p) for p in parts)
```

### IN-06: Provider-truth cost cannot trigger cost cap (intentional but undocumented)

**File:** `apps/api/backends/openrouter/adapter.py:225-230, 274-283`
**Issue:** When the final usage chunk lands, the adapter calls `tracker.record_final_usage(...)` (line 226-228) which overrides `_tokens_in`/`_tokens_out`, then immediately `continue`s — skipping the `tracker.over_cap()` check on line 274. The final-cost-based cap is therefore impossible to trigger for OpenRouter. This is probably intentional (the stream is over by the final chunk) but should be documented.

**Fix:** Add a comment next to line 230: `# Final usage chunk — stream is ending anyway, no cap check needed.`

### IN-07: `chunks.py` `image_b64` is `str | None` but `Done.tokens_in` is `int | None` — inconsistent

**File:** `apps/api/backends/chunks.py:101-114, 142-157`
**Issue:** Both `Screenshot.image_b64` and `Done.tokens_in` accept `None`, but the semantics differ. `Screenshot` mandates EXACTLY ONE of `image_b64`/`image_ref` to be non-None (per the docstring) but Pydantic does not enforce this — a `Screenshot(step=1)` with both fields None validates successfully. Phase 3's STORE-04 swap depends on this invariant.

**Fix:** Add a `model_validator(mode="after")`:

```python
from pydantic import model_validator

class Screenshot(BaseModel):
    type: Literal["screenshot"] = "screenshot"
    step: int
    image_b64: str | None = None
    image_ref: str | None = None
    image_format: Literal["png", "jpeg"] = "png"

    @model_validator(mode="after")
    def _exactly_one_image_source(self) -> "Screenshot":
        if (self.image_b64 is None) == (self.image_ref is None):
            raise ValueError(
                "Screenshot must set exactly one of image_b64 or image_ref"
            )
        return self
```

Add a unit test that asserts `Screenshot(step=1)` (both None) and `Screenshot(step=1, image_b64="x", image_ref="r")` (both set) raise `ValidationError`.

---

_Reviewed: 2026-05-15T18:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
