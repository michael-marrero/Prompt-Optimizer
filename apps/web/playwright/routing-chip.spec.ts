// Plan 04-01 Wave-0 STUB. VALIDATION.md row: "UI-04 E2E".
// Plan 04-04 (Wave 4 — chip integration) overwrites this stub with the real
// end-to-end test that submits a prompt, asserts the chip pops within ~100ms
// of POST (before the first text_delta), and stays visible through the full
// turn lifecycle until the next prompt is sent (UI-SPEC §6.4).
import { test } from "@playwright/test";

test.skip(
  "UI-04 E2E: routing chip pops within ~100ms of POST, before first text_delta, and stays visible after Done",
  async () => {
    // Implemented by Plan 04-04.
  },
);
