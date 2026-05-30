// Phase 5 Plan 05 Wave 2 — auto-rename orchestration helper (UI-14, D-08/D-09/D-10).
//
// The single source of truth for the auto-rename behavior the sidebar /
// useThreads hook fires on the first user message of a fresh thread. The
// RED suite (apps/web/tests/auto-rename.test.ts) drives this helper directly.
//
// Behavior contract:
//   - D-08: POST /api/threads/{id}/rename with {first_user_message} — the
//     caller fires this in PARALLEL with the turn stream (does NOT await it
//     before sending the message). On a 200 the returned {title} is used.
//   - D-09: on a 400 (no OpenRouter key), a 413 (too long), a 404, or ANY
//     fetch/parse failure, fall back to the first user message truncated to
//     40 chars. If the message was longer than 40 chars a single-character
//     ellipsis (U+2026) is appended (so the returned title is 41 chars); a
//     message ≤40 chars is returned verbatim with no ellipsis.
//   - D-10: ONCE only, and only when the title is still the default/empty —
//     never overwrite a user-set or prior auto-title, and never fire on a
//     follow-up message. The guard short-circuits BEFORE any network call.
//
// The swap is silent — no toast, no row spinner (UI-SPEC §6.5). The caller
// updates the row title in place when this promise resolves.
//
// Cross-refs:
//   - apps/web/app/api/threads/[id]/rename/route.ts (the 05-03 proxy this calls)
//   - apps/api/routes/rename.py (upstream: openai/gpt-4o-mini, $0.01 cap)
//   - 05-CONTEXT.md D-08/D-09/D-10
//   - 05-UI-SPEC.md §6.5

// The set of titles treated as "still default" — auto-rename may fire only
// when the current title is one of these (or blank). A thread created with
// no explicit title lands as "Untitled" (or empty) until the first message.
const DEFAULT_TITLES = new Set(["", "Untitled", "New chat", "New Chat"]);

/** Truncate a first user message to a sidebar-safe title (D-09 fallback).
 * ≤40 chars → verbatim; >40 chars → first 40 chars + single ellipsis (U+2026). */
export function truncateFirstMessage(message: string): string {
  const trimmed = message.trim();
  if (trimmed.length <= 40) {
    return trimmed;
  }
  return trimmed.slice(0, 40) + "…";
}

/** True when `title` is the default/empty placeholder a fresh thread carries
 * (so auto-rename is allowed to run — D-10 guard). */
export function isDefaultTitle(title: string): boolean {
  return DEFAULT_TITLES.has(title.trim());
}

export interface MaybeAutoRenameArgs {
  /** The thread to rename. */
  threadId: string;
  /** The thread's current title — auto-rename only runs when this is default. */
  currentTitle: string;
  /** The first user message text (drives the rename + the truncation fallback). */
  firstUserMessage: string;
  /** True only for the very first user message of the thread (D-10 once-only). */
  isFirstUserMessage: boolean;
}

/**
 * Auto-rename a thread from its first user message (UI-14 / D-08/D-09/D-10).
 *
 * Returns the resolved title to display in the sidebar:
 *   - the cheap-model title on a 200,
 *   - the 40-char-truncated first message on 400/404/413/failure (D-09),
 *   - the existing title UNCHANGED when the D-10 guard blocks the rename
 *     (non-default title, or not the first user message) — no fetch fires.
 *
 * The caller is responsible for firing this in parallel with the turn (D-08)
 * and applying the returned title to the thread row when it resolves.
 */
export async function maybeAutoRenameThread({
  threadId,
  currentTitle,
  firstUserMessage,
  isFirstUserMessage,
}: MaybeAutoRenameArgs): Promise<string> {
  // D-10: once-only guard — never re-rename a user-set/prior-auto title, and
  // never fire on a follow-up. Short-circuit BEFORE any network call.
  if (!isFirstUserMessage || !isDefaultTitle(currentTitle)) {
    return currentTitle;
  }

  try {
    const response = await fetch(`/api/threads/${threadId}/rename`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ first_user_message: firstUserMessage }),
    });

    if (!response.ok) {
      // 400 (no key) / 404 (unknown thread) / 413 (too long) / any non-2xx →
      // D-09 truncation fallback.
      return truncateFirstMessage(firstUserMessage);
    }

    const data = (await response.json()) as { title?: string };
    if (typeof data.title === "string" && data.title.length > 0) {
      return data.title;
    }
    // Malformed 200 body with no usable title → still fall back.
    return truncateFirstMessage(firstUserMessage);
  } catch {
    // Network failure (ECONNREFUSED, DNS, parse error) → D-09 fallback.
    return truncateFirstMessage(firstUserMessage);
  }
}
