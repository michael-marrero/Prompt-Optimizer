// Plan 04-07 Wave 6 — FirstRunModal + KeyForm RTL test suite.
//
// VALIDATION.md row: UI-13 (unit) + D-18 (KeyForm hygiene).
//
// What this asserts (UI-SPEC §10 + §17 byte-for-byte + Plan 04-07 must_haves):
//   - Heading text: "Connect OpenRouter to get started"
//   - Body text: "Prompt-Optimizer routes your prompts to the best model.
//     OpenRouter is the gateway to most chat models — start by pasting your key."
//   - Primary button: "Save & continue"
//   - Link: openrouter.ai/keys with href + target=_blank + rel=noopener noreferrer
//   - Input aria-label "OpenRouter API key" and placeholder "sk-or-v1-..."
//   - Submitting with EMPTY value does NOT call postSettings
//   - Submitting with a real-shaped key calls postSettings("openrouter", key)
//     AND dispatches "pomu:key-saved" window event AND fires toast.success
//   - On postSettings reject with 503 / "unavailable", toast.error fires
//     the UI-SPEC §10.5 network-down string
//   - On postSettings reject with any other error, toast.error fires the
//     "That key doesn't look right" string
//
// Cross-refs:
//   - 04-UI-SPEC.md §10 (modal copy) + §17 (canonical strings)
//   - 04-CONTEXT.md D-18 (KeyForm hygiene — no console.*)
//   - 04-CONTEXT.md D-19 (pomu:key-saved event)

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

vi.mock("@/lib/api-client", () => ({
  postSettings: vi.fn(),
}));
vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { postSettings } from "@/lib/api-client";
import { toast } from "sonner";
import { FirstRunModal } from "@/components/FirstRunModal";
import { KeyForm } from "@/components/KeyForm";

const mockedPostSettings = postSettings as unknown as ReturnType<typeof vi.fn>;
const mockedToastSuccess = toast.success as unknown as ReturnType<typeof vi.fn>;
const mockedToastError = toast.error as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockedPostSettings.mockReset();
  mockedToastSuccess.mockReset();
  mockedToastError.mockReset();
});

describe("UI-13 unit — FirstRunModal copy + ARIA", () => {
  it("renders the heading 'Connect OpenRouter to get started'", () => {
    render(<FirstRunModal open={true} />);
    expect(
      screen.getByText("Connect OpenRouter to get started"),
    ).toBeInTheDocument();
  });

  it("renders the body text from UI-SPEC §10.2 byte-for-byte", () => {
    render(<FirstRunModal open={true} />);
    expect(
      screen.getByText(
        "Prompt-Optimizer routes your prompts to the best model. OpenRouter is the gateway to most chat models — start by pasting your key.",
      ),
    ).toBeInTheDocument();
  });

  it("renders the Input with aria-label 'OpenRouter API key' and placeholder 'sk-or-v1-...'", () => {
    render(<FirstRunModal open={true} />);
    const input = screen.getByLabelText("OpenRouter API key") as HTMLInputElement;
    expect(input.placeholder).toBe("sk-or-v1-...");
  });

  it("renders the primary button 'Save & continue'", () => {
    render(<FirstRunModal open={true} />);
    expect(
      screen.getByRole("button", { name: "Save & continue" }),
    ).toBeInTheDocument();
  });

  it("renders an external link to openrouter.ai/keys with target=_blank rel=noopener noreferrer", () => {
    render(<FirstRunModal open={true} />);
    const link = screen.getByRole("link", {
      name: /openrouter\.ai\/keys/,
    }) as HTMLAnchorElement;
    expect(link.href).toBe("https://openrouter.ai/keys");
    expect(link.target).toBe("_blank");
    expect(link.rel).toContain("noopener");
    expect(link.rel).toContain("noreferrer");
  });

  it("does NOT render when open={false}", () => {
    render(<FirstRunModal open={false} />);
    expect(
      screen.queryByText("Connect OpenRouter to get started"),
    ).not.toBeInTheDocument();
  });
});

describe("UI-13 unit — KeyForm submit flow + D-19 dispatch + D-18 hygiene", () => {
  it("does NOT call postSettings when the value is empty", () => {
    render(<KeyForm mode="blocking" />);
    const submit = screen.getByRole("button", { name: "Save & continue" });
    fireEvent.click(submit);
    expect(mockedPostSettings).not.toHaveBeenCalled();
  });

  it("calls postSettings('openrouter', value) on submit with a real-shaped key", async () => {
    mockedPostSettings.mockResolvedValue({
      keys: { openrouter: { present: true, masked: "sk-or-…XXX" } },
    });
    render(<KeyForm mode="blocking" />);
    const input = screen.getByLabelText("OpenRouter API key");
    fireEvent.change(input, { target: { value: "sk-or-v1-" + "X".repeat(48) } });
    fireEvent.click(screen.getByRole("button", { name: "Save & continue" }));
    await waitFor(() => {
      expect(mockedPostSettings).toHaveBeenCalledWith(
        "openrouter",
        "sk-or-v1-" + "X".repeat(48),
      );
    });
  });

  it("fires toast.success 'OpenRouter connected — try a prompt!' on resolve", async () => {
    mockedPostSettings.mockResolvedValue({
      keys: { openrouter: { present: true, masked: "sk-or-…XXX" } },
    });
    render(<KeyForm mode="blocking" />);
    fireEvent.change(screen.getByLabelText("OpenRouter API key"), {
      target: { value: "sk-or-v1-AAA" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save & continue" }));
    await waitFor(() => {
      expect(mockedToastSuccess).toHaveBeenCalledWith(
        "OpenRouter connected — try a prompt!",
      );
    });
  });

  it("dispatches a 'pomu:key-saved' CustomEvent on the window after a successful submit (D-19)", async () => {
    mockedPostSettings.mockResolvedValue({
      keys: { openrouter: { present: true, masked: "sk-or-…ZZZ" } },
    });
    const dispatchSpy = vi.spyOn(window, "dispatchEvent");
    render(<KeyForm mode="blocking" />);
    fireEvent.change(screen.getByLabelText("OpenRouter API key"), {
      target: { value: "sk-or-v1-ZZZ" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save & continue" }));
    await waitFor(() => {
      const events = dispatchSpy.mock.calls.map((c) => c[0]);
      expect(
        events.some(
          (e) => e instanceof CustomEvent && e.type === "pomu:key-saved",
        ),
      ).toBe(true);
    });
    dispatchSpy.mockRestore();
  });

  it("fires toast.error network-down catalog string on 503 / 'unavailable' error", async () => {
    mockedPostSettings.mockRejectedValue(
      new Error("postSettings failed (503 Service Unavailable): API unavailable"),
    );
    render(<KeyForm mode="blocking" />);
    fireEvent.change(screen.getByLabelText("OpenRouter API key"), {
      target: { value: "sk-or-v1-NETDOWN" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save & continue" }));
    await waitFor(() => {
      expect(mockedToastError).toHaveBeenCalledWith(
        "Couldn't save the key — is the local API running?",
      );
    });
  });

  it("fires toast.error validation-error catalog string on a generic 400 error", async () => {
    mockedPostSettings.mockRejectedValue(
      new Error("postSettings failed (400 Bad Request): invalid key"),
    );
    render(<KeyForm mode="blocking" />);
    fireEvent.change(screen.getByLabelText("OpenRouter API key"), {
      target: { value: "sk-or-v1-BAD" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save & continue" }));
    await waitFor(() => {
      expect(mockedToastError).toHaveBeenCalledWith(
        "That key doesn't look right. Check it and try again.",
      );
    });
  });
});

describe("UI-13 unit — KeyForm console hygiene (D-18 in-component enforcement)", () => {
  let consoleLogSpy: ReturnType<typeof vi.spyOn>;
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;
  let consoleWarnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    consoleLogSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    consoleWarnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    consoleLogSpy.mockRestore();
    consoleErrorSpy.mockRestore();
    consoleWarnSpy.mockRestore();
  });

  it("submitting NEVER calls console.log / console.error / console.warn (D-18 belt)", async () => {
    mockedPostSettings.mockResolvedValue({
      keys: { openrouter: { present: true, masked: "sk-or-…XXX" } },
    });
    render(<KeyForm mode="blocking" />);
    fireEvent.change(screen.getByLabelText("OpenRouter API key"), {
      target: { value: "sk-or-v1-NOLOG" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save & continue" }));
    await waitFor(() => {
      expect(mockedPostSettings).toHaveBeenCalled();
    });
    expect(consoleLogSpy).not.toHaveBeenCalled();
    expect(consoleErrorSpy).not.toHaveBeenCalled();
    expect(consoleWarnSpy).not.toHaveBeenCalled();
  });

  it("on submit failure, console.* still NEVER fires (the literal key cannot leak via console)", async () => {
    mockedPostSettings.mockRejectedValue(
      new Error("postSettings failed (400): bad"),
    );
    render(<KeyForm mode="blocking" />);
    fireEvent.change(screen.getByLabelText("OpenRouter API key"), {
      target: { value: "sk-or-v1-SECRET" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save & continue" }));
    await waitFor(() => {
      expect(mockedToastError).toHaveBeenCalled();
    });
    expect(consoleLogSpy).not.toHaveBeenCalled();
    expect(consoleErrorSpy).not.toHaveBeenCalled();
    expect(consoleWarnSpy).not.toHaveBeenCalled();
  });
});

describe("UI-13 unit — KeyForm settings-mode label switching", () => {
  it("renders 'Save & continue' label in blocking mode regardless of value", () => {
    render(<KeyForm mode="blocking" />);
    expect(
      screen.getByRole("button", { name: "Save & continue" }),
    ).toBeInTheDocument();
  });

  it("renders 'Update key' label in settings mode when value is empty", () => {
    render(<KeyForm mode="settings" />);
    expect(
      screen.getByRole("button", { name: "Update key" }),
    ).toBeInTheDocument();
  });
});
