// Wave-0 PLACEHOLDER for the /api/health proxy. Plan 04-03 (Wave 2) replaces
// this file with the real passthrough to FastAPI `GET /api/v1/healthz`.
//
// Why ship a placeholder NOW: Next 16's route discovery wires up the
// `app/api/` tree at build time. Shipping at least one route handler in
// Wave 0 establishes the directory + the PATTERNS Pattern C declarations
// (runtime='nodejs' + dynamic='force-dynamic') from the very first route,
// satisfying threat T-04-06 (the SSE proxy pattern is consistent across
// every handler from day one — RESEARCH Critical Finding #3).
//
// The returned payload mirrors the shape Plan 04-07's first-run modal
// expects: `body.adapters.openrouter.status` ∈ {ready, missing_key,
// opt_out, error}. Wave 0 returns `missing_key` so the modal-trigger logic
// has a known, repeatable path to exercise during early-wave dev.

export const runtime = "nodejs"; // Pitfall 1 — never Edge runtime
export const dynamic = "force-dynamic"; // never cache; this is a status probe

export async function GET() {
  return Response.json({
    ok: true,
    adapters: {
      openrouter: { status: "missing_key" },
    },
  });
}
