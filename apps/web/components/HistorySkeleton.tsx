// Phase 8 Plan 08-03 Wave 3 — HistorySkeleton (the one net-new visual, D-02).
//
// The loading bridge shown inside ChatSurface's ThreadPrimitive.Viewport while a
// selected thread's persisted history is fetched + reconstructed (08-UI-SPEC
// §"New Visual Element — Skeleton Loading State"). D-04's abort-on-switch + the
// per-thread `key={activeThreadId}` remount unmount the previous thread's
// messages immediately, so this skeleton is the bridge (chosen over
// keep-previous-then-swap because it is hydration-mechanism-agnostic — CONTEXT
// D-02). Replaced (not crossfaded) by the rendered restored rows once the fetch
// resolves and the runtime is hydrated.
//
// ZERO-REFLOW CONTRACT: every row reuses the live `.msg` article geometry from
// MessageBubble.tsx:117-133 (`article.mb-7`; assistant header `mb-1.5 flex
// items-center gap-2`; bubble body `bg-[var(--surface-2)] border
// border-[var(--line)] rounded-lg p-4 max-w-prose`) and the user `ChatBubble`
// `ml-auto` shape, so swapping placeholders for real rows shifts the conversation
// column by zero pixels.
//
// ALTERNATION (08-UI-SPEC §148 recorded decision): the skeleton MUST reflect the
// user-vs-assistant alternation, not a uniform column. Each exchange pair renders
// a USER skeleton (right-aligned `ml-auto`, NO header role bar, narrow ~40-60%)
// followed by an ASSISTANT skeleton (left-aligned, role-label header bar + 2-3
// body lines at full / ~85% / ~60% widths). Render exactly 2 pairs (08-UI-SPEC
// §Count) — enough to fill the first viewport without implying a length.
//
// COLOR (08-UI-SPEC §Color skeleton token-fix): the `Skeleton` primitive now
// fills with `bg-[var(--surface-2)]` (the dead shadcn muted default was replaced
// in skeleton.tsx) and gates its pulse behind `motion-safe:animate-pulse` (the
// established RoutingChip.tsx / ComputerUseBubble.tsx convention), so under
// `prefers-reduced-motion: reduce` it renders as a static greyed block.
//
// ACCESSIBILITY (08-UI-SPEC §Accessibility): the container is `role="status"` +
// `aria-busy="true"` with a visually-hidden "Loading conversation history" label
// (the only a11y string — there is no on-screen copy); every placeholder block is
// `aria-hidden="true"` (decorative). When real messages render the container
// unmounts, so assistive tech announces completion naturally.
//
// Cross-refs:
//   - apps/web/components/MessageBubble.tsx:117-133 (the `.msg` geometry mirrored)
//   - apps/web/components/ChatBubble.tsx:71-72 (the user `ml-auto` bubble shape)
//   - apps/web/components/ui/skeleton.tsx (the token-fixed shadcn primitive)
//   - apps/web/components/RoutingChip.tsx:123,153 (motion-safe convention)
//   - 08-UI-SPEC.md §"New Visual Element — Skeleton Loading State (D-02)"
//   - 08-PATTERNS.md §"apps/web/components/HistorySkeleton.tsx"
"use client";

import type React from "react";
import { Skeleton } from "@/components/ui/skeleton";

// One assistant skeleton row — left-aligned, with the mono role-label header bar
// and the bubble shell holding 2-3 text lines (full / ~85% / ~60% widths). The
// shell classes are byte-identical to MessageBubble's real assistant bubble body
// so the swap causes zero reflow.
function AssistantSkeletonRow(): React.JSX.Element {
  return (
    <article className="mb-7" aria-hidden="true">
      {/* .msg header — stand-in for the mono role label ("Prompt Optimizer"). */}
      <div className="mb-1.5 flex items-center gap-2">
        <Skeleton className="h-[11px] w-24" />
      </div>
      {/* bubble body shell — identical to ChatBubble's assistant container. */}
      <div className="bg-[var(--surface-2)] border border-[var(--line)] rounded-lg p-4 max-w-prose">
        <div className="flex flex-col gap-2">
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-[85%]" />
          <Skeleton className="h-3 w-[60%]" />
        </div>
      </div>
    </article>
  );
}

// One user skeleton row — right-aligned (`ml-auto`), NO header role bar, narrower
// than the assistant bubble (~50%), mirroring the user `ChatBubble` `ml-auto`
// shape so a real right-aligned user bubble lands in the same place.
function UserSkeletonRow(): React.JSX.Element {
  return (
    <article className="mb-7" aria-hidden="true">
      <div className="bg-[var(--surface-2)] border border-[var(--line)] rounded-lg p-4 max-w-prose ml-auto w-[50%]">
        <div className="flex flex-col gap-2">
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-[70%]" />
        </div>
      </div>
    </article>
  );
}

// The composite skeleton: 2 exchange pairs (2 user + 2 assistant rows), shown
// inside the centered conversation column while history loads.
export function HistorySkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-busy="true">
      <span className="sr-only">Loading conversation history</span>
      {[0, 1].map((pair) => (
        <div key={pair}>
          <UserSkeletonRow />
          <AssistantSkeletonRow />
        </div>
      ))}
    </div>
  );
}
