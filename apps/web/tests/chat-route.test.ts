// Phase 5 Wave 1 — /api/chat override_backend forwarding test (UI-05, D-01).
//
// VALIDATION.md row: "UI-05 override forward" → `pnpm --dir apps/web test chat-route`.
//
// 05-00 did not author a chat-route test (chat/route.ts shipped in Phase 4);
// 05-03 Task 3 owns this assertion: when the inbound body carries
// `override_backend`, the forwarded FastAPI turn body MUST include it; when
// absent, the forwarded body MUST omit it (so the 05-01 allowlist filter
// runs on auto turns). The SSE streaming path is unchanged — we mock the
// translator to a passthrough so the test focuses on the outbound body.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock the translator: return the upstream body untouched so the route's
// streaming return path stays exercised without parsing real SSE bytes.
vi.mock("@/lib/sse-translate", () => ({
  translateNamedSSEToUIMessageStream: (body: ReadableStream) => body,
}));

import { POST as POST_CHAT } from "@/app/api/chat/route";

const FASTAPI = "http://localhost:8000";

// A minimal 2xx streaming upstream response (has a body so the route takes
// the streaming branch and never `await upstream.text()`s it — Pitfall 2).
function streamingUpstream(): Response {
  const body = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode("event: done\ndata: {}\n\n"));
      controller.close();
    },
  });
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

function chatRequest(body: Record<string, unknown>): Request {
  return new Request("http://localhost/api/chat", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

const USER_MESSAGE = {
  role: "user",
  parts: [{ type: "text", text: "What is the capital of France?" }],
};

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("UI-05 /api/chat — override_backend forwarding", () => {
  it("forwards override_backend to the FastAPI turn body when present", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      streamingUpstream(),
    );
    const res = await POST_CHAT(
      chatRequest({
        messages: [USER_MESSAGE],
        threadId: "t-1",
        override_backend: "claude_code",
      }),
    );
    // Streaming response — stream header preserved, body not buffered here.
    expect(res.headers.get("x-vercel-ai-ui-message-stream")).toBe("v1");

    const fetchMock = fetch as ReturnType<typeof vi.fn>;
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${FASTAPI}/api/v1/threads/t-1/turn`);
    const forwarded = JSON.parse((init as RequestInit).body as string);
    expect(forwarded.message).toBe("What is the capital of France?");
    expect(forwarded.override_backend).toBe("claude_code");
  });

  it("omits override_backend from the forwarded body on an auto turn", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      streamingUpstream(),
    );
    const res = await POST_CHAT(
      chatRequest({ messages: [USER_MESSAGE], threadId: "t-1" }),
    );
    expect(res.headers.get("x-vercel-ai-ui-message-stream")).toBe("v1");

    const fetchMock = fetch as ReturnType<typeof vi.fn>;
    const [, init] = fetchMock.mock.calls[0];
    const forwarded = JSON.parse((init as RequestInit).body as string);
    expect(forwarded.message).toBe("What is the capital of France?");
    expect("override_backend" in forwarded).toBe(false);
  });

  it("omits override_backend when it is an empty string", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      streamingUpstream(),
    );
    await POST_CHAT(
      chatRequest({
        messages: [USER_MESSAGE],
        threadId: "t-1",
        override_backend: "",
      }),
    );
    const fetchMock = fetch as ReturnType<typeof vi.fn>;
    const [, init] = fetchMock.mock.calls[0];
    const forwarded = JSON.parse((init as RequestInit).body as string);
    expect("override_backend" in forwarded).toBe(false);
  });
});
