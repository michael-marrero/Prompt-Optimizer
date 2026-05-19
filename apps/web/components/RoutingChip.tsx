// Plan 04-05 Wave 4 — RoutingChip.
//
// UI-SPEC §6 — the color-coded chip that sits ABOVE every assistant message
// and announces which backend / model the router picked. UI-04 requires the
// chip to be visible on every assistant turn — never collapsed, never null
// when a `data-routing` part exists on the message.
//
// Data path (Plan 02 Wave 1 + Plan 04 Wave 3 + assistant-ui v0.14.5 conversion):
//   1. apps/api/routes/turn.py emits an SSE `event: routing_decision` as the
//      first yield (D-15 amendment). Payload is the STRUCTURED 5-key
//      RoutingDecision record: {backend, model_or_agent, rationale,
//      confidence, signals}.
//   2. apps/web/lib/sse-translate.ts forwards this as an AI SDK v6 chunk
//      `{type: "data-routing", data: <5-key>}`.
//   3. @assistant-ui/react-ai-sdk's convertMessage maps any AI SDK part whose
//      `type` starts with `data-` into a MessageState part of shape
//      `{type: "data", name: "routing", data: <RoutingDecision>}`
//      (see node_modules/@assistant-ui/react-ai-sdk/dist/ui/utils/convertMessage.js).
//   4. This component finds that part via `useMessage().parts.find(...)`
//      and renders the chip.
//
// IMPORTANT (Blocker 1 — Plan 05 revision iteration 1):
// The local variable is `routing` (NOT `signals`) because the part's `data`
// is the FULL RoutingDecision record. Reading `routing.backend`, `.model_or_agent`,
// `.rationale`, `.confidence` directly is safe — Plan 02's Zod schema enforces
// this shape at the wire boundary and the translator rejects malformed payloads.
//
// Cross-refs:
//   - apps/web/lib/types.ts (Backend + RoutingDecision)
//   - apps/web/lib/chunk-schemas.ts (RoutingDecisionDataSchema)
//   - config/model_mapping.json (display_name lookup — bundled, never fs.readFileSync)
//   - 04-UI-SPEC.md §6 (visual contract + ARIA + animation)
//   - 04-PATTERNS.md Pattern E (cn helper)
"use client";

import { useMessage } from "@assistant-ui/react";
import { cn } from "@/lib/cn";
import type { Backend, RoutingDecision } from "@/lib/types";
// Bundled JSON import (Pitfall 12 — never fs.readFileSync at request time;
// model_mapping.json is repo-committed source-of-truth keyed by benchmark slug).
import mapping from "../../../config/model_mapping.json";

// Backend → chip color class (UI-SPEC §6.3). Unknown backends fall back to
// the openrouter palette (graceful degradation, even though Plan 02's Zod
// schema rejects unknown backends at the wire boundary).
const chipClassByBackend: Record<Backend, string> = {
  openrouter: "bg-slate-100 text-slate-900 border-slate-200",
  claude_code: "bg-green-100 text-green-900 border-green-200",
  computer_use: "bg-amber-100 text-amber-900 border-amber-200",
};

type ModelMappingEntry = { display_name?: string };
const modelMapping = mapping as Record<string, ModelMappingEntry>;

// Minimal structural shape of a data part — `useMessage().parts` carries
// these alongside text / reasoning / tool parts. The MessageState type
// exported from @assistant-ui/core has TWO definitions in the package — the
// runtime/api one omits `parts`, the store/scopes one includes it. The
// runtime value DOES expose `parts` (see useMessage's JS source which reads
// the store state), so we treat the returned object as a structural type
// that carries `parts`.
type DataPart = { readonly type: "data"; readonly name: string; readonly data: unknown };
type PartLike = { readonly type: string };
type MessageStateWithParts = { readonly parts: ReadonlyArray<PartLike> };

function isRoutingPart(
  p: PartLike,
): p is DataPart & { readonly name: "routing"; readonly data: RoutingDecision } {
  return p.type === "data" && (p as { name?: string }).name === "routing";
}

export function RoutingChip(): React.JSX.Element | null {
  // useMessage is optional here so the chip doesn't crash if rendered outside
  // a MessagePrimitive context (e.g. in isolation during a Storybook story).
  // We cast through `unknown` because the @assistant-ui/core MessageState
  // type exported by the runtime API omits `parts` even though the runtime
  // value carries it.
  const message = useMessage({ optional: true }) as
    | MessageStateWithParts
    | null;
  // Find the data-routing part. assistant-ui converts AI SDK v6 `data-routing`
  // chunks into parts of shape {type:"data", name:"routing", data:<5-key>}.
  const routingPart = message?.parts?.find(isRoutingPart);

  if (!routingPart) return null;

  const routing = routingPart.data;
  const mappingEntry = modelMapping[routing.model_or_agent];
  const displayName = mappingEntry?.display_name ?? routing.model_or_agent;
  const colorClass =
    chipClassByBackend[routing.backend] ?? chipClassByBackend.openrouter;

  // UI-SPEC §6.2 — rationale truncates at 80 chars with ellipsis. The full
  // text lives in the title attribute so screen-reader users + hover users
  // both see the un-truncated string.
  const truncated =
    routing.rationale.length > 80
      ? routing.rationale.slice(0, 79) + "…"
      : routing.rationale;

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={`Routing decision: Routed to ${displayName}. ${routing.rationale}`}
      title={routing.rationale}
      className={cn(
        "inline-flex items-center gap-2 px-2 py-1 rounded-md border text-[13px] motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-top-1 motion-safe:duration-150",
        colorClass,
      )}
    >
      <span className="font-semibold">Routed to {displayName}</span>
      {" "}
      <span className="opacity-70">{"·"}</span>
      {" "}
      <span>{truncated}</span>
    </div>
  );
}
