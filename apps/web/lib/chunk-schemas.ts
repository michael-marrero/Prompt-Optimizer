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
//     + the 11-value StreamError.code enum, kept byte-for-byte in lockstep)
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

// StreamError.code closed vocabulary — 11 values from
// `apps/api/backends/chunks.py` StreamError.code. Order preserved to ease
// byte-for-byte comparison with the Python source. The last two entries
// were added additively in Phase 9 (D-05); keep this list in lockstep with
// the Python Literal (same order).
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
  "wall_clock_exceeded",
  "budget_exceeded",
]);
export type StreamErrorCodeT = z.infer<typeof StreamErrorCodeSchema>;

// StreamError — `apps/api/backends/chunks.py:117-139`.
export const StreamErrorSchema = z.object({
  type: z.literal("stream_error"),
  code: StreamErrorCodeSchema,
  message: z.string(),
  retriable: z.boolean(),
});

// Done — `apps/api/backends/chunks.py` Done model. EVERY field is nullable AND
// optional because the Python defaults are `int | None = None`. The auth-
// failure path lands Done with no usage info; the translator must accept it.
// `assistant_message_id` (Phase 9, DEBT-04) mirrors the optional Python
// `assistant_message_id: str | None = None` — the server-assigned id used as
// the feedback join key for a live turn. `.nullish()` == `.nullable().optional()`.
export const DoneSchema = z.object({
  type: z.literal("done"),
  tokens_in: z.number().nullable().optional(),
  tokens_out: z.number().nullable().optional(),
  cost_usd: z.number().nullable().optional(),
  latency_ms: z.number().nullable().optional(),
  routing_signals: z.record(z.string(), z.unknown()).nullable().optional(),
  assistant_message_id: z.string().nullish(),
});

// --------------------------------------------------------------------
// Phase 11 named SIBLING events (NOT part of the frozen ChatChunk union)
// --------------------------------------------------------------------
//
// `turn_start` and `awaiting_approval` are emitted by
// `apps/api/routes/turn.py` as named SSE siblings of the 7-variant ChatChunk
// union (Seam A — the Python ChatChunk union + its byte-for-byte Zod port
// above are NOT extended). They are added ONLY to the SSE parse-boundary
// `NamedSSEEventSchema` below so the translator can consume them instead of
// collapsing them into a Pattern-F error chunk (GAP-1).
//
// Wire shapes mirror turn.py exactly:
//   - turn_start         → {"turn_id": ...}                (turn.py:968)
//   - awaiting_approval  → {"turn_id": ..., "correlation_id": ...} (turn.py:1165)

// turn_start payload — carries the turn_id so the client can later address
// POST /api/control/{turnId} (Phase 12).
export const TurnStartDataSchema = z.object({
  turn_id: z.string(),
});

// awaiting_approval payload — turn_id + a per-emit correlation_id
// (secrets.token_urlsafe(12) on the wire).
export const AwaitingApprovalDataSchema = z.object({
  turn_id: z.string(),
  correlation_id: z.string(),
});

// --------------------------------------------------------------------
// NamedSSEEvent discriminated union (10 variants, keyed by `event`)
// --------------------------------------------------------------------

// The single discriminator on which sse-translate.ts switches.
// Closed-vocabulary: anything outside the 10 variants fails Zod parse and the
// translator emits {type:"error"} per Pattern F.
export const NamedSSEEventSchema = z.discriminatedUnion("event", [
  z.object({ event: z.literal("turn_start"), data: TurnStartDataSchema }),
  z.object({ event: z.literal("awaiting_approval"), data: AwaitingApprovalDataSchema }),
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

// --------------------------------------------------------------------
// MessageRow / MessagesResponse (Plan 08-02) — the GET
// /api/threads/{id}/messages payload boundary.
// --------------------------------------------------------------------
//
// One restored row per persisted message. `reconstruct-messages.ts` turns each
// row into an AI-SDK-v6 `UIMessage` whose parts use the WIRE `data-*` vocabulary
// (08-RESEARCH §Pattern 1). This Zod schema lets ChatSurface (08-03) parse-
// validate the fetched payload at the client trust boundary before reconstruction.
//
// Field provenance (08-RESEARCH §Pattern 1 / §Pitfall 3):
//   - `content_blocks` is the ALREADY-PARSED array (the endpoint `json.loads()`es
//     the `Message.content_blocks` TEXT column server-side; Pitfall 3). Each entry
//     is a `chunk.model_dump()` dict with a `type` discriminator — kept OPEN
//     (`{type: string}` + passthrough) so a forward-compat block.type round-trips
//     instead of failing the whole-row parse (Security §DoS tolerance).
//   - `routing` is the D-01 LEFT JOIN sub-object: null on user rows and on
//     assistant rows with no recorded routing decision.
//   - Every metrics column is nullable (Phase 2 Done allows `int | None = None`
//     on every field; mirrors `MetricsPayload` / `DoneSchema`).

// A single stored content block — the `chunk.model_dump()` dict. The `type`
// discriminator is required (it regenerates the `data-<type>` wire name 1:1);
// every other key is passthrough so unknown/forward-compat fields survive and a
// novel block.type cannot fail the parse (DoS tolerance — T-08-02-DoS).
export const ContentBlockSchema = z
  .object({ type: z.string() })
  .passthrough();
export type ContentBlockT = z.infer<typeof ContentBlockSchema>;

// The D-01 routing join sub-object (null when absent).
export const MessageRoutingSchema = z
  .object({
    rationale: z.string(),
    override: z.boolean(),
    // Story 5.2: overall route confidence for the restored low-confidence nudge.
    // Nullable AND optional to match the TS MessageRow.routing type: the server
    // always emits the key (null on legacy rows), but tolerating an absent key
    // keeps the zod contract consistent with the optional TS shape + older fixtures.
    confidence: z.number().nullable().optional(),
    // Story 6.2: the brain's calibrated low-confidence-fallback verdict, recovered
    // server-side from the persisted signals JSON. This closed object is the RESTORE
    // parse boundary (ChatSurface → MessagesResponseSchema.safeParse → reconstruct);
    // Zod strips unknown keys, so WITHOUT this field the persisted verdict is dropped
    // and the reloaded nudge silently disappears (AD-7 parity break). Optional so
    // legacy rows/fixtures compile → absent → no nudge.
    low_confidence: z.boolean().optional(),
  })
  .nullable();
export type MessageRoutingT = z.infer<typeof MessageRoutingSchema>;

// One row from GET /api/threads/{id}/messages.
export const MessageRowSchema = z.object({
  id: z.string(),
  role: z.enum(["user", "assistant"]),
  text: z.string(),
  content_blocks: z.array(ContentBlockSchema),
  backend_used: z.string().nullable(),
  model_used: z.string().nullable(),
  cost_usd: z.number().nullable(),
  latency_ms: z.number().nullable(),
  tokens_in: z.number().nullable(),
  tokens_out: z.number().nullable(),
  status: z.enum(["complete", "error", "cancelled"]),
  routing: MessageRoutingSchema,
});
export type MessageRowT = z.infer<typeof MessageRowSchema>;

// The full response — an ordered array of rows (oldest-first).
export const MessagesResponseSchema = z.array(MessageRowSchema);
export type MessagesResponseT = z.infer<typeof MessagesResponseSchema>;
