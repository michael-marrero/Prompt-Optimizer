// Phase 7 Plan 07-05 (UI-REDESIGN-10) — Plasma sidebar.
//
// Rebuilds the Phase-5 nav into the Plasma 256px sidebar: brand lockup (gradient
// router-fan mark + Instrument Sans wordmark + mono sub), an accent New Chat
// button (⌘N kbd), grouped history (Today / Yesterday / Previous 7 days /
// Earlier), and a footer (avatar + name + plan + gear → Routing Preferences).
//
// PRESERVED from Phase 5 (D-05): the props contract (threads/activeThreadId/
// onSelect/onCreate/onRename/onDelete, all optional → useThreads fallback), the
// `data-testid="thread-list"` ordered newest-first, ThreadRow's aria-current +
// CRUD, and the delete-active reselect. Group labels never end in "chat", so the
// app-sidebar test's `within(thread-list).getAllByText(/chat$/)` still returns
// only thread titles in newest-first DOM order.
//
// Cross-refs:
//   - apps/web/components/ThreadRow.tsx (Plasma row + --danger delete, 07-05)
//   - apps/web/components/Icon.tsx (07-02, D-04 depicted surface)
//   - apps/web/hooks/useThreads.ts (self-managed fallback)
//   - 07-UI-SPEC.md §Spacing/§Color/§Copywriting
"use client";

import { Fragment } from "react";
import { ThreadRow } from "@/components/ThreadRow";
import { Icon } from "@/components/Icon";
import { useThreads, type Thread } from "@/hooks/useThreads";
import { cn } from "@/lib/cn";

export interface AppSidebarProps {
  threads?: Thread[];
  activeThreadId?: string | null;
  onSelect?: (id: string) => void;
  onCreate?: () => void;
  onRename?: (id: string, title: string) => void;
  onDelete?: (id: string) => void;
  /** Opens the Routing Preferences modal (07-07 wires the handler). */
  onOpenRoutingPrefs?: () => void;
}

/** Sort newest-first by updated_at DESC (§6.1). */
function sortNewestFirst(threads: Thread[]): Thread[] {
  return [...threads].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
}

/** Bucket already-sorted (newest-first) threads by recency. Buckets render in
 * newest→oldest order and rows stay newest-first within each, so global DOM
 * order remains newest-first for any "now". */
function bucketByRecency(threads: Thread[]): { label: string; items: Thread[] }[] {
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const todayMs = startOfToday.getTime();
  const day = 86_400_000;
  const order = ["Today", "Yesterday", "Previous 7 days", "Earlier"] as const;
  const buckets: Record<string, Thread[]> = {
    Today: [],
    Yesterday: [],
    "Previous 7 days": [],
    Earlier: [],
  };
  for (const t of threads) {
    const ts = new Date(t.updated_at).getTime();
    if (ts >= todayMs) buckets.Today.push(t);
    else if (ts >= todayMs - day) buckets.Yesterday.push(t);
    else if (ts >= todayMs - 7 * day) buckets["Previous 7 days"].push(t);
    else buckets.Earlier.push(t);
  }
  return order
    .map((label) => ({ label, items: buckets[label] }))
    .filter((g) => g.items.length > 0);
}

export function AppSidebar(props: AppSidebarProps): React.JSX.Element {
  const isControlled = props.threads !== undefined;
  const hook = useThreads({ enabled: !isControlled });

  const threads = isControlled ? props.threads! : hook.threads;
  const activeThreadId = isControlled
    ? (props.activeThreadId ?? null)
    : hook.activeThreadId;
  const onSelect = props.onSelect ?? hook.selectThread;
  const onCreate = props.onCreate ?? hook.createThread;
  const onRename = props.onRename ?? hook.renameThread;
  const onDelete = props.onDelete ?? hook.deleteThread;

  const ordered = sortNewestFirst(threads);
  const groups = bucketByRecency(ordered);

  function handleConfirmDelete(id: string): void {
    if (id === activeThreadId) {
      const remaining = ordered.filter((thread) => thread.id !== id);
      if (remaining.length > 0) onSelect(remaining[0].id);
    }
    onDelete(id);
  }

  return (
    <nav
      aria-label="Chat threads"
      className="flex h-full w-64 flex-col border-r border-[var(--line)] bg-[var(--surface)]"
    >
      {/* Brand lockup */}
      <div className="flex items-center gap-2 px-4 pt-4 pb-2">
        <span
          aria-hidden="true"
          className="h-8 w-8 rounded-[9px] bg-gradient-to-br from-[var(--accent)] via-[var(--accent-2)] to-[var(--accent-3)] flex items-center justify-center text-white"
        >
          <Icon name="sparkle" size={18} />
        </span>
        <span className="flex flex-col leading-tight">
          <span className="font-[var(--font-display)] text-[14px] font-semibold tracking-[-0.025em] text-[var(--ink)]">
            Prompt Optimizer
          </span>
          <span className="font-[var(--font-mono-plasma)] text-[9.5px] font-medium uppercase tracking-[0.08em] text-[var(--ink-3)]">
            auto-router
          </span>
        </span>
      </div>

      {/* New chat */}
      <div className="px-2.5 pb-2">
        <button
          type="button"
          onClick={() => onCreate()}
          className={cn(
            "inline-flex w-full items-center justify-between gap-2 rounded-[9px]",
            "bg-[var(--accent)] px-3 py-2 text-[13px] font-medium text-white",
            "transition-colors hover:bg-[var(--accent-hover)] active:scale-[0.99]",
            "focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]",
          )}
        >
          <span className="inline-flex items-center gap-1.5">
            <Icon name="plus" size={16} />
            <span>New chat</span>
          </span>
          <kbd className="font-[var(--font-mono-plasma)] text-[10px] opacity-80">⌘N</kbd>
        </button>
      </div>

      {/* Grouped history */}
      <div className="flex min-h-0 flex-1 flex-col overflow-auto px-2.5 pb-2">
        <ul data-testid="thread-list" className="flex w-full min-w-0 flex-col gap-0.5">
          {groups.map((group) => (
            <Fragment key={group.label}>
              <li
                aria-hidden="true"
                className="list-none px-2 pt-3 pb-1 font-[var(--font-mono-plasma)] text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--ink-4)]"
              >
                {group.label}
              </li>
              {group.items.map((thread) => (
                <ThreadRow
                  key={thread.id}
                  id={thread.id}
                  title={thread.title}
                  isActive={thread.id === activeThreadId}
                  onSelect={onSelect}
                  onRename={onRename}
                  onConfirmDelete={handleConfirmDelete}
                />
              ))}
            </Fragment>
          ))}
        </ul>
      </div>

      {/* Footer */}
      <div className="flex items-center gap-2 border-t border-[var(--line)] px-3 py-2.5">
        <span
          aria-hidden="true"
          className="h-7 w-7 rounded-full bg-gradient-to-br from-[var(--accent-2)] to-[var(--accent)]"
        />
        <span className="flex flex-1 flex-col leading-tight">
          <span className="text-[12.5px] font-medium text-[var(--ink)]">You</span>
          <span className="font-[var(--font-mono-plasma)] text-[9.5px] uppercase tracking-[0.06em] text-[var(--ink-3)]">
            Local · BYOK
          </span>
        </span>
        <button
          type="button"
          aria-label="Settings"
          title="Routing preferences"
          onClick={() => props.onOpenRoutingPrefs?.()}
          className="inline-flex h-8 w-8 items-center justify-center rounded-[6px] text-[var(--ink-3)] hover:bg-[var(--surface-2)] hover:text-[var(--ink)] focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]"
        >
          <Icon name="settings" size={18} />
        </button>
      </div>
    </nav>
  );
}
