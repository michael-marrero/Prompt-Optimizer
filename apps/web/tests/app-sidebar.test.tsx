// Phase 5 Wave 0 — AppSidebar RED test suite (UI-02, UI-SPEC §6).
//
// VALIDATION.md row: "UI-02 component" → `pnpm --dir apps/web test app-sidebar`.
//
// RED-by-design: `@/components/AppSidebar` does NOT exist yet. The import fails
// to resolve so every `it` is collected and reported FAILED until it ships.
//
// What this asserts (UI-SPEC §6 + §17):
//   - §6.2 a "New chat" button (exact copy from §17)
//   - §6.1 thread rows ordered newest-first (updated_at DESC)
//   - §6.4 the "…" actions menu with "Rename" / "Delete" items
//   - §6.4 deleting the active thread selects the newest remaining thread
//
// The sidebar is fed threads + an onSelect/onDelete contract by the page shell;
// the exact prop names are an implementation choice, so these tests drive off
// the rendered DOM (roles + copy) rather than internal props where possible.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { AppSidebar } from "@/components/AppSidebar";

// Threads in arbitrary order — the sidebar must sort newest-first by updated_at.
const THREADS = [
  { id: "t-old", title: "Oldest chat", updated_at: "2026-05-20T10:00:00Z" },
  { id: "t-new", title: "Newest chat", updated_at: "2026-05-24T10:00:00Z" },
  { id: "t-mid", title: "Middle chat", updated_at: "2026-05-22T10:00:00Z" },
];

beforeEach(() => {
  vi.clearAllMocks();
});

describe("UI-02 component — AppSidebar (UI-SPEC §6)", () => {
  it("UI-02: renders a 'New chat' button (§6.2 / §17 exact copy)", () => {
    render(
      <AppSidebar threads={THREADS} activeThreadId="t-new" onSelect={vi.fn()} onCreate={vi.fn()} onRename={vi.fn()} onDelete={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: /New chat/ })).toBeInTheDocument();
  });

  it("UI-02: thread rows are ordered newest-first by updated_at (§6.1)", () => {
    render(
      <AppSidebar threads={THREADS} activeThreadId="t-new" onSelect={vi.fn()} onCreate={vi.fn()} onRename={vi.fn()} onDelete={vi.fn()} />,
    );
    // IN-04: scope the title query to the thread list so the "New chat"
    // button (a single text node ending in "chat") does not pollute it.
    const list = screen.getByTestId("thread-list");
    const titles = within(list)
      .getAllByText(/chat$/)
      .map((el) => el.textContent);
    // Newest → middle → oldest.
    expect(titles).toEqual(["Newest chat", "Middle chat", "Oldest chat"]);
  });

  it("UI-02: the active row carries aria-current='page' (§6.6)", () => {
    render(
      <AppSidebar threads={THREADS} activeThreadId="t-mid" onSelect={vi.fn()} onCreate={vi.fn()} onRename={vi.fn()} onDelete={vi.fn()} />,
    );
    const active = screen.getByText("Middle chat").closest('[aria-current="page"]');
    expect(active).not.toBeNull();
  });

  it("UI-02: the '…' actions menu exposes Rename and Delete items (§6.4 / §17)", () => {
    render(
      <AppSidebar threads={THREADS} activeThreadId="t-new" onSelect={vi.fn()} onCreate={vi.fn()} onRename={vi.fn()} onDelete={vi.fn()} />,
    );
    // Open the actions menu on the active row.
    const triggers = screen.getAllByRole("button", { name: "Thread actions" });
    fireEvent.click(triggers[0]);
    expect(screen.getByRole("menuitem", { name: "Rename" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Delete" })).toBeInTheDocument();
  });

  it("UI-02: deleting the active thread selects the newest remaining thread (§6.4)", () => {
    const onSelect = vi.fn();
    const onDelete = vi.fn();
    render(
      <AppSidebar threads={THREADS} activeThreadId="t-new" onSelect={onSelect} onCreate={vi.fn()} onRename={vi.fn()} onDelete={onDelete} />,
    );
    // Open actions on the active (newest) row and delete it.
    const triggers = screen.getAllByRole("button", { name: "Thread actions" });
    fireEvent.click(triggers[0]);
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete" }));
    // Confirm in the alert-dialog (§6.4 destructive confirm copy from §17).
    const confirm = screen.getByRole("button", { name: "Delete chat" });
    fireEvent.click(confirm);
    expect(onDelete).toHaveBeenCalledWith("t-new");
    // After deleting the active newest thread, the next-newest remaining
    // ("Middle chat", t-mid) becomes active.
    expect(onSelect).toHaveBeenCalledWith("t-mid");
  });

  it("UI-02: the delete confirmation dialog uses the §17 copy strings", () => {
    render(
      <AppSidebar threads={THREADS} activeThreadId="t-new" onSelect={vi.fn()} onCreate={vi.fn()} onRename={vi.fn()} onDelete={vi.fn()} />,
    );
    const triggers = screen.getAllByRole("button", { name: "Thread actions" });
    fireEvent.click(triggers[0]);
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete" }));
    const dialog = screen.getByRole("alertdialog");
    expect(within(dialog).getByText("Delete this chat?")).toBeInTheDocument();
    expect(
      within(dialog).getByText("Delete this chat? This can't be undone."),
    ).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Keep chat" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Delete chat" })).toBeInTheDocument();
  });
});
