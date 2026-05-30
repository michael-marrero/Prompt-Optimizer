"use client";

// Phase 5 Plan 06 Wave 3 — ChatPage (the feature-complete chat surface).
//
// Replaces the Phase-4 single-column chat with the two-column app shell
// (UI-SPEC §5): the page now renders <PageShell/>, which wraps the chat
// surface in the persistent thread sidebar (UI-02), mounts the header
// StatusStrip (UI-11) + the composer OverrideDropdown (UI-05), dispatches the
// per-backend bubbles via MessageBubble (UI-09/UI-10), and wires the
// EmptyState sample cards (UI-16), the FeedbackButtons (UI-15), and the
// first-user-send auto-rename (UI-14).
//
// The whole composition lives in PageShell + ChatSurface + MessageBubble so the
// shell is independently testable (page-shell.test.tsx) and page.tsx stays a
// thin entry point. The wiring this entry point pulls together:
//   - SidebarProvider two-column shell      → PageShell.tsx
//   - per-backend bubble dispatch            → MessageBubble.tsx
//       (claude_code → CodeBubble, computer_use → ComputerUseBubble,
//        openrouter/default → ChatBubble)
//   - status strip / override dropdown       → PageShell.tsx / ChatSurface.tsx
//
// Cross-refs:
//   - apps/web/components/PageShell.tsx (SidebarProvider shell + StatusStrip)
//   - apps/web/components/ChatSurface.tsx (runtime-bound chat column + override)
//   - apps/web/components/MessageBubble.tsx (claude_code / CodeBubble dispatch)
//   - 05-UI-SPEC.md §5 / §16

import { PageShell } from "@/components/PageShell";
import {
  RoutingPrefsProvider,
  useRoutingPrefs,
} from "@/components/RoutingPrefsProvider";
import { RoutingPrefsModal } from "@/components/RoutingPrefsModal";

// Connector: reads the opener from the provider and hands it to PageShell's
// gear + top-bar Routing button (07-05 seam). Keeps PageShell prop-driven and
// independently testable (page-shell.test.tsx renders it with no provider).
function ChatShell(): React.JSX.Element {
  const { openRoutingPrefs } = useRoutingPrefs();
  return <PageShell onOpenRoutingPrefs={openRoutingPrefs} />;
}

export default function ChatPage(): React.JSX.Element {
  return (
    <RoutingPrefsProvider>
      <ChatShell />
      <RoutingPrefsModal />
    </RoutingPrefsProvider>
  );
}
