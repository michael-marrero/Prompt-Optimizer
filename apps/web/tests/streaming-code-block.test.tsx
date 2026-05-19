// Plan 04-06 Wave 5 Task 1 — Vitest+RTL tests for StreamingCodeBlock.
//
// Asserts the fence-state contract (RESEARCH Pattern 5b lines 831-855 +
// Pitfall 5):
//   - isStreamingComplete=false → renders <pre><code class="language-X">RAW</code></pre>
//     with React JSX text-content (NEVER dangerouslySetInnerHTML on raw source)
//   - isStreamingComplete=true → awaits highlightCode then renders the
//     shiki-tokenized HTML once (dangerouslySetInnerHTML on shiki OUTPUT only)
//   - false → true transition triggers EXACTLY ONE highlightCode call
//   - subsequent same-props rerender triggers ZERO additional calls
//   - language=undefined defaults to "text" without throwing (Pitfall 11
//     unknown-language fallback)

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup, act } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

// Mock the shiki module so we can spy on highlightCode + return a deterministic
// tokenized HTML string. The factory is wrapped in vi.hoisted so the mock fn
// is initialized BEFORE the vi.mock call (which Vitest hoists to the top of
// the file at transform time).
const { highlightCodeMock } = vi.hoisted(() => ({
  highlightCodeMock: vi.fn(
    async (_code: string, _lang: string) =>
      "<pre class=\"shiki\"><code><span style=\"color:#0a0\">hi</span></code></pre>",
  ),
}));
vi.mock("@/lib/shiki", () => ({
  highlightCode: highlightCodeMock,
  getHighlighter: vi.fn(),
}));

import { StreamingCodeBlock } from "@/components/StreamingCodeBlock";

beforeEach(() => {
  highlightCodeMock.mockClear();
});

afterEach(() => {
  cleanup();
});

// Helper: flush microtasks so the StreamingCodeBlock's useEffect setHtml
// resolves before assertions read the DOM.
async function flushPromises(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("StreamingCodeBlock fence-state transitions", () => {
  it("renders raw <pre><code class='language-python'>RAW</code></pre> while isStreamingComplete=false; no highlight call yet", () => {
    const { container } = render(
      <StreamingCodeBlock language="python" isStreamingComplete={false}>
        {"print('hi')"}
      </StreamingCodeBlock>,
    );
    const pre = container.querySelector("pre");
    const code = container.querySelector("pre > code");
    expect(pre).not.toBeNull();
    expect(code).not.toBeNull();
    expect(code?.className).toContain("language-python");
    // textContent is the raw code — JSX child, not innerHTML
    expect(code?.textContent).toBe("print('hi')");
    expect(highlightCodeMock).not.toHaveBeenCalled();
  });

  it("transitions false → true triggers EXACTLY ONE highlightCode call and swaps to the tokenized HTML", async () => {
    const { rerender, container } = render(
      <StreamingCodeBlock language="python" isStreamingComplete={false}>
        {"print('hi')"}
      </StreamingCodeBlock>,
    );
    expect(highlightCodeMock).not.toHaveBeenCalled();

    rerender(
      <StreamingCodeBlock language="python" isStreamingComplete={true}>
        {"print('hi')"}
      </StreamingCodeBlock>,
    );
    await flushPromises();
    expect(highlightCodeMock).toHaveBeenCalledTimes(1);
    expect(highlightCodeMock).toHaveBeenCalledWith("print('hi')", "python");

    // The shiki-tokenized HTML is now in the DOM via dangerouslySetInnerHTML
    // on the wrapper div (not the raw <pre>). The mocked output contains
    // a span with shiki-typical class/style.
    expect(container.innerHTML).toContain("color:#0a0");
    expect(container.innerHTML).toContain(">hi<");
  });

  it("same props rerender after a successful highlight does NOT trigger a second highlightCode call (no re-highlight)", async () => {
    const { rerender } = render(
      <StreamingCodeBlock language="python" isStreamingComplete={true}>
        {"print('hi')"}
      </StreamingCodeBlock>,
    );
    await flushPromises();
    expect(highlightCodeMock).toHaveBeenCalledTimes(1);

    rerender(
      <StreamingCodeBlock language="python" isStreamingComplete={true}>
        {"print('hi')"}
      </StreamingCodeBlock>,
    );
    await flushPromises();
    // Still 1 — the effect deps (isStreamingComplete, children, language)
    // are unchanged, so the effect does not re-run.
    expect(highlightCodeMock).toHaveBeenCalledTimes(1);
  });

  it("undefined language defaults to 'text' without throwing", async () => {
    const { container } = render(
      <StreamingCodeBlock language={undefined} isStreamingComplete={true}>
        {"plain text body"}
      </StreamingCodeBlock>,
    );
    await flushPromises();
    expect(highlightCodeMock).toHaveBeenCalledTimes(1);
    expect(highlightCodeMock).toHaveBeenCalledWith("plain text body", "text");
    expect(container.textContent).toContain("hi"); // mocked shiki output
  });

  it("changing children while isStreamingComplete=false does NOT trigger highlightCode (defers until close)", () => {
    const { rerender } = render(
      <StreamingCodeBlock language="python" isStreamingComplete={false}>
        {"def hello():"}
      </StreamingCodeBlock>,
    );
    rerender(
      <StreamingCodeBlock language="python" isStreamingComplete={false}>
        {"def hello():\n    pass"}
      </StreamingCodeBlock>,
    );
    rerender(
      <StreamingCodeBlock language="python" isStreamingComplete={false}>
        {"def hello():\n    pass\nhello()"}
      </StreamingCodeBlock>,
    );
    expect(highlightCodeMock).not.toHaveBeenCalled();
  });
});
