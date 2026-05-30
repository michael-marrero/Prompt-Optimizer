// Phase 7 Plan 07-05 (UI-REDESIGN-03/10) — Plasma app shell.
//
// The Plasma `256px 1fr` grid shell. Keeps the shadcn SidebarProvider +
// AppSidebar + SidebarInset structure (page-shell.test.tsx asserts the
// data-slot="sidebar-wrapper") and the single threads source of truth, but
// re-skins the header into the Plasma top bar: title · meta · Share · Export ·
// Routing (the Routing button + the sidebar gear both open the Routing
// Preferences modal — 07-07 wires the opener via onOpenRoutingPrefs).
//
// Carbon mesh: the global `.app::before` mesh (globals.css, 07-02) resolves only
// under .theme-carbon; the SidebarInset main carries the z-index:1 children hook.
//
// Cross-refs:
//   - apps/web/components/AppSidebar.tsx, StatusStrip.tsx, ChatSurface.tsx
//   - apps/web/components/ui/sidebar.tsx (SidebarProvider + SidebarInset)
//   - apps/web/components/Icon.tsx (07-02, D-04)
//   - 07-UI-SPEC.md §Spacing/§Copywriting (top bar)
"use client";

import type React from "react";
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/AppSidebar";
import { StatusStrip } from "@/components/StatusStrip";
import { ChatSurface } from "@/components/ChatSurface";
import { Icon } from "@/components/Icon";
import { useThreads } from "@/hooks/useThreads";

export interface PageShellProps {
  /** Opens the Routing Preferences modal (07-07 passes the real opener; the
   * Routing top-bar button + the sidebar gear both call it). */
  onOpenRoutingPrefs?: () => void;
}

export function PageShell({ onOpenRoutingPrefs }: PageShellProps = {}): React.JSX.Element {
  const threads = useThreads();
  const openRoutingPrefs = onOpenRoutingPrefs ?? (() => undefined);

  const activeTitle =
    threads.threads.find((t) => t.id === threads.activeThreadId)?.title ??
    "New chat";

  return (
    <SidebarProvider>
      <AppSidebar
        threads={threads.threads}
        activeThreadId={threads.activeThreadId}
        onSelect={threads.selectThread}
        onCreate={threads.createThread}
        onRename={threads.renameThread}
        onDelete={threads.deleteThread}
        onOpenRoutingPrefs={openRoutingPrefs}
      />
      <SidebarInset className="flex min-h-svh flex-col bg-[var(--bg)]">
        {/* Plasma top bar — title · meta · Share · Export · Routing */}
        <header className="sticky top-0 z-10 flex h-[60px] items-center justify-between gap-4 border-b border-[var(--line)] bg-[var(--surface)] px-6 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <h1 className="truncate font-[var(--font-display)] text-[15px] font-semibold tracking-[-0.015em] text-[var(--ink)]">
              {activeTitle}
            </h1>
            <span className="font-[var(--font-mono-plasma)] text-[10.5px] uppercase tracking-[0.08em] text-[var(--ink-3)]">
              Auto-routed
            </span>
            <StatusStrip />
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="inline-flex items-center gap-1.5 rounded-[9px] border border-[var(--line)] px-2.5 py-1.5 text-[12.5px] font-medium text-[var(--ink-2)] transition-colors hover:bg-[var(--surface-2)] hover:shadow-[var(--shadow-md)]"
            >
              <Icon name="share" size={16} />
              Share
            </button>
            <button
              type="button"
              className="inline-flex items-center gap-1.5 rounded-[9px] border border-[var(--line)] px-2.5 py-1.5 text-[12.5px] font-medium text-[var(--ink-2)] transition-colors hover:bg-[var(--surface-2)] hover:shadow-[var(--shadow-md)]"
            >
              <Icon name="doc" size={16} />
              Export
            </button>
            <button
              type="button"
              onClick={openRoutingPrefs}
              className="inline-flex items-center gap-1.5 rounded-[9px] bg-[var(--accent)] px-3 py-1.5 text-[12.5px] font-medium text-white transition-colors hover:bg-[var(--accent-hover)] focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]"
            >
              <Icon name="settings" size={16} />
              Routing
            </button>
          </div>
        </header>

        <ChatSurface
          activeThreadId={threads.activeThreadId}
          autoRenameFromFirstMessage={threads.autoRenameFromFirstMessage}
        />
      </SidebarInset>
    </SidebarProvider>
  );
}
