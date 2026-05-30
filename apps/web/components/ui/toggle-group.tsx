"use client"

// Phase 7 Plan 07-07 — shadcn toggle-group primitive (official registry shape,
// single-select) for the Routing Preferences modal's Priority segmented control.
// Scaffolds over the already-present `radix-ui` umbrella (no new external npm
// dependency; components.json registries stay {}). Self-contained — does not
// depend on a separate ui/toggle.tsx; item variants are inline Plasma tokens.

import * as React from "react"
import { ToggleGroup as ToggleGroupPrimitive } from "radix-ui"

import { cn } from "@/lib/utils"

function ToggleGroup({
  className,
  ...props
}: React.ComponentProps<typeof ToggleGroupPrimitive.Root>) {
  return (
    <ToggleGroupPrimitive.Root
      data-slot="toggle-group"
      className={cn(
        "inline-flex items-center gap-0.5 rounded-full bg-[var(--surface-2)] p-0.5",
        className,
      )}
      {...props}
    />
  )
}

function ToggleGroupItem({
  className,
  children,
  ...props
}: React.ComponentProps<typeof ToggleGroupPrimitive.Item>) {
  return (
    <ToggleGroupPrimitive.Item
      data-slot="toggle-group-item"
      className={cn(
        "inline-flex items-center justify-center rounded-full px-3 py-1 font-[var(--font-mono-plasma)] text-[10.5px] font-semibold uppercase tracking-[0.06em] text-[var(--ink-3)] outline-none transition-colors",
        "hover:text-[var(--ink)] focus-visible:shadow-[var(--shadow-focus)]",
        "data-[state=on]:bg-[var(--surface)] data-[state=on]:text-[var(--accent)] data-[state=on]:shadow-[var(--shadow-sm)]",
        className,
      )}
      {...props}
    >
      {children}
    </ToggleGroupPrimitive.Item>
  )
}

export { ToggleGroup, ToggleGroupItem }
