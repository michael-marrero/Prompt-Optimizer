// Sidebar — brand, new chat, conversation history, user footer.

function Sidebar({ activeId, onSelect, onNew, onOpenSettings }) {
  const { HISTORY } = window.PO_DATA;
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 32 32" fill="none">
            <defs>
              <linearGradient id="po-mark-grad" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
                <stop offset="0%" stopColor="var(--accent)" />
                <stop offset="55%" stopColor="var(--accent-2)" />
                <stop offset="100%" stopColor="var(--accent-3, var(--accent-2))" />
              </linearGradient>
            </defs>
            {/* input node */}
            <circle cx="5.5" cy="16" r="2.6" fill="url(#po-mark-grad)" />
            {/* routes */}
            <path d="M7.5 14.5 L20.5 6.5" stroke="url(#po-mark-grad)" strokeWidth="1.5" strokeLinecap="round" opacity="0.55" />
            <path d="M7.5 16 L24 16" stroke="url(#po-mark-grad)" strokeWidth="2.6" strokeLinecap="round" />
            <path d="M7.5 17.5 L20.5 25.5" stroke="url(#po-mark-grad)" strokeWidth="1.5" strokeLinecap="round" opacity="0.55" />
            {/* output nodes */}
            <circle cx="22" cy="5.5"  r="2"  fill="url(#po-mark-grad)" opacity="0.5" />
            <circle cx="26" cy="16"   r="3.2" fill="url(#po-mark-grad)" />
            <circle cx="22" cy="26.5" r="2"  fill="url(#po-mark-grad)" opacity="0.5" />
          </svg>
        </div>
        <div className="brand-lockup">
          <div className="brand-name">prompt optimizer</div>
          <div className="brand-sub">auto-routing · v1.4</div>
        </div>
      </div>

      <button className="new-chat" onClick={onNew}>
        <Icon name="plus" />
        New chat
        <kbd>⌘ N</kbd>
      </button>

      <nav className="history">
        {HISTORY.map(group => (
          <div className="history-group" key={group.group}>
            <div className="history-label">{group.group}</div>
            {group.items.map(item => (
              <div
                key={item.id}
                className={`history-item ${item.id === activeId ? 'active' : ''}`}
                onClick={() => onSelect(item.id)}
              >
                <span className="history-title">{item.title}</span>
                <span className="history-when">{item.when}</span>
              </div>
            ))}
          </div>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div className="avatar">MA</div>
        <div>
          <div className="user-name">Maya Asante</div>
          <div className="user-plan">PRO · 24k credits</div>
        </div>
        <button className="icon-btn" onClick={onOpenSettings} aria-label="Settings">
          <Icon name="settings" />
        </button>
      </div>
    </aside>
  );
}

window.Sidebar = Sidebar;
