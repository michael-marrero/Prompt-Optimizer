// Phase 5 Wave 0 — auto-rename orchestration RED test suite (UI-14, D-08/D-09/D-10).
//
// VALIDATION.md row: "UI-14 unit" → `pnpm --dir apps/web test auto-rename`.
//
// RED-by-design: `@/lib/auto-rename` does NOT exist yet (the helper is the
// contract that a later plan, 05-05, implements). The import fails to resolve so
// every `it` is collected and reported FAILED until the helper ships.
//
// What this asserts:
//   - D-08: the rename POST fires in PARALLEL with the turn (not awaited before send)
//   - D-09: a 400/413/failure response falls back to the first user message
//           truncated to 40 chars with an ellipsis
//   - D-10: once-only guard — does NOT fire when the title is already non-default
//           or when it is not the first user message

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { maybeAutoRenameThread } from "@/lib/auto-rename";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("UI-14 unit — maybeAutoRenameThread (D-08/D-09/D-10)", () => {
  it("D-08: fires the rename POST to /api/threads/{id}/rename without awaiting the turn", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify({ title: "Capital of France" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const title = await maybeAutoRenameThread({
      threadId: "t-1",
      currentTitle: "Untitled",
      firstUserMessage: "What is the capital of France?",
      isFirstUserMessage: true,
    });
    const fetchMock = fetch as ReturnType<typeof vi.fn>;
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/threads/t-1/rename");
    expect((init as RequestInit).method).toBe("POST");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      first_user_message: "What is the capital of France?",
    });
    expect(title).toBe("Capital of France");
  });

  it("D-09: a 400 (no key) falls back to the first message truncated to 40 chars + ellipsis", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "no openrouter key" }), { status: 400 }),
    );
    const longMessage =
      "Build me a small finance tracker app with charts and budgets and categories";
    const title = await maybeAutoRenameThread({
      threadId: "t-1",
      currentTitle: "Untitled",
      firstUserMessage: longMessage,
      isFirstUserMessage: true,
    });
    // First 40 chars + single-character ellipsis (U+2026).
    expect(title).toBe(longMessage.slice(0, 40) + "…");
    expect(title.length).toBe(41);
  });

  it("D-09: a 413 (too long) also falls back to the truncated first message", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response("too long", { status: 413 }),
    );
    const title = await maybeAutoRenameThread({
      threadId: "t-1",
      currentTitle: "Untitled",
      firstUserMessage: "Open this URL and check the price please",
      isFirstUserMessage: true,
    });
    expect(title).toBe("Open this URL and check the price please"); // ≤40? it's 40 chars
  });

  it("D-09: a network failure falls back to the truncated first message", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("ECONNREFUSED"));
    const title = await maybeAutoRenameThread({
      threadId: "t-1",
      currentTitle: "Untitled",
      firstUserMessage: "short prompt",
      isFirstUserMessage: true,
    });
    // Shorter than 40 chars → no ellipsis.
    expect(title).toBe("short prompt");
  });

  it("D-10: does NOT fire when the title is already non-default", async () => {
    const title = await maybeAutoRenameThread({
      threadId: "t-1",
      currentTitle: "A user-set title",
      firstUserMessage: "What is the capital of France?",
      isFirstUserMessage: true,
    });
    expect(fetch).not.toHaveBeenCalled();
    // No rename → returns the existing title unchanged.
    expect(title).toBe("A user-set title");
  });

  it("D-10: does NOT fire when it is not the first user message", async () => {
    const title = await maybeAutoRenameThread({
      threadId: "t-1",
      currentTitle: "Untitled",
      firstUserMessage: "follow-up message",
      isFirstUserMessage: false,
    });
    expect(fetch).not.toHaveBeenCalled();
    expect(title).toBe("Untitled");
  });
});
