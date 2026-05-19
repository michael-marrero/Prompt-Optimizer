// Plan 04-07 Wave 6 — NetworkDownBanner.
//
// UI-SPEC §13 — the red banner rendered above the composer when
// `/api/health` is unreachable (proxy 503 or network failure). This is
// the SEPARATE surface from StreamErrorBanner: StreamErrorBanner is
// per-turn (UI-SPEC §12) and announces a single stream_error chunk;
// NetworkDownBanner is page-level and announces connectivity to the
// local FastAPI proxy.
//
// Polling contract (UI-SPEC §13 + Plan must_haves line 11):
//   - Mounts → calls getHealth() once
//   - Sets up a setInterval that re-polls every 5000ms
//   - Cleanup on unmount cancels the interval
//   - When getHealth() resolves → setOffline(false) (banner hidden)
//   - When getHealth() rejects → setOffline(true) (banner visible)
//
// Banner copy (UI-SPEC §17 byte-for-byte): "API unavailable — is uvicorn running?"
//   The em-dash is U+2014.
//
// Cross-refs:
//   - 04-UI-SPEC.md §13 (banner shape)
//   - 04-UI-SPEC.md §17 (canonical copy)
//   - apps/web/components/StreamErrorBanner.tsx (Plan 05 — separate surface)
//   - apps/web/lib/api-client.ts:getHealth (Plan 02 wrapper)

"use client";

import { useEffect, useState } from "react";
import type React from "react";
import { WifiOff } from "lucide-react";
import { getHealth } from "@/lib/api-client";

const POLL_INTERVAL_MS = 5000;

export function NetworkDownBanner(): React.JSX.Element | null {
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const check = async (): Promise<void> => {
      try {
        await getHealth();
        if (!cancelled) setOffline(false);
      } catch {
        if (!cancelled) setOffline(true);
      }
    };

    void check();
    const intervalId = setInterval(check, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, []);

  if (!offline) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="mx-auto max-w-3xl px-4 mb-2"
    >
      <div className="flex items-center gap-3 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-900">
        <WifiOff className="h-4 w-4 text-red-600" />
        <span>API unavailable — is uvicorn running?</span>
      </div>
    </div>
  );
}
