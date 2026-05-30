// Phase 7 Plan 07-01 Wave 0 — RoutingChip RTL test suite REWRITTEN to the
// Plasma L1 / D-08 contract.
//
// 07-VALIDATION.md row: "Optimized pill + D-08 override pill | L1/D-08 | unit"
// + "showBadge gating | D-08 | unit".
//
// WHY this file was rewritten (07-CONTEXT D-01 / UI-SPEC §0.3 L1):
//   Phase 4/5 shipped an ALWAYS-VISIBLE color-coded chip ("Routed to {model}
//   · {rationale}", role="status", with per-backend green/amber/slate utility
//   classes). Phase 7 LOCKED decision L1 makes routing INVISIBLE-BY-DEFAULT: it is
//   replaced by a hover/focus-only "optimized" pill in the assistant message
//   header. The full rationale moves OFF the inline body and ONTO the pill's
//   title / aria-label so assistive-tech + hover users retain access
//   (UI-SPEC §0.3 accessibility caveat). Per D-01 we update the TEST, not the
//   design — this file now encodes the NEW contract.
//
// RED-by-design: the optimized-pill presentation lands in Plan 07-02/07-04.
// Until then these assertions fail for "RoutingChip still renders the old
// always-visible chip" reasons — that is the correct Wave-0 RED state, NOT a
// malformed-test failure. The data path is unchanged (the chip still reads the
// {type:"data", name:"routing"} part off useMessage().content), so the mock
// shape below is identical to the preserved Phase 4/5 data contract.
//
// The NEW locked contract (UI-SPEC §Copywriting + §0.3 + D-08):
//   (a) AUTO route  → visible text "optimized" (lowercase, JetBrains Mono);
//                     aria-label === "Routed to {model.label} — {routedReason}"
//                     with an em-dash (U+2014) and the FULL, untruncated
//                     rationale (no 80-char ellipsis, no inline "· rationale").
//   (b) OVERRIDE (signals.override===true, D-08) → a DISTINCT, neutral
//                     (non-accent) pill reading "manual override" with the model
//                     name carried in title / aria-label. A manual override is a
//                     deliberate user action, NOT auto-routing, so it is NOT
//                     governed by L1 and stays visible regardless of showBadge.
//   (c) showBadge gating (D-08 / UI-SPEC §Copywriting "showBadge semantics") →
//                     when the badge is gated OFF the AUTO optimized pill is
//                     suppressed, but the manual-override pill STILL renders.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { RoutingChip } from "@/components/RoutingChip";

// Mock the assistant-ui useMessage hook — the chip subscribes to it.
// In assistant-ui v0.14.5, useMessage() returns MessageState which exposes a
// `content` array. The AI-SDK v6 `data-routing` chunk is converted into a
// content entry of shape {type:"data", name:"routing", data:<RoutingDecision>}.
vi.mock("@assistant-ui/react", () => ({
  useMessage: vi.fn(),
}));

import { useMessage } from "@assistant-ui/react";

const mockedUseMessage = useMessage as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockedUseMessage.mockReset();
});

// Helper: build a MessageState-shaped fixture with one routing data entry on
// `content` — exactly as RoutingChip reads it (p.type==="data" &&
// p.name==="routing"). Identical to the preserved Phase 4/5 data shape.
function withRoutingPart(routingData: {
  backend: string;
  model_or_agent: string;
  rationale: string;
  confidence: number;
  signals: Record<string, unknown>;
}) {
  return {
    content: [
      {
        type: "data",
        name: "routing",
        data: routingData,
      },
    ],
  };
}

describe("RoutingChip — Plasma optimized pill (L1) + manual-override pill (D-08)", () => {
  it("renders null when the message has no routing data part", () => {
    mockedUseMessage.mockReturnValue({ content: [] });
    const { container } = render(<RoutingChip />);
    expect(container.firstChild).toBeNull();
  });

  // ----------------------------------------------------------------
  // (a) AUTO route → optimized pill (L1 / UI-SPEC §0.3 + §Copywriting)
  // ----------------------------------------------------------------
  it("L1: auto-route renders the lowercase 'optimized' pill (not the old inline chip)", () => {
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
    // The visible text of the pill is the lowercase word "optimized"
    // (JetBrains Mono 9.5px per UI-SPEC §Typography). It is NOT the old
    // "Routed to … · …" inline body text.
    expect(screen.getByText("optimized")).toBeInTheDocument();
  });

  it("L1: optimized pill aria-label is 'Routed to {model} — {reason}' with an em-dash + FULL rationale", () => {
    const fullRationale =
      "Strong reasoning fit for a multi-step analytical question that exceeds the old eighty-character truncation limit by a wide margin and must not be cut.";
    mockedUseMessage.mockReturnValue(
      withRoutingPart({
        backend: "openrouter",
        model_or_agent: "gpt-5",
        rationale: fullRationale,
        confidence: 0.9,
        signals: { task_type: "chat" },
      }),
    );
    render(<RoutingChip />);
    // UI-SPEC §0.3: the pill MUST carry the full "Routed to {model} — {reason}"
    // on its aria-label so non-hover assistive-tech users retain access.
    // The separator is an em-dash (U+2014), and the rationale is the FULL,
    // un-truncated string (no 80-char ellipsis).
    const pill = screen.getByLabelText(
      `Routed to GPT-5 — ${fullRationale}`,
    );
    expect(pill).toBeInTheDocument();
    // Belt-and-suspenders: the aria-label contains "Routed to" followed by an
    // em-dash, and the rationale was NOT truncated with an ellipsis.
    const ariaLabel = pill.getAttribute("aria-label") ?? "";
    expect(ariaLabel).toMatch(/Routed to .* — /);
    expect(ariaLabel).toContain(fullRationale);
    expect(ariaLabel).not.toMatch(/…/); // no U+2026 ellipsis
  });

  it("L1: unmapped OpenRouter slug renders verbatim in the optimized pill aria-label", () => {
    mockedUseMessage.mockReturnValue(
      withRoutingPart({
        backend: "openrouter",
        model_or_agent: "openai/gpt-5", // not a direct key in model_mapping.json
        rationale: "Default route",
        confidence: 0.5,
        signals: {},
      }),
    );
    render(<RoutingChip />);
    // The display-name fallback (raw slug) is preserved under L1; it just lives
    // on the aria-label now instead of the inline body.
    const ariaLabel =
      screen.getByText("optimized").closest("[aria-label]")?.getAttribute("aria-label") ??
      "";
    expect(ariaLabel).toContain("Routed to openai/gpt-5");
  });

  // ----------------------------------------------------------------
  // (b) OVERRIDE branch → distinct neutral "manual override" pill (D-08)
  // ----------------------------------------------------------------
  it("D-08: signals.override===true renders a DISTINCT neutral 'manual override' pill", () => {
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
    // The override pill's visible text reads "manual override" (D-08). It must
    // NOT read the auto-route "optimized" word.
    expect(screen.getByText(/manual override/i)).toBeInTheDocument();
    expect(screen.queryByText("optimized")).toBeNull();
  });

  it("D-08: manual-override pill carries the model name in its title / aria-label", () => {
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
    const pill = screen.getByText(/manual override/i).closest("[aria-label]");
    expect(pill).not.toBeNull();
    // The §17 brand-cased model name ("Claude Code") must be discoverable via
    // the accessible name so an overridden turn is unambiguous to AT users.
    const accessibleText =
      (pill?.getAttribute("aria-label") ?? "") +
      " " +
      (pill?.getAttribute("title") ?? "");
    expect(accessibleText).toMatch(/Claude Code/);
  });

  it("D-08: the neutral override pill is NOT styled with the accent optimized-pill text", () => {
    // The override pill is a DISTINCT, neutral (non-accent) variant — it must
    // not reuse the "optimized" accent wording. (Color-class exactness is a
    // manual pixel-fidelity check per 07-VALIDATION Manual-Only; the assertable
    // contract here is the distinct wording + persistence under showBadge.)
    mockedUseMessage.mockReturnValue(
      withRoutingPart({
        backend: "computer_use",
        model_or_agent: "computer-use",
        rationale: "user override",
        confidence: 1.0,
        signals: { override: true },
      }),
    );
    render(<RoutingChip />);
    expect(screen.getByText(/manual override/i)).toBeInTheDocument();
    expect(screen.queryByText("optimized")).toBeNull();
  });

  // ----------------------------------------------------------------
  // (c) showBadge gating (D-08 / UI-SPEC §Copywriting "showBadge semantics")
  // ----------------------------------------------------------------
  it("D-08: showBadge=false SUPPRESSES the auto optimized pill", () => {
    mockedUseMessage.mockReturnValue(
      withRoutingPart({
        backend: "openrouter",
        model_or_agent: "gpt-5",
        rationale: "Strong reasoning fit",
        confidence: 0.9,
        signals: { task_type: "chat" },
      }),
    );
    // Under L1 the "Show routing badge" toggle gates the AUTO optimized pill.
    // When off, the pill is suppressed (routing rationale then only reachable
    // via the modal/log). The flag is passed as a prop so the behavior is
    // assertable without wiring the whole settings modal.
    render(<RoutingChip showBadge={false} />);
    expect(screen.queryByText("optimized")).toBeNull();
  });

  it("D-08: showBadge=false STILL renders the manual-override pill (explicit user intent persists)", () => {
    mockedUseMessage.mockReturnValue(
      withRoutingPart({
        backend: "claude_code",
        model_or_agent: "claude-code",
        rationale: "user override",
        confidence: 1.0,
        signals: { override: true },
      }),
    );
    // D-08: the manual-override indicator reflects explicit user intent, not
    // router rationale, so it persists regardless of the showBadge gate.
    render(<RoutingChip showBadge={false} />);
    expect(screen.getByText(/manual override/i)).toBeInTheDocument();
  });

  it("D-08: showBadge=true (default) renders the auto optimized pill", () => {
    mockedUseMessage.mockReturnValue(
      withRoutingPart({
        backend: "openrouter",
        model_or_agent: "gpt-5",
        rationale: "Strong reasoning fit",
        confidence: 0.9,
        signals: { task_type: "chat" },
      }),
    );
    render(<RoutingChip showBadge={true} />);
    expect(screen.getByText("optimized")).toBeInTheDocument();
  });
});
