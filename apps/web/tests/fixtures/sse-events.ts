// Fixture event strings sampled from the real Phase-3 SSE wire shape.
// Each constant is the exact byte sequence FastAPI's
// `ServerSentEvent(event=..., data=chunk.model_dump_json())` produces:
//
//   event: <chunk.type>\ndata: <json-payload>\n\n
//
// Used by:
//   - apps/web/tests/chunk-schemas.test.ts (asserts every fixture parses
//     through NamedSSEEventSchema)
//   - apps/web/tests/sse-translate.test.ts (feeds fixtures into a fake
//     ReadableStream and asserts the translator emits the right AI SDK v6
//     UI Message Stream chunks)
//
// Cross-refs:
//   - apps/api/routes/turn.py lines 481-484 (canonical wire format)
//   - apps/api/backends/chunks.py (per-variant payload shapes)
//   - 04-CONTEXT.md D-15 (structured 5-key routing_decision payload)
//   - 04-PATTERNS.md Pattern A (closed-vocabulary union)

// --------------------------------------------------------------------
// routing_decision (Plan 04 D-15 — STRUCTURED 5-key payload)
// --------------------------------------------------------------------

// Happy-path routing decision — Plan 04's amended turn.py payload shape.
// `signals` is a SUB-FIELD here, not the whole payload.
export const ROUTING_DECISION_EVENT =
  'event: routing_decision\ndata: {"backend":"openrouter","model_or_agent":"openai/gpt-5","rationale":"Strong reasoning fit","confidence":0.9,"signals":{"task_type":"chat","agentic_intent":false,"rule_fired":"default"}}\n\n';

// Drift fixture — payload is missing `model_or_agent`. Used to assert
// Pattern F: Zod parse rejects, translator emits an error chunk and
// CONTINUES (never half-renders a chip).
export const ROUTING_DECISION_EVENT_MISSING_MODEL =
  'event: routing_decision\ndata: {"backend":"openrouter","rationale":"Strong reasoning fit","confidence":0.9,"signals":{"task_type":"chat"}}\n\n';

// --------------------------------------------------------------------
// text_delta — apps/api/backends/chunks.py:49-53
// --------------------------------------------------------------------

export const TEXT_DELTA_EVENT =
  'event: text_delta\ndata: {"type":"text_delta","text":"Hello"}\n\n';

export const TEXT_DELTA_EVENT_2 =
  'event: text_delta\ndata: {"type":"text_delta","text":" world"}\n\n';

export const TEXT_DELTA_EVENT_3 =
  'event: text_delta\ndata: {"type":"text_delta","text":"!"}\n\n';

// --------------------------------------------------------------------
// tool_call / tool_result / file_diff / screenshot
// (Phase 5 forward-compat — Phase 4 ignores these but the contract must hold.)
// --------------------------------------------------------------------

export const TOOL_CALL_EVENT =
  'event: tool_call\ndata: {"type":"tool_call","tool_call_id":"tc_abc123","tool_name":"read_file","arguments":{"path":"src/foo.py"}}\n\n';

export const TOOL_RESULT_EVENT =
  'event: tool_result\ndata: {"type":"tool_result","tool_call_id":"tc_abc123","content":"file contents...","is_error":false}\n\n';

export const FILE_DIFF_EVENT =
  'event: file_diff\ndata: {"type":"file_diff","tool_call_id":"tc_abc123","path":"src/foo.py","diff":"@@ -1 +1 @@\\n-old\\n+new","operation":"edit"}\n\n';

// 1x1 PNG transparent pixel (small enough to ship inline — keeps the fixture
// readable and exercises the image_b64 branch of the Screenshot variant).
export const SCREENSHOT_SMALL_EVENT =
  'event: screenshot\ndata: {"type":"screenshot","step":1,"image_b64":"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=","image_ref":null,"image_format":"png"}\n\n';

// --------------------------------------------------------------------
// stream_error variants
// --------------------------------------------------------------------

// Cancellation — translator maps to {type:"abort", reason:"cancelled"}.
export const STREAM_ERROR_CANCELLED_EVENT =
  'event: stream_error\ndata: {"type":"stream_error","code":"cancelled","message":"User cancelled the turn","retriable":false}\n\n';

// Auth failure — translator maps to {type:"error", errorText, code, retriable}.
export const STREAM_ERROR_AUTH_FAILED_EVENT =
  'event: stream_error\ndata: {"type":"stream_error","code":"auth_failed","message":"Invalid OpenRouter API key","retriable":false}\n\n';

// Cost-cap breach — non-retriable error.
export const STREAM_ERROR_COST_CAP_EVENT =
  'event: stream_error\ndata: {"type":"stream_error","code":"cost_cap_exceeded","message":"Cost cap of $0.10 exceeded","retriable":false}\n\n';

// --------------------------------------------------------------------
// done — terminal chunk with metrics + routing_signals
// --------------------------------------------------------------------

export const DONE_EVENT =
  'event: done\ndata: {"type":"done","tokens_in":42,"tokens_out":17,"cost_usd":0.0021,"latency_ms":1400,"routing_signals":{"task_type":"chat","agentic_intent":false,"rule_fired":"default"}}\n\n';

// Failure-path Done — every field null (the auth-failure path can land Done
// with no usage information at all; mirrors `int | None = None` defaults).
export const DONE_EVENT_EMPTY =
  'event: done\ndata: {"type":"done"}\n\n';

// --------------------------------------------------------------------
// Malformed / negative fixtures
// --------------------------------------------------------------------

// Data line is not valid JSON — exercises the Pattern F try/catch path.
export const MALFORMED_EVENT =
  'event: text_delta\ndata: not-json\n\n';

// Event name not in the 8-variant closed vocabulary — exercises the Zod
// discriminator-rejection path.
export const UNKNOWN_EVENT =
  'event: unknown_garbage_event\ndata: {}\n\n';

// SSE heartbeat (sse-starlette emits `:ping` comments every 15s by default).
// Translator should skip silently — no chunk emitted.
export const HEARTBEAT =
  ':ping\n\n';
