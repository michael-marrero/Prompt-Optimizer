// Plan 04-07 Wave 6 — FirstRunModal.
//
// Blocking shadcn Dialog that wraps KeyForm. UI-SPEC §10 specifies the
// modal copy, ARIA, and the focus management rules. Pitfall 9 from
// RESEARCH lines 1024-1031: Radix Dialog's default `modal=true` mode
// still allows the user to close via Escape AND via outside click — the
// blocking semantics require BOTH to be disabled while needsKey is true.
//
// Pitfall 9 fix (PLAN must_haves line 5):
//   - onEscapeKeyDown={(e) => e.preventDefault()}: blocks the Escape-key
//     close path.
//   - onPointerDownOutside={(e) => e.preventDefault()}: blocks the
//     outside-click close path.
//   - showCloseButton={false} on DialogContent: hides the [×] in the
//     top-right so the user has no manual dismissal affordance.
// The modal CAN only close when the parent flips `open` to false, which
// happens once useFirstRunGate's needsKey turns false (after the
// pomu:key-saved event triggers a /api/health re-poll and the upstream
// reports adapters.openrouter.status === "ready").
//
// UI-SPEC §10.2 BYTE-FOR-BYTE COPY (every string here must match
// UI-SPEC §17 exactly — heading, body, primary CTA, link prefix,
// link text):
//   - Heading: "Connect OpenRouter to get started"
//   - Body:    "Prompt-Optimizer routes your prompts to the best model.
//              OpenRouter is the gateway to most chat models — start by
//              pasting your key."
//   - Input placeholder: "sk-or-v1-..."  (three ASCII dots, NOT U+2026
//                                          ellipsis — explicit callout)
//   - Primary CTA: "Save & continue"
//   - Link prefix: "Don't have a key? Get one at "
//   - Link text:   "openrouter.ai/keys ↗"  (U+2197 NORTH EAST ARROW)
//   - Link href:   "https://openrouter.ai/keys"
//
// Cross-refs:
//   - 04-UI-SPEC.md §10 (full modal structure + copy + ARIA)
//   - 04-UI-SPEC.md §17 (canonical strings table)
//   - 04-RESEARCH.md Pitfall 9 (Radix outside-click close)
//   - 04-CONTEXT.md D-16 (modal trigger), D-17 (KeyForm reuse), D-19 (unblock)

"use client";

import type React from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { KeyForm } from "./KeyForm";

export interface FirstRunModalProps {
  /** Driven by useFirstRunGate().needsKey from the parent. The modal
   *  cannot be dismissed manually while open=true (Pitfall 9). */
  open: boolean;
}

export function FirstRunModal({ open }: FirstRunModalProps): React.JSX.Element | null {
  // Return null when closed so the unit test (rendering with open={false})
  // confirms NOTHING from the modal copy appears in the DOM. Radix would
  // unmount automatically via the portal, but this is the belt: react-dom
  // never has to evaluate the children.
  if (!open) return null;

  return (
    <Dialog open={open}>
      <DialogContent
        onEscapeKeyDown={(e) => e.preventDefault()}
        onPointerDownOutside={(e) => e.preventDefault()}
        onInteractOutside={(e) => e.preventDefault()}
        showCloseButton={false}
        className="max-w-md"
      >
        <DialogHeader>
          {/*
            Radix DialogTitle / DialogDescription auto-generate their IDs
            and wire aria-labelledby / aria-describedby on DialogContent.
            Setting a custom `id` on these would break Radix's accessibility
            assertion (it does document.getElementById(titleId) and prints
            a console.error if the IDs don't match what it set on Content).
            We leave the IDs alone and trust Radix's defaults — UI-SPEC §14.2
            ARIA requirements are still satisfied because Radix's auto-wiring
            produces the same semantic outcome.
          */}
          <DialogTitle className="text-lg font-semibold text-slate-900">
            Connect OpenRouter to get started
          </DialogTitle>
          <DialogDescription className="text-sm text-slate-700 leading-relaxed mt-2">
            Prompt-Optimizer routes your prompts to the best model. OpenRouter is the gateway to most chat models — start by pasting your key.
          </DialogDescription>
        </DialogHeader>

        <div className="mt-6">
          <KeyForm mode="blocking" />
        </div>

        <p className="text-xs text-slate-500 mt-4">
          Don&apos;t have a key? Get one at{" "}
          <a
            href="https://openrouter.ai/keys"
            target="_blank"
            rel="noopener noreferrer"
            className="underline underline-offset-2 hover:text-slate-700"
          >
            openrouter.ai/keys ↗
          </a>
        </p>
      </DialogContent>
    </Dialog>
  );
}
