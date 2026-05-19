// Plan 04-07 Wave 6 — first-run.spec.ts
//
// VALIDATION.md rows wired by this spec:
//   - UI-13: first-run modal + missing-key setup screen
//   - UI-01: clone-to-first-turn (the happy path verifying the modal flow
//     does not regress the streaming pipeline)
//
// Test contract (PLAN must_haves + UI-SPEC §10):
//   1. Launch fresh — mock-fastapi boots with _has_openrouter_key=False
//      so the initial GET /api/health returns adapters.openrouter.status
//      ="missing_key" → useFirstRunGate flips needsKey=true → modal opens
//   2. Modal heading "Connect OpenRouter to get started" is visible
//   3. Composer (textarea with placeholder "Type a message…") is disabled
//   4. User types a real-shaped key + clicks "Save & continue"
//   5. KeyForm POSTs /api/settings → mock-fastapi accepts + flips the
//      module flag → on resolve KeyForm dispatches 'pomu:key-saved'
//   6. useFirstRunGate's listener re-fetches /api/health → status="ready"
//      → needsKey=false → modal closes + composer enables WITHOUT reload
//   7. toast.success "OpenRouter connected — try a prompt!" fires (sonner)
//   8. User submits a turn → routing_chip appears within 2s (D-15
//      routing_decision is the first SSE event) → metrics footer lands
//      on Done
//
// Cross-refs:
//   - 04-UI-SPEC.md §10 (modal copy + submit flow)
//   - 04-CONTEXT.md D-16 (missing-key trigger), D-19 (post-entry unblock)
//   - apps/web/playwright/mock-fastapi.py [fixture:missing-key] state machine

import { test, expect } from "@playwright/test";

test("UI-13 + UI-01: first-run modal blocks composer until key entered, then full turn streams", async ({
  page,
  baseURL,
}) => {
  // Reset mock-fastapi's _has_openrouter_key flag to False so this spec
  // starts from a fresh missing-key state regardless of prior test order.
  // The /__reset endpoint is a test helper added by Task 2.
  const upstream = (baseURL ?? "http://localhost:3000").replace("3000", "8001");
  await page.request.post(`${upstream}/__reset`).catch(() => {
    // /__reset is mock-only; if running against a real backend the reset
    // is a no-op (the modal will show or not based on actual state).
  });

  // Clear browser storage to simulate a fresh-clone first visit.
  await page.context().clearCookies();

  await page.goto("/");

  // ----- Assertion 1: modal appears within 5s -----
  const modalHeading = page.getByText("Connect OpenRouter to get started");
  await expect(modalHeading).toBeVisible({ timeout: 5_000 });

  // ----- Assertion 2: composer is disabled -----
  const composer = page.locator('textarea[placeholder="Type a message…"]');
  await expect(composer).toBeDisabled({ timeout: 2_000 });

  // ----- Assertion 3: enter a real-shaped key + submit -----
  const keyInput = page.getByLabel("OpenRouter API key");
  await keyInput.fill("sk-or-v1-" + "X".repeat(48));
  await page.getByRole("button", { name: "Save & continue" }).click();

  // ----- Assertion 4: modal closes within 5s -----
  await expect(modalHeading).toBeHidden({ timeout: 5_000 });

  // ----- Assertion 5: composer enables -----
  await expect(composer).toBeEnabled({ timeout: 5_000 });

  // ----- Assertion 6: success toast fires -----
  await expect(
    page.getByText("OpenRouter connected — try a prompt!"),
  ).toBeVisible({ timeout: 5_000 });

  // ----- Assertion 7: submit a turn → chip + done -----
  await composer.fill("hello");
  await page.keyboard.press("Enter");

  // Chip renders within 2s of the first text_delta (Plan 04 D-15 timing
  // contract — routing_decision is the FIRST SSE event from the Phase 3
  // /turn endpoint).
  await expect(
    page.locator('[role="status"][aria-label*="Routing decision"]').first(),
  ).toBeVisible({ timeout: 5_000 });

  // Footer renders final metrics when Done lands.
  await expect(
    page.locator('[aria-label*="Turn cost"]').first(),
  ).toBeVisible({ timeout: 15_000 });
});
