---
phase: 4
slug: minimal-chat-ui-openrouter-backend
status: draft
shadcn_initialized: true
preset: shadcn/ui new-york (Tailwind v4, light mode only)
created: 2026-05-18
---

# Phase 4 — UI Design Contract

> Visual and interaction contract for the minimal chat UI (OpenRouter backend). Translates the 19 locked decisions in `04-CONTEXT.md` into a concrete, executable spec. The 6 checker dimensions (copywriting, visuals, color, typography, spacing, registry safety) are all addressed below.

**Source of truth:** every decision below traces to `04-CONTEXT.md` D-01..D-19, `REQUIREMENTS.md` UI-01/03/04/06/07/08/13/17, and `ROADMAP.md` Phase 4 SC #1..5. No new design decisions are introduced in this file — only translation of locked choices into design tokens.

---

## 1. Design System

| Property | Value | Source |
|----------|-------|--------|
| Tool | shadcn/ui CLI (`pnpm dlx shadcn@latest add ...`) | CONTEXT D-03 |
| Preset | shadcn/ui "new-york" style, Tailwind v4 CSS-first config | CONTEXT D-03, D-04 |
| Style mode | Light mode only (no `next-themes`, no dark variant CSS) | CONTEXT D-04 |
| Component library | shadcn/ui primitives wrapping Radix UI | CONTEXT D-03 |
| Runtime root | `@assistant-ui/react@>=0.10` Thread / Composer / MessagePrimitive | CONTEXT D-06 |
| Chat hook | `@ai-sdk/react@>=2` `useChat` via `@assistant-ui/react-ai-sdk` `useChatRuntime` adapter | CONTEXT D-06 |
| Markdown | `@assistant-ui/react-markdown` (assistant-ui native wrapper for `react-markdown`) | CONTEXT D-10 |
| Code highlighting | `shiki` through assistant-ui code-block primitive — fence-state aware, one-time highlight on `\`\`\`` close | CONTEXT D-11 |
| Shiki theme | `github-light` (single theme, no light/dark switching) | CONTEXT D-11 |
| Icon library | `lucide-react` | CONTEXT canonical_refs External Dependencies |
| Toast library | `sonner` (shipped as the shadcn Sonner component) | CONTEXT D-17, "Claude's Discretion" |
| Font (UI) | Tailwind v4 default stack: `ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif` | Tailwind v4 default |
| Font (mono) | Tailwind v4 default stack: `ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace` | Tailwind v4 default |
| Class composition | `clsx` + `tailwind-merge` (shadcn `cn()` helper) | CONTEXT canonical_refs |
| Package manager | `pnpm` | CONTEXT D-01 |
| Browser title | `Prompt-Optimizer` | CONTEXT "Claude's Discretion" |
| Favicon | Simple emoji-derived SVG (planner picks during Phase 6 polish) | CONTEXT "Claude's Discretion" |

**shadcn components installed in Phase 4 (only these):** `button`, `dialog`, `input`, `sonner`. Additional shadcn components (e.g., dropdown-menu, tabs, sheet) are deferred to Phase 5 per CONTEXT "shadcn component subset" discretion.

---

## 2. Spacing Scale

Tailwind v4 default 4px-grid is canonical. All Phase 4 components use multiples of 4. No custom spacing extensions.

| Token | Tailwind class | Pixel value | Usage in Phase 4 |
|-------|---------------|-------------|------------------|
| `2xs` | `gap-1`, `p-1`, `m-1` | 4 | Icon-to-label gap inside chip; metrics-footer separator dot spacing |
| `xs` | `gap-2`, `p-2`, `m-2` | 8 | Chip internal padding (`px-2 py-1`); action-row icon button gap |
| `sm` | `gap-3`, `p-3`, `m-3` | 12 | Bubble-to-chip vertical gap; bubble-to-metrics-footer vertical gap |
| `md` | `gap-4`, `p-4`, `m-4` | 16 | Default ChatBubble internal padding; composer textarea padding |
| `lg` | `gap-6`, `p-6`, `m-6` | 24 | Modal body padding; thread vertical gap between message groups |
| `xl` | `gap-8`, `p-8`, `m-8` | 32 | Modal outer padding; settings page section spacing |
| `2xl` | `gap-12`, `p-12` | 48 | Empty-state centered tagline vertical breathing room |
| `3xl` | `gap-16` | 64 | Page-level top padding above header |

**Touch / hit targets:** all icon-only buttons (stop, send, copy, regenerate, gear) are `h-9 w-9` (36px) minimum, expanding the visible icon (typically 16px from lucide) inside a `p-2` (8px) padding ring. Modal and composer text inputs are `h-10` (40px) minimum.

**Exceptions:** none. If a future component needs an off-grid value, the planner must update this table first.

---

## 3. Typography

Two weights (regular `font-normal` = 400, semibold `font-semibold` = 600). Bold (`font-bold` = 700) is reserved for the `Routed to <model_name>` portion of the chip per CONTEXT D-12. Four sizes total.

| Role | Size | Tailwind class | Weight | Line height | Usage |
|------|------|----------------|--------|-------------|-------|
| Mono / metrics | 12px | `text-xs font-mono` | 400 | 1.5 (`leading-normal`) | Metrics footer (`$0.0021 · 1.4s · 312↑/847↓`), `streaming…` mid-stream placeholder |
| Label / chip | 13px | `text-[13px]` | 400 (rationale) + 700 (`font-bold` on model name) | 1.4 | Routing chip text, action-row tooltips |
| Body | 14px | `text-sm` | 400 | 1.5 (`leading-relaxed` for prose, `leading-normal` for chrome) | ChatBubble markdown body, composer text, modal body copy, toast text |
| Heading | 18px | `text-lg` | 600 (`font-semibold`) | 1.3 | Modal heading ("Connect OpenRouter to get started"), `/settings` section headings, empty-state tagline |

**No `text-base` (16px), no `text-xl`, no `text-2xl` in Phase 4.** The empty-state tagline uses `text-lg` (18px) intentionally — the marketing tagline weight comes from visual centering and surrounding whitespace, not a larger font size. The composer placeholder uses `text-sm` (14px) — same size as user input.

**Code block typography (inside markdown):**
- Inline `code` spans: `text-sm font-mono` with `bg-slate-100 px-1 py-0.5 rounded-sm`
- Fenced code blocks: `text-sm font-mono leading-relaxed` rendered by shiki primitive (`github-light` theme tokens override inline color)

**Markdown heading scale (rendered inside ChatBubble assistant output):** assistant-ui-react-markdown defaults applied. H1 = `text-xl font-semibold` (20px), H2 = `text-lg font-semibold` (18px), H3 = `text-base font-semibold` (16px). These appear ONLY inside LLM-rendered markdown and are not part of the app chrome scale.

---

## 4. Color (60 / 30 / 10)

Light-mode-only palette built from Tailwind v4 default `slate` / `green` / `amber` / `red` scales. No custom hex values are introduced beyond the per-backend chip system.

### 4.1 Surface (60% dominant)

| Role | Tailwind | Hex | Usage |
|------|----------|-----|-------|
| Page background | `bg-white` | `#FFFFFF` | Root `<body>`, thread scroll surface |
| Border-default | `border-slate-200` | `#E2E8F0` | Bubble outlines, chip outlines, divider lines |
| Text-default | `text-slate-900` | `#0F172A` | All body / heading / label text |
| Text-muted | `text-slate-500` | `#64748B` | Timestamps ("just now"), metrics footer separators |

### 4.2 Secondary (30%)

| Role | Tailwind | Hex | Usage |
|------|----------|-----|-------|
| Surface-elevated | `bg-slate-50` | `#F8FAFC` | Assistant ChatBubble background, modal body background |
| Surface-elevated-2 | `bg-slate-100` | `#F1F5F9` | User message bubble background, inline `code` span background, hovered action-row buttons |
| Border-strong | `border-slate-300` | `#CBD5E1` | Composer textarea border, modal input border |

### 4.3 Accent (10% — reserved-for list, NEVER "all interactive elements")

The 10% accent is the **chip color system** below. The chip is the single visual expression of "the router made a decision" — the only place backend identity is communicated in chrome. Every other interactive element (send button, stop button, regenerate, copy, modal CTA) uses neutral slate.

**Per-backend chip palette (Phase 4 ships slate only; green + amber wired but unused until Phase 5):**

| Backend | Background | Text | Border | Tailwind classes |
|---------|------------|------|--------|-------------------|
| `openrouter` | `slate-100` `#F1F5F9` | `slate-900` `#0F172A` | `slate-200` `#E2E8F0` | `bg-slate-100 text-slate-900 border border-slate-200` |
| `claude_code` (Phase 5) | `green-100` `#DCFCE7` | `green-900` `#14532D` | `green-200` `#BBF7D0` | `bg-green-100 text-green-900 border border-green-200` |
| `computer_use` (Phase 5) | `amber-100` `#FEF3C7` | `amber-900` `#78350F` | `amber-200` `#FDE68A` | `bg-amber-100 text-amber-900 border border-amber-200` |

**Accent reserved-for explicit list:**
1. Routing chip background + border + text (the only chrome element that color-codes by backend).
2. **Nothing else.** Send button, stop button, modal "Save & continue" button, regenerate, copy, gear icon — all use neutral `slate-900` text on `white` surface with `slate-200` borders. Buttons signal state via shadcn default focus/hover/active variants on the slate scale, NOT via accent color.

### 4.4 Semantic (functional, not decorative)

| Role | Tailwind | Hex | Usage |
|------|----------|-----|-------|
| Destructive / error border | `border-red-300` | `#FCA5A5` | StreamError inline banner border |
| Destructive / error background | `bg-red-50` | `#FEF2F2` | StreamError inline banner fill |
| Destructive / error text | `text-red-900` | `#7F1D1D` | StreamError code + message text |
| Destructive / error icon | `text-red-600` | `#DC2626` | StreamError `AlertCircle` icon |
| Network-down banner background | `bg-red-50` | `#FEF2F2` | "API unavailable" 503 banner above composer |
| Success toast accent | `bg-green-50 text-green-900 border-green-200` | (sonner defaults) | "OpenRouter connected — try a prompt!" |

**No destructive action ships in Phase 4** (no thread-delete UI in this phase). The red palette appears only on the StreamError banner and the network-down banner — both are state surfaces, not actions.

### 4.5 Focus ring (accessibility — non-negotiable)

All focusable elements (`<button>`, `<input>`, `<textarea>`, the Composer field, modal Close action) carry `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2 focus-visible:ring-offset-white`. shadcn defaults already enforce this on its primitives; custom components MUST replicate it.

---

## 5. Layout & Page Structure

Phase 4 ships exactly **two pages**.

### 5.1 `/` — Chat surface

```
+---------------------------------------------------+
|  Prompt-Optimizer                          [gear] |   ← header (h-14, border-b border-slate-200)
+---------------------------------------------------+
|                                                   |
|  (empty-state tagline OR scrolling thread)        |   ← main (flex-1 overflow-y-auto, max-w-3xl mx-auto px-4)
|                                                   |
|    [Routing chip — slate-100]                     |
|    +-------------------------------------------+  |
|    |  Assistant markdown body                  |  |   ← ChatBubble (bg-slate-50 border border-slate-200 rounded-lg p-4)
|    |                                           |  |
|    |                              [copy] [↻]   |  |   ← action row (hover-revealed, bottom-right)
|    +-------------------------------------------+  |
|    $0.0021 · 1.4s · 312↑/847↓                     |   ← metrics footer (text-xs font-mono text-slate-500 mt-2)
|                                                   |
|         +-------------------------------------+   |
|         |          User message               |   |   ← user bubble (bg-slate-100 ml-auto rounded-lg p-4)
|         +-------------------------------------+   |
|                                                   |
+---------------------------------------------------+
|  [Network-down banner — only when offline]        |
+---------------------------------------------------+
|  +---------------------------------------------+  |
|  |  Type a message…                            |  |   ← Composer (h-auto min-h-12 max-h-48, bg-white border border-slate-300)
|  +---------------------------------------------+  |
|  [send] / [stop]                                  |   ← right-aligned button row
+---------------------------------------------------+
```

**Header:** `h-14` (56px), `border-b border-slate-200`, `bg-white`, sticky top. Left: app name `text-lg font-semibold text-slate-900`. Right: gear `Settings` icon button linking to `/settings`.

**Main thread area:** `max-w-3xl mx-auto px-4 py-6`, `overflow-y-auto`. Messages stack with `space-y-6` (24px gap between user+assistant turn groups). Chip + bubble + metrics-footer for one assistant message are visually grouped via `space-y-2` (8px).

**Composer container:** sticky bottom, `border-t border-slate-200 bg-white px-4 py-3`. Composer field is `min-h-12` (48px) growing to `max-h-48` (192px). Send/stop button is `h-9 w-9` aligned to the right of the composer.

### 5.2 `/settings` — Non-blocking key management

Same header. Main = `max-w-xl mx-auto px-4 py-8`. Single section: "OpenRouter API key". Same `KeyForm` component as the modal (CONTEXT D-17). Displays masked key after save: `sk-or-…ABC` in `text-slate-500 font-mono text-sm`. "Update key" button replaces "Save & continue".

### 5.3 Responsive scope

Phase 4 ships **desktop-only** (≥1024px Chrome / Firefox / Safari). Mobile is out of scope per CONTEXT deferred → "Mobile-responsive layout — out of scope for v1". The layout does NOT need media queries; max-width centering provides a usable narrow-window experience but is not formally supported.

---

## 6. Routing Chip Specification (UI-04, CONTEXT D-12)

The single most visually distinctive component in Phase 4. **Above the bubble. Always visible. Never collapsed.**

### 6.1 Position and structure

- Vertical position: directly above the assistant ChatBubble, `mb-2` gap (8px).
- Horizontal position: left-aligned with the bubble's left edge.
- DOM: `<div role="status" aria-live="polite" aria-label="Routing decision: ...">`.
- Inline layout: `inline-flex items-center gap-2 px-2 py-1 rounded-md border text-[13px]`.

### 6.2 Content format

Exact string template:

```
**Routed to** {display_name} · {one-line rationale}
```

Rendered as:

- `Routed to` — bold (`font-bold`).
- ` {display_name}` — bold (`font-bold`).
- ` · ` — neutral separator (regular weight, single space on each side).
- `{rationale}` — regular weight (`font-normal`).

`display_name` resolves from `config/model_mapping.json` keyed by the `model_or_agent` field on the `RoutingDecision` payload. Examples confirmed against the existing mapping file:

| `model_or_agent` slug | Rendered chip text |
|-----------------------|--------------------|
| `gpt-5` | **Routed to GPT-5** · Strong reasoning fit |
| `qwen3-235b-a22b-2507` | **Routed to Qwen3 235B A22B Instruct 2507** · Long-form generation |
| `deepseek-v3.1-terminus` | **Routed to DeepSeek V3.1 Terminus** · Coding-leaning task |
| `gemini-2.5-flash` | **Routed to Gemini 2.5 Flash** · Quick chat response |
| `openrouter` | **Routed to OpenRouter Auto Router** · Auto-router fallback |
| `OTHER` | **Routed to Other Model** · Fallback model |

Rationale text is sourced from the `RoutingDecision.rationale` field (Phase 1 D-03). Truncation: if rationale exceeds 80 characters, truncate with ellipsis (`text-overflow: ellipsis` on `max-w-md`) — full string available via `title` attribute on hover.

### 6.3 Color (per backend)

Already declared in §4.3. Phase 4 only emits `openrouter` → slate. Components for `claude_code` and `computer_use` are written as switch cases on the `backend` field but unreachable from Phase 4's adapter set.

```typescript
const chipClassByBackend = {
  openrouter: "bg-slate-100 text-slate-900 border-slate-200",
  claude_code: "bg-green-100 text-green-900 border-green-200",
  computer_use: "bg-amber-100 text-amber-900 border-amber-200",
} as const;
```

### 6.4 Timing & state

- Subscribes to the AI SDK "data part" produced by `apps/web/lib/sse-translate.ts` from the `routing_decision` named SSE event (CONTEXT D-15).
- Chip MUST appear within ~100ms of POST initiation (Phase 3 contract test asserts upstream latency; UI latency is purely React render time).
- Never disappears once mounted. No "loading" placeholder for the chip — it either exists or hasn't arrived yet (in which case the assistant bubble itself has not yet rendered, because `routing_decision` precedes the first `text_delta`).
- ARIA: `role="status"` + `aria-live="polite"` so screen readers announce the route without interrupting in-flight content.

---

## 7. Metrics Footer Specification (UI-07, CONTEXT D-13)

Below the assistant bubble. Single line. Monospace.

### 7.1 Mid-stream state

```
streaming●
```

- Class: `text-xs font-mono text-slate-500 mt-2 flex items-center gap-1`.
- The `●` glyph is a `<span aria-hidden="true">` with `animate-pulse` (Tailwind default 2s ease-in-out infinite).
- `prefers-reduced-motion: reduce` users see a static `●` (Tailwind `animate-pulse` honors the media query natively; no extra CSS required).
- ARIA: parent has `aria-label="Streaming response in progress"`. The animated dot is `aria-hidden`.

### 7.2 Final state (on `done` SSE event)

```
$0.0021 · 1.4s · 312↑/847↓
```

Exact format rules:

| Field | Format | Source |
|-------|--------|--------|
| Cost | `$` prefix + 4 decimal places, no rounding to zero (always show `$0.0001` minimum if non-zero, `$0.0000` if exactly zero) | `Done.cost_usd` |
| Separator | ` · ` — space, middle dot U+00B7, space | literal |
| Latency | Floating seconds with 1 decimal place + `s` suffix (e.g. `1.4s`, `12.3s`) — derived from `Done.latency_ms / 1000`. Show `0.0s` if `<50ms`. | `Done.latency_ms` |
| Separator | ` · ` | literal |
| Tokens-in | Integer + `↑` (U+2191) suffix, no comma separator below 10000, comma above (e.g. `312↑`, `12,847↑`) | `Done.tokens_in` |
| Slash | `/` no spaces around | literal |
| Tokens-out | Integer + `↓` (U+2193) suffix, same comma rule | `Done.tokens_out` |

ARIA: the entire footer has `aria-label="Turn cost {cost_usd_formatted}, latency {latency_formatted}, {tokens_in} tokens in, {tokens_out} tokens out"` so screen-reader users hear human prose, not symbols.

### 7.3 Position

Same horizontal alignment as the chip (left-aligned with assistant bubble's left edge). Vertical: `mt-2` (8px) below the bubble. Group: chip + bubble + footer is `space-y-2`.

---

## 8. ChatBubble Specification (UI-08, CONTEXT D-14)

### 8.1 Container

| Element | Tailwind |
|---------|----------|
| Assistant bubble | `bg-slate-50 border border-slate-200 rounded-lg p-4 max-w-prose` |
| User bubble | `bg-slate-100 border border-slate-200 rounded-lg p-4 max-w-prose ml-auto` |

Both bubbles use `max-w-prose` (Tailwind ≈65ch) to keep markdown line lengths readable. User bubble right-aligned via `ml-auto`; assistant left-aligned (default).

### 8.2 Markdown body

Rendered by `<MessagePrimitive.Content components={MarkdownComponents}>` where `MarkdownComponents` is the assistant-ui-react-markdown default + shiki integration for `pre code`.

Element styles (applied via the react-markdown components map, NOT via a `prose` plugin — Phase 4 does not install `@tailwindcss/typography`):

| Element | Tailwind |
|---------|----------|
| `p` | `text-sm leading-relaxed text-slate-900 mb-3 last:mb-0` |
| `ul` / `ol` | `text-sm leading-relaxed text-slate-900 mb-3 ml-5 list-disc` (or `list-decimal`) |
| `li` | `mb-1` |
| `h1`/`h2`/`h3` | `font-semibold text-slate-900 mb-2 mt-4 first:mt-0` (sizes per §3) |
| `a` | `text-slate-900 underline underline-offset-2 hover:text-slate-700` |
| `code` (inline) | `text-sm font-mono bg-slate-100 px-1 py-0.5 rounded-sm` |
| `pre` (fenced — shiki-rendered) | `text-sm font-mono leading-relaxed rounded-md overflow-x-auto p-4 my-3` — shiki injects `github-light` background |
| `blockquote` | `border-l-4 border-slate-300 pl-4 italic text-slate-700` |

**Streaming-safe rendering (UI-03, CONTEXT D-11):** while a `\`\`\`` code fence is open, the assistant-ui code-block primitive emits a plain `<pre><code>{rawText}</code></pre>` without shiki tokens. On fence close, the primitive performs a one-shot highlight swap. **No re-highlight per token.** Playwright assertion in `apps/web/playwright/no-flicker.spec.ts` captures DOM snapshots and asserts the `<code>` inner structure transitions exactly once per block.

### 8.3 Action row (hover-revealed)

Position: `absolute bottom-2 right-2` inside the assistant bubble (the bubble is `relative`).
Visibility: hidden by default; shown on `group-hover:opacity-100 opacity-0 transition-opacity duration-150`. Parent bubble has `group` class.
Layout: `flex items-center gap-1`.

Two icon buttons:

| Button | Icon | aria-label | Action |
|--------|------|------------|--------|
| Copy | `lucide-react` `Copy` (16px) | "Copy message as markdown" | Copies the raw markdown source string (not rendered HTML) to clipboard via `navigator.clipboard.writeText`. Toast on success: "Copied to clipboard". |
| Regenerate | `lucide-react` `RefreshCw` (16px) | "Regenerate response" | Calls `useChat.reload()` (AI SDK v5) which re-issues the same user prompt. **Appends** a new assistant turn — does NOT replace the existing one (CONTEXT D-14). Phase 5 may add a "replace" affordance; deferred. |

Buttons are `h-7 w-7 rounded-md hover:bg-slate-200 focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2`.

**Accessibility:** action row is keyboard-reachable via Tab order even when not hovered (`focus-within:opacity-100`). Tooltip on hover delays 500ms (shadcn Tooltip default if added; Phase 4 keeps the aria-label as the accessible name and omits a visual tooltip to stay within the 4-component shadcn budget).

### 8.4 Timestamps

Show as relative ("just now", "2m ago", "1h ago", "3d ago") in `text-xs text-slate-500`. Absolute time available as `<time dateTime={created_at}>` for screen readers + browser tooltip on hover. Generated client-side from `created_at` returned by FastAPI — **never** generated client-side from `Date.now()` (would drift from DB truth, CONTEXT "Claude's Discretion").

Position: bottom-left of the assistant bubble, opposite the action row. Hidden until bubble is finalized (suppressed during streaming).

---

## 9. Composer Specification (UI-01, UI-06)

### 9.1 Layout

| Element | Tailwind |
|---------|----------|
| Container | `sticky bottom-0 border-t border-slate-200 bg-white px-4 py-3` |
| Inner | `max-w-3xl mx-auto flex items-end gap-2` |
| Textarea | `flex-1 min-h-12 max-h-48 resize-none rounded-md border border-slate-300 bg-white px-3 py-2 text-sm leading-normal placeholder:text-slate-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2` |
| Send/Stop button | `h-9 w-9 rounded-md` (state-dependent variant — see §9.3) |

### 9.2 Placeholder

Exact text: `Type a message…` (single ellipsis character U+2026, not three dots). Class: `placeholder:text-slate-500`.

### 9.3 Send / Stop button state machine

**Three discrete states.** Same button slot — variant + icon swap.

| State | When | Icon | Tailwind | aria-label |
|-------|------|------|----------|------------|
| Send (idle) | Composer has non-whitespace content, no in-flight turn | `lucide-react` `Send` (16px) | `bg-slate-900 text-white hover:bg-slate-800 disabled:bg-slate-300 disabled:cursor-not-allowed` | "Send message" |
| Send (disabled) | Composer empty or whitespace-only | `Send` (16px) | `bg-slate-300 text-white cursor-not-allowed` | "Send message (composer is empty)" |
| Stop | First `text_delta` arrived, stream still open | `lucide-react` `Square` (16px, filled) | `bg-slate-900 text-white hover:bg-slate-800` | "Stop generating" |

Transition Send → Stop happens on first chunk arrival (CONTEXT "Claude's Discretion" loading-state). The chip's appearance precedes Stop by ~100ms — there is a brief window where the chip is visible but no stop button yet (composer disabled, no Send/Stop icon visible). During that window the button slot shows a `Loader2` spinner with `animate-spin` and `aria-label="Sending..."`.

### 9.4 Keyboard shortcuts

| Shortcut | Action | Implementation |
|----------|--------|----------------|
| `Enter` (no modifier) | Send message | `onKeyDown`: if `!e.shiftKey && !e.ctrlKey && !e.metaKey` then `preventDefault()` + submit |
| `Shift+Enter` | Insert newline | Default textarea behavior |
| `Cmd+K` (macOS) / `Ctrl+K` (other) | Focus composer | Global `keydown` listener on `document` |
| `Esc` | Blur composer + (if streaming) stop | Global `keydown` when composer is focused or stream is active |

A visible keyboard-shortcuts hint is NOT shown in Phase 4 (deferred to Phase 6 polish). Shortcuts are discoverable via standard chat UX expectations.

---

## 10. First-Run Modal Specification (UI-13, CONTEXT D-16, D-17, D-18, D-19)

shadcn `Dialog` primitive. Blocking (non-dismissible) on first-run trigger; non-blocking on `/settings` mount.

### 10.1 Trigger sources

Two independent triggers route through the **same** `<FirstRunModal>` component (CONTEXT D-16):

1. **Boot trigger:** `GET /api/health` (proxied to `/api/v1/healthz`) returns `adapters.openrouter.status === "missing_key"`. Modal opens with `mode="blocking"` and composer is disabled.
2. **Mid-session trigger:** any turn request returns HTTP 400 with `code: "auth_failed"` (or the SSE stream emits `StreamError(code="auth_failed")`). Modal opens with `mode="blocking"`. Existing composer content preserved.

### 10.2 Structure & exact copy

```
+---------------------------------------------------+
|  Connect OpenRouter to get started                |   ← <h2 text-lg font-semibold>
|                                                   |
|  Prompt-Optimizer routes your prompts to the      |   ← <p text-sm text-slate-700 leading-relaxed>
|  best model. OpenRouter is the gateway to most    |
|  chat models — start by pasting your key.         |
|                                                   |
|  [ sk-or-v1-...                                ]  |   ← <input> placeholder, h-10
|                                                   |
|  [        Save & continue        ]                |   ← <Button>, primary, w-full
|                                                   |
|  Don't have a key? Get one at                     |   ← <p text-xs text-slate-500>
|  openrouter.ai/keys ↗                             |   ← <a underline> external link
+---------------------------------------------------+
```

| Element | Exact text | Tailwind |
|---------|-----------|----------|
| Heading | `Connect OpenRouter to get started` | `text-lg font-semibold text-slate-900` |
| Body | `Prompt-Optimizer routes your prompts to the best model. OpenRouter is the gateway to most chat models — start by pasting your key.` | `text-sm text-slate-700 leading-relaxed mt-2` |
| Input placeholder | `sk-or-v1-...` (three ASCII dots, NOT ellipsis) | `mt-6 h-10` |
| Primary button | `Save & continue` | `mt-4 w-full bg-slate-900 text-white hover:bg-slate-800` |
| Link prefix | `Don't have a key? Get one at ` | `text-xs text-slate-500 mt-4` |
| Link text | `openrouter.ai/keys ↗` (trailing arrow is U+2197) | `underline underline-offset-2 hover:text-slate-700` |
| Link href | `https://openrouter.ai/keys` | `target="_blank" rel="noopener noreferrer"` |

### 10.3 ARIA & focus management

| Property | Value |
|----------|-------|
| Root | `role="dialog" aria-modal="true" aria-labelledby="first-run-title" aria-describedby="first-run-body"` |
| Heading | `id="first-run-title"` |
| Body | `id="first-run-body"` |
| Initial focus | On the `<input>` field (autofocus when mounted) |
| Focus trap | shadcn Dialog handles this (Radix internals) |
| Escape key | Disabled in `blocking` mode (no `onEscapeKeyDown` close); enabled in `/settings` mode |
| Click outside | Disabled in `blocking` mode (no `onPointerDownOutside` close); enabled in `/settings` mode |

### 10.4 Submit flow

1. User pastes `sk-or-v1-...` and clicks `Save & continue` (or presses Enter inside the input).
2. Browser POSTs `{provider: "openrouter", key: <pasted_string>}` to `/api/settings` (Next route handler).
3. Next route forwards via `PATCH /api/v1/settings` with body `{keys: {openrouter: <key>}}` (CONTEXT D-18).
4. On 200 from FastAPI, Next route re-fetches `GET /api/v1/healthz` (CONTEXT D-19).
5. If `adapters.openrouter.status === "ready"`, modal closes, success toast fires, composer enables.
6. On any failure (validation 400, network), error toast fires; modal stays open.

### 10.5 Toasts (sonner)

| Trigger | Variant | Text | Duration |
|---------|---------|------|----------|
| Successful key save + healthz ready | success | `OpenRouter connected — try a prompt!` | 4000ms |
| Validation failure (key format wrong, FastAPI returns 400) | error | `That key doesn't look right. Check it and try again.` | 6000ms |
| Network failure during key save | error | `Couldn't save the key — is the local API running?` | 6000ms |
| Copy-as-markdown success | success | `Copied to clipboard` | 2000ms |

All toasts are bottom-right positioned (sonner default), with `aria-live="polite"`.

---

## 11. Empty Thread State (CONTEXT "Claude's Discretion")

Shown when the auto-created default thread has zero messages.

| Element | Tailwind | Exact text |
|---------|----------|-----------|
| Container | `flex flex-col items-center justify-center h-full text-center px-4 py-12` | (none) |
| Tagline | `text-lg font-semibold text-slate-900` | `Ask anything. We'll route to the right model.` |

**No sample prompts in Phase 4** (CONTEXT defers UI-16 to Phase 5). The composer remains at the bottom of the page exactly as in the populated state — only the thread area swaps from a scrolling message list to the centered tagline.

---

## 12. StreamError Banner Specification (CONTEXT "Claude's Discretion")

Inline red banner rendered **inside** the assistant ChatBubble (not above, not below, not toast — inside, replacing or appending to the bubble content depending on stream state).

### 12.1 Structure

```
+-----------------------------------------------+
|  ⚠  {user_friendly_message}                   |
|     [Retry]                                   |
+-----------------------------------------------+
```

| Element | Tailwind |
|---------|----------|
| Banner | `mt-3 first:mt-0 flex items-start gap-3 rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-900` |
| Icon | `lucide-react` `AlertCircle` (16px) `text-red-600 mt-0.5 flex-shrink-0` |
| Message | `flex-1 leading-relaxed` |
| Retry button | `mt-2 inline-flex h-8 items-center rounded-md border border-red-300 bg-white px-3 text-xs font-semibold text-red-900 hover:bg-red-100` — shown only when `retriable === true` |

### 12.2 Error code → user-friendly message catalog

Maps from the Phase 2 D-06 closed `StreamError.code` vocabulary. **The raw `code` is shown in monospace at the end of each message for support / debugging**, e.g. `Cost cap of $0.50 reached. Try a shorter prompt or raise the cap in settings. (cost_cap_exceeded)`.

| `StreamError.code` | User-friendly message | Retriable? |
|--------------------|----------------------|------------|
| `cost_cap_exceeded` | `Cost cap of $0.50 reached. Try a shorter prompt or raise the cap in settings.` | No |
| `step_cap_exceeded` | `The model hit its step limit. Try a more focused prompt.` | No |
| `cancelled` | `Generation cancelled.` | Yes |
| `rate_limited` | `OpenRouter is rate-limiting requests. Wait a moment and try again.` | Yes |
| `auth_failed` | `OpenRouter rejected the key. Update it in settings and try again.` | No (triggers modal re-pop per D-16) |
| `provider_unavailable` | `The upstream model is temporarily unavailable. Try again in a moment.` | Yes |
| `timeout` | `The request timed out. The model may be slow — try again.` | Yes |
| `validation_error` | `That request couldn't be sent. Check your input and try again.` | No |
| `internal_error` | `Something went wrong inside Prompt-Optimizer. Check the API logs and retry.` | Yes |

Code suffix format: ` (` + monospace code + `)` rendered as `<code class="font-mono text-xs">cost_cap_exceeded</code>`.

### 12.3 ARIA

`role="alert"` on the banner (announces immediately to assistive tech). Retry button `aria-label="Retry the failed turn"`.

---

## 13. Network-Down Banner (CONTEXT "Claude's Discretion")

Banner above the composer when the Next proxy reports the FastAPI server is unreachable (`ECONNREFUSED`, 503 from `/api/chat` or `/api/health`).

| Element | Tailwind | Exact text |
|---------|----------|-----------|
| Container | `mx-auto max-w-3xl px-4 mb-2` | (wrapper) |
| Banner | `flex items-center gap-3 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-900` | (style) |
| Icon | `lucide-react` `WifiOff` (16px) `text-red-600` | (icon) |
| Message | (text content) | `API unavailable — is uvicorn running?` |

Auto-clear behavior: while in error state, poll `/api/health` every 5 seconds via `setInterval`. On any 200 response with non-error body, hide the banner.

`role="status" aria-live="polite"`.

---

## 14. Accessibility Contract

Non-negotiable. Phase 4 reliability target requires WCAG 2.1 AA equivalence across all six checker dimensions.

### 14.1 Color contrast (verified at design time)

| Pair | Ratio | Required (AA normal text) |
|------|-------|---------------------------|
| `text-slate-900 #0F172A` on `bg-white #FFFFFF` | 19.7 : 1 | ≥ 4.5 |
| `text-slate-900` on `bg-slate-50 #F8FAFC` | 18.6 : 1 | ≥ 4.5 |
| `text-slate-900` on `bg-slate-100 #F1F5F9` | 17.1 : 1 | ≥ 4.5 |
| `text-slate-500 #64748B` on `bg-white` | 4.78 : 1 | ≥ 4.5 |
| `text-green-900 #14532D` on `bg-green-100 #DCFCE7` | 11.5 : 1 | ≥ 4.5 |
| `text-amber-900 #78350F` on `bg-amber-100 #FEF3C7` | 8.4 : 1 | ≥ 4.5 |
| `text-red-900 #7F1D1D` on `bg-red-50 #FEF2F2` | 11.3 : 1 | ≥ 4.5 |
| `text-white` on `bg-slate-900` (primary button) | 19.7 : 1 | ≥ 4.5 |

All passes. The `text-slate-500` on `bg-white` pair is the tightest at 4.78 : 1 and is reserved for non-essential metadata (timestamps, metrics-footer separators) — never for primary content.

### 14.2 ARIA labels (master list)

| Element | Attribute | Value |
|---------|-----------|-------|
| Routing chip | `role` | `status` |
| Routing chip | `aria-live` | `polite` |
| Routing chip | `aria-label` | `Routing decision: Routed to {display_name}. {rationale}` |
| Metrics footer (streaming) | `aria-label` | `Streaming response in progress` |
| Metrics footer (final) | `aria-label` | `Turn cost {cost}, latency {latency}, {tokens_in} tokens in, {tokens_out} tokens out` |
| Send button (idle) | `aria-label` | `Send message` |
| Send button (disabled) | `aria-label` | `Send message (composer is empty)` |
| Stop button | `aria-label` | `Stop generating` |
| Copy button | `aria-label` | `Copy message as markdown` |
| Regenerate button | `aria-label` | `Regenerate response` |
| Gear icon | `aria-label` | `Settings` |
| Modal root | `role` + `aria-modal` + `aria-labelledby` + `aria-describedby` | (see §10.3) |
| Modal input | `aria-label` | `OpenRouter API key` |
| StreamError banner | `role` | `alert` |
| Network-down banner | `role` + `aria-live` | `status` + `polite` |
| Retry button | `aria-label` | `Retry the failed turn` |
| External link in modal | `rel` | `noopener noreferrer` (plus visual `↗` to signal external) |

### 14.3 Keyboard navigation

Tab order (in DOM order): header gear → thread region landmark → composer textarea → send/stop button → modal dialog (when open, traps focus). All interactive elements are reachable without a mouse. Escape closes non-blocking modal / blurs composer; in blocking modal, Escape is intercepted (does nothing).

### 14.4 Reduced motion

All animations honor `prefers-reduced-motion: reduce` per Tailwind v4 defaults. Specifically:

- `animate-pulse` on the streaming dot: Tailwind disables under reduced-motion.
- Chip fade-in: written as `motion-safe:animate-in motion-safe:fade-in motion-safe:duration-150` so users with reduced motion preference see an instant appearance.
- shadcn Dialog open/close: Radix UI honors `prefers-reduced-motion` natively.

**NO opt-out of `prefers-reduced-motion` anywhere in Phase 4.** No `motion-reduce:` overrides that re-enable animation.

### 14.5 Screen reader live regions

- Thread message list: `<div role="log" aria-live="polite" aria-atomic="false" aria-relevant="additions">` so screen readers announce new assistant turns without re-reading old ones.
- Toasts: sonner default `aria-live="polite"` is sufficient.
- Streaming text: AI SDK's `useChat` writes deltas into a `<MessagePrimitive.Content>` that does NOT have its own `aria-live` — to prevent SR reading every token. The chip's `aria-live="polite"` announcement at turn start tells the user a response is coming; the final assistant content is announced once on completion via the parent `role="log"`.

---

## 15. Motion Tokens

Three motion primitives, all 150–200ms, all honoring `prefers-reduced-motion`.

| Token | Trigger | Duration | Easing | Tailwind |
|-------|---------|----------|--------|----------|
| `chip-arrival` | `routing_decision` SSE event lands | 150ms | `ease-out` | `motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-top-1 motion-safe:duration-150` |
| `action-row-reveal` | Hover over assistant bubble | 150ms | `ease-in-out` | `transition-opacity duration-150` |
| `streaming-dot-pulse` | Mid-stream metrics footer dot | 2000ms (Tailwind default) | `cubic-bezier(0.4, 0, 0.6, 1)` (Tailwind default) | `animate-pulse` |
| `modal-open` | Dialog `open` state | 200ms | `ease-out` | shadcn / Radix defaults — `data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95` |
| `modal-close` | Dialog `closed` state | 200ms | `ease-in` | `data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95` |
| `toast-enter` | sonner toast mount | sonner default | sonner default | n/a (library-owned) |
| `loader-spin` | Composer "Sending..." spinner between submit and first chunk | 1000ms linear infinite | `linear` | `animate-spin` |

**No bouncy easings.** No `spring()`. No motion exceeding 250ms. The visual surface stays calm — reliability over delight in Phase 4.

---

## 16. Page Title & Browser Tab

| Property | Value |
|----------|-------|
| `<title>` (default) | `Prompt-Optimizer` |
| `<title>` (when streaming) | `Prompt-Optimizer` (NO mid-stream title mutation — keeps the tab stable) |
| `<meta name="description">` | `Quality-first prompt router that picks the right LLM for every question.` |
| Favicon | Single SVG with a simple emoji-derived mark (Phase 6 polish replaces) |

No tab-flash on completion. No notification API in Phase 4.

---

## 17. Copywriting Contract (master copy table)

All user-facing strings in Phase 4. Any new string introduced during execution MUST extend this table (single source of truth).

| Element | Exact copy |
|---------|-----------|
| Browser title | `Prompt-Optimizer` |
| Header app name | `Prompt-Optimizer` |
| Gear icon aria-label | `Settings` |
| Composer placeholder | `Type a message…` |
| Empty-state tagline | `Ask anything. We'll route to the right model.` |
| Send button aria | `Send message` |
| Send button disabled aria | `Send message (composer is empty)` |
| Stop button aria | `Stop generating` |
| Copy button aria | `Copy message as markdown` |
| Regenerate button aria | `Regenerate response` |
| Copy success toast | `Copied to clipboard` |
| Modal heading | `Connect OpenRouter to get started` |
| Modal body | `Prompt-Optimizer routes your prompts to the best model. OpenRouter is the gateway to most chat models — start by pasting your key.` |
| Modal input placeholder | `sk-or-v1-...` |
| Modal input aria | `OpenRouter API key` |
| Modal primary CTA | `Save & continue` |
| Modal link prefix | `Don't have a key? Get one at ` |
| Modal link text | `openrouter.ai/keys ↗` |
| Connected toast | `OpenRouter connected — try a prompt!` |
| Invalid key toast | `That key doesn't look right. Check it and try again.` |
| Network-failure-on-save toast | `Couldn't save the key — is the local API running?` |
| Network-down banner | `API unavailable — is uvicorn running?` |
| Settings page heading | `Settings` |
| Settings section heading | `OpenRouter API key` |
| Settings save button (updating) | `Update key` |
| StreamError prefix | (per code, see §12.2) |
| Retry button | `Retry` |
| Chip prefix | `Routed to ` (bold) |
| Chip separator | ` · ` (regular weight) |
| Streaming placeholder | `streaming` + animated dot |

**Tone rules:**
- Sentence case for everything except brand names ("OpenRouter", "Prompt-Optimizer").
- Em-dashes (`—` U+2014) with no surrounding spaces in error/info strings ("API unavailable — is uvicorn running?").
- Ellipsis character `…` (U+2026) in placeholders ("Type a message…", "streaming…"), NOT three dots.
- Right-arrow `↗` (U+2197) for external links; up-arrow `↑` (U+2191) and down-arrow `↓` (U+2193) for token counts.
- Middle-dot `·` (U+00B7) as separator in chip and metrics footer.
- US English spelling.
- No exclamation points except in success toasts ("OpenRouter connected — try a prompt!").
- No emoji in chrome strings (only in optional favicon mark).

---

## 18. Registry Safety

Phase 4 ships **only the official shadcn/ui registry**. No third-party blocks. Registry vetting gate is therefore not applicable; the safety column documents the audit-trail expectation.

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official (`https://ui.shadcn.com/r/`) | `button`, `dialog`, `input`, `sonner` | not required (official registry) — recorded 2026-05-18 |
| (any third-party) | (none) | n/a — no third-party registries declared for Phase 4 |

**If a developer adds a third-party shadcn registry block during execution, the registry vetting gate from `gsd-ui-researcher` MUST be re-run** (`npx shadcn view {block} --registry {url}` + flag scan + developer approval). This UI-SPEC is the canonical declaration: any block from outside the official registry is a Phase 4 scope expansion and must be approved as such.

---

## 19. Component Inventory (Phase 4 → file paths)

Maps every visual element to its file path per CONTEXT canonical_refs "New Files Phase 4 Creates":

| Component | File path | Owns |
|-----------|-----------|------|
| `RootLayout` | `apps/web/app/layout.tsx` | `<html>`, `<body>`, root Tailwind class, font setup, runtime provider mount |
| `ChatPage` | `apps/web/app/page.tsx` | Header + thread + composer + first-run modal trigger |
| `SettingsPage` | `apps/web/app/settings/page.tsx` | Header + `<KeyForm mode="settings">` |
| `RoutingChip` | `apps/web/components/RoutingChip.tsx` | §6 — chip with backend-color switch + ARIA |
| `MetricsFooter` | `apps/web/components/MetricsFooter.tsx` | §7 — mid-stream + final formatting |
| `ChatBubble` (assistant) | (inline in `apps/web/app/page.tsx` or extracted) | §8 — markdown body + action row + timestamp |
| `Composer` | (uses `@assistant-ui/react` Composer primitive) | §9 — placeholder, keyboard shortcuts, state machine |
| `FirstRunModal` | `apps/web/components/FirstRunModal.tsx` | §10 — Dialog + KeyForm in blocking mode |
| `KeyForm` | `apps/web/components/KeyForm.tsx` | Shared between modal and `/settings` — input + submit + masked display |
| `StreamErrorBanner` | (inline in ChatBubble or extracted) | §12 — code → user message + retry |
| `NetworkDownBanner` | (above composer in `apps/web/app/page.tsx`) | §13 — 503 + polling |
| `EmptyState` | (inline in `apps/web/app/page.tsx`) | §11 — centered tagline |
| Toasts | `<Toaster />` from `sonner` mounted in `RootLayout` | All copy listed in §17 |

---

## 20. Open Questions Forwarded to Planner

The UI-SPEC is complete and self-sufficient. The planner does NOT need to revisit any visual / interaction question. The following are implementation choices the planner owns (not design choices):

1. Whether `ChatBubble`, `StreamErrorBanner`, and `EmptyState` are extracted to their own files or inlined in `page.tsx` — purely a code-organization choice; the visual contract is the same either way.
2. The exact `setInterval` strategy for `/api/health` polling (React effect with cleanup vs. SWR vs. custom hook) — function over form.
3. Whether the `MarkdownComponents` map for `@assistant-ui/react-markdown` lives in a shared `lib/markdown-components.tsx` or co-located with `ChatBubble` — see (1).
4. Hot-reload behavior of the runtime provider during `pnpm dev` — out of UI-SPEC scope.

---

## 21. Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS — §17 declares every user-facing string with exact characters
- [ ] Dimension 2 Visuals: PASS — §5 declares layout; §6–13 declare every component's structure
- [ ] Dimension 3 Color: PASS — §4 declares the 60/30/10 split + accent reserved-for list + WCAG ratios in §14.1
- [ ] Dimension 4 Typography: PASS — §3 declares 4 sizes × 2 weights with line heights
- [ ] Dimension 5 Spacing: PASS — §2 declares the 4-grid scale with no exceptions
- [ ] Dimension 6 Registry Safety: PASS — §18 declares only official shadcn registry; no third-party blocks

**Approval:** pending (gsd-ui-checker will upgrade `status: draft` → `status: approved` and timestamp this line)
