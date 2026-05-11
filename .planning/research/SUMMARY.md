# Project Research Summary

**Project:** Prompt-Optimizer — Auto-Routing Chat Milestone
**Domain:** Brownfield open-source BYOK multi-turn chat with classifier-based prompt routing (OpenRouter chat / Claude Code SDK / Anthropic computer-use) over an existing scikit-learn offline pipeline
**Researched:** 2026-05-11
**Confidence:** HIGH

## Executive Summary

This is a brownfield "subsequent milestone" on top of a working offline scikit-learn routing pipeline (task-type classifier + two-stage model router). The new work layers a FastAPI backend, a Next.js 15 chat UI, three live LLM/agent backends, and a new agentic-intent binary classifier onto existing `src/` code without touching anything that already works. The architectural keystone decision — and the one that must be made before any other code is written — is the **discriminated-union `ChatChunk` taxonomy** (`text_delta`, `tool_call`, `screenshot`, `file_diff`, `error`, `done`) defined in `apps/api/backends/chunks.py`. Every other component (adapters, storage, UI renderers) is a consumer of that shape. Equally important is keeping the routing brain in a **pure-function module at `src/routing/`** (not inside FastAPI), so the offline evaluation harness can replay end-to-end routing decisions on benchmark data without spinning up a server.

The single most important quality risk is **benchmark distribution drift**. The existing routers were trained on LLMRouterBench and already achieve only ~0.21 Stage-2 exact-model accuracy on that test split. Live chat prompts — short, lowercase, fragmentary, multi-turn — are dramatically further out of distribution. Without an OOD/unknown class, calibration validation, and a hand-labeled canary prompt set, the router will produce confidently wrong routes on day one. This must be addressed in the very first phase, before any UI exists, because the routing brain is the product's core value proposition.

The "must-fix-or-it's-embarrassing" pitfalls are: (1) cost runaway with no per-turn / per-day spend cap on agentic backends, (2) BYOK key leakage through casual `print()` or request logs, (3) computer-use prompt injection from visited webpages if the feature is enabled by default, and (4) fresh-clone quickstart breakage from git-LFS pointers and unresolved NLTK downloads. The recommended mitigation for all four is early, not deferred: spend caps and logger-redaction filters in the backend phase, computer-use disabled by default from the first commit that touches it, and a working `make setup` script before the first public commit.

## Key Findings

### Recommended Stack

The new additions layer cleanly onto the existing Python ML stack. On the Python side: **uv 0.5+** replaces the missing requirements lockfile (closes a HIGH concern from CONCERNS.md), **FastAPI 0.135+** provides native `EventSourceResponse` from `fastapi.sse` without a third-party shim, and **SQLModel 0.0.22+ with aiosqlite + WAL mode** handles persistence. On the JS side: **Next.js 15.2 + React 19**, **AI SDK v5** using the UI Message Stream Protocol (`x-vercel-ai-ui-message-stream: v1` header), and **assistant-ui `@assistant-ui/react@>=0.10`** for thread/composer primitives. The three LLM/agent backends use: **OpenAI SDK v1.40+ pointed at OpenRouter**, **`claude-agent-sdk 0.1.80+`** (the March 2026 rename of the deprecated `claude-code-sdk`), and **`anthropic 0.40+`** with `computer_20251124` tool + `computer-use-2025-11-24` beta header on Claude Opus 4.7 or Sonnet 4.6.

**Hard version and naming pins (planner must enforce):**

- `uv 0.5+` — Python package manager; replaces missing lockfile
- `FastAPI 0.135+` — first version with native `fastapi.sse.EventSourceResponse`; pydantic v2 required
- `SQLModel 0.0.22+` + `aiosqlite 0.20+` — async SQLite; WAL mode on first connect
- `claude-agent-sdk 0.1.80+` (NOT `claude-code-sdk`) — `ClaudeAgentOptions` (NOT `ClaudeCodeOptions`)
- `anthropic 0.40+` with `computer_20251124` + `computer-use-2025-11-24` beta header — Claude Opus 4.7 or Sonnet 4.6 only
- `openai 1.40+` pointed at `https://openrouter.ai/api/v1` — more battle-tested than native `openrouter` SDK
- `ai@>=5` + `@ai-sdk/react@>=2` — v4 is incompatible; use UI Message Stream Protocol not old Data Stream Protocol
- `Next.js 15.2.x` + React 19 — stay on 15, not 16; 16 requires async `params`/`searchParams` migration
- `@assistant-ui/react@>=0.10` + `@assistant-ui/react-ai-sdk` — `useChatRuntime` integrates with `useChat`
- `pytest 8.4+` + `pytest-anyio 0.4+` + `httpx AsyncClient + ASGITransport` — do NOT use `TestClient` for streaming
- `Vitest 2.x` + `Playwright 1.45+` — Vitest replaces Jest; Playwright replaces Cypress
- Python 3.11 target (minimum 3.10)

### Expected Features

**Must have (table stakes — v1):**

The routing chip and one-line rationale are on the critical path for nearly every other feature. Without the visible "Routed to X because Y" chip, the core value proposition is invisible — this is the #1 failure mode of ChatGPT's auto-router and the explicit design mistake to avoid.

- Token-by-token streaming on all three backends (not just OpenRouter)
- Stop button mid-stream with partial-response preservation (per-backend cancellation semantics differ)
- "Routed to X" chip on every assistant message — always visible, never collapsed
- One-line rationale next to the chip (e.g., "Build-and-edit task → Claude Code SDK")
- Per-turn backend override (slash command or dropdown) — required for trust when routing is wrong
- Multi-turn persistent threads + sidebar
- Markdown + code block syntax highlighting (streaming-safe: defer highlighting until closing fence)
- Backend availability check at startup with green/red status per backend
- BYOK key entry for OpenRouter and Anthropic
- Per-turn latency + token count display
- Local JSONL log of every routing decision
- "Wrong route" thumbs-down feedback button
- Thread auto-rename from first message (async, bypasses the router)
- Three golden-path demo prompts in README
- First-run modal + missing-key setup screen
- Computer-use disabled by default — explicit opt-in required

**Should have (differentiators — v1.x):**

- Expandable "why this route" with classifier confidence breakdown
- Inline file-diff renderer for Claude Code (rich red/green; v1 minimum is a fenced `diff` block)
- Model fallback on error (auto-retry in same tier)
- Cost-per-turn display
- Export thread as `.md`
- Export routing-decision log to CSV

**Defer (v2+):** Side-by-side backend comparison, A/B routing strategy test, auto-summarize long threads, analytics dashboard, voice/file uploads, MCP marketplace, personas

**Never build (anti-features):** User accounts, server-side telemetry on by default, hosted SaaS, server-stored API keys, live retraining loop, public chat sharing, persona marketplace

### Architecture Approach

The entire architecture hangs on two early decisions: the **`ChatChunk` discriminated union** (defines the stream type all adapters emit and the UI consumes) and the **`src/routing/` pure-function module** (lives under `src/`, not `apps/api/`, so the offline eval harness works without FastAPI). The `apps/api/turn_service.py` orchestrator joins these: calls `src/routing/decide()`, resolves an adapter, pipes `AsyncIterator[ChatChunk]` into an `EventSourceResponse`, persists on completion. The Next.js route handler proxies to FastAPI server-side so BYOK keys never touch the browser direct wire.

**Major components:**

1. **`src/routing/`** — pure-function pipeline: `classify_task` → `classify_agentic` → `predict_model` → `apply_quality_first_policy` → `RoutingDecision`; no FastAPI dependency; used by both live server and offline eval
2. **`apps/api/backends/chunks.py`** — `ChatChunk` discriminated union (`TextDelta | ToolCall | Screenshot | FileDiff | StreamError | Done`); the contract between adapters, storage, and UI
3. **`apps/api/backends/{openrouter,claude_code,computer_use}.py`** — each implements `BackendAdapter` Protocol with one `async def stream(...) -> AsyncIterator[ChatChunk]`
4. **`apps/api/turn_service.py`** — one-turn orchestrator: persist user message → decide → dispatch adapter → stream chunks → persist on done
5. **`apps/api/storage/sqlite.py`** — `aiosqlite` CRUD with WAL + busy_timeout; blob-by-reference for screenshots; `routing_decisions` as a separate table
6. **`apps/web/app/api/chat/route.ts`** — Next.js server-side proxy; browser never calls FastAPI directly
7. **`apps/web/components/BackendBubble/{ChatBubble,CodeBubble,ComputerUseBubble}.tsx`** — per-backend renderers dispatched by `chunk.type`; same outer container for cross-backend consistency
8. **`src/agentic_intent/`** — new binary classifier trainer (embedding + LogisticRegression); output: `models/agentic_intent_classifier.joblib`

**Key cross-cutting rules:**
- `src/routing/` never imports from `apps/api/` (one-way dependency)
- No joblib loading inside request handlers (load once in FastAPI `lifespan`)
- No `async def` handler for synchronous sklearn calls without `run_in_threadpool`
- Screenshots and large diffs stored on disk as blobs, referenced by hash from DB

### Critical Pitfalls

1. **Benchmark drift cratering on real chat prompts** — ~0.21 Stage-2 accuracy on benchmark; live chat is even further OOD. Add an OOD/unknown class, apply `CalibratedClassifierCV`, maintain a 30-50 prompt canary set, define an uncertainty threshold (max-class probability < 0.45) that triggers fallback. Do this in Phase 1 before any UI.

2. **Cost runaway on agentic backends** — a single "fix all the bugs" prompt can loop for hundreds of tool calls. Enforce a hard per-turn USD cap (default $0.50) and per-iteration cap (25 for Claude Code, 15 for computer-use) at the adapter layer. Cancel upstream requests when the browser tab closes. Surface running cost live in the UI.

3. **BYOK key leakage through logging** — the repo has 354 `print()` calls. Install a logger redaction filter (strips `sk-`, `sk-ant-`, `Bearer \S+`) before any log handler; enforce via pre-commit hook. Keys never touch SQLite. Root `.gitignore` must include `.env` from the first commit that touches key handling.

4. **Computer-use prompt injection from visited webpages** — an autonomous browser agent visiting attacker-controlled pages can exfiltrate files or run shell commands. Computer-use disabled by default, explicit `COMPUTER_USE_OPT_IN=1` env flag required; per-turn cost + step cap enforced at the call site; threat model documented in README.

5. **Fresh-clone quickstart breakage** — git-LFS CSV pointers parse as junk, `sentence-transformers` downloads ~90 MB on first import, `nltk.download` fails silently offline, no `pyproject.toml` exists yet. A `make setup` script that runs `git lfs pull`, pre-fetches caches, creates `.env` from `.env.example`; README tested by a first-time contributor on a clean machine.

6. **SDK rename trap** — `claude-code-sdk` is deprecated March 2026; the correct package is `claude-agent-sdk`; the correct type is `ClaudeAgentOptions`. Any tutorial predating March 2026 is broken. Add a CI smoke test that asserts on the import path.

7. **SQLite write contention** — default `journal_mode=DELETE` + `busy_timeout=0` produces "database is locked" under any concurrency. On first connect: `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=5000;`. Buffer full assistant message in memory, persist once on `Done`, never per-chunk.

## Implications for Roadmap

Suggested phase structure (6 phases, A through F):

### Phase A: Router Brain (Foundation)

**Rationale:** Everything depends on `src/routing/` and the three classifier joblibs. `RoutingDecision` defines the API contract for the turn service, the storage schema for `routing_decisions`, and the offline eval. No phase can be merged producing or consuming routing output until `src/routing/` exists.

**Delivers:** `src/routing/decide(prompt, history, artifacts, settings) -> RoutingDecision` callable from CLI demo and FastAPI. Canary prompt set with backend accuracy and tier accuracy metrics. `agentic_intent_classifier.joblib`. `routing_decision_eval.csv` distinct from classifier training split. `CalibratedClassifierCV` on existing classifiers. OOD/unknown sentinel class.

**Avoids:** Pitfalls 1, 2, 3, 4, 26 (benchmark drift, task-type ≠ backend, overconfidence, hardcoded rules, missing routing-quality eval)

**Parallelizable:** Agentic-intent dataset labeling + routing module scaffolding; calibration work after trainers exist

**Research flag:** MEDIUM — OOD class definition and confidence threshold values are judgment calls; recommend a half-day spike during planning.

### Phase B: Backend Adapters

**Rationale:** Once `RoutingDecision` and `ChatChunk` are fixed, all three adapters are independent and can be built in parallel. Adapters are the gate to any live streaming behavior.

**Delivers:** Three independently testable adapters emitting `AsyncIterator[ChatChunk]`. Per-turn USD cap and per-iteration cap inside each adapter. BYOK key reading. OpenRouter model-list startup validation. Per-thread ephemeral workspace for Claude Code. Computer-use opt-in gating. Logger redaction filter. `CLAUDE_ENABLE_STREAM_WATCHDOG=1` set.

**Avoids:** Pitfalls 5, 6, 7, 8, 9, 10, 16, 17, 18 (SDK rename, timeout hangs, working-dir collisions, computer-use default-on, cost runaway, key leakage, OpenRouter SSE types, stale slugs, missing attribution headers)

**Parallelizable:** All three adapters after `chunks.py` lands. OpenRouter first; Claude Code and computer-use in parallel.

**Research flag:** LOW for OpenRouter. MEDIUM for Claude Code SDK. HIGH for computer-use — recommend a thin spike before planning the adapter.

### Phase C: FastAPI Service Layer

**Rationale:** Joins Phase A (routing brain) and Phase B (adapters) into the first HTTP-exposed surface. First time anything streams over HTTP.

**Delivers:** Running `uvicorn` process: `POST /threads/{id}/turn` → routing → adapter dispatch → SSE → SQLite persistence. Thread CRUD. BYOK settings endpoint. Integration tests via `httpx AsyncClient + ASGITransport`. SQLite WAL + busy_timeout. Schema migrations from day one. Blob-by-reference for screenshots. Cancel endpoint. 15-second SSE heartbeats during agent runs. Client-disconnect detection.

**Avoids:** Pitfalls 11, 12, 13, 14, 15, 19 (multi-worker memory, blocking sklearn in async, SQLite contention, schema migration breakage, DB bloat, context lost on backend switch)

**Research flag:** LOW — well-documented patterns; only non-standard element is heartbeat + disconnect-cancel plumbing.

### Phase D: Minimal Chat UI (Single Backend)

**Rationale:** Validates the SSE pipe end-to-end (browser → Next.js → FastAPI → OpenRouter → SSE back) with one backend before adding complexity.

**Delivers:** Running `next dev` app with single chat input, streaming OpenRouter responses with routing chip and rationale, streaming-safe markdown + code blocks, stop button, copy message, SSE pipe validated in dev and prod.

**Avoids:** SSE buffered by Next.js proxy (validate early), code block flickering (Pitfall 22), hydration mismatch on timestamps (Pitfall 24), auto-scroll snap (Pitfall 23), routing chip layout shift.

**Research flag:** LOW for SSE plumbing. MEDIUM for AI SDK v5 → FastAPI message format; add Playwright E2E test immediately.

### Phase E: Feature-Complete UI

**Rationale:** Phase D proves the pipe. Phase E adds all three backends, the full thread UX, settings, and routing UX.

**Delivers:** `CodeBubble` with collapsible tool-call chips and file-diff display. `ComputerUseBubble` with screenshot strip. Thread sidebar. Settings panel. Per-turn backend override (dropdown + slash commands). Pin-to-backend toggle. "Wrong route" feedback button. Local JSONL routing log. Backend availability check. Empty-state sample prompts. Auto-rename threads. First-run modal. Abort wired to `query.interrupt()` for all three backends. Per-turn latency + token display. "Computer-use is working… 0:42" indicator.

**Avoids:** Pitfalls 6, 7, 8, 20, 21, 22 (timeout hangs, workspace collision, computer-use silent failures, chip too hidden/prominent, no override, code block flicker)

**Parallelizable:** `CodeBubble`, `ComputerUseBubble`, `ThreadSidebar`, `SettingsPanel`, `RoutingChip` are independent React components once TS chunk types are mirrored.

**Research flag:** MEDIUM — `CodeBubble` streaming state machine (inside tool call vs. between tool calls vs. final summary) is non-trivial; recommend a half-day design session before implementation.

### Phase F: Hardening and Open-Source Release

**Rationale:** "Will this actually work for a first-time contributor on a fresh machine?" The golden-path README, setup script, security audit, and packaging all land here.

**Delivers:** `make setup` script (git lfs pull, NLTK, HuggingFace cache warm, `.env` from example). README rewrite with three golden-path demo prompts + screenshots. `.gitignore` with `.env`, `__pycache__`, `chat.db`. CI grep blocking `sk-`, `sk-ant-`. CORS configured explicitly. Computer-use threat model documented. Workspace isolation documented. Fresh-clone test by a new contributor.

**Avoids:** Pitfall 25 (fresh-clone breakage), Pitfall 10 (key leakage through missing gitignore), CORS misconfiguration, pickle trust model gap.

**Research flag:** LOW — engineering polish, no new research territory.

### Phase Ordering Rationale

- Phase A must come first — `RoutingDecision` is the contract everything else depends on
- `ChatChunk` can land at the top of Phase B or end of Phase A — recommend it as the first deliverable of Phase B since it belongs to the dispatch layer conceptually
- Phases B and C are sequential but work within each is highly parallelizable
- Phase D before Phase E — validates SSE with one backend before adding two more, dramatically reducing debugging surface
- Phase F is last but logger redaction filter and `.gitignore` should be partially done in earlier phases — do not defer all security hygiene to the final phase

### Research Flags

**Needs deeper research or planning spike:**
- **Phase A:** OOD class definition and confidence threshold values — judgment calls requiring a half-day planning spike
- **Phase B (computer-use):** Coordinate scaling, screenshot-to-`tool_result` loop, VNC-to-FastAPI translation — recommend a thin implementation spike before planning the adapter in detail
- **Phase D/E:** AI SDK v5 → FastAPI UI Message Stream Protocol stability — add a Playwright E2E test immediately in Phase D to catch protocol drift automatically
- **Phase E:** `CodeBubble` streaming state machine — half-day design session before implementation

**Standard patterns (skip additional research):**
- **Phase B (OpenRouter):** Well-documented; OpenAI SDK v1.x + SSE parsing is established
- **Phase C:** FastAPI streaming + SQLite WAL patterns are well-documented
- **Phase F:** Engineering polish; no research needed

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Core technologies verified against official 2026 docs. One MEDIUM item: AI SDK v5 → FastAPI message format is recent; needs an E2E test to catch protocol drift. |
| Features | MEDIUM-HIGH | Table stakes and anti-features well-established from competitor analysis. Routing-specific UX (chip design, override, multi-turn momentum) is an emerging design space; recommendations are opinionated hypotheses to validate with early users. |
| Architecture | HIGH | Component shape, data flow, and build order drawn from existing repo conventions + verified FastAPI/Next.js streaming patterns. MEDIUM exception: computer-use adapter shape warrants a thin spike before detailed planning. |
| Pitfalls | HIGH | Anthropic and OpenRouter docs verified; sklearn calibration behavior verified; SDK rename confirmed against 2026 migration guide. All pitfalls are project-specific. |

**Overall confidence:** HIGH

### Gaps to Address

- **OOD/unknown task-type class design:** Research recommends it but does not specify exact training data composition (synthetic vs. real noisy prompts). Resolve during Phase A planning before training begins.
- **Confidence threshold values:** The 0.45 uncertainty threshold is a starting point; must be empirically validated against the canary prompt set after calibrated classifiers are trained. Plan a calibration validation step as a Phase A exit criterion.
- **Computer-use adapter implementation scope:** Coordinate scaling for Opus 4.7 vs. older models, screenshot-to-`tool_result` loop, and VNC-to-FastAPI action translation need a short implementation spike to size correctly.
- **AI SDK v5 UI Message Stream Protocol stability:** Add a Playwright E2E test in Phase D that exercises the full SSE pipe and catches protocol drift automatically.
- **Multi-turn context handoff between backends:** The v1 decision (text-flatten prior agent turns for the next backend) is pragmatic but lossy. Plan a half-day design session in Phase C to define exactly what the per-backend `format_history()` functions produce.

## Sources

### Primary (HIGH confidence)
- Anthropic computer-use tool docs (2026) — `computer_20251124`, beta header, model support matrix
- Claude Agent SDK Python GitHub + PyPI — package name, version, `ClaudeAgentOptions`, streaming pattern, deprecation of `claude-code-sdk`
- Claude Agent SDK migration guide — March 2026 rename + `claude_code` preset behavior change
- AI SDK UI Stream Protocol (ai-sdk.dev) — `x-vercel-ai-ui-message-stream: v1` header + event shapes
- FastAPI 0.135 release notes — native `fastapi.sse.EventSourceResponse`
- OpenRouter OpenAI SDK integration docs — `base_url` + attribution headers + BYOK auth pattern
- Next.js 15 and 16 release notes — version boundary, migration cost
- Existing repo `.planning/codebase/` — primary source for brownfield constraints and what reuses what

### Secondary (MEDIUM confidence)
- uv vs. poetry vs. pip-tools 2026 comparison (multiple community sources) — uv as consensus default
- assistant-ui community review 2026 — dominant chat-UI primitive lib
- Competitor analysis: Perplexity Comet, OpenRouter Chat, Poe, ChatGPT auto-router, Cursor, Claude.ai
- vllm-project/semantic-router#1458 — multi-turn routing momentum problem
- Cursor forum expand/collapse agent responses — confirms collapsible-by-default for agentic UI
- LiteLLM fallback + retry patterns — model fallback chain design

### Tertiary (LOW confidence)
- OpenRouter native `openrouter` Python SDK — not widely battle-tested; keeping OpenAI-SDK-as-primary
- `anthropic-experimental/sandbox-runtime` — future-facing lighter-weight computer-use sandbox; not production-ready as of May 2026

---
*Research completed: 2026-05-11*
*Ready for roadmap: yes*
