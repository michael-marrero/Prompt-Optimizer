// Plan 04-05 Wave 4 — useChatThread hook.
//
// RESEARCH §Pattern 1 — the canonical mount shape for the AI SDK v6 +
// assistant-ui chat surface. Wraps useChatRuntime + AssistantChatTransport
// with threadId injection from Plan 02's thread-id.ts helper.
//
// Behaviour:
//   - On first mount, calls getOrCreateDefaultThread() in a useEffect to
//     load (or create) the default thread id from localStorage. While the
//     id is still null the runtime sends requests with threadId=null —
//     the route handler returns 400 in that case; Plan 07's first-run
//     gate prevents this from being observable to the user.
//   - prepareSendMessagesRequest closes over the latest threadId via
//     useEffect-updated ref so a value resolved AFTER initial mount is
//     still injected on the next POST.
//   - experimental_throttle: 50 ms — RESEARCH Pattern 4 + Pitfall 4 (the
//     markdown re-render storm mitigation). The @assistant-ui/react-ai-sdk
//     type surface omits this option from UseChatRuntimeOptions (it lives
//     on @ai-sdk/react UseChatOptions), but the runtime spreads all extra
//     props into useChat() (see useChatRuntime.js). We cast through a
//     local type that adds the field so tsc strict stays clean.
//   - The Cancel/Stop button on the Composer primitive is automatically
//     wired to the runtime's stop action by @assistant-ui — no extra
//     code needed (RESEARCH Pitfall 3 partial-preserved is honored).
//
// Cross-refs:
//   - 04-RESEARCH.md §Pattern 1 (mount), §Pattern 3 (stop/reload),
//     §Pattern 4 (throttle), Pitfall 8 (use client)
//   - apps/web/lib/thread-id.ts (default-thread localStorage helper)
//   - apps/api/routes/turn.py (the upstream POST /api/v1/threads/{id}/turn
//     target which the route handler proxies — see Plan 04-03)
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { AssistantRuntime } from "@assistant-ui/react";
import {
  AssistantChatTransport,
  useChatRuntime,
  type UseChatRuntimeOptions,
} from "@assistant-ui/react-ai-sdk";
import type { UIMessage } from "@ai-sdk/react";
import { getOrCreateDefaultThread } from "@/lib/thread-id";
import type { Backend } from "@/lib/types";

// useChatRuntime's typed options surface omits `experimental_throttle`
// because it lives on @ai-sdk/react's UseChatOptions, not on the upstream
// ChatInit interface. The runtime spreads extra props into useChat() so
// the throttle value DOES flow through at runtime — we just need to
// satisfy tsc by widening the options shape locally.
type ThrottleableOptions = UseChatRuntimeOptions<UIMessage> & {
  experimental_throttle?: number;
};

export interface UseChatThreadResult {
  runtime: AssistantRuntime;
  threadId: string | null;
  /** Phase 5 (UI-05, D-02): force the backend for the NEXT turn only. The
   *  OverrideDropdown + slash-command parsing call this to set
   *  override_backend; it is injected into the next /api/chat body and reset
   *  to undefined immediately after the send dispatches (one-shot). Pass null
   *  to clear (Auto). */
  setOverrideBackend: (backend: Backend | null) => void;
  /** The currently-armed one-shot override (null = Auto). Mirrors the ref so
   *  the OverrideDropdown trigger label stays in sync. */
  overrideBackend: Backend | null;
}

// Phase 8 Plan 08-03 (D-06 / SC-3): the hook now accepts the sidebar-selected
// `activeThreadId` and the reconstructed `initialMessages` so a restored thread
// (a) seeds the runtime with its prior turns and (b) points the composer's next
// POST at the active/restored thread rather than the localStorage default.
//   - `initialMessages` is threaded into the runtime options as `messages` —
//     `useChatRuntime` spreads `...options` into `useChat` and `ChatInit.messages`
//     is a real field, so the seed lands in the rendered thread state (RESEARCH
//     §Pattern 2; GATED + PROVEN by the 08-00 spike — A1 PASS).
//   - `activeThreadId` is synced into `threadIdRef` via a `[activeThreadId]`
//     effect (Pitfall 4 / D-06). The existing `prepareSendMessagesRequest` reads
//     `threadIdRef.current`, so the next POST picks up the synced id through the
//     ref closure with NO transport recreation. ChatSurface also remounts this
//     hook with `key={activeThreadId}`, so the ref re-initializes per thread
//     anyway — the effect is the belt for an id change within a single mount.
//   - When `activeThreadId` is null (a brand-new session), the existing
//     `getOrCreateDefaultThread` first-mount effect still provides the default
//     thread, so a fresh chat is unaffected (fallback intact).
export function useChatThread(
  activeThreadId?: string | null,
  initialMessages?: UIMessage[],
): UseChatThreadResult {
  const [threadId, setThreadId] = useState<string | null>(null);
  // Ref so prepareSendMessagesRequest closes over the latest value without
  // having to re-create the transport on every re-render.
  const threadIdRef = useRef<string | null>(null);

  // Phase 5 (UI-05, D-02) — the one-shot forced backend. The ref is read inside
  // prepareSendMessagesRequest (which closes over it once) so a value set
  // between renders is still injected on the next POST; the `overrideBackend`
  // state mirrors it for the OverrideDropdown trigger label.
  const overrideRef = useRef<Backend | null>(null);
  const [overrideBackend, setOverrideBackendState] = useState<Backend | null>(
    null,
  );
  const setOverrideBackend = useCallback((backend: Backend | null): void => {
    overrideRef.current = backend;
    setOverrideBackendState(backend);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void getOrCreateDefaultThread()
      .then((id) => {
        if (!cancelled) {
          threadIdRef.current = id;
          setThreadId(id);
        }
      })
      .catch(() => {
        // getOrCreateDefaultThread can fail when the FastAPI backend isn't
        // reachable. Plan 07's first-run modal surfaces this; here we just
        // leave threadId as null and the Composer remains visible (sends
        // will produce a 400 until the modal saves a key + auto-creates).
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // D-06 (Pitfall 4) — point the transport's thread id at the sidebar-selected
  // `activeThreadId` so the composer's next POST continues the active/restored
  // thread, not the localStorage default. Mirrors the first-mount effect shape
  // (`threadIdRef.current = id; setThreadId(id)`). The ref closure means
  // prepareSendMessagesRequest (line ~138, `threadId: threadIdRef.current`)
  // picks this up on the next send with no transport recreation. When
  // `activeThreadId` is null we leave the default-thread fallback above in
  // control (so a brand-new session keeps its default thread).
  useEffect(() => {
    if (activeThreadId) {
      threadIdRef.current = activeThreadId;
      setThreadId(activeThreadId);
    }
  }, [activeThreadId]);

  // Hooks must be called unconditionally — we always invoke useChatRuntime,
  // even before threadId is resolved. The transport injects the LATEST
  // threadId at request time via the ref closure.
  const transport = useRef(
    new AssistantChatTransport({
      api: "/api/chat",
      prepareSendMessagesRequest: ({ messages, body }) => {
        // Inject the one-shot override_backend alongside threadId, then reset
        // the ref so the override applies to EXACTLY this turn (D-02). The
        // chat proxy (05-03) only forwards override_backend when it is a
        // non-empty string, so omitting it (undefined) keeps auto-routing.
        const override = overrideRef.current;
        overrideRef.current = null;
        // Mirror the reset into state so the dropdown trigger snaps back to
        // Auto after dispatch. Scheduled async to avoid a setState-in-render
        // warning from the transport call site.
        // WR-04: guard the mirror on the ref STILL being null at microtask
        // time. If the user re-arms an override between this synchronous
        // reset and the microtask running, an unconditional
        // setOverrideBackendState(null) would clobber the freshly-armed
        // value (label snaps to "Auto" while the next send still forces the
        // armed backend — state and ref transiently disagree).
        if (override !== null) {
          queueMicrotask(() => {
            if (overrideRef.current === null) setOverrideBackendState(null);
          });
        }
        return {
          body: {
            ...(body ?? {}),
            messages,
            threadId: threadIdRef.current,
            ...(override ? { override_backend: override } : {}),
          },
        };
      },
    }),
  ).current;

  // Seed the runtime with the reconstructed history when present (08-03 / D-04).
  // `useChatRuntime` spreads `...options` into `useChat`, and `ChatInit.messages`
  // is a real field, so the seeded `messages` array becomes the initial thread
  // state and the prior turns render through the unchanged bubbles (RESEARCH
  // §Pattern 2; A1 spike PASS). The conditional spread keeps a brand-new thread
  // (no `initialMessages`) on the exact pre-08-03 options shape. The
  // `key={activeThreadId}` remount in ChatSurface re-runs this hook per thread,
  // so each thread select re-seeds atomically from the freshly-fetched rows.
  const options: ThrottleableOptions = {
    transport,
    experimental_throttle: 50,
    ...(initialMessages ? { messages: initialMessages } : {}),
  };

  const runtime = useChatRuntime(options);

  return { runtime, threadId, setOverrideBackend, overrideBackend };
}
