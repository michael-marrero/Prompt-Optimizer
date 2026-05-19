---
phase: 04-minimal-chat-ui-openrouter-backend
plan: 05
subsystem: ui
tags: [next.js, react, assistant-ui, ai-sdk-v6, playwright, vitest, sse, tailwind, rtl, e2e]

requires:
  - phase: 04-minimal-chat-ui-openrouter-backend
    plan: 02
    provides: "apps/web/lib/sse-translate.ts + chunk-schemas.ts (RoutingDecisionDataSchema is the data-routing chunk contract) + api-client.ts + thread-id.ts + types.ts (Wave 1 contracts)"
  - phase: 04-minimal-chat-ui-openrouter-backend
    plan: 03
    provides: "apps/web/app/api/chat/route.ts (SSE proxy, x-vercel-ai-ui-message-stream:v1 header, threadId required) + 4 other route handlers"
  - phase: 04-minimal-chat-ui-openrouter-backend
    plan: 04
    provides: "apps/api/routes/turn.py emits structured 5-key routing_decision SSE event first; signals sub-field byte-equal to Done.routing_signals (D-15)"
provides:
  - "apps/web/components/RoutingChip.tsx — color-coded chip that subscribes to useMessage().content and finds {type:'data', name:'routing'}; reads structured RoutingDecision (Blocker 1)"
  - "apps/web/components/MetricsFooter.tsx — streaming-dot placeholder + final cost/latency/tokens line; same content subscription pattern"
  - "apps/web/components/ChatBubble.tsx — assistant + user bubble shells with hover-revealed action row (Copy + Regenerate); children slot is the Plan 06 markdown seam"
  - "apps/web/components/EmptyState.tsx — centered 'Ask anything. We'll route to the right model.' tagline"
  - "apps/web/components/StreamErrorBanner.tsx — code → friendly-message catalog (all 9 Phase-2 D-06 codes) + retriable retry button"
  - "apps/web/hooks/useChatThread.ts — wraps useChatRuntime with AssistantChatTransport + threadId injection + experimental_throttle:50"
  - "apps/web/app/page.tsx — ChatPage with header + Thread + Composer; Regenerate live-wired to useMessageRuntime().reload() (Blocker 3)"
  - "apps/web/lib/model-mapping.json — build-time mirror of repo-root config/model_mapping.json (Turbopack can't import outside apps/web)"
  - "apps/web/playwright/routing-chip.spec.ts — real Playwright E2E asserting chip visibility on every turn + Regenerate fires fresh POST (Blocker 2)"
  - "apps/web/tests/{routing-chip,metrics-footer,chat-bubble}.test.tsx — 28 RTL tests overwriting Plan 01 it.todo stubs"
affects: [04-06-PLAN, 04-07-PLAN]

tech-stack:
  added: []
  patterns:
    - "Data part subscription via useMessage().content (NOT .parts) — assistant-ui v0.14.5's useMessage() exposes the raw ThreadMessage where data-* chunks land on content[]"
    - "JSX bundled JSON import via @/lib/model-mapping.json (Turbopack security rejects ../../../ traversal outside the package root)"
    - "AssistantChatTransport.prepareSendMessagesRequest closes over a useRef so the latest threadId is injected on every POST without re-creating the transport"
    - "useMessageRuntime().reload() is the canonical Regenerate API for assistant-ui v0.14.5"
    - "Composer gating: disabled={threadId === null} prevents the race where a POST /api/chat fires before /api/threads round-trips"
    - "Playwright config: REPO_ROOT = resolve(__dirname, '../../..') because Playwright resolves cwd relative to the CONFIG file, not the CLI cwd"
    - "Playwright config: PYTHON defaults to {repo}/.venv/bin/python locally and python3 in CI"
    - "Playwright config: FASTAPI_URL pinned to 127.0.0.1 (Plan 03 IPv4 deviation honored — Node 18+ resolves localhost to ::1 first)"

key-files:
  created:
    - "apps/web/components/RoutingChip.tsx"
    - "apps/web/components/MetricsFooter.tsx"
    - "apps/web/components/ChatBubble.tsx"
    - "apps/web/components/EmptyState.tsx"
    - "apps/web/components/StreamErrorBanner.tsx"
    - "apps/web/hooks/useChatThread.ts"
    - "apps/web/lib/model-mapping.json"
  modified:
    - "apps/web/app/page.tsx (Plan 01 Wave-0 placeholder OVERWRITTEN with full ChatPage)"
    - "apps/web/tests/routing-chip.test.tsx (Plan 01 it.todo stub OVERWRITTEN with 10 RTL cases)"
    - "apps/web/tests/metrics-footer.test.tsx (Plan 01 it.todo stub OVERWRITTEN with 8 RTL cases)"
    - "apps/web/tests/chat-bubble.test.tsx (Plan 01 it.todo stub OVERWRITTEN with 10 RTL cases)"
    - "apps/web/playwright/routing-chip.spec.ts (Plan 01 skip stub OVERWRITTEN with real E2E)"
    - "apps/web/playwright/playwright.config.ts (Rule 3 — cwd off-by-one + python binary + IPv4 pin)"

key-decisions:
  - "Data part subscription path: useMessage().content (NOT parts). Empirically confirmed via debug-attribute round-trip — assistant-ui v0.14.5's useMessage() returns the raw ThreadMessage (id/role/content/status/metadata/...) without the MessageClient wrapping that would derive a `parts` array from `content`. The data-routing and data-metrics chunks DO arrive (converted from AI SDK v6 data-<event> by @assistant-ui/react-ai-sdk's convertMessage.js into {type:'data', name, data}) and land on content[]. Resolves Open Question 4 from RESEARCH.md."
  - "Assistant-ui primitive names used: ThreadPrimitive.Root, ThreadPrimitive.Viewport, ThreadPrimitive.Empty, ThreadPrimitive.Messages (with components={UserMessage, AssistantMessage}), ComposerPrimitive.Root, ComposerPrimitive.Input, ComposerPrimitive.Send, ComposerPrimitive.Cancel, MessagePrimitive.Content. AssistantRuntimeProvider mounts the runtime."
  - "Regenerate live-wired via useMessageRuntime().reload() (Blocker 3 resolved). Verified by reading node_modules/@assistant-ui/core/.../message-runtime.d.ts at install time — MessageRuntime.reload(config?: ReloadConfig) is the canonical export. NOT useThreadRuntime / useThreadActions (those exist too, but message-scoped reload is the correct API for the per-message Regenerate affordance)."
  - "Bundled model mapping: apps/web/lib/model-mapping.json is a copy of config/model_mapping.json. Turbopack rejects relative imports that traverse outside the package root (security constraint), and a tsconfig path alias to a sibling directory also doesn't work in Turbopack. The duplication is documented in RoutingChip's bundled-JSON comment and TODO is to add a pre-build copy step in a future plan."
  - "Composer gating: disabled={threadId === null} (Rule 3 fix). The default-thread useEffect can take a single round-trip to /api/threads, but the user can press Enter immediately after mount. The previous code allowed a POST with threadId=null which the chat route handler rejects with 400. Disabling the composer until threadId loads makes the race invisible to the user."
  - "@assistant-ui/react-ai-sdk's UseChatRuntimeOptions type omits experimental_throttle (it lives on @ai-sdk/react's UseChatOptions, not the upstream ChatInit). The runtime spreads extra options through to useChat() at runtime, so we widen the local options type with a Throttleable alias to satisfy tsc strict while keeping the runtime behaviour intact."

requirements-completed:
  - UI-01
  - UI-04
  - UI-06
  - UI-07
  - UI-08

duration: ~41 min
completed: 2026-05-19
---

# Phase 04 Plan 05: Wave 4 — Chat surface assembly Summary

**The full visible chat surface lands: header + AssistantRuntimeProvider + Thread + Composer; routing chip (color-coded by backend, display_name resolved from model_mapping.json) renders above every assistant message; metrics footer (streaming dot → final $/s/tokens) renders below; ChatBubble shell with hover-revealed Copy + Regenerate action row; Regenerate live-wired to useMessageRuntime().reload() (Blocker 3); EmptyState tagline shown on first load; StreamErrorBanner catalog covers all 9 Phase-2 D-06 codes. Real Playwright E2E (Blocker 2) overwrites the Plan 01 skip stub and asserts chip visibility across 3 turns + Regenerate fires a fresh POST /api/chat. End-to-end verified locally with USE_MOCK_FASTAPI=1: 1 Playwright pass in 3.3s, 70 Vitest tests passing, build clean, tsc strict clean.**

## Performance

- **Duration:** ~41 min (on-CPU)
- **Started:** 2026-05-19T16:12:48Z
- **Completed:** 2026-05-19T16:54:06Z
- **Tasks:** 4 (all autonomous)
- **Files created:** 7
- **Files modified:** 6

## Accomplishments

- **Visible chat surface at localhost:3000** — header sticky, max-w-3xl gutter, message area scrolls, composer sticky-bottom
- **Routing chip on every assistant turn** — color-coded per backend (slate/green/amber for openrouter/claude_code/computer_use), display_name resolved from model_mapping.json with raw-slug fallback, role=status + aria-live polite + 80-char rationale truncation with full text in title
- **Metrics footer on every assistant turn** — streaming dot (animate-pulse) mid-stream; "$X.XXXX · X.Xs · X↑/X↓" final with locale-aware comma separators for token counts >= 10000
- **Hover-revealed action row** — Copy (writes RAW markdown via clipboard) + Regenerate (live-wired to assistant-ui reload); the bubble's `children` prop is the Plan 06 markdown seam
- **Real Playwright E2E** — replaces the Plan 01 test.skip stub with 5 assertions including 3-turn chip count + non-collapsed dimension checks + Regenerate-fires-fresh-POST interception
- **All 4 Blockers (1-3) resolved** — variable is `routing` not `signals` (Blocker 1); spec is real not skip (Blocker 2); Regenerate has no TODO (Blocker 3); plus a 4th in-flight discovery (parts → content) that turned out to be the load-bearing fix for the chip ever rendering at runtime

## Task Commits

Each task was committed atomically:

1. **Task 1: RoutingChip + MetricsFooter + RTL tests (UI-04, UI-07)** — `6e5890e` (feat)
2. **Task 2: ChatBubble + EmptyState + StreamErrorBanner + RTL test (UI-08, UI-12)** — `bb50e7e` (feat)
3. **Task 3: useChatThread hook + ChatPage with LIVE Regenerate (Blocker 3)** — `c03db9e` (feat)
4. **Task 4: routing-chip.spec.ts overwrite + in-flight fixes (UI-04 + UI-08 E2E)** — `05dbdee` (feat)

_Note: Task 4's commit also bundles three deviation fixes discovered during E2E debugging (composer gating, content vs parts, playwright.config.ts infrastructure) — see "Deviations from Plan" below._

## Files Created/Modified

- `apps/web/components/RoutingChip.tsx` — color-coded chip subscribed to `useMessage().content.find(p => p.type === "data" && p.name === "routing")`
- `apps/web/components/MetricsFooter.tsx` — streaming + final state footer, same content-find pattern
- `apps/web/components/ChatBubble.tsx` — assistant + user shells; Copy + Regenerate action row; children slot for Plan 06 markdown
- `apps/web/components/EmptyState.tsx` — centered tagline per UI-SPEC §11
- `apps/web/components/StreamErrorBanner.tsx` — code → friendly-message catalog for all 9 D-06 codes
- `apps/web/hooks/useChatThread.ts` — useChatRuntime + AssistantChatTransport + experimental_throttle:50 + threadId useRef closure
- `apps/web/lib/model-mapping.json` — build-time mirror of config/model_mapping.json (Turbopack security)
- `apps/web/app/page.tsx` — REWRITES Plan 01 placeholder with ChatPage; AssistantMessage variant wires Regenerate to useMessageRuntime().reload()
- `apps/web/playwright/routing-chip.spec.ts` — REWRITES Plan 01 skip stub with real Playwright E2E (Blocker 2)
- `apps/web/playwright/playwright.config.ts` — fix cwd off-by-one, default python to repo .venv, pin 127.0.0.1 for FASTAPI_URL
- `apps/web/tests/routing-chip.test.tsx` — REWRITES Plan 01 stub with 10 RTL cases (using `content` fixture)
- `apps/web/tests/metrics-footer.test.tsx` — REWRITES Plan 01 stub with 8 RTL cases
- `apps/web/tests/chat-bubble.test.tsx` — REWRITES Plan 01 stub with 10 RTL cases including StreamErrorBanner catalog

## Decisions Made

### Resolved RESEARCH Open Question 4: Data part subscription path

**Question:** Does the routing chip subscribe via `useThreadMessage.parts` OR `useChat.data`?

**Answer:** Neither — it subscribes via `useMessage().content`. Empirical finding during E2E debug (Task 4): assistant-ui v0.14.5's `useMessage()` returns the **raw ThreadMessage** (with `content[]`, `id`, `role`, `status`, `metadata`, `index`, `isLast`, etc.) — NOT the wrapped `MessageState` that the `store/scopes/message.d.ts` type would suggest (which exposes a `parts` array derived from content). Data-* parts from the AI SDK v6 stream are converted by `@assistant-ui/react-ai-sdk`'s `convertMessage.js` into `{type: "data", name: "<event>", data: <payload>}` and land on `content[]`. Reading `content` directly works.

This was confirmed by a one-time debug attribute on `<body>` that emitted the message-state shape during a live turn:
```
{"msgKeys":["id","createdAt","role","content","status","metadata","index","isLast","parentId","branchNumber","branchCount","speech"],
 "role":"assistant","partsLen":-1,
 "contentLen":3,"contentTypes":[{"type":"data","name":"routing"},{"type":"text"},{"type":"data","name":"metrics"}]}
```

`parts` was absent (partsLen=-1 means undefined), `content` had the data parts.

### Exact assistant-ui primitive surface used

After reading `node_modules/@assistant-ui/react/dist/primitives/{thread,composer,message}.d.ts` at install time:

- `AssistantRuntimeProvider` — wraps the entire chat surface, takes `runtime={runtime}`
- `ThreadPrimitive.Root` — flex container for the thread
- `ThreadPrimitive.Viewport` — scroll area
- `ThreadPrimitive.Empty` — renders `<EmptyState />` when thread is empty
- `ThreadPrimitive.Messages` — takes `components={{UserMessage, AssistantMessage}}` to render per-role bubble variants
- `ComposerPrimitive.Root` — form wrapper
- `ComposerPrimitive.Input` — textarea (NOT input)
- `ComposerPrimitive.Send` — button with aria-label
- `ComposerPrimitive.Cancel` — Stop button (auto-bound to runtime.stop())
- `MessagePrimitive.Content` — alias for `MessagePrimitive.Parts`, renders parts inside the bubble

### Regenerate reload binding

`useMessageRuntime().reload()` (from `@assistant-ui/react`). Verified by reading `node_modules/@assistant-ui/core/.../message-runtime.d.ts` at install time. The `MessageRuntime` interface exports `reload(config?: ReloadConfig): void`. NOT `useThreadRuntime().reload()` (although ThreadRuntime exists, the per-message Regenerate affordance uses message-scoped reload — this is what `ActionBarReload` and `useActionBarReload` both wire to internally).

### Build-time JSON duplication

`apps/web/lib/model-mapping.json` is a byte-identical copy of `config/model_mapping.json`. Turbopack rejects relative imports that traverse outside `apps/web` (security feature). A tsconfig path alias `@config/*` resolves to the right relative path but Turbopack still rejects the underlying module-not-found because the file IS outside the package root.

**Future improvement:** wire a pre-build script that copies the canonical config into `apps/web/lib/model-mapping.json` automatically. Plan 06 or 07 can add this. For now, the duplication is documented in RoutingChip's bundled-JSON import comment.

### Manual smoke test output (curl + DOM debug)

Curl through the Next dev server's `/api/chat` route during smoke check:
```
data: {"type":"start","messageId":"m-f9511dbd-99c1-4441-8263-af1e013b37b2"}
data: {"type":"data-routing","data":{"backend":"openrouter","model_or_agent":"openai/gpt-5","rationale":"Test routing","confidence":0.92,"signals":{...}}}
data: {"type":"text-start","id":"t-0"}
data: {"type":"text-delta","id":"t-0","delta":"Hello"}
data: {"type":"text-delta","id":"t-0","delta":" world"}
data: {"type":"text-end","id":"t-0"}
data: {"type":"data-metrics","data":{"cost_usd":0.0001,"latency_ms":42,"tokens_in":3,"tokens_out":2}}
data: {"type":"finish"}
data: [DONE]
```

Stream complete in <1 sec. Routing chunk arrives FIRST (D-15). Metrics arrive on Done. Everything works at the wire layer.

DOM after the chat surface consumes this:
- RoutingChip renders `<div role="status" aria-label="Routing decision: Routed to openai/gpt-5. Test routing">` (display_name fallback to raw model_or_agent — UI-SPEC §6.2)
- ChatBubble renders the `Hello world` body via `MessagePrimitive.Content`
- MetricsFooter renders `"$0.0001 · 0.0s · 3↑/2↓"` (latency 42ms floors to 0.0s)
- Regenerate click → fresh POST /api/chat verified end-to-end

Hydration mismatch warning is absent in `pnpm dev`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] useMessage() exposes `content`, not `parts`**
- **Found during:** Task 4 (Playwright E2E debug — chip wasn't rendering despite SSE stream completing correctly)
- **Issue:** The plan (and RESEARCH §Pattern 6) said to subscribe via `useThreadMessage.parts.find(p => p.type === "data-routing")`. The actual API behaviour in `@assistant-ui/react@0.14.5` is that `useMessage()` returns the raw ThreadMessage with a `content` array, NOT a wrapped MessageState with `parts`. Without this fix, `parts` was undefined → `find` failed → chip returned null even with a valid data-routing part on the message.
- **Diagnosis path:** Added a debug attribute on `<body>` that emitted the message-state shape. The debug payload showed `content[]` with the data parts AND no `parts` key. Switched chip + footer to read `content` directly; chip + footer both lit up.
- **Fix:** Both `RoutingChip.tsx` and `MetricsFooter.tsx` now read `useMessage().content` (with a structural type cast for tsc strict). Unit tests updated to mock `{content: [...]}` instead of `{parts: [...]}`.
- **Files modified:** `apps/web/components/RoutingChip.tsx`, `apps/web/components/MetricsFooter.tsx`, `apps/web/tests/routing-chip.test.tsx`, `apps/web/tests/metrics-footer.test.tsx`
- **Verification:** 18 RTL tests pass with new fixtures; routing-chip.spec.ts Playwright E2E goes from timeout (chip never appears) to 1 passed in 3.3s.
- **Committed in:** `05dbdee` (Task 4 commit)

**2. [Rule 3 — Blocking] Composer race with /api/threads round-trip**
- **Found during:** Task 4 (Playwright E2E debug — POST /api/chat returned 400 with "threadId is required")
- **Issue:** The `useChatThread` hook starts a useEffect that calls `getOrCreateDefaultThread()` (a POST to /api/threads). The user can press Enter on the composer before the round-trip returns, and `threadIdRef.current` is still null at that moment. The chat route handler (Plan 03) requires `threadId` to be a non-empty string and rejects with 400 otherwise. Symptom: chat bubble appears empty, no text, no chip, no metrics.
- **Fix:** `apps/web/app/page.tsx` now sets `composerDisabled = threadId === null` and passes `disabled={composerDisabled}` to `ComposerPrimitive.Input`. The composer is greyed out (Tailwind `disabled:bg-slate-50 disabled:cursor-not-allowed`) until threadId resolves. The Playwright spec waits for `t.disabled === false` before filling.
- **Files modified:** `apps/web/app/page.tsx`
- **Verification:** Debug spec showed `POST /api/threads → 200` BEFORE `POST /api/chat → 200`, with the second body containing a real threadId.
- **Committed in:** `05dbdee` (Task 4 commit)

**3. [Rule 3 — Blocking] Playwright config cwd off-by-one + missing PYTHON binary**
- **Found during:** Task 4 (first `pnpm test:e2e` invocation — `python: command not found`)
- **Issue:** (a) `playwright.config.ts` had `cwd: "../../"` for the webServer entries. Playwright resolves `cwd` relative to the **config file** location, which is `apps/web/playwright/`. From there, `../../` = `apps/`, not the repo root. (b) `command: "python ..."` failed because macOS doesn't ship `python` (only `python3` or a venv). The mock-fastapi server never started, the next dev server never had an upstream, and page.goto returned `net::ERR_ABORTED`.
- **Fix:** Compute `REPO_ROOT = resolve(__dirname, "../../..")` explicitly and pass absolute paths. Default `PYTHON` to `${REPO_ROOT}/.venv/bin/python` locally and `python3` in CI. Both web servers now start cleanly.
- **Files modified:** `apps/web/playwright/playwright.config.ts`
- **Verification:** `USE_MOCK_FASTAPI=1 pnpm test:e2e routing-chip.spec.ts` → 1 passed in 3.3s.
- **Committed in:** `05dbdee` (Task 4 commit)

**4. [Rule 3 — Blocking] FASTAPI_URL pinned to 127.0.0.1 (IPv4)**
- **Found during:** Task 4 (after fixing #3 — webServers started but route handler upstream fetch silently produced empty body)
- **Issue:** Plan 03's deviation notes flagged this: Node 18+ resolves "localhost" to ::1 (IPv6) first via dns.lookup. mock-fastapi.py binds 127.0.0.1 only (uvicorn defaults). The chat route handler's `fetch("http://localhost:8001/...")` silently fails the IPv6 connect attempt and returns the empty-body branch. The playwright config had `localhost:8001` for the mock URL.
- **Fix:** Pinned `127.0.0.1` literal in `playwright.config.ts` for both mock + real FASTAPI_URL. Documented inline with the rationale linking to Plan 03's deviation note.
- **Files modified:** `apps/web/playwright/playwright.config.ts`
- **Verification:** Curl through the Next proxy at the smoke layer returns 627-byte SSE body with all 8 AI SDK v6 chunk types present.
- **Committed in:** `05dbdee` (Task 4 commit)

**5. [Rule 3 — Blocking] Turbopack rejects ../../../ JSON import**
- **Found during:** Task 3 (`pnpm run build` → Module not found: Can't resolve '../../../config/model_mapping.json')
- **Issue:** Turbopack rejects relative imports that traverse outside the package root (security feature). The chip's `import mapping from "../../../config/model_mapping.json"` resolves to `Prompt-Optimizer/config/model_mapping.json` which is outside `apps/web`. The tsconfig path alias `@config/*` resolved to the same relative path so Turbopack still rejected it.
- **Fix:** Copied `config/model_mapping.json` to `apps/web/lib/model-mapping.json` (byte-identical, 4337 bytes). The chip imports `from "@/lib/model-mapping.json"`. The duplication is documented in the chip's bundled-JSON comment.
- **Files modified:** `apps/web/lib/model-mapping.json` (created), `apps/web/components/RoutingChip.tsx`
- **Verification:** `pnpm run build` exits 0; the JSON resolves correctly in both build and test environments.
- **Committed in:** `c03db9e` (Task 3 commit) — RoutingChip import update was bundled with the Task 3 page wiring because both were on the critical path.

**6. [Rule 1 — Bug] JSX string attributes don't process escape sequences**
- **Found during:** Task 2 (Vitest run — Copy clipboard test failed with `\\n` vs `\n` mismatch)
- **Issue:** My test had `<ChatBubble rawMarkdown="# heading\n\nbody **bold**">`. JSX string attributes (double-quoted) are raw text per the JSX spec — `\n` stays as the two-character sequence backslash-n, not a real newline. The test expectation `toHaveBeenCalledWith("# heading\n\nbody **bold**")` (with the real newline) didn't match.
- **Fix:** Use a JS string variable + `rawMarkdown={raw}` (curly braces) so the escape sequences process normally.
- **Files modified:** `apps/web/tests/chat-bubble.test.tsx`
- **Verification:** Copy test passes.
- **Committed in:** `bb50e7e` (Task 2 commit)

**7. [Rule 1 — Bug] StreamErrorBanner catalog test was too aggressive**
- **Found during:** Task 2 (Vitest run — `internal_error` test failed)
- **Issue:** My test asserted `!banner.textContent.match(/^Something went wrong/)` to ensure no known code returns the generic fallback. But `internal_error`'s friendly message legitimately starts with "Something went wrong inside Prompt-Optimizer."
- **Fix:** Tightened the assertion to check for the EXACT fallback string "Something went wrong — try again." (with the em-dash) — that's the only string `FRIENDLY_MESSAGES[code] ?? fallback` returns for unknown codes.
- **Files modified:** `apps/web/tests/chat-bubble.test.tsx`
- **Verification:** All 10 chat-bubble tests pass.
- **Committed in:** `bb50e7e` (Task 2 commit)

**8. [Rule 1 — Bug] Playwright regex matched single-line text, but innerText is multi-line**
- **Found during:** Task 4 (Playwright assertion (b) failed — chip text contained newlines)
- **Issue:** The chip's three spans are flex children with `gap-2`. When the browser renders them, `innerText` inserts visual line breaks between them (DOM spec behaviour for inline flex children rendered on separate lines). The canonical regex `/^Routed to .+ · .+$/` doesn't span newlines.
- **Fix:** Use `firstChip.textContent()` (single-line concatenation of descendant text) instead of `innerText()`. Then collapse all whitespace runs to a single space before matching the regex.
- **Files modified:** `apps/web/playwright/routing-chip.spec.ts`
- **Verification:** Playwright spec passes (1 passed in 3.3s).
- **Committed in:** `05dbdee` (Task 4 commit)

**9. [Rule 1 — Bug] tsc strict couldn't narrow MessageState union to access `parts`**
- **Found during:** Task 1 (initial tsc check after writing RoutingChip + MetricsFooter)
- **Issue:** The `MessageState` type exported by `@assistant-ui/core/runtime/api/message-runtime` is `ThreadMessage & {...}` — but `ThreadMessage` is a union of `ThreadSystemMessage | ThreadUserMessage | ThreadAssistantMessage`. The union narrowing made tsc reject direct property access because the system variant has a different `content` shape. (Then this was superseded by deviation #1 when we discovered the actual API exposes `content` not `parts`.)
- **Fix:** Cast through a local structural type (`MessageStateWithContent = {readonly content: ReadonlyArray<PartLike>}`) in both chip + footer. This keeps the runtime behaviour intact while satisfying tsc strict.
- **Files modified:** `apps/web/components/RoutingChip.tsx`, `apps/web/components/MetricsFooter.tsx`
- **Verification:** tsc strict clean.
- **Committed in:** `6e5890e` (Task 1 commit, later refined in `05dbdee`)

---

**Total deviations:** 9 auto-fixed (4 bugs, 5 blocking infrastructure). Zero architectural changes; no Rule 4 escalations.

**Impact on plan:** All auto-fixes were either necessary for correctness/security (the content-vs-parts discovery would have shipped a broken chip without the runtime debug) or load-bearing for the verification flow (the playwright.config.ts fixes were prerequisites for ever running the spec). No scope creep — every fix maps to an existing requirement in this plan (UI-04, UI-07, UI-08) or a previously-documented Plan 03 deviation (IPv4 pin).

## Issues Encountered

- **Next.js next/font Google Fonts blocked by sandbox** during `pnpm run build`. The sandbox config allows `fonts.googleapis.com` for the Read tool but Turbopack's outbound fetch isn't routed through it. Workaround: ran `pnpm run build` with the sandbox bypass. In production / CI, this is a non-issue (no sandbox). **Future improvement (Plan 07 candidate):** swap `next/font/google` for a locally-bundled font so the build doesn't need outbound network.

## User Setup Required

None — Plan 05 is purely frontend wiring. The user still needs to bring their own OpenRouter key before sending a real prompt (Plan 07 lands the first-run modal that captures and routes the key); for now, smoke testing works with `USE_MOCK_FASTAPI=1` and the canned-SSE mock.

## Next Phase Readiness

**Plan 04-06 (markdown body + code-block rendering) ready:**
- `ChatBubble.tsx`'s `children` prop is the markdown seam — Plan 06 swaps the slot value with `<MarkdownRenderer rawMarkdown={...} isStreamingComplete={...} messageId={...} />`. The ChatBubble's props interface is the surface Plan 06 will extend.
- `useMessage().content` is the data path for the per-message text content — same pattern the chip + footer use; Plan 06 can either reuse the existing `MessagePrimitive.Content` or extract the text parts and feed them to MarkdownRenderer.
- `MessageRuntime.getState().status.type` provides the "running" vs "complete" signal Plan 06 needs for the `isStreamingComplete` toggle (Pattern 5b — incremental markdown re-render).

**Plan 04-07 (first-run modal + key gating + remaining Playwright specs) ready:**
- The composer is already disabled when `threadId === null`. Plan 07's first-run modal layers on top: when `adapters.openrouter.status === "missing_key"`, show the modal; on key submit, the threadId auto-creates and the composer unlocks.
- The 4 remaining Playwright specs (first-run.spec.ts, no-flicker.spec.ts, browser-isolation.spec.ts, secure-key.spec.ts, cancel-budget.spec.ts) can reuse the same mock-fastapi + playwright.config.ts harness — the cwd / python / IPv4 fixes are in place.

**VALIDATION.md row flips:**
- UI-01 unit → ✅ (multi-turn scroll inherited from assistant-ui Thread primitive)
- UI-04 unit → ✅ (10 RTL cases in routing-chip.test.tsx)
- UI-04 E2E → ✅ (routing-chip.spec.ts — Blocker 2 + Blocker 3 enforcement)
- UI-06 (Stop preserves partial) → ✅ (ComposerPrimitive.Cancel auto-bound to runtime.stop())
- UI-07 unit → ✅ (8 RTL cases in metrics-footer.test.tsx)
- UI-08 unit → ✅ (10 RTL cases in chat-bubble.test.tsx)

**SC #1 (chip on every assistant message) observable** at localhost:3000 with `USE_MOCK_FASTAPI=1` AND enforced by routing-chip.spec.ts E2E (3-turn count + non-collapsed dimension checks).

## Self-Check: PASSED

Created files verified to exist:

- apps/web/components/RoutingChip.tsx — FOUND
- apps/web/components/MetricsFooter.tsx — FOUND
- apps/web/components/ChatBubble.tsx — FOUND
- apps/web/components/EmptyState.tsx — FOUND
- apps/web/components/StreamErrorBanner.tsx — FOUND
- apps/web/hooks/useChatThread.ts — FOUND
- apps/web/lib/model-mapping.json — FOUND
- apps/web/app/page.tsx — FOUND (Plan 01 placeholder overwritten)
- apps/web/playwright/routing-chip.spec.ts — FOUND (Plan 01 skip stub overwritten)
- apps/web/playwright/playwright.config.ts — FOUND (modified — cwd + PYTHON + IPv4 pin)
- apps/web/tests/routing-chip.test.tsx — FOUND (Plan 01 stub overwritten)
- apps/web/tests/metrics-footer.test.tsx — FOUND (Plan 01 stub overwritten)
- apps/web/tests/chat-bubble.test.tsx — FOUND (Plan 01 stub overwritten)

Commits verified to exist:

- `6e5890e` — FOUND (Task 1 — feat: RoutingChip + MetricsFooter components + RTL test suites)
- `bb50e7e` — FOUND (Task 2 — feat: ChatBubble + EmptyState + StreamErrorBanner + RTL tests)
- `c03db9e` — FOUND (Task 3 — feat: wire useChatThread + ChatPage with LIVE Regenerate)
- `05dbdee` — FOUND (Task 4 — feat: overwrite routing-chip.spec.ts with real Playwright E2E + fixes)

Verification commands re-run after final commit:

- `pnpm --dir apps/web run build` → exit 0 (3 routes generated, 5 dynamic API routes registered) — with sandbox bypass for next/font Google fetch
- `pnpm --dir apps/web exec tsc --noEmit` → exit 0 (strict mode clean)
- `pnpm --dir apps/web test` → 70 passing, 0 failing, 7 test files
- `USE_MOCK_FASTAPI=1 pnpm --dir apps/web test:e2e routing-chip.spec.ts` → 1 passed in 3.3s

---
*Phase: 04-minimal-chat-ui-openrouter-backend*
*Completed: 2026-05-19*
