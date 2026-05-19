# Wave-0 Spike — assistant-ui-react-markdown code-block primitive

**Spike date:** 2026-05-19
**Spiked by:** Plan 04-01 Task 3
**Decision:** **Plan 06 uses Pattern 5 (built-in primitive — `CodeOverride` + `PreOverride` + `DefaultCodeBlock`).**

---

## (a) Modules / exports inspected

Inside `apps/web/node_modules/@assistant-ui/react-markdown@0.14.0/dist/`:

| File | Export | Role |
|------|--------|------|
| `overrides/PreOverride.js` | `PreContext`, `useIsMarkdownCodeBlock`, `PreOverride` | A React Context. `<pre>` elements push their props into `PreContext.Provider`. `useIsMarkdownCodeBlock()` returns `true` iff the calling `<code>` is wrapped in a `<pre>` (i.e. it's a fenced code block, not inline `\`code\``). |
| `overrides/CodeOverride.js` | `CodeOverride` (default for `<code>`) | The component react-markdown calls for every `<code>` element. `useIsMarkdownCodeBlock()` first — if `false`, return `<Code {...props}/>` (inline). If `true`, dispatch to `CodeBlockOverride` → `DefaultCodeBlock`. |
| `overrides/CodeBlock.js` | `DefaultCodeBlock` | Decides at render time: if `language` (parsed from `className="language-X"`) is non-empty → render `<SyntaxHighlighter ...>`; otherwise render `<DefaultCodeBlockContent>` (plain `<pre><code>{rawText}</code></pre>`). |
| `memoization.js` | `memoCompareNodes` | Memo equality used by both `CodeOverride` and `PreOverride`. Compares hast `node` references plus the props that matter for layout. |

---

## (b) Fence-state detection — built-in or DIY?

**Built-in. The combination of three mechanisms produces the no-flicker contract for free:**

1. **react-markdown is the tokenizer.** A code fence does NOT produce a `<pre><code class="language-X">` node until the closing ` ``` ` is observed in the stream. While the fence is open, react-markdown emits the partial fence body as raw text inside an unclassed `<code>` element (no `language-X`). At that point, `DefaultCodeBlock.SH` resolves to `DefaultCodeBlockContent` (plain `<pre><code>`) — **NOT shiki**.
2. **One-shot highlight on close.** The moment the closing ` ``` ` lands, react-markdown re-emits the node as `<pre><code class="language-X">`. `DefaultCodeBlock` now selects `SyntaxHighlighter` (the shiki component the user injects via `components`) and renders it. This is the single highlight pass per block.
3. **Memo prevents re-highlight after close.** Both `PreOverride` and `CodeOverride` are wrapped in `React.memo` with `memoCompareNodes`. Once the closed block is rendered, subsequent stream ticks (markdown body continues around the block) hit the memo cache and the shiki component does not re-render. No second highlight. No flicker.

The Playwright `no-flicker.spec.ts` assertion (Plan 06 implements) — "the inner `<code>` element's child structure changes exactly once per block" — is satisfied by the upstream library without any fence-state code on our side. Open fence: 0 mutations (plain pre). Close fence: 1 mutation (shiki swap). Post-close stream ticks: 0 mutations (memo).

---

## (c) Decision

**Plan 06 uses Pattern 5 (built-in primitive).** The exact shape Plan 06 should ship:

```tsx
// apps/web/lib/markdown-components.tsx — to be authored by Plan 06
import { ComponentType, memo } from "react";
import { codeToHtml } from "shiki";
// ... shiki async highlighter, memoized per (language, code) key

export const SyntaxHighlighter: ComponentType<{ language: string; code: string }> = memo(
  function SyntaxHighlighter({ language, code }) {
    // call shiki.codeToHtml({lang: language, theme: 'github-light'})
    // render with dangerouslySetInnerHTML
  },
);

// Then in Plan 06's MarkdownText usage:
<MarkdownTextPrimitive
  components={{
    SyntaxHighlighter,
    CodeHeader: DefaultHeader,
    // Pre / Code use shadcn defaults
  }}
/>
```

**Plan 06 does NOT need to implement Pattern 5b (custom `StreamingCodeBlock`).** Pattern 5b is the fallback for projects that bypass `@assistant-ui/react-markdown` and use raw `react-markdown` directly — that path does not benefit from the `PreOverride`/`CodeOverride` memo chain and would re-highlight on every tick.

---

## (d) Note for the Plan 06 executor

Read RESEARCH.md §"Pattern 5" lines 778-829 — the implementation sketch there matches what this spike confirmed. The plan should:

1. Author `apps/web/lib/markdown-components.tsx` exporting a memoized `SyntaxHighlighter` that calls `shiki.codeToHtml({ lang, theme: 'github-light' })` once per (`lang`, `code`) input. Memoize on the `code` string so identical-content re-renders return the cached HTML.
2. Pass that component to `<MarkdownTextPrimitive>` via the `components.SyntaxHighlighter` slot. The fence-state plumbing is automatic from there.
3. Do NOT touch `PreOverride` / `CodeOverride` — they're already wired by `MarkdownTextPrimitive`.
4. The `no-flicker.spec.ts` MutationObserver assertion (RESEARCH lines 789-825) is the regression guard.

Pattern 5b stays as a documented fallback in RESEARCH but is not on the Plan 06 implementation path.
