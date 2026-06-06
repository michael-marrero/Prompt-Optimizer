// Plan 04-02 (Wave 1) — D-07 contract test suite for the pure-function
// SSE translator. VALIDATION.md row: "D-07 contract" → flips ✅ green
// when this file passes.
//
// Each test feeds fixture event strings (from tests/fixtures/sse-events.ts)
// into a fake ReadableStream<Uint8Array>, runs the translator, and asserts
// the consumed output is the right sequence of AI SDK v6 UI Message Stream
// chunks per the mapping table in 04-RESEARCH.md §"Pattern 2" lines 498-506.
//
// Critical assertions:
//   - routing_decision → start + data-routing chunk whose `data` field is
//     the STRUCTURED 5-key payload verbatim (Plan 04 D-15)
//   - text_delta sequencing → 1 text-start + N text-deltas (all reusing
//     id:"t-0")
//   - done → text-end + data-metrics + finish + literal "data: [DONE]\n\n"
//   - stream_error(cancelled) → text-end + abort
//   - stream_error(other) → text-end + error
//   - malformed JSON → error chunk + CONTINUE (Pattern F)
//   - unknown event name → error chunk + CONTINUE (Pattern F)
//   - routing_decision missing model_or_agent → error chunk + CONTINUE
//   - multi-read buffer accumulation (one SSE block split across two
//     Uint8Array chunks)

import { describe, it, expect } from "vitest";
import { translateNamedSSEToUIMessageStream } from "@/lib/sse-translate";
import {
  AWAITING_APPROVAL_EVENT,
  DONE_EVENT,
  DONE_EVENT_EMPTY,
  FILE_DIFF_EVENT,
  HEARTBEAT,
  MALFORMED_EVENT,
  ROUTING_DECISION_EVENT,
  ROUTING_DECISION_EVENT_MISSING_MODEL,
  SCREENSHOT_SMALL_EVENT,
  STREAM_ERROR_CANCELLED_EVENT,
  STREAM_ERROR_COST_CAP_EVENT,
  TEXT_DELTA_EVENT,
  TEXT_DELTA_EVENT_2,
  TEXT_DELTA_EVENT_3,
  TOOL_CALL_EVENT,
  TOOL_RESULT_EVENT,
  TURN_START_EVENT,
  UNKNOWN_EVENT,
} from "@/tests/fixtures/sse-events";

// --------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------

/** Build a ReadableStream<Uint8Array> from a list of fixture chunks.
 * Each entry is enqueued as one read() return value, simulating how
 * a real upstream might split blocks across network reads. */
function fixtureStream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}

/** Consume a ReadableStream to a single decoded string. */
async function consumeToText(
  stream: ReadableStream<Uint8Array>,
): Promise<string> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let out = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    out += decoder.decode(value, { stream: true });
  }
  out += decoder.decode(); // flush
  return out;
}

/** Parse the translator's output (which is itself an SSE-formatted byte
 * stream of `data: <json>\n\n` lines + the literal `data: [DONE]\n\n`
 * sentinel) into the list of emitted JSON chunks. */
function parseEmittedChunks(text: string): unknown[] {
  const chunks: unknown[] = [];
  for (const block of text.split("\n\n")) {
    const stripped = block.trim();
    if (!stripped) continue;
    // Each emitted block is `data: <payload>`; payload may be "[DONE]" or JSON.
    const payload = stripped.startsWith("data: ")
      ? stripped.slice(6)
      : stripped;
    if (payload === "[DONE]") {
      chunks.push({ __sentinel: "DONE" });
      continue;
    }
    try {
      chunks.push(JSON.parse(payload));
    } catch {
      // Surface as a parse-failure marker for the test to assert on.
      chunks.push({ __parseFailure: payload });
    }
  }
  return chunks;
}

// Typed selectors for narrowing test assertions.
function typeOf(c: unknown): string {
  return (c as { type?: string }).type ?? "";
}
function dataOf<T = unknown>(c: unknown): T {
  return (c as { data: T }).data;
}

// --------------------------------------------------------------------
// Tests
// --------------------------------------------------------------------

describe("D-07 contract — translateNamedSSEToUIMessageStream", () => {
  it("empty input stream emits NOTHING and closes cleanly", async () => {
    const out = await consumeToText(
      translateNamedSSEToUIMessageStream(fixtureStream([])),
    );
    expect(out).toBe("");
  });

  it("emits {type:start} + {type:data-routing} on routing_decision, with the STRUCTURED 5-key payload verbatim", async () => {
    const out = await consumeToText(
      translateNamedSSEToUIMessageStream(fixtureStream([ROUTING_DECISION_EVENT])),
    );
    const chunks = parseEmittedChunks(out);
    // Sequence: start, data-routing.
    expect(chunks.length).toBe(2);
    expect(typeOf(chunks[0])).toBe("start");
    expect(chunks[0]).toHaveProperty("messageId");
    expect(typeOf(chunks[1])).toBe("data-routing");
    // CRITICAL: the data field carries the structured 5-key payload verbatim.
    const routing = dataOf<{
      backend: string;
      model_or_agent: string;
      rationale: string;
      confidence: number;
      signals: Record<string, unknown>;
    }>(chunks[1]);
    expect(routing.backend).toBe("openrouter");
    expect(routing.model_or_agent).toBe("openai/gpt-5");
    expect(routing.rationale).toBe("Strong reasoning fit");
    expect(routing.confidence).toBe(0.9);
    expect(routing.signals).toEqual({
      task_type: "chat",
      agentic_intent: false,
      rule_fired: "default",
    });
  });

  it("routing_decision + first text_delta → start + data-routing + text-start (id:t-0) + text-delta", async () => {
    const out = await consumeToText(
      translateNamedSSEToUIMessageStream(
        fixtureStream([ROUTING_DECISION_EVENT, TEXT_DELTA_EVENT]),
      ),
    );
    const chunks = parseEmittedChunks(out);
    expect(chunks.length).toBe(4);
    expect(typeOf(chunks[0])).toBe("start");
    expect(typeOf(chunks[1])).toBe("data-routing");
    expect(typeOf(chunks[2])).toBe("text-start");
    expect((chunks[2] as { id: string }).id).toBe("t-0");
    expect(typeOf(chunks[3])).toBe("text-delta");
    expect((chunks[3] as { id: string; delta: string }).id).toBe("t-0");
    expect((chunks[3] as { delta: string }).delta).toBe("Hello");
  });

  it("3 text_deltas in sequence → 1 text-start + 3 text-deltas (all reusing id:t-0)", async () => {
    const out = await consumeToText(
      translateNamedSSEToUIMessageStream(
        fixtureStream([
          TEXT_DELTA_EVENT,
          TEXT_DELTA_EVENT_2,
          TEXT_DELTA_EVENT_3,
        ]),
      ),
    );
    const chunks = parseEmittedChunks(out);
    // start, text-start, 3x text-delta.
    expect(chunks.length).toBe(5);
    expect(typeOf(chunks[0])).toBe("start");
    expect(typeOf(chunks[1])).toBe("text-start");
    expect(typeOf(chunks[2])).toBe("text-delta");
    expect(typeOf(chunks[3])).toBe("text-delta");
    expect(typeOf(chunks[4])).toBe("text-delta");
    // All text-deltas reuse the same id.
    expect((chunks[1] as { id: string }).id).toBe("t-0");
    for (let i = 2; i <= 4; i++) {
      expect((chunks[i] as { id: string }).id).toBe("t-0");
    }
    // Deltas concatenate to the full string.
    const full =
      (chunks[2] as { delta: string }).delta +
      (chunks[3] as { delta: string }).delta +
      (chunks[4] as { delta: string }).delta;
    expect(full).toBe("Hello world!");
  });

  it("done event → text-end + data-metrics + finish + literal data: [DONE] sentinel", async () => {
    const out = await consumeToText(
      translateNamedSSEToUIMessageStream(
        fixtureStream([TEXT_DELTA_EVENT, DONE_EVENT]),
      ),
    );
    const chunks = parseEmittedChunks(out);
    // start, text-start, text-delta, text-end, data-metrics, finish, [DONE].
    expect(chunks.length).toBe(7);
    expect(typeOf(chunks[3])).toBe("text-end");
    expect(typeOf(chunks[4])).toBe("data-metrics");
    expect(typeOf(chunks[5])).toBe("finish");
    expect(chunks[6]).toEqual({ __sentinel: "DONE" });

    // Metrics carry the flattened payload.
    const metrics = dataOf<{
      cost_usd: number | null;
      latency_ms: number | null;
      tokens_in: number | null;
      tokens_out: number | null;
    }>(chunks[4]);
    expect(metrics.cost_usd).toBe(0.0021);
    expect(metrics.latency_ms).toBe(1400);
    expect(metrics.tokens_in).toBe(42);
    expect(metrics.tokens_out).toBe(17);
    // Literal [DONE] sentinel string is in the raw output bytes.
    expect(out).toContain("data: [DONE]\n\n");
  });

  it("done with all metrics absent → nullable metrics payload", async () => {
    const out = await consumeToText(
      translateNamedSSEToUIMessageStream(fixtureStream([DONE_EVENT_EMPTY])),
    );
    const chunks = parseEmittedChunks(out);
    // No text part was opened, so no text-end is emitted. The translator
    // still emits a `start` first, then data-metrics, finish, [DONE].
    const metricsIdx = chunks.findIndex((c) => typeOf(c) === "data-metrics");
    expect(metricsIdx).toBeGreaterThanOrEqual(0);
    const metrics = dataOf<{
      cost_usd: number | null;
      latency_ms: number | null;
    }>(chunks[metricsIdx]);
    expect(metrics.cost_usd).toBeNull();
    expect(metrics.latency_ms).toBeNull();
  });

  it("stream_error with code=cancelled → text-end + abort chunk", async () => {
    const out = await consumeToText(
      translateNamedSSEToUIMessageStream(
        fixtureStream([TEXT_DELTA_EVENT, STREAM_ERROR_CANCELLED_EVENT]),
      ),
    );
    const chunks = parseEmittedChunks(out);
    // start, text-start, text-delta, text-end, abort.
    expect(chunks.length).toBe(5);
    expect(typeOf(chunks[3])).toBe("text-end");
    expect(typeOf(chunks[4])).toBe("abort");
    expect((chunks[4] as { reason: string }).reason).toBe("cancelled");
  });

  it("stream_error with code=cost_cap_exceeded → text-end + error chunk with code+retriable", async () => {
    const out = await consumeToText(
      translateNamedSSEToUIMessageStream(
        fixtureStream([TEXT_DELTA_EVENT, STREAM_ERROR_COST_CAP_EVENT]),
      ),
    );
    const chunks = parseEmittedChunks(out);
    expect(chunks.length).toBe(5);
    expect(typeOf(chunks[3])).toBe("text-end");
    expect(typeOf(chunks[4])).toBe("error");
    const err = chunks[4] as {
      errorText: string;
      code: string;
      retriable: boolean;
    };
    expect(err.errorText).toBe("Cost cap of $0.10 exceeded");
    expect(err.code).toBe("cost_cap_exceeded");
    expect(err.retriable).toBe(false);
  });

  it("tool_call / tool_result / file_diff / screenshot forwarded as data-<event> for Phase 5 forward-compat", async () => {
    const out = await consumeToText(
      translateNamedSSEToUIMessageStream(
        fixtureStream([
          TOOL_CALL_EVENT,
          TOOL_RESULT_EVENT,
          FILE_DIFF_EVENT,
          SCREENSHOT_SMALL_EVENT,
        ]),
      ),
    );
    const chunks = parseEmittedChunks(out);
    // start + 4 data-<event>.
    expect(chunks.length).toBe(5);
    expect(typeOf(chunks[0])).toBe("start");
    expect(typeOf(chunks[1])).toBe("data-tool_call");
    expect(typeOf(chunks[2])).toBe("data-tool_result");
    expect(typeOf(chunks[3])).toBe("data-file_diff");
    expect(typeOf(chunks[4])).toBe("data-screenshot");
  });

  it("malformed event (data is not JSON) → emits one error chunk and CONTINUES the stream", async () => {
    const out = await consumeToText(
      translateNamedSSEToUIMessageStream(
        fixtureStream([MALFORMED_EVENT, DONE_EVENT]),
      ),
    );
    const chunks = parseEmittedChunks(out);
    // The translator must emit an error chunk for the bad event AND still
    // produce data-metrics + finish + [DONE] from the trailing valid done.
    const errors = chunks.filter((c) => typeOf(c) === "error");
    expect(errors.length).toBe(1);
    expect((errors[0] as { errorText: string }).errorText).toContain(
      "Malformed upstream event: text_delta",
    );
    expect(chunks.some((c) => typeOf(c) === "data-metrics")).toBe(true);
    expect(chunks.some((c) => typeOf(c) === "finish")).toBe(true);
  });

  it("turn_start at stream head → start + data-turn_start(turn_id), no error, routing+metrics still land (GAP-1)", async () => {
    const out = await consumeToText(
      translateNamedSSEToUIMessageStream(
        fixtureStream([TURN_START_EVENT, ROUTING_DECISION_EVENT, DONE_EVENT]),
      ),
    );
    const chunks = parseEmittedChunks(out);
    // No error chunk references turn_start — the parse fix removed the
    // "Malformed upstream event: turn_start" collapse (GAP-1 closed).
    const turnStartErrors = chunks.filter(
      (c) =>
        typeOf(c) === "error" &&
        ((c as { errorText?: string }).errorText ?? "").includes("turn_start"),
    );
    expect(turnStartErrors.length).toBe(0);
    // The stream still starts and the turn_id is surfaced as a data part.
    expect(chunks.some((c) => typeOf(c) === "start")).toBe(true);
    const turnStartChunk = chunks.find((c) => typeOf(c) === "data-turn_start");
    expect(turnStartChunk).toBeDefined();
    expect(dataOf<{ turn_id: string }>(turnStartChunk).turn_id).toBe(
      "turn-abc123",
    );
    // Downstream routing + metrics are unaffected (stream not broken).
    expect(chunks.some((c) => typeOf(c) === "data-routing")).toBe(true);
    expect(chunks.some((c) => typeOf(c) === "data-metrics")).toBe(true);
  });

  it("mid-turn awaiting_approval → data-awaiting_approval, no error, stream continues to done (GAP-1)", async () => {
    const out = await consumeToText(
      translateNamedSSEToUIMessageStream(
        fixtureStream([
          ROUTING_DECISION_EVENT,
          AWAITING_APPROVAL_EVENT,
          DONE_EVENT,
        ]),
      ),
    );
    const chunks = parseEmittedChunks(out);
    // No error chunk references awaiting_approval.
    const approvalErrors = chunks.filter(
      (c) =>
        typeOf(c) === "error" &&
        ((c as { errorText?: string }).errorText ?? "").includes(
          "awaiting_approval",
        ),
    );
    expect(approvalErrors.length).toBe(0);
    // The event is consumed as a data part (no-op consumer).
    expect(chunks.some((c) => typeOf(c) === "data-awaiting_approval")).toBe(
      true,
    );
    // Stream continues to done.
    expect(chunks.some((c) => typeOf(c) === "data-metrics")).toBe(true);
  });

  it("unknown event name (outside the 10-variant union) → error chunk + CONTINUES", async () => {
    const out = await consumeToText(
      translateNamedSSEToUIMessageStream(
        fixtureStream([UNKNOWN_EVENT, DONE_EVENT]),
      ),
    );
    const chunks = parseEmittedChunks(out);
    const errors = chunks.filter((c) => typeOf(c) === "error");
    expect(errors.length).toBe(1);
    expect((errors[0] as { errorText: string }).errorText).toContain(
      "Malformed upstream event: unknown_garbage_event",
    );
    expect(chunks.some((c) => typeOf(c) === "data-metrics")).toBe(true);
  });

  it("routing_decision missing model_or_agent (Pattern F drift) → error chunk + CONTINUES", async () => {
    const out = await consumeToText(
      translateNamedSSEToUIMessageStream(
        fixtureStream([ROUTING_DECISION_EVENT_MISSING_MODEL, DONE_EVENT]),
      ),
    );
    const chunks = parseEmittedChunks(out);
    const errors = chunks.filter((c) => typeOf(c) === "error");
    expect(errors.length).toBe(1);
    expect((errors[0] as { errorText: string }).errorText).toContain(
      "Malformed upstream event: routing_decision",
    );
    // Stream continues — done lands.
    expect(chunks.some((c) => typeOf(c) === "data-metrics")).toBe(true);
    expect(chunks.some((c) => typeOf(c) === "finish")).toBe(true);
  });

  it("SSE heartbeats (lines starting with :) are skipped silently", async () => {
    const out = await consumeToText(
      translateNamedSSEToUIMessageStream(
        fixtureStream([HEARTBEAT, TEXT_DELTA_EVENT, HEARTBEAT, DONE_EVENT]),
      ),
    );
    const chunks = parseEmittedChunks(out);
    // No chunk should be emitted for the heartbeats themselves.
    // Sequence: start, text-start, text-delta, text-end, data-metrics, finish, [DONE].
    expect(chunks.length).toBe(7);
    expect(typeOf(chunks[0])).toBe("start");
    expect(typeOf(chunks[2])).toBe("text-delta");
  });

  it("buffer accumulation — a single SSE block split across two Uint8Array reads is parsed correctly", async () => {
    // Split one text_delta block at an arbitrary boundary mid-`data:` line.
    const split = [
      "event: text_delta\nda",
      'ta: {"type":"text_delta","text":"hi"}\n\n',
    ];
    const out = await consumeToText(
      translateNamedSSEToUIMessageStream(fixtureStream(split)),
    );
    const chunks = parseEmittedChunks(out);
    const deltas = chunks.filter((c) => typeOf(c) === "text-delta");
    expect(deltas.length).toBe(1);
    expect((deltas[0] as { delta: string }).delta).toBe("hi");
  });

  it("CRLF line endings (sse-starlette wire format) are parsed correctly — Plan 03 regression", async () => {
    // sse-starlette (Phase 3) emits CRLF (`\r\n`) line endings; the
    // earlier Wave 1 fixtures all used LF (`\n`) so this case never
    // exercised. The translator normalises CRLF → LF in its buffer
    // accumulator. Without that normalisation indexOf("\n\n") never
    // matches against a CRLF stream and zero chunks emit.
    const crlf = [
      "event: text_delta\r\n" +
        'data: {"type":"text_delta","text":"crlf"}\r\n\r\n',
    ];
    const out = await consumeToText(
      translateNamedSSEToUIMessageStream(fixtureStream(crlf)),
    );
    const chunks = parseEmittedChunks(out);
    const deltas = chunks.filter((c) => typeOf(c) === "text-delta");
    expect(deltas.length).toBe(1);
    expect((deltas[0] as { delta: string }).delta).toBe("crlf");
  });
});
