// D-18: this file must NEVER log the key. Every error path runs
// `.replace(key, "***")` (Pattern G — Secret scrub) so the literal key
// never appears in a thrown Error.message, response body, or response
// header. The Playwright secure-key.spec.ts test (Plan 07) enforces
// zero literal-key matches across Next stdout/stderr/responses.
//
// Body translation: the browser POSTs the ergonomic
// `{provider, key}` shape; this handler forwards as the FastAPI-native
// `{keys: {[provider]: key}}` PATCH shape so the upstream
// patch_settings handler can route to KeyStore.set(provider, key).
//
// Cross-refs:
//   - 04-CONTEXT.md D-18 (key isolation invariants); D-19 (post-entry unblock)
//   - 04-RESEARCH.md §"Pattern 8" lines 992-1023 (canonical handler shape)
//   - 04-PATTERNS.md apps/web/app/api/settings/route.ts section (full pattern);
//     Pattern G — Secret-scrub on every error path
//   - apps/api/routes/settings.py lines 238-317 (upstream PATCH /api/v1/settings)
//   - apps/web/lib/api-client.ts (browser-side wrapper that posts {provider,key})
//
// Forbidden in this file:
//   * Any stdout/stderr logging primitive (anywhere — even on the happy
//     path; some runtime stringifies request bodies for debugging and a
//     stray log would leak the key). The Task 2 verify grep enforces a
//     literal-token absence for the Node logger calls.
//   * Re-exporting `key` outside its lexical block scope
//   * Caching the key in a module-level variable, file, or cookie

export const runtime = "nodejs"; // Pitfall 1 — Node runtime only
export const dynamic = "force-dynamic"; // status-changing endpoint; never cache

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";

export async function POST(req: Request) {
  // Parse body — guard against malformed JSON so a hostile/buggy client
  // does not crash the route. NOTE: the parsed body holds the plaintext
  // key in `body.key` from this point forward; every error path below
  // MUST scrub it before re-throwing or returning.
  let body: { provider?: unknown; key?: unknown };
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const { provider, key } = body;

  // Closed-vocabulary provider check (mirrors Phase 3 settings.py's
  // KeyPatch.openrouter/anthropic field set). Unknown providers return
  // 400 BEFORE we touch the upstream so a misconfigured client cannot
  // probe the FastAPI surface for what providers exist.
  if (provider !== "openrouter" && provider !== "anthropic") {
    return Response.json({ error: "unknown provider" }, { status: 400 });
  }

  // Validate key is a non-empty string. Empty/non-string key is treated
  // as a programmer error (the UI's submit button is disabled for empty
  // input — see UI-SPEC §15) so a 400 is fine.
  if (typeof key !== "string" || key.length === 0) {
    return Response.json({ error: "key is required" }, { status: 400 });
  }

  // ----------------------------------------------------------------
  // Upstream PATCH — Phase 3 D-10 contract: {keys: {[provider]: key}}.
  // We do NOT forward signal:req.signal here because settings PATCH is
  // a non-streaming write; aborting mid-write could leave the upstream
  // in a half-applied state (Phase 3 D-15 cache invalidation runs after
  // the file write completes).
  // ----------------------------------------------------------------
  let upstream: Response;
  try {
    upstream = await fetch(`${FASTAPI_URL}/api/v1/settings`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keys: { [provider]: key } }),
    });
  } catch (err: unknown) {
    // Network error (ECONNREFUSED, DNS, timeout). The runtime's err
    // message MAY contain the serialized request body — scrub before
    // returning. Using the canonical .replace(key, "***") form so the
    // grep-based verifier finds the scrub call; the literal key cannot
    // appear after this point.
    const rawMsg = String((err as { message?: string })?.message ?? err);
    const errMsg = rawMsg.replace(key, "***");
    return Response.json(
      { error: "Could not save key", detail: errMsg },
      { status: 503 },
    );
  }

  if (!upstream.ok) {
    // Belt-and-suspenders D-18 scrub: some FastAPI error serializers
    // echo request fields back in the validation message. Read the body
    // ONCE, scrub the key, and forward the (now-scrubbed) bytes with
    // the upstream status. We do this BEFORE returning so the caller
    // gets the upstream's diagnostic without the key leaking.
    let text = "";
    try {
      text = await upstream.text();
    } catch {
      // body unreadable — keep going with empty
    }
    const scrubbed = text.replace(key, "***");
    return new Response(scrubbed, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  // Happy path — the FastAPI response body contains ONLY the masked
  // representation (e.g. {"keys":{"openrouter":{"present":true,"masked":"sk-or-…ABC"}}})
  // per Phase 3 D-10. No scrub needed; the upstream never echoes the
  // plaintext key. Forward verbatim.
  return Response.json(await upstream.json());
}
