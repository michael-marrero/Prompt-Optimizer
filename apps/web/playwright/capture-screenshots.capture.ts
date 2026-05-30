// Plan 06-04 — capture-screenshots.capture.ts (OSS-04 / D-10 screenshot tool)
//
// LOCAL AUTHORING TOOL — NOT a CI gate. This script drives the three
// golden-path routing-chip bubbles against mock-fastapi.py (NO real keys,
// deterministic) and writes four PNGs to docs/img/ for the README:
//   docs/img/hero.png             — full-app shell / empty-state hero (D-10)
//   docs/img/chip-openrouter.png  — OpenRouter ChatBubble + GREEN-less default chip
//   docs/img/chip-claude-code.png — Claude Code CodeBubble + GREEN chip + diff
//   docs/img/chip-computer-use.png— computer-use ComputerUseBubble + AMBER chip
//
// THREE layers of CI-exclusion (RESEARCH Pitfall 4 — this must never gate a PR):
//   1. The filename uses the `.capture.ts` suffix, which does NOT match the
//      playwright.config.ts default `testMatch: /.*\.spec\.ts/` — so the normal
//      `pnpm test:e2e` run never discovers it.
//   2. playwright.config.ts adds a defensive `testIgnore` for `*.capture.ts`
//      whenever CAPTURE_SCREENSHOTS is unset.
//   3. The test body below is guarded with `test.skip(!!process.env.CI)`.
//
// HOW TO RUN (local only — needs Chromium + mock-fastapi; no OpenRouter key):
//   CAPTURE_SCREENSHOTS=1 USE_MOCK_FASTAPI=1 \
//     pnpm --dir apps/web exec playwright test playwright/capture-screenshots.capture.ts
//
// CAPTURE_SCREENSHOTS=1 flips playwright.config.ts's testMatch to also accept
// `.capture.ts`, so the explicit path resolves; USE_MOCK_FASTAPI=1 boots
// mock-fastapi.py on :8001 (the deterministic canned-SSE backend) instead of
// real uvicorn. The mock's [fixture:claude-code] / [fixture:computer-use]
// fixtures (Plan 06-04) emit the matching `backend` so MessageBubble dispatches
// to the CodeBubble / ComputerUseBubble renderers.
//
// Driving patterns (goto, first-run-modal tolerance, composer fill) are lifted
// from routing-chip.spec.ts:43-65.

import { test, expect } from "@playwright/test";
import { resolve } from "node:path";
import { mkdirSync } from "node:fs";

// docs/img/ lives at the repo root. This config file is at
// apps/web/playwright/, so walk up three levels (mirrors
// playwright.config.ts:15 REPO_ROOT derivation).
const REPO_ROOT = resolve(__dirname, "../../..");
const IMG_DIR = resolve(REPO_ROOT, "docs/img");

// Locator for the composer. Phase 7 (ChatSurface.tsx:419) changed the
// ComposerPrimitive.Input placeholder to "Ask anything — we'll route it to the
// best model."; match on the ASCII prefix to avoid the em-dash/apostrophe.
const COMPOSER = 'textarea[placeholder^="Ask anything"]';

// Tolerate the first-run modal on a no-key clone (routing-chip.spec.ts:46-56).
// A dummy key satisfies the gate; the mock answers regardless of key value.
async function dismissFirstRunModal(page: import("@playwright/test").Page): Promise<void> {
  const modalHeading = page.getByText("Connect OpenRouter to get started");
  if (await modalHeading.isVisible({ timeout: 2000 }).catch(() => false)) {
    await page.getByLabel("OpenRouter API key").fill("sk-or-v1-" + "K".repeat(48));
    await page.getByRole("button", { name: "Save & continue" }).click();
    await expect(modalHeading).toBeHidden({ timeout: 5000 });
  }
}

// Send a prompt and wait for the assistant bubble identified by `testid` to
// render, then return the enclosing message container (chip + bubble) so the
// caller can screenshot the chip together with its bubble.
async function sendAndAwaitBubble(
  page: import("@playwright/test").Page,
  message: string,
  testid: string,
): Promise<import("@playwright/test").Locator> {
  const composer = page.locator(COMPOSER);
  await composer.waitFor({ state: "visible", timeout: 10_000 });
  await composer.fill(message);
  await page.keyboard.press("Enter");

  // The chip renders ABOVE the bubble; both live inside the same `mb-6`
  // message container (MessageBubble.tsx:117-128). Wait for the bubble, then
  // climb to the container that also holds the RoutingChip.
  const bubble = page.locator(`[data-testid="${testid}"]`).first();
  await bubble.waitFor({ state: "visible", timeout: 20_000 });

  // Confirm the routing chip rendered for this turn before shooting.
  // Phase 7 (07-03) re-skinned the always-visible chip into the L1 "optimized"
  // pill: same role="status", but the aria-label is now
  // `Routed to <model> — <reason>` (em-dash), NOT the old "Routing decision …".
  // Match the stable "Routed to" substring so the wait resolves on the new pill.
  const chip = page
    .locator('[role="status"][aria-label*="Routed to"]')
    .first();
  await chip.waitFor({ state: "visible", timeout: 20_000 });

  // The message container is the enclosing <article> (MessageBubble.tsx:117 —
  // Phase 7 changed this from `<div class="mb-6">` to `<article class="mb-7">`).
  // It holds the header row (mono "Prompt Optimizer" label + the optimized pill),
  // the bubble, and the footer — so screenshotting it captures chip + bubble.
  return page.locator(`[data-testid="${testid}"]`).first().locator("xpath=ancestor::article[1]");
}

test.describe("Plan 06-04 — README screenshot capture (local tool, CI-excluded)", () => {
  // Hard CI guard (Pitfall 4 layer 3) — never run as a build gate.
  test.skip(!!process.env.CI, "capture tool — local authoring only, never in CI");

  test.beforeAll(() => {
    // Create docs/img/ if absent so locator.screenshot has a target dir.
    mkdirSync(IMG_DIR, { recursive: true });
  });

  test("capture hero + three routing-chip screenshots to docs/img/", async ({ page }) => {
    // ---- HERO: full-app shell / empty-state, before any turn. ----
    await page.goto("/");
    await dismissFirstRunModal(page);
    // Let the empty-state three-prompt cards settle.
    await page.locator(COMPOSER).waitFor({ state: "visible", timeout: 10_000 });
    await page.screenshot({ path: resolve(IMG_DIR, "hero.png"), fullPage: false });

    // ---- CHIP 1: OpenRouter (default fixture → ChatBubble / chat-bubble). ----
    // The mock's default fixture emits backend "openrouter".
    const openrouterContainer = await sendAndAwaitBubble(
      page,
      "What is the capital of France?",
      "chat-bubble",
    );
    await openrouterContainer.screenshot({
      path: resolve(IMG_DIR, "chip-openrouter.png"),
    });

    // ---- CHIP 2: Claude Code ([fixture:claude-code] → CodeBubble). ----
    const claudeCodeContainer = await sendAndAwaitBubble(
      page,
      "[fixture:claude-code] Build me a small finance tracker app",
      "code-bubble",
    );
    await claudeCodeContainer.screenshot({
      path: resolve(IMG_DIR, "chip-claude-code.png"),
    });

    // ---- CHIP 3: computer-use ([fixture:computer-use] → ComputerUseBubble). ----
    const computerUseContainer = await sendAndAwaitBubble(
      page,
      "[fixture:computer-use] Open this URL and check the price",
      "computer-use-bubble",
    );
    await computerUseContainer.screenshot({
      path: resolve(IMG_DIR, "chip-computer-use.png"),
    });
  });
});
