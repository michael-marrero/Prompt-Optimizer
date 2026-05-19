---
phase: 04
slug: minimal-chat-ui-openrouter-backend
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-18
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Sourced from `04-RESEARCH.md` § Validation Architecture (lines 1259-1307).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework (unit / component)** | Vitest 4.1 + jsdom + @testing-library/react |
| **Framework (E2E)** | Playwright 1.60 with multi-server `webServer` config (uvicorn + next dev) |
| **Framework (Phase-3 contract)** | pytest (existing — for the D-15 SSE-event contract test in `apps/api/tests/`) |
| **Config file (Vitest)** | `apps/web/vitest.config.ts` — Wave 0 installs |
| **Config file (Playwright)** | `apps/web/playwright/playwright.config.ts` — Wave 0 installs |
| **Setup file (RTL)** | `apps/web/tests/setup.ts` — Wave 0 installs |
| **Quick run command (unit + component)** | `pnpm --dir apps/web test` |
| **Quick run command (E2E)** | `pnpm --dir apps/web test:e2e` |
| **Full suite command** | `pnpm --dir apps/web test && pnpm --dir apps/web test:e2e` |
| **Phase-3 contract command** | `pytest apps/api/tests/test_turn_streaming.py` |
| **Estimated runtime** | ~10 s (Vitest unit) / 60-120 s (Playwright full E2E spinning up uvicorn + next dev) |

---

## Sampling Rate

- **After every task commit:** Run `pnpm --dir apps/web test` (Vitest unit + component, watch off)
- **After every plan wave:** Run `pnpm --dir apps/web test && pnpm --dir apps/web test:e2e`
- **Before `/gsd-verify-work`:** Full suite green AND Phase-3 contract test for D-15 green AND a manual UAT confirming the five Success Criteria
- **Max feedback latency:** 120 s (full suite, worst case with Playwright)

---

## Per-Task Verification Map

> Detailed task IDs are populated by the planner. The table below is keyed by **requirement → test command** as derived from RESEARCH.md and locks the file each test must exist in. The planner MUST map every task to one of these requirement rows (or explicitly mark the task as `<manual>` with justification).

| Req / Contract | Behavior | Test Type | Automated Command | Test File (Wave 0 stub) | Status |
|---|---|---|---|---|---|
| UI-01 | Chat surface renders; user can type and submit | E2E happy-path | `pnpm --dir apps/web test:e2e first-run.spec.ts` | `apps/web/playwright/first-run.spec.ts` | ⬜ pending |
| UI-03 | Markdown streams + code blocks highlight once on close | E2E no-flicker | `pnpm --dir apps/web test:e2e no-flicker.spec.ts` | `apps/web/playwright/no-flicker.spec.ts` | ⬜ pending |
| UI-04 | Routing chip renders on every assistant message (never collapsed) | E2E + unit | `pnpm --dir apps/web test:e2e routing-chip.spec.ts` + `pnpm --dir apps/web test routing-chip.test.tsx` | `apps/web/playwright/routing-chip.spec.ts`, `apps/web/components/RoutingChip.test.tsx` | ⬜ pending |
| UI-06 | Stop preserves partial; cancels within 2 s; persisted status set | E2E budget | `pnpm --dir apps/web test:e2e cancel-budget.spec.ts` | `apps/web/playwright/cancel-budget.spec.ts` | ⬜ pending |
| UI-07 | Metrics footer shows cost / latency / tokens after Done | E2E + unit | `pnpm --dir apps/web test metrics-footer.test.tsx` | `apps/web/components/MetricsFooter.test.tsx` | ⬜ pending |
| UI-08 | ChatBubble renders + copy + regenerate actions | unit + manual UAT | `pnpm --dir apps/web test chat-bubble.test.tsx` | `apps/web/components/ChatBubble.test.tsx` | ⬜ pending |
| UI-13 | First-run modal flow guides clone → first turn | E2E | `pnpm --dir apps/web test:e2e first-run.spec.ts` | `apps/web/playwright/first-run.spec.ts` | ⬜ pending |
| UI-17 | Browser never opens connections to FastAPI directly | E2E network-assertion | `pnpm --dir apps/web test:e2e browser-isolation.spec.ts` | `apps/web/playwright/browser-isolation.spec.ts` | ⬜ pending |
| D-18 belt | OpenRouter key never appears in logs / headers / bodies / storage | E2E regression | `pnpm --dir apps/web test:e2e secure-key.spec.ts` | `apps/web/playwright/secure-key.spec.ts` | ⬜ pending |
| D-07 contract | SSE translator (Phase-3 named events → AI SDK v6 chunks) is a pure function and matches the protocol exactly | Vitest unit | `pnpm --dir apps/web test sse-translate.test.ts` | `apps/web/lib/sse-translate.test.ts` | ⬜ pending |
| D-15 contract | Phase 3 `routing_decision` SSE event arrives within 100 ms and matches `Done.routing_signals` | pytest (Phase 3 amendment) | `pytest apps/api/tests/test_turn_streaming.py::test_routing_decision_event` | `apps/api/tests/test_turn_streaming.py` | ⬜ pending |
| Schema contract | Every Phase-3 SSE event is parseable by the Zod schemas at the route-handler boundary | Vitest | `pnpm --dir apps/web test chunk-schemas.test.ts` | `apps/web/lib/chunk-schemas.test.ts` | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `apps/web/vitest.config.ts` — Vitest jsdom config
- [ ] `apps/web/playwright/playwright.config.ts` — multi-server config (uvicorn + next dev)
- [ ] `apps/web/tests/setup.ts` — RTL setup (`@testing-library/jest-dom`)
- [ ] Framework install: `pnpm add -D vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/jest-dom @playwright/test`
- [ ] Playwright browsers: `pnpm exec playwright install chromium`
- [ ] CI workflow extension to run `pnpm --dir apps/web test && pnpm --dir apps/web test:e2e`
- [ ] Mocked-FastAPI fixture for E2E in CI (small Python script serving canned named-event SSE responses without needing real OpenRouter)
- [ ] Test stubs (empty `it.todo` / `test.skip`) for every row in the table above so the planner's Per-Task Verification Map references existing files

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|---|---|---|---|
| Visual "no flicker" sanity on real OpenRouter response | UI-03 | Playwright's MutationObserver assertion proves no re-highlight, but the human-perceptible smoothness needs a real eye on a real stream | Run `pnpm --dir apps/web dev` + `uvicorn apps.api.main:app`; submit "Write a short Python class that prints hello with a docstring"; watch the code fence render once highlight finalizes — no flash, no second highlight pass |
| First-run modal flow on a brand-new clone | UI-13 | E2E covers the gated state, but the contributor-experience clock starts at `git clone` — Phase 6 measures this end-to-end | On a clean workdir with no `.env`, run `pnpm --dir apps/web dev` + `uvicorn`; verify modal appears, paste an OpenRouter key, verify chat input unlocks without restart |
| Metrics footer accuracy against OpenRouter's actual billed cost | UI-07 | Cost USD comes from the upstream `Done` chunk — manual cross-check against the OpenRouter dashboard a few times catches drift | Submit 3 turns; compare the displayed cost USD to the OpenRouter activity log within 24 h |
| BYOK key UX: enter, mask, replace, clear | UI-13 / D-18 | The full settings panel is Phase 5 — Phase 4 minimal modal only enters / unlocks. Manual UAT confirms no key residue after entry | After entering a key via the modal, open DevTools → Application → Storage; confirm no plaintext key in localStorage / sessionStorage / cookies |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references in the table above
- [ ] No watch-mode flags (`vitest --watch`, `playwright --ui`) in CI commands
- [ ] Feedback latency < 120 s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
