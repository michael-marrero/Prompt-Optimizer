// Phase 9 Wave-0 RED test slice — feedback join-key (DEBT-04).
//
// VALIDATION.md / PROJECT tech-debt: Phase 5 WR-01 feedback join-key
// mismatch. FeedbackButtons currently POSTs `message_id: message.id` —
// the assistant-ui RUNTIME id (FeedbackButtons.tsx:88,108). For a LIVE
// turn that id is NOT the server-assigned assistant message id, so the
// logged feedback row cannot be joined back to the persisted message.
//
// The Phase-9 contract adds an OPTIONAL `assistant_message_id` to the
// Done chunk (Plan 01, this phase). Plan 04 rewires FeedbackButtons to
// use that SERVER id as the `message_id` join key instead of the runtime
// id. This slice asserts the TARGET: the POST body's `message_id` equals
// the server-assigned id sourced from the Done chunk's
// `assistant_message_id`, NOT the assistant-ui `message.id`.
//
// History: shipped as an `it.fails(...)` RED slice in Plan 01 (collectable +
// reporting RED against the baseline component, which sent the runtime id).
// Plan 04 landed the rewire and removed the `.fails` marker (a green assertion
// now): FeedbackButtons reads the server id from the assistant_message_id data
// part (live) or message.id seeded from the DB row id (reload).
//
// This file is intentionally `.ts` (no JSX) per the plan's file list;
// it renders via React.createElement.
//
// Cross-refs:
//   - apps/web/components/FeedbackButtons.tsx:88,108 (message.id → message_id)
//   - apps/api/backends/chunks.py Done.assistant_message_id (Plan 01 field)

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, fireEvent, screen } from "@testing-library/react";
import { createElement } from "react";

// Mock the assistant-ui hook the component subscribes to (same pattern as
// routing-chip.test.tsx). `useMessage()` returns a MessageState whose
// `id` is the RUNTIME id and whose `content` carries the data parts.
vi.mock("@assistant-ui/react", () => ({
  useMessage: vi.fn(),
}));
// sonner toasts fire on the fetch resolution — stub so they no-op.
vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { useMessage } from "@assistant-ui/react";
import {
  FeedbackButtons,
  type FeedbackButtonsProps,
} from "@/components/FeedbackButtons";

const mockedUseMessage = useMessage as unknown as ReturnType<typeof vi.fn>;

// The two ids that MUST differ so the assertion is meaningful.
const RUNTIME_UI_ID = "runtime-ui-id-xyz"; // assistant-ui message.id
// The server-assigned id sourced from the Done chunk's new optional
// `assistant_message_id` field (Plan 01). This is the correct join key.
const SERVER_ASSISTANT_MESSAGE_ID = "msg_srv_from_done_abc123";

beforeEach(() => {
  mockedUseMessage.mockReset();
  // A message whose RUNTIME id differs from the server id. The server id
  // is surfaced on the message content as a data part (the Done chunk's
  // assistant_message_id flows here on a live turn).
  mockedUseMessage.mockReturnValue({
    id: RUNTIME_UI_ID,
    content: [
      { type: "text", text: "the assistant answer" },
      {
        type: "data",
        name: "assistant_message_id",
        data: SERVER_ASSISTANT_MESSAGE_ID,
      },
    ],
  });

  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }),
    ),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("DEBT-04 — feedback join key uses the server assistant_message_id", () => {
  it(
    "POSTs message_id == Done.assistant_message_id (server id), not the runtime message.id (GREEN — Plan 04)",
    () => {
      render(
        createElement<FeedbackButtonsProps>(FeedbackButtons, {
          threadId: "t1",
          prompt: "hi",
        }),
      );

      fireEvent.click(
        screen.getByRole("button", { name: "Mark this route as good" }),
      );

      const fetchMock = fetch as ReturnType<typeof vi.fn>;
      const postCall = fetchMock.mock.calls.find(
        ([url, init]) =>
          url === "/api/feedback" &&
          (init as RequestInit | undefined)?.method === "POST",
      );
      expect(postCall).toBeTruthy();
      const body = JSON.parse((postCall![1] as RequestInit).body as string);

      // TARGET: the join key is the server id from the Done chunk …
      expect(body.message_id).toBe(SERVER_ASSISTANT_MESSAGE_ID);
      // … and explicitly NOT the assistant-ui runtime id.
      expect(body.message_id).not.toBe(RUNTIME_UI_ID);
    },
  );
});
