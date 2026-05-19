// Plan 04-02 (Wave 1) — Schema contract test suite.
// VALIDATION.md row: "Schema contract" → flips ✅ when this file is green.
//
// Asserts the Zod schemas in apps/web/lib/chunk-schemas.ts:
//   - parse every fixture in apps/web/tests/fixtures/sse-events.ts
//   - reject unknown event names (closed vocabulary)
//   - reject invalid StreamError.code values (closed enum)
//   - reject the STRUCTURED routing_decision payload when fields are missing
//     or out-of-vocabulary (Pattern F — Plan 02 revision iteration 1)
//
// Cross-refs:
//   - apps/api/backends/chunks.py (Pydantic source of truth)
//   - 04-CONTEXT.md D-15 (structured 5-key routing_decision payload)
//   - 04-PATTERNS.md Pattern A + F

import { describe, it, expect } from "vitest";
import {
  BackendEnum,
  NamedSSEEventSchema,
  RoutingDecisionDataSchema,
  StreamErrorCodeSchema,
} from "@/lib/chunk-schemas";
import {
  DONE_EVENT,
  DONE_EVENT_EMPTY,
  FILE_DIFF_EVENT,
  ROUTING_DECISION_EVENT,
  ROUTING_DECISION_EVENT_MISSING_MODEL,
  SCREENSHOT_SMALL_EVENT,
  STREAM_ERROR_AUTH_FAILED_EVENT,
  STREAM_ERROR_CANCELLED_EVENT,
  STREAM_ERROR_COST_CAP_EVENT,
  TEXT_DELTA_EVENT,
  TOOL_CALL_EVENT,
  TOOL_RESULT_EVENT,
} from "@/tests/fixtures/sse-events";

// Helper: split a fixture's raw bytes into the `{event, data}` shape the
// NamedSSEEventSchema expects. The translator's full block-parser is tested
// separately in sse-translate.test.ts; this helper exists ONLY to feed fixtures
// into Zod cleanly without duplicating that logic.
function parseFixture(fixture: string): { event: string; data: unknown } {
  // Strip the trailing \n\n SSE block terminator.
  const block = fixture.replace(/\n\n$/, "");
  let event = "";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event: ")) event = line.slice(7).trim();
    else if (line.startsWith("data: ")) dataLines.push(line.slice(6));
  }
  return { event, data: JSON.parse(dataLines.join("\n")) };
}

describe("Schema contract — NamedSSEEventSchema parses every Phase-3 SSE variant", () => {
  it("parses event:routing_decision with the structured 5-key payload (Plan 04 D-15)", () => {
    const parsed = NamedSSEEventSchema.parse(parseFixture(ROUTING_DECISION_EVENT));
    expect(parsed.event).toBe("routing_decision");
    // Type narrowing: discriminated union resolves to RoutingDecisionData.
    if (parsed.event !== "routing_decision") throw new Error("narrowing");
    expect(parsed.data.backend).toBe("openrouter");
    expect(parsed.data.model_or_agent).toBe("openai/gpt-5");
    expect(parsed.data.rationale).toBe("Strong reasoning fit");
    expect(parsed.data.confidence).toBe(0.9);
    expect(parsed.data.signals).toEqual({
      task_type: "chat",
      agentic_intent: false,
      rule_fired: "default",
    });
  });

  it("parses event:text_delta {type, text}", () => {
    const parsed = NamedSSEEventSchema.parse(parseFixture(TEXT_DELTA_EVENT));
    expect(parsed.event).toBe("text_delta");
    if (parsed.event !== "text_delta") throw new Error("narrowing");
    expect(parsed.data.type).toBe("text_delta");
    expect(parsed.data.text).toBe("Hello");
  });

  it("parses event:tool_call {type, tool_call_id, tool_name, arguments}", () => {
    const parsed = NamedSSEEventSchema.parse(parseFixture(TOOL_CALL_EVENT));
    expect(parsed.event).toBe("tool_call");
    if (parsed.event !== "tool_call") throw new Error("narrowing");
    expect(parsed.data.tool_call_id).toBe("tc_abc123");
    expect(parsed.data.tool_name).toBe("read_file");
    expect(parsed.data.arguments).toEqual({ path: "src/foo.py" });
  });

  it("parses event:tool_result {type, tool_call_id, content, is_error}", () => {
    const parsed = NamedSSEEventSchema.parse(parseFixture(TOOL_RESULT_EVENT));
    expect(parsed.event).toBe("tool_result");
    if (parsed.event !== "tool_result") throw new Error("narrowing");
    expect(parsed.data.is_error).toBe(false);
    expect(parsed.data.content).toBe("file contents...");
  });

  it("parses event:file_diff {type, tool_call_id, path, diff, operation}", () => {
    const parsed = NamedSSEEventSchema.parse(parseFixture(FILE_DIFF_EVENT));
    expect(parsed.event).toBe("file_diff");
    if (parsed.event !== "file_diff") throw new Error("narrowing");
    expect(parsed.data.operation).toBe("edit");
    expect(parsed.data.path).toBe("src/foo.py");
  });

  it("parses event:screenshot with image_b64 + null image_ref + png format", () => {
    const parsed = NamedSSEEventSchema.parse(parseFixture(SCREENSHOT_SMALL_EVENT));
    expect(parsed.event).toBe("screenshot");
    if (parsed.event !== "screenshot") throw new Error("narrowing");
    expect(parsed.data.step).toBe(1);
    expect(parsed.data.image_format).toBe("png");
    expect(parsed.data.image_b64).toBeTypeOf("string");
    expect(parsed.data.image_ref).toBeNull();
  });

  it("parses event:stream_error with code=cancelled", () => {
    const parsed = NamedSSEEventSchema.parse(parseFixture(STREAM_ERROR_CANCELLED_EVENT));
    expect(parsed.event).toBe("stream_error");
    if (parsed.event !== "stream_error") throw new Error("narrowing");
    expect(parsed.data.code).toBe("cancelled");
    expect(parsed.data.retriable).toBe(false);
  });

  it("parses event:stream_error with code=auth_failed", () => {
    const parsed = NamedSSEEventSchema.parse(parseFixture(STREAM_ERROR_AUTH_FAILED_EVENT));
    expect(parsed.event).toBe("stream_error");
    if (parsed.event !== "stream_error") throw new Error("narrowing");
    expect(parsed.data.code).toBe("auth_failed");
  });

  it("parses event:stream_error with code=cost_cap_exceeded", () => {
    const parsed = NamedSSEEventSchema.parse(parseFixture(STREAM_ERROR_COST_CAP_EVENT));
    expect(parsed.event).toBe("stream_error");
    if (parsed.event !== "stream_error") throw new Error("narrowing");
    expect(parsed.data.code).toBe("cost_cap_exceeded");
  });

  it("parses event:done with all metrics + routing_signals", () => {
    const parsed = NamedSSEEventSchema.parse(parseFixture(DONE_EVENT));
    expect(parsed.event).toBe("done");
    if (parsed.event !== "done") throw new Error("narrowing");
    expect(parsed.data.tokens_in).toBe(42);
    expect(parsed.data.tokens_out).toBe(17);
    expect(parsed.data.cost_usd).toBe(0.0021);
    expect(parsed.data.latency_ms).toBe(1400);
    expect(parsed.data.routing_signals).toEqual({
      task_type: "chat",
      agentic_intent: false,
      rule_fired: "default",
    });
  });

  it("parses event:done with all fields absent (Python int | None = None semantics)", () => {
    const parsed = NamedSSEEventSchema.parse(parseFixture(DONE_EVENT_EMPTY));
    expect(parsed.event).toBe("done");
    if (parsed.event !== "done") throw new Error("narrowing");
    expect(parsed.data.tokens_in).toBeUndefined();
    expect(parsed.data.cost_usd).toBeUndefined();
  });
});

describe("Schema contract — closed-vocabulary rejections (Pattern F)", () => {
  it("rejects unknown event names", () => {
    expect(() =>
      NamedSSEEventSchema.parse({ event: "garbage", data: {} }),
    ).toThrow();
  });

  it("rejects invalid StreamError.code (outside the 9-value enum)", () => {
    expect(() => StreamErrorCodeSchema.parse("not_a_real_code")).toThrow();
    expect(() =>
      NamedSSEEventSchema.parse({
        event: "stream_error",
        data: {
          type: "stream_error",
          code: "not_a_real_code",
          message: "oops",
          retriable: false,
        },
      }),
    ).toThrow();
  });

  it("accepts all 9 StreamError.code values from chunks.py lines 127-137", () => {
    const codes = [
      "cost_cap_exceeded",
      "step_cap_exceeded",
      "cancelled",
      "rate_limited",
      "auth_failed",
      "provider_unavailable",
      "timeout",
      "validation_error",
      "internal_error",
    ];
    for (const code of codes) {
      expect(() => StreamErrorCodeSchema.parse(code)).not.toThrow();
    }
  });

  it("rejects routing_decision missing model_or_agent (drift fixture)", () => {
    expect(() =>
      NamedSSEEventSchema.parse(parseFixture(ROUTING_DECISION_EVENT_MISSING_MODEL)),
    ).toThrow();
  });

  it("rejects routing_decision with backend outside the 3-value enum", () => {
    expect(() =>
      NamedSSEEventSchema.parse({
        event: "routing_decision",
        data: {
          backend: "foo",
          model_or_agent: "x",
          rationale: "y",
          confidence: 0.5,
          signals: {},
        },
      }),
    ).toThrow();
    // BackendEnum directly:
    expect(() => BackendEnum.parse("foo")).toThrow();
    // The three valid values:
    expect(() => BackendEnum.parse("openrouter")).not.toThrow();
    expect(() => BackendEnum.parse("claude_code")).not.toThrow();
    expect(() => BackendEnum.parse("computer_use")).not.toThrow();
  });

  it("rejects routing_decision with non-string rationale", () => {
    expect(() =>
      RoutingDecisionDataSchema.parse({
        backend: "openrouter",
        model_or_agent: "x",
        rationale: 42, // bad type
        confidence: 0.5,
        signals: {},
      }),
    ).toThrow();
  });

  it("rejects text_delta with wrong inner type literal", () => {
    expect(() =>
      NamedSSEEventSchema.parse({
        event: "text_delta",
        data: { type: "tool_call", text: "hi" }, // type literal must match
      }),
    ).toThrow();
  });
});
