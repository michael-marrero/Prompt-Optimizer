// Plan 04-05 Wave 4 — ChatBubble.
//
// UI-SPEC §8 — the visible shell that wraps every chat message. Assistant
// variant has a hover-revealed action row (Copy + Regenerate per D-14);
// user variant has no action row. Both share the same container shape.
//
// Slot contract: the `children` prop is the message body. Plan 05 mounts
// a plain pre-formatted text node here (callers pass {<MessagePrimitive.Content />}
// or any other React node). Plan 06 (markdown wave) replaces the VALUE of
// the children slot — NOT a marker comment — with the memoized
// MarkdownRenderer. The ChatBubble's prop interface is the seam Plan 06
// extends with `isStreamingComplete` + `messageId`.
//
// Action row (UI-SPEC §8.3):
//   - Copy: copies the RAW markdown source from `rawMarkdown` to the
//     clipboard via navigator.clipboard.writeText, then fires a sonner
//     success toast "Copied to clipboard". Plan 06's markdown renderer
//     never wraps this — copy MUST be source-text, not rendered HTML
//     (UI-SPEC §17 + D-14).
//   - Regenerate: invokes the `onRegenerate` callback prop. The PAGE
//     (apps/web/app/page.tsx Task 3) wires this to assistant-ui's
//     `useMessageRuntime().reload()` so a fresh POST /api/chat is issued
//     and a new assistant turn lands. Blocker 3 fix: NO TODO marker
//     remains; the live wiring lives in page.tsx.
//
// Cross-refs:
//   - 04-UI-SPEC.md §8 (container + body + action row)
//   - 04-CONTEXT.md D-14 (Copy = raw source, Regenerate = new turn)
//   - 04-PATTERNS.md Pattern D (use client) + Pattern E (cn helper)
"use client";

import type { ReactNode } from "react";
import { Copy, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/cn";

export interface ChatBubbleProps {
  /** "assistant" gets the action row + slate-50 background;
   *  "user" gets ml-auto + slate-100, no action row. */
  role: "assistant" | "user";
  /** The raw markdown source text. Copy writes this to the clipboard
   *  (NOT the rendered HTML). The user variant doesn't render the
   *  action row so this prop is functionally only consumed by the
   *  assistant variant, but the type is the same for symmetry. */
  rawMarkdown: string;
  /** Invoked when Regenerate is clicked (assistant variant only).
   *  Plan 05's page.tsx wires this to assistant-ui's reload(). */
  onRegenerate?: () => void;
  /** The body slot. Plan 05 passes a pre-formatted text node or
   *  <MessagePrimitive.Content />; Plan 06 swaps it for
   *  <MarkdownRenderer rawMarkdown=... /> without changing the
   *  surrounding bubble shell. */
  children: ReactNode;
}

const assistantContainerClass =
  "bg-slate-50 border border-slate-200 rounded-lg p-4 max-w-prose group relative";
const userContainerClass =
  "bg-slate-100 border border-slate-200 rounded-lg p-4 max-w-prose ml-auto";

// Shared action-row button class (Copy + Regenerate) — shadcn focus-ring
// pattern + hover bg. Size h-7 w-7 matches UI-SPEC §8.3.
const actionButtonClass =
  "h-7 w-7 rounded-md hover:bg-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2 inline-flex items-center justify-center text-slate-700";

export function ChatBubble({
  role,
  rawMarkdown,
  onRegenerate,
  children,
}: ChatBubbleProps): React.JSX.Element {
  if (role === "user") {
    return <div className={userContainerClass}>{children}</div>;
  }

  // Assistant variant — body slot + hover-revealed action row.
  async function handleCopy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(rawMarkdown);
      toast.success("Copied to clipboard");
    } catch {
      // Clipboard access can be blocked by browser permissions; in that
      // case we silently swallow — the user can still select text.
      // Plan 07 may add a fallback toast.error if requested.
    }
  }

  return (
    <div className={assistantContainerClass}>
      {children}
      <div
        className={cn(
          "absolute bottom-2 right-2 flex items-center gap-1",
          "opacity-0 group-hover:opacity-100 focus-within:opacity-100",
          "transition-opacity duration-150",
        )}
      >
        <button
          type="button"
          aria-label="Copy message as markdown"
          onClick={handleCopy}
          className={actionButtonClass}
        >
          <Copy className="h-4 w-4" />
        </button>
        <button
          type="button"
          aria-label="Regenerate response"
          onClick={onRegenerate}
          className={actionButtonClass}
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
