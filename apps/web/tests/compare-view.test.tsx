// Phase 7 Plan 07-01 Wave 0 — NEW RED test: Compare view 2-up render + locked
// head copy.
//
// 07-VALIDATION.md row: "Compare 2-column render | L5 | unit".
//
// RED-by-design: @/components/CompareView does NOT exist yet — the Compare view
// (one prompt rendered side-by-side across two candidate models) lands in Plan
// 07-08. The import below therefore fails to resolve, which is the correct
// Wave-0 RED state ("not implemented"), NOT a malformed-test failure. Once
// 07-08 ships CompareView this turns toward GREEN.
//
// The LOCKED contract (UI-SPEC §Spacing + §Copywriting):
//   - 2-column card grid, grid-template-columns: 1fr 1fr, gap 12px.
//   - each card head reads "{Model} · {latency}s · ${cost}", e.g.
//     "Claude Sonnet 4.5 · 1.84s · $0.0042" (U+00B7 middle-dot separators).
//
// Prop contract pinned by this test (planner may refine the internals, but the
// rendered 2-up grid + head-copy format are locked): CompareView takes a
// `completions` array of two lanes, each { model, latency, cost, text }.

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
// RED: this import fails until Plan 07-08 creates apps/web/components/CompareView.
import { CompareView } from "@/components/CompareView";

const COMPLETIONS = [
  {
    model: "Claude Sonnet 4.5",
    latency: 1.84,
    cost: 0.0042,
    text: "Claude's answer to the shared prompt.",
  },
  {
    model: "GPT-5",
    latency: 2.11,
    cost: 0.0067,
    text: "GPT-5's answer to the shared prompt.",
  },
] as const;

describe("CompareView — 2-up Compare grid + locked head copy (L5)", () => {
  it("L5: renders two column cards (one per candidate model)", () => {
    render(<CompareView completions={[...COMPLETIONS]} />);
    // Both candidate answers render side-by-side.
    expect(screen.getByText("Claude's answer to the shared prompt.")).toBeInTheDocument();
    expect(screen.getByText("GPT-5's answer to the shared prompt.")).toBeInTheDocument();
  });

  it("L5: a 2-column grid container (grid-template-columns: 1fr 1fr) exists", () => {
    const { container } = render(<CompareView completions={[...COMPLETIONS]} />);
    // UI-SPEC §Spacing locks the Compare grid to `1fr 1fr`. The grid container
    // declares it via an inline style or a style attribute the test can read.
    const grid = container.querySelector('[style*="1fr 1fr"]');
    expect(grid, "Compare grid must declare grid-template-columns: 1fr 1fr").not.toBeNull();
  });

  it("L5: each card head matches the locked '{Model} · {latency}s · ${cost}' format", () => {
    render(<CompareView completions={[...COMPLETIONS]} />);
    // Exact locked head copy from UI-SPEC §Copywriting (Compare card head).
    // U+00B7 middle dots; latency suffixed with "s"; cost prefixed with "$".
    expect(screen.getByText("Claude Sonnet 4.5 · 1.84s · $0.0042")).toBeInTheDocument();
    expect(screen.getByText("GPT-5 · 2.11s · $0.0067")).toBeInTheDocument();
  });
});
