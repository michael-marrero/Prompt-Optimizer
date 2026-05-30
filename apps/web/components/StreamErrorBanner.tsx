// Plan 04-05 Wave 4 — StreamErrorBanner.
//
// UI-SPEC §12 — the inline red banner rendered inside an assistant
// ChatBubble when a stream_error AI SDK chunk lands (Plan 02's translator
// maps Phase 2 StreamError chunks to AI SDK v6 {type:"error", code, retriable}
// chunks).
//
// Catalog: the code → friendly-message map covers all 9 D-06 codes from
// apps/api/backends/chunks.py lines 127-137 (cost_cap_exceeded,
// step_cap_exceeded, cancelled, rate_limited, auth_failed,
// provider_unavailable, timeout, validation_error, internal_error).
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
// apps/api/backends/chunks.py when adding new codes. The 9 baseline codes
// are the Phase-2 D-06 closed vocabulary.
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
};

export interface StreamErrorBannerProps {
  /** The closed-vocab D-06 error code. */
  code: string;
  /** The upstream error message. Currently not surfaced in the banner
   *  body (the friendly text wins for the user-facing copy) but kept on
   *  the props interface so Plan 06 can opt into "show technical details"
   *  if requested. */
  message: string;
  /** Whether retry is offered. Only retriable codes show "Try again". */
  retriable: boolean;
  /** Called when the user clicks "Try again". Page wires this to the
   *  assistant-ui reload action. */
  onRetry: () => void;
}

export function StreamErrorBanner({
  code,
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
      </div>
    </div>
  );
}
