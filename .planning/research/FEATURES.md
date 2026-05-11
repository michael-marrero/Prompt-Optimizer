# Feature Research

**Domain:** Auto-routing multi-backend AI chat product (Perplexity-Comet-style "no model picker" UX; OpenRouter + Claude Code SDK + Anthropic computer-use; open-source, BYOK, local-first)
**Researched:** 2026-05-11
**Confidence:** MEDIUM-HIGH (HIGH on table-stakes patterns and per-backend display via observed competitor implementations; MEDIUM on routing-specific UX which is still an emerging design space in 2026)

---

## Executive Framing

This product lives or dies on a single user moment: **the user types a prompt, the right backend handles it, and the user trusts that the routing was correct without having to verify.** Every feature below is graded against that loop.

Three things separate the strong auto-routing products from the weak ones:

1. **Visible routing rationale that survives skepticism.** ChatGPT's auto-router (2025-2026) is widely criticized for hiding which model actually answered ([TechCrunch](https://techcrunch.com/2025/08/12/chatgpts-model-picker-is-back-and-its-complicated/), [TechRadar](https://www.techradar.com/ai-platforms-assistants/chatgpt/chatgpt-might-not-be-using-the-model-you-think-and-its-also-hiding-others-in-settings)). Comet and Cursor are praised for being explicit. Our `rationale` field from `PROJECT.md` Active scope is the right call — it must be **always visible, never hidden behind a hover**.
2. **Per-backend response surfaces.** A chat model's reply is a markdown bubble. A Claude Code SDK run is a streaming sequence of tool calls, file diffs, and a final summary. A computer-use run is screenshots + action narration. Stuffing all three into the same `<div>` without thought is the fastest way to make the product feel chaotic ([openclaw#21032](https://github.com/openclaw/openclaw/issues/21032), [Cursor forum](https://forum.cursor.com/t/add-expand-collapse-for-agent-responses-in-chat/158779)).
3. **Multi-turn routing momentum.** Per-turn re-routing without conversation context causes "wrong-model-in-the-middle-of-a-thread" failures — a follow-up "yes do that" gets misclassified as trivial and sent to a cheap model after a deep coding discussion ([vllm-project/semantic-router#1458](https://github.com/vllm-project/semantic-router/issues/1458)). The right default is **soft-sticky with explicit override**.

The features below are categorized by whether absence breaks the product (table stakes), whether presence wins users (differentiators), or whether their presence contradicts the open-source-BYOK positioning (anti-features).

---

## Feature Landscape

### Table Stakes (Users Expect These — Missing = Broken)

These are not negotiable for a v1 that takes itself seriously as a chat product in 2026. Users have been trained by ChatGPT/Claude.ai/Perplexity to expect every one.

#### Chat UX Primitives

| Feature | Why Expected | Complexity | v1 / v2 / Out | Notes |
|---|---|---|---|---|
| **Token-by-token streaming** | Anything that buffers a full response feels broken in 2026 | M | v1 | SSE over FastAPI → Next.js. Must also stream from Claude Code SDK and computer-use, not just OpenRouter. See [Hidden Complexity](#hidden-complexity). |
| **Stop button mid-stream** | Users will hit it within their first 5 minutes; it's the universal "you're heading off a cliff" signal | M | v1 | Needs cancel signal propagated to OpenRouter / Claude Code SDK / computer-use process; partial response must be preserved as a real message. See [LibreChat continue pattern](https://www.librechat.ai/). |
| **Regenerate last response** | Standard since GPT-3.5; users assume it. Should give option to re-route (try a different backend) or re-run same backend | S-M | v1 | Combine with **"re-route" option** as a differentiator (below). |
| **Edit prior user message** (and fork thread) | Standard on Claude.ai; lets users iterate without polluting the thread. Claude calls this "edit + branch" — [Claude Help Center](https://support.claude.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them) | M | v1.x | Schema needs to support branches (`parent_message_id`). If we skip in v1, must at least allow plain edit-and-resend. Defer fork to v1.x. |
| **Copy message as markdown** | Single most-used button in any chat UI. Copy as plaintext is not enough — devs paste into IDEs/PRs | XS | v1 | Per-message hover button. |
| **Code block syntax highlighting** | Non-negotiable for a product that routes coding tasks | S | v1 | Use `shiki` or `react-syntax-highlighter`. Must work **mid-stream** (see [Hidden Complexity](#hidden-complexity)). |
| **Markdown rendering** (headings, lists, tables, inline code, blockquotes) | Every model outputs markdown; raw asterisks would look amateur | S | v1 | Use `react-markdown` + `remark-gfm`. Sanitize with DOMPurify ([Chrome Developers](https://developer.chrome.com/docs/ai/render-llm-responses)). |
| **Multi-turn persistent threads with sidebar** | "Why don't my old chats show up?" is the #1 dropoff in BYOK chat apps | M | v1 | SQLite per `PROJECT.md`. Sidebar list, click to load, current thread highlighted. |
| **Thread auto-rename from first message** | Users will never manually name 50 threads. ChatGPT/Claude/Perplexity all do this | S | v1 | Call cheap model (cheapest in OpenRouter) with first turn → 5-word title. Run async, don't block the response. |
| **Thread rename / delete / export** | Standard; thread list becomes unmanageable without them | S | v1 (rename, delete); v1.x (export) | Export as `.md` is the BYOK-native format. JSON for round-tripping. |
| **Error state inline in the message** | When OpenRouter 429s, users must see "rate limited — retry?" in-place, not a toast that disappears | S | v1 | Inline error + retry button + (in v1.x) automatic fallback. |
| **Auto-scroll with "scroll to bottom" pin** | Auto-scroll while streaming, but stop auto-scrolling if user scrolls up to read | S | v1 | Subtle but every product gets this wrong on first try. |
| **New chat button** | Obvious | XS | v1 | — |
| **Keyboard shortcuts** (`Cmd+Enter` to send, `Cmd+K` for new chat, `Esc` to stop) | Power users assume them | XS | v1 | Document in a `?` overlay. |
| **Loading / "thinking" indicator** before first token | Cold starts are 1–3s on cloud models; silence = "is it broken?" | XS | v1 | A pulsing dot or "Routing to Claude Sonnet…" pre-stream chip. |

#### Routing-Specific Table Stakes

These are the things that distinguish "a chat app that happens to route" from "an auto-routing product." Per the [PROJECT.md Core Value](.planning/PROJECT.md), every prompt routes silently — but routing must be **legible** or users won't trust it.

| Feature | Why Expected | Complexity | v1 / v2 / Out | Notes |
|---|---|---|---|---|
| **"Routed to X" chip on every assistant message** | The core promise of the product. Hiding it is the ChatGPT-auto failure mode | XS | v1 | Pill above or below the message bubble: `[Claude Sonnet 4.5 • coding]`. Visual, not buried in a tooltip. |
| **One-line rationale next to the chip** | Per `PROJECT.md` Active scope: `{backend, model_or_agent, rationale}`. Users need this to build trust | S | v1 | e.g. "Build-and-edit task → Claude Code SDK". Keep it under 80 chars; expandable for the full classifier breakdown. |
| **Override backend for the next turn** | Users must be able to escape a bad route. Without this, mis-routes feel like a cage | M | v1 | Dropdown next to the send button, or "/" command (`/claude-sonnet`, `/code`, `/computer`). Sticky for one turn only by default. |
| **Override is visually distinct from auto-route** | When the user overrides, the next message's chip must say "Manual: Claude Sonnet" not just "Claude Sonnet" — otherwise the user can't tell if their override stuck | XS | v1 | Different color or `🖐` icon. |
| **Backend availability check at startup** | If user has no Anthropic key and a prompt would route to Claude Code, fail loudly with a clear "set ANTHROPIC_API_KEY" message — never silently route around it | S | v1 | Settings page shows green/red per backend; first-run banner. |
| **Streaming applies to all three backends, not just chat models** | If chat models stream but Claude Code dumps a wall of text at the end, the UX feels broken | L | v1 | Claude Code SDK supports `include_partial_messages` for incremental tool-call streaming ([docs](https://code.claude.com/docs/en/agent-sdk/streaming-output)). Computer-use streams via tool-result blocks. |
| **Token / latency display per turn** (subtle) | Devs want to know what each route cost in ms and tokens, even if non-devs ignore it | S | v1 | Small dim text under the chip: `1.2s • 421 tokens`. Cost in v1.x once we have a cost lookup. |

---

### Differentiators (Where We Win)

These are not required to ship, but each one moves the product from "a router demo with a UI" to "the way I want all chat to work." Prioritized by **leverage on the Core Value** (quality-first auto-routing transparency).

#### Routing Transparency Differentiators

| Feature | Value Proposition | Complexity | v1 / v2 / Out | Notes |
|---|---|---|---|---|
| **Expandable "why this route" with classifier breakdown** | Goes beyond the one-line rationale: show task_type_classifier probabilities, agentic-intent probability, and the Stage-2 model choice with its confidence | M | v1.x | Renders as a collapsible card. Devs love this; non-devs hide it. Aligns with `PROJECT.md` repo's evaluation infrastructure. |
| **"Wrong route" feedback button** (per-turn) | Captures structured signal for offline router retraining without violating the "no live retraining" constraint | S | v1 | Thumbs-down with an optional "should have been X" backend selector. Log to local JSONL. Bridges to repo's eval infra. |
| **Re-route with different backend** (in regenerate menu) | Lets users say "give me Claude's take instead" without re-typing. Better than a global model picker because it preserves the routing-first ethos | S | v1 | Regenerate dropdown: "Try again with auto" / "Try with Claude Sonnet" / "Try with GPT-5" / etc. |
| **Side-by-side comparison: routed vs. alternative** | Power feature for devs evaluating the router. "Run this prompt on Claude Sonnet AND DeepSeek, show me both columns" | L | v2 | Inspired by [OpenRouter playground](https://openrouter.ai/chat), [Braintrust](https://www.braintrust.dev/articles/ab-testing-llm-prompts). Defer — heavy UI work, fights the single-input ethos. |
| **A/B test two routing strategies in dev mode** | Researcher-grade feature: run prompt through both `model_router` and `tier_router`, log divergences | M | v2 (dev-mode only) | Repo already has both routers. Useful for the project itself but probably hidden behind a `?dev=1` flag. |
| **Export routing decisions to CSV** | Closes the loop with repo's existing `src/evaluation/` infra: every chat session feeds offline router analysis | S | v1.x | Single button in settings: dump all routing decisions + (optional) feedback to CSV. |
| **Classifier confidence threshold settings** | "If task classifier confidence < 0.6, ask me before routing" — opt-in friction for power users who don't trust the router yet | M | v2 | Settings option. Default off. |

#### Agent-Backend UX Differentiators

| Feature | Value Proposition | Complexity | v1 / v2 / Out | Notes |
|---|---|---|---|---|
| **Live tool-call trace for Claude Code (collapsed by default)** | Without this, agentic backends feel like a black box. With it, users can stop the agent mid-task | M | v1 | See [Per-Backend Response Shape](#per-backend-response-shape). |
| **Inline file-diff rendering for Claude Code** | When the agent edits files, show a real diff (red/green) in the chat bubble, not just text. Cursor does this and it's the single most-praised feature ([Cursor changelog](https://cursor.com/changelog/page/5)) | M | v1.x | Use `react-diff-viewer-continued`. Can defer to v1.x if v1 just renders the diff as a fenced ` ```diff` block. |
| **Computer-use screenshot strip** | Show the screenshot at each action step, like Comet's agentic browsing surface ([Perplexity blog](https://www.perplexity.ai/hub/blog/introducing-comet)) | M | v1 | Thumbnail strip in the chat bubble; click to expand. Without this, computer-use is unwatchable. |
| **Action narration toggle** | "Computer-use is doing 47 things; show me one summary line or all 47" | S | v1 | Default: one line per logical action. Expand: full screenshots + clicks + keystrokes. |
| **Abort agent mid-task** | Bigger version of the stop button: must kill the agent loop, not just the stream | M | v1 | Critical — computer-use can rack up cost / take destructive actions. Without abort, BYOK users won't enable it. |
| **Agent "still working" pulse with elapsed time** | Long agent runs (>30s) feel hung without it | XS | v1 | "Claude Code is working… 0:42" |

#### Chat Quality Differentiators

| Feature | Value Proposition | Complexity | v1 / v2 / Out | Notes |
|---|---|---|---|---|
| **Auto-summarize long threads** | Hits a token limit at ~30 turns. Summarize older turns into a compact memory; preserve last N verbatim ([LangMem](https://langchain-ai.github.io/langmem/guides/summarization/)) | L | v2 | Per `PROJECT.md` Out of Scope: no live retraining, but summarization is a context-management feature, not a training feature. Defer to v2 — most threads won't hit this. Flag in [Hidden Complexity](#hidden-complexity). |
| **Model fallback on error** | OpenRouter 503 → automatically try DeepSeek; user sees "Anthropic timed out, fell back to DeepSeek" inline | M | v1.x | Per [LiteLLM patterns](https://docs.litellm.ai/docs/proxy/reliability). v1: surface error + manual retry. v1.x: auto-fallback within same tier. |
| **Prompt rewriting suggestion** | "Improve prompt" button rewrites a vague prompt into a clearer one before sending ([arxiv 2503.16789](https://arxiv.org/html/2503.16789v1)) | M | v2 | Cool but fights the "just type and it works" ethos. Defer. |
| **Cost-per-turn display** | Devs love it; pairs with quality-first messaging ("this took $0.02 and saved you from picking the wrong model") | S | v1.x | Needs cost lookup table from OpenRouter pricing API. |
| **Conversation context indicator** | Visual showing how full the context window is for the current backend ("75% of Claude Sonnet's 200k window used") | M | v2 | Differentiator for power users; non-power users won't care. Defer. |

---

### Anti-Features (Deliberately Not Built)

Each is justified by `PROJECT.md` Out of Scope, the open-source-BYOK positioning, or the Core Value (quality-first auto-routing).

| Feature | Why Tempting | Why We Won't Build It | Alternative |
|---|---|---|---|
| **User accounts / login wall** | Standard SaaS pattern | Direct conflict with [`PROJECT.md` Out of Scope](.planning/PROJECT.md): "User accounts / auth — open-source BYOK; each user runs their own instance." | Local SQLite per machine; trust the OS user boundary. |
| **Server-side analytics / telemetry phone-home** | Useful to know what users do | Conflicts with BYOK trust model. If keys live locally, behavior should too | Optional local-only event log; CSV export. If we ever add telemetry, it must be opt-in, off-by-default, with full disclosure. |
| **Hosted/cloud version** | Easier user onboarding | [Out of Scope](.planning/PROJECT.md): "Hosted multi-tenant SaaS." | Polished local quickstart. |
| **Sharing / public chat links** | Viral growth feature | Requires a server. Conflicts with local-first BYOK. Plus: sharing a chat that hit a paid agent backend is a cost-attribution mess | Export as `.md` and let users share via their own channels. |
| **Marketplace of personas / bots** (à la Poe) | Engagement / monetization | Conflicts with the single-input "no model picker" ethos. Personas re-introduce the picking problem we're trying to remove | None — the router IS the recommendation engine. |
| **Pre-baked opinionated personas/system prompts** ("Act as a senior engineer…") | Engagement feature | Same problem: re-introduces a choice the user shouldn't have to make. Pollutes the routing decision (system prompts change classifier behavior) | Optional global system-prompt slot in settings, hidden, off by default. No pre-baked roster. |
| **Social features** (likes, comments, follows) | — | Out of scope by every measure | None. |
| **In-app billing / subscriptions** | — | [Out of Scope](.planning/PROJECT.md): "Billing / payments — no hosted version." Costs are paid directly to OpenRouter/Anthropic via the user's key | None. |
| **Live online learning of the router from chat traffic** | Self-improving system, sounds great | Direct conflict with [`PROJECT.md` Out of Scope](.planning/PROJECT.md): "Live retraining loop — no online learning of the routers from chat-UI traffic in v1; all training stays offline against `data_processed/`." | Export feedback to CSV → offline retraining pipeline reuses repo's `src/evaluation/`. |
| **Mobile / native apps** | Bigger TAM | [Out of Scope](.planning/PROJECT.md): "web-first; mobile is post-v1 if ever." | Responsive web; treat as v2+. |
| **Voice input / TTS output** | Comet has it | Scope explosion (transcription model, voice-activity detection, latency budget). Not needed to prove the routing thesis | Defer to v2+ if there is even a clear ask. |
| **Image / file uploads to chat models** | Standard in ChatGPT/Claude.ai | Possibly in scope for v2 (OpenRouter chat models support vision); explicit anti-feature for **v1** because each backend handles attachments differently and we'd need backend-aware attachment routing | Drop attachment UI in v1; revisit in v2 once the text-only routing thesis is validated. |
| **Plugin / MCP marketplace** | Trendy | Each plugin would change routing behavior; the surface is too unconstrained to ship in v1 | Claude Code SDK already brings tool-use; that's enough for v1. |
| **Server-stored API keys** (cloud key vault) | "Convenience" | Direct conflict with [`PROJECT.md` Constraints](.planning/PROJECT.md): "Keys never leave the user's local instance." | `.env` file + in-app settings panel that writes to local config only. |
| **Default-on web search across all chat models** | Comet/Perplexity built around it | Web search is a backend choice the router should make, not a global toggle. Adding it as a separate axis to every backend reintroduces config sprawl | If/when added, route to it through an explicit "web-search task" classifier head, not a global flag. v2+. |
| **"Compare 5 models on this prompt" as a default UX** | Cool demo | Fights the single-input "auto-route" ethos. Belongs in a hidden dev mode | Side-by-side compare lives in v2 dev mode only. |

---

## Per-Backend Response Shape

This is the most product-critical section because the three backends produce radically different output and stuffing them into one bubble naively will make the product feel chaotic. Each row below is a **must-decide** for v1.

### 1. OpenRouter chat models (Claude Sonnet, GPT-5, Gemini, DeepSeek, Qwen)

**Shape:** Standard markdown-streamed text. Single bubble, no nested structure.

| Element | v1 Behavior | Reference |
|---|---|---|
| Streaming | Token-by-token via SSE | [Vercel AI SDK](https://www.sitepoint.com/nextjs-ai-streaming-building-realtime-apps-with-vercel-ai-sdk/) |
| Markdown | Headings, lists, tables, inline code | [react-markdown + remark-gfm] |
| Code blocks | Syntax highlight; must not break mid-stream (defer rendering until closing fence, OR render progressively with "streaming" indicator inside) | [llm-ui code blocks](https://llm-ui.com/docs/blocks/code/), [Chrome Developers](https://developer.chrome.com/docs/ai/render-llm-responses) |
| Citations | OpenRouter doesn't natively return citations from most models. If a model returns them inline, render as links | — |
| Tool-use output | OpenRouter chat models in v1 are conversational only — no tool calls. If they call tools (some Anthropic models can), render as a collapsed `[tool: X]` chip | — |
| "Routed to" chip | Above the bubble: `Claude Sonnet 4.5 · writing` | — |
| Stop button | Visible during stream; converts to Regenerate after | — |

### 2. Claude Code SDK (agentic coding backend)

**Shape:** Streamed sequence of (tool calls + tool results + interim narration) culminating in a final assistant summary. This is **the hardest backend to render well.** The repo will live or die on whether this looks coherent.

| Element | v1 Behavior | Reference |
|---|---|---|
| Outer bubble | One assistant bubble per "agent turn" (regardless of how many tool calls happen inside) | [Cursor agent UI](https://docs.cursor.com/chat/agent) |
| Agent header | `Claude Code · building…` with elapsed timer; flips to `Claude Code · done in 0:47` on finish | [Claude SDK demos](https://github.com/anthropics/claude-agent-sdk-demos) |
| Tool-call list | Collapsed by default. Inline chip per tool: `[Read src/app.py]`, `[Edit src/app.py]`, `[Bash npm test]`. Click chip → expand details ([AG-UI pattern](https://docs.ag-ui.com/introduction), [openclaw#21032](https://github.com/openclaw/openclaw/issues/21032)) | — |
| File diffs | When the agent edits a file, render a real red/green diff inline in the bubble. v1 minimum: render as ` ```diff` fenced block. v1.x: real diff component | [Cursor diff display](https://dredyson.com/fix-cursor-ide-diff-display-issues-a-complete-beginners-step-by-step-guide-to-resolving-only-some-diffs-being-shown-when-agent-makes-changes/) |
| Terminal output | Render in a `<pre>` with monospace font; truncate if >50 lines with "show all" expander | — |
| Interim narration | Stream the model's natural-language commentary between tool calls as italicized inline text | [Claude SDK streaming-output docs](https://code.claude.com/docs/en/agent-sdk/streaming-output) |
| Final summary | The agent's last assistant message renders as a normal markdown section at the bottom of the bubble | — |
| Working indicator | Pulsing dot + tool name: `🔧 Reading src/app.py…` (auto-replaces with the tool chip once done) | — |
| Abort | Stop button kills the whole agent loop, not just the current stream. Partial work is shown as "Aborted at step 3" | — |
| "Routed to" chip | `Claude Code SDK · build-and-edit` | — |
| Token / latency / cost | Aggregate across all sub-calls; show under the bubble | — |

**Visual archetype:** Cursor's chat panel, but inside a single chat surface instead of a sidebar. Each tool call is a collapsible chip; the final summary is the headline.

### 3. Anthropic computer-use (browse/act backend)

**Shape:** Streamed sequence of (screenshot + action) pairs, sometimes interspersed with text narration, ending in a final summary. Visual heavy.

| Element | v1 Behavior | Reference |
|---|---|---|
| Outer bubble | One bubble per agent run | [Anthropic computer use docs](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/computer-use-tool) |
| Screenshot strip | Horizontal thumbnail strip below the agent header. Each thumbnail is one action step. Click to enlarge in modal | [Simon Willison's exploration](https://simonwillison.net/2024/Oct/22/computer-use/) |
| Action narration | One line per action: `Clicked "Submit" at (412, 689)` / `Typed "michael@…" into email field` | — |
| Latest screenshot pinned large | Newest screenshot rendered full-width above the strip while the agent works | — |
| Browser snapshot (final) | After the run, the last screenshot stays visible; user can download it | — |
| Final summary | Markdown summary of what was accomplished | — |
| Working indicator | "Computer-use is acting on browser… step 5 of ?" | — |
| Abort | Stop button kills the agent loop and the underlying VM/process | — |
| Safety chip | A prominent "⚠ Computer-use can browse and click" disclaimer chip the first time it's invoked in a thread (BYOK trust signal) | — |
| "Routed to" chip | `Computer Use · browse-and-act` | — |

**Visual archetype:** Closest analog is [Anthropic's reference computer-use demo](https://www.anthropic.com/news/3-5-models-and-computer-use) (noVNC panel beside chat), adapted to live inside a chat bubble instead of a separate panel.

### Cross-Backend Consistency Rules

To prevent the chat from feeling chaotic with three different bubble shapes:

1. **Same outer container** — every assistant bubble has the same width, padding, border, and header (routing chip + rationale).
2. **Same "stop" button position** — top right of every assistant bubble.
3. **Same final-summary section** — every bubble ends with a markdown-rendered conclusion, even if the body is a screenshot strip or tool list.
4. **Same metadata footer** — every bubble has the same `[1.2s · 421 tokens · $0.02]` row.
5. **Collapse aggressive complexity** — agent details (tool calls, screenshots) collapse by default; expand on click. The default view of three different backends should look more alike than different.

---

## Multi-Turn Routing UX

Per the question, this is a routing-specific design area with no clear industry consensus. The strong opinion below is informed by [vllm-project/semantic-router#1458 (Conversational Routing Momentum)](https://github.com/vllm-project/semantic-router/issues/1458) and the observed Poe / Cursor / ChatGPT behaviors.

### How competitors handle thread-level vs turn-level model choice

- **Poe** — `@mention` to switch models per turn within a thread; default is the bot the thread started with. Thread-level = sticky to first-chosen bot; turn-level = explicit `@`. ([Poe blog](https://poe.com/blog/multi-bot-chat-on-poe))
- **ChatGPT auto** — Hidden router decides per turn; user has no per-turn override visibility, which is the main criticism. ([TechCrunch](https://techcrunch.com/2025/08/12/chatgpts-model-picker-is-back-and-its-complicated/))
- **OpenRouter chat playground** — Manual model selection per chat or per turn via a dropdown; no auto-routing. ([OpenRouter](https://openrouter.ai/chat))
- **Cursor** — Explicit per-conversation mode (Ask vs Agent) but model is sticky within a conversation. ([Cursor docs](https://docs.cursor.com/chat/overview))
- **Claude.ai** — One model per thread (sticky); no per-turn switching. ([Claude.ai])

### Recommended v1 behavior

**Default: per-turn re-routing with conversation-aware classification.** Every turn is re-routed, BUT the classifier sees the recent conversation history (not just the last user message). This avoids the "yes do that" misclassification problem ([semantic-router#1458](https://github.com/vllm-project/semantic-router/issues/1458)) while preserving the Core Value of letting the router pick the best backend for each task.

**Soft stickiness:** when the previous turn used an agent backend (Claude Code or computer-use), the next turn is biased toward continuing on that backend if the user message is short/contextual ("yes", "now run the tests", "continue"). This is captured as a feature in the classifier feature vector (`prev_backend`, `prev_was_agent`), not as a hard pin.

**Explicit overrides:**

1. **Per-turn override** — `/claude-sonnet`, `/code`, `/computer`, `/auto` slash commands, or a dropdown next to the send button. Applies to the next turn only.
2. **Pin to backend** — checkbox in thread settings: "Always use Claude Sonnet in this thread." Toggleable per-thread. Useful for "I just want to chat with Claude for this whole conversation, stop routing."
3. **Pin to "no agents"** — separate toggle: "Don't route to agentic backends in this thread." Useful for casual conversation where the user doesn't want to accidentally trigger a $$ Claude Code run.

| Routing policy | v1 / v2 |
|---|---|
| Per-turn re-routing with conversation context fed into classifier | v1 |
| Soft stickiness on agent backends for short follow-ups | v1 |
| Per-turn override via slash command or dropdown | v1 |
| Pin-to-backend toggle per thread | v1 |
| Pin-to-no-agents toggle per thread | v1.x |
| Different routing strategies per thread (model_router vs tier_router) | v2 (dev mode) |

### Backend-switching mid-thread

When the router switches backends within a thread (e.g., chat → Claude Code), the next backend must receive **enough prior context to be useful** but **not the noisy full agent trace**. v1 rule:

- For chat-to-chat transitions: pass full message history.
- For chat-to-agent transitions: pass the last user message + a summary of the last 3 turns (generated by a cheap model).
- For agent-to-chat transitions: pass the agent's final summary + the last user message, not the full tool-call log.

This is non-trivial — flag in [Hidden Complexity](#hidden-complexity).

---

## Settings / Configuration Features

For an open-source BYOK product, settings are the second-most-important UI surface after the chat itself. Below is what an opinionated v1 settings page looks like.

### Backend Configuration

| Setting | Type | Default | v1 / v2 |
|---|---|---|---|
| OpenRouter API key | Password input | (empty; reads `.env`) | v1 |
| Anthropic API key (for Claude Code & computer-use) | Password input | (empty; reads `.env`) | v1 |
| Optional Google API key | Password input | (empty) | v1.x |
| Enable backend: OpenRouter chat | Toggle | On if key present | v1 |
| Enable backend: Claude Code SDK | Toggle | On if key present | v1 |
| Enable backend: Computer-use | Toggle | **Off by default** (cost + safety) | v1 |
| Per-backend availability indicator | Read-only | Green/red dot | v1 |

### Routing Behavior

| Setting | Type | Default | v1 / v2 |
|---|---|---|---|
| Default routing strategy | Dropdown: `model_router` / `tier_router` / `embedding_router` | `model_router` | v1 (devs only; hidden by default) |
| Classifier confidence threshold (ask-before-routing-below-X) | Slider 0.0–1.0 | 0.0 (never ask) | v2 |
| Default backend override (when router is uncertain) | Dropdown of backends | Auto | v2 |
| Budget cap per turn (max tokens) | Number input | 4096 | v1.x |
| Allow auto-fallback on error | Toggle | On | v1.x |

### Chat / UX

| Setting | Type | Default | v1 / v2 |
|---|---|---|---|
| Theme | Light / Dark / System | System | v1 |
| Font size | Small / Medium / Large | Medium | v1.x |
| Show routing chip | Always / On hover / Never | Always | v1 (but defending "Always" as the only sane default; the option exists so power users can hide it for screenshots) |
| Show token / latency / cost per turn | Toggle | On | v1 |
| Auto-rename threads | Toggle | On | v1 |

### Privacy

| Setting | Type | Default | v1 / v2 |
|---|---|---|---|
| Telemetry | Toggle | **Off** | v1 (must be off by default — BYOK trust) |
| Local logging of routing decisions | Toggle | On | v1 |
| Export local data | Button | — | v1.x |
| Wipe all threads | Button (with confirm) | — | v1 |

### Pro/Dev Options (hidden by default behind a "Show advanced" toggle)

| Setting | v1 / v2 |
|---|---|
| Routing strategy switcher | v2 |
| Show classifier breakdown by default | v2 |
| A/B route comparison mode | v2 |
| Custom OpenRouter base URL | v1.x |
| Custom model mapping JSON override | v2 |

---

## Onboarding / First-Run Experience

What an open-source chat app a developer just `git clone`'d expects to encounter.

### README quickstart (required for v1)

1. **Three-command install** — `git clone`, `make install` (or `pnpm install && pip install -r requirements.txt`), `make dev`.
2. **`.env.example`** with `OPENROUTER_API_KEY=`, `ANTHROPIC_API_KEY=` and a comment explaining what each enables.
3. **The "golden path" demo prompts** (from `PROJECT.md` Active scope) — three prompts that prove the routing thesis end-to-end:
   - "What's the capital of France?" → routes to cheap chat model
   - "Build me a React todo app with localStorage" → routes to Claude Code SDK
   - "Open hacker news and tell me the top story title" → routes to computer-use
4. **Screenshot or 30s video** of all three routes happening in the UI.
5. **Troubleshooting** — what to do if a backend key is missing, if a model is rate-limited, etc.

### First-run in-app experience

| Step | v1 / v2 |
|---|---|
| First-run welcome modal explaining "this app auto-routes; here's why" | v1 |
| Detect missing keys → friendly setup screen with deep-links to OpenRouter / Anthropic key creation pages | v1 |
| Sample prompts displayed as one-click cards in empty thread state | v1 |
| Backend availability check on startup with green/red status row | v1 |
| Walkthrough tour (clicking through the chip, rationale, override) | v2 |

### Sample prompts shown in empty state

These should be hardcoded in v1 and chosen to **demonstrate routing diversity**:

- "Explain transformers to a 12-year-old" — routes to a cheap-medium chat model
- "Write a SQL query to find top 10 customers by revenue" — routes to a strong chat model (coding-leaning)
- "Build me a Python CLI that converts CSV to JSON with type inference" — routes to Claude Code SDK
- "Open weather.com and tell me tomorrow's forecast for Brooklyn" — routes to computer-use
- "What was Napoleon's birth year?" — routes to the cheapest chat model

When the user clicks one, the prompt is inserted and they see the routing chip and rationale fire on the response. **This is the most important onboarding moment in the product.**

---

## Quality / Evaluation Features

Since the existing repo has `src/evaluation/`, the product should close the loop by exposing user-facing eval features. This is a differentiator (researcher-grade transparency) and explicitly does NOT violate the "no live retraining" constraint — these features only **capture** signal; retraining happens offline.

| Feature | v1 / v2 | Notes |
|---|---|---|
| Show classifier confidence per turn (expandable) | v1.x | Renders as a sparkline or "task=coding (0.82)" tag in the expandable rationale. |
| Log every routing decision to local JSONL | v1 | One row per turn: `{ts, thread_id, turn_id, prompt, classifier_output, chosen_backend, rationale, latency, tokens, user_feedback?}`. |
| "Wrong route" feedback button | v1 | Thumbs-down opens "what should have been routed?" picker. |
| Export routing-decision log to CSV | v1.x | Single button in settings. Feeds repo's `src/evaluation/`. |
| Dev mode: run prompt through all routers, show divergences | v2 | Hidden behind `?dev=1`. |
| Routing-decision history view (filterable, sortable) | v2 | Like a mini analytics dashboard inside the app. |

**Key constraint:** none of this data ever leaves the user's machine. Export is explicit user action only.

---

## Hidden Complexity (Features That Look Simple But Bite)

Flagged so the planner can budget time in the roadmap.

### 1. Streaming code blocks without breaking syntax highlighting (M-L)

The fenced code block ` ``` ` is the closing fence — but the highlighter doesn't know what language it is until the opening fence's language tag arrives, and during streaming the closing fence hasn't arrived yet. Naive implementations either flash unstyled text or fail to highlight at all. Solutions:

- Defer highlighting until the closing fence arrives, with a visible "streaming" pulse inside the block ([llm-ui pattern](https://llm-ui.com/docs/blocks/code/)).
- Or, re-tokenize after every chunk with a debounce — works but is expensive on large blocks.
- Pick one and commit; document the choice.

### 2. Abort mid-stream with partial preservation (M)

The stop button must:
- Cancel the upstream HTTP/SSE connection without leaking sockets.
- For OpenRouter: cancel the request via the AbortController.
- For Claude Code SDK: kill the agent loop without leaving orphan processes ([SDK streaming docs](https://code.claude.com/docs/en/agent-sdk/streaming-output)).
- For computer-use: kill the agent loop AND the controlled browser/VM.
- Save what was streamed as a real persisted message marked "stopped by user."
- Trigger UI state change (Stop → Regenerate) without race conditions.

Each backend has different cancellation semantics. v1 must handle all three.

### 3. Switching backends mid-thread without losing context (M-L)

Covered in [Multi-Turn Routing UX](#multi-turn-routing-ux). The context-summarization logic for chat-to-agent transitions is genuinely tricky and worth a half-day of dedicated design.

### 4. Streaming tool calls from Claude Code SDK alongside narration (M)

The SDK streams `StreamEvent` messages mixed with `AssistantMessage` and `ResultMessage` ([docs](https://code.claude.com/docs/en/agent-sdk/streaming-output)). The UI needs a state machine that knows whether we're currently inside a tool call, between tool calls, or in the final summary, and renders each appropriately. Naive concatenation produces garbled output.

### 5. Displaying agent tool calls without visual noise (M)

Collapsing-by-default is the right pattern ([openclaw#21032](https://github.com/openclaw/openclaw/issues/21032), [Cursor forum](https://forum.cursor.com/t/add-expand-collapse-for-agent-responses-in-chat/158779)), but you still have to decide:
- What counts as a "step worth showing as a chip" vs. an internal detail?
- How to summarize 47 tool calls into something a non-developer can skim?
- How to avoid showing both the tool input and tool result if the result is huge?

Plan to iterate on this — first cut will not be ideal.

### 6. Auto-rename threads without blocking the chat (S-M)

The "name the thread from first message" feature must be async — don't block the user's first turn waiting for the title-generation call to complete. Common bug: title generation also routes through the router, which classifies "Give me a 5-word title for…" as some weird task and gets routed wrong. Solution: title generation bypasses the router entirely and goes to the cheapest model.

### 7. SSE through a Next.js/FastAPI pair (M)

Multiple HTTP middleware layers (Next.js dev server, prod reverse proxy, FastAPI middleware) can buffer SSE chunks. Confirm streaming works in both dev and prod modes end-to-end early, before building the rest of the UI.

### 8. Backpressure when the user opens 5 threads (S-M)

Each open thread might have a pending streaming response if the user navigates away mid-stream. Either: (a) cancel the stream on navigation, or (b) let it complete in the background and accumulate. (b) is the right answer (matches ChatGPT/Claude.ai behavior) but requires managing background streams and ensuring they complete to local storage.

### 9. Routing chip layout shift (XS-S)

The routing chip resolves AFTER the prompt is sent but BEFORE the first token streams. There's a ~200ms window where the bubble exists but the chip isn't filled in yet. Reserve the chip's space to prevent a layout shift; show a shimmer/skeleton until the route resolves.

### 10. Race between thread auto-rename and user manual rename (S)

If the auto-rename arrives 800ms after the user has already manually renamed, don't overwrite. Use a "user_renamed" flag.

### 11. "Routed to X" trust when X is the wrong choice (UX, not technical)

Even with a visible chip and rationale, users will sometimes feel "this should have gone to Claude, not GPT." The "Re-route with different backend" regenerate option is the v1 safety valve. Without it, mis-routes feel like the product is gaslighting them.

### 12. Long thread context window overflow (L)

Eventually a thread will exceed the chosen backend's context window. v1 can fail gracefully with a clear error ("This thread exceeds Claude Sonnet's 200k context — start a new thread or summarize"). v2 should auto-summarize. Plan for this — flagged in differentiators.

---

## Feature Dependencies

```
Per-turn routing decision layer
    └──requires──> Task type classifier (existing)
    └──requires──> Agentic-intent classifier (Active scope, needs training)
    └──requires──> Backend availability check
    └──requires──> Model mapping config

Streaming UI
    └──requires──> SSE endpoint in FastAPI
    └──requires──> Per-backend streaming adapter (OpenRouter, Claude Code, computer-use)
    └──requires──> Stop button + AbortController plumbing

Persistent threads
    └──requires──> SQLite schema (threads, messages, routing_decisions)
    └──requires──> Sidebar UI
    └──requires──> Thread auto-rename pipeline

Routing chip + rationale
    └──requires──> Routing decision layer
    └──requires──> Persistent storage of {backend, model, rationale} per message

Override / pin-to-backend
    └──requires──> Routing chip (so user can see what they're overriding)
    └──requires──> Manual route flag in routing decision

Tool-call display for Claude Code
    └──requires──> Claude Code SDK streaming integration
    └──requires──> Collapsible-section component
    └──requires──> File-diff renderer (v1.x for rich diffs)

Screenshot strip for computer-use
    └──requires──> Computer-use integration
    └──requires──> Image storage (local) and display

"Wrong route" feedback button
    └──requires──> Routing chip
    └──requires──> Local logging of routing decisions
    └──enhances──> Future offline router retraining

Side-by-side comparison
    └──requires──> All routing/streaming machinery
    └──conflicts──> Single-input "auto-route" ethos (so: defer to v2 dev mode)

Auto-summarize long threads
    └──requires──> Context-window detection per backend
    └──conflicts──> "No live retraining" constraint? — NO, summarization is context management, not training
```

### Dependency Notes

- **Routing chip is on the critical path** for almost every routing-related feature. Build it once, build it well, on day one.
- **Per-backend streaming adapter** is the gate to a believable v1. Build OpenRouter first (easiest, validates the SSE pipe), then Claude Code SDK, then computer-use.
- **Override / pin-to-backend conflicts with the "no model picker" ethos** in spirit but is necessary for trust. The way to reconcile: defaults are auto; overrides are explicit and visible.
- **Side-by-side comparison and auto-routing conflict philosophically** — the former says "pick whichever you like better," the latter says "we'll pick for you." Keep them in different UI modes; never blend them into the default chat surface.

---

## MVP Definition

### Launch With (v1) — The "Prove the Thesis" Cut

The single goal of v1 is to make a user say "huh, it routed to Claude Code without me asking, and the result was actually right." Everything below serves that moment.

**Chat foundation (table stakes):**
- [ ] Single-input chat with multi-turn threads + sidebar
- [ ] Token-by-token streaming for OpenRouter chat models
- [ ] Stop button mid-stream (all three backends)
- [ ] Regenerate (with optional re-route)
- [ ] Markdown + code block syntax highlighting (with streaming-safe rendering)
- [ ] Copy message as markdown
- [ ] Thread auto-rename from first message
- [ ] Thread rename / delete
- [ ] Inline error states with manual retry
- [ ] Backend availability check at startup
- [ ] Empty-state sample prompt cards (the routing-thesis demo set)

**Routing surface (the core value):**
- [ ] Routed-to chip on every assistant message (always visible)
- [ ] One-line rationale next to the chip
- [ ] Per-turn override via slash command or dropdown
- [ ] Pin-to-backend toggle per thread
- [ ] Manual-route chip visually distinct from auto-route chip

**Backend integration:**
- [ ] OpenRouter chat streaming (Claude Sonnet, GPT-5, Gemini, DeepSeek, Qwen)
- [ ] Claude Code SDK with streamed tool calls + collapsible chips + final summary
- [ ] Computer-use with screenshot strip + action narration + final summary
- [ ] Cross-backend consistency rules (same bubble shape, same metadata footer)

**Settings:**
- [ ] BYOK key entry for OpenRouter / Anthropic
- [ ] Per-backend enable toggles (computer-use off by default)
- [ ] Theme (light/dark/system)
- [ ] Telemetry off by default
- [ ] Wipe all threads button

**Quality/eval (cheap to do, big payoff):**
- [ ] Local JSONL log of every routing decision
- [ ] "Wrong route" thumbs-down feedback button

**Onboarding:**
- [ ] README with three golden-path demo prompts + screenshots
- [ ] `.env.example`
- [ ] First-run modal explaining auto-routing
- [ ] Missing-key friendly setup screen

### Add After Validation (v1.x)

- [ ] Edit prior user message + fork thread (Claude.ai-style)
- [ ] Export thread as `.md`
- [ ] Inline file-diff renderer for Claude Code (rich red/green diffs)
- [ ] Model fallback on error (auto-retry on alternative within same tier)
- [ ] Expandable "why this route" classifier breakdown
- [ ] Cost-per-turn display
- [ ] Pin-to-no-agents toggle per thread
- [ ] Export routing-decision log to CSV
- [ ] Budget cap per turn (max tokens)
- [ ] Custom OpenRouter base URL

### Future Consideration (v2+)

- [ ] Side-by-side comparison of two backends (dev mode only)
- [ ] A/B test two routing strategies (dev mode only)
- [ ] Auto-summarize long threads
- [ ] Conversation context-fill indicator
- [ ] Classifier confidence threshold (ask-before-routing)
- [ ] Routing strategy switcher (`model_router` vs `tier_router` vs `embedding_router`)
- [ ] Routing-decision history view (analytics dashboard)
- [ ] Voice input / TTS
- [ ] File / image uploads
- [ ] Prompt rewriting suggestion ("Improve prompt" button)
- [ ] Mobile-responsive polish

### Explicit "Never" (Anti-Features — see [section above](#anti-features-deliberately-not-built))

- User accounts / auth
- Server-side telemetry phone-home
- Hosted version
- Public sharing of chats
- Persona / bot marketplace
- Server-stored API keys
- In-app billing
- Live online learning of the router
- Voice as a v1 backend

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---|---|---|---|
| Streaming OpenRouter chat | HIGH | MEDIUM | P1 |
| Routing chip on every message | HIGH | LOW | P1 |
| One-line rationale | HIGH | LOW | P1 |
| Per-turn override (slash / dropdown) | HIGH | MEDIUM | P1 |
| Pin-to-backend per thread | HIGH | MEDIUM | P1 |
| Claude Code SDK with collapsible tool chips | HIGH | HIGH | P1 |
| Computer-use with screenshot strip | HIGH | HIGH | P1 |
| Stop button (all backends) | HIGH | MEDIUM | P1 |
| Regenerate with re-route | HIGH | LOW-MEDIUM | P1 |
| Multi-turn persistent threads + sidebar | HIGH | MEDIUM | P1 |
| Markdown + code blocks (streaming-safe) | HIGH | MEDIUM | P1 |
| BYOK settings panel | HIGH | MEDIUM | P1 |
| Empty-state sample prompts (golden path) | HIGH | LOW | P1 |
| Backend availability check at startup | HIGH | LOW | P1 |
| "Wrong route" feedback button | MEDIUM | LOW | P1 |
| Local JSONL log of routing decisions | MEDIUM | LOW | P1 |
| Auto-rename threads | MEDIUM | LOW | P1 |
| Copy message as markdown | MEDIUM | LOW | P1 |
| Token / latency display | MEDIUM | LOW | P1 |
| Theme (light/dark) | MEDIUM | LOW | P1 |
| Edit + fork thread | MEDIUM | MEDIUM | P2 |
| Export thread as `.md` | MEDIUM | LOW | P2 |
| Inline file-diff renderer (rich) | MEDIUM | MEDIUM | P2 |
| Model fallback on error | MEDIUM | MEDIUM | P2 |
| Expandable classifier breakdown | MEDIUM | LOW-MEDIUM | P2 |
| Cost-per-turn display | MEDIUM | MEDIUM | P2 |
| Export routing decisions to CSV | MEDIUM | LOW | P2 |
| Side-by-side comparison | LOW (dev only) | HIGH | P3 |
| A/B router strategy compare | LOW (dev only) | MEDIUM | P3 |
| Auto-summarize long threads | MEDIUM | HIGH | P3 |
| Voice / file uploads | MEDIUM | HIGH | P3 |
| Prompt rewriting | LOW | MEDIUM | P3 |

**Priority key:** P1 = must have for v1 launch · P2 = v1.x (add when validated) · P3 = v2+ (defer)

---

## Competitor Feature Analysis

| Feature / UX choice | Perplexity Comet | OpenRouter Chat | Poe | ChatGPT auto | Cursor (Ask) | Claude.ai | **Our approach** |
|---|---|---|---|---|---|---|---|
| Auto-routing | ✓ (Pro Search auto) | ✗ (manual select) | ✗ (recommended bots, @-mention) | ✓ (Instant vs Thinking, hidden) | ✗ (manual) | ✗ (manual) | **✓ default; always-visible chip + rationale; manual override** |
| Visible "routed to X" chip | partial | n/a | n/a (visible bot mention) | ✗ (criticized) | n/a (model shown) | n/a | **✓ always visible above bubble** |
| Per-turn model override | n/a | per-message dropdown | @-mention | ✗ | ✗ (per-conversation) | ✗ (per-thread) | **✓ slash command + dropdown** |
| Thread-level pin | n/a | per-chat selection | sticky to first bot | n/a | per-conversation | per-thread | **✓ explicit toggle in thread settings** |
| Agent (build/edit) | ✓ (browser actions) | ✗ | ✗ (general) | ✗ | ✓ (Agent Mode) | partial (artifacts) | **✓ Claude Code SDK + computer-use** |
| Tool-call display | inline narration | n/a | n/a | n/a | ✓ (collapsible) | partial | **✓ collapsible chips, Cursor-style** |
| File diff display | n/a | n/a | n/a | n/a | ✓ (inline) | partial | **✓ inline (`diff` block in v1, rich in v1.x)** |
| Screenshots for browse | ✓ (browser snapshots) | n/a | n/a | n/a | n/a | n/a | **✓ thumbnail strip** |
| Streaming | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **✓ across all 3 backends** |
| Stop / regenerate | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **✓** |
| Edit + fork | partial | partial | ✓ | partial | partial | ✓ | v1.x |
| Export | partial | ✓ (export from chatroom) | partial | partial | n/a | partial (email) | **v1.x as `.md`** |
| Side-by-side compare | n/a | ✓ (playground) | ✓ (multi-bot) | n/a | n/a | n/a | **v2 dev mode** |
| Thumbs-up/down feedback | ✓ | ✗ | ✓ | ✓ | ✗ | ✓ | **✓ as "wrong route" not "bad response"** |
| Sharing / public links | ✓ | partial | ✓ | ✓ | n/a | ✓ | **✗ anti-feature (local-first)** |
| Personas / bots marketplace | ✗ | ✗ | ✓ (core) | ✓ (GPTs) | ✗ | partial (Projects) | **✗ anti-feature** |
| BYOK | partial | ✓ | ✗ | ✗ | ✗ | ✗ | **✓ required** |
| Login required | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **✗ anti-feature** |
| Telemetry | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **✗ off by default; opt-in only** |

### Things to copy
- **Cursor:** collapsible tool-call chips + inline diff view + Stop-button-aborts-agent. Cursor has the cleanest agentic chat UI in the market.
- **Claude.ai:** thread auto-rename, edit + fork, the calm minimalist layout.
- **Perplexity Comet:** screenshot strip + agentic browser surface; visible "what the agent is doing right now."
- **Poe:** explicit per-turn model switching as a power-user escape hatch (we do this as override, not as @-mention).
- **OpenRouter chat:** BYOK + local storage of chats + export.

### Things to NOT copy
- **ChatGPT auto:** hiding which model answered. This is the cardinal sin our chip + rationale design exists to avoid.
- **Poe:** personas/bot marketplace. Reintroduces the "which thing do I pick" problem we're trying to remove.
- **All hosted competitors:** login walls, server-stored keys, telemetry on by default.
- **Cursor / Claude.ai:** model picker at the top of the thread. Replace it with auto-routing + override.

---

## Sources

### Competitors analyzed
- [Perplexity Comet — Introducing Comet](https://www.perplexity.ai/hub/blog/introducing-comet)
- [Perplexity Comet — Quick Start Guide](https://www.perplexity.ai/comet/resources/articles/comet-quick-start-guide)
- [Perplexity April 2025 changelog (auto-routing in Pro Search)](https://www.perplexity.ai/changelog/april-2025-product-update)
- [OpenRouter Chat — multi-model comparison playground](https://openrouter.ai/chat)
- [OpenRouter BYOK docs](https://openrouter.ai/docs/guides/overview/auth/byok)
- [OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection)
- [Poe — Multi-bot chat](https://poe.com/blog/multi-bot-chat-on-poe)
- [TechCrunch — ChatGPT's model picker is back, and it's complicated](https://techcrunch.com/2025/08/12/chatgpts-model-picker-is-back-and-its-complicated/)
- [TechRadar — ChatGPT's answers might not come from the model you think](https://www.techradar.com/ai-platforms-assistants/chatgpt/chatgpt-might-not-be-using-the-model-you-think-and-its-also-hiding-others-in-settings)
- [ChatGPT models explained — auto-router behavior 2026](https://www.ai-toolbox.co/chatgpt-models/chatgpt-models-explained-complete-comparison-2026)
- [Cursor — Chat overview](https://docs.cursor.com/chat/overview)
- [Cursor — Agent mode](https://docs.cursor.com/chat/agent)
- [Cursor — Best practices for coding with agents](https://cursor.com/blog/agent-best-practices)
- [Cursor — Skywork 2025 review](https://skywork.ai/blog/cursor-ai-review-2025-agent-refactors-privacy/)
- [Claude.ai — Artifacts and how to use them](https://support.claude.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them)
- [Claude.ai exporter guide](https://exploreaitogether.com/export-download-claude-guide/)
- [LibreChat](https://www.librechat.ai/)
- [Open WebUI vs LibreChat vs LobeChat comparison](https://blog.elest.io/the-best-open-source-chatgpt-interfaces-lobechat-vs-open-webui-vs-librechat/)

### Backend / SDK references
- [Claude Code SDK — streaming output](https://code.claude.com/docs/en/agent-sdk/streaming-output)
- [Claude Agent SDK overview](https://platform.claude.com/docs/en/agent-sdk/overview)
- [anthropics/claude-agent-sdk-demos](https://github.com/anthropics/claude-agent-sdk-demos)
- [Anthropic computer-use tool docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool)
- [Simon Willison — initial exploration of computer use](https://simonwillison.net/2024/Oct/22/computer-use/)
- [Anthropic — introducing computer use](https://www.anthropic.com/news/3-5-models-and-computer-use)

### UX / streaming / rendering patterns
- [Chrome Developers — best practices to render streamed LLM responses](https://developer.chrome.com/docs/ai/render-llm-responses)
- [llm-ui — code block streaming](https://llm-ui.com/docs/blocks/code/)
- [AI Chat UI best practices 2026](https://thefrontkit.com/blogs/ai-chat-ui-best-practices)
- [Vercel AI SDK — stopping streams](https://ai-sdk.dev/docs/advanced/stopping-streams)
- [Markdown Streaming UI — Markdoc approach](https://dev.to/abhaygawade/why-markdoc-for-llm-streaming-ui-3m26)
- [Skovy — rendering rich responses from LLMs](https://www.skovy.dev/blog/vercel-ai-rendering-markdown)
- [Upstash — Using SSE to stream LLM responses in Next.js](https://upstash.com/blog/sse-streaming-llm-responses)
- [Vercel AI SDK streaming in Next.js](https://www.sitepoint.com/nextjs-ai-streaming-building-realtime-apps-with-vercel-ai-sdk/)

### Routing / multi-turn behavior
- [vllm-project/semantic-router #1458 — Conversational routing momentum](https://github.com/vllm-project/semantic-router/issues/1458)
- [TrueFoundry — Sticky routing](https://www.truefoundry.com/docs/sticky-routing)
- [LangMem — managing long context with summarization](https://langchain-ai.github.io/langmem/guides/summarization/)
- [Maxim — context window management strategies](https://www.getmaxim.ai/articles/context-window-management-strategies-for-long-context-ai-agents-and-chatbots/)
- [RouteLLM — open-source LLM routing framework](https://github.com/lm-sys/RouteLLM)
- [LMSYS — RouteLLM blog post](https://www.lmsys.org/blog/2024-07-01-routellm/)

### Agent UI patterns
- [Cursor forum — expand/collapse agent responses](https://forum.cursor.com/t/add-expand-collapse-for-agent-responses-in-chat/158779)
- [openclaw #21032 — hide/collapse tool-call messages in chat](https://github.com/openclaw/openclaw/issues/21032)
- [AG-UI — Agent User Interaction Protocol](https://docs.ag-ui.com/introduction)
- [LangChain — agent-chat-ui](https://github.com/langchain-ai/agent-chat-ui)

### Feedback / evaluation patterns
- [Dwarves Memo — Thumbs up/down pattern](https://memo.d.foundation/llm/thumbs-up-and-thumbs-down-pattern)
- [Nebuly — LLM feedback loop](https://www.nebuly.com/blog/llm-feedback-loop)
- [Microsoft — beyond thumbs up/down for LLM evaluation](https://medium.com/data-science-at-microsoft/beyond-thumbs-up-and-thumbs-down-a-human-centered-approach-to-evaluation-design-for-llm-products-d2df5c821da5)
- [PAIR-code/llm-comparator — side-by-side LLM comparison](https://github.com/PAIR-code/llm-comparator)
- [Braintrust — A/B testing for LLM prompts](https://www.braintrust.dev/articles/ab-testing-llm-prompts)

### Error / fallback patterns
- [LiteLLM — fallbacks and retries](https://docs.litellm.ai/docs/proxy/reliability)
- [Maxim — retries, fallbacks, circuit breakers in LLM apps](https://www.getmaxim.ai/articles/retries-fallbacks-and-circuit-breakers-in-llm-apps-a-production-guide/)
- [Portkey — retries, fallbacks, and circuit breakers](https://portkey.ai/blog/retries-fallbacks-and-circuit-breakers-in-llm-apps/)

### Prompt rewriting
- [arXiv 2503.16789 — Conversational User-AI Intervention: Prompt Rewriting](https://arxiv.org/html/2503.16789v1)
- [Cursor forum — Improve Prompt button feature request](https://forum.cursor.com/t/feature-request-improve-prompt-button/139730)

---
*Feature research for: auto-routing multi-backend AI chat product (BYOK, open-source, local-first)*
*Researched: 2026-05-11*
