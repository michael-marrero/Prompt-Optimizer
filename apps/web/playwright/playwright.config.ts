// Playwright config — multi-server webServer that spins up either
//   (a) the real uvicorn FastAPI on :8000 (default; matches RESEARCH Example 3)
//   (b) the mock-fastapi.py canned-SSE server on :8001 when USE_MOCK_FASTAPI=1
//       (CI-only path; no OpenRouter key needed — see threat T-04-03)
// plus `next dev` on :3000 in both cases. Tests target baseURL=:3000 and
// never observe FASTAPI_URL directly (UI-17 invariant).
import { defineConfig } from "@playwright/test";
import { resolve } from "node:path";

const useMock = process.env.USE_MOCK_FASTAPI === "1";

// Plan 06-04 — local screenshot capture mode. capture-screenshots.capture.ts
// is a LOCAL authoring tool (writes docs/img/*.png), NOT a CI gate. Its
// `.capture.ts` suffix already escapes the default `testMatch: /.*\.spec\.ts/`,
// so the normal `pnpm test:e2e` run never discovers it. CAPTURE_SCREENSHOTS=1
// opts the `.capture.ts` files INTO testMatch so an explicit-path capture run
// resolves; when the flag is unset we additionally `testIgnore` them (a
// defensive double-guard — RESEARCH Pitfall 4).
const capturing = process.env.CAPTURE_SCREENSHOTS === "1";

// Playwright resolves `cwd` relative to the CONFIG file. The config lives
// at apps/web/playwright/playwright.config.ts, so we compute REPO_ROOT
// explicitly to avoid the "../../ = apps/" off-by-one trap.
const REPO_ROOT = resolve(__dirname, "../../..");

// Python executable detection — local dev uses repo-root .venv, CI
// typically has python3 on PATH. Override via PYTHON env if needed.
const PYTHON =
  process.env.PYTHON ??
  (process.env.CI ? "python3" : `${REPO_ROOT}/.venv/bin/python`);

const fastapiWebServer = useMock
  ? {
      command: `${PYTHON} ${REPO_ROOT}/apps/web/playwright/mock-fastapi.py --port 8001`,
      port: 8001,
      cwd: REPO_ROOT,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    }
  : {
      command: `${PYTHON} -m uvicorn apps.api.main:app --port 8000`,
      port: 8000,
      cwd: REPO_ROOT,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    };

// FASTAPI_URL gets pointed at whichever backend is active so the Next dev
// server's route handlers talk to the right port.
// Pin 127.0.0.1 literal: Node 18+ resolves "localhost" to ::1 first via
// dns.lookup, but mock-fastapi binds 127.0.0.1 only — see Plan 04-03's
// IPv4 deviation note. Without the pin, the Next route handler's upstream
// fetch silently fails the IPv6 connect attempt and returns empty body.
const FASTAPI_URL = useMock
  ? "http://127.0.0.1:8001"
  : "http://127.0.0.1:8000";

export default defineConfig({
  testDir: ".",
  // Normal runs match only `*.spec.ts`. In CAPTURE_SCREENSHOTS mode also match
  // `*.capture.ts` so the local screenshot tool is discoverable by explicit path.
  testMatch: capturing ? /.*\.(spec|capture)\.ts/ : /.*\.spec\.ts/,
  // Defensive double-guard: when NOT capturing, ignore the `.capture.ts`
  // authoring tool so it can never accidentally gate a CI run (Pitfall 4).
  testIgnore: capturing ? undefined : /.*\.capture\.ts/,
  fullyParallel: false,
  workers: 1,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },
  webServer: [
    fastapiWebServer,
    {
      command: `FASTAPI_URL=${FASTAPI_URL} pnpm dev --port 3000`,
      port: 3000,
      cwd: `${REPO_ROOT}/apps/web`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
