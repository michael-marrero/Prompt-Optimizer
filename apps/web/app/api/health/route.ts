// Pure passthrough proxy for `GET /api/v1/healthz`. The Wave-0 placeholder
// hard-coded `{adapters: {openrouter: {status: "missing_key"}}}` so the
// Plan 07 first-run modal trigger logic had a deterministic dev path;
// Plan 03 (Wave 2) overwrites that with this real passthrough so the
// modal trigger now reflects actual upstream adapter readiness state.
//
// No transformation — the UI consumer (apps/web/lib/api-client.ts:getHealth)
// reads `body.adapters.openrouter.status` directly. The rich Phase 3 D-18
// shape (`status`, `artifacts_loaded`, `db_ok`, `schema_version`,
// `adapters.{openrouter,claude_code,computer_use}.status`, `version`) flows
// through verbatim so future UI surfaces (Phase 5 status-dot strip) get
// the full payload without a second round-trip.
//
// Cross-refs:
//   - 04-CONTEXT.md D-16 (two independent missing-key triggers — this is the boot one)
//   - 04-CONTEXT.md D-19 (post-entry unblock — UI re-fetches /api/health after key submit)
//   - 04-PATTERNS.md apps/web/app/api/health/route.ts section (passthrough shape)
//   - apps/api/routes/health.py lines 133-178 (upstream we mirror verbatim)

// Pitfall 1 — Edge runtime forbids Node-specific fetch features and would
// break the consistency of every other route in this directory; PATTERNS
// Pattern C: every apps/web/app/api/**/route.ts declares Node runtime.
export const runtime = "nodejs";

// Health is a status probe; cached responses would lie about adapter
// readiness immediately after a settings PATCH (D-19 unblock path).
export const dynamic = "force-dynamic";

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";

export async function GET() {
  let upstream: Response;
  try {
    upstream = await fetch(`${FASTAPI_URL}/api/v1/healthz`);
  } catch {
    // ECONNREFUSED — uvicorn not running. Mirror chat route's banner text
    // so the UI's network-down toast is consistent across endpoints.
    return Response.json(
      { error: "API unavailable — is uvicorn running?" },
      { status: 503 },
    );
  }

  if (!upstream.ok) {
    return Response.json(
      { error: "upstream unhealthy" },
      { status: upstream.status },
    );
  }

  // Passthrough — preserves the full D-18 shape so the UI can read
  // adapters.openrouter.status without any defensive shape-checking.
  return Response.json(await upstream.json());
}
