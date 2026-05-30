// Phase 7 Plan 07-04 (UI-REDESIGN-08) — Animated router-fan diagram.
//
// Ported near-verbatim from design_handoff_prompt_optimizer/source/router-diagram.jsx.
// A prompt feeds a central hub that fans out to each candidate model; the pulse +
// active edge cycle through the lineup (every 2100ms) to tell the routing story.
//
// Port deltas (07-PATTERNS.md "RouterDiagram.tsx"):
//   - "use client" (React state/effect + SMIL).
//   - window.PO_DATA.MODELS → a real `models` prop with a self-contained default
//     (the 6-model lineup; mirrors the "6 models" eyebrow). No global lookup.
//   - Strokes/fills use Plasma token vars directly (var(--accent)/--accent-2/
//     --accent-soft/--surface/--line-strong/--ink-3) — the source used these exact
//     names via classes; applied inline here since the token vars (07-02) are live
//     but the source's component classes are not ported.
//   - LOCKED cadence preserved: 2100ms active cycle · 3s hub ring · 1s node halo ·
//     1.6s traveling pulse re-keyed via key={`p-${active}`} so SMIL restarts on
//     every active change.
//   - svg is aria-hidden (decorative); caption renders the LOCKED copy.
"use client";

import { useEffect, useState } from "react";
import type React from "react";

export interface RouterModel {
  id: string;
  short: string;
  label: string;
  tag: string;
}

// Default 6-model lineup (mirrors the lede + the "6 models" eyebrow). Callers may
// pass a real list; this presentational diagram only needs short/label/tag.
const DEFAULT_MODELS: readonly RouterModel[] = [
  { id: "claude", short: "Claude", label: "Claude Sonnet 4.5", tag: "nuance" },
  { id: "gpt4o", short: "GPT-4o", label: "GPT-4o", tag: "vision" },
  { id: "deepseek", short: "DeepSeek", label: "DeepSeek V3", tag: "code" },
  { id: "gemini", short: "Gemini", label: "Gemini 2.5", tag: "speed" },
  { id: "gpt5", short: "GPT-5", label: "GPT-5", tag: "reasoning" },
  { id: "qwen", short: "Qwen", label: "Qwen3", tag: "math" },
];

export interface RouterDiagramProps {
  models?: readonly RouterModel[];
}

export function RouterDiagram({
  models = DEFAULT_MODELS,
}: RouterDiagramProps = {}): React.JSX.Element {
  const [active, setActive] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      setActive((a) => (a + 1) % models.length);
    }, 2100);
    return () => clearInterval(id);
  }, [models.length]);

  const W = 800;
  const H = 340;
  const hub = { x: 300, y: H / 2 };
  const promptX = 60;
  const nodeX = 620;

  const nodes = models.map((m, i) => {
    const t = models.length === 1 ? 0.5 : i / (models.length - 1);
    const y = 38 + t * (H - 76);
    return { ...m, x: nodeX, y, i };
  });

  const activeNode = nodes[active] ?? nodes[0];

  return (
    <div className="w-full max-w-[760px] mx-auto my-4 rounded-[14px] border border-[var(--line)] bg-[var(--surface)] p-4">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" aria-hidden="true">
        <defs>
          <radialGradient id="hubGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="var(--accent-soft)" stopOpacity="1" />
            <stop offset="100%" stopColor="var(--accent-soft)" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="hubFill" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="var(--accent)" />
            <stop offset="100%" stopColor="var(--accent-2)" />
          </linearGradient>
        </defs>

        {/* prompt → hub */}
        <line
          x1={promptX}
          y1={hub.y}
          x2={hub.x - 32}
          y2={hub.y}
          stroke="var(--accent)"
          strokeWidth="2"
        />

        {/* hub → models */}
        {nodes.map((n) => (
          <line
            key={n.id}
            x1={hub.x + 32}
            y1={hub.y}
            x2={n.x - 7}
            y2={n.y}
            stroke={n.i === active ? "var(--accent)" : "var(--line-strong)"}
            strokeWidth={n.i === active ? 2 : 1}
            opacity={n.i === active ? 1 : 0.6}
          />
        ))}

        {/* hub glow + circle */}
        <circle cx={hub.x} cy={hub.y} r="64" fill="url(#hubGlow)" />
        <circle cx={hub.x} cy={hub.y} r="34" fill="url(#hubFill)" stroke="none" />
        <circle
          cx={hub.x}
          cy={hub.y}
          r="34"
          fill="none"
          stroke="var(--accent)"
          strokeWidth="1.2"
          opacity="0.35"
        >
          <animate attributeName="r" values="34;46;34" dur="3s" repeatCount="indefinite" />
          <animate attributeName="opacity" values="0.35;0;0.35" dur="3s" repeatCount="indefinite" />
        </circle>
        <text x={hub.x} y={hub.y + 9} textAnchor="middle" fill="#ffffff" fontSize="20" fontWeight="600">
          P
        </text>

        {/* prompt indicator */}
        <rect
          x={promptX - 30}
          y={hub.y - 14}
          width="60"
          height="28"
          rx="6"
          fill="var(--surface)"
          stroke="var(--line-strong)"
          strokeWidth="0.75"
        />
        <line x1={promptX - 18} y1={hub.y - 4} x2={promptX + 14} y2={hub.y - 4} stroke="var(--ink-3)" strokeWidth="1" strokeLinecap="round" />
        <line x1={promptX - 18} y1={hub.y + 1} x2={promptX + 18} y2={hub.y + 1} stroke="var(--ink-3)" strokeWidth="1" strokeLinecap="round" />
        <line x1={promptX - 18} y1={hub.y + 6} x2={promptX + 6} y2={hub.y + 6} stroke="var(--ink-3)" strokeWidth="1" strokeLinecap="round" />
        <text x={promptX} y={hub.y + 38} textAnchor="middle" fill="var(--ink-3)" fontSize="10" fontWeight="600" letterSpacing="0.08em">
          PROMPT
        </text>

        {/* model nodes + labels */}
        {nodes.map((n) => (
          <g key={n.id}>
            <circle
              cx={n.x}
              cy={n.y}
              r="7"
              fill={n.i === active ? "var(--accent)" : "var(--surface)"}
              stroke={n.i === active ? "var(--accent)" : "var(--line-strong)"}
              strokeWidth="1.5"
            />
            {n.i === active && (
              <circle cx={n.x} cy={n.y} r="14" fill="none" stroke="var(--accent)" strokeWidth="1" opacity="0.4">
                <animate attributeName="r" from="7" to="18" dur="1s" repeatCount="indefinite" />
                <animate attributeName="opacity" from="0.5" to="0" dur="1s" repeatCount="indefinite" />
              </circle>
            )}
            <text
              x={n.x + 18}
              y={n.y + 4}
              fill={n.i === active ? "var(--accent)" : "var(--ink-3)"}
              fontSize="11"
              fontWeight={n.i === active ? 600 : 400}
            >
              {n.short}
            </text>
          </g>
        ))}

        {/* traveling pulse — re-keyed on active change to restart SMIL */}
        <circle r="4" fill="var(--accent)" key={`p-${active}`}>
          <animate
            attributeName="cx"
            values={`${promptX};${hub.x};${activeNode.x}`}
            keyTimes="0;0.45;1"
            dur="1.6s"
            begin="0s"
            fill="freeze"
          />
          <animate
            attributeName="cy"
            values={`${hub.y};${hub.y};${activeNode.y}`}
            keyTimes="0;0.45;1"
            dur="1.6s"
            begin="0s"
            fill="freeze"
          />
          <animate
            attributeName="opacity"
            values="0;1;1;0"
            keyTimes="0;0.1;0.9;1"
            dur="1.6s"
            begin="0s"
            fill="freeze"
          />
        </circle>
      </svg>

      <div className="mt-2 text-center font-[var(--font-mono-plasma)] text-[10.5px] uppercase tracking-[0.04em] text-[var(--ink-3)]">
        Optimized for <strong className="text-[var(--accent)] font-semibold">{activeNode.tag}</strong> → routed to{" "}
        <strong className="text-[var(--accent)] font-semibold">{activeNode.label}</strong>
      </div>
    </div>
  );
}
