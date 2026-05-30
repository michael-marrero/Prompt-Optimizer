// GET /api/threads/[id]/messages — the server-side proxy that fetches a
// thread's persisted message rows from FastAPI for restore (Phase 8 D-05).
// The browser fetches THIS route; the route handler talks to FastAPI. The
// browser NEVER speaks to FastAPI directly (SC-2 / UI-17 invariant —
// browser-isolation.spec.ts asserts zero direct browser→FastAPI calls).
//
// Mirrors the GET handler in `app/api/threads/[id]/route.ts` byte-for-byte,
// changing ONLY the upstream path suffix to `/messages` (JSON passthrough;
// this is NOT the streaming blob branch). The reconstructed rows feed
// `reconstructUIMessages` (lib/reconstruct-messages.ts) which ChatSurface (08-03)
// seeds into useChatRuntime.
//
// NOTE — Next 16 changed the route-params shape: `{params}` is now a PROMISE,
// not a plain object. The handler must `await params` BEFORE destructuring.
// Forgetting this used to silently work in Next 15 but is a TypeScript error in
// Next 16. See:
// https://nextjs.org/docs/app/api-reference/file-conventions/route#context
//
// FASTAPI_URL is read ONLY here and in the sibling thread routes — NEVER as a
// `NEXT_PUBLIC_*` var, never re-exported to the client (UI-17). Edge runtime is
// forbidden (Pitfall 1: the proxy must run on Node so the server-to-server
// fetch stays off the browser).
//
// Cross-refs:
//   - apps/web/app/api/threads/[id]/route.ts (the GET handler mirrored)
//   - apps/api/routes/threads.py (get_thread_messages upstream — D-05)
//   - apps/web/tests/messages-route.test.ts (the SC-2 unit this turns green)
//   - 08-PATTERNS.md §"apps/web/app/api/threads/[id]/messages/route.ts";
//     08-RESEARCH.md §"Pattern 3"; 08-CONTEXT.md §"Anti-Patterns to AVOID"

export const runtime = "nodejs"; // Pitfall 1 — never Edge
export const dynamic = "force-dynamic"; // mutation-following endpoint; never cache

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  // Next 16 — `params` is a Promise; await before reading. The leading
  // underscore on `_req` flags it as deliberately unused (the request body is
  // irrelevant for a GET).
  const { id } = await params;

  let upstream: Response;
  try {
    upstream = await fetch(
      `${FASTAPI_URL}/api/v1/threads/${encodeURIComponent(id)}/messages`,
    );
  } catch {
    return Response.json(
      { error: "API unavailable — is uvicorn running?" },
      { status: 503 },
    );
  }

  if (!upstream.ok) {
    // 404 (thread not found) flows through verbatim so the UI can distinguish
    // "no such thread" from "server down" cleanly (D-01/D-03 not-found vs
    // empty-state).
    const text = await upstream.text().catch(() => "");
    return new Response(text, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  return Response.json(await upstream.json());
}
