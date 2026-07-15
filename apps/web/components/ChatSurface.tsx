// Phase 5 Plan 06 Wave 3 — ChatSurface (the runtime-bound chat column).
//
// The right column of the PageShell (UI-SPEC §5.1): the AssistantRuntimeProvider
// + Thread + Composer, with the Phase-5 wiring layered on top of the Phase-4
// surface:
//   - Per-backend bubble dispatch via <MessageBubble/> (UI-09/UI-10/UI-05).
//   - <OverrideDropdown/> in the composer row, left of Send (UI-05 §9.2),
//     bound to useChatThread().setOverrideBackend (D-02 one-shot).
//   - Client-side slash parsing (UI-05 §9.1 / D-04): a leading /openrouter
//     /code /computer token is stripped + mapped to the forced backend before
//     the turn dispatches; /computer while computer-use is OFF shows the
//     inline StreamErrorBanner copy and does NOT send.
//   - Auto-rename on the FIRST user send of a thread (UI-14 / D-08), fired in
//     parallel with the turn via useThreads.autoRenameFromFirstMessage.
//   - <EmptyState/> three sample cards (UI-16) when the active thread has no
//     messages; clicking a card submits the exact prompt immediately.
//
// TEST-COMPAT GUARD (Rule 3): page-shell.test.tsx mocks @assistant-ui/react to
// expose ONLY useMessage + useMessageRuntime, so AssistantRuntimeProvider et al.
// are undefined under the mock. This component renders nothing when the runtime
// primitive is absent — the page-shell test only needs the SidebarProvider
// wrapper from PageShell, and production is unaffected (the primitives are real
// there).
//
// Cross-refs:
//   - apps/web/app/page.tsx (Phase 4 surface this extends)
//   - apps/web/hooks/useChatThread.ts (override one-shot)
//   - apps/web/components/MessageBubble.tsx (dispatch), OverrideDropdown.tsx
//   - apps/web/components/EmptyState.tsx (onSelectPrompt), StreamErrorBanner.tsx
//   - apps/web/lib/slash-parse.ts (parseSlashCommand)
//   - 05-UI-SPEC.md §5/§9/§12 + 05-CONTEXT.md D-02/D-04/D-08
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type React from "react";
import type { UIMessage } from "@ai-sdk/react";
// Namespace import (NOT named imports): page-shell.test.tsx mocks
// @assistant-ui/react with only useMessage + useMessageRuntime. A named import
// of an unlisted export (e.g. AssistantRuntimeProvider) makes vitest's mock
// throw on the binding access. A namespace import yields plain `undefined` for
// the missing members so the TEST-COMPAT GUARD below can detect the mock and
// render nothing without tripping the strict-mock error. Production has the
// real exports.
import * as AUI from "@assistant-ui/react";
import { useChatThread } from "@/hooks/useChatThread";
import { useFirstRunGate } from "@/hooks/useFirstRunGate";
import { ChatBubble } from "@/components/ChatBubble";
import { MessageBubble } from "@/components/MessageBubble";
import { CompareView } from "@/components/CompareView";
import type { CompareCompletion } from "@/components/CompareView";
import { EmptyState } from "@/components/EmptyState";
import { FirstRunModal } from "@/components/FirstRunModal";
import { HistorySkeleton } from "@/components/HistorySkeleton";
import { NetworkDownBanner } from "@/components/NetworkDownBanner";
import { OverrideDropdown } from "@/components/OverrideDropdown";
import { StreamErrorBanner } from "@/components/StreamErrorBanner";
import { getHealth } from "@/lib/api-client";
import { MessagesResponseSchema } from "@/lib/chunk-schemas";
import { reconstructUIMessages } from "@/lib/reconstruct-messages";
import { parseSlashCommand } from "@/lib/slash-parse";
import { Icon } from "@/components/Icon";
import { cn } from "@/lib/cn";

export interface ChatSurfaceProps {
  activeThreadId: string | null;
  autoRenameFromFirstMessage: (
    threadId: string,
    firstUserMessage: string,
  ) => Promise<void>;
}

// The two models that DEFAULT the Compare lanes (matches Task 1's backend
// choice — turn.py `_COMPARE_DEFAULT_MODELS`). `id` is the OpenRouter slug
// forced per lane (allowlist-validated server-side, T-07-16); `label` is the
// display name for the LOCKED card head "{Model} · {latency}s · ${cost}".
const COMPARE_LANE_MODELS: ReadonlyArray<{ id: string; label: string }> = [
  { id: "openai/gpt-5", label: "GPT-5" },
  { id: "anthropic/claude-sonnet-4.5", label: "Claude Sonnet 4.5" },
];

// Drain the lane-tagged AI-SDK stream returned by /api/compare, folding each
// lane's text-delta chunks + terminal metrics into a CompareCompletion. The
// proxy emits `data: {lane, chunk}` lines (chunk = an AI-SDK UI-message-stream
// chunk: text-delta / data-metrics / finish-lane). onUpdate fires on each
// chunk so the 2-up view streams in.
async function consumeCompareStream(
  body: ReadableStream<Uint8Array>,
  onUpdate: (lanes: { text: string; latency: number; cost: number }[]) => void,
): Promise<void> {
  const lanes = [
    { text: "", latency: 0, cost: 0 },
    { text: "", latency: 0, cost: 0 },
  ];
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl: number;
    while ((nl = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, nl);
      buffer = buffer.slice(nl + 2);
      const line = block.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      let parsed: { lane?: number; chunk?: Record<string, unknown> };
      try {
        parsed = JSON.parse(line.slice(6));
      } catch {
        continue;
      }
      const lane = parsed.lane === 1 ? 1 : 0;
      const chunk = parsed.chunk ?? {};
      if (chunk.type === "text-delta" && typeof chunk.delta === "string") {
        lanes[lane].text += chunk.delta;
      } else if (chunk.type === "data-metrics") {
        const data = (chunk.data ?? {}) as Record<string, unknown>;
        const ms = typeof data.latency_ms === "number" ? data.latency_ms : 0;
        lanes[lane].latency = Math.round((ms / 1000) * 100) / 100;
        lanes[lane].cost = typeof data.cost_usd === "number" ? data.cost_usd : 0;
      }
      onUpdate(lanes.map((l) => ({ ...l })));
    }
  }
}

// User-role message body (clone of page.tsx UserMessage).
function UserMessage(): React.JSX.Element {
  const MessagePrimitive = AUI.MessagePrimitive;
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

export function ChatSurface({
  activeThreadId,
  autoRenameFromFirstMessage,
}: ChatSurfaceProps): React.JSX.Element | null {
  // Phase 8 Plan 08-03 (SC-3 / D-02/03/04) — restore hydration state.
  //   - `history === undefined`  → fetch in flight (show the skeleton for a real
  //                                existing thread; D-02 bridge).
  //   - `history === UIMessage[]` → reconstructed rows ready to seed (empty array
  //                                = a 0-message thread → falls through to the
  //                                Plasma <ThreadPrimitive.Empty>; D-03).
  //   - `fetchError`             → a non-404 fetch failure → inline retriable
  //                                StreamErrorBanner (NOT a toast; D-03).
  // The reconstructed `history` is seeded into the runtime via
  // `useChatThread(activeThreadId, history)`; the `key={activeThreadId}` remount
  // below re-runs the hook per thread so the seed is atomic. There is NO client
  // history cache — every `activeThreadId` change re-fetches from the Next proxy
  // (D-04 anti-pattern: SQLite/FastAPI is the source of truth).
  const [history, setHistory] = useState<UIMessage[] | undefined>(undefined);
  const [fetchError, setFetchError] = useState(false);
  // Monotonic token so a slow in-flight fetch for a previous thread can never
  // commit its result over a newer selection (belt for the abort + the remount).
  const fetchSeqRef = useRef(0);

  const { runtime, threadId, setOverrideBackend, overrideBackend } =
    useChatThread(activeThreadId, history);
  const { needsKey } = useFirstRunGate();

  // Abortable history fetch on EVERY activeThreadId change + on first mount of an
  // existing thread (D-04 re-fetch; mirrors the computer-use health-poll
  // cleanup-with-`cancelled` shape below). The browser fetches the Next proxy
  // path ONLY — never a FastAPI host (T-08-03-Disclo / SC-2). The payload is
  // Zod-validated at the client trust boundary (T-08-03-DoS) before
  // reconstruction; a parse/network failure renders the inline banner instead of
  // crashing the surface.
  const loadHistory = useCallback((threadIdToLoad: string | null): (() => void) => {
    // Brand-new session (no active thread) — nothing to restore. Leave history
    // undefined; the brand-new-thread guard below keeps the skeleton hidden and
    // the default-thread path (useChatThread's first-mount effect) runs.
    if (!threadIdToLoad) {
      setHistory(undefined);
      setFetchError(false);
      return () => undefined;
    }
    const seq = ++fetchSeqRef.current;
    const controller = new AbortController();
    // Reset to the loading state synchronously so the keyed remount never seeds
    // the new thread's runtime with the previous thread's messages.
    setHistory(undefined);
    setFetchError(false);
    void (async () => {
      try {
        const res = await fetch(
          `/api/threads/${encodeURIComponent(threadIdToLoad)}/messages`,
          { signal: controller.signal },
        );
        // A 404 (deleted/unknown thread) is a not-found state, not an error —
        // fall back to the empty state (UI-SPEC §Copywriting 404 default).
        if (res.status === 404) {
          if (seq === fetchSeqRef.current) setHistory([]);
          return;
        }
        if (!res.ok) {
          // 503 (proxy → FastAPI unreachable) is covered page-level by
          // NetworkDownBanner; any other non-OK status shows the inline banner.
          if (seq === fetchSeqRef.current) setFetchError(true);
          return;
        }
        const json: unknown = await res.json();
        const parsed = MessagesResponseSchema.safeParse(json);
        if (!parsed.success) {
          if (seq === fetchSeqRef.current) setFetchError(true);
          return;
        }
        const messages = reconstructUIMessages(parsed.data);
        if (seq === fetchSeqRef.current) setHistory(messages);
      } catch {
        // AbortError (thread switched / unmount) lands here too — only commit the
        // error if this is still the latest fetch (an abort is not a failure).
        if (!controller.signal.aborted && seq === fetchSeqRef.current) {
          setFetchError(true);
        }
      }
    })();
    return () => controller.abort();
  }, []);

  useEffect(() => loadHistory(activeThreadId), [activeThreadId, loadHistory]);

  // computer-use availability — read from /api/health so the OverrideDropdown
  // disabled state + the /computer slash guard both reflect the live strict-AND
  // gate (D-06). Re-read on the 5s cadence the rest of the UI uses.
  const [computerUseEnabled, setComputerUseEnabled] = useState(false);
  useEffect(() => {
    let cancelled = false;
    const read = async (): Promise<void> => {
      try {
        const health = await getHealth();
        if (cancelled) return;
        const status = (health.adapters ?? {})?.computer_use?.status;
        setComputerUseEnabled(status === "ready");
      } catch {
        if (!cancelled) setComputerUseEnabled(false);
      }
    };
    void read();
    const id = setInterval(read, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  // Inline /computer-off error (UI-SPEC §9.1) — shown above the composer when a
  // /computer slash command is used while computer-use is off; cleared on the
  // next successful send.
  const [slashError, setSlashError] = useState(false);

  // Compare toggle (07-04 seam; 07-08 wires the next send into the Compare view).
  // Default off. When ON, the next send goes to /api/compare and renders a 2-up
  // CompareView instead of a single assistant message; OFF leaves the single-turn
  // path (assistant-ui runtime → /api/chat) entirely unchanged.
  const [compareMode, setCompareMode] = useState(false);
  const [compareCompletions, setCompareCompletions] = useState<
    CompareCompletion[] | null
  >(null);
  const compareAbortRef = useRef<AbortController | null>(null);

  // Drive one Compare run: POST the prompt + the two lane models to the Next
  // /api/compare proxy (UI-17 — never FastAPI directly), then fold the
  // lane-tagged stream into the 2-up CompareView. The forced model ids are
  // validated against the allowlist server-side (T-07-16).
  const runCompare = useRef<(text: string) => void>(() => undefined);
  runCompare.current = (text: string): void => {
    const tid = activeThreadId ?? threadId;
    if (!tid || !text.trim()) return;
    compareAbortRef.current?.abort();
    const controller = new AbortController();
    compareAbortRef.current = controller;
    // Seed both lanes empty so the 2-up grid renders immediately with heads.
    setCompareCompletions(
      COMPARE_LANE_MODELS.map((m) => ({
        model: m.label,
        latency: 0,
        cost: 0,
        text: "",
      })),
    );
    void (async () => {
      try {
        const res = await fetch("/api/compare", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: text,
            threadId: tid,
            models: COMPARE_LANE_MODELS.map((m) => m.id),
          }),
          signal: controller.signal,
        });
        if (!res.ok || !res.body) return;
        await consumeCompareStream(res.body, (lanes) => {
          setCompareCompletions(
            lanes.map((l, i) => ({
              model: COMPARE_LANE_MODELS[i].label,
              latency: l.latency,
              cost: l.cost,
              text: l.text,
              isStreamingComplete: false,
            })),
          );
        });
        // Mark both lanes complete so the one-shot code highlight runs.
        setCompareCompletions((prev) =>
          prev
            ? prev.map((c) => ({ ...c, isStreamingComplete: true }))
            : prev,
        );
      } catch {
        // Aborted or network down — leave whatever streamed so far on screen.
      }
    })();
  };

  // Abort any in-flight compare stream on unmount.
  useEffect(() => {
    return () => compareAbortRef.current?.abort();
  }, []);

  // Track whether the active thread has already had its first user send (so the
  // auto-rename fires once per thread — D-10 belt; the helper has the primary
  // guard).
  const firstSendDoneRef = useRef<Set<string>>(new Set());

  const composerDisabled = threadId === null || needsKey;
  const effectiveThreadId = activeThreadId ?? threadId;

  // D-02 skeleton gate: show ONLY while a real existing thread's history is in
  // flight (activeThreadId set, history not yet resolved) and no fetch error is
  // up. A brand-new session (activeThreadId null) never shows it; a resolved
  // fetch (rows, [], or 404→[]) hides it so messages / the empty state render.
  const showSkeleton =
    activeThreadId !== null && history === undefined && !fetchError;

  // Per-thread remount key (08-03 / D-04, RESEARCH §Pattern 2). It encodes BOTH
  // the thread id AND whether its seed is ready, because `useChat`'s
  // `ChatInit.messages` is read ONCE at construction (`@ai-sdk/react` Chat ctor —
  // ReactChatState(messages)) and is NOT reactive: a `messages` change after
  // mount does NOT re-seed an existing runtime. So the runtime must (re)mount
  // AFTER `history` resolves. The key flips `…:loading` → `…:ready` when the
  // fetch settles, forcing a remount whose construction sees the populated seed.
  // During `…:loading` the empty runtime is mounted (composer stays usable) but
  // <ThreadPrimitive.Empty> is suppressed (showSkeleton) so only the skeleton is
  // visible; switching threads bumps the id segment and remounts atomically
  // (aborts the in-flight stream — Pitfall 5).
  const runtimeKey = `${activeThreadId ?? "none"}:${
    history === undefined ? "loading" : "ready"
  }`;

  // TEST-COMPAT GUARD — when the assistant-ui runtime primitives are mocked
  // away (page-shell.test.tsx mocks @assistant-ui/react with only useMessage +
  // useMessageRuntime), accessing the missing exports throws via vitest's
  // strict-mock getter. We catch that and render nothing — the page-shell test
  // only needs PageShell's SidebarProvider wrapper. Production has the real
  // exports so this path is never taken outside the mock.
  let AssistantRuntimeProvider: typeof AUI.AssistantRuntimeProvider;
  let ThreadPrimitive: typeof AUI.ThreadPrimitive;
  let ComposerPrimitive: typeof AUI.ComposerPrimitive;
  try {
    AssistantRuntimeProvider = AUI.AssistantRuntimeProvider;
    ThreadPrimitive = AUI.ThreadPrimitive;
    ComposerPrimitive = AUI.ComposerPrimitive;
  } catch {
    return null;
  }
  // Real production exports are React components: in @assistant-ui/react 0.14.x
  // AssistantRuntimeProvider is a memo/forwardRef object (typeof "object"), NOT a
  // plain function. Guard on PRESENCE only — it is undefined under the page-shell
  // test mock. The previous `typeof !== "function"` check matched the real object
  // in production and returned null, blanking the entire chat surface (the
  // composer never mounted).
  if (AssistantRuntimeProvider == null) return null;

  return (
    <main className="flex-1 overflow-hidden bg-[var(--bg)]">
      <FirstRunModal open={needsKey} />
      {/* Per-thread remount keyed on activeThreadId (08-03 / D-04, RESEARCH
          §Pattern 2): `runtimeKey` = `${activeThreadId}:${loading|ready}`.
          Switching threads bumps the id segment and unmounts the prior runtime
          subtree, which aborts the in-flight stream + clears the composer
          atomically, so a switch is NEVER blocked (Pitfall 5); the skeleton
          (D-02) bridges the gap. The loading→ready flip remounts the runtime
          AFTER `history` resolves so `useChatThread`'s seed is present at the
          construction that renders the restored rows (the `key={activeThreadId}`
          contract, extended for the async seed — see runtimeKey above). */}
      <AssistantRuntimeProvider key={runtimeKey} runtime={runtime}>
        <ThreadPrimitive.Root className="flex flex-col h-full">
          <ThreadPrimitive.Viewport className="flex-1 overflow-y-auto">
            <div className="max-w-3xl mx-auto px-4 py-6">
              {/* D-02 skeleton — shown WHILE history is in flight for a REAL
                  existing thread (activeThreadId set) and no fetch error. A
                  brand-new session (activeThreadId null) or a resolved fetch
                  hides it; a 0-message thread resolves history to [] and falls
                  through to <ThreadPrimitive.Empty> below. */}
              {showSkeleton ? <HistorySkeleton /> : null}
              {/* D-03 restore fetch-failure — inline retriable banner (NOT a
                  toast). "Try again" re-fetches GET …/messages. A downed proxy
                  (503) is covered page-level by NetworkDownBanner below. */}
              {fetchError ? (
                <div className="mb-4">
                  <StreamErrorBanner
                    code="internal_error"
                    message="Couldn't load this conversation's history."
                    retriable
                    onRetry={() => loadHistory(activeThreadId)}
                  />
                </div>
              ) : null}
              {/* Suppress the Plasma empty state WHILE the skeleton is bridging
                  (history undefined): the runtime is momentarily empty during the
                  fetch, so an un-gated <ThreadPrimitive.Empty> would flash the
                  empty-state hero behind the skeleton. Once history resolves to
                  [] (0-message / 404 thread) the skeleton hides and the empty
                  state renders normally (D-03). */}
              {showSkeleton ? null : (
                <ThreadPrimitive.Empty>
                  <EmptyStateSubmit />
                </ThreadPrimitive.Empty>
              )}
              <ThreadPrimitive.Messages
                components={{
                  UserMessage,
                  AssistantMessage: () => (
                    <MessageBubble
                      threadId={effectiveThreadId}
                      overrideBackend={overrideBackend}
                      onOverride={setOverrideBackend}
                      computerUseEnabled={computerUseEnabled}
                    />
                  ),
                }}
              />
              {/* Compare toggle ON → the next send renders here as a 2-up
                  CompareView (Seam A). OFF → this is absent and the single-turn
                  thread above is unchanged. */}
              {compareMode && compareCompletions && (
                <CompareView completions={compareCompletions} />
              )}
            </div>
          </ThreadPrimitive.Viewport>

          <NetworkDownBanner />

          {slashError && (
            <div className="mx-auto max-w-3xl px-4 mb-2 w-full">
              <StreamErrorBanner
                code="validation_error"
                message="Computer use is off. Turn it on in settings to use this command."
                retriable={false}
                onRetry={() => undefined}
              />
            </div>
          )}

          <ComposerPrimitive.Root className="sticky bottom-0 px-7 pt-4 pb-[22px] bg-gradient-to-t from-[var(--bg)] via-[var(--bg)] to-transparent">
            <div className="mx-auto w-full max-w-[760px] rounded-[14px] border border-[var(--line)] bg-[var(--surface)] px-3 pt-3 pb-2 shadow-[var(--shadow-sm)] transition-shadow duration-[120ms] focus-within:border-[var(--accent)] focus-within:shadow-[var(--shadow-focus)]">
              <CompareAwareInput
                compareMode={compareMode}
                disabled={composerDisabled}
                onCompareSend={(text) => {
                  const tid = effectiveThreadId;
                  if (tid && !firstSendDoneRef.current.has(tid)) {
                    firstSendDoneRef.current.add(tid);
                    void autoRenameFromFirstMessage(tid, text);
                  }
                  runCompare.current(text);
                }}
              />
              {/* Story 7.3 (answer-forward): the deferred attachment/voice/web
                  shells (paperclip/image/mic/globe) were removed — dead
                  affordances with no backend this phase. The toolbar keeps only
                  the WIRED controls: Compare, model override, and Send. */}
              <div className="mt-2 flex items-center gap-1">
                <button
                  type="button"
                  aria-pressed={compareMode}
                  onClick={() => setCompareMode((v) => !v)}
                  className={cn(
                    "ml-1 inline-flex items-center gap-1 rounded-full border px-2.5 py-1 font-[var(--font-mono-plasma)] text-[10.5px] font-medium uppercase tracking-[0.04em] transition-colors",
                    compareMode
                      ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                      : "border-[var(--line)] text-[var(--ink-3)] hover:bg-[var(--surface-2)]",
                  )}
                >
                  <Icon name="compare" size={14} />
                  Compare
                </button>
                <div className="ml-auto flex items-center gap-1.5">
                  <OverrideDropdown
                    value={overrideBackend}
                    onChange={setOverrideBackend}
                    computerUseEnabled={computerUseEnabled}
                  />
                  <SlashAwareSend
                    disabled={composerDisabled}
                    computerUseEnabled={computerUseEnabled}
                    compareMode={compareMode}
                    onCompareSend={(text) => runCompare.current(text)}
                    onForceBackend={setOverrideBackend}
                    onSlashError={setSlashError}
                    onFirstSend={(text) => {
                      const tid = effectiveThreadId;
                      if (!tid) return;
                      if (firstSendDoneRef.current.has(tid)) return;
                      firstSendDoneRef.current.add(tid);
                      void autoRenameFromFirstMessage(tid, text);
                    }}
                  />
                  <ComposerPrimitive.Cancel
                    aria-label="Stop generating"
                    className="inline-flex h-8 w-8 items-center justify-center rounded-[9px] bg-[var(--surface-2)] text-[var(--ink-2)] hover:bg-[var(--line)] focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]"
                  >
                    <Icon name="x" size={16} />
                  </ComposerPrimitive.Cancel>
                </div>
              </div>
              <div className="mt-1.5 font-[var(--font-mono-plasma)] text-[10.5px] uppercase tracking-[0.08em] text-[var(--ink-4)]">
                ↵ send · ⇧ ↵ newline · ⌘ K commands
              </div>
            </div>
          </ComposerPrimitive.Root>
        </ThreadPrimitive.Root>
      </AssistantRuntimeProvider>
    </main>
  );
}

// Composer textarea with a compare-aware Enter interceptor. Lives inside the
// runtime context so it can read + clear the composer draft. When compareMode
// is ON, Enter (without Shift) fans the draft out to /api/compare and does NOT
// invoke the single-turn runtime submit (→ /api/chat); when OFF, Enter falls
// through to assistant-ui's native submit unchanged.
function CompareAwareInput({
  compareMode,
  disabled,
  onCompareSend,
}: {
  compareMode: boolean;
  disabled: boolean;
  onCompareSend: (text: string) => void;
}): React.JSX.Element {
  const composer = AUI.useComposerRuntime();
  const ComposerPrimitive = AUI.ComposerPrimitive;
  return (
    <ComposerPrimitive.Input
      placeholder="Ask anything — we'll route it to the best model."
      disabled={disabled}
      rows={1}
      onKeyDownCapture={(e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        // Only hijack Enter-to-send in compare mode; Shift+Enter (newline) and
        // all keys in normal mode pass through to assistant-ui untouched.
        if (!compareMode || e.key !== "Enter" || e.shiftKey) return;
        e.preventDefault();
        e.stopPropagation();
        const text = composer.getState().text ?? "";
        if (!text.trim()) return;
        onCompareSend(text);
        composer.setText("");
      }}
      className="w-full min-h-[22px] max-h-[200px] resize-none [field-sizing:content] bg-transparent font-[var(--font-body)] text-[14.5px] leading-[1.5] tracking-[-0.005em] text-[var(--ink)] outline-none placeholder:text-[var(--ink-4)] disabled:cursor-not-allowed disabled:opacity-60"
    />
  );
}

// EmptyState wired to submit the sample prompt immediately (UI-16). Lives inside
// the runtime context so it can drive the composer runtime to append + send.
function EmptyStateSubmit(): React.JSX.Element {
  const composer = AUI.useComposerRuntime();
  return (
    <EmptyState
      onSelectPrompt={(prompt) => {
        // D-01: fill the composer draft ONLY — the user refines, then sends.
        // (The Phase-5 immediate-submit behavior is removed per O-1/D-01.)
        composer.setText(prompt);
      }}
    />
  );
}

// A Send control that intercepts the composer text for slash parsing + override
// dispatch + auto-rename BEFORE delegating to the runtime send. Replaces the
// bare ComposerPrimitive.Send so the §9.1 slash semantics run client-side.
function SlashAwareSend({
  disabled,
  computerUseEnabled,
  compareMode,
  onCompareSend,
  onForceBackend,
  onSlashError,
  onFirstSend,
}: {
  disabled: boolean;
  computerUseEnabled: boolean;
  compareMode: boolean;
  onCompareSend: (text: string) => void;
  onForceBackend: (backend: import("@/lib/types").Backend | null) => void;
  onSlashError: (show: boolean) => void;
  onFirstSend: (text: string) => void;
}): React.JSX.Element {
  const composer = AUI.useComposerRuntime();

  function handleSend(): void {
    const text = composer.getState().text ?? "";
    const parsed = parseSlashCommand(text);

    // Compare mode (07-08): the next send fans out to /api/compare's two
    // forced-model lanes and renders a 2-up CompareView instead of a single
    // assistant turn. Slash overrides do not apply (Compare picks its own two
    // models); we still strip a leading slash token for a clean compare prompt.
    // The single-turn runtime (composer.send → /api/chat) is NOT invoked.
    if (compareMode) {
      onSlashError(false);
      onFirstSend(parsed.prompt);
      onCompareSend(parsed.prompt);
      composer.setText("");
      return;
    }

    if (parsed.backend !== null) {
      // /computer while computer-use is OFF → inline error, do NOT send.
      if (parsed.backend === "computer_use" && !computerUseEnabled) {
        onSlashError(true);
        return;
      }
      // Strip the token + arm the one-shot override.
      composer.setText(parsed.prompt);
      onForceBackend(parsed.backend);
    }

    onSlashError(false);
    onFirstSend(parsed.prompt);
    void composer.send();
  }

  return (
    <button
      type="button"
      aria-label="Send"
      disabled={disabled}
      onClick={handleSend}
      className="inline-flex h-8 w-8 items-center justify-center rounded-[9px] bg-[var(--accent)] text-white transition-colors hover:bg-[var(--accent-hover)] disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]"
    >
      <Icon name="arrowUp" size={16} />
    </button>
  );
}
