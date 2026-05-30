// Phase 5 Plan 05 Wave 2 — ThreadRow (UI-02, UI-SPEC §6.3/§6.4/§6.6).
//
// One thread row in the sidebar. States (§6.3):
//   - default: text-sm font-normal px-2 py-2 rounded-md truncate
//   - hover:  hover:bg-slate-100, reveals the "…" trigger
//             (group-hover:opacity-100 opacity-0)
//   - active: bg-slate-100 font-semibold + aria-current="page" (§6.6)
//
// The trailing "…" (lucide MoreHorizontal, aria-label="Thread actions") opens a
// dropdown-menu (§6.4) with:
//   - Rename (lucide Pencil) → inline-edit: the title is replaced by an
//     <input aria-label="Rename thread">; Enter saves via onRename, Esc cancels.
//   - Delete (lucide Trash2, text-red-600) → opens the alert-dialog with the
//     §6.4 copy (title "Delete this chat?", description
//     "Delete this chat? This can't be undone.", cancel "Keep chat",
//     destructive confirm "Delete chat" bg-red-600 text-white). Confirm fires
//     onConfirmDelete (which the sidebar wires to onDelete + reselect).
//
// While a rename hasn't resolved the row shows the provisional title verbatim
// (the parent supplies the first ~40 chars via the auto-rename helper — UI-SPEC
// §6.5). This component owns no rename network call — it calls onRename(title).
//
// Cross-refs:
//   - apps/web/components/ChatBubble.tsx (hover-reveal action-row pattern)
//   - apps/web/components/ui/{dropdown-menu,alert-dialog,input}.tsx
//   - 05-UI-SPEC.md §6 + §17 (exact copy)
"use client";

import { useState } from "react";
import { MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/cn";

export interface ThreadRowProps {
  id: string;
  title: string;
  isActive: boolean;
  onSelect: (id: string) => void;
  onRename: (id: string, title: string) => void;
  /** Fired when the user confirms deletion in the alert-dialog. The sidebar
   * wires this to onDelete(id) + reselect-next so it owns the ordering logic. */
  onConfirmDelete: (id: string) => void;
}

export function ThreadRow({
  id,
  title,
  isActive,
  onSelect,
  onRename,
  onConfirmDelete,
}: ThreadRowProps): React.JSX.Element {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(title);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  function startRename(): void {
    setDraft(title);
    setEditing(true);
  }

  function commitRename(): void {
    const next = draft.trim();
    if (next.length > 0 && next !== title) {
      onRename(id, next);
    }
    setEditing(false);
  }

  return (
    <li className="group relative">
      <div
        className={cn(
          "flex items-center justify-between gap-1 rounded-[6px] px-2.5 py-1.5",
          "hover:bg-[var(--surface-2)]",
          isActive && "bg-[var(--accent-soft)] border-l-2 border-[var(--accent)] pl-2",
        )}
        aria-current={isActive ? "page" : undefined}
      >
        {editing ? (
          <Input
            autoFocus
            aria-label="Rename thread"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onBlur={commitRename}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                commitRename();
              } else if (event.key === "Escape") {
                event.preventDefault();
                setEditing(false);
              }
            }}
            className="h-7 text-sm"
          />
        ) : (
          <button
            type="button"
            onClick={() => onSelect(id)}
            className={cn(
              "flex-1 truncate text-left text-[13px] text-[var(--ink)]",
              isActive ? "font-medium" : "font-normal",
            )}
          >
            {title}
          </button>
        )}

        {!editing && (
          // Controlled open state: Radix's DropdownMenuTrigger toggles on
          // pointer events, which jsdom does not synthesize from
          // fireEvent.click. Driving `open` from the trigger button's onClick
          // keeps the menu openable in the RED test (and via real clicks).
          <DropdownMenu open={menuOpen} onOpenChange={setMenuOpen}>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                aria-label="Thread actions"
                onClick={() => setMenuOpen((open) => !open)}
                className={cn(
                  "inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md",
                  "text-[var(--ink-3)] hover:bg-[var(--surface-2)]",
                  "opacity-0 group-hover:opacity-100 focus-visible:opacity-100 aria-expanded:opacity-100",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2",
                )}
              >
                <MoreHorizontal className="h-4 w-4" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => startRename()}>
                <Pencil className="mr-2 h-4 w-4" />
                Rename
              </DropdownMenuItem>
              <DropdownMenuItem
                className="text-[var(--danger)] focus:text-[var(--danger)]"
                onSelect={(event) => {
                  // Keep the menu's Radix focus from racing the dialog open.
                  event.preventDefault();
                  setConfirmOpen(true);
                }}
              >
                <Trash2 className="mr-2 h-4 w-4 text-[var(--danger)]" />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this chat?</AlertDialogTitle>
            <AlertDialogDescription>
              Delete this chat? This can&apos;t be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep chat</AlertDialogCancel>
            <AlertDialogAction
              className="bg-[var(--danger)] text-white hover:opacity-90"
              onClick={() => {
                setConfirmOpen(false);
                onConfirmDelete(id);
              }}
            >
              Delete chat
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </li>
  );
}
