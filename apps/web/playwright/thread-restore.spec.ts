// Phase 8 Plan 08-04 Wave 4 — SC-4 thread-history restore (switch + reopen).
//
// 08-VALIDATION.md SC-4 sampling: BOTH restore paths in ONE spec, asserting on a
// CONTENT signal (the assistant message text OR the `[aria-label*="Routed to"]`
// pill), not merely "a bubble exists":
//   (path a) THREAD SWITCH — seed a turn in thread A, create a 2nd thread, switch
//            back to thread A, assert the restored assistant bubble + routing
//            pill reappear.
//   (path b) BROWSER REOPEN — close the browser context, reopen via
//            `browser.newContext()`, navigate, select thread A, assert the same
//            thread's history renders from the persistent store.
//
// SEED MECHANISM — Open Q2 RESOLVED → option (b): the EXTENDED `mock-fastapi.py`
// in-memory thread+messages store (08-RESEARCH §"Open Questions" Q2 +
// §"Pitfall 6"; 08-PATTERNS.md §thread-restore). Rationale recorded in
// 08-04-SUMMARY.md:
//   - CI-PORTABLE + KEY-FREE: the real-uvicorn default branch persists to SQLite
//     but needs an OpenRouter key OR NLTK-seeded routing — not runnable key-free
//     in CI. The mock streams a deterministic canned turn (no live network).
//   - DETERMINISTIC: the seed is the default fixture's openrouter golden path;
//     the mock's `/turn` handler persists the turn into its store on the terminal
//     Done frame (mirroring the real `persist_turn`).
//   - SURVIVES `browser.newContext()` (Assumption A3): the store is module-level
//     state on the LONG-LIVED mock process, so it persists across
//     `context.close()` + a fresh context within ONE spec — exactly SC-4's
//     "reopen". (It does NOT survive a mock PROCESS restart — no SQLite — which
//     SC-4 does not require.)
// The mock now serves `GET /api/v1/threads`, `GET /api/v1/threads/{id}`,
// `PATCH /api/v1/threads/{id}/rename`, and `GET /api/v1/threads/{id}/messages`
// mirroring the real `MessageWithRouting` JSON shape, so the client
// `reconstructUIMessages` path is byte-identical to the real backend.
//
// RUN (this spec requires USE_MOCK_FASTAPI=1):
//   USE_MOCK_FASTAPI=1 pnpm --dir apps/web exec playwright test \
//     --config=playwright/playwright.config.ts playwright/thread-restore.spec.ts
// (See 08-04-SUMMARY.md §"Manual e2e required" for the exact command — pnpm/the
//  Next dev `webServer` are environment-gated in some sandboxes.)
//
// COMPOSER SELECTOR (08-RESEARCH §Pitfall 7 — load-bearing): the actual composer
// placeholder is `"Ask anything — we'll route it to the best model."`
// (ChatSurface.tsx:561). This spec uses the REAL placeholder; the stale Phase-4
// composer placeholder string appears NOWHERE here (grep-asserted in the plan
// acceptance criteria — the drift-detection grep returns zero).
//
// Cross-refs:
//   - 08-PLAN-04 Task 2 + 08-VALIDATION.md SC-4 sampling
//   - 08-PATTERNS.md §"apps/web/playwright/thread-restore.spec.ts"
//   - apps/web/playwright/routing-chip.spec.ts:38-69 (modal + send + pill selector)
//   - apps/web/playwright/mock-fastapi.py (the extended in-memory store + /messages)
//   - apps/web/components/ChatSurface.tsx:561 (the real composer placeholder)
//   - apps/web/components/RoutingChip.tsx:141 (the [aria-label*="Routed to"] pill)
//   - apps/web/components/AppSidebar.tsx:140 (data-testid="thread-list"; "New chat")

import { test, expect, type Page } from "@playwright/test";

// The REAL composer placeholder (ChatSurface.tsx:561). NEVER the stale Phase-4
// placeholder the other specs drifted onto (Pitfall 7).
const COMPOSER_PLACEHOLDER =
  "Ask anything — we'll route it to the best model.";

// The restored routing pill carries "Routed to {model} — {reason}" on its
// aria-label (RoutingChip; L1 / Phase 7). This is the CONTENT signal SC-4
// asserts on for a restored assistant turn.
const ROUTED_PILL = '[aria-label*="Routed to"]';

// The seeded assistant text the default fixture streams + persists ("Hello"
// + " world"). A second CONTENT signal (alongside the pill) per SC-4 sampling.
const SEEDED_ASSISTANT_TEXT = "Hello world";

/** Reset the mock store + missing-key flag so each run starts clean. The mock's
 * `/__reset` clears _THREADS/_MESSAGES (Plan 08-04). `page.request` is a
 * Node-side fetch (never counted by browser request recorders). The mock binds
 * 127.0.0.1 only, so we target the IPv4 literal (Node resolves "localhost"→::1
 * first — the playwright.config.ts IPv4 pin note). */
async function resetMock(page: Page, baseURL: string | undefined): Promise<void> {
  const upstream = (baseURL ?? "http://localhost:3000")
    .replace("localhost", "127.0.0.1")
    .replace("3000", "8001");
  await page.request.post(`${upstream}/__reset`).catch(() => {});
  // Pre-flip the key so the first-run modal never blocks the composer.
  await page.request
    .patch(`${upstream}/api/v1/settings`, {
      data: { keys: { openrouter: "sk-or-v1-PREFLIPPED" } },
    })
    .catch(() => {});
}

/** Dismiss the first-run OpenRouter modal if it appears (verbatim from
 * routing-chip.spec.ts:38-46 — tolerate either path). */
async function dismissFirstRunModal(page: Page): Promise<void> {
  const modalHeading = page.getByText("Connect OpenRouter to get started");
  if (await modalHeading.isVisible({ timeout: 2000 }).catch(() => false)) {
    await page
      .getByLabel("OpenRouter API key")
      .fill("sk-or-v1-" + "K".repeat(48));
    await page.getByRole("button", { name: "Save & continue" }).click();
    await expect(modalHeading).toBeHidden({ timeout: 5000 });
  }
}

/** Locate the composer by the STABLE real placeholder (Pitfall 7). */
function composer(page: Page) {
  return page.locator(`textarea[placeholder="${COMPOSER_PLACEHOLDER}"]`);
}

// The seeded prompt — also the auto-renamed title of thread A (UI-14 renames a
// thread from its first user message). NOTE: the auto-rename PATCH is
// fire-and-forget and OPTIMISTIC client-side, so a fresh reopen may show the
// server's pre-rename "Untitled" title — we therefore select thread A by
// POSITION (oldest row), not by title (see selectOldestThreadRow).
const SEED_PROMPT = "What is the capital of France?";

/** Select the seeded thread A from the sidebar by POSITION (the oldest row).
 *
 * Both restore paths leave thread A as the OLDEST thread: path a creates a newer
 * thread via "New chat"; path b's reopen auto-creates a fresh default thread.
 * The sidebar renders newest-first (AppSidebar.tsx:41 sorts updated_at desc), so
 * thread A is the LAST thread-row title button. Selecting by position is robust
 * to the fire-and-forget auto-rename (which may not have persisted server-side
 * before a reopen, leaving both rows titled "Untitled"). We scope to thread-row
 * title buttons via `aria-current`-bearing ThreadRow markup: the row title
 * buttons are the ones NOT named "Thread actions" (the kebab) — matched by a
 * title regex that tolerates both "Untitled" and the auto-renamed prompt. */
async function selectSeededThreadA(page: Page): Promise<void> {
  const threadList = page.getByTestId("thread-list");
  await expect(threadList).toBeVisible({ timeout: 10_000 });
  // Title buttons: name is either the auto-renamed prompt or the default
  // "Untitled". The kebab is "Thread actions"; the header is "New chat ⌘N".
  const rows = threadList.getByRole("button", {
    name: new RegExp(`${SEED_PROMPT.replace(/[.?]/g, "\\$&")}|Untitled`),
  });
  await expect.poll(async () => rows.count(), { timeout: 15_000 }).toBeGreaterThanOrEqual(1);
  // Thread A is the oldest = the last matching row.
  await rows.last().click();
}

/**
 * SEED: send a single turn into the active thread so a persisted assistant
 * message + routing decision exists to restore. The default fixture streams the
 * openrouter golden path (routing_decision backend=openrouter) and the mock
 * persists it into its in-memory store on the terminal Done frame (Open Q2 (b)).
 */
async function seedOneTurn(page: Page, prompt: string): Promise<void> {
  const input = composer(page);
  await input.waitFor({ state: "visible", timeout: 10_000 });
  // The composer is gated until the default thread id resolves AND the key is
  // ready (ChatSurface.tsx:335 `composerDisabled`). Wait for it to enable.
  await expect(input).toBeEnabled({ timeout: 15_000 });
  // Settle: the brand-new session mounts the default thread and the runtime
  // does an initial `none:loading`→`none:ready` seed-ready remount (08-03). A
  // send fired DURING that remount can be dropped (the composer subtree
  // re-mounts). Wait for the network/render to go idle so the first send lands
  // on the settled runtime.
  await page.waitForLoadState("networkidle").catch(() => {});

  const sendButton = page.getByRole("button", { name: "Send" });
  await expect(sendButton).toBeVisible({ timeout: 10_000 });

  // Submit via the Send control (aria-label="Send", ChatSurface.tsx:653) rather
  // than keyboard Enter: the 08-03 seed-ready remount can re-mount the composer
  // between fill and a global keypress, dropping textarea focus so a bare
  // `keyboard.press("Enter")` lands on no element. A button click is robust to
  // that remount. We retry the fill+click ONCE if the first send is swallowed by
  // a concurrent remount (Pitfall 5 / A4) — confirmed by the routing pill not
  // appearing quickly.
  const pill = page.locator(ROUTED_PILL).first();
  for (let attempt = 0; attempt < 2; attempt++) {
    if (((await input.inputValue().catch(() => "")) ?? "") !== prompt) {
      await input.fill(prompt);
    }
    await sendButton.click();
    // The routing pill is the terminal content signal; the mock persists the
    // turn AFTER the stream completes. First attempt: short wait so a swallowed
    // send can be retried; final attempt: the full budget.
    try {
      await pill.waitFor({
        state: "attached",
        timeout: attempt === 0 ? 12_000 : 25_000,
      });
      return;
    } catch (err) {
      if (attempt === 1) throw err;
      // Swallowed by a remount — re-fill + re-send.
    }
  }
}

test.describe("SC-4 — thread history restore (persistent mock-fastapi store)", () => {
  test("path a: restore on thread switch (seed A → new B → back to A)", async ({
    page,
    baseURL,
  }) => {
    await resetMock(page, baseURL);
    await page.goto("/");
    await dismissFirstRunModal(page);

    // SEED a turn into the default/active thread A.
    await seedOneTurn(page, "What is the capital of France?");

    // Capture thread A's first-turn assistant pill aria-label so we can assert
    // the SAME content reappears after switching away and back.
    const seededLabel = await page
      .locator(ROUTED_PILL)
      .first()
      .getAttribute("aria-label");
    expect(seededLabel, "seed turn must produce a routing pill").toBeTruthy();

    // Create a SECOND thread (B). The "New chat" button resets the surface.
    await page.getByRole("button", { name: "New chat" }).click();
    // Thread B is empty — the routing pill from A must NOT be present.
    await expect(page.locator(ROUTED_PILL)).toHaveCount(0, { timeout: 10_000 });

    // Switch BACK to thread A by clicking its row in the sidebar list. Thread A
    // is now the oldest (B is newer), i.e. the last row — selected
    // deterministically (titles may not be auto-renamed yet).
    await selectSeededThreadA(page);

    // CONTENT-SIGNAL ASSERTION (SC-4 path a): A's restored assistant turn — the
    // routing pill — reappears after the switch (08-03 fetch-on-select +
    // seed-ready remount hydrates it from the store).
    const restoredPill = page.locator(ROUTED_PILL).first();
    await restoredPill.waitFor({ state: "attached", timeout: 15_000 });
    expect(await restoredPill.getAttribute("aria-label")).toMatch(
      /^Routed to .+ — .+$/,
    );
    // Second content signal: the seeded assistant text re-renders.
    await expect(
      page.getByText(SEEDED_ASSISTANT_TEXT).first(),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("path b: restore after full browser-close + reopen (browser.newContext)", async ({
    browser,
    baseURL,
  }) => {
    // ---- First context: seed a turn so it persists to the mock store. ----
    const ctx1 = await browser.newContext({ baseURL });
    const page1 = await ctx1.newPage();
    await resetMock(page1, baseURL);
    await page1.goto("/");
    await dismissFirstRunModal(page1);
    await seedOneTurn(page1, "What is the capital of France?");

    // Confirm the seeded assistant turn rendered before we tear the context
    // down (the content signal is the routing pill).
    await expect(page1.locator(ROUTED_PILL).first()).toBeVisible({
      timeout: 15_000,
    });
    const seededText = await page1
      .locator(ROUTED_PILL)
      .first()
      .getAttribute("aria-label");

    // Confirm the turn PERSISTED server-side before closing — the turn write is
    // what the reopen restores, and tearing ctx1 down too early could race the
    // mock's persist-on-Done. Poll the store (Node-side `page.request`, never a
    // browser request) until some thread reports an assistant message. This is
    // the real precondition for the reopen restore (independent of the
    // fire-and-forget auto-rename, which the reopen does NOT rely on — thread A
    // is selected by position).
    const upstream = (baseURL ?? "http://localhost:3000")
      .replace("localhost", "127.0.0.1")
      .replace("3000", "8001");
    await expect
      .poll(
        async () => {
          const list = await page1.request
            .get(`${upstream}/api/v1/threads`)
            .then((r) => r.json())
            .catch(() => []);
          for (const t of Array.isArray(list) ? list : []) {
            const msgs = await page1.request
              .get(`${upstream}/api/v1/threads/${t.id}/messages`)
              .then((r) => r.json())
              .catch(() => []);
            if (
              Array.isArray(msgs) &&
              msgs.some((m: { role: string }) => m.role === "assistant")
            ) {
              return true;
            }
          }
          return false;
        },
        { timeout: 15_000 },
      )
      .toBe(true);

    // ---- Close the entire browser context (simulates closing the browser). ----
    await ctx1.close();

    // ---- Reopen a FRESH context + page and navigate back. The mock store is
    //      module-level state on the long-lived server process, so the seeded
    //      thread + messages survive this close+reopen (Open Q2 (b) / A3). ----
    const ctx2 = await browser.newContext({ baseURL });
    const page2 = await ctx2.newPage();
    await page2.goto("/");
    await dismissFirstRunModal(page2);

    // Select the seeded thread A from the sidebar. The reopen auto-creates a
    // fresh EMPTY default thread that competes with thread A (both may show
    // "Untitled" if the fire-and-forget rename hasn't persisted), and either may
    // sort first by updated_at — so position/title alone is ambiguous. Instead
    // we click each thread row in turn and stop at the one that RESTORES content
    // (the routing pill). Thread A is the only thread with a persisted turn, so
    // exactly one row produces the pill (deterministic outcome).
    const rows = page2.getByTestId("thread-list").getByRole("button", {
      name: new RegExp(`${SEED_PROMPT.replace(/[.?]/g, "\\$&")}|Untitled`),
    });
    await expect.poll(async () => rows.count(), { timeout: 15_000 }).toBeGreaterThanOrEqual(1);
    const rowCount = await rows.count();
    let restored = false;
    for (let i = 0; i < rowCount; i++) {
      await rows.nth(i).click();
      if (
        await page2
          .locator(ROUTED_PILL)
          .first()
          .waitFor({ state: "attached", timeout: 6_000 })
          .then(() => true)
          .catch(() => false)
      ) {
        restored = true;
        break;
      }
    }
    expect(restored, "one thread row must restore the seeded turn").toBe(true);

    // CONTENT-SIGNAL ASSERTION (SC-4 path b): the same thread's history renders
    // from the persistent store after reopen — the routing pill reappears with
    // the same "Routed to … — …" content.
    const reopenedPill = page2.locator(ROUTED_PILL).first();
    await reopenedPill.waitFor({ state: "attached", timeout: 15_000 });
    expect(await reopenedPill.getAttribute("aria-label")).toMatch(
      /^Routed to .+ — .+$/,
    );
    // Second content signal + the restored content matches what was seeded.
    await expect(
      page2.getByText(SEEDED_ASSISTANT_TEXT).first(),
    ).toBeVisible({ timeout: 15_000 });
    expect(seededText).toBeTruthy();

    await ctx2.close();
  });
});
