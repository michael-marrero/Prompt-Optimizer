# Phase 4: Minimal Chat UI (OpenRouter Backend) - Context

**Gathered:** 2026-05-18
**Status:** Ready for planning

<domain>
## Phase Boundary

A `pnpm --dir apps/web dev` Next.js 15.2 + React 19 app that delivers a single-input, multi-turn chat surface streaming OpenRouter responses end-to-end through:

```
browser ──fetch──▶ Next.js route handler ──fetch──▶ FastAPI POST /api/v1/threads/{id}/turn
                   (apps/web/app/api/chat/route.ts)   ──SSE────▶ named events
                          ▲                                          │
                          │  ◀───── translated to AI SDK v5 UI Message Stream Protocol
                          │
                  useChat hook (via @assistant-ui/react-ai-sdk useChatRuntime)
                          │
                  @assistant-ui/react primitives (Thread / Composer / MessagePrimitive)
                          │
                  Rendered: routing chip ABOVE bubble + markdown body + metrics footer BELOW
```

The phase exists to **prove the SSE pipe with one backend** before Phase 5 adds two more. OpenRouter is the only adapter exercised; Claude Code + computer-use bubbles wait for Phase 5. Even so, the visual system (color-coded chips, bubble layout, runtime extensibility) is **forward-compatible with Phase 5** — switching renderers is a config change, not a rewrite.

Per-turn UX lifecycle:

1. User types in composer → Enter sends.
2. Browser POSTs `{messages: [...]}` to `apps/web/app/api/chat/route.ts` (AI SDK v5 default body).
3. Proxy strips to `{message: <latest user text>}`, forwards to FastAPI `POST /api/v1/threads/{id}/turn`.
4. FastAPI returns an SSE stream. **First event:** the new `routing_decision` named event (Phase 3 wire extension) — chip pops immediately. **Subsequent events:** `text_delta` chunks streamed token-by-token; `done` lands last with totals.
5. Proxy translates each Phase-3 named event into AI SDK v5 UI Message Stream Protocol parts; `useChat` consumes natively.
6. Bubble renders markdown via `@assistant-ui/react-markdown`; code blocks render as plain `<pre>` while `\`\`\`` fence is open, then one-time highlighted via `shiki` on close (no re-highlight mid-stream).
7. On `done`: footer metrics (`$X · Xs · X↑/X↓`) populate; routing chip stays visible.
8. Stop button → `useChat.stop()` → `AbortController.abort()` → Next.js `req.signal.aborted` → upstream `fetch` aborts → FastAPI `request.is_disconnected()` cancels OpenRouter upstream within 2s. Partial response is preserved on screen and was already persisted by FastAPI as `status='cancelled'` (Phase 3 D-04).

**Verification surface (per ROADMAP SC):**
- Fresh `pnpm dev` + `uvicorn` boot → first streamed turn with routing chip visible at top of assistant message.
- Playwright: code blocks highlight exactly once per block (DOM snapshot diff before/after fence close).
- Playwright: Stop within 2s, partial persisted with `status='complete'` (or `'error'` if abort lands pre-text).
- DevTools: browser only opens connections to `/api/chat`, `/api/settings`, `/api/health` on the Next.js origin — never to FastAPI directly.
- First-run UAT: empty `.env`, blocking modal appears, user enters OpenRouter key, completes a turn without restarting either process.

**Not in scope (deferred to Phase 5):**
- Thread sidebar (UI-02), create/select/rename/delete UI — Phase 4 ships with a single auto-created default thread (planner's discretion: thread_id minted on app boot, stored in localStorage, persists across reloads; Phase 5 sidebar replaces this layer).
- Per-turn override slash commands `/openrouter`, `/code`, `/computer` (UI-05) — the `override_backend` field on the turn body exists but the UI doesn't surface it.
- CodeBubble (UI-09), ComputerUseBubble (UI-10) — only `ChatBubble` (UI-08) ships in Phase 4.
- Backend availability status dots (UI-11), settings panel with per-backend toggles (UI-12) — Phase 4 reads `/healthz` only to detect `missing_key` for the first-run flow.
- Thread auto-rename (UI-14), thumbs-down feedback log (UI-15), empty-state sample prompts (UI-16) — Phase 5.

**Not in scope (deferred to Phase 6):**
- Playwright E2E in CI (OSS-07), `make setup`, README golden path, fresh-clone UAT, computer-use threat-model docs.

</domain>

<decisions>
## Implementation Decisions

### Scaffolding & Monorepo Shape

- **D-01: `apps/web/` is a sibling of `apps/api/`.** Scaffolded with `pnpm create next-app@latest apps/web --typescript --tailwind --app --src-dir` and then the additional dep installs (assistant-ui, AI SDK v5, shiki, etc.). pnpm is the package manager — workspace-friendly, fast, the de facto choice for Next.js monorepos. No `pnpm-workspace.yaml` needed yet (single Next app + existing Python apps don't share JS deps); planner adds one if Phase 6 introduces a second JS package.

- **D-02: Two-terminal dev orchestration.** No `concurrently`, no Makefile target in Phase 4. README documents:
  ```
  Terminal 1: uvicorn apps.api.main:app --reload
  Terminal 2: pnpm --dir apps/web dev
  ```
  Phase 6 OSS-02 (`make setup`) may revisit; Phase 4 stays minimal.

- **D-03: Tailwind CSS v4 + shadcn/ui.** Mirrors the assistant-ui starter and AI SDK examples. shadcn primitives (Button, Dialog, Input, Toast) are pulled in via `pnpm dlx shadcn@latest add ...` as needed — only commit what's used. **No design-token sprawl** in Phase 4: rely on shadcn defaults; planner picks any minor palette tweaks needed for the backend color coding (D-12).

- **D-04: Light mode only.** No `next-themes`, no `prefers-color-scheme` switching. Single light theme keeps the visual surface area small for Phase 4's "prove the pipe" goal. Dark mode is deferred to Phase 6+ polish (or v2).

- **D-05: Env-var separation.** `apps/web/.env.local` holds `FASTAPI_URL=http://localhost:8000` and any `NEXT_PUBLIC_*` browser-safe constants only. Repo-root `.env` stays Python/FastAPI-exclusive (BYOK keys, `COMPUTER_USE_OPT_IN`, `PROMPT_OPTIMIZER_HOME`). README documents both files distinctly. **Belt-and-suspenders:** `apps/web/.env.local` is added to `.gitignore` (Phase 1 SECURE-03 already covers `.env`; new line added for `.env.local`).

### Streaming Stack

- **D-06: `@assistant-ui/react` is the runtime root, fed by `@ai-sdk/react`'s `useChat` via `@assistant-ui/react-ai-sdk`'s `useChatRuntime` adapter.** This is the documented starter pattern. Phase 4 gains battle-tested Thread / Composer / MessagePrimitive primitives that swap renderers cleanly when Phase 5 adds CodeBubble + ComputerUseBubble. **Direction:** no custom runtime; lean on the primitive set.

- **D-07: Proxy at `apps/web/app/api/chat/route.ts` translates Phase 3 named events → AI SDK v5 UI Message Stream Protocol.** FastAPI side untouched; Phase 3's wire stays canonical for non-Next clients (CLI, Playwright fixtures, future MCP/external consumers). Translation layer is a pure function `translateNamedSSEToUIMessageStream(reader: ReadableStreamReader) → ReadableStream<UIMessagePart>` testable in isolation against fixture event streams.

- **D-08: History shape — Next.js proxy strips AI SDK v5 `{messages: [...]}` body to FastAPI's `{message: <latest user text>}`.** FastAPI's `get_thread_messages(thread_id)` is the single source of truth for prior history; the AI SDK messages array is discarded at the proxy boundary. **Zero possibility of client/server drift** — thread reloads after browser-close always re-render from DB (the same data FastAPI uses for routing context).

- **D-09: Cancellation chain — standard `AbortController` end-to-end, 2s budget asserted at three layers.**
  ```
  useChat.stop()
    → AbortController.abort()
    → fetch to /api/chat aborts
    → Next route handler observes req.signal.aborted
    → upstream fetch to FastAPI aborts
    → FastAPI request.is_disconnected() (Phase 3 D-06) cancels OpenRouter
  ```
  **Three independent assertions** of the 2s invariant:
  1. Playwright (browser → Next): elapsed < 2s from `stop()` click to UI showing "cancelled" state.
  2. Phase-4 httpx async test (Next → FastAPI): proxy `fetch` aborts within 2s of the inbound abort signal.
  3. Phase-3 existing test (FastAPI → OpenRouter): already in place.

  No new `POST /cancel` endpoint (rejected: extra surface + race conditions outweigh redundancy).

### Message Rendering

- **D-10: Markdown via `@assistant-ui/react-markdown`** (assistant-ui-native wrapper around `react-markdown`). Same maintainer as the runtime; no cross-vendor drift. Plugged into `MessagePrimitive.Content` directly. `streamdown` rejected for v1 (introduces a second markdown opinion that may conflict with assistant-ui's component model).

- **D-11: Code-block highlighting via `shiki` through assistant-ui's code-block primitive.** The primitive owns fence-state detection: renders plain `<pre>` until `\`\`\`` close, then one-time highlighted swap. **No flicker.** Playwright assertion: capture DOM snapshots during stream, assert the inner `<code>` element's child structure changes exactly once per block (no mid-stream re-highlight). shiki theme: planner picks one shadcn-compatible theme (e.g., `github-light` for Phase 4's light-mode-only stance).

- **D-12: Routing chip placement and content.** Chip sits **above** the assistant bubble, always visible, never collapsed. Content: `Routed to <display_name>` (bold) + `· <one-line rationale>`. **Color-coded by backend** even in Phase 4:
  - `openrouter` → slate (`bg-slate-100 text-slate-900 border-slate-200`)
  - `claude_code` → green (Phase 5 ready)
  - `computer_use` → amber (Phase 5 ready)

  display_name resolves via `config/model_mapping.json` (Phase 1 D-02 mechanism). **The chip pops as soon as the `routing_decision` SSE event lands** (see D-15 below) — usually within ~100ms of POST, well before the first `text_delta`.

- **D-13: Per-turn metrics footer.** Compact monospace line **below** the assistant bubble: `$0.0021 · 1.4s · 312↑/847↓`. Mid-stream: footer shows `streaming…` with an animated dot (Tailwind `animate-pulse`). All three values populate on `done`. **No mid-stream zeros / placeholders that look like real data** — the explicit "streaming…" string makes mid-stream state unambiguous.

- **D-14: ChatBubble affordances (UI-08).** Hover-revealed action row at the bottom-right of each assistant bubble:
  - **Copy-as-markdown** → copies the raw markdown source (not the rendered HTML) to clipboard.
  - **Regenerate** → re-issues the same user prompt against the same thread; new assistant turn is appended (does NOT replace the existing one; Phase 5 may add a "replace" affordance, deferred).

  Hover-only is acceptable because UI-04 ("routing chip always visible") is independently satisfied by the chip placement; the action row is bonus chrome.

- **D-15: NEW SSE event type `routing_decision`** emitted by `apps/api/routes/turn.py` **before** adapter dispatch. **This is a Phase 3 wire-format extension required by Phase 4.**
  - **Does NOT modify the Phase 2 `ChatChunk` Pydantic union** — the event is yielded by the SSE handler alongside chunks, not as a chunk itself.
  - **Payload shape (revised 2026-05-19 during plan-checker iteration 1):** the FULL routing-chip contract — `{backend, model_or_agent, rationale, confidence, signals}` sourced from `RoutingDecision`'s top-level fields plus the `signals` telemetry sub-dict (Phase 1 D-03). The earlier wording ("payload IS the signals dict") was reconciled when the chip integration revealed the chip needs `backend`/`model_or_agent`/`rationale` to render its "Routed to … · …" text; `RoutingDecision.signals` alone is telemetry (task_type, agentic_intent, rule_fired) and does not contain those fields.
  - **Belt-and-suspenders contract test:** assert the `routing_decision` event arrives within 100ms of the turn POST AND that the parsed payload's `signals` sub-field equals `Done.routing_signals` byte-for-byte. `Done.routing_signals` remains the canonical persistence source (Phase 3 STORE-02 / D-04); the early SSE event is for UX freshness only. The byte-for-byte equality moved from the whole payload to the `signals` sub-field as part of the reconciliation above.
  - **Phase 3 amendment scope:** edit `apps/api/routes/turn.py` only. Add the new event to Phase 3's REQUIREMENTS.md API-02 wording (or document the extension inline in Phase 4's CONTEXT — planner decides which).
  - **Phase 4 contract:** the proxy translates `event: routing_decision` to an AI SDK v6 `data-routing` part that the assistant-ui chip component subscribes to via `useThreadMessage`'s parts.

### First-Run Modal & Key Setup

- **D-16: Two independent missing-key triggers.**
  1. **On app boot:** `GET /api/v1/healthz` (via the proxy); read `adapters.openrouter.status`. `missing_key` → block composer + show modal.
  2. **On any turn:** catch HTTP 400 / SSE `StreamError(code="auth_failed")` and re-pop the modal.

  Both triggers route through the **same modal component** — single render surface, single state machine. Healthz catches first-run; the 400-catch covers the case where the user removed a key in another session/process and the Next side hasn't re-polled yet.

- **D-17: Modal + persistent `/settings` route.** Blocking modal on first-run (non-dismissible until ≥1 usable key saved). Same component is also mounted at `apps/web/app/settings/page.tsx` (non-blocking) for later management. Modal copy: input field + "Save & continue" button + external link to `https://openrouter.ai/keys`. Reachable later via a gear icon in the app header.

- **D-18: Key-plumbing path (UI-17 critical).** Browser POSTs `{provider: "openrouter", key: "sk-or-v1-..."}` to a new Next server-side route at `apps/web/app/api/settings/route.ts`. The route handler **immediately** forwards via `PATCH /api/v1/settings` with body `{keys: {openrouter: <key>}}`. **Key never:**
  - Stored in cookies / localStorage / sessionStorage on the Next side.
  - Returned to the browser in any response body, header, or error message.
  - Persisted to disk on the Next side (no `.next/cache/settings.json`).

  FastAPI's `KeyStore` (Phase 2 D-10 + Phase 3 D-11) is the single source of truth. Response to the browser includes only the masked form (`{"openrouter": {"present": true, "masked": "sk-or-…ABC"}}`).

  **Belt-and-suspenders Next-side hygiene:** the route handler wraps `fetch` with a try/catch that scrubs the key from any thrown error message before re-throwing or returning to the browser. Regression test posts a real-shaped key, then greps every Next-side log file, response body, response header, and cookie for the literal key string — must return zero matches.

- **D-19: Post-entry unblock sequence.** On successful 200 from `PATCH /api/v1/settings`, the proxy re-fetches `GET /api/v1/healthz`. Chat input unblocks only when `adapters.openrouter.status == "ready"`. **No process reload** — Phase 3 D-15 (lazy adapter construction + `app.state.adapters.clear()` cache invalidation on PATCH) handles the rest. Toast: "OpenRouter connected — try a prompt!" The healthz round-trip catches the rare race where PATCH validation passed but the KeyStore write failed (e.g., OS keyring unavailable).

### Claude's Discretion

The planner / researcher own these — no user preference was expressed:

- **Thread creation in minimal mode** — auto-create one default thread via `POST /api/v1/threads` on app boot. Store the returned `thread_id` in `localStorage` under key `prompt-optimizer.defaultThreadId`. Reuse across page reloads. Phase 5's sidebar replaces this with full CRUD.
- **Composer behavior** — assistant-ui Composer defaults: Enter sends; Shift+Enter inserts newline; Cmd/Ctrl+K focuses composer.
- **StreamError UI surfacing** — when a `stream_error` SSE event lands, render a red inline banner inside the assistant bubble with the error code + message + a "retry" button (for retriable=True). On `cost_cap_exceeded` show the cap value.
- **Loading state on composer submit** — composer disables, send button shows a spinner, "Stop" button replaces "Send" once the first streamed chunk arrives.
- **shadcn component subset** — Button, Dialog (for first-run modal), Input, Toast / Sonner (for the connected toast). Planner pulls others as Phase 4 progresses.
- **Assistant message timestamps** — show as relative ("just now", "2m ago") with an absolute-time tooltip on hover. Generated on the client from `created_at` returned by FastAPI; **never** generated client-side independently (would drift from DB truth).
- **Empty-state visual** — Phase 4 minimal: centered tagline + the composer below. No sample prompts (UI-16 = Phase 5). Planner picks any tagline; e.g., "Ask anything. We'll route to the right model."
- **Network error handling on the proxy** — if FastAPI is unreachable (`ECONNREFUSED`), the Next route returns a 503 with `{error: "API unavailable — is uvicorn running?"}`. UI surfaces as a banner above the composer. Restart-detection: poll `/healthz` every 5s while in error state; auto-clear when 200 returns.
- **Default OpenRouter model on first turn** — `decide()` picks per the routing brain. UI does not pre-select.
- **Composer placeholder** — "Type a message…" (planner discretion).
- **Browser title** — `Prompt-Optimizer` (matches PROJECT.md).
- **Favicon** — a simple emoji-derived SVG (planner picks; can be replaced in Phase 6 polish).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner, executor) MUST read these before planning or implementing.**

### Phase Scope & Requirements

- `.planning/ROADMAP.md` §"Phase 4: Minimal Chat UI (OpenRouter Backend)" — goal, dependencies, requirement mapping, 5 success criteria. Phase boundary is FIXED.
- `.planning/REQUIREMENTS.md` — read UI-01, UI-03, UI-04, UI-06, UI-07, UI-08, UI-13, UI-17 (the 8 requirements assigned to Phase 4). Phase 5/6 UI items are explicitly deferred.
- `.planning/PROJECT.md` — Core Value ("quality first, cost as tiebreaker"), constraints (BYOK; open-source local-only; no auth/billing).
- `CLAUDE.md` (repo root) — project conventions, GSD workflow enforcement.

### Phase 1, 2, 3 Carry-Forward (the upstream contract Phase 4 consumes)

- `.planning/phases/01-router-brain-foundation/01-CONTEXT.md` — D-02 (`config/model_mapping.json` resolves `display_name` for the chip), D-03 (`RoutingDecision.signals` shape — payload of the new `routing_decision` SSE event in D-15), D-04 (concrete `model_or_agent` strings the chip displays).
- `.planning/phases/02-backend-adapters-chatchunk-contract/02-CONTEXT.md` — D-01/D-02 (`ChatChunk` 7-variant Pydantic union — NOT modified by Phase 4), D-04 (terminal `[StreamError]? + Done` invariant the proxy and UI rely on), D-06 (`StreamError.code` closed vocabulary — UI maps these to user-friendly messages).
- `.planning/phases/03-fastapi-service-persistent-storage/03-CONTEXT.md` — D-04 (one transaction per turn on Done — UI trusts persistence is atomic), D-06 (sse-starlette `request.is_disconnected()` polling — last link in the cancellation chain D-09), D-07 (Phase 3 SSE named-event format — the upstream wire Phase 4 translates), D-09 (`/api/v1` namespace), D-10 (PATCH `/api/v1/settings` body shape + masked GET response), D-11 (settings.json persistence + KeyStore separation), D-15 (lazy adapter construction + cache invalidation on PATCH — load-bearing for D-19 post-entry unblock), D-18 (`GET /api/v1/healthz` adapter status — D-16 missing-key detection consumer).
- `.planning/phases/03-fastapi-service-persistent-storage/03-VERIFICATION.md` — Phase 3 closing state; all 15 API/STORE/OSS requirements satisfied.

### Source Files Phase 4 Consumes (Read-Only)

- `apps/api/routes/turn.py` — Phase 4 amends with the new `routing_decision` SSE event (D-15). Single edit site.
- `apps/api/routes/health.py` — Phase 4 consumer; no edits.
- `apps/api/routes/settings.py` — Phase 4 consumer; no edits.
- `apps/api/routes/threads.py` — Phase 4 calls `POST /api/v1/threads` for the default-thread auto-create.
- `apps/api/backends/chunks.py` — `ChatChunk` union; Phase 4 does NOT modify (the new SSE event is yielded alongside, not as a chunk).
- `apps/api/backends/keystore.py` — single source of truth for keys; Phase 4 never replicates state.
- `config/model_mapping.json` — `display_name` lookup for the routing chip.

### External Dependencies (NEW in Phase 4)

- `next@15.2.x` — App Router, React 19, server components, route handlers for the proxy.
- `react@19.x`, `react-dom@19.x`.
- `typescript@5.x`.
- `tailwindcss@4.x` + `@tailwindcss/postcss` (Tailwind v4 uses CSS-first config).
- `@ai-sdk/react@>=2` — `useChat` hook (the transport that drives the runtime).
- `@assistant-ui/react@>=0.10` — Thread / Composer / MessagePrimitive primitives.
- `@assistant-ui/react-ai-sdk` — `useChatRuntime` adapter bridging useChat to the assistant-ui runtime.
- `@assistant-ui/react-markdown` — markdown renderer integrated with `MessagePrimitive.Content`.
- `shiki` — code highlighter; loaded via assistant-ui's code-block primitive.
- `shadcn/ui` components added via CLI as needed: Button, Dialog, Input, Sonner (toast).
- `lucide-react` — icon set (gear, stop, send, copy, refresh).
- `clsx` + `tailwind-merge` — class composition (shadcn convention).

### Existing Codebase Maps

- `.planning/codebase/STACK.md` — Python side authoritative; Phase 4 introduces the first JS toolchain. No conflicts.
- `.planning/codebase/STRUCTURE.md` — `apps/api/` already exists; `apps/web/` is the sibling Phase 4 adds.
- `.planning/codebase/CONVENTIONS.md` — Python conventions don't apply to JS code; Phase 4 establishes JS conventions (TypeScript strict, ESLint via Next defaults, pnpm).

### New Files Phase 4 Creates

- `apps/web/` — entire Next.js app (scaffolded via `pnpm create next-app`).
  - `apps/web/app/layout.tsx` — root layout with Tailwind, runtime provider mount.
  - `apps/web/app/page.tsx` — chat surface (Thread + Composer).
  - `apps/web/app/settings/page.tsx` — non-blocking key-management page.
  - `apps/web/app/api/chat/route.ts` — SSE proxy (D-07).
  - `apps/web/app/api/settings/route.ts` — key submission proxy (D-18).
  - `apps/web/app/api/health/route.ts` — `/healthz` pass-through used by D-16 boot check.
  - `apps/web/components/RoutingChip.tsx` — D-12 component.
  - `apps/web/components/MetricsFooter.tsx` — D-13 component.
  - `apps/web/components/FirstRunModal.tsx` — D-17 component.
  - `apps/web/components/KeyForm.tsx` — shared form used by modal + /settings.
  - `apps/web/lib/sse-translate.ts` — D-07 named-event → AI SDK UI Message Stream translation (pure function, unit-tested against fixtures).
  - `apps/web/lib/api-client.ts` — typed wrappers for `/api/chat`, `/api/settings`, `/api/health`.
  - `apps/web/lib/thread-id.ts` — D-(Claude's discretion) default-thread auto-create + localStorage persistence.
  - `apps/web/tests/sse-translate.test.ts` — Vitest unit tests for the translation pure function.
  - `apps/web/playwright/no-flicker.spec.ts` — D-11 highlight-once assertion.
  - `apps/web/playwright/cancel-budget.spec.ts` — D-09 layer-1 assertion (2s budget browser→Next).
  - `apps/web/playwright/first-run.spec.ts` — D-16/D-17 modal flow.
  - `apps/web/playwright/secure-key.spec.ts` — D-18 zero-match key-scrub regression.
  - `apps/web/package.json`, `apps/web/pnpm-lock.yaml`, `apps/web/tsconfig.json`, `apps/web/next.config.ts`, `apps/web/tailwind.config.ts`, `apps/web/postcss.config.mjs`, `apps/web/.env.example`, `apps/web/.env.local` (gitignored).
- `apps/api/routes/turn.py` — EDIT to emit `routing_decision` SSE event before adapter dispatch (D-15). New contract test added.
- `apps/api/tests/test_turn_streaming.py` — EDIT to assert the new event's presence + 100ms latency + byte-for-byte match with `Done.routing_signals`.
- `.gitignore` — append `apps/web/node_modules/`, `apps/web/.next/`, `apps/web/.env.local`, `apps/web/coverage/`, `apps/web/playwright-report/`, `apps/web/test-results/`.
- `ReadMe.md` — append "Running the chat UI" section with two-terminal instructions (D-02).

### Wire-Format Extension (Phase 3 → Phase 4)

- **NEW SSE event:** `event: routing_decision\ndata: <JSON of RoutingDecision.signals>\n\n` emitted by `apps/api/routes/turn.py` immediately after `decide()` returns and BEFORE adapter dispatch. ChatChunk Pydantic union is NOT modified.
- **Phase 3 REQUIREMENTS.md API-02** wording update (planner decides if this lands in Phase 4 or stays inline in CONTEXT): "`POST /threads/{thread_id}/turn` runs routing decision → emits a `routing_decision` SSE event with `RoutingDecision.signals` payload → dispatches adapter → streams `ChatChunk`s back via `fastapi.sse.EventSourceResponse`."

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`apps/api/routes/turn.py`** — Phase 4's single FastAPI edit site (D-15). Routing decision already happens before adapter dispatch (Phase 3 D-05) — emitting an additional SSE event at that point is structurally cheap.
- **`apps/api/routes/health.py`** — Phase 3 D-18 ships `adapters.openrouter.status ∈ {ready, missing_key, opt_out, error}`. Phase 4's D-16 reads exactly this field; no new endpoint needed.
- **`apps/api/routes/settings.py`** — Phase 3 D-10's `PATCH /api/v1/settings` with `{keys: {openrouter: ...}}` body is exactly what Phase 4 D-18 forwards. Masked GET response (`sk-or-…ABC`) is what the UI shows after submit.
- **`apps/api/backends/chunks.py:ChatChunk`** — Phase 4 NEVER modifies this union. The `routing_decision` SSE event is yielded alongside, not as a chunk. Forward-compatible with Phase 5 backends.
- **`config/model_mapping.json`** — `display_name` field powers the routing chip. Already 16 entries; planner verifies coverage for the 4 OpenRouter-routable slugs Phase 4 might surface.
- **Phase 3 SSE wire (D-07)** — named-event SSE format is extensible by design. Adding a new event type does not break existing parsers; Phase 4's proxy switch-statement gets a new branch.
- **Phase 3 `app.state.adapters.clear()` on PATCH /settings (D-15)** — Phase 4's D-19 post-entry unblock relies on this; no Phase 3 code change needed for the cache-invalidation behavior.

### Established Patterns (apps/api → carry to apps/web)

- **`pathlib.Path(__file__).resolve().parents[N]`** — Python convention. Not applicable to JS; Next's `process.cwd()` + Path module already standard.
- **Closed-vocabulary `Literal[...]`** — Python pattern. JS equivalent: TypeScript discriminated unions on `type` field. `apps/web/lib/sse-translate.ts` mirrors Phase 2 D-01's discriminated approach in TS:
  ```typescript
  type Backend = "openrouter" | "claude_code" | "computer_use";
  type NamedSSEEvent =
    | { event: "text_delta"; data: { text: string } }
    | { event: "routing_decision"; data: RoutingSignals }
    | { event: "tool_call"; data: { id: string; name: string; input: unknown } }
    | { event: "stream_error"; data: { code: string; message: string; retriable: boolean } }
    | { event: "done"; data: { tokens_in: number; tokens_out: number; cost_usd: number; latency_ms: number } };
  ```

- **Single-file SSE serializer / deserializer** — Phase 3's `EventSourceResponse` is the server side; `apps/web/lib/sse-translate.ts` is its client mirror. Same closed vocabulary on both sides; CI keeps them in sync via the new `routing_decision` regression test.

### Integration Points

- **Phase 4 → Phase 3:** `POST /api/v1/threads/{id}/turn`, `POST /api/v1/threads`, `GET /api/v1/healthz`, `PATCH /api/v1/settings`, `GET /api/v1/settings`. All via the Next.js proxy; browser never opens FastAPI sockets directly (UI-17).
- **Phase 4 ← Phase 3 amendment:** new `routing_decision` SSE event (D-15) — single edit to `apps/api/routes/turn.py`.
- **Phase 4 → Phase 5 (downstream):** the `@assistant-ui/react` runtime + the color-coded chip system is the foundation Phase 5 extends with CodeBubble + ComputerUseBubble + sidebar + override slash commands. The translation layer in `apps/web/lib/sse-translate.ts` already handles `tool_call` / `tool_result` / `file_diff` / `screenshot` event types — Phase 5 wires the renderers; no new translation work.
- **Phase 4 → Phase 6 (downstream):** Playwright E2E (OSS-07) reuses the four Phase 4 Playwright specs as the foundation suite.

### Anti-Patterns to AVOID

- **Do NOT speak directly from browser to FastAPI.** UI-17 violation. Every API hit goes through `apps/web/app/api/*` route handlers. The browser only knows about the Next.js origin.
- **Do NOT cache the OpenRouter key on the Next side.** D-18 violation. No cookies, no localStorage, no sessionStorage, no `.next/cache` file. FastAPI's `KeyStore` is the single source.
- **Do NOT modify the Phase 2 `ChatChunk` union.** Phase 4's wire extension (D-15) is a peer event, not a chunk. Modifying the union would force a Phase 2 / Phase 3 reverification.
- **Do NOT add re-highlight on every stream tick.** D-11. The shiki primitive does fence-state detection; trust it. Re-highlighting per chunk would fail SC #2 and the no-flicker Playwright assertion.
- **Do NOT forward AI SDK v5's full `messages` array to FastAPI.** D-08. FastAPI/SQLite is the canonical history source; client array is discarded at the proxy.
- **Do NOT add a `POST /cancel` endpoint.** D-09 rejection. The AbortController chain is sufficient; an explicit endpoint adds race conditions.
- **Do NOT use AI SDK v5's direct `useChat` without the `useChatRuntime` adapter.** D-06. The runtime root is `@assistant-ui/react`; bypassing the adapter forgoes the bubble extensibility we need for Phase 5.
- **Do NOT include the OpenRouter key in any Next.js log line, response body, response header, or error message.** D-18 belt-and-suspenders. Regression test will catch any leak.
- **Do NOT introduce dark mode in Phase 4.** D-04. Light only; dark is Phase 6+ polish.
- **Do NOT add `concurrently` or a Makefile target for dev.** D-02. Two terminals; README documents both.

</code_context>

<specifics>
## Specific Ideas

- **NEW SSE event `routing_decision`** — payload is `RoutingDecision.signals` (Phase 1 D-03). Emitted by `apps/api/routes/turn.py` after `decide()` returns and BEFORE adapter dispatch. ChatChunk union unchanged. Contract test asserts arrival within 100ms and byte-for-byte match with `Done.routing_signals`.

- **Chip color coding** — slate (openrouter), green (claude_code), amber (computer_use). Phase 4 only exercises slate; the other two are wired Phase-5-ready. Tailwind classes (light mode only):
  - `bg-slate-100 text-slate-900 border-slate-200`
  - `bg-green-100 text-green-900 border-green-200`
  - `bg-amber-100 text-amber-900 border-amber-200`

- **Chip content format:** `Routed to <display_name> · <one-line rationale>`. Display name resolves via `config/model_mapping.json`. Bold the model name, regular weight rationale.

- **Metrics footer format:** `$0.0021 · 1.4s · 312↑/847↓` (USD, latency, in/out tokens). Monospace font (Tailwind `font-mono text-xs`). Mid-stream replacement: `streaming…` with `animate-pulse` dot.

- **Two-terminal README block:**
  ```
  ## Running the chat UI

  Terminal 1 (FastAPI):
      uv sync
      uvicorn apps.api.main:app --reload

  Terminal 2 (Next.js):
      pnpm --dir apps/web install
      pnpm --dir apps/web dev

  Then open http://localhost:3000.
  On first run, paste your OpenRouter key into the modal.
  ```

- **Default thread auto-create** — call `POST /api/v1/threads` with `{title: "Untitled"}` on app boot if `localStorage.getItem("prompt-optimizer.defaultThreadId")` is null. Store the returned `id`. Phase 5 sidebar will replace this with a thread selector.

- **First-run modal copy:**
  > **Connect OpenRouter to get started**
  >
  > Prompt-Optimizer routes your prompts to the best model. OpenRouter is the gateway to most chat models — start by pasting your key.
  >
  > [ sk-or-v1-... ] [ Save & continue ]
  >
  > Don't have a key? Get one at [openrouter.ai/keys ↗](https://openrouter.ai/keys)

- **Connected toast:** "OpenRouter connected — try a prompt!"

- **Composer placeholder:** "Type a message…" (Cmd+K to focus).

- **shadcn components to install in this phase:** Button, Dialog, Input, Sonner. Pull others as planner needs.

- **Playwright budget assertions** — `cancel-budget.spec.ts` asserts elapsed time from `stop()` click to "cancelled" UI state is under 2000ms. Uses `performance.now()` markers.

- **Key-scrub regression test** — `secure-key.spec.ts` POSTs a real-shaped key (`sk-or-v1-XXXXXXXXXX...`), then greps:
  - Browser DevTools storage (cookies, localStorage, sessionStorage) — must return zero matches.
  - All response bodies from `/api/settings`, `/api/health`, `/api/chat` — must return zero matches.
  - All response headers — must return zero matches.
  - All Next.js server logs captured during the test — must return zero matches.

- **Browser-to-FastAPI isolation test** — Playwright captures all network requests, asserts that no request hits `localhost:8000` directly (only `localhost:3000` for the Next.js origin).

- **Phase 3 amendment patch shape** — pseudocode for the turn handler edit:
  ```python
  async def turn_handler(...):
      decision = await asyncio.to_thread(decide, ...)
      append_routing_decisions_jsonl(decision, ...)  # Phase 3 D-05 existing

      async def event_stream():
          # NEW: Phase 4 wire extension
          yield {"event": "routing_decision", "data": json.dumps(decision.signals)}

          adapter = get_or_create_adapter(decision.backend)
          async for chunk in adapter.stream(...):
              yield {"event": chunk.type, "data": chunk.model_dump_json()}

      return EventSourceResponse(event_stream(), ping=15)
  ```

</specifics>

<deferred>
## Deferred Ideas

- **Thread sidebar** — Phase 5 UI-02.
- **Multi-thread CRUD UI** — Phase 5.
- **Per-turn override slash commands `/openrouter`, `/code`, `/computer`** — Phase 5 UI-05.
- **CodeBubble for Claude Code output** — Phase 5 UI-09.
- **ComputerUseBubble for computer-use output** — Phase 5 UI-10.
- **Backend availability status dots** — Phase 5 UI-11.
- **Settings panel with per-backend enable/disable toggles + computer-use opt-in** — Phase 5 UI-12.
- **Thread auto-rename from first user message** — Phase 5 UI-14 (Phase 3 D-17 already lit up the rename endpoint).
- **Thumbs-down "wrong route" feedback log** — Phase 5 UI-15.
- **Empty-state sample prompts** — Phase 5 UI-16.
- **Dark mode** — Phase 6+ polish or v2.
- **`concurrently` / `make dev` orchestration** — possibly Phase 6 OSS-02 with `make setup`.
- **Tailwind theme palette / design tokens** — planner's discretion if minor; v2 if a full design system.
- **Explicit `POST /cancel` endpoint** — rejected; standard AbortController chain is sufficient.
- **`streamdown`** — rejected for Phase 4; assistant-ui-native markdown is the bulletproof choice. Revisit if assistant-ui-markdown shows streaming defects.
- **`@ai-sdk/react` without `useChatRuntime` adapter** — rejected; loses bubble extensibility needed for Phase 5.
- **next-themes / OS-driven theme** — deferred per D-04.
- **Cookie-encrypted key cache on Next side** — rejected per D-18; FastAPI KeyStore is canonical.
- **localStorage key storage** — rejected; violates UI-17 + D-18.
- **Hard reload after key submit** — rejected; healthz round-trip per D-19 is cleaner.
- **Mid-stream zero placeholders for metrics** — rejected per D-13; "streaming…" string is honest UI.
- **Replace-on-regenerate UI** — Phase 4 only appends; replace affordance deferred to Phase 5.
- **AI SDK v5 UI Message Stream Protocol direct from FastAPI** — rejected; FastAPI wire stays Phase 3 named-event canonical for non-Next consumers.
- **Single repo-root `.env` shared by Python and Next** — rejected per D-05; boundary clarity wins.
- **Composer mention/slash autocomplete** — defer until Phase 5 needs `/code`, `/computer` slash overrides.
- **File attachments / image uploads** — REQUIREMENTS Out of Scope.
- **Voice / audio input** — REQUIREMENTS Out of Scope.
- **Web search button in composer** — Out of Scope (router decides; user doesn't pick).
- **Public chat sharing** — REQUIREMENTS Out of Scope.
- **Per-thread cost display in sidebar** — Phase 5 sidebar may add; defer.
- **Streaming-aware diff renderer for FileDiff chunks** — Phase 5 CodeBubble owns this.
- **Server-sent ping/keepalive UI indicator** — sse-starlette `:ping` comments are silent at the EventSource layer; no UI surfacing needed.
- **Custom 404 / error pages** — Phase 6 polish.
- **Browser-side analytics / telemetry** — PROJECT.md Out of Scope.
- **Mobile-responsive layout** — out of scope for v1 (web-first).
- **Tiktoken on Next side for live cost estimation** — defer; cost comes from `Done.cost_usd`.

</deferred>

---

*Phase: 04-minimal-chat-ui-openrouter-backend*
*Context gathered: 2026-05-18*
