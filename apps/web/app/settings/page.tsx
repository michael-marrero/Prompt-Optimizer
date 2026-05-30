// Phase 5 Plan 06 Wave 3 — /settings page (UI-12, UI-SPEC §11).
//
// Rebuilds the Phase-4 single-section settings page into the three §11
// sections:
//   1. API keys      — one KeyForm row per provider (OpenRouter sk-or-v1-…,
//                      Anthropic sk-ant-…). Masked-after-save, write-only on
//                      the wire (KeyForm forwards to /api/settings; the GET
//                      only ever returns the masked form — Phase 3 SECURE-04).
//   2. Backends      — three switches (OpenRouter / Claude Code / computer-use)
//                      with the exact §11.2 helper text; toggling issues
//                      PATCH /api/settings {backends_enabled}. The UI prevents
//                      disabling the LAST enabled backend (OpenRouter floor —
//                      D-05): a switch that would leave zero enabled is itself
//                      disabled.
//   3. Computer use  — a single separated switch (Enable computer use) with the
//                      §11.3 security helper; PATCH {computer_use_opt_in}. When
//                      the env flag is unset the switch is disabled + the §17
//                      env note is shown (D-06 strict-AND — the in-app switch
//                      cannot enable a deployment that withheld the env flag).
//
// All copy verbatim from §17. Current settings loaded via GET /api/settings
// (masked).
//
// Cross-refs:
//   - apps/web/components/KeyForm.tsx (per-provider key entry)
//   - apps/web/components/ui/switch.tsx (toggles)
//   - apps/web/app/api/settings/route.ts (GET masked + PATCH whitelisted)
//   - apps/web/tests/settings-page.test.tsx (the RED test this turns green)
//   - 05-UI-SPEC.md §11 + §17 + 05-CONTEXT.md D-05/D-06

"use client";

import { useCallback, useEffect, useState } from "react";
import type React from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { toast } from "sonner";
import { KeyForm } from "@/components/KeyForm";
import { Switch } from "@/components/ui/switch";

type BackendKey = "openrouter" | "claude_code" | "computer_use";

interface MaskedKey {
  present: boolean;
  masked: string | null;
}

interface SettingsState {
  keys: Record<string, MaskedKey>;
  backends_enabled: Record<BackendKey, boolean>;
  computer_use_opt_in: boolean;
  /** Whether COMPUTER_USE_OPT_IN=1 is set in the deployment env (strict-AND,
   *  D-06). Absent in the masked payload → treated as unset (note shown +
   *  switch disabled). */
  computer_use_env_enabled?: boolean;
}

const DEFAULT_STATE: SettingsState = {
  keys: {},
  backends_enabled: { openrouter: true, claude_code: true, computer_use: false },
  computer_use_opt_in: false,
  computer_use_env_enabled: false,
};

// §11.2 — backend toggle rows: label + exact helper copy (§17).
const BACKEND_ROWS: ReadonlyArray<{
  key: BackendKey;
  label: string;
  helper: string;
}> = [
  {
    key: "openrouter",
    label: "OpenRouter",
    helper: "Conversational models (GPT, Claude, Gemini, DeepSeek, Qwen).",
  },
  {
    key: "claude_code",
    label: "Claude Code",
    helper: "Build-and-edit coding tasks.",
  },
  {
    key: "computer_use",
    label: "computer-use",
    helper: "Browse-and-act tasks. Requires the opt-in below.",
  },
];

async function patchSettings(body: Record<string, unknown>): Promise<void> {
  const response = await fetch("/api/settings", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`PATCH /api/settings failed (${response.status})`);
  }
}

export default function SettingsPage(): React.JSX.Element {
  const [state, setState] = useState<SettingsState>(DEFAULT_STATE);

  // Load the masked settings on mount.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const response = await fetch("/api/settings", { method: "GET" });
        if (!response.ok) return;
        const data = (await response.json()) as Partial<SettingsState>;
        if (cancelled) return;
        setState((prev) => ({
          keys: data.keys ?? prev.keys,
          backends_enabled: data.backends_enabled ?? prev.backends_enabled,
          computer_use_opt_in:
            data.computer_use_opt_in ?? prev.computer_use_opt_in,
          computer_use_env_enabled:
            data.computer_use_env_enabled ?? prev.computer_use_env_enabled,
        }));
      } catch {
        // FastAPI unreachable — keep the defaults; the network banner surfaces
        // the outage on the chat surface.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const enabledCount = Object.values(state.backends_enabled).filter(
    Boolean,
  ).length;

  const toggleBackend = useCallback(
    async (key: BackendKey, next: boolean) => {
      // OpenRouter floor (D-05): refuse a toggle that would leave zero enabled.
      if (!next && enabledCount <= 1 && state.backends_enabled[key]) {
        toast.error("At least one backend must stay enabled.");
        return;
      }
      const previous = state.backends_enabled;
      const nextEnabled = { ...previous, [key]: next };
      setState((prev) => ({ ...prev, backends_enabled: nextEnabled }));
      try {
        await patchSettings({ backends_enabled: nextEnabled });
      } catch {
        setState((prev) => ({ ...prev, backends_enabled: previous }));
        toast.error("Couldn't update backends — is the local API running?");
      }
    },
    [enabledCount, state.backends_enabled],
  );

  const toggleComputerUseOptIn = useCallback(
    async (next: boolean) => {
      const previous = state.computer_use_opt_in;
      setState((prev) => ({ ...prev, computer_use_opt_in: next }));
      try {
        await patchSettings({ computer_use_opt_in: next });
      } catch {
        setState((prev) => ({ ...prev, computer_use_opt_in: previous }));
        toast.error("Couldn't update computer use — is the local API running?");
      }
    },
    [state.computer_use_opt_in],
  );

  const envEnabled = state.computer_use_env_enabled === true;

  function maskedFor(provider: string): MaskedKey | undefined {
    return state.keys[provider];
  }

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

      <main className="max-w-xl mx-auto px-4 py-8 w-full space-y-12">
        {/* §11.1 — API keys (one KeyForm per provider). */}
        <section>
          <h2 className="text-lg font-semibold text-slate-900 mb-4">API keys</h2>

          <div className="space-y-6">
            <div>
              <p className="text-sm font-semibold text-slate-900 mb-2">
                OpenRouter
              </p>
              {maskedFor("openrouter")?.present && (
                <p className="text-slate-500 font-mono text-sm mb-2">
                  {maskedFor("openrouter")?.masked}
                </p>
              )}
              <KeyForm mode="settings" provider="openrouter" />
            </div>

            <div>
              <p className="text-sm font-semibold text-slate-900 mb-2">
                Anthropic
              </p>
              {maskedFor("anthropic")?.present && (
                <p className="text-slate-500 font-mono text-sm mb-2">
                  {maskedFor("anthropic")?.masked}
                </p>
              )}
              <KeyForm mode="settings" provider="anthropic" />
            </div>
          </div>
        </section>

        {/* §11.2 — Backends (per-backend enable/disable). */}
        <section>
          <h2 className="text-lg font-semibold text-slate-900 mb-4">Backends</h2>
          <div>
            {BACKEND_ROWS.map(({ key, label, helper }) => {
              const checked = state.backends_enabled[key];
              // OpenRouter floor (D-05) — block the last enabled backend.
              const floorLocked =
                checked && enabledCount <= 1;
              return (
                <div
                  key={key}
                  className="flex items-center justify-between py-3 border-b border-slate-200"
                >
                  <div className="pr-4">
                    <p className="text-sm text-slate-900">{label}</p>
                    <p className="text-sm text-slate-700">{helper}</p>
                  </div>
                  <Switch
                    aria-label={`Enable ${label} backend`}
                    checked={checked}
                    disabled={floorLocked}
                    onCheckedChange={(next) => void toggleBackend(key, next)}
                  />
                </div>
              );
            })}
          </div>
        </section>

        {/* §11.3 — Computer use (explicit opt-in, strict-AND with the env flag). */}
        <section>
          <h2 className="text-lg font-semibold text-slate-900 mb-4">
            Computer use
          </h2>
          <div className="flex items-start justify-between py-3">
            <div className="pr-4">
              <p className="text-sm text-slate-900 mb-1">Enable computer use</p>
              <p className="text-sm text-slate-700 leading-relaxed">
                Computer use can browse and act on web pages on your behalf. It
                is off by default. Visited pages may attempt prompt injection —
                only enable it when you understand the risk.
              </p>
              {!envEnabled && (
                <p className="text-xs text-slate-500 mt-2">
                  Also set COMPUTER_USE_OPT_IN=1 in your environment — both this
                  switch and the env flag must be on.
                </p>
              )}
            </div>
            <Switch
              aria-label="Enable computer use"
              checked={state.computer_use_opt_in}
              disabled={!envEnabled}
              onCheckedChange={(next) => void toggleComputerUseOptIn(next)}
            />
          </div>
        </section>
      </main>
    </div>
  );
}
