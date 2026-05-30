// Phase 8 Plan 08-00 Wave 0 — SC-3 RED reconstruction unit.
//
// 08-VALIDATION.md SC-3 sampling: feed `MessageRow[]` rows — one per backend
// (`openrouter`/`claude_code`/`computer_use`) PLUS one override row — into
// `reconstructUIMessages(rows)` and assert the produced AI-SDK-v6 `UIMessage.parts`:
//   - `data-routing` FIRST, with the correct `backend` and `signals.override`,
//   - each stored `content_blocks` entry mapped 1:1 to `data-<chunk.type>`
//     (`data-tool_call` / `data-file_diff` / `data-screenshot`),
//   - a single `text` part for the collapsed body,
//   - `data-metrics` LAST.
//
// RED-by-design: `@/lib/reconstruct-messages` does NOT exist yet. The import
// fails to resolve, so every `it` is collected and reported FAILED until 08-02
// ships the module. This is a missing-IMPLEMENTATION failure (unresolved import),
// NOT a malformed-test error.
//
// PART-SHAPE (08-RESEARCH.md §Pitfall 2 — load-bearing): the reconstruction must
// emit the WIRE shape `{type:"data-routing", data}` (NO `name` field). The
// react-ai-sdk `convertParts` strips the `data-` prefix to `name` at render
// time, producing the `{type:"data", name:"routing"}` shape the bubble
// components read. Emitting the converted shape would trigger
// console.warn("Unsupported message part type: data") and break dispatch. So
// this test asserts `type === "data-routing"` and that NO part carries a `name`
// field (the converted shape must never be hand-produced here).
//
// WHY `data-${block.type}` regenerates the live names exactly (08-PATTERNS):
// stored `content_blocks` entries are `chunk.model_dump()` dicts with a `type`
// discriminator (`tool_call`/`tool_result`/`file_diff`/`screenshot` —
// persist_turn at queries.py:522). So `data-${block.type}` reproduces the live
// SSE `data-*` part names byte-for-byte (sse-translate.ts:221-227).
//
// The block payloads reuse the canonical stored-chunk shapes from
// tests/fixtures/sse-events.ts (the same `chunk.model_dump()` dicts the
// CLAUDE_CODE_CONTENT_PARTS / COMPUTER_USE_CONTENT_PARTS arrays carry under
// `.data`).
//
// Cross-refs:
//   - 08-PLAN-00 Task 2 (b) + 08-VALIDATION.md SC-3 sampling
//   - 08-PATTERNS.md §"apps/web/lib/reconstruct-messages.ts" (the vocabulary table)
//   - 08-RESEARCH.md §"Pattern 1" (reconstruction shape), §Pitfall 2 (wire shape)
//   - apps/web/lib/sse-translate.ts:135-242 (the event→part vocabulary mirrored)
//   - apps/web/tests/fixtures/sse-events.ts (the stored block payloads)

import { describe, it, expect } from "vitest";
import { reconstructUIMessages } from "@/lib/reconstruct-messages";

// --------------------------------------------------------------------
// MessageRow — the shape of one row from GET /api/threads/{id}/messages
// (08-RESEARCH §Pattern 1). `content_blocks` is the PARSED array (the endpoint
// json.loads()es the DB column); `routing` is the LEFT JOIN sub-object
// (null on user rows / assistant rows with no routing decision).
// --------------------------------------------------------------------

interface MessageRow {
  id: string;
  role: "user" | "assistant";
  text: string;
  content_blocks: Array<{ type: string } & Record<string, unknown>>;
  backend_used: string | null;
  model_used: string | null;
  cost_usd: number | null;
  latency_ms: number | null;
  tokens_in: number | null;
  tokens_out: number | null;
  status: "complete" | "error" | "cancelled";
  routing: { rationale: string; override: boolean } | null;
}

// Stored content_blocks payloads — the `chunk.model_dump()` dicts persist_turn
// writes. These match the `.data` payloads in tests/fixtures/sse-events.ts
// (CLAUDE_CODE_CONTENT_PARTS tool_call/file_diff + COMPUTER_USE screenshot).
const TOOL_CALL_BLOCK = {
  type: "tool_call",
  tool_call_id: "tc_cc_001",
  tool_name: "edit_file",
  arguments: { path: "src/app.py", instruction: "add a budget total" },
};
const FILE_DIFF_BLOCK = {
  type: "file_diff",
  tool_call_id: "tc_cc_001",
  path: "src/app.py",
  diff: "@@ -1,2 +1,3 @@\n context\n-old\n+new",
  operation: "edit",
};
const SCREENSHOT_BLOCK = {
  type: "screenshot",
  step: 2,
  image_b64: null,
  image_ref: "a1b2c3d4e5f60718293a4b5c6d7e8f90.png",
  image_format: "png",
};

function row(partial: Partial<MessageRow>): MessageRow {
  return {
    id: "m-x",
    role: "assistant",
    text: "body text",
    content_blocks: [],
    backend_used: "openrouter",
    model_used: "openai/gpt-5",
    cost_usd: 0.0021,
    latency_ms: 1400,
    tokens_in: 42,
    tokens_out: 17,
    status: "complete",
    routing: { rationale: "Strong reasoning fit", override: false },
    ...partial,
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function partsOf(msg: any): any[] {
  return (msg.parts ?? []) as any[];
}

describe("reconstructUIMessages — SC-3 reconstruction contract", () => {
  it("emits data-routing FIRST with the correct backend + signals.override", () => {
    const [msg] = reconstructUIMessages([
      row({
        role: "assistant",
        backend_used: "claude_code",
        model_used: "claude-code",
        routing: { rationale: "Build-and-edit coding task", override: true },
        content_blocks: [TOOL_CALL_BLOCK, FILE_DIFF_BLOCK],
        text: "I added a budget total.",
      }),
    ]);

    const parts = partsOf(msg);
    // FIRST part is the routing part (MessageBubble dispatches on it).
    expect(parts[0].type).toBe("data-routing");
    expect(parts[0].data.backend).toBe("claude_code");
    // override row → signals.override true (the D-08 distinct override pill).
    expect(parts[0].data.signals.override).toBe(true);
  });

  it("maps each content_blocks entry 1:1 to data-<chunk.type> (claude_code)", () => {
    const [msg] = reconstructUIMessages([
      row({
        role: "assistant",
        backend_used: "claude_code",
        content_blocks: [TOOL_CALL_BLOCK, FILE_DIFF_BLOCK],
        text: "done",
      }),
    ]);

    const types = partsOf(msg).map((p) => p.type);
    expect(types).toContain("data-tool_call");
    expect(types).toContain("data-file_diff");
  });

  it("maps a computer_use screenshot block to data-screenshot", () => {
    const [msg] = reconstructUIMessages([
      row({
        role: "assistant",
        backend_used: "computer_use",
        model_used: "computer-use",
        routing: { rationale: "Browse-and-act task", override: false },
        content_blocks: [SCREENSHOT_BLOCK],
        text: "The price is $42.00.",
      }),
    ]);

    const types = partsOf(msg).map((p) => p.type);
    expect(types).toContain("data-screenshot");
  });

  it("emits a single collapsed text part for the body", () => {
    const [msg] = reconstructUIMessages([
      row({
        role: "assistant",
        backend_used: "openrouter",
        content_blocks: [],
        text: "hi there",
      }),
    ]);

    const textParts = partsOf(msg).filter((p) => p.type === "text");
    expect(textParts).toHaveLength(1);
    expect(textParts[0].text).toBe("hi there");
  });

  it("emits data-metrics LAST", () => {
    const [msg] = reconstructUIMessages([
      row({
        role: "assistant",
        backend_used: "openrouter",
        content_blocks: [TOOL_CALL_BLOCK],
        text: "body",
        cost_usd: 0.0021,
        latency_ms: 1400,
        tokens_in: 42,
        tokens_out: 17,
      }),
    ]);

    const parts = partsOf(msg);
    const last = parts[parts.length - 1];
    expect(last.type).toBe("data-metrics");
    expect(last.data.cost_usd).toBe(0.0021);
    expect(last.data.latency_ms).toBe(1400);
  });

  it("preserves part ORDER: routing first, blocks, text, metrics last", () => {
    const [msg] = reconstructUIMessages([
      row({
        role: "assistant",
        backend_used: "claude_code",
        content_blocks: [TOOL_CALL_BLOCK, FILE_DIFF_BLOCK],
        text: "narration",
      }),
    ]);

    const types = partsOf(msg).map((p) => p.type);
    // routing is index 0; metrics is the final element; the text part sits
    // after the data-* blocks and before metrics.
    expect(types[0]).toBe("data-routing");
    expect(types[types.length - 1]).toBe("data-metrics");
    const textIdx = types.indexOf("text");
    const diffIdx = types.indexOf("data-file_diff");
    const metricsIdx = types.indexOf("data-metrics");
    expect(diffIdx).toBeGreaterThan(0);
    expect(textIdx).toBeGreaterThan(diffIdx);
    expect(metricsIdx).toBeGreaterThan(textIdx);
  });

  it("renders a user row as a single text part with no routing/metrics", () => {
    const [msg] = reconstructUIMessages([
      row({ role: "user", text: "build me a finance app", content_blocks: [] }),
    ]);

    const parts = partsOf(msg);
    expect(parts).toHaveLength(1);
    expect(parts[0].type).toBe("text");
    expect(parts[0].text).toBe("build me a finance app");
  });

  it("reconstructs all three backends + override in one call (full sampling)", () => {
    const msgs = reconstructUIMessages([
      row({ role: "user", text: "q1", content_blocks: [] }),
      row({
        role: "assistant",
        backend_used: "openrouter",
        routing: { rationale: "reasoning", override: false },
        content_blocks: [],
        text: "a1",
      }),
      row({
        role: "assistant",
        backend_used: "claude_code",
        routing: { rationale: "coding", override: false },
        content_blocks: [TOOL_CALL_BLOCK, FILE_DIFF_BLOCK],
        text: "a2",
      }),
      row({
        role: "assistant",
        backend_used: "computer_use",
        routing: { rationale: "browse", override: false },
        content_blocks: [SCREENSHOT_BLOCK],
        text: "a3",
      }),
      row({
        role: "assistant",
        backend_used: "openrouter",
        routing: { rationale: "user override", override: true },
        content_blocks: [],
        text: "a4",
      }),
    ]);

    expect(msgs).toHaveLength(5);
    // Every assistant message carries a routing part with the right backend.
    const assistantBackends = msgs
      .slice(1)
      .map((m) => partsOf(m).find((p) => p.type === "data-routing")?.data.backend);
    expect(assistantBackends).toEqual([
      "openrouter",
      "claude_code",
      "computer_use",
      "openrouter",
    ]);
    // The override row's routing part flags signals.override.
    const overrideMsg = msgs[4];
    const overrideRouting = partsOf(overrideMsg).find(
      (p) => p.type === "data-routing",
    );
    expect(overrideRouting.data.signals.override).toBe(true);
  });

  it("WIRE shape only — no part carries a `name` field (Pitfall 2)", () => {
    const [msg] = reconstructUIMessages([
      row({
        role: "assistant",
        backend_used: "claude_code",
        content_blocks: [TOOL_CALL_BLOCK, FILE_DIFF_BLOCK],
        text: "x",
      }),
    ]);

    // The converted `{type:"data", name:"..."}` shape must NEVER be hand-produced
    // by the reconstruction; convertParts adds `name` at render time. Assert no
    // emitted part has a `name` key and none uses the bare `type:"data"`.
    for (const part of partsOf(msg)) {
      expect(part).not.toHaveProperty("name");
      expect(part.type).not.toBe("data");
    }
  });
});
