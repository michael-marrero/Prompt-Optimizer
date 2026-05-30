// Plan 04-07 Wave 6 — KeyForm.
//
// Shared form posting to /api/settings via apps/web/lib/api-client.ts.
// Used by FirstRunModal (blocking mode) AND apps/web/app/settings/page.tsx
// (settings mode). The mode prop controls the submit button label and the
// autoFocus behaviour; everything else (submit handler, dispatched event,
// toasts) is identical.
//
// D-18 IN-COMPONENT HYGIENE (the belt-and-suspenders layer):
//   - This component NEVER calls console.log / console.error / console.warn
//     anywhere — not on the happy path, not on the error path. The unit
//     test asserts zero console calls on submit success AND failure; the
//     Playwright secure-key.spec.ts asserts no console message contains
//     the literal key end-to-end. A grep gate in Task 1's verify also
//     scans the file for any console.* token.
//   - The plaintext key lives ONLY in React useState (memory) for the
//     duration of the form. After a successful submit it is cleared via
//     setValue("") so subsequent renders cannot leak it.
//   - The postSettings wrapper (apps/web/lib/api-client.ts) already
//     scrubs the literal key from any thrown Error.message before
//     re-throwing; this component does NOT include the value in any
//     toast string (the §10.5 catalog is byte-constant copy).
//
// D-19 POST-ENTRY UNBLOCK:
//   On 200 response, the component dispatches a custom window event
//   `'pomu:key-saved'`. useFirstRunGate listens for it and re-fetches
//   /api/health, which flips needsKey to false and closes the modal.
//
// UI-SPEC §10.5 TOAST CATALOG (byte-for-byte):
//   - success: "OpenRouter connected — try a prompt!"
//   - 503 / "unavailable" error: "Couldn't save the key — is the local API running?"
//   - any other error: "That key doesn't look right. Check it and try again."
//
// Cross-refs:
//   - 04-UI-SPEC.md §10.4 (submit flow), §10.5 (toast catalog), §17 (copy)
//   - 04-CONTEXT.md D-18 (key isolation invariants)
//   - 04-CONTEXT.md D-19 (post-entry unblock event)
//   - apps/web/lib/api-client.ts:postSettings (Plan 02 typed wrapper)

"use client";

import { useState } from "react";
import type React from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { postSettings, type SettingsProvider } from "@/lib/api-client";

export interface KeyFormProps {
  /** "blocking" — used by FirstRunModal; autofocuses the Input and renders
   *  the "Save & continue" button label.
   *  "settings" — used by /settings page; no autofocus; renders the
   *  "Update key" label when the field is empty (the user is replacing an
   *  existing key) and "Save & continue" when typing a new key. */
  mode: "blocking" | "settings";
  /** Which provider key this form writes (UI-12 §11.1 — one row per provider).
   *  Defaults to "openrouter" so existing call sites (FirstRunModal + the
   *  Phase-4 single-section settings page) keep their exact behavior. */
  provider?: SettingsProvider;
}

// §17 per-provider input placeholder + accessible label.
const PROVIDER_PLACEHOLDER: Record<SettingsProvider, string> = {
  openrouter: "sk-or-v1-...",
  anthropic: "sk-ant-...",
};
const PROVIDER_LABEL: Record<SettingsProvider, string> = {
  openrouter: "OpenRouter API key",
  anthropic: "Anthropic API key",
};

export function KeyForm({
  mode,
  provider = "openrouter",
}: KeyFormProps): React.JSX.Element {
  const [value, setValue] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || submitting) return;
    setSubmitting(true);
    try {
      await postSettings(provider, trimmed);
      toast.success("OpenRouter connected — try a prompt!");
      // Notify the rest of the app — useFirstRunGate listens for this.
      window.dispatchEvent(new CustomEvent("pomu:key-saved"));
      // Clear the value from memory once the submit succeeds. The
      // unmount path also clears via React; this is the belt.
      setValue("");
    } catch (err) {
      // postSettings (Plan 02) already scrubs the literal key from
      // err.message. We do NOT interpolate the user-supplied value
      // into any toast string — the §10.5 catalog is byte-constant.
      const msg = String((err as Error)?.message ?? "");
      if (msg.includes("503") || msg.toLowerCase().includes("unavailable")) {
        toast.error("Couldn't save the key — is the local API running?");
      } else {
        toast.error("That key doesn't look right. Check it and try again.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  // Button label: in settings mode, when the input is empty the user is
  // replacing an existing key — show "Update key". Once they start
  // typing show "Save & continue" so the affirmative action is clear.
  const buttonLabel =
    mode === "settings" && value === "" ? "Update key" : "Save & continue";

  return (
    <form onSubmit={handleSubmit}>
      <Input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={PROVIDER_PLACEHOLDER[provider]}
        aria-label={PROVIDER_LABEL[provider]}
        autoComplete="off"
        autoCorrect="off"
        autoCapitalize="off"
        spellCheck={false}
        autoFocus={mode === "blocking"}
        className="h-10"
      />
      <Button
        type="submit"
        disabled={submitting || !value.trim()}
        className="w-full mt-4 bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)]"
      >
        {buttonLabel}
      </Button>
    </form>
  );
}
