"use client";

// Plan 04-05 Wave 4 — ChatPage (the visible chat surface).
//
// Replaces the Plan 01 Wave-0 placeholder with the full
// AssistantRuntimeProvider + Thread + Composer composition per RESEARCH
// Pattern 1. Mounts:
//   - Sticky header (UI-SPEC §5.1) — "Prompt-Optimizer" + Settings link
//   - Main scroll area + max-w-3xl gutter (UI-SPEC §3)
//   - Thread.Empty → EmptyState centered tagline (UI-SPEC §11)
//   - Thread.Messages with UserMessage + AssistantMessage variants
//     - AssistantMessage renders RoutingChip + ChatBubble + MetricsFooter
//     - Regenerate is LIVE-WIRED to useMessageRuntime().reload() (D-14,
//       Blocker 3 — no TODO stub remaining)
//   - Composer.Root sticky-bottom with Input + Send + Cancel/Stop
//
// All hooks rules respected: useMessageRuntime is called inside the
// AssistantMessage component body where it has a valid MessageRuntime
// context (it would throw if called at top level).
//
// Cross-refs:
//   - 04-RESEARCH.md §Pattern 1 (mount), §Pattern 3 (reload), Pitfall 8 (use client)
//   - 04-UI-SPEC.md §3 (layout), §5 (header), §8 (bubble), §9 (composer), §16 (page title)
//   - 04-CONTEXT.md D-14 (Regenerate live)
//   - Plan 04-05 Blocker 3 (live-wired reload, NO TODO)

import Link from "next/link";
import { Settings } from "lucide-react";
import {
  AssistantRuntimeProvider,
  ThreadPrimitive,
  ComposerPrimitive,
  MessagePrimitive,
  useMessage,
  useMessageRuntime,
} from "@assistant-ui/react";
import { useChatThread } from "@/hooks/useChatThread";
import { useFirstRunGate } from "@/hooks/useFirstRunGate";
import { ChatBubble } from "@/components/ChatBubble";
import { RoutingChip } from "@/components/RoutingChip";
import { MetricsFooter } from "@/components/MetricsFooter";
import { EmptyState } from "@/components/EmptyState";
import { FirstRunModal } from "@/components/FirstRunModal";
import { NetworkDownBanner } from "@/components/NetworkDownBanner";

// Renders the body of a user-role message: just the bubble with no
// action row + the underlying MessagePrimitive.Content (which Plan 06
// will replace with the MarkdownRenderer for the assistant variant).
function UserMessage(): React.JSX.Element {
  return (
    <div className="mb-4">
      <ChatBubble role="user" rawMarkdown="">
        <div className="whitespace-pre-wrap">
          <MessagePrimitive.Content />
        </div>
      </ChatBubble>
    </div>
  );
}

// Minimal structural shape of the message state useMessage() returns.
// Plan 05 SUMMARY established that v0.14.5 exposes the raw ThreadMessage
// with a `content` array (not a wrapped MessageState.parts). We read it
// directly here to compute (a) the rawMarkdown string from text parts and
// (b) the isStreamingComplete signal — both via the `data-metrics` part
// presence (Plan 02 contract: data-metrics is emitted ONLY on Done, so
// presence means the stream is complete) AND the `status.type` field
// (assistant-ui's canonical signal). We use status.type when available
// and fall back to the data-metrics check for runtimes where status is
// absent during the render.
type PartLike = { readonly type: string };
type TextPartLike = { readonly type: "text"; readonly text: string };
type DataPartLike = {
  readonly type: "data";
  readonly name?: string;
};
type MessageStateShape = {
  readonly id?: string;
  readonly content?: ReadonlyArray<PartLike>;
  readonly status?: { readonly type?: string };
};
function isTextPart(p: PartLike): p is TextPartLike {
  return p.type === "text";
}
function isMetricsPart(p: PartLike): p is DataPartLike {
  return p.type === "data" && (p as { name?: string }).name === "metrics";
}

// Renders the body of an assistant-role message: the RoutingChip ABOVE,
// the ChatBubble shell wrapping the streamed content, and the
// MetricsFooter BELOW. Regenerate is wired LIVE to the assistant-ui
// reload action (Blocker 3 fix — no TODO stub, no console.warn).
//
// Plan 04-06 Wave 5: extracts `rawMarkdown` from the message's text parts
// AND computes `isStreamingComplete` from the message status / data-metrics
// presence; both flow into ChatBubble → MarkdownRenderer → StreamingCodeBlock
// so fenced code blocks render plain <pre> during streaming and highlight
// exactly once on Done (RESEARCH §Pattern 5b + Pitfall 5).
function AssistantMessage(): React.JSX.Element {
  // useMessageRuntime returns the runtime for the CURRENT message — the
  // one this component is mounted under. Calling .reload() issues a fresh
  // turn that REPLACES this message with a regenerated one (assistant-ui's
  // built-in reload semantics; D-14 says "Regenerate appends a new turn"
  // which is satisfied because reload() pushes a fresh assistant message
  // into the messages array).
  const messageRuntime = useMessageRuntime();
  const handleRegenerate = (): void => {
    messageRuntime.reload();
  };

  // Subscribe to the message state for rawMarkdown extraction +
  // isStreamingComplete derivation. Plan 04-05 SUMMARY confirmed that
  // useMessage() returns the raw ThreadMessage with a `content` array.
  const message = useMessage({ optional: true }) as MessageStateShape | null;
  const messageId = message?.id ?? "";
  const textParts = (message?.content ?? []).filter(isTextPart);
  const rawMarkdown = textParts.map((p) => p.text).join("");
  // Two-source isStreamingComplete signal — primary via assistant-ui's
  // status.type === "complete"; fallback via data-metrics part presence
  // (Plan 02 translator emits data-metrics only on Done).
  const hasMetricsPart = (message?.content ?? []).some(isMetricsPart);
  const statusComplete = message?.status?.type === "complete";
  const isStreamingComplete = statusComplete || hasMetricsPart;

  return (
    <div className="mb-6">
      <div className="mb-2">
        <RoutingChip />
      </div>
      <ChatBubble
        role="assistant"
        rawMarkdown={rawMarkdown}
        isStreamingComplete={isStreamingComplete}
        messageId={messageId}
        onRegenerate={handleRegenerate}
      />
      <MetricsFooter />
    </div>
  );
}

export default function ChatPage(): React.JSX.Element {
  const { runtime, threadId } = useChatThread();
  // Plan 04-07 Wave 6 — the boot-time key gate. Drives:
  //   - FirstRunModal open state (open={needsKey})
  //   - composer disabled state (disabled={composerDisabled || needsKey})
  // Network-down is the SEPARATE surface: NetworkDownBanner polls
  // /api/health on its own 5s timer and surfaces the §17 string when
  // the proxy can't reach uvicorn. The first-run gate stays
  // {isReady:false, needsKey:false} in that case so the modal does NOT
  // open on every transient outage.
  const { needsKey } = useFirstRunGate();

  // Until the default thread id is loaded (or auto-created on first run),
  // the chat route handler rejects with 400 ("threadId is required").
  // Plan 07 layers on top: also disable when the user has no key set
  // (needsKey === true), so the composer is doubly-gated.
  const composerDisabled = threadId === null || needsKey;

  return (
    <div className="flex flex-col h-screen">
      {/* Sticky header — UI-SPEC §5.1. */}
      <header className="h-14 border-b border-slate-200 bg-white sticky top-0 z-10 px-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-900">
          Prompt-Optimizer
        </h1>
        <Link
          href="/settings"
          aria-label="Settings"
          className="inline-flex h-9 w-9 items-center justify-center rounded-md text-slate-700 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2"
        >
          <Settings className="h-5 w-5" />
        </Link>
      </header>

      {/* First-run modal — Plan 04-07. Pitfall 9 prevention (no Escape /
          outside-click dismiss) lives inside FirstRunModal itself.
          Returns null when open=false so this is zero-overhead in the
          happy path. */}
      <FirstRunModal open={needsKey} />

      {/* Main message area — fills remaining vertical space; Composer is
          rendered inside Thread.Root so assistant-ui can wire it up. */}
      <main className="flex-1 overflow-hidden bg-white">
        <AssistantRuntimeProvider runtime={runtime}>
          <ThreadPrimitive.Root className="flex flex-col h-full">
            <ThreadPrimitive.Viewport className="flex-1 overflow-y-auto">
              <div className="max-w-3xl mx-auto px-4 py-6">
                <ThreadPrimitive.Empty>
                  <EmptyState />
                </ThreadPrimitive.Empty>
                <ThreadPrimitive.Messages
                  components={{
                    UserMessage,
                    AssistantMessage,
                  }}
                />
              </div>
            </ThreadPrimitive.Viewport>

            {/* NetworkDownBanner sits ABOVE the composer (UI-SPEC §13).
                Renders nothing when /api/health is reachable. */}
            <NetworkDownBanner />

            {/* Composer — sticky bottom, UI-SPEC §9. The Cancel primitive
                is automatically wired by useChatRuntime to runtime.stop()
                so partial preservation works out-of-the-box. */}
            <ComposerPrimitive.Root className="border-t border-slate-200 bg-white px-4 py-3 sticky bottom-0">
              <div className="max-w-3xl mx-auto flex items-end gap-2">
                <ComposerPrimitive.Input
                  placeholder="Type a message…"
                  disabled={composerDisabled}
                  className="flex-1 min-h-12 max-h-48 resize-none rounded-md border border-slate-300 bg-white px-3 py-2 text-sm leading-normal text-slate-900 placeholder:text-slate-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2 disabled:bg-slate-50 disabled:cursor-not-allowed"
                />
                <ComposerPrimitive.Send
                  aria-label="Send message"
                  disabled={composerDisabled}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-md bg-slate-900 text-white hover:bg-slate-800 disabled:bg-slate-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2"
                >
                  Send
                </ComposerPrimitive.Send>
                <ComposerPrimitive.Cancel
                  aria-label="Stop generating"
                  className="inline-flex h-9 w-9 items-center justify-center rounded-md bg-slate-900 text-white hover:bg-slate-800 disabled:bg-slate-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2"
                >
                  Stop
                </ComposerPrimitive.Cancel>
              </div>
            </ComposerPrimitive.Root>
          </ThreadPrimitive.Root>
        </AssistantRuntimeProvider>
      </main>
    </div>
  );
}
