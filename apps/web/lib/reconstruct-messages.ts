// Phase 8 Plan 08-02 Wave 2 — `reconstructUIMessages`: the parallel pure reader
// that rehydrates persisted message rows into AI-SDK-v6 `UIMessage[]`.
//
// THE PARITY CONTRACT (the single biggest risk this phase carries, SC-3):
// the live render path is fully built and tested, so a restored turn renders
// identically IFF its `UIMessage.parts` use the EXACT same `data-*` wire
// vocabulary the live SSE stream emits. This module reproduces that vocabulary
// from a DIFFERENT input shape (already-parsed JSON rows, not a byte stream).
//
// WHY THIS IS A STANDALONE FUNCTION, NOT A REFACTOR OF sse-translate.ts:
// `sse-translate.ts` is a `ReadableStream<Uint8Array> → ReadableStream<Uint8Array>`
// transformer with SSE framing, CRLF normalization, and incremental
// `text-start`/`text-delta`/`text-end` emission. Stored rows are already-parsed
// JSON with a single collapsed `text` field and NO framing — the shapes barely
// overlap. The CONTEXT anti-pattern + RESEARCH §Alternatives both mandate a
// PARALLEL pure reader: restore is a READ path that must NOT touch the live
// wire. We read sse-translate.ts ONLY for its vocabulary (the `switch` at
// lines 135-242); we do NOT import or modify it.
//
// THE EXACT PART ORDER for an assistant turn (mirrors the live terminal state):
//   1. `data-routing`            FIRST — MessageBubble dispatches on `.data.backend`;
//                                RoutingChip + the D-08 override pill read it.
//   2. `data-<block.type>` × N   each stored `content_blocks` entry 1:1
//                                (`data-tool_call`/`data-tool_result`/
//                                 `data-file_diff`/`data-screenshot`).
//   3. `text`                    a single collapsed body part (if non-empty).
//   4. `data-metrics`            LAST — MetricsFooter renders it; its presence
//                                flips the bubble's `isStreamingComplete=true`.
//
// WIRE SHAPE, NOT CONVERTED SHAPE (08-RESEARCH §Pitfall 2 — load-bearing):
// parts are seeded as `{type:"data-routing", data}` (NO `name` key). The
// `@assistant-ui/react-ai-sdk` `convertParts` strips the `data-` prefix to
// `name` at render time, producing the `{type:"data", name:"routing"}` shape the
// components READ. Seeding the converted shape would trigger
// `console.warn("Unsupported message part type: data")` and silently break
// dispatch (fall back to ChatBubble). So we emit `data-<x>` and never hand-write
// a `name` key.
//
// LOCAL-DoS ROBUSTNESS (Security §DoS — T-08-02-DoS): the user's own stored
// rows are still untrusted input at the reconstruction boundary. An unknown
// `block.type` still maps to `data-<type>` (convertParts drops unknown `data-*`
// gracefully); a null `routing` produces a routing part with `backend:"openrouter"`
// + empty `signals` (the default ChatBubble). A single malformed row is skipped
// rather than throwing — one bad block can never crash the whole surface.
//
// Cross-refs:
//   - apps/web/lib/sse-translate.ts:135-242 (the event→part VOCABULARY mirrored)
//   - apps/web/lib/chunk-schemas.ts (MessageRowSchema — the client parse boundary)
//   - apps/web/lib/types.ts (RoutingDecision / MetricsPayload output shapes)
//   - apps/web/components/MessageBubble.tsx (isRoutingPart → .data.backend dispatch)
//   - apps/web/tests/restore-messages.test.ts (the SC-3 unit this turns green)
//   - 08-RESEARCH.md §"Pattern 1", §"Pitfall 2", §"Pitfall 3"; 08-PATTERNS.md
//     §"apps/web/lib/reconstruct-messages.ts"

import type { UIMessage } from "@ai-sdk/react";

// --------------------------------------------------------------------
// MessageRow — one row from GET /api/threads/{id}/messages (08-RESEARCH
// §Pattern 1). `content_blocks` is the PARSED array (the endpoint json.loads()es
// the DB TEXT column server-side — Pitfall 3). `routing` is the D-01 LEFT JOIN
// sub-object (null on user rows / assistant rows with no routing decision).
// The runtime Zod equivalent is `MessageRowSchema` in chunk-schemas.ts.
// --------------------------------------------------------------------
export interface MessageRow {
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
  routing: {
    rationale: string;
    override: boolean;
    // Story 5.2: overall route confidence; null on legacy rows (pre schema_v3).
    // Optional so pre-5.2 callers/fixtures compile — absent → the safe 1 default.
    confidence?: number | null;
  } | null;
}

// `UIMessage.parts` is a union of pre-conversion part shapes. The data-* parts
// we seed are not in the AI-SDK's narrowed literal union (they carry runtime
// `data-<name>` types), so we widen to this element type at the push sites and
// cast once — the same `as UIMessage["parts"][number]` escape hatch the
// RESEARCH reference uses. No `name` key is ever written (Pitfall 2).
type PartElement = UIMessage["parts"][number];

// Reconstruct ONE row → UIMessage. A user row collapses to a single text part;
// an assistant row emits the routing → blocks → text → metrics sequence above.
function reconstructUIMessage(row: MessageRow): UIMessage {
  if (row.role === "user") {
    return {
      id: row.id,
      role: "user",
      parts: [{ type: "text", text: row.text }] as UIMessage["parts"],
    };
  }

  const parts: PartElement[] = [];

  // 1. routing part FIRST. backend defaults to "openrouter" (the default
  //    ChatBubble) when backend_used is null; signals carries ONLY the D-08
  //    override flag (or an empty object). Story 5.2 makes confidence load-bearing
  //    for render (the low-confidence nudge), so it now restores the PERSISTED
  //    value (schema_v3); legacy rows with no stored confidence fall back to 1
  //    (a safe "high" that never triggers the nudge — AD-7 parity for new rows,
  //    graceful no-nudge for old ones).
  parts.push({
    type: "data-routing",
    data: {
      backend: row.backend_used ?? "openrouter",
      model_or_agent: row.model_used ?? "",
      rationale: row.routing?.rationale ?? "",
      confidence: row.routing?.confidence ?? 1,
      signals: row.routing?.override ? { override: true } : {},
    },
  } as PartElement);

  // 2. non-text chunks 1:1 → data-<block.type>. The stored block IS the chunk
  //    dict (chunk.model_dump()); `data-${block.type}` regenerates the live SSE
  //    part name byte-for-byte. An unknown/forward-compat block.type still maps
  //    to data-<type> (convertParts drops unknown data-* gracefully). Each block
  //    is guarded individually so one malformed entry cannot abort the row.
  for (const block of row.content_blocks ?? []) {
    if (!block || typeof block.type !== "string") continue;
    parts.push({
      type: `data-${block.type}`,
      data: block,
    } as PartElement);
  }

  // 3. collapsed text (markdown summary / narration / chat body). Skip when empty
  //    so a tool-only turn does not seed a blank text part.
  if (row.text) {
    parts.push({ type: "text", text: row.text } as PartElement);
  }

  // 4. metrics part LAST. MetricsFooter renders the final stat line; its presence
  //    is what flips the bubble's isStreamingComplete=true on a restored turn.
  parts.push({
    type: "data-metrics",
    data: {
      cost_usd: row.cost_usd ?? null,
      latency_ms: row.latency_ms ?? null,
      tokens_in: row.tokens_in ?? null,
      tokens_out: row.tokens_out ?? null,
    },
  } as PartElement);

  return { id: row.id, role: "assistant", parts: parts as UIMessage["parts"] };
}

// Reconstruct the full thread → UIMessage[] for seeding useChatRuntime. Rows are
// expected oldest-first (the endpoint orders by sequence). A single row that
// throws during mapping is SKIPPED rather than failing the whole reconstruction
// (T-08-02-DoS): one corrupt stored row cannot blank the entire surface.
export function reconstructUIMessages(rows: MessageRow[]): UIMessage[] {
  const messages: UIMessage[] = [];
  for (const row of rows ?? []) {
    try {
      messages.push(reconstructUIMessage(row));
    } catch {
      // Defensive: skip the bad row, keep rendering the rest of the thread.
      continue;
    }
  }
  return messages;
}
