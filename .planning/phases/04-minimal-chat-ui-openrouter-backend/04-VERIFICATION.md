---
phase: 04-minimal-chat-ui-openrouter-backend
verified: 2026-05-19T18:30:00Z
status: pass
status_history:
  - 2026-05-19T18:30:00Z: human_needed (5/5 SCs verified by impl; 4 manual UAT items pending)
  - 2026-05-20T00:30:00Z: pass (UAT 7/7 verified; Gap #1 fix landed in commit 907fa38; Gap #2 deferred to Phase 5 scope)
score: 5/5
overrides_applied: 0
gaps_logged:
  - id: gap_1
    severity: blocker
    scope: phase-4
    status: fixed
    fix_commit: 907fa38
    description: "_get_or_create_adapter only caught ImportError; RuntimeError from missing-key adapter ctor escaped as 500"
  - id: gap_2
    severity: minor
    scope: phase-5
    status: deferred
    description: "Conversation history does not restore on /settings → / navigation (Phase 5 owns thread restore on mount)"
human_verification:
  - test: "Visual no-flicker sanity on a real OpenRouter stream"
    expected: "A Python code block renders as plain <pre><code> during streaming, then shiki highlights once after the closing fence — no visible flash or second highlight pass to the human eye"
    why_human: "Playwright's MutationObserver asserts no DOM mutations post-Done, but perceptible smoothness under real network latency requires a live visual check against OpenRouter"
  - test: "First-run modal flow from a brand-new clone (no .env)"
    expected: "On a clean workdir with no .env, pnpm dev + uvicorn start, the modal appears, user pastes OpenRouter key, chat input unlocks without restarting either process"
    why_human: "E2E spec covers the gated state with mock-fastapi; the clone-to-first-turn contributor experience is Phase 6 territory for time measurement (VALIDATION.md §Manual-Only Verifications row 2)"
  - test: "Metrics footer accuracy versus OpenRouter's billed cost"
    expected: "Cost USD shown in the footer matches the OpenRouter activity log within normal rounding for 3 submitted turns"
    why_human: "Cost value comes from the Done chunk upstream; a manual cross-check against the OpenRouter dashboard catches drift that mock-fastapi cannot"
  - test: "BYOK key UX: enter, mask, replace, clear"
    expected: "After entering a key via the modal, DevTools Application > Storage shows no plaintext key in localStorage / sessionStorage / cookies"
    why_human: "secure-key.spec.ts covers this programmatically; the manual check is belt-and-suspenders confirmation of no key residue after entry"
---

# Phase 4: Minimal Chat UI (OpenRouter Backend) — Verification Report

**Phase Goal:** A running `next dev` app delivers a single-input multi-turn chat that streams OpenRouter responses through a Next.js route handler proxying FastAPI; the routing chip and one-line rationale appear on every assistant message; streaming markdown + code blocks render without flicker; stop button preserves partial responses. This phase exists to prove the SSE pipe end-to-end with one backend before adding two more.
**Verified:** 2026-05-19T18:30:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## VERIFICATION PASSED (automated checks) — human UAT items remain

All five success criteria have automated test coverage or code-level evidence. Four manual items from VALIDATION.md §Manual-Only Verifications remain open. These are not implementation gaps — they are human-observable quality checks (visual smoothness, real-backend cost accuracy, contributor UX timing). No blockers found.

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User types a prompt, presses Enter, sees a streamed assistant response with token-by-token rendering; routing chip appears at top of every assistant message, never collapsed | VERIFIED | `apps/web/app/page.tsx` mounts `RoutingChip` unconditionally above every `AssistantMessage`; `RoutingChip.tsx` returns `null` only when no `data-routing` part exists on the message (correct guard — chip has no data to render before routing_decision arrives). `routing-chip.spec.ts` asserts chip visible across 3 turns and none has `offsetHeight=0` or `display:none`. |
| 2 | Code blocks render as plain `<pre>` during open fence, then receive syntax highlighting exactly once on fence close, with no mid-stream re-highlight | VERIFIED | `StreamingCodeBlock.tsx`: `isStreamingComplete=false` branch renders `<pre><code className>RAW</code></pre>` via React JSX text (no `dangerouslySetInnerHTML` on raw source). `useEffect` deps are `(isStreamingComplete, children, language)` — gates highlight to exactly one `highlightCode()` call. `no-flicker.spec.ts` installs a `MutationObserver` on the `<pre>` ancestor, waits for the Done signal, asserts `mutationsAfterDone === mutationsAtDone` (no post-Done mutations). Secondary assertion confirms `<span style|class` tokens are present (highlight did fire once). Visual manual check remains open per VALIDATION.md. |
| 3 | Stop button cancels in-flight stream within 2 seconds; partial response preserved on screen and persisted to SQLite; per-turn metrics (cost/latency/tokens) displayed | VERIFIED | `cancel-budget.spec.ts` measures `performance.now()` delta from Stop click to terminal UI (metrics footer OR alert banner OR Stop button hidden) and asserts `< 2000ms`. Partial preserved assertion: `partialAfter.length >= partialBefore.length`. DB persistence: `turn.py` writes `status="cancelled"` when `StreamError.code === "cancelled"` (lines 554-555) and `status="complete"` otherwise (line 553) — satisfying the amended `status IN ('cancelled','complete','error')` contract from Critical Finding #2. `MetricsFooter.tsx` renders `streaming●` mid-stream and `$X.XXXX · X.Xs · X↑/X↓` on `data-metrics` part arrival. |
| 4 | Browser never opens a connection to FastAPI directly — all requests target the Next.js origin only; `FASTAPI_URL` is server-only, never `NEXT_PUBLIC_*` | VERIFIED | `grep -rn "NEXT_PUBLIC" apps/web/` returns zero matches in production source (only comments in test files warning against it). `FASTAPI_URL` is only read at `apps/web/app/api/chat/route.ts:40`, `apps/web/app/api/settings/route.ts:31`, `apps/web/app/api/health/route.ts` — all server-side route handlers, never client components. `browser-isolation.spec.ts` registers `page.on('request')` for every browser request and asserts `offendingRequests` array is empty after a full happy-path turn. |
| 5 | On a fresh clone with no `.env`, the first-run modal appears, blocks the chat input, links to settings, and unblocks without restarting once a key is entered | VERIFIED | `useFirstRunGate.ts` calls `GET /api/health` on mount; `adapters.openrouter.status === "missing_key"` sets `needsKey=true`. `FirstRunModal.tsx`: `open={needsKey}`, non-dismissible (`onEscapeKeyDown`, `onPointerDownOutside`, `onInteractOutside` all `preventDefault`, `showCloseButton={false}`). Composer has `disabled={composerDisabled || needsKey}`. `KeyForm` dispatches `pomu:key-saved` on success; hook re-polls health to unblock. `first-run.spec.ts` asserts all seven steps of the modal flow end-to-end using mock-fastapi's state machine. Visual manual check on a real clone remains per VALIDATION.md. |

**Score:** 5/5 truths verified

---

## Per-Requirement Coverage

| Requirement | Description | Source Evidence | Status |
|-------------|-------------|-----------------|--------|
| UI-01 | Multi-turn chat input + scrolling message list | `apps/web/app/page.tsx` mounts `AssistantRuntimeProvider + ThreadPrimitive.Root + ThreadPrimitive.Viewport + ThreadPrimitive.Messages + ComposerPrimitive`; `useChatThread.ts` wires `AssistantChatTransport` with `prepareSendMessagesRequest` threadId injection. `first-run.spec.ts` submits a turn end-to-end. 04-01-SUMMARY: `requirements-completed: [UI-01]`. | VERIFIED |
| UI-03 | Streaming markdown + code-block highlight on fence close, no per-token re-highlight | `StreamingCodeBlock.tsx` + `MarkdownRenderer.tsx` (React.memo, arePropsEqual) + `shiki.ts` (singleton `createHighlighter`). `no-flicker.spec.ts` MutationObserver assertion. 04-06-SUMMARY: `requirements-completed: [UI-03]`. | VERIFIED |
| UI-04 | Routing chip + rationale on every assistant message, always visible | `RoutingChip.tsx` reads `useMessage().content.find(isRoutingPart)`; renders `Routed to <displayName> · <rationale>`. `routing-chip.spec.ts` asserts chip count = 3 after 3 turns, all with `offsetHeight > 0`. 04-05-SUMMARY: `requirements-completed: [UI-04]`. | VERIFIED |
| UI-06 | Stop / cancel mid-stream preserves partial response | `ComposerPrimitive.Cancel` wired to runtime's stop action in `page.tsx`. `cancel-budget.spec.ts` asserts 2s budget + partial preservation. 04-05-SUMMARY: `requirements-completed: [UI-06]`. | VERIFIED |
| UI-07 | Per-turn cost + latency + tokens alongside each assistant message | `MetricsFooter.tsx` reads `data-metrics` part from `useMessage().content`; formats `$X.XXXX · X.Xs · X↑/X↓`. `sse-translate.ts` emits `data-metrics` chunk on `done` event. 04-05-SUMMARY: `requirements-completed: [UI-07]`. | VERIFIED |
| UI-08 | ChatBubble renders OpenRouter responses — streamed markdown, copy-as-markdown, regenerate | `ChatBubble.tsx` assistant variant mounts `MarkdownRenderer`; copy uses `navigator.clipboard.writeText(rawMarkdown)` (raw source, not HTML); Regenerate calls `useMessageRuntime().reload()` (live-wired, Blocker 3 resolved). `routing-chip.spec.ts` assertion (e) verifies Regenerate fires a fresh POST. 04-05-SUMMARY: `requirements-completed: [UI-08]`. | VERIFIED |
| UI-13 | First-run modal + missing-key setup screen guides clone-to-first-turn | `FirstRunModal.tsx` + `useFirstRunGate.ts` + `KeyForm.tsx`. `first-run.spec.ts` asserts all steps. 04-07-SUMMARY: `requirements-completed: [UI-13]`. | VERIFIED |
| UI-17 | Next.js route handler proxies to FastAPI server-side; BYOK keys never travel browser ↔ FastAPI directly | Every route handler in `apps/web/app/api/*/route.ts` reads `FASTAPI_URL` (server-only). `browser-isolation.spec.ts` asserts zero browser requests outside Next origin. `settings/route.ts` scrubs key from all error paths. Zero `NEXT_PUBLIC_*` matches in production source. 04-03-SUMMARY: `requirements-completed: [UI-17]`. | VERIFIED |

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `apps/web/app/api/chat/route.ts` | SSE proxy with Node runtime + signal forwarding + body stripping | VERIFIED | `runtime="nodejs"`, `dynamic="force-dynamic"`, `signal: req.signal` forwarded to upstream fetch, `translateNamedSSEToUIMessageStream` called, `x-vercel-ai-ui-message-stream: v1` header set |
| `apps/web/app/api/settings/route.ts` | Key submission proxy with secret scrub on every error path | VERIFIED | `runtime="nodejs"`, `dynamic="force-dynamic"`, `.replace(key, "***")` on both `catch` and `!upstream.ok` paths; no `console.*` calls; no module-level key cache |
| `apps/web/lib/sse-translate.ts` | Pure function: Phase-3 named events → AI SDK v6 UI Message Stream chunks | VERIFIED | No module-level mutable state; all state in `start()` closure; CRLF normalization; `NamedSSEEventSchema.parse` at boundary; pattern F (error chunk + continue) on parse failures; 8-case switch covers all variants |
| `apps/web/lib/chunk-schemas.ts` | Zod schemas mirroring `chunks.py`; D-15 structured 5-key RoutingDecisionDataSchema | VERIFIED | `RoutingDecisionDataSchema` has exactly `{backend, model_or_agent, rationale, confidence, signals}` matching D-15 amended payload; `NamedSSEEventSchema` has 8 variants keyed by `event`; `StreamErrorCodeSchema` has 9 values matching `chunks.py:127-137` |
| `apps/web/components/RoutingChip.tsx` | Reads `routing.backend` / `.model_or_agent` / `.rationale` from data-routing content part | VERIFIED | `isRoutingPart` guard checks `p.type === "data" && name === "routing"`; reads `routing.backend`, `routing.model_or_agent`, `routing.rationale`, `routing.confidence` directly; no optional-chaining needed because Zod schema enforces shape at wire boundary |
| `apps/web/components/ChatBubble.tsx` | Assistant variant mounts MarkdownRenderer; live Regenerate | VERIFIED | `body = children ?? <MarkdownRenderer ...>`; Regenerate button calls `onRegenerate` prop (wired to `useMessageRuntime().reload()` in `page.tsx`); Copy calls `navigator.clipboard.writeText(rawMarkdown)` |
| `apps/web/components/MarkdownRenderer.tsx` | React.memo with custom arePropsEqual; no flicker | VERIFIED | `memo(MarkdownRendererBase, arePropsEqual)` where equality is `messageId === && rawMarkdown.length === && isStreamingComplete ===`; `rehypeSanitize` applied |
| `apps/web/lib/shiki.ts` | Single createHighlighter call at module scope | VERIFIED | `let highlighterPromise: Promise<Highlighter> | null = null` at module scope; `getHighlighter()` initializes it once; no second `createHighlighter` call anywhere |
| `apps/web/components/FirstRunModal.tsx` | Non-dismissible Dialog while `needsKey=true` | VERIFIED | `onEscapeKeyDown={(e) => e.preventDefault()}`, `onPointerDownOutside={(e) => e.preventDefault()}`, `onInteractOutside={(e) => e.preventDefault()}`, `showCloseButton={false}`; `if (!open) return null` |
| `apps/web/hooks/useFirstRunGate.ts` | Calls /api/health on boot; listens to visibilitychange + pomu:key-saved | VERIFIED | `useEffect` calls `refresh()` on mount; adds `document.addEventListener("visibilitychange")` and `window.addEventListener("pomu:key-saved")`; network-down distinct from missing-key (both `isReady:false,needsKey:false`) |
| `apps/web/playwright/no-flicker.spec.ts` | MutationObserver pattern; no test.skip | VERIFIED | Full assertion implementation; no `test.skip` or `it.todo` in file body |
| `apps/web/playwright/routing-chip.spec.ts` | Chip visibility across 3 turns, format regex, aria-label, Regenerate; no test.skip | VERIFIED | Full assertion implementation; 5 assertions (a-e); no `test.skip` |
| `apps/web/playwright/cancel-budget.spec.ts` | 2s budget; terminal state accepted; no test.skip | VERIFIED | `Promise.race` over 3 terminal signals; `elapsed < 2000` assertion; partial preserved assertion; no `test.skip` |
| `apps/web/playwright/browser-isolation.spec.ts` | Zero requests to FastAPI port; no test.skip | VERIFIED | `page.on('request')` captures all browser requests; filters for `https?:` scheme; asserts `offendingRequests.length === 0`; no `test.skip` |
| `apps/web/playwright/secure-key.spec.ts` | Key not in body/header/storage/console; no test.skip | VERIFIED | 6-channel check: response bodies, response headers, localStorage, sessionStorage, cookies, console messages; 57-char distinctive `SECRET_KEY`; no `test.skip` |
| `apps/web/playwright/first-run.spec.ts` | Modal flow; no test.skip | VERIFIED | 7 assertions covering modal visible → composer disabled → key entry → modal closes → composer enables → toast fires → turn streams with chip and metrics; no `test.skip` |
| `apps/web/playwright/mock-fastapi.py` | Canonical fixture catalog + body-prefix selector; no query-param mechanism | VERIFIED | `CANONICAL FIXTURE CATALOG` comment at top; `_resolve_fixture` uses `body.message.startswith("[fixture:NAME]")` exclusively; fixtures: default, code-block, slow, missing-key, auth-failed; `_FIXTURE_DISPATCH` table; `/__reset` test helper |
| `apps/api/routes/turn.py` (amended) | `routing_decision` event emitted as first yield before adapter dispatch | VERIFIED | Lines 465-485: `payload = {backend, model_or_agent, rationale, confidence, signals}`; `yield ServerSentEvent(event="routing_decision", data=json.dumps(payload))` before the `async for chunk in adapter.stream()` loop |
| `apps/api/tests/test_turn_streaming.py` | D-15 contract test | VERIFIED | `test_routing_decision_event_arrives_first_and_matches_done` at line 852; assertions: (a) first event is `routing_decision`, (b) within 500ms, (c) payload has exactly 5 keys, (d) `payload['signals'] == done_payload['routing_signals']` byte-for-byte |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `apps/web/app/page.tsx` | `/api/chat` (Next route) | `AssistantChatTransport({ api: "/api/chat" })` in `useChatThread.ts` | VERIFIED | `prepareSendMessagesRequest` injects `threadId`; transport set on `AssistantChatTransport` |
| `apps/web/app/api/chat/route.ts` | `apps/api/routes/turn.py` | `fetch(FASTAPI_URL + /api/v1/threads/${threadId}/turn)` with `signal: req.signal` | VERIFIED | Line 116-124 in `route.ts`; FASTAPI_URL read server-only |
| `apps/web/lib/sse-translate.ts` | `apps/web/lib/chunk-schemas.ts` | `import { NamedSSEEventSchema }` at module top | VERIFIED | Direct import; every event block parsed through schema before translation |
| `RoutingChip.tsx` | `data-routing` AI SDK part | `useMessage().content.find(isRoutingPart)` where `p.type === "data" && p.name === "routing"` | VERIFIED | Data path: turn.py → sse-translate (data-routing chunk) → @assistant-ui/react-ai-sdk convertMessage (type:data, name:routing) → useMessage().content |
| `MetricsFooter.tsx` | `data-metrics` AI SDK part | `useMessage().content.find(isMetricsPart)` where `p.name === "metrics"` | VERIFIED | Data path: turn.py done event → sse-translate (data-metrics chunk) → convertMessage → useMessage().content |
| `StreamingCodeBlock.tsx` | `shiki.ts:highlightCode` | `import { highlightCode } from "@/lib/shiki"` | VERIFIED | Called in `useEffect` only when `isStreamingComplete === true`; effect deps prevent re-call |
| `apps/web/app/api/settings/route.ts` | `apps/api/routes/settings.py` | `fetch(FASTAPI_URL + /api/v1/settings, { method: "PATCH" })` | VERIFIED | Line 71-75 in settings route; body shape `{ keys: { [provider]: key } }` per Phase 3 D-10 |
| `useFirstRunGate.ts` | `/api/health` proxy | `import { getHealth } from "@/lib/api-client"` | VERIFIED | `getHealth()` makes same-origin call; on `adapters.openrouter.status === "missing_key"` sets `needsKey=true` |
| `KeyForm.tsx` | `/api/settings` proxy | `import { postSettings } from "@/lib/api-client"` | VERIFIED | `postSettings` POSTs `{ provider, key }` to `/api/settings`; dispatches `pomu:key-saved` on success |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `RoutingChip.tsx` | `routingPart.data` (RoutingDecision) | `apps/api/routes/turn.py` lines 465-485 yields structured 5-key `routing_decision` SSE event sourced from real `decide()` return value | Yes — `decide()` calls calibrated classifiers and returns `RoutingDecision(backend, model_or_agent, rationale, confidence, signals)` | FLOWING |
| `MetricsFooter.tsx` | `metricsPart.data` (MetricsPayload) | `apps/api/routes/turn.py` yields `done` event with `tokens_in, tokens_out, cost_usd, latency_ms` from adapter's `Done` chunk | Yes — adapter accumulates real usage from OpenRouter API response | FLOWING |
| `ChatBubble.tsx` / `MarkdownRenderer.tsx` | `rawMarkdown` | `useMessage().content` text parts accumulated from `text_delta` SSE events | Yes — `text_delta` events carry real LLM output tokens | FLOWING |
| `FirstRunModal.tsx` | `open` prop (needsKey) | `useFirstRunGate.ts` → `GET /api/health` → `apps/api/routes/health.py` reading `app.state.settings` key status | Yes — healthz reads actual KeyStore state | FLOWING |

---

## Behavioral Spot-Checks

Step 7b is SKIPPED for the real-backend path — the app requires `uvicorn` + OpenRouter key to run live.

For the mock-fastapi CI path, verified via Plan 04-05 and Plan 04-07 SUMMARY evidence:

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Routing chip visible after turn | `pnpm --dir apps/web test:e2e routing-chip.spec.ts` | 1 test passed (3.3s per Plan 04-05 SUMMARY) | PASS (evidence) |
| No-flicker code block highlight | `pnpm --dir apps/web test:e2e no-flicker.spec.ts` | 1 test passed (4.4s per Plan 04-06 SUMMARY) | PASS (evidence) |
| 86 Vitest unit/component tests | `pnpm --dir apps/web test` | 86 passing per Plan 04-06 SUMMARY | PASS (evidence) |

---

## Probe Execution

No `scripts/*/tests/probe-*.sh` probes found in this phase. Phase 4 uses `pytest apps/api/tests/test_turn_streaming.py` as the D-15 contract probe.

| Probe | Command | Result | Status |
|-------|---------|--------|--------|
| D-15 contract test | `pytest apps/api/tests/test_turn_streaming.py::test_routing_decision_event_arrives_first_and_matches_done` | Assertions at lines 971-996 verify: first event is routing_decision, payload has exactly 5 keys, signals equals Done.routing_signals byte-for-byte. Test exists and is substantive (not stub). | PASS (code-level evidence; not run in this session — sandbox cannot start uvicorn) |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| UI-01 | Plan 04-01 + 04-05 | Multi-turn chat input + scrolling message list | SATISFIED | AssistantRuntimeProvider + ThreadPrimitive + ComposerPrimitive in page.tsx; first-run.spec.ts E2E |
| UI-03 | Plan 04-06 | Streaming markdown + no-flicker code-block highlight | SATISFIED | StreamingCodeBlock + MarkdownRenderer + shiki singleton + no-flicker.spec.ts |
| UI-04 | Plan 04-05 | Routing chip always visible on every assistant message | SATISFIED | RoutingChip unconditionally above AssistantMessage; routing-chip.spec.ts |
| UI-06 | Plan 04-05 + 04-07 | Stop preserves partial response | SATISFIED | ComposerPrimitive.Cancel + cancel-budget.spec.ts |
| UI-07 | Plan 04-05 | Per-turn cost + latency + tokens | SATISFIED | MetricsFooter + sse-translate data-metrics chunk |
| UI-08 | Plan 04-05 + 04-06 | ChatBubble renders markdown + copy + regenerate | SATISFIED | ChatBubble + MarkdownRenderer + live reload() wiring |
| UI-13 | Plan 04-07 | First-run modal guides clone-to-first-turn | SATISFIED | FirstRunModal + useFirstRunGate + KeyForm + first-run.spec.ts |
| UI-17 | Plan 04-03 | Next.js proxy; BYOK keys never travel browser↔FastAPI | SATISFIED | All route handlers server-only; browser-isolation.spec.ts + secure-key.spec.ts |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `apps/web/tests/first-run-modal.test.tsx` | 109, 125, 212 | `"sk-or-…XXX"` | INFO | This is a mock masked-key string literal in test data, not a debt marker. The "XXX" is part of a canned `masked` response body from the mock API. Not a FIXME/TBD debt comment. No action needed. |

No TBD, FIXME, or XXX markers found in production source files (apps/web/app/, apps/web/components/, apps/web/hooks/, apps/web/lib/, apps/api/routes/turn.py). The only matches are in test fixtures and comments referencing the absence of TODOs.

---

## Critical-Finding Compliance

| Finding | Requirement | Implementation | Status |
|---------|-------------|----------------|--------|
| CF #1: Current ecosystem is Next 16 / AI SDK v6, not Next 15.2 / v5 | D-07, UI-01 | Plan 04-01 SUMMARY: `next@16.2.6`, `ai@^6.0.184`, `@ai-sdk/react@^3.0.186`; `x-vercel-ai-ui-message-stream: v1` header set correctly for v6 protocol | COMPLIANT |
| CF #2: Stop writes `status="cancelled"`, not `status="complete"` | SC #3 | `turn.py` lines 553-557: `status="complete"` (no error), `status="cancelled"` (`StreamError.code=="cancelled"`), `status="error"` (other errors); cancel-budget.spec.ts broadened to `Promise.race` over 3 terminal signals | COMPLIANT |
| CF #3: Node runtime mandatory for SSE proxy | D-07, UI-17 | All 5 route handlers in `apps/web/app/api/` declare `export const runtime = "nodejs"` | COMPLIANT |
| CF #4: Return streaming `Response` immediately; never await body | D-07 | `route.ts` calls `translateNamedSSEToUIMessageStream(upstream.body)` and returns `new Response(translated, {...})` without any `await upstream.text()` on the success path | COMPLIANT |

---

## Cross-Cutting Truth Checks

| Truth | Evidence | Status |
|-------|----------|--------|
| `runtime = 'nodejs'` in every `apps/web/app/api/**/route.ts` | Confirmed for chat, settings, health, threads, threads/[id] — all 5 route files | VERIFIED |
| `dynamic = 'force-dynamic'` in every `apps/web/app/api/**/route.ts` | Confirmed for all 5 route files | VERIFIED |
| `FASTAPI_URL` is server-only; no `NEXT_PUBLIC_FASTAPI_URL` anywhere | Zero `NEXT_PUBLIC` matches in production source; only in test comments warning against it | VERIFIED |
| OpenRouter key never in client storage / response bodies / headers / logs | `settings/route.ts` scrubs key from all error paths; zero `console.*` in that file; `secure-key.spec.ts` enforces 6-channel check | VERIFIED |
| Phase 3 amendment contained — only `turn.py` + `test_turn_streaming.py` modified outside Phase 4 territory | `routing_decision` yield added only in `apps/api/routes/turn.py`; `test_turn_streaming.py` has the D-15 contract test added; no other Phase 3 files modified | VERIFIED |
| No scope creep into Phase 5/6 | No sidebar, no multi-thread CRUD, no all-three-backends, no README golden path, no OSS-07 Playwright CI E2E — all deferred per CONTEXT `<deferred>` section | VERIFIED |

---

## Non-Blocking Deviations (Sandbox/Environment)

Documented in Plan summaries; none affect production runtime:

1. **Geist font fetch blocked in sandbox** (Plan 04-01): Replaced with system font stack in `layout.tsx`. Production uses the system font; Geist can be added in Phase 6 polish. Non-blocking.
2. **Playwright browser install path** (Plan 04-01): Playwright 1.60 Chromium installed via `pnpm exec playwright install chromium` in CI; local `.venv/bin/python` path used for mock-fastapi on dev machines. Non-blocking.
3. **mock-fastapi IPv4 binding** (playwright.config.ts): `FASTAPI_URL=http://127.0.0.1:8001` (not `localhost`) because Node 18+ resolves `localhost` to `::1` first but mock-fastapi binds `127.0.0.1` only. Documented in config comments. Non-blocking (CI works correctly).
4. **Turbopack `../` traversal restriction** (Plan 04-05): `apps/web/lib/model-mapping.json` is a copy of `config/model_mapping.json`. Documented in `RoutingChip.tsx` comment. The canonical source is `config/model_mapping.json`; the copy must be kept in sync. Non-blocking for Phase 4; Phase 5+ should add a pre-build copy step.
5. **ROADMAP SC #3 wording says `status='complete'` for cancelled turns** (Critical Finding #2): Phase 3 actually writes `status='cancelled'`. The Playwright assertion was broadened to accept `status IN ('cancelled','complete','error')` which is correct behavior. The ROADMAP wording is slightly imprecise but the implementation is correct. Non-blocking.

---

## Human Verification Required

### 1. Visual No-Flicker Check

**Test:** Run `pnpm --dir apps/web dev` + `uvicorn apps.api.main:app --reload`. Submit "Write a short Python class that prints hello with a docstring". Watch the code fence render.
**Expected:** The code block appears as plain text during streaming, then syntax-highlighted spans appear once the closing ``` fence arrives — no visible flash, no second highlight pass.
**Why human:** Playwright's MutationObserver proves no DOM mutations post-Done, but the human-perceptible smoothness requires a live visual check on a real network stream.

### 2. First-Run Modal on a Real Clone

**Test:** On a clean workdir with no `.env`, run `pnpm --dir apps/web dev` + `uvicorn`. Open http://localhost:3000.
**Expected:** Modal appears with heading "Connect OpenRouter to get started"; chat input is disabled; paste an OpenRouter key and click "Save & continue"; modal closes and chat input enables without restarting either server; toast "OpenRouter connected — try a prompt!" fires.
**Why human:** The E2E spec covers this with mock-fastapi; the contributor-experience clock from `git clone` to first turn is Phase 6 territory (OSS-08).

### 3. Metrics Footer Accuracy

**Test:** Submit 3 turns with the real OpenRouter backend. Compare the displayed cost (e.g., `$0.0021`) to the OpenRouter activity log at openrouter.ai.
**Expected:** Displayed cost matches the billed cost within rounding tolerance.
**Why human:** `Done.cost_usd` comes from the upstream; manual cross-check catches upstream cost drift that mock-fastapi cannot simulate.

### 4. BYOK Key UX Storage Check

**Test:** After entering a key via the modal, open DevTools → Application → Storage.
**Expected:** No plaintext key in localStorage / sessionStorage / cookies. Only `prompt-optimizer.defaultThreadId` appears in localStorage.
**Why human:** `secure-key.spec.ts` covers this programmatically; manual DevTools check is belt-and-suspenders confirmation on a real browser session.

---

## Gaps Summary

No gaps found. All five ROADMAP success criteria are achievable through implemented and tested code. All eight assigned requirements have source-level evidence. All Playwright specs contain real assertions with no `test.skip` or `it.todo` bodies. The four human verification items are quality checks from VALIDATION.md §Manual-Only Verifications — they are not implementation gaps.

---

_Verified: 2026-05-19T18:30:00Z_
_Verifier: Claude (gsd-verifier)_
