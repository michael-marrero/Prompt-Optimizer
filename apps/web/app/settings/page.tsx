// Plan 04-07 Wave 6 — /settings page.
//
// CONTEXT D-17 — the modal (FirstRunModal) and the persistent /settings
// page reuse the SAME KeyForm component. The modal mounts KeyForm in
// "blocking" mode; this page mounts it in "settings" mode (no autofocus,
// alternate "Update key" label when the field is empty).
//
// UI-SPEC §17 copy (byte-for-byte):
//   - Page H1: "Settings"
//   - Section H2: "OpenRouter API key"
//
// The header here mirrors apps/web/app/page.tsx's sticky header so the
// user has a consistent "back to chat" affordance. Plan 05's ChatPage
// uses an inline Link → "/settings"; this page uses a Link → "/" for
// the same purpose.
//
// Cross-refs:
//   - 04-UI-SPEC.md §5.2 (settings page layout) + §17 (copy)
//   - 04-CONTEXT.md D-17 (persistent /settings reuses KeyForm)

"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import type React from "react";
import { KeyForm } from "@/components/KeyForm";

export default function SettingsPage(): React.JSX.Element {
  return (
    <div className="flex flex-col min-h-screen">
      <header className="h-14 border-b border-slate-200 bg-white sticky top-0 z-10 px-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            href="/"
            aria-label="Back to chat"
            className="inline-flex h-9 w-9 items-center justify-center rounded-md text-slate-700 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2"
          >
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <h1 className="text-lg font-semibold text-slate-900">Settings</h1>
        </div>
      </header>

      <main className="max-w-xl mx-auto px-4 py-8 w-full">
        <section>
          <h2 className="text-base font-semibold text-slate-900 mb-3">
            OpenRouter API key
          </h2>
          <p className="text-sm text-slate-600 mb-4 leading-relaxed">
            Paste your key from{" "}
            <a
              href="https://openrouter.ai/keys"
              target="_blank"
              rel="noopener noreferrer"
              className="underline underline-offset-2 hover:text-slate-700"
            >
              openrouter.ai/keys ↗
            </a>
            . The key is held only in your local API process — it never
            leaves this machine.
          </p>
          <KeyForm mode="settings" />
        </section>
      </main>
    </div>
  );
}
