// Phase 7 Plan 07-01 Wave 0 — routing-chip.spec.ts REWRITTEN to the Plasma L1
// optimized-pill contract.
//
// 07-VALIDATION.md row: "E2E routing visibility (L1) | L1/D-01 | E2E —
// REWRITE playwright/routing-chip.spec.ts + drift.spec.ts: pill + aria-label;
// remove always-visible-chip assertions".
//
// WHY this spec was rewritten (07-CONTEXT L1 / UI-SPEC §0.3):
//   Phase 4/5 shipped an ALWAYS-VISIBLE chip on every assistant message
//   (located by a role=status selector whose aria-label began with the old
//   routing-decision prefix, inline text /^Routed to .+ · .+$/, chip count
//   growing to 3). Phase 7 LOCKED decision
//   L1 makes routing INVISIBLE-BY-DEFAULT: the chip is replaced by a
//   hover/focus-only "optimized" pill whose aria-label carries the full
//   "Routed to {model} — {reason}" (em-dash). This spec now re-points to that
//   pill and DROPS the always-visible / count-grows-to-3 assertions. Per D-01
//   we update the test, not the design. The literal substring "Routing
//   decision" no longer appears anywhere in this file (it was the old chip's
//   aria-label prefix; the new pill uses "Routed to … — …").
//
// RED-by-design: the optimized pill lands in Plan 07-02/07-04; until then the
// pill locator finds nothing and this spec is RED for "pill not implemented"
// reasons — the correct Wave-0 state. (E2E specs are not run in the unit tier;
// the Playwright run is gated behind /gsd-verify-work per 07-VALIDATION.)
//
// Uses Plan 01's mock-fastapi.py default fixture (USE_MOCK_FASTAPI=1 in CI).
// The default fixture emits a routing_decision event with
// model_or_agent="openai/gpt-5" which resolves verbatim as the pill's model
// label (UI-SPEC §0.3 fallback rule — unmapped OpenRouter slugs render raw).

import { test, expect } from "@playwright/test";

test("L1: optimized pill carries the 'Routed to {model} — {reason}' aria-label (invisible-by-default)", async ({
  page,
}) => {
  await page.goto("/");

  // Satisfy the first-run modal if it appears (tolerate either path).
  const modalHeading = page.getByText("Connect OpenRouter to get started");
  if (await modalHeading.isVisible({ timeout: 2000 }).catch(() => false)) {
    await page
      .getByLabel("OpenRouter API key")
      .fill("sk-or-v1-" + "K".repeat(48));
    await page.getByRole("button", { name: "Save & continue" }).click();
    await expect(modalHeading).toBeHidden({ timeout: 5000 });
  }

  const composer = page.locator('textarea[placeholder="Type a message…"]');
  await composer.waitFor({ state: "visible", timeout: 10_000 });

  // Send a single turn.
  await composer.fill("hello");
  await page.keyboard.press("Enter");

  // L1 contract: the assistant message carries an "optimized" pill whose
  // aria-label is the FULL "Routed to {model} — {reason}" (em-dash U+2014).
  // We locate by the aria-label pattern rather than the old role=status
  // routing-chip selector. The pill exists in the DOM even though it is
  // visually revealed only on hover/focus (the rationale moves to the
  // title/aria-label per UI-SPEC §0.3), so we assert presence in the DOM.
  const pill = page
    .locator('[aria-label*="Routed to"]')
    .filter({ has: page.locator(":scope") })
    .first();
  await pill.waitFor({ state: "attached", timeout: 15_000 });

  const ariaLabel = (await pill.getAttribute("aria-label")) ?? "";
  // Em-dash separated "Routed to {model} — {reason}" (L1 / UI-SPEC §0.3).
  expect(ariaLabel).toMatch(/^Routed to .+ — .+$/);

  // The visible text of the pill is the lowercase word "optimized"
  // (UI-SPEC §Copywriting / §Typography). Tolerant hover to exercise the
  // reveal-on-hover affordance without asserting computed visibility (that is
  // a Manual-Only pixel/hover check per 07-VALIDATION).
  await pill.hover().catch(() => {});
  const optimized = page.getByText("optimized", { exact: true }).first();
  await expect(optimized).toHaveCount(1);
});
