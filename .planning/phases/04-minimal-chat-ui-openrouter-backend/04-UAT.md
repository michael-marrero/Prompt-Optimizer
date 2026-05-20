---
status: complete
phase: 04-minimal-chat-ui-openrouter-backend
source:
  - 04-01-SUMMARY.md
  - 04-02-SUMMARY.md
  - 04-03-SUMMARY.md
  - 04-04-SUMMARY.md
  - 04-05-SUMMARY.md
  - 04-06-SUMMARY.md
  - 04-07-SUMMARY.md
started: 2026-05-19T18:50:00Z
updated: 2026-05-20T00:20:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start — first-run modal appears
expected: With no .env file at the repo root, two terminals run `uvicorn apps.api.main:app --reload` and `pnpm --dir apps/web dev`. Browser opens to http://localhost:3000. A modal appears with "OpenRouter key required" copy + a key input field. The chat composer below is disabled.
result: pass

### 2. Modal Unlock — key entry without restart
expected: Paste an OpenRouter key (sk-or-v1-…) into the modal field. Click "Save & continue". Modal closes. Composer becomes enabled. Neither uvicorn nor pnpm dev needed to be restarted — same processes, same terminals, just a state flip.
result: pass

### 3. Streaming + Routing Chip
expected: Type "What is the capital of France?" and press Enter. A "Routed to <model-name> · <one-line-rationale>" chip appears above the assistant message within ~100ms — BEFORE any text streams. Then the response streams in token-by-token (you can see partial words/sentences forming). After the stream finishes, a metrics footer appears below the message with cost USD, latency in ms, and token count.
result: pass
observed: |
  Chip: "Routed to openrouter/auto · task=knowledge | agentic=conversational | model_router=internlm3-8b-instruct | …"
  Footer: "$0.0007 · 6.8s · 15↑/88↓"
  Streamed prose response renders, all 3 visual elements present (chip on top, body in middle, footer below).

### 4. No-Flicker Code Block
expected: Type "Explain the difference between let and const in JavaScript with a brief example" and press Enter. The response is mostly prose but includes one or two fenced code blocks. Watch each code block as the fence streams in: while the closing ``` has NOT yet arrived, the code renders as plain monospace text (no syntax colors). The moment the closing ``` arrives, syntax highlighting applies ONCE to the whole block — no visible flash, no second highlight pass, no flicker. The eye sees one clean transition.
result: pass
observed: |
  Full markdown body streamed (headers, bullets, prose), one JavaScript fenced code block rendered with syntax highlighting after the closing fence. User confirmed the highlight transition was clean — no flash, no re-paint, no perceptible flicker.
prior_attempt:
  prompt: "Write a short Python class named Greeter that prints hello, with a docstring"
  reported: "response never populated — empty bubble + perpetual streaming● indicator; no routing chip ever appeared"
  observed: |
    Empty assistant bubble + perpetual streaming● + no routing chip.
    Server logs show Phase 1 router picked claude_code backend; ClaudeCodeAdapter raised RuntimeError (ANTHROPIC_API_KEY not set); turn.py escaped as a 500.
  gap_logged: "see Gaps section — Phase 4 pre-stream error handling gap"
  resolution: "retry with a knowledge prompt that should route to openrouter"

### 5. Stop Preserves Partial
expected: Type a long prompt like "Write a 10-paragraph essay about the history of the printing press" and press Enter. As soon as the first sentence streams in, click the Stop button (which replaced Send while streaming). Within 2 seconds, streaming halts. The partial text remains visible on screen (not blanked, not error-replaced). The metrics footer shows the partial state (cost/latency/tokens for what was generated).
result: pass
observed: |
  Retry with "Describe Paris in detail — architecture, history, culture, landmarks, food, and famous neighborhoods. Use bullet points." routed to openrouter and produced streaming output. Stop click halted streaming within 2s; partial bullets preserved on screen; metrics footer reflected the partial / cancelled state. User confirmed pass.
retry_blocked_by: prior-phase
reason: |
  Router picked claude_code backend for the "10-paragraph essay" prompt; same crash path as Test 4's first attempt (logged in Gaps): turn.py 500 from RuntimeError(ANTHROPIC_API_KEY not set) → empty bubble + perpetual streaming●. Stop button cannot be tested without a streaming turn that completes initial deltas.
prior_attempt:
  prompt: "Write a 10-paragraph essay about the history of the printing press"
  reported: "it stalled / no response"
  observed: "POST /api/chat 500 in 22ms; FastAPI traceback shows _get_or_create_adapter → ClaudeCodeAdapter → _missing_api_key_error() — identical to Test 4 first-attempt path"
  gap: "same as logged Gap #1 — Phase 4 pre-stream error handling"

### 6. DevTools Network — browser never connects to FastAPI directly
expected: Open Chrome DevTools → Network tab. Submit any prompt. Observe every request that fires during the turn. EVERY request's URL has host `localhost:3000` (the Next.js origin) — typically `/api/chat`, `/api/threads/...`, `/api/health`, `/api/settings`. ZERO requests show host `localhost:8000` (FastAPI) or any other host. The browser only ever talks to Next.
result: pass

### 7. DevTools Storage — no key residue
expected: Open Chrome DevTools → Application tab → Storage. After entering a key via the modal and submitting at least one turn, inspect localStorage, sessionStorage, and Cookies for `localhost:3000`. Search each storage area for "sk-or-" or any substring of your actual key. ZERO matches. The key lives only in FastAPI's KeyStore — never reaches the browser.
result: pass

## Summary

total: 7
passed: 7
issues: 0
pending: 0
skipped: 0
blocked: 0
gaps_logged: 2

## Gaps

- truth: "Submitting any prompt produces a streamed response or a user-visible error — never an empty bubble with a perpetual streaming indicator"
  status: failed
  reason: "User reported: response never populated — empty bubble + perpetual streaming● indicator; no routing chip ever appeared"
  severity: blocker
  test: 4
  root_cause: |
    apps/api/routes/turn.py:_get_or_create_adapter (lines 283-307) only catches ImportError, not RuntimeError. The trained router (Phase 1) routes code-style prompts to the claude_code backend; ClaudeCodeAdapter.__init__ raises RuntimeError when ANTHROPIC_API_KEY is missing (apps/api/backends/claude_code/adapter.py:260). The RuntimeError propagates as an uncaught FastAPI 500, before the SSE stream opens. assistant-ui's optimistic assistant-message slot stays empty; the MetricsFooter streaming● state never advances to Done; the StreamErrorBanner never renders because the SSE stream itself was never opened (StreamErrorBanner only handles in-stream stream_error events).
  artifacts:
    - path: "apps/api/routes/turn.py"
      line_range: "283-307"
      issue: "try/except only catches ImportError; RuntimeError from adapter __init__ (missing API key) escapes as a 500"
    - path: "apps/web/hooks/useFirstRunGate.ts"
      issue: "Only reads adapters.openrouter.status; does not enforce that other backends the router might pick have keys before allowing composer submit"
  missing:
    - "In apps/api/routes/turn.py:_get_or_create_adapter — extend the except clause to also catch RuntimeError and convert to HTTPException(400, detail=\"<backend> backend requires <KEY_NAME>\") so pre-stream key-missing failures match the documented D-08 HTTPException pattern (already used for 400 computer-use opt-out)."
    - "OR: in post_turn — wrap the _get_or_create_adapter call so the missing-key error opens the SSE stream and emits StreamError(code=\"auth_failed\") + Done; the existing StreamErrorBanner catalog already handles this code."
    - "In apps/web/hooks/useFirstRunGate.ts — check all three adapters.{openrouter,claude_code,computer_use}.status (or at least consult the routing decision the router would make for a given prompt class)."
  debug_session: ""
  scope: "Phase 4 implementation gap — pre-stream error handling in the FastAPI route + first-run gate enforcement on the Next side. Phase 1 router decision is correct as designed; the gap is downstream error handling, not the routing pick."

- truth: "Navigating to /settings and back to / preserves the current conversation"
  status: failed
  reason: "User observed during Test 6 setup: 'going to settings and back the conversation history disappears'"
  severity: minor
  test: 6 (side observation)
  root_cause: |
    Phase 4 useChatThread mounts the assistant-ui runtime in-memory only. The threadId from localStorage (apps/web/lib/thread-id.ts) is reused across mounts, but the assistant-ui runtime does NOT load prior messages from the server on mount — that capability belongs to Phase 5 ('thread sidebar lists every persisted thread and supports create / select / rename / delete; selecting a thread loads its full history').
    Server-side persistence is correct: Phase 3's STORE-02 writes the thread + messages to SQLite on each Done chunk. Restore-on-mount is the missing piece.
  artifacts:
    - path: "apps/web/hooks/useChatThread.ts"
      issue: "No initialMessages or onMount fetch from /api/threads/{id}/messages — runtime starts empty on every page mount"
    - path: "apps/web/app/page.tsx"
      issue: "Page mount does not call /api/threads/{threadId} to seed the runtime with prior messages"
  missing:
    - "Phase 5: implement thread restore on mount — fetch /api/threads/{threadId} (or its messages sub-resource), seed assistant-ui runtime with initialMessages, restore routing chip + metrics parts where possible"
  debug_session: ""
  scope: "Phase 5 — multi-thread sidebar + history restore. Phase 4 is single-thread MVP per ROADMAP; restore-on-mount is documented as Phase 5 SC #1: 'selecting a thread loads its full history; threads survive a full browser-close + reopen because they live in SQLite'."
