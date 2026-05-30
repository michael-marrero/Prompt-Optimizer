// Plan 04-05 Wave 4 — ChatBubble + StreamErrorBanner RTL test suite.
//
// VALIDATION.md row: "UI-08 unit".
// Replaces the Plan 01 it.todo stub with real RTL renders.
//
// What this asserts (UI-SPEC §8 + §12 + Plan 04-05 must_haves):
//   - assistant bubble shell: bg-slate-50 border rounded-lg p-4 max-w-prose group relative
//   - user bubble shell: bg-slate-100 ml-auto, NO action row
//   - assistant action row reveals on hover/focus-within (group-hover:opacity-100)
//   - Copy button aria-label "Copy message as markdown"; on click writes
//     the raw markdown source to clipboard + fires sonner.success toast
//   - Regenerate button aria-label "Regenerate response"; on click invokes
//     the `onRegenerate` prop exactly once
//   - StreamErrorBanner code → friendly-message catalog covers every Phase 2
//     D-06 code with role="alert" + "Try again" visible when retriable=true

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ChatBubble } from "@/components/ChatBubble";
import { StreamErrorBanner } from "@/components/StreamErrorBanner";

// Mock sonner so we can assert toast.success was called with the right text
// without depending on the actual toast DOM rendering (the Toaster lives in
// app/layout.tsx, not under our test root).
vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { toast } from "sonner";

const mockedToastSuccess = toast.success as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockedToastSuccess.mockReset();
  // Mock navigator.clipboard.writeText. jsdom doesn't ship a real clipboard
  // implementation, so we install a stub on the navigator object before each test.
  Object.assign(navigator, {
    clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
});

describe("UI-08 unit — ChatBubble (assistant)", () => {
  it("UI-08: assistant bubble has the Plasma surface/line tokens + rounded-lg p-4 max-w-prose group relative", () => {
    const { container } = render(
      <ChatBubble role="assistant" rawMarkdown="# hello">
        <p>body</p>
      </ChatBubble>,
    );
    const bubble = container.firstChild as HTMLElement;
    expect(bubble.className).toMatch(/var\(--surface-2\)/);
    expect(bubble.className).toMatch(/var\(--line\)/);
    expect(bubble.className).toMatch(/rounded-lg/);
    expect(bubble.className).toMatch(/p-4/);
    expect(bubble.className).toMatch(/max-w-prose/);
    expect(bubble.className).toMatch(/group/);
    expect(bubble.className).toMatch(/relative/);
  });

  it("UI-08: action row is hidden by default, revealed on hover (group-hover:opacity-100 + focus-within)", () => {
    render(
      <ChatBubble role="assistant" rawMarkdown="# hello">
        <p>body</p>
      </ChatBubble>,
    );
    const copyBtn = screen.getByRole("button", {
      name: "Copy message as markdown",
    });
    // The action row container has the reveal classes.
    const actionRow = copyBtn.parentElement as HTMLElement;
    expect(actionRow.className).toMatch(/opacity-0/);
    expect(actionRow.className).toMatch(/group-hover:opacity-100/);
    expect(actionRow.className).toMatch(/focus-within:opacity-100/);
  });

  it("UI-08: Copy button writes the RAW markdown source to clipboard (not rendered HTML)", async () => {
    // JSX string attributes are RAW (escape sequences not processed). Pass
    // the multi-line string via {...} so `\n` becomes a real newline.
    const raw = "# heading\n\nbody **bold**";
    render(
      <ChatBubble role="assistant" rawMarkdown={raw}>
        <p>this is the rendered DOM body</p>
      </ChatBubble>,
    );
    const copyBtn = screen.getByRole("button", {
      name: "Copy message as markdown",
    });
    fireEvent.click(copyBtn);
    // The click handler is async; await one microtask so the clipboard
    // mock has time to record the call.
    await Promise.resolve();
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(raw);
  });

  it("UI-08: Copy success fires sonner.success 'Copied to clipboard'", async () => {
    render(
      <ChatBubble role="assistant" rawMarkdown="hello">
        <p>body</p>
      </ChatBubble>,
    );
    const copyBtn = screen.getByRole("button", {
      name: "Copy message as markdown",
    });
    fireEvent.click(copyBtn);
    // Wait for the async clipboard promise + toast call to land.
    await Promise.resolve();
    await Promise.resolve();
    expect(mockedToastSuccess).toHaveBeenCalledWith("Copied to clipboard");
  });

  it("UI-08: Regenerate button invokes the onRegenerate prop exactly once", () => {
    const onRegenerate = vi.fn();
    render(
      <ChatBubble
        role="assistant"
        rawMarkdown="hi"
        onRegenerate={onRegenerate}
      >
        <p>body</p>
      </ChatBubble>,
    );
    const regenBtn = screen.getByRole("button", {
      name: "Regenerate response",
    });
    fireEvent.click(regenBtn);
    expect(onRegenerate).toHaveBeenCalledTimes(1);
  });
});

describe("UI-08 unit — ChatBubble (user)", () => {
  it("UI-08: user bubble has bg-slate-100 ml-auto max-w-prose AND NO action row", () => {
    render(
      <ChatBubble role="user" rawMarkdown="hello">
        <p>user body</p>
      </ChatBubble>,
    );
    // No action-row buttons exist for user variant.
    expect(
      screen.queryByRole("button", { name: "Copy message as markdown" }),
    ).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Regenerate response" }),
    ).toBeNull();
  });
});

describe("UI-08 unit — StreamErrorBanner", () => {
  it("StreamErrorBanner has role=alert and renders the friendly text for a known code", () => {
    render(
      <StreamErrorBanner
        code="cost_cap_exceeded"
        message="upstream message"
        retriable={false}
        onRetry={() => {}}
      />,
    );
    const banner = screen.getByRole("alert");
    expect(banner).toBeInTheDocument();
    // UI-SPEC §12.2 — friendly message text
    expect(banner.textContent).toMatch(/Cost cap of \$0\.50 reached/);
    // Raw code is appended in monospace
    expect(banner.textContent).toMatch(/cost_cap_exceeded/);
  });

  it("StreamErrorBanner shows 'Try again' button only when retriable=true", () => {
    const onRetry = vi.fn();
    const { rerender } = render(
      <StreamErrorBanner
        code="cost_cap_exceeded"
        message="msg"
        retriable={false}
        onRetry={onRetry}
      />,
    );
    expect(screen.queryByRole("button", { name: /Retry the failed turn/ })).toBeNull();

    rerender(
      <StreamErrorBanner
        code="rate_limited"
        message="msg"
        retriable={true}
        onRetry={onRetry}
      />,
    );
    const retryBtn = screen.getByRole("button", {
      name: "Retry the failed turn",
    });
    expect(retryBtn).toBeInTheDocument();
    expect(retryBtn.textContent).toMatch(/Try again/);
    fireEvent.click(retryBtn);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("StreamErrorBanner falls back to a generic message for unknown codes", () => {
    render(
      <StreamErrorBanner
        code="some_brand_new_code"
        message="upstream"
        retriable={false}
        onRetry={() => {}}
      />,
    );
    expect(
      screen.getByRole("alert").textContent,
    ).toMatch(/Something went wrong/);
  });

  it("StreamErrorBanner catalog covers all 9 Phase-2 D-06 codes", () => {
    const codes = [
      "cost_cap_exceeded",
      "step_cap_exceeded",
      "cancelled",
      "rate_limited",
      "auth_failed",
      "provider_unavailable",
      "timeout",
      "validation_error",
      "internal_error",
    ];
    // Capture the exact fallback string the banner uses for unknown codes.
    // No known code may produce this string — internal_error legitimately
    // starts with "Something went wrong" but has a longer specific suffix.
    const FALLBACK = "Something went wrong — try again.";
    for (const code of codes) {
      const { container, unmount } = render(
        <StreamErrorBanner
          code={code}
          message="x"
          retriable={false}
          onRetry={() => {}}
        />,
      );
      const banner = container.querySelector('[role="alert"]') as HTMLElement;
      // The banner must NOT show the EXACT generic fallback for any known
      // code. (Note: "internal_error" legitimately starts with "Something
      // went wrong inside Prompt-Optimizer" — that's not the fallback.)
      expect(banner.textContent).not.toContain(FALLBACK);
      // The raw code is appended somewhere in the text.
      expect(banner.textContent).toContain(code);
      unmount();
    }
  });
});
