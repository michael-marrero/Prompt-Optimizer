---
phase: 04-minimal-chat-ui-openrouter-backend
plan: 04
subsystem: backend
tags: [fastapi, sse, sse-starlette, routing, phase3-amendment, d-15, tdd]

requires:
  - phase: 04-minimal-chat-ui-openrouter-backend
    plan: 01
    provides: "apps/web/ workspace scaffold + Wave-0 spike (no app-code dependency for this plan)"
provides:
  - "apps/api/routes/turn.py event_stream() now yields a `routing_decision` named SSE event as its FIRST yield (line 482-485), with a STRUCTURED 5-key payload `{backend, model_or_agent, rationale, confidence, signals}` sourced directly from the in-scope RoutingDecision local — payload['signals'] equals Done.routing_signals byte-for-byte"
  - "apps/api/tests/test_turn_streaming.py test_routing_decision_event_arrives_first_and_matches_done — contract test with 4 independent assertions (ordering, ASGITransport latency bound, 5-key structured shape, signals sub-field byte-equality)"
affects: [04-05-PLAN]

tech-stack:
  added: []
  patterns:
    - "PATTERNS turn.py MODIFY — D-15 inject `routing_decision` event as event_stream()'s first yield"
    - "PATTERNS test_turn_streaming.py MODIFY — mirror the test_streams_chatchunks shape with (event, data) tuple collection + finite-consume on event:done (Pitfall 4)"
    - "TDD RED→GREEN — failing test committed first (407d24a), implementation makes it pass (2e0770b)"
    - "Yield before try/except CancelledError so cancellation between adapter creation and adapter.stream() still ships the chip data (T-04-24 mitigation)"

key-files:
  created: []
  modified:
    - "apps/api/routes/turn.py (import json added at line 135; routing_decision yield + 8-line attribution comment added at lines 465-485, INSIDE event_stream(), BEFORE buffer init and BEFORE the try/except CancelledError block)"
    - "apps/api/tests/test_turn_streaming.py (new test test_routing_decision_event_arrives_first_and_matches_done appended after test_unknown_thread_returns_404; 189 insertions)"

key-decisions:
  - "Payload is the STRUCTURED 5-key record {backend, model_or_agent, rationale, confidence, signals} — NOT free-form `decision.signals` only. CONTEXT D-15 was reconciled during Plan 02 revision iteration 1: the chip in Plan 05 needs `backend` (for color), `model_or_agent` (for display_name lookup), `rationale` (for the chip body), `confidence` (for visual confidence indicator). The `signals` sub-field preserves D-15's persistence-source byte-equality requirement."
  - "Yield placed BEFORE the try/except CancelledError block (T-04-24 mitigation): even if cancellation lands between adapter creation and adapter.stream(), the chip data has already shipped. The try/except in event_stream() is only for adapter.stream() exceptions; the routing_decision yield is structurally outside that protection because it cannot fail (no I/O, no provider call — pure dataclass field reads + json.dumps)."
  - "ChatChunk Pydantic union (apps/api/backends/chunks.py) is byte-identical to its pre-amendment state — verified by `git diff apps/api/backends/chunks.py` returning empty. The routing_decision event is yielded as a ServerSentEvent alongside ChatChunks, not as a new chunk variant. Phase 2 contract preserved verbatim."
  - "Import order: `import json` placed alphabetically between `import asyncio` and `import logging` (line 135). Matches the existing PEP 8 import order in the file."
  - "Test uses the realistic 5-key signals shape `{task_type, task_type_confidence, agentic_intent, agentic_intent_confidence, rule_fired}` so the byte-equality test catches any signals truncation in either direction — wire emission or Done.routing_signals persistence."

duration: ~8 min
completed: 2026-05-19
---

# Phase 04 Plan 04: Wave 3 — D-15 routing_decision SSE Event Summary

**Wave 3 lands the cross-phase Phase 3 wire-format amendment that Phase 4's chip render contract requires. `apps/api/routes/turn.py` now emits a `routing_decision` named SSE event as event_stream()'s FIRST yield — BEFORE the adapter.stream() async-for loop and BEFORE the try/except CancelledError block. The payload is the structured 5-key record `{backend, model_or_agent, rationale, confidence, signals}` sourced directly from the in-scope `decision: RoutingDecision`, where `payload['signals']` equals `Done.routing_signals` byte-for-byte (preserving D-15's canonical-persistence equality requirement). The contract test in `apps/api/tests/test_turn_streaming.py` ships RED-then-GREEN with 4 independent assertions covering ordering, latency, 5-key shape, and signals sub-field byte-equality. Whole-repo pytest (apps/api + src) is 302 passed, 5 skipped — zero Phase 1/2/3 regression. ChatChunk Pydantic union is byte-identical to its pre-amendment state.**

## Performance

- **Duration:** ~8 min (on-CPU)
- **Started:** 2026-05-19T15:57:21Z
- **Completed:** 2026-05-19T16:05:00Z
- **Tasks:** 2 (Task 1 RED test, Task 2 GREEN amendment)
- **Files modified:** 2
- **Files created:** 0

## Exact Line Numbers in turn.py Post-Amendment

| Item | Line | Content |
|------|------|---------|
| `import json` | 135 | Alphabetically inserted between `import asyncio` and `import logging` |
| D-15 attribution comment block | 465-473 | 8-line comment explaining payload shape + cancellation safety |
| `payload = {...}` dict literal | 474-480 | 5 keys sourced from `decision.<field>` |
| `yield ServerSentEvent(event="routing_decision", ...)` | 481-484 | The new SSE event yield |
| Original `buffer: list[ChatChunk] = []` | 487 | UNCHANGED, now follows the new yield |
| Original `try:` for CancelledError wrap | 489 | UNCHANGED |
| Original `async for chunk in adapter.stream(...)` | 490-492 | UNCHANGED |

The yield is the FIRST executable statement inside `event_stream()` (the docstring spans lines 453-463). No other behavior in `event_stream()` was modified.

## Test Assertions (4 Independent)

`test_routing_decision_event_arrives_first_and_matches_done` in `apps/api/tests/test_turn_streaming.py`:

| # | Assertion | Catches |
|---|-----------|---------|
| (a) | `events[0][0] == "routing_decision"` | Future plan re-orders event_stream to emit text_delta first |
| (b) | `(first_event_t - t0) < 0.5` | Latency regression (ASGITransport bound; real-network target is 100ms) |
| (c) | `set(routing_payload.keys()) == {"backend", "model_or_agent", "rationale", "confidence", "signals"}` + value equality on the four top-level scalars | Future plan changes payload to anything other than the 5-key record |
| (d) | `routing_payload["signals"] == done_payload["routing_signals"]` | Future plan stops mirroring decision.signals at payload['signals'] — preserves D-15 canonical-persistence-source invariant |

## RED → GREEN Transition

| Commit | Phase | Description |
|--------|-------|-------------|
| `407d24a` | RED | `test(04-04): add D-15 routing_decision contract (RED)` — new test, exits 1 on assertion (a) because un-amended turn.py emits text_delta first |
| `2e0770b` | GREEN | `feat(04-04): emit routing_decision SSE event with structured payload before adapter dispatch (D-15)` — turn.py amendment makes the test pass; whole-repo pytest exits 0 |

**RED gate verification:** the Task 1 verify command piped pytest output through `tee /tmp/04-04-red.log && grep -qE 'FAILED|AssertionError'` to catch the case where the test unexpectedly passes (e.g., Task 2 executed prematurely). The grep matched `AssertionError` and the exit-1 fallback never fired — RED gate honored.

## ChatChunk Pydantic Union Preserved

```
$ git diff apps/api/backends/chunks.py
(empty output — chunks.py is byte-identical to its pre-amendment state)
```

The routing_decision event is yielded as a ServerSentEvent alongside ChatChunks, not as a new chunk variant. The Phase 2 D-01 / D-02 closed-vocabulary union remains the canonical adapter return type. Phase 5 forward-compatibility: when CodeBubble + ComputerUseBubble land, the same data-routing wire part flows through with `backend="claude_code"` or `backend="computer_use"` — no further wire amendment needed.

## Whole-Repo Pytest Results

```
$ .venv/bin/pytest apps/api/ src/
...
302 passed, 5 skipped in 79.81s
```

| Suite | Tests | Status |
|-------|-------|--------|
| apps/api (Phase 2 + Phase 3 + new Plan 04-04 test) | 254 | passed |
| src (Phase 1 routing brain) | 48 + 5 skipped | passed |
| **Total** | **302 passed, 5 skipped** | **0 failures** |

The 5 skipped tests are pre-existing (slow / env-gated) — not introduced by this plan. Skip list unchanged from the pre-amendment baseline.

## Deviations from Plan

**None — plan executed exactly as written.**

The two-task RED-then-GREEN flow landed verbatim:
- Task 1's verify command (RED gate with `tee` + `grep -qE 'FAILED|AssertionError'`) confirmed the test failed BEFORE Task 2 ran, with the precise AssertionError message expected.
- Task 2's verify command (eight grep checks + GREEN pytest + whole-repo pytest) all passed on the first run.

No auto-fixes (Rules 1-3) needed.
No checkpoints encountered (autonomous plan).
No authentication gates.
No CLAUDE.md adjustments needed (Python conventions: snake_case modules, 4-space indent, sklearn-conventional X/y not applicable here — preserved).

## Notes for Downstream Plans

**Plan 04-05 (Wave 4 — chat surface + chip):** the Plan 02 SSE translator already maps `event: routing_decision` to the AI SDK v6 `data-routing` part. Plan 05's chip subscribes via `useThreadMessage.parts.find(p => p.type === "data-routing")` and reads `part.data.backend`, `part.data.model_or_agent`, `part.data.rationale`, `part.data.confidence` directly — no defensive optional-chaining required (the Zod schema in Plan 02's chunk-schemas.ts and the new wire emission both enforce the 5-key structure).

**Phase 5 forward-compat:** when CodeBubble (UI-09) and ComputerUseBubble (UI-10) ship in Phase 5, the same `data-routing` part flows through with `backend="claude_code"` or `backend="computer_use"`. The chip's color-coding switch in Plan 05 (slate / green / amber per CONTEXT D-12) handles the new backends without any wire-format change.

**For the orchestrator:** D-15 wording in `04-CONTEXT.md` was already reconciled in commit `91f5579` (`docs(04): UI-SPEC approved (rev 2; 6/6 dimensions PASS)`) — the CONTEXT now describes the structured 5-key payload shape correctly, with the byte-equality moved to the `signals` sub-field. No further docs-only commit needed; the planner's revision-iteration-1 notes flagged this as a possible follow-up, but the reconciliation has landed.

**ROADMAP SC #3 reconciliation (RESEARCH Critical Finding #2):** the stop-status assertion broadens to `status IN ('cancelled', 'complete', 'error')` per Phase 3's existing terminology — see `apps/api/routes/turn.py` lines 533-540 where the `status` derivation already uses `cancelled` / `complete` / `error`. No code change needed in this plan; the wording reconciliation is a docs-only follow-up for the orchestrator if the ROADMAP says otherwise.

## VALIDATION.md Row Flip

- `D-15 contract` → **PASS** (was pending Plan 04-04 wave delivery)

The byte-for-byte equality between the mid-stream chip data signals sub-field and final Done.routing_signals is provably preserved by assertion (d) of the contract test.

## Self-Check: PASSED

Created files verified to exist:

- apps/api/routes/turn.py — FOUND (modified; `import json` at line 135; routing_decision yield at lines 465-485)
- apps/api/tests/test_turn_streaming.py — FOUND (modified; new test appended; 189 insertions)

Commits verified to exist:

```
$ git log --oneline -2
2e0770b feat(04-04): emit routing_decision SSE event with structured payload before adapter dispatch (D-15)
407d24a test(04-04): add D-15 routing_decision contract (RED)
```

- `407d24a` — FOUND (Task 1 — RED test)
- `2e0770b` — FOUND (Task 2 — GREEN amendment)

Verification commands re-run after final commit:

- `.venv/bin/pytest apps/api/tests/test_turn_streaming.py::test_routing_decision_event_arrives_first_and_matches_done -x` → 1 passed (exit 0)
- `.venv/bin/pytest apps/api/ src/` → 302 passed, 5 skipped (exit 0)
- `git diff apps/api/backends/chunks.py` → empty (unchanged)
- 8 verify-greps from Task 2 plan → all matched (import json + 5 payload keys + json.dumps(payload) + event="routing_decision")
- 4 verify-greps from Task 1 plan → all matched (test name + ordering assertion + 5-key shape + signals byte-equality)

---
*Phase: 04-minimal-chat-ui-openrouter-backend*
*Completed: 2026-05-19*
