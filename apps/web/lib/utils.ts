// shadcn primitives in components/ui/* import `cn` from `@/lib/utils` by
// convention. The canonical implementation lives in `./cn.ts` (the path
// PATTERNS Pattern E names); this barrel re-exports it so the shadcn-generated
// files compile unchanged (UI-SPEC §18 — registry components must not be
// hand-edited).
export { cn } from "./cn";
