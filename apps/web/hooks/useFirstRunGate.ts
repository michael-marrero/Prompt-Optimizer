// Plan 04-07 Wave 6 — useFirstRunGate boot-time health gate hook.
//
// CONTEXT D-16 — two independent missing-key triggers route through the
// SAME first-run modal:
//   1. App boot: GET /api/health → adapters.openrouter.status === "missing_key"
//   2. Visibility refresh: user removed/added a key in another tab/process
//      and returned to the chat tab → re-fetch /api/health on visibilitychange
//      so the modal opens (or closes) without a manual reload
//
// CONTEXT D-19 — the post-entry unblock contract: after a successful
// PATCH /api/settings response (200), KeyForm dispatches a custom
// `pomu:key-saved` window event. This hook listens for that event and
// calls refresh() so /api/health is polled again, flipping needsKey to
// false. The chat surface (app/page.tsx) then opens the composer.
//
// Network failure semantics (PLAN must_haves line 1):
//   - Success path: openrouter.status === "ready"        → {isReady: true, needsKey: false}
//   - Success path: openrouter.status === "missing_key"  → {isReady: false, needsKey: true}
//   - Fetch reject (ECONNREFUSED / 503 / proxy error):    → {isReady: false, needsKey: false}
//     This network-down state is DISTINCT from missing-key — the
//     NetworkDownBanner is the surface for it, NOT the modal. If a
//     transient API outage flipped needsKey to true, the modal would
//     pop on every disconnect (UI noise + wrong remediation copy).
//
// The Phase 3 /api/v1/healthz contract (verified by reading
// apps/api/routes/health.py line 148-178):
//   {
//     "status": "ok" | "degraded",
//     "adapters": {
//       "openrouter":   {"status": <AdapterStatus>, "reason"?: string},
//       "claude_code":  {"status": <AdapterStatus>, "reason"?: string},
//       "computer_use": {"status": <AdapterStatus>, "reason"?: string}
//     },
//     ...
//   }
// The /api/health Next proxy is a verbatim passthrough on 200 and emits
// {error: "..."} on upstream/network failure with a non-2xx status —
// see apps/web/app/api/health/route.ts.
//
// Cross-refs:
//   - apps/api/routes/health.py lines 148-178 (upstream shape)
//   - apps/web/app/api/health/route.ts (proxy)
//   - apps/web/lib/api-client.ts:getHealth (typed wrapper)
//   - 04-CONTEXT.md D-16 (two missing-key triggers)
//   - 04-CONTEXT.md D-19 (post-entry unblock)

"use client";

import { useCallback, useEffect, useState } from "react";
import { getHealth } from "@/lib/api-client";

export interface FirstRunGateState {
  isReady: boolean;
  needsKey: boolean;
  refresh: () => Promise<void>;
}

interface InternalState {
  isReady: boolean;
  needsKey: boolean;
}

const INITIAL_STATE: InternalState = { isReady: false, needsKey: false };

export function useFirstRunGate(): FirstRunGateState {
  const [state, setState] = useState<InternalState>(INITIAL_STATE);

  const refresh = useCallback(async (): Promise<void> => {
    try {
      const body = await getHealth();
      const status = body.adapters?.openrouter?.status;
      setState({
        isReady: status === "ready",
        needsKey: status === "missing_key",
      });
    } catch {
      // Fetch failed — network down or proxy 503. NetworkDownBanner is
      // the surface for this state; we do NOT flip needsKey here
      // because the user can't fix a network outage by typing a key.
      setState({ isReady: false, needsKey: false });
    }
  }, []);

  useEffect(() => {
    void refresh();

    const onVisibility = (): void => {
      if (document.visibilityState === "visible") {
        void refresh();
      }
    };
    const onKeySaved = (): void => {
      void refresh();
    };

    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pomu:key-saved", onKeySaved);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pomu:key-saved", onKeySaved);
    };
  }, [refresh]);

  return { isReady: state.isReady, needsKey: state.needsKey, refresh };
}
