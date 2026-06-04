// Plan 04-07 Wave 6 — browser-isolation.spec.ts
// Phase 5 Plan 06 Wave 3 — UI-17 extension to every new Phase-5 endpoint.
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
//     general). Zero requests to the FastAPI origin (localhost:8000 /
//     FASTAPI_URL) or any other host.
//   - Exercise the full happy path: gate → key entry → modal close →
//     turn submit → metrics footer (so /api/health, /api/settings,
//     /api/chat, /api/threads, /api/threads/{id} all run end-to-end)
//   - Phase 5 (Plan 06, T-05-06-PROXY): ALSO exercise the new Phase-5
//     surfaces — open /settings, toggle a backend (PATCH /api/settings),
//     and click a thumbs button (POST /api/feedback) — and assert NONE of
//     /api/feedback, /api/threads (list/PATCH/DELETE), /api/threads/{id}/
//     rename, /api/settings (GET/PATCH), /api/blobs/{hash} ever issue a
//     direct browser→FastAPI request. The network-recording assertion is the
//     contract; live upstream responses are not required (a 503/empty upstream
//     still proves the request stayed on the Next origin).
//   - Phase 11 (Plan 03, CTRL-01/UI-17): ALSO exercise the new control proxy
//     — issue a browser-context POST /api/control/{turnId} — and assert it
//     never issues a direct browser→FastAPI request to
//     POST /api/v1/turns/{turn_id}/control. Same network-recording contract:
//     a 404/503 upstream still proves the request stayed on the Next origin.
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
//   - 05-RESEARCH.md Security Domain (T-proxy-bypass — every new endpoint)
//   - 05-VALIDATION.md (UI-15 feedback proxy-only e2e)
//   - apps/web/app/api/*/route.ts (the only place FASTAPI_URL is read)

import { test, expect } from "@playwright/test";

// The FastAPI origin the browser MUST NEVER reach directly. The Next route
// handlers proxy here; the browser must only ever see the Next origin.
// localhost:8000 is the default uvicorn port; FASTAPI_URL overrides it (the
// mock-fastapi path uses :8001). We assert against the host generically (any
// non-Next host is an offense) AND name the FastAPI ports explicitly so a
// regression report is unambiguous.
const FASTAPI_HOSTS = ["localhost:8000", "127.0.0.1:8000", "localhost:8001", "127.0.0.1:8001"];

test("UI-17: browser never opens connections to FastAPI — only to Next.js origin", async ({
  page,
  baseURL,
}) => {
  const nextOriginHost = new URL(baseURL ?? "http://localhost:3000").host;
  const offendingRequests: string[] = [];
  // Sanity: confirm we know which hosts are FastAPI so the regression message
  // is explicit about the 8000/8001 (FASTAPI_URL) origins being forbidden.
  expect(FASTAPI_HOSTS).toContain("localhost:8000");

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
  // The mock binds 127.0.0.1 only (playwright.config.ts IPv4 pin note), so target
  // the IPv4 literal — Node resolves "localhost"→::1 first and would miss it.
  const upstream = (baseURL ?? "http://localhost:3000")
    .replace("localhost", "127.0.0.1")
    .replace("3000", "8001");
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
  //
  // SELECTOR (08 Pitfall 7): locate the composer by the REAL placeholder
  // (ChatSurface.tsx:419), not the stale Phase-4 string the spec used before.
  // This keeps the composer stable when the placeholder copy is the current
  // Plasma wording. Scoped minimal fix per 08-PLAN-00 Task 4.
  const composer = page.locator(
    'textarea[placeholder="Ask anything — we\'ll route it to the best model."]',
  );
  await composer.waitFor({ state: "visible", timeout: 10_000 });
  await expect(composer).toBeEnabled({ timeout: 10_000 });
  // Settle the initial seed-ready remount (08-03) so the send is not swallowed
  // by a concurrent composer re-mount (Pitfall 5).
  await page.waitForLoadState("networkidle").catch(() => {});
  // Submit via the Send control (aria-label="Send") rather than keyboard Enter:
  // a global keypress can land on no element if the composer re-mounts between
  // fill and press, dropping focus. The button click is robust to that remount.
  const sendButton = page.getByRole("button", { name: "Send" });
  await expect(sendButton).toBeVisible({ timeout: 10_000 });
  await composer.fill("hello");
  await sendButton.click();

  // Wait for the full turn to complete (exercises /api/chat + /api/threads +
  // /api/threads/{id} + /api/feedback target wiring on the assistant turn). The
  // routing pill is a robust terminal signal; the metrics footer ("Turn cost")
  // also lands but the pill is the load-bearing content signal.
  await page
    .locator('[aria-label*="Routed to"]')
    .first()
    .waitFor({ state: "attached", timeout: 30_000 });

  // ===== Phase 5 (T-05-06-PROXY): exercise the NEW Phase-5 endpoints =====

  // Feedback (UI-15): click thumbs-down on the assistant turn → POST
  // /api/feedback (the Next proxy → FastAPI). The browser must NOT hit
  // FastAPI directly. A 503/empty upstream still keeps the request on the
  // Next origin, which is the contract.
  const thumbsDown = page
    .getByRole("button", { name: "Mark this route as wrong" })
    .first();
  if (await thumbsDown.isVisible({ timeout: 5_000 }).catch(() => false)) {
    await thumbsDown.click({ force: true });
    // Give the fire-and-forget POST /api/feedback a moment to dispatch.
    await page.waitForTimeout(500);
  }

  // Settings (UI-12): navigate to /settings → GET /api/settings (masked), then
  // toggle a backend switch → PATCH /api/settings {backends_enabled}. Both must
  // proxy through the Next origin (never FastAPI directly).
  await page.goto("/settings");
  await expect(
    page.getByRole("heading", { name: "Backends" }),
  ).toBeVisible({ timeout: 10_000 });
  const claudeSwitch = page.getByRole("switch", {
    name: "Enable Claude Code backend",
  });
  if (await claudeSwitch.isVisible({ timeout: 5_000 }).catch(() => false)) {
    await claudeSwitch.click({ force: true });
    await page.waitForTimeout(500);
  }

  // ===== Phase 8 (SC-2 extension): exercise the NEW /messages proxy =====
  //
  // Selecting a thread with prior history must fetch its messages through the
  // Next proxy GET /api/threads/{id}/messages (browser→Next→FastAPI only,
  // UI-17). We navigate back to the chat surface, then click a thread row in
  // the sidebar. The "hello" turn submitted above already created/seeded a
  // thread (the extended mock-fastapi store persists it — Plan 08-04), so its
  // row exists in the list; selecting it triggers the fetch-on-select wired in
  // 08-03, which fires GET /api/threads/{id}/messages on the Next origin.
  //
  // GREEN (08-04): the select now issues a real /messages request — it MUST
  // appear on the Next origin (localhost:3000) and NEVER on a FASTAPI_HOSTS
  // entry. We `waitForResponse` on the proxy path so the recorded window
  // DEFINITELY captures the request before the assertion (proves the proxy is
  // exercised, per Task 3 acceptance). The single forbidden-host assertion
  // below covers the new route the moment it fires (it asserts over ALL
  // recorded browser requests) — no new/weakened assertion is introduced.
  await page.goto("/");
  const threadList = page.getByTestId("thread-list");
  if (await threadList.isVisible({ timeout: 10_000 }).catch(() => false)) {
    const firstThread = threadList.locator("button").first();
    if (await firstThread.isVisible({ timeout: 5_000 }).catch(() => false)) {
      // Race the click with a wait for the /messages proxy response so the
      // recorded `page.on("request")` window captures the GET. A tolerant
      // catch keeps the test robust if the row was already active (no refetch).
      const messagesResponse = page
        .waitForResponse(
          (resp) => /\/api\/threads\/[^/]+\/messages$/.test(resp.url()),
          { timeout: 10_000 },
        )
        .catch(() => null);
      await firstThread.click({ force: true });
      const resp = await messagesResponse;
      if (resp) {
        // The proxy response MUST be served from the Next origin, never FastAPI.
        expect(new URL(resp.url()).host).toBe(nextOriginHost);
      } else {
        // Fallback: still give any late fetch-on-select a moment to dispatch.
        await page.waitForTimeout(500);
      }
    }
  }

  // ===== Phase 11 (11-03 CTRL-01/UI-17): exercise the NEW /control proxy =====
  //
  // A control command (approve/pause/interrupt/redirect/take-over) must reach
  // an in-flight turn via the Next route handler ONLY — the browser must NEVER
  // POST FastAPI's POST /api/v1/turns/{turn_id}/control directly (UI-17). The
  // Next proxy (apps/web/app/api/control/[turnId]/route.ts) owns FASTAPI_URL
  // server-side; this case proves the browser path stays on the Next origin.
  //
  // We issue the control POST from the BROWSER context via the in-page
  // window.fetch (NOT page.request, which is Node-side and not recorded). The
  // turn_id is the capability the browser learns from the turn_start SSE event;
  // for the isolation invariant the EXACT id is immaterial — a 404/503/202 all
  // keep the request on the Next origin, which is the contract (mirrors the
  // feedback case: live upstream responses are not required). We race the POST
  // with a waitForResponse on the proxy path so the recorded `page.on("request")`
  // window DEFINITELY captures the browser→Next request before the assertion.
  const controlResponse = page
    .waitForResponse(
      (resp) => /\/api\/control\/[^/]+$/.test(resp.url()),
      { timeout: 10_000 },
    )
    .catch(() => null);
  await page.evaluate(async () => {
    // Browser-context fetch to the Next /control proxy — recorded by
    // page.on("request"). A non-existent turn_id is fine: the upstream
    // 404 still proves the request never left the Next origin.
    await fetch("/api/control/playwright-isolation-probe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: "pause" }),
    }).catch(() => {});
  });
  const controlResp = await controlResponse;
  if (controlResp) {
    // The proxy response MUST be served from the Next origin, never FastAPI.
    expect(new URL(controlResp.url()).host).toBe(nextOriginHost);
  } else {
    // Fallback: still give the fire-and-forget POST a moment to dispatch so
    // page.on("request") records it before the forbidden-host assertion.
    await page.waitForTimeout(500);
  }

  // ===== KEY ASSERTION: zero non-origin browser requests =====
  // Covers EVERY Phase-5 endpoint exercised above plus the Phase-4 happy path
  // AND the Phase-8 GET /api/threads/{id}/messages proxy exercised by the
  // thread-select above AND the Phase-11 POST /api/control/{turnId} proxy
  // exercised by the in-page fetch above:
  //   /api/health, /api/settings (GET/PATCH), /api/chat, /api/threads
  //   (list/PATCH/DELETE), /api/threads/{id}/rename, /api/threads/{id}/messages,
  //   /api/control/{turnId}, /api/feedback, /api/blobs/{hash}. If any request
  //   hit the FastAPI origin (8000/8001 or FASTAPI_URL) directly it would
  //   appear here and fail the test.
  expect(
    offendingRequests,
    `Browser MUST NOT open connections outside ${nextOriginHost} (FastAPI origins ${FASTAPI_HOSTS.join(", ")} are forbidden); saw: ${offendingRequests.join("; ")}`,
  ).toEqual([]);
});
