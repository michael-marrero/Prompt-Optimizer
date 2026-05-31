// Plan 04-05 Wave 4 — StreamErrorBanner.
//
// UI-SPEC §12 — the inline red banner rendered inside an assistant
// ChatBubble when a stream_error AI SDK chunk lands (Plan 02's translator
// maps Phase 2 StreamError chunks to AI SDK v6 {type:"error", code, retriable}
// chunks).
//
// Catalog: the code → friendly-message map covers all 11 D-06/D-05 codes
// from apps/api/backends/chunks.py StreamError.code (cost_cap_exceeded,
// step_cap_exceeded, cancelled, rate_limited, auth_failed,
// provider_unavailable, timeout, validation_error, internal_error, plus the
// two Phase 9 D-05 kill-switch codes — see the last two map entries below).
// Unknown codes (defense-in-depth — Zod schema should already reject)
// fall back to a generic "Something went wrong" message.
//
// Accessibility:
//   - role="alert" — screen readers announce when this lands mid-stream
//   - retry button visible label "Try again" + aria-label "Retry the
//     failed turn" (UI-SPEC §17)
//
// Cross-refs:
//   - apps/api/backends/chunks.py:127-137 (the 9-value closed vocabulary)
//   - apps/web/lib/chunk-schemas.ts (StreamErrorCodeSchema)
//   - 04-UI-SPEC.md §12 (banner shape + ARIA + retry button rules)
//   - 04-CONTEXT.md D-06 (closed-vocabulary error codes)
"use client";

import { AlertCircle } from "lucide-react";

// UI-SPEC §12.2 — code → human-readable copy. Update this map together with
// apps/api/backends/chunks.py when adding new codes. The 11 baseline codes
// are the Phase-2 D-06 closed vocabulary plus the two Phase-9 D-05 kill-switch
// codes (the last two map entries — Plan 02 server reasons).
const FRIENDLY_MESSAGES: Record<string, string> = {
  cost_cap_exceeded:
    "Cost cap of $0.50 reached. Try a shorter prompt or raise the cap in settings.",
  step_cap_exceeded:
    "The model hit its step limit. Try a more focused prompt.",
  cancelled: "Generation cancelled.",
  rate_limited:
    "OpenRouter is rate-limiting requests. Wait a moment and try again.",
  auth_failed:
    "OpenRouter rejected the key. Update it in settings and try again.",
  provider_unavailable:
    "The upstream model is temporarily unavailable. Try again in a moment.",
  timeout: "The request timed out. The model may be slow — try again.",
  validation_error:
    "That request couldn't be sent. Check your input and try again.",
  internal_error:
    "Something went wrong inside Prompt-Optimizer. Check the API logs and retry.",
  // Phase 9 D-05 kill-switch codes — the turn was stopped by a hard limit
  // (Plan 02 turn.py). Both are non-retriable: retrying hits the same limit.
  wall_clock_exceeded:
    "Stopped — this turn hit its time limit.",
  budget_exceeded:
    "Stopped — this turn reached its budget limit.",
};

export interface StreamErrorBannerProps {
  /** The closed-vocab D-06 error code. */
  code: string;
  /** The upstream error message, ALREADY redacted server-side by SECURE-07
   *  (Plans 02/03 route it through logging_filter._redact_text before it
   *  reaches the SSE chunk). When truthy it is surfaced verbatim inside a
   *  collapsible "Details" disclosure (Phase 9 D-07 opt-in) for power users;
   *  the friendly text still wins as the primary user-facing copy. The banner
   *  renders it as-is and does NOT reconstruct unredacted text (T-09-02). */
  message: string;
  /** Whether retry is offered. Only retriable codes show "Try again". */
  retriable: boolean;
  /** Called when the user clicks "Try again". Page wires this to the
   *  assistant-ui reload action. */
  onRetry: () => void;
}

export function StreamErrorBanner({
  code,
  message,
  retriable,
  onRetry,
}: StreamErrorBannerProps): React.JSX.Element {
  const friendly =
    FRIENDLY_MESSAGES[code] ?? "Something went wrong — try again.";

  return (
    <div
      role="alert"
      className="mt-3 first:mt-0 flex items-start gap-3 rounded-md border border-[var(--danger)]/40 bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]"
    >
      <AlertCircle className="h-4 w-4 text-[var(--danger)] flex-shrink-0 mt-0.5" />
      <div className="flex-1 leading-relaxed">
        {friendly}{" "}
        <code className="font-mono text-xs">({code})</code>
        {retriable && (
          <button
            type="button"
            onClick={onRetry}
            aria-label="Retry the failed turn"
            className="mt-2 inline-flex h-8 items-center rounded-md border border-[var(--danger)]/40 bg-white px-3 text-xs font-semibold text-[var(--danger)] hover:bg-[var(--danger)]/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--danger)] focus-visible:ring-offset-2"
          >
            Try again
          </button>
        )}
        {/* D-07 opt-in: a collapsible disclosure surfacing the (already
            server-redacted — T-09-02) technical message for power users.
            Rendered ONLY when a message is present. */}
        {message && (
          <details className="mt-2 text-xs">
            <summary className="cursor-pointer select-none">Details</summary>
            <code className="mt-1 block whitespace-pre-wrap break-words font-mono">
              {message}
            </code>
          </details>
        )}
      </div>
    </div>
  );
}
