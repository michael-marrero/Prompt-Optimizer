// Phase 5 Wave 0 — StatusStrip RED test suite (UI-11, UI-SPEC §10).
//
// VALIDATION.md row: "UI-11 component" → `pnpm --dir apps/web test status-strip`.
//
// RED-by-design: `@/components/StatusStrip` does NOT exist yet. The import fails
// to resolve so every `it` is collected and reported FAILED until it ships.
//
// What this asserts (UI-SPEC §10.2 + §17):
//   - AdapterStatus → dot color: ready→green, missing_key|error→red, opt_out→slate
//   - the exact §10.2 / §17 tooltip strings per status
//
// The strip reads a per-backend health payload. To keep this a pure render
// contract (no live /api/health fetch) the component accepts a `statuses` prop;
// the exact wiring to the poll is an implementation choice covered elsewhere.

import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { StatusStrip } from "@/components/StatusStrip";

const STATUSES = {
  openrouter: { status: "ready", reason: "" },
  claude_code: { status: "missing_key", reason: "" },
  computer_use: { status: "opt_out", reason: "" },
} as const;

describe("UI-11 component — StatusStrip (UI-SPEC §10)", () => {
  it("UI-11: a ready backend shows a green dot (§10.2)", () => {
    const { container } = render(<StatusStrip statuses={STATUSES} />);
    const group = screen.getByRole("status", { name: /OpenRouter status/ });
    const dot = within(group).getByTestId("status-dot");
    expect(dot.className).toMatch(/var\(--good\)/);
    expect(container).toBeTruthy();
  });

  it("UI-11: a missing_key backend shows a red dot (§10.2)", () => {
    render(<StatusStrip statuses={STATUSES} />);
    const group = screen.getByRole("status", { name: /Claude Code status/ });
    const dot = within(group).getByTestId("status-dot");
    expect(dot.className).toMatch(/var\(--danger\)/);
  });

  it("UI-11: an error backend shows a red dot (§10.2)", () => {
    render(
      <StatusStrip
        statuses={{
          openrouter: { status: "error", reason: "" },
          claude_code: { status: "ready", reason: "" },
          computer_use: { status: "ready", reason: "" },
        }}
      />,
    );
    const group = screen.getByRole("status", { name: /OpenRouter status/ });
    expect(within(group).getByTestId("status-dot").className).toMatch(/var\(--danger\)/);
  });

  it("UI-11: an opt_out backend shows a slate dot (§10.2)", () => {
    render(<StatusStrip statuses={STATUSES} />);
    const group = screen.getByRole("status", { name: /computer-use status/ });
    expect(within(group).getByTestId("status-dot").className).toMatch(/var\(--ink-4\)/);
  });

  it("UI-11: ready tooltip text is '{Backend} ready' (§17)", () => {
    render(<StatusStrip statuses={STATUSES} />);
    expect(screen.getByText("OpenRouter ready")).toBeInTheDocument();
  });

  it("UI-11: missing_key tooltip text matches §17 verbatim", () => {
    render(<StatusStrip statuses={STATUSES} />);
    expect(
      screen.getByText("Claude Code: no API key — add one in settings"),
    ).toBeInTheDocument();
  });

  it("UI-11: opt_out tooltip text matches §17 verbatim", () => {
    render(<StatusStrip statuses={STATUSES} />);
    expect(
      screen.getByText("Computer use is off — turn it on in settings"),
    ).toBeInTheDocument();
  });

  it("UI-11: error tooltip text matches §17 verbatim", () => {
    render(
      <StatusStrip
        statuses={{
          openrouter: { status: "error", reason: "" },
          claude_code: { status: "ready", reason: "" },
          computer_use: { status: "ready", reason: "" },
        }}
      />,
    );
    expect(
      screen.getByText("OpenRouter: availability check failed"),
    ).toBeInTheDocument();
  });
});
