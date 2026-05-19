// Plan 04-05 Wave 4 — RoutingChip RTL test suite.
//
// VALIDATION.md row: "UI-04 unit".
// Replaces the Plan 01 it.todo stub with real RTL renders.
//
// What this asserts (UI-SPEC §6 + Plan 04-05 must_haves):
//   - chip subscribes to `useMessage().parts` and finds the {type: "data", name: "routing"} part
//     (assistant-ui v0.14.5 converts AI SDK v6 `data-routing` parts into MessageState
//      parts of `{type: "data", name: "routing", data: ...}`)
//   - chip renders null when no routing part exists
//   - chip text format: "Routed to <display_name> · <rationale>" with U+00B7 separator
//   - chip color class is chipClassByBackend[backend], with openrouter fallback for unknown
//   - chip rationale truncates at 80 chars with ellipsis + full text in title
//   - chip has role="status", aria-live="polite", aria-label that includes the display name
//
// CRITICAL: every fixture for the data-routing part uses the STRUCTURED 5-key payload
// (backend, model_or_agent, rationale, confidence, signals) per Plan 02 Zod schema +
// Plan 04 D-15 amendment. The chip reads routing.backend / routing.model_or_agent /
// routing.rationale directly — NOT `signals.*` (Blocker 1 fix).

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { RoutingChip } from "@/components/RoutingChip";

// Mock the assistant-ui useMessage hook — the chip subscribes to it.
// In assistant-ui v0.14.5, useMessage() returns MessageState which has `parts`.
// Data-* AI SDK v6 parts arrive as {type: "data", name: "routing", data: <RoutingDecision>}.
vi.mock("@assistant-ui/react", () => ({
  useMessage: vi.fn(),
}));

import { useMessage } from "@assistant-ui/react";

const mockedUseMessage = useMessage as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockedUseMessage.mockReset();
});

// Helper: build a MessageState-shaped fixture with one routing data part.
function withRoutingPart(routingData: {
  backend: string;
  model_or_agent: string;
  rationale: string;
  confidence: number;
  signals: Record<string, unknown>;
}) {
  return {
    parts: [
      {
        type: "data",
        name: "routing",
        data: routingData,
      },
    ],
  };
}

describe("UI-04 unit — RoutingChip", () => {
  it("renders null when the message has no routing data part", () => {
    mockedUseMessage.mockReturnValue({ parts: [] });
    const { container } = render(<RoutingChip />);
    expect(container.firstChild).toBeNull();
  });

  it("UI-04: renders 'Routed to <display_name> · <rationale>' with U+00B7 separator", () => {
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
    // Prefix is font-semibold
    expect(chip).toHaveTextContent("Routed to GPT-5");
    // Separator is U+00B7 with spaces
    expect(chip.textContent).toMatch(/Routed to GPT-5\s+·\s+Strong reasoning fit/);
  });

  it("UI-04: falls back to raw model_or_agent slug when not in model_mapping.json", () => {
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
    expect(screen.getByRole("status")).toHaveTextContent(
      "Routed to openai/gpt-5",
    );
  });

  it("UI-04: applies bg-slate-* color for backend=openrouter (UI-SPEC §6.3)", () => {
    mockedUseMessage.mockReturnValue(
      withRoutingPart({
        backend: "openrouter",
        model_or_agent: "gpt-5",
        rationale: "Test",
        confidence: 0.9,
        signals: {},
      }),
    );
    render(<RoutingChip />);
    const chip = screen.getByRole("status");
    expect(chip.className).toMatch(/bg-slate-100/);
    expect(chip.className).toMatch(/text-slate-900/);
  });

  it("UI-04: applies bg-green-* color for backend=claude_code (Phase 5 ready)", () => {
    mockedUseMessage.mockReturnValue(
      withRoutingPart({
        backend: "claude_code",
        model_or_agent: "claude-code-sdk",
        rationale: "Code task",
        confidence: 0.9,
        signals: {},
      }),
    );
    render(<RoutingChip />);
    expect(screen.getByRole("status").className).toMatch(/bg-green-100/);
  });

  it("UI-04: applies bg-amber-* color for backend=computer_use (Phase 5 ready)", () => {
    mockedUseMessage.mockReturnValue(
      withRoutingPart({
        backend: "computer_use",
        model_or_agent: "claude-3.5-sonnet-cua",
        rationale: "Browse task",
        confidence: 0.9,
        signals: {},
      }),
    );
    render(<RoutingChip />);
    expect(screen.getByRole("status").className).toMatch(/bg-amber-100/);
  });

  it("UI-04: falls back to openrouter color class for unknown backend (graceful degradation)", () => {
    mockedUseMessage.mockReturnValue(
      withRoutingPart({
        // Cast through unknown to bypass TS — Zod schema rejects this upstream,
        // but the chip's fallback prevents a crash if the schema is bypassed.
        backend: "foo" as unknown as "openrouter",
        model_or_agent: "gpt-5",
        rationale: "Test",
        confidence: 0.9,
        signals: {},
      }),
    );
    render(<RoutingChip />);
    expect(screen.getByRole("status").className).toMatch(/bg-slate-100/);
  });

  it("UI-04: truncates rationale > 80 chars with ellipsis + full text in title attribute", () => {
    const longRationale =
      "This is an extremely long rationale that definitely exceeds the eighty character truncation limit and must be cut.";
    mockedUseMessage.mockReturnValue(
      withRoutingPart({
        backend: "openrouter",
        model_or_agent: "gpt-5",
        rationale: longRationale,
        confidence: 0.9,
        signals: {},
      }),
    );
    render(<RoutingChip />);
    const chip = screen.getByRole("status");
    // Visible text ends with ellipsis (U+2026)
    expect(chip.textContent).toMatch(/…$/);
    // title attribute carries the FULL rationale
    expect(chip).toHaveAttribute("title", longRationale);
  });

  it("UI-04: role=status + aria-live=polite + aria-label includes display_name", () => {
    mockedUseMessage.mockReturnValue(
      withRoutingPart({
        backend: "openrouter",
        model_or_agent: "gpt-5",
        rationale: "Strong reasoning fit",
        confidence: 0.9,
        signals: {},
      }),
    );
    render(<RoutingChip />);
    const chip = screen.getByRole("status");
    expect(chip).toHaveAttribute("aria-live", "polite");
    expect(chip).toHaveAttribute(
      "aria-label",
      "Routing decision: Routed to GPT-5. Strong reasoning fit",
    );
  });

  it("UI-04: prefix 'Routed to <display_name>' is rendered in a font-semibold span (UI-SPEC §6.2)", () => {
    mockedUseMessage.mockReturnValue(
      withRoutingPart({
        backend: "openrouter",
        model_or_agent: "gpt-5",
        rationale: "Strong reasoning fit",
        confidence: 0.9,
        signals: {},
      }),
    );
    render(<RoutingChip />);
    const prefix = screen.getByText("Routed to GPT-5");
    expect(prefix.className).toMatch(/font-semibold/);
  });
});
