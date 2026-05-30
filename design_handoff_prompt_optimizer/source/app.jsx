// Prompt Optimizer — top-level app shell.

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme": "plasma",
  "density": "regular",
  "view": "empty",
  "showBadge": true
}/*EDITMODE-END*/;

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [activeId, setActiveId] = React.useState('c1');
  const [draft, setDraft] = React.useState('');
  const [compare, setCompare] = React.useState(false);
  const [settingsOpen, setSettingsOpen] = React.useState(false);
  const [prefs, setPrefs] = React.useState({
    priority: 'Balanced',
    showBadge: true,
    costAware: true,
    zdr: false,
  });

  const setPref = (k, v) => setPrefs(p => ({ ...p, [k]: v }));

  const isEmpty = t.view === 'empty';
  const showCompare = t.view === 'compare';

  // Apply theme class on the root element
  React.useEffect(() => {
    const cls = `theme-${t.theme} density-${t.density}`;
    document.documentElement.className = cls;
  }, [t.theme, t.density]);

  const onSuggestion = (text) => {
    setDraft(text);
    setTweak('view', 'thread');
  };

  const onSend = () => {
    if (!draft.trim()) return;
    setDraft('');
    setTweak('view', 'thread');
  };

  const thread = window.PO_DATA.THREAD;
  const activeTitle = window.PO_DATA.HISTORY
    .flatMap(g => g.items)
    .find(i => i.id === activeId)?.title || 'New chat';

  return (
    <div className="app">
      <Sidebar
        activeId={isEmpty ? null : activeId}
        onSelect={(id) => { setActiveId(id); setTweak('view', 'thread'); }}
        onNew={() => setTweak('view', 'empty')}
        onOpenSettings={() => setSettingsOpen(true)}
      />

      <main className="main">
        <div className="topbar">
          <div className="topbar-title">
            {isEmpty ? 'New chat' : activeTitle}
          </div>
          {!isEmpty && (
            <span className="topbar-meta">
              4 messages · auto-routed
            </span>
          )}
          <button className="btn ghost" title="Share">
            <Icon name="share" size={14} /> Share
          </button>
          <button className="btn ghost" title="Export">
            <Icon name="doc" size={14} /> Export
          </button>
          <button
            className="btn"
            onClick={() => setSettingsOpen(true)}
            title="Routing preferences"
          >
            <Icon name="settings" size={14} /> Routing
          </button>
        </div>

        <div className="pane">
          {isEmpty ? (
            <EmptyState onSuggestion={onSuggestion} />
          ) : (
            <div className="pane-inner">
              {thread.map(m => <Message key={m.id} msg={m} />)}
              {showCompare && <CompareView msg={{ when: '11:48 AM' }} />}
            </div>
          )}
        </div>

        <Composer
          value={draft}
          onChange={setDraft}
          onSend={onSend}
          compare={compare || showCompare}
          onToggleCompare={() => setCompare(c => !c)}
        />
      </main>

      <Settings
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        prefs={prefs}
        setPref={setPref}
      />

      <TweaksPanel>
        <TweakSection label="Look" />
        <TweakRadio
          label="View"
          value={t.view}
          options={[
            { value: 'thread', label: 'Thread' },
            { value: 'empty',  label: 'Empty' },
            { value: 'compare', label: 'Compare' },
          ]}
          onChange={v => setTweak('view', v)}
        />
        <TweakSelect
          label="Theme"
          value={t.theme}
          options={[
            { value: 'plasma',  label: 'Plasma · violet & magenta' },
            { value: 'citrus',  label: 'Citrus · terracotta & lemon' },
            { value: 'tide',    label: 'Tide · coral on mint' },
            { value: 'bauhaus', label: 'Bauhaus · red, mustard & cobalt' },
            { value: 'carbon',  label: 'Carbon · dark with glow' },
          ]}
          onChange={v => setTweak('theme', v)}
        />
        <TweakRadio
          label="Density"
          value={t.density}
          options={['compact', 'regular', 'comfy']}
          onChange={v => setTweak('density', v)}
        />
      </TweaksPanel>
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
