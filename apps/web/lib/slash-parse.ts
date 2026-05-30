// Phase 5 Plan 06 Wave 3 — slash-command parsing (UI-05, D-04).
//
// Client-side, compose-time parsing of the three override slash commands. A
// leading `/openrouter`, `/code`, or `/computer` token — followed by a space OR
// end-of-input — is stripped from the message text and mapped to the closed
// `override_backend` Literal mirrored on apps/api/routes/turn.py. Anything else
// (a non-slash message, an unknown slash command like `/explain`, or a prefix
// that is not a whole token like `/codex`) is left UNTOUCHED with backend=null.
//
// Contract (slash-parse.test.ts):
//   parseSlashCommand("/code build it")  → {backend:"claude_code", prompt:"build it"}
//   parseSlashCommand("/computer go")    → {backend:"computer_use", prompt:"go"}
//   parseSlashCommand("/openrouter q")   → {backend:"openrouter",  prompt:"q"}
//   parseSlashCommand("just a message")  → {backend:null,          prompt:"just a message"}
//   parseSlashCommand("/explain code")   → {backend:null,          prompt:"/explain code"}
//   parseSlashCommand("/codex run")      → {backend:null,          prompt:"/codex run"}
//   parseSlashCommand("/code")           → {backend:"claude_code", prompt:""}
//
// Cross-refs:
//   - apps/api/routes/turn.py (override_backend closed Literal)
//   - apps/web/tests/slash-parse.test.ts (the RED test this turns green)
//   - 05-CONTEXT.md D-04 (compose-time, client-side, strip-token)
//   - 05-UI-SPEC.md §9.1 (slash command table)

import type { Backend } from "@/lib/types";

// The token → backend map. The token MUST be matched as a whole word: it is
// only consumed when followed by a space or at end-of-input, so `/codex` does
// NOT match `/code` (UI-SPEC §9.1).
const SLASH_COMMANDS: Record<string, Backend> = {
  "/openrouter": "openrouter",
  "/code": "claude_code",
  "/computer": "computer_use",
};

export interface ParsedSlashCommand {
  /** The forced backend, or null when the text is not a known slash command. */
  backend: Backend | null;
  /** The prompt text with the command token stripped (unchanged when null). */
  prompt: string;
}

export function parseSlashCommand(text: string): ParsedSlashCommand {
  for (const [token, backend] of Object.entries(SLASH_COMMANDS)) {
    if (text === token) {
      // Bare command with no prompt → empty prompt (D-04).
      return { backend, prompt: "" };
    }
    if (text.startsWith(token + " ")) {
      // Token followed by a space — strip the token + the single delimiter
      // space; the remainder is the actual prompt.
      return { backend, prompt: text.slice(token.length + 1) };
    }
  }
  // Not a known slash command — leave untouched.
  return { backend: null, prompt: text };
}
