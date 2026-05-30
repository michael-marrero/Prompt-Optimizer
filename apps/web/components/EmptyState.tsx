// Phase 7 Plan 07-04 (UI-REDESIGN-07) — Plasma empty state (D-01).
//
// Supersedes the Phase-5 three-backend-card grid (O-1 / D-01). The Plasma empty
// state is: an eyebrow pill, a gradient hero, the lede, the animated router-fan
// diagram, and a 2×2 grid of FOUR capability suggestion cards (Write / Code /
// Analyze / Plan). Clicking a card FILLS the composer draft (onSelectPrompt) and
// does NOT submit — the user can refine before sending (D-01). All copy is LOCKED
// (UI-SPEC §Copywriting) — do NOT paraphrase.
//
// Cross-refs:
//   - apps/web/components/ChatSurface.tsx (EmptyStateSubmit — now fill-only)
//   - apps/web/components/RouterDiagram.tsx (animated diagram, 07-04 Task 1)
//   - apps/web/components/Icon.tsx (bespoke icons, 07-02 / D-04 depicted surface)
//   - apps/web/tests/empty-state.test.tsx (the RED test this turns green)
//   - 07-UI-SPEC.md §Copywriting + 07-CONTEXT.md D-01
"use client";

import type React from "react";
import { Icon, type IconName } from "@/components/Icon";
import { RouterDiagram } from "@/components/RouterDiagram";

export interface EmptyStateProps {
  /** Invoked with the exact suggestion text when a card is clicked. Under D-01
   * this only FILLS the composer draft — it never submits. */
  onSelectPrompt?: (prompt: string) => void;
  /** Present for the fill-not-submit contract test: a card click must never call
   * this. Not wired to any card handler (D-01). */
  onSubmit?: () => void;
}

interface CapabilityCard {
  kind: string;
  prompt: string;
  icon: IconName;
}

// The FOUR LOCKED capability suggestions (UI-SPEC §Copywriting) — EXACT strings.
const CAPABILITY_CARDS: readonly CapabilityCard[] = [
  { kind: "Write", prompt: "Draft a follow-up email to a customer who churned", icon: "doc" },
  { kind: "Code", prompt: "Refactor this Python function for readability", icon: "copy" },
  { kind: "Analyze", prompt: "Find the top 3 themes in these support tickets", icon: "search" },
  { kind: "Plan", prompt: "Outline a 6-week launch plan for a beta product", icon: "compare" },
];

export function EmptyState({
  onSelectPrompt,
}: EmptyStateProps = {}): React.JSX.Element {
  return (
    <div className="mx-auto w-full max-w-[860px] px-7 py-6 flex flex-col items-center text-center gap-[18px]">
      {/* Eyebrow pill */}
      <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--accent-soft)] px-3 py-1 font-[var(--font-mono-plasma)] text-[9.5px] font-semibold uppercase tracking-[0.06em] text-[var(--accent)]">
        <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-[var(--accent)]" />
        Auto-routed · 6 models · 0 config
      </span>

      {/* Gradient hero — h1 with the "right model" gradient <em> inline */}
      <h1 className="font-[var(--font-display)] text-[48px] leading-[1.04] tracking-[-0.035em] font-semibold text-[var(--ink)]">
        Ask anything. We&apos;ll pick the{" "}
        <em className="not-italic bg-gradient-to-r from-[var(--accent)] via-[var(--accent-2)] to-[var(--accent-3)] bg-clip-text text-transparent">
          right model
        </em>{" "}
        for the job.
      </h1>

      {/* Lede */}
      <p className="max-w-[640px] font-[var(--font-body)] text-[15px] leading-[1.55] tracking-[-0.005em] text-[var(--ink-2)]">
        Every prompt is analyzed and routed to the model that handles it best —
        Claude for nuance, GPT-4o for vision, DeepSeek for code, Gemini for speed.
        You just write.
      </p>

      {/* Animated router-fan diagram */}
      <RouterDiagram />

      {/* 2×2 capability suggestion grid (fill-not-submit) */}
      <div className="grid w-full grid-cols-1 gap-3 sm:grid-cols-2">
        {CAPABILITY_CARDS.map(({ kind, prompt, icon }) => (
          <button
            key={prompt}
            type="button"
            onClick={() => onSelectPrompt?.(prompt)}
            className="group flex flex-col items-start gap-1.5 rounded-[9px] border border-[var(--line)] bg-[var(--surface)] p-4 text-left transition-all duration-[120ms] hover:-translate-y-px hover:border-[var(--line-strong)] hover:shadow-[var(--shadow-md)] cursor-pointer focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]"
          >
            <span className="inline-flex items-center gap-1.5 font-[var(--font-mono-plasma)] text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--accent)]">
              <Icon name={icon} size={14} />
              {kind}
            </span>
            <span className="font-[var(--font-body)] text-[13px] leading-[1.5] tracking-[-0.005em] text-[var(--ink)]">
              {prompt}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
