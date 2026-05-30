// Phase 5 Wave 0 — ComputerUseBubble RED test suite (UI-10, UI-SPEC §8).
//
// VALIDATION.md row: "UI-10 component" → `pnpm --dir apps/web test computer-use-bubble`.
//
// RED-by-design: `@/components/ComputerUseBubble` does NOT exist yet. The import
// fails to resolve so every `it` is collected and reported FAILED until the
// component ships. Behavioral contract — not skip/todo.
//
// What this asserts (UI-SPEC §8):
//   - §8.2 a screenshot thumbnail strip — one <button aria-label="Screenshot 1 of …">
//   - §8.3 the "still working…" indicator with role="status" while incomplete
//   - §8.2 an image_ref-only thumbnail resolves to a /api/blobs/{hash} src
//
// Drives off the shared computer_use fixture (tests/fixtures/sse-events.ts):
// one inline image_b64 screenshot + one image_ref-only screenshot.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { ComputerUseBubble } from "@/components/ComputerUseBubble";
import {
  COMPUTER_USE_CONTENT_PARTS,
  COMPUTER_USE_SCREENSHOT_REF_HASH,
} from "./fixtures/sse-events";

vi.mock("@assistant-ui/react", () => ({
  useMessage: vi.fn(),
}));

import { useMessage } from "@assistant-ui/react";

const mockedUseMessage = useMessage as unknown as ReturnType<typeof vi.fn>;

// Incomplete message — stream still open (no metrics part, status running).
function incompleteMessage() {
  return {
    content: COMPUTER_USE_CONTENT_PARTS,
    status: { type: "running" },
  };
}

beforeEach(() => {
  mockedUseMessage.mockReset();
  mockedUseMessage.mockReturnValue(incompleteMessage());
});

describe("UI-10 component — ComputerUseBubble (computer_use)", () => {
  it("UI-10: renders a screenshot thumbnail strip with one button per screenshot (§8.2)", () => {
    render(<ComputerUseBubble />);
    // Two screenshots in the fixture → buttons "Screenshot 1 of 2" + "2 of 2".
    const thumb1 = screen.getByRole("button", {
      name: "Screenshot 1 of 2 — click to enlarge",
    });
    expect(thumb1).toBeInTheDocument();
    const thumb2 = screen.getByRole("button", {
      name: "Screenshot 2 of 2 — click to enlarge",
    });
    expect(thumb2).toBeInTheDocument();
  });

  it("UI-10: shows the 'still working…' indicator with role=status while incomplete (§8.3)", () => {
    render(<ComputerUseBubble />);
    const status = screen.getByRole("status");
    expect(status.textContent).toMatch(/still working…/);
  });

  it("UI-10: the 'still working…' indicator disappears once the turn is complete (§8.3)", () => {
    mockedUseMessage.mockReturnValue({
      content: [
        ...COMPUTER_USE_CONTENT_PARTS,
        { type: "data", name: "metrics", data: { cost_usd: 0.019, latency_ms: 7800 } },
      ],
      status: { type: "complete" },
    });
    render(<ComputerUseBubble />);
    expect(screen.queryByText(/still working…/)).toBeNull();
  });

  it("UI-10: an image_ref-only screenshot thumbnail resolves to /api/blobs/{hash} (§8.2)", () => {
    render(<ComputerUseBubble />);
    const thumb2 = screen.getByRole("button", {
      name: "Screenshot 2 of 2 — click to enlarge",
    });
    const img = thumb2.querySelector("img") as HTMLImageElement;
    expect(img).not.toBeNull();
    expect(img.getAttribute("src")).toBe(
      `/api/blobs/${COMPUTER_USE_SCREENSHOT_REF_HASH}`,
    );
  });

  it("UI-10: the inline image_b64 screenshot uses a data: URI src (§8.2)", () => {
    render(<ComputerUseBubble />);
    const thumb1 = screen.getByRole("button", {
      name: "Screenshot 1 of 2 — click to enlarge",
    });
    const img = thumb1.querySelector("img") as HTMLImageElement;
    expect(img).not.toBeNull();
    expect(img.getAttribute("src")).toMatch(/^data:image\/png;base64,/);
  });
});
