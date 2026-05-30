// Phase 5 Wave 0 — page-shell dispatch RED test suite (UI-05/UI-09/UI-10/UI-15).
//
// VALIDATION.md row: "page shell dispatch" → `pnpm --dir apps/web test page-shell`.
//
// RED-by-design: the per-backend bubble dispatch seam `@/components/MessageBubble`
// (the contract 05-06 rebuilds the page shell around) does NOT exist yet, and
// neither do CodeBubble / ComputerUseBubble / FeedbackButtons. The imports fail
// to resolve so every `it` is collected and reported FAILED until they ship.
//
// What this asserts (PATTERNS bubble dispatch + UI-SPEC §16):
//   (a) per-backend dispatch — claude_code mounts CodeBubble, computer_use mounts
//       ComputerUseBubble, openrouter/default mounts ChatBubble
//   (b) a SidebarProvider is present in the assembled shell
//   (c) FeedbackButtons are mounted on assistant messages
//
// The dispatch is tested at the seam (MessageBubble) so it is assertable without
// the live assistant-ui runtime. The shell + FeedbackButtons mounting are tested
// by rendering MessageBubble for an assistant message and the shell wrapper.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MessageBubble } from "@/components/MessageBubble";
import { PageShell } from "@/components/PageShell";

vi.mock("@assistant-ui/react", () => ({
  useMessage: vi.fn(),
  useMessageRuntime: vi.fn(() => ({ reload: vi.fn() })),
}));

import { useMessage } from "@assistant-ui/react";

const mockedUseMessage = useMessage as unknown as ReturnType<typeof vi.fn>;

function messageForBackend(backend: string) {
  return {
    id: "m-1",
    status: { type: "complete" },
    content: [
      {
        type: "data",
        name: "routing",
        data: {
          backend,
          model_or_agent: backend === "openrouter" ? "openai/gpt-5" : backend,
          rationale: "test",
          confidence: 0.9,
          signals: {},
        },
      },
      { type: "text", text: "answer body" },
    ],
  };
}

beforeEach(() => {
  mockedUseMessage.mockReset();
});

describe("page shell — per-backend bubble dispatch", () => {
  it("UI-09: a claude_code routing part mounts CodeBubble", () => {
    mockedUseMessage.mockReturnValue(messageForBackend("claude_code"));
    render(<MessageBubble />);
    expect(screen.getByTestId("code-bubble")).toBeInTheDocument();
  });

  it("UI-10: a computer_use routing part mounts ComputerUseBubble", () => {
    mockedUseMessage.mockReturnValue(messageForBackend("computer_use"));
    render(<MessageBubble />);
    expect(screen.getByTestId("computer-use-bubble")).toBeInTheDocument();
  });

  it("UI-05: an openrouter routing part mounts the default ChatBubble", () => {
    mockedUseMessage.mockReturnValue(messageForBackend("openrouter"));
    render(<MessageBubble />);
    expect(screen.getByTestId("chat-bubble")).toBeInTheDocument();
  });

  it("UI-05: a message with no routing part defaults to ChatBubble", () => {
    mockedUseMessage.mockReturnValue({
      id: "m-1",
      status: { type: "complete" },
      content: [{ type: "text", text: "answer body" }],
    });
    render(<MessageBubble />);
    expect(screen.getByTestId("chat-bubble")).toBeInTheDocument();
  });

  it("UI-15: FeedbackButtons are mounted on assistant messages", () => {
    mockedUseMessage.mockReturnValue(messageForBackend("openrouter"));
    render(<MessageBubble />);
    expect(
      screen.getByRole("button", { name: "Mark this route as wrong" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Mark this route as good" }),
    ).toBeInTheDocument();
  });

  it("shell: a SidebarProvider is present in the assembled page shell", () => {
    const { container } = render(<PageShell />);
    // shadcn SidebarProvider renders a wrapper carrying data-slot="sidebar-wrapper".
    expect(
      container.querySelector('[data-slot="sidebar-wrapper"]'),
    ).not.toBeNull();
  });
});
