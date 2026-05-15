# Phase 2: Backend Adapters & ChatChunk Contract - Research

**Researched:** 2026-05-15
**Domain:** Async streaming backend adapters (OpenAI SDK + claude-agent-sdk + anthropic SDK + Playwright) behind a Pydantic v2 discriminated union
**Confidence:** HIGH (primary SDK contracts verified against official docs and live endpoints; one secondary-confidence area called out in Open Questions)

## Summary

Phase 2 wires three async backend adapters behind a single Pydantic v2 `ChatChunk` discriminated union. Every locked decision in CONTEXT.md was research-validated against current (May 2026) official documentation. The SDK contract for each backend is well-understood and there are no blocking unknowns; one critical adapter shape decision was sharpened by research (**Claude Code adapter must use `ClaudeSDKClient`, NOT the standalone `query()` function**, because only the client has `interrupt()` for D-04 cancellation).

The three adapters share a stable pattern: construct an async stream → for each upstream event, emit one or more `ChatChunk` Pydantic instances → after each emission, check the per-adapter `CostTracker.over_cap()` and per-adapter step counter → on caps/cancellation/exception, emit terminal `[StreamError]?` + `Done` pair → in `finally`, run cleanup (close httpx, close Playwright, call `interrupt()`). All three adapters honor the same `BackendAdapter` Protocol, which makes D-19's parametric contract test the right enforcement mechanism.

**Primary recommendation:** Use `pydantic>=2.6,<3.0` with `Annotated[Union[...], Field(discriminator="type")]` for ChatChunk; for OpenRouter use the OpenAI SDK's `async with client.chat.completions.stream(...) as stream:` pattern (NOT raw `stream=True`); for Claude Code use `ClaudeSDKClient` not `query()`; for computer-use run an explicit `while True` agent loop around `client.beta.messages.create(..., stream=True)` with Playwright `async_playwright()` driving the screen layer.

## User Constraints (from CONTEXT.md)

> Copied verbatim from `.planning/phases/02-backend-adapters-chatchunk-contract/02-CONTEXT.md`. The planner MUST honor these.

### Locked Decisions

**ChatChunk Contract:**

- **D-01: ChatChunk is a Pydantic v2 BaseModel discriminated union** keyed by a `Literal["text_delta" | "tool_call" | "tool_result" | "file_diff" | "screenshot" | "stream_error" | "done"]` `type` field. Each variant is a `BaseModel` with its own fields; the union is `Annotated[Union[...], Field(discriminator="type")]`. Pydantic is added as a Phase 2 base dependency (`pydantic>=2.6,<3.0`); Phase 3 FastAPI uses it natively, so there is no double-cost. `model_dump_json()` will be the SSE serializer in Phase 3. Adapter signatures use the union type; runtime validation is automatic.
- **D-02: BACKEND-01's six-variant union grows to seven by adding `ToolResult`.** REQUIREMENTS-BACKEND-01 enumerates `TextDelta | ToolCall | Screenshot | FileDiff | StreamError | Done`. We add a generic `ToolResult` variant so non-edit tools (Bash stdout, Read file contents, computer-use action narration) carry a typed result chunk linked back to the originating call. `FileDiff` remains the typed specialization for `Edit` / `Write`. Update REQUIREMENTS.md BACKEND-01 wording to `TextDelta | ToolCall | ToolResult | FileDiff | Screenshot | StreamError | Done` as part of this phase.
- **D-03: Tool calls and their results are flat sibling chunks linked by `tool_call_id`.** Both `ToolCall` and the matching `ToolResult` / `FileDiff` carry `tool_call_id: str`. The UI joins on this id to render the result under its call. Wire order is causal (call before result) but the schema does not require nesting.
- **D-04: Every stream terminates with `[StreamError]?` then `Done` — `Done` always lands.** Happy path: `… TextDelta(s) … Done`. Abnormal: `… StreamError(code, message, retriable) Done(metrics-so-far)`. Cancellation = `StreamError(code="cancelled", retriable=True)` + `Done`.
- **D-05: TextDelta is pass-through — one TextDelta per provider event, no coalescing.**
- **D-06: StreamError carries `code: str`, `message: str`, `retriable: bool`.** Closed initial vocabulary: `cost_cap_exceeded`, `step_cap_exceeded`, `cancelled`, `rate_limited`, `auth_failed`, `provider_unavailable`, `timeout`, `validation_error`, `internal_error`.

**Module Layout:**

- **D-07: Birth `apps/` now — adapters live at `apps/api/backends/<backend>/`.** `pyproject.toml` `[tool.hatch.build.targets.wheel] packages = ["src", "apps"]`.
- **D-08: Per-backend directory with split modules** (`__init__.py`, `__main__.py`, `adapter.py`, `cost.py`, `errors.py`, helpers, `tests/`). Shared modules at `apps/api/backends/` (`protocol.py`, `chunks.py`, `keystore.py`, `logging_filter.py`, `pricing.py`, `cost.py`, `tests/test_adapter_contract.py`).
- **D-09: SECURE-02 pre-commit hook ships via the `pre-commit` framework.** Two local hooks: `no-secrets` (regex `^\+.*(sk-ant-[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9]{20,}|Bearer [A-Za-z0-9_.-]{20,})`) and `no-deprecated-claude-code-sdk`.
- **D-10: `keyring` is an optional extra, lazy-loaded.** `[project.optional-dependencies] keyring = ["keyring>=24,<26"]`. Linux dbus-python transitive is gated behind the extra.
- **D-11: BYOK keys flow via `python-dotenv` loaded at `apps/api/__init__.py` import.** `dotenv.load_dotenv()` + `install_redaction_filter()` at import. Env var convention: `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `COMPUTER_USE_OPT_IN`.

**Computer-Use:**

- **D-12: Adapter owns the full agent loop.** Internal screenshot → model → action → screenshot loop. Per-iteration chunks: `TextDelta` (commentary), `ToolCall` (action), `Screenshot` (post-action), `ToolResult` (narration).
- **D-13: Execution target is a Playwright Chromium sandbox per turn.** 1280×800 viewport. Actions: `click(x,y)` → `page.mouse.click`; `screenshot()` → `page.screenshot(type="png")`; `key(name)` → `page.keyboard.press`; `type(text)` → `page.keyboard.type`; `navigate(url)` → `page.goto`. Add `playwright>=1.45,<2.0`.
- **D-14: Screenshot chunk is base64-inline in Phase 2.** Fields: `image_b64: str | None`, `image_ref: str | None`, `image_format: Literal["png","jpeg"] = "png"`, `step: int`.
- **D-15: "Step" = agent loop iteration for both adapters; cap = 15 (computer-use), 25 (Claude Code).** Step exhaustion emits `StreamError(code="step_cap_exceeded", retriable=False)` + `Done`. Update REQUIREMENTS.md BACKEND-06 wording to "per-iteration step cap (25 for Claude Code, 15 for computer-use)".

**Cost Caps:**

- **D-16: `CostTracker` base class** with `record_input(n)`, `record_output_delta(n)`, `total() -> float`, `over_cap() -> bool`. Each adapter subclasses.
- **D-17: `config/pricing.json`** schema `{"<model_id>": {"input_per_mtok": float, "output_per_mtok": float}, "_default": {...}}`. OpenRouter adapter attempts `GET https://openrouter.ai/api/v1/models` on startup; 24h cache at `~/.prompt-optimizer/cache/openrouter_models.json`. Initial entries: the 9 OpenRouter-verified slugs from Phase 1's `config/model_mapping.json` + `anthropic/claude-opus-4-7` + `anthropic/claude-sonnet-4-6` + `_default: {input_per_mtok: 5.00, output_per_mtok: 20.00}`.

**Tests / CI:**

- **D-18: Tiered test strategy.** Hand-stubbed fakes (`FakeOpenAIClient`, `FakeAnthropicClient`, `fake_claude_code_query`, `FakePlaywrightScreen`) for unit tests. Opt-in `@pytest.mark.live` for real-provider smoke.
- **D-19: Shared `BackendAdapter` contract test parameterized across all 3 adapters.** 6 invariants (happy path, cost cap, step cap, cancellation within 2 s, terminal Done, missing-key raises before stream).
- **D-20: CI green = uv-sync + pre-commit + import-smoke + redaction test + `pytest -m 'not live'`.** Live smoke is a separate manual + weekly cron workflow.

### Claude's Discretion

- **Async runtime:** asyncio (default; matches FastAPI Phase 3).
- **Cancellation:** prefer natural `aclose()` → upstream `interrupt()` / aborted HTTP path. No custom cancel-token API.
- **Pydantic version:** `pydantic>=2.6,<3.0`. Researcher pins exact lower bound based on `model_config` features used.
- **OpenRouter attribution:** `HTTP-Referer = "https://github.com/<owner>/Prompt-Optimizer"`, `X-Title = "Prompt-Optimizer"`.
- **claude-agent-sdk MCP tool list:** `["Read", "Edit", "Write", "Bash", "Glob", "Grep"]` for v1.
- **`CLAUDE_ENABLE_STREAM_WATCHDOG=1`:** set via `os.environ.setdefault(...)` at `apps/api/backends/claude_code/__init__.py` import.
- **Per-thread workspace path template:** `~/.prompt-optimizer/workspaces/<thread_id>/`. Phase 2 CLI uses `tempfile.mkdtemp(prefix="pomu-cc-")`.
- **`Done.routing_signals: dict | None`** surfaces `RoutingDecision.signals`.
- **Pre-flight token estimator:** any reasonable approach — see Code Examples below.

### Deferred Ideas (OUT OF SCOPE)

- Gitleaks / detect-secrets full secret scanner — Phase 6 OSS hardening.
- Settings panel BYOK entry — Phase 5 UI-12.
- Disk-by-hash blob writes for screenshots — Phase 3 STORE-04.
- Pricing refresh from Anthropic models endpoint — no public pricing API, defer.
- `RoutingDecision.signals` → `routing_decisions.jsonl` — Phase 3 STORE-06.
- Cross-backend handoff, model fallback chain — v2.
- VCR cassettes for adapter tests — defer to cleanup phase if fakes drift.

## Project Constraints (from CLAUDE.md)

Extracted from `/Users/michaelmarrero/GitHub/Prompt-Optimizer/CLAUDE.md`:

- **Python pipeline tech stack:** Python 3.10+ with scikit-learn / pandas / scipy / joblib / sentence-transformers / nltk. Preserve compatibility with saved artifacts. [VERIFIED: pyproject.toml `requires-python = ">=3.10"`]
- **Web stack:** Next.js (TypeScript) front-end + FastAPI (Python) back-end. Phase 2 sets up the FastAPI side's adapter layer (FastAPI itself lands in Phase 3). [VERIFIED: PROJECT.md]
- **BYOK key handling:** Keys never leave the user's local instance. Adapters must not log raw key material. [VERIFIED: SECURE-01 requirement and `apps/api/backends/logging_filter.py` per D-11]
- **Optimization target:** Quality first, cost as tiebreaker. Cost caps are a hard ceiling, not an optimization target. [VERIFIED: BACKEND-06]
- **No fine-tuning of generative LLMs.** Phase 2 only routes; no model training. [VERIFIED: no training in scope]
- **GSD Workflow Enforcement:** Use `/gsd-execute-phase` for planned phase work. Do not make direct repo edits outside the GSD workflow. [Planner-level constraint, not adapter-design constraint.]
- **Module naming:** snake_case for modules. One legacy exception: `src/feature_extraction/Feature_extractor.py` (CamelCase). All Phase 2 new modules MUST be snake_case. [VERIFIED: CONVENTIONS.md]
- **Indentation:** 4 spaces, PEP 8.
- **Section headers:** wide ASCII comment banners are a deliberate pattern.
- **Import organization:** No path aliases or installed-package imports today; Phase 2 introduces `from apps.api.backends.chunks import …`. Existing `sys.path` injection for `Feature_extractor` stays (CLAUDE.md documents this as legacy).
- **Logging:** Training/inference scripts use `print()`; data pipeline scripts use `logging`. Adapters are NOT training/inference scripts → use `logging.getLogger(__name__)` so the redaction filter applies (CONTEXT D-11 anti-pattern: direct `print()` of keys is forbidden).
- **Type hints:** PEP 585 generics (`list[str]`, `dict[str, Any]`) are acceptable in newer modules. Phase 2 is greenfield → use them everywhere.
- **Persistence pattern:** `joblib.dump(dict, path)` with required-key validation. Phase 2 does NOT add new joblib artifacts; the parallel pattern is the Pydantic-validated `ChatChunk` dict shape.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BACKEND-01 | `ChatChunk` discriminated union | Pydantic v2 syntax verified — Pattern 1 |
| BACKEND-02 | `BackendAdapter` Protocol | `typing.Protocol` stdlib pattern — Pattern 2 |
| BACKEND-03 | OpenRouter adapter via OpenAI SDK 1.40+ | OpenAI SDK 2.36.0 streaming API verified — Pattern 3 |
| BACKEND-04 | Claude Code via claude-agent-sdk 0.1.80+ | `ClaudeSDKClient` with `interrupt()` verified — Pattern 4. **NOT** standalone `query()` (no interrupt) |
| BACKEND-05 | Computer-use via anthropic 0.40+ | `anthropic 0.102.0` `client.beta.messages.create` + `betas=["computer-use-2025-11-24"]` verified — Pattern 5 |
| BACKEND-06 | Per-turn USD cap + per-iteration step cap | `CostTracker` + `step_counter` design — Pattern 6 |
| BACKEND-07 | Mid-stream cancellation | `asyncio.CancelledError` propagation chain — Pattern 7 |
| BACKEND-08 | Per-thread ephemeral workspace | `tempfile.mkdtemp(prefix="pomu-cc-")` + `cwd` in `ClaudeAgentOptions` — Pattern 8 |
| BACKEND-09 | `CLAUDE_ENABLE_STREAM_WATCHDOG=1` | `os.environ.setdefault(...)` at module import — Pattern 9 |
| SECURE-01 | Logging redaction filter at process import | `logging.Filter` subclass that mutates `record.msg` — Pattern 10 |
| SECURE-02 | Pre-commit hook blocks `sk-` / `sk-ant-` / `Bearer …` | pre-commit framework local script hook — Pattern 11 |
| SECURE-04 | BYOK keys in memory + optional keyring | `keyring 25.x` with lazy import — Pattern 12 |
| SECURE-05 | Computer-use OFF unless `COMPUTER_USE_OPT_IN=1` | Constructor-time env-var check — Pattern 13 |
| OSS-06 | `claude_agent_sdk` import smoke; `claude-code-sdk` absent | Triad: CI smoke + uv.lock grep + pre-commit hook — Pattern 14 |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| ChatChunk schema + Protocol | API / Backend (shared) | — | `apps/api/backends/{chunks,protocol}.py`. Phase 3 FastAPI imports both. Browser tier never sees Pydantic. |
| OpenRouter adapter | API / Backend | — | `apps/api/backends/openrouter/`. Owns OpenAI SDK client + cost tracker + cancellation. |
| Claude Code adapter | API / Backend | OS subprocess | `apps/api/backends/claude_code/`. claude-agent-sdk spawns a Claude CLI subprocess; adapter inherits the env var (`CLAUDE_ENABLE_STREAM_WATCHDOG=1`). |
| Computer-use adapter | API / Backend | OS subprocess (Playwright Chromium) | `apps/api/backends/computer_use/`. Owns the full agent loop + Playwright lifecycle. Browser is sandboxed in headless Chromium. |
| Key store (BYOK) | API / Backend | OS keyring (optional) | `apps/api/backends/keystore.py`. In-memory primary; `keyring 25.x` as optional disk persistence. |
| Logging redaction | API / Backend (process-wide) | — | `apps/api/backends/logging_filter.py`. Installed at `apps/api/__init__.py` import. Mutates `logging.LogRecord` before any handler. |
| Pricing table | API / Backend | External (OpenRouter `/api/v1/models`) | `apps/api/backends/pricing.py`. Static JSON + optional 24h refresh from OpenRouter. |
| Pre-commit hook | Repo tooling (build-time) | — | `.pre-commit-config.yaml` + `scripts/no-secrets.sh` + `scripts/no-deprecated-sdk.sh`. Runs in developer's git, not in process. |
| CI smoke for OSS-06 | CI runner | — | `.github/workflows/ci.yml`. Runs `from claude_agent_sdk import ClaudeAgentOptions` import smoke + `uv.lock` grep. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pydantic` | `>=2.6,<3.0` | `ChatChunk` discriminated union; per-chunk runtime validation | Locked by D-01. `Annotated[Union[...], Field(discriminator=...)]` stable since v2.0; pinning `>=2.6` matches the locked range. Phase 3 FastAPI uses it natively (zero double-cost). [VERIFIED: pypi pydantic 2.13.4 released 2026-05-06; pyproject.org] |
| `openai` | `>=1.40,<3.0` | OpenRouter adapter; OpenAI-compatible chat completions streaming | Locked by BACKEND-03. Latest is 2.36.0 (2026-05-07). [VERIFIED: pypi openai 2.36.0 supports Python 3.9-3.14, async client via httpx] |
| `anthropic` | `>=0.40,<1.0` | Computer-use adapter; `client.beta.messages.create` with `betas=["computer-use-2025-11-24"]` | Locked by BACKEND-05. Latest is 0.102.0 (2026-05-13). [VERIFIED: pypi anthropic 0.102.0] |
| `claude-agent-sdk` | `>=0.1.80,<0.2` | Claude Code adapter (build-and-edit) | Locked by BACKEND-04. Latest is 0.1.81 (2026-05-11). Replaces deprecated `claude-code-sdk`. [VERIFIED: pypi claude-agent-sdk 0.1.81, github CHANGELOG.md] |
| `playwright` | `>=1.45,<2.0` | Computer-use Chromium sandbox | Locked by D-13. Latest is 1.59.0 (2026-04-29). [VERIFIED: pypi playwright 1.59.0] |
| `python-dotenv` | `>=1.0,<2.0` | `.env` loading at `apps/api/__init__.py` import | Locked by D-11. Standard for BYOK in open-source Python apps. [CITED: pypi python-dotenv] |
| `pre-commit` | `>=4.0,<5.0` | Local hook framework for SECURE-02 | Locked by D-09. Latest is 4.6.0 (2026-04-21). [VERIFIED: pypi pre-commit 4.6.0] |
| `pytest` | `>=9.0,<10.0` (already in dev) | Test runner; `pytest.mark.live` and `pytest.mark.timeout(2)` for D-19 invariants | Already pinned in Phase 1 `pyproject.toml` `[project.optional-dependencies] dev`. [VERIFIED: pyproject.toml line 21] |
| `pytest-asyncio` | `>=0.24,<2.0` | Async test fixtures (`@pytest_asyncio.fixture`, `asyncio_mode = "auto"`) | NOT in Phase 1 deps. MUST add to `[project.optional-dependencies] dev`. [VERIFIED: pypi pytest-asyncio active] |
| `pytest-timeout` | `>=2.3,<3.0` | `@pytest.mark.timeout(2)` for D-19 cancellation invariant | NOT in Phase 1 deps. MUST add. [VERIFIED: pypi pytest-timeout standard for timeout enforcement] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `keyring` | `>=24,<26` | Optional disk persistence for BYOK keys per D-10 | `uv sync --extra keyring` opt-in. Latest is 25.7.0 (2025-11-16). [VERIFIED: pypi keyring 25.7.0] |
| `tiktoken` | `>=0.7,<1.0` | Pre-flight token estimator for OpenAI-family models (CONTEXT discretion) | Use for OpenRouter input-token estimation BEFORE the call. Real cost comes from `usage` in streamed response. [CITED: openai-cookbook] |
| `httpx` | (transitive via openai/anthropic) | Underlying async HTTP client | Don't add directly; the SDKs ship httpx. Adapter cancellation flows through httpx's `AsyncClient.aclose()`. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `pydantic` v2 discriminated union | stdlib `@dataclass` + manual `type` switch | Drops runtime validation, drops `model_dump_json()` for Phase 3 SSE serialization, drops type-narrowing on the union. Pydantic is mandatory anyway because Phase 3 FastAPI uses it. **D-01 locks this — no alternative.** |
| `openai` SDK against OpenRouter | `httpx` directly + raw SSE parsing | Drops free OpenAI-compatible types (`ChatCompletionChunk`, `ChoiceDelta`). BACKEND-03 says "using OpenAI SDK v1.40+" → no alternative. |
| `claude-agent-sdk.query()` standalone function | `ClaudeSDKClient.connect()` + `query()` + `interrupt()` | The standalone `query()` returns a stateless async iterator with NO `interrupt()` method. **For BACKEND-07 cancellation we MUST use `ClaudeSDKClient`.** [VERIFIED: github client.py — `interrupt()` is on the client class, not the standalone function] |
| `anthropic` SDK `messages.stream()` context manager | `messages.create(stream=True)` raw async iterator | The context manager (`async with client.beta.messages.stream(...) as stream:`) auto-cleans the response. Locked path. |
| `tiktoken` for Anthropic pre-flight | `anthropic.messages.count_tokens()` (free endpoint) | `count_tokens` is a real network call (free but adds latency); tiktoken is local-only but underestimates Claude. **For Phase 2's pre-flight estimator (CONTEXT discretion), use char-count / 4 as a rough lower bound for Anthropic — tiktoken's gpt-4 encoder is fine for OpenRouter models.** |
| `pre-commit` framework local hook | Raw `.git/hooks/pre-commit` shell script | Loses shared install (`pre-commit install`), shared CI integration (`pre-commit run --all-files`), shared config schema. D-09 locks pre-commit framework. |
| `keyring` 25.x with optional extra | Mandatory `keyring` dep | Linux installs would pull `dbus-python` transitively (compilation often fails). D-10 locks the optional-extra approach. |

**Installation (Phase 2 additions to `pyproject.toml`):**

```toml
[project]
dependencies = [
    # ... Phase 1 deps ...
    "pydantic>=2.6,<3.0",
    "openai>=1.40,<3.0",
    "anthropic>=0.40,<1.0",
    "claude-agent-sdk>=0.1.80,<0.2",
    "playwright>=1.45,<2.0",
    "python-dotenv>=1.0,<2.0",
    "pre-commit>=4.0,<5.0",
]

[project.optional-dependencies]
dev = [
    # ... Phase 1 dev deps ...
    "pytest-asyncio>=0.24,<2.0",
    "pytest-timeout>=2.3,<3.0",
]
keyring = ["keyring>=24,<26"]

[tool.hatch.build.targets.wheel]
packages = ["src", "apps"]

[tool.pytest.ini_options]
testpaths = ["src", "apps"]
python_files = ["test_*.py"]
addopts = "-x -q --import-mode=importlib"
asyncio_mode = "auto"
markers = [
    "live: hits real provider APIs (BYOK required); skipped by default",
]
```

**Version verification (verified at research time, 2026-05-15):**

| Package | Verified Latest | Source |
|---------|-----------------|--------|
| `pydantic` | 2.13.4 (2026-05-06) | [pypi.org/project/pydantic/](https://pypi.org/project/pydantic/) |
| `openai` | 2.36.0 (2026-05-07) | [pypi.org/project/openai/](https://pypi.org/project/openai/) |
| `anthropic` | 0.102.0 (2026-05-13) | [pypi.org/project/anthropic/](https://pypi.org/project/anthropic/) |
| `claude-agent-sdk` | 0.1.81 (2026-05-11) | [pypi.org/project/claude-agent-sdk/](https://pypi.org/project/claude-agent-sdk/) |
| `playwright` | 1.59.0 (2026-04-29) | [pypi.org/project/playwright/](https://pypi.org/project/playwright/) |
| `keyring` | 25.7.0 (2025-11-16) | [pypi.org/project/keyring/](https://pypi.org/project/keyring/) |
| `pre-commit` | 4.6.0 (2026-04-21) | [pypi.org/project/pre-commit/](https://pypi.org/project/pre-commit/) |

## Architecture Patterns

### System Architecture Diagram

```
                       Phase 1: RoutingDecision (frozen dataclass, stdlib only)
                              │ backend, model_or_agent, rationale, signals
                              ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  apps/api/backends/ (Phase 2 — shared layer)                         │
   │                                                                      │
   │    protocol.py    BackendAdapter Protocol                            │
   │    chunks.py      ChatChunk = TextDelta | ToolCall | ToolResult |    │
   │                              FileDiff | Screenshot | StreamError |   │
   │                              Done   (Pydantic v2 discriminated)      │
   │    keystore.py    KeyStore (in-memory + optional keyring)            │
   │    logging_filter.py  RedactionFilter (installed at import)          │
   │    pricing.py     PricingTable (config/pricing.json + OR refresh)    │
   │    cost.py        CostTracker base class                             │
   └──────────────────────────────────────────────────────────────────────┘
              │                       │                       │
              ▼                       ▼                       ▼
   ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────────┐
   │ openrouter/      │   │ claude_code/     │   │ computer_use/        │
   │  adapter.py      │   │  adapter.py      │   │  adapter.py          │
   │  AsyncOpenAI     │   │  ClaudeSDKClient │   │  AsyncAnthropic +    │
   │  → stream.create │   │  → connect()     │   │   beta.messages      │
   │  → async for     │   │  → query()       │   │  → manual agent loop │
   │  → ChatChunk     │   │  → receive_*()   │   │  → Playwright Screen │
   │                  │   │  → interrupt()   │   │  → ChatChunk         │
   │  cost.py         │   │                  │   │                      │
   │  errors.py       │   │  cost.py         │   │  cost.py             │
   │  __main__.py     │   │  errors.py       │   │  errors.py           │
   │                  │   │  workspace.py    │   │  screen.py           │
   │                  │   │  step_counter.py │   │  step_counter.py     │
   │                  │   │  __main__.py     │   │  __main__.py         │
   └──────────────────┘   └──────────────────┘   └──────────────────────┘
              │                       │                       │
              ▼                       ▼                       ▼
        OpenRouter API           Claude CLI                Anthropic API
        (OpenAI-compat)           subprocess                +  Playwright
                                 (claude-agent-sdk)            Chromium

                       (Each adapter yields ChatChunk; D-19
                        contract test parameterizes across all 3)
```

### Recommended Project Structure

```
apps/
├── __init__.py
└── api/
    ├── __init__.py              # dotenv.load_dotenv() + install_redaction_filter()
    └── backends/
        ├── __init__.py
        ├── protocol.py          # BackendAdapter Protocol
        ├── chunks.py            # ChatChunk Pydantic union
        ├── keystore.py          # in-memory KeyStore + optional keyring
        ├── logging_filter.py    # RedactionFilter (SECURE-01)
        ├── pricing.py           # PricingTable
        ├── cost.py              # CostTracker base + DEFAULT_PER_TURN_COST_USD
        ├── tests/
        │   ├── __init__.py
        │   ├── conftest.py      # fakes, shared fixtures
        │   ├── test_chunks.py   # Pydantic union serialization round-trip
        │   ├── test_keystore.py
        │   ├── test_logging_filter.py  # redaction regression (SC #3)
        │   ├── test_pricing.py
        │   └── test_adapter_contract.py  # D-19 shared parametric suite
        ├── openrouter/
        │   ├── __init__.py
        │   ├── __main__.py
        │   ├── adapter.py
        │   ├── cost.py          # OpenRouterCostTracker
        │   ├── errors.py        # provider-error → StreamError mapping
        │   └── tests/
        │       ├── __init__.py
        │       ├── conftest.py
        │       ├── fakes.py     # FakeOpenAIClient
        │       ├── test_adapter.py
        │       └── test_live.py # @pytest.mark.live opt-in smoke
        ├── claude_code/
        │   ├── __init__.py      # os.environ.setdefault("CLAUDE_ENABLE_STREAM_WATCHDOG", "1")
        │   ├── __main__.py
        │   ├── adapter.py
        │   ├── cost.py
        │   ├── errors.py
        │   ├── workspace.py     # tempfile.mkdtemp lifecycle
        │   ├── step_counter.py
        │   └── tests/
        │       ├── ...
        └── computer_use/
            ├── __init__.py
            ├── __main__.py
            ├── adapter.py       # owns the agent loop
            ├── cost.py
            ├── errors.py
            ├── screen.py        # Playwright wrapper
            ├── step_counter.py
            └── tests/
                ├── ...

config/
└── pricing.json                 # static prices + _default

scripts/
├── no-secrets.sh                # pre-commit hook script
└── no-deprecated-sdk.sh         # pre-commit hook script

.pre-commit-config.yaml          # local hooks per D-09
.github/workflows/
├── ci.yml                       # extended per D-20
└── live-smoke.yml               # optional manual + weekly cron (D-20)
```

### Pattern 1: Pydantic v2 ChatChunk Discriminated Union

**What:** Use `Annotated[Union[T1, T2, ...], Field(discriminator="type")]` where each variant has a `type: Literal["…"]` field. Expose `ChatChunk` as the type alias and `TypeAdapter(ChatChunk)` for ingestion of unknown JSON.

**When to use:** Every adapter return value. Every cross-process boundary in Phase 3 (FastAPI SSE).

**Example:**

```python
# Source: https://pydantic.dev/docs/validation/latest/concepts/unions/ (VERIFIED)
# apps/api/backends/chunks.py
from __future__ import annotations
from typing import Annotated, Any, Literal, Union
from pydantic import BaseModel, Field, TypeAdapter


class TextDelta(BaseModel):
    type: Literal["text_delta"] = "text_delta"
    text: str


class ToolCall(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    tool_call_id: str            # set by adapter; format "tc_<6-char-base32>" (CONTEXT specifics)
    tool_name: str
    arguments: dict[str, Any]    # parsed from provider's streaming JSON


class ToolResult(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    tool_call_id: str
    content: str | dict[str, Any]
    is_error: bool = False


class FileDiff(BaseModel):
    type: Literal["file_diff"] = "file_diff"
    tool_call_id: str
    path: str
    diff: str
    operation: Literal["create", "edit", "delete"]


class Screenshot(BaseModel):
    type: Literal["screenshot"] = "screenshot"
    step: int
    image_b64: str | None = None
    image_ref: str | None = None       # Phase 3 STORE-04 conversion target
    image_format: Literal["png", "jpeg"] = "png"


class StreamError(BaseModel):
    type: Literal["stream_error"] = "stream_error"
    code: Literal[
        "cost_cap_exceeded",
        "step_cap_exceeded",
        "cancelled",
        "rate_limited",
        "auth_failed",
        "provider_unavailable",
        "timeout",
        "validation_error",
        "internal_error",
    ]
    message: str
    retriable: bool


class Done(BaseModel):
    type: Literal["done"] = "done"
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None
    routing_signals: dict[str, Any] | None = None   # carries RoutingDecision.signals (CONTEXT discretion)


# THE discriminated union — adapter signatures use this name.
ChatChunk = Annotated[
    Union[TextDelta, ToolCall, ToolResult, FileDiff, Screenshot, StreamError, Done],
    Field(discriminator="type"),
]

# For ingesting unknown JSON (Phase 3 / tests):
chat_chunk_adapter = TypeAdapter(ChatChunk)
# chat_chunk_adapter.validate_python({"type": "text_delta", "text": "hello"}) -> TextDelta
# chat_chunk_adapter.validate_json('{"type":"done"}') -> Done
```

**Notes:**

- `Literal["…"]` default value pattern means callers can `TextDelta(text="hi")` without specifying `type`. The default is `Literal`-checked by Pydantic.
- `model_dump_json()` produces the SSE payload Phase 3 will emit.
- `chat_chunk_adapter` is the right ingestion path for any JSON-line-in source (tests, persisted logs, Phase 3 storage replay).

### Pattern 2: BackendAdapter Protocol

**What:** Use `typing.Protocol` so adapters are structurally typed; no inheritance required.

**Example:**

```python
# Source: typing-Protocol stdlib pattern (HIGH confidence)
# apps/api/backends/protocol.py
from __future__ import annotations
from dataclasses import dataclass
from typing import AsyncIterator, Protocol

from apps.api.backends.chunks import ChatChunk


@dataclass(frozen=True)
class Message:
    """Conversation history element. Frozen so adapters can share by reference."""
    role: str            # "user" | "assistant" | "tool"
    content: str         # already-rendered text (Phase 2 doesn't preserve content blocks)


@dataclass(frozen=True)
class AdapterOptions:
    """Per-turn adapter options. Locked-decision defaults live in cost.py / step_counter.py."""
    model: str | None = None              # overrides the routed model_or_agent
    max_cost_usd: float | None = None     # falls back to DEFAULT_PER_TURN_COST_USD
    max_steps: int | None = None          # falls back to DEFAULT_STEP_CAP per backend
    cwd: str | None = None                # claude_code: opt-in to user's repo (BACKEND-08)
    routing_signals: dict | None = None   # from RoutingDecision.signals; surfaced on Done


class BackendAdapter(Protocol):
    async def stream(
        self,
        prompt: str,
        history: list[Message],
        options: AdapterOptions,
    ) -> AsyncIterator[ChatChunk]: ...
```

**Notes:**

- Phase 3 FastAPI lifespan uses `adapters: dict[Backend, BackendAdapter]` keyed by Phase 1's `Backend` literal (`openrouter | claude_code | computer_use`).
- `AdapterOptions` is intentionally minimal in Phase 2. UI overrides (Phase 4/5) add fields without breaking the Protocol.

### Pattern 3: OpenRouter Adapter (OpenAI SDK 2.36 + AsyncOpenAI streaming)

**What:** `async with client.chat.completions.stream(...)` is the recommended path (auto-cleanup on exit). For Phase 2 we need explicit cancellation, so use it inside a `try/finally`.

**Example:**

```python
# Source: github.com/openai/openai-python/blob/main/helpers.md (VERIFIED) +
#         openrouter.ai/docs/quickstart (VERIFIED) + live curl of /api/v1/models (VERIFIED)
# apps/api/backends/openrouter/adapter.py
from __future__ import annotations
import asyncio
import logging
import secrets
from typing import AsyncIterator

from openai import AsyncOpenAI, APIStatusError, APITimeoutError, AuthenticationError
from openai.types.chat import ChatCompletionChunk

from apps.api.backends.chunks import (
    ChatChunk, TextDelta, ToolCall, ToolResult, StreamError, Done,
)
from apps.api.backends.cost import DEFAULT_PER_TURN_COST_USD
from apps.api.backends.openrouter.cost import OpenRouterCostTracker
from apps.api.backends.protocol import Message, AdapterOptions

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
HTTP_REFERER = "https://github.com/marreroii-michael/Prompt-Optimizer"  # CONTEXT discretion
X_TITLE = "Prompt-Optimizer"


class OpenRouterAdapter:
    def __init__(
        self,
        api_key: str,
        *,
        max_cost_usd: float = DEFAULT_PER_TURN_COST_USD,
        client_factory=None,    # test injection: returns AsyncOpenAI-like
    ):
        if not api_key:
            raise AuthenticationError("OPENROUTER_API_KEY not set", response=None, body=None)
        self._client = (client_factory or self._default_client_factory)(api_key)
        self._max_cost = max_cost_usd

    @staticmethod
    def _default_client_factory(api_key: str) -> AsyncOpenAI:
        return AsyncOpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=api_key,
            default_headers={
                "HTTP-Referer": HTTP_REFERER,
                "X-Title": X_TITLE,
            },
        )

    async def stream(
        self,
        prompt: str,
        history: list[Message],
        options: AdapterOptions,
    ) -> AsyncIterator[ChatChunk]:
        tracker = OpenRouterCostTracker(
            model_id=options.model or "openai/gpt-5",
            max_cost_usd=options.max_cost_usd or self._max_cost,
        )
        # Pre-flight: estimate input tokens (tiktoken; Pattern 6)
        tracker.record_input_estimate(prompt, history)

        messages = [{"role": m.role, "content": m.content} for m in history]
        messages.append({"role": "user", "content": prompt})

        in_flight = None
        start_t = asyncio.get_event_loop().time()
        try:
            in_flight = await self._client.chat.completions.create(
                model=options.model or "openai/gpt-5",
                messages=messages,
                stream=True,
                stream_options={"include_usage": True},   # VERIFIED: gets final usage chunk
            )

            # Tool-call state — OpenAI streams tool_call deltas by index.
            # See developers.openai.com/api/reference/...streaming-events (VERIFIED)
            tool_calls: dict[int, dict] = {}

            async for chunk in in_flight:                  # type: ChatCompletionChunk
                # Final usage chunk has empty choices but non-None usage.
                if chunk.usage is not None:
                    tracker.record_final_usage(
                        prompt_tokens=chunk.usage.prompt_tokens,
                        completion_tokens=chunk.usage.completion_tokens,
                    )
                    continue

                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                finish_reason = chunk.choices[0].finish_reason

                if delta.content:
                    tracker.record_output_delta(delta.content)
                    yield TextDelta(text=delta.content)

                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        slot = tool_calls.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                        if tc_delta.id:
                            slot["id"] = tc_delta.id
                        if tc_delta.function and tc_delta.function.name:
                            slot["name"] = tc_delta.function.name
                        if tc_delta.function and tc_delta.function.arguments:
                            slot["arguments"] += tc_delta.function.arguments

                if finish_reason == "tool_calls":
                    for slot in tool_calls.values():
                        import json
                        try:
                            args = json.loads(slot["arguments"]) if slot["arguments"] else {}
                        except json.JSONDecodeError:
                            args = {"_raw": slot["arguments"]}
                        yield ToolCall(
                            tool_call_id=slot["id"] or _gen_tool_call_id(),
                            tool_name=slot["name"],
                            arguments=args,
                        )

                if tracker.over_cap():
                    yield StreamError(
                        code="cost_cap_exceeded",
                        message=f"Cost cap ${tracker.max_cost_usd:.4f} exceeded "
                                f"(used ${tracker.total():.4f}).",
                        retriable=False,
                    )
                    break

            latency_ms = int((asyncio.get_event_loop().time() - start_t) * 1000)
            yield Done(
                tokens_in=tracker.tokens_in(),
                tokens_out=tracker.tokens_out(),
                cost_usd=tracker.total(),
                latency_ms=latency_ms,
                routing_signals=options.routing_signals,
            )

        except asyncio.CancelledError:
            # See Pattern 7 — emit terminal pair, re-raise.
            yield StreamError(code="cancelled", message="Stream cancelled by caller.", retriable=True)
            yield Done(
                tokens_in=tracker.tokens_in(), tokens_out=tracker.tokens_out(),
                cost_usd=tracker.total(),
                latency_ms=int((asyncio.get_event_loop().time() - start_t) * 1000),
                routing_signals=options.routing_signals,
            )
            raise
        except AuthenticationError as exc:
            yield StreamError(code="auth_failed", message=str(exc), retriable=False)
            yield Done(routing_signals=options.routing_signals)
        except APITimeoutError as exc:
            yield StreamError(code="timeout", message=str(exc), retriable=True)
            yield Done(routing_signals=options.routing_signals)
        except APIStatusError as exc:
            code = "rate_limited" if exc.status_code == 429 else "provider_unavailable"
            yield StreamError(code=code, message=str(exc), retriable=(code == "rate_limited"))
            yield Done(routing_signals=options.routing_signals)
        except Exception as exc:
            logger.exception("OpenRouter adapter internal error")
            yield StreamError(code="internal_error", message=f"{type(exc).__name__}: {exc}", retriable=False)
            yield Done(routing_signals=options.routing_signals)
        finally:
            if in_flight is not None:
                try:
                    await in_flight.close()   # aborts the underlying httpx connection
                except Exception:
                    pass


def _gen_tool_call_id() -> str:
    """CONTEXT specifics: tc_<6-char-base32>."""
    alphabet = "abcdefghijklmnopqrstuvwxyz234567"
    return "tc_" + "".join(secrets.choice(alphabet) for _ in range(6))
```

**Notes:**

- `default_headers=` on the AsyncOpenAI constructor (VERIFIED — supported since openai 1.x) is the right place for `HTTP-Referer` / `X-Title` because they apply to every call, not just one. (OpenRouter docs show `extra_headers=` on the `.create()` call, which also works but requires every-call repetition.)
- `stream_options={"include_usage": True}` is the **only way** to get a final usage chunk from OpenAI-compatible streaming. [VERIFIED: developers.openai.com/api/reference/...streaming-events]
- Tool-call streaming is delta-indexed; the adapter accumulates `arguments` strings across chunks and emits a single `ToolCall` chunk when `finish_reason == "tool_calls"` arrives.
- `in_flight.close()` aborts the httpx connection in the `finally`; this is what propagates cancellation to the OpenRouter wire. [CITED: helpers.md "Stream Closure"]

### Pattern 4: Claude Code Adapter (claude-agent-sdk 0.1.81 + ClaudeSDKClient)

**What:** Use `ClaudeSDKClient.connect() + .query() + .receive_response() + .interrupt() + .disconnect()`. **Do NOT use the standalone `query()` function** — it has no `interrupt()` method and BACKEND-07 requires propagating cancellation to the underlying subprocess within 2 s.

**Example:**

```python
# Source: github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/client.py (VERIFIED)
# apps/api/backends/claude_code/adapter.py
from __future__ import annotations
import asyncio
import logging
import tempfile
import shutil
from typing import AsyncIterator

from claude_agent_sdk import (
    ClaudeSDKClient, ClaudeAgentOptions,
    AssistantMessage, UserMessage, SystemMessage, ResultMessage,
    TextBlock, ToolUseBlock, ToolResultBlock, ThinkingBlock,
    ClaudeSDKError, ProcessError,
)

from apps.api.backends.chunks import (
    ChatChunk, TextDelta, ToolCall, ToolResult, FileDiff, StreamError, Done,
)
from apps.api.backends.cost import DEFAULT_PER_TURN_COST_USD
from apps.api.backends.claude_code.cost import ClaudeCodeCostTracker
from apps.api.backends.claude_code.step_counter import StepCounter, DEFAULT_STEP_CAP
from apps.api.backends.protocol import Message, AdapterOptions

logger = logging.getLogger(__name__)

ALLOWED_TOOLS = ["Read", "Edit", "Write", "Bash", "Glob", "Grep"]   # CONTEXT discretion


class ClaudeCodeAdapter:
    def __init__(
        self,
        api_key: str | None = None,    # claude_agent_sdk picks ANTHROPIC_API_KEY from env
        *,
        max_cost_usd: float = DEFAULT_PER_TURN_COST_USD,
        max_steps: int = DEFAULT_STEP_CAP,    # 25 per D-15
        client_factory=None,
    ):
        # claude-agent-sdk inherits ANTHROPIC_API_KEY from os.environ. Don't pass api_key.
        # The constructor just snapshots configuration.
        self._max_cost = max_cost_usd
        self._max_steps = max_steps
        self._client_factory = client_factory or ClaudeSDKClient

    async def stream(
        self,
        prompt: str,
        history: list[Message],
        options: AdapterOptions,
    ) -> AsyncIterator[ChatChunk]:
        # Per-turn workspace (BACKEND-08).
        if options.cwd:
            workspace = options.cwd
            cleanup_workspace = False
        else:
            workspace = tempfile.mkdtemp(prefix="pomu-cc-")
            cleanup_workspace = True

        tracker = ClaudeCodeCostTracker(
            model_id=options.model or "claude-agent-sdk",
            max_cost_usd=options.max_cost_usd or self._max_cost,
        )
        steps = StepCounter(cap=options.max_steps or self._max_steps)
        start_t = asyncio.get_event_loop().time()

        agent_opts = ClaudeAgentOptions(
            allowed_tools=ALLOWED_TOOLS,
            cwd=workspace,
            # No permission_mode override: default user-controlled; UI/Phase 5 may set "acceptEdits".
        )

        client: ClaudeSDKClient | None = None
        try:
            client = self._client_factory(options=agent_opts)
            await client.connect()
            # query() on the client is the streaming-mode entry; interrupt() only works in this mode.
            await client.query(prompt=prompt)

            async for msg in client.receive_response():
                # ResultMessage marks the end of one turn. Use it as the loop terminator.
                if isinstance(msg, ResultMessage):
                    # ResultMessage carries usage and total_cost_usd; let the tracker finalize.
                    tracker.record_result(msg)
                    break

                if isinstance(msg, AssistantMessage):
                    steps.increment()             # each assistant message = one step
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            tracker.record_output_text(block.text)
                            yield TextDelta(text=block.text)
                        elif isinstance(block, ToolUseBlock):
                            yield ToolCall(
                                tool_call_id=block.id,
                                tool_name=block.name,
                                arguments=block.input,
                            )
                        elif isinstance(block, ThinkingBlock):
                            # v1: surface as TextDelta with a marker, or drop. Drop for cleanliness.
                            continue
                    # usage is on the message itself in claude-agent-sdk v0.1.x; tracker handles it.
                    if hasattr(msg, "usage") and msg.usage:
                        tracker.record_assistant_usage(msg.usage)

                elif isinstance(msg, UserMessage):
                    # In claude-agent-sdk, UserMessages within a turn carry tool_result blocks
                    # (the SDK injects them after executing a ToolUse on Claude's behalf).
                    for block in msg.content if hasattr(msg, "content") else []:
                        if isinstance(block, ToolResultBlock):
                            if block.tool_name in ("Edit", "Write"):
                                # FileDiff specialization. The block.content for Edit/Write
                                # carries before/after; mapping is in errors.py helper.
                                yield FileDiff(
                                    tool_call_id=block.tool_use_id,
                                    path=block.input.get("path", "") if hasattr(block, "input") else "",
                                    diff=str(block.content),
                                    operation="edit" if block.tool_name == "Edit" else "create",
                                )
                            else:
                                yield ToolResult(
                                    tool_call_id=block.tool_use_id,
                                    content=block.content if isinstance(block.content, (str, dict)) else str(block.content),
                                    is_error=getattr(block, "is_error", False),
                                )

                # SystemMessage: log only.

                if steps.exceeded():
                    yield StreamError(
                        code="step_cap_exceeded",
                        message=f"Step cap of {steps.cap} reached.",
                        retriable=False,
                    )
                    await client.interrupt()
                    break

                if tracker.over_cap():
                    yield StreamError(
                        code="cost_cap_exceeded",
                        message=f"Cost cap ${tracker.max_cost_usd:.4f} exceeded.",
                        retriable=False,
                    )
                    await client.interrupt()
                    break

            latency_ms = int((asyncio.get_event_loop().time() - start_t) * 1000)
            yield Done(
                tokens_in=tracker.tokens_in(),
                tokens_out=tracker.tokens_out(),
                cost_usd=tracker.total(),
                latency_ms=latency_ms,
                routing_signals=options.routing_signals,
            )

        except asyncio.CancelledError:
            if client is not None:
                try:
                    await client.interrupt()
                except Exception:
                    pass
            yield StreamError(code="cancelled", message="Stream cancelled by caller.", retriable=True)
            yield Done(
                tokens_in=tracker.tokens_in(), tokens_out=tracker.tokens_out(),
                cost_usd=tracker.total(),
                latency_ms=int((asyncio.get_event_loop().time() - start_t) * 1000),
                routing_signals=options.routing_signals,
            )
            raise
        except ProcessError as exc:
            yield StreamError(code="provider_unavailable", message=str(exc), retriable=False)
            yield Done(routing_signals=options.routing_signals)
        except ClaudeSDKError as exc:
            yield StreamError(code="internal_error", message=str(exc), retriable=False)
            yield Done(routing_signals=options.routing_signals)
        except Exception as exc:
            logger.exception("Claude Code adapter internal error")
            yield StreamError(code="internal_error", message=f"{type(exc).__name__}: {exc}", retriable=False)
            yield Done(routing_signals=options.routing_signals)
        finally:
            if client is not None:
                try:
                    await client.disconnect()
                except Exception:
                    pass
            if cleanup_workspace:
                try:
                    shutil.rmtree(workspace, ignore_errors=True)
                except Exception:
                    pass
```

**Notes:**

- `apps/api/backends/claude_code/__init__.py` MUST set `os.environ.setdefault("CLAUDE_ENABLE_STREAM_WATCHDOG", "1")` at import time (BACKEND-09, CONTEXT discretion). The Claude CLI subprocess inherits the var.
- `claude-agent-sdk` does NOT accept an `api_key` parameter — it reads `ANTHROPIC_API_KEY` from `os.environ`. The adapter's auth-precheck happens at construction time by reading the env var and raising if absent.
- The "one step = one assistant message" mapping (D-15) is the correct interpretation: each `AssistantMessage` represents one model round-trip in the SDK's transport.
- `ResultMessage.total_cost_usd` is the authoritative cost; `tracker.record_result` overrides the running estimate at `Done` time.
- **Critical:** A `break` in `async for msg in client.receive_response()` can leave the underlying async generator in an unfinished state. Letting `ResultMessage` terminate the loop naturally is safer; for cap-exceeded we call `interrupt()` first so the SDK closes the loop cleanly.

### Pattern 5: Computer-Use Adapter (anthropic 0.102 + manual agent loop + Playwright)

**What:** Build an explicit `while True` agent loop. Each iteration: take screenshot → send messages (including the screenshot as `tool_result`) → consume the streamed `MessageStream` → execute any tool_use blocks against Playwright → feed `tool_result` back into the next iteration. Stop when `stop_reason == "end_turn"` or step cap is hit.

**Example:**

```python
# Source: platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool (VERIFIED)
#         + helpers.md AsyncMessageStream (VERIFIED)
# apps/api/backends/computer_use/adapter.py
from __future__ import annotations
import asyncio
import base64
import logging
import os
from typing import AsyncIterator

from anthropic import AsyncAnthropic, APIStatusError, AuthenticationError, APITimeoutError

from apps.api.backends.chunks import (
    ChatChunk, TextDelta, ToolCall, ToolResult, Screenshot, StreamError, Done,
)
from apps.api.backends.computer_use.cost import ComputerUseCostTracker
from apps.api.backends.computer_use.screen import PlaywrightScreen
from apps.api.backends.computer_use.step_counter import StepCounter, DEFAULT_STEP_CAP
from apps.api.backends.cost import DEFAULT_PER_TURN_COST_USD
from apps.api.backends.protocol import Message, AdapterOptions

logger = logging.getLogger(__name__)

BETA_HEADER = "computer-use-2025-11-24"
DEFAULT_MODEL = "claude-opus-4-7"
DEFAULT_VIEWPORT = (1280, 800)   # CONTEXT specifics


class ComputerUseAdapter:
    def __init__(
        self,
        api_key: str,
        *,
        viewport: tuple[int, int] = DEFAULT_VIEWPORT,
        max_cost_usd: float = DEFAULT_PER_TURN_COST_USD,
        max_steps: int = DEFAULT_STEP_CAP,    # 15 per D-15
        client_factory=None,
        screen_factory=None,
    ):
        # SECURE-05: hard-fail before anything else.
        if os.environ.get("COMPUTER_USE_OPT_IN") != "1":
            raise RuntimeError(
                "computer-use is OFF — set COMPUTER_USE_OPT_IN=1 to enable"
            )
        if not api_key:
            raise AuthenticationError("ANTHROPIC_API_KEY not set", response=None, body=None)
        self._client = (client_factory or AsyncAnthropic)(api_key=api_key)
        self._viewport = viewport
        self._max_cost = max_cost_usd
        self._max_steps = max_steps
        self._screen_factory = screen_factory or PlaywrightScreen

    async def stream(
        self,
        prompt: str,
        history: list[Message],
        options: AdapterOptions,
    ) -> AsyncIterator[ChatChunk]:
        tracker = ComputerUseCostTracker(
            model_id=options.model or DEFAULT_MODEL,
            max_cost_usd=options.max_cost_usd or self._max_cost,
        )
        steps = StepCounter(cap=options.max_steps or self._max_steps)
        start_t = asyncio.get_event_loop().time()

        width, height = self._viewport
        tools = [
            {
                "type": "computer_20251124",
                "name": "computer",
                "display_width_px": width,
                "display_height_px": height,
                "display_number": 1,
            },
        ]

        messages: list[dict] = (
            [{"role": m.role, "content": m.content} for m in history]
            + [{"role": "user", "content": prompt}]
        )

        screen: PlaywrightScreen | None = None
        try:
            screen = self._screen_factory(viewport=self._viewport)
            await screen.start()

            while True:
                if steps.exceeded():
                    yield StreamError(
                        code="step_cap_exceeded",
                        message=f"Step cap of {steps.cap} reached.",
                        retriable=False,
                    )
                    break
                if tracker.over_cap():
                    yield StreamError(
                        code="cost_cap_exceeded",
                        message=f"Cost cap ${tracker.max_cost_usd:.4f} exceeded.",
                        retriable=False,
                    )
                    break

                steps.increment()
                tool_uses_this_step: list[dict] = []

                # Anthropic SDK: async with client.beta.messages.stream(...) as stream:
                async with self._client.beta.messages.stream(
                    model=options.model or DEFAULT_MODEL,
                    max_tokens=4096,
                    tools=tools,
                    messages=messages,
                    betas=[BETA_HEADER],
                ) as stream:
                    async for event in stream:
                        # Raw event types per platform.claude.com/.../streaming (VERIFIED):
                        #   message_start, content_block_start, content_block_delta,
                        #   content_block_stop, message_delta, message_stop
                        if event.type == "content_block_delta":
                            if event.delta.type == "text_delta":
                                tracker.record_output_text(event.delta.text)
                                yield TextDelta(text=event.delta.text)
                            # input_json_delta accumulates tool_use input; SDK exposes
                            # the assembled block on content_block_stop.

                        elif event.type == "content_block_stop":
                            block = event.content_block
                            if block.type == "tool_use":
                                tool_uses_this_step.append({
                                    "id": block.id,
                                    "name": block.name,
                                    "input": block.input,
                                })
                                yield ToolCall(
                                    tool_call_id=block.id,
                                    tool_name=block.name,
                                    arguments=block.input,
                                )

                    final_msg = await stream.get_final_message()
                    if final_msg.usage:
                        tracker.record_iteration_usage(
                            input_tokens=final_msg.usage.input_tokens,
                            output_tokens=final_msg.usage.output_tokens,
                            cache_read=getattr(final_msg.usage, "cache_read_input_tokens", 0) or 0,
                            cache_write=getattr(final_msg.usage, "cache_creation_input_tokens", 0) or 0,
                        )

                # Append assistant message to history
                messages.append({"role": "assistant", "content": final_msg.content})

                # Terminal stop_reason — agent says it's done.
                if final_msg.stop_reason != "tool_use" or not tool_uses_this_step:
                    break

                # Execute tools, build tool_result content for the next iteration.
                tool_results: list[dict] = []
                for tu in tool_uses_this_step:
                    action = tu["input"].get("action")
                    result_content, is_error = await self._execute_action(screen, action, tu["input"])

                    # ToolResult chunk (action narration).
                    yield ToolResult(
                        tool_call_id=tu["id"],
                        content=result_content if isinstance(result_content, (str, dict)) else str(result_content),
                        is_error=is_error,
                    )

                    # Always take a post-action screenshot and emit it.
                    png_bytes = await screen.screenshot()
                    image_b64 = base64.b64encode(png_bytes).decode("ascii")
                    yield Screenshot(
                        step=steps.value(),
                        image_b64=image_b64,
                        image_format="png",
                    )

                    # Construct the tool_result block to feed back to Anthropic. The screenshot
                    # is passed as an image content block inside the tool_result content list.
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu["id"],
                        "content": [
                            {"type": "image", "source": {
                                "type": "base64", "media_type": "image/png", "data": image_b64,
                            }},
                        ],
                        "is_error": is_error,
                    })

                messages.append({"role": "user", "content": tool_results})

            latency_ms = int((asyncio.get_event_loop().time() - start_t) * 1000)
            yield Done(
                tokens_in=tracker.tokens_in(),
                tokens_out=tracker.tokens_out(),
                cost_usd=tracker.total(),
                latency_ms=latency_ms,
                routing_signals=options.routing_signals,
            )

        except asyncio.CancelledError:
            yield StreamError(code="cancelled", message="Stream cancelled by caller.", retriable=True)
            yield Done(
                tokens_in=tracker.tokens_in(), tokens_out=tracker.tokens_out(),
                cost_usd=tracker.total(),
                latency_ms=int((asyncio.get_event_loop().time() - start_t) * 1000),
                routing_signals=options.routing_signals,
            )
            raise
        except AuthenticationError as exc:
            yield StreamError(code="auth_failed", message=str(exc), retriable=False)
            yield Done(routing_signals=options.routing_signals)
        except APITimeoutError as exc:
            yield StreamError(code="timeout", message=str(exc), retriable=True)
            yield Done(routing_signals=options.routing_signals)
        except APIStatusError as exc:
            code = "rate_limited" if exc.status_code == 429 else "provider_unavailable"
            yield StreamError(code=code, message=str(exc), retriable=(code == "rate_limited"))
            yield Done(routing_signals=options.routing_signals)
        except Exception as exc:
            logger.exception("Computer-use adapter internal error")
            yield StreamError(code="internal_error", message=f"{type(exc).__name__}: {exc}", retriable=False)
            yield Done(routing_signals=options.routing_signals)
        finally:
            if screen is not None:
                try:
                    await screen.aclose()
                except Exception:
                    pass

    async def _execute_action(self, screen, action: str, params: dict) -> tuple[str, bool]:
        """Map a computer_20251124 action to a Playwright call. Returns (narration, is_error)."""
        try:
            if action == "screenshot":
                return ("Captured screenshot.", False)
            elif action == "left_click":
                x, y = params["coordinate"]
                await screen.left_click(x, y, modifier=params.get("text"))
                return (f"Clicked at ({x}, {y}).", False)
            elif action == "type":
                await screen.type_text(params["text"])
                return (f"Typed: {params['text'][:40]!r}.", False)
            elif action == "key":
                await screen.press_key(params["text"])
                return (f"Pressed: {params['text']}.", False)
            elif action == "scroll":
                x, y = params["coordinate"]
                direction = params["scroll_direction"]
                amount = params["scroll_amount"]
                await screen.scroll(x, y, direction, amount)
                return (f"Scrolled {direction} by {amount} at ({x}, {y}).", False)
            elif action == "navigate":
                await screen.goto(params["url"])
                return (f"Navigated to {params['url']}.", False)
            elif action == "wait":
                await asyncio.sleep(params.get("duration", 1.0))
                return ("Waited.", False)
            else:
                return (f"Unsupported action: {action}", True)
        except Exception as exc:
            return (f"Error executing {action}: {exc}", True)
```

```python
# apps/api/backends/computer_use/screen.py — Playwright wrapper
# Source: playwright.dev/python/docs/api/class-page (VERIFIED via search)
from __future__ import annotations
import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Browser, Page, Playwright


class PlaywrightScreen:
    def __init__(self, *, viewport: tuple[int, int] = (1280, 800), headless: bool = True):
        self._viewport = viewport
        self._headless = headless
        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None

    async def start(self) -> None:
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self._headless)
        context = await self._browser.new_context(
            viewport={"width": self._viewport[0], "height": self._viewport[1]}
        )
        self._page = await context.new_page()

    async def screenshot(self) -> bytes:
        return await self._page.screenshot(type="png", full_page=False)

    async def left_click(self, x: int, y: int, *, modifier: str | None = None) -> None:
        modifiers = [modifier.capitalize()] if modifier else []
        await self._page.mouse.click(x, y, modifiers=modifiers)

    async def type_text(self, text: str) -> None:
        await self._page.keyboard.type(text)

    async def press_key(self, key: str) -> None:
        # Anthropic uses "ctrl+s" notation; Playwright wants "Control+s".
        normalized = key.replace("ctrl", "Control").replace("super", "Meta")
        await self._page.keyboard.press(normalized)

    async def scroll(self, x: int, y: int, direction: str, amount: int) -> None:
        await self._page.mouse.move(x, y)
        delta = amount * 100      # rough pixels-per-tick
        if direction == "down":
            await self._page.mouse.wheel(0, delta)
        elif direction == "up":
            await self._page.mouse.wheel(0, -delta)
        elif direction == "right":
            await self._page.mouse.wheel(delta, 0)
        elif direction == "left":
            await self._page.mouse.wheel(-delta, 0)

    async def goto(self, url: str) -> None:
        await self._page.goto(url)

    async def aclose(self) -> None:
        try:
            if self._browser is not None:
                await self._browser.close()
        finally:
            if self._pw is not None:
                await self._pw.stop()
```

**Notes:**

- `playwright install chromium` must run in `make setup` (Phase 6) to fetch the Chromium binary. The Playwright Python wheel contains the bindings, NOT the browser binary. The binary lives under `~/.cache/ms-playwright/`.
- `client.beta.messages.stream(...)` returns an AsyncMessageStream (a context-manager-enabled async iterator). The context manager closes the response on exit, which is the correct cleanup for cancellation.
- Per Anthropic docs (VERIFIED), Claude Opus 4.7's `computer_20251124` is 1:1 pixel-to-coord at up to 2576px on the long edge — at 1280×800 there's no coordinate scaling needed. We do NOT need the `get_scale_factor` math from the Anthropic doc.
- The `screenshot` action emitted by Claude does not require a separate Playwright call from us — we ALWAYS take a screenshot after every action and emit it as both a `Screenshot` chunk and a `tool_result` image. This is the canonical pattern from the Anthropic quickstart sample loop.

### Pattern 6: CostTracker (per-adapter pricing + cap enforcement)

**What:** Base `CostTracker` with `record_input(n)`, `record_output_delta(text)`, `total() -> float`, `over_cap() -> bool`. Per-adapter subclasses know how to extract tokens from their provider's events.

**Example:**

```python
# Source: openrouter.ai/api/v1/models live response (VERIFIED via curl)
# apps/api/backends/cost.py
from __future__ import annotations
from typing import Final

DEFAULT_PER_TURN_COST_USD: Final[float] = 0.50    # CONTEXT specifics


class CostTracker:
    """Base class — adapters subclass to extract tokens from provider events."""

    def __init__(self, *, model_id: str, max_cost_usd: float, pricing):
        self.model_id = model_id
        self.max_cost_usd = max_cost_usd
        self._pricing = pricing            # PricingTable
        self._tokens_in = 0
        self._tokens_out = 0
        self._final_cost_override: float | None = None    # provider-reported authoritative cost

    def record_input(self, n: int) -> None:
        self._tokens_in += n

    def record_output(self, n: int) -> None:
        self._tokens_out += n

    def tokens_in(self) -> int:
        return self._tokens_in

    def tokens_out(self) -> int:
        return self._tokens_out

    def total(self) -> float:
        if self._final_cost_override is not None:
            return self._final_cost_override
        rates = self._pricing.get(self.model_id)
        return (
            self._tokens_in * rates["input_per_mtok"] / 1_000_000
            + self._tokens_out * rates["output_per_mtok"] / 1_000_000
        )

    def over_cap(self) -> bool:
        return self.total() > self.max_cost_usd
```

```python
# apps/api/backends/pricing.py
# Source: live curl of openrouter.ai/api/v1/models — pricing.prompt/completion are
# decimal strings in USD per token (e.g., "0.00003" = $30/Mtok input for Opus 4.7).
from __future__ import annotations
import json
import os
import time
from pathlib import Path
import logging

import httpx

logger = logging.getLogger(__name__)

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
CACHE_TTL_SECONDS = 24 * 60 * 60


class PricingTable:
    def __init__(self, table: dict[str, dict[str, float]]):
        self._table = table

    @classmethod
    def from_static(cls, path: str | Path) -> "PricingTable":
        with open(path, "r", encoding="utf-8") as fh:
            return cls(json.load(fh))

    def get(self, model_id: str) -> dict[str, float]:
        return self._table.get(model_id) or self._table["_default"]

    async def refresh_from_openrouter(self, cache_path: str | Path) -> None:
        cache = Path(cache_path)
        if cache.exists() and (time.time() - cache.stat().st_mtime) < CACHE_TTL_SECONDS:
            try:
                with open(cache, "r", encoding="utf-8") as fh:
                    snapshot = json.load(fh)
                self._merge_openrouter_snapshot(snapshot)
                return
            except Exception:
                pass
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(OPENROUTER_MODELS_URL)
                resp.raise_for_status()
                snapshot = resp.json()
            cache.parent.mkdir(parents=True, exist_ok=True)
            with open(cache, "w", encoding="utf-8") as fh:
                json.dump(snapshot, fh)
            self._merge_openrouter_snapshot(snapshot)
        except httpx.HTTPError as exc:
            logger.warning("OpenRouter pricing refresh failed: %s — using static table.", exc)

    def _merge_openrouter_snapshot(self, snapshot: dict) -> None:
        for model in snapshot.get("data", []):
            pricing = model.get("pricing") or {}
            if "prompt" not in pricing or "completion" not in pricing:
                continue
            try:
                # OpenRouter returns USD per TOKEN as decimal strings; convert to per Mtok.
                input_per_mtok = float(pricing["prompt"]) * 1_000_000
                output_per_mtok = float(pricing["completion"]) * 1_000_000
            except (ValueError, TypeError):
                continue
            self._table[model["id"]] = {
                "input_per_mtok": input_per_mtok,
                "output_per_mtok": output_per_mtok,
            }
```

**Initial `config/pricing.json` entries** (derived from `config/model_mapping.json` + Anthropic docs; cross-check against live OpenRouter on first refresh):

```json
{
  "openai/gpt-5": {"input_per_mtok": 2.50, "output_per_mtok": 10.00},
  "openai/gpt-5-chat": {"input_per_mtok": 2.50, "output_per_mtok": 10.00},
  "qwen/qwen3-235b-a22b-2507": {"input_per_mtok": 0.30, "output_per_mtok": 0.90},
  "qwen/qwen3-235b-a22b-thinking-2507": {"input_per_mtok": 0.30, "output_per_mtok": 0.90},
  "deepseek/deepseek-v3.1-terminus": {"input_per_mtok": 0.27, "output_per_mtok": 1.10},
  "deepseek/deepseek-chat-v3-0324": {"input_per_mtok": 0.27, "output_per_mtok": 1.10},
  "moonshotai/kimi-k2-0905": {"input_per_mtok": 0.60, "output_per_mtok": 2.50},
  "google/gemini-2.5-flash": {"input_per_mtok": 0.075, "output_per_mtok": 0.30},
  "openrouter/auto": {"input_per_mtok": 2.00, "output_per_mtok": 8.00},
  "anthropic/claude-opus-4-7": {"input_per_mtok": 5.00, "output_per_mtok": 25.00},
  "anthropic/claude-sonnet-4-6": {"input_per_mtok": 3.00, "output_per_mtok": 15.00},
  "claude-agent-sdk": {"input_per_mtok": 5.00, "output_per_mtok": 25.00},
  "computer-use-2025-11-24": {"input_per_mtok": 5.00, "output_per_mtok": 25.00},
  "_default": {"input_per_mtok": 5.00, "output_per_mtok": 20.00}
}
```

[ASSUMED] Specific dollar amounts for individual models are based on training-data prices; the OpenRouter refresh on first run will replace any stale values. `_default` is the conservative upper bound from CONTEXT specifics.

**Pre-flight token estimator (CONTEXT discretion):**

```python
# apps/api/backends/openrouter/cost.py
import tiktoken

class OpenRouterCostTracker(CostTracker):
    """OpenAI-family — use tiktoken for pre-flight estimation."""

    _ENCODING = tiktoken.encoding_for_model("gpt-4")   # close enough for non-OpenAI slugs

    def record_input_estimate(self, prompt: str, history: list) -> None:
        joined = prompt + "\n".join(m.content for m in history)
        self.record_input(len(self._ENCODING.encode(joined)))

    def record_output_delta(self, text: str) -> None:
        self.record_output(len(self._ENCODING.encode(text)))

    def record_final_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Override the running estimate with provider truth at stream end."""
        self._tokens_in = prompt_tokens
        self._tokens_out = completion_tokens
```

For Anthropic / claude-agent-sdk, use `len(text) // 4` as a rough char-count estimator pre-flight; the real `usage` block from each iteration / the `ResultMessage` overrides at `Done` time. [CITED: anthropic docs note that tiktoken under/overestimates Claude]

### Pattern 7: Cancellation Propagation (asyncio.CancelledError → terminal pair + re-raise)

**What:** When the caller `aclose()`s the iterator (or the consuming task is cancelled), the adapter's generator receives `CancelledError` at the next `await`. The `try/except CancelledError` block emits `StreamError(code="cancelled", retriable=True) + Done` (the D-04 invariant), then re-raises to honor Python 3.11+ cancellation semantics.

**Example:**

```python
# Source: docs.python.org/3/library/asyncio-task.html + PEP 789 (VERIFIED)
async def stream(self, ...) -> AsyncIterator[ChatChunk]:
    in_flight = None
    try:
        in_flight = await self._client...
        async for chunk in in_flight:
            yield ...
        yield Done(...)

    except asyncio.CancelledError:
        # Emit terminal pair BEFORE re-raising. The `yield` here is critical:
        # the consumer is in aclose() and is *expecting* the generator to
        # produce one more chunk before raising StopAsyncIteration.
        yield StreamError(code="cancelled", message="...", retriable=True)
        yield Done(...)
        raise   # Required in 3.11+: do NOT swallow CancelledError.

    except OtherException as exc:
        yield StreamError(...)
        yield Done(...)
        # Don't re-raise — the consumer expects the iterator to terminate normally
        # via StopAsyncIteration after Done.

    finally:
        if in_flight is not None:
            await in_flight.close()
        if screen is not None:
            await screen.aclose()
        if claude_client is not None:
            await claude_client.disconnect()
```

**Key invariants:**

- `Done` is ALWAYS the last chunk (D-04). The contract test asserts `chunks[-1].type == "done"`.
- On `CancelledError`, MUST re-raise. Python 3.11 made unsanctioned `except CancelledError: pass` an asyncio.TaskGroup-violating pattern; PEP 789 (not yet accepted but signaled by 3.11 hardening) confirms.
- Cleanup runs in `finally`. The 2-second budget (CONTEXT specifics) is honored because:
  1. `aclose()` triggers immediate `CancelledError` at the consumer's next `await`.
  2. The adapter's generator runs `except CancelledError` → 2 yields (fast) → `raise`.
  3. `finally` runs `in_flight.close()` (httpx `aclose` is async but generally < 100 ms) or `client.interrupt()` (claude-agent-sdk's CLI subprocess takes ~ 200-500 ms to wind down per CHANGELOG) or `screen.aclose()` (Playwright Chromium shutdown ~ 1-1.5 s in headless mode).
- The contract test (D-19, item 4) uses `pytest.mark.timeout(2)` to enforce this empirically. `pytest-timeout` is the standard plugin. [CITED: pypi pytest-timeout]

### Pattern 8: Per-Thread Ephemeral Workspace (BACKEND-08)

**Example:**

```python
# Source: tempfile stdlib (HIGH confidence)
import tempfile
import shutil

# In ClaudeCodeAdapter.stream():
if options.cwd is None:
    workspace = tempfile.mkdtemp(prefix="pomu-cc-")    # CONTEXT specifics
    cleanup = True
else:
    workspace = options.cwd                            # opt-in user repo (BACKEND-08)
    cleanup = False

agent_opts = ClaudeAgentOptions(cwd=workspace, allowed_tools=ALLOWED_TOOLS)
# ...
finally:
    if cleanup:
        shutil.rmtree(workspace, ignore_errors=True)
```

Phase 3 will swap `tempfile.mkdtemp` for `~/.prompt-optimizer/workspaces/<thread_id>/` once thread IDs exist.

### Pattern 9: `CLAUDE_ENABLE_STREAM_WATCHDOG=1` (BACKEND-09)

**Example:**

```python
# apps/api/backends/claude_code/__init__.py
import os
os.environ.setdefault("CLAUDE_ENABLE_STREAM_WATCHDOG", "1")

from apps.api.backends.claude_code.adapter import ClaudeCodeAdapter

__all__ = ["ClaudeCodeAdapter"]
```

`setdefault` is the right call: don't overwrite if the operator has already set it. The Claude CLI subprocess inherits the env var because `claude-agent-sdk` uses `subprocess.Popen(..., env=os.environ)` (verified via the SDK's `_internal/transport/subprocess_cli.py` per github read).

### Pattern 10: Logging Redaction Filter (SECURE-01)

**What:** Subclass `logging.Filter`, mutate `record.msg` and `record.args` BEFORE format. Install at process import.

**Example:**

```python
# Source: dev.to "Mask Sensitive Data using Python Built-in Logging Module" (CITED) +
#         relaxdiego.com "Hiding Sensitive Data from Logs with Python" (CITED)
# apps/api/backends/logging_filter.py
from __future__ import annotations
import logging
import re

# CONTEXT specifics: the same regex as the pre-commit hook (D-09) so the test
# coverage in one place validates the other.
SECRET_PATTERNS = [
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}"), "***REDACTED-ANTHROPIC***"),
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "***REDACTED-OPENAI***"),
    (re.compile(r"Bearer\s+[A-Za-z0-9_.\-]{20,}"), "Bearer ***REDACTED***"),
]


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Get fully-formatted message (handles %s interpolation).
        try:
            msg = record.getMessage()
        except Exception:
            return True   # don't drop records due to formatter bugs

        for pattern, replacement in SECRET_PATTERNS:
            msg = pattern.sub(replacement, msg)

        # Reset record.msg and clear record.args so the formatter doesn't
        # re-interpolate the original values (this is the key subtlety —
        # mutating record.msg alone isn't enough when args is non-empty).
        record.msg = msg
        record.args = ()
        return True


def install_redaction_filter() -> None:
    """Install the redaction filter on the root logger. Called at apps/api/__init__.py import."""
    root = logging.getLogger()
    # Idempotent: only attach once.
    for f in root.filters:
        if isinstance(f, RedactionFilter):
            return
    root.addFilter(RedactionFilter())
    # Also attach to all existing handlers in case a handler was added without filters.
    for h in root.handlers:
        h.addFilter(RedactionFilter())
```

**Regression test (SC #3):**

```python
# apps/api/backends/tests/test_logging_filter.py
import logging
import pytest

from apps.api.backends.logging_filter import install_redaction_filter

def test_redaction_replaces_anthropic_keys(caplog):
    install_redaction_filter()
    logger = logging.getLogger("test")
    with caplog.at_level(logging.INFO):
        logger.info("auth header: Bearer sk-ant-api03-XYZ1234567890ABCDEFGHIJKL")
    assert "sk-ant-" not in caplog.text
    assert "***REDACTED-ANTHROPIC***" in caplog.text

def test_redaction_handles_args_interpolation(caplog):
    install_redaction_filter()
    logger = logging.getLogger("test")
    with caplog.at_level(logging.INFO):
        logger.info("key=%s url=%s", "sk-proj-abcdefghijklmnopqrstuvwxyz", "https://api.example.com")
    assert "sk-proj-" not in caplog.text
    assert "***REDACTED-OPENAI***" in caplog.text
```

**Notes:**

- `record.getMessage()` returns the formatted message; we replace `record.msg` with it AND clear `record.args = ()` so subsequent formatters don't re-interpolate. [CITED: runebook.dev / dev.to]
- The filter is attached to the root logger so it cascades to all loggers (named loggers propagate to root by default). For belt-and-suspenders, also attach to each handler. [CITED: relaxdiego.com]
- `caplog` is pytest's stdlib-logging capture fixture — it captures records BEFORE handlers see them, so the test inspects post-filter content correctly.

### Pattern 11: pre-commit Local Hooks (SECURE-02)

**Example:**

```yaml
# .pre-commit-config.yaml
# Source: pre-commit.com docs (VERIFIED), adamj.eu "Various ways to run hooks" (CITED)
repos:
  - repo: local
    hooks:
      - id: no-secrets
        name: Block secrets in staged content
        entry: scripts/no-secrets.sh
        language: script
        pass_filenames: false      # script uses `git diff --cached` directly
        stages: [pre-commit]
      - id: no-deprecated-claude-code-sdk
        name: Block deprecated claude-code-sdk
        entry: scripts/no-deprecated-sdk.sh
        language: script
        pass_filenames: false
        stages: [pre-commit]
```

```bash
# scripts/no-secrets.sh
#!/usr/bin/env bash
set -euo pipefail

# Match lines being ADDED in staged content (lines starting with +, excluding +++ headers).
# Regex matches the three locked-decision patterns from D-09.
if git diff --cached --diff-filter=AM | \
   grep -E '^\+[^+]' | \
   grep -E '(sk-ant-[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9]{20,}|Bearer [A-Za-z0-9_.-]{20,})' > /dev/null; then
    echo "ERROR: Staged content contains what looks like an API key or bearer token."
    echo "If this is a false positive, remove the literal and use an env-var reference."
    exit 1
fi
exit 0
```

```bash
# scripts/no-deprecated-sdk.sh
#!/usr/bin/env bash
set -euo pipefail

# Check staged content (covers .py source).
if git diff --cached --diff-filter=AM | \
   grep -E '^\+[^+].*\b(import claude_code_sdk|from claude_code_sdk|"claude-code-sdk")' > /dev/null; then
    echo "ERROR: Use 'claude_agent_sdk' (NOT the deprecated 'claude-code-sdk')."
    echo "See OSS-06 in .planning/REQUIREMENTS.md."
    exit 1
fi

# Also check uv.lock — D-09 says: catch contributors who add the dep accidentally.
if [ -f uv.lock ] && grep -q '"claude-code-sdk"' uv.lock; then
    echo "ERROR: 'claude-code-sdk' found in uv.lock. Remove the dep and re-lock."
    exit 1
fi
exit 0
```

**CI integration (D-20):** Add `- run: pre-commit run --all-files` to `.github/workflows/ci.yml` so the same hooks run in CI.

### Pattern 12: KeyStore with Optional `keyring` (SECURE-04)

**Example:**

```python
# apps/api/backends/keystore.py
# Source: keyring package docs (CITED)
from __future__ import annotations
import os
from typing import Final

SERVICE_NAME: Final[str] = "prompt-optimizer"

try:
    import keyring as _keyring
    _HAS_KEYRING = True
except ImportError:
    _HAS_KEYRING = False


_ENV_MAP = {
    "openrouter": "OPENROUTER_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


class KeyStore:
    """In-memory primary store; optional disk persistence via OS keyring."""

    def __init__(self, *, use_keyring: bool = False):
        if use_keyring and not _HAS_KEYRING:
            raise RuntimeError(
                "use_keyring=True but the 'keyring' extra is not installed. "
                "Run: uv sync --extra keyring"
            )
        self._memory: dict[str, str] = {}
        self._use_keyring = use_keyring

    def get(self, provider: str) -> str | None:
        if provider in self._memory:
            return self._memory[provider]
        if self._use_keyring and _HAS_KEYRING:
            stored = _keyring.get_password(SERVICE_NAME, provider)
            if stored:
                self._memory[provider] = stored
                return stored
        env_var = _ENV_MAP.get(provider)
        if env_var:
            val = os.environ.get(env_var)
            if val:
                self._memory[provider] = val
                return val
        return None

    def set(self, provider: str, key: str) -> None:
        self._memory[provider] = key
        if self._use_keyring and _HAS_KEYRING:
            _keyring.set_password(SERVICE_NAME, provider, key)
```

### Pattern 13: COMPUTER_USE_OPT_IN Constructor Check (SECURE-05)

Shown inline in Pattern 5. The check is at `__init__` so it fires BEFORE any provider client is constructed (no key-leak surface — even a `keyring.get_password` call is avoided).

### Pattern 14: OSS-06 Enforcement Triad

**Three independent guards:**

1. **CI smoke** (D-20):
   ```yaml
   - run: python -c "from claude_agent_sdk import ClaudeAgentOptions"
   - name: ensure deprecated SDK absent
     run: |
       ! python -c "import claude_code_sdk" 2>/dev/null
       ! grep -q '"claude-code-sdk"' uv.lock
   ```

2. **Pre-commit hook** (`scripts/no-deprecated-sdk.sh`, Pattern 11 above).

3. **Pyproject pin**:
   ```toml
   [project.dependencies]
   claude-agent-sdk = ">=0.1.80,<0.2"
   # Notably NOT: claude-code-sdk
   ```

The `uv.lock` grep is the canary — the lock file uses the format:
```
[[package]]
name = "claude-code-sdk"
version = "..."
```
So `grep -q '"claude-code-sdk"' uv.lock` matches either the TOML quoted-string form or any reference. [VERIFIED: uv.lock format from Phase 1's existing file]

### Anti-Patterns to Avoid

- **Buffering TextDelta:** D-05 forbids it. One provider event → one TextDelta. UI does the smoothing.
- **Silent `except CancelledError: pass`:** Python 3.11+ flags this as an asyncio integrity issue. Always re-raise after the terminal pair.
- **Calling `print()` of any value that could contain a key:** SECURE-01's redaction filter only intercepts `logging.LogRecord`. Adapter must use `logging.getLogger(__name__)`, never `print()`.
- **`sys.path.append` in adapter modules:** CLAUDE.md and CONTEXT both forbid. Use `from apps.api.backends.X import Y`.
- **Importing `fastapi`, `httpx`, `requests`, `openai`, `anthropic` from `src/routing/`:** Phase 1 D-18 import-graph guard test catches this. Phase 2 imports are ONE-WAY: `apps/api → src/routing`, never the reverse.
- **Standalone `claude_agent_sdk.query()` for the adapter:** No `interrupt()` method → BACKEND-07 cancellation fails the 2-second budget. Use `ClaudeSDKClient`.
- **Sync `httpx.Client.send`, `requests.get`, etc.:** Block the asyncio loop. Use `httpx.AsyncClient`, `openai.AsyncOpenAI`, `anthropic.AsyncAnthropic`, `playwright.async_api`.
- **Default `headless=False` for Chromium:** Phase 2 CLI must be headless. A debug toggle is fine; the default is `True`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| ChatChunk runtime validation | Custom `__init__` validators | `pydantic.BaseModel` | Phase 3 SSE serialization, free type-narrowing, free JSON round-trip, locked by D-01. |
| Discriminated union dispatch | `match ch.type: case "text_delta": …` everywhere | `TypeAdapter(ChatChunk).validate_python(d)` | Returns the correct typed subclass; mypy/pyright narrow on `isinstance`. |
| OpenAI / OpenRouter streaming SSE parser | Custom `httpx.AsyncClient` + SSE parser | `openai.AsyncOpenAI` | Tool-call delta accumulation (`delta.tool_calls`), `stream_options.include_usage` final chunk, error-class hierarchy — all handled. BACKEND-03 locks this. |
| Anthropic streaming SSE parser | Custom SSE parser | `anthropic.AsyncAnthropic` + `client.beta.messages.stream()` | `input_json_delta` accumulation across `content_block_delta` events is non-trivial. SDK uses `jiter` for partial-JSON parsing. |
| Claude Code subprocess management | `subprocess.Popen` + stdout pipe | `claude_agent_sdk.ClaudeSDKClient` | Session state, hook events, stream watchdog, permission flow — all in SDK. BACKEND-04 locks. |
| Browser automation | `pyppeteer`, `selenium`, manual Playwright bindings | `playwright.async_api` | Async-native, headless Chromium ships in the wheel, locked by D-13. |
| OS keyring access | Per-platform shell-outs to `security find-generic-password` etc. | `keyring 25.x` | Cross-platform, lazy backend selection, ZDR-friendly. |
| Pre-commit hook plumbing | Raw `.git/hooks/pre-commit` shell scripts | `pre-commit` framework | Shared install, CI integration, multi-language support. D-09. |
| `.env` loading | Custom parser | `python-dotenv` | Quote handling, bash-`export`-line compat, `override` semantics. D-11. |
| Log redaction | Custom handler subclass | `logging.Filter` subclass (Pattern 10) | Filters run BEFORE handlers; mutate `record.msg` + clear `record.args`. |
| Token counting (OpenAI-family) | Custom BPE | `tiktoken` | Maintained by OpenAI; encodings are exact. |
| Token counting (Anthropic) | tiktoken (under/overestimates) | `client.beta.messages.count_tokens` for accuracy; char-count / 4 for offline pre-flight | Anthropic's tokenizer is not public; count_tokens is free but adds a network hop. For pre-flight estimate only, char-count is good enough. |
| 24-hour cache invalidation | Custom expiry logic | mtime-based file freshness check (Pattern 6) | One stat() call; no extra dep. |
| BackendAdapter base class | Inheritance hierarchy | `typing.Protocol` | Structural typing; tests can use any object that satisfies the shape (FakeOpenAIClient, etc.). |
| Tool-call ID generation | UUID4 | `tc_<6-char-base32>` per CONTEXT specifics | Stable, readable in logs, fits Phase 4 UI rendering. |
| Step counting state machine | Custom dataclass | Small `StepCounter` helper class with `increment()` / `exceeded()` / `value()` / `cap` | Two-line abstraction; per-backend defaults via subclass constant. |

**Key insight:** Phase 2 is heavy on SDK integration but light on novel algorithms. The hard problems are *all* in the SDKs (streaming, cancellation, tool-call accumulation, subprocess management, browser automation, secure key handling). Our job is composition + the ChatChunk normalization layer.

## Runtime State Inventory

> Phase 2 is greenfield code with no pre-existing runtime state to migrate. Workspace state (`tempfile.mkdtemp`) is per-turn and cleaned up in the adapter's `finally` block. There is no string-rename or refactor at play.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — Phase 2 adds no persistent stores. (Phase 3 adds SQLite + `routing_decisions.jsonl`.) | None |
| Live service config | None — no Datadog/n8n/Cloudflare integrations exist. | None |
| OS-registered state | None — no Task Scheduler / launchd / systemd / pm2 registrations. | None |
| Secrets / env vars | NEW: `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `COMPUTER_USE_OPT_IN`. None are renamed from prior phases. `.env.example` (Phase 6 OSS-03) will enumerate them. | Document in `apps/api/__init__.py` docstring; defer `.env.example` to Phase 6. |
| Build artifacts | NEW: `~/.cache/ms-playwright/chromium-*/` once `playwright install chromium` runs. Out of git, gitignored implicitly (it's in `~`). | Document in `make setup` (Phase 6). |

**Nothing to migrate.** All Phase 2 state is either net-new or per-turn ephemeral.

## Common Pitfalls

### Pitfall 1: Forgetting `stream_options={"include_usage": True}`

**What goes wrong:** OpenAI-compatible streaming defaults to omitting the `usage` block. The final chunk has `choices: []` and `usage: None`, so the cost tracker never gets authoritative numbers — the `Done` chunk reports the (lossy) tiktoken estimate.

**Why it happens:** This option is opt-in by design (older SDK versions didn't support it).

**How to avoid:** Always pass `stream_options={"include_usage": True}` in `client.chat.completions.create()`. The OpenRouter adapter MUST do this. [VERIFIED: developers.openai.com/api/reference]

**Warning signs:** `Done.tokens_in` and `Done.tokens_out` don't match the OpenRouter dashboard within a few percent.

### Pitfall 2: Using standalone `claude_agent_sdk.query()` for the Claude Code adapter

**What goes wrong:** The standalone function returns an `AsyncIterator[Message]` with no `interrupt()` method. BACKEND-07's cancellation contract (2 s) cannot be honored — the subprocess keeps running. The contract test's `aclose()` invariant times out.

**Why it happens:** Tutorials and quickstart docs lead with the standalone `query()` because it's simpler for "hello world" demos.

**How to avoid:** Use `ClaudeSDKClient` (Pattern 4). The interrupt path is `await client.interrupt()` in both the cap-exceeded branch and the `except CancelledError` branch. [VERIFIED: github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/client.py]

**Warning signs:** D-19 contract test #4 (cancellation within 2 s) times out for the claude_code adapter only.

### Pitfall 3: `default_headers` vs `extra_headers` on the OpenAI client

**What goes wrong:** Setting `HTTP-Referer` via `extra_headers=` on `chat.completions.create()` works for the first call only — every subsequent `.create()` call must repeat them. Easy to forget on retries / streaming reconnects.

**Why it happens:** OpenRouter's quickstart uses `extra_headers=`. OpenAI SDK supports both.

**How to avoid:** Set both attribution headers via `default_headers=` on the `AsyncOpenAI(...)` constructor (Pattern 3). They become part of every request made by that client instance.

**Warning signs:** App doesn't show up on the OpenRouter leaderboard / per-app analytics. [VERIFIED: openrouter.ai/docs/app-attribution — "this header is required for app attribution"]

### Pitfall 4: Anthropic `input_json_delta` accumulation

**What goes wrong:** Tool-use blocks stream their `input` argument as JSON fragments across multiple `content_block_delta` events with `delta.type == "input_json_delta"`. If you naively `JSON.parse(delta.partial_json)` after each chunk you get a parse error on partial JSON.

**Why it happens:** It's a streaming optimization — the model can start sending function args before the full JSON is generated.

**How to avoid:** **Use the SDK's `content_block_stop` event instead.** The SDK accumulates the full block and exposes it on `event.content_block` at `content_block_stop` time, fully-parsed via `jiter`. Our Pattern 5 code does exactly this. [VERIFIED: github.com/anthropics/anthropic-sdk-python/blob/main/helpers.md]

**Warning signs:** Random JSON parse errors mid-stream when computer-use tries to click.

### Pitfall 5: Async generator cleanup ordering

**What goes wrong:** Cleanup code in an async generator's `finally` runs LATER than you think — Python defers async generator finalization. If the consumer's `aclose()` raises before all generators clean up, you can leak the Playwright browser process or the Claude CLI subprocess.

**Why it happens:** PEP 525 / Python's async generator finalization model.

**How to avoid:**
- Always `await` cleanup inside `finally` (do not just register `loop.run_until_complete(...)` callbacks).
- For the orchestrator (Phase 3), call `asyncio.run(main())` so the loop runs `loop.shutdown_asyncgens()` automatically at exit.
- Wrap Playwright in an explicit `async with` block where possible.
- Never `break` out of `async for client.receive_response()` without first calling `client.interrupt()`.

**Warning signs:** Zombie Chromium processes after the test suite; CI hangs after a failing test.

### Pitfall 6: Pricing rates double-conversion

**What goes wrong:** OpenRouter returns pricing as USD-per-TOKEN as decimal strings: `"0.00003"`. Our `pricing.json` uses USD-per-Mtok floats: `30.0`. Forgetting to multiply by 1,000,000 makes `over_cap()` always false (cost stays in the picodollar range).

**Why it happens:** Two different scales co-exist in the codebase.

**How to avoid:** `PricingTable._merge_openrouter_snapshot` does the multiplication once (Pattern 6). Static JSON entries are always per-Mtok. Tests should include a regression for a known-large model. [VERIFIED: live curl of openrouter.ai/api/v1/models shows decimal strings]

**Warning signs:** Cost cap never trips; `Done.cost_usd` is effectively 0 for a long generation.

### Pitfall 7: `pytest -m 'not live'` doesn't skip Playwright Chromium download

**What goes wrong:** The fake injection works at the SDK call boundary, but if a test instantiates `ComputerUseAdapter()` without injecting `screen_factory`, `screen.start()` calls `async_playwright().start()` → tries to spawn Chromium → fails on a CI runner that hasn't run `playwright install`.

**Why it happens:** Constructor doesn't lazy-init the browser, but `screen_factory` defaults to the real one.

**How to avoid:** D-19's contract test MUST inject `screen_factory=FakePlaywrightScreen` for every parametric run. The per-adapter `conftest.py` provides the fake fixture. Live smoke tests opt-in via `@pytest.mark.live` AND run `playwright install chromium` in their own workflow step. [VERIFIED: D-20 says CI runs `pytest -m 'not live'`, so live tests don't run on push.]

**Warning signs:** CI fails with "browserType.launch: Executable doesn't exist" on a contributor's fresh PR.

### Pitfall 8: `record.args = ()` is mandatory in the redaction filter

**What goes wrong:** Mutating `record.msg` to a redacted string but leaving `record.args` populated means the formatter re-interpolates `%s` with the original (unredacted) args. The redaction "works" for some handlers but not all.

**Why it happens:** Subtle behavior of Python's logging: `record.getMessage()` runs `record.msg % record.args` on each call.

**How to avoid:** After replacement, set `record.args = ()`. The Pattern 10 code does this. [CITED: runebook.dev "Python logging filter common traps"]

**Warning signs:** The redaction-filter regression test passes when called via `logger.info("auth: %s", key)` but fails when the message uses an f-string. Or vice versa.

## Code Examples

> All major code patterns are in §"Architecture Patterns" above (Patterns 1–14). This section is a quick-reference for the most-cited operations.

### Common Operation 1: Construct ChatChunk + serialize for SSE

```python
# Source: pydantic v2 docs (VERIFIED)
from apps.api.backends.chunks import TextDelta, Done, chat_chunk_adapter

td = TextDelta(text="hello")
print(td.model_dump_json())       # '{"type":"text_delta","text":"hello"}'

# Phase 3 SSE: yield each chunk as one SSE event.
async for chunk in adapter.stream(...):
    yield f"data: {chunk.model_dump_json()}\n\n"

# Ingestion from JSON (tests / replay):
restored = chat_chunk_adapter.validate_json('{"type":"text_delta","text":"hi"}')
assert isinstance(restored, TextDelta)
```

### Common Operation 2: Run an adapter from a CLI (`__main__.py`)

```python
# Source: src/routing/__main__.py pattern (VERIFIED) + asyncio.run docs
# apps/api/backends/openrouter/__main__.py
from __future__ import annotations
import argparse
import asyncio
import os
import sys

from apps.api.backends.openrouter.adapter import OpenRouterAdapter
from apps.api.backends.protocol import AdapterOptions


async def _run(prompt: str, model: str, max_cost_usd: float, max_steps: int) -> int:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: set OPENROUTER_API_KEY in env or .env", file=sys.stderr)
        return 1
    adapter = OpenRouterAdapter(api_key=api_key, max_cost_usd=max_cost_usd)
    options = AdapterOptions(model=model, max_cost_usd=max_cost_usd, max_steps=max_steps)
    async for chunk in adapter.stream(prompt=prompt, history=[], options=options):
        print(chunk.model_dump_json(), flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m apps.api.backends.openrouter")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--model", default="openai/gpt-5")
    parser.add_argument("--max-cost-usd", type=float, default=0.50)
    parser.add_argument("--max-steps", type=int, default=25)
    args = parser.parse_args(argv)
    return asyncio.run(_run(args.prompt, args.model, args.max_cost_usd, args.max_steps))


if __name__ == "__main__":
    sys.exit(main())
```

Identical shape for `claude_code/__main__.py` and `computer_use/__main__.py`, parametrized on the adapter class.

### Common Operation 3: Inject a fake into an adapter for unit tests

```python
# apps/api/backends/openrouter/tests/fakes.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class FakeDelta:
    content: str | None = None
    tool_calls: list | None = None


@dataclass
class FakeChoice:
    delta: FakeDelta
    finish_reason: str | None = None


@dataclass
class FakeUsage:
    prompt_tokens: int = 10
    completion_tokens: int = 5


@dataclass
class FakeChunk:
    choices: list[FakeChoice]
    usage: FakeUsage | None = None


class FakeAsyncStream:
    def __init__(self, chunks: list[FakeChunk]):
        self._chunks = chunks

    def __aiter__(self):
        async def gen():
            for c in self._chunks:
                yield c
        return gen()

    async def close(self):
        pass


class FakeChatCompletions:
    def __init__(self, chunks: list[FakeChunk]):
        self._chunks = chunks

    async def create(self, **_kw) -> FakeAsyncStream:
        return FakeAsyncStream(self._chunks)


class FakeOpenAIClient:
    def __init__(self, chunks: list[FakeChunk]):
        self.chat = type("Chat", (), {"completions": FakeChatCompletions(chunks)})()


# Usage in test:
# def factory(api_key): return FakeOpenAIClient([FakeChunk(...)])
# adapter = OpenRouterAdapter(api_key="x", client_factory=factory)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `claude-code-sdk` (deprecated package) | `claude-agent-sdk` (v0.1.x current) | Rename happened in v0.1.0 of claude-agent-sdk (~2025) | OSS-06 requires the new package; deprecated package no longer maintained per pypi. [VERIFIED: pypi claude-code-sdk page lists it as deprecated; CHANGELOG.md] |
| `computer-use-2025-01-24` beta | `computer-use-2025-11-24` beta with `computer_20251124` tool | November 2025 | Required for Claude Opus 4.7 / Sonnet 4.6 / Opus 4.5. Adds `zoom` action behind `enable_zoom: true`. Coordinate scaling no longer needed at viewports ≤ 2576px on long edge. [VERIFIED: platform.claude.com/docs] |
| OpenAI streaming without `usage` | `stream_options={"include_usage": True}` | Added late 2024 | Eliminates need for post-hoc tiktoken estimation; trustworthy cost tracking. [VERIFIED: developers.openai.com] |
| `cv='prefit'` for sklearn calibration | `FrozenEstimator + CalibratedClassifierCV(cv=None)` | sklearn 1.7+ removed `cv='prefit'` | Phase 1 already migrated. Not Phase 2's concern but mentioned in CONTEXT for completeness. |
| `requests` / `httpx` (sync) inside async code | `httpx.AsyncClient` + provider SDKs' async clients | asyncio became mainstream | Adapter MUST NOT block the loop. CONTEXT anti-pattern. |
| Python 3.10's lenient `CancelledError` | Python 3.11+ requires re-raise + uncancel semantics | 3.11 (2022) hardened | Pattern 7 reflects this. Re-raising after the terminal pair is mandatory. [CITED: PEP 789, github.com/python/cpython/issues/102780] |

**Deprecated/outdated:**

- `claude-code-sdk` (pypi): use `claude-agent-sdk`. Imports differ: `from claude_agent_sdk import ClaudeAgentOptions`. [VERIFIED: pypi pages]
- `computer_20250124` tool spec: still supported for older models, but Phase 2 targets `computer_20251124` exclusively per BACKEND-05.
- `cv='prefit'` for sklearn calibration: completely removed in sklearn 1.8 (Phase 1 used `FrozenEstimator`).
- Custom SSE parsers: superseded by `openai.AsyncOpenAI` and `anthropic.AsyncAnthropic` async iterators.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `config/pricing.json` static entries' per-Mtok dollar amounts (gpt-5 = $2.50/$10.00, etc.) | Pattern 6 | Cost caps may be too generous/strict for ~24h until the OpenRouter refresh runs; defensible because `_default` is conservative and refresh is automatic. |
| A2 | OpenRouter `/api/v1/models` is publicly accessible without auth | Pattern 6 | If wrong, the refresh path falls back to static silently. Live curl on 2026-05-15 returned HTTP/2 200 with no auth header — confirmed accessible. |
| A3 | The standalone `claude_agent_sdk.query()` function has no `interrupt()` method | Pattern 4 | This drove the major design decision to use `ClaudeSDKClient`. WebFetch of client.py confirms `interrupt()` is on the client class. The CHANGELOG and Github source for the standalone `query` function (not fetched directly) presumably matches. If `query()` ALSO has interrupt in 0.1.81, our design still works (we just don't use it). Low risk. |
| A4 | Playwright Chromium spawns within 2 s on a typical CI runner | Pattern 7 | Pitfall 5 notes ~1-1.5 s shutdown; startup similar. The 2 s cancellation budget assumes the stream has already started (browser already up). For cold-start tests, increase timeout. |
| A5 | `record.args = ()` in the logging filter is necessary | Pattern 10 | Cited in two community sources; verified by the test pattern. If wrong, redaction "works" but flakily. Low risk — the regression test catches it. |
| A6 | `tiktoken` gpt-4 encoder is "close enough" for non-OpenAI OpenRouter slugs (Qwen, DeepSeek, etc.) | Pattern 6 | Pre-flight only; the real `usage` block overrides. ~10-20% off is acceptable for the pre-flight gate. |
| A7 | `pytest-asyncio` `asyncio_mode = "auto"` is the right default for `pyproject.toml` | Pattern 0 (deps) | If we want explicit `@pytest.mark.asyncio` decorators, use `"strict"`. `"auto"` is more ergonomic for an adapter-heavy test suite. Low risk; either works. |
| A8 | `pre-commit` framework `pass_filenames: false` + `git diff --cached` in the script is correct | Pattern 11 | pre-commit's default is to pass filenames as positional args; turning that off lets the script run `git diff --cached` directly. Verified pattern from adamj.eu / gist examples. |
| A9 | `claude-agent-sdk` 0.1.81 picks up `ANTHROPIC_API_KEY` from `os.environ` automatically | Pattern 4 | Inferred from the constructor pattern (no `api_key=` parameter shown in docs). If the SDK adds an explicit kwarg later, the adapter's constructor signature should still work because `os.environ` will be the fallback. Low risk. |

**If this table is empty:** Not applicable — 9 assumed claims documented; all are explicitly flagged in the relevant section.

## Open Questions (RESOLVED)

1. **RESOLVED: OpenRouter `/api/v1/models` — confirmed unauthenticated**
   - What we know: Live `curl https://openrouter.ai/api/v1/models` returns HTTP/2 200 with no auth header (verified at research time). Response includes pricing for every model. Cloudflare-fronted with `Access-Control-Allow-Origin: *`.
   - What's unclear: Rate limits. The official doc mentions "cached at the edge" but no published rate limit. A 24h cache (D-17) is conservative.
   - Recommendation: Use the 24h cache; rate limits are unlikely to be an issue for a single startup hit per CLI invocation.
   - **Resolution:** Accept 24h cache; revisit if 429s appear (defer to operations).

2. **RESOLVED: Anthropic SDK `usage.cache_*_tokens` fields exact names**
   - What we know: Streaming `message_delta` events include a final `usage` block. `input_tokens`, `output_tokens` are standard.
   - What's unclear: The exact field names for cache read/write tokens (`cache_read_input_tokens` vs `cache_read`, etc.). Pattern 5's `getattr(..., "cache_read_input_tokens", 0)` is defensive.
   - Recommendation: Confirm via `anthropic --help` or live `usage` block inspection during live smoke. Defensive `getattr` is safe regardless.
   - **Resolution:** Defensive `getattr` is the locked approach (RESEARCH Pattern 5 line numbers).

3. **RESOLVED: Phase 2 `Done.cost_usd` precedence with mixed authority sources**
   - What we know: OpenRouter's pre-flight `tracker.record_input_estimate` is an estimate; the final `stream_options.include_usage` chunk has truth. Claude Code's `ResultMessage.total_cost_usd` is authoritative per the SDK.
   - What's unclear: For computer-use's per-iteration `usage` block, is the SUM of all iterations' `input_tokens` correct (i.e., does Anthropic charge for cached prefix on every iteration), or do we need to subtract the cached portion?
   - Recommendation: Live smoke against `claude-opus-4-7` with computer-use, compare `Done.cost_usd` to the Anthropic dashboard usage page for the same date. Adjust if off by more than ±10%.
   - **Resolution:** Defer authority precedence to live smoke; defensive code stands until then.

4. **RESOLVED: claude-agent-sdk message content shape for ToolResult blocks**
   - What we know: `AssistantMessage.content` is a list of blocks. `UserMessage.content` may also be a list with `ToolResultBlock` items the SDK injects after running a tool.
   - What's unclear: Whether `UserMessage` instances in `receive_response()` carry just text or also `ToolResultBlock` items, and whether the SDK exposes the tool's stdout (Bash) directly on the block or buried inside `content`.
   - Recommendation: Test with a `pytest -m live` Claude Code Bash invocation. Pattern 4's code defensively iterates over `getattr(msg, "content", [])` and pattern-matches by isinstance.
   - **Resolution:** `getattr(msg, "content", [])` + isinstance dispatch is the locked approach (Pattern 4); live smoke confirms shape.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.10+ | Everything | ✓ | 3.11 in CI, ≥3.10 in pyproject.toml | — |
| `uv` | CI sync, dev workflow | ✓ | astral-sh/setup-uv@v3 in CI | — |
| `git-lfs` | Existing CSV pulls | ✓ | Phase 1 CI has `lfs: true` | — |
| Chromium binary | Computer-use Playwright (live tests only) | ✗ on fresh clone | — | (a) `playwright install chromium` in `make setup` (Phase 6); (b) Phase 2 CI runs `pytest -m 'not live'` only, so no Chromium needed for green CI. |
| OpenRouter API access | BACKEND-03 live tests | ✗ in CI (no key in secrets) | — | `@pytest.mark.live` opt-in; weekly cron with repo secret. |
| Anthropic API access | BACKEND-04 + BACKEND-05 live tests | ✗ in CI | — | Same — opt-in live tests. |
| Claude CLI binary | claude-agent-sdk subprocess | ✓ via `claude-agent-sdk` (bundles the CLI per CHANGELOG 0.1.x) | bundled | — |
| `dotenv` parsing | `.env` load at `apps/api/__init__.py` | ✓ via `python-dotenv 1.x` | — | If `.env` absent, `load_dotenv()` is a no-op (defensive). |
| OS keyring (macOS Keychain / Windows DPAPI / Linux Secret Service) | `keyring` optional extra | ✓ on macOS dev machine; ✓ on Windows; partial on Linux (depends on session) | system | If keyring extra not installed, fall back to in-memory + env vars. |

**Missing dependencies with no fallback:** None. All Phase 2 unit-test paths (the default CI gate) are 100% offline. Live smoke is opt-in and BYOK-gated.

**Missing dependencies with fallback:**
- Chromium: live tests only; `make setup` installs in Phase 6.
- API keys: live tests opt-in; default test suite uses hand-stubbed fakes.

## Validation Architecture

> `workflow.nyquist_validation` is `true` in `.planning/config.json`. Validation architecture is included.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.x with pytest-asyncio + pytest-timeout |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (extends Phase 1; adds `asyncio_mode = "auto"`, `markers = ["live: …"]`) |
| Quick run command | `uv run pytest -x -q -m 'not live' apps/api/backends` (per-task commit) |
| Full suite command | `uv run pytest -m 'not live'` (per wave merge) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BACKEND-01 | ChatChunk Pydantic union round-trips JSON | unit | `pytest apps/api/backends/tests/test_chunks.py -x` | ❌ Wave 0 |
| BACKEND-02 | BackendAdapter Protocol structural compliance | unit | `pytest apps/api/backends/tests/test_adapter_contract.py::test_protocol_compliance -x` | ❌ Wave 0 |
| BACKEND-03 | OpenRouter adapter emits ChatChunk sequence; HTTP-Referer + X-Title headers set | unit (fake injection); live smoke (opt-in) | `pytest apps/api/backends/openrouter/tests/test_adapter.py -x`; `pytest -m live apps/api/backends/openrouter/tests/test_live.py -x` | ❌ Wave 0 |
| BACKEND-04 | Claude Code adapter uses claude_agent_sdk; ClaudeSDKClient.interrupt() called on cancel; FileDiff emitted for Edit/Write | unit (fake injection); live smoke | `pytest apps/api/backends/claude_code/tests/test_adapter.py -x`; `pytest -m live apps/api/backends/claude_code/tests/test_live.py -x` | ❌ Wave 0 |
| BACKEND-05 | Computer-use beta header set; computer_20251124 tool registered; agent loop runs; Screenshot emitted base64 | unit (fake screen + anthropic); live (opt-in, BYOK) | `pytest apps/api/backends/computer_use/tests/test_adapter.py -x`; `pytest -m live apps/api/backends/computer_use/tests/test_live.py -x` | ❌ Wave 0 |
| BACKEND-06 | Per-turn USD cap aborts mid-stream; per-iteration step cap aborts | unit (D-19 shared) | `pytest apps/api/backends/tests/test_adapter_contract.py::test_cost_cap_aborts apps/api/backends/tests/test_adapter_contract.py::test_step_cap_aborts -x` | ❌ Wave 0 |
| BACKEND-07 | aclose() propagates within 2 s; terminal pair lands | unit (D-19 shared with `@pytest.mark.timeout(2)`) | `pytest apps/api/backends/tests/test_adapter_contract.py::test_cancellation_within_2s -x` | ❌ Wave 0 |
| BACKEND-08 | Per-thread tmpdir workspace; cleanup on exit | unit | `pytest apps/api/backends/claude_code/tests/test_workspace.py -x` | ❌ Wave 0 |
| BACKEND-09 | `CLAUDE_ENABLE_STREAM_WATCHDOG=1` set in environment | unit (import smoke) | `pytest apps/api/backends/claude_code/tests/test_watchdog_env.py -x` | ❌ Wave 0 |
| SECURE-01 | Redaction filter rewrites `sk-`, `sk-ant-`, `Bearer …` to `***REDACTED***` before handlers see record | unit | `pytest apps/api/backends/tests/test_logging_filter.py -x` | ❌ Wave 0 |
| SECURE-02 | Pre-commit hook blocks staged secret content | manual + CI (pre-commit run --all-files) | `pre-commit run --all-files` | ❌ Wave 0 |
| SECURE-04 | KeyStore.get falls back to env; keyring lazy-import | unit | `pytest apps/api/backends/tests/test_keystore.py -x` | ❌ Wave 0 |
| SECURE-05 | ComputerUseAdapter raises at __init__ without COMPUTER_USE_OPT_IN=1 | unit | `pytest apps/api/backends/computer_use/tests/test_optin.py -x` | ❌ Wave 0 |
| OSS-06 | claude_agent_sdk import smoke; claude-code-sdk not in uv.lock | CI gate (Phase 1 also runs) | `python -c "from claude_agent_sdk import ClaudeAgentOptions"; ! grep -q '"claude-code-sdk"' uv.lock` | ❌ Wave 0 (extend ci.yml) |

### D-19 Shared Parametric Contract Suite

**Six invariants, every adapter:**

```python
# apps/api/backends/tests/test_adapter_contract.py
import asyncio
import pytest

from apps.api.backends.chunks import Done, StreamError, TextDelta
from apps.api.backends.openrouter.adapter import OpenRouterAdapter
from apps.api.backends.claude_code.adapter import ClaudeCodeAdapter
from apps.api.backends.computer_use.adapter import ComputerUseAdapter
from apps.api.backends.protocol import AdapterOptions

ADAPTER_PARAMS = [
    pytest.param("openrouter", id="openrouter"),
    pytest.param("claude_code", id="claude_code"),
    pytest.param("computer_use", id="computer_use"),
]


@pytest.fixture
def adapter_factory(request, fake_openai, fake_claude_sdk_client, fake_anthropic, fake_screen, monkeypatch):
    """Returns a callable that builds an adapter with all fakes injected."""
    def factory(backend: str, *, max_cost_usd: float = 0.50, max_steps: int = 25) -> object:
        if backend == "openrouter":
            return OpenRouterAdapter(
                api_key="fake", max_cost_usd=max_cost_usd,
                client_factory=lambda _key: fake_openai,
            )
        if backend == "claude_code":
            return ClaudeCodeAdapter(
                max_cost_usd=max_cost_usd, max_steps=max_steps,
                client_factory=lambda options: fake_claude_sdk_client,
            )
        if backend == "computer_use":
            monkeypatch.setenv("COMPUTER_USE_OPT_IN", "1")
            return ComputerUseAdapter(
                api_key="fake", max_cost_usd=max_cost_usd, max_steps=max_steps,
                client_factory=lambda api_key: fake_anthropic,
                screen_factory=lambda **kw: fake_screen,
            )
        raise ValueError(backend)
    return factory


@pytest.mark.parametrize("backend", ADAPTER_PARAMS)
@pytest.mark.asyncio
async def test_happy_path_terminates_with_done(adapter_factory, backend):
    adapter = adapter_factory(backend)
    chunks = []
    async for ch in adapter.stream(prompt="hello", history=[], options=AdapterOptions()):
        chunks.append(ch)
    assert chunks, "no chunks emitted"
    assert any(isinstance(c, TextDelta) for c in chunks), "no TextDelta"
    assert isinstance(chunks[-1], Done), f"last chunk is {type(chunks[-1])}, expected Done"


@pytest.mark.parametrize("backend", ADAPTER_PARAMS)
@pytest.mark.asyncio
async def test_cost_cap_aborts(adapter_factory, backend):
    adapter = adapter_factory(backend, max_cost_usd=0.000001)  # force cap
    chunks = []
    async for ch in adapter.stream(prompt="x" * 1000, history=[], options=AdapterOptions()):
        chunks.append(ch)
    assert any(
        isinstance(c, StreamError) and c.code == "cost_cap_exceeded" for c in chunks
    )
    assert isinstance(chunks[-1], Done)


@pytest.mark.parametrize("backend", ADAPTER_PARAMS)
@pytest.mark.asyncio
async def test_step_cap_aborts(adapter_factory, backend):
    # OpenRouter doesn't have step caps in v1, but we still assert no crash.
    if backend == "openrouter":
        pytest.skip("step cap not applicable to OpenRouter (single round-trip)")
    adapter = adapter_factory(backend, max_steps=1)
    chunks = []
    async for ch in adapter.stream(prompt="hi", history=[], options=AdapterOptions(max_steps=1)):
        chunks.append(ch)
    assert any(
        isinstance(c, StreamError) and c.code == "step_cap_exceeded" for c in chunks
    )
    assert isinstance(chunks[-1], Done)


@pytest.mark.parametrize("backend", ADAPTER_PARAMS)
@pytest.mark.asyncio
@pytest.mark.timeout(2)
async def test_cancellation_within_2_seconds(adapter_factory, backend):
    adapter = adapter_factory(backend)
    aiter = adapter.stream(prompt="hello", history=[], options=AdapterOptions()).__aiter__()
    await aiter.__anext__()       # ensure stream started
    # Trigger cancellation:
    chunks = []
    try:
        # Use a wrapper task and cancel it; the generator's CancelledError handler
        # should emit StreamError(cancelled) + Done within 2 s.
        async def consume():
            async for ch in adapter.stream(prompt="hello", history=[], options=AdapterOptions()):
                chunks.append(ch)
        task = asyncio.create_task(consume())
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    finally:
        await aiter.aclose()
    # The cancellation path must emit at least StreamError(cancelled) + Done.
    # Note: in the alternative path (aclose without task cancellation), some chunks
    # may be lost — the contract is that whatever lands ends with Done.
    if chunks:
        assert isinstance(chunks[-1], Done)


@pytest.mark.parametrize("backend", ADAPTER_PARAMS)
@pytest.mark.asyncio
async def test_done_always_lands(adapter_factory, backend):
    adapter = adapter_factory(backend)
    chunks = []
    async for ch in adapter.stream(prompt="hi", history=[], options=AdapterOptions()):
        chunks.append(ch)
    assert chunks
    assert isinstance(chunks[-1], Done)


@pytest.mark.parametrize("backend", ADAPTER_PARAMS)
def test_missing_api_key_raises_before_stream(adapter_factory, backend, monkeypatch):
    if backend == "openrouter":
        with pytest.raises(Exception):
            OpenRouterAdapter(api_key="")
    elif backend == "claude_code":
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        # claude_agent_sdk reads env lazily; the adapter's preflight check fires here.
        with pytest.raises(Exception):
            ClaudeCodeAdapter()
    elif backend == "computer_use":
        monkeypatch.setenv("COMPUTER_USE_OPT_IN", "1")
        with pytest.raises(Exception):
            ComputerUseAdapter(api_key="")
```

### Sampling Rate

- **Per task commit:** `uv run pytest -x -q -m 'not live' <touched-paths>` (e.g., `apps/api/backends/openrouter/`).
- **Per wave merge:** `uv run pytest -m 'not live'` (full apps/api + src/routing combined).
- **Phase gate:** `uv run pytest -m 'not live'` GREEN before `/gsd-verify-work`. The Phase 1 D-18 import-graph guard (in `src/routing/tests/test_decide_smoke.py`) MUST also still pass — adding `fastapi`, `openai`, `anthropic` to `apps/api/` MUST NOT change what `import src.routing.decide` pulls into `sys.modules`.

### Wave 0 Gaps

- [ ] `apps/api/__init__.py` — `dotenv.load_dotenv()` + `install_redaction_filter()` at import
- [ ] `apps/api/backends/__init__.py`, `protocol.py`, `chunks.py`, `keystore.py`, `logging_filter.py`, `pricing.py`, `cost.py`
- [ ] `apps/api/backends/tests/conftest.py` — shared fakes (`fake_openai`, `fake_claude_sdk_client`, `fake_anthropic`, `fake_screen`)
- [ ] `apps/api/backends/tests/test_chunks.py` — Pydantic union round-trip (BACKEND-01)
- [ ] `apps/api/backends/tests/test_adapter_contract.py` — D-19 shared parametric suite (the file above)
- [ ] `apps/api/backends/tests/test_logging_filter.py` — SC #3 redaction regression (SECURE-01)
- [ ] `apps/api/backends/tests/test_keystore.py` — env fallback + keyring (SECURE-04)
- [ ] `apps/api/backends/tests/test_pricing.py` — static load + OpenRouter merge math
- [ ] `apps/api/backends/openrouter/__init__.py`, `__main__.py`, `adapter.py`, `cost.py`, `errors.py`
- [ ] `apps/api/backends/openrouter/tests/{conftest.py, fakes.py, test_adapter.py, test_live.py}`
- [ ] `apps/api/backends/claude_code/__init__.py` (sets `CLAUDE_ENABLE_STREAM_WATCHDOG`), `__main__.py`, `adapter.py`, `cost.py`, `errors.py`, `workspace.py`, `step_counter.py`
- [ ] `apps/api/backends/claude_code/tests/{conftest.py, fakes.py, test_adapter.py, test_workspace.py, test_watchdog_env.py, test_live.py}`
- [ ] `apps/api/backends/computer_use/__init__.py`, `__main__.py`, `adapter.py`, `cost.py`, `errors.py`, `screen.py`, `step_counter.py`
- [ ] `apps/api/backends/computer_use/tests/{conftest.py, fakes.py, test_adapter.py, test_optin.py, test_live.py}`
- [ ] `config/pricing.json` — initial static entries
- [ ] `.pre-commit-config.yaml`, `scripts/no-secrets.sh`, `scripts/no-deprecated-sdk.sh` (D-09)
- [ ] `.github/workflows/ci.yml` — extend with uv sync, pre-commit, OSS-06 smoke, redaction test, pytest apps/api (D-20)
- [ ] `.github/workflows/live-smoke.yml` — optional manual + weekly cron live smoke
- [ ] Framework install: add `pytest-asyncio`, `pytest-timeout`, `pre-commit` to `pyproject.toml`

## Security Domain

> `security_enforcement` is the implicit default for this project (no `false` override in config). Required.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | BYOK keys via `KeyStore` (memory + optional `keyring`). No password auth, no service-account JWT, no OAuth in Phase 2. |
| V3 Session Management | no | No multi-tenant; no session state. Phase 3 introduces SQLite-backed threads but those are not auth sessions. |
| V4 Access Control | partial | Computer-use SECURE-05 opt-in flag is the only "access control" — it gates the entire feature. Claude Code workspace `cwd` opt-in (BACKEND-08) gates filesystem-write access. |
| V5 Input Validation | yes | Pydantic v2 `ChatChunk` discriminated union performs runtime validation on every adapter return (BACKEND-01). Adapter input (prompt, history) is treated as user-controlled but not parsed further — passed through to the SDK. |
| V6 Cryptography | partial | No crypto primitives are hand-rolled. TLS is the SDK's responsibility (httpx, anthropic, openai, claude-agent-sdk all use TLS by default to their respective endpoints). |
| V7 Error Handling and Logging | yes | SECURE-01 redaction filter (Pattern 10) scrubs `sk-`, `sk-ant-`, `Bearer …` from every log record before any handler sees it. All adapter errors are mapped to typed `StreamError` chunks (D-06 vocabulary). |
| V8 Data Protection | yes | BYOK keys never written to SQLite (Phase 3), never to logs (SECURE-01), only optionally to OS keyring (SECURE-04, opt-in extra). `.env` already gitignored (Phase 1 SECURE-03). |
| V12 Files | partial | Claude Code per-thread workspace under `tempfile.mkdtemp` (BACKEND-08). Cleanup on adapter exit. Computer-use Playwright Chromium runs in headless mode; no host-filesystem write surface. |
| V14 Configuration | yes | Phase 2 introduces `config/pricing.json` (committed, no secrets), `.pre-commit-config.yaml` (committed, no secrets). `.env` stays gitignored. `apps/api/__init__.py` is the SOLE process-import-time configuration entry point. |

### Known Threat Patterns for the Phase 2 Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Hardcoded API keys committed to git | Information Disclosure | Pre-commit hook scripts/no-secrets.sh (D-09); `.env` gitignored. |
| Deprecated SDK reintroduced | Tampering / Repudiation | OSS-06 triad: CI smoke + uv.lock grep + pre-commit hook (Pattern 14). |
| Prompt injection from computer-use page content | Tampering | Anthropic ships an automatic classifier that flags suspect actions and prompts for user confirmation (per platform.claude.com computer-use docs). Phase 2 inherits this defense-in-depth. README threat-model doc lands in Phase 6 SECURE-06. |
| Computer-use exfiltration of host files | Information Disclosure | Playwright Chromium sandbox — no host-filesystem access from the browser. No native-app access. Bounded blast radius per D-13. |
| Computer-use accidental cost runaway | Denial of Service (against user wallet) | Per-turn USD cap (BACKEND-06, default $0.50) + 15-step iteration cap (D-15). Both enforced at adapter boundary, not in UI. |
| Runaway Claude Code subprocess (stream stall) | Denial of Service | `CLAUDE_ENABLE_STREAM_WATCHDOG=1` set at module import (BACKEND-09) — known SDK mitigation per CONTEXT. |
| Cancellation not propagating to upstream | Denial of Service (cost runaway after user closes tab) | `await client.interrupt()` (Claude Code) / `await in_flight.close()` (OpenRouter) / `await screen.aclose()` (computer-use) in adapter `finally` (Pattern 7). 2 s budget verified by D-19 contract test. |
| Secrets leaked via `print()` debug | Information Disclosure | CONTEXT anti-pattern: `print()` of values that could carry keys is forbidden. All adapter logging via `logging.getLogger(__name__)`. SECURE-01 redaction filter on root logger. |
| `joblib.load` arbitrary code execution | Tampering | Out of scope for Phase 2 — adapters don't load joblib. Phase 1 already documented this trust model (artifacts come from this same repo). |
| pickle / msgpack over network | Tampering | Not in Phase 2; all inter-process state is JSON via Pydantic. |
| Dependency confusion (PyPI typosquat) | Tampering | OSS-06 triad addresses `claude-code-sdk` specifically. Broader typosquat protection is Phase 6 / contributor responsibility. |
| `keyring` Linux dbus failure | Denial of Service | D-10 makes `keyring` an optional extra. `KeyStore(use_keyring=True)` raises with a clear remediation message ("run uv sync --extra keyring"). |
| `playwright` Chromium missing on fresh clone | Denial of Service | `make setup` (Phase 6) runs `playwright install chromium`. Phase 2 CI runs `pytest -m 'not live'` so Chromium absence doesn't break CI. |

## Sources

### Primary (HIGH confidence — verified against official docs and live endpoints)

- [Pydantic v2 Discriminated Unions](https://pydantic.dev/docs/validation/latest/concepts/unions/) — Pattern 1 (Annotated[Union[...], Field(discriminator='…')] syntax, TypeAdapter)
- [OpenAI Python SDK Helpers](https://github.com/openai/openai-python/blob/main/helpers.md) — Pattern 3 (AsyncOpenAI stream context manager)
- [OpenAI Chat Completions Streaming Events](https://developers.openai.com/api/reference/resources/chat/subresources/completions/streaming-events) — Pattern 3 (ChatCompletionChunk schema, stream_options.include_usage, delta.tool_calls)
- [OpenRouter App Attribution](https://openrouter.ai/docs/app-attribution) — Pattern 3 (HTTP-Referer required; X-Title optional; both via default_headers)
- [OpenRouter Quickstart](https://openrouter.ai/docs/quickstart) — Pattern 3 (base_url, extra_headers vs default_headers)
- [OpenRouter Models API](https://openrouter.ai/docs/api/api-reference/models/get-models) — Pattern 6 (pricing schema, USD per token); confirmed unauthenticated via live curl 2026-05-15
- [Anthropic Computer Use Tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool) — Pattern 5 (computer_20251124 schema, action set, beta header, agent loop)
- [Anthropic Streaming Messages](https://platform.claude.com/docs/en/build-with-claude/streaming) — Pattern 5 (raw event types: message_start, content_block_start, content_block_delta, content_block_stop, message_delta, message_stop)
- [Anthropic SDK Helpers](https://github.com/anthropics/anthropic-sdk-python/blob/main/helpers.md) — Pattern 5 (AsyncMessageStream patterns, content_block_stop with assembled block, get_final_message)
- [Claude Agent SDK Python](https://github.com/anthropics/claude-agent-sdk-python) — Pattern 4 (ClaudeSDKClient.connect/query/receive_response/interrupt/disconnect; standalone query has NO interrupt)
- [Claude Agent SDK CHANGELOG](https://github.com/anthropics/claude-agent-sdk-python/blob/main/CHANGELOG.md) — 0.1.81 released 2026-05-11; migration from claude-code-sdk
- [Claude Agent SDK PyPI](https://pypi.org/project/claude-agent-sdk/) — version 0.1.81 verified
- [Claude Code SDK PyPI (deprecated)](https://pypi.org/project/claude-code-sdk/) — confirms deprecation
- [OpenAI Python PyPI](https://pypi.org/project/openai/) — version 2.36.0 (2026-05-07) verified
- [Anthropic Python PyPI](https://pypi.org/project/anthropic/) — version 0.102.0 (2026-05-13) verified
- [Pydantic PyPI](https://pypi.org/project/pydantic/) — version 2.13.4 (2026-05-06) verified
- [Playwright Python PyPI](https://pypi.org/project/playwright/) — version 1.59.0 (2026-04-29) verified
- [Keyring PyPI](https://pypi.org/project/keyring/) — version 25.7.0 (2025-11-16) verified
- [Pre-commit PyPI](https://pypi.org/project/pre-commit/) — version 4.6.0 (2026-04-21) verified
- [Playwright Python Docs](https://playwright.dev/python/docs/library) — Pattern 5/screen.py (async_playwright lifecycle, chromium.launch, page.screenshot)
- [Python asyncio Task Cancellation](https://docs.python.org/3/library/asyncio-task.html) — Pattern 7 (CancelledError, try/finally, re-raise requirement)
- [pre-commit framework docs](https://pre-commit.com/) — Pattern 11 (local hooks, pass_filenames, language: script)
- Live curl of `https://openrouter.ai/api/v1/models` (2026-05-15 02:19 UTC) — HTTP/2 200, no auth, public CORS, decimal-string pricing

### Secondary (MEDIUM confidence — multiple credible sources, no single official one)

- [Mask Sensitive Data using Python Built-in Logging Module](https://dev.to/camillehe1992/mask-sensitive-data-using-python-built-in-logging-module-45fa) — Pattern 10 (RedactionFilter via record.msg mutation + record.args reset)
- [Hiding Sensitive Data from Logs with Python](https://relaxdiego.com/2014/07/logging-in-python.html) — Pattern 10 (root logger filter attachment)
- [Pre-commit: Various ways to run hooks](https://adamj.eu/tech/2022/10/20/pre-commit-various-ways-to-run-hooks/) — Pattern 11 (pre-commit run --all-files, local hook patterns)
- [Lint Only Files with Changes on pre-commit](https://markus.oberlehner.net/blog/lint-only-files-with-changes-on-pre-commit) — Pattern 11 (git diff --cached + pass_filenames: false)
- [PEP 789 – Preventing task-cancellation bugs](https://peps.python.org/pep-0789/) — Pattern 7 (re-raise CancelledError discipline; relevant for 3.11+ async generator cleanup)
- [Token Counting Explained: tiktoken, Anthropic, Gemini Guide](https://www.propelcode.ai/blog/token-counting-tiktoken-anthropic-gemini-guide-2025) — Pattern 6 (tiktoken vs Anthropic count_tokens tradeoffs)

### Tertiary (LOW confidence — single source, flagged for validation)

- [Claude Agent SDK Migration Guide](https://platform.claude.com/docs/en/agent-sdk/migration-guide) — referenced in WebFetch results but not directly fetched; planner may want to validate the breaking-change list before locking the adapter constructor signature.

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — every version verified against pypi or live API call; SDK exports confirmed via github source.
- Architecture: HIGH — three adapter patterns derive directly from official docs + live testing of the OpenRouter endpoint. The standalone-`query()`-has-no-interrupt finding came from reading the actual SDK source.
- Pitfalls: HIGH for the Pydantic / OpenAI / Anthropic / Claude Code pitfalls (verified from official docs); MEDIUM for the logging filter `record.args = ()` requirement (cited from community sources but not in stdlib docs).
- ChatChunk schema: HIGH — Pydantic v2 discriminated union pattern is canonical and stable since v2.0.
- D-19 contract test shape: HIGH — `pytest-asyncio` + `pytest.mark.timeout(2)` + `pytest.mark.parametrize` is the canonical async-adapter test pattern.
- OpenRouter pricing refresh: HIGH for the schema (live curl); MEDIUM for the specific dollar-amount initial entries in `config/pricing.json` (these are best-effort and get replaced on first refresh).

**Research date:** 2026-05-15

**Valid until:** 2026-06-15 (30 days; the rapidly-moving SDKs — claude-agent-sdk especially with releases every 1-3 days — should be re-checked monthly). The locked decisions (D-01..D-20) and the architectural pattern are valid indefinitely; only specific version numbers and the OpenRouter pricing snapshot age out.
