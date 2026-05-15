---
phase: 02
slug: backend-adapters-chatchunk-contract
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-14
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.x with `pytest-asyncio` + `pytest-timeout` |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (extends Phase 1; adds `asyncio_mode = "auto"`, `markers = ["live: hits real provider APIs (BYOK required)"]`) |
| **Quick run command** | `uv run pytest -x -q -m 'not live' apps/api/backends` |
| **Full suite command** | `uv run pytest -m 'not live'` |
| **Estimated runtime** | ~15 seconds (offline fakes only; live suite is opt-in) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -x -q -m 'not live' <touched-paths>` (e.g., `uv run pytest -x -q -m 'not live' apps/api/backends/openrouter`)
- **After every plan wave:** Run `uv run pytest -m 'not live'` (full `apps/api/` + `src/routing/` combined)
- **Before `/gsd-verify-work`:** Full suite must be green AND Phase 1 D-18 import-graph guard (`src/routing/tests/test_decide_smoke.py`) still passes
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-00-T3 | 00 (scaffold) | 0 | BACKEND-01 | — | N/A | unit | `pytest apps/api/backends/tests/test_chunks.py -x` | ✅ | ✅ green |
| 02-00-T3 | 00 (scaffold) | 0 | BACKEND-02 | — | N/A | unit | `pytest apps/api/backends/tests/test_adapter_contract.py::test_protocol_compliance -x` | ✅ | ✅ green |
| 02-00-T3 | 00 (scaffold) | 0 | SECURE-01 | T-02-01 | Logger redaction filter rewrites `sk-`, `sk-ant-`, `Bearer …` to `***REDACTED***` before any handler sees the record | unit | `pytest apps/api/backends/tests/test_logging_filter.py -x` | ✅ | ✅ green |
| 02-00-T3 | 00 (scaffold) | 0 | SECURE-04 | T-02-02 | `KeyStore.get` falls back to env; `keyring` lazy-import; in-memory by default; never writes plaintext to disk | unit | `pytest apps/api/backends/tests/test_keystore.py -x` | ✅ | ✅ green |
| 02-00-T3 | 00 (scaffold) | 0 | BACKEND-06 / BACKEND-07 | T-02-03 | Cost cap aborts mid-stream; step cap aborts; `aclose()` lands `StreamError + Done` within 2 s | unit (D-19 shared) | `pytest apps/api/backends/tests/test_adapter_contract.py -x` | ✅ | ✅ green |
| 02-01-T3 | 01 (OpenRouter) | 1 | BACKEND-03 | — | `HTTP-Referer` + `X-Title` headers attach to every OpenRouter request; provider keys never logged | unit (fake injection) + opt-in live | `pytest apps/api/backends/openrouter/tests/test_adapter.py -x` | ✅ | ✅ green |
| 02-02-T3 | 02 (Claude Code) | 1 | BACKEND-04 | T-02-04 | `ClaudeSDKClient.interrupt()` fires on cancel; `FileDiff` emitted for `Edit`/`Write` | unit (fake) + opt-in live | `pytest apps/api/backends/claude_code/tests/test_adapter.py -x` | ✅ | ✅ green |
| 02-02-T1 | 02 (Claude Code) | 1 | BACKEND-08 | T-02-05 | Per-thread tmpdir under `~/.prompt-optimizer/workspaces/<thread_id>/` (Phase 2 uses `tempfile.mkdtemp`); workspace removed on exit | unit | `pytest apps/api/backends/claude_code/tests/test_workspace.py -x` | ✅ | ✅ green |
| 02-02-T1 | 02 (Claude Code) | 1 | BACKEND-09 | — | `CLAUDE_ENABLE_STREAM_WATCHDOG=1` set in adapter environment at import | unit (env smoke) | `pytest apps/api/backends/claude_code/tests/test_watchdog_env.py -x` | ✅ | ✅ green |
| 02-03-T3 | 03 (computer-use) | 1 | BACKEND-05 | — | computer-use-2025-11-24 beta header set; `computer_20251124` tool registered; agent loop emits `Screenshot` base64 | unit (fake screen + anthropic) + opt-in live | `pytest apps/api/backends/computer_use/tests/test_adapter.py -x` | ✅ | ✅ green |
| 02-03-T1 | 03 (computer-use) | 1 | SECURE-05 | T-02-06 | `ComputerUseAdapter.__init__` raises `RuntimeError` unless `COMPUTER_USE_OPT_IN=1` is set — BEFORE any provider client is constructed | unit | `pytest apps/api/backends/computer_use/tests/test_optin.py -x` | ✅ | ✅ green |
| 02-04-T1 | 04 (pre-commit + CI) | 2 | SECURE-02 | T-02-07 | `.pre-commit-config.yaml` blocks staged content matching `sk-`, `sk-ant-`, `Bearer …` regex | manual + CI (`pre-commit run --all-files`) | `pre-commit run --all-files` | ✅ | ✅ green |
| 02-04-T2 | 04 (pre-commit + CI) | 2 | OSS-06 | — | `from claude_agent_sdk import ClaudeAgentOptions` succeeds; `claude-code-sdk` not in `uv.lock`; pre-commit + CI both guard | CI gate | `python -c "from claude_agent_sdk import ClaudeAgentOptions"; ! grep -q '"claude-code-sdk"' uv.lock` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Note: Task IDs match the committed PLAN.md files. Each 02-NN-TM entry refers to Task M in Plan 02-NN. Wave 0 = Plan 02-00; Wave 1 = Plans 02-01/02/03; Wave 2 = Plan 02-04.*

---

## Wave 0 Requirements

Phase 1 left zero test infrastructure for `apps/`. Wave 0 of Phase 2 MUST install all of these before any adapter unit test can run:

- [ ] `apps/api/__init__.py` — `dotenv.load_dotenv()` + `install_redaction_filter()` at import (SECURE-01 + D-11)
- [ ] `apps/api/backends/__init__.py`, `protocol.py`, `chunks.py`, `keystore.py`, `logging_filter.py`, `pricing.py`, `cost.py` (D-08 shared modules)
- [ ] `apps/api/backends/tests/conftest.py` — shared fakes: `fake_openai`, `fake_claude_sdk_client`, `fake_anthropic`, `fake_screen` (D-18)
- [ ] `apps/api/backends/tests/test_chunks.py` — Pydantic discriminated-union round-trip (BACKEND-01)
- [ ] `apps/api/backends/tests/test_adapter_contract.py` — D-19 shared parametric suite (6 invariants × 3 adapters)
- [ ] `apps/api/backends/tests/test_logging_filter.py` — SC #3 redaction regression (SECURE-01)
- [ ] `apps/api/backends/tests/test_keystore.py` — env fallback + lazy keyring (SECURE-04)
- [ ] `apps/api/backends/tests/test_pricing.py` — static load + OpenRouter `/api/v1/models` merge math (per-token decimal × 1,000,000 → per-Mtok float)
- [ ] `apps/api/backends/openrouter/{__init__,__main__,adapter,cost,errors}.py` (D-08)
- [ ] `apps/api/backends/openrouter/tests/{conftest.py, fakes.py, test_adapter.py, test_live.py}`
- [ ] `apps/api/backends/claude_code/{__init__,__main__,adapter,cost,errors,workspace,step_counter}.py` — `__init__.py` sets `CLAUDE_ENABLE_STREAM_WATCHDOG=1` via `os.environ.setdefault` (BACKEND-09)
- [ ] `apps/api/backends/claude_code/tests/{conftest.py, fakes.py, test_adapter.py, test_workspace.py, test_watchdog_env.py, test_live.py}`
- [ ] `apps/api/backends/computer_use/{__init__,__main__,adapter,cost,errors,screen,step_counter}.py` (D-13 Playwright wrapper)
- [ ] `apps/api/backends/computer_use/tests/{conftest.py, fakes.py, test_adapter.py, test_optin.py, test_live.py}`
- [ ] `config/pricing.json` — initial 9 OpenRouter-verified slugs + `anthropic/claude-opus-4-7` + `anthropic/claude-sonnet-4-6` + `_default` (D-17)
- [ ] `.pre-commit-config.yaml` + `scripts/no-secrets.sh` + `scripts/no-deprecated-sdk.sh` (D-09)
- [ ] `.github/workflows/ci.yml` — extend with `uv sync --locked --extra keyring`, `pre-commit run --all-files`, OSS-06 import smoke + `claude-code-sdk` grep, `pytest -m 'not live' apps/api/backends`, keep `pytest src/` (D-20)
- [ ] `.github/workflows/live-smoke.yml` (optional) — manual + weekly cron with `--live-budget=$0.10`, `continue-on-error: true`
- [ ] Framework install: add `pytest-asyncio>=0.24`, `pytest-timeout>=2.3`, `pydantic>=2.6,<3.0`, `openai>=1.40,<3.0`, `anthropic>=0.40,<1.0`, `claude-agent-sdk>=0.1.80,<0.2`, `playwright>=1.45,<2.0`, `python-dotenv>=1.0,<2.0`, `pre-commit>=4.0,<5.0`, `[project.optional-dependencies] keyring = ["keyring>=24,<26"]` to `pyproject.toml`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| End-to-end OpenRouter live smoke against the real API | BACKEND-03 | Hits a paid provider; BYOK required; non-deterministic completion text | `OPENROUTER_API_KEY=… uv run pytest -m live apps/api/backends/openrouter/tests/test_live.py -x` — assert one TextDelta + Done with `cost_usd > 0` |
| End-to-end Claude Code live smoke (build-and-edit a hello.py in a tmp workspace) | BACKEND-04 | Spawns the real `claude` subprocess; BYOK required; mutates a tmp file | `ANTHROPIC_API_KEY=… uv run pytest -m live apps/api/backends/claude_code/tests/test_live.py -x` — assert at least one `FileDiff`, terminal `Done` with `total_cost_usd > 0` |
| End-to-end computer-use live smoke (open `https://example.com`, screenshot, narrate) | BACKEND-05 | Launches real Chromium + paid provider call; requires `COMPUTER_USE_OPT_IN=1` and `ANTHROPIC_API_KEY` | `COMPUTER_USE_OPT_IN=1 ANTHROPIC_API_KEY=… uv run pytest -m live apps/api/backends/computer_use/tests/test_live.py -x` — assert at least one `Screenshot`, one `ToolCall`, terminal `Done` |
| Per-adapter CLI smoke (Phase 2 SC #1) | BACKEND-03 / 04 / 05 + SC #1 | Verifies the `python -m apps.api.backends.<backend> --prompt "..."` JSON-line shape end-to-end | `python -m apps.api.backends.openrouter --prompt "say hi"` (etc.) — every line MUST `json.loads()` to a valid `ChatChunk`; last line MUST be `type=done` |
| OpenRouter attribution headers verified against captured request | BACKEND-03 | Header presence is asserted in unit via the recorder fake; live verification optional | Inspect `responses` recording in `test_adapter.py` for `HTTP-Referer` + `X-Title` |
| Pre-commit hook live block on a deliberate paste of `sk-ant-…` | SECURE-02 / T-02-07 | Tests the actual git-staging interaction (not the script in isolation) | `echo "sk-ant-AAAAAAAAAAAAAAAAAAAA" >> test.tmp && git add test.tmp && git commit -m "test"` → MUST fail; clean up `git rm -f test.tmp` |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (apps/api scaffolding, fakes, pre-commit, CI extensions)
- [x] No watch-mode flags (`-x -q` for fast-fail-quiet only)
- [x] Feedback latency < 15s (offline suite estimate; live suite excluded)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (B4 fix; task IDs reconciled with committed plans 02-00..02-04)
