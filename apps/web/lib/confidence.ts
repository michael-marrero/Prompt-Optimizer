// Story 5.2 — low-confidence trigger for the route-override nudge.
//
// The route's `confidence` (min of the per-stage calibrated max-probabilities;
// src/routing/schema.py) rides the SSE `routing_decision` event and is persisted
// (schema_v3) so live + restored renders agree (AD-7).
//
// ponytail: one constant + one predicate — the single place to tune the trigger.
// The 0.5 default is PROVISIONAL (Story 5.1 spike decision): a route the model is
// ~a coin-flip or less sure of among alternatives. Set the real value from Epic 2's
// calibration curve (where the chosen route's calibrated win-rate drops below ~0.5)
// rather than hand-tuning here.
export const LOW_CONFIDENCE_THRESHOLD = 0.5;

/** True when a route's calibrated confidence is low enough to nudge an override.
 *  Non-finite / missing confidence is treated as high (never nudges). */
export function isLowConfidence(
  confidence: number | null | undefined,
): boolean {
  return typeof confidence === "number" && Number.isFinite(confidence)
    ? confidence < LOW_CONFIDENCE_THRESHOLD
    : false;
}
