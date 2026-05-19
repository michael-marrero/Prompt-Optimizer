// Plan 04-01 Wave-0 STUB. VALIDATION.md row: "UI-03".
// Plan 04-06 (Wave 4 — markdown + shiki integration) overwrites this stub
// with the real MutationObserver-based DOM-snapshot test per RESEARCH §Pattern 5
// (lines 778-829) that asserts the <pre><code> inner structure transitions
// EXACTLY ONCE per code block during streaming (no per-token re-highlight).
import { test } from "@playwright/test";

test.skip(
  "UI-03: code block highlights exactly once on fence close (no flicker / no per-token re-highlight)",
  async () => {
    // Implemented by Plan 04-06.
  },
);
