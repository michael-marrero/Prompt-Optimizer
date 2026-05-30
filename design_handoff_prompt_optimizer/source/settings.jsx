// Routing preferences modal.

function Settings({ open, onClose, prefs, setPref }) {
  const { MODELS } = window.PO_DATA;
  if (!open) return null;
  return (
    <div className="settings-scrim" onClick={onClose}>
      <div className="settings" onClick={e => e.stopPropagation()}>
        <div className="settings-head">
          <div className="settings-title">Routing preferences</div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <Icon name="x" />
          </button>
        </div>
        <div className="settings-body">

          <section className="settings-section">
            <h3>Optimize for</h3>
            <div className="settings-row">
              <div className="settings-row-label">
                <div className="settings-row-name">Priority</div>
                <div className="settings-row-desc">
                  Bias routing toward what matters most to you on each request.
                </div>
              </div>
              <div className="priority-seg">
                {['Quality', 'Balanced', 'Speed', 'Cost'].map(p => (
                  <button
                    key={p}
                    className={prefs.priority === p ? 'on' : ''}
                    onClick={() => setPref('priority', p)}
                  >{p}</button>
                ))}
              </div>
            </div>
            <div className="settings-row">
              <div className="settings-row-label">
                <div className="settings-row-name">Show routing badge</div>
                <div className="settings-row-desc">
                  Display which model answered after each response.
                </div>
              </div>
              <button
                className={`toggle ${prefs.showBadge ? 'on' : ''}`}
                onClick={() => setPref('showBadge', !prefs.showBadge)}
                aria-pressed={prefs.showBadge}
              />
            </div>
            <div className="settings-row">
              <div className="settings-row-label">
                <div className="settings-row-name">Cost-aware fallback</div>
                <div className="settings-row-desc">
                  Use a cheaper model when the prompt is simple enough.
                </div>
              </div>
              <button
                className={`toggle ${prefs.costAware ? 'on' : ''}`}
                onClick={() => setPref('costAware', !prefs.costAware)}
                aria-pressed={prefs.costAware}
              />
            </div>
          </section>

          <section className="settings-section">
            <h3>Allowed models · {MODELS.length} of {MODELS.length}</h3>
            {MODELS.map(m => (
              <div className="model-pref" key={m.id}>
                <span className="model-dot" />
                <span className="model-name">{m.label}</span>
                <span className="model-vendor">{m.vendor}</span>
                <button className="toggle on" aria-pressed="true" />
              </div>
            ))}
          </section>

          <section className="settings-section">
            <h3>Privacy</h3>
            <div className="settings-row">
              <div className="settings-row-label">
                <div className="settings-row-name">Zero data retention</div>
                <div className="settings-row-desc">
                  Route only to providers that don't retain prompt data.
                </div>
              </div>
              <button
                className={`toggle ${prefs.zdr ? 'on' : ''}`}
                onClick={() => setPref('zdr', !prefs.zdr)}
                aria-pressed={prefs.zdr}
              />
            </div>
          </section>

        </div>
      </div>
    </div>
  );
}

window.Settings = Settings;
