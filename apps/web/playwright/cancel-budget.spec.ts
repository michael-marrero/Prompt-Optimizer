// Plan 04-01 Wave-0 STUB. VALIDATION.md row: "UI-06".
// Plan 04-05 (Wave 3 — AbortController chain) overwrites this stub with the
// real performance.now() measurement that asserts elapsed < 2000ms from
// stop button click to the cancelled UI state. Mirrors the existing
// apps/api/tests/test_turn_streaming.py::test_cancellation_within_2s
// invariant on the browser layer (CONTEXT D-09).
import { test } from "@playwright/test";

test.skip(
  "UI-06: stop click cancels within 2s budget AND partial assistant message stays on screen",
  async () => {
    // Implemented by Plan 04-05.
  },
);
