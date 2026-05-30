// Tiny SVG icon set. Use as <Icon name="plus" />.

const ICONS = {
  plus: <path d="M10 4v12M4 10h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />,
  paperclip: <path d="M14.5 6.5L8 13a2.5 2.5 0 1 0 3.5 3.5l6.5-6.5a4 4 0 1 0-5.5-5.5L6 11a5.5 5.5 0 1 0 7.7 7.7" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />,
  send: <path d="M3.5 10L17 3.5L13.5 17l-3-5.5L3.5 10z" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinejoin="round" strokeLinecap="round" />,
  image: <g fill="none" stroke="currentColor" strokeWidth="1.4"><rect x="3" y="3.5" width="14" height="13" rx="2" /><circle cx="7.5" cy="8" r="1.3" /><path d="M3.5 13l3.5-3 3 3 3-4 3.5 4.5" strokeLinejoin="round" /></g>,
  mic: <g fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"><rect x="8" y="3" width="4" height="9" rx="2" /><path d="M5 10a5 5 0 0 0 10 0M10 15v2.5" /></g>,
  globe: <g fill="none" stroke="currentColor" strokeWidth="1.3"><circle cx="10" cy="10" r="6.5" /><path d="M3.5 10h13M10 3.5c2 2 2 11 0 13M10 3.5c-2 2-2 11 0 13" /></g>,
  copy: <g fill="none" stroke="currentColor" strokeWidth="1.4"><rect x="6" y="6" width="10" height="10" rx="2" /><path d="M4 12V5a1 1 0 0 1 1-1h7" /></g>,
  refresh: <path d="M3.5 10a6.5 6.5 0 1 1 1.7 4.4M3.5 16v-3h3" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />,
  thumb: <path d="M5 9h2v8H5zM7 9l3-5c1 0 1.5.5 1.5 1.5L11 8h4c1 0 1.5.5 1.5 1.5L15 16c-.2 1-1 1.5-2 1.5H7" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />,
  share: <g fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"><path d="M10 3v10M6 7l4-4 4 4" /><path d="M4 13v3a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-3" /></g>,
  settings: <g fill="none" stroke="currentColor" strokeWidth="1.4"><circle cx="10" cy="10" r="2.4" /><path d="M10 2.5v2M10 15.5v2M17.5 10h-2M4.5 10h-2M15.3 4.7l-1.4 1.4M6.1 13.9l-1.4 1.4M15.3 15.3l-1.4-1.4M6.1 6.1L4.7 4.7" strokeLinecap="round" /></g>,
  compare: <g fill="none" stroke="currentColor" strokeWidth="1.4"><rect x="3" y="4.5" width="5.5" height="11" rx="1" /><rect x="11.5" y="4.5" width="5.5" height="11" rx="1" /></g>,
  sparkle: <path d="M10 3l1.5 4L16 8.5 11.5 10 10 14l-1.5-4L4 8.5 8.5 7 10 3zM16 14l.7 1.8L18.5 16.5l-1.8.7L16 19l-.7-1.8L13.5 16.5l1.8-.7L16 14z" fill="currentColor" />,
  doc: <g fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M5 3h7l3 3v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z" /><path d="M12 3v3h3M6.5 9.5h6M6.5 12.5h6M6.5 15.5h4" strokeLinecap="round" /></g>,
  x: <path d="M5 5l10 10M15 5L5 15" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />,
  search: <g fill="none" stroke="currentColor" strokeWidth="1.4"><circle cx="9" cy="9" r="5" /><path d="M13 13l3.5 3.5" strokeLinecap="round" /></g>,
  arrowUp: <path d="M10 16V4M5 9l5-5 5 5" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />,
  more: <g fill="currentColor"><circle cx="5" cy="10" r="1.4" /><circle cx="10" cy="10" r="1.4" /><circle cx="15" cy="10" r="1.4" /></g>,
};

function Icon({ name, size = 16 }) {
  const path = ICONS[name];
  if (!path) return null;
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" aria-hidden="true">
      {path}
    </svg>
  );
}

window.Icon = Icon;
