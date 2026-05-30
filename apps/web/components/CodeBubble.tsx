// Phase 5 Plan 04 Wave 2 — CodeBubble (UI-09, UI-SPEC §7).
//
// Renders a `claude_code` assistant turn. Sits below a GREEN routing chip
// (RoutingChip already emits the claude_code green palette). The bubble reads
// its content blocks off `useMessage().content` — the SAME data-part pattern
// the RoutingChip / MetricsFooter use (RoutingChip.tsx:82-95): the SSE
// translator forwards tool_call / tool_result / file_diff / screenshot →
// `data-<event>`, and @assistant-ui/react-ai-sdk's convertMessage maps each
// into `{type:"data", name:"<event>", data}` content entries.
//
// Content order (UI-SPEC §7.1, top→bottom):
//   1. Collapsible tool-call chips (§7.3, collapsed by default).
//   2. Inline red/green file-diff blocks (§7.2).
//   3. The terminal text part as a markdown summary (§7.4).
//
// The file-diff renderer is HAND-ROLLED (no diff library, per UI-SPEC §7.2):
// split the unified-diff string on "\n", classify each line by its leading
// glyph (`+` added / `-` removed / else context), and SPECIAL-CASE the
// unified-diff header lines (`+++ `, `--- `, `@@`) so they are not miscolored
// as add/remove. The Claude Code adapter emits FileDiff.diff as `str(content)`
// off the SDK's ToolResultBlock (apps/api/backends/claude_code/adapter.py:409)
// — the observed shape is a full unified diff WITH `@@` hunk headers (see the
// shared fixture CLAUDE_CODE_CONTENT_PARTS), hence the header special-casing.
//
// Cross-refs:
//   - apps/web/components/RoutingChip.tsx (data-part read)
//   - apps/web/components/ChatBubble.tsx (assistant shell + action row)
//   - apps/web/components/ui/collapsible.tsx (shadcn collapsible)
//   - apps/web/components/MarkdownRenderer.tsx (summary rendering)
//   - apps/web/lib/chunk-schemas.ts (tool_call / tool_result / file_diff shapes)
//   - 05-UI-SPEC.md §7
"use client";

import { useState } from "react";
import { Copy, RefreshCw, Wrench, ChevronRight, ChevronDown } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { MarkdownRenderer } from "@/components/MarkdownRenderer";
import { cn } from "@/lib/cn";
import { useMessage } from "@assistant-ui/react";

// --------------------------------------------------------------------
// Structural part shapes (same content-vs-parts rationale as RoutingChip).
// --------------------------------------------------------------------

type PartLike = { readonly type: string };
type MessageStateWithContent = { readonly content: ReadonlyArray<PartLike> };

interface ToolCallData {
  readonly tool_call_id: string;
  readonly tool_name: string;
  readonly arguments: Record<string, unknown>;
}
interface ToolResultData {
  readonly tool_call_id: string;
  readonly content: string | Record<string, unknown>;
  readonly is_error: boolean;
}
interface FileDiffData {
  readonly tool_call_id: string;
  readonly path: string;
  readonly diff: string;
  readonly operation: "create" | "edit" | "delete";
}
type TextPart = { readonly type: "text"; readonly text: string };
type DataPart<T> = { readonly type: "data"; readonly name: string; readonly data: T };

function isDataNamed(p: PartLike, name: string): boolean {
  return p.type === "data" && (p as { name?: string }).name === name;
}
function isTextPart(p: PartLike): p is TextPart {
  return p.type === "text";
}

// Shared action-row button class — mirrors ChatBubble.tsx:76-77 exactly.
const actionButtonClass =
  "h-7 w-7 rounded-md hover:bg-[var(--surface-2)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2 inline-flex items-center justify-center text-[var(--ink-2)]";

// --------------------------------------------------------------------
// Hand-rolled unified-diff classifier (UI-SPEC §7.2 — no diff library).
// --------------------------------------------------------------------

type DiffLineKind = "added" | "removed" | "context" | "header";

interface ClassifiedLine {
  readonly kind: DiffLineKind;
  /** The line text WITHOUT its leading +/- gutter glyph (for add/remove). */
  readonly text: string;
}

function classifyDiff(diff: string): ClassifiedLine[] {
  return diff.split("\n").map((line): ClassifiedLine => {
    // Unified-diff header lines are NOT add/remove content (UI-SPEC §7.2
    // special-case): file headers `+++ ` / `--- ` and hunk headers `@@`.
    if (
      line.startsWith("+++ ") ||
      line.startsWith("--- ") ||
      line.startsWith("@@")
    ) {
      return { kind: "header", text: line };
    }
    if (line.startsWith("+")) {
      return { kind: "added", text: line.slice(1) };
    }
    if (line.startsWith("-")) {
      return { kind: "removed", text: line.slice(1) };
    }
    // Context lines keep their content; a leading space (unified-diff
    // convention) is stripped for display.
    return { kind: "context", text: line.startsWith(" ") ? line.slice(1) : line };
  });
}

function FileDiffBlock({ data }: { data: FileDiffData }): React.JSX.Element {
  const lines = classifyDiff(data.diff);
  const additions = lines.filter((l) => l.kind === "added").length;
  const deletions = lines.filter((l) => l.kind === "removed").length;

  return (
    <div
      aria-label={`File diff for ${data.path}: ${additions} additions, ${deletions} deletions`}
      className="rounded-md border border-[var(--line-strong)] overflow-x-auto my-3 text-xs font-mono leading-relaxed"
    >
      <div className="bg-[var(--surface-2)] px-3 py-2 text-sm font-mono text-[var(--ink-2)] border-b border-[var(--line)]">
        {data.path}
      </div>
      {lines.map((line, i) => {
        if (line.kind === "header") {
          // Header lines (file/hunk markers) are neutral — never colored.
          return (
            <div key={i} className="text-[var(--ink-3)] px-3">
              <span aria-hidden="true" className="select-none pr-2">
                {" "}
              </span>
              <span>{line.text}</span>
            </div>
          );
        }
        if (line.kind === "added") {
          return (
            <div key={i} className="bg-[var(--good)]/10 text-[var(--good)] px-3">
              <span aria-hidden="true" className="select-none pr-2">
                +
              </span>
              <span className="bg-[var(--good)]/10 text-[var(--good)]">{line.text}</span>
            </div>
          );
        }
        if (line.kind === "removed") {
          return (
            <div key={i} className="bg-[var(--danger)]/10 text-[var(--danger)] px-3">
              <span aria-hidden="true" className="select-none pr-2">
                -
              </span>
              <span className="bg-[var(--danger)]/10 text-[var(--danger)]">{line.text}</span>
            </div>
          );
        }
        return (
          <div key={i} className="text-[var(--ink-2)] px-3">
            <span aria-hidden="true" className="select-none pr-2">
              {" "}
            </span>
            <span>{line.text}</span>
          </div>
        );
      })}
    </div>
  );
}

// --------------------------------------------------------------------
// Tool-call collapsible (UI-SPEC §7.3 — collapsed by default).
// --------------------------------------------------------------------

function ToolCallChip({
  call,
  result,
}: {
  call: ToolCallData;
  result?: ToolResultData;
}): React.JSX.Element {
  const [open, setOpen] = useState(false);
  const resultText =
    result === undefined
      ? ""
      : typeof result.content === "string"
        ? result.content
        : JSON.stringify(result.content, null, 2);

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="my-1">
      <CollapsibleTrigger
        aria-label={`Tool call: ${call.tool_name} (click to expand)`}
        className="flex items-center gap-1 bg-[var(--surface-2)] rounded-md px-2 py-1 text-sm w-full text-left hover:bg-[var(--surface-2)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2"
      >
        <Wrench aria-hidden="true" className="h-[14px] w-[14px] shrink-0 text-[var(--ink-2)]" />
        <span className="font-normal text-[var(--ink)]">{call.tool_name}</span>
        {open ? (
          <ChevronDown aria-hidden="true" className="h-[14px] w-[14px] ml-auto shrink-0 text-[var(--ink-3)]" />
        ) : (
          <ChevronRight aria-hidden="true" className="h-[14px] w-[14px] ml-auto shrink-0 text-[var(--ink-3)]" />
        )}
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-1 rounded-md border border-[var(--line)] p-3 text-xs font-mono text-[var(--ink-2)]">
        <div className="overflow-x-auto">
          <div className="text-[var(--ink-3)]">args</div>
          <pre className="whitespace-pre-wrap">
            {JSON.stringify(call.arguments, null, 2)}
          </pre>
          {result !== undefined && (
            <>
              <div className="text-[var(--ink-3)] mt-2">result</div>
              <pre className="whitespace-pre-wrap max-h-48 overflow-y-auto">
                {resultText}
              </pre>
            </>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

const assistantContainerClass =
  "bg-[var(--surface-2)] border border-[var(--line)] rounded-lg p-4 max-w-prose group relative";

export interface CodeBubbleProps {
  /** Forwarded to ChatBubble's action row in page.tsx; the bubble itself
   *  wires Regenerate so the standalone component keeps the §7.5 action row. */
  onRegenerate?: () => void;
}

export function CodeBubble({ onRegenerate }: CodeBubbleProps = {}): React.JSX.Element {
  const message = useMessage({ optional: true }) as
    | MessageStateWithContent
    | null;
  const content = message?.content ?? [];

  const toolCalls = content
    .filter((p) => isDataNamed(p, "tool_call"))
    .map((p) => (p as DataPart<ToolCallData>).data);
  const toolResults = content
    .filter((p) => isDataNamed(p, "tool_result"))
    .map((p) => (p as DataPart<ToolResultData>).data);
  const fileDiffs = content
    .filter((p) => isDataNamed(p, "file_diff"))
    .map((p) => (p as DataPart<FileDiffData>).data);
  const summary = content
    .filter(isTextPart)
    .map((p) => p.text)
    .join("");

  // Pair each tool_call with its matching tool_result by tool_call_id.
  const resultById = new Map(toolResults.map((r) => [r.tool_call_id, r]));

  async function handleCopy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(summary);
    } catch {
      // Clipboard may be blocked by permissions — silently swallow (same
      // posture as ChatBubble.tsx:96-100).
    }
  }

  return (
    <div className={assistantContainerClass}>
      {/* §7.1 #1 — tool-call collapsibles, collapsed by default. */}
      {toolCalls.map((call) => (
        <ToolCallChip
          key={call.tool_call_id}
          call={call}
          result={resultById.get(call.tool_call_id)}
        />
      ))}

      {/* §7.1 #2 — inline red/green file-diff blocks. */}
      {fileDiffs.map((diff, i) => (
        <FileDiffBlock key={`${diff.tool_call_id}-${i}`} data={diff} />
      ))}

      {/* §7.1 #3 — terminal text part as a markdown summary. */}
      {summary !== "" && (
        <div className="text-sm leading-relaxed text-[var(--ink)] mt-3">
          <MarkdownRenderer
            rawMarkdown={summary}
            isStreamingComplete
            messageId={`code-${toolCalls[0]?.tool_call_id ?? "summary"}`}
          />
        </div>
      )}

      {/* §7.5 — hover-revealed action row (clone of ChatBubble.tsx:118-141). */}
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
