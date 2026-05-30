// Phase 7 Plan 07-04 — OverrideChip suite RECONCILED to the L1/D-08 contract.
//
// Originally a Phase-5 RED suite asserting the always-visible "Overridden to … ·
// manual override" chip + backend identity colors (bg-green-100). Phase 7 L1
// makes routing invisible-by-default (hover "optimized" pill) and D-08 restyles
// the manual-override indicator to a DISTINCT NEUTRAL Plasma pill reading
// "manual override" (UI-SPEC §0.3 / §Copywriting "showBadge semantics"). Per
// D-01 we update the TEST, not the design. The comprehensive new-contract suite
// lives in routing-chip.test.tsx; this file keeps focused override-vs-auto
// coverage at its original path so VALIDATION/plan references stay valid.
//
// New contract (apps/web/components/RoutingChip.tsx, 07-03):
//   - signals.override===true → neutral pill, visible text "manual override",
//     aria-label "Manual override: forced to {display_name}", NOT accent-colored.
//   - auto-route (default showBadge) → accent "optimized" pill; the full
//     "Routed to {model} — {reason}" rationale lives on aria-label/title (NOT
//     visible body text).

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { RoutingChip } from "@/components/RoutingChip";

vi.mock("@assistant-ui/react", () => ({
  useMessage: vi.fn(),
}));

import { useMessage } from "@assistant-ui/react";

const mockedUseMessage = useMessage as unknown as ReturnType<typeof vi.fn>;

function withRoutingPart(routingData: {
  backend: string;
  model_or_agent: string;
  rationale: string;
  confidence: number;
  signals: Record<string, unknown>;
}) {
  return {
    content: [{ type: "data", name: "routing", data: routingData }],
  };
}

beforeEach(() => {
  mockedUseMessage.mockReset();
});

describe("OverrideChip — L1/D-08 neutral override pill vs. auto optimized pill", () => {
  it("D-08: with signals.override===true renders the neutral 'manual override' pill", () => {
    mockedUseMessage.mockReturnValue(
      withRoutingPart({
        backend: "claude_code",
        model_or_agent: "claude-code",
        rationale: "user override",
        confidence: 1.0,
        signals: { override: true },
      }),
    );
    render(<RoutingChip />);
    const chip = screen.getByRole("status");
    expect(chip.textContent).toMatch(/manual override/);
    // The retired Phase-5 wording must NOT appear.
    expect(chip.textContent).not.toMatch(/Overridden to/);
    expect(chip.textContent).not.toMatch(/Routed to/);
  });

  it("D-08: override pill is NEUTRAL (not the backend identity color)", () => {
    mockedUseMessage.mockReturnValue(
      withRoutingPart({
        backend: "claude_code",
        model_or_agent: "claude-code",
        rationale: "user override",
        confidence: 1.0,
        signals: { override: true },
      }),
    );
    render(<RoutingChip />);
    const chip = screen.getByRole("status");
    // Neutral Plasma surface, not the old green identity color.
    expect(chip.className).toMatch(/var\(--surface-2\)/);
    expect(chip.className).not.toMatch(/bg-green-100/);
  });

  it("D-08: override pill aria-label declares the manual override (§9b carried to D-08)", () => {
    mockedUseMessage.mockReturnValue(
      withRoutingPart({
        backend: "claude_code",
        model_or_agent: "claude-code",
        rationale: "user override",
        confidence: 1.0,
        signals: { override: true },
      }),
    );
    render(<RoutingChip />);
    expect(screen.getByRole("status")).toHaveAttribute(
      "aria-label",
      "Manual override: forced to Claude Code",
    );
  });

  it("L1: WITHOUT override renders the auto 'optimized' pill; rationale lives on aria-label", () => {
    mockedUseMessage.mockReturnValue(
      withRoutingPart({
        backend: "openrouter",
        model_or_agent: "gpt-5",
        rationale: "Strong reasoning fit",
        confidence: 0.9,
        signals: { task_type: "chat" },
      }),
    );
    render(<RoutingChip />);
    const chip = screen.getByRole("status");
    // Visible body text is the lowercase "optimized" pill (L1), not inline rationale.
    expect(chip.textContent).toMatch(/optimized/);
    expect(chip.textContent).not.toMatch(/manual override/);
    // Full rationale is on the accessible name (hover/AT path, UI-SPEC §0.3).
    expect(chip.getAttribute("aria-label")).toMatch(/Routed to .*Strong reasoning fit/);
  });
});
