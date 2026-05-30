// Plan 04-05 Wave 4 — ChatBubble. Plan 04-06 Wave 5 modification:
// assistant variant mounts MarkdownRenderer in place of the open children
// slot; props interface grew isStreamingComplete + messageId.
//
// UI-SPEC §8 — the visible shell that wraps every chat message. Assistant
// variant has a hover-revealed action row (Copy + Regenerate per D-14);
// user variant has no action row. Both share the same container shape.
//
// Slot contract (post Plan 06): the assistant variant renders
//   <MarkdownRenderer rawMarkdown={rawMarkdown} isStreamingComplete={...}
//                     messageId={...} />
// The `children` prop remains in the interface for forward-compat (Phase 5's
// CodeBubble / ComputerUseBubble may pass a custom node), but the default
// rendering path is the markdown renderer. The user variant still renders
// `{children}` because user messages are not markdown-rendered.
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
import { MarkdownRenderer } from "./MarkdownRenderer";

export interface ChatBubbleProps {
  /** "assistant" gets the action row + slate-50 background;
   *  "user" gets ml-auto + slate-100, no action row. */
  role: "assistant" | "user";
  /** The raw markdown source text. Copy writes this to the clipboard
   *  (NOT the rendered HTML). The assistant variant also feeds this
   *  string to MarkdownRenderer for the rendered body. */
  rawMarkdown: string;
  /** Plan 04-06: true when the assistant message has finished streaming.
   *  Used by the assistant variant to gate one-shot syntax highlighting on
   *  fenced code blocks (forwarded to MarkdownRenderer → StreamingCodeBlock).
   *  Optional with default false so existing call sites (e.g. user-variant
   *  tests that never set it) keep compiling. */
  isStreamingComplete?: boolean;
  /** Plan 04-06: the assistant message id. Forwarded to MarkdownRenderer
   *  for its React.memo equality predicate. Optional with default ""
   *  for backward compatibility with the user-variant tests. */
  messageId?: string;
  /** Invoked when Regenerate is clicked (assistant variant only).
   *  Plan 05's page.tsx wires this to assistant-ui's reload(). */
  onRegenerate?: () => void;
  /** Forward-compat body slot. Phase 5's CodeBubble / ComputerUseBubble
   *  may pass a custom React node; the default Phase 4 assistant variant
   *  renders MarkdownRenderer(rawMarkdown) and IGNORES this prop. The
   *  user variant still renders `{children}` (no markdown). */
  children?: ReactNode;
}

const assistantContainerClass =
  "bg-[var(--surface-2)] border border-[var(--line)] rounded-lg p-4 max-w-prose group relative";
const userContainerClass =
  "bg-[var(--surface-2)] border border-[var(--line)] rounded-lg p-4 max-w-prose ml-auto";

// Shared action-row button class (Copy + Regenerate) — shadcn focus-ring
// pattern + hover bg. Size h-7 w-7 matches UI-SPEC §8.3.
const actionButtonClass =
  "h-7 w-7 rounded-md hover:bg-[var(--surface-2)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2 inline-flex items-center justify-center text-[var(--ink-2)]";

export function ChatBubble({
  role,
  rawMarkdown,
  isStreamingComplete = false,
  messageId = "",
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

  // Plan 04-06: mount the memoized MarkdownRenderer in the assistant
  // bubble. Phase 5's CodeBubble / ComputerUseBubble may bypass this
  // by setting children (forward-compat); for Phase 4 the markdown
  // renderer is the only path.
  const body = children ?? (
    <MarkdownRenderer
      rawMarkdown={rawMarkdown}
      isStreamingComplete={isStreamingComplete}
      messageId={messageId}
    />
  );

  return (
    <div className={assistantContainerClass}>
      {body}
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
