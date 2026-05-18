# Requirements: Prompt-Optimizer (Auto-Routing Chat Milestone)

**Defined:** 2026-05-11
**Core Value:** Every prompt routes to the LLM or agent best suited to deliver a high-quality answer, with no manual model selection from the user.

## v1 Requirements

Requirements for the auto-routing chat milestone. Each maps to a roadmap phase.

### Router Brain

- [x] **ROUTER-01**: Trained binary `agentic_intent_classifier.joblib` distinguishes conversational from agentic prompts, persisted alongside existing classifiers
- [x] **ROUTER-02**: Task-type classifier extended with an OOD/unknown sentinel class that triggers a safe-default route when confidence is low
- [x] **ROUTER-03**: Existing classifiers (task type, model router) wrapped in `CalibratedClassifierCV` so `predict_proba` is meaningful for routing decisions
- [x] **ROUTER-04**: Hand-labeled routing canary eval set (30-50 real-chat prompts) measures backend-pick accuracy, distinct from the LLMRouterBench training split
- [x] **ROUTER-05**: Pure-function `src/routing/decide(prompt, history, artifacts, settings) -> RoutingDecision` returns `{backend, model_or_agent, rationale, confidence}` and is importable without FastAPI
- [x] **ROUTER-06**: Quality-first within budget policy — when multiple backends pass quality threshold, cost is the tiebreaker
- [x] **ROUTER-07**: Existing CLI demo (`src/demo/demo_router.py`) updated to call `src/routing/decide()`; regression check confirms no degradation on benchmark eval

### Backend Adapters

- [x] **BACKEND-01**: `ChatChunk` discriminated union (`TextDelta | ToolCall | ToolResult | FileDiff | Screenshot | StreamError | Done`) is the single contract between adapters, storage, and UI
- [x] **BACKEND-02**: Common `BackendAdapter` Protocol with one method: `async def stream(prompt, history, options) -> AsyncIterator[ChatChunk]`
- [x] **BACKEND-03**: OpenRouter adapter streams chat models (Claude Sonnet, GPT-5, Gemini, DeepSeek, Qwen) using OpenAI SDK v1.40+ pointed at `https://openrouter.ai/api/v1`, with HTTP-Referer / X-Title attribution headers
- [x] **BACKEND-04**: Claude Code adapter uses `claude-agent-sdk 0.1.80+` (NOT deprecated `claude-code-sdk`); streams tool calls + file diffs + final summary as `ChatChunk`s
- [x] **BACKEND-05**: Computer-use adapter uses `anthropic 0.40+` with `computer_20251124` tool + `computer-use-2025-11-24` beta header on Claude Opus 4.7 or Sonnet 4.6; streams screenshots + action narration
- [x] **BACKEND-06**: Each adapter enforces a hard per-turn USD cap (default $0.50) and per-iteration step cap (25 for Claude Code, 15 for computer-use) at the adapter boundary
- [x] **BACKEND-07**: Mid-stream cancellation — browser tab close / stop button propagates to upstream provider via `query.interrupt()` (Claude Code), aborted HTTP request (OpenRouter), or equivalent
- [x] **BACKEND-08**: Claude Code runs in a per-thread ephemeral workspace by default; opt-in flag required to point at user's repo `cwd`
- [x] **BACKEND-09**: `CLAUDE_ENABLE_STREAM_WATCHDOG=1` set to prevent the known Claude Code SDK stream-stall hang

### FastAPI Service Layer

- [x] **API-01**: FastAPI process loads all joblib artifacts once at `lifespan` startup; never reloaded per request
- [x] **API-02**: `POST /threads/{thread_id}/turn` runs routing decision → dispatches adapter → streams `ChatChunk`s back via `fastapi.sse.EventSourceResponse`
- [x] **API-03**: Thread CRUD endpoints (`POST /threads`, `GET /threads`, `GET /threads/{id}`, `PATCH /threads/{id}`, `DELETE /threads/{id}`)
- [x] **API-04**: BYOK settings endpoint accepts per-backend keys; keys held in-process only, never persisted to SQLite or logs
- [x] **API-05**: SSE stream emits a heartbeat every 15 seconds during long agentic runs to defeat intermediate proxy timeouts
- [x] **API-06**: Client-disconnect detection cancels in-flight upstream provider calls (`request.is_disconnected()` polling)
- [x] **API-07**: Synchronous sklearn `predict` / `predict_proba` calls are wrapped in `asyncio.to_thread` (or equivalent thread-pool offload such as `starlette.concurrency.run_in_threadpool`) when invoked from async handlers
- [x] **API-08**: Integration tests use `httpx AsyncClient + ASGITransport` (NOT `TestClient`) to exercise streaming end-to-end

### Chat UI

- [ ] **UI-01**: Multi-turn chat input + scrolling message list using Next.js 15.2 + React 19 + AI SDK v5 (`@ai-sdk/react@>=2`) + `@assistant-ui/react@>=0.10`
- [ ] **UI-02**: Thread sidebar — create, select, rename, delete; persists across browser sessions
- [ ] **UI-03**: Streaming markdown rendering with code-block syntax highlighting that is streaming-safe (highlight applied on closing fence, no per-token re-highlight flicker)
- [ ] **UI-04**: Routing chip + one-line rationale on every assistant message (e.g. "Routed to Claude Code · build-and-edit task"); always visible, never collapsed
- [ ] **UI-05**: Per-turn backend override via slash command (`/openrouter`, `/code`, `/computer`) and a dropdown next to the input
- [ ] **UI-06**: Stop / cancel button mid-stream preserves the partial response already received
- [ ] **UI-07**: Per-turn cost (USD) + latency (ms) + token count displayed alongside each assistant message
- [ ] **UI-08**: `ChatBubble` renders OpenRouter responses — streamed markdown, copy-as-markdown, regenerate
- [ ] **UI-09**: `CodeBubble` renders Claude Code output — collapsible tool-call chips, inline red/green file-diff renderer, final summary
- [ ] **UI-10**: `ComputerUseBubble` renders computer-use output — screenshot strip, action narration, "still working… 0:42" indicator
- [ ] **UI-11**: Backend availability status — green/red dot per backend at startup based on key presence + model-list ping
- [ ] **UI-12**: Settings panel — BYOK key entry per provider, backend enable/disable toggles, computer-use opt-in switch
- [ ] **UI-13**: First-run modal + missing-key setup screen guide a brand-new user from clone to first successful turn
- [ ] **UI-14**: Thread auto-renames from the first user message (cheap-model bypass route; never calls the main router)
- [ ] **UI-15**: "Wrong route" thumbs-down on any assistant message appends a row to a local JSONL routing-feedback log
- [ ] **UI-16**: Empty-state shows three sample prompts that exercise the three different backends
- [ ] **UI-17**: Next.js route handler proxies to FastAPI server-side; BYOK keys never travel over the browser ↔ FastAPI wire directly

### Persistent Storage

- [x] **STORE-01**: SQLite via `aiosqlite 0.20+` with `PRAGMA journal_mode=WAL; synchronous=NORMAL; busy_timeout=5000` on first connect
- [x] **STORE-02**: Schema: `threads(id, title, created_at, updated_at)`, `messages(id, thread_id, role, content_blocks JSON, backend_used, model_used, cost_usd, latency_ms, tokens_in, tokens_out, created_at)`, `routing_decisions(id, message_id, task_type, task_confidence, agentic_intent, agentic_confidence, predicted_model, rationale, decided_at)`
- [x] **STORE-03**: Schema migrations managed from day one (Alembic or SQLModel-native); never break existing user DBs across releases
- [x] **STORE-04**: Large blobs (screenshots ≥256 KB, large diffs) written to disk and referenced by content hash from the DB row
- [x] **STORE-05**: Assistant message persisted once on `Done` chunk (buffered in memory during stream); no per-chunk writes
- [x] **STORE-06**: Every routing decision appended to a local `.planning/data/routing_decisions.jsonl` log file alongside the DB row, for offline analysis

### Security & Cost Guards

- [x] **SECURE-01**: Python logging configured with a redaction filter that strips `sk-…`, `sk-ant-…`, `Bearer \S+` from any log record before it reaches a handler
- [x] **SECURE-02**: Pre-commit hook greps staged content for `sk-` and `sk-ant-` prefixes and blocks the commit if found
- [x] **SECURE-03**: Root `.gitignore` excludes `.env`, `*.db`, `*.db-journal`, `*.db-wal`, `__pycache__/`, `.venv/`, `chat.db` from the first commit that touches key handling
- [x] **SECURE-04**: BYOK keys live only in process memory + an OS keyring entry (via `keyring`) if the user opts in; never written to SQLite, JSON, or log files
- [x] **SECURE-05**: Computer-use is OFF by default; setting `COMPUTER_USE_OPT_IN=1` (env or settings panel) is required to enable it
- [ ] **SECURE-06**: README documents the computer-use threat model (prompt injection from visited pages, runaway cost, workspace exfiltration) and the per-thread ephemeral workspace defaults

### Open-Source Distribution

- [x] **OSS-01**: Root `pyproject.toml` + `uv.lock` replace the missing requirements lockfile; `uv sync` produces a working environment
- [ ] **OSS-02**: `make setup` (or `scripts/setup.sh`) runs `git lfs pull`, downloads NLTK `punkt_tab`, pre-fetches the SentenceTransformer model, and copies `.env.example` → `.env` if absent
- [ ] **OSS-03**: `.env.example` enumerates every key the app reads with one-line comments
- [ ] **OSS-04**: README rewritten — three golden-path demo prompts ("build me a finance app" → Claude Code; "what's the capital of France?" → cheap chat model; "open this URL and check the price" → computer-use), screenshots, quickstart that works from a clean clone
- [x] **OSS-05**: CORS configured explicitly between Next.js dev server and FastAPI; no `allow_origins=["*"]`
- [x] **OSS-06**: CI smoke test asserts `from claude_agent_sdk import ClaudeAgentOptions` to catch any regression to the deprecated `claude-code-sdk`
- [ ] **OSS-07**: Playwright E2E test exercises the full SSE pipe (browser → Next.js → FastAPI → OpenRouter → SSE back) to catch AI SDK v5 message-format drift
- [ ] **OSS-08**: Fresh-clone manual UAT — a contributor on a clean machine reaches the first streamed response in under 10 minutes following only the README

## v2 Requirements

Deferred to future release. Tracked but not in this milestone's roadmap.

### Router Brain (v2)

- **ROUTER-V2-01**: Expandable "why this route" panel showing full classifier confidence breakdown
- **ROUTER-V2-02**: Live retraining loop — periodically retrain agentic-intent classifier from accumulated user feedback (currently out of scope per PROJECT.md)
- **ROUTER-V2-03**: Model fallback chain — auto-retry within the same tier on provider error
- **ROUTER-V2-04**: Cross-backend handoff — preserve agent tool-call state when switching backends mid-thread (v1 flattens to text)

### Chat UI (v2)

- **UI-V2-01**: Export thread as `.md` file
- **UI-V2-02**: Export routing-decision log to CSV via UI button (raw JSONL is already in v1)
- **UI-V2-03**: Side-by-side backend comparison on the same prompt
- **UI-V2-04**: A/B routing strategy test mode (dev only)
- **UI-V2-05**: Auto-summarize long threads to manage context window

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| User accounts / auth | Open-source BYOK — each user runs their own instance |
| Billing / payments | No hosted version, so no monetization layer |
| Hosted multi-tenant SaaS | Repo ships a runnable open-source app, not a service |
| Mobile / native apps | Web-first; mobile is post-v1 if ever |
| Fine-tuning the generative LLMs | We route to existing third-party models; only train small routing heads |
| Live retraining from chat-UI traffic (v1) | All training stays offline against `data_processed/`; v2 candidate only |
| Server-side analytics / telemetry on by default | Phoning home is a reputation-killer for an open-source product |
| Public chat sharing | Privacy by default; not aligned with local-only stance |
| Persona / system-prompt marketplace | Anti-pattern for an auto-router; pre-baked personas dilute the routing thesis |
| Cost-aware target as primary objective | Core Value is quality-first; cost is tiebreaker only |
| Voice / audio input | Out of scope for v1; possible v2+ |
| File uploads / attachments | Out of scope for v1; complicates backend adapter contract |
| MCP marketplace | Out of scope for v1; adapters are hardcoded to three known backends |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| ROUTER-01 | Phase 1 | Complete |
| ROUTER-02 | Phase 1 | Complete |
| ROUTER-03 | Phase 1 | Complete |
| ROUTER-04 | Phase 1 | Complete |
| ROUTER-05 | Phase 1 | Complete |
| ROUTER-06 | Phase 1 | Complete |
| ROUTER-07 | Phase 1 | Complete |
| BACKEND-01 | Phase 2 | Complete |
| BACKEND-02 | Phase 2 | Complete |
| BACKEND-03 | Phase 2 | Complete |
| BACKEND-04 | Phase 2 | Complete |
| BACKEND-05 | Phase 2 | Complete |
| BACKEND-06 | Phase 2 | Complete |
| BACKEND-07 | Phase 2 | Complete |
| BACKEND-08 | Phase 2 | Complete |
| BACKEND-09 | Phase 2 | Complete |
| API-01 | Phase 3 | Complete |
| API-02 | Phase 3 | Complete |
| API-03 | Phase 3 | Complete |
| API-04 | Phase 3 | Complete |
| API-05 | Phase 3 | Complete |
| API-06 | Phase 3 | Complete |
| API-07 | Phase 3 | Complete |
| API-08 | Phase 3 | Complete |
| UI-01 | Phase 4 | Pending |
| UI-02 | Phase 5 | Pending |
| UI-03 | Phase 4 | Pending |
| UI-04 | Phase 4 | Pending |
| UI-05 | Phase 5 | Pending |
| UI-06 | Phase 4 | Pending |
| UI-07 | Phase 4 | Pending |
| UI-08 | Phase 4 | Pending |
| UI-09 | Phase 5 | Pending |
| UI-10 | Phase 5 | Pending |
| UI-11 | Phase 5 | Pending |
| UI-12 | Phase 5 | Pending |
| UI-13 | Phase 4 | Pending |
| UI-14 | Phase 5 | Pending |
| UI-15 | Phase 5 | Pending |
| UI-16 | Phase 5 | Pending |
| UI-17 | Phase 4 | Pending |
| STORE-01 | Phase 3 | Complete |
| STORE-02 | Phase 3 | Complete |
| STORE-03 | Phase 3 | Complete |
| STORE-04 | Phase 3 | Complete |
| STORE-05 | Phase 3 | Complete |
| STORE-06 | Phase 3 | Complete |
| SECURE-01 | Phase 2 | Complete |
| SECURE-02 | Phase 2 | Complete |
| SECURE-03 | Phase 1 | Complete |
| SECURE-04 | Phase 2 | Complete |
| SECURE-05 | Phase 2 | Complete |
| SECURE-06 | Phase 6 | Pending |
| OSS-01 | Phase 1 | Complete |
| OSS-02 | Phase 6 | Pending |
| OSS-03 | Phase 6 | Pending |
| OSS-04 | Phase 6 | Pending |
| OSS-05 | Phase 3 | Complete |
| OSS-06 | Phase 2 | Complete |
| OSS-07 | Phase 6 | Pending |
| OSS-08 | Phase 6 | Pending |

**Coverage:**
- v1 requirements: 61 total
- Mapped to phases: 61 / Unmapped: 0 ✓

---
*Requirements defined: 2026-05-11*
*Last updated: 2026-05-11 after roadmap creation (traceability filled in)*
