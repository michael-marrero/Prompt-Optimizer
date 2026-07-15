// Phase 5 Plan 06 Wave 3 — MessageBubble (per-backend bubble dispatch seam).
//
// The single dispatch point that selects an assistant-turn renderer by the
// message's routing backend (UI-SPEC §16 "Bubble dispatch"):
//   claude_code  → CodeBubble        (UI-09, §7)
//   computer_use → ComputerUseBubble (UI-10, §8)
//   openrouter / default / no routing part → ChatBubble (UI-05, §8 Phase 4)
//
// The RoutingChip (auto OR override variant) sits ABOVE every bubble and the
// FeedbackButtons (UI-15, §13) mount in the action row on every assistant
// message. Regenerate is live-wired to useMessageRuntime().reload().
//
// page-shell.test.tsx pins the dispatch contract here (the seam is assertable
// without the live assistant-ui runtime): it mocks useMessage()/useMessageRuntime
// and asserts data-testid="code-bubble" / "computer-use-bubble" / "chat-bubble"
// plus the two FeedbackButtons aria-labels. The testids are applied at THIS
// dispatch wrapper (not inside the leaf bubbles) so the dispatch decision is
// what is being asserted.
//
// Cross-refs:
//   - apps/web/components/CodeBubble.tsx, ComputerUseBubble.tsx, ChatBubble.tsx
//   - apps/web/components/RoutingChip.tsx (chip above), MetricsFooter.tsx
//   - apps/web/components/FeedbackButtons.tsx (UI-15 thumbs)
//   - apps/web/tests/page-shell.test.tsx (the RED test this turns green)
//   - 05-UI-SPEC.md §16
"use client";

import type React from "react";
import { useMessage, useMessageRuntime } from "@assistant-ui/react";
import { ChatBubble } from "@/components/ChatBubble";
import { CodeBubble } from "@/components/CodeBubble";
import { ComputerUseBubble } from "@/components/ComputerUseBubble";
import { RoutingChip } from "@/components/RoutingChip";
import { LowConfidenceNudge } from "@/components/LowConfidenceNudge";
import { MetricsFooter } from "@/components/MetricsFooter";
import { FeedbackButtons } from "@/components/FeedbackButtons";
import type { Backend } from "@/lib/types";

type PartLike = { readonly type: string };
type DataPart = {
  readonly type: "data";
  readonly name: string;
  readonly data: { backend?: Backend } & Record<string, unknown>;
};
type TextPart = { readonly type: "text"; readonly text: string };
type MessageStateShape = {
  readonly id?: string;
  readonly content?: ReadonlyArray<PartLike>;
  readonly status?: { readonly type?: string };
};

function isRoutingPart(p: PartLike): p is DataPart {
  return p.type === "data" && (p as { name?: string }).name === "routing";
}
function isTextPart(p: PartLike): p is TextPart {
  return p.type === "text";
}
function isMetricsPart(p: PartLike): boolean {
  return p.type === "data" && (p as { name?: string }).name === "metrics";
}

export interface MessageBubbleProps {
  /** The active thread id — forwarded to FeedbackButtons for the D-12 row. */
  threadId?: string | null;
  /** The originating user prompt for this turn — forwarded to FeedbackButtons
   *  as the D-12 row's `prompt`. */
  prompt?: string;
  /** Story 5.2 low-confidence nudge wiring — the composer's one-shot override
   *  state/setter + computer-use availability, threaded from ChatSurface so the
   *  nudge offers the EXISTING FR-3 override path. Omitted → the nudge still
   *  renders but its dropdown is a no-op (safe default for tests/isolation). */
  overrideBackend?: Backend | null;
  onOverride?: (backend: Backend | null) => void;
  computerUseEnabled?: boolean;
}

export function MessageBubble({
  threadId,
  prompt,
  overrideBackend = null,
  onOverride,
  computerUseEnabled = false,
}: MessageBubbleProps = {}): React.JSX.Element {
  const messageRuntime = useMessageRuntime();
  const handleRegenerate = (): void => {
    messageRuntime.reload();
  };

  const message = useMessage({ optional: true }) as MessageStateShape | null;
  const content = message?.content ?? [];

  const routingPart = content.find(isRoutingPart);
  const backend = (routingPart?.data?.backend ?? "openrouter") as Backend;

  // rawMarkdown + isStreamingComplete for the default ChatBubble path (clone of
  // page.tsx's AssistantMessage derivation).
  const rawMarkdown = content
    .filter(isTextPart)
    .map((p) => (p as TextPart).text)
    .join("");
  const messageId = message?.id ?? "";
  const isStreamingComplete =
    message?.status?.type === "complete" || content.some(isMetricsPart);

  // Per-backend dispatch (UI-SPEC §16). The testid wraps each bubble so the
  // page-shell dispatch test can assert which renderer was selected.
  let bubble: React.JSX.Element;
  let testid: string;
  if (backend === "claude_code") {
    testid = "code-bubble";
    bubble = <CodeBubble onRegenerate={handleRegenerate} />;
  } else if (backend === "computer_use") {
    testid = "computer-use-bubble";
    bubble = <ComputerUseBubble onRegenerate={handleRegenerate} />;
  } else {
    testid = "chat-bubble";
    bubble = (
      <ChatBubble
        role="assistant"
        rawMarkdown={rawMarkdown}
        isStreamingComplete={isStreamingComplete}
        messageId={messageId}
        onRegenerate={handleRegenerate}
      />
    );
  }

  return (
    <article className="mb-10">
      {/* Story 7.1 (answer-forward): the routing element sits inline ABOVE the
          answer with no competing "Prompt Optimizer" label — the answer is the
          hero. RoutingChip becomes the "model · why" affordance in Story 7.2. */}
      <div className="mb-2 flex items-center gap-2">
        <RoutingChip />
      </div>
      <div data-testid={testid}>{bubble}</div>
      {/* Story 5.2 — low-confidence override nudge (below the bubble; renders
          only for completed, low-confidence auto routes). */}
      <LowConfidenceNudge
        overrideBackend={overrideBackend}
        onOverride={onOverride ?? (() => undefined)}
        onRegenerate={handleRegenerate}
        computerUseEnabled={computerUseEnabled}
      />
      {/* assistant footer — folded metrics stat row + feedback actions (D-05) */}
      <div className="mt-2 flex items-center justify-between">
        <MetricsFooter />
        <FeedbackButtons threadId={threadId} prompt={prompt} />
      </div>
    </article>
  );
}
