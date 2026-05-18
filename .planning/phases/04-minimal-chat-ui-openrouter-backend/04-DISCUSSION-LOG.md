# Phase 4: Minimal Chat UI (OpenRouter Backend) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in 04-CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-18
**Phase:** 04-minimal-chat-ui-openrouter-backend
**Areas discussed:** App scaffolding & monorepo shape; Streaming stack + SSE wire translation + abort; Message rendering: markdown + code-block no-flicker + routing chip + metrics layout; First-run / key-setup flow + BYOK plumbing

---

## App scaffolding & monorepo shape

### Q1: Dev orchestration — how should `pnpm dev` behave?

| Option | Description | Selected |
|--------|-------------|----------|
| (a) Two terminals | `uvicorn` + `pnpm --dir apps/web dev` separately; README documents both | ✓ |
| (b) `concurrently` | Repo-root `pnpm dev` runs both, interleaved logs | |
| (c) `make dev` | Shell target backgrounding uvicorn + foregrounding pnpm | |

**User's choice:** (a) Two terminals
**Notes:** Simplest, no new tooling. Phase 6 OSS-02 may revisit one-shot orchestration.

### Q2: Styling stack?

| Option | Description | Selected |
|--------|-------------|----------|
| (a) Tailwind v4 + shadcn/ui | Dominant stack in assistant-ui starter / AI SDK examples | ✓ |
| (b) Tailwind only | Hand-assembled primitives | |
| (c) CSS modules / vanilla | No Tailwind | |

**User's choice:** (a) Tailwind v4 + shadcn/ui

### Q3: Theme support in v1?

| Option | Description | Selected |
|--------|-------------|----------|
| (a) Light mode only | Defer dark mode to Phase 6 polish | ✓ |
| (b) next-themes light+dark | Both from day one | |
| (c) System-only auto | prefers-color-scheme single pair | |

**User's choice:** (a) Light mode only

### Q4: Env-var location and proxy target?

| Option | Description | Selected |
|--------|-------------|----------|
| (a) `apps/web/.env.local` + repo-root `.env` | Separated by language boundary | ✓ |
| (b) Single shared `.env` | Next loadEnvConfig from ../../.env | |
| (c) You decide | | |

**User's choice:** (a) Separate env files

---

## Streaming stack + SSE wire translation + abort

User direction: *"Just go with whatever option is belt and suspenders, hitting all the marks and making sure things are bulletproof."*

### Q1: Runtime hierarchy

| Option | Description | Selected |
|--------|-------------|----------|
| (a) assistant-ui root + AI SDK transport | Via `useChatRuntime` adapter; starter pattern | ✓ |
| (b) AI SDK only | Bare React message list; defer assistant-ui to Phase 5 | |
| (c) assistant-ui LocalRuntime hand-rolled | No AI SDK; manual EventSource | |

**User's choice (interpreted as bulletproof):** (a)
**Notes:** Battle-tested primitives + clean upgrade path to Phase 5 bubbles.

### Q2: SSE wire format at the proxy

| Option | Description | Selected |
|--------|-------------|----------|
| (a) Translate to AI SDK v5 UI Message Stream Protocol | Phase 3 named events preserved server-side; proxy translates | ✓ |
| (b) Custom AI SDK transport reads named events | No translation, but ties to transport API | |
| (c) Bypass AI SDK consumption | Raw EventSource in UI | |

**User's choice (bulletproof):** (a)

### Q3: Cancellation chain

| Option | Description | Selected |
|--------|-------------|----------|
| (a) Standard AbortController chain end-to-end | 2s budget asserted at 3 layers | ✓ |
| (b) Chain + explicit POST /cancel | Belt-and-suspenders with extra endpoint | |
| (c) You decide | | |

**User's choice (bulletproof):** (a) — rejected (b) as scope creep + race-condition surface; (a)'s "belt-and-suspenders at the test layer" with 3 independent 2s assertions is sufficient.

### Q4: Multi-turn history shape

| Option | Description | Selected |
|--------|-------------|----------|
| (a) Latest-message only, DB canonical | Proxy strips messages array | ✓ |
| (b) Full messages array forwarded | Risk of drift | |
| (c) Latest + clientHistoryHash | Over-engineered | |

**User's choice (bulletproof):** (a)

---

## Message rendering: markdown + code-block no-flicker + routing chip + metrics layout

User direction: *"bulletproof everything, core focus should be reliability and strong engineering principles"*

### Q1: Markdown library

| Option | Description | Selected |
|--------|-------------|----------|
| (a) @assistant-ui/react-markdown | assistant-ui-native; same maintainer | ✓ |
| (b) streamdown | Vercel's streaming-markdown renderer | |
| (c) Plain react-markdown | Max control, manual streaming-safety | |

**User's choice:** (a)
**Notes:** No cross-vendor drift; integrates natively with MessagePrimitive.Content.

### Q2: Code-block highlighter + no-flicker mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| (a) shiki via assistant-ui code-block primitive | Tested fence-state detection; one-time highlight on close | ✓ |
| (b) prism-react-renderer + manual fence tracking | | |
| (c) react-syntax-highlighter + manual fence tracking | | |

**User's choice:** (a)
**Notes:** Playwright DOM-snapshot assertion that highlighted swap happens exactly once per block.

### Q3: Routing chip placement & content

| Option | Description | Selected |
|--------|-------------|----------|
| (a) Above bubble, always visible, color-coded by backend | Phase-5-ready visual system | ✓ |
| (b) Inside bubble top edge | Visually integrated | |
| (c) Message footer next to metrics | Low visual weight | |

**User's choice:** (a)
**Notes:** Reads UI-04 SC literally; forward-compatible with Phase 5 CodeBubble/ComputerUseBubble colors.

### Q4: Per-turn metrics layout + mid-stream behavior

| Option | Description | Selected |
|--------|-------------|----------|
| (a) Monospace footer below bubble + "streaming…" mid-stream + chip pops on routing_decision SSE event | Honest UI; no misleading zeros | ✓ |
| (b) Metrics in hover tooltip on chip | Less discoverable | |
| (c) Metrics inline in chip | Cramped | |

**User's choice:** (a)
**Notes:** Requires Phase 3 wire-format amendment — new `routing_decision` SSE event before adapter dispatch (does NOT modify ChatChunk union). Contract test asserts event arrives <100ms after POST and equals Done.routing_signals byte-for-byte.

---

## First-run / key-setup flow + BYOK plumbing

User direction: *"bulletproof everything"*

### Q1: How does the UI detect "key not configured"?

| Option | Description | Selected |
|--------|-------------|----------|
| (a) Healthz on boot + 400/auth_failed catch on turn | Two independent triggers, same modal component | ✓ |
| (b) Boot-time healthz only | | |
| (c) Lazy: catch 400 on first turn only | | |

**User's choice:** (a)

### Q2: Where does the key entry live?

| Option | Description | Selected |
|--------|-------------|----------|
| (a) Blocking modal on first-run + persistent /settings route | Non-dismissible until key saved; same component reused | ✓ |
| (b) Dedicated /settings page only | First-run modal links there | |
| (c) Inline empty-state with embedded form | | |

**User's choice:** (a)

### Q3: What does the proxy do with the submitted key?

| Option | Description | Selected |
|--------|-------------|----------|
| (a) Server-side proxy; key never returns to browser; FastAPI KeyStore canonical | Belt-and-suspenders Next-side scrub | ✓ |
| (b) Same + encrypted httpOnly cookie cache | Adds attack surface | |
| (c) localStorage + per-turn send | Violates UI-17; REJECTED | |

**User's choice:** (a)
**Notes:** Regression test greps every Next-side log/response/cookie/header for literal key string — must match zero.

### Q4: Post-key-entry behavior

| Option | Description | Selected |
|--------|-------------|----------|
| (a) Modal closes optimistically; healthz round-trip before unblock | Catches rare PATCH-but-keystore-fail race | ✓ |
| (b) Hard browser reload | Jarring | |
| (c) Optimistic unblock without re-check | | |

**User's choice:** (a)

---

## Claude's Discretion

Areas where user deferred or no preference was expressed — captured in 04-CONTEXT.md `<decisions>` "Claude's Discretion" subsection:

- Thread creation in minimal mode (default thread auto-create via POST /api/v1/threads, localStorage persistence)
- Composer keybindings (Enter sends; Shift+Enter newline; Cmd+K focuses)
- StreamError UI surfacing (red inline banner in bubble + retry button for retriable=True)
- Loading state on composer (disable + spinner; Stop replaces Send after first chunk)
- shadcn component subset (Button, Dialog, Input, Sonner — pull others as needed)
- Assistant message timestamps (client-derived relative, absolute on hover)
- Empty-state visual (centered tagline; no sample prompts — Phase 5)
- Network error handling (503 with toast; auto-clear via 5s healthz polling)
- Default OpenRouter model (decide() picks)
- Composer placeholder ("Type a message…")
- Browser title ("Prompt-Optimizer")
- Favicon (simple SVG)

## Deferred Ideas

Captured in 04-CONTEXT.md `<deferred>` section — short list (full list in CONTEXT):

- Phase 5: Thread sidebar (UI-02), per-turn override slash commands (UI-05), CodeBubble (UI-09), ComputerUseBubble (UI-10), status dots (UI-11), settings panel (UI-12), thread auto-rename UI (UI-14), thumbs-down (UI-15), empty-state sample prompts (UI-16)
- Phase 6: Dark mode (next-themes), make setup orchestration, mobile-responsive
- Rejected: explicit POST /cancel endpoint, streamdown, cookie-encrypted key cache, localStorage key storage, hard reload after key submit, mid-stream metric placeholders, AI SDK v5 protocol direct from FastAPI, single shared .env
- Out of Scope per REQUIREMENTS/PROJECT: file attachments, voice input, web search button, public chat sharing, browser analytics
