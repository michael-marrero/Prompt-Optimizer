// Phase 7 Plan 07-01 Wave 0 — EmptyState RTL test suite REWRITTEN to the
// Plasma D-01 contract.
//
// 07-VALIDATION.md row: "Empty state (4 cards, fill-not-submit) | D-01 | unit".
//
// WHY this file was rewritten (07-CONTEXT D-01 / UI-SPEC §Copywriting + O-1):
//   Phase 5 shipped THREE backend-exercising sample cards ("Build me a small
//   finance tracker app" → Claude Code, "What is the capital of France?" →
//   OpenRouter, "Open this URL and check the price" → computer-use) whose click
//   SUBMITTED the prompt immediately, plus the tagline "Ask anything. We'll
//   route to the right model." The Plasma empty state (D-01) replaces these with
//   FOUR capability suggestion cards (Write / Code / Analyze / Plan) whose click
//   only FILLS the composer (the user can refine, then send — no immediate
//   submit), under the new gradient hero + lede copy. Per D-01 we update the
//   TEST, not the design.
//
// RED-by-design: the four Plasma cards + the new hero/lede + the fill-not-submit
// behavior land in the empty-state rebuild plan (Plan 07-04). Until then these
// assertions fail because EmptyState still renders the old 3 cards / tagline and
// submits on click — the correct Wave-0 RED state, NOT a malformed-test failure.
//
// The NEW locked contract (UI-SPEC §Copywriting):
//   - hero h1: "Ask anything." / "We'll pick the right model for the job."
//     ("right model" is a gradient <em>).
//   - lede: "Every prompt is analyzed and routed to the model that handles it
//     best — Claude for nuance, GPT-4o for vision, DeepSeek for code, Gemini for
//     speed. You just write."
//   - FOUR suggestion cards (exact strings):
//       Write    "Draft a follow-up email to a customer who churned"
//       Code     "Refactor this Python function for readability"
//       Analyze  "Find the top 3 themes in these support tickets"
//       Plan     "Outline a 6-week launch plan for a beta product"
//   - clicking a card FILLS the composer draft (onSelectPrompt called with the
//     exact prompt) and does NOT submit (no send/submit handler fires).

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { EmptyState } from "@/components/EmptyState";

// The four EXACT Plasma capability suggestion strings (UI-SPEC §Copywriting).
const WRITE_PROMPT = "Draft a follow-up email to a customer who churned";
const CODE_PROMPT = "Refactor this Python function for readability";
const ANALYZE_PROMPT = "Find the top 3 themes in these support tickets";
const PLAN_PROMPT = "Outline a 6-week launch plan for a beta product";

describe("EmptyState — Plasma 4 capability cards + fill-not-submit (D-01)", () => {
  it("D-01: renders the new gradient hero copy (supersedes the old tagline)", () => {
    render(<EmptyState onSelectPrompt={vi.fn()} />);
    // Hero is split across an h1 + gradient <em>; assert both halves are
    // present. The old single tagline must be gone.
    expect(screen.getByText(/Ask anything\./)).toBeInTheDocument();
    expect(screen.getByText(/right model/)).toBeInTheDocument();
    expect(screen.getByText(/for the job\./)).toBeInTheDocument();
  });

  it("D-01: renders the new lede paragraph", () => {
    render(<EmptyState onSelectPrompt={vi.fn()} />);
    // Match a distinctive fragment of the locked lede so whitespace / em-dash
    // rendering differences across nodes do not make the assertion brittle.
    expect(
      screen.getByText(/Every prompt is analyzed and routed to the model that handles it best/),
    ).toBeInTheDocument();
    expect(screen.getByText(/You just write\./)).toBeInTheDocument();
  });

  it("D-01: renders all FOUR exact Plasma suggestion strings (Write/Code/Analyze/Plan)", () => {
    render(<EmptyState onSelectPrompt={vi.fn()} />);
    expect(screen.getByText(WRITE_PROMPT)).toBeInTheDocument();
    expect(screen.getByText(CODE_PROMPT)).toBeInTheDocument();
    expect(screen.getByText(ANALYZE_PROMPT)).toBeInTheDocument();
    expect(screen.getByText(PLAN_PROMPT)).toBeInTheDocument();
  });

  it("D-01: clicking a card FILLS the composer draft (onSelectPrompt called with the exact prompt)", () => {
    const onSelectPrompt = vi.fn();
    render(<EmptyState onSelectPrompt={onSelectPrompt} />);
    // Click the Code card; the exact prompt is forwarded to the fill handler.
    fireEvent.click(screen.getByText(CODE_PROMPT));
    expect(onSelectPrompt).toHaveBeenCalledTimes(1);
    expect(onSelectPrompt).toHaveBeenCalledWith(CODE_PROMPT);
  });

  it("D-01: clicking a card does NOT submit (no send/submit handler fires)", () => {
    // The fill-not-submit contract: a card click fills the draft but never
    // sends. We pass an explicit onSubmit spy alongside the fill handler and
    // assert it is never invoked. (Under the old Phase-5 contract the click
    // submitted immediately — that behavior is removed by D-01.)
    const onSelectPrompt = vi.fn();
    const onSubmit = vi.fn();
    render(<EmptyState onSelectPrompt={onSelectPrompt} onSubmit={onSubmit} />);
    fireEvent.click(screen.getByText(WRITE_PROMPT));
    expect(onSelectPrompt).toHaveBeenCalledWith(WRITE_PROMPT);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("D-01: each suggestion is an interactive control (button) the user can click", () => {
    render(<EmptyState onSelectPrompt={vi.fn()} />);
    // All four suggestions are buttons (fill-on-click). Exactly four cards.
    const buttons = screen.getAllByRole("button");
    const cardButtons = buttons.filter((b) =>
      [WRITE_PROMPT, CODE_PROMPT, ANALYZE_PROMPT, PLAN_PROMPT].some((p) =>
        (b.textContent ?? "").includes(p),
      ),
    );
    expect(cardButtons).toHaveLength(4);
  });
});
