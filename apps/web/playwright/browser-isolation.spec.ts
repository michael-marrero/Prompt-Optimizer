// Plan 04-01 Wave-0 STUB. VALIDATION.md row: "UI-17".
// Plan 04-03 (Wave 2 — proxy route handlers) overwrites this stub with the
// real page.on('request', ...) listener that asserts every browser request
// targets localhost:3000 (the Next origin) — NEVER localhost:8000 (FastAPI).
// Enforces the UI-17 invariant that BYOK keys never travel browser ↔ FastAPI
// directly. RESEARCH Architecture Diagram lines 365-371 documents the
// observable network panel state this test asserts.
import { test } from "@playwright/test";

test.skip(
  "UI-17: browser never opens connections to localhost:8000 — every request hits the Next origin",
  async () => {
    // Implemented by Plan 04-03.
  },
);
