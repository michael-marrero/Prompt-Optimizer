// Phase 5 Wave 0 — thread proxy-route RED test suite (UI-02).
//
// VALIDATION.md row: "UI-02 unit (route)" → `pnpm --dir apps/web test threads-route`.
//
// RED-by-design: the GET-list handler on `app/api/threads/route.ts` and the
// PATCH/DELETE handlers on `app/api/threads/[id]/route.ts` do NOT exist yet.
// Importing a not-yet-exported handler yields `undefined`, so calling it throws
// — the RED signal. Each `it` is collected and reported FAILED until the
// handlers ship.
//
// What this asserts (PATTERNS Next-proxy skeleton + Next-16 Promise params):
//   - GET /api/threads  → forwards to GET  {FASTAPI}/api/v1/threads
//   - PATCH /api/threads/[id] → forwards {title} to PATCH {FASTAPI}/api/v1/threads/{id}
//   - DELETE /api/threads/[id] → forwards to DELETE {FASTAPI}/api/v1/threads/{id} (204)

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { GET as GET_LIST } from "@/app/api/threads/route";
import {
  PATCH as PATCH_THREAD,
  DELETE as DELETE_THREAD,
} from "@/app/api/threads/[id]/route";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const FASTAPI = "http://localhost:8000";

describe("UI-02 route — threads proxy forwards", () => {
  it("UI-02: GET /api/threads forwards to GET {FASTAPI}/api/v1/threads", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify([{ id: "t-1", title: "x" }]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const res = await GET_LIST(new Request("http://localhost/api/threads"));
    expect(res.status).toBe(200);
    const fetchMock = fetch as ReturnType<typeof vi.fn>;
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${FASTAPI}/api/v1/threads`);
    // GET — no method or method:"GET".
    expect((init as RequestInit | undefined)?.method ?? "GET").toBe("GET");
  });

  it("UI-02: PATCH /api/threads/[id] forwards {title} to PATCH {FASTAPI}/api/v1/threads/{id}", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify({ id: "t-1", title: "Renamed" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const req = new Request("http://localhost/api/threads/t-1", {
      method: "PATCH",
      body: JSON.stringify({ title: "Renamed" }),
    });
    const res = await PATCH_THREAD(req, { params: Promise.resolve({ id: "t-1" }) });
    expect(res.status).toBe(200);
    const fetchMock = fetch as ReturnType<typeof vi.fn>;
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${FASTAPI}/api/v1/threads/t-1`);
    expect((init as RequestInit).method).toBe("PATCH");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      title: "Renamed",
    });
  });

  it("UI-02: DELETE /api/threads/[id] forwards to DELETE {FASTAPI}/api/v1/threads/{id} (204)", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(null, { status: 204 }),
    );
    const req = new Request("http://localhost/api/threads/t-1", {
      method: "DELETE",
    });
    const res = await DELETE_THREAD(req, { params: Promise.resolve({ id: "t-1" }) });
    expect(res.status).toBe(204);
    const fetchMock = fetch as ReturnType<typeof vi.fn>;
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${FASTAPI}/api/v1/threads/t-1`);
    expect((init as RequestInit).method).toBe("DELETE");
  });

  it("UI-02: a down upstream yields 503 with the canonical proxy error", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("ECONNREFUSED"));
    const res = await GET_LIST(new Request("http://localhost/api/threads"));
    expect(res.status).toBe(503);
    const body = await res.json();
    expect(body.error).toBe("API unavailable — is uvicorn running?");
  });
});
