// Plan 04-07 Wave 6 — browser-isolation.spec.ts
//
// VALIDATION.md row: UI-17 (browser never opens FastAPI sockets).
// ROADMAP SC #4: browser never opens FastAPI sockets — every request
// targets the Next origin only.
//
// Test contract (PLAN must_haves):
//   - Register page.on('request') for the entire page lifecycle
//   - Filter out non-http(s) schemes (data: / blob: / about:)
//   - For every remaining request, assert new URL(req.url()).host equals
//     the Next.js dev origin (localhost:3000 in dev, baseURL.host in
//     general). Zero requests to localhost:8000 or any other host.
//   - Exercise the full happy path: gate → key entry → modal close →
//     turn submit → metrics footer (so /api/health, /api/settings,
//     /api/chat, /api/threads, /api/threads/{id} all run end-to-end)
//
// The D-18 / D-08 BYOK invariant from CONTEXT: the browser never talks
// to FastAPI directly. The Next.js route handlers (Plan 03) own the
// upstream FASTAPI_URL and the env var is NEVER prefixed NEXT_PUBLIC_*,
// so it cannot leak into the bundle. This test catches any regression
// where a future developer adds a NEXT_PUBLIC_FASTAPI_URL env var or
// fetches FastAPI from a client component.
//
// Cross-refs:
//   - 04-CONTEXT.md D-08 (browser <-> FastAPI isolation), D-18 (key isolation)
//   - 04-RESEARCH.md §Architecture lines 365-371 (observable network panel)
//   - apps/web/app/api/*/route.ts (the only place FASTAPI_URL is read)

import { test, expect } from "@playwright/test";

test("UI-17: browser never opens connections to FastAPI — only to Next.js origin", async ({
  page,
  baseURL,
}) => {
  const nextOriginHost = new URL(baseURL ?? "http://localhost:3000").host;
  const offendingRequests: string[] = [];

  page.on("request", (req) => {
    const url = req.url();
    // Allow data:/blob:/about: schemes (no host) — they're inline browser
    // resources that can never reach FastAPI.
    if (!/^https?:/.test(url)) return;
    const host = new URL(url).host;
    if (host !== nextOriginHost) {
      offendingRequests.push(`${req.method()} ${url}`);
    }
  });

  // Pre-flip mock-fastapi so we can exercise the post-gate path. This
  // call goes through `page.request` which is a Node-side fetch — it is
  // NOT counted by `page.on('request')` (which only fires for browser
  // contexts), so the test helper itself never trips the assertion.
  const upstream = (baseURL ?? "http://localhost:3000").replace("3000", "8001");
  await page.request.post(`${upstream}/__reset`).catch(() => {});
  await page.request
    .patch(`${upstream}/api/v1/settings`, {
      data: { keys: { openrouter: "sk-or-v1-PREFLIPPED" } },
    })
    .catch(() => {});

  await page.goto("/");

  // Satisfy the first-run modal if it appears.
  const modalHeading = page.getByText("Connect OpenRouter to get started");
  if (await modalHeading.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await page
      .getByLabel("OpenRouter API key")
      .fill("sk-or-v1-" + "Z".repeat(48));
    await page.getByRole("button", { name: "Save & continue" }).click();
    await expect(modalHeading).toBeHidden({ timeout: 5_000 });
  }

  // Submit a turn so /api/chat (+ /api/threads/{id} via the assistant-ui
  // runtime, /api/health from the gate, /api/settings from the modal)
  // all fire end-to-end. Every one of these MUST hit the Next origin.
  const composer = page.locator('textarea[placeholder="Type a message…"]');
  await composer.waitFor({ state: "visible", timeout: 10_000 });
  await expect(composer).toBeEnabled({ timeout: 10_000 });
  await composer.fill("hello");
  await page.keyboard.press("Enter");

  // Wait for the full turn to complete.
  await page
    .locator('[aria-label*="Turn cost"]')
    .first()
    .waitFor({ timeout: 30_000 });

  // ===== KEY ASSERTION: zero non-origin browser requests =====
  expect(
    offendingRequests,
    `Browser MUST NOT open connections outside ${nextOriginHost}; saw: ${offendingRequests.join("; ")}`,
  ).toEqual([]);
});
