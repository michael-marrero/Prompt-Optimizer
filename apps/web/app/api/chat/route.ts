// SSE proxy + translator for the browser→FastAPI chat pipe. This is the
// load-bearing UI-17 satisfaction surface: the browser only ever talks to
// `/api/chat` on the Next.js origin, and this handler is the single point
// at which `FASTAPI_URL` is read. The browser bundle never sees it.
//
// Wire shape: browser POSTs `{messages: UIMessage[], threadId: string}`
// (AI SDK v6 default body + a Plan-05 `prepareSendMessagesRequest`
// injection of the resolved default-thread id). We strip the messages
// array to the latest user text per D-08 and forward to
// `POST /api/v1/threads/{threadId}/turn` with `{message: <text>}`.
// FastAPI's `get_thread_messages` is the single source of history truth.
//
// Cross-refs:
//   - 04-CONTEXT.md D-07 (named-event SSE wire), D-08 (body stripping),
//                   D-09 (AbortController chain), D-18 (key isolation)
//   - 04-RESEARCH.md §"Pattern 2" lines 642-697 (canonical skeleton);
//                   Critical Finding #3 (Node runtime mandatory);
//                   Pitfall 1 (never Edge), Pitfall 2 (never await body),
//                   Pitfall 7 (AI SDK v6 stream-protocol header)
//   - 04-PATTERNS.md apps/web/app/api/chat/route.ts section (full pattern)
//   - apps/web/lib/sse-translate.ts (Wave 1 translator we wrap)
//   - apps/api/routes/turn.py lines 350-590 (upstream handler we proxy)

import { translateNamedSSEToUIMessageStream } from "@/lib/sse-translate";

// Pitfall 1 — Edge runtime breaks SSE in production (no Node streams,
// no TransformStream parity); RESEARCH Critical Finding #3 mandates
// Node runtime for every route handler that touches an upstream stream.
export const runtime = "nodejs";

// Never cache; every chat turn is a fresh upstream call with abort
// semantics that the Next response cache would silently mangle.
export const dynamic = "force-dynamic";

// FASTAPI_URL is read here ONLY — it must never be re-exported to a lib
// or component file, and there must never be a NEXT_PUBLIC_FASTAPI_URL
// variant anywhere in the repo (Plan 07's browser-isolation.spec.ts
// enforces zero outbound browser requests to localhost:8000).
const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";

export async function POST(req: Request) {
  // ----------------------------------------------------------------
  // Parse body — AI SDK v6's default useChat shape carries the full
  // messages array; Plan 05's `prepareSendMessagesRequest` injects the
  // resolved `threadId` so this handler does not need to call
  // getOrCreateDefaultThread itself (UI-17 — browser owns the cache).
  // ----------------------------------------------------------------
  let body: { messages?: unknown; threadId?: unknown };
  try {
    body = await req.json();
  } catch {
    return new Response(
      JSON.stringify({ error: "invalid JSON body" }),
      { status: 400, headers: { "Content-Type": "application/json" } },
    );
  }

  // threadId is required — the browser caller (getOrCreateDefaultThread)
  // guarantees one exists before posting. A missing or non-string value
  // is a programmer error, not a user-recoverable state.
  const threadId = body.threadId;
  if (typeof threadId !== "string" || threadId.length === 0) {
    return new Response(
      JSON.stringify({ error: "threadId is required" }),
      { status: 400, headers: { "Content-Type": "application/json" } },
    );
  }

  // ----------------------------------------------------------------
  // D-08: strip the AI SDK v5+ {messages:[...]} body to FastAPI's
  // {message: <latest user text>}. FastAPI re-hydrates prior history
  // from SQLite — the messages array is discarded at this boundary so
  // the browser cache and the DB can never drift apart.
  // ----------------------------------------------------------------
  const messagesArray = Array.isArray(body.messages) ? body.messages : [];
  const lastUserMessage = [...messagesArray]
    .reverse()
    .find((m: unknown): m is { role: string; parts?: unknown; content?: unknown } => {
      return (
        typeof m === "object" &&
        m !== null &&
        "role" in m &&
        (m as { role: unknown }).role === "user"
      );
    });
  // AI SDK v6 stores text in `parts: [{type:"text", text:"..."}]`; older v4
  // shape uses bare `content`. Fall back through both for compatibility.
  const parts = (lastUserMessage as { parts?: unknown })?.parts;
  const partsArray = Array.isArray(parts) ? parts : [];
  const textPart = partsArray.find(
    (p: unknown): p is { type: string; text: string } =>
      typeof p === "object" &&
      p !== null &&
      "type" in p &&
      (p as { type: unknown }).type === "text" &&
      "text" in p &&
      typeof (p as { text: unknown }).text === "string",
  );
  const content = (lastUserMessage as { content?: unknown })?.content;
  const userText: string =
    textPart?.text ??
    (typeof content === "string" ? content : "") ??
    "";

  // ----------------------------------------------------------------
  // D-09: forward AbortController chain via `signal: req.signal`. When
  // the browser aborts, Next.js cancels req.signal, which cancels the
  // upstream fetch, which fires sse-starlette's request.is_disconnected
  // polling on the FastAPI side, which fires the adapter's
  // asyncio.CancelledError handler — the 2-second budget asserted by
  // Plan 07's cancel-budget.spec.ts.
  // ----------------------------------------------------------------
  let upstream: Response;
  try {
    upstream = await fetch(
      `${FASTAPI_URL}/api/v1/threads/${encodeURIComponent(threadId)}/turn`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userText }),
        signal: req.signal,
      },
    );
  } catch (err: unknown) {
    // Browser aborted before/during the upstream handshake — the chain
    // is intact; return the nginx-conventional 499 "Client Closed
    // Request" status so any future log analysis distinguishes user
    // aborts from real errors.
    if ((err as { name?: string })?.name === "AbortError") {
      return new Response(null, { status: 499 });
    }
    // ECONNREFUSED / DNS failure / network down. UI-SPEC §17 mandates
    // the exact banner text "API unavailable — is uvicorn running?"
    // so users get an actionable, non-alarming message.
    return new Response(
      JSON.stringify({ error: "API unavailable — is uvicorn running?" }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    );
  }

  // Upstream is reachable but returned a non-2xx (e.g. 404 thread-not-
  // found, 422 validation error, 500 adapter blew up before streaming).
  // Safe to read the body here because the upstream has already chosen
  // a non-streaming JSON response (FastAPI raises HTTPException BEFORE
  // returning EventSourceResponse on errors). For 2xx we MUST NOT read
  // the body — see Pitfall 2 just below.
  if (!upstream.ok || !upstream.body) {
    let detail = "";
    try {
      detail = await upstream.text();
    } catch {
      // body unreadable — keep going with an empty detail
    }
    return new Response(
      JSON.stringify({
        error: `Upstream returned ${upstream.status}`,
        detail,
      }),
      {
        status: upstream.status,
        headers: { "Content-Type": "application/json" },
      },
    );
  }

  // ----------------------------------------------------------------
  // Pitfall 2 + RESEARCH Critical Finding #4: return the response
  // IMMEDIATELY after wrapping the upstream body in the translator.
  // Never `await upstream.text()` or any other body-consuming call on
  // a successful streaming response — that buffers the entire stream
  // into memory and defeats the whole point of SSE.
  //
  // Pitfall 7: the `x-vercel-ai-ui-message-stream: v1` response header
  // is REQUIRED by the AI SDK v6 client to choose the UI Message Stream
  // protocol parser. Without it the client silently falls back to a
  // different protocol and message chunks drop on the floor with no
  // visible error in the browser console.
  // ----------------------------------------------------------------
  const translated = translateNamedSSEToUIMessageStream(upstream.body);

  return new Response(translated, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      // Prevent nginx / cloud proxy buffering of the SSE stream.
      "X-Accel-Buffering": "no",
      // Pitfall 7 — without this header the AI SDK v6 client misparses.
      "x-vercel-ai-ui-message-stream": "v1",
    },
  });
}
