// Phase 5 Plan 05 Wave 2 — useThreads hook (UI-02 + UI-14).
//
// Thread CRUD with optimistic UI + auto-rename orchestration. Loads the full
// thread list on mount via GET /api/threads (the 05-03 proxy; the FastAPI
// upstream already orders updated_at DESC per 05-01, so NO client re-sort).
// Exposes the create / select / rename / delete actions the AppSidebar binds
// to, plus autoRenameFromFirstMessage(threadId, firstUserMessage) which the
// page shell (05-06) fires in parallel with the first turn.
//
// Optimistic-UI contract (05-CONTEXT "Claude's Discretion"):
//   - createThread(): POST → optimistically prepend the new thread → select it.
//     On failure roll back + toast.error.
//   - renameThread(id, title): optimistic title swap → PATCH. Roll back + toast
//     on failure.
//   - deleteThread(id): optimistic remove → DELETE. When the deleted thread was
//     ACTIVE, select the most-recent remaining thread; if none remain, create +
//     select a fresh empty thread. Roll back + toast on failure.
//
// Auto-rename (UI-14, D-08/D-09/D-10): autoRenameFromFirstMessage delegates to
// maybeAutoRenameThread in @/lib/auto-rename — it POSTs /api/threads/{id}/rename
// in parallel, and on 400/404/413/failure falls back to the first user message
// truncated to 40 chars (msg.slice(0, 40) + ellipsis). The swap is silent (no
// toast, no row spinner — UI-SPEC §6.5). The once-only / default-title guard
// lives in the helper.
//
// Cross-refs:
//   - apps/web/hooks/useChatThread.ts (the active-thread-id coordination shape)
//   - apps/web/lib/auto-rename.ts (the rename helper — /rename + slice(0, 40))
//   - apps/web/app/api/threads/route.ts + [id]/route.ts + [id]/rename/route.ts
//   - 05-CONTEXT.md "Claude's Discretion" (order, active-delete, optimistic UI)
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  maybeAutoRenameThread,
  truncateFirstMessage,
} from "@/lib/auto-rename";

// A sidebar thread row. Mirrors the FastAPI thread CRUD shape (apps/api/routes/
// threads.py): the list endpoint returns {id, title, updated_at, created_at}.
export interface Thread {
  id: string;
  title: string;
  updated_at: string;
  created_at?: string;
}

export interface UseThreadsResult {
  threads: Thread[];
  activeThreadId: string | null;
  loading: boolean;
  selectThread: (id: string) => void;
  createThread: () => Promise<void>;
  renameThread: (id: string, title: string) => Promise<void>;
  deleteThread: (id: string) => Promise<void>;
  /** UI-14: auto-rename a thread from its first user message, in parallel with
   * the turn. Silently swaps the row title in place when it resolves. */
  autoRenameFromFirstMessage: (
    threadId: string,
    firstUserMessage: string,
  ) => Promise<void>;
}

const DEFAULT_TITLE = "New chat";

// --------------------------------------------------------------------
// API callers (every URL is a same-origin /api/* proxy — UI-17)
// --------------------------------------------------------------------

async function fetchThreads(): Promise<Thread[]> {
  const response = await fetch("/api/threads", { method: "GET" });
  if (!response.ok) {
    throw new Error(`GET /api/threads failed (${response.status})`);
  }
  const data = (await response.json()) as { threads?: Thread[] } | Thread[];
  // Upstream may return either a bare array or {threads: [...]}; accept both.
  return Array.isArray(data) ? data : (data.threads ?? []);
}

async function postThread(title: string): Promise<Thread> {
  const response = await fetch("/api/threads", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!response.ok) {
    throw new Error(`POST /api/threads failed (${response.status})`);
  }
  return (await response.json()) as Thread;
}

async function patchThreadTitle(id: string, title: string): Promise<void> {
  const response = await fetch(`/api/threads/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!response.ok) {
    throw new Error(`PATCH /api/threads/${id} failed (${response.status})`);
  }
}

async function deleteThreadRequest(id: string): Promise<void> {
  const response = await fetch(`/api/threads/${id}`, { method: "DELETE" });
  // 204 No Content is the success path; any other non-2xx is a failure.
  if (!response.ok && response.status !== 204) {
    throw new Error(`DELETE /api/threads/${id} failed (${response.status})`);
  }
}

// --------------------------------------------------------------------
// Hook
// --------------------------------------------------------------------

export interface UseThreadsOptions {
  /** IN-02: gate the mount fetch. When a fully-controlled caller (e.g.
   *  AppSidebar driven by PageShell) supplies its own thread data, it
   *  mounts this hook only to satisfy the unconditional-hooks rule and
   *  never reads `hook.threads`. Passing `enabled: false` suppresses the
   *  duplicate GET /api/threads that would otherwise fire on every
   *  controlled render tree. Defaults to `true` (self-managed). */
  enabled?: boolean;
}

export function useThreads(options: UseThreadsOptions = {}): UseThreadsResult {
  const enabled = options.enabled ?? true;
  const [threads, setThreads] = useState<Thread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  // When the fetch is disabled there is nothing to load — start settled.
  const [loading, setLoading] = useState<boolean>(enabled);

  // Tracks which threads have already auto-renamed (D-10 once-only belt — the
  // helper's default-title guard is the primary gate; this prevents a double
  // fire if the first message dispatches twice in a fast re-render).
  const renamedRef = useRef<Set<string>>(new Set());

  // Load the full list on mount. No client re-sort — upstream orders
  // updated_at DESC (05-01 / Pitfall 3). IN-02: skip entirely when the
  // hook is mounted only for hooks-rule compliance by a controlled caller.
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    void fetchThreads()
      .then((loaded) => {
        if (cancelled) return;
        setThreads(loaded);
        setActiveThreadId((current) => current ?? loaded[0]?.id ?? null);
      })
      .catch(() => {
        // FastAPI unreachable on mount — leave the list empty; the status
        // strip / network banner surfaces the outage. Sidebar stays usable.
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  const selectThread = useCallback((id: string) => {
    setActiveThreadId(id);
  }, []);

  const createThread = useCallback(async () => {
    let created: Thread;
    try {
      created = await postThread(DEFAULT_TITLE);
    } catch {
      toast.error("Couldn't create a new chat — is the local API running?");
      return;
    }
    // Optimistic prepend (newest-first) + select.
    setThreads((prev) => [created, ...prev]);
    setActiveThreadId(created.id);
  }, []);

  const renameThread = useCallback(
    async (id: string, title: string) => {
      let previousTitle = "";
      setThreads((prev) =>
        prev.map((thread) => {
          if (thread.id === id) {
            previousTitle = thread.title;
            return { ...thread, title };
          }
          return thread;
        }),
      );
      try {
        await patchThreadTitle(id, title);
      } catch {
        // Roll back the optimistic swap + toast.
        setThreads((prev) =>
          prev.map((thread) =>
            thread.id === id ? { ...thread, title: previousTitle } : thread,
          ),
        );
        toast.error("Couldn't rename the chat — is the local API running?");
      }
    },
    [],
  );

  const deleteThread = useCallback(
    async (id: string) => {
      // WR-03: capture only the row being removed (and its index) so the
      // rollback re-inserts it via a FUNCTIONAL update keyed off the
      // CURRENT state at await-resolution time. Restoring a whole captured
      // `snapshot` list would clobber any interleaved create/rename that
      // landed between the optimistic remove and the DELETE resolving.
      const wasActive = activeThreadId === id;
      const removedIndex = threads.findIndex((thread) => thread.id === id);
      const removedThread =
        removedIndex >= 0 ? threads[removedIndex] : undefined;
      const remaining = threads.filter((thread) => thread.id !== id);

      // Optimistic remove (functional — never clobbers concurrent updates).
      setThreads((prev) => prev.filter((thread) => thread.id !== id));

      // When the ACTIVE thread is deleted, select the most-recent remaining
      // thread (the list is already updated_at DESC, so remaining[0]); if none
      // remain, create + select a fresh empty thread (CONTEXT discretion).
      if (wasActive) {
        if (remaining.length > 0) {
          setActiveThreadId(remaining[0].id);
        } else {
          setActiveThreadId(null);
        }
      }

      try {
        await deleteThreadRequest(id);
      } catch {
        // Roll back the optimistic remove via a functional update: re-insert
        // the removed row at its original position into whatever the CURRENT
        // list is, so an interleaved create/rename is preserved. Guard
        // against a double-insert if the row somehow survived.
        if (removedThread !== undefined) {
          setThreads((prev) => {
            if (prev.some((thread) => thread.id === id)) return prev;
            const next = prev.slice();
            const insertAt = Math.min(
              removedIndex < 0 ? next.length : removedIndex,
              next.length,
            );
            next.splice(insertAt, 0, removedThread);
            return next;
          });
        }
        if (wasActive) setActiveThreadId(id);
        toast.error("Couldn't delete the chat — is the local API running?");
        return;
      }

      // Post-delete: if nothing remains, create a fresh empty thread to land in.
      if (wasActive && remaining.length === 0) {
        await createThread();
      }
    },
    [threads, activeThreadId, createThread],
  );

  const autoRenameFromFirstMessage = useCallback(
    async (threadId: string, firstUserMessage: string) => {
      // D-10 belt: skip if this thread already auto-renamed in this session.
      if (renamedRef.current.has(threadId)) return;

      const target = threads.find((thread) => thread.id === threadId);
      const currentTitle = target?.title ?? "";

      renamedRef.current.add(threadId);

      // Delegate the parallel POST /api/threads/{id}/rename + the D-09
      // first-message truncation fallback (msg.slice(0, 40)) to the helper.
      const resolvedTitle = await maybeAutoRenameThread({
        threadId,
        currentTitle,
        firstUserMessage,
        isFirstUserMessage: true,
      });

      // Silent in-place swap (no toast / no spinner — UI-SPEC §6.5). Belt for
      // an empty/whitespace message the helper would otherwise return blank:
      // fall back to the truncated first message directly.
      const nextTitle =
        resolvedTitle.length > 0
          ? resolvedTitle
          : truncateFirstMessage(firstUserMessage);

      setThreads((prev) =>
        prev.map((thread) =>
          thread.id === threadId ? { ...thread, title: nextTitle } : thread,
        ),
      );
    },
    [threads],
  );

  return {
    threads,
    activeThreadId,
    loading,
    selectThread,
    createThread,
    renameThread,
    deleteThread,
    autoRenameFromFirstMessage,
  };
}
