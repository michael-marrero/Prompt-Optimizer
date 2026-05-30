// Plan 04-05 Wave 4 — MetricsFooter RTL test suite.
//
// TODO(07): reconcile in Plan 07-05 (re-skin). 07-CONTEXT D-05 FOLDS
// MetricsFooter into the Plasma assistant footer stat row
// (latency · cost · model.short). These 18 assertions still PASS today
// (Phase-7 Wave-0 audit, 07-01) because the MetricsFooter component is NOT
// removed in Wave 0 — it is re-skinned/folded by its owning impl plan. NOT
// skipped here: deleting this coverage now would drop the UI-07 formatting
// contract before the fold lands. The owning plan reconciles the selector if
// the standalone component is absorbed.
//
// VALIDATION.md row: "UI-07 unit".
// Replaces the Plan 01 it.todo stub with real RTL renders.
//
// What this asserts (UI-SPEC §7 + Plan 04-05 must_haves):
//   - footer subscribes to `useMessage().parts` and finds the {type: "data", name: "metrics"} part
//     (assistant-ui v0.14.5 converts AI SDK v6 `data-metrics` parts into MessageState
//      parts of `{type: "data", name: "metrics", data: ...}`)
//   - mid-stream (no metrics yet) renders "streaming●" with animate-pulse + the streaming aria-label
//   - final state renders "$X.XXXX · X.Xs · X↑/X↓" per UI-SPEC §7.2 format rules
//   - latency <50ms renders "0.0s" (UI-SPEC §7.2)
//   - tokens >= 10000 use comma separator (UI-SPEC §7.2)
//   - aria-label format: "Turn cost <cost>, latency <latency>, <tokens_in> tokens in, <tokens_out> tokens out"

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MetricsFooter } from "@/components/MetricsFooter";

vi.mock("@assistant-ui/react", () => ({
  useMessage: vi.fn(),
}));

import { useMessage } from "@assistant-ui/react";

const mockedUseMessage = useMessage as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockedUseMessage.mockReset();
});

function withMetrics(data: {
  cost_usd: number | null;
  latency_ms: number | null;
  tokens_in: number | null;
  tokens_out: number | null;
}) {
  // assistant-ui exposes the data-metrics part on `content`, not `parts`.
  // See RoutingChip.tsx for the rationale.
  return {
    content: [
      {
        type: "data",
        name: "metrics",
        data,
      },
    ],
  };
}

describe("UI-07 unit — MetricsFooter", () => {
  it("UI-07: mid-stream (no metrics part) renders 'streaming●' with animate-pulse on the dot", () => {
    mockedUseMessage.mockReturnValue({ content: [] });
    render(<MetricsFooter />);
    const footer = screen.getByLabelText("Streaming response in progress");
    expect(footer.textContent).toMatch(/streaming/);
    // The dot has animate-pulse
    const dot = footer.querySelector(".animate-pulse");
    expect(dot).not.toBeNull();
    expect(dot?.textContent).toBe("●");
  });

  it("UI-07: final state renders '$0.0021 · 1.4s · 312↑/847↓' per UI-SPEC §7.2", () => {
    mockedUseMessage.mockReturnValue(
      withMetrics({
        cost_usd: 0.0021,
        latency_ms: 1400,
        tokens_in: 312,
        tokens_out: 847,
      }),
    );
    render(<MetricsFooter />);
    expect(screen.getByText(/\$0\.0021 · 1\.4s · 312↑\/847↓/)).toBeInTheDocument();
  });

  it("UI-07: cost_usd=0 renders '$0.0000' (UI-SPEC §7.2 zero rule)", () => {
    mockedUseMessage.mockReturnValue(
      withMetrics({
        cost_usd: 0,
        latency_ms: 1000,
        tokens_in: 10,
        tokens_out: 20,
      }),
    );
    render(<MetricsFooter />);
    expect(screen.getByText(/\$0\.0000/)).toBeInTheDocument();
  });

  it("UI-07: latency <50ms renders '0.0s' (UI-SPEC §7.2 latency rule)", () => {
    mockedUseMessage.mockReturnValue(
      withMetrics({
        cost_usd: 0.0001,
        latency_ms: 40,
        tokens_in: 5,
        tokens_out: 10,
      }),
    );
    render(<MetricsFooter />);
    expect(screen.getByText(/0\.0s/)).toBeInTheDocument();
  });

  it("UI-07: token counts >= 10000 use comma separator (UI-SPEC §7.2 token rule)", () => {
    mockedUseMessage.mockReturnValue(
      withMetrics({
        cost_usd: 0.0123,
        latency_ms: 2500,
        tokens_in: 12847,
        tokens_out: 5000,
      }),
    );
    render(<MetricsFooter />);
    expect(screen.getByText(/12,847↑/)).toBeInTheDocument();
  });

  it("UI-07: aria-label = 'Turn cost <cost>, latency <latency>, <in> tokens in, <out> tokens out'", () => {
    mockedUseMessage.mockReturnValue(
      withMetrics({
        cost_usd: 0.0021,
        latency_ms: 1400,
        tokens_in: 312,
        tokens_out: 847,
      }),
    );
    render(<MetricsFooter />);
    const footer = screen.getByLabelText(
      "Turn cost $0.0021, latency 1.4s, 312 tokens in, 847 tokens out",
    );
    expect(footer).toBeInTheDocument();
  });

  it("UI-07: footer uses font-mono and text-xs classes (UI-SPEC §7.1)", () => {
    mockedUseMessage.mockReturnValue({ content: [] });
    const { container } = render(<MetricsFooter />);
    const footer = container.firstChild as HTMLElement;
    expect(footer.className).toMatch(/font-mono/);
    expect(footer.className).toMatch(/text-xs/);
  });

  it("UI-07: nullable metrics (all fields null) render as $0.0000 · 0.0s · 0↑/0↓", () => {
    mockedUseMessage.mockReturnValue(
      withMetrics({
        cost_usd: null,
        latency_ms: null,
        tokens_in: null,
        tokens_out: null,
      }),
    );
    render(<MetricsFooter />);
    expect(screen.getByText(/\$0\.0000 · 0\.0s · 0↑\/0↓/)).toBeInTheDocument();
  });
});
