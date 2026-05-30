// Compare proxy (Seam A, UI-17) — Phase 7 Plan 07-08.
//
// The browser-facing half of the Compare view (L5): one prompt rendered
// side-by-side across two candidate models. Templated on
// `app/api/chat/route.ts` (the single-stream proxy), this handler is the
// ONLY point at which `FASTAPI_URL` is read for the Compare path — the
// browser bundle never sees it and never opens a FastAPI socket (UI-17).
//
// Wire shape: the browser POSTs `{message, threadId, models:[m1,m2]}`.
// We forward `{message, models}` to the FastAPI `POST
// /api/v1/threads/{threadId}/compare` endpoint (Task 1), which returns a
// SINGLE multiplexed SSE stream whose every event carries a `lane: 0|1`
// discriminator. This handler then:
//
//   1. demultiplexes the backend stream by `lane` into two clean
//      named-SSE sub-streams (stripping the `lane` tag);
//   2. runs EACH lane through its OWN `translateNamedSSEToUIMessageStream`
//      instance — the translator is a PURE per-invocation function
//      (`messageId = m-${crypto.randomUUID()}` is closure-scoped per
//      sse-translate.ts:41-53), so two instances never collide;
//   3. re-multiplexes the two translated AI-SDK streams to the client,
//      re-tagging each chunk with its lane so CompareView can demux.
//
// Reusing the existing translator per-lane (rather than inventing a new
// parser) is the RESEARCH Seam A Option-1 recommendation: the two-stream
// approach is low-risk precisely because the translator is pure.
//
// Cross-refs:
//   - apps/web/app/api/chat/route.ts (single-stream proxy template)
//   - apps/web/lib/sse-translate.ts (the pure per-invocation translator)
//   - apps/api/routes/turn.py post_compare (the upstream we proxy)
//   - 07-PATTERNS.md "Next proxy → FastAPI streaming (UI-17)" + Compare note
//   - 07-CONTEXT.md UI-17 (browser never opens a FastAPI socket)

import { translateNamedSSEToUIMessageStream } from "@/lib/sse-translate";

// Pitfall 1 — Edge runtime breaks SSE in production (no Node streams).
// RESEARCH Critical Finding #3 mandates Node runtime for stream handlers.
export const runtime = "nodejs";

// Never cache a stream; each Compare run is a fresh upstream call with
// abort semantics the Next response cache would mangle.
export const dynamic = "force-dynamic";

// FASTAPI_URL is read HERE ONLY (UI-17). It must never be re-exported to a
// lib/component, and there must be no browser-exposed (NEXT_PUBLIC_*)
// variant anywhere in the repo — the browser only ever calls /api/compare.
const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";

const encoder = new TextEncoder();
const decoder = new TextDecoder();

// Emit one client chunk: a lane-tagged AI-SDK UI-message-stream chunk.
// CompareView consumes /api/compare directly (not via assistant-ui's
// useChat), so it owns this parse — each line is `data: {lane, chunk}`.
function emitLaneChunk(lane: number, chunk: unknown): Uint8Array {
  return encoder.encode(`data: ${JSON.stringify({ lane, chunk })}\n\n`);
}

export async function POST(req: Request): Promise<Response> {
  // ----------------------------------------------------------------
  // Parse body — {message, threadId, models:[m1,m2]}.
  // ----------------------------------------------------------------
  let body: { message?: unknown; threadId?: unknown; models?: unknown };
  try {
    body = await req.json();
  } catch {
    return new Response(JSON.stringify({ error: "invalid JSON body" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const threadId = body.threadId;
  if (typeof threadId !== "string" || threadId.length === 0) {
    return new Response(JSON.stringify({ error: "threadId is required" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const message = typeof body.message === "string" ? body.message : "";

  // The two forced-model lanes. The SSRF/over-fetch guard lives on the
  // FastAPI side (turn.py validates BOTH ids against the allowlist and
  // rejects off-list ids with 422 — T-07-16); the proxy forwards the ids
  // verbatim and lets the backend be the single authority.
  const models = Array.isArray(body.models) ? body.models : [];
  if (models.length !== 2 || !models.every((m) => typeof m === "string")) {
    return new Response(
      JSON.stringify({ error: "models must be an array of exactly two ids" }),
      { status: 400, headers: { "Content-Type": "application/json" } },
    );
  }

  // ----------------------------------------------------------------
  // Open the single upstream Compare stream. `signal: req.signal`
  // forwards the abort chain: a client disconnect cancels this fetch,
  // which fires FastAPI's disconnect detection, which cancels BOTH lane
  // tasks server-side (T-07-19) — one upstream socket, both lanes.
  // ----------------------------------------------------------------
  let upstream: Response;
  try {
    upstream = await fetch(
      `${FASTAPI_URL}/api/v1/threads/${encodeURIComponent(threadId)}/compare`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, models }),
        signal: req.signal,
      },
    );
  } catch (err: unknown) {
    if ((err as { name?: string })?.name === "AbortError") {
      return new Response(null, { status: 499 });
    }
    return new Response(
      JSON.stringify({ error: "API unavailable — is uvicorn running?" }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    );
  }

  // Non-2xx (e.g. 404 thread-not-found, 422 off-list model) — safe to
  // read the body because FastAPI raises HTTPException BEFORE returning
  // the EventSourceResponse on errors. NEVER read the body on a 2xx
  // stream (Pitfall 2) — that buffers the whole stream into memory.
  if (!upstream.ok || !upstream.body) {
    let detail = "";
    try {
      detail = await upstream.text();
    } catch {
      // body unreadable — keep an empty detail
    }
    return new Response(
      JSON.stringify({ error: `Upstream returned ${upstream.status}`, detail }),
      {
        status: upstream.status,
        headers: { "Content-Type": "application/json" },
      },
    );
  }

  // ----------------------------------------------------------------
  // Per-lane translator wiring. Each lane gets its OWN TransformStream
  // whose writable receives clean named-SSE blocks (lane tag stripped)
  // and whose readable is fed to a dedicated translator instance.
  // ----------------------------------------------------------------
  const laneIn: TransformStream<Uint8Array, Uint8Array>[] = [
    new TransformStream(),
    new TransformStream(),
  ];
  const laneWriters = laneIn.map((t) => t.writable.getWriter());
  // Two independent translator instances — pure + closure-scoped, never
  // collide (RESEARCH Seam A; sse-translate.ts:41-53).
  const laneOut = laneIn.map((t) =>
    translateNamedSSEToUIMessageStream(t.readable),
  );

  const client = new ReadableStream<Uint8Array>({
    async start(controller) {
      // Pump each lane's translated output to the client, tagged by lane.
      const pumps = laneOut.map((stream, lane) =>
        (async () => {
          const reader = stream.getReader();
          let buf = "";
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            // The translator emits `data: {...}\n\n` AI-SDK chunks. Re-tag
            // each with its lane for the client demux. Accumulate across
            // reads so a chunk split mid-line still parses.
            buf += decoder.decode(value, { stream: true });
            let nl: number;
            while ((nl = buf.indexOf("\n\n")) !== -1) {
              const block = buf.slice(0, nl);
              buf = buf.slice(nl + 2);
              const line = block.split("\n").find((l) => l.startsWith("data: "));
              if (!line) continue;
              const json = line.slice(6);
              if (json === "[DONE]") {
                controller.enqueue(emitLaneChunk(lane, { type: "finish-lane" }));
                continue;
              }
              try {
                controller.enqueue(emitLaneChunk(lane, JSON.parse(json)));
              } catch {
                // Drop unparseable translator output rather than wedging
                // the client stream (the translator already guards
                // malformed upstream events with its own error chunk).
              }
            }
          }
        })(),
      );

      // Demultiplex the backend's multiplexed SSE: read `lane` per block,
      // strip it, and forward a clean named-SSE block to that lane's
      // translator input.
      const upstreamReader = upstream.body!.getReader();
      let buffer = "";
      try {
        for (;;) {
          const { done, value } = await upstreamReader.read();
          if (done) break;
          buffer += decoder
            .decode(value, { stream: true })
            .replace(/\r\n/g, "\n")
            .replace(/\r/g, "\n");
          let end: number;
          while ((end = buffer.indexOf("\n\n")) !== -1) {
            const block = buffer.slice(0, end);
            buffer = buffer.slice(end + 2);
            if (!block.trim() || block.startsWith(":")) continue;

            let eventName = "";
            const dataLines: string[] = [];
            for (const ln of block.split("\n")) {
              if (ln.startsWith("event: ")) eventName = ln.slice(7).trim();
              else if (ln.startsWith("data: ")) dataLines.push(ln.slice(6));
            }
            if (!eventName || dataLines.length === 0) continue;

            let parsed: Record<string, unknown>;
            try {
              parsed = JSON.parse(dataLines.join("\n")) as Record<
                string,
                unknown
              >;
            } catch {
              continue;
            }
            const laneVal = parsed["lane"];
            const lane = laneVal === 1 ? 1 : 0;
            // Strip the lane tag — the per-lane translator validates against
            // the closed NamedSSEEventSchema, and the lane key is our
            // multiplexing channel, not part of the chunk contract.
            delete parsed["lane"];
            const writer = laneWriters[lane];
            await writer.write(
              encoder.encode(
                `event: ${eventName}\ndata: ${JSON.stringify(parsed)}\n\n`,
              ),
            );
          }
        }
      } finally {
        // Close both lane inputs so the translators flush + their pumps
        // finish. Then wait for the pumps and close the client stream.
        await Promise.allSettled(laneWriters.map((w) => w.close()));
        await Promise.allSettled(pumps);
        controller.close();
      }
    },
    cancel() {
      // Client disconnected — abort the lane inputs; the upstream fetch is
      // already cancelled via req.signal (which cancels both backend lanes).
      laneWriters.forEach((w) => {
        void w.abort();
      });
    },
  });

  // Pitfall 7: the `x-vercel-ai-ui-message-stream: v1` header is REQUIRED
  // for the AI SDK v6 UI-message-stream protocol (CompareView's lane
  // chunks ride the same protocol). Without it chunks drop silently.
  return new Response(client, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
      "x-vercel-ai-ui-message-stream": "v1",
    },
  });
}
