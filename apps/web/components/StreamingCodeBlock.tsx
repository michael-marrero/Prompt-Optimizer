// Plan 04-06 Wave 5 Task 1 — Fence-state-aware code block.
//
// Pattern 5b path (RESEARCH lines 831-855) — chosen over Pattern 5 because
// MarkdownRenderer needs a callable React component that takes
// rawMarkdown/isStreamingComplete/messageId as explicit props for memo
// equality and unit testing. The thin-wrapper pattern only applies when
// rendering inside the @assistant-ui/react-markdown MarkdownTextPrimitive
// (which subscribes to message text via context, not props). Plan 06 takes
// the direct react-markdown route, so this component is the real
// implementation.
//
// Contract:
//   - isStreamingComplete=false  → <pre><code class="language-X">{raw}</code></pre>
//     The raw code is a React JSX child (text content). NEVER
//     dangerouslySetInnerHTML on the raw source — that would be the XSS
//     vector RESEARCH Pattern 5b forbids.
//   - isStreamingComplete=true   → fires highlightCode(raw, lang) ONCE,
//     then renders <div dangerouslySetInnerHTML={shikiHTML} />. shiki
//     escapes its inputs and emits a closed vocabulary of <pre><code>
//     <span class="..." style="...">text</span> — safe by construction
//     (T-04-36 disposition: accept).
//
// The effect deps are (isStreamingComplete, children, language) so a
// same-props rerender after the close-fence highlight does NOT re-fire.
// Pitfall 5 acceptance: zero re-highlights mid-stream + zero re-highlights
// post-close.
//
// Cross-refs:
//   - 04-RESEARCH.md §Pattern 5b, Pitfall 5, Pitfall 11
//   - 04-UI-SPEC.md §8.2 (fenced code block typography)
//   - 04-06-PLAN.md must_haves.truths (no dangerouslySetInnerHTML on raw)
"use client";

import { useEffect, useState } from "react";
import { highlightCode } from "@/lib/shiki";
import { cn } from "@/lib/cn";

export interface StreamingCodeBlockProps {
  /** Language tag extracted from the fenced code block's
   *  className="language-X" (e.g., "python"). Undefined → "text". */
  language?: string;
  /** Raw code body — the source string between the opening and (if
   *  arrived) closing ``` fences. Always a string. */
  children: string;
  /** Wave 4 contract: the assistant message has finished streaming.
   *  Plan 06's page.tsx derives this from the assistant-ui message
   *  status (`status?.type === 'complete'`) OR the equivalent
   *  `data-metrics` part presence. Until true, we render plain <pre>. */
  isStreamingComplete: boolean;
}

const PRE_CLASS =
  "text-sm font-mono leading-relaxed rounded-md overflow-x-auto p-4 my-3 bg-[var(--surface-2)] border border-[var(--line)]";

const HIGHLIGHTED_CLASS =
  "text-sm font-mono leading-relaxed rounded-md overflow-x-auto p-4 my-3";

export function StreamingCodeBlock({
  language,
  children,
  isStreamingComplete,
}: StreamingCodeBlockProps): React.JSX.Element {
  const [html, setHtml] = useState<string | null>(null);

  useEffect(() => {
    if (!isStreamingComplete) {
      // Fence still open. Clear any prior highlight (defensive — the
      // component is normally mounted-once-per-block so this branch is
      // rarely hit, but a memo upstream could pass false after true on
      // a regenerate).
      setHtml(null);
      return;
    }
    let cancelled = false;
    highlightCode(children, language ?? "text")
      .then((tokenized) => {
        if (!cancelled) setHtml(tokenized);
      })
      .catch(() => {
        // shiki failure → fall back to plain pre. Never crash the bubble.
        if (!cancelled) setHtml(null);
      });
    return () => {
      cancelled = true;
    };
  }, [isStreamingComplete, children, language]);

  // Pre-highlight (open fence) OR highlight pending OR highlight failed →
  // render plain <pre><code> with React JSX text content.
  if (!isStreamingComplete || !html) {
    const langClass = `language-${language ?? "text"}`;
    return (
      <pre className={cn(PRE_CLASS)}>
        <code className={langClass}>{children}</code>
      </pre>
    );
  }

  // Post-highlight — shiki output is the trusted HTML (closed vocabulary
  // of <pre><code><span class/style>...</span></code></pre>).
  return (
    <div
      className={cn(HIGHLIGHTED_CLASS)}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
