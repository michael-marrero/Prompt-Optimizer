# Phase 4: Minimal Chat UI (OpenRouter Backend) - Research

**Researched:** 2026-05-18
**Domain:** Next.js 16 App Router + AI SDK v6 + assistant-ui — SSE proxy from a custom FastAPI named-event wire to the AI SDK v6 UI Message Stream Protocol, with no-flicker streaming markdown + shiki code blocks, AbortController stop semantics, and BYOK key gating.
**Confidence:** HIGH on stack, architecture, and pitfalls. MEDIUM on the exact internal shape of `AssistantChatTransport` (verified via npm metadata + assistant-ui example wiring; the source of truth is the package itself, which the planner will read at execution time). LOW on whether `@assistant-ui/react-markdown` exposes a public hook for "intercept fence open/close" (treated as ASSUMED — the planner verifies during Wave 1 spike).

## Summary

Phase 4 stands up a Next.js 16 / React 19 / AI SDK v6 / assistant-ui app at `apps/web/`, scaffolded with `pnpm create next-app`, that delivers a single-input multi-turn chat. The browser POSTs to `apps/web/app/api/chat/route.ts`, which proxies to FastAPI's existing `POST /api/v1/threads/{id}/turn` (Phase 3) — an `EventSourceResponse` emitting **named SSE events** keyed by `chunk.type` (`event: text_delta\ndata: <JSON>\n\n`). The proxy reads the upstream SSE byte stream, parses each `event:`/`data:` block, and re-emits the equivalent AI SDK v6 **UI Message Stream Protocol** chunks (bare `data: {JSON}\n\n` lines with `text-start` / `text-delta` / `text-end` / `data-routing-decision` / `error` / `finish` types, with the `x-vercel-ai-ui-message-stream: v1` response header). The `useChatRuntime` adapter from `@assistant-ui/react-ai-sdk` consumes the protocol natively and feeds the `Thread` / `Composer` / `MessagePrimitive` set.

Markdown rendering goes through `@assistant-ui/react-markdown` (which wraps `react-markdown`) with `shiki` for code blocks. The "no flicker" requirement (ROADMAP SC #2) is satisfied by the assistant-ui code-block primitive's built-in fence-state detection (renders plain `<pre>` until ``` close, then a one-shot highlight swap). Performance under streaming is handled by AI SDK v6's `experimental_throttle` + React 19 `startTransition`-aware updates + block-level `React.memo()` of markdown segments (the AI SDK cookbook pattern). The Stop button uses a standard `AbortController` chain: `useChat.stop()` → `fetch` abort → Next route handler's `req.signal.aborted` → upstream `fetch` to FastAPI aborts → Phase 3's `request.is_disconnected()` polling cancels the OpenRouter HTTP request within 2 seconds (Phase 3 already proves the upstream half).

The first-run modal is driven by `GET /api/health` (proxy to `/api/v1/healthz`) — `adapters.openrouter.status === "missing_key"` blocks the composer and shows the modal; submission posts `{provider, key}` to `/api/settings` which proxies `PATCH /api/v1/settings`, then re-fetches `/api/health` to confirm `"ready"` before unblocking (Phase 3 D-15 already invalidates the lazy adapter cache on PATCH).

**Primary recommendation:** Use the canonical `assistant-ui/examples/with-ai-sdk-v6` starter as the structural template, but **REPLACE** the `streamText` route handler with a thin SSE proxy + translation layer (`apps/web/lib/sse-translate.ts`) that converts Phase 3's named events to AI SDK v6 UI Message Stream chunks. The translation layer is a pure function over a `ReadableStream<Uint8Array>` and is unit-tested in isolation against fixture event streams.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Scaffolding & Monorepo Shape (D-01 – D-05):**

- **D-01:** `apps/web/` is a sibling of `apps/api/`. Scaffolded with `pnpm create next-app@latest apps/web --typescript --tailwind --app --src-dir`. pnpm is the package manager. No `pnpm-workspace.yaml` needed yet; planner adds one if Phase 6 introduces a second JS package.
- **D-02:** Two-terminal dev orchestration. No `concurrently`, no Makefile target in Phase 4. README documents:
  ```
  Terminal 1: uvicorn apps.api.main:app --reload
  Terminal 2: pnpm --dir apps/web dev
  ```
- **D-03:** Tailwind CSS v4 + shadcn/ui (new-york style). shadcn primitives pulled in via `pnpm dlx shadcn@latest add ...` as needed; commit only what's used.
- **D-04:** Light mode only. No `next-themes`, no `prefers-color-scheme` switching.
- **D-05:** Env-var separation. `apps/web/.env.local` holds `FASTAPI_URL=http://localhost:8000` and any `NEXT_PUBLIC_*` browser-safe constants only. Repo-root `.env` stays Python/FastAPI-exclusive. `apps/web/.env.local` is added to `.gitignore` (already covered by existing `.env.local` rule, verified).

**Streaming Stack (D-06 – D-09):**

- **D-06:** `@assistant-ui/react` is the runtime root, fed by `@ai-sdk/react`'s `useChat` via `@assistant-ui/react-ai-sdk`'s `useChatRuntime` adapter. No custom runtime.
- **D-07:** Proxy at `apps/web/app/api/chat/route.ts` translates Phase 3 named events → AI SDK v5 UI Message Stream Protocol. **NOTE:** AI SDK is now at **v6** in the canonical assistant-ui example (CONTEXT wording says v5; the planner uses v6 — verified against the upstream starter; see Critical Finding #1 below). FastAPI side untouched.
- **D-08:** Next.js proxy strips AI SDK `{messages: [...]}` body to FastAPI's `{message: <latest user text>}`. FastAPI's `get_thread_messages` is the single source of truth for prior history.
- **D-09:** Cancellation chain — standard `AbortController` end-to-end, 2s budget asserted at three layers (Playwright browser→Next, httpx Next→FastAPI, existing Phase-3 FastAPI→OpenRouter). No new `POST /cancel` endpoint.

**Message Rendering (D-10 – D-15):**

- **D-10:** Markdown via `@assistant-ui/react-markdown`. `streamdown` rejected for v1.
- **D-11:** Code-block highlighting via `shiki` through assistant-ui's code-block primitive. Fence-state detection renders plain `<pre>` until ``` close, then one-time highlighted swap. Playwright assertion: DOM snapshots assert the inner `<code>` element's child structure changes exactly once per block.
- **D-12:** Routing chip above bubble, never collapsed. Content: `Routed to <display_name>` (bold) + `· <one-line rationale>`. Color-coded by backend.
- **D-13:** Per-turn metrics footer below the bubble. Mid-stream: `streaming…` with animated dot. Final: `$0.0021 · 1.4s · 312↑/847↓`. No mid-stream zero placeholders.
- **D-14:** ChatBubble hover-revealed action row: Copy-as-markdown + Regenerate (appends new turn).
- **D-15:** NEW SSE event type `routing_decision` emitted by `apps/api/routes/turn.py` BEFORE adapter dispatch. Payload = `RoutingDecision.signals`. Does NOT modify the Phase 2 ChatChunk Pydantic union. Contract test: event arrives within 100ms of POST AND byte-for-byte matches `Done.routing_signals`.

**First-Run Modal & Key Setup (D-16 – D-19):**

- **D-16:** Two independent missing-key triggers: (1) boot `GET /api/v1/healthz` → `adapters.openrouter.status === "missing_key"`; (2) any turn 400 / SSE `StreamError(code="auth_failed")`. Same modal component.
- **D-17:** Modal + persistent `/settings` route. Blocking on first-run, non-blocking from `/settings`.
- **D-18:** Browser POSTs `{provider, key}` to `apps/web/app/api/settings/route.ts`. Route handler forwards via `PATCH /api/v1/settings`. Key NEVER stored in cookies/localStorage/sessionStorage on Next side, never returned to browser, never written to disk on Next side. Response includes only the masked form (`sk-or-…ABC`). Regression test: zero literal-key matches across logs, response bodies, headers, cookies.
- **D-19:** Post-entry unblock — proxy re-fetches `GET /api/v1/healthz`. Chat unblocks only when `adapters.openrouter.status === "ready"`. No process reload — Phase 3 D-15 lazy adapter cache invalidation handles the rest. Toast: "OpenRouter connected — try a prompt!"

### Claude's Discretion

The planner / researcher own these:

- **Thread creation in minimal mode** — auto-create one default thread via `POST /api/v1/threads` on app boot. Store the returned `thread_id` in `localStorage` under key `prompt-optimizer.defaultThreadId`. Reuse across page reloads.
- **Composer behavior** — assistant-ui Composer defaults: Enter sends; Shift+Enter inserts newline; Cmd/Ctrl+K focuses composer.
- **StreamError UI surfacing** — red inline banner inside the assistant bubble with the error code + message + a "retry" button (when retriable=True).
- **Loading state on composer submit** — composer disables, send button shows a spinner, "Stop" button replaces "Send" once the first streamed chunk arrives.
- **shadcn component subset** — Button, Dialog, Input, Sonner.
- **Assistant message timestamps** — relative ("just now"); generated client-side from FastAPI-returned `created_at`, never from `Date.now()`.
- **Empty-state visual** — Phase 4 minimal: centered tagline + composer.
- **Network error handling on the proxy** — `ECONNREFUSED` returns 503; UI banner + 5s `/healthz` poll.
- **Default OpenRouter model on first turn** — `decide()` picks per the routing brain.
- **Composer placeholder** — "Type a message…".
- **Browser title** — `Prompt-Optimizer`.

### Deferred Ideas (OUT OF SCOPE)

- Thread sidebar (UI-02) — Phase 5.
- Multi-thread CRUD UI — Phase 5.
- Per-turn override slash commands `/openrouter`, `/code`, `/computer` (UI-05) — Phase 5.
- CodeBubble (UI-09), ComputerUseBubble (UI-10) — Phase 5.
- Backend availability status dots (UI-11) — Phase 5.
- Settings panel with per-backend enable/disable toggles + computer-use opt-in (UI-12) — Phase 5.
- Thread auto-rename from first user message (UI-14) — Phase 5 (Phase 3 D-17 already lit the rename endpoint).
- Thumbs-down feedback log (UI-15) — Phase 5.
- Empty-state sample prompts (UI-16) — Phase 5.
- Dark mode — Phase 6+ polish.
- `concurrently` / `make dev` orchestration — possibly Phase 6 OSS-02.
- Tailwind theme palette / design tokens — planner discretion if minor; v2 if a full design system.
- Explicit `POST /cancel` endpoint — rejected.
- `streamdown` — rejected for Phase 4; revisit only if assistant-ui-markdown shows streaming defects.
- `@ai-sdk/react` without `useChatRuntime` adapter — rejected.
- next-themes / OS-driven theme — deferred per D-04.
- Cookie-encrypted key cache on Next side — rejected per D-18.
- localStorage key storage — rejected; violates UI-17 + D-18.
- Hard reload after key submit — rejected; healthz round-trip per D-19 is cleaner.
- Mid-stream zero placeholders for metrics — rejected per D-13.
- Replace-on-regenerate UI — Phase 4 only appends.
- AI SDK v5/v6 UI Message Stream Protocol direct from FastAPI — rejected; FastAPI wire stays Phase 3 named-event canonical.
- Single repo-root `.env` shared by Python and Next — rejected per D-05.
- Composer mention/slash autocomplete — defer until Phase 5.
- File attachments / image uploads — REQUIREMENTS Out of Scope.
- Voice / audio input — REQUIREMENTS Out of Scope.
- Web search button in composer — Out of Scope.
- Public chat sharing — REQUIREMENTS Out of Scope.
- Per-thread cost display in sidebar — Phase 5.
- Streaming-aware diff renderer for FileDiff chunks — Phase 5 CodeBubble.
- Server-sent ping/keepalive UI indicator — sse-starlette `:ping` comments are silent at the EventSource layer.
- Custom 404 / error pages — Phase 6 polish.
- Browser-side analytics / telemetry — PROJECT.md Out of Scope.
- Mobile-responsive layout — out of scope for v1 (web-first).
- Tiktoken on Next side for live cost estimation — defer; cost comes from `Done.cost_usd`.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| UI-01 | Multi-turn chat input + scrolling message list using Next.js 15.2 + React 19 + AI SDK v5 + `@assistant-ui/react@>=0.10` | §"Standard Stack" pins current versions (Next 16.2.6, React 19.2.6, AI SDK 6.0.185, assistant-ui 0.14.5); §"Architecture Patterns Pattern 1" shows the `useChatRuntime` + `AssistantRuntimeProvider` + `Thread` setup |
| UI-03 | Streaming markdown rendering with code-block syntax highlighting that is streaming-safe (highlight on close fence, no per-token re-highlight) | §"Pattern 4 (Markdown rendering)" + §"Pattern 5 (No-flicker code blocks)" detail the assistant-ui code-block primitive + memoization + `experimental_throttle` |
| UI-04 | Routing chip + one-line rationale on every assistant message; always visible, never collapsed | §"Pattern 6 (Routing chip)" maps the new D-15 `routing_decision` SSE event → translated `data-routing-decision` AI SDK chunk → React subscription via `useThreadMessage.metadata` (or AI SDK `data` parts) |
| UI-06 | Stop / cancel mid-stream preserves partial response | §"Pattern 3 (AbortController chain)" + §"Pitfall 3 (useChat partial-loss on abort)" — `useChat.stop()` keeps the partial in `messages`; the Phase 3 `persist_turn(..., status="cancelled")` invariant preserves the partial DB-side |
| UI-07 | Per-turn cost (USD) + latency (ms) + token count alongside each assistant message | §"Pattern 7 (Metrics footer)" — read from the terminal `Done` chunk's `cost_usd` / `latency_ms` / `tokens_in` / `tokens_out` fields (Phase 2 D-04 + STORE-05 invariant) |
| UI-08 | `ChatBubble` renders OpenRouter responses — streamed markdown, copy-as-markdown, regenerate | §"Architecture Patterns Pattern 1" + UI-SPEC §8 cover the bubble structure; copy uses `navigator.clipboard.writeText` against the raw markdown source, regenerate uses `useChat.reload()` |
| UI-13 | First-run modal + missing-key setup screen guides clone-to-first-turn | §"Pattern 8 (First-run flow)" — shadcn Dialog + `/api/health` boot check + `PATCH /api/v1/settings` → re-fetch `/api/health` until `"ready"` |
| UI-17 | Next.js route handler proxies to FastAPI server-side; BYOK keys never travel browser ↔ FastAPI directly | §"Pattern 2 (SSE proxy architecture)" + §"Pattern 8" + §"Don't Hand-Roll: Direct browser→FastAPI calls"; isolation enforced by no `NEXT_PUBLIC_FASTAPI_URL` (server-only env var `FASTAPI_URL`) plus a Playwright network-assertion test |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Stack:** Python 3.10+ pipeline (preserved untouched) + Next.js / TypeScript / FastAPI web stack — both required.
- **Distribution:** Open-source, runnable locally. No hosted backend, no shared infra. README's two-terminal block is the ONLY documented orchestration in Phase 4.
- **Key handling:** Bring-your-own-keys. Keys never leave the user's local instance. The Next side never touches plaintext keys except in the request body to forward to FastAPI; FastAPI's `KeyStore` is canonical.
- **Optimization target:** Quality first, cost as tiebreaker — applies to the routing brain, not the UI; the chip just renders what `decide()` returned.
- **GSD Workflow Enforcement:** Use GSD commands; for Phase 4, this is `/gsd-execute-phase` and `/gsd-plan-phase` already in flight. No direct repo edits.
- **JS conventions (NEW for this phase — not yet established):**
  - TypeScript strict mode (default in `create-next-app`).
  - kebab-case for file paths (`apps/web/app/api/chat/route.ts`).
  - PascalCase for component files (`apps/web/components/RoutingChip.tsx`).
  - `apps/web/lib/*.ts` for pure functions (kebab-case file names).
  - Path discovery via Next's built-in `process.cwd()` + path module — not the Python `pathlib.Path(__file__).resolve().parents[N]` pattern.
  - No `os.path.join` equivalent gymnastics — Next handles paths via the bundler.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Single-input multi-turn chat (UI-01) | Browser / Client | Frontend Server (SSR initial paint) | Interactive chat is client-side React; SSR renders the empty shell |
| SSE streaming consumption (UI-03, UI-07) | Browser / Client | — | The browser's `useChat` consumes the AI SDK protocol; bubbles re-render as chunks arrive |
| SSE proxy + protocol translation (UI-17) | Frontend Server (route handler) | — | The Next.js Node-runtime route handler is the ONLY component that can both (a) talk to FastAPI server-side and (b) re-emit the AI SDK v6 wire — Edge runtime is wrong choice (see Pitfall 1) |
| BYOK key submission (UI-13, UI-17) | Frontend Server (route handler) | API / Backend (FastAPI KeyStore is canonical) | Browser never holds the key; the Next route handler is the proxy layer; FastAPI's `KeyStore` is the storage layer |
| Routing chip rendering (UI-04) | Browser / Client | — | The chip is a React component fed by the AI SDK `data-routing-decision` chunk delivered through the message metadata stream |
| Markdown + shiki rendering (UI-03, UI-08) | Browser / Client | — | Markdown parsing + shiki highlighting happen in the browser as chunks arrive; SSR would re-run on every token and defeat the streaming benefit |
| Stop button + AbortController (UI-06) | Browser / Client | Frontend Server (relay) + API/Backend (cancel observer) | Browser fires `AbortController.abort()`; Next route's `req.signal` propagates to its upstream `fetch`; FastAPI's `request.is_disconnected()` polling tears down the OpenRouter HTTP request |
| Healthz + settings round-trip (UI-13) | Frontend Server (route handler) | API / Backend (auth on adapters) | All FastAPI calls go through Next route handlers (UI-17); browser only sees `/api/health` and `/api/settings` |
| Thread CRUD (default-thread auto-create) | Frontend Server (route handler on first render) | API / Backend (`POST /api/v1/threads`) | Auto-create on first boot, persist ID in `localStorage`; Phase 5 sidebar replaces this with full CRUD UI |
| Markdown body memoization | Browser / Client | — | React.memo on parsed-block components; AI SDK `experimental_throttle` limits update rate |
| Playwright E2E + unit tests | Build / Static | — | Tests live in `apps/web/`; spin up `uvicorn` + `next dev` via Playwright web-server config |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `next` | **16.2.6** (latest; CONTEXT-pinned `15.2.x` is stale — see Critical Finding #1) | App Router + route handlers + Node runtime + server components | Canonical Next; assistant-ui starter uses 16.2.4 `[VERIFIED: registry.npmjs.org/next/latest]` |
| `react` | **19.2.6** | React 19 concurrent features (Suspense, `startTransition`, hydration) | Required by assistant-ui 0.14+ and AI SDK 6 `[VERIFIED: registry.npmjs.org/react/latest]` |
| `react-dom` | **19.2.6** | React DOM | Pair with react `[VERIFIED]` |
| `typescript` | **5.x** (CONTEXT pin) or **6.0.3** (assistant-ui starter) | Type system | Strict mode on by Next default; planner picks one version and pins. Recommend **5.x stable** to avoid TS 6 alpha surface area in Phase 4 `[CITED: assistant-ui example uses 6.0.3, but Next 16 supports both]` |
| `tailwindcss` | **4.3.0** (latest 4.x) | Utility CSS | Tailwind v4 CSS-first config, no JS config file in shadcn new-york preset `[VERIFIED: registry.npmjs.org/tailwindcss/latest]` |
| `@tailwindcss/postcss` | **^4.2.4** | PostCSS plugin (Tailwind v4 ships as PostCSS plugin, not a CLI) | Required for Tailwind v4 with Next.js `[CITED: assistant-ui starter package.json]` |
| `postcss` | **^8.5.14** | CSS processor | Tailwind v4 prerequisite `[CITED]` |

### AI / Streaming

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `ai` | **^6.0.175** (`6.0.185` is current latest) | AI SDK core — `createUIMessageStream`, `createUIMessageStreamResponse`, UI Message Stream Protocol types | The protocol Phase 4's proxy emits to the browser. CONTEXT D-07 said "v5"; the assistant-ui canonical example is **v6**. See Critical Finding #1. `[VERIFIED: registry.npmjs.org/ai/latest + assistant-ui example]` |
| `@ai-sdk/react` | **^3.0.187** | `useChat` hook + `DefaultChatTransport` | The transport that drives the runtime. CONTEXT pinned `>=2`; current is 3.x. `[VERIFIED: registry.npmjs.org/@ai-sdk/react/latest]` |
| `@assistant-ui/react` | **^0.14.5** | Thread / Composer / MessagePrimitive primitives + `AssistantRuntimeProvider` | The runtime root per D-06 `[VERIFIED: registry.npmjs.org/@assistant-ui/react/latest]` |
| `@assistant-ui/react-ai-sdk` | **^1.3.26** | `useChatRuntime` adapter + `AssistantChatTransport` (the v6 transport that auto-forwards system messages and frontend tools) | Bridges `useChat` to the assistant-ui runtime per D-06 `[VERIFIED: registry.npmjs.org/@assistant-ui/react-ai-sdk/latest]` |
| `@assistant-ui/react-markdown` | **^0.14.0** | Markdown renderer integrated with `MessagePrimitive.Content`; wraps `react-markdown@^10` internally | The assistant-ui-native markdown choice per D-10 `[VERIFIED: registry.npmjs.org/@assistant-ui/react-markdown/latest]` |
| `shiki` | **^4.0.2** | Syntax highlighting for code blocks | Bundled by the assistant-ui code-block primitive per D-11 `[VERIFIED: registry.npmjs.org/shiki/latest]` |

### UI Primitives & Utilities

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| shadcn/ui (CLI-installed components: `button`, `dialog`, `input`, `sonner`) | `pnpm dlx shadcn@latest add ...` | Composable Radix-based primitives; new-york style per UI-SPEC §1 | The de facto Radix wrapper in 2026; no npm install — components are copy-pasted into `apps/web/components/ui/` `[CITED: ui.shadcn.com]` |
| `lucide-react` | **^1.14.0** | Icon set (gear, stop, send, copy, refresh, AlertCircle, WifiOff) | Standard with shadcn/ui; assistant-ui starter uses it `[CITED: assistant-ui example]` |
| `sonner` | (via shadcn) | Toast notifications | UI-SPEC §10.5 + §17 declare specific toast strings `[CITED: UI-SPEC]` |
| `clsx` | **^2.1.1** | Conditional class names | shadcn `cn()` helper dependency `[CITED]` |
| `tailwind-merge` | **^3.5.0** | Tailwind class merging | shadcn `cn()` helper dependency `[CITED]` |
| `class-variance-authority` | **^0.7.1** | Variant prop helper | shadcn pattern (used for button variants etc.) `[CITED: assistant-ui example]` |
| `zod` | **^4.4.3** | Schema validation at the route handler boundary (Validation Architecture §11) | Standard TS schema lib in 2026 `[VERIFIED: registry.npmjs.org/zod/latest]` |

### Testing

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `@playwright/test` | **^1.60.0** | E2E tests (no-flicker, cancel-budget, first-run, secure-key, browser-isolation) | Canonical E2E for Next.js; UI-SPEC declares the four specs `[VERIFIED: registry.npmjs.org/@playwright/test/latest]` |
| `vitest` | **^4.1.6** | Unit tests (the pure-function SSE translator + small helpers) | Standard for Next.js / Vite-ecosystem unit tests; faster than Jest for TS-heavy projects `[VERIFIED: registry.npmjs.org/vitest/latest]` |
| `@testing-library/react` | (latest 16.x at time of install) | Component tests (FirstRunModal interaction, MetricsFooter rendering) | Standard React component testing `[ASSUMED — verified before install]` |
| `@testing-library/jest-dom` | (latest) | DOM matchers for Vitest | Pairs with @testing-library/react `[ASSUMED]` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `@assistant-ui/react-markdown` | `streamdown` (v2.5.0; vercel's drop-in for react-markdown with built-in shiki + incomplete-markdown auto-close) | Streamdown is genuinely strong for raw `useChat` + `react-markdown` setups but the CONTEXT D-10 rejection stands: assistant-ui's MessagePrimitive expects its own markdown wrapper for component-map injection. Streamdown would force a parallel rendering path. Revisit only if assistant-ui-markdown shows defects. |
| `react-syntax-highlighter` | `shiki` | shiki produces correct VS Code-quality highlighting; react-syntax-highlighter is heavier and ships its own theme system that conflicts with shadcn. shiki + assistant-ui primitive is the documented path. |
| `react-syntax-highlighter` | `highlight.js` | Smaller bundle but cruder highlighting. shiki wins on quality and is shadcn-native. |
| `useChat` (raw, no assistant-ui) | `@assistant-ui/react` runtime root | Rejected by D-06. Phase 5 needs bubble extensibility (CodeBubble, ComputerUseBubble); raw `useChat` would force a rewrite. |
| `EventSource` (browser native) | `fetch` + `ReadableStream` (used internally by `useChat`) | EventSource is GET-only and cannot send a JSON body. Phase 4 needs POST. The AI SDK handles this internally; we never touch EventSource. |
| `@microsoft/fetch-event-source` (browser client SSE) | `useChat` (internal AI SDK transport) | Adopted only if we bypass the AI SDK. Since the AI SDK is the runtime per D-06, we never need this. (Mentioned for completeness — the SSE proxy on the *server* side reads upstream FastAPI SSE using Node's native `fetch` + `response.body.getReader()`, not this library.) |
| `Vercel deploy` + Edge runtime | Node runtime (`export const runtime = 'nodejs'`) | Edge runtime cannot reliably proxy long-lived SSE to a non-Vercel upstream; buffering issues + lack of `fetch` request streaming support in some Edge environments. Local-only deployment makes this moot, but the runtime declaration matters — see Pitfall 1. |
| `EventEmitter` / Server-Sent Events from a Next API route | The proxy pattern (this phase) | The FastAPI side is canonical (Phase 3 D-07). The Next route is a thin translator, not a source. |
| Hand-rolled markdown lib | `react-markdown` (via assistant-ui-react-markdown) | Cosmic complexity. Wouldn't ship in any reasonable Phase 4 timeline. |
| Server-side render of routing chip | Client-side render | The chip arrives via the AI SDK stream's metadata; SSR has no access. Client-only. |
| `next-themes` for dark mode | Light-mode-only | Rejected per D-04. |

**Installation:**
```bash
# Scaffolding (one-time)
pnpm create next-app@latest apps/web --typescript --tailwind --app --src-dir

# Inside apps/web/
cd apps/web
pnpm add ai @ai-sdk/react @assistant-ui/react @assistant-ui/react-ai-sdk @assistant-ui/react-markdown shiki zod
pnpm add lucide-react clsx tailwind-merge class-variance-authority

# shadcn components (these are not npm installs — they're code generation)
pnpm dlx shadcn@latest init
pnpm dlx shadcn@latest add button dialog input sonner

# Testing
pnpm add -D @playwright/test vitest @testing-library/react @testing-library/jest-dom @vitejs/plugin-react jsdom
pnpm exec playwright install chromium
```

**Version verification:** Versions confirmed via npm registry (`registry.npmjs.org/<pkg>/latest`) on 2026-05-18. The CONTEXT D-07 wording references "AI SDK v5" — the current canonical assistant-ui example is **AI SDK v6** (verified via the `assistant-ui/examples/with-ai-sdk-v6/package.json`). This drift is **Critical Finding #1** below; the planner uses v6.

## Critical Findings (Read Before Writing Tasks)

### Critical Finding #1: CONTEXT pins are stale — current ecosystem is Next 16 / React 19 / AI SDK v6, not Next 15.2 / React 19 / AI SDK v5

CONTEXT canonical_refs lists:
- `next@15.2.x`
- `@ai-sdk/react@>=2`
- `@assistant-ui/react@>=0.10`

The npm registry says (2026-05-18):
- `next@16.2.6` (latest); assistant-ui v6 example uses `^16.2.4` `[VERIFIED]`
- `react@19.2.6` (latest); assistant-ui example uses `^19.2.5` `[VERIFIED]`
- `@ai-sdk/react@3.0.187` (latest) `[VERIFIED]`
- `ai@6.0.185` (latest); assistant-ui v6 example uses `^6.0.175` `[VERIFIED]`
- `@assistant-ui/react@0.14.5` (latest) `[VERIFIED]`

**Implication:** the CONTEXT-locked versions ARE compatible (Next 15.2 + React 19 + AI SDK v5 + assistant-ui 0.10 was a valid stack at CONTEXT-gathering time). But the assistant-ui project has shipped a **v6 starter** at `examples/with-ai-sdk-v6` that is now the canonical reference. AI SDK v5 → v6 changed the UI Message Stream Protocol shape (named chunks like `text-delta` with `id`/`delta`, not numeric prefixes); the protocol the proxy emits depends on which AI SDK major the client uses.

**Recommendation to planner:** Adopt the **current** stack (Next 16 / React 19.2 / AI SDK v6 / assistant-ui 0.14). The CONTEXT pinning was a floor; current versions satisfy the floor. Document the version bump as a planning decision (it does not require a new discuss-phase round because no architecture changes — just version uplift).

**Action items for planner:**
1. Write the Wave 0 scaffolding task with current versions.
2. Use the `with-ai-sdk-v6` example structure (NOT the older `with-ai-sdk` v4/v5 examples).
3. The SSE translation layer emits **AI SDK v6** UI Message Stream chunks (see Pattern 2 below for the exact shape).
4. Add a `## Open Question` to the plan: confirm the version bump with the user during execution if any concern, but no blocker.

### Critical Finding #2: ROADMAP SC #3 says "preserved on screen and persisted to SQLite with `status='complete'`" — but Phase 3 actually writes `status='cancelled'` for stop scenarios

Phase 3's `apps/api/routes/turn.py` cancellation handler (lines 496-514) explicitly emits `StreamError(code="cancelled")` + `Done` on `asyncio.CancelledError`, and `apps/api/db/queries.py:persist_turn` (line 348-516) derives `status` from the buffered StreamError code — so a stop produces `status="cancelled"` (not `"complete"`). The CHECK constraint `CHECK (status IN ('complete','error','cancelled'))` (Phase 3 schema) confirms `cancelled` is a first-class status.

**ROADMAP SC #3 wording is loose:** "preserved and persisted to SQLite with `status='complete'` (or `'error'` if the abort happens before any text arrived)". The actual Phase 3 invariant is:
- Stop with text already streamed → `status="cancelled"` (Phase 3 D-19 turn_done log includes this; Phase 2 D-06 `StreamError.code = "cancelled"` is closed-vocabulary literal).
- Stop before any text → `status="cancelled"` too (the cancellation handler runs regardless of whether `TextDelta` has been seen — the `asyncio.CancelledError` triggers from the `async for chunk in adapter.stream()` loop).
- `status="error"` is reserved for adapter-emitted StreamError with codes OTHER than `cancelled` (e.g., `cost_cap_exceeded`, `auth_failed`).

**Recommendation to planner:**
1. Treat the ROADMAP wording as approximate. The Playwright assertion should assert the partial assistant message is visible AND that the DB row for the assistant message has `status IN ('cancelled', 'complete', 'error')` — i.e., one of the three valid terminal statuses.
2. The specific Phase 4 behavior the user-facing SC really cares about is **"partial message stays on screen + the metrics footer shows what was buffered"** — the DB status string is implementation detail.
3. Flag this as an ASSUMED claim that the user/planner should confirm if they intended `cancelled` as the canonical stop status, OR if they want to amend Phase 3 to write `complete` on stop-with-text. Recommend the former (`cancelled` is more honest).

### Critical Finding #3: The proxy MUST run on Node runtime, NOT Edge runtime

Edge runtime has two SSE-killing limitations for this use case:
1. The Edge runtime in Next.js 16 supports streaming responses, but **proxying an upstream `fetch` SSE stream to a long-lived downstream SSE response is unreliable on Edge** because Edge environments buffer or terminate connections at platform-imposed durations (Vercel's Edge limit is 25s; Cloudflare Workers ~30s). Local-dev `next dev` uses a Node-like Edge polyfill but production Edge would silently break.
2. AbortSignal propagation from `request.signal` to upstream `fetch(req.signal)` is known to have edge cases on Edge (vercel/next.js#50364). Node runtime has stable behavior.

**Decision (pinned):** `export const runtime = 'nodejs'` + `export const dynamic = 'force-dynamic'` at the top of `apps/web/app/api/chat/route.ts`. Same for `/api/settings` and `/api/health` route handlers.

**Source:** Next.js docs explicitly recommend Node runtime for streaming; multiple GitHub discussions (vercel/next.js#48427, #50614, #61972) confirm SSE proxy patterns require Node runtime + force-dynamic. `[VERIFIED: github.com/vercel/next.js/discussions/48427 + nextjs.org/docs/app/getting-started/route-handlers]`

### Critical Finding #4: The SSE proxy must `return new Response(stream)` IMMEDIATELY — async work happens INSIDE the stream's `start()`/pull loop

If the route handler `await`s the upstream stream before returning the `Response`, Next.js buffers the entire response until the handler resolves — defeating SSE entirely. The pattern is:

```typescript
export async function POST(req: Request) {
  const upstream = await fetch(`${FASTAPI_URL}/api/v1/threads/${threadId}/turn`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: latestUserText }),
    signal: req.signal,  // CRITICAL: AbortController chain
  });

  if (!upstream.ok || !upstream.body) {
    return new Response(JSON.stringify({ error: '...' }), { status: upstream.status });
  }

  // Translate inside a ReadableStream so chunks flow as they arrive
  const translatedStream = translateNamedSSEToUIMessageStream(upstream.body);

  return new Response(translatedStream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      'Connection': 'keep-alive',
      'X-Accel-Buffering': 'no',  // disable nginx buffering if behind a proxy
      'x-vercel-ai-ui-message-stream': 'v1',  // AI SDK v6 client expects this header
    },
  });
}
```

The translator (`apps/web/lib/sse-translate.ts`) is a pure function `(input: ReadableStream<Uint8Array>) => ReadableStream<Uint8Array>` that pipes chunks through a `TransformStream`. See Pattern 2 below.

**Source:** medium.com/@oyetoketoby80/fixing-slow-sse... + multiple Next.js discussions. `[CITED]`

## Architecture Patterns

### System Architecture Diagram

```
Browser (apps/web client)                Frontend Server (Next route handler)              API/Backend (FastAPI — Phase 3)              External (OpenRouter)
─────────────────────────                ────────────────────────────────────              ─────────────────────────────                 ────────────────────────

┌─────────────────────┐                  ┌─────────────────────────────────┐               ┌──────────────────────────────┐               ┌──────────────────────┐
│ AssistantRuntime    │                  │ /api/chat/route.ts              │               │ POST /api/v1/threads/{id}/  │               │ /v1/chat/            │
│ Provider            │                  │  (runtime='nodejs')             │               │ turn (EventSourceResponse)  │               │ completions          │
│                     │                  │                                  │               │                              │               │ stream=true          │
│  ├─ useChatRuntime  │  POST            │  1. Read JSON body              │  POST         │  1. decide() to_thread       │  HTTPS        │                      │
│  │   via Assistant- │  ──fetch──▶      │  2. messages.slice(-1)          │  ──fetch──▶   │  2. emit routing_decision   │  ──stream──▶  │ stream chunks back   │
│  │   ChatTransport  │  (req.signal)    │  3. {message: <latest>}         │  (signal)     │  3. adapter.stream()         │               │                      │
│  │                  │                  │                                  │               │  4. yield named SSE events   │               │                      │
│  ├─ Thread          │                  │  4. fetch(FASTAPI_URL, signal)  │               │     event: routing_decision  │               │                      │
│  │  ├─ MessageList  │  SSE             │  5. translate to AI SDK v6      │  SSE          │     event: text_delta        │  SSE chunks   │                      │
│  │  ├─ Composer     │  ◀────stream──── │     UI Message Stream chunks    │  ◀──stream─── │     event: done              │  ◀────────    │                      │
│  │  └─ FirstRunModal│                  │  6. return Response(stream)     │               │                              │               │                      │
│  │                  │                  │                                  │               │  5. buffer in memory         │               │                      │
│  └─ Components:     │  Stop click      │  AbortController chain:         │  upstream     │  6. on Done → persist_turn  │               │                      │
│      RoutingChip    │  ──abort()──▶    │  req.signal.aborted →           │  ──abort──▶   │     (one BEGIN/COMMIT)       │               │                      │
│      MetricsFooter  │                  │  upstream fetch aborts          │               │  7. is_disconnected()        │  cancel       │                      │
│      ChatBubble     │                  │                                  │               │     polling → cancel adapter │  ──────▶      │                      │
│                     │                  │                                  │               │     (within 2s — Phase 3)    │               │                      │
└─────────────────────┘                  │                                  │               │                              │               │                      │
                                          │                                  │               │                              │               │                      │
                                          │ /api/settings/route.ts          │  PATCH        │ PATCH /api/v1/settings       │               │                      │
                                          │  ──forward {provider,key}──▶    │  ──fetch──▶   │  KeyStore.set()              │               │                      │
                                          │  ◀──return masked──────────     │  ◀──masked─── │  clear adapter cache         │               │                      │
                                          │                                  │               │                              │               │                      │
                                          │ /api/health/route.ts            │  GET          │ GET /api/v1/healthz          │               │                      │
                                          │  ──forward───▶                  │  ──fetch──▶   │  adapter status check         │               │                      │
                                          │  ◀────────                      │  ◀───────     │   (read-only)                 │               │                      │
                                          └─────────────────────────────────┘               └──────────────────────────────┘               └──────────────────────┘

Browser network panel observation (UI-17 invariant):
  - GET  http://localhost:3000/                      (Next page)
  - GET  http://localhost:3000/_next/static/...      (Next assets)
  - GET  http://localhost:3000/api/health            (boot check)
  - POST http://localhost:3000/api/settings          (first-run key entry)
  - POST http://localhost:3000/api/chat              (each turn)
  - 0 connections to http://localhost:8000           (FastAPI is invisible to browser)
```

### Recommended Project Structure

```
apps/web/
├── app/
│   ├── layout.tsx                          # Root layout: Tailwind, fonts, AssistantRuntimeProvider mount, Sonner Toaster
│   ├── page.tsx                            # Chat surface: header + thread + composer + first-run modal trigger
│   ├── settings/
│   │   └── page.tsx                        # Non-blocking key management — reuses KeyForm component
│   └── api/
│       ├── chat/
│       │   └── route.ts                    # SSE proxy (D-07) — runtime='nodejs', dynamic='force-dynamic'
│       ├── settings/
│       │   └── route.ts                    # Key submission proxy (D-18) — forwards PATCH /api/v1/settings
│       └── health/
│           └── route.ts                    # /healthz pass-through used by D-16 boot check
├── components/
│   ├── ui/                                 # shadcn-installed primitives (button, dialog, input, sonner)
│   ├── RoutingChip.tsx                     # D-12 — color-coded chip, ARIA role="status"
│   ├── MetricsFooter.tsx                   # D-13 — mid-stream + final formatting
│   ├── FirstRunModal.tsx                   # D-17 — Dialog + KeyForm (blocking mode)
│   ├── KeyForm.tsx                         # Shared input + submit — used by modal AND /settings
│   ├── ChatBubble.tsx                      # UI-08 — assistant bubble with action row + markdown body
│   ├── StreamErrorBanner.tsx               # §12 of UI-SPEC — red banner with retry
│   ├── NetworkDownBanner.tsx               # §13 of UI-SPEC — 503 banner above composer
│   └── EmptyState.tsx                      # §11 of UI-SPEC — centered tagline
├── lib/
│   ├── sse-translate.ts                    # D-07 named-event → AI SDK v6 UI Message Stream — pure function, unit-tested
│   ├── api-client.ts                       # Typed wrappers for the three proxy routes
│   ├── thread-id.ts                        # Default-thread auto-create + localStorage persistence
│   ├── chunk-schemas.ts                    # Zod schemas for incoming Phase-3 SSE events (Validation Architecture)
│   ├── markdown-components.tsx             # Component map for @assistant-ui/react-markdown (block-memoized)
│   └── cn.ts                               # shadcn `cn()` helper (clsx + tailwind-merge)
├── tests/
│   ├── sse-translate.test.ts               # Vitest — translation pure function vs fixture event streams
│   ├── chunk-schemas.test.ts               # Vitest — Zod schema parses every Phase-3 event shape
│   ├── routing-chip.test.tsx               # RTL — chip renders backend-color + ARIA
│   └── metrics-footer.test.tsx             # RTL — streaming and final states
├── playwright/
│   ├── playwright.config.ts                # webServer config to spin up uvicorn + next dev
│   ├── no-flicker.spec.ts                  # D-11 highlight-once assertion (DOM snapshot diff)
│   ├── cancel-budget.spec.ts               # D-09 layer-1 (2s budget browser→Next)
│   ├── first-run.spec.ts                   # D-16/D-17 modal flow
│   ├── secure-key.spec.ts                  # D-18 zero-match key-scrub regression
│   └── browser-isolation.spec.ts           # UI-17 — no localhost:8000 hits from browser
├── package.json
├── pnpm-lock.yaml
├── tsconfig.json
├── next.config.ts
├── tailwind.config.ts                       # Tailwind v4 minimal; CSS-first preferred
├── postcss.config.mjs
├── components.json                          # shadcn config (style: new-york, baseColor: slate)
├── .env.example                             # FASTAPI_URL=http://localhost:8000
├── .env.local                               # (gitignored)
└── vitest.config.ts                         # Vitest config — jsdom environment, RTL setup
```

### Pattern 1: assistant-ui + AI SDK v6 runtime mounting

**What:** The runtime is created in a client component via `useChatRuntime` and passed to `AssistantRuntimeProvider`. The `Thread` component reads from the runtime via context.

**When to use:** Once at the top of the chat page (Phase 4: `apps/web/app/page.tsx` or a dedicated `<Chat>` client component).

**Example:**
```tsx
// apps/web/app/page.tsx  (or apps/web/components/Chat.tsx + "use client")
"use client";

import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useChatRuntime, AssistantChatTransport } from "@assistant-ui/react-ai-sdk";
import { Thread } from "@/components/assistant-ui/thread";

export default function ChatPage() {
  const runtime = useChatRuntime({
    transport: new AssistantChatTransport({
      api: "/api/chat",
      // CRITICAL — strip messages to last user text before POSTing to FastAPI (D-08).
      // The Next route handler will further validate, but this saves bandwidth.
      prepareSendMessagesRequest: ({ messages }) => ({
        body: {
          // Send the full UI message array; the route handler picks last user text.
          messages,
        },
      }),
    }),
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <Thread />
    </AssistantRuntimeProvider>
  );
}
```

**Source:** `[CITED: assistant-ui/examples/with-ai-sdk-v6 + ai-sdk.dev/docs/ai-sdk-ui/transport]`

### Pattern 2: SSE proxy — Phase-3 named events → AI SDK v6 UI Message Stream

**What:** A `TransformStream` reads upstream `event: <type>\ndata: <JSON>\n\n` blocks and emits AI SDK v6 `data: {JSON}\n\n` chunks with the v6 chunk-type vocabulary.

**Phase 3 wire (input) — closed event-name vocabulary** (Phase 3 D-07 + Phase 2 D-01):
- `event: routing_decision` — Phase 4 D-15 new event, data = `RoutingDecision.signals` dict
- `event: text_delta` — data = `{type, text}`
- `event: tool_call` — data = `{type, tool_call_id, tool_name, arguments}`
- `event: tool_result` — data = `{type, tool_call_id, content, is_error}`
- `event: file_diff` — data = `{type, tool_call_id, path, diff, operation}`
- `event: screenshot` — data = `{type, step, image_b64?, image_ref?, image_format}`
- `event: stream_error` — data = `{type, code, message, retriable}`
- `event: done` — data = `{type, tokens_in?, tokens_out?, cost_usd?, latency_ms?, routing_signals?}`

**AI SDK v6 UI Message Stream (output) — wire shape** `[CITED: ai-sdk.dev/docs/ai-sdk-ui/stream-protocol]`:
- `data: {"type":"start","messageId":"<id>"}\n\n`
- `data: {"type":"text-start","id":"<text-id>"}\n\n` (open a text part — must precede any text-delta)
- `data: {"type":"text-delta","id":"<text-id>","delta":"<text>"}\n\n` (append; `id` must match)
- `data: {"type":"text-end","id":"<text-id>"}\n\n` (close text part)
- `data: {"type":"data-routing","data":{...RoutingSignals...}}\n\n` (CUSTOM data part for the chip; v6 supports `data-*` arbitrary types)
- `data: {"type":"data-metrics","data":{"cost_usd":...,"latency_ms":...,"tokens_in":...,"tokens_out":...}}\n\n` (CUSTOM, emitted on Done)
- `data: {"type":"error","errorText":"<message>"}\n\n` (on StreamError)
- `data: {"type":"abort","reason":"cancelled"}\n\n` (on StreamError code=cancelled — v6 has a specific abort chunk)
- `data: {"type":"finish"}\n\n` (always last)
- `data: [DONE]\n\n` (terminator per protocol)

**Translation mapping (Phase 4's central contract):**

| Phase 3 event | AI SDK v6 emission |
|---------------|---------------------|
| `routing_decision` | Emit `{type: "start", messageId}` (first event) + `{type: "data-routing", data: signals}` — chip component subscribes to message metadata `data-routing` field |
| First `text_delta` after `routing_decision` | If text part not yet opened: emit `{type: "text-start", id: "t-0"}`, then `{type: "text-delta", id: "t-0", delta: text}`. Subsequent text_deltas reuse the same id. |
| `text_delta` (Nth) | `{type: "text-delta", id: "t-0", delta: text}` |
| `tool_call` / `tool_result` / `file_diff` / `screenshot` | **Phase 4 IGNORES these gracefully** (OpenRouter only emits text_delta + done). Pass through as `{type: "data-tool", data: chunk}` for forward-compat with Phase 5; assistant-ui ignores unrecognised `data-*` types without error. |
| `stream_error` with `code !== "cancelled"` | Emit `{type: "text-end", id: "t-0"}` (close any open text part) + `{type: "error", errorText: <user-friendly message from UI-SPEC §12.2 catalog>}` |
| `stream_error` with `code === "cancelled"` | Emit `{type: "text-end", id: "t-0"}` + `{type: "abort", reason: "cancelled"}` |
| `done` | Emit `{type: "text-end", id: "t-0"}` (close text part) + `{type: "data-metrics", data: {cost_usd, latency_ms, tokens_in, tokens_out}}` + `{type: "finish"}` + literal `data: [DONE]\n\n` |

**Reference implementation skeleton (the planner extends this in Wave 1):**

```typescript
// apps/web/lib/sse-translate.ts
import { z } from "zod";

// Closed vocabulary — mirrors Phase 2 D-01 and Phase 3 D-07 + Phase 4 D-15.
const NamedSSEEventSchema = z.discriminatedUnion("event", [
  z.object({ event: z.literal("routing_decision"), data: z.record(z.unknown()) }),
  z.object({ event: z.literal("text_delta"), data: z.object({ type: z.literal("text_delta"), text: z.string() }) }),
  z.object({ event: z.literal("tool_call"), data: z.object({ type: z.literal("tool_call"), tool_call_id: z.string(), tool_name: z.string(), arguments: z.record(z.unknown()) }) }),
  z.object({ event: z.literal("tool_result"), data: z.object({ type: z.literal("tool_result"), tool_call_id: z.string(), content: z.union([z.string(), z.record(z.unknown())]), is_error: z.boolean() }) }),
  z.object({ event: z.literal("file_diff"), data: z.object({ type: z.literal("file_diff"), tool_call_id: z.string(), path: z.string(), diff: z.string(), operation: z.enum(["create","edit","delete"]) }) }),
  z.object({ event: z.literal("screenshot"), data: z.object({ type: z.literal("screenshot"), step: z.number(), image_b64: z.string().nullable().optional(), image_ref: z.string().nullable().optional(), image_format: z.enum(["png","jpeg"]) }) }),
  z.object({ event: z.literal("stream_error"), data: z.object({ type: z.literal("stream_error"), code: z.enum(["cost_cap_exceeded","step_cap_exceeded","cancelled","rate_limited","auth_failed","provider_unavailable","timeout","validation_error","internal_error"]), message: z.string(), retriable: z.boolean() }) }),
  z.object({ event: z.literal("done"), data: z.object({ type: z.literal("done"), tokens_in: z.number().nullable().optional(), tokens_out: z.number().nullable().optional(), cost_usd: z.number().nullable().optional(), latency_ms: z.number().nullable().optional(), routing_signals: z.record(z.unknown()).nullable().optional() }) }),
]);

export function translateNamedSSEToUIMessageStream(
  upstream: ReadableStream<Uint8Array>,
): ReadableStream<Uint8Array> {
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  let buffer = "";
  let messageStarted = false;
  let textPartOpen = false;
  const messageId = `m-${crypto.randomUUID()}`;
  const textPartId = "t-0";

  function emit(chunk: object): Uint8Array {
    return encoder.encode(`data: ${JSON.stringify(chunk)}\n\n`);
  }

  return new ReadableStream({
    async start(controller) {
      const reader = upstream.getReader();
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          // SSE blocks are separated by \n\n.
          let blockEnd: number;
          while ((blockEnd = buffer.indexOf("\n\n")) !== -1) {
            const block = buffer.slice(0, blockEnd);
            buffer = buffer.slice(blockEnd + 2);
            if (!block.trim() || block.startsWith(":")) continue; // skip empty + comments (heartbeats)

            // Parse event:/data: lines
            let event = "";
            const dataLines: string[] = [];
            for (const line of block.split("\n")) {
              if (line.startsWith("event: ")) event = line.slice(7).trim();
              else if (line.startsWith("data: ")) dataLines.push(line.slice(6));
            }
            if (!event || !dataLines.length) continue;

            let parsed;
            try {
              parsed = NamedSSEEventSchema.parse({
                event,
                data: JSON.parse(dataLines.join("\n")),
              });
            } catch (err) {
              controller.enqueue(emit({ type: "error", errorText: `Malformed upstream event: ${event}` }));
              continue;
            }

            // Translate to AI SDK v6 chunks.
            switch (parsed.event) {
              case "routing_decision":
                if (!messageStarted) {
                  controller.enqueue(emit({ type: "start", messageId }));
                  messageStarted = true;
                }
                controller.enqueue(emit({ type: "data-routing", data: parsed.data }));
                break;
              case "text_delta":
                if (!messageStarted) {
                  controller.enqueue(emit({ type: "start", messageId }));
                  messageStarted = true;
                }
                if (!textPartOpen) {
                  controller.enqueue(emit({ type: "text-start", id: textPartId }));
                  textPartOpen = true;
                }
                controller.enqueue(emit({ type: "text-delta", id: textPartId, delta: parsed.data.text }));
                break;
              case "stream_error":
                if (textPartOpen) {
                  controller.enqueue(emit({ type: "text-end", id: textPartId }));
                  textPartOpen = false;
                }
                if (parsed.data.code === "cancelled") {
                  controller.enqueue(emit({ type: "abort", reason: "cancelled" }));
                } else {
                  // Map to UI-SPEC §12.2 friendly message at the component layer; pass code through.
                  controller.enqueue(emit({ type: "error", errorText: parsed.data.message, /* extra: */ code: parsed.data.code, retriable: parsed.data.retriable }));
                }
                break;
              case "done":
                if (textPartOpen) {
                  controller.enqueue(emit({ type: "text-end", id: textPartId }));
                  textPartOpen = false;
                }
                controller.enqueue(emit({ type: "data-metrics", data: {
                  cost_usd: parsed.data.cost_usd ?? null,
                  latency_ms: parsed.data.latency_ms ?? null,
                  tokens_in: parsed.data.tokens_in ?? null,
                  tokens_out: parsed.data.tokens_out ?? null,
                }}));
                controller.enqueue(emit({ type: "finish" }));
                controller.enqueue(encoder.encode("data: [DONE]\n\n"));
                break;
              // tool_call / tool_result / file_diff / screenshot: forward as data-tool for Phase 5
              default:
                controller.enqueue(emit({ type: `data-${parsed.event}`, data: parsed.data }));
            }
          }
        }
        controller.close();
      } catch (err) {
        controller.error(err);
      } finally {
        reader.releaseLock();
      }
    },
  });
}
```

**The route handler is then tiny:**

```typescript
// apps/web/app/api/chat/route.ts
import { translateNamedSSEToUIMessageStream } from "@/lib/sse-translate";
import { getOrCreateDefaultThread } from "@/lib/thread-id";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";

export async function POST(req: Request) {
  const body = await req.json();
  // D-08: strip to {message: <latest user text>} — FastAPI's get_thread_messages is the truth.
  const lastUserMessage = [...(body.messages ?? [])].reverse().find((m: any) => m.role === "user");
  const userText = lastUserMessage?.parts?.find((p: any) => p.type === "text")?.text
    ?? lastUserMessage?.content
    ?? "";

  const threadId = await getOrCreateDefaultThread(); // calls POST /api/v1/threads via /api/health proxy or direct server-to-server fetch

  let upstream: Response;
  try {
    upstream = await fetch(`${FASTAPI_URL}/api/v1/threads/${threadId}/turn`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: userText }),
      signal: req.signal,  // D-09 cancellation chain
    });
  } catch (err: any) {
    if (err?.name === "AbortError") return new Response(null, { status: 499 }); // client aborted, no body needed
    // ECONNREFUSED → 503 per CONTEXT discretion
    return new Response(
      JSON.stringify({ error: "API unavailable — is uvicorn running?" }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    );
  }

  if (!upstream.ok || !upstream.body) {
    return new Response(
      JSON.stringify({ error: `Upstream returned ${upstream.status}` }),
      { status: upstream.status, headers: { "Content-Type": "application/json" } },
    );
  }

  const translated = translateNamedSSEToUIMessageStream(upstream.body);

  return new Response(translated, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      "Connection": "keep-alive",
      "X-Accel-Buffering": "no",
      "x-vercel-ai-ui-message-stream": "v1",
    },
  });
}
```

**Source:** Cross-verified pattern from `[CITED: ai-sdk.dev/docs/ai-sdk-ui/transport]`, `[CITED: ai-sdk.dev/docs/ai-sdk-ui/stream-protocol]`, `[CITED: github.com/vercel/next.js/discussions/48427]`, `[CITED: medium.com/@oyetoketoby80/fixing-slow-sse...]`, Phase 3 turn.py source.

### Pattern 3: AbortController chain — `useChat.stop()` → upstream cancel

**What:** The AI SDK `useChat` returns a `stop()` method; calling it aborts the in-flight `fetch`. The Next route handler's `req.signal` is wired into the upstream `fetch(req.signal)` call, so the abort cascades all the way to FastAPI's `request.is_disconnected()` polling (Phase 3 D-06).

**When to use:** The Stop button binds directly to `useChat.stop()`. The assistant-ui Composer's stop affordance proxies this method.

**Example:**
```tsx
"use client";
import { useChat } from "@ai-sdk/react";

function StopButton() {
  const { stop, status } = useChat();
  if (status !== "streaming") return null;
  return (
    <button onClick={() => stop()} aria-label="Stop generating">
      <Square /> Stop
    </button>
  );
}
```

**`useChat.stop()` semantics in v6** `[CITED: ai-sdk.dev/docs/ai-sdk-ui/chatbot]`:
- Aborts the underlying fetch.
- **Preserves all messages already in `messages` state** — the partial assistant message stays visible.
- The next user submission starts a fresh assistant message; no implicit cleanup of the partial.

This satisfies the "preserved on screen" half of ROADMAP SC #3 natively. The DB persistence half is satisfied by Phase 3's existing `persist_turn(..., status="cancelled")` invariant (Critical Finding #2).

**Source:** `[CITED]` AI SDK useChat reference + Phase 3 turn.py cancellation handler (lines 496-514).

### Pattern 4: Markdown rendering with block-level memoization

**What:** Wrap the markdown body in a memoized component, split the markdown source into blocks (via `marked` lexer or via `@assistant-ui/react-markdown`'s built-in block-splitting), and memoize each block so unchanged blocks don't re-render on every token.

**When to use:** Every assistant message bubble.

**Example (canonical AI SDK cookbook pattern):**
```tsx
// apps/web/lib/markdown-components.tsx
"use client";
import { memo } from "react";
import { MarkdownTextPrimitive } from "@assistant-ui/react-markdown";

const MemoizedMarkdownBlock = memo(
  ({ block }: { block: string }) => (
    <MarkdownTextPrimitive>{block}</MarkdownTextPrimitive>
  ),
  (prev, next) => prev.block === next.block,
);
MemoizedMarkdownBlock.displayName = "MemoizedMarkdownBlock";

export function MemoizedMarkdownBody({ content }: { content: string }) {
  // Split into blocks (paragraphs, headings, code fences) by double-newline boundary.
  // For higher fidelity use `marked.lexer(content).map(...)`; for Phase 4 the simple split is enough.
  const blocks = content.split(/\n\n+/);
  return (
    <>
      {blocks.map((block, i) => (
        <MemoizedMarkdownBlock key={i} block={block} />
      ))}
    </>
  );
}
```

**At the `useChat` site, enable throttling** `[CITED: ai-sdk.dev/cookbook/next/markdown-chatbot-with-memoization]`:
```tsx
const runtime = useChatRuntime({
  transport: new AssistantChatTransport({ api: "/api/chat" }),
  experimental_throttle: 50, // ms — batch UI updates to limit re-render frequency
});
```

**Source:** `[CITED: ai-sdk.dev/cookbook/next/markdown-chatbot-with-memoization + tigerabrodi.blog/how-to-build-a-performant-ai-markdown-renderer]`

### Pattern 5: No-flicker streaming code blocks via assistant-ui code-block primitive

**What:** The `@assistant-ui/react-markdown` package exposes a code-block primitive that detects fence-state (open vs closed) and renders plain `<pre><code>{rawText}</code></pre>` while the fence is open. On fence close, it performs a single shiki highlight pass and swaps the children.

**When to use:** Implicit — using `@assistant-ui/react-markdown`'s default components map provides this behavior. The planner does NOT need to write custom fence-state logic; the primitive owns it.

**Verification (Playwright assertion for the no-flicker SC):**

The assertion uses a `MutationObserver` snapshot pattern: open the page, send a known prompt that produces a code block, and observe the `<code>` element's children. Assertion: the inner DOM transitions from "single text node containing raw code" to "shiki-tokenized spans" EXACTLY ONCE per code block (not once per token).

```ts
// apps/web/playwright/no-flicker.spec.ts
import { test, expect } from "@playwright/test";

test("code block highlights exactly once", async ({ page }) => {
  await page.goto("/");
  await page.fill('[aria-label="Send message"]', "Write a Python hello world in a fenced code block.");
  await page.keyboard.press("Enter");

  // Wait for the code element to appear.
  const codeEl = page.locator("pre code").first();
  await codeEl.waitFor({ state: "attached", timeout: 5_000 });

  // Install MutationObserver in the page context.
  await page.evaluate(() => {
    (window as any).__codeMutations = 0;
    const observer = new MutationObserver(() => {
      (window as any).__codeMutations += 1;
    });
    const target = document.querySelector("pre code");
    if (target) observer.observe(target, { childList: true, subtree: true });
    (window as any).__observer = observer;
  });

  // Wait for the stream to fully complete.
  await page.waitForSelector('[aria-label*="Turn cost"]', { timeout: 30_000 });
  await page.waitForTimeout(500); // brief settle window

  // Read the mutation count.
  const mutations = await page.evaluate(() => (window as any).__codeMutations as number);

  // During streaming: many text-node mutations (text content appended). These show as childList
  // mutations on the parent <code>. Allow plenty for streaming. The KEY assertion is that
  // AFTER the stream is done, no further mutations fire (verified by waiting and counting twice).
  const mutationsAfterDone = await page.evaluate(() => (window as any).__codeMutations as number);
  expect(mutationsAfterDone).toBe(mutations); // no late re-highlights
});
```

**Alternative stronger assertion:** capture the inner HTML *during* streaming at three points and assert that token-stream growth is monotonic (always longer, never replaced wholesale by a different inner structure). The planner picks the right test shape during Wave 1.

**Source:** `[CITED: x.com/haydenbleasel/status/1990843208386134069 — Streamdown's fence detection rationale]`, `[ASSUMED]` the assistant-ui code-block primitive implements similar fence-state semantics — verified by reading `@assistant-ui/react-markdown` source at install time (Wave 0 spike). If the primitive does NOT do fence-state detection internally, the planner adds a custom code component to the markdown components map that does (Pattern 5b below).

**Pattern 5b — fallback if the primitive doesn't auto-detect fence state:**
```tsx
// apps/web/lib/code-block.tsx
import { useEffect, useState } from "react";
import { codeToHtml } from "shiki";

export function StreamingCodeBlock({ language, children, isStreamingComplete }: {
  language?: string;
  children: string;
  isStreamingComplete: boolean;
}) {
  const [html, setHtml] = useState<string | null>(null);
  useEffect(() => {
    if (!isStreamingComplete) return; // only highlight ONCE, after the fence has closed
    codeToHtml(children, { lang: language ?? "text", theme: "github-light" })
      .then(setHtml)
      .catch(() => setHtml(null));
  }, [isStreamingComplete, children, language]);
  if (!isStreamingComplete || !html) {
    return <pre className="..."><code>{children}</code></pre>;
  }
  return <div dangerouslySetInnerHTML={{ __html: html }} />;
}
```

The `isStreamingComplete` signal comes from the parent's awareness of whether the stream finished (the final `Done` chunk landed). The planner threads this signal via the assistant-ui runtime's message-state.

### Pattern 6: Routing chip via the AI SDK `data-routing` chunk

**What:** The translator emits a `data-routing` chunk early in the stream (after `start`, before any `text-delta`). In assistant-ui, message-level data parts are accessible via `useThreadMessage` or by reading the message's `parts` array.

**When to use:** Once per assistant message, rendered above the bubble.

**Example:**
```tsx
"use client";
import { useThreadMessage } from "@assistant-ui/react";

function RoutingChip() {
  const message = useThreadMessage();
  // Iterate message.parts (AI SDK v6 message shape) and find the data-routing part.
  const routingPart = message?.parts?.find((p: any) => p.type === "data-routing");
  if (!routingPart) return null;
  const signals = routingPart.data as { backend: string; model_or_agent: string; rationale: string; [k: string]: unknown };

  // Look up display_name from config/model_mapping.json (bundled or fetched server-side and cached client-side).
  const displayName = resolveDisplayName(signals.model_or_agent);
  const colorClass = chipClassByBackend[signals.backend as Backend] ?? chipClassByBackend.openrouter;

  return (
    <div role="status" aria-live="polite" aria-label={`Routing decision: Routed to ${displayName}. ${signals.rationale}`}
         className={`inline-flex items-center gap-2 px-2 py-1 rounded-md border text-[13px] ${colorClass}`}>
      <span className="font-semibold">Routed to {displayName}</span>
      <span className="opacity-70"> · </span>
      <span>{signals.rationale}</span>
    </div>
  );
}
```

**`resolveDisplayName`** — bundle `config/model_mapping.json` into the JS build at apps/web build time (Webpack/Next can `import mapping from "../../../config/model_mapping.json"` since Next allows JSON imports). Fall back to the slug if not in the mapping.

**Source:** `[CITED: ai-sdk.dev/docs/ai-sdk-ui/stream-protocol — data-*]` + `[ASSUMED]` assistant-ui's `useThreadMessage` exposes the v6 `parts` shape (verified at install).

### Pattern 7: Metrics footer driven by `data-metrics`

**What:** The translator emits `data-metrics` on `Done`. The footer subscribes via `useThreadMessage` analogous to the chip.

**Mid-stream behavior:** while no `data-metrics` part exists in the message, render the `streaming…` placeholder. When the part lands, render the final formatted string.

```tsx
function MetricsFooter() {
  const message = useThreadMessage();
  const metricsPart = message?.parts?.find((p: any) => p.type === "data-metrics");
  if (!metricsPart) {
    return (
      <div aria-label="Streaming response in progress" className="text-xs font-mono text-slate-500 mt-2 flex items-center gap-1">
        <span>streaming</span>
        <span aria-hidden="true" className="animate-pulse">●</span>
      </div>
    );
  }
  const m = metricsPart.data as { cost_usd: number; latency_ms: number; tokens_in: number; tokens_out: number };
  const cost = `$${m.cost_usd.toFixed(4)}`;
  const latency = `${(m.latency_ms / 1000).toFixed(1)}s`;
  const fmtTokens = (n: number) => n < 10_000 ? String(n) : n.toLocaleString();
  return (
    <div className="text-xs font-mono text-slate-500 mt-2"
         aria-label={`Turn cost ${cost}, latency ${latency}, ${m.tokens_in} tokens in, ${m.tokens_out} tokens out`}>
      {cost} · {latency} · {fmtTokens(m.tokens_in)}↑/{fmtTokens(m.tokens_out)}↓
    </div>
  );
}
```

**Source:** Same as Pattern 6.

### Pattern 8: First-run modal + key gating flow

**Boot sequence (in `apps/web/app/page.tsx` or a top-level layout effect):**

```tsx
"use client";
import { useEffect, useState } from "react";

export function ChatPage() {
  const [openrouterReady, setOpenrouterReady] = useState<boolean | null>(null); // null = loading
  const [modalOpen, setModalOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/health")
      .then(r => r.json())
      .then(j => {
        if (cancelled) return;
        const ready = j?.adapters?.openrouter?.status === "ready";
        setOpenrouterReady(ready);
        if (!ready) setModalOpen(true);
      })
      .catch(() => {
        if (cancelled) return;
        // Network down — show network-down banner; do NOT show first-run modal (separate concern).
        setOpenrouterReady(false);
      });
    return () => { cancelled = true; };
  }, []);

  // Wire modal completion → re-fetch healthz → unblock composer
  const handleKeySaved = async () => {
    const j = await fetch("/api/health").then(r => r.json());
    const ready = j?.adapters?.openrouter?.status === "ready";
    setOpenrouterReady(ready);
    if (ready) {
      setModalOpen(false);
      // sonner toast
      toast.success("OpenRouter connected — try a prompt!");
    }
  };

  return (
    <>
      {/* main UI; composer is disabled when !openrouterReady */}
      <FirstRunModal open={modalOpen} onKeySaved={handleKeySaved} mode="blocking" />
    </>
  );
}
```

**KeyForm submission:**
```tsx
async function submitKey(key: string) {
  const res = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider: "openrouter", key }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json(); // {keys: {openrouter: {present: true, masked: "sk-or-…ABC"}}, ...}
}
```

**Settings route handler (`apps/web/app/api/settings/route.ts`):**
```typescript
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";

export async function POST(req: Request) {
  const { provider, key } = await req.json();
  if (provider !== "openrouter" && provider !== "anthropic") {
    return Response.json({ error: "unknown provider" }, { status: 400 });
  }
  try {
    const upstream = await fetch(`${FASTAPI_URL}/api/v1/settings`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keys: { [provider]: key } }),
    });
    if (!upstream.ok) {
      // D-18 belt-and-suspenders: scrub the key from any error body that might echo it.
      const text = await upstream.text();
      const scrubbed = text.replace(key, "***");
      return new Response(scrubbed, { status: upstream.status });
    }
    return Response.json(await upstream.json());
  } catch (err: any) {
    // Catch BEFORE the error message can include the key
    const errMsg = String(err?.message ?? err).replace(key, "***");
    return Response.json({ error: "Could not save key", detail: errMsg }, { status: 503 });
  }
}
```

**Source:** Phase 3 settings.py + healthz.py contracts (read in this research); `[CITED]`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Browser-side SSE consumption | Custom EventSource wrapper, `@microsoft/fetch-event-source` | `useChat` from `@ai-sdk/react` via `useChatRuntime` from `@assistant-ui/react-ai-sdk` | The AI SDK handles connection, abort, reconnection-disable, error envelopes. D-06 locked. |
| AI SDK protocol emission | Manual numeric-prefix or JSON-line writer | `data: {JSON}\n\n` lines following AI SDK v6 UIMessage Stream chunk types | Documented protocol; future-proofs against AI SDK updates. |
| Markdown parsing | Custom regex parser | `@assistant-ui/react-markdown` (wraps `react-markdown@^10` + `remark-gfm`) | Markdown edge cases are vast. D-10 locked. |
| Syntax highlighting | Custom tokenizer | `shiki` via assistant-ui code-block primitive | shiki uses VS Code's tokenizer — production-quality. D-11 locked. |
| Streaming-safe code blocks | Re-highlight on every token | Fence-state detection (assistant-ui primitive) or `isStreamingComplete` deferred highlight (Pattern 5b) | Per-token re-highlight causes flicker AND CPU melt. SC #2 explicit. |
| Toast notifications | Custom toast widget | `sonner` (shadcn-wrapped) | Toast UX nuances (stack, dismiss, ARIA) are non-trivial. UI-SPEC §10.5 declares strings. |
| Form input + validation | Hand-rolled `<input>` styling | shadcn `Input` + shadcn `Dialog` for the modal | Accessibility (focus trap, ESC handling), keyboard nav, ARIA — all handled. UI-SPEC §10 locks shadcn primitives. |
| Color-class composition | Inline template strings | `clsx` + `tailwind-merge` via `cn()` helper | Idiomatic shadcn. Reduces duplicate-class bugs. |
| Schema validation for incoming SSE events | `if (typeof x === "string") ...` chains | `zod` discriminated union (chunk-schemas.ts) | The wire is a closed-vocabulary contract; the boundary deserves typed enforcement. Validation Architecture §11. |
| CORS handling | Manual response headers | FastAPI's `CORSMiddleware` is already configured in Phase 3 main.py | OSS-05 already done by Phase 3; Next side does NOT need to touch CORS because the browser only ever talks to the Next origin. |
| AbortController plumbing | Custom signal management | Native `req.signal` (Next route) + `useChat.stop()` (browser) | All major browsers + Node 18+ implement this stably. D-09 locked. |
| BYOK key storage | Browser localStorage / cookies / Next-side cache | FastAPI's `KeyStore` (already Phase 2/3) | D-18 explicit. Key isolation is critical for an open-source BYOK app. |
| Playwright dev orchestration | Hand-rolled spawn + kill | Playwright's `webServer` config (multiple commands supported in 1.43+) | Idiomatic E2E setup; survives CI runners. |
| Default-thread CRUD UI | Phase 5 sidebar | `localStorage` ID + auto-create on first boot | D-(discretion) explicit; Phase 5 owns the real sidebar. |
| Cost / latency / token math in browser | tiktoken on Next side | Trust `Done.cost_usd` / `Done.latency_ms` / `Done.tokens_in` / `Done.tokens_out` | Phase 2 adapters compute these from upstream usage; UI just renders. |

**Key insight:** Phase 4 is **assembly, not construction**. Every hard problem (SSE, markdown, highlighting, chat state, abort) is already solved by an actively-maintained library. The only meaningful code Phase 4 writes is (a) the SSE translator (~150 lines pure function), (b) the route handlers (~50 lines each), (c) the small components for chip / footer / modal / banners (~80 lines each), and (d) the tests. The total Phase 4 LOC budget should be roughly **1,500–2,500 lines of TypeScript/TSX**, not 5,000+. A higher count is a red flag that the planner reinvented something.

## Runtime State Inventory

> N/A — Phase 4 is a greenfield scaffold under `apps/web/` (does not yet exist). No rename / refactor / migration aspects. The only existing-code interaction is the single Phase 3 file edit for D-15 (`apps/api/routes/turn.py`), which adds an event yield BEFORE the adapter dispatch — no state migration, no stored data, no OS-registered tasks, no secret renames.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — Phase 4 introduces no new persistent records. Existing SQLite tables unchanged. | No data migration. |
| Live service config | None — Phase 3 `app.state.adapters` lazy cache is already invalidated on PATCH /settings (D-15). | None. |
| OS-registered state | None — local dev only, no system tasks/timers. | None. |
| Secrets / env vars | NEW: `FASTAPI_URL` env var (Next-side, defaults to `http://localhost:8000`). `apps/web/.env.local` added to `.gitignore`. | Document in `apps/web/.env.example` (planner). |
| Build artifacts | NEW: `apps/web/node_modules/`, `apps/web/.next/`, `apps/web/playwright-report/`, `apps/web/test-results/`, `apps/web/coverage/` — all gitignored. `apps/web/pnpm-lock.yaml` IS committed. | `.gitignore` additions per CONTEXT canonical_refs. |

## Common Pitfalls

### Pitfall 1: Using Edge runtime for the proxy
**What goes wrong:** SSE proxy works in `next dev` but silently truncates / buffers in production Edge environments (Vercel Edge has 25s limit, Cloudflare Workers ~30s). AbortSignal propagation is also flaky.
**Why it happens:** Default Next.js route handlers are Node runtime in v16, but developers sometimes opt into Edge for "performance" without knowing the streaming caveats.
**How to avoid:** Always `export const runtime = "nodejs"` on `/api/chat`, `/api/settings`, `/api/health`. Add a comment explaining why.
**Warning signs:** Stream "freezes" after some bytes in production; abort fires don't propagate; logs show truncated responses.

### Pitfall 2: Awaiting the upstream stream before returning the Response
**What goes wrong:** `const data = await upstream.text();` (or any await on the body) makes Next buffer the response — SSE never streams.
**Why it happens:** Natural TypeScript instinct to "consume" the response.
**How to avoid:** Pipe the `upstream.body` ReadableStream through a TransformStream and return immediately. Async work happens INSIDE the stream's pull loop.
**Warning signs:** Browser receives the entire response in one chunk after a long delay.

### Pitfall 3: `useChat.stop()` throwing away the partial in some libraries
**What goes wrong:** Some chat libraries reset `messages` on abort, losing the partial assistant text. ROADMAP SC #3 says the partial MUST stay visible.
**Why it happens:** Library author thought "abort = bad state, clean it up".
**How to avoid:** AI SDK v6's `useChat.stop()` **preserves** the partial in `messages` per its documented contract. Verified via assistant-ui's v6 example wiring. Do NOT add custom abort-cleanup logic.
**Warning signs:** Cancel button click empties the bubble — sign that some upstream handler is wrongly clearing state.

### Pitfall 4: Markdown re-render storm at long conversation lengths
**What goes wrong:** At 200+ tokens or 2,000+ words, every token-arrival re-renders the entire conversation. UI stutters; scrolling jitters.
**Why it happens:** Default `react-markdown` re-parses the entire string on every update.
**How to avoid:** Block-memoization (Pattern 4) + AI SDK `experimental_throttle: 50` + React 19 `startTransition` for non-urgent updates.
**Warning signs:** Browser DevTools Performance tab shows long React commit times during streaming. Frame drops > 100ms.

### Pitfall 5: Code block re-highlight every token
**What goes wrong:** shiki re-tokenizes the entire code block on every text-delta — UI freezes for 100+ms per token in large code blocks.
**Why it happens:** Naive `<SyntaxHighlighter language=...>{streamingCode}</SyntaxHighlighter>` pattern.
**How to avoid:** Pattern 5 — defer highlight until fence-close (closing ``` arrives in the stream). The assistant-ui primitive does this automatically; the fallback is Pattern 5b.
**Warning signs:** Playwright `no-flicker.spec.ts` fails. Browser CPU pegged during streaming of code-heavy responses.

### Pitfall 6: Plaintext key leaking through error messages or logs
**What goes wrong:** A `fetch` error includes the request body in its message, which contains the plaintext key. Logged or echoed to browser, the key is exposed.
**Why it happens:** Default error handling doesn't scrub.
**How to avoid:** Wrap the Settings route handler `fetch` in try/catch and scrub the key string from any error message before re-throwing or returning. The Playwright `secure-key.spec.ts` regression test enforces zero matches.
**Warning signs:** Any test that searches log files / response bodies finds the literal key string.

### Pitfall 7: Forgetting `x-vercel-ai-ui-message-stream: v1` response header
**What goes wrong:** AI SDK v6 client expects this header to identify the stream as v1 protocol. Without it, the client may not parse chunks correctly.
**Why it happens:** Not documented prominently — easy to miss when writing a custom proxy.
**How to avoid:** Set the header at the route handler `Response` construction (see Pattern 2). Confirm via unit test (snapshot the response headers).
**Warning signs:** `useChat` shows no messages despite SSE traffic in DevTools.

### Pitfall 8: Hydration mismatch from runtime mounted in a server component
**What goes wrong:** `useChatRuntime` is a client hook. Mounting `<AssistantRuntimeProvider>` in a server component crashes at hydration with "useState only works in client components".
**Why it happens:** App Router defaults to server components.
**How to avoid:** Mark the chat shell as `"use client"` at the top of the file. The runtime provider + Thread + Composer all live in a client tree.
**Warning signs:** "useState is only available in a Client Component" error in Next dev.

### Pitfall 9: shadcn dialog `modal=true` allowing pointer-events outside
**What goes wrong:** Radix Dialog defaults allow `onPointerDownOutside` to close, even when `mode="blocking"` is intended.
**Why it happens:** Default Radix UX.
**How to avoid:** Pass `onEscapeKeyDown={(e) => e.preventDefault()}` and `onPointerDownOutside={(e) => e.preventDefault()}` on the Dialog Content when in blocking mode. UI-SPEC §10.3 covers this.
**Warning signs:** First-run modal closes on stray click, leaving composer disabled with no way to re-open the modal.

### Pitfall 10: AI SDK v6 protocol mismatch with stale assistant-ui packages
**What goes wrong:** Mixing `@assistant-ui/react@0.10.x` (AI SDK v5-era) with `ai@^6.0.x` and the v6 stream protocol — the runtime adapter doesn't know about new chunk types.
**Why it happens:** Partial version uplift.
**How to avoid:** Pin the **entire** assistant-ui set (`react`, `react-ai-sdk`, `react-markdown`) to current versions in a single uplift. The v6 starter is the canonical pairing.
**Warning signs:** `useChat` errors in console about unknown chunk types; messages appear empty.

### Pitfall 11: `next dev` HMR breaking the runtime provider on every save
**What goes wrong:** Editing a component file causes the runtime to re-initialize, losing message state mid-stream.
**Why it happens:** HMR replaces React tree; the runtime's local state is reset.
**How to avoid:** Acceptable for Phase 4 dev — don't mid-stream-edit while testing. Phase 5 may explore stable-storage for in-flight streams. Document as known Phase 4 limitation in README.
**Warning signs:** Mid-stream save → bubble empties.

### Pitfall 12: Reading `model_mapping.json` from a server file path at request time
**What goes wrong:** `fs.readFileSync('config/model_mapping.json')` in a route handler depends on `process.cwd()` and may fail in production builds. Repeated reads also slow.
**Why it happens:** Habit from Python where reading from disk is normal.
**How to avoid:** Use `import mapping from "../../../config/model_mapping.json"` at module top. Next bundles JSON imports into the output. Tests confirm the import resolves.
**Warning signs:** Chip falls back to slug instead of display_name in production builds.

## Code Examples

### Example 1 — Route handler signature checklist

```typescript
// apps/web/app/api/chat/route.ts
export const runtime = "nodejs";         // Pitfall 1
export const dynamic = "force-dynamic";  // Prevent caching

export async function POST(req: Request) { /* ... */ }
```

### Example 2 — SSE Block parser detail (single-line vs multi-line `data:`)

Phase 3 emits single-line `data:` blocks (Pydantic `model_dump_json` produces no newlines), so the parser can `JSON.parse(dataLines.join("\n"))` safely. Multi-line `data:` is RFC-valid but Phase 3 never produces it. Document this assumption inline.

### Example 3 — Playwright webServer config

```typescript
// apps/web/playwright/playwright.config.ts
import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: ".",
  webServer: [
    { command: "uvicorn apps.api.main:app --port 8000", port: 8000, cwd: "../../", reuseExistingServer: !process.env.CI },
    { command: "pnpm dev --port 3000", port: 3000, reuseExistingServer: !process.env.CI },
  ],
  use: { baseURL: "http://localhost:3000" },
});
```

### Example 4 — useChat throttle wiring

```tsx
const runtime = useChatRuntime({
  transport: new AssistantChatTransport({ api: "/api/chat" }),
  experimental_throttle: 50,
});
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Vercel AI SDK v4 numeric-prefix stream protocol (`0:"text",2:tool_call`) | AI SDK v5+ UI Message Stream Protocol (`data: {type:"text-delta",...}`) — closed JSON vocabulary, SSE-native | AI SDK 5 release (2025) | Translation layer (Pattern 2) targets the v6 vocabulary, not v4 prefixes. |
| `react-markdown` + manual memo wrapper | `@assistant-ui/react-markdown` integrated with `MessagePrimitive.Content` | assistant-ui 0.10+ | Less hand-rolling; consistent with runtime extension model. |
| `react-syntax-highlighter` | `shiki` (VS Code-quality tokens) | shiki 1.x → 4.x progression | Cleaner highlighting, better theme support, smaller runtime. |
| EventSource API for browser SSE | `fetch` + `ReadableStream` (via AI SDK internal transport) | AI SDK v5 | EventSource doesn't allow POST body — necessary change for chat-style APIs. |
| Vercel SDK v4's `useChat` returning `messages: Message[]` with `content: string` | AI SDK v6's `messages: UIMessage[]` with `parts: Part[]` | AI SDK v5 → v6 transition | Custom data parts (`data-*`) enable per-message metadata streams (chip, metrics, tool calls) cleanly. |
| Next.js `pages/api/` API routes | App Router route handlers in `app/api/.../route.ts` | Next.js 13 App Router GA (2023) | Phase 4 uses route handlers exclusively. |
| `next-themes` for dark/light toggle | Light-only for Phase 4 (D-04); Tailwind v4 CSS-first config means dark mode is later additive | n/a | Reduce surface area. |

**Deprecated / outdated:**
- AI SDK v4 numeric prefixes — Phase 4 does NOT target this.
- Pages router API routes — Phase 4 does NOT use these.
- `react-syntax-highlighter` — superseded by `shiki` for new projects.
- `EventSource` browser API — superseded by fetch + ReadableStream for chat use cases.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `@assistant-ui/react-markdown` code-block primitive performs fence-state detection (renders plain `<pre>` until fence-close, then one-shot shiki swap) | Pattern 5 + D-11 | Medium — if the primitive does NOT do this, the planner falls back to Pattern 5b (custom `StreamingCodeBlock` component with `isStreamingComplete` prop). Verified by reading `@assistant-ui/react-markdown` source at Wave 0 spike. |
| A2 | AI SDK v6 `useChat.stop()` preserves partial assistant text in `messages` after abort | Pattern 3 + Pitfall 3 | Medium — ROADMAP SC #3 fails if partial is lost. Verified by reading AI SDK v6 useChat source at Wave 0 or by an early Vitest spike. |
| A3 | `useThreadMessage` from `@assistant-ui/react` exposes AI SDK v6 `parts: Part[]` shape so `data-routing` and `data-metrics` parts are reachable | Pattern 6 + Pattern 7 | Medium — if the assistant-ui runtime doesn't surface custom data parts cleanly, the planner uses `useChat`'s `data` state directly (AI SDK v6 `useChat` returns `data` alongside `messages`). Spike during Wave 1. |
| A4 | `@ai-sdk/react@^3` + `ai@^6` + `@assistant-ui/react@^0.14` + `@assistant-ui/react-ai-sdk@^1.3` all peer-compatible with React 19.2 | Standard Stack | Low — verified via assistant-ui example package.json which uses these exact major versions. Wave 0 `pnpm install` confirms. |
| A5 | The Phase 4 D-15 `routing_decision` SSE event lands within 100ms of POST and BEFORE the first `text_delta` (so the chip can render before any assistant text) | Pattern 6 + D-15 | Low — Phase 3 already runs `decide()` before adapter dispatch and the JSONL log; D-15 explicitly orders the new event between `decide()` and `adapter.stream()`. Phase 3 amendment test asserts this. |
| A6 | The Next.js v16 Node runtime correctly streams `Response(new ReadableStream(...))` and the `X-Accel-Buffering: no` header survives the response pipeline | Critical Finding #3 + Pitfall 2 | Low — verified via multiple Next.js docs and GitHub discussions. |
| A7 | shadcn `Dialog` (Radix Dialog) supports `onEscapeKeyDown` + `onPointerDownOutside` preventDefault for blocking mode | Pitfall 9 | Low — documented Radix API, stable for years. |
| A8 | `localStorage.setItem("prompt-optimizer.defaultThreadId", id)` is allowed in this app (no incognito-mode handling needed for Phase 4) | Pattern 1 + discretion | Low — local-only dev, incognito is out of scope. |
| A9 | The CONTEXT-pinned versions `next@15.2.x` and `ai-sdk v5` are loose floors and the user accepts current versions (Next 16, AI SDK 6) | Critical Finding #1 | LOW-MEDIUM — recommended approach is to use current. If the user explicitly wants v5 + Next 15, the planner uses the older `assistant-ui/examples/with-ai-sdk` example structure (which is also still supported). Flag this in the plan's Open Questions if any doubt. |
| A10 | The browser's `MutationObserver` reliably reports child-list mutations on a `<code>` element fed by React, even when React uses batching | Pattern 5 (Playwright assertion) | Medium — MutationObserver fires synchronously after the DOM commits, so React-batched updates produce mutation callbacks. The exact mutation count depends on React's commit strategy; the assertion targets "no mutations after Done", which is the SC-relevant invariant. Verified at Wave 1. |

## Open Questions

1. **AI SDK version — v5 vs v6?**
   - What we know: CONTEXT D-07 wording says "AI SDK v5"; current ecosystem is v6; canonical assistant-ui example uses v6 (`ai@^6.0.175`).
   - What's unclear: Whether the user prefers the older stack pin literally, or accepts the version uplift (we recommend uplift).
   - Recommendation: Pin v6 in the plan. Add a one-line callout in plan-01's "Decisions" section so the user can object during execution if they have a reason for v5.

2. **Stop status = `cancelled` (Phase 3) vs `complete` (ROADMAP wording)?**
   - What we know: Phase 3 writes `status="cancelled"` for stop scenarios; ROADMAP SC #3 wording suggests `complete`.
   - What's unclear: Whether the ROADMAP wording was intentional or loose.
   - Recommendation: Accept Phase 3's `cancelled` as canonical and adjust the SC verification step to assert `status IN ('cancelled','complete','error')`. The user-facing requirement (partial preserved on screen + footer metrics) is independent of the DB string. Surface to user during execution if they intended otherwise.

3. **Does `@assistant-ui/react-markdown`'s code-block primitive auto-detect fence state?**
   - What we know: assistant-ui ships its own code-block component that integrates with shiki.
   - What's unclear: Whether fence-state detection is built in OR whether the planner needs Pattern 5b.
   - Recommendation: Wave 0 / Wave 1 spike — install the package, write a tiny harness, send a streamed code block, observe whether the inner DOM transitions once (built-in) or many times (need Pattern 5b). Outcome decides the implementation path. Both paths satisfy SC #2.

4. **Where does `RoutingDecision.signals` end up in the AI SDK v6 message?**
   - What we know: Translator emits `{type: "data-routing", data: signals}`.
   - What's unclear: Whether assistant-ui's `useThreadMessage` surfaces this part directly OR whether we read from `useChat`'s `data` state.
   - Recommendation: Wave 1 spike against the runtime API. Both paths are viable.

5. **Should `prepareSendMessagesRequest` send the full `messages` array or only the last user text?**
   - What we know: CONTEXT D-08 says the Next route strips to `{message: <latest user text>}`. The current Pattern 1 code shows the full array being sent to the route handler; the route handler does the stripping.
   - What's unclear: Whether to push the stripping into `prepareSendMessagesRequest` (browser-side, smaller body) or keep it in the route handler.
   - Recommendation: Keep the stripping in the route handler. Browser-side stripping risks the route handler receiving an empty body if the client is updated incorrectly. Single source of truth for the message extraction = the proxy.

6. **How is the default thread ID created — server-to-server fetch at Next route handler time, or browser-driven via `/api/threads` proxy?**
   - What we know: Phase 4 needs to call `POST /api/v1/threads` once.
   - What's unclear: Whether the browser POSTs to `/api/threads` (new proxy route) on mount, or whether the chat route handler does it transparently.
   - Recommendation: Add a `POST /api/threads` proxy route in apps/web AND drive thread creation from the browser on first mount. Persist the returned ID in `localStorage`. Cleaner separation of concerns; the chat route handler doesn't need to know about thread creation. Planner decides during Wave 1.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `pnpm` | Phase 4 scaffolding + dev | (planner verifies on developer machine) | should be 8.x+ | `corepack enable pnpm@latest` if missing |
| `node` | Next.js dev + build | (verify) | ≥18.18.0 (Next 16 requirement) | `nvm install 20` / `mise install node@20` |
| `pnpm dlx shadcn` | shadcn component install | via pnpm (network) | latest | downloads at install time |
| `uvicorn apps.api.main:app` | Phase 4 dev (uvicorn must be runnable from repo root for the two-terminal flow) | YES (Phase 3 dependency) | already in `pyproject.toml` | `uv sync` to re-install |
| `playwright install chromium` | Playwright E2E | downloads ~150 MB at install time | latest | offline: pre-cache via CI |
| FastAPI on `localhost:8000` | Phase 4 dev / Playwright | YES (Phase 3 ships uvicorn entry) | n/a | docs explicit |
| OpenRouter API key (BYOK) | Manual UAT only — Playwright tests can use mocked FastAPI | depends on developer | n/a | tests should mock `/api/v1/threads/{id}/turn` via a fake FastAPI when in CI |

**Missing dependencies with no fallback:**
- None for the implementation itself.
- **Manual UAT requires an OpenRouter key** (BYOK; the developer provides). Playwright tests can run against a mocked FastAPI fixture (set `FASTAPI_URL=http://localhost:8001` and run a tiny fake uvicorn that emits canned named-event SSE streams). Recommended for CI.

**Missing dependencies with fallback:**
- shiki theme — defaults to `github-light` per UI-SPEC §1; assistant-ui primitive supports theme prop.

## Validation Architecture

> Phase 3 already enabled Nyquist validation; Phase 4 continues. `workflow.nyquist_validation` is not explicitly false in `.planning/config.json`.

### Test Framework

| Property | Value |
|----------|-------|
| Framework (unit) | **Vitest 4.1** + jsdom + `@testing-library/react` |
| Framework (E2E) | **Playwright 1.60** with multi-server `webServer` config (uvicorn + next dev) |
| Config file (Vitest) | `apps/web/vitest.config.ts` (Wave 0 creates) |
| Config file (Playwright) | `apps/web/playwright/playwright.config.ts` (Wave 0 creates) |
| Quick run command (unit) | `pnpm --dir apps/web test` (Vitest watch off by default in CI) |
| Quick run command (component) | same — RTL tests run under Vitest |
| Quick run command (E2E) | `pnpm --dir apps/web test:e2e` |
| Full suite command | `pnpm --dir apps/web test && pnpm --dir apps/web test:e2e` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| UI-01 | Chat surface renders; user can type and submit | E2E happy-path | `pnpm --dir apps/web test:e2e first-run.spec.ts` (covers full first-turn flow) | ❌ Wave 0 |
| UI-03 | Markdown streams + code blocks highlight once on close | E2E no-flicker | `pnpm --dir apps/web test:e2e no-flicker.spec.ts` | ❌ Wave 0 |
| UI-04 | Routing chip renders on every assistant message | E2E + unit | `pnpm --dir apps/web test routing-chip.test.tsx` | ❌ Wave 0 |
| UI-06 | Stop preserves partial; cancels within 2s | E2E budget | `pnpm --dir apps/web test:e2e cancel-budget.spec.ts` | ❌ Wave 0 |
| UI-07 | Metrics footer shows cost/latency/tokens after Done | E2E + unit | `pnpm --dir apps/web test metrics-footer.test.tsx` | ❌ Wave 0 |
| UI-08 | ChatBubble renders + copy + regenerate | unit + E2E | `pnpm --dir apps/web test` (unit) + manual UAT | ❌ Wave 0 |
| UI-13 | First-run modal flow guides clone-to-first-turn | E2E | `pnpm --dir apps/web test:e2e first-run.spec.ts` | ❌ Wave 0 |
| UI-17 | Browser never opens connections to FastAPI directly | E2E network assertion | `pnpm --dir apps/web test:e2e browser-isolation.spec.ts` | ❌ Wave 0 |
| (D-18 belt) | OpenRouter key never appears in logs / headers / bodies / storage | E2E regression | `pnpm --dir apps/web test:e2e secure-key.spec.ts` | ❌ Wave 0 |
| (D-07 contract) | SSE translator pure function matches AI SDK v6 protocol exactly | Vitest unit | `pnpm --dir apps/web test sse-translate.test.ts` | ❌ Wave 0 |
| (D-15 contract) | Phase 3 `routing_decision` SSE event arrives within 100ms and matches `Done.routing_signals` | pytest (Phase 3 edit) | `pytest apps/api/tests/test_turn_streaming.py` | ❌ Wave (Phase 3 amendment) |
| (Schema contract) | Every Phase-3 SSE event is parseable by the Zod schema | Vitest | `pnpm --dir apps/web test chunk-schemas.test.ts` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pnpm --dir apps/web test` (Vitest unit suite — should complete < 10s).
- **Per wave merge:** `pnpm --dir apps/web test && pnpm --dir apps/web test:e2e` (full suite — Playwright spins up two servers; expect 60-120s).
- **Phase gate:** Full suite green AND Phase 3 contract test for D-15 green AND a manual UAT confirming the five SCs.

### Wave 0 Gaps

- [ ] `apps/web/vitest.config.ts` — Vitest jsdom config
- [ ] `apps/web/playwright/playwright.config.ts` — multi-server config
- [ ] `apps/web/tests/setup.ts` — RTL setup (`@testing-library/jest-dom`)
- [ ] Framework install (Wave 0 task): `pnpm add -D vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/jest-dom @playwright/test`
- [ ] Playwright browsers: `pnpm exec playwright install chromium`
- [ ] CI workflow extension to run `pnpm --dir apps/web test && pnpm --dir apps/web test:e2e`
- [ ] Mocked FastAPI fixture for E2E in CI (a small Python script that serves canned SSE responses without needing real OpenRouter)

## Security Domain

Per `security_enforcement` default-on (no `false` in config). Phase 4 introduces a JS surface with new attack vectors.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (BYOK keys) | FastAPI `KeyStore` (Phase 2/3); Next side never persists keys — only forwards |
| V3 Session Management | partial | No sessions; localStorage holds only `defaultThreadId` (non-secret) |
| V4 Access Control | yes (CORS) | FastAPI `CORSMiddleware` allowlist (Phase 3 — already configured for `http://localhost:3000`); Next side has no auth |
| V5 Input Validation | yes | **Zod schemas at the route handler boundary** (`chunk-schemas.ts`) validate every Phase-3 SSE event; `SettingsPatch` Pydantic on FastAPI side already validates key shape |
| V6 Cryptography | partial | Never hand-roll. BYOK keys flow through HTTPS in production; in local dev, both servers are on localhost so plaintext is acceptable |
| V8 Data Protection | yes | D-18 explicit — keys never reach disk on Next side; masked form in responses |
| V11 Business Logic | yes | Routing decision is server-side only; chip displays what server returned |
| V12 Files and Resources | n/a (Phase 4) | No file uploads in Phase 4 |
| V13 API and Web Services | yes | Closed-vocabulary SSE event names + Zod validation at boundary |
| V14 Configuration | yes | `apps/web/.env.local` gitignored; no client-side secret leakage |

### Known Threat Patterns for {Next.js + AI SDK proxy}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Plaintext key in error response body | Information Disclosure | Try/catch + scrub key string from error messages before returning (Pattern 8 + Pitfall 6) |
| Plaintext key in log line (Next stdout) | Information Disclosure | Never `console.log(req.body)`; FastAPI side already has redaction filter |
| XSS via assistant-rendered markdown | Tampering | `react-markdown` + `rehype-sanitize` (assistant-ui-react-markdown includes hardening via `rehype-harden` equivalent — verify at install) |
| Direct browser→FastAPI bypass | Spoofing of CORS / Information Disclosure | No `NEXT_PUBLIC_FASTAPI_URL` env var; `FASTAPI_URL` is server-only. Playwright `browser-isolation.spec.ts` enforces. |
| Malformed SSE upstream causing translator crash | Denial of Service | Zod parse + try/catch in translator; on parse failure emit `{type:"error", errorText:"..."}` and continue. Never throw uncaught. |
| AbortController exhaustion (orphaned upstream fetches if abort fails) | Resource exhaustion | Always pass `req.signal` to upstream `fetch`; rely on Node 18+ AbortController stability |
| Reflected XSS via routing rationale | Tampering | Rationale is rendered as text content (not `dangerouslySetInnerHTML`); React's auto-escaping covers it |
| CORS leak (someone scraping localhost:8000 from a malicious page) | Information Disclosure | Phase 3 CORSMiddleware allowlist is `http://localhost:3000` only; no wildcard. Already done. |
| Race in adapter cache invalidation after key swap | Logic error | Phase 3 D-15 clears cache AFTER atomic file write, BEFORE response — Pitfall 8 documented. |

### Security Test Plan

1. **`apps/web/playwright/secure-key.spec.ts`** — submits a real-shaped key, then asserts:
   - DevTools storage (localStorage / sessionStorage / cookies) contains zero matches for the key.
   - All response bodies from `/api/settings`, `/api/health`, `/api/chat` contain zero matches.
   - All response headers contain zero matches.
   - All captured Next.js server stdout / stderr contains zero matches.
2. **`apps/web/playwright/browser-isolation.spec.ts`** — intercepts all browser network requests, asserts no request hits `localhost:8000`.
3. **Vitest schema parity**: `chunk-schemas.test.ts` ensures the Zod schemas reject unknown event names and accept every closed-vocabulary event.

## Sources

### Primary (HIGH confidence)
- npm registry — version & dependency metadata for every library `[VERIFIED: registry.npmjs.org/<pkg>/latest]` (2026-05-18)
  - `next` → 16.2.6
  - `react` → 19.2.6
  - `@ai-sdk/react` → 3.0.187
  - `@assistant-ui/react` → 0.14.5
  - `@assistant-ui/react-ai-sdk` → 1.3.26 (peer: `ai@^6.0.175`)
  - `@assistant-ui/react-markdown` → 0.14.0 (peer: `@assistant-ui/react@^0.14.0`)
  - `ai` → 6.0.185
  - `shiki` → 4.0.2
  - `zod` → 4.4.3
  - `tailwindcss` → 4.3.0
  - `@playwright/test` → 1.60.0
  - `vitest` → 4.1.6
  - `streamdown` → 2.5.0 (rejected for Phase 4)
- AI SDK v6 docs — UI Message Stream Protocol chunk types, `createUIMessageStream`, transport reference [https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol], [https://ai-sdk.dev/docs/ai-sdk-ui/transport], [https://ai-sdk.dev/docs/reference/ai-sdk-ui/create-ui-message-stream]
- AI SDK Cookbook — Markdown chatbot with memoization [https://ai-sdk.dev/cookbook/next/markdown-chatbot-with-memoization]
- assistant-ui canonical example — `examples/with-ai-sdk-v6/package.json` and `app/api/chat/route.ts` shape [https://github.com/assistant-ui/assistant-ui/tree/main/examples/with-ai-sdk-v6]
- assistant-ui docs — Custom Runtime overview, AI SDK v6 integration [https://www.assistant-ui.com/docs/runtimes/ai-sdk/v6], [https://www.assistant-ui.com/docs/runtimes/custom/overview]
- Next.js docs — Route Handlers [https://nextjs.org/docs/app/getting-started/route-handlers], Streaming guide [https://nextjs.org/docs/app/guides/streaming]
- Phase 3 source files read in this research: `apps/api/main.py`, `apps/api/routes/turn.py`, `apps/api/routes/health.py`, `apps/api/routes/settings.py`, `apps/api/routes/threads.py`, `apps/api/backends/chunks.py`, `apps/api/db/queries.py` — canonical contract Phase 4 consumes
- Phase 4 CONTEXT.md (locked decisions D-01 — D-19) and UI-SPEC.md (visual contract) — the planner's source of truth
- Phase 2 RoutingDecision schema (`src/routing/schema.py`)
- `config/model_mapping.json` (16 entries) — `display_name` source for the routing chip

### Secondary (MEDIUM confidence)
- Next.js GitHub discussions on SSE [https://github.com/vercel/next.js/discussions/48427], [https://github.com/vercel/next.js/discussions/50614], [https://github.com/vercel/next.js/discussions/61972] — verified across multiple sources
- AppSignal / MDN on AbortController [https://blog.appsignal.com/2025/02/12/managing-asynchronous-operations-in-nodejs-with-abortcontroller.html], [https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal] — verified
- Hayden Bleasel on shiki streaming pitfalls [https://x.com/haydenbleasel/status/1990843208386134069] — informs Pattern 5 fallback (Pattern 5b)
- tigerabrodi.blog on AI markdown rendering [https://tigerabrodi.blog/how-to-build-a-performant-ai-markdown-renderer] — informs Pattern 4
- LogRocket on AI SDK streaming [https://blog.logrocket.com/nextjs-vercel-ai-sdk-streaming/] — corroborates Pattern 2

### Tertiary (LOW confidence — flagged for spike verification at Wave 0/1)
- Whether assistant-ui's code-block primitive does fence-state detection internally (A1) — verified at install
- Whether `useThreadMessage` exposes v6 `parts: Part[]` (A3) — verified at install
- AI SDK v6 `useChat.stop()` preserves partial (A2) — documented but worth a 5-line Vitest spike at Wave 0

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every library verified against npm registry on 2026-05-18; canonical assistant-ui v6 example pins these exact majors
- Architecture: HIGH — the SSE proxy + translation pattern is documented in AI SDK docs; the Phase 3 wire is fully understood from reading the actual turn.py
- Pitfalls: HIGH — twelve pitfalls cross-verified against multiple sources or directly from upstream issue trackers
- Validation Architecture: HIGH — the test scaffolding is conventional Next.js + Playwright; CI shape is clear
- Routing chip + metrics footer wiring: MEDIUM — depends on assistant-ui's exposure of AI SDK v6 `parts`; fallback path exists if the assumption fails

**Research date:** 2026-05-18
**Valid until:** ~2026-08-18 (3 months for the v6-era stack; AI SDK versions move fast — re-verify if execution slips past then)
