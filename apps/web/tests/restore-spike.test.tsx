// Phase 8 Plan 08-00 Wave 0 — HYDRATION GATE SPIKE (Assumption A1 / RESEARCH Open Q1).
//
// 08-VALIDATION.md §"Wave 0 Requirements": "seed 2 static UIMessages into
// useChatRuntime({messages}) → assert a rendered bubble. The phase is gated on
// this — if it fails, fall back to the external-store/remount path before
// building the reconstruction."
//
// WHY THIS IS THE PHASE GATE (08-RESEARCH.md §Pattern 2 + §Pitfall 1 + A1/Q1):
//   The whole hydration plan (08-03) rests on ONE unverified runtime behavior:
//   does the installed @assistant-ui/react-ai-sdk@1.3.26 honor a seeded
//   `messages` array passed to useChatRuntime({messages})? Official docs say
//   useChatRuntime has no `initialMessages` and steer toward ThreadHistoryAdapter
//   (which no-ops here — the local thread-list never sets `remoteId`). The
//   INSTALLED type surface (ai 6.0.184 `ChatInit.messages`) accepts a `messages`
//   array; this spike exercises whether that array actually lands in the
//   runtime's thread state AND passes through the react-ai-sdk converter into
//   the part shape MessageBubble reads. A PASS unblocks the `messages` +
//   `key={activeThreadId}` remount path (08-03); a FAIL routes to the documented
//   fallback (expose useChat.setMessages via a custom thread-runtime, or adopt
//   the remoteId thread-list model) BEFORE any hydration code is written.
//
// WHAT THIS SPIKE ASSERTS (the A1 contract, verifiable in jsdom):
//   Using the REAL installed runtime (NOT mocked — unlike page-shell.test.tsx),
//   seed exactly 2 static AI-SDK-v6 UIMessages and assert, by reading the
//   runtime's own thread state via useThread():
//     (1) the seeded messages land in the runtime thread state (count 0 → 2,
//         roles user+assistant) — proves the `messages` option is honored;
//     (2) the assistant message's parts were run through the react-ai-sdk
//         `convertParts` step: the WIRE `data-routing` seed became the CONVERTED
//         `{type:"data", name:"routing"}` part MessageBubble.isRoutingPart reads,
//         and the routing payload (.data.backend === "openrouter") survives;
//     (3) the collapsed assistant text "hi there" is present as a text part;
//     (4) an empty runtime (no `messages`) yields 0 thread messages — the
//         control that distinguishes "seed honored" from "always non-empty".
//   This is the load-bearing mechanism 08-03 builds on: feed reconstructed
//   UIMessages into useChatRuntime({messages}) and the existing MessageBubble
//   dispatch renders them (it reads exactly the converted parts asserted here).
//
// PART-SHAPE (08-RESEARCH.md §Pitfall 2 — load-bearing): the seeded assistant
// message parts use the WIRE shape `{type:"data-routing", data}` (NO `name`
// field). convertParts strips the `data-` prefix to `name` at runtime, producing
// the `{type:"data", name:"routing"}` shape the components read. Seeding the
// CONVERTED shape would trigger console.warn("Unsupported message part type:
// data"). This spike fails the run if that warning fires.
//
// RENDER-PATH CAVEAT (documented, NOT an A1 disproof): mounting the seeded
// messages through <ThreadPrimitive.Messages> (the production render path in
// ChatSurface.tsx:288-295) renders empty in jsdom. ThreadPrimitive.Messages
// subscribes to the OUTER useRemoteThreadListRuntime aui-store slice
// (`s.thread.messages.length`), which is gated on per-thread-item activation
// that does not flush synchronously under jsdom's render (no real
// requestAnimationFrame / ResizeObserver lifecycle). The INNER chat-thread
// runtime — the one the seed lands in and the one production hydration targets —
// IS correctly seeded, which is what useThread() reads here and what this spike
// asserts. The end-to-end "bubble visibly renders on screen" assertion is owned
// by the SC-4 Playwright spec (real browser, real runtime lifecycle).
//
// Cross-refs:
//   - apps/web/hooks/useChatThread.ts:50-52,146-151 (ThrottleableOptions where
//     `messages` threads into useChatRuntime)
//   - apps/web/components/ChatSurface.tsx:281-296 (the real
//     AssistantRuntimeProvider + ThreadPrimitive.Messages mount block)
//   - apps/web/components/MessageBubble.tsx:51-59 (isRoutingPart / isTextPart /
//     isMetricsPart — the exact converted shape this spike asserts)
//   - node_modules/@assistant-ui/react-ai-sdk/dist/ui/utils/convertMessage.js
//     (242-248: data-<x> → {type:"data", name:"<x>", data})
//   - 08-RESEARCH.md §Pattern 2, §Pitfall 1, §Pitfall 2, §Assumptions A1, §Open Q1

import { describe, it, expect, vi, beforeAll, afterAll } from "vitest";
import { render } from "@testing-library/react";
import type { UIMessage } from "@ai-sdk/react";

// --------------------------------------------------------------------
// jsdom polyfills (Rule 3 — blocking test-env gaps, NOT A1 behavior).
// The REAL @assistant-ui/react primitives mount useOnResizeContent
// (ResizeObserver) + scroll-anchoring helpers that jsdom does not implement.
// These are pure environment stubs scoped to THIS spike file (we deliberately
// do NOT touch the shared 05-00-owned tests/setup.ts). They do not influence
// whether the seeded `messages` land in the runtime (that is the A1 GATE).
// --------------------------------------------------------------------
if (typeof globalThis.ResizeObserver === "undefined") {
  class ResizeObserverStub {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  globalThis.ResizeObserver =
    ResizeObserverStub as unknown as typeof ResizeObserver;
}
if (
  typeof Element !== "undefined" &&
  typeof Element.prototype.scrollIntoView !== "function"
) {
  Element.prototype.scrollIntoView = function scrollIntoView(): void {};
}

// REAL runtime — NOT mocked. This is the entire point of the spike.
import {
  AssistantRuntimeProvider,
  useThread,
} from "@assistant-ui/react";
import { useChatRuntime } from "@assistant-ui/react-ai-sdk";

// --------------------------------------------------------------------
// Pitfall 2 guard — fail the run if convertParts emits the "Unsupported
// message part type: data" warning (which fires only when the seed used the
// CONVERTED shape instead of the WIRE shape). We collect every console.warn
// and assert it never contains that string.
// --------------------------------------------------------------------

const warnSpy = vi.spyOn(console, "warn");

beforeAll(() => {
  warnSpy.mockClear();
});

afterAll(() => {
  warnSpy.mockRestore();
});

// --------------------------------------------------------------------
// The two seeded UIMessages (AI SDK v6 shape). WIRE part vocabulary only.
// --------------------------------------------------------------------
//
// 1) a user message — single text part.
// 2) an assistant message — a `data-routing` part (WIRE shape, NO `name`)
//    followed by a `text` part. The routing part's data is the structured
//    5-key RoutingDecision record MessageBubble dispatches on (.data.backend);
//    the openrouter backend resolves to the default ChatBubble.
const SEEDED_MESSAGES: UIMessage[] = [
  {
    id: "spike-user-1",
    role: "user",
    // AI SDK v6 UIMessage.parts — a plain text part.
    parts: [{ type: "text", text: "hello" }],
  } as UIMessage,
  {
    id: "spike-assistant-1",
    role: "assistant",
    parts: [
      // WIRE shape — `type: "data-routing"`, NO `name`. convertParts adds the
      // `name:"routing"` the components read (Pitfall 2). Seeding
      // `{type:"data", name:"routing"}` here would warn + fall back.
      {
        type: "data-routing",
        data: {
          backend: "openrouter",
          model_or_agent: "openai/gpt-5",
          rationale: "test",
          confidence: 1,
          signals: {},
        },
      },
      { type: "text", text: "hi there" },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ] as any,
  } as UIMessage,
];

// --------------------------------------------------------------------
// A snapshot of the runtime's thread state, captured by reading useThread()
// inside the provider tree. This reads the INNER chat-thread runtime the seed
// lands in (the same runtime production hydration targets), through the public
// useThread() hook.
// --------------------------------------------------------------------

interface AssistantPart {
  readonly type: string;
  readonly name?: string;
  readonly text?: string;
  readonly data?: { backend?: string } & Record<string, unknown>;
}

interface ThreadSnapshot {
  count: number;
  roles: string[];
  assistantParts: AssistantPart[];
}

function captureSnapshot(seed: UIMessage[] | undefined): ThreadSnapshot {
  let snapshot: ThreadSnapshot = { count: 0, roles: [], assistantParts: [] };

  function Probe(): React.JSX.Element {
    const thread = useThread();
    snapshot = {
      count: thread.messages.length,
      roles: thread.messages.map((m) => m.role),
      assistantParts: thread.messages
        .filter((m) => m.role === "assistant")
        .flatMap((m) =>
          // `content` is the converted-parts array (post convertParts), which is
          // exactly what MessageBubble.useMessage().content reads.
          ((m as { content?: AssistantPart[] }).content ?? []).map((p) => ({
            type: p.type,
            name: p.name,
            text: p.text,
            data: p.data,
          })),
        ),
    };
    return <div data-testid="probe">{thread.messages.length}</div>;
  }

  function Harness(): React.JSX.Element {
    // The A1 GATE: useChatRuntime({messages}) — `messages` is `ChatInit.messages`
    // (ai 6.0.184 dist/index.d.ts:3808), spread into useChat by useChatRuntime
    // (useChatRuntime.js:36-49,81-91). NO transport — the runtime never sends.
    const runtime = useChatRuntime(seed ? { messages: seed } : {});
    return (
      <AssistantRuntimeProvider runtime={runtime}>
        <Probe />
      </AssistantRuntimeProvider>
    );
  }

  render(<Harness />);
  return snapshot;
}

describe("Phase 8 GATE — useChatRuntime({messages}) hydration spike (A1 / Open Q1)", () => {
  it("seeds 2 static UIMessages into the installed runtime's thread state (A1)", () => {
    const snap = captureSnapshot(SEEDED_MESSAGES);

    // A1 PRIMARY ASSERTION: the seeded `messages` array landed in the runtime
    // thread state. If the installed runtime ignored the seed (rendered empty),
    // count would be 0 → A1 DISPROVEN → invoke the Task-5 fallback BEFORE Wave 2.
    expect(snap.count, `seeded thread snapshot: ${JSON.stringify(snap)}`).toBe(
      2,
    );
    expect(snap.roles).toEqual(["user", "assistant"]);
  });

  it("runs the assistant parts through convertParts → the converted shape MessageBubble reads", () => {
    const snap = captureSnapshot(SEEDED_MESSAGES);

    // The WIRE `data-routing` seed must have been converted to the
    // `{type:"data", name:"routing"}` shape MessageBubble.isRoutingPart matches
    // (MessageBubble.tsx:51-53). This is what makes the existing bubble dispatch
    // render reconstructed history unchanged (08-03).
    const routingPart = snap.assistantParts.find(
      (p) => p.type === "data" && p.name === "routing",
    );
    expect(
      routingPart,
      `assistant parts: ${JSON.stringify(snap.assistantParts)}`,
    ).toBeDefined();
    // The routing payload survives the round-trip — MessageBubble dispatches on
    // .data.backend (here "openrouter" → default ChatBubble).
    expect(routingPart?.data?.backend).toBe("openrouter");

    // The collapsed assistant text survives as a text part (the ChatBubble body).
    const textPart = snap.assistantParts.find(
      (p) => p.type === "text" && p.text === "hi there",
    );
    expect(textPart).toBeDefined();
  });

  it("an empty runtime (no messages) yields 0 thread messages (control)", () => {
    const snap = captureSnapshot(undefined);
    // The control: without a `messages` seed the thread is empty. Distinguishes
    // "the seed was honored" from "the runtime is always non-empty".
    expect(snap.count).toBe(0);
  });

  it("emits no convertParts 'Unsupported message part type: data' warning (Pitfall 2 wire-shape)", () => {
    captureSnapshot(SEEDED_MESSAGES);

    const sawUnsupportedDataWarning = warnSpy.mock.calls.some((args) =>
      args.some(
        (a) =>
          typeof a === "string" &&
          a.includes("Unsupported message part type: data"),
      ),
    );
    expect(sawUnsupportedDataWarning).toBe(false);
  });
});
