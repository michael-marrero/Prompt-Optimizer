// Phase 4 chat surface — Wave 0 PLACEHOLDER ONLY.
// Plan 04-04 replaces this file with the real AssistantRuntimeProvider + Thread
// + Composer wiring per RESEARCH Pattern 1. Wave 0 only needs a known-good
// overwrite target so `pnpm build` succeeds with the current dependency set.
//
// "use client" is required (PATTERNS Pattern D) because the eventual page mounts
// the assistant-ui runtime which uses React hooks.
"use client";

export default function ChatPage() {
  return (
    <main className="flex-1 flex items-center justify-center bg-white text-slate-900">
      Phase 4 chat surface — wave 0 placeholder
    </main>
  );
}
