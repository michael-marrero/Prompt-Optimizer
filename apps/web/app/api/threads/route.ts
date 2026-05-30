// POST /api/threads — creates a thread, used primarily by
// apps/web/lib/thread-id.ts:getOrCreateDefaultThread() on first app
// load. The browser caches the resulting id in localStorage so all
// subsequent chat turns can reference it without a round-trip.
//
// Body forwarded verbatim — Phase 3 D-10 contract is `{title: string}`.
// If the browser omits a title (the default-thread auto-create case),
// we default it to "Untitled" so FastAPI's ThreadCreateRequest model
// validation passes.
//
// Cross-refs:
//   - 04-CONTEXT.md "Thread creation in minimal mode" (Claude's Discretion)
//   - 04-PATTERNS.md apps/web/app/api/threads/route.ts section (POST shape)
//   - apps/api/routes/threads.py lines 118-130 (post_thread upstream)
//   - apps/web/lib/api-client.ts:postThread (browser-side wrapper)

export const runtime = "nodejs"; // Pitfall 1
export const dynamic = "force-dynamic"; // mutation endpoint; never cache

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";

// GET /api/threads — sidebar thread-list source (UI-02). Pure passthrough
// to FastAPI `GET /api/v1/threads`, which already orders by `updated_at`
// DESC (Phase 5 05-01), so no client-side re-sort is needed. The browser
// never speaks to FastAPI directly (UI-17) — this proxy is the only path.
//
// Cross-refs:
//   - 05-PATTERNS.md apps/web/app/api/threads/route.ts (EXTEND: add GET list)
//   - apps/web/app/api/health/route.ts (GET passthrough analog)
//   - apps/api/routes/threads.py (GET /threads list)
export async function GET(_req: Request) {
  let upstream: Response;
  try {
    upstream = await fetch(`${FASTAPI_URL}/api/v1/threads`);
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

export async function POST(req: Request) {
  // Parse body — fall back to {} so the auto-create call with no body
  // still produces a valid {title:"Untitled"} forward.
  let body: { title?: unknown };
  try {
    body = await req.json();
  } catch {
    body = {};
  }
  const title =
    typeof body.title === "string" && body.title.length > 0
      ? body.title
      : "Untitled";

  let upstream: Response;
  try {
    upstream = await fetch(`${FASTAPI_URL}/api/v1/threads`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
  } catch {
    return Response.json(
      { error: "API unavailable — is uvicorn running?" },
      { status: 503 },
    );
  }

  if (!upstream.ok) {
    // Forward upstream error body + status — useful for diagnostics
    // (404 thread-id collision, 422 title-too-long, etc).
    const text = await upstream.text().catch(() => "");
    return new Response(text, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  return Response.json(await upstream.json());
}
