import { cn } from "@/lib/utils"

// Phase 8 Plan 08-03 (D-02) token fix: the shadcn default ships the dead muted
// fill and a bare `animate-pulse`, but `--muted` / the muted Tailwind color is
// NOT defined in this project's Plasma `globals.css` (the token layer was fully
// replaced in Phase 7 — `grep --muted globals.css` → none), so that default
// resolves to a transparent/incorrect fill. The skeleton placeholder fill
// resolves to `--surface-2` (the neutral Plasma token used for hover backgrounds
// + chip fills) so it reads as a greyed bubble in every theme. The pulse is gated
// the project's established `motion-safe:` convention (RoutingChip.tsx:123,153,
// ComputerUseBubble.tsx:236) so `prefers-reduced-motion: reduce` renders a static
// block. The API is unchanged (08-UI-SPEC §Color skeleton token-fix note).
function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn(
        "motion-safe:animate-pulse rounded-md bg-[var(--surface-2)]",
        className,
      )}
      {...props}
    />
  )
}

export { Skeleton }
