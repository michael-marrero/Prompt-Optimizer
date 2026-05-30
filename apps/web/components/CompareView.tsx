// CompareView (L5) — Phase 7 Plan 07-08. The 2-up Compare grid: one prompt's
// two model completions rendered side-by-side below the thread.
//
// UI-SPEC §Spacing + §Copywriting (LOCKED):
//   - 2-column card grid, `grid-template-columns: 1fr 1fr`, gap 12px.
//   - Each card head reads "{Model} · {latency}s · ${cost}", e.g.
//     "Claude Sonnet 4.5 · 1.84s · $0.0042" (U+00B7 middle-dot separators).
//
// Each column reuses the EXISTING assistant render path — `ChatBubble`
// (assistant variant → MarkdownRenderer / StreamingCodeBlock per 07-05/07-06)
// — so there is NO new markdown/code renderer here; only the 2-up grid is new
// (07-PATTERNS.md "CompareView.tsx (NEW)").
//
// The two lanes are produced by `/api/compare` (Task 2): the Next proxy opens
// the FastAPI Compare stream and re-emits lane-tagged AI-SDK chunks. The lane
// model defaults match Task 1's backend choice — GPT-5 (lane 0) + Claude
// Sonnet 4.5 (lane 1).
//
// Cross-refs:
//   - apps/web/components/ChatBubble.tsx (per-column assistant render)
//   - apps/web/components/Icon.tsx (compare glyph — depicted surface, D-04)
//   - apps/web/app/api/compare/route.ts (the 2-lane stream source)
//   - apps/web/tests/compare-view.test.tsx (the contract this satisfies)
//   - 07-UI-SPEC.md §Spacing/§Copywriting · 07-PATTERNS.md CompareView section
"use client";

import type React from "react";
import { ChatBubble } from "@/components/ChatBubble";
import { Icon } from "@/components/Icon";
import { cn } from "@/lib/cn";

/** One Compare lane = one model's completion + its per-lane metrics. */
export interface CompareCompletion {
  /** Display model label for the card head (e.g. "Claude Sonnet 4.5"). */
  model: string;
  /** Latency in seconds — rendered as "{latency}s". */
  latency: number;
  /** Cost in USD — rendered as "${cost}". */
  cost: number;
  /** The assistant completion body (markdown source), rendered via ChatBubble. */
  text: string;
  /** True once this lane's stream has finished (gates one-shot code highlight). */
  isStreamingComplete?: boolean;
  /** Optional per-lane message id for the MarkdownRenderer memo predicate. */
  messageId?: string;
}

export interface CompareViewProps {
  /** The two lanes (2-up only — RESEARCH: Compare across >2 models is OOS). */
  completions: CompareCompletion[];
}

// LOCKED head copy: "{Model} · {latency}s · ${cost}" with U+00B7 separators.
// Values are interpolated as-is (the metrics arrive already at their display
// precision, e.g. 1.84 / 0.0042); do not re-round here ("do not round").
function headCopy(c: CompareCompletion): string {
  return `${c.model} · ${c.latency}s · $${c.cost}`;
}

export function CompareView({
  completions,
}: CompareViewProps): React.JSX.Element {
  return (
    <section aria-label="Compare model completions" className="mb-7">
      {/* Section eyebrow — depicted compare glyph (D-04) + mono label. */}
      <div className="mb-2 flex items-center gap-1.5 text-[var(--ink-3)]">
        <Icon name="compare" size={14} />
        <span className="font-[var(--font-mono-plasma)] text-[10.5px] font-semibold uppercase tracking-[0.08em]">
          Compare
        </span>
      </div>

      {/* LOCKED grid: 1fr 1fr, gap 12px. Declared via inline style so the
          token-agnostic spec value is exact and assertable. */}
      <div
        style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}
      >
        {completions.map((c, lane) => (
          <article
            key={c.messageId ?? `${c.model}-${lane}`}
            className={cn(
              "flex flex-col gap-2 rounded-[var(--radius-lg)] border border-[var(--line)]",
              "bg-[var(--surface)] p-3 shadow-[var(--shadow-sm)]",
            )}
          >
            {/* Card head — LOCKED "{Model} · {latency}s · ${cost}". */}
            <header className="font-[var(--font-mono-plasma)] text-[11px] font-medium tracking-[0.02em] text-[var(--ink-2)]">
              {headCopy(c)}
            </header>
            {/* Column body reuses the existing assistant bubble path —
                MarkdownRenderer / StreamingCodeBlock (no new renderer). */}
            <ChatBubble
              role="assistant"
              rawMarkdown={c.text}
              isStreamingComplete={c.isStreamingComplete ?? false}
              messageId={c.messageId ?? `compare-lane-${lane}`}
            />
          </article>
        ))}
      </div>
    </section>
  );
}
