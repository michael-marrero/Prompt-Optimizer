---
phase: 02-backend-adapters-chatchunk-contract
verified: 2026-05-15T18:16:38Z
status: gaps_found
score: 18/22 must-haves verified
overrides_applied: 0
re_verification:
  mode: initial
gaps:
  - truth: "Claude Code adapter emits FileDiff chunks for Edit/Write tool results (BACKEND-04, D-02, ROADMAP SC #1, Plan 02-02 must-have)"
    status: failed
    reason: "Adapter reads `tool_name` and `input` from `ToolResultBlock`, but the real `claude_agent_sdk==0.1.81` `ToolResultBlock` dataclass has only `tool_use_id`, `content`, `is_error`. `getattr(block, 'tool_name', '')` will always return `''` in production, so `tool_name in ('Edit', 'Write')` is False and the FileDiff branch is unreachable. Tests pass only because `FakeToolResultBlock` adds the non-existent fields."
    artifacts:
      - path: "apps/api/backends/claude_code/adapter.py"
        issue: "Lines 363, 367 read fields that do not exist on the installed SDK's ToolResultBlock. FileDiff is dead code in production."
      - path: "apps/api/backends/claude_code/tests/fakes.py"
        issue: "FakeToolResultBlock adds tool_name and input fields that mask the bug."
    missing:
      - "Track tool_use_id → (tool_name, input) at ToolUseBlock emit site and look up by tool_use_id on the matching ToolResultBlock."
      - "Update FakeToolResultBlock to drop tool_name/input so unit tests exercise the same lookup path as production."
      - "Add a regression test that verifies FileDiff emission against a FakeToolResultBlock with only the real SDK's three fields."
  - truth: "ComputerUseCostTracker.record_iteration_usage overrides the running token estimate with provider-authoritative counts (Plan 02-03 cost-accounting contract; ROADMAP SC #2 cap arithmetic correctness)"
    status: failed
    reason: "Method docstring claims 'Override the running estimate' but implementation uses `+=`, causing per-iteration text_delta char/4 estimates to be summed with the authoritative Anthropic usage block. Inflates both Done.tokens_out and the over_cap() arithmetic. Reproduced: text='x'*40 (10 char/4 tokens) + record_iteration_usage(output_tokens=5) yields tokens_out=15, not 5."
    artifacts:
      - path: "apps/api/backends/computer_use/cost.py"
        issue: "Lines 114-115 use `+=` for input_tokens/output_tokens; the OpenRouter and Claude Code trackers correctly use `=` (override semantics)."
    missing:
      - "Change `self._tokens_in += int(input_tokens)` to `self._tokens_in = int(input_tokens)` (and same for `_tokens_out`)."
      - "Add a regression test using text='x'*40 plus record_iteration_usage(input_tokens=10, output_tokens=5) and assert `tokens_in == 10` and `tokens_out == 5`."
  - truth: "Pre-commit `no-secrets.sh` regex set MATCHES `logging_filter.SECRET_PATTERNS` (SECURE-01/SECURE-02 contract — docstring asserts the two regex sets are intentionally synchronised)"
    status: failed
    reason: "Two of three patterns differ. OpenAI: filter uses `sk-[A-Za-z0-9_-]{20,}` (incl. `_` / `-`), hook uses `sk-[A-Za-z0-9]{20,}` (alphanumeric only). Bearer: filter uses `\\s+` (any whitespace), hook uses literal space. Verified: a key like `sk-AAAAA_AAAAAAAAAAAAAAAAAA` is redacted by the filter but NOT blocked by the pre-commit hook. Bearer with tab redacts but does not block."
    artifacts:
      - path: "scripts/no-secrets.sh"
        issue: "Line 14 — three locked D-09 regex patterns must match logging_filter.SECRET_PATTERNS exactly."
      - path: "apps/api/backends/logging_filter.py"
        issue: "Lines 50-54 declare the source-of-truth patterns whose alphabets/whitespace differ from the shell script."
    missing:
      - "Synchronise both regex sets to the unified `(sk-ant-[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9_-]{20,}|Bearer[[:space:]]+[A-Za-z0-9_.-]{20,})` form."
      - "Add a CI step (or unit test) that loads both regex sets and asserts equivalence to catch future drift."
  - truth: "Logger redaction guarantees stay coherent for canonical `Authorization: Bearer sk-ant-…` headers (SECURE-01)"
    status: failed
    reason: "Pattern order causes mis-redaction. `sk-ant-…` fires before `Bearer\\s+…`, so `Bearer sk-ant-api03-XYZ1234567890ABCDEFGHIJKL` rewrites to `Bearer ***REDACTED-ANTHROPIC***` — the `Bearer` literal stays attached. Downstream pattern-matchers looking for `Bearer ***REDACTED***` (the Bearer-branch result) will miss this case. Reproduced live; the existing unit test deliberately uses a non-`sk-` payload to dodge the issue."
    artifacts:
      - path: "apps/api/backends/logging_filter.py"
        issue: "SECRET_PATTERNS list at lines 50-54 — order makes the sk-ant- rule strip the auth-scheme prefix but leave `Bearer ` verbatim."
    missing:
      - "Reorder patterns (Bearer-prefixed forms FIRST), or add Bearer-prefixed sk-ant-/sk- variants whose replacement swallows the leading `Bearer\\s+`."
      - "Add a regression test asserting `logger.info('Authorization: Bearer sk-ant-…')` produces no literal `Bearer` followed by `***REDACTED-…***`."
human_verification:
  - test: "End-to-end OpenRouter live smoke against the real API"
    expected: "`OPENROUTER_API_KEY=… uv run pytest -m live apps/api/backends/openrouter/tests/test_live.py -x` produces at least one TextDelta and a terminal Done with `cost_usd > 0`. BACKEND-03 / ROADMAP SC #1."
    why_human: "Hits a paid provider; BYOK required; non-deterministic completion text — cannot run automatically without operator approval."
  - test: "End-to-end Claude Code live smoke (build hello.py in tmp workspace)"
    expected: "`ANTHROPIC_API_KEY=… uv run pytest -m live apps/api/backends/claude_code/tests/test_live.py -x` produces at least one FileDiff and a terminal Done with `total_cost_usd > 0`. BACKEND-04 / ROADMAP SC #1. NOTE: CR-01 in `gaps:` predicts this test will FAIL until the ToolResultBlock field bug is fixed."
    why_human: "Spawns the real `claude` subprocess; BYOK required; mutates a tmp file."
  - test: "End-to-end computer-use live smoke (navigate https://example.com)"
    expected: "`COMPUTER_USE_OPT_IN=1 ANTHROPIC_API_KEY=… uv run pytest -m live apps/api/backends/computer_use/tests/test_live.py -x` produces at least one Screenshot and a ToolCall and a terminal Done with `cost_usd > 0`. BACKEND-05 / ROADMAP SC #1."
    why_human: "Launches real Chromium + paid provider call; requires double opt-in."
  - test: "Pre-commit deliberate-paste live block"
    expected: "`echo 'sk-ant-AAAAAAAAAAAAAAAAAAAA' >> deleteme.tmp && git add deleteme.tmp && git commit` is BLOCKED by the no-secrets hook. SECURE-02."
    why_human: "Tests the actual git-staging hook interaction, not the script in isolation. Plan SUMMARY records this manual outcome; re-run on demand."
---

# Phase 02: Backend Adapters & ChatChunk Contract Verification Report

**Phase Goal:** Three async backend adapters (OpenRouter via OpenAI SDK pointed at OpenRouter, Claude Code SDK, Anthropic computer-use) implementing a common Protocol that streams the ChatChunk discriminated union. Per-turn cost cap, 2-second cancellation budget, KeyStore + RedactionFilter, PricingTable, CostTracker, CI enforcement of all invariants.

**Verified:** 2026-05-15T18:16:38Z
**Status:** gaps_found
**Re-verification:** No — initial verification

The codebase ships the architecture intended by the phase: 3 adapter packages (`openrouter/`, `claude_code/`, `computer_use/`), shared Wave 0 modules (`chunks.py`, `protocol.py`, `cost.py`, `pricing.py`, `keystore.py`, `logging_filter.py`), a 13-row + `_default` `config/pricing.json`, `.pre-commit-config.yaml` with two LOCAL hooks, an extended `.github/workflows/ci.yml`, and the D-19 shared parametric contract suite. Test state at verification time: `pytest -m 'not live' apps/api/backends` = 129 passed, 1 skipped; `test_adapter_contract.py` = 17 passed + 1 intentional skip; Phase 1 `test_decide_smoke.py` D-18 guard remains green.

However, four code-level defects (3 of which 02-REVIEW.md classified as Critical CR-01/CR-02/CR-04/CR-05) **invalidate documented must-have truths**. CR-03 and the warnings are noted as advisory follow-ups; the four below are blocking gaps because the actual codebase does not satisfy the phase contract they claim.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | ROADMAP SC #1 — Per-adapter CLI `python -m apps.api.backends.<backend> --prompt "..."` is callable and streams ChatChunk JSON lines | VERIFIED | All three `--help` invocations succeed (verified live). `__main__.py` exists for each adapter; each parses `--prompt`, `--model`, `--max-cost-usd`, `--max-steps`. CLI smoke is gated on real keys for full end-to-end, but the help surface and entry point are wired. |
| 2 | ROADMAP SC #2(a) — Per-turn USD cap of $0.50 aborts mid-stream and emits `StreamError` + `Done` | VERIFIED | D-19 `test_cost_cap_aborts[openrouter|claude_code|computer_use]` all 3 PASS. `DEFAULT_PER_TURN_COST_USD = 0.50` in `apps/api/backends/cost.py:42`. Each adapter checks `tracker.over_cap()` and emits `StreamError(code="cost_cap_exceeded")` before `break`. |
| 3 | ROADMAP SC #2(b) — Claude Code stops at 25 tool calls; computer-use at 15 steps | VERIFIED | `claude_code/step_counter.py:DEFAULT_STEP_CAP = 25`; `computer_use/step_counter.py:DEFAULT_STEP_CAP = 15`. D-19 `test_step_cap_aborts[claude_code|computer_use]` PASS; openrouter intentionally skips ("N/A single round-trip"). |
| 4 | ROADMAP SC #2(c) — Cancellation propagates within 2 seconds | VERIFIED | D-19 `test_cancellation_within_2_seconds[*]` all 3 PASS with `@pytest.mark.timeout(2)`. Every adapter implements `except asyncio.CancelledError → yield StreamError("cancelled") + Done → raise` per PEP 789. `finally` blocks abort the in-flight transport (`in_flight.close()` / `client.interrupt() + disconnect()` / `screen.aclose()`). |
| 5 | ROADMAP SC #3 — Logger redaction installed at process import time; rewriting `sk-ant-…`, `sk-…`, `Bearer …` to `***REDACTED***` before any handler sees the record | VERIFIED (with caveats — see Truth 19, 20) | `apps/api/__init__.py:59` calls `install_redaction_filter()` at import. Smoke test passes: `sk-ant-A...` → `***REDACTED-ANTHROPIC***`, `sk-A...` → `***REDACTED-OPENAI***`, `Bearer A...` → `Bearer ***REDACTED***`. **CAVEAT (CR-05):** `Bearer sk-ant-...` mis-redacts to `Bearer ***REDACTED-ANTHROPIC***` — Bearer literal preserved (see Truth 20). |
| 6 | ROADMAP SC #3 — BYOK key store holds keys in process memory + optional `keyring`; never on disk | VERIFIED | `apps/api/backends/keystore.py` — `KeyStore.set()` writes to `self._memory: dict[str, str]`; only writes to `_keyring.set_password()` when `use_keyring=True` was opted in. `KeyStore(use_keyring=True)` raises `RuntimeError` with `uv sync --extra keyring` message when the extra is absent (D-10). 8 unit tests pass. |
| 7 | ROADMAP SC #4 — CI smoke test asserts `from claude_agent_sdk import ClaudeAgentOptions` succeeds and `claude-code-sdk` is not in `uv.lock` (OSS-06) | VERIFIED | `.github/workflows/ci.yml:34-40` contains both checks. `grep -c '"claude-code-sdk"' uv.lock` returns 0 (verified). Import smoke `from claude_agent_sdk import ClaudeAgentOptions` returns OK (verified live). Pre-commit hook + CI step + uv.lock grep = triad enforcement. |
| 8 | ROADMAP SC #4 — OpenRouter requests carry `HTTP-Referer` and `X-Title` headers | VERIFIED | `apps/api/backends/openrouter/adapter.py:79-80` declares the constants; `_default_client_factory` (lines 163-179) injects them via `default_headers={...}` on the `AsyncOpenAI` ctor. Pitfall-3 regression test `test_default_headers_set_on_constructor` passes. |
| 9 | ROADMAP SC #4 — `CLAUDE_ENABLE_STREAM_WATCHDOG=1` set in the adapter's environment-bootstrapping code (BACKEND-09) | VERIFIED | `apps/api/backends/claude_code/__init__.py` calls `os.environ.setdefault("CLAUDE_ENABLE_STREAM_WATCHDOG", "1")`. Smoke test: `import apps.api.backends.claude_code; os.environ['CLAUDE_ENABLE_STREAM_WATCHDOG']` returns `'1'` (verified live). `setdefault` semantics also tested — if pre-set to `"0"`, value stays `"0"`. |
| 10 | ROADMAP SC #5 — Computer-use adapter raises startup error unless `COMPUTER_USE_OPT_IN=1` (SECURE-05) | VERIFIED | `apps/api/backends/computer_use/adapter.py:217-223` raises `RuntimeError("computer-use is OFF — set COMPUTER_USE_OPT_IN=1 …")` BEFORE the api-key check and BEFORE any provider client. 4 `test_optin.py` tests pass; verified live by unsetting the env var and constructing the adapter. |
| 11 | ROADMAP SC #5 — Claude Code adapter uses per-thread ephemeral workspace by default, with opt-in `cwd` flag (BACKEND-08) | VERIFIED | `apps/api/backends/claude_code/adapter.py:286-291` — `options.cwd` is honored verbatim when provided; otherwise `tempfile.mkdtemp(prefix="pomu-cc-")` and `shutil.rmtree` in `finally`. ROADMAP SC #5 is annotated (B1 fix) that `pomu-cc-` is the Phase 2 placeholder for the Phase 3+ `~/.prompt-optimizer/workspaces/<thread_id>/` target — annotation present and grep-confirmed in ROADMAP.md. |
| 12 | ROADMAP SC #5 — Pre-commit hook blocks commits whose staged content matches `sk-` or `sk-ant-` (SECURE-02) | VERIFIED (with drift — see Truth 19) | `.pre-commit-config.yaml` declares both hooks; `scripts/no-secrets.sh` is executable and reads `git diff --cached`. `uv run pre-commit run --all-files` exits 0 on a clean tree. **CAVEAT (CR-04):** the regex set DRIFTS from `logging_filter.SECRET_PATTERNS` (see Truth 19). |
| 13 | BACKEND-01 — `ChatChunk` is a 7-variant discriminated union via `Annotated[Union[...], Field(discriminator="type")]` + `TypeAdapter` | VERIFIED | `apps/api/backends/chunks.py:167-184` — exactly 7 variants (`TextDelta | ToolCall | ToolResult | FileDiff | Screenshot | StreamError | Done`); `chat_chunk_adapter = TypeAdapter(ChatChunk)`. Round-trip smoke: `chat_chunk_adapter.validate_python({"type":"text_delta","text":"hi"})` returns `TextDelta(text="hi")` — verified live. 16 unit tests pass. REQUIREMENTS.md BACKEND-01 wording reconciled to include `ToolResult` per D-02 (Plan 02-04 Task 3). |
| 14 | BACKEND-02 — Common `BackendAdapter` Protocol with `async def stream(prompt, history, options) -> AsyncIterator[ChatChunk]` | VERIFIED | `apps/api/backends/protocol.py:72-86` — single-method `typing.Protocol`. All three adapter classes (`OpenRouterAdapter`, `ClaudeCodeAdapter`, `ComputerUseAdapter`) expose a matching `async def stream(self, prompt, history, options)` signature; structurally type-compatible. D-19 contract suite parametrises across them. |
| 15 | BACKEND-03 — OpenRouter adapter uses AsyncOpenAI pointed at `https://openrouter.ai/api/v1`, sets `stream_options={"include_usage": True}` | VERIFIED | `OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"` at line 78. Line 217 passes `stream_options={"include_usage": True}` to `chat.completions.create()`. Pitfall-1 regression `test_stream_options_include_usage_set` passes. |
| 16 | BACKEND-04(partial) — Claude Code adapter uses `claude_agent_sdk.ClaudeSDKClient` (NOT deprecated `claude-code-sdk`, NOT standalone `query()`) | VERIFIED | `apps/api/backends/claude_code/adapter.py:72-85` imports from `claude_agent_sdk`. Lines 313-319 use `ClaudeSDKClient.connect/query/receive_response` (NOT `query()` standalone). Pitfall-2 regression `test_uses_claudesdkclient_not_query_function` passes. `grep -q "claude_code_sdk"` against adapter.py returns 0. |
| 17 | BACKEND-05 — Computer-use adapter uses `computer_20251124` tool + `computer-use-2025-11-24` beta header on Claude Opus 4.7 / Sonnet 4.6 | VERIFIED | `BETA_HEADER = "computer-use-2025-11-24"` at line 115. Tool spec at lines 277-285 includes `"type": "computer_20251124"`, `display_width_px=1280`, `display_height_px=800`. `client.beta.messages.stream(..., betas=[BETA_HEADER])` at line 338. T2 unit test asserts the recorded kwargs. |
| 18 | BACKEND-06 / BACKEND-07 — D-19 6 invariants × 3 adapters | VERIFIED | `apps/api/backends/tests/test_adapter_contract.py` collects 18 cases; 17 pass + 1 intentional N/A skip for `step_cap_aborts[openrouter]`. Covers: happy path, cost cap, step cap, cancellation, terminal Done, missing-key raise — all 3 adapters. |
| 19 | **SECURE-02 contract — pre-commit `no-secrets.sh` regex set MATCHES `logging_filter.SECRET_PATTERNS`** (CR-04) | FAILED | Hook uses `sk-[A-Za-z0-9]{20,}` (no `_-`); filter uses `sk-[A-Za-z0-9_-]{20,}`. Hook uses literal space in `Bearer `; filter uses `\s+`. A key like `sk-AAAAA_AAAAAAAAAAAAAA…` is redacted at runtime but **not blocked** at commit time — verified live with two `re.compile` checks. The `logging_filter.py:31-32` docstring explicitly claims the regex sets are intentionally synchronised. |
| 20 | **SECURE-01 — `Bearer sk-ant-…` redacts as a single `Bearer ***REDACTED-…***` unit** (CR-05) | FAILED | Pattern order (`sk-ant-` first, `Bearer` last) means a canonical Anthropic Authorization header rewrites to `Bearer ***REDACTED-ANTHROPIC***`. The `Bearer` literal prefix is preserved verbatim — verified live. Existing `test_redaction_replaces_bearer_tokens` deliberately uses a non-`sk-` payload, dodging the regression. |
| 21 | **BACKEND-04 — Adapter emits `FileDiff` chunks for `Edit`/`Write` tool results** (CR-01) | FAILED | The real `claude_agent_sdk==0.1.81 ToolResultBlock` has only `tool_use_id`, `content`, `is_error` — verified via `dataclasses.fields(ToolResultBlock)` against the installed SDK. The adapter at lines 363, 367 reads `tool_name` and `input` via `getattr(..., default)` — defaults always fire in production, so the `tool_name in ("Edit", "Write")` branch is unreachable. FileDiff cannot be produced from real SDK events. Unit tests mask the bug because `FakeToolResultBlock` adds the missing fields. Phase 5's `CodeBubble` UI depends on FileDiff emission. |
| 22 | **Computer-use cost-tracking arithmetic — `record_iteration_usage` overrides the running estimate** (CR-02) | FAILED | `apps/api/backends/computer_use/cost.py:114-115` use `+=` instead of `=`. Verified live: `record_output_text('x'*40)` adds 10 char/4 tokens, then `record_iteration_usage(input_tokens=10, output_tokens=5)` produces `tokens_out=15`, not the docstring-promised `5`. Inflates `Done.tokens_out` AND the cap arithmetic that drives mid-stream `cost_cap_exceeded` decisions. |

**Score:** 18/22 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `apps/__init__.py` | Top-level package marker | VERIFIED | Exists. |
| `apps/api/__init__.py` | `load_dotenv()` + `install_redaction_filter()` at import; PROJECT_ROOT via pathlib.parents[2] | VERIFIED | Lines 49, 55, 59 — all present. |
| `apps/api/backends/protocol.py` | `BackendAdapter` Protocol, `Message`, `AdapterOptions`, `Backend` literal | VERIFIED | All four symbols defined; `Backend = Literal["openrouter", "claude_code", "computer_use"]` mirrors Phase 1. |
| `apps/api/backends/chunks.py` | 7-variant ChatChunk union + `chat_chunk_adapter` | VERIFIED | All 7 variants + `Field(discriminator="type")` + `TypeAdapter(ChatChunk)` present. |
| `apps/api/backends/keystore.py` | `KeyStore` with `use_keyring`, env fallback, lazy keyring import | VERIFIED | `SERVICE_NAME = "prompt-optimizer"`; `_ENV_MAP` covers `openrouter`/`anthropic`; `_HAS_KEYRING` lazy try/except. |
| `apps/api/backends/logging_filter.py` | `SECRET_PATTERNS` + `RedactionFilter` + `install_redaction_filter()` + record-factory hook | VERIFIED (functionally) — see Truth 20 for ordering defect | All three symbols present; record factory + filter on root both installed idempotently. |
| `apps/api/backends/pricing.py` | `PricingTable` with `from_static`, `get`, async `refresh_from_openrouter`, `_merge_openrouter_snapshot` (per-Mtok conversion) | VERIFIED | All four methods present. Pitfall-6 per-token → per-Mtok ×1_000_000 conversion at line 134-135. 12 unit tests pass. |
| `apps/api/backends/cost.py` | `CostTracker` base + `DEFAULT_PER_TURN_COST_USD: Final[float] = 0.50` | VERIFIED | Both declared (lines 42, 45-94). |
| `apps/api/backends/openrouter/adapter.py` | OpenRouterAdapter class | VERIFIED | All required elements: AsyncOpenAI, HTTP_REFERER/X_TITLE constants, `stream_options.include_usage`, tool-call delta accumulation, cancel/finally, cost cap. 360 lines. |
| `apps/api/backends/openrouter/cost.py` | OpenRouterCostTracker with tiktoken + `record_final_usage` | VERIFIED | Class subclasses CostTracker; uses tiktoken gpt-4 encoder; `record_input_estimate`/`record_output_delta`/`record_final_usage` all present. |
| `apps/api/backends/openrouter/errors.py` | PROVIDER_ERROR_MAP + `map_provider_error` (4 openai classes) | VERIFIED (but unused — see WR-03 advisory) | All 4 classes mapped; canonical-class-name fallback for D-18 sys.modules purge. NB: adapter inlines its own mapping; the `errors.py` module is exercised by tests but never imported by `adapter.py`. |
| `apps/api/backends/claude_code/adapter.py` | ClaudeCodeAdapter — ClaudeSDKClient + ALLOWED_TOOLS lock + workspace + step cap + cancel | VERIFIED (with CR-01 defect in FileDiff branch — see Truth 21) | All structural elements present, but the FileDiff branch uses non-existent fields on the real SDK. |
| `apps/api/backends/claude_code/__init__.py` | `os.environ.setdefault("CLAUDE_ENABLE_STREAM_WATCHDOG", "1")` + re-export | VERIFIED | Watchdog env var set via setdefault on import; smoke test confirms behavior. |
| `apps/api/backends/claude_code/workspace.py` | `ephemeral_workspace` async context manager | VERIFIED (but unused by adapter — WR-08 advisory) | Module exists and is tested by `test_workspace.py`. Adapter inlines the same mkdtemp/rmtree logic instead of using it (intentional deviation per Plan 02-02 Decision #3). |
| `apps/api/backends/claude_code/step_counter.py` | DEFAULT_STEP_CAP=25 + StepCounter | VERIFIED | Cap value 25 confirmed. |
| `apps/api/backends/computer_use/adapter.py` | ComputerUseAdapter — opt-in gate, beta header, tool spec, agent loop, Screenshot, cancel | VERIFIED | All structural elements present; SECURE-05 opt-in is at top of `__init__` BEFORE api_key check (verified live). |
| `apps/api/backends/computer_use/screen.py` | PlaywrightScreen with headless=True default + start/screenshot/click/type/press/scroll/goto/aclose | VERIFIED (with WR-09 URL scheme issue — advisory) | All methods present; `headless=True` default locked. |
| `apps/api/backends/computer_use/step_counter.py` | DEFAULT_STEP_CAP=15 + StepCounter (sibling to claude_code/) | VERIFIED | Cap value 15 confirmed. |
| `apps/api/backends/computer_use/cost.py` | ComputerUseCostTracker — record_output_text + record_iteration_usage | VERIFIED (with CR-02 arithmetic bug — see Truth 22) | Both methods present; arithmetic uses `+=` instead of `=`. |
| `apps/api/backends/tests/test_adapter_contract.py` | D-19 6-invariant × 3-adapter parametric suite | VERIFIED | Collects 18 cases; 17 pass + 1 intentional skip (`step_cap_aborts[openrouter]`). Lazy `try/except ImportError → pytest.skip` pattern in conftest. |
| `config/pricing.json` | 13 model rows + `_default` per D-17 | VERIFIED | 14 entries; all required keys present (`openai/gpt-5`, `anthropic/claude-opus-4-7`, etc.) plus `_default = {input_per_mtok: 5.00, output_per_mtok: 20.00}`. |
| `.pre-commit-config.yaml` | Two LOCAL hooks: no-secrets + no-deprecated-claude-code-sdk | VERIFIED | Both hooks declared; `pass_filenames: false`, `language: script`, `stages: [pre-commit]`. |
| `scripts/no-secrets.sh` | Executable; 3 patterns matching SECRET_PATTERNS | VERIFIED (executable) / FAILED (drift — see Truth 19) | Executable bit set; pattern set drifts from `logging_filter.SECRET_PATTERNS`. |
| `scripts/no-deprecated-sdk.sh` | Executable; staged-content + uv.lock check for claude-code-sdk | VERIFIED | Executable; two-step grep pipeline (Rule-1 fix); blocks staged `import claude_code_sdk` and `uv.lock` re-entry. |
| `.github/workflows/ci.yml` | Adds: `uv sync --extra keyring`, `pre-commit run --all-files`, OSS-06 import smoke, OSS-06 absence assertions, `pytest -m 'not live' apps/api/backends` + retains `pytest src/` | VERIFIED | All 6 new steps inserted; both YAML files parse. Phase 1 advisory `Routing canary eval` step preserved with `continue-on-error: true`. |
| `.github/workflows/live-smoke.yml` | manual `workflow_dispatch` + weekly cron + `secrets.OPENROUTER_API_KEY` gate + `continue-on-error: true` | VERIFIED | All elements present; runs `pytest -m live apps/api/backends/openrouter -x --maxfail=1`. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `apps/api/__init__.py` | `install_redaction_filter` | module-level call at import | VERIFIED | Line 59 — `install_redaction_filter()` runs unconditionally on import. |
| `apps/api/__init__.py` | `dotenv.load_dotenv` | module-level call at import | VERIFIED | Line 55 — `load_dotenv()` runs unconditionally on import. |
| `apps/api/backends/keystore.py` | `keyring` | lazy try/except optional import | VERIFIED | Lines 52-57 — try/except sets `_HAS_KEYRING` flag. |
| `apps/api/backends/pricing.py` | `httpx.AsyncClient` | async refresh from openrouter.ai/api/v1/models | VERIFIED | Line 112 — `httpx.AsyncClient(timeout=10.0)`. |
| `openrouter/adapter.py` | `openai.AsyncOpenAI` | `_default_client_factory` constructor injects `default_headers` | VERIFIED | Lines 163-179. |
| `openrouter/adapter.py` | `apps.api.backends.chunks` (TextDelta/ToolCall/StreamError/Done) | module import + yield | VERIFIED | `from apps.api.backends.chunks import (...)` + 8 yield sites in `stream`. |
| `openrouter/__main__.py` | `OpenRouterAdapter` | instantiate + iterate stream | VERIFIED | CLI exists; `--help` runs successfully. |
| `claude_code/__init__.py` | `os.environ['CLAUDE_ENABLE_STREAM_WATCHDOG']` | `setdefault` at module import | VERIFIED | Confirmed live (`'1'` after import). |
| `claude_code/adapter.py` | `claude_agent_sdk.ClaudeSDKClient` | module import + connect/query/receive_response/interrupt/disconnect | VERIFIED | Lines 72-85 + lifecycle calls at 313-319, 405, 441, 486. |
| `claude_code/adapter.py` | `chunks.FileDiff` | yield | **NOT_WIRED IN PRODUCTION** | Module imports `FileDiff` but the dispatch branch at adapter.py:366-378 is unreachable against the real SDK (CR-01) — see Truth 21. |
| `computer_use/adapter.py` | `os.environ['COMPUTER_USE_OPT_IN']` | constructor check BEFORE provider client | VERIFIED | Lines 217-223 — opt-in raise is the FIRST statement in `__init__`. |
| `computer_use/adapter.py` | `anthropic.AsyncAnthropic` | `client_factory` default | VERIFIED | Line 238-239. |
| `computer_use/adapter.py` | `anthropic client.beta.messages.stream` | `async with` agent loop | VERIFIED | Line 333. |
| `computer_use/screen.py` | `playwright.async_api.async_playwright` | `PlaywrightScreen.start` | VERIFIED | Line 93. |
| `.pre-commit-config.yaml` | `scripts/no-secrets.sh` | `entry` | VERIFIED | Line 8. |
| `.pre-commit-config.yaml` | `scripts/no-deprecated-sdk.sh` | `entry` | VERIFIED | Line 14. |
| `.github/workflows/ci.yml` | `pre-commit run --all-files` | step | VERIFIED | Line 32. |
| `.github/workflows/ci.yml` | claude_agent_sdk import smoke | step | VERIFIED | Line 35. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full Phase 2 test suite passes | `uv run pytest -m 'not live' apps/api/backends` | `129 passed, 1 skipped, 3 deselected in 1.05s` | PASS |
| D-19 contract suite passes for all 3 adapters | `uv run pytest -m 'not live' apps/api/backends/tests/test_adapter_contract.py` | `17 passed, 1 skipped in 0.83s` | PASS |
| Phase 1 D-18 import-graph guard stays green | `uv run pytest src/routing/tests/test_decide_smoke.py -x -q` | 7 passed | PASS |
| Per-adapter CLI `--help` runs | `python -m apps.api.backends.{openrouter,claude_code,computer_use} --help` | All 3 print usage with --prompt/--model/--max-cost-usd/--max-steps (claude_code also --cwd) | PASS |
| Pre-commit clean tree | `uv run pre-commit run --all-files` | `Block secrets...Passed` / `Block deprecated...Passed` | PASS |
| OSS-06 import smoke | `uv run python -c "from claude_agent_sdk import ClaudeAgentOptions; print('OK')"` | `OK` | PASS |
| OSS-06 lockfile absence | `grep -c '"claude-code-sdk"' uv.lock` | `0` | PASS |
| BACKEND-09 watchdog env var on import | `import apps.api.backends.claude_code; os.environ['CLAUDE_ENABLE_STREAM_WATCHDOG']` | `'1'` | PASS |
| SECURE-05 opt-in regression | `unset COMPUTER_USE_OPT_IN; ComputerUseAdapter(api_key='fake')` | RuntimeError with `COMPUTER_USE_OPT_IN` text | PASS |
| YAML workflow validity | `python -c "import yaml; yaml.safe_load(open('.github/workflows/{ci,live-smoke}.yml'))"` | YAML OK | PASS |
| TypeAdapter round-trip (BACKEND-01) | `chat_chunk_adapter.validate_python({"type":"text_delta","text":"hi"})` | Returns `TextDelta(text="hi")` | PASS |
| Logger redaction on common patterns | `logging.info('auth: sk-ant-A...'); logging.info('open: sk-A...'); logging.info('bearer: Bearer A...')` | All three rewritten to `***REDACTED-…***` | PASS |
| **Logger redaction on Bearer-prefixed sk-ant- (CR-05)** | `logging.info('Authorization: Bearer sk-ant-api03-XYZ1234567890ABCDEFGHIJKL')` | Mis-redacts to `Bearer ***REDACTED-ANTHROPIC***` — leaves literal `Bearer ` exposed | FAIL — see Truth 20 |
| **Pre-commit / filter regex parity (CR-04)** | Compare `sk-[A-Za-z0-9]{20,}` (hook) vs `sk-[A-Za-z0-9_-]{20,}` (filter) on `sk-AAAAA_AAAAAAAAAAAAAAAAAA` | Filter matches (redact); hook MISSES (no block) | FAIL — see Truth 19 |
| **ToolResultBlock fields against real SDK (CR-01)** | `dataclasses.fields(ToolResultBlock)` from `claude_agent_sdk==0.1.81` | `['tool_use_id', 'content', 'is_error']` — `tool_name` and `input` ABSENT | FAIL — see Truth 21 |
| **ComputerUseCostTracker override semantics (CR-02)** | `record_output_text('x'*40)` then `record_iteration_usage(input_tokens=10, output_tokens=5)`; check `tokens_out()` | Returns `15`, expected `5` per docstring | FAIL — see Truth 22 |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| BACKEND-01 | 02-00 | `ChatChunk` discriminated union (7 variants) is the single contract | SATISFIED | `chunks.py` ships all 7 variants + `chat_chunk_adapter`. REQUIREMENTS.md was reconciled in Plan 02-04 to include `ToolResult`. |
| BACKEND-02 | 02-00 | Common `BackendAdapter` Protocol with `async def stream(...)` | SATISFIED | `protocol.py:72-86`. All three adapters structurally implement it; D-19 parametric suite enforces. |
| BACKEND-03 | 02-01 | OpenRouter adapter via OpenAI SDK pointed at `https://openrouter.ai/api/v1` + HTTP-Referer/X-Title attribution | SATISFIED | `openrouter/adapter.py:78-80, 163-179, 217`. Header recording + `stream_options.include_usage` regressions pass. |
| BACKEND-04 | 02-02 | Claude Code adapter via `claude-agent-sdk 0.1.80+`; streams tool calls + **file diffs** + final summary | **BLOCKED** | `tool calls` and `final summary` ship. `file diffs` cannot be emitted in production — see Truth 21 / CR-01. |
| BACKEND-05 | 02-03 | Computer-use adapter via `anthropic 0.40+` with `computer_20251124` tool + `computer-use-2025-11-24` beta header | SATISFIED | `computer_use/adapter.py:115, 277-285, 333-338`. T2 unit test asserts tool spec + beta header recorded. |
| BACKEND-06 | 02-01/02/03 | Per-turn USD cap (default $0.50) + per-iteration step cap (25 / 15) | SATISFIED | `DEFAULT_PER_TURN_COST_USD = 0.50` + `DEFAULT_STEP_CAP` (25 / 15) constants. D-19 cost-cap + step-cap PASS for 3+2 adapter parameterisations. NB: CR-02 inflates the computer-use cap arithmetic but does not eliminate the cap behavior. |
| BACKEND-07 | 02-01/02/03 | Mid-stream cancellation propagates within 2 s | SATISFIED | D-19 `test_cancellation_within_2_seconds[*]` all 3 PASS with `@pytest.mark.timeout(2)`. Each adapter has `except asyncio.CancelledError → terminal pair → raise`. |
| BACKEND-08 | 02-02 | Claude Code per-thread ephemeral workspace by default; opt-in `cwd` flag | SATISFIED | `claude_code/adapter.py:286-291` — tempfile.mkdtemp(prefix="pomu-cc-") default; `options.cwd` opt-in honored. ROADMAP B1 annotation present. |
| BACKEND-09 | 02-02 | `CLAUDE_ENABLE_STREAM_WATCHDOG=1` set at module import | SATISFIED | `claude_code/__init__.py` calls `os.environ.setdefault("CLAUDE_ENABLE_STREAM_WATCHDOG", "1")`. Smoke test confirms `'1'` after import. |
| SECURE-01 | 02-00 | Logger redaction filter strips `sk-…`, `sk-ant-…`, `Bearer …` before any handler sees the record | NEEDS HUMAN ATTENTION | Filter works for the three documented patterns (PASS) but CR-05 (Bearer-prefixed sk-ant-) mis-redacts. Truth 20 calls out the gap; SECURE-01 wording does not specifically require Bearer-prefixed sk-ant- handling, so this is borderline — flagging as advisory follow-up that downstream pattern-matchers may break. |
| SECURE-02 | 02-04 | Pre-commit hook greps staged content for `sk-` and `sk-ant-` prefixes and blocks | SATISFIED (partial — see CR-04) | Pre-commit blocks `sk-`/`sk-ant-`/`Bearer ` literals. Truth 19 calls out drift with the filter regex set; the hook still satisfies SECURE-02's literal wording but the contract docstring claim of "identical regex set" is violated. |
| SECURE-04 | 02-00 | BYOK keys live only in process memory + optional `keyring`; never on disk | SATISFIED | `KeyStore` does not persist to SQLite/JSON/log files; `keyring` is opt-in via constructor flag + optional extra. 8 unit tests pass. |
| SECURE-05 | 02-03 | Computer-use is OFF by default; `COMPUTER_USE_OPT_IN=1` required | SATISFIED | Constructor raise fires BEFORE api_key check AND BEFORE any provider client construction. 4 unit tests + live smoke confirm. |
| OSS-06 | 02-04 | CI smoke test asserts `from claude_agent_sdk import ClaudeAgentOptions` to catch regression to deprecated `claude-code-sdk` | SATISFIED | Pre-commit hook + CI import smoke + CI uv.lock grep + pyproject.toml pin = quadruple enforcement. All four verified live. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `apps/api/backends/claude_code/adapter.py` | 362-372 | Field-access drift vs real SDK (`getattr(b, "tool_name", "")`) | Blocker (CR-01) | FileDiff is unreachable from real SDK events — invalidates BACKEND-04 truth #21. |
| `apps/api/backends/computer_use/cost.py` | 114-115 | `+=` instead of `=` in a method whose docstring promises "Override" | Blocker (CR-02) | Token counts inflated; cap arithmetic inflated by char/4 estimates not displaced. |
| `apps/api/backends/logging_filter.py` | 50-54 | Pattern ordering puts `sk-ant-` ahead of `Bearer\s+…` | Blocker (CR-05) | Canonical `Authorization: Bearer sk-ant-…` mis-redacts; downstream scrubbers will miss. |
| `scripts/no-secrets.sh` vs `logging_filter.py` | n/a | Regex set drift between hook and runtime filter; docstring asserts they are identical | Blocker (CR-04) | Underscore-bearing OpenAI keys redact at runtime but commit through. Bearer-with-tab passes through commit. |
| Multiple adapter files | per CR-03 | `StreamError.message=str(exc)` passes unredacted SDK exception text through SSE | Warning (CR-03 advisory) | Provider exception messages can echo URLs/keys; the RedactionFilter only covers log records, not ChatChunk payloads. NOT counted as a Phase 2 truth failure because SECURE-01 only specifies log redaction, but Phase 3 SSE will reveal this leak path. |
| Multiple adapter files | per WR-02 | `options.max_cost_usd or self._max_cost` (and `or self._max_steps`) treat 0 as falsy | Warning | A caller setting max_cost_usd=0.0 for an explicit dry-run gets the default 0.50 instead. Use `is None`. |
| Multiple adapter files | per WR-03 | `errors.py` modules tested but never imported by adapter.py | Warning | Maintenance trap; adapters could regress their error mapping without test coverage detecting it. |
| `claude_code/adapter.py` | 286-291, 492-496 | Inline workspace lifecycle duplicates `workspace.py`'s `ephemeral_workspace` | Warning (WR-08) | Two divergent code paths for the same lifecycle. |
| `computer_use/screen.py` | 181-185 | `goto(url)` accepts arbitrary URL schemes | Warning (WR-09) | `file:///`, `chrome://`, `data:` allowed once opted in — info-disclosure risk. |
| `computer_use/adapter.py` | 647-650 | Unbounded `asyncio.sleep` in `wait` action | Warning (WR-01) | Model can pin the stream for hours; cancel-only termination. |

**Debt markers (`TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER`):** None found in Phase 2 source files. The "placeholder" reference for `pomu-cc-` is in ROADMAP.md as a documented design note, not as code debt.

### Human Verification Required

These cannot be validated programmatically because they require BYOK credentials or external services. Frontmatter `human_verification:` enumerates the exact commands.

1. **OpenRouter live smoke** — `OPENROUTER_API_KEY=… uv run pytest -m live apps/api/backends/openrouter/tests/test_live.py -x` proves BACKEND-03 / ROADMAP SC #1 against the real provider.
2. **Claude Code live smoke** — `ANTHROPIC_API_KEY=… uv run pytest -m live apps/api/backends/claude_code/tests/test_live.py -x` should produce at least one FileDiff. **Predicted FAIL** until CR-01 (Truth 21) is fixed.
3. **Computer-use live smoke** — `COMPUTER_USE_OPT_IN=1 ANTHROPIC_API_KEY=… uv run pytest -m live apps/api/backends/computer_use/tests/test_live.py -x` proves BACKEND-05 against real Anthropic + Chromium.
4. **Pre-commit deliberate-paste live block** — stage a fake key and confirm `git commit` is blocked. Plan 02-04 SUMMARY documents this; recommend re-running after CR-04 fix.

### Gaps Summary

Phase 2 delivers the **architecture** of the goal: three async adapters share a single `ChatChunk` Pydantic discriminated union, implement a one-method `BackendAdapter` Protocol, enforce per-turn cost caps, per-iteration step caps, and 2-second cancellation via PEP 789. CI gates SECURE-02 + OSS-06 via pre-commit hooks and workflow checks. 129 unit tests pass, the D-19 shared contract suite is 17/18 green (1 intentional skip), and the Phase 1 D-18 import-graph guard remains green.

However, four critical defects in the actual code invalidate four documented must-have truths:

- **CR-01 (Truth 21):** `claude_code/adapter.py` reads `tool_name` / `input` from `ToolResultBlock`, but the real `claude_agent_sdk==0.1.81 ToolResultBlock` does not carry those fields. `FileDiff` is dead code in production. Phase 5's `CodeBubble` cannot render file diffs as required by ROADMAP Phase 5 SC #2. Tests pass only because `FakeToolResultBlock` adds the missing fields.
- **CR-02 (Truth 22):** `ComputerUseCostTracker.record_iteration_usage` uses `+=` instead of `=`. Per-iteration char/4 text-delta estimates accumulate with the authoritative Anthropic usage block, so `Done.tokens_out` and `over_cap()` arithmetic are double-counted.
- **CR-04 (Truth 19):** The pre-commit `no-secrets.sh` regex set diverges from `logging_filter.SECRET_PATTERNS` (OpenAI alphabet missing `_`/`-`; Bearer whitespace literal vs `\s+`). The `logging_filter.py:31-32` docstring explicitly claims the two sets are intentionally synchronised — that contract is broken.
- **CR-05 (Truth 20):** Pattern order in `SECRET_PATTERNS` makes `Bearer sk-ant-…` (the canonical Anthropic Authorization header form) rewrite to `Bearer ***REDACTED-ANTHROPIC***` instead of `Bearer ***REDACTED***`, leaving the `Bearer ` prefix visible and breaking downstream scrubbers that look for the Bearer-branch redaction marker.

**Group analysis:**
- CR-04 and CR-05 are both `logging_filter.py` / `scripts/no-secrets.sh` defects — a single planning iteration on the redaction subsystem (pattern set + ordering + script regex parity + a CI equivalence check) can close both.
- CR-01 and CR-02 are independent defects in two different adapters; both are tight, scoped, code-level fixes (one moves a tool_use_id lookup to a `dict`; one changes `+=` to `=` and adds a regression test).

**Not deferred:** All four gaps map to Phase 2 must-haves and downstream Phase 5 dependencies. Step 9b deferral check against later milestone phases (Phases 3, 4, 5, 6 in ROADMAP.md) found no later phase that explicitly addresses these defects — they must be fixed in Phase 2 closure.

**Advisory (NOT counted as gaps):**
- **CR-03** (`str(exc)` unredacted on `StreamError.message`) is a Phase 3 SSE concern. Phase 2's SECURE-01 wording only mandates log redaction; Phase 3 (`API-04` BYOK / `API-02` SSE) should add chunk-payload redaction.
- **WR-01..WR-09** are pre-Phase 3 quality issues (deprecated `asyncio.get_event_loop()`, unbounded `wait`, `or` falsy traps for cap options, errors.py dead code, mutable PricingTable.get return, navigate scheme allow-list). None invalidates a Phase 2 must-have; all should be in the Phase 2 closure plan or carried as Phase 3 prep work.

**Recommendation:** Re-plan with `--gaps` to close CR-01, CR-02, CR-04, CR-05. After fixes, re-verify per the truths listed in `gaps:` frontmatter. The four human-verification items also remain pending.

---

_Verified: 2026-05-15T18:16:38Z_
_Verifier: Claude (gsd-verifier)_
