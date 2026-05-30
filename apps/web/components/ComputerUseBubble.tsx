// Phase 5 Plan 04 Wave 2 — ComputerUseBubble (UI-10, UI-SPEC §8).
//
// Renders a `computer_use` assistant turn. Sits below an AMBER routing chip.
// Reads its content blocks off `useMessage().content` — the SAME data-part
// pattern RoutingChip uses (RoutingChip.tsx:82-95). The SSE translator
// forwards `screenshot` events → `data-screenshot`, which convertMessage maps
// to `{type:"data", name:"screenshot", data}` content entries.
//
// Content order (UI-SPEC §8.1):
//   1. Action-narration text (interleaved text parts), rendered as markdown.
//   2. Horizontal screenshot thumbnail strip (§8.2) — each thumbnail is a
//      <button> that opens the full image in the installed shadcn Dialog.
//   3. "still working… m:ss" in-progress indicator (§8.3) while the stream is
//      open; once complete it is replaced by the metrics footer.
//
// Screenshot src resolution (UI-SPEC §8.2 + RESEARCH Pitfall 1):
//   - Inline screenshots carry `image_b64` → `data:image/{format};base64,…`.
//   - Large (≥256KB) screenshots are externalized by the adapter: `image_b64`
//     is null and `image_ref` carries the content KEY (`<sha>.<ext>`, the blob
//     filename — apps/api/blobs.py `_maybe_externalize_screenshot`). The
//     thumbnail resolves to `/api/blobs/{hash}` — the 05-02 blob proxy
//     (apps/web/app/api/blobs/[hash]/route.ts) streams the bytes from FastAPI's
//     guarded GET /api/v1/blobs/{hash}. The {hash} the endpoint expects is the
//     bare sha STEM (no extension; it globs `{hash}.*`), so `screenshotSrc`
//     strips the directory + extension off `image_ref` before interpolating
//     (BL-01: an earlier revision interpolated the value verbatim, which when
//     `image_ref` was a full path produced a traversal-shaped URL that 404'd).
//
// "still working…" timer (UI-SPEC §8.3): elapsed seconds tick client-side via
// setInterval(1000), gated on `!isComplete`. `isComplete` clones the page.tsx
// gate (page.tsx:118-123): `status.type === "complete"` OR a `metrics` data
// part is present. On complete, render MetricsFooter instead of the timer.
//
// Cross-refs:
//   - apps/web/components/RoutingChip.tsx (data-part read)
//   - apps/web/app/page.tsx:114-123 (isComplete derivation)
//   - apps/web/components/ui/dialog.tsx (click-to-enlarge)
//   - apps/web/components/MetricsFooter.tsx (replaces the timer on complete)
//   - apps/web/lib/chunk-schemas.ts (screenshot {step, image_b64?, image_ref?, image_format})
//   - 05-UI-SPEC.md §8
"use client";

import { useEffect, useRef, useState } from "react";
import { Copy, RefreshCw } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { MarkdownRenderer } from "@/components/MarkdownRenderer";
import { MetricsFooter } from "@/components/MetricsFooter";
import { cn } from "@/lib/cn";
import { useMessage } from "@assistant-ui/react";

// --------------------------------------------------------------------
// Structural part shapes (same content-vs-parts rationale as RoutingChip).
// --------------------------------------------------------------------

type PartLike = { readonly type: string };
type MessageStatus = { readonly type?: string };
type MessageStateShape = {
  readonly content: ReadonlyArray<PartLike>;
  readonly status?: MessageStatus;
};

interface ScreenshotData {
  readonly step: number;
  readonly image_b64?: string | null;
  readonly image_ref?: string | null;
  readonly image_format: "png" | "jpeg";
}
type TextPart = { readonly type: "text"; readonly text: string };
type DataPart<T> = { readonly type: "data"; readonly name: string; readonly data: T };

function isDataNamed(p: PartLike, name: string): boolean {
  return p.type === "data" && (p as { name?: string }).name === name;
}
function isTextPart(p: PartLike): p is TextPart {
  return p.type === "text";
}

// Resolve a screenshot's <img> src (UI-SPEC §8.2): inline base64 → data URI;
// image_ref-only → the 05-02 blob proxy. Returns null when neither is present.
function screenshotSrc(s: ScreenshotData): string | null {
  if (s.image_b64) {
    return `data:image/${s.image_format};base64,${s.image_b64}`;
  }
  if (s.image_ref) {
    // BL-01: `image_ref` is the bare content key (`<sha>.<ext>`). The
    // blob endpoint contracts on the bare sha stem and globs `{hash}.*`
    // for the extension, so strip any directory + extension before
    // interpolating. (Legacy rows that stored a full filesystem path are
    // also handled: `split("/").pop()` discards the directory.)
    const stem = s.image_ref.split("/").pop()!.replace(/\.[^.]+$/, "");
    return `/api/blobs/${encodeURIComponent(stem)}`;
  }
  return null;
}

// Format elapsed seconds as `m:ss` (UI-SPEC §8.3).
function formatElapsed(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

// Shared action-row button class — mirrors ChatBubble.tsx:76-77 exactly.
const actionButtonClass =
  "h-7 w-7 rounded-md hover:bg-[var(--surface-2)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2 inline-flex items-center justify-center text-[var(--ink-2)]";

const assistantContainerClass =
  "bg-[var(--surface-2)] border border-[var(--line)] rounded-lg p-4 max-w-prose group relative";

export interface ComputerUseBubbleProps {
  onRegenerate?: () => void;
}

export function ComputerUseBubble({
  onRegenerate,
}: ComputerUseBubbleProps = {}): React.JSX.Element {
  const message = useMessage({ optional: true }) as MessageStateShape | null;
  const content = message?.content ?? [];

  const screenshots = content
    .filter((p) => isDataNamed(p, "screenshot"))
    .map((p) => (p as DataPart<ScreenshotData>).data);
  const narration = content
    .filter(isTextPart)
    .map((p) => p.text)
    .join("");

  // isComplete gate — clone of page.tsx:118-123 (status complete OR a metrics
  // data part landed). Drives the "still working…" timer + footer swap.
  const statusComplete = message?.status?.type === "complete";
  const hasMetricsPart = content.some((p) => isDataNamed(p, "metrics"));
  const isComplete = statusComplete || hasMetricsPart;

  // Elapsed-time ticker — ticks once a second while the stream is open.
  // WR-05: seed from a stream-start timestamp captured ONCE in a ref and
  // recompute elapsed from wall-clock on every tick. A naive `e + 1`
  // counter resets to 0:00 on any unmount/remount (virtualized list, tab
  // switch) and misrepresents the true elapsed time; deriving from the
  // captured start makes a remount recover the real value immediately.
  const startRef = useRef<number>(Date.now());
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (isComplete) return;
    // Recompute immediately so a remount mid-stream shows the true elapsed
    // before the first interval tick fires.
    setElapsed(Math.floor((Date.now() - startRef.current) / 1000));
    const id = setInterval(
      () => setElapsed(Math.floor((Date.now() - startRef.current) / 1000)),
      1000,
    );
    return () => clearInterval(id);
  }, [isComplete]);

  async function handleCopy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(narration);
    } catch {
      // Clipboard may be blocked by permissions — silently swallow.
    }
  }

  const total = screenshots.length;

  return (
    <div className={assistantContainerClass}>
      {/* §8.1 #1 — action narration (markdown). */}
      {narration !== "" && (
        <div className="text-sm leading-relaxed text-[var(--ink)]">
          <MarkdownRenderer
            rawMarkdown={narration}
            isStreamingComplete={isComplete}
            messageId={`cu-${total}`}
          />
        </div>
      )}

      {/* §8.2 — horizontal screenshot thumbnail strip. */}
      {total > 0 && (
        <div className="flex gap-2 overflow-x-auto py-2 my-3">
          {screenshots.map((shot, i) => {
            const src = screenshotSrc(shot);
            const n = i + 1;
            return (
              <Dialog key={`${shot.step}-${i}`}>
                <DialogTrigger asChild>
                  <button
                    type="button"
                    aria-label={`Screenshot ${n} of ${total} — click to enlarge`}
                    className="h-20 rounded-md border border-[var(--line)] cursor-zoom-in hover:border-[var(--line-strong)] flex-shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2 overflow-hidden"
                  >
                    {src !== null && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={src}
                        alt={`Screenshot ${n}`}
                        className="h-20 w-auto"
                      />
                    )}
                  </button>
                </DialogTrigger>
                <DialogContent className="max-w-4xl">
                  <DialogTitle className="sr-only">{`Screenshot ${n} enlarged`}</DialogTitle>
                  {src !== null && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={src}
                      alt={`Screenshot ${n} enlarged`}
                      className="w-full h-auto rounded-md"
                    />
                  )}
                </DialogContent>
              </Dialog>
            );
          })}
        </div>
      )}

      {/* §8.3 — "still working…" indicator while open; metrics footer once
          complete. */}
      {isComplete ? (
        <MetricsFooter />
      ) : (
        <div
          role="status"
          aria-live="polite"
          aria-label={`Still working, ${formatElapsed(elapsed)} elapsed`}
          className="flex items-center gap-2 text-xs font-mono text-[var(--ink-3)] mt-2"
        >
          <span
            aria-hidden="true"
            className="h-2 w-2 rounded-full bg-amber-500 motion-safe:animate-pulse"
          />
          <span>{`still working… ${formatElapsed(elapsed)}`}</span>
        </div>
      )}

      {/* §8.4 — hover-revealed action row (clone of ChatBubble.tsx:118-141). */}
      <div
        className={cn(
          "absolute bottom-2 right-2 flex items-center gap-1",
          "opacity-0 group-hover:opacity-100 focus-within:opacity-100",
          "transition-opacity duration-150",
        )}
      >
        <button
          type="button"
          aria-label="Copy message as markdown"
          onClick={handleCopy}
          className={actionButtonClass}
        >
          <Copy className="h-4 w-4" />
        </button>
        <button
          type="button"
          aria-label="Regenerate response"
          onClick={onRegenerate}
          className={actionButtonClass}
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
