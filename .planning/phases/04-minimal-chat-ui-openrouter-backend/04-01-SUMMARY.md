---
phase: 04-minimal-chat-ui-openrouter-backend
plan: 01
subsystem: ui
tags: [next.js, react, tailwind, shadcn, ai-sdk, assistant-ui, shiki, vitest, playwright, typescript, pnpm]

requires:
  - phase: 03-fastapi-service-persistent-storage
    provides: "FastAPI namespace + ChatChunk wire + healthz/settings/threads/turn endpoints that the Wave 2 proxies forward to"
provides:
  - "apps/web/ Next.js 16 + React 19.2 + AI SDK v6 + assistant-ui workspace bootstrapped from greenfield"
  - "shadcn/ui new-york nova preset with baseColor=slate and ONLY the 4 UI-SPEC §18 components: button, dialog, input, sonner"
  - "Vitest 4.1 + Playwright 1.60 + RTL test harness wired into apps/web/ with mock-fastapi.py CI fixture"
  - "11 test-stub files (5 Vitest, 6 Playwright) mapping byte-for-byte to the VALIDATION.md Per-Task Verification Map"
  - "Pattern 5 vs Pattern 5b verdict pinned in apps/web/lib/MARKDOWN-DECISION.md so Plan 06 has a binding decision file"
  - "/api/health Wave-0 placeholder establishing the runtime='nodejs' + dynamic='force-dynamic' pattern (PATTERNS Pattern C)"
  - ".github/workflows/web-test.yml running Vitest + Playwright (USE_MOCK_FASTAPI=1, no OpenRouter key required in CI)"
  - "ReadMe.md two-terminal 'Running the chat UI' block per CONTEXT specifics"
affects: [04-02-PLAN, 04-03-PLAN, 04-04-PLAN, 04-05-PLAN, 04-06-PLAN, 04-07-PLAN]

tech-stack:
  added:
    - "next@16.2.6"
    - "react@19.2.4 + react-dom@19.2.4"
    - "typescript@^5.9.3"
    - "tailwindcss@4.3.0 + @tailwindcss/postcss@4.3.0"
    - "ai@^6.0.184 (AI SDK v6 core — UI Message Stream Protocol)"
    - "@ai-sdk/react@^3.0.186 (useChat hook)"
    - "@assistant-ui/react@^0.14.5 (Thread/Composer/MessagePrimitive)"
    - "@assistant-ui/react-ai-sdk@^1.3.26 (useChatRuntime adapter)"
    - "@assistant-ui/react-markdown@^0.14.0 (markdown wrapper with built-in fence-state detection)"
    - "shiki@^4.0.2 (Plan 06 wires it as the SyntaxHighlighter component)"
    - "zod@^4.4.3 (boundary validation in Plan 02 lib/chunk-schemas.ts)"
    - "lucide-react@^1.16.0 + clsx@^2.1.1 + tailwind-merge@^3.6.0 + class-variance-authority@^0.7.1"
    - "shadcn registry components: button, dialog, input, sonner (UI-SPEC §18)"
    - "vitest@^4.1.6 + @vitejs/plugin-react + jsdom@^29.1.1"
    - "@testing-library/react@^16.3.2 + @testing-library/jest-dom@^6.9.1"
    - "@playwright/test@^1.60.0 (Chromium 148.0.7778.96 installed)"
  patterns:
    - "PATTERNS Pattern C — route handlers declare runtime='nodejs' + dynamic='force-dynamic' from the very first handler"
    - "PATTERNS Pattern D — every component file starts with \"use client\" except app/layout.tsx (server)"
    - "PATTERNS Pattern E — cn() helper composes clsx + tailwind-merge; lib/utils.ts re-exports for shadcn compatibility"
    - "Multi-server Playwright webServer config gated by USE_MOCK_FASTAPI env (RESEARCH Example 3)"
    - "Test-stub convention: every it.todo/test.skip name leads with the requirement ID + a one-line behavior"

key-files:
  created:
    - "apps/web/package.json"
    - "apps/web/pnpm-lock.yaml"
    - "apps/web/tsconfig.json"
    - "apps/web/next.config.ts"
    - "apps/web/postcss.config.mjs"
    - "apps/web/components.json"
    - "apps/web/pnpm-workspace.yaml"
    - "apps/web/.env.example"
    - "apps/web/.gitignore"
    - "apps/web/app/layout.tsx"
    - "apps/web/app/page.tsx"
    - "apps/web/app/globals.css"
    - "apps/web/app/api/health/route.ts"
    - "apps/web/components/ui/button.tsx"
    - "apps/web/components/ui/dialog.tsx"
    - "apps/web/components/ui/input.tsx"
    - "apps/web/components/ui/sonner.tsx"
    - "apps/web/lib/cn.ts"
    - "apps/web/lib/utils.ts"
    - "apps/web/lib/MARKDOWN-DECISION.md"
    - "apps/web/vitest.config.ts"
    - "apps/web/playwright/playwright.config.ts"
    - "apps/web/playwright/mock-fastapi.py"
    - "apps/web/tests/setup.ts"
    - "apps/web/tests/sse-translate.test.ts"
    - "apps/web/tests/chunk-schemas.test.ts"
    - "apps/web/tests/routing-chip.test.tsx"
    - "apps/web/tests/metrics-footer.test.tsx"
    - "apps/web/tests/chat-bubble.test.tsx"
    - "apps/web/playwright/no-flicker.spec.ts"
    - "apps/web/playwright/cancel-budget.spec.ts"
    - "apps/web/playwright/first-run.spec.ts"
    - "apps/web/playwright/secure-key.spec.ts"
    - "apps/web/playwright/browser-isolation.spec.ts"
    - "apps/web/playwright/routing-chip.spec.ts"
    - ".github/workflows/web-test.yml"
  modified:
    - ".gitignore"
    - "ReadMe.md"

key-decisions:
  - "Adopted RESEARCH Critical Finding #1 stack: Next 16.2.6 / React 19.2.4 / AI SDK v6.0.184 / @assistant-ui/react 0.14.5 (CONTEXT D-06/D-07 pins were stale floors; latest npm + assistant-ui-with-ai-sdk-v6 example are the canonical reference)."
  - "Plan 06 will use Pattern 5 (built-in primitive) — @assistant-ui/react-markdown 0.14 already has three-mechanism fence-state detection (react-markdown tokenizer + DefaultCodeBlock language gate + React.memo on CodeOverride/PreOverride). Pattern 5b (custom StreamingCodeBlock) NOT needed."
  - "shadcn CLI new-york nova preset accepted (Lucide + Geist match our lucide-react + Geist font choices). baseColor manually patched to slate in components.json (UI-SPEC §1)."
  - "lib/utils.ts re-exports cn from lib/cn.ts so the unedited shadcn registry components (UI-SPEC §18 — components must not be hand-edited) compile against @/lib/utils while the plan-specified lib/cn.ts is the canonical implementation (PATTERNS Pattern E)."
  - "Playwright config has TWO webServer modes: default uvicorn:8000 (local dev) and USE_MOCK_FASTAPI=1 mock-fastapi.py:8001 (CI). FASTAPI_URL is set on the Next dev server command so route handlers talk to the right port without env-var leakage to the browser."
  - "/api/health Wave-0 placeholder returns missing_key so Plan 07 first-run modal trigger logic has a deterministic exercise path (Plan 04-03 overwrites with the real passthrough)."

patterns-established:
  - "Greenfield JS workspace at apps/web/ — mirrors apps/api/ siblinghood (CONTEXT D-01)"
  - "All Next route handlers declare runtime='nodejs' + dynamic='force-dynamic' (Critical Finding #3)"
  - "All component files prefixed with \"use client\" except layout.tsx (Pitfall 8)"
  - "Dynamic className via cn() helper — no raw template strings"
  - "Test stubs ship with VALIDATION.md row + requirement ID embedded in the test name"
  - "Server-only FASTAPI_URL env (no NEXT_PUBLIC_ leak) — UI-17 invariant established from day one"
  - "D-05 belt-and-suspenders gitignore — .env.local is excluded by BOTH root .gitignore AND apps/web/.gitignore explicit rules; .env.example un-ignored via `!.env.example`"

requirements-completed: [UI-01]

duration: ~13 min
completed: 2026-05-19
---

# Phase 04 Plan 01: Wave 0 — Toolchain Bootstrap Summary

**Next 16 + React 19.2 + AI SDK v6 + assistant-ui 0.14 workspace at apps/web/ with shadcn-button/dialog/input/sonner, Vitest+Playwright+RTL harness, 11 VALIDATION-mapped test stubs, Wave-0 Pattern 5 spike verdict, and CI workflow that runs the full suite with a mock-FastAPI fixture so no OpenRouter key is needed in CI.**

## Performance

- **Duration:** ~13 min (on-CPU)
- **Started:** 2026-05-19T06:37:00Z (approx — first scaffolding command)
- **Completed:** 2026-05-19T06:50:18Z
- **Tasks:** 3
- **Files created:** 36 (apps/web/ entire workspace + 1 root config + 1 workflow)
- **Files modified:** 2 (root .gitignore, ReadMe.md)

## Accomplishments

- **Workspace scaffolded green:** `pnpm --dir apps/web install --frozen-lockfile` + `pnpm run build` both exit 0; Next 16's static + dynamic route discovery shows `/` (static) and `/api/health` (dynamic) in the route tree.
- **Standard Stack pinned to current majors:** every dependency in apps/web/package.json matches RESEARCH Critical Finding #1 (next 16.2.6, react 19.2.4, ai 6.0.184, @ai-sdk/react 3.0.186, @assistant-ui/react 0.14.5, @assistant-ui/react-ai-sdk 1.3.26, @assistant-ui/react-markdown 0.14.0, shiki 4.0.2, zod 4.4.3, tailwindcss 4.3.0, vitest 4.1.6, @playwright/test 1.60.0).
- **shadcn UI-SPEC §18 registry-safety verified:** components/ui/ contains ONLY button, dialog, input, sonner — no extras. nova preset (Lucide + Geist) chosen as the closest match to our lucide-react + Geist font setup. baseColor=slate per UI-SPEC §1.
- **Test harness green from day one:** `pnpm --dir apps/web test` reports `Tests 32 todo (32)` / `Test Files 5 skipped (5)` / exit 0; `pnpm --dir apps/web test:e2e --list` reports `Total: 6 tests in 6 files` / exit 0. Every later Plan 04-02..04-07 can reference these paths in its acceptance criteria.
- **Pattern 5 vs Pattern 5b spike resolved:** apps/web/lib/MARKDOWN-DECISION.md records the three-mechanism chain that already ships in @assistant-ui/react-markdown 0.14 (react-markdown tokenizer + DefaultCodeBlock language gate + React.memo on CodeOverride/PreOverride). Plan 06 uses Pattern 5; Pattern 5b NOT needed.
- **CI workflow live:** `.github/workflows/web-test.yml` runs Vitest then Playwright with `USE_MOCK_FASTAPI=1` so no OPENROUTER_API_KEY is ever required (threat T-04-03 mitigation). pnpm cache + uv cache wired.

## Task Commits

Each task was committed atomically:

1. **Task 1: Scaffold apps/web/ Next 16 workspace + install dependency set + commit Wave-0 build artifacts** — `85522cf` (feat)
2. **Task 2: Install Vitest + Playwright + RTL; write all test-framework configs; create Wave-0 test stubs + mock-FastAPI** — `367df1f` (test)
3. **Task 3: Wave-0 spike — verify @assistant-ui/react-markdown code-block primitive fence-state behavior + author MARKDOWN-DECISION.md + author placeholder /api/health route + commit CI workflow** — `5565e57` (feat)

## Resolved Versions (every Standard Stack package — actual pinned values)

| Package | Pin | Latest available |
|---------|-----|------------------|
| next | 16.2.6 | 16.2.6 ✓ |
| react | 19.2.4 | 19.2.6 (`pnpm add` resolved 19.2.4 from create-next-app default) |
| react-dom | 19.2.4 | 19.2.6 |
| typescript | ^5.9.3 | 5.9.3 ✓ (recommend stable 5.x per RESEARCH) |
| tailwindcss | ^4.3.0 | 4.3.0 ✓ |
| @tailwindcss/postcss | ^4.3.0 | 4.3.0 ✓ |
| ai | ^6.0.184 | 6.0.185 (resolved 6.0.184 — within ^6.0.175 floor from plan) |
| @ai-sdk/react | ^3.0.186 | 3.0.187 (resolved 3.0.186 — within ^3 floor from plan) |
| @assistant-ui/react | ^0.14.5 | 0.14.5 ✓ |
| @assistant-ui/react-ai-sdk | ^1.3.26 | 1.3.26 ✓ |
| @assistant-ui/react-markdown | ^0.14.0 | 0.14.0 ✓ |
| shiki | ^4.0.2 | 4.0.2 ✓ |
| zod | ^4.4.3 | 4.4.3 ✓ |
| lucide-react | ^1.16.0 | 1.16.0 ✓ |
| clsx | ^2.1.1 | 2.1.1 ✓ |
| tailwind-merge | ^3.6.0 | 3.6.0 ✓ |
| class-variance-authority | ^0.7.1 | 0.7.1 ✓ |
| vitest | ^4.1.6 | 4.1.6 ✓ |
| @playwright/test | ^1.60.0 | 1.60.0 ✓ |
| @vitejs/plugin-react | ^6.0.2 | 6.0.2 ✓ |
| jsdom | ^29.1.1 | 29.1.1 ✓ |
| @testing-library/react | ^16.3.2 | 16.3.2 ✓ |
| @testing-library/jest-dom | ^6.9.1 | 6.9.1 ✓ |

No peer-dep conflicts forced a downgrade.

## Wave-0 Spike Outcome (apps/web/lib/MARKDOWN-DECISION.md)

**Verdict:** Plan 06 uses **Pattern 5** (built-in primitive — `CodeOverride` + `PreOverride` + `DefaultCodeBlock`). Pattern 5b (custom `StreamingCodeBlock`) NOT needed.

Spike file path for Plan 06 to read: `apps/web/lib/MARKDOWN-DECISION.md`

The three-mechanism chain (already shipped by @assistant-ui/react-markdown 0.14):
1. react-markdown only emits `<pre><code class="language-X">` on fence close (partial fences render as unclassed `<code>` — no language → no shiki call).
2. `DefaultCodeBlock` selects `SyntaxHighlighter` (user-injected, will be shiki in Plan 06) only when `language` is non-empty.
3. Both `CodeOverride` and `PreOverride` are `React.memo`-wrapped with `memoCompareNodes` — post-close stream ticks hit the memo cache, no re-highlight.

Plan 06's only job: author `apps/web/lib/markdown-components.tsx` with a memoized `SyntaxHighlighter` calling `shiki.codeToHtml({lang, theme: 'github-light'})`. Pass that component via `<MarkdownTextPrimitive components={{ SyntaxHighlighter }} />`. Done.

## Test-Stub Count

| Surface | Count | Path prefix |
|---------|-------|-------------|
| Vitest unit/component stubs | **5 files / 32 it.todo** | `apps/web/tests/*.test.{ts,tsx}` |
| Playwright E2E stubs | **6 files / 6 test.skip** | `apps/web/playwright/*.spec.ts` |
| **Total** | **11 files** (target: 11 ✓) | |

Each stub's `it.todo` / `test.skip` name leads with the VALIDATION.md row's requirement ID (e.g. `D-07:`, `UI-04 E2E:`, `D-18 belt:`) and a verbatim one-line restatement of the row's "Behavior" column.

## Exact Command Sequence That Produced a Green Local + CI Run

```bash
# Local (executed during this plan)
pnpm create next-app@latest apps/web --typescript --tailwind --app --src-dir=false --use-pnpm --import-alias '@/*' --no-eslint --skip-install --turbopack=false --yes
cd apps/web
pnpm add ai@^6.0.175 @ai-sdk/react@^3 @assistant-ui/react@^0.14.5 @assistant-ui/react-ai-sdk@^1.3.26 @assistant-ui/react-markdown@^0.14.0 shiki@^4 zod@^4 lucide-react clsx tailwind-merge class-variance-authority
pnpm dlx shadcn@latest init --template next --base radix --preset nova --yes --force --no-monorepo
# (manual patch components.json: baseColor → slate)
pnpm add tw-animate-css next-themes sonner @radix-ui/react-dialog @radix-ui/react-slot
pnpm dlx shadcn@latest add button dialog input sonner --yes --overwrite
pnpm add -D vitest@^4.1 @vitejs/plugin-react jsdom @testing-library/react @testing-library/jest-dom @playwright/test@^1.60
pnpm exec playwright install chromium
pnpm install --frozen-lockfile && pnpm run build && pnpm test && pnpm test:e2e --list

# CI (.github/workflows/web-test.yml; runs USE_MOCK_FASTAPI=1)
uv sync --locked
pnpm --dir apps/web install --frozen-lockfile
pnpm --dir apps/web exec playwright install --with-deps chromium
pnpm --dir apps/web test
USE_MOCK_FASTAPI=1 pnpm --dir apps/web test:e2e
```

## Files Created/Modified

**Created (36):**
- `apps/web/package.json` — dep manifest with every Standard Stack pin
- `apps/web/pnpm-lock.yaml` — frozen lockfile for `--frozen-lockfile` in CI
- `apps/web/pnpm-workspace.yaml` — declares ignoredBuiltDependencies (sharp, unrs-resolver) — scaffolder artifact
- `apps/web/tsconfig.json` — strict TS; `@` alias points at apps/web/
- `apps/web/next.config.ts` — Next 16 default (empty config)
- `apps/web/postcss.config.mjs` — @tailwindcss/postcss plugin
- `apps/web/components.json` — shadcn config, baseColor patched to slate
- `apps/web/.env.example` — `FASTAPI_URL=http://localhost:8000` (un-ignored via `!.env.example`)
- `apps/web/.gitignore` — Next scaffold gitignore + D-05 belt-and-suspenders `.env.local` rule
- `apps/web/app/layout.tsx` — server component, mounts `<Toaster />`, Geist fonts, UI-SPEC §16 metadata
- `apps/web/app/page.tsx` — Wave-0 placeholder "use client" page (Plan 04-04 overwrites)
- `apps/web/app/globals.css` — Tailwind v4 CSS-first, light mode only (D-04)
- `apps/web/app/api/health/route.ts` — Wave-0 placeholder GET returning `missing_key`
- `apps/web/components/ui/button.tsx` — shadcn primitive (registry, unedited)
- `apps/web/components/ui/dialog.tsx` — shadcn primitive (registry, unedited)
- `apps/web/components/ui/input.tsx` — shadcn primitive (registry, unedited)
- `apps/web/components/ui/sonner.tsx` — shadcn primitive (registry, unedited)
- `apps/web/lib/cn.ts` — PATTERNS Pattern E cn() helper
- `apps/web/lib/utils.ts` — re-exports cn so shadcn registry imports compile
- `apps/web/lib/MARKDOWN-DECISION.md` — Wave-0 spike outcome (Plan 06 reads this)
- `apps/web/vitest.config.ts` — jsdom env, alias `@`, include scoped to tests/
- `apps/web/playwright/playwright.config.ts` — multi-server with USE_MOCK_FASTAPI gate
- `apps/web/playwright/mock-fastapi.py` — canned 4-event SSE server for CI
- `apps/web/tests/setup.ts` — RTL afterEach(cleanup) + jest-dom matchers
- `apps/web/tests/sse-translate.test.ts` — D-07 contract stub (6 it.todo)
- `apps/web/tests/chunk-schemas.test.ts` — Schema contract stub (8 it.todo)
- `apps/web/tests/routing-chip.test.tsx` — UI-04 unit stub (6 it.todo)
- `apps/web/tests/metrics-footer.test.tsx` — UI-07 unit stub (6 it.todo)
- `apps/web/tests/chat-bubble.test.tsx` — UI-08 unit stub (6 it.todo)
- `apps/web/playwright/no-flicker.spec.ts` — UI-03 stub (test.skip)
- `apps/web/playwright/cancel-budget.spec.ts` — UI-06 stub (test.skip)
- `apps/web/playwright/first-run.spec.ts` — UI-01 + UI-13 stub (test.skip)
- `apps/web/playwright/secure-key.spec.ts` — D-18 belt stub (test.skip)
- `apps/web/playwright/browser-isolation.spec.ts` — UI-17 stub (test.skip)
- `apps/web/playwright/routing-chip.spec.ts` — UI-04 E2E stub (test.skip)
- `.github/workflows/web-test.yml` — pnpm cache + Vitest + Playwright with USE_MOCK_FASTAPI

**Modified (2):**
- `.gitignore` — appended the 6-line Next.js block (apps/web/{node_modules,.next,coverage,playwright-report,test-results,.env.local})
- `ReadMe.md` — appended "Running the chat UI" H2 section per CONTEXT specifics lines 317-331

## Decisions Made

1. **Stack uplift to RESEARCH Critical Finding #1 current majors** — CONTEXT D-06/D-07 floor (Next 15.2 + AI SDK v5) was stale; assistant-ui's canonical with-ai-sdk-v6 example is the current reference. No architectural change — just version bump. Documented in MARKDOWN-DECISION.md and frontmatter.
2. **Pattern 5 verdict pinned** — Plan 06 uses built-in @assistant-ui/react-markdown fence detection. Spike inspected `dist/overrides/{CodeBlock,CodeOverride,PreOverride}.js` and confirmed the three-mechanism chain. Pattern 5b removed from the Plan 06 candidate set.
3. **shadcn nova preset** — chosen because the CLI removed `--style=new-york` and `--base-color=slate` flags; nova preset (Lucide + Geist) matches our existing lucide-react + Geist setup. baseColor manually patched to slate per UI-SPEC §1.
4. **lib/utils.ts re-export** — shadcn registry components import `cn` from `@/lib/utils`; UI-SPEC §18 forbids editing registry files. Solution: `lib/utils.ts` is a 1-line barrel re-exporting from `lib/cn.ts` (the plan-specified canonical implementation).
5. **/api/health placeholder returns `missing_key`** — Plan 07 first-run-modal trigger logic needs a deterministic exercise path during early-wave dev; `missing_key` makes the modal-trigger code reachable. Plan 04-03 overwrites this with the real `/api/v1/healthz` passthrough.
6. **USE_MOCK_FASTAPI=1 in CI** — Playwright webServer config switches between uvicorn:8000 (local dev with real adapters) and mock-fastapi.py:8001 (CI, no OpenRouter key needed). FASTAPI_URL is set on the Next dev command so the route handlers talk to the right port without browser-side env-var leakage (UI-17).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] shadcn CLI flag rename — `--style=new-york` + `--base-color=slate` no longer accepted**
- **Found during:** Task 1 (shadcn init)
- **Issue:** Plan's `shadcn init` invocation used `--style=new-york --base-color=slate` which the current shadcn@4.7 CLI rejects (`error: unknown option '--base-color=slate'`).
- **Fix:** Switched to `--template next --base radix --preset nova --yes --force --no-monorepo`. Manually patched `components.json` to set `baseColor: "slate"` (UI-SPEC §1 requirement). nova preset (Lucide + Geist) is the closest match to our lucide-react + Geist font setup; UI-SPEC §1's typographic tokens are still satisfied because the Geist family is what the preset selects.
- **Files modified:** apps/web/components.json
- **Verification:** `grep baseColor apps/web/components.json` shows `"baseColor": "slate"`; shadcn add ran successfully and wrote button/dialog/input/sonner.
- **Committed in:** 85522cf (Task 1)

**2. [Rule 2 - Missing Critical] lib/utils.ts re-export — shadcn registry components import `cn` from `@/lib/utils`**
- **Found during:** Task 1 (post-shadcn add inspection)
- **Issue:** shadcn-generated `button.tsx` (and the other 3) hard-code `import { cn } from "@/lib/utils"`. The plan only mandates `apps/web/lib/cn.ts`. UI-SPEC §18 forbids hand-editing the registry files, so the import path must be honored.
- **Fix:** Created `apps/web/lib/utils.ts` as a 1-line barrel re-exporting `cn` from `./cn.ts`. The canonical implementation stays in `lib/cn.ts` (PATTERNS Pattern E); `lib/utils.ts` is just a compatibility shim. Both files commented to explain the relationship.
- **Files modified:** apps/web/lib/utils.ts (new)
- **Verification:** `pnpm run build` exits 0 (would fail with "Module not found: @/lib/utils" otherwise).
- **Committed in:** 85522cf (Task 1)

**3. [Rule 3 - Blocking] pnpm-workspace.yaml scaffolder artifact not in `files_modified`**
- **Found during:** Task 1 (post-scaffold ls)
- **Issue:** `pnpm create next-app` emits `apps/web/pnpm-workspace.yaml` declaring `ignoredBuiltDependencies: [sharp, unrs-resolver]`. The plan's `files_modified` array does not list it.
- **Fix:** Committed it anyway — without it, `pnpm install` warns about unapproved build scripts on every run and the user would have to `pnpm approve-builds` interactively. Treated as a scaffolder artifact (same category as `next-env.d.ts`, which is gitignored).
- **Files modified:** apps/web/pnpm-workspace.yaml (new)
- **Verification:** `pnpm install --frozen-lockfile` exits 0 cleanly without warnings about sharp/unrs-resolver.
- **Committed in:** 85522cf (Task 1)

**4. [Rule 3 - Blocking] `apps/web/.gitignore` `.env*` rule blocks `.env.example`**
- **Found during:** Task 1 (first `git add` of `.env.example`)
- **Issue:** Scaffolder writes `.env*` in `apps/web/.gitignore`. The plan requires `.env.example` committed (verification command lists it). Without an un-ignore the file is uncommittable.
- **Fix:** Added `!.env.example` un-ignore line in apps/web/.gitignore, kept the existing `.env.local` belt-and-suspenders line (D-05).
- **Files modified:** apps/web/.gitignore
- **Verification:** `git check-ignore -v apps/web/.env.example` shows `!.env.example`; `git check-ignore -v apps/web/.env.local` still shows `.env.local` (correctly ignored).
- **Committed in:** 85522cf (Task 1)

**5. [Rule 1 - Bug] Scaffolder README.md / AGENTS.md / CLAUDE.md / public/ noise files**
- **Found during:** Task 1 (post-scaffold inspection)
- **Issue:** `pnpm create next-app` emits `apps/web/README.md`, `apps/web/AGENTS.md`, `apps/web/CLAUDE.md` (an `@AGENTS.md` redirect), and `apps/web/public/{file.svg,globe.svg,next.svg,vercel.svg,window.svg}`. None are in the plan's `files_modified`; the public SVGs leak into the route bundle.
- **Fix:** `rm` them all before committing. The repo-root ReadMe.md is the authoritative project README; the AGENTS.md scaffolder content was a warning about Next 16 breaking changes which I honored by inspecting `node_modules/next/dist/docs/01-app/01-getting-started/13-fonts.md` before authoring layout.tsx (no breaking change for `next/font/google` Geist usage). Project's `apps/web/CLAUDE.md` would conflict with the root `CLAUDE.md` discovery; removed.
- **Files modified:** none (delete-only)
- **Verification:** `find apps/web -maxdepth 2 -type f` shows only plan-specified files plus the scaffolder configs (tsconfig/next.config/postcss).
- **Committed in:** 85522cf (Task 1)

**6. [Rule 2 - Missing Critical] page.tsx default font-Geist references broke (dark-mode default)**
- **Found during:** Task 1 (post-scaffold inspection of page.tsx + globals.css)
- **Issue:** Scaffolder page.tsx uses `dark:bg-black` everywhere and globals.css has a `@media (prefers-color-scheme: dark)` branch — both violate CONTEXT D-04 (light mode only).
- **Fix:** Replaced page.tsx with the Wave-0 placeholder per plan spec. Replaced globals.css with the Tailwind v4 CSS-first config that explicitly OMITS the dark-mode media query and pins `--color-foreground: #0f172a` (slate-900 per UI-SPEC §4.1).
- **Files modified:** apps/web/app/page.tsx, apps/web/app/globals.css
- **Verification:** `grep -i 'dark' apps/web/app/{page,layout}.tsx apps/web/app/globals.css` returns no matches; `pnpm build` exits 0.
- **Committed in:** 85522cf (Task 1)

---

**Total deviations:** 6 auto-fixed (3 blocking, 2 missing critical, 1 bug)
**Impact on plan:** All auto-fixes essential for a green build + frozen-lockfile install + UI-SPEC compliance. No scope creep. No architectural changes. The Pattern 5 verdict was the only spike outcome and matches the plan's expected output shape.

## Issues Encountered

- **shadcn CLI exited with code 1 on "Ignored build scripts" warning** — non-fatal warning treated as a fatal exit code by the shadcn CLI. Twice. First pass (init) wrote `components.json` but aborted before writing components/ files. Second pass (add) failed before writing the 4 component files. Fix: pre-installed the missing deps (`tw-animate-css next-themes sonner @radix-ui/react-dialog @radix-ui/react-slot`) so the second `shadcn add button dialog input sonner --yes --overwrite` only needed to write files (which it did successfully). The `[ERR_PNPM_IGNORED_BUILDS]` warning about sharp/msw is benign — they're optional native deps and the Next 16 build doesn't need them.

## User Setup Required

None. All required CLI tooling (pnpm 11.1.2, node 24.15.0, uv) was already installed locally. CI installs the same toolchain on every run.

## Next Phase / Plan Readiness

- **Plan 04-02 (Wave 1) ready:** can author `apps/web/lib/sse-translate.ts` + `apps/web/lib/chunk-schemas.ts` + `apps/web/lib/types.ts` and overwrite the matching test stubs (`tests/sse-translate.test.ts`, `tests/chunk-schemas.test.ts`).
- **Plan 04-03 (Wave 2) ready:** can author `apps/web/app/api/chat/route.ts` + overwrite `apps/web/app/api/health/route.ts` (real passthrough) + `apps/web/app/api/settings/route.ts` + `apps/web/app/api/threads/route.ts`. Pattern C (runtime+dynamic) is established.
- **Plan 04-04..04-07 ready:** every test path in their acceptance criteria already exists as a stub on disk.
- **Plan 04-06 has its binding decision file:** `apps/web/lib/MARKDOWN-DECISION.md` says Pattern 5.
- **No blockers.** The orchestrator can advance plan counter to 04-02.

## Self-Check: PASSED

Created files verified to exist:
- apps/web/package.json — FOUND
- apps/web/pnpm-lock.yaml — FOUND
- apps/web/tsconfig.json — FOUND
- apps/web/next.config.ts — FOUND
- apps/web/postcss.config.mjs — FOUND
- apps/web/components.json — FOUND
- apps/web/pnpm-workspace.yaml — FOUND
- apps/web/.env.example — FOUND
- apps/web/.gitignore — FOUND
- apps/web/app/layout.tsx — FOUND
- apps/web/app/page.tsx — FOUND
- apps/web/app/globals.css — FOUND
- apps/web/app/api/health/route.ts — FOUND
- apps/web/components/ui/button.tsx — FOUND
- apps/web/components/ui/dialog.tsx — FOUND
- apps/web/components/ui/input.tsx — FOUND
- apps/web/components/ui/sonner.tsx — FOUND
- apps/web/lib/cn.ts — FOUND
- apps/web/lib/utils.ts — FOUND
- apps/web/lib/MARKDOWN-DECISION.md — FOUND
- apps/web/vitest.config.ts — FOUND
- apps/web/playwright/playwright.config.ts — FOUND
- apps/web/playwright/mock-fastapi.py — FOUND
- apps/web/tests/setup.ts — FOUND
- apps/web/tests/sse-translate.test.ts — FOUND
- apps/web/tests/chunk-schemas.test.ts — FOUND
- apps/web/tests/routing-chip.test.tsx — FOUND
- apps/web/tests/metrics-footer.test.tsx — FOUND
- apps/web/tests/chat-bubble.test.tsx — FOUND
- apps/web/playwright/no-flicker.spec.ts — FOUND
- apps/web/playwright/cancel-budget.spec.ts — FOUND
- apps/web/playwright/first-run.spec.ts — FOUND
- apps/web/playwright/secure-key.spec.ts — FOUND
- apps/web/playwright/browser-isolation.spec.ts — FOUND
- apps/web/playwright/routing-chip.spec.ts — FOUND
- .github/workflows/web-test.yml — FOUND

Commits verified to exist:
- 85522cf — FOUND (Task 1 — feat: scaffold apps/web/ Next 16 + AI SDK v6 + assistant-ui workspace)
- 367df1f — FOUND (Task 2 — test: scaffold Vitest + Playwright + RTL + 11 test stubs + mock-FastAPI)
- 5565e57 — FOUND (Task 3 — feat: Wave-0 spike, /api/health placeholder, CI workflow)

---
*Phase: 04-minimal-chat-ui-openrouter-backend*
*Completed: 2026-05-19*
