// Phase 8 Plan 08-04 Wave 4 — SC-3 component-dispatch test (the RENDER half).
//
// 08-VALIDATION.md SC-3 sampling: "A component-level test mounts `MessageBubble`
// over a seeded message and asserts `data-testid` = `code-bubble` /
// `computer-use-bubble` / `chat-bubble` accordingly (mirrors `page-shell.test.tsx`'s
// existing dispatch assertion). Sampling = all 3 backends + override variant →
// all 3 testids + pill aria-label."
//
// This is the rendered-bubble half of SC-3. The reconstruction-SHAPE half lives
// in `restore-messages.test.ts` (08-02): it asserts the WIRE-shape parts
// `reconstructUIMessages` produces (`{type:"data-routing", data}`, no `name`).
// THIS test asserts what those reconstructed parts RENDER as, once
// `@assistant-ui/react-ai-sdk`'s `convertParts` has stripped the `data-` prefix to
// `name` — i.e. the CONVERTED shape (`{type:"data", name:"routing", data}`) that
// every bubble component actually reads off `useMessage().content`. We feed the
// CONVERTED shape directly (mocking `useMessage`), bypassing `convertParts`
// exactly the way `page-shell.test.tsx:34-86` does — keeping the two concerns
// (reconstruction vs. render) separate per 08-PATTERNS §"Component-dispatch half
// of SC-3".
//
// To prove the WIRE→CONVERTED parity is real (not just hand-waved), the
// openrouter case derives its CONVERTED parts by running the actual
// `reconstructUIMessages` reader over a `MessageRow` and applying the documented
// `data-<x>` → `{type:"data", name:"<x>"}` transform inline (the same substring
// strip `convertParts` performs at `convertMessage.js:242-248`). The other cases
// hand-build the CONVERTED parts mirroring `messageForBackend`.
//
// Dispatch contract (MessageBubble.tsx:98-115, UI-SPEC §16):
//   claude_code  → data-testid="code-bubble"        (CodeBubble)
//   computer_use → data-testid="computer-use-bubble" (ComputerUseBubble)
//   openrouter / default / no routing part → data-testid="chat-bubble" (ChatBubble)
//
// Pill contract (RoutingChip.tsx:117,141):
//   auto turn      → aria-label "Routed to {displayName} — {rationale}" (U+2014)
//   override turn  → neutral "manual override" pill,
//                    aria-label "Manual override: forced to {name}"
//
// Cross-refs:
//   - apps/web/tests/page-shell.test.tsx:34-86 (messageForBackend + dispatch assert)
//   - apps/web/tests/code-bubble.test.tsx:24-55 (useMessage mock + render-assert)
//   - apps/web/components/MessageBubble.tsx (the dispatch + RoutingChip mount)
//   - apps/web/components/RoutingChip.tsx (the pill aria-label / override pill)
//   - apps/web/lib/reconstruct-messages.ts (the 08-02 reader fed in the parity case)
//   - 08-PATTERNS.md §"restore-messages.test.ts"; 08-VALIDATION.md §SC-3

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MessageBubble } from "@/components/MessageBubble";
import {
  reconstructUIMessages,
  type MessageRow,
} from "@/lib/reconstruct-messages";

// MessageBubble reads useMessage()/useMessageRuntime() (MessageBubble.tsx:73,78);
// RoutingChip + the leaf bubbles read useMessage().content. Mock both so the
// dispatch seam is assertable without the live assistant-ui runtime (the exact
// page-shell.test.tsx:25-28 pattern).
vi.mock("@assistant-ui/react", () => ({
  useMessage: vi.fn(),
  useMessageRuntime: vi.fn(() => ({ reload: vi.fn() })),
}));

import { useMessage } from "@assistant-ui/react";

const mockedUseMessage = useMessage as unknown as ReturnType<typeof vi.fn>;

// ---------------------------------------------------------------------------
// CONVERTED-shape part builders (what convertParts produces; what components
// READ). `{type:"data", name:"<x>", data}` — NOT the wire `data-<x>` shape.
// ---------------------------------------------------------------------------
type ConvertedPart =
  | { type: "data"; name: string; data: Record<string, unknown> }
  | { type: "text"; text: string };

/** Build a CONVERTED-shape assistant message for a given backend + model +
 *  rationale, mirroring page-shell.test.tsx's `messageForBackend`. */
function convertedMessage(opts: {
  backend: string;
  model_or_agent: string;
  rationale: string;
  signals?: Record<string, unknown>;
}): { id: string; status: { type: string }; content: ConvertedPart[] } {
  return {
    id: "m-1",
    status: { type: "complete" },
    content: [
      {
        type: "data",
        name: "routing",
        data: {
          backend: opts.backend,
          model_or_agent: opts.model_or_agent,
          rationale: opts.rationale,
          confidence: 1,
          signals: opts.signals ?? {},
        },
      },
      {
        type: "data",
        name: "metrics",
        data: {
          cost_usd: 0.0001,
          latency_ms: 42,
          tokens_in: 3,
          tokens_out: 2,
        },
      },
      { type: "text", text: "answer body" },
    ],
  };
}

/** Apply the documented WIRE→CONVERTED transform `convertParts` performs:
 *  `data-<name>` → `{type:"data", name:"<name>", data}` (substring(5) strip,
 *  convertMessage.js:242-248). Text parts pass through unchanged. This lets the
 *  openrouter case render the EXACT parts the 08-02 reconstruction reader
 *  produces, proving the parity is real. */
function convertReconstructedParts(
  parts: ReadonlyArray<{ type: string } & Record<string, unknown>>,
): ConvertedPart[] {
  return parts.map((p) => {
    if (typeof p.type === "string" && p.type.startsWith("data-")) {
      return {
        type: "data",
        name: p.type.substring(5),
        data: p.data as Record<string, unknown>,
      };
    }
    return p as unknown as ConvertedPart;
  });
}

beforeEach(() => {
  mockedUseMessage.mockReset();
});

describe("SC-3 component-dispatch — restored message renders the right bubble per backend", () => {
  it("claude_code → data-testid=code-bubble (CodeBubble)", () => {
    mockedUseMessage.mockReturnValue(
      convertedMessage({
        backend: "claude_code",
        model_or_agent: "claude-code",
        rationale: "build-and-edit task",
      }),
    );
    render(<MessageBubble />);
    expect(screen.getByTestId("code-bubble")).toBeInTheDocument();
  });

  it("computer_use → data-testid=computer-use-bubble (ComputerUseBubble)", () => {
    mockedUseMessage.mockReturnValue(
      convertedMessage({
        backend: "computer_use",
        model_or_agent: "computer-use",
        rationale: "browse-and-act task",
      }),
    );
    render(<MessageBubble />);
    expect(screen.getByTestId("computer-use-bubble")).toBeInTheDocument();
  });

  it("openrouter → data-testid=chat-bubble (ChatBubble) — fed via the real reconstruct-messages reader", () => {
    // Drive the CONVERTED parts from the ACTUAL 08-02 reconstruction reader so
    // this case exercises the real WIRE→CONVERTED parity, not a hand-built shape.
    const row: MessageRow = {
      id: "m-or",
      role: "assistant",
      text: "Paris is the capital of France.",
      content_blocks: [],
      backend_used: "openrouter",
      model_used: "openai/gpt-5",
      cost_usd: 0.0001,
      latency_ms: 42,
      tokens_in: 3,
      tokens_out: 2,
      status: "complete",
      routing: { rationale: "Strong reasoning fit", override: false },
    };
    const [uiMessage] = reconstructUIMessages([row]);
    const converted = convertReconstructedParts(
      uiMessage.parts as unknown as ReadonlyArray<
        { type: string } & Record<string, unknown>
      >,
    );
    mockedUseMessage.mockReturnValue({
      id: uiMessage.id,
      status: { type: "complete" },
      content: converted,
    });
    render(<MessageBubble />);
    expect(screen.getByTestId("chat-bubble")).toBeInTheDocument();
  });

  it("no routing part → defaults to chat-bubble (ChatBubble)", () => {
    mockedUseMessage.mockReturnValue({
      id: "m-1",
      status: { type: "complete" },
      content: [{ type: "text", text: "answer body" }],
    });
    render(<MessageBubble />);
    expect(screen.getByTestId("chat-bubble")).toBeInTheDocument();
  });
});

describe("SC-3 component-dispatch — restored message renders the right routing pill", () => {
  it("auto turn → optimized pill aria-label 'Routed to {model} — {reason}' (U+2014)", () => {
    mockedUseMessage.mockReturnValue(
      convertedMessage({
        backend: "openrouter",
        model_or_agent: "openai/gpt-5",
        rationale: "Strong reasoning fit",
      }),
    );
    render(<MessageBubble />);
    // Story 7.2: RoutingChip renders the "model · why" button carrying the FULL
    // un-truncated rationale on aria-label. Target it by accessible name (the
    // bubble also has copy/regenerate buttons).
    const why = screen.getByRole("button", { name: /^Routed to/u });
    const label = why.getAttribute("aria-label");
    expect(label).toMatch(/^Routed to .+ — .+$/u);
    // The em-dash is U+2014 (not a hyphen) and the rationale is carried verbatim.
    expect(label).toContain(" — Strong reasoning fit");
    expect(label).toContain("—");
  });

  it("override turn → neutral 'manual override' pill (NOT the optimized pill)", () => {
    mockedUseMessage.mockReturnValue(
      convertedMessage({
        backend: "openrouter",
        model_or_agent: "openai/gpt-5",
        rationale: "user override",
        signals: { override: true },
      }),
    );
    render(<MessageBubble />);
    // D-08: an override turn renders a DISTINCT neutral pill reading
    // "manual override", with the override aria-label — and NOT the optimized
    // "Routed to …" pill.
    const overridePill = screen.getByText("manual override");
    expect(overridePill).toBeInTheDocument();
    expect(overridePill.getAttribute("aria-label")).toMatch(
      /^Manual override: forced to /u,
    );
    expect(screen.queryByText("optimized")).not.toBeInTheDocument();
  });
});
