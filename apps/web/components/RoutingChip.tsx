// Story 7.2 (answer-forward redesign) — RoutingChip is now the SIGNATURE inline
// "why" element: `● {model} · why ▾` that expands a rationale panel showing what
// the brain did (task, what it picked, what it dispatched, calibrated confidence).
// This is the product's differentiator vs plain chat, and it surfaces the Epic 6
// work: the 6.1 degrade breadcrumb and the 6.2 confidence live right here.
//
// Data path UNCHANGED (byte-for-byte from Phase 4/5): SSE routing_decision →
// data-routing part → useMessage().content.find(isRoutingPart). AD-4 preserved:
// no new wire field — the panel reads the existing `signals` dict.
//
// D-08 override: a manual-override turn keeps the neutral "manual override" pill
// (explicit user intent, not a router rationale — no "why" to explain).
//
// Cross-refs: apps/web/lib/types.ts, lib/chunk-schemas.ts, 07-UI-SPEC.md.
"use client";

import { useState } from "react";
import { useMessage } from "@assistant-ui/react";
import { cn } from "@/lib/cn";
import { useShowBadge } from "@/components/RoutingPrefsProvider";
import type { Backend, RoutingDecision } from "@/lib/types";
import mapping from "@/lib/model-mapping.json";

type ModelMappingEntry = { display_name?: string };
const modelMapping = mapping as Record<string, ModelMappingEntry>;

const displayNameByBackend: Record<Backend, string> = {
  openrouter: "OpenRouter",
  claude_code: "Claude Code",
  computer_use: "Computer Use",
};

type DataPart = { readonly type: "data"; readonly name: string; readonly data: unknown };
type PartLike = { readonly type: string };
type MessageStateWithContent = { readonly content: ReadonlyArray<PartLike> };

function isRoutingPart(
  p: PartLike,
): p is DataPart & { readonly name: "routing"; readonly data: RoutingDecision } {
  return p.type === "data" && (p as { name?: string }).name === "routing";
}

// Known non-model sentinels that should render as the friendly backend name
// rather than the raw slug. Real OpenRouter model ids (e.g. "openai/gpt-5")
// contain a "/" too but are NOT sentinels — they render verbatim (UI-04).
const SENTINELS = new Set(["openrouter/auto", "computer_use/unavailable"]);

function resolveName(slug: string, backend: Backend): string {
  const mapped = modelMapping[slug]?.display_name;
  if (mapped) return mapped;
  // Agent backends emit sentinels ("claude-code", "computer_use/unavailable");
  // there is no real model id to show → use the backend name.
  if (backend !== "openrouter") return displayNameByBackend[backend] ?? slug;
  if (!slug || SENTINELS.has(slug)) return displayNameByBackend.openrouter;
  return slug; // real OpenRouter model id (mapped above, or verbatim)
}

interface RoutingChipProps {
  showBadge?: boolean;
}

export function RoutingChip({ showBadge: showBadgeProp }: RoutingChipProps): React.JSX.Element | null {
  const [open, setOpen] = useState(false);
  const contextShowBadge = useShowBadge();
  const showBadge = showBadgeProp ?? contextShowBadge;
  const message = useMessage({ optional: true }) as MessageStateWithContent | null;
  const routingPart = message?.content?.find(isRoutingPart);

  if (!routingPart) return null;

  const routing = routingPart.data;
  const signals = (routing.signals ?? {}) as Record<string, unknown>;
  const isOverride = signals.override === true;
  const displayName = resolveName(routing.model_or_agent, routing.backend);

  // ---- D-08 manual override: neutral pill, no "why" (user's explicit pick) ----
  if (isOverride) {
    return (
      <span
        role="status"
        aria-live="polite"
        aria-label={`Manual override: forced to ${displayName}`}
        title={`Manual override: forced to ${displayName}`}
        className={cn(
          "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[11px] cursor-default select-none",
          "bg-[var(--surface-2)] text-[var(--ink-2)] border-[var(--line)] font-[var(--mono)]",
        )}
      >
        <span aria-hidden className="h-[6px] w-[6px] rounded-full bg-[var(--ink-4)]" />
        manual override
      </span>
    );
  }

  // L1: auto pill suppressed when showBadge is off.
  if (!showBadge) return null;

  // ---- Epic-6-aware breadcrumbs for the panel ----
  const degradedFrom = signals.degraded_from as string | undefined;
  const degradedFromModel = signals.degraded_from_model as string | undefined;
  const rerErouteFrom = signals.rerouted_from as string | undefined;
  const blockedBackend = signals.blocked_backend as string | undefined;
  const lowConf = signals.low_confidence === true;
  const taskType = (signals.task_type as string | undefined) ?? "—";
  const agentic = signals.agentic_intent as string | undefined;
  const conf = typeof routing.confidence === "number" && Number.isFinite(routing.confidence)
    ? routing.confidence
    : null;

  const brainPicked = degradedFrom
    ? `${displayNameByBackend[degradedFrom as Backend] ?? degradedFrom}${degradedFromModel ? ` (${degradedFromModel})` : ""}`
    : rerErouteFrom
      ? displayNameByBackend[rerErouteFrom as Backend] ?? rerErouteFrom
      : displayName;

  const tag = degradedFrom
    ? "degraded → OpenRouter"
    : blockedBackend
      ? "browse blocked"
      : null;

  const ariaLabel = `Routed to ${displayName} — ${routing.rationale}`;

  return (
    <span className="inline-flex flex-col items-start">
      <button
        type="button"
        aria-label={ariaLabel}
        aria-expanded={open}
        title={ariaLabel}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "group inline-flex items-center gap-1.5 text-[12.5px] cursor-pointer select-none",
          "text-[var(--ink-2)] hover:text-[var(--ink)] transition-colors",
        )}
      >
        <span
          aria-hidden
          className={cn(
            "h-[7px] w-[7px] rounded-full shrink-0",
            lowConf ? "bg-[var(--warn)]" : "bg-[var(--accent)]",
          )}
        />
        <span className="font-semibold text-[var(--ink)]">{displayName}</span>
        {tag ? (
          <span className="font-[var(--mono)] text-[9px] uppercase tracking-[0.08em] text-[var(--accent)] bg-[var(--accent-soft)] px-1.5 py-[1px] rounded-full">
            {tag}
          </span>
        ) : null}
        <span className="inline-flex items-center gap-1 text-[var(--ink-3)]">
          · why
          <svg
            viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"
            className={cn("h-[11px] w-[11px] transition-transform", open && "rotate-180")}
            aria-hidden
          >
            <path d="M6 9l6 6 6-6" />
          </svg>
        </span>
      </button>

      {open ? (
        <div
          role="region"
          aria-label="Routing rationale"
          className={cn(
            "mt-2 mb-1 w-fit min-w-[280px] max-w-[520px] rounded-[var(--radius)] px-3.5 py-3",
            "bg-[var(--surface)] border border-[var(--line)] shadow-[var(--shadow-sm)]",
            "text-[12.5px] text-[var(--ink-2)]",
            "motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-top-1 motion-safe:duration-150",
          )}
        >
          <RationaleRow k="Task" v={agentic ? `${taskType} · ${agentic}` : taskType} />
          <RationaleRow k="Brain picked" v={brainPicked} />
          <RationaleRow
            k="Dispatched"
            v={`${displayNameByBackend[routing.backend] ?? routing.backend} — ${displayName}`}
          />
          {conf !== null ? (
            <div className="flex items-center gap-2 py-[3px]">
              <span className="font-[var(--mono)] text-[10px] uppercase tracking-[0.05em] text-[var(--ink-3)] min-w-[92px]">
                Confidence
              </span>
              <span className="inline-flex items-center gap-2">
                <span className="h-[4px] w-[70px] rounded-full bg-[var(--surface-2)] overflow-hidden">
                  <span
                    className={cn("block h-full rounded-full", lowConf ? "bg-[var(--warn)]" : "bg-[var(--good)]")}
                    style={{ width: `${Math.round(Math.max(0, Math.min(1, conf)) * 100)}%` }}
                  />
                </span>
                <span className="font-[var(--mono)] text-[11px] text-[var(--ink)]">{conf.toFixed(2)}</span>
                {lowConf ? <span className="text-[var(--warn)] text-[11px]">low</span> : null}
              </span>
            </div>
          ) : null}
        </div>
      ) : null}
    </span>
  );
}

function RationaleRow({ k, v }: { k: string; v: string }): React.JSX.Element {
  return (
    <div className="flex gap-2 py-[3px]">
      <span className="font-[var(--mono)] text-[10px] uppercase tracking-[0.05em] text-[var(--ink-3)] min-w-[92px]">
        {k}
      </span>
      <span className="text-[var(--ink)]">{v}</span>
    </div>
  );
}
