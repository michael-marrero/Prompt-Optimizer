// GET /api/threads/[id] — lazy fetch for a single thread including
// its messages. Phase 4 only calls this on demand (e.g. when the user
// navigates back to a tab after a reload and the in-memory message
// state was lost); Phase 5 adds the sidebar that uses it heavier.
//
// NOTE — Next 16 changed the route-params shape: `{params}` is now a
// PROMISE, not a plain object. The handler must `await params` BEFORE
// destructuring. Forgetting this used to silently work in Next 15 but
// is a TypeScript error in Next 16. See:
// https://nextjs.org/docs/app/api-reference/file-conventions/route#context
//
// Cross-refs:
//   - 04-PATTERNS.md apps/web/app/api/threads/[id]/route.ts section
//   - apps/api/routes/threads.py lines 148-161 (get_single_thread upstream)
//   - apps/web/lib/api-client.ts:getThread (browser-side wrapper)

export const runtime = "nodejs"; // Pitfall 1
export const dynamic = "force-dynamic"; // mutation-following endpoint; never cache

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  // Next 16 — `params` is a Promise; await before reading. The leading
  // underscore on `_req` flags it as deliberately unused (the request
  // body is irrelevant for a GET).
  const { id } = await params;

  let upstream: Response;
  try {
    upstream = await fetch(
      `${FASTAPI_URL}/api/v1/threads/${encodeURIComponent(id)}`,
    );
  } catch {
    return Response.json(
      { error: "API unavailable — is uvicorn running?" },
      { status: 503 },
    );
  }

  if (!upstream.ok) {
    // 404 (thread not found) flows through verbatim so the UI can
    // distinguish "no such thread" from "server down" cleanly.
    const text = await upstream.text().catch(() => "");
    return new Response(text, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  return Response.json(await upstream.json());
}

// PATCH /api/threads/[id] — rename a thread's title (UI-02 sidebar
// rename + auto-rename write path). Forwards `{title}` to FastAPI
// `PATCH /api/v1/threads/{id}`. Next 16 — `params` is a Promise; await
// before destructuring.
//
// Cross-refs:
//   - 05-PATTERNS.md apps/web/app/api/threads/[id]/route.ts (EXTEND: PATCH + DELETE)
//   - apps/api/routes/threads.py (PATCH /threads/{id} {title})
export async function PATCH(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  let body: { title?: unknown };
  try {
    body = await req.json();
  } catch {
    body = {};
  }

  let upstream: Response;
  try {
    upstream = await fetch(
      `${FASTAPI_URL}/api/v1/threads/${encodeURIComponent(id)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: body.title }),
      },
    );
  } catch {
    return Response.json(
      { error: "API unavailable — is uvicorn running?" },
      { status: 503 },
    );
  }

  if (!upstream.ok) {
    const text = await upstream.text().catch(() => "");
    return new Response(text, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  return Response.json(await upstream.json());
}

// DELETE /api/threads/[id] — remove a thread (UI-02 sidebar delete).
// Forwards to FastAPI `DELETE /api/v1/threads/{id}`, which returns 204
// No Content. We return that 204 status with NO JSON body (a 204 must
// not carry a body). Next 16 — `params` is a Promise; await before use.
export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  let upstream: Response;
  try {
    upstream = await fetch(
      `${FASTAPI_URL}/api/v1/threads/${encodeURIComponent(id)}`,
      { method: "DELETE" },
    );
  } catch {
    return Response.json(
      { error: "API unavailable — is uvicorn running?" },
      { status: 503 },
    );
  }

  if (!upstream.ok) {
    const text = await upstream.text().catch(() => "");
    return new Response(text, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  // Upstream returns 204 No Content — propagate the bodyless status.
  return new Response(null, { status: upstream.status });
}
