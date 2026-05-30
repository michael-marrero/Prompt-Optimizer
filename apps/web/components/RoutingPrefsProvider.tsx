"use client";

// Phase 7 Plan 07-07 — RoutingPrefsProvider (D-03 / showBadge seam).
//
// A small client context owning (a) the Routing Preferences modal open/close
// state and (b) the routing prefs. priority / cost_aware_fallback /
// zero_data_retention persist server-side via PATCH /api/settings (the Next
// proxy → FastAPI, UI-17); showBadge is a client-only display pref (gates the
// auto optimized pill — UI-SPEC §Copywriting "showBadge semantics") persisted to
// localStorage. useShowBadge() is consumed by RoutingChip (07-03) to gate the
// AUTO pill only; the D-08 manual-override pill is unaffected.
//
// No-provider safety: useShowBadge() / useRoutingPrefs() return defaults when no
// provider is mounted (showBadge=true, open handlers are no-ops) so RoutingChip
// renders correctly in isolation (routing-chip.test.tsx has no provider).

import * as React from "react";

export type Priority = "quality" | "balanced" | "speed" | "cost";

interface RoutingPrefsContextValue {
  open: boolean;
  priority: Priority;
  costAwareFallback: boolean;
  zeroDataRetention: boolean;
  showBadge: boolean;
  openRoutingPrefs: () => void;
  closeRoutingPrefs: () => void;
  setPriority: (p: Priority) => void;
  setCostAwareFallback: (v: boolean) => void;
  setZeroDataRetention: (v: boolean) => void;
  setShowBadge: (v: boolean) => void;
}

const DEFAULT: RoutingPrefsContextValue = {
  open: false,
  priority: "quality",
  costAwareFallback: false,
  zeroDataRetention: false,
  showBadge: true,
  openRoutingPrefs: () => undefined,
  closeRoutingPrefs: () => undefined,
  setPriority: () => undefined,
  setCostAwareFallback: () => undefined,
  setZeroDataRetention: () => undefined,
  setShowBadge: () => undefined,
};

const RoutingPrefsContext = React.createContext<RoutingPrefsContextValue>(DEFAULT);

const SHOW_BADGE_KEY = "po:show-routing-badge";

export function RoutingPrefsProvider({
  children,
}: {
  children: React.ReactNode;
}): React.JSX.Element {
  const [open, setOpen] = React.useState(false);
  const [priority, setPriorityState] = React.useState<Priority>("quality");
  const [costAwareFallback, setCostAwareState] = React.useState(false);
  const [zeroDataRetention, setZdrState] = React.useState(false);
  const [showBadge, setShowBadgeState] = React.useState(true);

  // Init prefs from GET /api/settings (server-persisted) + showBadge from
  // localStorage (client-only display pref).
  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch("/api/settings");
        if (!cancelled && res.ok) {
          const s = (await res.json()) as Record<string, unknown>;
          if (s.priority === "quality" || s.priority === "balanced" || s.priority === "speed" || s.priority === "cost") {
            setPriorityState(s.priority);
          }
          if (typeof s.cost_aware_fallback === "boolean") setCostAwareState(s.cost_aware_fallback);
          if (typeof s.zero_data_retention === "boolean") setZdrState(s.zero_data_retention);
        }
      } catch {
        /* offline — keep defaults */
      }
    })();
    try {
      const sb = localStorage.getItem(SHOW_BADGE_KEY);
      if (sb !== null) setShowBadgeState(sb === "true");
    } catch {
      /* no localStorage */
    }
    return () => {
      cancelled = true;
    };
  }, []);

  // Merge-patch a single pref to the Next proxy (never browser→FastAPI; UI-17).
  const patchPref = React.useCallback((patch: Record<string, unknown>) => {
    void fetch("/api/settings", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }).catch(() => undefined);
  }, []);

  const setPriority = React.useCallback(
    (p: Priority) => {
      setPriorityState(p);
      patchPref({ priority: p });
    },
    [patchPref],
  );
  const setCostAwareFallback = React.useCallback(
    (v: boolean) => {
      setCostAwareState(v);
      patchPref({ cost_aware_fallback: v });
    },
    [patchPref],
  );
  const setZeroDataRetention = React.useCallback(
    (v: boolean) => {
      setZdrState(v);
      patchPref({ zero_data_retention: v });
    },
    [patchPref],
  );
  const setShowBadge = React.useCallback((v: boolean) => {
    setShowBadgeState(v);
    try {
      localStorage.setItem(SHOW_BADGE_KEY, String(v));
    } catch {
      /* ignore */
    }
  }, []);

  const value: RoutingPrefsContextValue = {
    open,
    priority,
    costAwareFallback,
    zeroDataRetention,
    showBadge,
    openRoutingPrefs: React.useCallback(() => setOpen(true), []),
    closeRoutingPrefs: React.useCallback(() => setOpen(false), []),
    setPriority,
    setCostAwareFallback,
    setZeroDataRetention,
    setShowBadge,
  };

  return (
    <RoutingPrefsContext.Provider value={value}>
      {children}
    </RoutingPrefsContext.Provider>
  );
}

export function useRoutingPrefs(): RoutingPrefsContextValue {
  return React.useContext(RoutingPrefsContext);
}

/** Gate for the AUTO optimized pill (RoutingChip, 07-03). Defaults to true when
 * no provider is mounted (e.g. unit tests) so the pill renders by default. */
export function useShowBadge(): boolean {
  return React.useContext(RoutingPrefsContext).showBadge;
}
