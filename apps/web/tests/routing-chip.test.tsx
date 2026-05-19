// Plan 04-01 Wave-0 STUB. VALIDATION.md row: "UI-04 unit".
// Plan 04-04 (Wave 4 — RoutingChip component) overwrites this stub with real
// RTL renders that mount <RoutingChip /> via a mocked useThreadMessage()
// providing a data-routing message part and asserts the chip text, color
// class per backend (slate / green / amber), and ARIA contract per UI-SPEC §6.
import { describe, it } from "vitest";

describe("UI-04 unit — RoutingChip", () => {
  it.todo(
    "UI-04: chip renders 'Routed to <display_name> · <rationale>' with display_name resolved via model_mapping.json",
  );
  it.todo(
    "UI-04: chip applies bg-slate-100 border-slate-200 for backend=openrouter (UI-SPEC §6.3)",
  );
  it.todo(
    "UI-04: chip applies bg-green-100 for backend=claude_code (Phase-5-ready)",
  );
  it.todo(
    "UI-04: chip applies bg-amber-100 for backend=computer_use (Phase-5-ready)",
  );
  it.todo(
    "UI-04: chip has role=status + aria-live=polite + aria-label='Routing decision: ...' (UI-SPEC §6.4)",
  );
  it.todo(
    "UI-04: chip renders null when no data-routing part is present on the message",
  );
});
