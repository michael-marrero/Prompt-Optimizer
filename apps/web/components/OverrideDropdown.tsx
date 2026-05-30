// Phase 5 Plan 06 Wave 3 — OverrideDropdown (UI-05, UI-SPEC §9.2).
//
// A dropdown-menu trigger that sits LEFT of Send in the composer row. Default
// label is `Auto`; selecting a non-Auto item forces that backend for the NEXT
// turn only (D-02 one-shot — the page resets it to undefined after dispatch).
// The four items each carry the §17 label and (for the three backends) a
// leading identity-color swatch (§9.2 / §4.3 item #2 — the only new accent
// surface this phase):
//   Auto (let the router decide)  — neutral, no swatch
//   OpenRouter                    — bg-slate-400 dot
//   Claude Code                   — bg-green-500 dot
//   computer-use                  — bg-amber-500 dot
//
// The computer-use item is DISABLED (aria-disabled, text-slate-400) when
// computer-use is off; a tooltip on hover reads `Turn on computer use in
// settings` (§9.2 / §17). The trigger aria-label is §9.2:
//   "Override the routed backend (currently {Auto|backend})".
//
// Controlled: `value` is the current forced backend (null = Auto) and
// `onChange(backend|null)` is called on selection. The PAGE owns the one-shot
// reset (D-02) — it sets value=null after each send dispatches.
//
// Cross-refs:
//   - apps/web/components/ui/dropdown-menu.tsx, tooltip.tsx
//   - apps/web/hooks/useChatThread.ts (setOverrideBackend the page wires)
//   - apps/web/lib/types.ts (Backend)
//   - 05-UI-SPEC.md §9.2 + §17
"use client";

import type React from "react";
import { ChevronDown } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { Backend } from "@/lib/types";
import { cn } from "@/lib/cn";

export interface OverrideDropdownProps {
  /** The currently-forced backend, or null for Auto (the default). */
  value: Backend | null;
  /** Called when the user picks an item (null = Auto). */
  onChange: (backend: Backend | null) => void;
  /** When false, the computer-use item is disabled + tooltip-explained (§9.2).
   *  Read from the live health/settings state by the page. */
  computerUseEnabled?: boolean;
}

// §9.2 trigger label per value.
const TRIGGER_LABEL: Record<Backend | "auto", string> = {
  auto: "Auto",
  openrouter: "OpenRouter",
  claude_code: "Claude Code",
  computer_use: "computer-use",
};

interface BackendItem {
  backend: Backend;
  label: string;
  swatch: string;
}

// §9.2 item table — label + identity-color swatch (§4.3 item #2).
const BACKEND_ITEMS: readonly BackendItem[] = [
  { backend: "openrouter", label: "OpenRouter", swatch: "bg-slate-400" },
  { backend: "claude_code", label: "Claude Code", swatch: "bg-green-500" },
  { backend: "computer_use", label: "computer-use", swatch: "bg-amber-500" },
];

export function OverrideDropdown({
  value,
  onChange,
  computerUseEnabled = false,
}: OverrideDropdownProps): React.JSX.Element {
  const triggerLabel = TRIGGER_LABEL[value ?? "auto"];

  return (
    <TooltipProvider>
      <DropdownMenu>
        <DropdownMenuTrigger
          aria-label={`Override the routed backend (currently ${triggerLabel})`}
          className="h-8 px-2 rounded-[9px] border border-[var(--line)] bg-[var(--surface)] text-[12.5px] text-[var(--ink-2)] inline-flex items-center gap-1 hover:bg-[var(--surface-2)] focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]"
        >
          <span>{triggerLabel}</span>
          <ChevronDown aria-hidden="true" className="h-[14px] w-[14px]" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-56">
          {/* Auto (default) — neutral, no swatch. */}
          <DropdownMenuItem onSelect={() => onChange(null)}>
            <span className="text-[13px]">Auto (let the router decide)</span>
          </DropdownMenuItem>

          {BACKEND_ITEMS.map(({ backend, label, swatch }) => {
            const isComputer = backend === "computer_use";
            const disabled = isComputer && !computerUseEnabled;

            const item = (
              <DropdownMenuItem
                key={backend}
                disabled={disabled}
                aria-disabled={disabled || undefined}
                onSelect={(event) => {
                  if (disabled) {
                    event.preventDefault();
                    return;
                  }
                  onChange(backend);
                }}
                className={cn(disabled && "text-[var(--ink-4)]")}
              >
                <span
                  aria-hidden="true"
                  className={cn("h-2 w-2 rounded-full", swatch)}
                />
                <span className="text-[13px]">{label}</span>
              </DropdownMenuItem>
            );

            if (disabled) {
              // §9.2 — disabled computer-use item gets the §17 hover tooltip.
              return (
                <Tooltip key={backend}>
                  <TooltipTrigger asChild>
                    {/* A wrapper span keeps the tooltip target hoverable even
                        though the item itself is pointer-events:none when
                        disabled. */}
                    <span className="block">{item}</span>
                  </TooltipTrigger>
                  <TooltipContent>Turn on computer use in settings</TooltipContent>
                </Tooltip>
              );
            }
            return item;
          })}
        </DropdownMenuContent>
      </DropdownMenu>
    </TooltipProvider>
  );
}
