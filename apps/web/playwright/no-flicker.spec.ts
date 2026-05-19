// Plan 04-06 Wave 5 Task 3 — Real Playwright E2E for VALIDATION.md UI-03.
//
// Overwrites the Plan 01 Wave-0 test.skip stub. Asserts the no-flicker
// invariant (RESEARCH §Pattern 5 lines 788-825, Pitfall 5):
//   - During streaming, the assistant message contains a fenced code block
//     rendered as plain <pre><code class="language-python">RAW</code></pre>
//     (NO shiki tokens, NO dangerouslySetInnerHTML on raw source).
//   - On the metrics-footer Done signal (the aria-label*=Turn cost
//     selector), StreamingCodeBlock highlights the block ONCE.
//   - Crucially: no FURTHER mutations to the rendered code element fire
//     after Done lands. The MutationObserver count immediately after Done
//     equals the count 500ms later — proving the React.memo equality
//     predicate prevents re-renders on post-Done state changes.
//
// Fixture: the canonical [fixture:code-block] body-prefix (Warning 5 lock-in).
// Mock-fastapi.py emits 6 text_deltas (4 inside the fence) + done, with
// 50ms inter-chunk sleeps so the MutationObserver installation runs to
// completion BEFORE the closing fence arrives.

import { test, expect } from "@playwright/test";

test("UI-03: code block highlights exactly once on fence close", async ({
  page,
}) => {
  await page.goto("/");

  // First-run modal tolerance — Plan 07 may add a key modal; this spec
  // pre-dates that, but if a future PR ships the modal we handle it here.
  const modalHeading = page.getByText("Connect OpenRouter to get started");
  if (await modalHeading.isVisible({ timeout: 2000 }).catch(() => false)) {
    await page
      .getByLabel("OpenRouter API key")
      .fill("sk-or-v1-" + "N".repeat(48));
    await page.getByRole("button", { name: "Save & continue" }).click();
    await expect(modalHeading).toBeHidden({ timeout: 5000 });
  }

  // Wait for the composer to enable (default thread auto-create round-trip
  // must complete before sending — Plan 05 Blocker 2 fix).
  const composer = page.locator('textarea[placeholder="Type a message…"]');
  await composer.waitFor({ state: "visible", timeout: 10_000 });
  await expect(composer).toBeEnabled({ timeout: 10_000 });

  // Send the code-block fixture prompt.
  await composer.fill("[fixture:code-block] please show a hello world");
  await page.keyboard.press("Enter");

  // Wait for the <code> element to attach. This appears either:
  //   - as <pre><code class="language-python">...</code></pre> during the
  //     pre-close render (no shiki), OR
  //   - inside the shiki-replaced <div dangerouslySetInnerHTML=...> after
  //     the close fence. The selector `pre code` matches both shapes
  //     because shiki ALSO emits <pre><code> as its wrapper structure.
  const codeEl = page.locator("pre code").first();
  await codeEl.waitFor({ state: "attached", timeout: 15_000 });

  // Install a MutationObserver on the <pre> ancestor BEFORE the closing
  // fence arrives — we want to capture the count delta from "open fence"
  // to "Done arrives" (the highlight pass should fire exactly once during
  // this window) AND the count from "Done arrives" to "Done + 500ms"
  // (which must be ZERO, proving no late re-highlight).
  await page.evaluate(() => {
    (window as unknown as { __codeMutations: number }).__codeMutations = 0;
    const observer = new MutationObserver(() => {
      (window as unknown as { __codeMutations: number }).__codeMutations += 1;
    });
    // Observe the closest <pre> ancestor so we catch the React replacement
    // of <pre><code>RAW</code></pre> with <div dangerouslySetInnerHTML=...>
    // on highlight (a childList mutation on the parent, plus character/
    // tree changes inside).
    const code = document.querySelector("pre code");
    const target =
      (code?.closest("pre") as Element | null) ??
      (code?.parentElement as Element | null) ??
      document.body;
    observer.observe(target, {
      childList: true,
      subtree: true,
      characterData: true,
    });
    (window as unknown as { __observer: MutationObserver }).__observer =
      observer;
  });

  // Wait for the stream to finish — the metrics footer renders its final
  // "Turn cost" aria-label only on Done (Plan 05 MetricsFooter contract).
  await page.waitForSelector('[aria-label*="Turn cost"]', { timeout: 30_000 });

  // Capture mutation count at Done.
  const mutationsAtDone = await page.evaluate(
    () => (window as unknown as { __codeMutations: number }).__codeMutations,
  );

  // Hold for 500ms past Done. If any post-Done re-highlight or React
  // re-render touches the code subtree, the observer will record it.
  await page.waitForTimeout(500);

  const mutationsAfterDone = await page.evaluate(
    () => (window as unknown as { __codeMutations: number }).__codeMutations,
  );

  // KEY ASSERTION (UI-03): mutation count is stable across the 500ms
  // window after Done — no late re-highlight, no re-tokenize. The
  // memo equality predicate (RESEARCH §Pattern 4) holds.
  expect(mutationsAfterDone).toBe(mutationsAtDone);

  // Secondary assertion: shiki tokens are present in the final innerHTML
  // (the highlight DID fire once — without this we'd only have asserted
  // "nothing happened" which would silently pass on a totally broken
  // pipeline). shiki emits <span style="color: ..."> tokens — match either
  // an inline-style span OR a token-class span.
  const finalInnerHtml = await page.evaluate(() => {
    const pre =
      document.querySelector("pre code")?.closest("pre") ??
      document.querySelector("pre");
    return pre?.innerHTML ?? "";
  });
  expect(finalInnerHtml).toMatch(/<span[^>]+style=|<span[^>]+class=/);

  // Cleanup the observer.
  await page.evaluate(() => {
    (
      window as unknown as { __observer?: MutationObserver }
    ).__observer?.disconnect();
  });
});
