// Plan 04-06 Wave 5 Task 2 — Memoized markdown body renderer.
//
// Pattern 4 (RESEARCH lines 733-776): wrap react-markdown in React.memo
// with a CUSTOM equality predicate keyed by (messageId, rawMarkdown.length,
// isStreamingComplete). A token append on the SAME message id with longer
// content DOES re-render (length differs); a same-props rerender from an
// unrelated state change in the parent does NOT.
//
// Whole-message memoization (Phase 4 choice over block-level memo): the
// memo predicate compares scalar fields only — O(1) per render. Block-level
// memo (splitting on \n\n and memoizing each block) is RESEARCH Pattern 4's
// stretch optimization for very long messages; profiling will decide
// whether Phase 5 needs it.
//
// Security: rehype-sanitize strips <script>, <iframe>, javascript: URLs,
// and inline event handlers (T-04-35 mitigation). remark-gfm enables the
// GFM table / strikethrough / task-list extensions per UI-SPEC §4.
//
// Cross-refs:
//   - 04-RESEARCH.md §Pattern 4 + Pitfall 4 (re-render storm)
//   - 04-CONTEXT.md D-10 (markdown via react-markdown wrapper)
//   - 04-UI-SPEC.md §4 (markdown styling) + §8.2 (element classes)
"use client";

import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import { getMarkdownComponents } from "@/lib/markdown-components";

export interface MarkdownRendererProps {
  /** Raw markdown source (the assistant message body text). */
  rawMarkdown: string;
  /** True when the streaming turn has finished — gates the one-shot
   *  syntax-highlight pass on fenced code blocks (Pattern 5b). */
  isStreamingComplete: boolean;
  /** The assistant message id. Combined with rawMarkdown.length, this
   *  forms the React.memo equality predicate. */
  messageId: string;
}

function MarkdownRendererBase({
  rawMarkdown,
  isStreamingComplete,
}: MarkdownRendererProps): React.JSX.Element {
  const components = getMarkdownComponents(isStreamingComplete);
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeSanitize]}
      components={components}
    >
      {rawMarkdown}
    </ReactMarkdown>
  );
}

function arePropsEqual(
  prev: MarkdownRendererProps,
  next: MarkdownRendererProps,
): boolean {
  return (
    prev.messageId === next.messageId &&
    prev.rawMarkdown.length === next.rawMarkdown.length &&
    prev.isStreamingComplete === next.isStreamingComplete
  );
}

export const MarkdownRenderer = memo(MarkdownRendererBase, arePropsEqual);
MarkdownRenderer.displayName = "MarkdownRenderer";
