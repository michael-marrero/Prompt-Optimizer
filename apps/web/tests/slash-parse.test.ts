// Phase 5 Wave 0 — slash-command parsing RED test suite (UI-05, D-04).
//
// VALIDATION.md row: "UI-05 unit" → `pnpm --dir apps/web test slash-parse`.
//
// RED-by-design: `@/lib/slash-parse` does NOT exist yet. The import fails to
// resolve so every `it` is collected and reported FAILED until the helper ships.
//
// Contract (D-04 — compose-time, client-side):
//   parseSlashCommand(text) maps a leading `/code `, `/computer `,
//   `/openrouter ` token to {backend, prompt:<rest>} and leaves non-slash text
//   untouched ({backend: null, prompt: text}). The backend values are the
//   closed Literal mirrored on turn.py's override_backend field.

import { describe, it, expect } from "vitest";
import { parseSlashCommand } from "@/lib/slash-parse";

describe("UI-05 unit — parseSlashCommand (D-04)", () => {
  it("D-04: '/code ' maps to {backend:'claude_code', prompt:<rest>}", () => {
    expect(parseSlashCommand("/code build me a finance app")).toEqual({
      backend: "claude_code",
      prompt: "build me a finance app",
    });
  });

  it("D-04: '/computer ' maps to {backend:'computer_use', prompt:<rest>}", () => {
    expect(parseSlashCommand("/computer open this URL and check the price")).toEqual({
      backend: "computer_use",
      prompt: "open this URL and check the price",
    });
  });

  it("D-04: '/openrouter ' maps to {backend:'openrouter', prompt:<rest>}", () => {
    expect(parseSlashCommand("/openrouter what is the capital of France?")).toEqual({
      backend: "openrouter",
      prompt: "what is the capital of France?",
    });
  });

  it("D-04: non-slash text is left untouched (backend null)", () => {
    expect(parseSlashCommand("just a normal message")).toEqual({
      backend: null,
      prompt: "just a normal message",
    });
  });

  it("D-04: a leading slash that is not a known command is NOT treated as an override", () => {
    expect(parseSlashCommand("/explain this code")).toEqual({
      backend: null,
      prompt: "/explain this code",
    });
  });

  it("D-04: the command token is stripped only when followed by a space or end-of-input", () => {
    // '/codex ...' is not '/code ' — must not match the claude_code command.
    expect(parseSlashCommand("/codex run the thing")).toEqual({
      backend: null,
      prompt: "/codex run the thing",
    });
  });

  it("D-04: a bare '/code' with no prompt yields an empty prompt", () => {
    expect(parseSlashCommand("/code")).toEqual({
      backend: "claude_code",
      prompt: "",
    });
  });
});
