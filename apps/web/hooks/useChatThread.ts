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

import { useEffect, useRef, useState } from "react";
import type { AssistantRuntime } from "@assistant-ui/react";
import {
  AssistantChatTransport,
  useChatRuntime,
  type UseChatRuntimeOptions,
} from "@assistant-ui/react-ai-sdk";
import type { UIMessage } from "@ai-sdk/react";
import { getOrCreateDefaultThread } from "@/lib/thread-id";

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
}

export function useChatThread(): UseChatThreadResult {
  const [threadId, setThreadId] = useState<string | null>(null);
  // Ref so prepareSendMessagesRequest closes over the latest value without
  // having to re-create the transport on every re-render.
  const threadIdRef = useRef<string | null>(null);

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

  // Hooks must be called unconditionally — we always invoke useChatRuntime,
  // even before threadId is resolved. The transport injects the LATEST
  // threadId at request time via the ref closure.
  const transport = useRef(
    new AssistantChatTransport({
      api: "/api/chat",
      prepareSendMessagesRequest: ({ messages, body }) => ({
        body: { ...(body ?? {}), messages, threadId: threadIdRef.current },
      }),
    }),
  ).current;

  const options: ThrottleableOptions = {
    transport,
    experimental_throttle: 50,
  };

  const runtime = useChatRuntime(options);

  return { runtime, threadId };
}
