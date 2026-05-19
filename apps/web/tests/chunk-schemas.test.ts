// Plan 04-01 Wave-0 STUB. VALIDATION.md row: "Schema contract".
// Plan 04-02 (Wave 1 — chunk-schemas.ts implementation) overwrites this stub
// with one parse test per Phase 3 named event variant (RESEARCH Pattern A
// closed-vocabulary union). Wave 0 just guarantees the path exists.
import { describe, it } from "vitest";

describe("Schema contract — Zod schemas mirror Phase 2 ChatChunk union", () => {
  it.todo(
    "Schema: parses event:routing_decision data with backend/model_or_agent/rationale/confidence/signals",
  );
  it.todo("Schema: parses event:text_delta {type, text}");
  it.todo("Schema: parses event:tool_call {type, tool_call_id, tool_name, arguments}");
  it.todo("Schema: parses event:tool_result {type, tool_call_id, content, is_error}");
  it.todo("Schema: parses event:file_diff {type, tool_call_id, path, diff, operation}");
  it.todo("Schema: parses event:screenshot {type, step, image_b64?, image_ref?, image_format}");
  it.todo(
    "Schema: parses event:stream_error with all 9 StreamError.code literals (Pattern A)",
  );
  it.todo(
    "Schema: parses event:done {type, tokens_in?, tokens_out?, cost_usd?, latency_ms?, routing_signals?}",
  );
});
