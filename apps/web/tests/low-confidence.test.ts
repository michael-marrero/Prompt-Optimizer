// Story 5.2 — low-confidence nudge trigger + restore-parity of the confidence
// value. Two non-trivial paths: the threshold predicate, and that the persisted
// confidence survives reconstruction (AD-7 — restored render must match live).
import { describe, it, expect } from "vitest";
import { isLowConfidence, LOW_CONFIDENCE_THRESHOLD } from "@/lib/confidence";
import { reconstructUIMessages } from "@/lib/reconstruct-messages";

describe("isLowConfidence — override nudge trigger", () => {
  it("fires strictly below the threshold", () => {
    expect(isLowConfidence(LOW_CONFIDENCE_THRESHOLD - 0.01)).toBe(true);
    expect(isLowConfidence(0)).toBe(true);
  });
  it("does NOT fire at or above the threshold", () => {
    expect(isLowConfidence(LOW_CONFIDENCE_THRESHOLD)).toBe(false);
    expect(isLowConfidence(0.99)).toBe(false);
  });
  it("treats missing / non-finite confidence as high (never nudges)", () => {
    expect(isLowConfidence(null)).toBe(false);
    expect(isLowConfidence(undefined)).toBe(false);
    expect(isLowConfidence(Number.NaN)).toBe(false);
  });
});

// The routing part the bubble/nudge reads: {type:"data-routing", data:{confidence,...}}.
function routingConfidenceOf(msg: unknown): number | undefined {
  const parts = (msg as { parts?: Array<{ type: string; data?: { confidence?: number } }> })
    .parts ?? [];
  return parts.find((p) => p.type === "data-routing")?.data?.confidence;
}

describe("reconstructUIMessages — confidence restore parity (AD-7)", () => {
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

  it("restores the PERSISTED low confidence so the nudge renders like live", () => {
    const [msg] = reconstructUIMessages([
      { ...base, routing: { rationale: "close call", override: false, confidence: 0.31 } },
    ]);
    const c = routingConfidenceOf(msg);
    expect(c).toBe(0.31);
    expect(isLowConfidence(c)).toBe(true); // low → nudge shows on reload too
  });

  it("legacy rows with no persisted confidence fall back to a safe high (no nudge)", () => {
    const [msg] = reconstructUIMessages([
      { ...base, routing: { rationale: "old row", override: false } }, // pre-schema_v3
    ]);
    const c = routingConfidenceOf(msg);
    expect(c).toBe(1);
    expect(isLowConfidence(c)).toBe(false);
  });
});
