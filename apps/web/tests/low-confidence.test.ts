// Story 6.2 — low-confidence nudge trigger + restore-parity. The nudge now keys
// off the routing brain's calibrated fallback verdict `signals.low_confidence`
// (not a mis-scaled numeric `confidence` vs 0.5, which fired on ~every turn).
// Two non-trivial paths: the predicate, and that the persisted verdict survives
// reconstruction (AD-7 — restored render must match live).
import { describe, it, expect } from "vitest";
import { isLowConfidence } from "@/lib/confidence";
import { reconstructUIMessages } from "@/lib/reconstruct-messages";
import { MessagesResponseSchema } from "@/lib/chunk-schemas";

describe("isLowConfidence — override nudge trigger", () => {
  it("fires when the brain flagged a low-confidence fallback", () => {
    expect(isLowConfidence({ low_confidence: true })).toBe(true);
  });
  it("does NOT fire on a confident route", () => {
    expect(isLowConfidence({ low_confidence: false })).toBe(false);
    // A confident route can still have a low numeric composite — must not nudge.
    expect(isLowConfidence({ low_confidence: false, task_confidence: 0.3 })).toBe(false);
  });
  it("treats missing / malformed signals as high (never nudges)", () => {
    expect(isLowConfidence(null)).toBe(false);
    expect(isLowConfidence(undefined)).toBe(false);
    expect(isLowConfidence({})).toBe(false); // legacy row: no verdict → no nudge
    expect(isLowConfidence({ low_confidence: "true" })).toBe(false); // strict === true
  });
});

// The routing part the bubble/nudge reads: {type:"data-routing", data:{signals,...}}.
function routingSignalsOf(msg: unknown): Record<string, unknown> | undefined {
  const parts = (msg as { parts?: Array<{ type: string; data?: { signals?: Record<string, unknown> } }> })
    .parts ?? [];
  return parts.find((p) => p.type === "data-routing")?.data?.signals;
}

describe("reconstructUIMessages — low-confidence restore parity (AD-7)", () => {
  const base = {
    id: "m1",
    role: "assistant" as const,
    text: "answer",
    content_blocks: [],
    backend_used: "openrouter",
    model_used: "openai/gpt-5",
    cost_usd: null,
    latency_ms: null,
    tokens_in: null,
    tokens_out: null,
    status: "complete" as const,
  };

  it("restores the PERSISTED low-confidence verdict so the nudge renders like live", () => {
    const [msg] = reconstructUIMessages([
      { ...base, routing: { rationale: "close call - low confidence — fallback", override: false, confidence: 0.31, low_confidence: true } },
    ]);
    const signals = routingSignalsOf(msg);
    expect(signals?.low_confidence).toBe(true);
    expect(isLowConfidence(signals)).toBe(true); // low → nudge shows on reload too
  });

  it("a confident restored route does NOT nudge (even with a low numeric confidence)", () => {
    const [msg] = reconstructUIMessages([
      { ...base, routing: { rationale: "task=knowledge ...", override: false, confidence: 0.31, low_confidence: false } },
    ]);
    const signals = routingSignalsOf(msg);
    expect(signals?.low_confidence).toBeUndefined(); // only truthy verdicts seeded
    expect(isLowConfidence(signals)).toBe(false);
  });

  it("legacy rows with no persisted verdict fall back to no-nudge", () => {
    const [msg] = reconstructUIMessages([
      { ...base, routing: { rationale: "old row", override: false } }, // pre-6.2
    ]);
    const signals = routingSignalsOf(msg);
    expect(isLowConfidence(signals)).toBe(false);
  });

  // Code-review (Acceptance Auditor, HIGH): the REAL reload path parses the
  // server JSON through MessagesResponseSchema.safeParse BEFORE reconstruct
  // (ChatSurface.tsx). Zod strips unknown keys, so without low_confidence in
  // MessageRoutingSchema the persisted verdict is dropped and the nudge silently
  // vanishes on reload. This test exercises that boundary — it would have caught it.
  it("low_confidence survives the MessagesResponseSchema parse boundary (AD-7)", () => {
    const serverJson = [
      {
        ...base,
        routing: {
          rationale: "close call - low confidence — fallback",
          override: false,
          confidence: 0.31,
          low_confidence: true,
        },
      },
    ];
    const parsed = MessagesResponseSchema.safeParse(serverJson);
    expect(parsed.success).toBe(true);
    // The field must NOT be stripped by the schema.
    expect(parsed.data?.[0]?.routing?.low_confidence).toBe(true);
    // …and it must drive the nudge after reconstruction.
    const [msg] = reconstructUIMessages(parsed.data!);
    expect(isLowConfidence(routingSignalsOf(msg))).toBe(true);
  });
});
