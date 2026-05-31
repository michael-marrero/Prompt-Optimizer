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
//
// DEBT-05 (Phase 9):
//   - WR-06: patchPref used to swallow rejections silently (fire-and-forget).
//     It is now an awaited write that, on rejection, surfaces a toast AND
//     reverts the optimistic value (mirrors app/settings/page.tsx) so the UI
//     cannot silently diverge from the server (T-09-10).
//   - IN-02: the per-model allowlist toggle (previously pure local useState in
//     RoutingPrefsModal, reset on remount) is lifted here and persisted so it
//     survives a remount.

import * as React from "react";
import { toast } from "sonner";

export type Priority = "quality" | "balanced" | "speed" | "cost";

interface RoutingPrefsContextValue {
  open: boolean;
  priority: Priority;
  costAwareFallback: boolean;
  zeroDataRetention: boolean;
  showBadge: boolean;
  /** Per-model routing allowlist (slug → allowed). DEBT-05 IN-02: persisted so
   *  it survives a remount; defaults to all-allowed (absent slug ⇒ allowed). */
  modelAllowlist: Record<string, boolean>;
  openRoutingPrefs: () => void;
  closeRoutingPrefs: () => void;
  setPriority: (p: Priority) => void;
  setCostAwareFallback: (v: boolean) => void;
  setZeroDataRetention: (v: boolean) => void;
  setShowBadge: (v: boolean) => void;
  setModelAllowed: (slug: string, allowed: boolean) => void;
}

const DEFAULT: RoutingPrefsContextValue = {
  open: false,
  priority: "quality",
  costAwareFallback: false,
  zeroDataRetention: false,
  showBadge: true,
  modelAllowlist: {},
  openRoutingPrefs: () => undefined,
  closeRoutingPrefs: () => undefined,
  setPriority: () => undefined,
  setCostAwareFallback: () => undefined,
  setZeroDataRetention: () => undefined,
  setShowBadge: () => undefined,
  setModelAllowed: () => undefined,
};

const RoutingPrefsContext = React.createContext<RoutingPrefsContextValue>(DEFAULT);

const SHOW_BADGE_KEY = "po:show-routing-badge";
// DEBT-05 IN-02 — the persisted allowlist store key. Mirrors the showBadge
// localStorage precedent so a toggled value survives a remount even before the
// 09-05 backend read-back endpoint lands.
const ALLOWLIST_KEY = "po:model-allowlist";

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
  const [modelAllowlist, setModelAllowlistState] = React.useState<
    Record<string, boolean>
  >({});

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
    // DEBT-05 IN-02 — read back the persisted allowlist (survives a remount).
    try {
      const raw = localStorage.getItem(ALLOWLIST_KEY);
      if (raw !== null) {
        const parsed = JSON.parse(raw) as unknown;
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
          setModelAllowlistState(parsed as Record<string, boolean>);
        }
      }
    } catch {
      /* no localStorage / malformed — keep default (all allowed) */
    }
    return () => {
      cancelled = true;
    };
  }, []);

  // DEBT-05 WR-06 — merge-patch a single pref to the Next proxy (never
  // browser→FastAPI; UI-17). No longer fire-and-forget: the write is AWAITED and
  // a rejection (network error OR a non-2xx upstream) runs `rollback` to revert
  // the optimistic value and surfaces a toast, mirroring app/settings/page.tsx.
  const patchPref = React.useCallback(
    async (
      patch: Record<string, unknown>,
      rollback: () => void,
    ): Promise<void> => {
      try {
        const res = await fetch("/api/settings", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(patch),
        });
        if (!res.ok) throw new Error(`PATCH /api/settings failed (${res.status})`);
      } catch {
        rollback();
        toast.error("Couldn't save your routing preference — is the local API running?");
      }
    },
    [],
  );

  const setPriority = React.useCallback(
    (p: Priority) => {
      const previous = priority;
      setPriorityState(p);
      void patchPref({ priority: p }, () => setPriorityState(previous));
    },
    [patchPref, priority],
  );
  const setCostAwareFallback = React.useCallback(
    (v: boolean) => {
      const previous = costAwareFallback;
      setCostAwareState(v);
      void patchPref({ cost_aware_fallback: v }, () => setCostAwareState(previous));
    },
    [patchPref, costAwareFallback],
  );
  const setZeroDataRetention = React.useCallback(
    (v: boolean) => {
      const previous = zeroDataRetention;
      setZdrState(v);
      void patchPref({ zero_data_retention: v }, () => setZdrState(previous));
    },
    [patchPref, zeroDataRetention],
  );
  const setShowBadge = React.useCallback((v: boolean) => {
    setShowBadgeState(v);
    try {
      localStorage.setItem(SHOW_BADGE_KEY, String(v));
    } catch {
      /* ignore */
    }
  }, []);

  // DEBT-05 IN-02 + WR-06 — persist a per-model allowlist toggle. Optimistically
  // updates + writes to localStorage (read back on remount), PATCHes the server,
  // and on a failed PATCH reverts the value (state + localStorage) and toasts.
  const setModelAllowed = React.useCallback(
    (slug: string, allowed: boolean) => {
      setModelAllowlistState((prev) => {
        const previous = prev;
        const next = { ...prev, [slug]: allowed };
        try {
          localStorage.setItem(ALLOWLIST_KEY, JSON.stringify(next));
        } catch {
          /* no localStorage — server PATCH is still the source of truth */
        }
        void patchPref({ model_allowlist: next }, () => {
          setModelAllowlistState(previous);
          try {
            localStorage.setItem(ALLOWLIST_KEY, JSON.stringify(previous));
          } catch {
            /* ignore */
          }
        });
        return next;
      });
    },
    [patchPref],
  );

  const value: RoutingPrefsContextValue = {
    open,
    priority,
    costAwareFallback,
    zeroDataRetention,
    showBadge,
    modelAllowlist,
    openRoutingPrefs: React.useCallback(() => setOpen(true), []),
    closeRoutingPrefs: React.useCallback(() => setOpen(false), []),
    setPriority,
    setCostAwareFallback,
    setZeroDataRetention,
    setShowBadge,
    setModelAllowed,
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
