// Plan 04-01 Wave-0 STUB. VALIDATION.md row: "UI-07 unit".
// Plan 04-04 (Wave 4 — MetricsFooter component) overwrites this stub with
// real RTL renders asserting the mid-stream "streaming●" + animate-pulse and
// the final "$0.0021 · 1.4s · 312↑/847↓" format per UI-SPEC §7.
import { describe, it } from "vitest";

describe("UI-07 unit — MetricsFooter", () => {
  it.todo(
    "UI-07: mid-stream state renders 'streaming●' with animate-pulse on the dot (UI-SPEC §7.1)",
  );
  it.todo(
    "UI-07: final state renders '$0.0021 · 1.4s · 312↑/847↓' formatted per UI-SPEC §7.2 table",
  );
  it.todo(
    "UI-07: cost <0.0001 floors to '$0.0001' (never shows mid-stream zero placeholder)",
  );
  it.todo("UI-07: latency <50ms shows '0.0s' (UI-SPEC §7.2 latency rule)");
  it.todo(
    "UI-07: token counts >=10000 use comma separator (UI-SPEC §7.2 token rule)",
  );
  it.todo(
    "UI-07: aria-label is the human prose 'Turn cost ..., latency ..., ... tokens in, ... tokens out'",
  );
});
