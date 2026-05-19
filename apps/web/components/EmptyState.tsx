// Plan 04-05 Wave 4 — EmptyState.
//
// UI-SPEC §11 + §17 — centered tagline that fills the message area when
// the thread is empty (no user messages have been sent yet). Composer
// remains visible at the bottom; this component only owns the message
// area placeholder.
//
// Copy contract (UI-SPEC §17): "Ask anything. We'll route to the right
// model." — exact text, do NOT paraphrase. The single quote on "We'll"
// uses an HTML entity to keep the JSX parser happy.
"use client";

export function EmptyState(): React.JSX.Element {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-4 py-12">
      <p className="text-lg font-semibold text-slate-900">
        Ask anything. We&apos;ll route to the right model.
      </p>
    </div>
  );
}
