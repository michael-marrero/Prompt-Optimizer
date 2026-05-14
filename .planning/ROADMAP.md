# Roadmap: Prompt-Optimizer (Auto-Routing Chat Milestone)

## Overview

Six phases stand up a production-quality auto-routing chat app on top of the existing offline scikit-learn pipeline. Phase 1 hardens the routing brain into a framework-free `src/routing/decide()` module (calibrated classifiers, OOD class, agentic-intent head, hand-labeled canary eval). Phase 2 builds the three live backend adapters (OpenRouter / Claude Code / computer-use) behind a single `ChatChunk` discriminated union, with cost caps, key-redaction, and computer-use opt-in baked in from the first commit. Phase 3 fuses brain + adapters behind a FastAPI service with SSE streaming and SQLite persistence. Phase 4 ships a minimal Next.js chat UI exercising one backend end-to-end so the SSE pipe is proven before complexity. Phase 5 brings the UI to feature-complete (all three backends, sidebar, settings, override, routing chip). Phase 6 closes with the open-source release: `make setup`, README golden path, fresh-clone UAT, threat-model docs, Playwright E2E.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Router Brain Foundation** - Pure `src/routing/decide()` with calibrated classifiers, agentic-intent head, OOD sentinel, and a hand-labeled routing canary eval
- [ ] **Phase 2: Backend Adapters & ChatChunk Contract** - Three backend adapters (OpenRouter, Claude Code, computer-use) emitting `ChatChunk` streams with cost caps and key-redaction baked in
- [ ] **Phase 3: FastAPI Service & Persistent Storage** - HTTP/SSE service joining router + adapters, with `aiosqlite` thread/message/routing-decision persistence
- [ ] **Phase 4: Minimal Chat UI (OpenRouter Backend)** - Next.js single-backend chat that proves the browser → Next → FastAPI → OpenRouter SSE pipe end-to-end
- [ ] **Phase 5: Feature-Complete Chat UI** - Sidebar, settings, override, routing chip, code/computer-use bubbles, status dots, feedback log — all three backends live
- [ ] **Phase 6: Open-Source Release Hardening** - `make setup`, README golden path, fresh-clone UAT, Playwright E2E, computer-use threat model, packaging polish

## Phase Details

### Phase 1: Router Brain Foundation
**Goal**: A framework-free `src/routing/decide(prompt, history, artifacts, settings) -> RoutingDecision` is callable from the existing CLI demo and from any future FastAPI process, backed by calibrated classifiers, an agentic-intent head, an OOD sentinel, and a hand-labeled canary eval distinct from LLMRouterBench.
**Depends on**: Nothing (first phase)
**Requirements**: ROUTER-01, ROUTER-02, ROUTER-03, ROUTER-04, ROUTER-05, ROUTER-06, ROUTER-07, OSS-01, SECURE-03
**Success Criteria** (what must be TRUE):
  1. `python -m src.routing.decide "<prompt>"` (or the updated `src/demo/demo_router.py`) prints a `RoutingDecision` JSON containing `{backend, model_or_agent, rationale, confidence}` for any prompt, with no FastAPI dependency in the import graph.
  2. `models/agentic_intent_classifier.joblib` exists, loads via the same artifact-dict shape as the existing classifiers, and a held-out test reports precision/recall on agentic vs. conversational prompts.
  3. The hand-labeled `routing_decision_eval.csv` (30-50 prompts with `expected_backend`) runs in CI; `python -m src.evaluation.evaluate_routing` prints backend-pick accuracy and reliability-diagram ECE for each calibrated classifier; existing benchmark eval shows no regression.
  4. Sub-threshold prompts (max-class probability below the configured uncertainty cutoff) deterministically route to the configured fallback model and emit `rationale` containing "low confidence — fallback"; unit test in `src/routing/tests/` proves this.
  5. `uv sync` against the new root `pyproject.toml` + `uv.lock` produces a working environment that can run all Phase 1 commands; the new `.gitignore` already excludes `.env`, `*.db`, `*.db-journal`, `*.db-wal`, `__pycache__/`, `.venv/`, and `chat.db` from this phase's first commit.

**Plans**: 8 plans
- [x] 01-01-PLAN.md — Wave 0: Toolchain bootstrap (uv + pyproject.toml + uv.lock + .gitignore + pytest scaffolding + CI workflow) — OSS-01, SECURE-03
- [x] 01-02-PLAN.md — Wave 1: Extend PromptFeatureExtractor with 5 agentic features + lift text_inputs.py from duplicate sites — ROUTER-01 prep
- [x] 01-03-PLAN.md — Wave 1: Build agentic-intent dataset (seeds + LLM-synthesized + LLMRouterBench-mined negatives -> 1,000-row balanced CSV) — ROUTER-01 prep
- [x] 01-04-PLAN.md — Wave 2: Train calibrated agentic-intent classifier -> models/agentic_intent_classifier.joblib — ROUTER-01
- [x] 01-05-PLAN.md — Wave 2: Backup originals, add unknown class to build_question_type, calibrate task_type + model_router with FrozenEstimator, snapshot baselines.json — ROUTER-02 + ROUTER-03
- [ ] 01-06-PLAN.md — Wave 3: Build src/routing/ package (schema, config, policy, decide, __main__) + smoke tests for D-18 import-graph guard + Success Criterion #4 — ROUTER-05 + ROUTER-06
- [ ] 01-07-PLAN.md — Wave 4: Author ~42-row canary CSV + evaluate_routing.py runner + canary schema tests — ROUTER-04
- [ ] 01-08-PLAN.md — Wave 4: Wire demo_router.py to call src.routing.decide + artifact-compat regression guard + benchmark-no-regression guard — ROUTER-07

### Phase 2: Backend Adapters & ChatChunk Contract
**Goal**: Three backend adapters (OpenRouter, Claude Code, computer-use) each implement the `BackendAdapter` Protocol and stream a single `ChatChunk` discriminated union. Per-turn cost caps, per-iteration step caps, key redaction, computer-use opt-in, and the `claude-agent-sdk` SDK pin are all enforced from the adapter layer — no UI yet.
**Depends on**: Phase 1
**Requirements**: BACKEND-01, BACKEND-02, BACKEND-03, BACKEND-04, BACKEND-05, BACKEND-06, BACKEND-07, BACKEND-08, BACKEND-09, SECURE-01, SECURE-02, SECURE-04, SECURE-05, OSS-06
**Success Criteria** (what must be TRUE):
  1. A standalone CLI harness (e.g., `python -m apps.api.backends.openrouter --prompt "..."`) streams `ChatChunk` JSON lines to stdout for each of the three backends, terminating with a `Done` chunk that includes `tokens_in`, `tokens_out`, `cost_usd`, and `latency_ms` where the upstream provides them.
  2. `pytest apps/api/backends/tests` proves: (a) per-turn USD cap of $0.50 aborts mid-stream and emits `StreamError` + `Done`; (b) Claude Code stops at 25 tool calls and computer-use at 15 steps; (c) cancelling the iterator (browser-tab-close simulation) propagates to `query.interrupt()` / aborted HTTP within 2 seconds.
  3. Logger redaction filter is installed at process import time; a regression test asserts that emitting a record containing `sk-ant-…`, `sk-…`, or `Bearer …` is rewritten to `***REDACTED***` before any handler sees it; the BYOK key store holds keys in process memory + optional `keyring`, never on disk.
  4. CI smoke test asserts `from claude_agent_sdk import ClaudeAgentOptions` succeeds and the deprecated `claude-code-sdk` is not in `uv.lock`; OpenRouter requests carry `HTTP-Referer` and `X-Title` headers (verified by request-recording test); `CLAUDE_ENABLE_STREAM_WATCHDOG=1` is set in the adapter's environment-bootstrapping code.
  5. Computer-use adapter raises a startup error unless `COMPUTER_USE_OPT_IN=1` is set; Claude Code adapter writes into a per-thread tmpdir under `~/.prompt-optimizer/workspaces/<thread_id>/` by default, with a settings flag required to point at the user's repo `cwd`; a pre-commit hook installed in this phase blocks any commit whose staged content matches `sk-` or `sk-ant-`.

**Plans**: TBD

### Phase 3: FastAPI Service & Persistent Storage
**Goal**: A running `uvicorn apps.api.main:app` process exposes thread CRUD, settings, and `POST /threads/{id}/turn` over SSE; routing artifacts load once at lifespan startup; SQLite (WAL + busy_timeout) persists threads, messages, routing decisions, and large blobs by reference; integration tests exercise streaming end-to-end without a browser.
**Depends on**: Phase 2
**Requirements**: API-01, API-02, API-03, API-04, API-05, API-06, API-07, API-08, STORE-01, STORE-02, STORE-03, STORE-04, STORE-05, STORE-06, OSS-05
**Success Criteria** (what must be TRUE):
  1. `uvicorn apps.api.main:app` starts in under 3 seconds, loads all joblib artifacts exactly once (verified by a startup log line and a "no joblib loads after lifespan" assertion in tests), and serves `GET /healthz` plus thread CRUD on `POST/GET/PATCH/DELETE /threads`.
  2. An `httpx AsyncClient + ASGITransport` integration test posts a turn to `POST /threads/{id}/turn`, receives an SSE event stream of `ChatChunk`s, and observes a heartbeat event at the 15-second mark during a long agent run; `request.is_disconnected()` polling cancels the upstream provider call within 2 seconds when the client drops.
  3. After one turn completes, the SQLite file at the configured path contains exactly one `threads` row, two `messages` rows (user + assistant), and one `routing_decisions` row; the assistant row's `content_blocks` JSON contains every non-`TextDelta` chunk emitted; `PRAGMA journal_mode` returns `wal` and `PRAGMA busy_timeout` returns `5000`.
  4. Each routing decision is also appended as a JSON line to `.planning/data/routing_decisions.jsonl`; screenshots ≥256 KB and large diffs are written under `~/.prompt-optimizer/blobs/<sha256>` and referenced by hash from the DB row (verified by a computer-use simulation test).
  5. A schema-migration test upgrades a v0 DB (created from the initial `schema.sql`) to v1 using the chosen migration tool (Alembic or yoyo) without data loss; CORS middleware is configured with the explicit Next.js dev-server origin (no `allow_origins=["*"]`); BYOK keys submitted via `PATCH /settings` never appear in the DB or in any log line (regression test).

**Plans**: TBD

### Phase 4: Minimal Chat UI (OpenRouter Backend)
**Goal**: A running `next dev` app delivers a single-input multi-turn chat that streams OpenRouter responses through a Next.js route handler proxying FastAPI; the routing chip and one-line rationale appear on every assistant message; streaming markdown + code blocks render without flicker; stop button preserves partial responses. This phase exists to prove the SSE pipe end-to-end with one backend before adding two more.
**Depends on**: Phase 3
**Requirements**: UI-01, UI-03, UI-04, UI-06, UI-07, UI-08, UI-13, UI-17
**Success Criteria** (what must be TRUE):
  1. From a fresh `pnpm dev` + `uvicorn` boot, a user types a prompt, presses Enter, and sees a streamed assistant response with token-by-token markdown rendering; the routing chip ("Routed to <model> · <rationale>") appears at the top of each assistant message and is never collapsed or hidden.
  2. Code blocks inside the streamed response render as plain `<pre>` while the fence is still open, then receive syntax highlighting on close — verified by a manual "no flicker" check and a Playwright assertion that no re-highlight runs mid-stream.
  3. The Stop button cancels the in-flight stream within 2 seconds, the partial assistant message is preserved on screen and persisted to SQLite with `status='complete'` (or `'error'` if the abort happens before any text arrived), and the UI displays per-turn latency (ms) + cost (USD) + token count alongside the final message.
  4. The browser never opens a connection to FastAPI directly — DevTools shows requests only to `/api/chat` on the Next.js origin; the route handler at `apps/web/app/api/chat/route.ts` proxies to FastAPI server-side and pipes the SSE response through.
  5. On a fresh clone with no `.env`, the first-run modal appears, links to the settings panel for entering an OpenRouter key, and blocks the chat input until at least one usable key is set; once the key is entered the user can complete a turn without restarting either process.

**Plans**: TBD
**UI hint**: yes

### Phase 5: Feature-Complete Chat UI
**Goal**: All three backends are live in the UI with their dedicated bubble renderers; the thread sidebar, settings panel, per-turn override, backend status dots, auto-rename, "wrong route" feedback, and empty-state sample prompts ship; the routing chip's rationale is the visible expression of the router's decision for every assistant message across every backend.
**Depends on**: Phase 4
**Requirements**: UI-02, UI-05, UI-09, UI-10, UI-11, UI-12, UI-14, UI-15, UI-16
**Success Criteria** (what must be TRUE):
  1. The thread sidebar lists every persisted thread and supports create / select / rename / delete; selecting a thread loads its full history; threads survive a full browser-close + reopen because they live in SQLite, and threads auto-rename from the first user message via a cheap-model bypass route (no main-router invocation).
  2. A "build me a small finance app" prompt routes to Claude Code and renders in `CodeBubble` with collapsible tool-call chips, an inline red/green file-diff view, and a final summary; a "what is the capital of France?" prompt routes through OpenRouter and renders in `ChatBubble`; an "open this URL and check the price" prompt (with `COMPUTER_USE_OPT_IN=1`) routes to computer-use and renders in `ComputerUseBubble` with a screenshot strip and "still working… 0:42" indicator.
  3. The user can override the routed backend per turn via slash command (`/openrouter`, `/code`, `/computer`) and via a dropdown next to the input; choosing an override re-runs the turn against the selected backend; clicking the thumbs-down on any assistant message appends a row to a local `.planning/data/routing_feedback.jsonl` log file with the original prompt, the routed decision, and a timestamp.
  4. A status strip at the top of the app shows a green or red dot per backend reflecting key presence + a startup `GET /api/v1/models` (or equivalent availability check) ping; the settings panel exposes BYOK key entry per provider, per-backend enable/disable toggles, and an explicit computer-use opt-in switch separate from the env flag.
  5. The empty-state for a new thread shows three sample prompts that exercise the three different backends; clicking one populates the composer and submits, producing three different routing chips ("Routed to OpenRouter · …", "Routed to Claude Code · …", "Routed to computer-use · …") on the resulting assistant turns.

**Plans**: TBD
**UI hint**: yes

### Phase 6: Open-Source Release Hardening
**Goal**: A first-time contributor can clone the repo on a clean machine, run `make setup`, follow the README's three golden-path demo prompts, and reach the first streamed response in under 10 minutes — without leaking keys, without hitting cost runaway, and with the computer-use threat model spelled out before they enable it. Playwright E2E catches AI SDK ↔ FastAPI message-format drift automatically.
**Depends on**: Phase 5
**Requirements**: OSS-02, OSS-03, OSS-04, OSS-07, OSS-08, SECURE-06
**Success Criteria** (what must be TRUE):
  1. `make setup` (or `scripts/setup.sh`) on a clean clone runs `git lfs install && git lfs pull`, downloads NLTK `punkt_tab`, pre-fetches the SentenceTransformer model into the local cache, and copies `.env.example` → `.env` if absent; `.env.example` enumerates every key the app reads with one-line comments; the script exits non-zero if any step fails.
  2. The rewritten `README.md` walks a brand-new user from `git clone` to first streamed response with the three golden-path prompts ("build me a finance app" → Claude Code, "what's the capital of France?" → cheap chat model, "open this URL and check the price" → computer-use) plus screenshots of the routing chip on each turn.
  3. A Playwright E2E test boots `next dev` + `uvicorn`, sends a prompt to OpenRouter, asserts streamed text appears in the DOM, and asserts the routing chip is visible on the assistant message — wired into CI so any AI SDK v5 ↔ FastAPI UI Message Stream Protocol drift fails the build.
  4. Fresh-clone UAT: a contributor on a clean machine (no prior project state, no caches) follows only the README and reaches the first successful streamed turn in under 10 minutes; the time-to-first-turn measurement is recorded in the README as a "tested on" stamp.
  5. The README's Security & Safety section documents the computer-use threat model (prompt injection from visited pages, runaway cost, workspace exfiltration), explains the per-thread ephemeral workspace defaults, and explicitly states that computer-use is OFF unless both `COMPUTER_USE_OPT_IN=1` and the in-app toggle are set.

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Router Brain Foundation | 3/8 | In Progress | - |
| 2. Backend Adapters & ChatChunk Contract | 0/TBD | Not started | - |
| 3. FastAPI Service & Persistent Storage | 0/TBD | Not started | - |
| 4. Minimal Chat UI (OpenRouter Backend) | 0/TBD | Not started | - |
| 5. Feature-Complete Chat UI | 0/TBD | Not started | - |
| 6. Open-Source Release Hardening | 0/TBD | Not started | - |
