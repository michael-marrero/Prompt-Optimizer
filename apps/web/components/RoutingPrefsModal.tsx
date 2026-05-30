"use client";

// Phase 7 Plan 07-07 — Routing Preferences modal (L5 / D-03).
//
// The ONE settings surface the gear + top-bar Routing button open (D-03). Three
// sections with LOCKED copy (UI-SPEC §Copywriting) + a folded Keys/Backends
// section so BYOK key entry + computer-use opt-in live in the same place:
//   1. OPTIMIZE FOR — Priority segmented (toggle-group) · Show routing badge ·
//      Cost-aware fallback.
//   2. Allowed models · N of N — per-model toggles (display; the active routing
//      allowlist is per-backend, Phase 5 D-05, via the Backends section).
//   3. Privacy — Zero data retention.
//   + Keys & Backends — re-skinned KeyForm (openrouter + anthropic) + the
//     computer-use opt-in note.
//
// priority / cost_aware_fallback / zero_data_retention persist via the provider
// → PATCH /api/settings (Next proxy → FastAPI, UI-17). showBadge gates ONLY the
// auto optimized pill (RoutingChip 07-03); the D-08 override pill is unaffected.
// Keys ride KeyForm's dedicated POST path (never the prefs PATCH; SECURE-04).

import * as React from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { KeyForm } from "@/components/KeyForm";
import { useRoutingPrefs, type Priority } from "@/components/RoutingPrefsProvider";
import mapping from "@/lib/model-mapping.json";
import { cn } from "@/lib/utils";

type MappingEntry = {
  display_name?: string;
  provider?: string;
  api_model?: string | null;
};
const ROUTABLE = Object.entries(mapping as Record<string, MappingEntry>)
  .filter(([, e]) => e.provider === "openrouter" && e.api_model)
  .map(([slug, e]) => ({ slug, label: e.display_name ?? slug }));

const PRIORITIES: Priority[] = ["quality", "balanced", "speed", "cost"];

function Row({
  name,
  desc,
  children,
}: {
  name: string;
  desc: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <div className="min-w-0">
        <div className="text-[13.5px] font-medium text-[var(--ink)]">{name}</div>
        <div className="text-[12px] leading-[1.45] text-[var(--ink-3)]">{desc}</div>
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

function SectionHeading({ children }: { children: React.ReactNode }): React.JSX.Element {
  return (
    <div className="mb-1 mt-2 font-[var(--font-mono-plasma)] text-[10.5px] font-semibold uppercase tracking-[0.1em] text-[var(--ink-3)]">
      {children}
    </div>
  );
}

export function RoutingPrefsModal(): React.JSX.Element {
  const {
    open,
    closeRoutingPrefs,
    priority,
    setPriority,
    showBadge,
    setShowBadge,
    costAwareFallback,
    setCostAwareFallback,
    zeroDataRetention,
    setZeroDataRetention,
  } = useRoutingPrefs();

  // Per-model allowlist is display-only this phase (the active allowlist is
  // per-backend, D-05). Default all on; "N of N".
  const [allowed, setAllowed] = React.useState<Record<string, boolean>>(() =>
    Object.fromEntries(ROUTABLE.map((m) => [m.slug, true])),
  );
  const allowedCount = Object.values(allowed).filter(Boolean).length;

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? undefined : closeRoutingPrefs())}>
      <DialogContent className="w-full max-w-[calc(100%-2rem)] sm:max-w-[880px] max-h-[85vh] overflow-y-auto rounded-[14px] border-[var(--line)] bg-[var(--surface)] p-0">
        <div className="px-5 pt-5">
          <DialogHeader>
            <DialogTitle className="font-[var(--font-display)] text-[17px] font-semibold tracking-[-0.02em] text-[var(--ink)]">
              Routing preferences
            </DialogTitle>
            <DialogDescription className="sr-only">
              Bias routing, control the routing badge, allowed models, and privacy.
            </DialogDescription>
          </DialogHeader>
        </div>

        <div className="px-5 pb-5">
          {/* 1. OPTIMIZE FOR */}
          <SectionHeading>Optimize for</SectionHeading>
          <Row
            name="Priority"
            desc="Bias routing toward what matters most to you on each request."
          >
            <ToggleGroup
              type="single"
              value={priority}
              onValueChange={(v) => {
                if (v) setPriority(v as Priority);
              }}
              aria-label="Routing priority"
            >
              {PRIORITIES.map((p) => (
                <ToggleGroupItem key={p} value={p} aria-label={p}>
                  {p}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </Row>
          <Row
            name="Show routing badge"
            desc="Display which model answered after each response."
          >
            <Switch
              checked={showBadge}
              onCheckedChange={setShowBadge}
              aria-label="Show routing badge"
            />
          </Row>
          <Row
            name="Cost-aware fallback"
            desc="Use a cheaper model when the prompt is simple enough."
          >
            <Switch
              checked={costAwareFallback}
              onCheckedChange={setCostAwareFallback}
              aria-label="Cost-aware fallback"
            />
          </Row>

          <div className="my-2 h-px bg-[var(--line)]" />

          {/* 2. Allowed models · N of N */}
          <SectionHeading>
            Allowed models · {allowedCount} of {ROUTABLE.length}
          </SectionHeading>
          <div className="flex flex-col">
            {ROUTABLE.map((m) => (
              <Row key={m.slug} name={m.label} desc="OpenRouter">
                <Switch
                  checked={allowed[m.slug] ?? true}
                  onCheckedChange={(v) =>
                    setAllowed((prev) => ({ ...prev, [m.slug]: v }))
                  }
                  aria-label={`Allow ${m.label}`}
                />
              </Row>
            ))}
          </div>

          <div className="my-2 h-px bg-[var(--line)]" />

          {/* 3. Privacy */}
          <SectionHeading>Privacy</SectionHeading>
          <Row
            name="Zero data retention"
            desc="Route only to providers that don't retain prompt data."
          >
            <Switch
              checked={zeroDataRetention}
              onCheckedChange={setZeroDataRetention}
              aria-label="Zero data retention"
            />
          </Row>

          <div className="my-2 h-px bg-[var(--line)]" />

          {/* Folded Keys & Backends (D-03) */}
          <SectionHeading>Keys &amp; backends</SectionHeading>
          <div className={cn("flex flex-col gap-3 pt-1")}>
            <div>
              <div className="mb-1 text-[12.5px] font-medium text-[var(--ink-2)]">
                OpenRouter key
              </div>
              <KeyForm mode="settings" provider="openrouter" />
            </div>
            <div>
              <div className="mb-1 text-[12.5px] font-medium text-[var(--ink-2)]">
                Anthropic key
              </div>
              <KeyForm mode="settings" provider="anthropic" />
            </div>
            <p className="text-[12px] leading-[1.45] text-[var(--ink-3)]">
              Computer use can browse and act on web pages on your behalf. It is
              off by default — enable it in the Backends settings only when you
              understand the prompt-injection risk.
            </p>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
