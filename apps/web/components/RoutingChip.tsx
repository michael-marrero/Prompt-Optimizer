// Plan 07-03 Wave 2 — RoutingChip: Plasma optimized pill (L1) + D-08 neutral override pill.
//
// L1 (LOCKED): routing is invisible-by-default. The always-visible slate/green/amber
// chip is REPLACED by a hover/focus-only "optimized" pill. The full rationale is
// carried on the pill's aria-label / title so AT users and hover users retain access
// (UI-SPEC §0.3 accessibility caveat).
//
// D-08: a manual-override turn (signals.override===true) renders a DISTINCT, neutral
// (non-accent) pill reading "manual override". This pill reflects explicit user intent
// and is NOT governed by L1 — it persists regardless of showBadge.
//
// showBadge gate: suppresses the AUTO optimized pill only. The manual-override pill
// always renders (UI-SPEC §Copywriting "showBadge semantics").
//
// Data path (UNCHANGED from Phase 4/5 — byte-for-byte preserved):
//   1. apps/api/routes/turn.py emits SSE `event: routing_decision`.
//   2. apps/web/lib/sse-translate.ts forwards as AI SDK v6 `{type:"data-routing"}`.
//   3. @assistant-ui/react-ai-sdk convertMessage maps to `{type:"data",name:"routing",data:<RoutingDecision>}`.
//   4. This component finds that entry via `useMessage().content.find(isRoutingPart)`.
//
// Cross-refs:
//   - apps/web/lib/types.ts (Backend + RoutingDecision)
//   - apps/web/lib/chunk-schemas.ts (RoutingDecisionDataSchema)
//   - config/model_mapping.json / apps/web/lib/model-mapping.json (R4: keep this import)
//   - 07-UI-SPEC.md §0.3, §Copywriting, §Color, §Typography
"use client";

import { useMessage } from "@assistant-ui/react";
import { cn } from "@/lib/cn";
import { useShowBadge } from "@/components/RoutingPrefsProvider";
import type { Backend, RoutingDecision } from "@/lib/types";
// Bundled JSON import (Pitfall 12 — never fs.readFileSync at request time).
// The canonical source-of-truth is repo-root config/model_mapping.json;
// apps/web/lib/model-mapping.json is a build-time mirror of that file
// (Turbopack rejects relative imports that traverse outside apps/web).
// Keep the two files in sync — update both, or wire a pre-build copy step.
import mapping from "@/lib/model-mapping.json";

type ModelMappingEntry = { display_name?: string };
const modelMapping = mapping as Record<string, ModelMappingEntry>;

// Backend → human display name fallback (UI-SPEC §9b / §17). The auto-route
// pill resolves the display name from config/model_mapping.json keyed by
// `model_or_agent`. Agent backends emit model_or_agent: "claude-code" /
// "computer-use" which have NO entry in model_mapping.json (only OpenRouter slugs).
const displayNameByBackend: Record<Backend, string> = {
  openrouter: "OpenRouter Auto Router",
  claude_code: "Claude Code",
  computer_use: "computer-use",
};

// Minimal structural shape of a data part. The chip reads from
// `useMessage().content` — the raw ThreadMessage content array carried
// through from the AI SDK runtime via assistant-ui's converter.
type DataPart = { readonly type: "data"; readonly name: string; readonly data: unknown };
type PartLike = { readonly type: string };
type MessageStateWithContent = { readonly content: ReadonlyArray<PartLike> };

function isRoutingPart(
  p: PartLike,
): p is DataPart & { readonly name: "routing"; readonly data: RoutingDecision } {
  return p.type === "data" && (p as { name?: string }).name === "routing";
}

interface RoutingChipProps {
  /** When false, the auto optimized pill is suppressed. The manual-override pill
   * still renders regardless (D-08: reflects explicit user intent, not router
   * rationale). Defaults to true if not provided. */
  showBadge?: boolean;
}

export function RoutingChip({ showBadge: showBadgeProp }: RoutingChipProps): React.JSX.Element | null {
  // showBadge resolution: an explicit prop wins (used by unit tests); otherwise
  // fall back to the RoutingPrefs context, which defaults to true when no
  // provider is mounted. Gates ONLY the auto optimized pill — the D-08
  // manual-override pill below ignores showBadge (07-07 wiring).
  const contextShowBadge = useShowBadge();
  const showBadge = showBadgeProp ?? contextShowBadge;
  // useMessage is optional here so the chip doesn't crash if rendered outside
  // a MessagePrimitive context (e.g. in isolation during a Storybook story).
  const message = useMessage({ optional: true }) as
    | MessageStateWithContent
    | null;
  // Find the data-routing part on the message's content array.
  // DATA PATH PRESERVED BYTE-FOR-BYTE from Phase 4/5 (isRoutingPart finds
  // p.type==="data" && p.name==="routing").
  const routingPart = message?.content?.find(isRoutingPart);

  if (!routingPart) return null;

  const routing = routingPart.data;
  const mappingEntry = modelMapping[routing.model_or_agent];
  // Auto-route display name: model_mapping.json keyed by `model_or_agent`,
  // falling back to the raw slug (UI-04 contract — unmapped OpenRouter slugs
  // render verbatim). UNCHANGED from Phase 4.
  const displayName = mappingEntry?.display_name ?? routing.model_or_agent;

  // D-08: manual-override branch (signals.override === true) — UNCHANGED data read.
  // Re-skinned from the Hand-icon chip to the neutral Plasma pill.
  const isOverride = routing.signals?.override === true;

  if (isOverride) {
    // Agent backends emit model_or_agent="claude-code" / "computer-use"
    // which have NO model_mapping.json entry; the backend-keyed fallback
    // resolves the §17 brand-cased name.
    const overrideName =
      mappingEntry?.display_name ??
      displayNameByBackend[routing.backend] ??
      routing.model_or_agent;

    // D-08 neutral pill: non-accent, --surface-2/--ink/--line palette,
    // reads "manual override". Persists regardless of showBadge.
    return (
      <span
        role="status"
        aria-live="polite"
        aria-label={`Manual override: forced to ${overrideName}`}
        title={`Manual override: forced to ${overrideName}`}
        className={cn(
          "inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] cursor-default select-none",
          "bg-[var(--surface-2)] text-[var(--ink-2)] border-[var(--line)]",
          "font-[var(--mono)]",
          "motion-safe:animate-in motion-safe:fade-in-0 motion-safe:duration-150",
        )}
      >
        manual override
      </span>
    );
  }

  // L1 AUTO pill: invisible-by-default, showBadge-gated.
  // When showBadge is false, suppress the auto optimized pill entirely.
  if (!showBadge) return null;

  // Plasma "optimized" pill:
  //   - Visible text: "optimized" (lowercase, JetBrains Mono 9.5px)
  //   - Accent text + dot on var(--accent-soft) bg
  //   - cursor: help (hover-to-reveal pattern)
  //   - aria-label + title: full "Routed to {model} — {reason}" (em-dash U+2014,
  //     FULL un-truncated rationale — UI-SPEC §0.3)
  const ariaLabel = `Routed to ${displayName} — ${routing.rationale}`;

  return (
    <span
      role="status"
      aria-live="polite"
      aria-label={ariaLabel}
      title={ariaLabel}
      className={cn(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-[var(--accent-soft)] cursor-help select-none",
        "bg-[var(--accent-soft)] text-[var(--accent)]",
        "font-[var(--mono)] text-[9.5px]",
        "motion-safe:animate-in motion-safe:fade-in-0 motion-safe:duration-150",
      )}
    >
      <span
        aria-hidden="true"
        className="h-[5px] w-[5px] rounded-full shrink-0 bg-[var(--accent)]"
      />
      optimized
    </span>
  );
}
