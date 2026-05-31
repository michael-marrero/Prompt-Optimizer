// Phase 9 Wave-0 RED test suite — StreamErrorBanner (RELI-04 / D-07).
//
// VALIDATION.md row RELI-04: "Banner: friendly text + (code) + retry for
// retriable; collapsible redacted detail".
//
// Three cases:
//   1. (GREEN today) renders friendly text + (code) + a "Try again"
//      affordance for a retriable code — the Phase 4/5 baseline contract.
//   2. (RED) renders the two new D-05 codes (wall_clock_exceeded,
//      budget_exceeded) with FRIENDLY copy — fails until Plan 04 adds them
//      to FRIENDLY_MESSAGES (today they fall back to the generic message).
//   3. (RED) exposes a collapsible "Details" disclosure showing the
//      (already-redacted) `message` prop — fails until Plan 04 adds the
//      <details> element (today the `message` prop is accepted but never
//      rendered).
//
// RED convention: cases 2 + 3 use `it.fails(...)` so they are COLLECTABLE
// and report failing (RED) against today's component; the owning plan
// removes the `.fails` marker when the behavior lands (at which point an
// unexpected pass flips `it.fails` red, signaling the flip).
//
// Cross-refs:
//   - apps/web/components/StreamErrorBanner.tsx (FRIENDLY_MESSAGES + message prop)
//   - apps/api/backends/chunks.py StreamError.code (11-value vocabulary)

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { StreamErrorBanner } from "@/components/StreamErrorBanner";

describe("RELI-04 — StreamErrorBanner", () => {
  it("renders friendly text + (code) + a Try again button for a retriable code", () => {
    render(
      <StreamErrorBanner
        code="rate_limited"
        message="429 from upstream"
        retriable={true}
        onRetry={vi.fn()}
      />,
    );
    // Friendly copy for the known code …
    expect(
      screen.getByText(/rate-limiting/i),
    ).toBeInTheDocument();
    // … the raw (code) annotation …
    expect(screen.getByText("(rate_limited)")).toBeInTheDocument();
    // … and a "Try again" affordance for the retriable code.
    expect(
      screen.getByRole("button", { name: "Retry the failed turn" }),
    ).toBeInTheDocument();
  });

  it.fails(
    "renders FRIENDLY copy for the two new D-05 codes (RED until Plan 04)",
    () => {
      const { rerender } = render(
        <StreamErrorBanner
          code="wall_clock_exceeded"
          message="deadline"
          retriable={false}
          onRetry={vi.fn()}
        />,
      );
      // Target: a bespoke wall-clock message, NOT the generic fallback.
      expect(
        screen.queryByText(/Something went wrong/i),
      ).not.toBeInTheDocument();
      expect(screen.getByText("(wall_clock_exceeded)")).toBeInTheDocument();

      rerender(
        <StreamErrorBanner
          code="budget_exceeded"
          message="over budget"
          retriable={false}
          onRetry={vi.fn()}
        />,
      );
      // Target: a bespoke budget message, NOT the generic fallback.
      expect(
        screen.queryByText(/Something went wrong/i),
      ).not.toBeInTheDocument();
      expect(screen.getByText("(budget_exceeded)")).toBeInTheDocument();
    },
  );

  it.fails(
    "exposes a collapsible Details disclosure showing the message prop (RED until Plan 04 / D-07)",
    () => {
      const technical = "RequestId 0xDEADBEEF — upstream 503 after 2 retries";
      render(
        <StreamErrorBanner
          code="provider_unavailable"
          message={technical}
          retriable={true}
          onRetry={vi.fn()}
        />,
      );
      // Target: a <details>/<summary> "Details" disclosure that surfaces the
      // (already-redacted) technical message for power users.
      const details = screen.getByText("Details");
      expect(details).toBeInTheDocument();
      expect(screen.getByText(technical)).toBeInTheDocument();
    },
  );
});
