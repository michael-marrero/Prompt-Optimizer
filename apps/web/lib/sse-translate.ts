// Pure-function SSE translator — Phase 3 named events → AI SDK v6 UI
// Message Stream Protocol chunks. Reference implementation per
// 04-RESEARCH.md §"Pattern 2" lines 510-637.
//
// Contract (Plan 04 D-07):
//   translateNamedSSEToUIMessageStream(upstream: ReadableStream<Uint8Array>)
//     : ReadableStream<Uint8Array>
//
//   - PURE function — no I/O, no module-level mutable state, no globals.
//     Each invocation builds its own messageId / textPartOpen state and
//     consumes the upstream reader inside the returned stream's start()
//     handler.
//   - Parse failures (malformed JSON, unknown event names, structurally
//     invalid payloads e.g. routing_decision missing model_or_agent)
//     emit a {type:"error",errorText} chunk and CONTINUE — the translator
//     never throws uncaught (Pattern F).
//   - SSE heartbeat lines (`:ping`) and empty blocks are skipped silently.
//   - Multi-read buffer accumulation: a single SSE block split across
//     multiple Uint8Array reads is still parsed correctly (buffer
//     accumulates until the next `\n\n` boundary).
//
// Translation mapping (04-RESEARCH.md lines 498-506):
//   routing_decision (any position) → start (first event only) + data-routing
//   text_delta (first)              → start (if first) + text-start + text-delta
//   text_delta (Nth)                → text-delta (reuses id:"t-0")
//   tool_call / tool_result /
//     file_diff / screenshot         → data-<event> (Phase 5 forward-compat)
//   stream_error (cancelled)         → text-end + abort
//   stream_error (other)             → text-end + error
//   done                             → text-end + data-metrics + finish
//                                       + literal "data: [DONE]\n\n"
//
// Cross-refs:
//   - apps/web/lib/chunk-schemas.ts (NamedSSEEventSchema is the parse boundary)
//   - apps/api/routes/turn.py (the upstream wire shape this consumes)
//   - 04-CONTEXT.md D-15 (structured 5-key routing_decision payload)
//   - 04-PATTERNS.md Pattern F (parse failures → error chunk → CONTINUE)

import { NamedSSEEventSchema } from "@/lib/chunk-schemas";

export function translateNamedSSEToUIMessageStream(
  upstream: ReadableStream<Uint8Array>,
): ReadableStream<Uint8Array> {
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();

  // Per-invocation state — closure-scoped, never module-level.
  let buffer = "";
  let messageStarted = false;
  let textPartOpen = false;
  const messageId = `m-${crypto.randomUUID()}`;
  const textPartId = "t-0";

  // Encode an object as one AI SDK v6 UI Message Stream chunk.
  function emit(chunk: object): Uint8Array {
    return encoder.encode(`data: ${JSON.stringify(chunk)}\n\n`);
  }

  // Ensure the start chunk is emitted exactly once, before any other chunk
  // that requires an open message (data-routing, text-start, data-tool, etc).
  function ensureMessageStarted(
    controller: ReadableStreamDefaultController<Uint8Array>,
  ): void {
    if (!messageStarted) {
      controller.enqueue(emit({ type: "start", messageId }));
      messageStarted = true;
    }
  }

  return new ReadableStream<Uint8Array>({
    async start(controller) {
      const reader = upstream.getReader();
      try {
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          // Per HTML Living Standard §9.2 the SSE line terminator can be
          // `\r\n`, `\r`, or `\n`. sse-starlette (the Phase 3 framing) emits
          // CRLF (`\r\n`), while the Vitest fixtures use LF (`\n`). Normalise
          // to LF so the `indexOf("\n\n")` block boundary scan downstream is
          // wire-format-agnostic. Without this, the translator's buffer grows
          // unboundedly against a CRLF upstream and ZERO chunks ever emit.
          // (Discovered during the Wave 2 smoke check; the unit-test fixtures
          // used LF-only so the bug never surfaced under Vitest.)
          buffer += decoder
            .decode(value, { stream: true })
            .replace(/\r\n/g, "\n")
            .replace(/\r/g, "\n");

          // SSE blocks are separated by `\n\n`. Drain every complete block
          // in the accumulated buffer; the trailing partial (if any) is
          // preserved for the next read.
          let blockEnd: number;
          while ((blockEnd = buffer.indexOf("\n\n")) !== -1) {
            const block = buffer.slice(0, blockEnd);
            buffer = buffer.slice(blockEnd + 2);

            // Skip empty blocks and `:`-prefixed heartbeats silently.
            if (!block.trim() || block.startsWith(":")) continue;

            // Parse `event:` / `data:` lines from the block.
            let eventName = "";
            const dataLines: string[] = [];
            for (const line of block.split("\n")) {
              if (line.startsWith("event: ")) {
                eventName = line.slice(7).trim();
              } else if (line.startsWith("data: ")) {
                dataLines.push(line.slice(6));
              }
            }
            if (!eventName || dataLines.length === 0) continue;

            // Parse the JSON payload AND validate against the closed-vocab
            // Zod union. Any failure (bad JSON, unknown event, structurally
            // invalid payload — e.g. routing_decision missing model_or_agent)
            // collapses into a single error chunk and we CONTINUE (Pattern F).
            let parsed;
            try {
              const rawData = JSON.parse(dataLines.join("\n"));
              parsed = NamedSSEEventSchema.parse({
                event: eventName,
                data: rawData,
              });
            } catch {
              controller.enqueue(
                emit({
                  type: "error",
                  errorText: `Malformed upstream event: ${eventName}`,
                }),
              );
              continue;
            }

            // Translate to AI SDK v6 chunks per the mapping table.
            switch (parsed.event) {
              case "routing_decision": {
                ensureMessageStarted(controller);
                // The data field carries the STRUCTURED 5-key routing record
                // verbatim — backend/model_or_agent/rationale/confidence/signals.
                // Plan 04 D-15 contract — the chip reads these fields directly.
                controller.enqueue(
                  emit({ type: "data-routing", data: parsed.data }),
                );
                break;
              }
              case "text_delta": {
                ensureMessageStarted(controller);
                if (!textPartOpen) {
                  controller.enqueue(
                    emit({ type: "text-start", id: textPartId }),
                  );
                  textPartOpen = true;
                }
                controller.enqueue(
                  emit({
                    type: "text-delta",
                    id: textPartId,
                    delta: parsed.data.text,
                  }),
                );
                break;
              }
              case "stream_error": {
                if (textPartOpen) {
                  controller.enqueue(
                    emit({ type: "text-end", id: textPartId }),
                  );
                  textPartOpen = false;
                }
                if (parsed.data.code === "cancelled") {
                  controller.enqueue(
                    emit({ type: "abort", reason: "cancelled" }),
                  );
                } else {
                  // Non-cancelled errors carry the code + retriable flag so the
                  // UI can render the right banner + retry affordance.
                  controller.enqueue(
                    emit({
                      type: "error",
                      errorText: parsed.data.message,
                      code: parsed.data.code,
                      retriable: parsed.data.retriable,
                    }),
                  );
                }
                break;
              }
              case "done": {
                ensureMessageStarted(controller);
                if (textPartOpen) {
                  controller.enqueue(
                    emit({ type: "text-end", id: textPartId }),
                  );
                  textPartOpen = false;
                }
                controller.enqueue(
                  emit({
                    type: "data-metrics",
                    data: {
                      cost_usd: parsed.data.cost_usd ?? null,
                      latency_ms: parsed.data.latency_ms ?? null,
                      tokens_in: parsed.data.tokens_in ?? null,
                      tokens_out: parsed.data.tokens_out ?? null,
                    },
                  }),
                );
                controller.enqueue(emit({ type: "finish" }));
                // Literal AI SDK v6 terminator sentinel.
                controller.enqueue(encoder.encode("data: [DONE]\n\n"));
                break;
              }
              // tool_call / tool_result / file_diff / screenshot — forwarded as
              // data-<event> for Phase 5 forward-compat. assistant-ui ignores
              // unrecognised data-* types without error so Phase 4 needs no
              // renderer for these.
              case "tool_call":
              case "tool_result":
              case "file_diff":
              case "screenshot": {
                ensureMessageStarted(controller);
                controller.enqueue(
                  emit({
                    type: `data-${parsed.event}`,
                    data: parsed.data,
                  }),
                );
                break;
              }
              default: {
                // Defensive — Zod parse already excludes this branch, but the
                // discriminator type-narrows exhaustively only if every case
                // is handled. Forward unknown shapes as data-<event> too.
                ensureMessageStarted(controller);
                const fallback = parsed as { event: string; data: unknown };
                controller.enqueue(
                  emit({
                    type: `data-${fallback.event}`,
                    data: fallback.data,
                  }),
                );
              }
            }
          }
        }
        controller.close();
      } catch (err) {
        controller.error(err);
      } finally {
        reader.releaseLock();
      }
    },
  });
}
