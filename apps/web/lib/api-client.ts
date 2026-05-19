// Same-origin typed API-client for the Next.js route handlers landed in
// Plan 04-03. EVERY URL is a `/api/*` path — the browser never talks to
// the upstream FastAPI service directly (UI-17 invariant). The server-
// only upstream-URL constant lives ONLY in apps/web/app/api/*/route.ts
// handlers (PATTERNS Pattern B); referencing it here would force a
// browser-exposed env prefix and leak the upstream URL into the bundle.
//
// D-18 belt-and-suspenders: postSettings catches every error path and
// scrubs the literal key from the thrown Error.message before re-throwing.
// This is defense-in-depth before the server-side scrub in Plan 04-03's
// /api/settings route handler — the regression test in api-client.test.ts
// proves the wrapper layer holds even if the route handler ever regresses.
//
// Cross-refs:
//   - 04-CONTEXT.md D-08 (body shape Next sends to FastAPI)
//   - 04-CONTEXT.md D-18 (key never leaks)
//   - 04-PATTERNS.md Pattern B (same-origin /api/* paths)
//   - apps/api/routes/health.py / settings.py / threads.py (upstream contracts)

import type { AdapterStatus } from "@/lib/types";

// --------------------------------------------------------------------
// Types
// --------------------------------------------------------------------

export interface MaskedKeyEntry {
  present: boolean;
  masked: string;
}

export interface SettingsResponse {
  keys: Record<string, MaskedKeyEntry>;
}

export interface HealthResponse {
  adapters: Record<string, { status: AdapterStatus }>;
}

export interface ThreadCreateResponse {
  id: string;
  title: string;
}

export interface ThreadDetailResponse {
  id: string;
  messages: unknown[];
}

export type SettingsProvider = "openrouter" | "anthropic";

// --------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------

/** Scrub a literal key string from any text. Used by the postSettings
 * error path so a thrown Error.message can never include the plaintext
 * key, even if the upstream response body or fetch error message echoed
 * it back (D-18 belt). Uses split+join (regex-free) so the key is never
 * interpreted as a pattern; equivalent to `text.replace(key, "***")` but
 * scrubs EVERY occurrence, not just the first one. */
function scrubKey(text: string, key: string): string {
  if (!key) return text;
  // String.prototype.split + join replaces every occurrence safely; this is
  // the canonical text.replace(key, "***") generalized to all matches.
  return text.split(key).join("***");
}

// --------------------------------------------------------------------
// Chat (streaming SSE — caller consumes Response.body)
// --------------------------------------------------------------------

export async function postChat(
  messages: unknown[],
  signal?: AbortSignal,
): Promise<Response> {
  return fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
    signal,
  });
}

// --------------------------------------------------------------------
// Settings (D-18: key NEVER appears in any thrown error message)
// --------------------------------------------------------------------

export async function postSettings(
  provider: SettingsProvider,
  key: string,
): Promise<SettingsResponse> {
  let response: Response;
  try {
    response = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider, key }),
    });
  } catch (err) {
    // Network error (ECONNREFUSED, DNS failure, etc). The error message
    // may contain the key if a runtime stringified the request body for
    // debugging. Scrub before re-throw.
    const original = err instanceof Error ? err.message : String(err);
    throw new Error(`postSettings failed: ${scrubKey(original, key)}`);
  }

  if (!response.ok) {
    // Read the body so the caller sees the upstream's error reason — but
    // scrub the key first (some FastAPI error serializers echo the
    // request body back).
    let body = "";
    try {
      body = await response.text();
    } catch {
      // Body unreadable — ignore.
    }
    const scrubbed = scrubKey(body, key);
    throw new Error(
      `postSettings failed (${response.status} ${response.statusText}): ${scrubbed}`,
    );
  }

  return (await response.json()) as SettingsResponse;
}

// --------------------------------------------------------------------
// Health (D-16 boot trigger)
// --------------------------------------------------------------------

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch("/api/health", { method: "GET" });
  if (!response.ok) {
    throw new Error(
      `getHealth failed (${response.status} ${response.statusText})`,
    );
  }
  return (await response.json()) as HealthResponse;
}

// --------------------------------------------------------------------
// Threads (default-thread auto-create + lazy fetch)
// --------------------------------------------------------------------

export async function postThread(
  title: string,
): Promise<ThreadCreateResponse> {
  const response = await fetch("/api/threads", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!response.ok) {
    throw new Error(
      `postThread failed (${response.status} ${response.statusText})`,
    );
  }
  return (await response.json()) as ThreadCreateResponse;
}

export async function getThread(id: string): Promise<ThreadDetailResponse> {
  const response = await fetch(`/api/threads/${encodeURIComponent(id)}`, {
    method: "GET",
  });
  if (!response.ok) {
    throw new Error(
      `getThread failed (${response.status} ${response.statusText})`,
    );
  }
  return (await response.json()) as ThreadDetailResponse;
}
