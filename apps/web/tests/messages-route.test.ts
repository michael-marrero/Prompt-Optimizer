// Phase 8 Plan 08-00 Wave 0 — SC-2 RED Next-proxy unit.
//
// 08-VALIDATION.md SC-2 (unit half): the Next route handler at
// `app/api/threads/[id]/messages/route.ts` forwards a GET to
// `${FASTAPI}/api/v1/threads/{id}/messages`, maps a connect-refused upstream to
// the canonical 503 banner, and passes a 404 upstream through verbatim. The
// browser-isolation e2e half (SC-2) lives in browser-isolation.spec.ts.
//
// RED-by-design: `@/app/api/threads/[id]/messages/route` does NOT exist yet.
// Importing the not-yet-authored `GET` export yields `undefined`, so the import
// fails to resolve and every `it` is collected + FAILED until 08-01 ships the
// proxy. This is a missing-IMPLEMENTATION failure, NOT a malformed-test error.
//
// Mirrors apps/web/tests/threads-route.test.ts exactly:
//   - vi.stubGlobal("fetch", vi.fn()) per test; vi.unstubAllGlobals() teardown
//   - assert the forwarded upstream URL
//   - 503-on-down-upstream with the canonical proxy error (U+2014 em-dash)
//   - params: Promise.resolve({ id }) — Next 16 promise params
//
// Cross-refs:
//   - 08-PLAN-00 Task 3 (a) + 08-RESEARCH.md §"SC-2 Next-proxy unit test skeleton"
//   - 08-PATTERNS.md §"apps/web/tests/messages-route.test.ts"
//   - apps/web/tests/threads-route.test.ts (the analog this mirrors)
//   - apps/web/app/api/threads/[id]/route.ts (the GET proxy being mirrored)

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { GET } from "@/app/api/threads/[id]/messages/route";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const FASTAPI = "http://localhost:8000";

describe("SC-2 route — messages proxy forwards (browser→Next→FastAPI only)", () => {
  it("forwards to GET {FASTAPI}/api/v1/threads/{id}/messages", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const res = await GET(
      new Request("http://localhost/api/threads/t-1/messages"),
      { params: Promise.resolve({ id: "t-1" }) },
    );

    expect(res.status).toBe(200);
    const fetchMock = fetch as ReturnType<typeof vi.fn>;
    const [url, init] = fetchMock.mock.calls[0];
    // Exact forwarded upstream URL — the SC-2 contract.
    expect(url).toBe(`${FASTAPI}/api/v1/threads/t-1/messages`);
    // GET — no method, or method:"GET".
    expect((init as RequestInit | undefined)?.method ?? "GET").toBe("GET");
  });

  it("a down upstream yields 503 with the canonical proxy error", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error("ECONNREFUSED"),
    );

    const res = await GET(
      new Request("http://localhost/api/threads/t-1/messages"),
      { params: Promise.resolve({ id: "t-1" }) },
    );

    expect(res.status).toBe(503);
    const body = await res.json();
    // U+2014 em-dash verbatim — the canonical "API unavailable" banner.
    expect(body.error).toBe("API unavailable — is uvicorn running?");
  });

  it("passes a 404 upstream through verbatim (unknown thread)", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "thread not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const res = await GET(
      new Request("http://localhost/api/threads/nope/messages"),
      { params: Promise.resolve({ id: "nope" }) },
    );

    // 404 flows through so the client distinguishes "no such thread" from
    // "server down" (D-01/D-03 empty-state vs not-found).
    expect(res.status).toBe(404);
    const fetchMock = fetch as ReturnType<typeof vi.fn>;
    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe(`${FASTAPI}/api/v1/threads/nope/messages`);
  });

  it("encodeURIComponent-escapes the thread id in the forwarded URL", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await GET(new Request("http://localhost/api/threads/a%2Fb/messages"), {
      params: Promise.resolve({ id: "a/b" }),
    });

    const fetchMock = fetch as ReturnType<typeof vi.fn>;
    const [url] = fetchMock.mock.calls[0];
    // The "/" in the id must be percent-encoded so it cannot alter the path.
    expect(url).toBe(`${FASTAPI}/api/v1/threads/a%2Fb/messages`);
  });
});
