// Zod schemas mirroring the Pydantic discriminated union in
// `apps/api/backends/chunks.py` byte-for-byte, plus the Plan 04 D-15
// `routing_decision` event added by `apps/api/routes/turn.py`.
//
// The `NamedSSEEventSchema` is the parse boundary for `sse-translate.ts` —
// every upstream block from FastAPI is validated here before being translated
// into AI SDK v6 UI Message Stream chunks (Plan 04-PATTERNS Pattern A + F).
//
// Cross-refs:
//   - apps/api/backends/chunks.py (Pydantic source of truth — 7 chunk variants
//     + the 9-value StreamError.code enum on lines 127-137)
//   - src/routing/schema.py (RoutingDecision shape mirrored by
//     RoutingDecisionDataSchema)
//   - 04-CONTEXT.md D-15 (structured 5-key routing_decision payload)
//   - 04-RESEARCH.md §"Pattern 2" lines 510-524 (the canonical NamedSSEEventSchema
//     skeleton; we extend it with the structured routing_decision shape per
//     Plan 02 revision iteration 1)

import { z } from "zod";

// --------------------------------------------------------------------
// Backend + RoutingDecision (the structured routing_decision payload)
// --------------------------------------------------------------------

// Mirrors `Backend = Literal["openrouter", "claude_code", "computer_use"]`
// in src/routing/schema.py. The 3-value enum is load-bearing: an upstream
// drift (e.g. "openrotuer") fails Zod parse and the translator emits an
// error chunk (Pattern F) instead of forwarding a half-rendered chip.
export const BackendEnum = z.enum(["openrouter", "claude_code", "computer_use"]);
export type BackendT = z.infer<typeof BackendEnum>;

// The STRUCTURED 5-key payload added by Plan 04 D-15 amendment to
// apps/api/routes/turn.py. Earlier wording said "data IS the signals dict";
// Plan 02 revision iteration 1 reconciled this to the full RoutingDecision
// record so the chip can read backend/model_or_agent/rationale/confidence
// directly without defensive optional-chaining.
//
// `signals` remains a free-form Record<string, unknown> because Phase 1 D-03
// allows arbitrary per-stage telemetry under that key.
export const RoutingDecisionDataSchema = z.object({
  backend: BackendEnum,
  model_or_agent: z.string(),
  rationale: z.string(),
  confidence: z.number(),
  signals: z.record(z.string(), z.unknown()),
});
export type RoutingDecisionDataT = z.infer<typeof RoutingDecisionDataSchema>;

// --------------------------------------------------------------------
// Per-variant chunk schemas (mirror apps/api/backends/chunks.py)
// --------------------------------------------------------------------

// TextDelta — `apps/api/backends/chunks.py:49-53`.
export const TextDeltaSchema = z.object({
  type: z.literal("text_delta"),
  text: z.string(),
});

// ToolCall — `apps/api/backends/chunks.py:56-68`. `arguments` is the parsed
// JSON object from the provider's streaming function-call accumulator.
export const ToolCallSchema = z.object({
  type: z.literal("tool_call"),
  tool_call_id: z.string(),
  tool_name: z.string(),
  arguments: z.record(z.string(), z.unknown()),
});

// ToolResult — `apps/api/backends/chunks.py:71-83`. `content` is either
// the text body or a structured dict (image-returning tools).
export const ToolResultSchema = z.object({
  type: z.literal("tool_result"),
  tool_call_id: z.string(),
  content: z.union([z.string(), z.record(z.string(), z.unknown())]),
  is_error: z.boolean(),
});

// FileDiff — `apps/api/backends/chunks.py:86-98`. `operation` is closed.
export const FileDiffSchema = z.object({
  type: z.literal("file_diff"),
  tool_call_id: z.string(),
  path: z.string(),
  diff: z.string(),
  operation: z.enum(["create", "edit", "delete"]),
});

// Screenshot — `apps/api/backends/chunks.py:101-114`. Both image_b64 and
// image_ref are nullable+optional to mirror `str | None = None` in Python.
export const ScreenshotSchema = z.object({
  type: z.literal("screenshot"),
  step: z.number(),
  image_b64: z.string().nullable().optional(),
  image_ref: z.string().nullable().optional(),
  image_format: z.enum(["png", "jpeg"]),
});

// StreamError.code closed vocabulary — 9 values from
// `apps/api/backends/chunks.py:127-137`. Order preserved to ease byte-for-byte
// comparison with the Python source.
export const StreamErrorCodeSchema = z.enum([
  "cost_cap_exceeded",
  "step_cap_exceeded",
  "cancelled",
  "rate_limited",
  "auth_failed",
  "provider_unavailable",
  "timeout",
  "validation_error",
  "internal_error",
]);
export type StreamErrorCodeT = z.infer<typeof StreamErrorCodeSchema>;

// StreamError — `apps/api/backends/chunks.py:117-139`.
export const StreamErrorSchema = z.object({
  type: z.literal("stream_error"),
  code: StreamErrorCodeSchema,
  message: z.string(),
  retriable: z.boolean(),
});

// Done — `apps/api/backends/chunks.py:142-157`. EVERY field is nullable AND
// optional because the Python defaults are `int | None = None`. The auth-
// failure path lands Done with no usage info; the translator must accept it.
export const DoneSchema = z.object({
  type: z.literal("done"),
  tokens_in: z.number().nullable().optional(),
  tokens_out: z.number().nullable().optional(),
  cost_usd: z.number().nullable().optional(),
  latency_ms: z.number().nullable().optional(),
  routing_signals: z.record(z.string(), z.unknown()).nullable().optional(),
});

// --------------------------------------------------------------------
// NamedSSEEvent discriminated union (8 variants, keyed by `event`)
// --------------------------------------------------------------------

// The single discriminator on which sse-translate.ts switches.
// Closed-vocabulary: anything outside the 8 variants fails Zod parse and the
// translator emits {type:"error"} per Pattern F.
export const NamedSSEEventSchema = z.discriminatedUnion("event", [
  z.object({ event: z.literal("routing_decision"), data: RoutingDecisionDataSchema }),
  z.object({ event: z.literal("text_delta"), data: TextDeltaSchema }),
  z.object({ event: z.literal("tool_call"), data: ToolCallSchema }),
  z.object({ event: z.literal("tool_result"), data: ToolResultSchema }),
  z.object({ event: z.literal("file_diff"), data: FileDiffSchema }),
  z.object({ event: z.literal("screenshot"), data: ScreenshotSchema }),
  z.object({ event: z.literal("stream_error"), data: StreamErrorSchema }),
  z.object({ event: z.literal("done"), data: DoneSchema }),
]);
export type NamedSSEEventT = z.infer<typeof NamedSSEEventSchema>;
