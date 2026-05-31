// Phase 5 Plan 06 Wave 3 — FeedbackButtons (UI-15, UI-SPEC §13).
//
// Thumbs-up / thumbs-down on every assistant message, mounted in the action
// row next to Copy + Regenerate. Reads the routing decision off the message's
// content array (the SAME data-part pattern RoutingChip uses,
// RoutingChip.tsx:82-95), and POSTs the D-12 feedback row to the same-origin
// /api/feedback proxy (UI-17 — the browser never speaks to FastAPI directly;
// the proxy forwards to POST /api/v1/feedback).
//
// DEBT-04 (Phase 9): the `message_id` join key is the SERVER-assigned
// assistant message id — read from the live Done chunk's assistant_message_id
// data part, or (on a reloaded turn) from message.id which reconstructUIMessages
// already seeds from the DB row id. The assistant-ui RUNTIME message.id is
// never used as the join key for a live turn (it would not join back to the
// persisted message row — Phase 5 WR-01).
//
// D-11 (AUTHORITATIVE over UI-SPEC §13): BOTH thumbs log. UI-SPEC §13 reserved
// up-logging for v2 and called up "silent", but CONTEXT D-11 is a locked user
// decision that wins — positive examples are as valuable as negative for later
// routing evaluation. Both buttons POST with the matching `sentiment` (up/down).
// This resolution is surfaced in the plan SUMMARY (per the plan output spec).
//
// Toasts (§17 + D-11):
//   - down → toast.success("Thanks — logged as a wrong route.")
//   - up   → toast.success("Thanks — noted as a good route.")   [the chosen
//            equivalent positive acknowledgment, D-11 + UI-SPEC §17 tone]
//   - any failure → toast.error("Couldn't log feedback — is the local API running?")
//
// Append-only + fire-and-forget (D-13): every click appends a row; the network
// call is not awaited by the UI render path. The button UI reflects the user's
// latest choice via a subtle filled state.
//
// D-12 row schema:
//   {sentiment, timestamp, thread_id, message_id, prompt, decision:{backend,
//    model_or_agent, rationale, confidence, signals}}
//
// Cross-refs:
//   - apps/web/components/RoutingChip.tsx (data-part read)
//   - apps/web/components/ChatBubble.tsx:76-77 (actionButtonClass)
//   - apps/web/app/api/feedback/route.ts (the 05-03 Next proxy → FastAPI)
//   - apps/web/lib/types.ts (RoutingDecision)
//   - 05-CONTEXT.md D-11..D-14 + 05-UI-SPEC.md §13 + §17
"use client";

import { useState } from "react";
import type React from "react";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import { toast } from "sonner";
import { useMessage } from "@assistant-ui/react";
import { cn } from "@/lib/cn";
import type { RoutingDecision } from "@/lib/types";

type Sentiment = "up" | "down";

type PartLike = { readonly type: string };
type DataPart = {
  readonly type: "data";
  readonly name: string;
  readonly data: unknown;
};
type TextPart = { readonly type: "text"; readonly text: string };
type MessageStateShape = {
  readonly id?: string;
  readonly content?: ReadonlyArray<PartLike>;
};

function isRoutingPart(
  p: PartLike,
): p is DataPart & { readonly name: "routing"; readonly data: RoutingDecision } {
  return p.type === "data" && (p as { name?: string }).name === "routing";
}
// DEBT-04: the server-assigned assistant message id arrives as a data part
// named "assistant_message_id" (sse-translate.ts emits `data-assistant_message_id`
// on the live Done; `convertParts` strips the `data-` prefix to this `name`).
function isAssistantIdPart(
  p: PartLike,
): p is DataPart & { readonly name: "assistant_message_id"; readonly data: string } {
  return (
    p.type === "data" &&
    (p as { name?: string }).name === "assistant_message_id" &&
    typeof (p as { data?: unknown }).data === "string"
  );
}
function isTextPart(p: PartLike): p is TextPart {
  return p.type === "text";
}

// Action-row button class — mirrors ChatBubble.tsx:76-77 exactly (h-7 w-7).
const actionButtonClass =
  "h-7 w-7 rounded-md hover:bg-[var(--surface-2)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2 inline-flex items-center justify-center text-[var(--ink-2)]";

export interface FeedbackButtonsProps {
  /** The active thread id, threaded through from the page (the D-12 row's
   *  thread_id). Optional — falls back to "" when not yet resolved. */
  threadId?: string | null;
  /** The original user prompt for this turn (D-12 row's `prompt`). The page
   *  supplies it from the preceding user message; falls back to "". */
  prompt?: string;
}

export function FeedbackButtons({
  threadId,
  prompt,
}: FeedbackButtonsProps = {}): React.JSX.Element {
  const message = useMessage({ optional: true }) as MessageStateShape | null;
  const content = message?.content ?? [];

  // DEBT-04 — the feedback join key MUST be the SERVER-assigned assistant
  // message id, never the assistant-ui runtime `message.id`.
  //   - LIVE turn: the server id rides the Done chunk as a data part
  //     (assistant_message_id); read it off the content.
  //   - RELOADED turn: reconstructUIMessages seeds `message.id` from the DB
  //     row id (already the server id), so the fallback stays correct.
  // The runtime id is never used as the join key (it would break the
  // offline-analysis join for live turns — Phase 5 WR-01 / T-09-09).
  const serverIdPart = content.find(isAssistantIdPart);
  const messageId = serverIdPart?.data ?? message?.id ?? "";

  const routingPart = content.find(isRoutingPart);
  const decision = routingPart?.data ?? null;
  // Fall back to the assistant body text if no explicit prompt is wired (the
  // D-12 `prompt` field — the page wires the real user prompt).
  const fallbackPrompt = content
    .filter(isTextPart)
    .map((p) => p.text)
    .join("");

  const [selected, setSelected] = useState<Sentiment | null>(null);

  function sendFeedback(sentiment: Sentiment): void {
    setSelected(sentiment);

    const row = {
      sentiment,
      timestamp: new Date().toISOString(),
      thread_id: threadId ?? "",
      message_id: messageId,
      prompt: prompt ?? fallbackPrompt,
      decision: decision ?? {
        backend: "openrouter",
        model_or_agent: "",
        rationale: "",
        confidence: 0,
        signals: {},
      },
    };

    // Fire-and-forget (D-13). The browser never speaks to FastAPI directly —
    // /api/feedback is the same-origin Next proxy (UI-17).
    void fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(row),
    })
      .then((response) => {
        if (!response.ok) throw new Error(`feedback failed (${response.status})`);
        // D-11 — both sentiments log; pick the matching toast.
        if (sentiment === "down") {
          toast.success("Thanks — logged as a wrong route.");
        } else {
          toast.success("Thanks — noted as a good route.");
        }
      })
      .catch(() => {
        toast.error("Couldn't log feedback — is the local API running?");
      });
  }

  return (
    <div className="inline-flex items-center gap-1">
      <button
        type="button"
        aria-label="Mark this route as good"
        aria-pressed={selected === "up"}
        onClick={() => sendFeedback("up")}
        className={cn(actionButtonClass, selected === "up" && "text-[var(--ink)]")}
      >
        <ThumbsUp className="h-4 w-4" />
      </button>
      <button
        type="button"
        aria-label="Mark this route as wrong"
        aria-pressed={selected === "down"}
        onClick={() => sendFeedback("down")}
        className={cn(actionButtonClass, selected === "down" && "text-[var(--ink)]")}
      >
        <ThumbsDown className="h-4 w-4" />
      </button>
    </div>
  );
}
