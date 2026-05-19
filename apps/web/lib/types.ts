// TypeScript port of `src/routing/schema.py` — types only, no runtime values.
// Plan 04-02 (Wave 1): mirrors the Phase 1 `RoutingDecision` dataclass field-for-field
// so the Routing Chip (Plan 04-05) and any other consumer of the `data-routing` UI
// chunk reads {backend, model_or_agent, rationale, confidence, signals} directly.
//
// Cross-refs:
//   - src/routing/schema.py (the canonical Python contract)
//   - apps/api/backends/chunks.py (the discriminated union of stream chunks)
//   - apps/web/lib/chunk-schemas.ts (the runtime Zod equivalents)
//   - 04-CONTEXT.md D-15 (the structured 5-key routing_decision payload)
//   - 04-PATTERNS.md Pattern A (closed-vocabulary discriminated unions)

// Backend sentinel — Plan 04 only exercises "openrouter"; "claude_code" and
// "computer_use" exist for Phase 5 forward-compatibility (the chip already
// color-codes all three; UI-SPEC §4).
export type Backend = "openrouter" | "claude_code" | "computer_use";

// Telemetry sub-dict — `RoutingDecision.signals` is opaque-by-design (Phase 1 D-03):
// task_type / agentic_intent / rule_fired plus arbitrary stage telemetry. Consumers
// SHOULD NOT structurally narrow this; treat as a debug payload only.
export type RoutingSignals = Record<string, unknown>;

// The structured 5-key record the `data-routing` UI chunk carries (Plan 04 D-15
// amendment). Mirrors `src/routing/schema.py:RoutingDecision` 1:1 — every field
// here exists on the Python dataclass with the same Python type.
export interface RoutingDecision {
  backend: Backend;
  model_or_agent: string;
  rationale: string;
  confidence: number;
  signals: RoutingSignals;
}

// `apps/api/routes/health.py` returns one of these four strings per adapter
// (Phase 3 D-18). Plan 04 D-16 reads `adapters.openrouter.status` and triggers
// the first-run modal when it is "missing_key".
export type AdapterStatus = "ready" | "missing_key" | "opt_out" | "error";

// The flattened terminal-chunk metrics carried by the `data-metrics` UI chunk
// (Plan 04 D-13). Every field is nullable because Phase 2 Done allows
// `int | None = None` on every field (an auth-failure path can land Done with
// no usage information at all).
export interface MetricsPayload {
  cost_usd: number | null;
  latency_ms: number | null;
  tokens_in: number | null;
  tokens_out: number | null;
}
