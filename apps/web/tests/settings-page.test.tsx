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
