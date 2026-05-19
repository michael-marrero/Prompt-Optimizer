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
  useMessageRuntime,
} from "@assistant-ui/react";
import { useChatThread } from "@/hooks/useChatThread";
import { ChatBubble } from "@/components/ChatBubble";
import { RoutingChip } from "@/components/RoutingChip";
import { MetricsFooter } from "@/components/MetricsFooter";
import { EmptyState } from "@/components/EmptyState";

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

// Renders the body of an assistant-role message: the RoutingChip ABOVE,
// the ChatBubble shell wrapping the streamed content, and the
// MetricsFooter BELOW. Regenerate is wired LIVE to the assistant-ui
// reload action (Blocker 3 fix — no TODO stub, no console.warn).
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

  return (
    <div className="mb-6">
      <div className="mb-2">
        <RoutingChip />
      </div>
      <ChatBubble
        role="assistant"
        rawMarkdown=""
        onRegenerate={handleRegenerate}
      >
        {/* Plan 06 replaces this children slot's VALUE with the memoized
            MarkdownRenderer. Plan 05 mounts MessagePrimitive.Content as
            a pre-formatted text node so the chat surface is observable
            during smoke testing. */}
        <div className="whitespace-pre-wrap text-slate-900">
          <MessagePrimitive.Content />
        </div>
      </ChatBubble>
      <MetricsFooter />
    </div>
  );
}

export default function ChatPage(): React.JSX.Element {
  const { runtime } = useChatThread();

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

            {/* Composer — sticky bottom, UI-SPEC §9. The Cancel primitive
                is automatically wired by useChatRuntime to runtime.stop()
                so partial preservation works out-of-the-box. */}
            <ComposerPrimitive.Root className="border-t border-slate-200 bg-white px-4 py-3 sticky bottom-0">
              <div className="max-w-3xl mx-auto flex items-end gap-2">
                <ComposerPrimitive.Input
                  placeholder="Type a message…"
                  className="flex-1 min-h-12 max-h-48 resize-none rounded-md border border-slate-300 bg-white px-3 py-2 text-sm leading-normal text-slate-900 placeholder:text-slate-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2"
                />
                <ComposerPrimitive.Send
                  aria-label="Send message"
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
