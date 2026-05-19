// Playwright config — multi-server webServer that spins up either
//   (a) the real uvicorn FastAPI on :8000 (default; matches RESEARCH Example 3)
//   (b) the mock-fastapi.py canned-SSE server on :8001 when USE_MOCK_FASTAPI=1
//       (CI-only path; no OpenRouter key needed — see threat T-04-03)
// plus `next dev` on :3000 in both cases. Tests target baseURL=:3000 and
// never observe FASTAPI_URL directly (UI-17 invariant).
import { defineConfig } from "@playwright/test";

const useMock = process.env.USE_MOCK_FASTAPI === "1";

const fastapiWebServer = useMock
  ? {
      command: "python apps/web/playwright/mock-fastapi.py --port 8001",
      port: 8001,
      cwd: "../../",
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    }
  : {
      command: "uvicorn apps.api.main:app --port 8000",
      port: 8000,
      cwd: "../../",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    };

// FASTAPI_URL gets pointed at whichever backend is active so the Next dev
// server's route handlers talk to the right port.
const FASTAPI_URL = useMock
  ? "http://localhost:8001"
  : "http://localhost:8000";

export default defineConfig({
  testDir: ".",
  testMatch: /.*\.spec\.ts/,
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
      cwd: "../",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
