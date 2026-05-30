// Phase 5 Wave 0 — CodeBubble RED test suite (UI-09, UI-SPEC §7).
//
// VALIDATION.md row: "UI-09 component" → `pnpm --dir apps/web test code-bubble`.
//
// RED-by-design: `@/components/CodeBubble` does NOT exist yet (it lands in a
// later Phase 5 plan). The import below fails to resolve, so every `it` in this
// file is collected and reported FAILED until CodeBubble ships. These tests are
// the behavioral contract the implementation must satisfy — they are NOT
// skip/todo stubs.
//
// What this asserts (UI-SPEC §7):
//   - §7.3 a collapsed-by-default tool-call collapsible with the tool name visible
//   - §7.2 a file-diff block with red removed lines + green added lines
//   - §7.4 the final summary text rendered from the terminal text part
//
// Drives off the shared claude_code fixture (tests/fixtures/sse-events.ts).

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { CodeBubble } from "@/components/CodeBubble";
import { CLAUDE_CODE_CONTENT_PARTS } from "./fixtures/sse-events";

// CodeBubble reads data parts off useMessage().content (RoutingChip.tsx:85-91).
vi.mock("@assistant-ui/react", () => ({
  useMessage: vi.fn(),
}));

import { useMessage } from "@assistant-ui/react";

const mockedUseMessage = useMessage as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockedUseMessage.mockReset();
  mockedUseMessage.mockReturnValue({ content: CLAUDE_CODE_CONTENT_PARTS });
});

describe("UI-09 component — CodeBubble (claude_code)", () => {
  it("UI-09: renders a tool-call collapsible with the tool name visible (§7.3)", () => {
    render(<CodeBubble />);
    // Tool name from the fixture's tool_call part.
    expect(screen.getByText("edit_file")).toBeInTheDocument();
    // The collapsible trigger advertises the tool call by name.
    const trigger = screen.getByRole("button", {
      name: "Tool call: edit_file (click to expand)",
    });
    expect(trigger).toBeInTheDocument();
  });

  it("UI-09: tool-call collapsible is collapsed by default (§7.3 — aria-expanded false)", () => {
    render(<CodeBubble />);
    const trigger = screen.getByRole("button", {
      name: "Tool call: edit_file (click to expand)",
    });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("UI-09: renders a file-diff block with --danger removed + --good added line tokens (§7.2 / Plasma D-02)", () => {
    const { container } = render(<CodeBubble />);
    // The fixture diff has one removed line (old_total = 0) and two added lines.
    const removed = screen.getByText(/old_total = 0/);
    const added = screen.getByText(/total = sum\(amounts\)/);
    expect(removed.className).toMatch(/var\(--danger\)/);
    expect(added.className).toMatch(/var\(--good\)/);
    // The diff container carries the accessible label per §7.2.
    expect(
      container.querySelector('[aria-label^="File diff for src/app.py"]'),
    ).not.toBeNull();
  });

  it("UI-09: renders the final summary text from the terminal text part (§7.4)", () => {
    render(<CodeBubble />);
    expect(
      screen.getByText("I added a budget total to your finance tracker."),
    ).toBeInTheDocument();
  });

  it("UI-09: bubble shell uses the assistant shell classes (§7 container)", () => {
    const { container } = render(<CodeBubble />);
    const bubble = container.firstChild as HTMLElement;
    expect(bubble.className).toMatch(/var\(--surface-2\)/);
    expect(bubble.className).toMatch(/var\(--line\)/);
    expect(bubble.className).toMatch(/rounded-lg/);
    expect(bubble.className).toMatch(/p-4/);
  });
});
