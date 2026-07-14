// Epic 5 / Story 5.2 — low-confidence override affordance (Story 5.1 Variant B).
//
// When a turn's calibrated route confidence is low, a subtle below-message nudge
// appears offering the EXISTING override path (FR-3) — it reuses OverrideDropdown
// bound to the same one-shot `setOverrideBackend` the composer uses, so picking a
// backend arms it for the resend (UJ-2). Never shows a raw % (Story 5.1 AC #1):
// the user sees an action, not a score.
//
// Contract:
//   - Triggers on the EXISTING `confidence` field (no new SSE member — AD-4). It
//     rides the live `routing_decision` event and is persisted (schema_v3), so a
//     reloaded thread renders this identically to the live stream (AD-7 parity).
//   - Renders nothing for above-threshold turns, manual overrides, or before the
//     turn completes → no regression to FR-7 (AC #3).
//
// Data read mirrors RoutingChip.tsx exactly (useMessage().content → data-routing).
//
// Cross-refs:
//   - apps/web/lib/confidence.ts (LOW_CONFIDENCE_THRESHOLD / isLowConfidence)
//   - apps/web/components/OverrideDropdown.tsx (the existing FR-3 path)
//   - apps/web/components/MessageBubble.tsx (mounts this below the bubble)
"use client";

import type React from "react";
import { useMessage } from "@assistant-ui/react";
import { OverrideDropdown } from "@/components/OverrideDropdown";
import { isLowConfidence } from "@/lib/confidence";
import type { Backend, RoutingDecision } from "@/lib/types";

type PartLike = { readonly type: string };
type DataPart = {
  readonly type: "data";
  readonly name: string;
  readonly data: RoutingDecision;
};
type MessageStateShape = {
  readonly content?: ReadonlyArray<PartLike>;
  readonly status?: { readonly type?: string };
};

function isRoutingPart(p: PartLike): p is DataPart {
  return p.type === "data" && (p as { name?: string }).name === "routing";
}
function isMetricsPart(p: PartLike): boolean {
  return p.type === "data" && (p as { name?: string }).name === "metrics";
}

export interface LowConfidenceNudgeProps {
  /** The currently-armed one-shot override backend (null = Auto). */
  overrideBackend: Backend | null;
  /** Arms the one-shot override for the next (re)send — the composer's setter. */
  onOverride: (backend: Backend | null) => void;
  /** Disables the computer-use item when computer-use is off (OverrideDropdown §9.2). */
  computerUseEnabled?: boolean;
}

export function LowConfidenceNudge({
  overrideBackend,
  onOverride,
  computerUseEnabled = false,
}: LowConfidenceNudgeProps): React.JSX.Element | null {
  const message = useMessage({ optional: true }) as MessageStateShape | null;
  const content = message?.content ?? [];

  const routingPart = content.find(isRoutingPart);
  if (!routingPart) return null;
  const routing = routingPart.data;

  // Manual-override turns already reflect explicit user intent — never nudge.
  if (routing.signals?.override === true) return null;
  // Only low-confidence auto routes (non-finite/missing confidence → no nudge).
  if (!isLowConfidence(routing.confidence)) return null;
  // Only after the turn completes, so the nudge never flashes mid-stream.
  const complete =
    message?.status?.type === "complete" || content.some(isMetricsPart);
  if (!complete) return null;

  return (
    <div
      role="note"
      aria-label="Low-confidence route — consider a different model"
      className="mt-2 flex items-center gap-3 border-l-2 border-[var(--warn)] pl-3 py-1"
    >
      <span className="text-[12.5px] text-[var(--ink-2)]">
        Close call on where to route this. Prefer a different model?
      </span>
      <OverrideDropdown
        value={overrideBackend}
        onChange={onOverride}
        computerUseEnabled={computerUseEnabled}
      />
    </div>
  );
}
