// localStorage-backed default-thread helper for Plan 04's minimal-mode
// single-thread UX (CONTEXT Claude's Discretion — "Thread creation in
// minimal mode"). Plan 05 will replace this with a full sidebar.
//
// SSR safety: readDefaultThreadId is callable from server components
// (returns null cleanly when typeof window === "undefined").
// getOrCreateDefaultThread WRITES to localStorage, so callers must invoke
// it from useEffect / event handlers (never directly in a server
// component body).
//
// D-18 hygiene comment: this module persists ONLY a non-secret thread id
// string. NEVER write key material here — keys live exclusively in
// FastAPI's KeyStore (Phase 3 D-10/D-11), never in browser storage.
//
// Cross-refs:
//   - 04-CONTEXT.md Claude's Discretion (default-thread key + UX)
//   - 04-PATTERNS.md (apps/web/lib/thread-id.ts "No Analog Found")
//   - apps/api/routes/threads.py (the upstream POST /api/v1/threads target)

import { postThread } from "@/lib/api-client";

/** Documented localStorage key — public so the secure-key Playwright spec
 * (Phase 4 E2E) can assert what IS allowed in storage and what is NOT. */
export const DEFAULT_THREAD_KEY = "prompt-optimizer.defaultThreadId";

/** SSR-safe localStorage read. Returns null when window is undefined
 * (server component body) or when no thread id has been cached yet. */
export function readDefaultThreadId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(DEFAULT_THREAD_KEY);
  } catch {
    // localStorage can throw in privacy mode or when the quota is full.
    // Treat as cache-miss; caller will re-create on next opportunity.
    return null;
  }
}

/** On first call (empty localStorage): POSTs to /api/threads, stores the
 * returned id, returns it. On subsequent calls: returns the cached value
 * WITHOUT a second POST. Must be invoked from a client context where
 * window is defined (useEffect, event handler, etc) — calling it during
 * SSR will fail in the localStorage write below.
 *
 * Plan 04's app boot calls this once from a top-level useEffect; Plan 05
 * replaces this with a sidebar that creates/selects/renames threads. */
export async function getOrCreateDefaultThread(): Promise<string> {
  const cached = readDefaultThreadId();
  if (cached) return cached;

  const { id } = await postThread("Untitled");
  // Defensive write — same try/catch as readDefaultThreadId. If
  // localStorage is unavailable the user simply re-creates a thread
  // every page load (degraded UX, no data loss).
  try {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(DEFAULT_THREAD_KEY, id);
    }
  } catch {
    // Persist failure: still return the id so the caller can use it for
    // this session.
  }
  return id;
}
