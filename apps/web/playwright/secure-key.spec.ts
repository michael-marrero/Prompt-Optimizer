// Plan 04-01 Wave-0 STUB. VALIDATION.md row: "D-18 belt".
// Plan 04-07 (Wave 4 — settings proxy) overwrites this stub with the real
// disclosure-regression test that posts a real-shaped key
// (sk-or-v1-XXXXXXXXXX...) then asserts ZERO literal-key matches across
// browser DevTools storage (cookies/localStorage/sessionStorage), every
// response body from /api/settings, /api/health, /api/chat, every response
// header, AND captured Next stdout/stderr. Mirrors the existing Python
// regression at apps/api/tests/test_secure_no_key_in_logs.py on the
// browser+Next surface.
import { test } from "@playwright/test";

test.skip(
  "D-18 belt: real-shaped OpenRouter key never appears in cookies, localStorage, sessionStorage, response bodies, response headers, or Next stdout",
  async () => {
    // Implemented by Plan 04-07.
  },
);
