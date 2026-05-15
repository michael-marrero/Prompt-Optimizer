# Phase 2: Backend Adapters & ChatChunk Contract - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-14
**Phase:** 2-backend-adapters-chatchunk-contract
**Areas discussed:** ChatChunk runtime form, Module layout, Computer-use adapter shape, Live-API test strategy

---

## ChatChunk runtime form

### Q1 — Runtime form for ChatChunk

| Option | Description | Selected |
|--------|-------------|----------|
| Pydantic v2 BaseModel + discriminated union | Each variant a Pydantic BaseModel; union discriminated by `type` field. FastAPI uses Pydantic natively in Phase 3; `model_dump_json()` gives clean SSE serialization. Adds a Phase 2 dep but Phase 3 needs it anyway. | ✓ |
| Frozen @dataclass + type field | Mirrors Phase 1's `RoutingDecision` style — stdlib only, no new dep at Phase 2. Manual `to_json()` per variant. | |
| TypedDict | Plainest possible — shape-typed dicts. Zero runtime validation, zero overhead. No frozen guarantees. | |

**User's choice:** Pydantic v2 BaseModel + discriminated union (Recommended)
**Notes:** Pydantic enters in Phase 2 rather than Phase 3 because the schema benefits (validation, IDE autocomplete, schema generation, `model_dump_json()`) outweigh the single-phase dep delay. Phase 1's `RoutingDecision` stays a stdlib `@dataclass` for D-18 import-graph guard reasons; the divergence is intentional (different layers).

---

### Q2 — Tool call ↔ result linkage

| Option | Description | Selected |
|--------|-------------|----------|
| Flat sibling chunks linked by `tool_call_id` | ToolCall and FileDiff/ToolResult are independent ChatChunks; both carry `tool_call_id`. Simplest streaming, easy SSE, UI joins on id. Matches Anthropic SDK's flat event stream. | ✓ |
| Nested: FileDiff is a field on ToolCall | ToolCall carries optional `result` field filled when tool completes. Adapter buffers and re-yields. | |
| Flat siblings, no tool_call_id linkage | Stream order alone pairs them. Fragile if chunks ever reorder. | |

**User's choice:** Flat siblings linked by tool_call_id (Recommended)
**Notes:** Implicitly grows the BACKEND-01 union from 6 variants to 7 — adds a generic `ToolResult` for non-edit tools (Bash stdout, Read contents, computer-use action narration). FileDiff stays the typed specialization for Edit/Write. REQUIREMENTS-BACKEND-01 wording will be updated as part of Phase 2 (D-02).

---

### Q3 — Final-chunk contract on abnormal termination

| Option | Description | Selected |
|--------|-------------|----------|
| Always StreamError then Done | Optional StreamError + mandatory Done on every termination (cancelled, cap hit, error, happy-path). Done always lands. | ✓ |
| StreamError only on error, Done always (with cancelled flag) | Cancellation is not an error; Done carries `cancelled=True`. Subtler distinction. | |
| Raise typed exceptions instead of StreamError | Caller catches `CostCapExceeded`, `Cancelled`, etc. Wire format diverges from iterator interface. | |

**User's choice:** Always StreamError then Done (Recommended)
**Notes:** Phase 4 UI-06 ("preserve partial response") and Phase 3 FastAPI rely on `Done` always arriving. Cancellation gets `StreamError(code="cancelled", retriable=True)` so the UI can show "stopped" without sniffing the iterator state.

---

### Q4 — TextDelta streaming granularity

| Option | Description | Selected |
|--------|-------------|----------|
| Pass-through, one TextDelta per provider event | Adapter forwards each upstream token/chunk as one TextDelta. Lowest latency; matches AI SDK v5 expectations. | ✓ |
| Time-windowed coalescing (e.g., 50ms) | Adapter buffers up to 50ms then flushes one larger TextDelta. Smoother UI, fewer SSE frames. | |
| Sentence-break coalescing | Adapter waits for `. ! ? \n` before flushing. Most natural rendering, very high latency. | |

**User's choice:** Pass-through, one TextDelta per provider event (Recommended)
**Notes:** Phase 5 UI-03 "no per-token re-highlight flicker" is solved in the renderer, not the adapter. Adapter stays as dumb as possible.

---

## Module layout

### Q1 — Where do backend adapters live?

| Option | Description | Selected |
|--------|-------------|----------|
| Birth `apps/api/` now — adapters at `apps/api/backends/` | ROADMAP SC #1 CLI text matches as-is. Phase 3 FastAPI lands at `apps/api/main.py`. | ✓ |
| Land under `src/backends/`, move in Phase 3 | Avoids creating a half-empty `apps/` tree in Phase 2. ROADMAP CLI hint reworded. | |
| Hybrid: contracts in `src/`, adapters in `apps/` | Clean separation between contract and implementations. | |

**User's choice:** Birth apps/api/ now (Recommended)
**Notes:** `src/routing/` remains untouched (Phase 1 D-18 guard intact). `pyproject.toml [tool.hatch.build.targets.wheel]` packages list grows to `["src", "apps"]`.

---

### Q2 — Per-backend file structure

| Option | Description | Selected |
|--------|-------------|----------|
| Directory per backend with split modules | adapter.py, __main__.py, helpers (cost.py / workspace.py / screen.py / step_counter.py / errors.py), tests/. Mirrors src/routing/. | ✓ |
| Single-file adapter per backend | Each backend is one Python file. Simpler tree; larger files. | |
| Flat — all adapters share apps/api/backends/ with naming prefixes | Avoids deep nesting; tighter coupling between backends. | |

**User's choice:** Directory per backend (Recommended)
**Notes:** Each adapter gets its own `__main__.py` for the SC #1 per-adapter CLI. Shared modules (chunks.py, keystore.py, logging_filter.py, protocol.py, pricing.py, cost.py) live one level up.

---

### Q3 — SECURE-02 pre-commit hook installation

| Option | Description | Selected |
|--------|-------------|----------|
| pre-commit framework with .pre-commit-config.yaml + custom local hook | Standard Python toolchain; works on every contributor's machine; Phase 6 OSS contributors expect it. | ✓ |
| Raw .git/hooks/pre-commit shell script | No extra Python dep. Lower magic. | |
| Gitleaks/detect-secrets via pre-commit framework | Industry-standard secret scanner. Heavier dep; broader coverage. | |

**User's choice:** pre-commit framework (Recommended)
**Notes:** Same .pre-commit-config.yaml also adds the no-deprecated-claude-code-sdk hook for OSS-06. `pre-commit install` runs in `make setup` (Phase 6 OSS-02).

---

### Q4 — keyring shipping strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Optional dep, lazy-loaded — `[project.optional-dependencies] keyring = [...]` | Base install lightweight; users opt in via `uv sync --extra keyring`. | ✓ |
| Required dep — always installed | Pulls platform-specific transitive deps on Linux. | |
| No keyring in Phase 2 — in-memory only | Strictly meets SECURE-04 minimum; defers "optional keyring" to v2. | |

**User's choice:** Optional dep, lazy-loaded (Recommended)
**Notes:** `KeyStore(use_keyring=True)` raises if extra not installed. Linux dbus-python transitive is gated.

---

### Q5 — BYOK key flow into KeyStore

| Option | Description | Selected |
|--------|-------------|----------|
| python-dotenv at apps/api/__init__.py import | `dotenv.load_dotenv()` once at package import; adapters read os.environ via KeyStore.get fallback. | ✓ |
| Explicit os.environ reads in each adapter, no dotenv | Lighter footprint; worse first-run UX. | |
| Key file at ~/.prompt-optimizer/keys.toml | First-class config file; duplicates the .env / keyring story. | |

**User's choice:** python-dotenv at apps/api/__init__.py (Recommended)
**Notes:** Same site installs the SECURE-01 redaction filter at process import time. Env-var convention: OPENROUTER_API_KEY, ANTHROPIC_API_KEY, COMPUTER_USE_OPT_IN.

---

## Computer-use adapter shape

### Q1 — Agent loop ownership

| Option | Description | Selected |
|--------|-------------|----------|
| Adapter owns the full loop, yields ChatChunks per iteration | Matches Anthropic's reference computer_use loop pattern. Symmetric with OpenRouter / Claude Code adapter shapes. | ✓ |
| Caller drives the loop, adapter is single-step | Pushes loop logic to FastAPI. Mismatched abstraction with the other two adapters. | |
| Spike first, decide later | Run a `/gsd-spike` (~1-2h) to validate against real Anthropic responses before committing. | |

**User's choice:** Adapter owns the full loop (Recommended)
**Notes:** Each iteration emits TextDelta + ToolCall + Screenshot + ToolResult chunks. Stops on `stop_reason="end_turn"` or 15-step cap.

---

### Q2 — Execution target

| Option | Description | Selected |
|--------|-------------|----------|
| Playwright Chromium sandbox per turn | Bounded blast radius (browser only); coordinate scaling solved by viewport (1280×800 logical px); synergy with OSS-07 Phase 6 E2E. | ✓ |
| Anthropic-recommended Docker container (xdotool + scrot) | Broadest capability; heavy install (Docker required); 10s startup; full Linux user threat surface. | |
| Local OS via pyautogui | Highest fidelity; ZERO isolation — model can click anywhere in user's real desktop. Strongly discouraged for OSS. | |

**User's choice:** Playwright Chromium sandbox (Recommended)
**Notes:** Adds `playwright>=1.45,<2.0` as base dep + `playwright install chromium` in `make setup` (Phase 6). Loses non-browser desktop capability — acceptable per BACKEND-05 use case ("open this URL and check the price").

---

### Q3 — Screenshot delivery in ChatChunk

| Option | Description | Selected |
|--------|-------------|----------|
| Always base64-inline in Phase 2; STORE-04 adds disk-ref in Phase 3 | Phase 2: image_b64 always set. Phase 3 wraps and converts to image_ref when ≥256 KB per STORE-04. | ✓ |
| Disk-by-hash from day one | No base64 ever crosses the wire. Introduces filesystem state in Phase 2 before SQLite. | |
| Skip Screenshot in Phase 2 — emit ToolResult only | Loses visual debugging; defers to Phase 3/5. | |

**User's choice:** Base64-inline in Phase 2; disk-ref in Phase 3 (Recommended)
**Notes:** Schema carries both `image_b64: str | None` AND `image_ref: str | None` from Phase 2. Phase 2 sets only image_b64; Phase 3 conditionally swaps.

---

### Q4 — Step counter unit

| Option | Description | Selected |
|--------|-------------|----------|
| Agent loop iteration for both | 1 step = 1 model round-trip. computer-use cap=15 iterations, claude_code cap=25 iterations. User-meaningful unit. | ✓ |
| Per-tool-invocation for both | 1 step = 1 tool_use block. Tighter cost guard; fragments user's view of progress. | |
| Different unit per adapter | Iterations for computer-use, tool calls for claude_code. Honors BACKEND-06 literal text; two mental models. | |

**User's choice:** Agent loop iteration for both (Recommended)
**Notes:** **Deviation from BACKEND-06 literal text** ("25 tool calls" → "25 iterations"). REQUIREMENTS.md BACKEND-06 wording will be updated in this phase to "per-iteration step cap (25 for Claude Code, 15 for computer-use)" for mental-model consistency.

---

## Live-API test strategy

### Q1 — Test strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Tiered: hand-stubbed fakes for unit tests + opt-in live smoke | Default suite uses per-adapter fakes (deterministic, offline, $0 CI); `pytest -m live` runs against real providers gated by BYOK env vars. | ✓ |
| VCR cassettes — record once against live, replay forever | One-time recording cost; cassettes go stale on provider format drift; auth header redaction needs care. | |
| Live calls always, gated by BYOK env vars | Maximum coverage; ongoing CI cost; flaky on provider outages; broken on forks (no shared secrets). | |

**User's choice:** Tiered: fakes + opt-in live smoke (Recommended)
**Notes:** Adds `markers = ["live: hits real provider APIs (BYOK required)"]` to pytest config. Contributors can run live opt-in; CI never does (per Q3).

---

### Q2 — Cost cap mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Post-hoc running total per adapter | Each adapter maintains cost_so_far_usd from per-event token counts × per-model price; aborts when over cap. Different mechanism per adapter, same StreamError shape. | ✓ |
| Pre-flight estimate, hard refuse if predicted > cap | Refuses immediately if estimated max > cap. Doesn't catch tool-use loops blowing up cost. | |
| Provider-reported cost from final message only | Cap checked at Done time only — too late to mid-stream abort. Violates BACKEND-06 literal requirement. | |

**User's choice:** Post-hoc running total per adapter (Recommended)
**Notes:** Shared base `CostTracker` interface; per-adapter subclasses know how to extract token counts from their provider's events.

---

### Q3 — Pricing source

| Option | Description | Selected |
|--------|-------------|----------|
| Static config/pricing.json + OpenRouter /api/v1/models refresh on startup | Hand-curated for 9 OpenRouter slugs + Anthropic Opus/Sonnet; OpenRouter refresh cached 24h on disk; falls back to static on failure. | ✓ |
| Static config/pricing.json only — manual updates | Deterministic, simple; risk of price drift. | |
| Per-adapter Python pricing.py — no external config | Three pricing tables to maintain; loses single-source-of-truth. | |

**User's choice:** Static + OpenRouter refresh (Recommended)
**Notes:** Tests construct `PricingTable` from a deterministic dict (no HTTP). Initial entries cover the 9 OpenRouter-verified slugs from Phase 1's `config/model_mapping.json` + `anthropic/claude-opus-4-7` + `anthropic/claude-sonnet-4-6` + `_default` fallback.

---

### Q4 — CI scope per push

| Option | Description | Selected |
|--------|-------------|----------|
| uv sync + pytest (fakes only) + import-smoke + redaction-filter test | Zero LLM calls, zero credentials. OSS-06 import smoke + deprecated SDK absence check. | ✓ |
| All of the above + scheduled weekly live smoke against OpenRouter | Adds ~$0.50/month cron job catching wire format drift. | |
| Per-push CI runs live tests too | Maximum confidence; ~$0.50 per CI run; flaky; broken on forks. | |

**User's choice:** Per-push CI = fakes + smoke; live tests opt-in only (Recommended)
**Notes:** Live smoke is a separate optional `workflow_dispatch` + cron workflow; failures informational, not push-blocking.

---

### Q5 — Shared adapter contract test

| Option | Description | Selected |
|--------|-------------|----------|
| Shared contract suite + per-adapter specifics | `apps/api/backends/tests/test_adapter_contract.py` with 6 invariants every adapter MUST satisfy, parameterized across 3 fakes. Per-adapter dirs cover provider-specific things. | ✓ |
| Each adapter defines its own tests — no shared suite | More flexibility; less guarantee they conform to the protocol. | |
| Shared suite as a base class adapters extend | Older test pattern; pytest's parametrize is the modern replacement. | |

**User's choice:** Shared contract suite (Recommended)
**Notes:** 6 invariants: happy path, cost-cap abort, step-cap abort, cancellation, Done always lands, key-absent raises before stream() is awaited. Per-adapter tests cover OpenRouter HTTP-Referer / X-Title headers, computer-use coordinate scaling, claude_code workspace cleanup.

---

## Claude's Discretion

Areas where the user did not express a preference and the planner / researcher own the call:

- Async runtime choice (asyncio default vs anyio).
- `asyncio.CancelledError` propagation pattern (vs explicit cancel token).
- Pydantic exact lower bound (`>=2.6`).
- OpenRouter `HTTP-Referer` / `X-Title` exact values.
- claude-agent-sdk MCP tool restriction list (initial: `["Read", "Edit", "Write", "Bash", "Glob", "Grep"]`).
- `CLAUDE_ENABLE_STREAM_WATCHDOG=1` install point (`apps/api/backends/claude_code/__init__.py`).
- Per-thread workspace path template in Phase 2 (tempdir until thread_id exists in Phase 3).
- `RoutingDecision.signals` flow into adapter (surfaces on `Done.routing_signals`).
- Per-adapter CLI flag set (minimum: `--prompt`, `--max-cost-usd`, `--model`).
- Pre-flight token estimator approach (tiktoken vs char-count fallback).

## Deferred Ideas

Captured for future phases — not in Phase 2 scope:

- **Gitleaks / detect-secrets full secret scanner** — Phase 6 polish over the per-prefix grep hook.
- **Settings panel BYOK entry / per-backend toggles** — Phase 5 (UI-12).
- **Disk-by-hash blob writes for screenshots** — Phase 3 (STORE-04).
- **Pricing-table refresh from Anthropic /v1/models** — Anthropic doesn't expose a programmatic pricing API today.
- **`RoutingDecision.signals` → routing_decisions.jsonl** — Phase 3 (STORE-06).
- **Cross-backend handoff** — REQUIREMENTS v2 (ROUTER-V2-04).
- **Model fallback chain** — REQUIREMENTS v2 (ROUTER-V2-03).
- **Live retraining loop** — out of v1 milestone.
- **MCP marketplace / pluggable adapter registry** — REQUIREMENTS Out of Scope.
- **Voice / audio input, file uploads, persona marketplace** — REQUIREMENTS Out of Scope.
- **VCR cassettes for adapter tests** — alternative to D-18 fakes; defer if fakes show maintenance drift.
- **Refresh-from-OpenRouter pricing failure handling verbosity** — log-on-every-fallback vs once-per-startup.
- **Tier-router family migration to shared `text_inputs.py`** — Phase 1 D-15-style cleanup; out of Phase 2 scope.
