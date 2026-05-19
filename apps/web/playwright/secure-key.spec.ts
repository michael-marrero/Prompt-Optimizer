// Plan 04-07 Wave 6 — secure-key.spec.ts
//
// VALIDATION.md row: D-18 belt (key never leaves the local API process).
//
// Test contract (PLAN must_haves + RESEARCH §Security Domain
// lines 1342-1349):
//   - Submit a real-shaped sk-or-v1-... key (48-character distinctive body)
//   - Assert ZERO occurrences of the literal key string across 6 channels:
//     (a) every captured response body (page.on('response') + resp.text())
//     (b) every captured response header value
//     (c) window.localStorage JSON-stringified
//     (d) window.sessionStorage JSON-stringified
//     (e) document.cookie
//     (f) every browser console message (page.on('console'))
//
// This is the end-to-end enforcement of D-18 spanning:
//   - Plan 02 api-client.ts.postSettings scrubKey (browser wrapper layer)
//   - Plan 03 /api/settings route handler .replace(key, '***') (Pattern G)
//   - Plan 05 chat surface (no logging anywhere)
//   - Plan 06 markdown renderer (no console output anywhere)
//   - Plan 07 KeyForm zero-console.* + storage-clean
//
// The threat model that drove this test (T-04-45/46/47/48/53):
//   - Information Disclosure via localStorage/sessionStorage/cookies
//   - Information Disclosure via console.log
//   - Information Disclosure via response body echo (a future regression
//     that removes the .replace(key, '***') scrub would leak)
//   - Information Disclosure via response header echo (e.g., a misguided
//     middleware that puts the request body into a header)
//   - FASTAPI_URL leak via NEXT_PUBLIC_* (browser-isolation.spec.ts is
//     the other side of this coin)
//
// Cross-refs:
//   - 04-CONTEXT.md D-18 (full key-handling rules + belt-and-suspenders)
//   - 04-RESEARCH.md §Security Test Plan lines 1344-1349
//   - 04-VALIDATION.md D-18 belt row

import { test, expect } from "@playwright/test";

test("D-18 belt: OpenRouter key never appears in response bodies, headers, storage, cookies, or console", async ({
  page,
  baseURL,
}) => {
  // 48 distinctive Q chars + the canonical sk-or-v1- prefix gives a
  // 57-char string that is extremely unlikely to appear in any other
  // content (the threat model T-04-58 acceptance).
  const SECRET_KEY = "sk-or-v1-" + "Q".repeat(48);
  const violations: string[] = [];

  // Reset mock-fastapi so this spec starts from a missing-key state.
  const upstream = (baseURL ?? "http://localhost:3000").replace("3000", "8001");
  await page.request.post(`${upstream}/__reset`).catch(() => {});

  // ----- Channel (a) + (b): response bodies + headers -----
  page.on("response", async (resp) => {
    const url = resp.url();
    try {
      // (b) headers
      const headers = resp.headers();
      for (const [name, val] of Object.entries(headers)) {
        if (val.includes(SECRET_KEY)) {
          violations.push(`HEADER ${name}=${val} (url: ${url})`);
        }
      }
      // (a) body — only attempt for same-origin (browser-isolation.spec
      // independently asserts there are NO cross-origin requests). The
      // narrowing here is defensive; this layer doesn't need to read
      // bytes from non-existent cross-origin responses.
      if (new URL(url).host === new URL(page.url() || "http://localhost:3000").host) {
        const text = await resp.text().catch(() => "");
        if (text.includes(SECRET_KEY)) {
          violations.push(`BODY (url: ${url})`);
        }
      }
    } catch {
      // ignore unreadable responses
    }
  });

  // ----- Channel (f): console messages -----
  page.on("console", (msg) => {
    const text = msg.text();
    if (text.includes(SECRET_KEY)) {
      violations.push(`CONSOLE [${msg.type()}] ${text.slice(0, 200)}`);
    }
  });

  await page.goto("/");

  // Wait for the modal (mock-fastapi starts in missing-key state after
  // the __reset call).
  const modalHeading = page.getByText("Connect OpenRouter to get started");
  await expect(modalHeading).toBeVisible({ timeout: 5_000 });

  // Enter the secret key.
  await page.getByLabel("OpenRouter API key").fill(SECRET_KEY);
  await page.getByRole("button", { name: "Save & continue" }).click();
  await expect(modalHeading).toBeHidden({ timeout: 5_000 });

  // Submit a turn so /api/chat is also exercised — a regression in the
  // chat route handler or AI SDK runtime that started echoing request
  // bodies would be caught here.
  const composer = page.locator('textarea[placeholder="Type a message…"]');
  await composer.waitFor({ state: "visible", timeout: 10_000 });
  await expect(composer).toBeEnabled({ timeout: 10_000 });
  await composer.fill("hello");
  await page.keyboard.press("Enter");

  // Wait for the full turn to land so every response has been captured.
  await page
    .locator('[aria-label*="Turn cost"]')
    .first()
    .waitFor({ timeout: 30_000 });

  // ----- Channels (c) (d) (e): browser storage -----
  const storageSnapshot = await page.evaluate(() => ({
    localStorage: JSON.stringify({ ...window.localStorage }),
    sessionStorage: JSON.stringify({ ...window.sessionStorage }),
    cookies: document.cookie,
  }));
  if (storageSnapshot.localStorage.includes(SECRET_KEY)) {
    violations.push(`localStorage`);
  }
  if (storageSnapshot.sessionStorage.includes(SECRET_KEY)) {
    violations.push(`sessionStorage`);
  }
  if (storageSnapshot.cookies.includes(SECRET_KEY)) {
    violations.push(`cookies`);
  }

  // ===== KEY ASSERTION: zero violations across all 6 channels =====
  expect(
    violations,
    `OpenRouter key leaked through: ${violations.join("; ")}`,
  ).toEqual([]);
});
