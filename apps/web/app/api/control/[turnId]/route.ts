// POST /api/control/[turnId] — per-turn control-channel proxy (CTRL-01, UI-17).
//
// A control command (approve / pause / interrupt / redirect / take-over)
// must reach an IN-FLIGHT turn while its SSE stream is still open. The
// browser learned the `turnId` from the `turn_start` named SSE event
// (Plan 02, D-05) and POSTs the control body here. The browser cannot —
// and must never — speak to FastAPI directly (UI-17), so this Next route
// handler is the ONLY path: it owns `FASTAPI_URL` server-side and forwards
// the body verbatim to FastAPI `POST /api/v1/turns/{turn_id}/control`,
// returning the upstream status (202/404/422/413) unchanged.
//
// Fire-and-forget, non-SSE: this models the `feedback/route.ts` proxy, NOT
// the streaming `chat/route.ts`. There is no stream to wrap — the upstream
// returns a small JSON body and a status code, both forwarded as-is.
//
// No secret scrub is needed — control bodies carry no key material (a
// closed `kind` verb + an opaque `payload`); the size cap + `kind`
// validation live at the FastAPI boundary (Plan 02 T-11-06), so this proxy
// forwards verbatim and returns the upstream 413/422 unchanged.
//
// Cross-refs:
//   - apps/web/app/api/feedback/route.ts (the non-SSE proxy template)
//   - apps/api/routes/control.py (upstream POST /api/v1/turns/{turn_id}/control)
//   - 11-02-SUMMARY.md (turn_start surfaces turn_id; /control 202/404/422/413)
//   - 11-03-PLAN.md Task 1 (UI-17 fire-and-forget; FASTAPI_URL server-side only)

export const runtime = "nodejs"; // Pitfall 1 — Node runtime only
export const dynamic = "force-dynamic"; // mutation endpoint; never cache

// FASTAPI_URL is read here ONLY and there must never be a browser-exposed
// (client-public-prefixed) variant of it anywhere in the repo (UI-17,
// T-11-11). The browser-isolation.spec.ts asserts zero direct
// browser→FastAPI requests on the control path, and the public-env-prefix
// grep on this file returns 0 — the internal origin never ships to the
// client bundle.
const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";

export async function POST(
  req: Request,
  { params }: { params: { turnId: string } },
) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "invalid JSON body" }, { status: 400 });
  }

  // The [turnId] dynamic segment is the capability the browser learned from
  // the turn_start SSE event (D-05). Forward the body verbatim server-side.
  let upstream: Response;
  try {
    upstream = await fetch(
      `${FASTAPI_URL}/api/v1/turns/${params.turnId}/control`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    );
  } catch {
    return Response.json(
      { error: "API unavailable — is uvicorn running?" },
      { status: 503 },
    );
  }

  // Return the upstream status (202 accepted / 404 unknown-or-finished /
  // 422 bad kind / 413 oversize) VERBATIM — the proxy never hardcodes 200.
  const text = await upstream.text().catch(() => "");
  return new Response(text, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
