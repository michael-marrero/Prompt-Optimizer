// Plan 04-02 (Wave 1) — Task 3 unit test suite for apps/web/lib/api-client.ts.
//
// Asserts:
//   (1) postSettings throws an Error whose .message does NOT contain the
//       literal key string when the upstream returns non-2xx — D-18
//       belt-and-suspenders at the wrapper layer (T-04-10 mitigation).
//   (2) postSettings happy-path returns the typed {keys: {...}} payload.
//
// Cross-refs:
//   - 04-CONTEXT.md D-18 (key-handling rules — key NEVER leaks)
//   - 04-PATTERNS.md Pattern B (same-origin /api/* paths; no FASTAPI_URL leak)
//   - 04-VALIDATION.md "secure-key" Playwright spec (Phase 4 E2E follow-up)

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { postSettings } from "@/lib/api-client";

// The literal-shaped OpenRouter key the test posts and then greps for.
// Identical-shape to real keys (`sk-or-v1-...`) so the scrubber must match.
const TEST_KEY = "sk-or-v1-LITERAL_SECRET_TEST_KEY_DO_NOT_LEAK";

describe("api-client.postSettings — D-18 belt: key never leaks in errors", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("on 500 response: thrown Error.message does NOT contain the literal key", async () => {
    // Worst-case upstream — response body echoes the key (some FastAPI error
    // serializers do this when validation fails). The wrapper must scrub.
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(`Invalid key value: ${TEST_KEY}`, {
        status: 500,
        statusText: "Internal Server Error",
      }),
    );

    let thrown: unknown = null;
    try {
      await postSettings("openrouter", TEST_KEY);
    } catch (err) {
      thrown = err;
    }
    expect(thrown).toBeInstanceOf(Error);
    const message = (thrown as Error).message;
    // CRITICAL: the literal key must not appear anywhere in the message.
    expect(message).not.toContain(TEST_KEY);
    expect(message).not.toMatch(/sk-or-v1-LITERAL_SECRET_TEST_KEY_DO_NOT_LEAK/);
  });

  it("on network error: thrown error message does NOT contain the literal key", async () => {
    // fetch itself rejects (e.g. ECONNREFUSED). The wrapper should still
    // scrub the key from any re-thrown error.
    const networkErr = new Error(
      `connect ECONNREFUSED: payload had ${TEST_KEY}`,
    );
    (fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(networkErr);

    let thrown: unknown = null;
    try {
      await postSettings("openrouter", TEST_KEY);
    } catch (err) {
      thrown = err;
    }
    expect(thrown).toBeInstanceOf(Error);
    expect((thrown as Error).message).not.toContain(TEST_KEY);
  });

  it("happy-path 200 returns the typed {keys: {...}} response", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          keys: {
            openrouter: { present: true, masked: "sk-or-...ABC" },
          },
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    const result = await postSettings("openrouter", TEST_KEY);
    expect(result.keys.openrouter.present).toBe(true);
    expect(result.keys.openrouter.masked).toBe("sk-or-...ABC");
  });

  it("POSTs to /api/settings (same-origin) with {provider, key} body", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify({ keys: {} }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await postSettings("openrouter", TEST_KEY);
    const fetchMock = fetch as ReturnType<typeof vi.fn>;
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/settings");
    expect((init as RequestInit).method).toBe("POST");
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body.provider).toBe("openrouter");
    expect(body.key).toBe(TEST_KEY);
  });
});
