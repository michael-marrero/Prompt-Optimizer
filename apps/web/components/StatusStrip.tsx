// Phase 5 Plan 06 Wave 3 — StatusStrip (UI-11, UI-SPEC §10).
//
// A row of three labeled dots in the header (§5.2 / §10.1), one per backend,
// reflecting per-adapter availability read from GET /api/health (the Phase 3
// healthz passthrough). Each dot maps an AdapterStatus to a color (§10.2):
//   ready       → bg-[var(--good)]
//   missing_key → bg-[var(--danger)]
//   error       → bg-[var(--danger)]
//   opt_out     → bg-[var(--ink-4)]   (computer-use disabled; neutral, not an error)
//
// Each dot+label group is `role="status" aria-label="{Backend} status: …"` so
// the meaning is carried by the accessible name, never by color alone (§10.2 /
// §14.1 — color is never the sole signal; the dot itself is aria-hidden). The
// exact §17 tooltip copy is rendered as the group's screen-reader text AND in a
// hover tooltip.
//
// Polling (§10.2 + §10.5): the strip reads /api/health on mount and re-polls
// every 5s while ANY dot is red — reusing the NetworkDownBanner cadence
// (POLL_INTERVAL_MS = 5000). When the component is given an explicit `statuses`
// prop (the RED test + storybook), it is a pure render of that prop and does
// NOT poll (the prop is the source of truth).
//
// Cross-refs:
//   - apps/web/components/NetworkDownBanner.tsx (5s poll-while-red cadence)
//   - apps/web/lib/api-client.ts:getHealth + apps/web/app/api/health/route.ts
//   - apps/web/lib/types.ts (AdapterStatus)
//   - apps/web/components/ui/tooltip.tsx
//   - 05-UI-SPEC.md §10 + §17
"use client";

import { useEffect, useState } from "react";
import type React from "react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { getHealth } from "@/lib/api-client";
import type { AdapterStatus } from "@/lib/types";

const POLL_INTERVAL_MS = 5000;

export type BackendKey = "openrouter" | "claude_code" | "computer_use";

export interface AdapterStatusEntry {
  status: AdapterStatus;
  reason?: string;
}

export type StatusMap = Record<BackendKey, AdapterStatusEntry>;

export interface StatusStripProps {
  /** When supplied, the strip is a pure render of this map and does NOT poll
   *  (the RED test + isolated rendering). When omitted, the strip polls
   *  /api/health on its own 5s-while-red cadence. */
  statuses?: StatusMap;
}

// §10.1 — the short backend names shown next to each dot.
const BACKEND_LABEL: Record<BackendKey, string> = {
  openrouter: "OpenRouter",
  claude_code: "Claude Code",
  computer_use: "computer-use",
};

// The order the three dots render in (§10.1).
const BACKEND_ORDER: readonly BackendKey[] = [
  "openrouter",
  "claude_code",
  "computer_use",
];

// §10.2 — AdapterStatus → dot color class.
function dotColorClass(status: AdapterStatus): string {
  switch (status) {
    case "ready":
      return "bg-[var(--good)]";
    case "missing_key":
    case "error":
      return "bg-[var(--danger)]";
    case "opt_out":
      return "bg-[var(--ink-4)]";
    default:
      // Defense-in-depth — an unknown status reads as unavailable.
      return "bg-[var(--danger)]";
  }
}

// §17 — the exact tooltip copy per (backend, status). The opt_out string is
// computer-use-specific per §17.
function tooltipCopy(backend: BackendKey, status: AdapterStatus): string {
  const label = BACKEND_LABEL[backend];
  switch (status) {
    case "ready":
      return `${label} ready`;
    case "missing_key":
      return `${label}: no API key — add one in settings`;
    case "error":
      return `${label}: availability check failed`;
    case "opt_out":
      return "Computer use is off — turn it on in settings";
    default:
      return `${label}: availability check failed`;
  }
}

// §10.2 — short status word used in the group aria-label.
function statusWord(status: AdapterStatus): string {
  switch (status) {
    case "ready":
      return "ready";
    case "opt_out":
      return "off";
    default:
      return "unavailable";
  }
}

const DEFAULT_STATUSES: StatusMap = {
  openrouter: { status: "missing_key" },
  claude_code: { status: "missing_key" },
  computer_use: { status: "opt_out" },
};

function StatusDot({
  backend,
  entry,
}: {
  backend: BackendKey;
  entry: AdapterStatusEntry;
}): React.JSX.Element {
  const label = BACKEND_LABEL[backend];
  const copy = tooltipCopy(backend, entry.status);

  return (
    <div
      role="status"
      aria-label={`${label} status: ${statusWord(entry.status)}`}
      className="flex items-center gap-1 text-[13px] text-[var(--ink-2)]"
    >
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-flex items-center gap-1">
            <span
              data-testid="status-dot"
              aria-hidden="true"
              className={`h-2 w-2 rounded-full ${dotColorClass(entry.status)}`}
            />
            <span>{label}</span>
          </span>
        </TooltipTrigger>
        <TooltipContent>{copy}</TooltipContent>
      </Tooltip>
      {/* The §17 copy is also rendered as always-present screen-reader text so
          the status meaning is available without hovering (the dot color is
          never the sole signal — §14.1). */}
      <span className="sr-only">{copy}</span>
    </div>
  );
}

export function StatusStrip({
  statuses,
}: StatusStripProps = {}): React.JSX.Element {
  const isControlled = statuses !== undefined;
  const [polled, setPolled] = useState<StatusMap>(DEFAULT_STATUSES);

  // Poll /api/health on mount + every 5s WHILE any dot is red. Only when
  // uncontrolled — a supplied `statuses` prop is the source of truth.
  useEffect(() => {
    if (isControlled) return;
    let cancelled = false;

    const read = async (): Promise<void> => {
      try {
        const health = await getHealth();
        if (cancelled) return;
        const adapters = (health.adapters ?? {}) as Record<
          string,
          { status?: AdapterStatus; reason?: string }
        >;
        setPolled({
          openrouter: {
            status: adapters.openrouter?.status ?? "error",
            reason: adapters.openrouter?.reason,
          },
          claude_code: {
            status: adapters.claude_code?.status ?? "error",
            reason: adapters.claude_code?.reason,
          },
          computer_use: {
            status: adapters.computer_use?.status ?? "error",
            reason: adapters.computer_use?.reason,
          },
        });
      } catch {
        if (cancelled) return;
        // Health unreachable — every backend reads as error (red) so the strip
        // signals the outage and the poll keeps running.
        setPolled({
          openrouter: { status: "error" },
          claude_code: { status: "error" },
          computer_use: { status: "error" },
        });
      }
    };

    void read();
    // Re-poll every 5s regardless of state — the dots stay live so a backend
    // going down (or a key landing) is reflected within the cadence window.
    const intervalId = setInterval(read, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, [isControlled]);

  const active = isControlled ? statuses! : polled;

  return (
    <TooltipProvider>
      <div className="flex items-center gap-3">
        {BACKEND_ORDER.map((backend) => (
          <StatusDot key={backend} backend={backend} entry={active[backend]} />
        ))}
      </div>
    </TooltipProvider>
  );
}
