# Phase 2: Backend Adapters & ChatChunk Contract - Context

**Gathered:** 2026-05-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Three async backend adapters — **OpenRouter** (chat models via OpenAI SDK v1.40+), **Claude Code** (build-and-edit via `claude-agent-sdk 0.1.80+`), and **computer-use** (browse-and-act via `anthropic 0.40+` with `computer_20251124` tool + `computer-use-2025-11-24` beta header on Claude Opus 4.7 / Sonnet 4.6) — each implementing the same `BackendAdapter` Protocol:

```python
class BackendAdapter(Protocol):
    async def stream(
        self,
        prompt: str,
        history: list[Message],
        options: AdapterOptions,
    ) -> AsyncIterator[ChatChunk]: ...
```

`ChatChunk` is a discriminated Pydantic v2 union: `TextDelta | ToolCall | ToolResult | FileDiff | Screenshot | StreamError | Done`. Adapters consume the `model_or_agent` string from a Phase 1 `RoutingDecision` and stream provider events through to chunks. Per-turn USD cap ($0.50) and per-iteration step cap (15 / 25) enforced inside each adapter; cancellation propagates to upstream within 2 s; key redaction installed at process import time; computer-use OFF unless `COMPUTER_USE_OPT_IN=1`; pre-commit hook blocks `sk-` / `sk-ant-` content.

**Verification surface:** per-adapter CLIs (`python -m apps.api.backends.{openrouter,claude_code,computer_use} --prompt "..."`) stream `ChatChunk` JSON lines to stdout. Unit tests use hand-stubbed provider fakes; live tests are opt-in via `pytest -m live` and gated by BYOK env vars.

**Not in scope (deferred to later phases):**
- FastAPI endpoints, SSE wire format, lifespan loading (Phase 3)
- SQLite persistence and routing-decisions JSONL (Phase 3)
- Disk-by-hash blob writes (Phase 3 wraps the Phase 2 stream — Screenshot stays base64 in Phase 2)
- Any UI rendering, settings panel, slash commands (Phase 4/5)
- `make setup`, README golden path, fresh-clone UAT, Playwright UI E2E (Phase 6)
- Live retraining, v2 routing items (out of milestone)

</domain>

<decisions>
## Implementation Decisions

### ChatChunk Contract

- **D-01: ChatChunk is a Pydantic v2 BaseModel discriminated union** keyed by a `Literal["text_delta" | "tool_call" | "tool_result" | "file_diff" | "screenshot" | "stream_error" | "done"]` `type` field. Each variant is a `BaseModel` with its own fields; the union is `Annotated[Union[...], Field(discriminator="type")]`. Pydantic is added as a Phase 2 base dependency (`pydantic>=2.6,<3.0`); Phase 3 FastAPI uses it natively, so there is no double-cost. `model_dump_json()` will be the SSE serializer in Phase 3. Adapter signatures use the union type; runtime validation is automatic.

- **D-02: BACKEND-01's six-variant union grows to seven by adding `ToolResult`.** REQUIREMENTS-BACKEND-01 enumerates `TextDelta | ToolCall | Screenshot | FileDiff | StreamError | Done`. We add a generic `ToolResult` variant so non-edit tools (Bash stdout, Read file contents, computer-use action narration) carry a typed result chunk linked back to the originating call. `FileDiff` remains the typed specialization for `Edit` / `Write`. Update REQUIREMENTS.md BACKEND-01 wording to `TextDelta | ToolCall | ToolResult | FileDiff | Screenshot | StreamError | Done` as part of this phase.

- **D-03: Tool calls and their results are flat sibling chunks linked by `tool_call_id`.** Both `ToolCall` and the matching `ToolResult` / `FileDiff` carry `tool_call_id: str`. The UI joins on this id to render the result under its call. Wire order is causal (call before result) but the schema does not require nesting. This matches the Anthropic SDK's flat event stream and keeps SSE dead simple.

- **D-04: Every stream terminates with `[StreamError]?` then `Done` — `Done` always lands.** Happy path: `… TextDelta(s) … Done`. Abnormal termination: `… StreamError(code, message, retriable) Done(metrics-so-far)`. Cancellation is treated as `StreamError(code="cancelled", retriable=True)` followed by `Done`. The terminal-pair invariant is asserted by the shared contract test (D-19) so Phase 4 UI-06 ("preserve partial response") and Phase 3 FastAPI can rely on it without sniffing the iterator.

- **D-05: TextDelta is pass-through — one TextDelta per provider event, no coalescing.** Adapter forwards each token/chunk from the upstream SDK (OpenAI streaming, Anthropic streaming, claude_agent_sdk message events) as a single TextDelta. No time-window or sentence-break buffering at the adapter layer. Phase 5 UI-03's "no per-token re-highlight flicker" requirement is solved in the renderer, not the adapter. AI SDK v5 (Phase 4) expects this granularity.

- **D-06: StreamError carries `code: str`, `message: str`, `retriable: bool`.** Closed initial vocabulary: `cost_cap_exceeded`, `step_cap_exceeded`, `cancelled`, `rate_limited`, `auth_failed`, `provider_unavailable`, `timeout`, `validation_error`, `internal_error`. Add cases as needed via planner discretion; document in `apps/api/backends/chunks.py` docstring.

### Module Layout

- **D-07: Birth `apps/` now — adapters live at `apps/api/backends/<backend>/`.** ROADMAP Phase 2 SC #1 (`python -m apps.api.backends.openrouter --prompt "..."`) drives this. Phase 3 lands `apps/api/main.py` next to it. Phase 4 introduces `apps/web/`. `src/routing/` is untouched (Phase 1 D-18 import-graph guard remains intact). `pyproject.toml` `[tool.hatch.build.targets.wheel]` packages list grows to `["src", "apps"]`.

- **D-08: Per-backend directory with split modules.** Each backend lives in its own directory mirroring `src/routing/`'s split:
  ```
  apps/api/backends/<backend>/
    __init__.py          # exports the adapter class
    __main__.py          # the per-adapter CLI required by SC #1
    adapter.py           # class XxxAdapter implements BackendAdapter
    cost.py              # CostTracker subclass for this backend's pricing
    errors.py            # provider-error -> StreamError mapping
    <backend-specific helpers>: workspace.py | screen.py | step_counter.py
    tests/
  ```
  Shared modules — one level up at `apps/api/backends/`:
  ```
  apps/api/backends/
    __init__.py
    protocol.py          # BackendAdapter Protocol
    chunks.py            # ChatChunk Pydantic union
    keystore.py          # in-memory + optional keyring
    logging_filter.py    # SECURE-01 redaction filter
    pricing.py           # PricingTable (loads config/pricing.json)
    tests/
      test_adapter_contract.py   # shared contract suite (D-19)
  ```

- **D-09: SECURE-02 pre-commit hook ships via the `pre-commit` framework.** Add `pre-commit` as a dev dep. Commit `.pre-commit-config.yaml` with two local hooks: (a) `no-secrets` running `scripts/no-secrets.sh` against staged content (regex: `^\+.*(sk-ant-[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9]{20,}|Bearer [A-Za-z0-9_.-]{20,})`); (b) `no-deprecated-claude-code-sdk` running `scripts/no-deprecated-sdk.sh` (greps staged content + `uv.lock` for `claude-code-sdk`, satisfies OSS-06 from the contributor side too). `pre-commit install` is added to `make setup` (Phase 6 OSS-02).

- **D-10: `keyring` is an optional extra, lazy-loaded.** `pyproject.toml`: `[project.optional-dependencies] keyring = ["keyring>=24,<26"]`. `apps/api/backends/keystore.py`: `try: import keyring; _HAS_KEYRING = True; except ImportError: _HAS_KEYRING = False`. `KeyStore(use_keyring=True)` raises if the extra is not installed. Linux dbus-python transitive is gated behind the extra. README documents `uv sync --extra keyring` for users who want disk persistence.

- **D-11: BYOK keys flow via `python-dotenv` loaded at `apps/api/__init__.py` import.** `apps/api/__init__.py` calls `dotenv.load_dotenv()` (no-op if `.env` is missing) and `install_redaction_filter()` (SECURE-01) at import. Adapter constructors call `KeyStore.get(provider)` which falls back to `os.environ.get(VAR)`. Env var convention: `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `COMPUTER_USE_OPT_IN`. `.env` is already gitignored by Phase 1 SECURE-03. Phase 5 settings panel (UI-12) calls `KeyStore.set(provider, key)` directly without touching env vars.

### Computer-Use Adapter Shape

- **D-12: Adapter owns the full agent loop.** `ComputerUseAdapter.stream()` runs the entire screenshot → model → action → screenshot loop internally: take screenshot → send to Claude with `computer_20251124` tool → receive action(s) → execute → take new screenshot → repeat until model issues `stop_reason="end_turn"` or 15-step cap is hit. Per-iteration chunks emitted: `TextDelta` (model commentary), `ToolCall` (action), `Screenshot` (post-action), `ToolResult` (action narration). Caller (Phase 3 FastAPI) just consumes the stream — symmetric with OpenRouter/Claude Code adapter shapes.

- **D-13: Execution target is a Playwright Chromium sandbox per turn.** `apps/api/backends/computer_use/screen.py` wraps `async_playwright()` with a 1280×800 viewport (Anthropic's `computer_20251124` default; no DPI math). Actions: `click(x,y)` → `page.mouse.click`; `screenshot()` → `page.screenshot(type="png")`; `key(name)` → `page.keyboard.press`; `type(text)` → `page.keyboard.type`; `navigate(url)` → `page.goto`. Bounded blast radius: browser only, no filesystem, no native apps. Add `playwright>=1.45,<2.0` as a base dep + `playwright install chromium` in `make setup` (Phase 6). Synergy: Playwright also satisfies OSS-07 Phase 6 UI E2E test dep — same install. Acceptable tradeoff: loses non-browser desktop capability (out of scope for the BACKEND-05 use case "open this URL and check the price").

- **D-14: Screenshot chunk is base64-inline in Phase 2; Phase 3 wraps the stream and converts to disk-ref when ≥256 KB per STORE-04.** Schema fields: `image_b64: str | None`, `image_ref: str | None`, `image_format: Literal["png","jpeg"] = "png"`, `step: int`. Phase 2 only sets `image_b64` (always). Phase 3 conditionally swaps to `image_ref = "~/.prompt-optimizer/blobs/<sha256>.png"` when bytes ≥ 256 KB. Phase 4/5 UI handles either. Defers filesystem state until SQLite arrives in Phase 3.

- **D-15: "Step" = agent loop iteration for both adapters; cap = 15 (computer-use), 25 (Claude Code).** One step = one model round-trip. Computer-use: each `messages.create` call (which can contain multiple tool_use blocks) is one step. Claude Code: each `assistant` message from `claude_agent_sdk.query()` is one step.
  - **Deviation note:** REQUIREMENTS-BACKEND-06 reads "25 tool calls (Claude Code), 15 steps (computer-use)." We re-read both as "iterations" for mental-model consistency (one progress unit across both adapters). **Update REQUIREMENTS.md BACKEND-06 wording in this phase to**: "Each adapter enforces a hard per-turn USD cap (default $0.50) and per-iteration step cap (25 for Claude Code, 15 for computer-use) at the adapter boundary." Step exhaustion emits `StreamError(code="step_cap_exceeded", retriable=False)` + `Done`.

### Cost Cap Mechanism

- **D-16: Cost is tracked per-adapter as a post-hoc running total via a shared `CostTracker` interface.** `apps/api/backends/cost.py` provides a base `CostTracker` with `record_input(n)`, `record_output_delta(n)`, `total() -> float`, `over_cap() -> bool`. Each adapter has a subclass that knows how to extract token counts from its provider's events:
  - OpenRouter: pre-record input tokens from estimate, then `record_output_delta` per `delta.content` token.
  - Claude Code: per-message `usage` block (when present) feeds both counters; final `result.total_cost_usd` overrides at `Done` time.
  - Computer-use: per-iteration `usage` block updates both counters; screenshot bytes don't count toward token cost (Anthropic charges separately for image tokens — pricing table reflects this).
  After every chunk emission, adapter checks `tracker.over_cap()`; if true, emit `StreamError(code="cost_cap_exceeded", retriable=False)` + `Done(cost_usd=tracker.total(), ...)` and return.

- **D-17: Pricing comes from `config/pricing.json` (committed) with optional OpenRouter `/api/v1/models` refresh on startup.** Schema: `{"<model_id>": {"input_per_mtok": float, "output_per_mtok": float}, "_default": {...}}`. OpenRouter adapter on startup attempts `GET https://openrouter.ai/api/v1/models` (no auth required) and updates the in-memory table for known slugs; result cached at `~/.prompt-optimizer/cache/openrouter_models.json` for 24 h. If refresh fails, fall back to static. Tests use a fixture `PricingTable` constructed from a deterministic dict (no HTTP). Initial entries: the 9 OpenRouter-verified slugs from Phase 1's `config/model_mapping.json`, plus `anthropic/claude-opus-4-7` and `anthropic/claude-sonnet-4-6`, plus a `_default` fallback (`{input_per_mtok: 5.00, output_per_mtok: 20.00}`).

### Test Strategy

- **D-18: Tiered test strategy: hand-stubbed fakes for unit tests + opt-in live smoke gated by `pytest -m live`.** Default test suite uses per-adapter fakes (`FakeOpenAIClient`, `FakeAnthropicClient`, `fake_claude_code_query`, `FakePlaywrightScreen`) injected via constructor. Tests assert chunk sequences, cap enforcement, cancellation propagation — 100% offline, zero CI cost, deterministic. Live tests live alongside as `@pytest.mark.live` and `@pytest.mark.skipif(not os.getenv("…_API_KEY"))`; contributors run them opt-in. Add `markers = ["live: hits real provider APIs (BYOK required)"]` to `[tool.pytest.ini_options]`.

- **D-19: Shared `BackendAdapter` contract test parameterized across all 3 adapters.** `apps/api/backends/tests/test_adapter_contract.py` enforces invariants every adapter MUST satisfy (regardless of provider specifics):
  1. Happy path emits at least one `TextDelta` and exactly one terminal `Done`.
  2. Cost cap aborts mid-stream → emits `StreamError(code="cost_cap_exceeded", retriable=False)` + `Done`.
  3. Step cap aborts → emits `StreamError(code="step_cap_exceeded", retriable=False)` + `Done`.
  4. Cancellation (caller `aclose()`s the iterator) emits `StreamError(code="cancelled", retriable=True)` + `Done` within 2 s.
  5. `Done` always lands as the last chunk.
  6. Provider-key absent at construction time raises a typed exception BEFORE `stream()` is awaited.
  Per-adapter `tests/` directories cover provider-specific invariants (OpenRouter `HTTP-Referer` / `X-Title` headers, computer-use coordinate scaling, Claude Code workspace cleanup on thread close, claude-agent-sdk import smoke, etc.).

- **D-20: CI green = uv-sync + pre-commit + import-smoke + redaction-filter test + `pytest -m 'not live'` only. No live calls on push.** CI workflow steps (added to the existing `.github/workflows/ci.yml` from Phase 1):
  ```yaml
  - run: uv sync --locked --extra keyring
  - run: pre-commit run --all-files
  - run: python -c "from claude_agent_sdk import ClaudeAgentOptions"   # OSS-06
  - name: ensure deprecated SDK absent                                  # OSS-06
    run: |
      ! python -c "import claude_code_sdk" 2>/dev/null
      ! grep -q '"claude-code-sdk"' uv.lock
  - run: pytest -m 'not live' apps/api/backends                         # adapter unit tests
  - run: pytest src/                                                    # Phase 1 tests stay green
  ```
  Live smoke is a separate optional workflow (manual `workflow_dispatch` + scheduled weekly cron against OpenRouter only with `--live-budget=$0.10`); failures are informational, not push-blocking. Phase 1's `evaluate_routing --check` step keeps `continue-on-error: true` (already resolved in commit `64a07d2`).

### Claude's Discretion

The planner / researcher own these implementation details — no user preference was expressed:

- **Async runtime:** asyncio (default; matches FastAPI Phase 3) — anyio is acceptable if researcher finds a Trio-portability win, but not required.
- **`asyncio.CancelledError` vs explicit cancel token:** prefer the natural `aclose()` → upstream `interrupt()` / aborted HTTP path. No custom cancel-token API.
- **Pydantic version:** `pydantic>=2.6,<3.0`. Researcher pins exact lower bound based on `model_config` features used.
- **OpenRouter `HTTP-Referer` / `X-Title` values:** `HTTP-Referer = "https://github.com/<owner>/Prompt-Optimizer"` and `X-Title = "Prompt-Optimizer"` (OpenRouter attribution; lets the project show up on the OpenRouter leaderboard).
- **claude-agent-sdk MCP tool restriction list:** lock to `["Read", "Edit", "Write", "Bash", "Glob", "Grep"]` for v1 (no MCP, no Notebook tools). Planner expands if research surfaces a need.
- **`CLAUDE_ENABLE_STREAM_WATCHDOG=1` install point:** `apps/api/backends/claude_code/__init__.py` sets it via `os.environ.setdefault(...)` at module import. Subprocess inherits.
- **Per-thread workspace path template:** `~/.prompt-optimizer/workspaces/<thread_id>/`. In Phase 2 (no thread_id yet), the per-adapter CLI uses `tempfile.mkdtemp(prefix="pomu-cc-")` and removes on exit.
- **`RoutingDecision.signals` flow into adapter:** adapter stores `decision.signals` on the `Done` chunk's `routing_signals: dict | None` field (optional) so Phase 3 can persist them straight into the `routing_decisions` SQLite row without re-decoding.
- **Per-adapter CLI flag set:** at minimum `--prompt`, `--max-cost-usd`, `--model`. Planner expands.
- **Pre-flight token estimator:** any reasonable approach (tiktoken for OpenAI-family, char-count fallback for Anthropic). Estimates only, real cost comes from provider.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner, executor) MUST read these before planning or implementing.**

### Phase Scope & Requirements

- `.planning/ROADMAP.md` §"Phase 2: Backend Adapters & ChatChunk Contract" — goal, dependencies, requirement mapping, 5 success criteria. Phase boundary is FIXED.
- `.planning/REQUIREMENTS.md` — read BACKEND-01 through BACKEND-09, SECURE-01, SECURE-02, SECURE-04, SECURE-05, OSS-06 (the 15 requirements assigned to Phase 2). **Update BACKEND-01 wording** to add `ToolResult` to the union (per D-02). **Update BACKEND-06 wording** to "per-iteration step cap" (per D-15).
- `.planning/PROJECT.md` — Core Value ("quality first, cost as tiebreaker"), constraints (BYOK, single-process, open-source), Active requirement bullets for OpenRouter / Claude Code SDK / computer-use integrations.
- `CLAUDE.md` (repo root) — project conventions, GSD workflow enforcement.

### Phase 1 Carry-Forward (the upstream contract Phase 2 consumes)

- `.planning/phases/01-router-brain-foundation/01-CONTEXT.md` — D-01 (cascade), D-04 (backend sentinels: `openrouter` / `claude_code` / `computer_use`; model strings: `openai/gpt-5` etc., `claude-agent-sdk`, `computer-use-2025-11-24`, `openrouter/auto`), D-18 (import-graph guard for `src/routing/`).
- `.planning/phases/01-router-brain-foundation/01-VERIFICATION.md` — Phase 1 closing state, what's already wired, what's deliberately deferred.
- `src/routing/schema.py` — `RoutingDecision` frozen dataclass; the `signals` dict carries the per-stage telemetry adapters surface in `Done.routing_signals`.
- `src/routing/decide.py` — pure-function entry point; adapters receive its output, never call it.
- `src/routing/__main__.py` — `python -m src.routing.decide "<prompt>"` produces the JSON payload Phase 2 CLIs may consume for end-to-end smoke.

### Existing Codebase Maps (read before touching repo)

- `.planning/codebase/ARCHITECTURE.md` — pipeline diagram, layer responsibilities, the **Stage-2 text-input duplication** anti-pattern (informs the contract test parameterization), and the **path-discovery / sys.path injection** anti-patterns (informs the apps/api package layout).
- `.planning/codebase/STACK.md` — Python 3.10+, no test framework before Phase 1 (pytest + uv added in Phase 1's `pyproject.toml` + `uv.lock`); no `requests`/`httpx`/`openai` SDKs imported anywhere yet (Phase 2 introduces them).
- `.planning/codebase/INTEGRATIONS.md` — `config/model_mapping.json` schema (16 slugs, 9 OpenRouter-verified, 7 simulated; `OTHER` fallback bucket). Phase 2 extends this with `config/pricing.json` per D-17.
- `.planning/codebase/STRUCTURE.md` — module layout conventions; `apps/api/` is new but mirrors the `src/<package>/` style.
- `.planning/codebase/CONVENTIONS.md` — `snake_case` modules, saved-artifact dict shape (not relevant to adapters), keyword-only args for boolean flags, sklearn metric reporting (not relevant), import / sys.path patterns.
- `.planning/codebase/CONCERNS.md` — known sys.path hacks and missing package-layout issues; Phase 2's `apps/api/` is the chance to land a clean import surface from day one.

### External SDK References

- `openai` Python SDK ≥ 1.40 — chat completions streaming API; `OpenAI(base_url="https://openrouter.ai/api/v1", api_key=...)` per BACKEND-03.
- `claude_agent_sdk` ≥ 0.1.80 — `query(prompt, options) -> AsyncIterator[Message]` and `query.interrupt()` for cancellation per BACKEND-04 + BACKEND-07. Deprecated `claude-code-sdk` package MUST NOT appear in `uv.lock` (OSS-06).
- `anthropic` Python SDK ≥ 0.40 — `client.beta.messages.create(model="claude-opus-4-7", tools=[{"type": "computer_20251124", ...}], betas=["computer-use-2025-11-24"], stream=True)` per BACKEND-05.
- `playwright` Python SDK ≥ 1.45 — `async_playwright()`, `chromium.launch(headless=True)`, `page.mouse.click`, `page.screenshot(type="png")` per D-13.
- `pydantic` ≥ 2.6 — `BaseModel`, `Field(discriminator="type")`, `Annotated[Union[...], Field(discriminator=...)]`, `model_dump_json()` per D-01.
- `pre-commit` framework — `.pre-commit-config.yaml` with local script hooks per D-09.
- `python-dotenv` — `load_dotenv()` at `apps/api/__init__.py` import per D-11.
- `keyring` ≥ 24 (optional extra) — `set_password` / `get_password` per D-10.

### Source Files That Must Stay Compatible

- `src/routing/decide.py`, `src/routing/policy.py`, `src/routing/schema.py`, `src/routing/config.py`, `src/routing/__main__.py` — Phase 1 modules. Phase 2 MUST NOT add any import to `src/routing/*` from `apps/api/` (the import direction is `apps/api → src/routing`, never the reverse). Phase 1 D-18 guard test in `src/routing/tests/test_decide_smoke.py` keeps watching this.
- `src/routing/tests/test_decide_smoke.py` — the D-18 import-graph guard. Verify it still passes after Phase 2 adds adapter imports (`fastapi`, `httpx`, `openai`, `anthropic` MUST NOT show up in `sys.modules` after `import src.routing.decide`).
- `pyproject.toml` — extend `[tool.hatch.build.targets.wheel] packages = ["src", "apps"]`, add new base deps (pydantic, openai, anthropic, claude-agent-sdk, playwright, python-dotenv, pre-commit), add `[project.optional-dependencies] keyring = [...]`, add `[tool.pytest.ini_options] markers = ["live: ..."]`.
- `uv.lock` — regenerate with `uv lock`. CI asserts `claude-code-sdk` absent.
- `.gitignore` — already gitignores `.env` (Phase 1 SECURE-03). No changes needed; Phase 2 adds `~/.prompt-optimizer/` if a contributor accidentally commits the home dir, but that's defensive.

### New Files Phase 2 Creates

- `apps/api/__init__.py` — `dotenv.load_dotenv()` + `install_redaction_filter()` at import.
- `apps/api/backends/__init__.py`, `protocol.py`, `chunks.py`, `keystore.py`, `logging_filter.py`, `pricing.py`, `cost.py`.
- `apps/api/backends/{openrouter,claude_code,computer_use}/__init__.py`, `__main__.py`, `adapter.py`, `cost.py`, `errors.py`, plus per-backend helpers (`workspace.py` for claude_code, `screen.py` for computer_use, `step_counter.py` for both agentic backends).
- `apps/api/backends/tests/test_adapter_contract.py` — D-19 shared parametric suite.
- `apps/api/backends/<backend>/tests/{conftest.py, fakes.py, test_*.py}` — per-adapter unit tests + per-adapter live smoke (`-m live`).
- `config/pricing.json` — per D-17.
- `.pre-commit-config.yaml`, `scripts/no-secrets.sh`, `scripts/no-deprecated-sdk.sh` — per D-09.
- `.github/workflows/ci.yml` — extend the Phase 1 workflow per D-20.
- `.github/workflows/live-smoke.yml` (optional) — manual + weekly cron live smoke gated by repo secrets per D-20.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **Phase 1 `RoutingDecision`** (`src/routing/schema.py`) — concrete provider-ready `model_or_agent` strings (`openai/gpt-5`, `anthropic/claude-opus-4-7`, `claude-agent-sdk`, `computer-use-2025-11-24`, `openrouter/auto`). Adapters consume these directly with no second resolution step (D-04 from Phase 1).
- **Phase 1 `RoutingDecision.signals`** — structured per-stage telemetry that Phase 2 surfaces on `Done.routing_signals` so Phase 3 can persist it straight into the `routing_decisions` SQLite row.
- **Phase 1 `pyproject.toml` + `uv.lock`** (OSS-01) — base environment is already locked; Phase 2 extends it.
- **Phase 1 `.gitignore`** (SECURE-03) — `.env`, `*.db*`, `__pycache__/`, `.venv/`, `chat.db` already excluded.
- **Phase 1 pytest configuration** — `pyproject.toml [tool.pytest.ini_options]` uses `--import-mode=importlib`; Phase 2 keeps this and adds the `live` marker.
- **Phase 1 `.github/workflows/ci.yml`** — `uv sync --locked` + `pytest -x -q` baseline; Phase 2 extends with the OSS-06 import smoke and adapter test step.
- **`config/model_mapping.json`** (16 entries) — the `api_model` field on each entry is exactly the string an OpenRouter adapter sends to OpenAI SDK. `openrouter_verified: true` is the gate Phase 2 honors before issuing a real call.

### Established Patterns

- **`src/routing/` module split** (`decide.py` / `policy.py` / `schema.py` / `config.py` / `__main__.py` / `tests/`) — D-08 mirrors this for `apps/api/backends/<backend>/`.
- **CLI entry via `__main__.py`** — Phase 1 ships `python -m src.routing.decide`. Phase 2 ships `python -m apps.api.backends.openrouter` per SC #1. Same idiom.
- **Saved-artifact dict shape** — irrelevant to adapters (no joblib), but the `joblib.dump({...})` + required-key validation pattern from `src/demo/demo_router.py:35` is the spiritual parent of the Pydantic-validated chunk approach.
- **Deviation-noting in CONTEXT** — Phase 1 used "DEVIATION" notes (e.g., D-01 cascade reorder, browse-keyword fires before coding). D-15 in this CONTEXT follows the same pattern for the BACKEND-06 step-cap re-reading.

### Integration Points

- **`apps/api/__init__.py`** — entry point for the redaction filter (SECURE-01, "installed at process import time") and `python-dotenv` load. Importing any adapter (`from apps.api.backends.openrouter import OpenRouterAdapter`) triggers both.
- **`apps/api/backends/protocol.py`** — `BackendAdapter` `Protocol`; type-checked usage in Phase 3 FastAPI lifespan: `adapters: dict[str, BackendAdapter] = {"openrouter": OpenRouterAdapter(), ...}`.
- **`apps/api/backends/chunks.py`** — `ChatChunk` Pydantic union. Phase 3 FastAPI imports as `from apps.api.backends.chunks import ChatChunk` and serializes via `chunk.model_dump_json()` for SSE; Phase 4 Next.js parser consumes the JSON shape.
- **`apps/api/backends/keystore.py`** — singleton `KeyStore`; Phase 5 settings panel (UI-12) calls `KeyStore.set(provider, key)` server-side.
- **`config/pricing.json`** (new) — sibling to `config/model_mapping.json`. Both are `json.load`'d on startup; the loader pattern from `src/demo/demo_router.py:load_json()` carries over.
- **`.github/workflows/ci.yml`** — Phase 2 adds steps; the existing `evaluate_routing --check` step from Phase 1 keeps `continue-on-error: true` (resolved in commit `64a07d2`).

### Anti-Patterns to AVOID (from ARCHITECTURE.md + CONCERNS.md)

- **Do NOT add another `sys.path.append`** to import shared modules. `apps/` and `src/` are both proper packages declared in `pyproject.toml` `[tool.hatch.build.targets.wheel]`. Use `from apps.api.backends.chunks import TextDelta`, `from src.routing.decide import decide` — no path mutation.
- **Do NOT duplicate path-discovery boilerplate** (`PROJECT_ROOT = os.path.abspath(...)`) in adapter modules. Use `pathlib.Path(__file__).resolve().parents[N]` if absolutely needed; prefer importable paths from a single `apps/api/paths.py` module if the constants are referenced more than twice.
- **Do NOT import any adapter from `src/routing/`.** Phase 1 D-18 import-graph guard test asserts this. The dependency direction is `apps/api → src/routing`, never the reverse. Adapters MAY import `from src.routing.schema import RoutingDecision, Backend` (those modules use stdlib only).
- **Do NOT log raw key material.** `apps/api/__init__.py` installs the SECURE-01 redaction filter at import time; adapter logging must use `logging.getLogger(__name__)` so the filter applies. Direct `print()` of keys is forbidden by the redaction filter regression test.
- **Do NOT block the asyncio loop with `requests` / `httpx.Client.send`.** Use `httpx.AsyncClient`, `openai.AsyncOpenAI`, `anthropic.AsyncAnthropic`, `playwright.async_api`. Phase 3 FastAPI is asyncio-native; sync calls would defeat the SSE design.
- **Do NOT silently fall back to the deprecated `claude-code-sdk` package.** `from claude_agent_sdk import ClaudeAgentOptions` is mandatory. CI smoke + pre-commit hook + `uv.lock` grep all guard this (D-09 + D-20).

</code_context>

<specifics>
## Specific Ideas

- **The terminal pair `[StreamError]?` + `Done` is invariant.** Every test in the shared contract suite (D-19) ends with `assert isinstance(chunks[-1], Done)`. Phase 4 UI's "preserve partial response on stop" (UI-06) is downstream of this guarantee.
- **`tool_call_id` is a `str` set by the adapter when the upstream SDK doesn't provide one.** Format: `tc_<6-char-base32>` (e.g., `tc_a3f7zq`). Reuse the same id for the originating `ToolCall` and its matching `ToolResult` / `FileDiff`.
- **Cancellation timing budget: 2 seconds.** Adapter has 2 s from `aclose()` to surface `StreamError(code="cancelled") + Done`. The contract test uses `asyncio.timeout(2)` to enforce this.
- **OpenRouter attribution headers:** `HTTP-Referer = "https://github.com/<owner>/Prompt-Optimizer"` (from PROJECT title), `X-Title = "Prompt-Optimizer"`. Lets the project rank on OpenRouter's leaderboard.
- **Default `max_cost_usd = 0.50`** lives in `apps/api/backends/cost.py` as `DEFAULT_PER_TURN_COST_USD: Final[float] = 0.50`. Adapter constructors accept `max_cost_usd: float | None = None` and fall back to the default. Tests construct adapters with `max_cost_usd=0.001` to force easy cap-aborts.
- **Default step caps** live in `apps/api/backends/<backend>/step_counter.py` as `DEFAULT_STEP_CAP: Final[int] = 25` (claude_code) / `15` (computer_use). Tests construct with `max_steps=2`.
- **Computer-use viewport: `(1280, 800)` logical pixels.** Matches `computer_20251124` tool default; no DPI conversion. Override via `ComputerUseAdapter(viewport=(width, height))` if a planner finds a reason.
- **`COMPUTER_USE_OPT_IN=1` is checked at `ComputerUseAdapter.__init__` time.** If env var is unset/false, raises `RuntimeError("computer-use is OFF — set COMPUTER_USE_OPT_IN=1 to enable")` BEFORE any provider client is constructed (no key-leak surface).
- **Claude Code workspace path in Phase 2:** `tempfile.mkdtemp(prefix="pomu-cc-")`, removed via `shutil.rmtree` in `__aexit__` of an `async with adapter:` context. Phase 3 swaps to `~/.prompt-optimizer/workspaces/<thread_id>/` (BACKEND-08). The `cwd` opt-in flag for "point at user's repo" is an `AdapterOptions` field, default `None`.
- **`CLAUDE_ENABLE_STREAM_WATCHDOG=1`** is set via `os.environ.setdefault(...)` at `apps/api/backends/claude_code/__init__.py` import. Subprocess inherits.
- **`_default` entry in `config/pricing.json`** is `{input_per_mtok: 5.00, output_per_mtok: 20.00}` — conservative upper bound used when an unknown model id slips through. Cap exhaustion will trigger early for unknowns, which is the safe failure mode.
- **`Done.routing_signals: dict | None`** on the `Done` chunk surfaces `RoutingDecision.signals` so Phase 3 can persist directly into `routing_decisions.signals` SQLite column without re-decoding.
- **Update REQUIREMENTS.md as part of this phase**:
  - BACKEND-01: union → `TextDelta | ToolCall | ToolResult | FileDiff | Screenshot | StreamError | Done`.
  - BACKEND-06: "per-iteration step cap (25 for Claude Code, 15 for computer-use)".

</specifics>

<deferred>
## Deferred Ideas

- **Gitleaks / detect-secrets full secret scanner** (alternative to D-09's per-prefix grep). Would catch AWS keys, GitHub tokens, JWTs, etc. Defer to Phase 6 OSS hardening. The D-09 hook is sufficient for Phase 2's threat model (BYOK keys only).
- **Settings panel BYOK entry / per-backend toggles** — Phase 5 UI-12. `KeyStore.set(provider, key)` is callable from Phase 2 already, so Phase 5's UI just calls into the existing API.
- **Disk-by-hash blob writes for screenshots** — Phase 3 wraps the Phase 2 stream and converts large `image_b64` to `image_ref` per STORE-04. The schema field is present from Phase 2 (D-14).
- **Pricing-table refresh from Anthropic models endpoint** — Anthropic doesn't expose a public `/v1/models` with pricing, so Phase 2 sticks with hand-curated entries for `anthropic/claude-opus-4-7` and `anthropic/claude-sonnet-4-6`. Revisit if Anthropic ships a programmatic pricing API.
- **`RoutingDecision.signals` → `routing_decisions.jsonl`** — STORE-06 (Phase 3) appends each decision as a JSON line. Phase 2 just preserves the dict on `Done.routing_signals`; Phase 3 owns the disk write.
- **Cross-backend handoff (preserve agent state across backend switches mid-thread)** — REQUIREMENTS v2 ROUTER-V2-04. Out of v1.
- **Model fallback chain (auto-retry within tier on provider error)** — REQUIREMENTS v2 ROUTER-V2-03. Out of v1.
- **Live retraining loop from chat-UI traffic** — PROJECT.md "Out of Scope" line; v2 only.
- **MCP marketplace / pluggable adapter registry** — REQUIREMENTS Out of Scope.
- **Voice / audio input, file uploads, persona marketplace** — REQUIREMENTS Out of Scope; would expand the ChatChunk union beyond what Phase 2 commits to.
- **VCR cassettes for adapter tests** — alternative to D-18's hand-stubbed fakes. Could be folded in if maintenance of the fakes becomes a burden, but adds the cassette-staleness problem. Defer to a later cleanup phase if the fakes show drift.
- **Refresh-from-OpenRouter pricing failure handling** — D-17 says "fall back to static" on refresh failure. Researcher / planner decide whether to log a warning on every fallback or once per startup.
- **Tier-router family migration** — Phase 1 noted `src/model_router_tier/` still has its own `build_text_input` (CONTEXT D-15-style duplication). Out of Phase 2 scope.

</deferred>

---

*Phase: 2-backend-adapters-chatchunk-contract*
*Context gathered: 2026-05-14*
