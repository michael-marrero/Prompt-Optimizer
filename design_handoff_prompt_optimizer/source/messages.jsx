// Message thread + composer + empty state.

function formatBody(text) {
  // Minimal markdown: **bold**, `code`, blank lines = paragraphs
  const blocks = text.split(/\n{2,}/);
  return blocks.map((block, i) => {
    const lines = block.split('\n');
    return (
      <p key={i}>
        {lines.map((line, j) => {
          const parts = [];
          let remaining = line;
          let key = 0;
          // Tokenize bold + inline code
          const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
          let lastEnd = 0;
          let m;
          while ((m = re.exec(line)) !== null) {
            if (m.index > lastEnd) parts.push(line.slice(lastEnd, m.index));
            const tok = m[0];
            if (tok.startsWith('**')) parts.push(<strong key={`b${key++}`}>{tok.slice(2, -2)}</strong>);
            else parts.push(<code key={`c${key++}`}>{tok.slice(1, -1)}</code>);
            lastEnd = m.index + tok.length;
          }
          if (lastEnd < line.length) parts.push(line.slice(lastEnd));
          return (
            <React.Fragment key={j}>
              {parts}
              {j < lines.length - 1 && <br />}
            </React.Fragment>
          );
        })}
      </p>
    );
  });
}

function Message({ msg }) {
  const { MODELS } = window.PO_DATA;
  const isUser = msg.role === 'user';
  const model = msg.routedTo ? MODELS.find(m => m.id === msg.routedTo) : null;

  return (
    <article className={`msg msg-${msg.role}`}>
      <header className="msg-head">
        <span className="msg-role">{isUser ? 'You' : 'Prompt Optimizer'}</span>
        <span className="msg-when">{msg.when}</span>
        {!isUser && model && (
          <span
            className="optimized-pill"
            title={`Routed to ${model.label} — ${msg.routedReason}`}
          >
            optimized
          </span>
        )}
      </header>

      <div className="msg-body">
        {formatBody(msg.text)}
        {msg.attachments?.map(a => (
          <div className="attachment" key={a.name}>
            <span className="attachment-icon"><Icon name="doc" size={14} /></span>
            <span>{a.name}</span>
            <span className="attachment-size">{a.size}</span>
          </div>
        ))}
      </div>

      {!isUser && (
        <footer className="msg-foot">
          <span className="msg-foot-stat"><strong>{(msg.latencyMs / 1000).toFixed(2)}s</strong> · latency</span>
          <span className="msg-foot-stat"><strong>${msg.cost.toFixed(4)}</strong> · cost</span>
          <span className="msg-foot-stat"><strong>{model?.short}</strong></span>
          <div className="msg-foot-actions">
            <button className="icon-btn" title="Copy"><Icon name="copy" size={13} /></button>
            <button className="icon-btn" title="Regenerate"><Icon name="refresh" size={13} /></button>
            <button className="icon-btn" title="Compare with another model"><Icon name="compare" size={13} /></button>
            <button className="icon-btn" title="Helpful"><Icon name="thumb" size={13} /></button>
          </div>
        </footer>
      )}
    </article>
  );
}

function EmptyState({ onSuggestion }) {
  const { SUGGESTIONS } = window.PO_DATA;
  return (
    <div className="empty">
      <div className="empty-eyebrow">Auto-routed · 6 models · 0 config</div>
      <h1>
        Ask anything.<br />
        We'll pick the <em>right model</em> for the job.
      </h1>
      <p className="empty-lede">
        Every prompt is analyzed and routed to the model that handles it best — Claude for nuance, GPT-4o for vision, DeepSeek for code, Gemini for speed. You just write.
      </p>

      <RouterDiagram />

      <div className="suggestions">
        {SUGGESTIONS.map((s, i) => (
          <button
            key={i}
            className="suggestion"
            onClick={() => onSuggestion(s.text)}
          >
            <span className="suggestion-kind">{s.kind}</span>
            <span className="suggestion-text">{s.text}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function Composer({ value, onChange, onSend, compare, onToggleCompare }) {
  const ref = React.useRef(null);
  React.useEffect(() => {
    if (!ref.current) return;
    ref.current.style.height = 'auto';
    ref.current.style.height = Math.min(200, ref.current.scrollHeight) + 'px';
  }, [value]);
  return (
    <div className="composer-wrap">
      <div className="composer">
        <textarea
          ref={ref}
          className="composer-textarea"
          rows={1}
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder="Ask anything — we'll route it to the best model."
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              onSend();
            }
          }}
        />
        <div className="composer-row">
          <button className="icon-btn" title="Attach file"><Icon name="paperclip" /></button>
          <button className="icon-btn" title="Add image"><Icon name="image" /></button>
          <button className="icon-btn" title="Voice"><Icon name="mic" /></button>
          <button className="icon-btn" title="Web search"><Icon name="globe" /></button>
          <button
            className={`compare-toggle ${compare ? 'on' : ''}`}
            onClick={onToggleCompare}
            title="Run on two models and show side-by-side"
          >
            Compare
          </button>
          <button className="composer-send" onClick={onSend} disabled={!value.trim()} aria-label="Send">
            <Icon name="arrowUp" />
          </button>
        </div>
      </div>
      <div className="composer-hint">
        <kbd>↵</kbd> send · <kbd>⇧ ↵</kbd> newline · <kbd>⌘ K</kbd> commands
      </div>
    </div>
  );
}

function CompareView({ msg }) {
  // Show same prompt routed to two different models
  return (
    <div className="msg msg-assistant">
      <header className="msg-head">
        <span className="msg-role">Prompt Optimizer · Compare</span>
        <span className="msg-when">{msg.when}</span>
        <span className="optimized-pill" title="Comparing top 2 candidate models">2 models</span>
      </header>
      <div className="compare-stage">
        <div className="compare-card">
          <div className="compare-card-head">
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)' }}></span>
            Claude Sonnet 4.5 · 1.84s · $0.0042
          </div>
          <div className="compare-card-text">
            Tight, warm, and three steps. Drops the apology, keeps the workspace CTA, replaces the long signature with a single inline call to action.
          </div>
        </div>
        <div className="compare-card">
          <div className="compare-card-head">
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--ink-3)' }}></span>
            GPT-4o · 1.12s · $0.0029
          </div>
          <div className="compare-card-text">
            Shorter still — 40 words. Reads more transactional; you lose the "real person reads every message" line which softens the tone. Faster and cheaper.
          </div>
        </div>
      </div>
    </div>
  );
}

window.Message = Message;
window.EmptyState = EmptyState;
window.Composer = Composer;
window.CompareView = CompareView;
