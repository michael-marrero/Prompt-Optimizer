// Plan 04-02 (Wave 1) — Task 3 unit test suite for apps/web/lib/thread-id.ts.
//
// Asserts:
//   (1) readDefaultThreadId returns null cleanly when typeof window ===
//       "undefined" (SSR-safe).
//   (2) getOrCreateDefaultThread first call: postThread is called once
//       and the returned id is stored in localStorage.
//   (3) getOrCreateDefaultThread second call: the cached id is returned
//       WITHOUT a second postThread invocation.
//
// Cross-refs:
//   - 04-CONTEXT.md Claude's Discretion ("Thread creation in minimal mode" —
//     localStorage key "prompt-optimizer.defaultThreadId")
//   - 04-RESEARCH.md §Open Question 6 (browser-driven thread creation path)

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock api-client.postThread BEFORE importing thread-id (which imports it).
vi.mock("@/lib/api-client", () => ({
  postThread: vi.fn(),
}));

// Re-import per-test so the mock's call count is fresh.
import { postThread } from "@/lib/api-client";
import {
  DEFAULT_THREAD_KEY,
  getOrCreateDefaultThread,
  readDefaultThreadId,
} from "@/lib/thread-id";

describe("thread-id — SSR guard + localStorage caching", () => {
  beforeEach(() => {
    // Reset the postThread mock and localStorage between tests.
    vi.mocked(postThread).mockReset();
    if (typeof localStorage !== "undefined") {
      localStorage.clear();
    }
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("readDefaultThreadId returns null cleanly when typeof window === 'undefined' (SSR-safe)", () => {
    // jsdom always provides a `window`. Stub it to undefined to simulate
    // SSR (Next 16 server component evaluation phase).
    vi.stubGlobal("window", undefined);

    // The function must not throw a ReferenceError and must return null.
    expect(readDefaultThreadId()).toBeNull();
  });

  it("readDefaultThreadId returns null when localStorage has no entry", () => {
    // jsdom provides window; localStorage is empty.
    expect(readDefaultThreadId()).toBeNull();
  });

  it("getOrCreateDefaultThread first call: calls postThread once, caches in localStorage, returns the id", async () => {
    vi.mocked(postThread).mockResolvedValueOnce({
      id: "test-tid-1",
      title: "Untitled",
    });

    const id = await getOrCreateDefaultThread();
    expect(id).toBe("test-tid-1");
    expect(postThread).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem(DEFAULT_THREAD_KEY)).toBe("test-tid-1");
  });

  it("getOrCreateDefaultThread second call: returns cached id WITHOUT a second postThread invocation", async () => {
    vi.mocked(postThread).mockResolvedValueOnce({
      id: "test-tid-1",
      title: "Untitled",
    });

    const first = await getOrCreateDefaultThread();
    expect(first).toBe("test-tid-1");
    expect(postThread).toHaveBeenCalledTimes(1);

    // Second call must hit the cache, not the network.
    const second = await getOrCreateDefaultThread();
    expect(second).toBe("test-tid-1");
    // Count stays at 1.
    expect(postThread).toHaveBeenCalledTimes(1);
  });

  it("DEFAULT_THREAD_KEY is the documented localStorage key", () => {
    expect(DEFAULT_THREAD_KEY).toBe("prompt-optimizer.defaultThreadId");
  });
});
