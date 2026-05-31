// Phase 5 Wave 0 — SettingsPage RED test suite (UI-12, UI-SPEC §11).
//
// TODO(07): reconcile in Plan 07-06 (Routing Preferences modal, D-03). Phase 7
// adds a Routing Preferences MODAL as the primary settings surface, but D-03
// explicitly KEEPS the /settings page in scope (BYOK key entry + backend
// toggles may stay on the retained page, or fold into the modal — planner's
// choice). These 5 assertions still PASS today (Phase-7 Wave-0 audit, 07-01)
// because the /settings page is NOT removed in Wave 0. NOT skipped: the
// API-keys / Backends / Computer-use coverage must survive until the owning
// impl plan decides the page-vs-modal split and migrates the assertions.
//
// VALIDATION.md row: "UI-12 component" → `pnpm --dir apps/web test settings-page`.
//
// RED-by-design: the Phase 4 settings page is a single OpenRouter KeyForm; the
// Phase 5 three-section page (API keys / Backends / Computer use) does NOT exist
// yet. The import resolves to the current page but the assertions for the three
// sections + the PATCH-on-toggle behavior fail until the page is rebuilt.
//
// What this asserts (UI-SPEC §11 + §17):
//   - three sections with headings "API keys", "Backends", "Computer use"
//   - toggling a backend switch issues a PATCH carrying backends_enabled
//   - keys render masked only (never the plaintext key)

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import SettingsPage from "@/app/settings/page";

// Phase 9 (DEBT-05) extension mocks sonner so the WR-06 revert slice can
// assert toast.error fired. The existing UI-12 suite does not exercise
// toasts, so stubbing them is inert for those cases.
vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));
import { toast } from "sonner";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          keys: {
            openrouter: { present: true, masked: "sk-or-…ABC" },
            anthropic: { present: false, masked: null },
          },
          backends_enabled: { openrouter: true, claude_code: true, computer_use: false },
          computer_use_opt_in: false,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    ),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("UI-12 component — SettingsPage (UI-SPEC §11)", () => {
  it("UI-12: renders the three section headings (§11 / §17)", async () => {
    render(<SettingsPage />);
    expect(await screen.findByRole("heading", { name: "API keys" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Backends" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Computer use" })).toBeInTheDocument();
  });

  it("UI-12: toggling a backend switch issues a PATCH carrying backends_enabled (§11.2)", async () => {
    render(<SettingsPage />);
    const claudeSwitch = await screen.findByRole("switch", {
      name: "Enable Claude Code backend",
    });
    fireEvent.click(claudeSwitch);
    const fetchMock = fetch as ReturnType<typeof vi.fn>;
    // Find the PATCH call.
    const patchCall = fetchMock.mock.calls.find(
      ([, init]) => (init as RequestInit | undefined)?.method === "PATCH",
    );
    expect(patchCall).toBeTruthy();
    const body = JSON.parse((patchCall![1] as RequestInit).body as string);
    expect(body).toHaveProperty("backends_enabled");
  });

  it("UI-12: keys render masked only — the plaintext key never appears", async () => {
    render(<SettingsPage />);
    expect(await screen.findByText("sk-or-…ABC")).toBeInTheDocument();
    // A fully-formed plaintext OpenRouter key must never be in the DOM.
    expect(document.body.textContent).not.toMatch(/sk-or-v1-[A-Za-z0-9]/);
  });

  it("UI-12: the computer-use section shows the security-conscious helper copy (§17)", async () => {
    render(<SettingsPage />);
    expect(
      await screen.findByText(
        "Computer use can browse and act on web pages on your behalf. It is off by default. Visited pages may attempt prompt injection — only enable it when you understand the risk.",
      ),
    ).toBeInTheDocument();
  });

  it("UI-12: the Anthropic key input uses the §17 placeholder 'sk-ant-...'", async () => {
    render(<SettingsPage />);
    const apiKeys = (await screen.findByRole("heading", { name: "API keys" })).closest(
      "section",
    ) as HTMLElement;
    expect(within(apiKeys).getByPlaceholderText("sk-ant-...")).toBeInTheDocument();
  });
});

// =====================================================================
// Phase 9 Wave-0 RED slices — DEBT-05 (IN-02 allowlist persist + WR-06
// PATCH-failure revert)
// =====================================================================
//
// DEBT-05 covers two Phase-7 tech-debt items:
//   - IN-02: per-model allowlist toggles are NO-OPS (local-only state that
//     does not persist) — a toggle must SURVIVE a remount.
//   - WR-06: a fire-and-forget settings PATCH that does not surface a
//     failure — a failed PATCH must toast + REVERT the optimistic value.
//
// Both slices use `it.fails(...)` so they are COLLECTABLE and report
// failing (RED) against today's settings surface (the persisted per-model
// allowlist control does not exist yet, and the IN-02 toggle is a no-op).
// The owning plan removes the `.fails` marker when the behavior lands.

describe("DEBT-05 — settings allowlist persistence + PATCH-failure revert (RED)", () => {
  it.fails(
    "DEBT-05 IN-02: a per-model allowlist toggle survives a remount (persisted, not local-only)",
    async () => {
      const { unmount } = render(<SettingsPage />);

      // The per-model allowlist toggle (Routing Preferences, IN-02). Today
      // this control is absent / no-op, so the query throws → RED.
      const toggle = await screen.findByRole("switch", {
        name: /allow .* for routing/i,
      });
      // Capture its initial pressed state, flip it, and remount.
      const before = toggle.getAttribute("aria-checked");
      fireEvent.click(toggle);

      unmount();
      render(<SettingsPage />);

      const reloaded = await screen.findByRole("switch", {
        name: /allow .* for routing/i,
      });
      // Target: the flipped value PERSISTED across the remount (it was
      // written to the server, not just held in local component state).
      expect(reloaded.getAttribute("aria-checked")).not.toBe(before);
    },
  );

  it.fails(
    "DEBT-05 WR-06: a failed allowlist PATCH surfaces a toast AND reverts the optimistic value",
    async () => {
      // GET succeeds (initial load), the PATCH rejects (server 500).
      const fetchMock = fetch as ReturnType<typeof vi.fn>;
      fetchMock.mockImplementation((_url: string, init?: RequestInit) => {
        if (init?.method === "PATCH") {
          return Promise.resolve(new Response("err", { status: 500 }));
        }
        return Promise.resolve(
          new Response(
            JSON.stringify({
              keys: {
                openrouter: { present: true, masked: "sk-or-…ABC" },
                anthropic: { present: false, masked: null },
              },
              backends_enabled: {
                openrouter: true,
                claude_code: true,
                computer_use: false,
              },
              computer_use_opt_in: false,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      });

      render(<SettingsPage />);

      const toggle = await screen.findByRole("switch", {
        name: /allow .* for routing/i,
      });
      const before = toggle.getAttribute("aria-checked");
      fireEvent.click(toggle);

      // Let the rejected PATCH settle.
      await Promise.resolve();
      await Promise.resolve();

      // Target: a failure toast fired …
      expect(toast.error).toHaveBeenCalled();
      // … and the optimistic value REVERTED to its pre-click state.
      const reverted = await screen.findByRole("switch", {
        name: /allow .* for routing/i,
      });
      expect(reverted.getAttribute("aria-checked")).toBe(before);
    },
  );
});
