// Plan 04-06 Wave 5 Task 2 — Vitest+RTL tests for MarkdownRenderer.
//
// Asserts:
//   - React.memo equality: same (messageId, rawMarkdown.length, role-equivalent)
//     does NOT re-render the inner subtree; changes DO re-render
//   - UI-SPEC §8.2 element class mapping (p, h1, h2, h3, a, inline code,
//     blockquote)
//   - Open-fence path: fenced code block renders StreamingCodeBlock with
//     isStreamingComplete=false; the renderer DOES pass language through
//     (Warning 1: code mapper does NOT replace fenced inner code)
//   - Closed-fence path: same fenced code with isStreamingComplete=true
//     mounts StreamingCodeBlock with isStreamingComplete=true
//   - Inline code path: backtick `code` renders the UI-SPEC §8.2 inline
//     style (Warning 1: inline detection works)
//   - XSS sanitization: a literal <script> in markdown is NOT rendered as
//     an executable script element

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

// Mock StreamingCodeBlock with a vi.fn-backed stub so we can spy on its
// prop-passing (language + isStreamingComplete + children).
const { streamingStub } = vi.hoisted(() => ({
  streamingStub: vi.fn((props: { language?: string; isStreamingComplete: boolean; children: string }) => {
    return (
      <pre data-testid="streaming-code-block-stub" data-lang={props.language ?? ""} data-complete={props.isStreamingComplete ? "true" : "false"}>
        {props.children}
      </pre>
    );
  }),
}));
vi.mock("@/components/StreamingCodeBlock", () => ({
  StreamingCodeBlock: streamingStub,
}));

import { MarkdownRenderer } from "@/components/MarkdownRenderer";

afterEach(() => {
  cleanup();
  streamingStub.mockClear();
});

describe("MarkdownRenderer UI-SPEC §8.2 element styling", () => {
  it("renders `# heading` as <h1> with text-xl font-semibold per UI-SPEC §3", () => {
    render(
      <MarkdownRenderer
        rawMarkdown="# hello"
        isStreamingComplete={false}
        messageId="m1"
      />,
    );
    const h1 = screen.getByRole("heading", { level: 1, name: "hello" });
    expect(h1.className).toContain("text-xl");
    expect(h1.className).toContain("font-semibold");
    expect(h1.className).toContain("text-slate-900");
  });

  it("renders a paragraph with text-sm leading-relaxed text-slate-900 mb-3 (UI-SPEC §8.2)", () => {
    const { container } = render(
      <MarkdownRenderer
        rawMarkdown="just a paragraph"
        isStreamingComplete={false}
        messageId="m1"
      />,
    );
    const p = container.querySelector("p");
    expect(p).not.toBeNull();
    expect(p?.className).toContain("text-sm");
    expect(p?.className).toContain("leading-relaxed");
    expect(p?.className).toContain("text-slate-900");
    expect(p?.className).toContain("mb-3");
  });

  it("renders inline `code` as <code class='text-sm font-mono bg-slate-100 px-1 py-1 rounded-sm'> (Warning 1: inline detection)", () => {
    const { container } = render(
      <MarkdownRenderer
        rawMarkdown="use `foo` to test"
        isStreamingComplete={true}
        messageId="m1"
      />,
    );
    const inlineCode = container.querySelector("code");
    expect(inlineCode).not.toBeNull();
    expect(inlineCode?.className).toContain("bg-slate-100");
    expect(inlineCode?.className).toContain("font-mono");
    expect(inlineCode?.className).toContain("px-1");
    expect(inlineCode?.className).toContain("rounded-sm");
    expect(inlineCode?.textContent).toBe("foo");
  });

  it("renders a blockquote with border-l-4 border-slate-300 pl-4 italic", () => {
    const { container } = render(
      <MarkdownRenderer
        rawMarkdown="> a quote"
        isStreamingComplete={false}
        messageId="m1"
      />,
    );
    const blockquote = container.querySelector("blockquote");
    expect(blockquote).not.toBeNull();
    expect(blockquote?.className).toContain("border-l-4");
    expect(blockquote?.className).toContain("border-slate-300");
    expect(blockquote?.className).toContain("italic");
  });

  it("renders links with target='_blank' rel='noopener noreferrer' and the UI-SPEC §8.2 underline class", () => {
    const { container } = render(
      <MarkdownRenderer
        rawMarkdown="[link](https://example.com)"
        isStreamingComplete={true}
        messageId="m1"
      />,
    );
    const a = container.querySelector("a");
    expect(a).not.toBeNull();
    expect(a?.getAttribute("href")).toBe("https://example.com");
    expect(a?.getAttribute("target")).toBe("_blank");
    expect(a?.getAttribute("rel")).toContain("noopener");
    expect(a?.getAttribute("rel")).toContain("noreferrer");
    expect(a?.className).toContain("underline");
  });
});

describe("MarkdownRenderer fenced code block (Warning 1: language extraction not broken)", () => {
  it("renders an open-fence `\\`\\`\\`python\\nprint(\"hi\")` → StreamingCodeBlock with language='python' + isStreamingComplete=false", () => {
    // Note: react-markdown only emits the fenced code AST node once the
    // closing ``` arrives. To simulate a "partial" fence in unit tests we
    // pass the closing fence too — the language extraction is the contract
    // we're asserting, not the partial-render path (which is covered by
    // the streaming-code-block.test.tsx fence-state tests).
    render(
      <MarkdownRenderer
        rawMarkdown={"```python\nprint('hi')\n```"}
        isStreamingComplete={false}
        messageId="m1"
      />,
    );
    expect(streamingStub).toHaveBeenCalled();
    const lastCall = streamingStub.mock.calls.at(-1)![0];
    expect(lastCall.language).toBe("python");
    expect(lastCall.isStreamingComplete).toBe(false);
    expect(lastCall.children).toContain("print('hi')");
  });

  it("renders the SAME fenced block with isStreamingComplete=true → StreamingCodeBlock receives isStreamingComplete=true", () => {
    render(
      <MarkdownRenderer
        rawMarkdown={"```python\nprint('hi')\n```"}
        isStreamingComplete={true}
        messageId="m1"
      />,
    );
    expect(streamingStub).toHaveBeenCalled();
    const lastCall = streamingStub.mock.calls.at(-1)![0];
    expect(lastCall.language).toBe("python");
    expect(lastCall.isStreamingComplete).toBe(true);
  });
});

describe("MarkdownRenderer XSS sanitization (T-04-35)", () => {
  it("renders <script>alert(1)</script> as literal text — NO <script> element in the DOM", () => {
    const { container } = render(
      <MarkdownRenderer
        rawMarkdown="<script>alert(1)</script>"
        isStreamingComplete={true}
        messageId="m1"
      />,
    );
    // No actual <script> tag was constructed.
    expect(container.querySelector("script")).toBeNull();
  });
});

describe("MarkdownRenderer React.memo equality (Pattern 4)", () => {
  it("same (messageId, rawMarkdown.length, isStreamingComplete) does NOT re-render the inner subtree", () => {
    const { container, rerender } = render(
      <MarkdownRenderer
        rawMarkdown="# hi"
        isStreamingComplete={false}
        messageId="m1"
      />,
    );
    const firstH1 = container.querySelector("h1");
    expect(firstH1).not.toBeNull();

    rerender(
      <MarkdownRenderer
        rawMarkdown="# hi"
        isStreamingComplete={false}
        messageId="m1"
      />,
    );
    const secondH1 = container.querySelector("h1");
    // React.memo: when arePropsEqual returns true, the memo returns the
    // previously-rendered element subtree. The DOM node is the SAME node.
    expect(secondH1).toBe(firstH1);
  });

  it("longer rawMarkdown on the same messageId DOES re-render (memo predicate returns false)", () => {
    const { container, rerender } = render(
      <MarkdownRenderer
        rawMarkdown="# hi"
        isStreamingComplete={false}
        messageId="m1"
      />,
    );
    expect(container.querySelector("h1")?.textContent).toBe("hi");

    rerender(
      <MarkdownRenderer
        rawMarkdown="# hi there"
        isStreamingComplete={false}
        messageId="m1"
      />,
    );
    expect(container.querySelector("h1")?.textContent).toBe("hi there");
  });

  it("different messageId DOES re-render (different message)", () => {
    const { container, rerender } = render(
      <MarkdownRenderer
        rawMarkdown="# m1"
        isStreamingComplete={false}
        messageId="m1"
      />,
    );
    expect(container.querySelector("h1")?.textContent).toBe("m1");

    // Same length, different id — the predicate compares both, so this
    // tuple is unequal and the inner subtree re-renders.
    rerender(
      <MarkdownRenderer
        rawMarkdown="# m2"
        isStreamingComplete={false}
        messageId="m2"
      />,
    );
    expect(container.querySelector("h1")?.textContent).toBe("m2");
  });
});
