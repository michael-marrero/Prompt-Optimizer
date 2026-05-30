// Animated router diagram for the empty state.
// A prompt feeds a central hub that fans out to each available model;
// the pulse + active edge cycle through the lineup to tell the routing story.

function RouterDiagram() {
  const models = window.PO_DATA.MODELS;
  const [active, setActive] = React.useState(0);

  React.useEffect(() => {
    const id = setInterval(() => {
      setActive(a => (a + 1) % models.length);
    }, 2100);
    return () => clearInterval(id);
  }, [models.length]);

  const W = 800, H = 340;
  const hub = { x: 300, y: H / 2 };
  const promptX = 60;
  const nodeX = 620;

  const nodes = models.map((m, i) => {
    const t = models.length === 1 ? 0.5 : i / (models.length - 1);
    const y = 38 + t * (H - 76);
    return { ...m, x: nodeX, y, i };
  });

  const activeNode = nodes[active];

  return (
    <div className="router-stage" aria-hidden="true">
      <svg viewBox={`0 0 ${W} ${H}`}>
        <defs>
          <radialGradient id="hubGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="var(--accent-soft)" stopOpacity="1" />
            <stop offset="100%" stopColor="var(--accent-soft)" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* prompt → hub */}
        <line
          x1={promptX} y1={hub.y} x2={hub.x - 32} y2={hub.y}
          className="router-edge active"
        />

        {/* hub → models */}
        {nodes.map(n => (
          <line
            key={n.id}
            x1={hub.x + 32} y1={hub.y}
            x2={n.x - 7} y2={n.y}
            className={`router-edge ${n.i === active ? 'active' : ''}`}
          />
        ))}

        {/* hub glow + circle */}
        <circle cx={hub.x} cy={hub.y} r="64" fill="url(#hubGlow)" />
        <defs>
          <linearGradient id="hubFill" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="var(--accent)" />
            <stop offset="100%" stopColor="var(--accent-2)" />
          </linearGradient>
        </defs>
        <circle
          cx={hub.x} cy={hub.y} r="34"
          fill="url(#hubFill)"
          stroke="none"
        />
        <circle
          cx={hub.x} cy={hub.y} r="34"
          fill="none"
          stroke="var(--accent)"
          strokeWidth="1.2"
          opacity="0.35"
        >
          <animate
            attributeName="r"
            values="34;46;34"
            dur="3s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="0.35;0;0.35"
            dur="3s"
            repeatCount="indefinite"
          />
        </circle>
        <text
          x={hub.x} y={hub.y + 9}
          textAnchor="middle"
          className="router-hub-label"
        >P</text>

        {/* prompt indicator */}
        <rect
          x={promptX - 30} y={hub.y - 14}
          width="60" height="28" rx="6"
          fill="var(--surface)"
          stroke="var(--line-strong)"
          strokeWidth="0.75"
        />
        <line x1={promptX - 18} y1={hub.y - 4} x2={promptX + 14} y2={hub.y - 4} stroke="var(--ink-3)" strokeWidth="1" strokeLinecap="round" />
        <line x1={promptX - 18} y1={hub.y + 1} x2={promptX + 18} y2={hub.y + 1} stroke="var(--ink-3)" strokeWidth="1" strokeLinecap="round" />
        <line x1={promptX - 18} y1={hub.y + 6} x2={promptX + 6} y2={hub.y + 6} stroke="var(--ink-3)" strokeWidth="1" strokeLinecap="round" />
        <text x={promptX} y={hub.y + 38} textAnchor="middle" className="router-label">PROMPT</text>

        {/* model nodes + labels */}
        {nodes.map(n => (
          <g key={n.id}>
            <circle
              cx={n.x} cy={n.y} r="7"
              className={`router-node ${n.i === active ? 'active' : ''}`}
            />
            {n.i === active && (
              <circle cx={n.x} cy={n.y} r="14" fill="none" stroke="var(--accent)" strokeWidth="1" opacity="0.4">
                <animate attributeName="r" from="7" to="18" dur="1s" repeatCount="indefinite" />
                <animate attributeName="opacity" from="0.5" to="0" dur="1s" repeatCount="indefinite" />
              </circle>
            )}
            <text
              x={n.x + 18} y={n.y + 4}
              className={`router-label ${n.i === active ? 'active' : ''}`}
            >{n.short}</text>
          </g>
        ))}

        {/* traveling pulse */}
        <circle r="4" className="router-pulse" key={`p-${active}`}>
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

      <div className="router-caption">
        Optimized for <strong>{activeNode.tag}</strong> → routed to <strong>{activeNode.label}</strong>
      </div>
    </div>
  );
}

window.RouterDiagram = RouterDiagram;
