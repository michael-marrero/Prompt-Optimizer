---
phase: 02-backend-adapters-chatchunk-contract
verified: 2026-05-15T21:48:03Z
status: human_needed
score: 22/22 must-haves verified
overrides_applied: 0
re_verification:
  mode: re-verification
  previous_status: gaps_found
  previous_score: 18/22
  previous_verified_at: 2026-05-15T18:16:38Z
  gaps_closed:
    - "Truth 21 (CR-01) — Claude Code adapter emits FileDiff for Edit/Write tool results via _pending_tool_calls lookup"
    - "Truth 22 (CR-02) — ComputerUseCostTracker.record_iteration_usage now OVERRIDES (=) running token tally"
    - "Truth 19 (CR-04) — scripts/no-secrets.sh regex set matches logging_filter.SECRET_PATTERNS alphabets exactly"
    - "Truth 20 (CR-05) — Bearer-prefixed sk-ant-… redacts as a single `Bearer ***REDACTED***` unit"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "End-to-end OpenRouter live smoke against the real API"
    expected: "`OPENROUTER_API_KEY=… uv run pytest -m live apps/api/backends/openrouter/tests/test_live.py -x` produces at least one TextDelta and a terminal Done with `cost_usd > 0`. BACKEND-03 / ROADMAP SC #1."
    why_human: "Hits a paid provider; BYOK required; non-deterministic completion text — cannot run automatically without operator approval."
  - test: "End-to-end Claude Code live smoke (build hello.py in tmp workspace)"
    expected: "`ANTHROPIC_API_KEY=… uv run pytest -m live apps/api/backends/claude_code/tests/test_live.py -x` produces at least one FileDiff and a terminal Done with `total_cost_usd > 0`. BACKEND-04 / ROADMAP SC #1. Plan 02-05 (CR-01) closure makes this branch reachable in production for the first time — this is the canonical live confirmation."
    why_human: "Spawns the real `claude` subprocess; BYOK required; mutates a tmp file."
  - test: "End-to-end computer-use live smoke (navigate https://example.com)"
    expected: "`COMPUTER_USE_OPT_IN=1 ANTHROPIC_API_KEY=… uv run pytest -m live apps/api/backends/computer_use/tests/test_live.py -x` produces at least one Screenshot and a ToolCall and a terminal Done with `cost_usd > 0`. BACKEND-05 / ROADMAP SC #1."
    why_human: "Launches real Chromium + paid provider call; requires double opt-in."
  - test: "Pre-commit deliberate-paste live block (refresh after CR-04 closure)"
    expected: "Three staged-secret reproductions are now BLOCKED end-to-end via the real `git commit` flow: (a) `sk-ant-AAAAAAAAAAAAAAAAAAAA`, (b) `sk-AAAAA_AAAAAAAAAAAAAAAAAA` (CR-04 underscore-bearing OpenAI), (c) `Bearer\\t<token>` (CR-04 tab-separated header). SECURE-02. Plan 02-07 (CR-04) SUMMARY records the bash-level outcomes; this human-verification item confirms the full pre-commit hook still wires through."
    why_human: "Tests the actual git-staging hook interaction, not the script in isolation. Plan SUMMARY records the bash-script outcomes after the fix; recommend re-running the end-to-end `git commit` flow on demand."
---

# Phase 02: Backend Adapters & ChatChunk Contract Verification Report

**Phase Goal:** Three backend adapters (OpenRouter, Claude Code, computer-use) each implement the `BackendAdapter` Protocol and stream a single `ChatChunk` discriminated union. Per-turn cost caps, per-iteration step caps, key redaction, computer-use opt-in, and the `claude-agent-sdk` SDK pin are all enforced from the adapter layer — no UI yet.

**Verified:** 2026-05-15T21:48:03Z
**Status:** human_needed
**Re-verification:** Yes — after gap closure (prior status: gaps_found, prior score: 18/22)

The codebase ships the architecture intended by the phase: 3 adapter packages (`openrouter/`, `claude_code/`, `computer_use/`), shared Wave 0 modules (`chunks.py`, `protocol.py`, `cost.py`, `pricing.py`, `keystore.py`, `logging_filter.py`), a 13-row + `_default` `config/pricing.json`, `.pre-commit-config.yaml` with two LOCAL hooks, an extended `.github/workflows/ci.yml` (now with a dedicated `Regex parity check` step from Plan 02-07), and the D-19 shared parametric contract suite. After three gap-closure plans (02-05, 02-06, 02-07), the full non-live test suite is GREEN: `uv run pytest -m 'not live'` = **233 passed, 2 skipped, 3 deselected** in 79.39 s. All four code-level defects from the prior verification (CR-01 / CR-02 / CR-04 / CR-05) are resolved.

This re-verification adopted the optimisation mandated by Step 0 of the goal-backward methodology: the four previously-FAILED truths received full 3-level re-verification (existence + substantive + wiring + behavioral spot-check); the eighteen previously-VERIFIED truths got quick regression checks (import smokes + key constant reads + counts) only. No regressions were detected in any of the eighteen.

All twenty-two observable truths are now VERIFIED. Status is `human_needed` because four items still require BYOK / external-service operator approval — those four human-verification commands are unchanged in shape from the prior report but two of them are sharper now: Truth 21 (Claude Code FileDiff) becomes a meaningful live confirmation rather than a predicted failure, and Truth 19 (pre-commit deliberate-paste) gets two additional regression reproductions (underscore-bearing OpenAI key + tab-separated Bearer) that previously slipped through.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | ROADMAP SC #1 — Per-adapter CLI `python -m apps.api.backends.<backend> --prompt "..."` is callable and streams ChatChunk JSON lines | VERIFIED | All three `--help` invocations succeed (verified live this run: `uv run python -m apps.api.backends.{openrouter,claude_code,computer_use} --help` each prints usage with `--prompt`, `--model`, `--max-cost-usd`, `--max-steps`; `claude_code` also offers `--cwd`). |
| 2 | ROADMAP SC #2(a) — Per-turn USD cap of $0.50 aborts mid-stream and emits `StreamError` + `Done` | VERIFIED | D-19 `test_cost_cap_aborts[openrouter|claude_code|computer_use]` all 3 PASS this run (17 of 18 contract cases passed; the 1 skip is `step_cap_aborts[openrouter]` intentional N/A). `DEFAULT_PER_TURN_COST_USD = 0.5` confirmed live. CR-02 cap-arithmetic correction (Plan 02-06) restores the cap to fire on the authoritative provider numbers rather than the inflated estimate. |
| 3 | ROADMAP SC #2(b) — Claude Code stops at 25 tool calls; computer-use at 15 steps | VERIFIED | `claude_code/step_counter.py:DEFAULT_STEP_CAP = 25`; `computer_use/step_counter.py:DEFAULT_STEP_CAP = 15` (smoke-confirmed this run). D-19 `test_step_cap_aborts[claude_code|computer_use]` PASS; openrouter intentionally skips. |
| 4 | ROADMAP SC #2(c) — Cancellation propagates within 2 seconds | VERIFIED | D-19 `test_cancellation_within_2_seconds[*]` all 3 PASS with `@pytest.mark.timeout(2)`. Every adapter implements `except asyncio.CancelledError → yield StreamError("cancelled") + Done → raise` per PEP 789; `finally` blocks call `client.interrupt() + disconnect()` / `screen.aclose()`. |
| 5 | ROADMAP SC #3 — Logger redaction installed at process import time; rewriting `sk-ant-…`, `sk-…`, `Bearer …` to `***REDACTED***` before any handler sees the record | VERIFIED | `apps/api/__init__.py:59` calls `install_redaction_filter()` at import (unchanged). Smoke test this run, **including the previously-failing CR-05 reproduction**: `Authorization: Bearer sk-ant-api03-XYZ1234567890ABCDEFGHIJKL` → `Authorization: Bearer ***REDACTED***` (single unit; no exposed Bearer literal alongside the anthropic marker). Plan 02-07 reordered `SECRET_PATTERNS` (Bearer FIRST). |
| 6 | ROADMAP SC #3 — BYOK key store holds keys in process memory + optional `keyring`; never on disk | VERIFIED | `KeyStore.set()` writes to `self._memory: dict[str, str]`; only writes to `_keyring.set_password()` when `use_keyring=True`. Tests pass (`keystore.py` regressions stable in this run's 233-pass total). |
| 7 | ROADMAP SC #4 — CI smoke test asserts `from claude_agent_sdk import ClaudeAgentOptions` succeeds and `claude-code-sdk` is not in `uv.lock` (OSS-06) | VERIFIED | `.github/workflows/ci.yml` retains both checks; `grep -q '"claude-code-sdk"' uv.lock` returns exit 1 (absent) — verified live this run. |
| 8 | ROADMAP SC #4 — OpenRouter requests carry `HTTP-Referer` and `X-Title` headers | VERIFIED | `openrouter/adapter.py` declares `OPENROUTER_HTTP_REFERER` / `OPENROUTER_X_TITLE` constants; `_default_client_factory` injects them via `default_headers={...}`. Pitfall-3 regression test `test_default_headers_set_on_constructor` passes in this run's 233-pass total. |
| 9 | ROADMAP SC #4 — `CLAUDE_ENABLE_STREAM_WATCHDOG=1` set in the adapter's environment-bootstrapping code (BACKEND-09) | VERIFIED | `apps/api/backends/claude_code/__init__.py` calls `os.environ.setdefault("CLAUDE_ENABLE_STREAM_WATCHDOG", "1")`. Live smoke: `import apps.api.backends.claude_code; os.environ['CLAUDE_ENABLE_STREAM_WATCHDOG']` returns `'1'` — verified this run. |
| 10 | ROADMAP SC #5 — Computer-use adapter raises startup error unless `COMPUTER_USE_OPT_IN=1` (SECURE-05) | VERIFIED | `computer_use/adapter.py` raises `RuntimeError("computer-use is OFF — set COMPUTER_USE_OPT_IN=1 …")` BEFORE the api-key check and BEFORE any provider client. 4 `test_optin.py` tests stable in this run's 233-pass total. |
| 11 | ROADMAP SC #5 — Claude Code adapter uses per-thread ephemeral workspace by default, with opt-in `cwd` flag (BACKEND-08) | VERIFIED | `claude_code/adapter.py:291-296` — `options.cwd` is honored verbatim when provided; otherwise `tempfile.mkdtemp(prefix="pomu-cc-")` and `shutil.rmtree` in `finally`. ROADMAP B1 annotation present (`pomu-cc-` is Phase 2 placeholder for the Phase 3+ `~/.prompt-optimizer/workspaces/<thread_id>/` target). |
| 12 | ROADMAP SC #5 — Pre-commit hook blocks commits whose staged content matches `sk-` or `sk-ant-` (SECURE-02) | VERIFIED | `.pre-commit-config.yaml` declares both hooks; `scripts/no-secrets.sh` is executable. **CR-04 closure (Plan 02-07)** unified the script's regex with `logging_filter.SECRET_PATTERNS` — `sk-[A-Za-z0-9_-]{20,}` and `Bearer[[:space:]]+[A-Za-z0-9_.-]{20,}`. `uv run pre-commit run --all-files` exits 0 on clean tree this run. |
| 13 | BACKEND-01 — `ChatChunk` is a 7-variant discriminated union via `Annotated[Union[...], Field(discriminator="type")]` + `TypeAdapter` | VERIFIED | `chunks.py` exposes exactly 7 variants; `chat_chunk_adapter = TypeAdapter(ChatChunk)`. Round-trip smoke this run: `chat_chunk_adapter.validate_python({"type":"text_delta","text":"hi"})` returns `TextDelta(text='hi')`. REQUIREMENTS.md BACKEND-01 wording reconciled to include `ToolResult` per D-02 (Plan 02-04). |
| 14 | BACKEND-02 — Common `BackendAdapter` Protocol with `async def stream(prompt, history, options) -> AsyncIterator[ChatChunk]` | VERIFIED | `protocol.py` defines a single-method `typing.Protocol`. All three adapter classes (`OpenRouterAdapter`, `ClaudeCodeAdapter`, `ComputerUseAdapter`) expose a matching signature; D-19 contract suite parametrises across them (17/18 PASS this run, 1 intentional N/A skip). |
| 15 | BACKEND-03 — OpenRouter adapter uses AsyncOpenAI pointed at `https://openrouter.ai/api/v1`, sets `stream_options={"include_usage": True}` | VERIFIED | `OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"` constant present; `stream_options={"include_usage": True}` passed to `chat.completions.create()`. Pitfall-1 regression `test_stream_options_include_usage_set` passes in this run's 233-pass total. |
| 16 | BACKEND-04(partial) — Claude Code adapter uses `claude_agent_sdk.ClaudeSDKClient` (NOT deprecated `claude-code-sdk`, NOT standalone `query()`) | VERIFIED | `claude_code/adapter.py:77-90` imports from `claude_agent_sdk`. Lines 328-334 use `ClaudeSDKClient.connect/query/receive_response` (NOT `query()` standalone). Pitfall-2 regression `test_uses_claudesdkclient_not_query_function` passes in this run's 233-pass total. |
| 17 | BACKEND-05 — Computer-use adapter uses `computer_20251124` tool + `computer-use-2025-11-24` beta header on Claude Opus 4.7 / Sonnet 4.6 | VERIFIED | `BETA_HEADER = "computer-use-2025-11-24"` declared; tool spec includes `"type": "computer_20251124"`, `display_width_px=1280`, `display_height_px=800`. `client.beta.messages.stream(..., betas=[BETA_HEADER])` plumbed. |
| 18 | BACKEND-06 / BACKEND-07 — D-19 6 invariants × 3 adapters | VERIFIED | `apps/api/backends/tests/test_adapter_contract.py` collects 18 cases; **17 pass + 1 intentional N/A skip** for `step_cap_aborts[openrouter]` (single round-trip — no in-loop step cap). Verified this run via `uv run pytest -m 'not live' apps/api/backends/tests/test_adapter_contract.py -v`. |
| 19 | **SECURE-02 contract — pre-commit `no-secrets.sh` regex set MATCHES `logging_filter.SECRET_PATTERNS`** (CR-04 closure) | VERIFIED | `scripts/no-secrets.sh` line 22 grep regex now reads `(sk-ant-[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9_-]{20,}|Bearer[[:space:]]+[A-Za-z0-9_.-]{20,})` — sk- alphabet gains `_-`; Bearer literal space becomes `[[:space:]]+`. **Closed by Plan 02-07 (commit `e4383e5`).** New `test_logging_filter_and_no_secrets_regex_parity` reads the script verbatim and asserts each of the 3 sub-patterns appears (after `[[:space:]]+` → `\s+` translation) in `SECRET_PATTERNS`. Test passes this run. CI workflow has a dedicated `Regex parity check (SECURE-01 + SECURE-02 contract)` step at line 34 that runs only that test for one-line failure visibility on future drift. |
| 20 | **SECURE-01 — `Bearer sk-ant-…` redacts as a single `Bearer ***REDACTED***` unit** (CR-05 closure) | VERIFIED | `SECRET_PATTERNS` reordered to put Bearer FIRST. Live verified this run: `_redact_text('Authorization: Bearer sk-ant-api03-XYZ1234567890ABCDEFGHIJKL')` returns `'Authorization: Bearer ***REDACTED***'` (NOT `'Bearer ***REDACTED-ANTHROPIC***'`). **Closed by Plan 02-07 (commit `e4383e5`).** Regression test `test_bearer_prefixed_sk_ant_redacts_as_bearer_unit` asserts the canonical Bearer-anthropic form redacts as a single unit. `SECRET_PATTERNS[0][0].pattern` = `Bearer\\s+[A-Za-z0-9_.\\-]{20,}` (verified live). |
| 21 | **BACKEND-04 — Adapter emits `FileDiff` chunks for `Edit`/`Write` tool results** (CR-01 closure) | VERIFIED | Adapter now records `(name, input)` from each `ToolUseBlock` at emit time into a per-`stream()` local `_pending_tool_calls: dict[str, tuple[str, dict]]` (init line 324, store line 369), and recovers them via `_pending_tool_calls.pop(tool_use_id, ("", {}))` (line 397) on the matching `ToolResultBlock`. The real `claude_agent_sdk==0.1.81 ToolResultBlock` carries only `tool_use_id`, `content`, `is_error` (verified this run via `dataclasses.fields(ToolResultBlock)`), but the adapter no longer reads `tool_name` / `input` off it — the FileDiff branch is now reachable in production. **Closed by Plan 02-05 (commit `2e79161`).** `FakeToolResultBlock` reduced to the three real-SDK fields so the masking layer is gone. New regression `test_filediff_emitted_against_real_sdk_shape` constructs `FakeToolResultBlock` with only `tool_use_id`, `content`, `is_error` and asserts FileDiff fires — passes this run. |
| 22 | **Computer-use cost-tracking arithmetic — `record_iteration_usage` overrides the running estimate** (CR-02 closure) | VERIFIED | `apps/api/backends/computer_use/cost.py` lines 122-123 now use `self._tokens_in = int(input_tokens)` and `self._tokens_out = int(output_tokens)` (override). Cache counters at lines 124-125 still use `+=` (visibility-only running totals) per the documented contract. Live verified this run via the VERIFICATION.md CR-02 reproduction recipe: `tracker.record_output_text('x'*40)` then `tracker.record_iteration_usage(input_tokens=10, output_tokens=5)` yields `tokens_in()=10`, `tokens_out()=5` (was 0/15 with the pre-fix `+=` bug). **Closed by Plan 02-06 (commit `a95617a`).** New regression `test_record_iteration_usage_overrides_running_estimate` passes this run. |

**Score:** 22/22 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `apps/__init__.py` | Top-level package marker | VERIFIED (carry-forward) | Exists. |
| `apps/api/__init__.py` | `load_dotenv()` + `install_redaction_filter()` at import; PROJECT_ROOT via pathlib.parents[2] | VERIFIED (carry-forward) | All present. |
| `apps/api/backends/protocol.py` | `BackendAdapter` Protocol, `Message`, `AdapterOptions`, `Backend` literal | VERIFIED (carry-forward) | All four symbols defined. |
| `apps/api/backends/chunks.py` | 7-variant ChatChunk union + `chat_chunk_adapter` | VERIFIED (carry-forward) | All 7 variants + `Field(discriminator="type")` + `TypeAdapter(ChatChunk)` present. |
| `apps/api/backends/keystore.py` | `KeyStore` with `use_keyring`, env fallback, lazy keyring import | VERIFIED (carry-forward) | All structural elements present. |
| `apps/api/backends/logging_filter.py` | `SECRET_PATTERNS` + `RedactionFilter` + `install_redaction_filter()` + record-factory hook; **Bearer FIRST in ordering (CR-05)** | VERIFIED (re-verified) | All three symbols present and idempotent installs intact. **CR-05 reorder confirmed live this run** — `SECRET_PATTERNS[0][0].pattern` starts with `Bearer\\s+`. |
| `apps/api/backends/pricing.py` | `PricingTable` with `from_static`, `get`, async `refresh_from_openrouter`, `_merge_openrouter_snapshot` | VERIFIED (carry-forward) | All four methods present; Pitfall-6 per-token → per-Mtok conversion. |
| `apps/api/backends/cost.py` | `CostTracker` base + `DEFAULT_PER_TURN_COST_USD: Final[float] = 0.50` | VERIFIED (carry-forward) | Both declared; smoke read returns `0.5` this run. |
| `apps/api/backends/openrouter/adapter.py` | OpenRouterAdapter class | VERIFIED (carry-forward) | All structural elements present. |
| `apps/api/backends/openrouter/cost.py` | OpenRouterCostTracker with tiktoken + `record_final_usage` | VERIFIED (carry-forward) | Class subclasses CostTracker; override semantics correct (parallel reference for CR-02). |
| `apps/api/backends/openrouter/errors.py` | PROVIDER_ERROR_MAP + `map_provider_error` (4 openai classes) | VERIFIED (carry-forward; WR-03 advisory unchanged — `errors.py` not imported by adapter.py, still a maintenance trap but not a phase blocker) | All 4 classes mapped. |
| `apps/api/backends/claude_code/adapter.py` | ClaudeCodeAdapter — ClaudeSDKClient + ALLOWED_TOOLS lock + workspace + step cap + cancel; **FileDiff branch reachable in production (CR-01)** | VERIFIED (re-verified) | All structural elements present. **CR-01 closure** introduces `_pending_tool_calls: dict[str, tuple[str, dict]]` (line 324 init, line 369 store, line 397 pop) so FileDiff fires from real SDK events. Verified live: `grep -c "_pending_tool_calls" adapter.py` = 5 occurrences. |
| `apps/api/backends/claude_code/__init__.py` | `os.environ.setdefault("CLAUDE_ENABLE_STREAM_WATCHDOG", "1")` + re-export | VERIFIED (carry-forward) | Watchdog env var set via setdefault on import; live smoke confirmed `'1'` this run. |
| `apps/api/backends/claude_code/workspace.py` | `ephemeral_workspace` async context manager | VERIFIED (carry-forward; WR-08 advisory unchanged — adapter inlines mkdtemp/rmtree instead) | Module exists and is tested. |
| `apps/api/backends/claude_code/step_counter.py` | DEFAULT_STEP_CAP=25 + StepCounter | VERIFIED (carry-forward; live smoke confirms `25` this run) | Cap value confirmed. |
| `apps/api/backends/claude_code/tests/fakes.py` | `FakeToolResultBlock` with three fields only (`tool_use_id`, `content`, `is_error`) — matches real SDK | VERIFIED (re-verified) | **CR-01 closure** drops `tool_name` / `input` fields. Verified live: `grep -E "^[[:space:]]+tool_name:[[:space:]]*str" fakes.py` returns 0 matches. |
| `apps/api/backends/computer_use/adapter.py` | ComputerUseAdapter — opt-in gate, beta header, tool spec, agent loop, Screenshot, cancel | VERIFIED (carry-forward) | All structural elements present; SECURE-05 opt-in at top of `__init__`. |
| `apps/api/backends/computer_use/screen.py` | PlaywrightScreen with headless=True default + start/screenshot/click/type/press/scroll/goto/aclose | VERIFIED (carry-forward; WR-09 URL scheme issue still advisory — not a phase blocker) | All methods present. |
| `apps/api/backends/computer_use/step_counter.py` | DEFAULT_STEP_CAP=15 + StepCounter | VERIFIED (carry-forward; live smoke confirms `15` this run) | Cap value confirmed. |
| `apps/api/backends/computer_use/cost.py` | ComputerUseCostTracker — `record_output_text` + `record_iteration_usage` with **override (=) semantics (CR-02)** | VERIFIED (re-verified) | **CR-02 closure** flips lines 122-123 from `+=` to `=`. Verified live: `grep -n "self._tokens_in = int" cost.py` returns line 122; `grep -n "self._tokens_in += int" cost.py` returns 0 matches. Cache counters at lines 124-125 still `+=` (preserved per contract). |
| `apps/api/backends/tests/test_adapter_contract.py` | D-19 6-invariant × 3-adapter parametric suite | VERIFIED (re-verified) | 17 passed + 1 intentional N/A skip (`step_cap_aborts[openrouter]`). Verified live this run. |
| `config/pricing.json` | 13 model rows + `_default` per D-17 | VERIFIED (carry-forward) | 14 entries present. |
| `.pre-commit-config.yaml` | Two LOCAL hooks: no-secrets + no-deprecated-claude-code-sdk | VERIFIED (carry-forward) | Both hooks declared; clean-tree run exits 0 this run. |
| `scripts/no-secrets.sh` | Executable; **regex set matches `SECRET_PATTERNS` alphabets exactly (CR-04)** | VERIFIED (re-verified) | **CR-04 closure** lines 22 + comment block 6-8 record the unified regex set. Live verified: grep for `sk-[A-Za-z0-9_-]{20,}` and `Bearer[[:space:]]+` returns both matches. |
| `scripts/no-deprecated-sdk.sh` | Executable; staged-content + uv.lock check for claude-code-sdk | VERIFIED (carry-forward) | Executable; two-step grep pipeline (Rule-1 fix); blocks staged `import claude_code_sdk` and `uv.lock` re-entry. |
| `.github/workflows/ci.yml` | Adds: `uv sync --extra keyring`, `pre-commit run --all-files`, **`Regex parity check (CR-04)`**, OSS-06 import smoke, OSS-06 absence assertions, `pytest -m 'not live' apps/api/backends` + retains `pytest src/` | VERIFIED (re-verified) | **CR-04 closure** inserts a dedicated step at line 34: `Regex parity check (SECURE-01 + SECURE-02 contract)` that runs only `test_logging_filter_and_no_secrets_regex_parity`. YAML still parses; live verified this run. |
| `.github/workflows/live-smoke.yml` | manual `workflow_dispatch` + weekly cron + `secrets.OPENROUTER_API_KEY` gate + `continue-on-error: true` | VERIFIED (carry-forward) | All elements present. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `apps/api/__init__.py` | `install_redaction_filter` | module-level call at import | VERIFIED (carry-forward) | Line 59 — runs unconditionally on import. |
| `apps/api/__init__.py` | `dotenv.load_dotenv` | module-level call at import | VERIFIED (carry-forward) | Line 55 — runs unconditionally on import. |
| `apps/api/backends/keystore.py` | `keyring` | lazy try/except optional import | VERIFIED (carry-forward) | `_HAS_KEYRING` flag pattern. |
| `apps/api/backends/pricing.py` | `httpx.AsyncClient` | async refresh from openrouter.ai/api/v1/models | VERIFIED (carry-forward) | `httpx.AsyncClient(timeout=10.0)`. |
| `openrouter/adapter.py` | `openai.AsyncOpenAI` | `_default_client_factory` constructor injects `default_headers` | VERIFIED (carry-forward) | Headers wired via constructor (D-12). |
| `openrouter/adapter.py` | `apps.api.backends.chunks` (TextDelta/ToolCall/StreamError/Done) | module import + yield | VERIFIED (carry-forward) | 8 yield sites in `stream`. |
| `openrouter/__main__.py` | `OpenRouterAdapter` | instantiate + iterate stream | VERIFIED (carry-forward) | `--help` runs this run. |
| `claude_code/__init__.py` | `os.environ['CLAUDE_ENABLE_STREAM_WATCHDOG']` | `setdefault` at module import | VERIFIED (carry-forward) | `'1'` after import — confirmed live. |
| `claude_code/adapter.py` | `claude_agent_sdk.ClaudeSDKClient` | module import + connect/query/receive_response/interrupt/disconnect | VERIFIED (carry-forward) | Lifecycle calls at 328-334, 438, 474, 519. |
| **`claude_code/adapter.py` ToolUseBlock emit site** | **`_pending_tool_calls` dict keyed by `tool_use_id`** | **store `(tool_name, input)` at emit** | **VERIFIED (CR-01 closure)** | Line 367-372: `if tool_id: _pending_tool_calls[tool_id] = (getattr(block, "name", ""), getattr(block, "input", {}) or {})`. |
| **`claude_code/adapter.py` ToolResultBlock dispatch** | **`chunks.FileDiff` emission** | **lookup `tool_name` + `input` from `_pending_tool_calls.pop(tool_use_id)`** | **VERIFIED (CR-01 closure — was NOT_WIRED IN PRODUCTION)** | Line 397-411: `tool_name, tool_input = _pending_tool_calls.pop(tool_use_id, ("", {}))` then `if tool_name in ("Edit", "Write"): yield FileDiff(...)`. The branch is now reachable from real SDK events. |
| `computer_use/adapter.py` | `os.environ['COMPUTER_USE_OPT_IN']` | constructor check BEFORE provider client | VERIFIED (carry-forward) | Opt-in raise is the FIRST statement in `__init__`. |
| `computer_use/adapter.py` | `anthropic.AsyncAnthropic` | `client_factory` default | VERIFIED (carry-forward) | Default factory wired. |
| `computer_use/adapter.py` | `anthropic client.beta.messages.stream` | `async with` agent loop | VERIFIED (carry-forward) | `betas=[BETA_HEADER]` plumbed. |
| **`computer_use/cost.py:record_iteration_usage`** | **`self._tokens_in` / `self._tokens_out` (assigned with `=`, not `+=`)** | **override semantics** | **VERIFIED (CR-02 closure)** | Lines 122-123 use `=`. Cache counters at lines 124-125 keep `+=` (correct per documented contract). |
| `computer_use/screen.py` | `playwright.async_api.async_playwright` | `PlaywrightScreen.start` | VERIFIED (carry-forward) | Playwright import + boot call wired. |
| `.pre-commit-config.yaml` | `scripts/no-secrets.sh` | `entry` | VERIFIED (carry-forward) | Hook entry present. |
| `.pre-commit-config.yaml` | `scripts/no-deprecated-sdk.sh` | `entry` | VERIFIED (carry-forward) | Hook entry present. |
| **`apps/api/backends/logging_filter.py` SECRET_PATTERNS list** | **`scripts/no-secrets.sh` `grep -E` pattern** | **verbatim regex equivalence (modulo `\s+` ↔ `[[:space:]]+`)** | **VERIFIED (CR-04 closure)** | Plan 02-07 unified the alphabets. Programmatic parity check (`test_logging_filter_and_no_secrets_regex_parity`) reads the script and asserts each of the 3 sub-patterns appears in `SECRET_PATTERNS` after `[[:space:]]+` → `\s+` translation — passes this run. |
| **`apps/api/backends/tests/test_logging_filter.py` parity test** | **`scripts/no-secrets.sh`** | **`Path(__file__).resolve().parents[4]` → read script file, split alternation, translate, compare against `SECRET_PATTERNS`** | **VERIFIED (CR-04 closure)** | Test now exists; runs as part of the dedicated CI `Regex parity check` step at line 34 of ci.yml AND as part of the broader `Phase 2 — apps/api/backends unit tests (no live)` step at line 56. Intentional duplication for one-line failure visibility. |
| `.github/workflows/ci.yml` | `pre-commit run --all-files` | step | VERIFIED (carry-forward) | Line 32. |
| `.github/workflows/ci.yml` | **`Regex parity check`** | dedicated step running `test_logging_filter_and_no_secrets_regex_parity` | **VERIFIED (CR-04 closure)** | Line 34 — new step inserted between pre-commit and OSS-06 import smoke. |
| `.github/workflows/ci.yml` | claude_agent_sdk import smoke | step | VERIFIED (carry-forward) | Line 40-41. |

### Data-Flow Trace (Level 4)

This phase ships adapter machinery (no dynamic-rendering UI yet). Data-flow tracing focuses on the chunk-emission pipeline whose upstream sources (provider streams, SDK events) cannot be programmatically invoked without a paid API key — those routes are covered by the human-verification items below.

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `claude_code/adapter.py` FileDiff emission | `tool_name`, `tool_input` | `_pending_tool_calls.pop(tool_use_id, ("", {}))` populated from `getattr(block, "name", "")` / `getattr(block, "input", {})` on each ToolUseBlock | Yes — `ToolUseBlock` carries `id`, `name`, `input` on the real SDK (verified via dataclass-introspection on the installed `claude_agent_sdk==0.1.81`). The fix maps that authoritative source into the FileDiff branch. | FLOWING (CR-01 closure) |
| `computer_use/cost.py` `Done.tokens_in/out` | `self._tokens_in`, `self._tokens_out` | `record_iteration_usage(input_tokens=..., output_tokens=...)` from `stream.get_final_message().usage` (Anthropic authoritative numbers) | Yes — override semantics replaces the running char/4 estimate with the provider-authoritative count on each iteration. Verified live: 0+10 estimate → override to (10, 5). | FLOWING (CR-02 closure) |
| `logging_filter.py` redacted log records | `record.msg`, `record.args` | `_redact_text(msg)` running every `SECRET_PATTERN` substitution in order (Bearer FIRST, then sk-ant-, then sk-) | Yes — verified live for all five canonical inputs including the previously-failing `Authorization: Bearer sk-ant-…` and `key: sk-AAAAA_AAAAAAAAAAAAAAAAAA` reproductions. | FLOWING (CR-04 + CR-05 closure) |
| `scripts/no-secrets.sh` staged-secret detection | `git diff --cached` lines | `grep -E '(sk-ant-[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9_-]{20,}|Bearer[[:space:]]+[A-Za-z0-9_.-]{20,})'` | Yes — unified alphabets now catch the two previously-bypassed reproductions (underscore-bearing OpenAI key + tab-separated Bearer header) per Plan 02-07 SUMMARY. End-to-end `git commit` flow is part of the human-verification list. | FLOWING (CR-04 closure) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full Phase 2 + Phase 1 non-live suite passes | `uv run pytest -m 'not live'` | `233 passed, 2 skipped, 3 deselected in 79.39s` | PASS |
| Four CR regression tests pass in isolation | `uv run pytest -m 'not live' apps/api/backends/claude_code/tests/test_adapter.py::test_filediff_emitted_against_real_sdk_shape apps/api/backends/computer_use/tests/test_adapter.py::test_record_iteration_usage_overrides_running_estimate apps/api/backends/tests/test_logging_filter.py::test_bearer_prefixed_sk_ant_redacts_as_bearer_unit apps/api/backends/tests/test_logging_filter.py::test_logging_filter_and_no_secrets_regex_parity -v` | `4 passed in 0.02s` | PASS |
| D-19 contract suite passes for all 3 adapters | `uv run pytest -m 'not live' apps/api/backends/tests/test_adapter_contract.py -v` | `17 passed, 1 skipped in 0.85s` | PASS |
| Phase 1 D-18 import-graph guard stays green | `uv run pytest -m 'not live' src/routing/tests/test_decide_smoke.py -x -q` | `7 passed` | PASS |
| Per-adapter CLI `--help` runs | `uv run python -m apps.api.backends.{openrouter,claude_code,computer_use} --help` | All 3 print usage with `--prompt`/`--model`/`--max-cost-usd`/`--max-steps` (claude_code also `--cwd`) | PASS |
| Pre-commit clean tree | `uv run pre-commit run --all-files` | `Block secrets...Passed` / `Block deprecated...Passed` | PASS |
| OSS-06 lockfile absence | `grep -q '"claude-code-sdk"' uv.lock` | exit 1 (absent) | PASS |
| BACKEND-09 watchdog env var on import | `import apps.api.backends.claude_code; os.environ['CLAUDE_ENABLE_STREAM_WATCHDOG']` | `'1'` | PASS |
| **Logger redaction on `Bearer sk-ant-…` (CR-05 closure)** | `_redact_text('Authorization: Bearer sk-ant-api03-XYZ1234567890ABCDEFGHIJKL')` | `'Authorization: Bearer ***REDACTED***'` (NOT `'Bearer ***REDACTED-ANTHROPIC***'`) | PASS (was FAIL) |
| **Pre-commit / filter regex parity (CR-04 closure)** | `_redact_text('key: sk-AAAAA_AAAAAAAAAAAAAAAAAA')` redacts AND `grep -E '(...sk-[A-Za-z0-9_-]{20,}...)' scripts/no-secrets.sh` returns a match line | Filter rewrites to `'key: ***REDACTED-OPENAI***'`; script grep line returned | PASS (was FAIL) |
| **ToolResultBlock fields against real SDK (CR-01 closure)** | `dataclasses.fields(ToolResultBlock)` from `claude_agent_sdk==0.1.81` AND adapter no longer reads `tool_name` / `input` off that block | Fields: `['tool_use_id', 'content', 'is_error']`; adapter source line 397 reads from `_pending_tool_calls.pop(tool_use_id, ("", {}))` instead | PASS (was FAIL) |
| **ComputerUseCostTracker override semantics (CR-02 closure)** | `record_output_text('x'*40)` then `record_iteration_usage(input_tokens=10, output_tokens=5)`; check `tokens_in() / tokens_out()` | Returns `10, 5` (override). Pre-fix produced `0, 15` (accumulate). | PASS (was FAIL) |
| TypeAdapter round-trip (BACKEND-01) | `chat_chunk_adapter.validate_python({"type":"text_delta","text":"hi"})` | Returns `TextDelta(text='hi')` | PASS |
| SECRET_PATTERNS Bearer-first ordering | `SECRET_PATTERNS[0][0].pattern` | `Bearer\\s+[A-Za-z0-9_.\\-]{20,}` | PASS |

### Probe Execution

This phase does not declare or imply probe-based verification (no `scripts/*/tests/probe-*.sh` paths referenced in PLAN, SUMMARY, or success criteria — the project uses pytest contract tests via D-19 instead). Probe execution: SKIPPED — phase verification contract is satisfied by the D-19 contract suite + targeted regression tests, both green.

### Requirements Coverage

All Phase 2 requirement IDs declared in plan frontmatter (BACKEND-01..09, SECURE-01, SECURE-02, SECURE-04, SECURE-05, OSS-06) are accounted for. The prior verification's gap analysis flagged BACKEND-04 as BLOCKED (CR-01) and SECURE-01 / SECURE-02 as partial (CR-04/CR-05) — all three are now SATISFIED after the gap-closure plans landed.

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| BACKEND-01 | 02-00 | `ChatChunk` discriminated union (7 variants) is the single contract | SATISFIED | `chunks.py` ships all 7 variants + `chat_chunk_adapter`; REQUIREMENTS.md reconciled to include `ToolResult`. Truth 13. |
| BACKEND-02 | 02-00, 02-05 | Common `BackendAdapter` Protocol with `async def stream(...)` | SATISFIED | `protocol.py:72-86`; all three adapters structurally implement it; D-19 parametric suite enforces. Truth 14. Plan 02-05 closure does not regress the Protocol shape. |
| BACKEND-03 | 02-01 | OpenRouter adapter via OpenAI SDK pointed at `https://openrouter.ai/api/v1` + HTTP-Referer/X-Title attribution | SATISFIED | Truth 8 + Truth 15. |
| BACKEND-04 | 02-02, 02-05 | Claude Code adapter via `claude-agent-sdk 0.1.80+`; streams tool calls + **file diffs** + final summary | **SATISFIED** (was BLOCKED in prior report) | **Plan 02-05 closes CR-01 — FileDiff is now reachable from real SDK events.** Truths 16, 21. |
| BACKEND-05 | 02-03 | Computer-use adapter via `anthropic 0.40+` with `computer_20251124` tool + `computer-use-2025-11-24` beta header | SATISFIED | Truth 17. |
| BACKEND-06 | 02-01/02/03, 02-06 | Per-turn USD cap (default $0.50) + per-iteration step cap (25 / 15) | SATISFIED | Truths 2, 3, 18, 22. **Plan 02-06 closes CR-02 — cap arithmetic now correct on the authoritative provider numbers.** |
| BACKEND-07 | 02-01/02/03 | Mid-stream cancellation propagates within 2 s | SATISFIED | Truth 4. |
| BACKEND-08 | 02-02 | Claude Code per-thread ephemeral workspace by default; opt-in `cwd` flag | SATISFIED | Truth 11. |
| BACKEND-09 | 02-02 | `CLAUDE_ENABLE_STREAM_WATCHDOG=1` set at module import | SATISFIED | Truth 9. |
| SECURE-01 | 02-00, 02-07 | Logger redaction filter strips `sk-…`, `sk-ant-…`, `Bearer …` before any handler sees the record | **SATISFIED** (was NEEDS HUMAN ATTENTION in prior report) | **Plan 02-07 closes CR-05 — `Bearer sk-ant-…` now redacts as `Bearer ***REDACTED***`.** Truths 5, 20. Programmatic parity check + dedicated CI step prevent future drift. |
| SECURE-02 | 02-04, 02-07 | Pre-commit hook greps staged content for `sk-` and `sk-ant-` prefixes and blocks | **SATISFIED** (was partial in prior report) | **Plan 02-07 closes CR-04 — script regex set now matches `SECRET_PATTERNS` alphabets exactly.** Truths 12, 19. End-to-end `git commit` flow verified by the human-verification item (Plan 02-07 SUMMARY records the bash-level reproductions). |
| SECURE-04 | 02-00 | BYOK keys live only in process memory + optional `keyring`; never on disk | SATISFIED | Truth 6. |
| SECURE-05 | 02-03 | Computer-use is OFF by default; `COMPUTER_USE_OPT_IN=1` required | SATISFIED | Truth 10. |
| OSS-06 | 02-04 | CI smoke test asserts `from claude_agent_sdk import ClaudeAgentOptions` to catch regression to deprecated `claude-code-sdk` | SATISFIED | Truth 7. |

**Orphaned requirements:** None. REQUIREMENTS.md Traceability table maps BACKEND-01..09, SECURE-01, SECURE-02, SECURE-04, SECURE-05, OSS-06 to Phase 2; every ID appears in at least one Phase 2 plan's `requirements` field.

### Anti-Patterns Found

After the three gap-closure plans landed, the four previously-blocking defects (CR-01 / CR-02 / CR-04 / CR-05) are RESOLVED. Several Warning-level items remain — these were called out in the prior verification report as advisory follow-ups that do not invalidate any Phase 2 must-have truth and were intentionally left out of the gap-closure scope.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (no blocker-level anti-patterns remain in this phase's source) | — | — | — | The four prior Blockers (CR-01 / CR-02 / CR-04 / CR-05) are all closed by Plans 02-05/06/07. |
| Multiple adapter files | per CR-03 | `StreamError.message=str(exc)` passes unredacted SDK exception text through SSE chunks | Warning (CR-03 advisory; carry-forward) | Provider exception messages may echo URLs/keys through the chunk payload (not the log record, which IS redacted). Phase 2 SECURE-01 wording mandates LOG redaction only — chunk-payload scrubbing is a Phase 3 concern (API-02 SSE / API-04 BYOK). Not counted as a Phase 2 truth failure. |
| Multiple adapter files | per WR-02 | `options.max_cost_usd or self._max_cost` (and `or self._max_steps`) treat 0 as falsy | Warning (carry-forward) | A caller setting max_cost_usd=0.0 for an explicit dry-run gets the default 0.50 instead. Use `is None`. Confirmed still present at openrouter:197, claude_code:299-300, computer_use:262-263. Not a Phase 2 truth failure. |
| Multiple adapter files | per WR-03 | `errors.py` modules tested but never imported by adapter.py | Warning (carry-forward) | Maintenance trap; adapters could regress their error mapping without test coverage detecting it. Not a Phase 2 truth failure. |
| `claude_code/adapter.py` | inline workspace lifecycle | Inline workspace mkdtemp/rmtree duplicates `workspace.py`'s `ephemeral_workspace` | Warning (WR-08 carry-forward) | Two divergent code paths for the same lifecycle. Not a Phase 2 truth failure. |
| `computer_use/screen.py` | `goto(url)` accepts arbitrary URL schemes | Warning (WR-09 carry-forward) | `file:///`, `chrome://`, `data:` allowed once opted in — info-disclosure risk. Not a Phase 2 truth failure. |
| `computer_use/adapter.py` | Unbounded `asyncio.sleep` in `wait` action | Warning (WR-01 carry-forward) | Model can pin the stream for hours; cancel-only termination. Not a Phase 2 truth failure. |

**Debt markers (`TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER`):** None in Phase 2 source files modified during gap closure (`adapter.py`, `cost.py`, `fakes.py`, `test_adapter.py`, `logging_filter.py`, `no-secrets.sh`, `test_logging_filter.py`, `ci.yml`). The "placeholder" reference for `pomu-cc-` is in ROADMAP.md as a documented design note, not as code debt.

### Human Verification Required

These cannot be validated programmatically because they require BYOK credentials or external services. Frontmatter `human_verification:` enumerates the exact commands.

1. **OpenRouter live smoke** — `OPENROUTER_API_KEY=… uv run pytest -m live apps/api/backends/openrouter/tests/test_live.py -x` proves BACKEND-03 / ROADMAP SC #1 against the real provider.
2. **Claude Code live smoke** — `ANTHROPIC_API_KEY=… uv run pytest -m live apps/api/backends/claude_code/tests/test_live.py -x` should produce at least one FileDiff. **Plan 02-05 (CR-01 closure) makes this branch reachable in production for the first time** — no longer a predicted FAIL.
3. **Computer-use live smoke** — `COMPUTER_USE_OPT_IN=1 ANTHROPIC_API_KEY=… uv run pytest -m live apps/api/backends/computer_use/tests/test_live.py -x` proves BACKEND-05 against real Anthropic + Chromium.
4. **Pre-commit deliberate-paste live block (refresh)** — stage three fake keys (`sk-ant-AAAAA…`, the CR-04 underscore-bearing OpenAI form, and the CR-04 tab-Bearer form) via `git add` and confirm `git commit` is blocked. Plan 02-07 SUMMARY records the bash-level reproductions after the fix; this human-verification item confirms the full hook still wires through to the actual git-staging hook interaction.

### Gaps Summary

The phase ships the architecture and the production-quality implementation intended by the goal: three async adapters share a single `ChatChunk` Pydantic discriminated union, implement a one-method `BackendAdapter` Protocol, enforce per-turn cost caps (with correct arithmetic after CR-02 closure), per-iteration step caps, and 2-second cancellation via PEP 789. The redaction subsystem is now self-consistent (CR-05 closure: `Bearer sk-ant-…` redacts as a single unit; CR-04 closure: the pre-commit hook regex matches the runtime filter's regex exactly, enforced by a parity test and a dedicated CI step). The Claude Code FileDiff branch is reachable from real SDK events (CR-01 closure: per-`stream()` `_pending_tool_calls` dict pairs ToolUseBlock id with ToolResultBlock tool_use_id).

The full non-live test suite is GREEN (233 passed, 2 skipped, 3 deselected in 79.39 s), the D-19 shared contract suite is 17/18 green (1 intentional skip), and the Phase 1 D-18 import-graph guard remains green (7/7). The full Phase 2 backend non-live suite is at 133 passed (4 more than the pre-gap-closure 129 baseline: +1 from CR-01 regression, +1 from CR-02 regression, +2 from CR-04/CR-05 regressions).

**No outstanding gaps.** The four previously-FAILED truths (19, 20, 21, 22) flip to VERIFIED after the gap-closure plans. The advisory CR-03 / WR-01 / WR-02 / WR-03 / WR-08 / WR-09 items remain as carry-forward warnings — they do NOT invalidate any Phase 2 must-have truth and were intentionally out of the gap-closure scope per the prior verification's classification.

**Status is `human_needed` (not `passed`) because four items still require BYOK / external-service operator approval.** These are unchanged in shape from the prior report, but two are sharper now: Truth 21's live test was predicted to FAIL pre-CR-01 closure and is now a meaningful confirmation; the pre-commit deliberate-paste test gets two new regression reproductions that previously slipped through.

**Recommendation:** Phase 2 is code-complete and re-verifier-green for everything automatable. Schedule the four BYOK live-smoke commands when operator credentials are at hand. The carry-forward Warnings (WR-01..WR-09, CR-03) should be tracked into Phase 3 prep or addressed in a follow-up cleanup plan, but they do NOT block phase closure.

---

_Verified: 2026-05-15T21:48:03Z_
_Verifier: Claude (gsd-verifier)_
