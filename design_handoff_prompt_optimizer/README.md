# Handoff: Prompt Optimizer — Chat Web App

## Overview

**Prompt Optimizer** is a chat web app for an AI product that automatically routes each prompt to the model best suited for the job (Claude, GPT-4o, Gemini, Llama, DeepSeek, Mistral via OpenRouter). The routing decision is **invisible by default** — the user just sees a great answer with a small "optimized" pill they can hover for routing details.

This bundle contains the **default Plasma theme** prototype plus 4 alternate themes (Citrus, Tide, Bauhaus, Carbon) so you can pick or expose whichever direction the team commits to.

## About the Design Files

The files in `source/` are **design references created in HTML+React+Babel** — running prototypes showing intended look and behavior, not production code to ship.

Your task is to **recreate these designs in the target codebase's existing environment** (React, Next.js, Vue, SwiftUI, etc.) using its established patterns and libraries. If no environment exists yet, choose the most appropriate framework. The HTML/JSX in `source/` is a **fidelity reference**, not a starting point — read it for exact tokens, layout math, and copy, then re-implement cleanly.

## Fidelity

**High-fidelity (hifi)** — colors, typography, spacing, radii, shadows, and interactions are all final. Recreate pixel-perfectly. Every value in the *Design Tokens* section is exact.

---

## Information Architecture

Single full-bleed page, two columns:

```
┌──────────────┬──────────────────────────────────────────┐
│              │ Top bar (chat title · meta · actions)    │
│   Sidebar    ├──────────────────────────────────────────┤
│   (256px)    │                                          │
│              │   Conversation pane (centered 760px)     │
│  brand       │                                          │
│  new chat    │   ┌──────────────────────────────────┐   │
│  history     │   │ Empty state OR thread of msgs   │   │
│  ─────       │   └──────────────────────────────────┘   │
│  user        │                                          │
│  + settings  │            Composer (centered)           │
└──────────────┴──────────────────────────────────────────┘
```

Three primary views (toggled in dev via Tweaks panel; in production, driven by chat state):
1. **Empty state** — new chat, no messages yet → animated router-fan diagram + suggested prompts
2. **Thread** — active conversation with alternating user/assistant messages
3. **Compare** — assistant response shown side-by-side from 2 candidate models (manual override)

A **Routing Preferences modal** is reachable from sidebar footer or top-bar "Routing" button.

---

## Design Tokens

Tokens are exposed as CSS custom properties on `:root`. The default theme is **Plasma**; alternates override the vars under a body class (`.theme-citrus`, `.theme-tide`, `.theme-bauhaus`, `.theme-carbon`).

### Plasma — default

| Token              | Value                                    | Use                                  |
| ------------------ | ---------------------------------------- | ------------------------------------ |
| `--bg`             | `#f8f6f1`                                | App background (warm off-white)      |
| `--surface`        | `#ffffff`                                | Cards, sidebar, composer, modals     |
| `--surface-2`      | `#efece4`                                | Hover bg, attachments, code chips    |
| `--line`           | `#e6e1d4`                                | Dividers, hairline borders           |
| `--line-strong`    | `#c8c2b1`                                | Emphasis borders, scrollbar thumb    |
| `--ink`            | `#14121f`                                | Primary text (deep purple-black)     |
| `--ink-2`          | `#3f3c4f`                                | Secondary text                       |
| `--ink-3`          | `#6c697b`                                | Tertiary / meta text                 |
| `--ink-4`          | `#98959f`                                | Placeholders, faint labels           |
| `--accent`         | `#6d4aff`                                | Primary CTA (electric violet)        |
| `--accent-hover`   | `#5933ee`                                |                                      |
| `--accent-soft`    | `rgba(109, 74, 255, 0.10)`               | Soft accent backgrounds              |
| `--accent-2`       | `#ff3d8b`                                | Hot magenta (gradient mid-stop)      |
| `--accent-3`       | `#00e8c0`                                | Mint-cyan (gradient end-stop)        |
| `--good`           | `#00b884`                                |                                      |
| `--warn`           | `#ff3d8b`                                |                                      |
| `--radius`         | `9px`                                    | Buttons, inputs                      |
| `--radius-sm`      | `6px`                                    | Small chips, kbd, tight controls     |
| `--radius-lg`      | `14px`                                   | Cards, composer, modal               |

### Shadows

```css
--shadow-sm:    0 1px 1px rgba(20,18,31,0.04), 0 0 0 1px rgba(20,18,31,0.05);
--shadow-md:    0 2px 6px rgba(20,18,31,0.06), 0 0 0 1px rgba(20,18,31,0.06);
--shadow-lg:    0 16px 48px -10px rgba(20,18,31,0.18), 0 0 0 1px rgba(20,18,31,0.06);
--shadow-focus: 0 0 0 4px var(--accent-soft);
```

### Typography

| Family               | Source                                | Used for                                          |
| -------------------- | ------------------------------------- | ------------------------------------------------- |
| **Instrument Sans**  | Google Fonts, weights 400/500/600/700 | Display: brand wordmark, headings, titles         |
| **Inter Tight**      | Google Fonts, weights 400/500/600/700 | Body, UI labels, buttons, message text            |
| **JetBrains Mono**   | Google Fonts, weights 400/500/600     | Meta labels, timestamps, kbd, the "optimized" pill |

```css
--display: 'Instrument Sans', 'Inter Tight', ui-sans-serif, system-ui, sans-serif;
/* body inherits 'Inter Tight' */
--mono:    'JetBrains Mono', ui-monospace, monospace;
```

Global body settings:
- `font-size: 14px`
- `line-height: 1.5`
- `letter-spacing: -0.005em`
- `-webkit-font-smoothing: antialiased`

Type scale (all are exact values, do not round):

| Role               | Family            | Size  | Weight | Line  | Tracking  | Notes                       |
| ------------------ | ----------------- | ----- | ------ | ----- | --------- | --------------------------- |
| Hero (`empty h1`)  | Instrument Sans   | 48px  | 600    | 1.04  | -0.035em  | Use 42px @ compact, 56px @ comfy |
| Topbar title       | Instrument Sans   | 15px  | 600    | 1     | -0.015em  |                             |
| Settings title     | Instrument Sans   | 17px  | 600    | 1     | -0.02em   |                             |
| Brand name         | Instrument Sans   | 14px  | 600    | 1.1   | -0.025em  | lowercase, "prompt optimizer" |
| Body / msg user    | Inter Tight       | 14px  | 400    | 1.55  | -0.005em  |                             |
| Body / msg assistant | Inter Tight     | 14.5px| 400    | 1.6   | -0.005em  |                             |
| Empty lede         | Inter Tight       | 15px  | 400    | 1.55  | -0.005em  | `max-width: 560px`          |
| Buttons (`.btn`)   | Inter Tight       | 12.5px| 500    | 1     | -0.005em  |                             |
| History item       | Inter Tight       | 13px  | 450    | 1.5   | -0.005em  | 500 when `.active`          |
| Composer text      | Inter Tight       | 14.5px| 400    | 1.5   | -0.005em  |                             |
| Suggestion text    | Inter Tight       | 13px  | 400    | 1.5   |           |                             |
| Suggestion kind    | JetBrains Mono    | 10px  | 600    | 1     | 0.1em     | uppercase, accent color     |
| `msg-role`         | JetBrains Mono    | 10.5px| 600    | 1     | 0.08em    | uppercase, --ink-3          |
| `msg-when`         | JetBrains Mono    | 10.5px| 400    | 1     |           | --ink-4                     |
| `optimized-pill`   | JetBrains Mono    | 9.5px | 600    | 1.4   | 0.06em    | uppercase, accent on accent-soft |
| `msg-foot-stat`    | JetBrains Mono    | 11px  | 500    | 1     | 0.02em    | --ink-3 (value strong is --ink 600) |
| `history-label`    | JetBrains Mono    | 10px  | 600    | 1     | 0.08em    | uppercase, --ink-4          |
| `brand-sub`        | JetBrains Mono    | 9.5px | 500    | 1     | 0.08em    | uppercase, --ink-4          |
| `compare-toggle`   | JetBrains Mono    | 10.5px| 600    | 1     | 0.06em    | uppercase                   |
| `composer-hint`    | JetBrains Mono    | 10.5px| 500    | 1     | 0.04em    | --ink-4                     |

### Spacing scale

Component-level spacing is bespoke, not a strict 4px/8px grid. Key values used repeatedly:

- App grid: sidebar `256px` + main `1fr`
- Pane content width: `min(760px, 100%)`, centered, horizontal padding `28px`
- Pane vertical padding: top `28px`, bottom `160px` (extra to clear composer)
- Empty state width: `min(860px, 100%)`
- Empty state vertical padding: `24px 28px 180px`
- Sidebar internal padding: `16px 10px 12px`, gap between sections `12px`
- Top bar: `12px 24px`
- Composer: `12px 12px 8px` padding, `min(760px, 100%)` width, `22px` bottom inset
- Message bottom margin: `28px`

### Border radii summary

- 4–6px: kbd, small chips, scrollbar thumbs
- 7–9px: buttons, inputs, sidebar nav items, composer send button
- 12–14px: user message bubble, composer, modal, router stage, suggestion cards
- 999px: pills (`optimized`, `compare-toggle`, `eyebrow`, `toggle`)

### Alternate themes

Each theme overrides `--bg`, `--surface*`, `--line*`, `--ink*`, `--accent*`. Carbon also overrides shadow vars.

| Theme    | bg         | ink        | accent     | accent-2   | accent-3   | Notes |
| -------- | ---------- | ---------- | ---------- | ---------- | ---------- | ----- |
| Plasma   | #f8f6f1    | #14121f    | #6d4aff    | #ff3d8b    | #00e8c0    | default |
| Citrus   | #f3ecdc    | #1f1c10    | #d95226    | #ddc31a    | #d95226    | warm bone + terracotta + lemon |
| Tide     | #ecf6f4    | #062528    | #ff6b54    | #2dc4b6    | #ffb648    | coral on mint |
| Bauhaus  | #f3ecdf    | #0e1b3d    | #e63946    | #f4b942    | #2563eb    | ivory + 3 primaries. Overrides `--radius: 6px`, `--radius-sm: 4px`, `--radius-lg: 10px` for a sharper graphic feel |
| Carbon   | #0b0d14    | #f0eee8    | #a78bfa    | #5dd3ff    | #ff7da7    | dark mode; also adds radial gradient mesh via `--bg-gradient` and inverts shadows |

See `source/styles.css` "THEMES" section for the complete override blocks.

### Carbon mesh gradient

```css
--bg-gradient:
  radial-gradient(60% 50% at 12% 8%,  rgba(167, 139, 250, 0.18) 0%, transparent 55%),
  radial-gradient(50% 40% at 90% 12%, rgba(255, 125, 167, 0.10) 0%, transparent 60%),
  radial-gradient(60% 50% at 78% 96%, rgba(93, 211, 255, 0.10) 0%, transparent 55%);
```
Applied via a `.app::before` overlay (`position: fixed; inset: 0; z-index: 0; pointer-events: none`). All app children sit at `z-index: 1`.

---

## Brand Logo

Custom **router-fan glyph** — input dot + 3 routes fanning to 3 output dots, middle route bolder = the "chosen" path. Stored gradient-filled.

- Container: `32×32px`, `border-radius: 9px`, `background: var(--surface)`, `border: 1px solid var(--line)`, `box-shadow: var(--shadow-sm)`
- SVG inside: `24×24px`, viewBox `0 0 32 32`

```svg
<svg viewBox="0 0 32 32" fill="none">
  <defs>
    <linearGradient id="po-mark-grad" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
      <stop offset="0%"   stop-color="var(--accent)"  />
      <stop offset="55%"  stop-color="var(--accent-2)" />
      <stop offset="100%" stop-color="var(--accent-3)" />
    </linearGradient>
  </defs>
  <!-- input -->
  <circle cx="5.5" cy="16" r="2.6" fill="url(#po-mark-grad)" />
  <!-- routes (middle is the chosen / bolder one) -->
  <path d="M7.5 14.5 L20.5 6.5"  stroke="url(#po-mark-grad)" stroke-width="1.5" stroke-linecap="round" opacity="0.55" />
  <path d="M7.5 16   L24   16"   stroke="url(#po-mark-grad)" stroke-width="2.6" stroke-linecap="round" />
  <path d="M7.5 17.5 L20.5 25.5" stroke="url(#po-mark-grad)" stroke-width="1.5" stroke-linecap="round" opacity="0.55" />
  <!-- output dots -->
  <circle cx="22" cy="5.5"  r="2"   fill="url(#po-mark-grad)" opacity="0.5" />
  <circle cx="26" cy="16"   r="3.2" fill="url(#po-mark-grad)" />
  <circle cx="22" cy="26.5" r="2"   fill="url(#po-mark-grad)" opacity="0.5" />
</svg>
```

Wordmark: `"prompt optimizer"` lowercase, Instrument Sans 14px / 600 / -0.025em tracking, color `--ink`.
Sub-label: `"auto-routing · v1.4"` JetBrains Mono 9.5px uppercase, `--ink-4`, `letter-spacing: 0.08em`, `margin-top: 4px`.

---

## Screens / Views

### 1. Sidebar (256px, always present)

Vertical flex, full height, `background: var(--surface)`, `border-right: 1px solid var(--line)`, padding `16px 10px 12px`, gap `12px`.

**Sections, top to bottom:**

1. **Brand lockup** (`.brand`) — mark + wordmark + sub. Padding `4px 6px 6px`. Gap `10px`.

2. **New Chat button** (`.new-chat`) — solid accent CTA. Full-width.
   - Background `var(--accent)`, color `#fff`
   - Padding `8px 12px`, radius `var(--radius)`, font-size `13px`, weight `500`
   - Box-shadow: `0 1px 2px rgba(10,37,64,0.08), 0 0 0 1px color-mix(in srgb, var(--accent) 60%, transparent) inset`
   - Icon (plus, 16px), label "New chat", trailing kbd `⌘ N` (white-on-white-alpha, 10px JetBrains Mono)
   - Hover: bg `var(--accent-hover)`. Active: `translateY(0.5px)`

3. **History list** (`.history`) — `flex: 1`, scrollable. Groups: "Today", "Yesterday", "Last 7 days".
   - **Group label** (`.history-label`) — JetBrains Mono 10px/600 uppercase, padding `0 10px 8px`
   - **Item** (`.history-item`) — flex row, padding `6px 10px`, radius `6px`, font-size `13px`. Title (truncate) + when (mono, 10.5px). Hover: bg `--surface-2`. Active: bg `--accent-soft`, weight 500, and a `2px × 14px` accent bar absolutely positioned at the left edge.

4. **Footer** (`.sidebar-footer`) — top border, `padding: 10px 6px 0`, gap `10px`.
   - **Avatar** — 28px circle, conic-ish linear gradient from `--accent` to mix-with-warn, white initials "MA"
   - **Name** "Maya Asante" (13px/500) + **plan** "PRO · 24k credits" (mono 10px/500 uppercase, --ink-4)
   - **Settings icon-btn** (28×28, gear icon, hover: bg --surface-2)

**Sample history data** (`source/data.js`):
- Today: "Onboarding email rewrite" (2m), "SQL: window functions for cohort retention" (1h), "Translate landing page · ja-JP" (3h)
- Yesterday: "Refactor auth middleware (Express → Hono)", "Pricing page tier comparison", "Image prompts for hero illustration"
- Last 7 days: "Debugging a Python traceback" (3d), "Investor update — Q2 narrative" (4d), "Customer interview synthesis" (6d)

### 2. Top Bar

Horizontal flex, `padding: 12px 24px`, `background: var(--surface)`, `border-bottom: 1px solid var(--line)`, gap `8px`.

Order: `title` (flex:1, ellipsis) → `meta` (mono 10px, `flex-shrink:0`, "4 MESSAGES · AUTO-ROUTED") → ghost btn **Share** (Icon `share`) → ghost btn **Export** (Icon `doc`) → solid btn **Routing** (Icon `settings`).

When the empty state is showing, title reads "New chat" and the meta + first two ghost buttons are hidden.

### 3. Empty State

Centered column inside the pane, `min(860px, 100%)`, vertical padding `24px 28px 180px`, content vertically centered (`justify-content: center`).

1. **Eyebrow pill** (`.empty-eyebrow`) — self-start, padding `5px 10px 5px 8px`, radius 999, `background: var(--accent-soft)`, color `var(--accent)`. Leading `6×6px` accent dot with `0 0 0 3px` soft halo. Copy: `"Auto-routed · 6 models · 0 config"` (mono 10.5px/500 uppercase, 0.12em tracking).

2. **Hero headline** (`<h1>`) — Instrument Sans 48px / 600, line 1.04, tracking -0.035em, `text-wrap: balance`, color `--ink`. Copy split across two lines:
   ```
   Ask anything.
   We'll pick the [right model] for the job.
   ```
   "right model" is wrapped in `<em>` and gets a gradient text fill:
   ```css
   background: linear-gradient(105deg, var(--accent) 0%, var(--accent-2) 50%, var(--accent-3) 100%);
   -webkit-background-clip: text;
   background-clip: text;
   color: transparent;
   ```
   `<em>` has `font-style: normal` (we override the default italic).

3. **Lede paragraph** (`.empty-lede`) — 15px, `--ink-2`, max-width 560px, `text-wrap: pretty`. Copy:
   > "Every prompt is analyzed and routed to the model that handles it best — Claude for nuance, GPT-4o for vision, DeepSeek for code, Gemini for speed. You just write."

4. **Router diagram** (see *Router Diagram* section below).

5. **Suggestions grid** (`.suggestions`) — `grid-template-columns: repeat(2, 1fr)`, gap `10px`.
   - Card (`.suggestion`): padding `14px 16px`, radius `var(--radius)`, bg `--surface`, 1px `--line` border, `--shadow-sm`. Hover: lift `translateY(-1px)`, `--line-strong` border, `--shadow-md`.
   - Top line: **kind** (mono 10px/600 uppercase, `--accent`). Bottom line: prompt text (13px, `--ink-2`).
   - Four suggestions:
     - **Write** — "Draft a follow-up email to a customer who churned"
     - **Code** — "Refactor this Python function for readability"
     - **Analyze** — "Find the top 3 themes in these support tickets"
     - **Plan** — "Outline a 6-week launch plan for a beta product"

### 4. Router Diagram (animated)

Centerpiece of the empty state. SVG inside a card (radius `--radius-lg`, padding `16px`, `--surface` bg, `--shadow-sm` border).

**Layout** (viewBox `0 0 800 340`, aspect-ratio 16:9, max-height 320px):
- **Prompt indicator** at `(60, 170)` — a 60×28 rounded rect (`--surface-2` bg, 0.75px `--line-strong` border) with 3 stacked short horizontal "text" lines inside, label "PROMPT" beneath.
- **Hub** at `(300, 170)` — `34px` radius circle filled with a `<linearGradient>` from `var(--accent) → var(--accent-2)` (top-left to bottom-right). Centered text "P" in `--display`, weight 700, 22px, white, tracking -0.03em.
  - Surrounding `64px` radius soft halo from a radial gradient using `--accent-soft`.
  - Pulsing ring: a second circle r=34, no fill, accent stroke, `<animate>` r from 34→46→34 over 3s, opacity 0.35→0→0.35.
- **Model nodes**, 6 of them, at `x = 620`, vertically spaced `y = 38 + i/5 * (340-76)`. Each is a 7px circle:
  - Inactive: `fill: var(--surface)`, `stroke: var(--line-strong)`
  - Active: `fill: var(--accent)`, `stroke: var(--accent)`, plus a separate ripple ring r=7→18, opacity 0.5→0, dur 1s repeating.
  - Label to the right, 18px offset, JetBrains Mono 11px/500, `--ink-3` (or `--accent` + weight 600 when active).
- **Edges**: prompt→hub is always-active (accent, 1.5px stroke). Hub→each-node: 1px `--line-strong` when inactive, 1.5px `--accent` when the node is active.
- **Traveling pulse**: a 4px filled accent circle that animates `prompt(60,170) → hub(300,170) → active node` over 1.6s. Use SVG `<animate>` on cx/cy with keyTimes `0;0.45;1`, plus an opacity animation `0→1→1→0`. Re-key on every change (React: `key={`p-${active}`}`) to restart.

**Cycle**: `setInterval`, advance active index every **2100ms**.

**Caption** beneath card, mono 10.5px uppercase, color `--ink-4`. Pattern:
> Optimized for `<strong>{activeNode.tag}</strong>` → routed to `<strong>{activeNode.label}</strong>`

Where `strong` is `color: var(--accent)`, `font-weight: 600`.

**Models** (use exact OpenRouter identifiers; see `source/data.js`):

| id                              | label              | short        | vendor    | tag         |
| ------------------------------- | ------------------ | ------------ | --------- | ----------- |
| `anthropic/claude-sonnet-4.5`   | Claude Sonnet 4.5  | Sonnet 4.5   | Anthropic | reasoning   |
| `openai/gpt-4o`                 | GPT-4o             | GPT-4o       | OpenAI    | multimodal  |
| `google/gemini-2.0-flash`       | Gemini 2.0 Flash   | Gemini 2.0   | Google    | fast        |
| `meta-llama/llama-3.3-70b`      | Llama 3.3 70B      | Llama 3.3    | Meta      | open        |
| `deepseek/deepseek-v3`          | DeepSeek V3        | DeepSeek V3  | DeepSeek  | code        |
| `mistralai/mistral-large`       | Mistral Large      | Mistral L    | Mistral   | balanced    |

### 5. Message Thread

Sequence of `<article>` elements, gap `28px` (margin-bottom).

**Header row** (`.msg-head`, gap `8px`, mb `8px`):
- Role label "YOU" or "PROMPT OPTIMIZER" (mono 10.5px/600, --ink-3, 0.08em tracking, uppercase)
- Timestamp (mono 10.5px, --ink-4)
- *(assistant only)* Optimized pill (see below)

**Optimized pill** (`.optimized-pill`):
- inline-flex, gap 5px, padding `2px 8px 2px 7px`, radius 999
- bg `var(--accent-soft)`, color `var(--accent)`, 1px `var(--line)` border
- 5px accent dot prefix
- text: `"optimized"` (mono 9.5px/600 uppercase, 0.06em tracking)
- `title` attribute = `"Routed to {model.label} — {reason}"` (this is the only place routing is surfaced — on hover/focus)
- `cursor: help`

**User message body** (`.msg-user .msg-body`):
- bg `var(--surface)`, radius `var(--radius-lg)` (14px), padding `12px 14px`, 1px `--line` border, `--shadow-sm`
- 14px Inter Tight, 1.55 line-height, color `--ink`

**Assistant message body** (`.msg-assistant .msg-body`):
- no background, padding `4px 0`
- 14.5px Inter Tight, 1.6 line-height
- Supports inline markdown: `**bold**` → `<strong>` (600 weight), `` `code` `` → `<code>` (mono 0.92em, `--surface-2` bg, padding `1px 5px`, radius 4px). Double-newlines = paragraph breaks. Single newlines = `<br>`.

**Attachment chip** (inside user message, optional):
- inline-flex, padding `6px 10px`, radius `--radius-sm`, 1px `--line` border, bg `--surface-2`
- doc icon (16px, --ink-3), filename, size (mono 11px, --ink-4)
- mt `10px`

**Footer** (`.msg-foot`, assistant only):
- 1px `--line` top border, mt `12px`, pt `10px`
- flex row, gap `14px`, flex-wrap
- Mono 11px/500, color `--ink-3`. Each stat shows `<strong>{value}</strong> · {label}`, with `strong` in `--ink` 600.
- Stats: `{latency}s · latency`, `${cost} · cost`, `{model.short}`
- Right-aligned action group: copy, refresh, compare (icon-only), thumb (each 26×26 icon-btn)

**Sample thread** (`source/data.js → THREAD`): 4 messages alternating user/assistant, about rewriting an onboarding email. Includes one attachment (`onboarding-v3.md, 2.1 KB`). Both assistant responses routed to Claude Sonnet 4.5 with `routedReason` "long-form writing · tone" and "iterative edit · same context".

### 6. Composer (sticky bottom)

Absolutely positioned at the bottom of the main pane, `left/right: 0; bottom: 0`, padding `16px 28px 22px`. Background is a top-transparent → `var(--bg)` linear gradient so messages fade behind it.

Inner card (`.composer`):
- `min(760px, 100%)`, centered, radius `--radius-lg`, `--surface` bg, 1px `--line` border, `--shadow-lg`
- Padding `12px 12px 8px`
- `:focus-within` → border `--accent`, box-shadow `--shadow-lg, --shadow-focus`

**Textarea**: auto-grow, min-height 22px, max-height 200px, no border, transparent bg, 14.5px / 1.5. Placeholder: `"Ask anything — we'll route it to the best model."`

**Action row** (`.composer-row`, gap 4px, pt 4px):
1. Icon buttons (30×30, radius 6px, --ink-3, hover bg --surface-2):
   - paperclip (Attach file)
   - image (Add image)
   - mic (Voice)
   - globe (Web search)
2. **Compare toggle** — pill button. Radius 999, padding `5px 10px 5px 9px`, mono 10.5px/600 uppercase 0.06em. Off state: `--ink-3` text, `--line` border, `--surface` bg. On state: `--accent` text, `--accent` border, `--accent-soft` bg. Leading 6px dot (ink-4 off, accent on).
3. **Send button** (`.composer-send`) — `margin-left: auto`. 30×30, radius 7px, bg `--accent`, color white, arrow-up icon. Disabled (empty draft): bg `--surface-2`, color `--ink-4`, no shadow.

**Hint row** (`.composer-hint`, below card):
- Centered flex, gap 6px, mt 10px
- Mono 10.5px/500, color `--ink-4`, 0.04em tracking
- Three kbd chips: `↵ send · ⇧ ↵ newline · ⌘ K commands`
- kbd: 2px 5px padding, radius 3px, --surface bg, 1px --line border, --ink-3

### 7. Routing Preferences Modal

Triggered by sidebar settings icon OR top-bar "Routing" button.

- Scrim: `position: fixed; inset: 0; background: rgba(10,37,64,0.4); backdrop-filter: blur(3px); z-index: 60`
- Card: `min(540px, 100%)`, `--surface` bg, radius `--radius-lg`, custom shadow `0 24px 60px -16px rgba(10,37,64,0.3), 0 0 0 1px rgba(10,37,64,0.05)`
- Click scrim to close. Click card stops propagation.

**Header** — padding `16px 20px 14px`, 1px `--line` bottom border. Title "Routing preferences" (Instrument Sans 17px/600/-0.02em). Close icon-btn on the right.

**Body** — padding `14px 20px 20px`, max-height `64vh`, scrollable, gap `18px`.

Three sections:

1. **Optimize for** — section heading mono 10.5px/600 uppercase, --ink-4
   - Row: "**Priority**" / "Bias routing toward what matters most to you on each request." → segmented control `Quality / Balanced / Speed / Cost` (mono 10.5px/600 uppercase, --surface-2 track, --surface active thumb with --shadow-sm, --accent active text)
   - Row: "**Show routing badge**" / "Display which model answered after each response." → custom toggle (32×18, --line-strong off / --accent on, white knob 14×14 with shadow)
   - Row: "**Cost-aware fallback**" / "Use a cheaper model when the prompt is simple enough." → toggle

2. **Allowed models · N of N** — list of 6 model rows (`.model-pref`):
   - Row: 8px accent square dot · model.label (13px/500) · model.vendor (mono 10px uppercase, --ink-4) · toggle (on by default)

3. **Privacy**
   - Row: "**Zero data retention**" / "Route only to providers that don't retain prompt data." → toggle (off by default)

### 8. Compare View

Shown when the user has run the same prompt across 2 candidate models. Renders below the thread as a single assistant message with a 2-column grid (`.compare-stage`, `grid-template-columns: 1fr 1fr`, gap 12px).

Each card (`.compare-card`):
- 1px `--line` border, radius `--radius`, padding `14px 16px`, `--surface` bg, `--shadow-sm`
- Head: 6px colored dot + "Model · 1.84s · $0.0042" (mono 11px/600 uppercase, --ink-3, mb 10px)
- Body text: 13px, --ink-2, 1.5 line-height

Sample copy (see `source/messages.jsx → CompareView`):
- Card A: Claude Sonnet 4.5 · 1.84s · $0.0042 — "Tight, warm, and three steps…"
- Card B: GPT-4o · 1.12s · $0.0029 — "Shorter still — 40 words…"

---

## Iconography

All icons are 20×20 viewBox, 1.4–1.5px stroke, `currentColor`, custom-drawn — no icon library. See `source/icons.jsx` for paths.

Set used: `plus, paperclip, send, image, mic, globe, copy, refresh, thumb, share, settings, compare, sparkle, doc, x, search, arrowUp, more`.

Default render size 16px. In your codebase, lift these into an `<Icon name="..." size={n} />` component or equivalent.

---

## Interactions & Behavior

### Navigation / state

- **Sidebar history click** → `setActiveId`, switches to thread view.
- **New chat button (or empty topbar state)** → resets to empty state; clears draft.
- **Sidebar settings icon / topbar Routing btn** → opens Routing Modal.
- **Suggestion card click** → fills the composer with that prompt text and switches to thread view (so the user can refine before sending).

### Composer

- **Enter** → send (only if draft.trim() is non-empty).
- **Shift+Enter** → newline.
- **Auto-grow**: on every value change, reset textarea height to `auto`, then set to `min(scrollHeight, 200px)`.
- **Send disabled** while draft is empty.
- **Compare toggle** → switches whether the next send runs through 2 models (visual indicator only in this prototype; in production, kicks off two parallel completions and renders the Compare View).

### Router diagram

- `setInterval(2100ms)` advances the active model index. `setActive(a => (a+1) % models.length)`.
- The pulse animation restarts on every active change (re-key the SVG element).
- The active node, its edge, its label, and the caption all reflect the same index.

### Hover states

- All `.btn`: bg `--surface-2`, shadow upgrades to `--shadow-md`.
- `.btn.primary`: bg `--accent-hover`.
- `.icon-btn`: bg `--surface-2`, color `--ink`.
- `.suggestion`: `translateY(-1px)`, border `--line-strong`, `--shadow-md`.
- `.history-item`: bg `--surface-2`, color `--ink`. If active, bg `--accent-soft` with the 2px accent bar.

### Focus

- All form controls (textarea, inputs) within `.composer` use the `:focus-within` ring (`--shadow-focus`).
- Buttons rely on the system focus ring (do not suppress).

### Transitions

- Buttons: `background .12s ease, color .12s ease, box-shadow .12s ease`
- New chat active press: `transform .06s ease`
- Composer border/shadow on focus: `.12s ease`
- Toggle knob: `transform .15s ease`
- Suggestion lift: `transform .12s ease`
- Pulse animations on the router diagram: SVG SMIL (declarative).

### Density variants (optional)

The Tweaks panel exposes `compact / regular / comfy`. In production this can become a user setting:
- `.density-compact` — body 13.5px, hero 42px, pane top-padding 20px
- regular — defaults
- `.density-comfy` — pane top-padding 36px, bottom 180px, hero 56px

---

## State Management

Minimal local state for this prototype:

```ts
const [activeId, setActiveId] = useState('c1');     // selected conversation
const [draft, setDraft] = useState('');             // composer text
const [compare, setCompare] = useState(false);      // compare toggle
const [settingsOpen, setSettingsOpen] = useState(false);
const [prefs, setPrefs] = useState({                // routing preferences
  priority: 'Balanced',  // 'Quality' | 'Balanced' | 'Speed' | 'Cost'
  showBadge: true,
  costAware: true,
  zdr: false,
});
const [view, setView] = useState('empty');          // 'empty' | 'thread' | 'compare'
```

For real production:
- Replace `THREAD` constant with messages from your backend / streaming source.
- `routedTo` and `routedReason` per assistant message come from the router service.
- `latencyMs` and `cost` come from the provider response.
- `HISTORY` becomes a paginated query.

---

## Accessibility

- Every icon-only button has a `title` and an `aria-label` (the `title` is double-duty as the optimized-pill explanation).
- Toggles use `aria-pressed`.
- Settings modal traps focus and closes on Escape (TODO in prototype — wire up in production).
- Hero gradient text uses semantic `<em>` (do not render the gradient on screenshots / OG images — use solid `--accent` instead).
- Color contrast: all `--ink*` / `--accent` pairs meet WCAG AA against their backgrounds; verify in Carbon dark mode after any changes.

---

## Assets

- No raster images. Logo is the inline SVG documented above.
- Fonts: Google Fonts (Instrument Sans, Inter Tight, JetBrains Mono). Self-host for production or use Next.js' built-in `next/font/google`.
- No third-party icon library — icons are bespoke SVGs in `source/icons.jsx`.

---

## Files in this bundle

```
design_handoff_prompt_optimizer/
  README.md                 ← this file
  source/
    Prompt Optimizer.html   ← entry, links fonts + stylesheet + scripts
    styles.css              ← all visual tokens & components
    data.js                 ← MODELS, HISTORY, SUGGESTIONS, THREAD
    icons.jsx               ← Icon component + path data
    router-diagram.jsx      ← animated SVG diagram
    sidebar.jsx             ← Sidebar component
    messages.jsx            ← Message, EmptyState, Composer, CompareView
    settings.jsx            ← Routing preferences modal
    app.jsx                 ← root component + theme application
    tweaks-panel.jsx        ← prototype-only theme switcher (DO NOT SHIP)
```

> **Don't ship `tweaks-panel.jsx`** — it's a prototype-only dev tool for cycling through themes. In production, theme is either a user setting or fixed.

---

## Implementation checklist (suggested order)

1. Wire up fonts and the CSS-variable token system. Mirror the Plasma palette as defaults; gate alternate themes behind a body class.
2. Build the static shell: app grid, sidebar, top bar, composer (no functionality yet).
3. Implement the empty state — including the router-fan logo and the animated router diagram. Confirm the gradient hero text renders correctly with `background-clip: text` (test Safari).
4. Implement the message thread + the inline markdown parser (or swap to your existing markdown component, but match the styling).
5. Implement the composer auto-grow + Enter-to-send + compare toggle.
6. Implement the Routing Preferences modal.
7. Implement the Compare View.
8. Hook up real data sources, streaming, and routing.
9. Pass through with the screenshots provided (or the HTML prototype open side-by-side) and verify spacing, weights, and colors.

If anything below pixel-precision is ambiguous, **open `source/Prompt Optimizer.html` in a browser and inspect the live element** — the prototype is the source of truth for any spacing the spec doesn't enumerate.
