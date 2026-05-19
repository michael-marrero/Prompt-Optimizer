// Plan 04-07 Wave 6 — useFirstRunGate RTL unit suite.
//
// VALIDATION.md rows wired by this test: UI-13 (unit) + D-16 + D-19.
//
// What this asserts (RESEARCH Pattern 8 + CONTEXT D-16 + D-19):
//   - On mount the hook calls api-client.getHealth() exactly once
//   - When getHealth resolves with adapters.openrouter.status === "ready",
//     hook state flips to {isReady: true, needsKey: false}
//   - When status === "missing_key", state flips to
//     {isReady: false, needsKey: true} — first-run modal trigger
//   - When getHealth rejects (network down / proxy returns 503), state
//     stays {isReady: false, needsKey: false} — network-down is DISTINCT
//     from missing-key (UI surfaces the NetworkDownBanner, NOT the modal)
//   - Dispatching `window.dispatchEvent(new CustomEvent("pomu:key-saved"))`
//     triggers a fresh getHealth call (D-19 post-entry unblock)
//   - Dispatching a "visibilitychange" event with
//     document.visibilityState === "visible" triggers a fresh getHealth
//     call (D-16 second trigger source — user added a key in another
//     tab/process)
//
// Cross-refs:
//   - 04-CONTEXT.md D-16 (two independent missing-key triggers)
//   - 04-CONTEXT.md D-19 (post-entry unblock event)
//   - 04-RESEARCH.md §"Pattern 8" lines 928-1023 (boot sequence)

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";

vi.mock("@/lib/api-client", () => ({
  getHealth: vi.fn(),
}));

import { getHealth } from "@/lib/api-client";
import { useFirstRunGate } from "@/hooks/useFirstRunGate";

const mockedGetHealth = getHealth as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockedGetHealth.mockReset();
});

describe("UI-13 unit — useFirstRunGate", () => {
  it("calls getHealth once on mount", async () => {
    mockedGetHealth.mockResolvedValue({
      adapters: { openrouter: { status: "ready" } },
    });
    renderHook(() => useFirstRunGate());
    await waitFor(() => {
      expect(mockedGetHealth).toHaveBeenCalledTimes(1);
    });
  });

  it("flips to {isReady: true, needsKey: false} on status='ready'", async () => {
    mockedGetHealth.mockResolvedValue({
      adapters: { openrouter: { status: "ready" } },
    });
    const { result } = renderHook(() => useFirstRunGate());
    await waitFor(() => {
      expect(result.current.isReady).toBe(true);
    });
    expect(result.current.needsKey).toBe(false);
  });

  it("flips to {isReady: false, needsKey: true} on status='missing_key' (D-16 trigger)", async () => {
    mockedGetHealth.mockResolvedValue({
      adapters: { openrouter: { status: "missing_key" } },
    });
    const { result } = renderHook(() => useFirstRunGate());
    await waitFor(() => {
      expect(result.current.needsKey).toBe(true);
    });
    expect(result.current.isReady).toBe(false);
  });

  it("stays {isReady: false, needsKey: false} on fetch failure (network-down distinct from missing-key)", async () => {
    mockedGetHealth.mockRejectedValue(new Error("503 Service Unavailable"));
    const { result } = renderHook(() => useFirstRunGate());
    // Give the hook's effect a turn of the event loop to settle.
    await waitFor(() => {
      expect(mockedGetHealth).toHaveBeenCalled();
    });
    // Network down: needsKey must NOT be true (otherwise the modal would
    // appear on every transient API outage). The NetworkDownBanner is the
    // separate surface for this state.
    expect(result.current.needsKey).toBe(false);
    expect(result.current.isReady).toBe(false);
  });

  it("re-fetches /api/health when the 'pomu:key-saved' window event fires (D-19 unblock)", async () => {
    mockedGetHealth.mockResolvedValue({
      adapters: { openrouter: { status: "missing_key" } },
    });
    renderHook(() => useFirstRunGate());
    await waitFor(() => {
      expect(mockedGetHealth).toHaveBeenCalledTimes(1);
    });

    // Simulate KeyForm dispatching the success event.
    await act(async () => {
      window.dispatchEvent(new CustomEvent("pomu:key-saved"));
    });

    await waitFor(() => {
      expect(mockedGetHealth).toHaveBeenCalledTimes(2);
    });
  });

  it("re-fetches /api/health on visibilitychange when document is visible (D-16 second trigger)", async () => {
    mockedGetHealth.mockResolvedValue({
      adapters: { openrouter: { status: "ready" } },
    });
    renderHook(() => useFirstRunGate());
    await waitFor(() => {
      expect(mockedGetHealth).toHaveBeenCalledTimes(1);
    });

    // jsdom defaults document.visibilityState to "visible".
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
    });

    await waitFor(() => {
      expect(mockedGetHealth).toHaveBeenCalledTimes(2);
    });
  });

  it("exposes a refresh() function that re-fetches /api/health on demand", async () => {
    mockedGetHealth.mockResolvedValue({
      adapters: { openrouter: { status: "ready" } },
    });
    const { result } = renderHook(() => useFirstRunGate());
    await waitFor(() => {
      expect(mockedGetHealth).toHaveBeenCalledTimes(1);
    });

    await act(async () => {
      await result.current.refresh();
    });
    expect(mockedGetHealth).toHaveBeenCalledTimes(2);
  });

  it("cleans up listeners on unmount (no extra fetches after the hook is gone)", async () => {
    mockedGetHealth.mockResolvedValue({
      adapters: { openrouter: { status: "ready" } },
    });
    const { unmount } = renderHook(() => useFirstRunGate());
    await waitFor(() => {
      expect(mockedGetHealth).toHaveBeenCalledTimes(1);
    });

    unmount();
    mockedGetHealth.mockClear();
    // After unmount these events MUST NOT trigger any further fetches.
    window.dispatchEvent(new CustomEvent("pomu:key-saved"));
    document.dispatchEvent(new Event("visibilitychange"));
    // Allow microtasks to flush.
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(mockedGetHealth).not.toHaveBeenCalled();
  });
});
