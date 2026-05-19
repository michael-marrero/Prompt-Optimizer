// Plan 04-06 Wave 5 — shiki Highlighter singleton.
//
// Pitfall 11 acceptance: createHighlighter is called EXACTLY ONCE at module
// scope across the entire process lifetime. Components import the
// highlightCode helper; they NEVER call createHighlighter themselves. The
// singleton survives HMR because module-scope state is preserved across
// React fast-refresh (Next.js Turbopack hot-replaces the importing module
// but leaves this module's exports cached as long as it didn't change).
//
// Theme: github-light (UI-SPEC §1, D-04 light-mode-only).
// Preloaded langs: the 9 most-common code-block languages observed in the
// router's training set (python/javascript/typescript/tsx/json/bash/yaml/
// markdown/sql). Unknown languages fall back to "text" via highlightCode's
// supported-langs check.
//
// Cross-refs:
//   - 04-RESEARCH.md Pitfall 11 (singleton highlighter at module scope)
//   - 04-CONTEXT.md D-11 (shiki + assistant-ui code-block primitive)
//   - 04-UI-SPEC.md §1 (single theme = github-light)

import { createHighlighter, type Highlighter } from "shiki";

// Module-scope memoized promise — concurrent first-callers share the
// same in-flight createHighlighter() so no double-init race.
let highlighterPromise: Promise<Highlighter> | null = null;

const PRELOADED_LANGS = [
  "python",
  "javascript",
  "typescript",
  "tsx",
  "json",
  "bash",
  "yaml",
  "markdown",
  "sql",
] as const;

const THEME = "github-light" as const;

export function getHighlighter(): Promise<Highlighter> {
  if (!highlighterPromise) {
    highlighterPromise = createHighlighter({
      themes: [THEME],
      langs: [...PRELOADED_LANGS],
    });
  }
  return highlighterPromise;
}

export async function highlightCode(
  code: string,
  lang: string,
): Promise<string> {
  const h = await getHighlighter();
  const loaded = h.getLoadedLanguages() as readonly string[];
  // Unknown languages fall back to "text" — shiki treats it as plaintext
  // (no tokenizer, no preload needed). Casting to string for the includes
  // check; the cast is safe because PRELOADED_LANGS is a const tuple of
  // string literals.
  const safeLang = loaded.includes(lang) ? lang : "text";
  return h.codeToHtml(code, { lang: safeLang, theme: THEME });
}
