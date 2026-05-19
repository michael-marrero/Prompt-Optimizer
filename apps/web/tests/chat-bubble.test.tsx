// Plan 04-01 Wave-0 STUB. VALIDATION.md row: "UI-08 unit".
// Plan 04-04 (Wave 4 — ChatBubble component) overwrites this stub with real
// RTL renders asserting markdown body styles, copy-as-markdown action that
// reads the raw source (not rendered HTML), and regenerate action that calls
// useChat.reload() per UI-SPEC §8.3 + CONTEXT D-14.
import { describe, it } from "vitest";

describe("UI-08 unit — ChatBubble", () => {
  it.todo(
    "UI-08: assistant bubble has bg-slate-50 border border-slate-200 rounded-lg p-4 max-w-prose (UI-SPEC §8.1)",
  );
  it.todo(
    "UI-08: action row is hidden by default, revealed on hover (group-hover:opacity-100)",
  );
  it.todo(
    "UI-08: copy button writes the RAW markdown source to clipboard (not rendered HTML)",
  );
  it.todo("UI-08: copy success fires the 'Copied to clipboard' toast (UI-SPEC §17)");
  it.todo(
    "UI-08: regenerate button calls useChat.reload() and APPENDS a new assistant turn (D-14)",
  );
  it.todo(
    "UI-08: timestamp renders from server-provided created_at (never client Date.now())",
  );
});
