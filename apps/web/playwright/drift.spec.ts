// Plan 06-03 Wave 2 — drift.spec.ts (OSS-07 Next↔FastAPI drift-catcher)
//
// THIS SPEC RUNS IN THE REAL-UVICORN DEFAULT MODE — there is NO
// USE_MOCK_FASTAPI here. playwright.config.ts's default branch boots the
// REAL `python -m uvicorn apps.api.main:app --port 8000` plus `next dev`,
// so the entire production wire is exercised: browser → Next proxy
// (/api/chat) → real FastAPI SSE named-event framing (turn.py) →
// apps/web/lib/sse-translate.ts → AI-SDK UI-Message-Stream → RoutingChip.
//
// REQUIREMENT: the env that spawns Playwright MUST set
//   PROMPT_OPTIMIZER_FAKE_ADAPTERS=1
// so the uvicorn child wires Plan 06-01's fake OpenRouter adapter at
// startup (lifespan.py logs "Lifespan: FAKE adapters wired"). With the fake
// wired, the REAL OpenRouterAdapter streams canned chunks
// ("Paris" → " is the capital.") with NO OpenRouter key and zero network /
// cost — deterministic, fork-PR-safe (D-06). Set it at the CI step env
// level, or prefix a local run:
//   PROMPT_OPTIMIZER_FAKE_ADAPTERS=1 pnpm --dir apps/web exec playwright test playwright/drift.spec.ts
//
// Why a NEW spec (not repurposing routing-chip.spec.ts): a hand-maintained
// mock-fastapi.py cannot catch AI-SDK ↔ FastAPI UI-Message-Stream-Protocol
// drift; only the real wire — browser to Next to FastAPI and back — can.
// This spec is trimmed to a single turn and carries no mock/Regenerate
// concerns (those are routing-chip.spec.ts's mock-specific job).

import { test, expect } from "@playwright/test";

test("OSS-07: real uvicorn + fake upstream — streamed text + routing chip (drift gate)", async ({
  page,
}) => {
  await page.goto("/");

  // Tolerate the first-run modal (the real app shows it on a no-key clone).
  // Copied verbatim from routing-chip.spec.ts:46-56. With the fake adapter
  // wired, a dummy key satisfies the gate and the fake upstream answers
  // regardless of the key value.
  const modalHeading = page.getByText("Connect OpenRouter to get started");
  if (
    await modalHeading.isVisible({ timeout: 2000 }).catch(() => false)
  ) {
    await page
      .getByLabel("OpenRouter API key")
      .fill("sk-or-v1-" + "K".repeat(48));
    await page.getByRole("button", { name: "Save & continue" }).click();
    await expect(modalHeading).toBeHidden({ timeout: 5000 });
  }

  const composer = page.locator('textarea[placeholder="Type a message…"]');
  await composer.waitFor({ state: "visible", timeout: 10_000 });

  // UI-16's OpenRouter golden-path prompt — MANDATORY per RESEARCH Pitfall 6:
  // Plan 06-01 wires ONLY the openrouter fake, and this prompt reliably
  // routes to OpenRouter (a coding/agentic prompt would route to a backend
  // with no fake wired and 400/500).
  await composer.fill("What is the capital of France?");
  await page.keyboard.press("Enter");

  // (1) Assert the optimized pill is present (Phase 7 L1 — routing is
  // invisible-by-default; the always-visible chip is replaced by a
  // hover/focus-only pill whose aria-label carries the full rationale, per
  // UI-SPEC §0.3). This is a GENUINE routing decision — the routing brain
  // still runs against the real models/*.joblib; only the upstream OpenRouter
  // HTTP call is faked. We locate by the new "Routed to {model} — {reason}"
  // aria-label (em-dash U+2014) instead of the old role=status chip selector
  // that matched the legacy routing-decision aria-label prefix.
  const pill = page.locator('[aria-label*="Routed to"]').first();
  await pill.waitFor({ state: "attached", timeout: 15_000 });

  // The pill's aria-label is the canonical em-dash-separated
  // "Routed to {model} — {reason}" (L1 / UI-SPEC §0.3).
  const ariaLabel = (await pill.getAttribute("aria-label")) ?? "";
  expect(ariaLabel).toMatch(/^Routed to .+ — .+$/);

  // (2) Assert streamed text from the fake upstream lands in the assistant
  // DOM. Plan 06-01's fake emits "Paris" then " is the capital." — if the
  // SSE wire or sse-translate.ts drifts, this text never reaches the DOM.
  await expect(page.getByText(/Paris|capital/i).first()).toBeVisible({
    timeout: 15_000,
  });
});
