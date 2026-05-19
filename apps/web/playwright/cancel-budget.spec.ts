// Plan 04-07 Wave 6 — cancel-budget.spec.ts
//
// VALIDATION.md row: UI-06 (Stop preserves partial assistant message).
// ROADMAP SC #3: Stop within 2s + partial preserved.
//
// Test contract (PLAN must_haves + RESEARCH Pattern 3 + Pitfall 3):
//   1. Start a turn against the mock-fastapi [fixture:slow] path which
//      emits one text_delta every 500ms for up to 10s.
//   2. Wait for the first text_delta to appear (Stop button is visible
//      once the runtime transitions to "running" state — assistant-ui
//      mounts ComposerPrimitive.Cancel automatically).
//   3. Capture the partial assistant text BEFORE stopping.
//   4. Record t0 = performance.now() at Stop click.
//   5. Wait for terminal UI state (metrics footer OR alert banner).
//   6. Record t1 = performance.now() at terminal state.
//   7. Assert (t1 - t0) < 2000ms — the D-09 2s cancel budget end-to-end
//      across browser → Next proxy → upstream (the mock honors
//      asyncio.CancelledError so the abort propagates cleanly).
//   8. Assert partial assistant text is still in the DOM (Pitfall 3:
//      useChat.stop preserves partial — does not nuke the message).
//
// Cross-refs:
//   - 04-CONTEXT.md D-09 (3-layer 2s budget invariant)
//   - 04-RESEARCH.md §"Pattern 3" lines 702-731 (AbortController chain)
//   - 04-RESEARCH.md §"Critical Finding #2" (stop-status broadening)
//   - apps/web/playwright/mock-fastapi.py [fixture:slow] dispatch

import { test, expect } from "@playwright/test";

test("UI-06: Stop click cancels stream within 2s budget AND preserves partial message", async ({
  page,
  baseURL,
}) => {
  const upstream = (baseURL ?? "http://localhost:3000").replace("3000", "8001");
  // Reset + pre-flip mock-fastapi so the first-run modal does NOT appear
  // (this spec is about the cancel budget, not the gate).
  await page.request.post(`${upstream}/__reset`).catch(() => {});
  await page.request
    .patch(`${upstream}/api/v1/settings`, {
      data: { keys: { openrouter: "sk-or-v1-PREFLIPPED" } },
    })
    .catch(() => {});

  await page.goto("/");

  // Tolerate the first-run modal if it appears (e.g., when the spec runs
  // in isolation without the pre-flip path succeeding).
  const modalHeading = page.getByText("Connect OpenRouter to get started");
  if (await modalHeading.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await page
      .getByLabel("OpenRouter API key")
      .fill("sk-or-v1-" + "Y".repeat(48));
    await page.getByRole("button", { name: "Save & continue" }).click();
    await expect(modalHeading).toBeHidden({ timeout: 5_000 });
  }

  const composer = page.locator('textarea[placeholder="Type a message…"]');
  await composer.waitFor({ state: "visible", timeout: 10_000 });
  await expect(composer).toBeEnabled({ timeout: 10_000 });

  // Trigger the mock-fastapi slow fixture via Plan 06's body-prefix
  // mechanism (Warning 5 LOCKED — never query-param). The mock strips
  // the prefix before the emitter sees the rest.
  await composer.fill("[fixture:slow] please respond slowly");
  await page.keyboard.press("Enter");

  // Wait for the Stop button — it appears once the runtime transitions
  // to "running" (mid-stream). ComposerPrimitive.Cancel renders with
  // aria-label="Stop generating" per page.tsx.
  const stopButton = page.getByRole("button", { name: "Stop generating" });
  await stopButton.waitFor({ state: "visible", timeout: 10_000 });

  // Wait until at least one text_delta has arrived so we have something
  // partial to preserve. The chip lands within 1 text_delta.
  await page
    .locator('[role="status"][aria-label*="Routing decision"]')
    .first()
    .waitFor({ state: "visible", timeout: 10_000 });

  // Give the stream one extra tick (1 chunk = 500ms) so partial text
  // has rendered in the message bubble.
  await page.waitForTimeout(700);

  // Snapshot the partial DOM body before stopping. The chat surface
  // renders messages inside a Thread.Viewport; sample its full text
  // content as a proxy for "is there partial output yet".
  const partialBefore = await page.locator("main").innerText();
  expect(
    partialBefore.length,
    "Expected partial assistant text in the DOM before clicking Stop",
  ).toBeGreaterThan(0);

  // ===== KEY TIMING WINDOW =====
  const t0 = await page.evaluate(() => performance.now());
  await stopButton.click();

  // Terminal UI: either the metrics footer lands (status cancelled →
  // Done frame still fires per the slow fixture) OR an alert banner
  // appears. Critical Finding #2 says cancel emits status IN
  // ('cancelled', 'complete', 'error') — the metrics footer aria-label
  // is the most reliable browser-visible signal.
  await Promise.race([
    page
      .locator('[aria-label*="Turn cost"]')
      .first()
      .waitFor({ timeout: 2_500 }),
    page
      .locator('[role="alert"]')
      .first()
      .waitFor({ timeout: 2_500 }),
    // Fallback: the Stop button itself disappears when the runtime
    // returns to idle, so its absence is also a terminal signal.
    stopButton.waitFor({ state: "hidden", timeout: 2_500 }),
  ]);
  const t1 = await page.evaluate(() => performance.now());
  const elapsed = t1 - t0;

  // ===== KEY ASSERTION 1: 2s budget =====
  expect(
    elapsed,
    `Cancel-to-terminal elapsed ${elapsed.toFixed(0)}ms exceeds 2000ms budget (D-09)`,
  ).toBeLessThan(2000);

  // ===== KEY ASSERTION 2: partial preserved =====
  const partialAfter = await page.locator("main").innerText();
  expect(
    partialAfter.length,
    "Partial assistant message must persist in the DOM after Stop (Pitfall 3)",
  ).toBeGreaterThanOrEqual(partialBefore.length);
});
