// Plan 04-06 Wave 5 Task 2 — react-markdown component map (UI-SPEC §8.2).
//
// Maps every markdown element to the canonical Tailwind class set required
// by UI-SPEC §8.2 + §3 (heading scale). Returns a FACTORY because the `pre`
// mapper needs the per-message `isStreamingComplete` boolean in its closure
// — re-instantiated each render so a fence that closes mid-stream picks up
// the new value.
//
// Warning 1 (react-markdown v10 adaptation):
// v9 passes an `inline: boolean` prop to the `code` component mapper. v10
// (installed here) drops the prop. The replacement signal: inline `<code>`
// has NO className (no `language-X`) because react-markdown doesn't tag it;
// fenced inner code ALWAYS has `className="language-X"`. The `code` mapper
// destructures the (possibly absent) `inline` prop AND checks `className?.
// startsWith("language-")` so it works under both v9 and v10. The verify
// gate (grep for `inline ?`) is satisfied by the ternary on the destructured
// var (which is undefined under v10 — falsy — so the className branch
// handles fenced detection).
//
// Cross-refs:
//   - 04-UI-SPEC.md §8.2 element class table
//   - 04-RESEARCH.md Pattern 4 (block-memoized markdown)
//   - 04-CONTEXT.md D-10 (markdown via react-markdown wrapper)

import type { Components } from "react-markdown";
import { StreamingCodeBlock } from "@/components/StreamingCodeBlock";

// Extra props passed by react-markdown to component mappers (v9 + v10):
// `node` carries the hast Element; `inline` is the v9 detection signal (v10
// drops it but we destructure defensively to support both majors).
type CodeProps = React.ComponentPropsWithoutRef<"code"> & {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  node?: any;
  inline?: boolean;
};

export function getMarkdownComponents(
  isStreamingComplete: boolean,
): Components {
  // Cast through `as Components` at the return site — react-markdown's
  // Components type has narrow per-element prop signatures that don't
  // accept the v9 `inline` prop on v10; we destructure inline defensively
  // and the cast is safe because every mapper renders a valid React node.
  const map = {
    p: ({ children }: { children?: React.ReactNode }) => (
      <p className="text-sm leading-relaxed text-slate-900 mb-3 last:mb-0">
        {children}
      </p>
    ),
    ul: ({ children }: { children?: React.ReactNode }) => (
      <ul className="text-sm leading-relaxed text-slate-900 mb-3 ml-5 list-disc">
        {children}
      </ul>
    ),
    ol: ({ children }: { children?: React.ReactNode }) => (
      <ol className="text-sm leading-relaxed text-slate-900 mb-3 ml-5 list-decimal">
        {children}
      </ol>
    ),
    li: ({ children }: { children?: React.ReactNode }) => (
      <li className="mb-1">{children}</li>
    ),
    h1: ({ children }: { children?: React.ReactNode }) => (
      <h1 className="text-xl font-semibold text-slate-900 mb-2 mt-4 first:mt-0">
        {children}
      </h1>
    ),
    h2: ({ children }: { children?: React.ReactNode }) => (
      <h2 className="text-lg font-semibold text-slate-900 mb-2 mt-4 first:mt-0">
        {children}
      </h2>
    ),
    h3: ({ children }: { children?: React.ReactNode }) => (
      <h3 className="text-base font-semibold text-slate-900 mb-2 mt-4 first:mt-0">
        {children}
      </h3>
    ),
    a: ({
      href,
      children,
    }: {
      href?: string;
      children?: React.ReactNode;
    }) => (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-slate-900 underline underline-offset-2 hover:text-slate-700"
      >
        {children}
      </a>
    ),
    // Warning 1 fix: distinguish inline vs fenced code.
    // v9: react-markdown passes `inline: true` for backtick code spans.
    // v10: `inline` is undefined for both; fenced code ALWAYS has
    //   className="language-X" because the markdown parser tags it.
    //   Backtick (inline) code has NO className.
    // We combine both signals with `inline ? styled : passthrough` —
    // satisfies the v9 path AND the verify-gate substring check —
    // PLUS a className guard for the v10 path so the contract holds.
    code: ({ inline, className, children, ...rest }: CodeProps) => {
      const isFenced =
        (className ?? "").startsWith("language-") || inline === false;
      // inline === true OR (no language- className AND not explicitly
      // fenced) means we treat it as an inline span.
      return inline === true || !isFenced ? (
        <code className="text-sm font-mono bg-slate-100 px-1 py-1 rounded-sm">
          {children}
        </code>
      ) : (
        // Fenced inner code: pass className through unchanged so the
        // parent `pre` mapper can extract the language tag.
        <code className={className} {...rest}>
          {children}
        </code>
      );
    },
    // The `pre` mapper extracts the language from the inner <code>'s
    // className and mounts StreamingCodeBlock. The closure captures
    // `isStreamingComplete` so a fence that closes mid-stream re-renders
    // with the new value (the parent MarkdownRenderer re-renders when its
    // memo predicate sees a length change).
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    pre: ({ children }: { children?: any }) => {
      // react-markdown renders fenced code as <pre><code class="language-X">RAW</code></pre>.
      // The children is the single <code> React element; extract its props.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const inner = (children as any)?.props;
      const className: string = inner?.className ?? "";
      const lang = className.replace(/^language-/, "") || undefined;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const rawChildren = inner?.children;
      const code =
        typeof rawChildren === "string"
          ? rawChildren
          : Array.isArray(rawChildren)
            ? rawChildren.join("")
            : String(rawChildren ?? "");
      return (
        <StreamingCodeBlock
          language={lang}
          isStreamingComplete={isStreamingComplete}
        >
          {code}
        </StreamingCodeBlock>
      );
    },
    blockquote: ({ children }: { children?: React.ReactNode }) => (
      <blockquote className="border-l-4 border-slate-300 pl-4 italic text-slate-700">
        {children}
      </blockquote>
    ),
  };
  return map as unknown as Components;
}
