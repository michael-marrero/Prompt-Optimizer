// Phase 7 Plan 07-01 Wave 0 — NEW RED test: Plasma design-token presence in
// app/globals.css.
//
// 07-VALIDATION.md row: "Plasma tokens + 4 theme blocks in globals.css | D-07 |
// unit" + the §Color --danger token (D-06).
//
// RED-by-design: app/globals.css currently holds the Phase-4 slate/Geist
// @theme-inline token layer (19 lines, no --accent / --bg / --danger custom
// properties, no .theme-* blocks). The Plasma token system + 4 alternate theme
// blocks land in Plan 07-02. Until then every assertion below fails because the
// token text is simply not in the file yet — the correct Wave-0 RED state, NOT a
// malformed-test failure. This test reads globals.css as raw TEXT (it does not
// import or evaluate CSS), so it can never fail for a transform reason.
//
// The LOCKED values (UI-SPEC §Color + §Alternate Themes; "do not round"):
//   :root           --accent: #6d4aff   --bg: #f8f6f1   --danger: <literal red, D-06 ~#e5484a>
//   .theme-citrus   --accent: #d95226
//   .theme-tide     --accent: #ff6b54
//   .theme-bauhaus  --accent: #e63946
//   .theme-carbon   --accent: #a78bfa

import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

// Resolve app/globals.css relative to THIS test file so the path is stable
// regardless of the cwd vitest is invoked from. tests/ is a sibling of app/.
const __dirname = dirname(fileURLToPath(import.meta.url));
const GLOBALS_CSS_PATH = resolve(__dirname, "..", "app", "globals.css");

function readGlobals(): string {
  return readFileSync(GLOBALS_CSS_PATH, "utf-8");
}

// Normalize whitespace inside a declaration so "--accent:#6d4aff" and
// "--accent: #6d4aff" both match. Collapses runs of spaces to one and strips
// spaces directly around the colon for the property:value pair under test.
function declaresProperty(css: string, prop: string, value: string): boolean {
  // Match `--prop:` optionally followed by whitespace then the value, allowing
  // any case for the hex digits. Escape regex-significant chars in value.
  const escapedValue = value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const re = new RegExp(`${prop}\\s*:\\s*${escapedValue}`, "i");
  return re.test(css);
}

// Find the body of a CSS rule whose selector contains `selector` (e.g.
// ".theme-citrus"). Returns the text between that selector's first `{` and its
// matching `}` (shallow — the theme blocks are flat declaration lists, no
// nesting), or "" if the selector is absent.
function ruleBody(css: string, selector: string): string {
  const selIdx = css.indexOf(selector);
  if (selIdx === -1) return "";
  const openIdx = css.indexOf("{", selIdx);
  if (openIdx === -1) return "";
  const closeIdx = css.indexOf("}", openIdx);
  if (closeIdx === -1) return "";
  return css.slice(openIdx + 1, closeIdx);
}

describe("globals.css — Plasma design tokens + 4 alternate theme blocks (D-06/D-07)", () => {
  it("D-07: :root declares the Plasma accent --accent: #6d4aff", () => {
    const css = readGlobals();
    expect(css).toMatch(/:root/);
    expect(declaresProperty(css, "--accent", "#6d4aff")).toBe(true);
  });

  it("Story 7.1: :root declares the answer-forward background --bg: #fbfbfa", () => {
    // Was #f8f6f1 (warm paper); shifted to a cooler near-white canvas in the
    // Epic 7 answer-forward redesign (user-approved 2026-07-15).
    const css = readGlobals();
    expect(declaresProperty(css, "--bg", "#fbfbfa")).toBe(true);
  });

  it("D-06: a --danger custom property exists (dedicated destructive red, NOT --warn/magenta)", () => {
    const css = readGlobals();
    // D-06 only locks that --danger EXISTS and is a literal red (recommend
    // ~#e5484a). We assert the property is declared; we do NOT pin the exact
    // hex so the planner can pick the precise red — but it must NOT be the
    // magenta --warn / --accent-2 value (#ff3d8b).
    expect(/--danger\s*:/.test(css)).toBe(true);
    const dangerMatch = css.match(/--danger\s*:\s*([^;]+);/i);
    expect(dangerMatch, "--danger must be declared with a value").not.toBeNull();
    const dangerValue = (dangerMatch?.[1] ?? "").trim().toLowerCase();
    expect(dangerValue).not.toBe("#ff3d8b"); // must not reuse brand magenta
  });

  it("D-07: .theme-citrus block redeclares --accent: #d95226", () => {
    const css = readGlobals();
    expect(css).toMatch(/\.theme-citrus/);
    expect(declaresProperty(ruleBody(css, ".theme-citrus"), "--accent", "#d95226")).toBe(true);
  });

  it("D-07: .theme-tide block redeclares --accent: #ff6b54", () => {
    const css = readGlobals();
    expect(css).toMatch(/\.theme-tide/);
    expect(declaresProperty(ruleBody(css, ".theme-tide"), "--accent", "#ff6b54")).toBe(true);
  });

  it("D-07: .theme-bauhaus block redeclares --accent: #e63946", () => {
    const css = readGlobals();
    expect(css).toMatch(/\.theme-bauhaus/);
    expect(declaresProperty(ruleBody(css, ".theme-bauhaus"), "--accent", "#e63946")).toBe(true);
  });

  it("D-07: .theme-carbon block redeclares --accent: #a78bfa", () => {
    const css = readGlobals();
    expect(css).toMatch(/\.theme-carbon/);
    expect(declaresProperty(ruleBody(css, ".theme-carbon"), "--accent", "#a78bfa")).toBe(true);
  });

  it("D-07: all four alternate theme class blocks are present", () => {
    const css = readGlobals();
    for (const sel of [".theme-citrus", ".theme-tide", ".theme-bauhaus", ".theme-carbon"]) {
      expect(css.includes(sel), `globals.css must declare a ${sel} block`).toBe(true);
    }
  });
});
