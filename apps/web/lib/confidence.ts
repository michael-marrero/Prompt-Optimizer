// Story 6.2 — low-confidence trigger for the route-override nudge.
//
// The nudge fires on the routing brain's OWN calibrated uncertainty verdict:
// `signals.low_confidence`, set by decide() (src/routing/decide.py) exactly when a
// driving stage's *calibrated* probability missed its per-stage tau
// (src/routing/config.py: task 0.35 / agentic 0.55 / model-router 0.20, Epic 2) and
// the route fell back to openrouter/auto.
//
// Why not the numeric `confidence`? That field is `min(task, agentic, router)` of
// three *individually* calibrated probabilities — but the min() itself is NOT
// calibrated as a route-quality score. A 16-class model-router top prob rarely tops
// ~0.40, so the composite sits ~0.30 even on a CORRECT route, and the old
// `confidence < 0.5` gate (PROVISIONAL, Story 5.1) fired on ~every turn. The brain's
// tau gates already encode "is this stage confident enough" against the calibrated
// distribution, so their verdict is the honest, data-free trigger. `confidence` is
// still emitted for telemetry (schema unchanged) but no longer gates the nudge.
//
// The boolean rides the SSE `routing_decision` event inside the free `signals` dict
// (no new SSE member — AD-4) and is persisted (schema_v3 signals JSON), so live +
// restored renders agree (AD-7). A true per-route win-rate calibrator (the original
// aspiration) is deferred until Epic 3 has enough rated turns — see deferred-work.md.
//
// ponytail: one predicate reading the verdict the brain already computed.

type SignalsLike = Record<string, unknown> | null | undefined;

/** True when the routing brain flagged this route as a low-confidence fallback,
 *  i.e. `signals.low_confidence === true`. Missing/legacy signals (no boolean) →
 *  false, so old rows and non-fallback routes never nudge. */
export function isLowConfidence(signals: SignalsLike): boolean {
  return signals?.low_confidence === true;
}
