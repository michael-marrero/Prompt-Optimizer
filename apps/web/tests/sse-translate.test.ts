// Plan 04-01 Wave-0 STUB. VALIDATION.md row: "D-07 contract".
// Plan 04-02 (Wave 1 — sse-translate.ts implementation) overwrites this stub
// with real fixtures that feed a fake upstream ReadableStream into
// translateNamedSSEToUIMessageStream and assert the AI SDK v6 chunk sequence.
// Until then: pure stubs collected as todo.
import { describe, it } from "vitest";

describe("D-07 contract — translateNamedSSEToUIMessageStream", () => {
  it.todo(
    "D-07: emits {type:start} + {type:data-routing} on a routing_decision event",
  );
  it.todo(
    "D-07: emits {type:text-start} once then {type:text-delta,id}* on text_delta events",
  );
  it.todo(
    "D-07: emits {type:text-end} + {type:data-metrics} + {type:finish} + literal data: [DONE] on done",
  );
  it.todo("D-07: emits {type:abort} on stream_error code=cancelled");
  it.todo(
    "D-07: emits {type:error} with errorText preserved on stream_error code!=cancelled",
  );
  it.todo("D-07: malformed upstream event emits a single error chunk and continues");
});
