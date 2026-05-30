// POST /api/feedback — "wrong route" feedback proxy (UI-15, D-11–D-14).
//
// Thumbs up/down on an assistant turn append a full-context row to
// FastAPI's `.planning/data/routing_feedback.jsonl` writer. The browser
// cannot write the filesystem, so it POSTs the D-12 row here and this
// proxy forwards it verbatim to FastAPI `POST /api/v1/feedback`. The
// server stamps the authoritative timestamp (the client clock is not
// trusted) and appends append-only (D-13).
//
// No secret scrub is needed — feedback rows carry no key material (just
// sentiment, ids, the prompt, and the routing decision already attached
// client-side). No streaming. The browser never speaks to FastAPI
// directly (UI-17) — this proxy is the only path.
//
// Cross-refs:
//   - 05-PATTERNS.md apps/web/app/api/feedback/route.ts (NEW)
//   - 05-CONTEXT.md D-11 (log up + down), D-12 (row schema), D-14 (proxy)
//   - apps/api/routes/feedback.py (upstream POST /api/v1/feedback)
//   - apps/web/app/api/settings/route.ts (POST→PATCH forward analog)

export const runtime = "nodejs"; // Pitfall 1 — Node runtime only
export const dynamic = "force-dynamic"; // mutation endpoint; never cache

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";

export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "invalid JSON body" }, { status: 400 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${FASTAPI_URL}/api/v1/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    return Response.json(
      { error: "API unavailable — is uvicorn running?" },
      { status: 503 },
    );
  }

  if (!upstream.ok) {
    // Forward upstream non-2xx verbatim (e.g. 422 from extra="forbid").
    const text = await upstream.text().catch(() => "");
    return new Response(text, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  return Response.json(await upstream.json());
}
