// Phase 5 Wave 0 — feedback proxy-route RED test suite (UI-15).
//
// VALIDATION.md row: "UI-15" → `pnpm --dir apps/web test feedback-route`.
//
// RED-by-design: `app/api/feedback/route.ts` does NOT exist yet. The import
// fails to resolve so every `it` is collected and reported FAILED until the
// proxy ships.
//
// What this asserts (PATTERNS feedback proxy + D-12 + UI-17):
//   - POST /api/feedback forwards the D-12 row to POST {FASTAPI}/api/v1/feedback
//   - a down upstream yields 503 with "API unavailable — is uvicorn running?"

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { POST as POST_FEEDBACK } from "@/app/api/feedback/route";

const FASTAPI = "http://localhost:8000";

// A representative D-12 feedback row (down sentiment).
const ROW = {
  sentiment: "down",
  thread_id: "t-1",
  message_id: "m-1",
  prompt: "What is the capital of France?",
  decision: {
    backend: "openrouter",
    model_or_agent: "openai/gpt-5",
    rationale: "Strong reasoning fit",
    confidence: 0.9,
    signals: { task_type: "chat" },
  },
};

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("UI-15 route — feedback proxy forwards", () => {
  it("UI-15: POST /api/feedback forwards the D-12 row to POST {FASTAPI}/api/v1/feedback", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const req = new Request("http://localhost/api/feedback", {
      method: "POST",
      body: JSON.stringify(ROW),
    });
    const res = await POST_FEEDBACK(req);
    expect(res.status).toBe(200);
    const fetchMock = fetch as ReturnType<typeof vi.fn>;
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${FASTAPI}/api/v1/feedback`);
    expect((init as RequestInit).method).toBe("POST");
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body.sentiment).toBe("down");
    expect(body.decision.backend).toBe("openrouter");
  });

  it("UI-15: returns 503 with the canonical proxy error when upstream is down", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("ECONNREFUSED"));
    const req = new Request("http://localhost/api/feedback", {
      method: "POST",
      body: JSON.stringify(ROW),
    });
    const res = await POST_FEEDBACK(req);
    expect(res.status).toBe(503);
    const body = await res.json();
    expect(body.error).toBe("API unavailable — is uvicorn running?");
  });

  it("UI-15: forwards an upstream non-2xx status verbatim (e.g. 422 extra='forbid')", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "extra fields not permitted" }), {
        status: 422,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const req = new Request("http://localhost/api/feedback", {
      method: "POST",
      body: JSON.stringify({ ...ROW, bogus: "field" }),
    });
    const res = await POST_FEEDBACK(req);
    expect(res.status).toBe(422);
  });
});
