// POST /api/threads/[id]/rename — auto-rename proxy (UI-14, D-08/D-09).
//
// Fires on the first user send (in parallel with the turn stream) so the
// sidebar title updates within ~1s. Forwards `{first_user_message}` to
// FastAPI `POST /api/v1/threads/{id}/rename` (cheap-model bypass:
// openai/gpt-4o-mini, $0.01 cap, brain-bypassed) and returns `{title}` on
// 200. Status 400 (no OpenRouter key) / 404 (unknown thread) / 413 (too
// long) are forwarded VERBATIM so the client can run the D-09
// truncate-first-message fallback (firstMessage.slice(0, 40)).
//
// The browser never speaks to FastAPI directly (UI-17) — this proxy is the
// only path. Next 16 — `params` is a Promise; await before destructuring.
//
// Cross-refs:
//   - 05-PATTERNS.md apps/web/app/api/threads/[id]/rename/route.ts (NEW)
//   - 05-CONTEXT.md D-08 (fire on first send, parallel), D-09 (truncate fallback)
//   - apps/api/routes/rename.py lines 182-301 (upstream: {title} / 400 / 404 / 413)
//   - apps/web/app/api/threads/[id]/route.ts (await params Next-16 pattern)

export const runtime = "nodejs"; // Pitfall 1 — Node runtime only
export const dynamic = "force-dynamic"; // mutation endpoint; never cache

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";

export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  // Next 16 — `params` is a Promise; await BEFORE destructuring.
  const { id } = await params;

  // The upstream RenameRequest accepts an empty string (valid), so a
  // malformed/absent body degrades to an empty first_user_message rather
  // than a 400 — the client's D-09 fallback still has the raw text.
  let body: { first_user_message?: unknown };
  try {
    body = await req.json();
  } catch {
    body = {};
  }
  const firstUserMessage =
    typeof body.first_user_message === "string" ? body.first_user_message : "";

  let upstream: Response;
  try {
    upstream = await fetch(
      `${FASTAPI_URL}/api/v1/threads/${encodeURIComponent(id)}/rename`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ first_user_message: firstUserMessage }),
      },
    );
  } catch {
    return Response.json(
      { error: "API unavailable — is uvicorn running?" },
      { status: 503 },
    );
  }

  if (!upstream.ok) {
    // Forward 400/404/413 status + body verbatim so the client runs the
    // D-09 truncation fallback on a rename failure (e.g. no OpenRouter key).
    const text = await upstream.text().catch(() => "");
    return new Response(text, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  // Happy path — upstream returns {title}. Forward verbatim.
  return Response.json(await upstream.json());
}
