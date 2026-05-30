// GET /api/blobs/[hash] — Next proxy that streams a stored screenshot/diff
// blob's bytes from FastAPI's `GET /api/v1/blobs/{hash}`. This is the ONLY
// path the browser uses to fetch blobs (UI-17 / T-05-02-PROXY): the
// ComputerUseBubble (built in 05-04) sets `<img src="/api/blobs/{hash}">`,
// which hits this handler on the Next origin. The browser bundle never sees
// `FASTAPI_URL` and never talks to the FastAPI port directly — Plan 06's
// browser-isolation.spec.ts enforces zero direct browser→FastAPI blob calls.
//
// Cross-refs:
//   - 05-PATTERNS.md "Next proxy handler skeleton" + "Next-16 dynamic params
//     are a Promise"
//   - apps/web/app/api/health/route.ts (GET passthrough skeleton)
//   - apps/web/app/api/threads/[id]/route.ts (Next 16 `await params`)
//   - apps/web/app/api/chat/route.ts (stream upstream.body through — never
//     `.text()`-buffer a binary/streaming body; Phase 4 streaming-proxy pitfall)
//   - apps/api/routes/blobs.py (upstream we proxy verbatim)

// Pitfall 1 — Edge runtime forbids Node stream features; every route handler
// in apps/web/app/api/**/route.ts declares the Node runtime for consistency.
export const runtime = "nodejs";

// Blobs are content-addressed (sha256-keyed) so the bytes are immutable, but
// the upstream may not exist yet at first paint; never let Next's response
// cache mask a real upstream state.
export const dynamic = "force-dynamic";

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ hash: string }> },
) {
  // Next 16 — `params` is a Promise; await before destructuring. The leading
  // underscore on `_req` flags it as deliberately unused (a blob GET ignores
  // the request body/headers).
  const { hash } = await params;

  let upstream: Response;
  try {
    upstream = await fetch(
      `${FASTAPI_URL}/api/v1/blobs/${encodeURIComponent(hash)}`,
    );
  } catch {
    // ECONNREFUSED — uvicorn not running. Mirror the canonical banner text so
    // the UI's network-down toast is consistent across every proxy route.
    return Response.json(
      { error: "API unavailable — is uvicorn running?" },
      { status: 503 },
    );
  }

  if (!upstream.ok || !upstream.body) {
    // 404 (unknown/traversal hash) and any other non-2xx flow through with
    // the upstream status so the <img> simply fails to load — no body to
    // forward for the image element's purposes.
    return new Response(null, { status: upstream.status });
  }

  // Stream the binary body through WITHOUT buffering via `.text()` (Phase 4
  // streaming-proxy pitfall — `.text()` on a binary body corrupts the bytes
  // and pulls the whole blob into memory). Forward the upstream content-type
  // so the browser renders the image correctly.
  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type":
        upstream.headers.get("content-type") ?? "application/octet-stream",
    },
  });
}
