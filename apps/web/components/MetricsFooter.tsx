// Plan 04-05 Wave 4 — MetricsFooter.
//
// UI-SPEC §7 — the inline footer that sits BELOW every assistant message
// and shows turn cost + latency + token counts. UI-07 requires the footer
// to render a streaming placeholder mid-stream and a deterministic
// dollar/seconds/tokens line once the `data-metrics` part lands.
//
// Data path (Plan 02 Wave 1 + assistant-ui v0.14.5 conversion):
//   1. apps/api/routes/turn.py emits an SSE `event: done` at end-of-turn
//      with cost_usd / latency_ms / tokens_in / tokens_out (all nullable).
//   2. apps/web/lib/sse-translate.ts maps `done` to AI SDK v6
//      `{type: "data-metrics", data: <MetricsPayload>}`.
//   3. @assistant-ui/react-ai-sdk's convertMessage normalises the part to
//      `{type: "data", name: "metrics", data: <MetricsPayload>}`.
//   4. This component finds that part via `useMessage().parts.find(...)`.
//
// Format rules (UI-SPEC §7.2):
//   - cost is always `$X.XXXX` (4 decimals; 0 → $0.0000)
//   - latency is `X.Xs` (1 decimal); <50 ms displays as "0.0s"
//   - tokens are int; >= 10000 use comma separator (e.g. "12,847")
//
// Cross-refs:
//   - apps/web/lib/types.ts (MetricsPayload)
//   - apps/web/lib/sse-translate.ts (the data-metrics emission)
//   - 04-UI-SPEC.md §7 (visual contract + format rules + ARIA)
"use client";

import { useMessage } from "@assistant-ui/react";
import type { MetricsPayload } from "@/lib/types";

function formatCost(cost: number | null): string {
  const v = cost ?? 0;
  return `$${v.toFixed(4)}`;
}

function formatLatency(latencyMs: number | null): string {
  const latencySec = (latencyMs ?? 0) / 1000;
  // UI-SPEC §7.2 — sub-50ms always displays as "0.0s" so the user can't
  // confuse a stale state with a real measurement.
  if (latencySec < 0.05) return "0.0s";
  return `${latencySec.toFixed(1)}s`;
}

function formatTokens(n: number | null): string {
  const v = n ?? 0;
  if (v < 10_000) return String(v);
  return v.toLocaleString("en-US");
}

// Minimal structural shape — see RoutingChip.tsx for the same content
// vs parts rationale: assistant-ui v0.14.5's useMessage() returns the raw
// ThreadMessage with a `content` array (not `parts`). data-metrics chunks
// from the AI SDK v6 stream land as content entries of shape
// {type: "data", name: "metrics", data: <MetricsPayload>}.
type DataPart = { readonly type: "data"; readonly name: string; readonly data: unknown };
type PartLike = { readonly type: string };
type MessageStateWithContent = { readonly content: ReadonlyArray<PartLike> };

function isMetricsPart(
  p: PartLike,
): p is DataPart & { readonly name: "metrics"; readonly data: MetricsPayload } {
  return p.type === "data" && (p as { name?: string }).name === "metrics";
}

export function MetricsFooter(): React.JSX.Element {
  const message = useMessage({ optional: true }) as
    | MessageStateWithContent
    | null;
  const metricsPart = message?.content?.find(isMetricsPart);

  // Mid-stream placeholder — UI-SPEC §7.1. The animated dot communicates
  // "still streaming" while leaving room for the final layout to remain
  // structurally identical.
  if (!metricsPart) {
    return (
      <div
        aria-label="Streaming response in progress"
        className="text-xs font-mono text-slate-500 mt-2 flex items-center gap-1"
      >
        <span>streaming</span>
        <span aria-hidden="true" className="animate-pulse">
          ●
        </span>
      </div>
    );
  }

  const m = metricsPart.data;
  const cost = formatCost(m.cost_usd);
  const latency = formatLatency(m.latency_ms);
  const tokensIn = formatTokens(m.tokens_in);
  const tokensOut = formatTokens(m.tokens_out);

  return (
    <div
      className="text-xs font-mono text-slate-500 mt-2"
      aria-label={`Turn cost ${cost}, latency ${latency}, ${m.tokens_in ?? 0} tokens in, ${m.tokens_out ?? 0} tokens out`}
    >
      {cost} · {latency} · {tokensIn}↑/{tokensOut}↓
    </div>
  );
}
