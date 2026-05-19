// Plan 04-01 Wave-0 STUB. VALIDATION.md rows: "UI-01 + UI-13".
// Plan 04-07 (Wave 4 — FirstRunModal + KeyForm) overwrites this stub with
// the real boot-trigger flow: GET /api/health → missing_key → modal opens →
// paste sk-or-v1-test → POST /api/settings → re-fetch /api/health → ready →
// modal closes → composer enables → user can send a turn (CONTEXT D-16..D-19).
import { test } from "@playwright/test";

test.skip(
  "UI-01 + UI-13: clone-to-first-turn — fresh boot shows blocking modal, key entry unblocks composer, first turn streams",
  async () => {
    // Implemented by Plan 04-07.
  },
);
