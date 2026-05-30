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

// --------------------------------------------------------------------
// Phase 5 — full per-backend turn fixtures (drive the bubble component tests)
// --------------------------------------------------------------------
//
// Each ordered array is the exact byte sequence a real FastAPI turn emits for
// the given backend, in stream order. Component tests feed these through the
// same fake-ReadableStream → translateNamedSSEToUIMessageStream path the
// sse-translate tests already use, OR parse the payloads directly to build the
// `useMessage().content` data-part array (RoutingChip.tsx:85-91 pattern).
//
// Event names match `sse-translate.ts` exactly (routing_decision, tool_call,
// tool_result, file_diff, screenshot, text_delta, done). Payload field names
// match `chunk-schemas.ts` exactly:
//   - file_diff:  {tool_call_id, path, diff, operation}
//   - screenshot: {step, image_b64?, image_ref?, image_format}
//   - tool_call:  {tool_call_id, tool_name, arguments}

// --------------------------------------------------------------------
// claude_code turn — routing_decision (green/claude_code) + tool_call +
// tool_result + file_diff + final text_delta + done.
// Drives CodeBubble (UI-09, UI-SPEC §7).
// --------------------------------------------------------------------

export const CLAUDE_CODE_ROUTING_DECISION_EVENT =
  'event: routing_decision\ndata: {"backend":"claude_code","model_or_agent":"claude-code","rationale":"Build-and-edit coding task","confidence":0.94,"signals":{"task_type":"coding","agentic_intent":true,"rule_fired":"coding_task"}}\n\n';

export const CLAUDE_CODE_TOOL_CALL_EVENT =
  'event: tool_call\ndata: {"type":"tool_call","tool_call_id":"tc_cc_001","tool_name":"edit_file","arguments":{"path":"src/app.py","instruction":"add a budget total"}}\n\n';

export const CLAUDE_CODE_TOOL_RESULT_EVENT =
  'event: tool_result\ndata: {"type":"tool_result","tool_call_id":"tc_cc_001","content":"Applied edit to src/app.py","is_error":false}\n\n';

export const CLAUDE_CODE_FILE_DIFF_EVENT =
  'event: file_diff\ndata: {"type":"file_diff","tool_call_id":"tc_cc_001","path":"src/app.py","diff":"@@ -1,2 +1,3 @@\\n context_line\\n-old_total = 0\\n+total = sum(amounts)\\n+return total","operation":"edit"}\n\n';

export const CLAUDE_CODE_TEXT_DELTA_EVENT =
  'event: text_delta\ndata: {"type":"text_delta","text":"I added a budget total to your finance tracker."}\n\n';

export const CLAUDE_CODE_DONE_EVENT =
  'event: done\ndata: {"type":"done","tokens_in":120,"tokens_out":64,"cost_usd":0.0085,"latency_ms":4200,"routing_signals":{"task_type":"coding","agentic_intent":true,"rule_fired":"coding_task"}}\n\n';

// Full ordered claude_code turn (routing → tool_call → tool_result → file_diff
// → text_delta → done). Import this array to render a complete CodeBubble.
export const CLAUDE_CODE_TURN_EVENTS = [
  CLAUDE_CODE_ROUTING_DECISION_EVENT,
  CLAUDE_CODE_TOOL_CALL_EVENT,
  CLAUDE_CODE_TOOL_RESULT_EVENT,
  CLAUDE_CODE_FILE_DIFF_EVENT,
  CLAUDE_CODE_TEXT_DELTA_EVENT,
  CLAUDE_CODE_DONE_EVENT,
] as const;

// Pre-built `useMessage().content`-shaped data-part array for the claude_code
// turn — mirrors what `convertMessage` produces (data-<event> → {type:"data",
// name:"<event>", data}). CodeBubble reads tool_call / file_diff / text parts
// off this shape (RoutingChip.tsx:85-91 + PATTERNS data-part subscription).
export const CLAUDE_CODE_CONTENT_PARTS = [
  {
    type: "data",
    name: "routing",
    data: {
      backend: "claude_code",
      model_or_agent: "claude-code",
      rationale: "Build-and-edit coding task",
      confidence: 0.94,
      signals: { task_type: "coding", agentic_intent: true, rule_fired: "coding_task" },
    },
  },
  {
    type: "data",
    name: "tool_call",
    data: {
      type: "tool_call",
      tool_call_id: "tc_cc_001",
      tool_name: "edit_file",
      arguments: { path: "src/app.py", instruction: "add a budget total" },
    },
  },
  {
    type: "data",
    name: "tool_result",
    data: {
      type: "tool_result",
      tool_call_id: "tc_cc_001",
      content: "Applied edit to src/app.py",
      is_error: false,
    },
  },
  {
    type: "data",
    name: "file_diff",
    data: {
      type: "file_diff",
      tool_call_id: "tc_cc_001",
      path: "src/app.py",
      diff: "@@ -1,2 +1,3 @@\n context_line\n-old_total = 0\n+total = sum(amounts)\n+return total",
      operation: "edit",
    },
  },
  {
    type: "text",
    text: "I added a budget total to your finance tracker.",
  },
] as const;

// --------------------------------------------------------------------
// computer_use turn — routing_decision (amber/computer_use) + screenshot with
// inline image_b64 + screenshot with image_ref only (≥256KB → externalized,
// served from /api/blobs/{hash}) + text_delta + done.
// Drives ComputerUseBubble (UI-10, UI-SPEC §8).
// --------------------------------------------------------------------

export const COMPUTER_USE_ROUTING_DECISION_EVENT =
  'event: routing_decision\ndata: {"backend":"computer_use","model_or_agent":"computer-use","rationale":"Browse-and-act task","confidence":0.88,"signals":{"task_type":"agentic","agentic_intent":true,"rule_fired":"browse_keyword"}}\n\n';

// First screenshot — small, shipped inline as base64 (1x1 transparent PNG).
export const COMPUTER_USE_SCREENSHOT_INLINE_EVENT =
  'event: screenshot\ndata: {"type":"screenshot","step":1,"image_b64":"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=","image_ref":null,"image_format":"png"}\n\n';

// Second screenshot — large (≥256KB) so the adapter externalized it to the blob
// store: image_b64 is null, image_ref carries the content hash. The thumbnail
// must resolve to `/api/blobs/{hash}` (RESEARCH Pitfall 1, UI-SPEC §8.2).
export const COMPUTER_USE_SCREENSHOT_REF_EVENT =
  'event: screenshot\ndata: {"type":"screenshot","step":2,"image_b64":null,"image_ref":"a1b2c3d4e5f60718293a4b5c6d7e8f90112233445566778899aabbccddeeff00","image_format":"png"}\n\n';

export const COMPUTER_USE_TEXT_DELTA_EVENT =
  'event: text_delta\ndata: {"type":"text_delta","text":"The price on the page is $42.00."}\n\n';

export const COMPUTER_USE_DONE_EVENT =
  'event: done\ndata: {"type":"done","tokens_in":210,"tokens_out":48,"cost_usd":0.0190,"latency_ms":7800,"routing_signals":{"task_type":"agentic","agentic_intent":true,"rule_fired":"browse_keyword"}}\n\n';

// Full ordered computer_use turn (routing → inline screenshot → image_ref
// screenshot → text_delta → done). Import to render a complete ComputerUseBubble.
export const COMPUTER_USE_TURN_EVENTS = [
  COMPUTER_USE_ROUTING_DECISION_EVENT,
  COMPUTER_USE_SCREENSHOT_INLINE_EVENT,
  COMPUTER_USE_SCREENSHOT_REF_EVENT,
  COMPUTER_USE_TEXT_DELTA_EVENT,
  COMPUTER_USE_DONE_EVENT,
] as const;

// The bare sha256 stem the second screenshot externalizes to. The
// ComputerUseBubble test asserts the thumbnail src resolves to
// `/api/blobs/${COMPUTER_USE_SCREENSHOT_REF_HASH}` (the bare stem the
// blob endpoint contracts on).
export const COMPUTER_USE_SCREENSHOT_REF_HASH =
  "a1b2c3d4e5f60718293a4b5c6d7e8f90112233445566778899aabbccddeeff00";

// BL-01: the backend stores `image_ref` as the bare content KEY
// (`<sha>.<ext>`), and the bubble strips the extension to the bare stem
// before building the proxy URL. This fixture carries the wire shape
// (with extension) so the test exercises the strip.
export const COMPUTER_USE_SCREENSHOT_REF_KEY = `${COMPUTER_USE_SCREENSHOT_REF_HASH}.png`;

// Pre-built `useMessage().content`-shaped data-part array for the computer_use
// turn — one inline screenshot (image_b64) and one image_ref-only screenshot.
// `status` is left open so the test can assert the "still working…" indicator
// (role="status") while incomplete and the metrics footer once done.
export const COMPUTER_USE_CONTENT_PARTS = [
  {
    type: "data",
    name: "routing",
    data: {
      backend: "computer_use",
      model_or_agent: "computer-use",
      rationale: "Browse-and-act task",
      confidence: 0.88,
      signals: { task_type: "agentic", agentic_intent: true, rule_fired: "browse_keyword" },
    },
  },
  {
    type: "data",
    name: "screenshot",
    data: {
      type: "screenshot",
      step: 1,
      image_b64:
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",
      image_ref: null,
      image_format: "png",
    },
  },
  {
    type: "data",
    name: "screenshot",
    data: {
      type: "screenshot",
      step: 2,
      image_b64: null,
      image_ref: COMPUTER_USE_SCREENSHOT_REF_KEY,
      image_format: "png",
    },
  },
  {
    type: "text",
    text: "The price on the page is $42.00.",
  },
] as const;
