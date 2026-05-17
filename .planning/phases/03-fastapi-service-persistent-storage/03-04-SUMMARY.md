---
gsd_summary_version: 1.0
phase: "03"
plan: "04"
plan_id: "03-04-sse-turn-handler"
subsystem: "api/routes"
tags: [phase-03, wave-4, sse, streaming, turn-handler, fastapi, persistence]
requires:
  - 03-00-SUMMARY.md   # Wave 0 — fake_adapter + test scaffolding
  - 03-01-SUMMARY.md   # Wave 1 — DB schema + persist_turn
  - 03-02-SUMMARY.md   # Wave 2 — lifespan + healthz
  - 03-03-SUMMARY.md   # Wave 3 — thread CRUD + settings
provides:
  - "POST /api/v1/threads/{thread_id}/turn — SSE stream + per-turn persistence"
  - "apps.api.routes.turn:router (FastAPI APIRouter mounted in main)"
  - "apps.api.routes.turn:TurnRequest (Pydantic v2 body shape)"
  - "apps.api.routes.turn:_synthesize_override_decision (Pattern 11)"
  - "apps.api.routes.turn:_get_or_create_adapter (D-15 lazy cache + D-12 gate)"
  - "apps.api.jsonl_log:append_routing_decisions_jsonl (STORE-06 writer)"
affects:
  - apps/api/main.py  # +include_router(turn.router)
tech_stack:
  added:
    - "(none — sse-starlette / FastAPI / Pydantic / aiosqlite already pinned in Wave 0)"
  patterns:
    - "SSE generator + buffer + persist_turn (RESEARCH Pattern 2)"
    - "Override-backend synthesis (Pattern 11)"
    - "Lazy adapter cache + D-12 STRICT AND gate (Pattern 13)"
    - "Named SSE events keyed by chunk.type (D-07)"
    - "asyncio.to_thread(decide, ...) — never synchronous (D-16)"
    - "task.cancel() cancellation under ASGITransport (Pitfall 6)"
    - "Finite consume break-on-event:done in tests (Pitfall 4)"
    - "Heartbeat ping override via subclass-or-monkeypatch (Pattern 7)"
key_files:
  created:
    - "apps/api/routes/turn.py — SSE turn handler (582 LOC)"
    - "apps/api/jsonl_log.py — routing_decisions.jsonl writer (141 LOC)"
    - "apps/api/tests/test_turn_streaming.py — 9 async tests (844 LOC)"
  modified:
    - "apps/api/main.py — include_router(turn.router) (+1 line)"
decisions:
  - "Rule 1 (FastAPI response_model): the SSE endpoint is decorated with response_model=None — without it FastAPI tries to generate a Pydantic response model from the EventSourceResponse return-type annotation and aborts at app construction time. response_model=None is the documented escape valve for non-Pydantic responses."
  - "Rule 1 (sys.modules class-identity): the _fresh_app test helper purges sse_starlette from sys.modules before reloading apps.api.routes.turn. The Phase 1 D-18 smoke test deletes 'starlette' / 'fastapi' / 'pydantic' / 'httpx' from sys.modules; without the sse_starlette purge, the route's cached EventSourceResponse class inherits from a STALE starlette.responses.Response while the freshly-reimported FastAPI compares against the NEW class — isinstance() fails and FastAPI falls through to jsonable_encoder. The purge is a test-only Rule 1 fix; it does not change production behavior."
  - "Rule 1 (test 3 class-identity): test_heartbeat_emits re-imports EventSourceResponse from the route module AFTER _fresh_app so the FastPingResponse subclass inherits from the post-purge class hierarchy. Same root cause as the sys.modules fix above; local workaround for the heartbeat test."
  - "Heartbeat strategy: sse_starlette 3.4.4 does NOT export DEFAULT_PING_INTERVAL as a module-level attribute (it lives as a CLASS attribute on EventSourceResponse). Tests use a FastPingResponse subclass that overrides DEFAULT_PING_INTERVAL=0.3 AND forces ping=0.3 in __init__ — both override paths are needed because the production code passes ping=15 explicitly, which wins over the class default when non-None."
  - "Cancellation budget assertion uses time.monotonic() wall-clock measurement (elapsed < 2.0) per CONTEXT critical context; @pytest.mark.timeout(5) is belt-and-suspenders headroom only."
  - "Override-backend default models: openrouter='openrouter/auto' / claude_code='claude-agent-sdk' / computer_use='computer-use-2025-11-24' — mirrors Phase 1 fallback choices + Phase 2 adapter sentinels."
  - "All three D-19 INFO logs (turn_start / routing_decision / turn_done) bound their content: user_msg_len is a length scalar; rationale is the Phase 1 generated string never user content; cost/tokens/latency are scalars. Defense in depth via the RedactionFilter installed at apps.api.__init__ import."
  - "request.is_disconnected() poll runs per chunk as defense-in-depth proactive cancellation. Under ASGITransport it is a no-op (RESEARCH Pitfall 6); production cancellation works because real-network close DOES inject http.disconnect."
metrics:
  duration: "102m 51s"
  completed: "2026-05-17T17:50:00Z"
---

# Phase 3 Plan 04: SSE Turn Handler — HEART of Phase 3 Summary

POST /api/v1/threads/{thread_id}/turn streams ChatChunks as named SSE events (D-07), wraps decide() in asyncio.to_thread (D-16 / API-07), buffers chunks to ONE BEGIN/COMMIT persist on terminal Done (D-04 / STORE-05), appends a routing-decisions JSONL line BEFORE adapter dispatch (D-05 / STORE-06), lazy-builds adapters with a D-12 STRICT AND gate for computer-use (D-15), and supports an override_backend body field that synthesises a RoutingDecision per Pattern 11.

## Task-by-task

### Task 1 — apps/api/jsonl_log.py (commit aa7ecad)

- `async def append_routing_decisions_jsonl(decision, thread_id, turn_id) -> None`
- Eight canonical fields per record: `turn_id`, `thread_id`, `timestamp`, `backend`, `model_or_agent`, `rationale`, `confidence`, `signals`.
- ISO 8601 UTC timestamp with `Z` suffix mirrors Phase 1 telemetry + schema_v0.sql convention.
- Plain blocking `open(path, "a")` per RESEARCH Open Question 4: POSIX append is atomic up to PIPE_BUF (~4 KB); routing-decision rows fit well within bound; single-user local server has near-zero concurrency on this file.
- Parent directory auto-created (`mkdir(parents=True, exist_ok=True)`); a fresh checkout does not need to seed `.planning/data/`.
- `ensure_ascii=False` preserves the U+2014 em-dash in fallback rationales (matches `RoutingDecision.to_json` from `src/routing/schema.py:64`).
- Duck-typed `decision` (getattr) so this module never imports from `src.routing.*` — preserves D-18 import-graph contract.
- Inline verify block executes round-trip write + JSON re-parse + key assertion; prints `OK jsonl`.

### Task 2 — apps/api/routes/turn.py + apps/api/main.py (commit 3c794f7)

`apps/api/routes/turn.py` (582 LOC) — the canonical SSE turn handler:

- `TurnRequest` Pydantic v2 body — `message: str`, `override_backend: Literal[...] | None`, `max_cost_usd: float | None`. The closed Literal mirrors the Phase 1 Backend type so wire-level typos return 422.
- `_synthesize_override_decision(backend)` — Pattern 11. Per-backend default model_or_agent map (`openrouter/auto` / `claude-agent-sdk` / `computer-use-2025-11-24`). Returns `RoutingDecision(rationale="user override", confidence=1.0, signals={"override": True})`.
- `_get_or_create_adapter(app, backend)` — Pattern 13 + D-15 lazy cache + D-12 STRICT AND gate.
  - Cached lookup first; second turn to same backend reuses instance.
  - For `computer_use`: `computer_use_enabled(settings)` check BEFORE construction. HTTPException(400) BEFORE the SSE response opens (D-08 pre-stream).
  - Lazy adapter class imports (B3 pattern) — ImportError surfaces as HTTPException(500); server boots even when an adapter package is broken.
- `@router.post("/threads/{thread_id}/turn", response_model=None)` — endpoint.
  - 404 when thread is unknown (pre-stream HTTPException).
  - `turn_id = secrets.token_urlsafe(12)`.
  - D-19 INFO log #1: `turn_start thread_id=... user_msg_len=... turn_id=...` — user_msg_len is a scalar, message body NEVER logged.
  - Routing decision: override path bypasses decide; else `await asyncio.to_thread(decide, prompt, history, artifacts, settings)`.
  - D-19 INFO log #2: `routing_decision backend=... model=... rationale='...' confidence=... turn_id=...`.
  - JSONL log: `await append_routing_decisions_jsonl(decision, thread_id, turn_id)` BEFORE adapter dispatch.
  - Adapter via `_get_or_create_adapter`.
  - AdapterOptions composed: `max_cost_usd` precedence is body > settings > DEFAULT_PER_TURN_COST_USD (50¢); `max_steps=None` so each adapter applies its own cap; `routing_signals=decision.signals`.
  - `event_stream()` async generator:
    - Buffers every ChatChunk in memory.
    - Yields `ServerSentEvent(event=chunk.type, data=chunk.model_dump_json())` — named events keyed by chunk.type per D-07 (NOT bare `data:` lines).
    - Breaks on `isinstance(chunk, Done)` (D-04 terminal Done invariant).
    - Polls `await request.is_disconnected()` per chunk (defense-in-depth; no-op under ASGITransport per Pitfall 6; tests use `task.cancel()`).
    - `except asyncio.CancelledError`: append StreamError(cancelled) + Done into buffer AND yield to wire, then re-raise so upstream adapter's CancelledError handler closes the provider connection within the 2-second budget (Pattern 7 + PEP 789).
    - `finally`: derive status from buffer's last StreamError (`complete` / `cancelled` / `error`); call `persist_turn(...)` wrapping user message + assistant message + routing_decisions row in ONE BEGIN/COMMIT. `try/except` around persist so a DB-lock failure logs but does not propagate.
    - D-19 INFO log #3: `turn_done thread_id=... backend=... cost_usd=... tokens_in=... tokens_out=... latency_ms=... status=... turn_id=...`. Latency falls back to wall-clock when Done doesn't carry it.
  - Returns `EventSourceResponse(event_stream(), ping=15)` — 15-second heartbeat satisfies API-05.

`apps/api/main.py` — single-line extension: `app.include_router(turn.router)` added after `settings.router`.

### Task 3 — apps/api/tests/test_turn_streaming.py (commit ab68659)

Nine async tests, all using `httpx.AsyncClient + ASGITransport` (NEVER TestClient):

| # | Test | What it verifies |
|---|------|------------------|
| 1 | `test_streams_chatchunks` | Content-Type: text/event-stream; ≥2 `event: text_delta` lines; last named event is `done`. |
| 2 | `test_decide_runs_in_thread` | `asyncio.to_thread` called exactly once (API-07 / D-16). |
| 3 | `test_heartbeat_emits` | FastPingResponse subclass with `ping=0.3` + sleep_per_chunk=1.0; ≥1 `:` comment-line heartbeat fires (API-05). |
| 4 | `test_cancellation_within_2s` | task.cancel() + `time.monotonic()` budget assertion `elapsed < 2.0` (API-06). |
| 5 | `test_one_transaction_per_turn` | After Done: 2 messages + 1 routing row in DB; assistant.text == "answer"; content_blocks JSON has ToolCall but NOT TextDelta (D-04 / STORE-05). |
| 6 | `test_jsonl_log_appended` | One JSONL line with the 8 canonical keys; `rationale == "test rationale"` (D-05 / STORE-06). |
| 7 | `test_override_backend` | decide() monkeypatched to raise; turn still succeeds; jsonl carries `rationale="user override"`, `confidence=1.0` (Pattern 11). |
| 8 | `test_computer_use_gated_when_opt_out` | env unset + `settings.computer_use_opt_in=False` + `override_backend="computer_use"` → 400 with `"computer-use is OFF"` in body (D-12 + D-08). |
| 9 | `test_unknown_thread_returns_404` | POST to non-existent thread → 404 `{"detail": "thread not found"}`. |

`_fresh_app` helper purges `sse_starlette` from `sys.modules` before reload to repair the class-identity break introduced by Phase 1's D-18 smoke test (see Deviations below).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] FastAPI response_model generation for SSE endpoint**

- **Found during:** Task 3 (running `pytest apps/api/tests/test_cors.py` after Task 2 commit).
- **Issue:** `apps/api/main.py:create_app()` aborted with `fastapi.exceptions.FastAPIError: Invalid args for response field! Hint: check that <class 'sse_starlette.sse.EventSourceResponse'> is a valid Pydantic field type.` FastAPI tries to generate a response model from the route's `-> EventSourceResponse` return-type annotation.
- **Fix:** Added `response_model=None` to the `@router.post("/threads/{thread_id}/turn")` decorator. This is FastAPI's documented escape valve for non-Pydantic responses like SSE.
- **Files modified:** `apps/api/routes/turn.py` (one decorator argument).
- **Commit:** `ab68659` (folded into the same commit as the test file since the bug was test-driven discovered).

**2. [Rule 1 — Bug] sys.modules class-identity break from Phase 1 D-18 smoke test**

- **Found during:** Task 3, running `pytest -m 'not live'` after Task 2 commit. The 276-test suite failed at `apps/api/tests/test_turn_streaming.py::test_streams_chatchunks` with `ValueError: [TypeError("'async_generator' object is not iterable"), ...]` ONLY when `src/routing/` tests ran before `apps/api/tests/`. The same test passed in isolation.
- **Issue:** `src/routing/tests/test_decide_smoke.py::test_no_forbidden_modules_imported_after_decide` deletes every module under `starlette`, `fastapi`, `pydantic`, etc. from `sys.modules` (D-18 enforcement). After this purge, `apps.api.routes.turn`'s cached `EventSourceResponse` class still inherits from a STALE `starlette.responses.Response` while the freshly-reimported FastAPI compares against the NEW `Response` class. FastAPI's `isinstance(result, Response)` check fails and falls through to `jsonable_encoder`, which tries to JSON-encode the async generator (the visible TypeError).
- **Fix:** `_fresh_app` test helper purges `sse_starlette` from `sys.modules` before reloading `apps.api.routes.turn`. The reload then picks up a fresh `EventSourceResponse` bound to the current `starlette.responses.Response` identity. `test_heartbeat_emits` additionally re-imports `EventSourceResponse` from the route module AFTER `_fresh_app` so its `FastPingResponse` subclass inherits from the post-purge hierarchy.
- **Files modified:** `apps/api/tests/test_turn_streaming.py` (`_fresh_app` purge block + `test_heartbeat_emits` re-import).
- **Commit:** `ab68659`. This is a TEST-ONLY workaround; production behavior is unchanged. The root cause is the D-18 smoke test's destructive purge; a future cleanup could refactor that test to use a child-process import isolation pattern instead of mutating shared `sys.modules` state. Filed implicitly as a deferred item.

**3. [Rule 1 — Bug] Acceptance criterion grep on `response.aclose` matched docstrings**

- **Found during:** Task 3 final acceptance-criteria verification.
- **Issue:** The plan's `\! grep -q "response.aclose"` negative-grep matched documentation strings inside docstrings/comments that EXPLAIN why we don't use `response.aclose()` for cancellation.
- **Fix:** Rewrote the explanatory text to use `` ``aclose`` `` (backtick code-quote) and "response close" (separate words) so the literal substring `response.aclose` no longer appears anywhere in the test file. Semantics unchanged; CI grep guard satisfied.
- **Files modified:** `apps/api/tests/test_turn_streaming.py` (three docstring/comment sites).
- **Commit:** `ab68659`.

## Acceptance criteria — Wave 4 truths (all 13 verified)

| # | Truth | Verified by |
|---|-------|-------------|
| 1 | Phase 3 files use `pathlib.Path(__file__).resolve().parents[N]`; no `sys.path.append`. | `grep "sys.path.append" apps/api/jsonl_log.py apps/api/routes/turn.py` returns nothing. |
| 2 | All modules trigger `dotenv.load_dotenv()` + `install_redaction_filter()` via `apps.api.__init__` import. | turn.py + jsonl_log.py import `apps.api.*` first; never re-install the filter. |
| 3 | POST /turn with `{"message": "hi"}` against FakeStreamingAdapter returns 200 + Content-Type: text/event-stream + last event is `done`. | `test_streams_chatchunks` (pass). |
| 4 | Each chunk serialised as `event: <type>\ndata: <json>\n\n` (D-07). | Test 1 enumerates `event:` and `data:` lines; named event matches chunk.type. |
| 5 | decide() runs via `await asyncio.to_thread(decide, prompt, history, artifacts, settings)`. | `test_decide_runs_in_thread` counter assert; source grep `asyncio.to_thread(decide`. |
| 6 | override_backend in body skips decide(); synthesised RoutingDecision has rationale="user override", confidence=1.0. | `test_override_backend` (pass; jsonl line shows the synthesised rationale). |
| 7 | After decide() and BEFORE adapter dispatch, one JSONL line appended with the 8 canonical fields. | `test_jsonl_log_appended` (pass). |
| 8 | After Done: DB has 1 user msg + 1 asst msg (content_blocks contains every non-TextDelta chunk) + 1 routing_decisions row — ONE BEGIN/COMMIT. | `test_one_transaction_per_turn` (pass). |
| 9 | Adapters lazily constructed; server boots without all keys (D-15). | `_get_or_create_adapter` source; `test_streams_chatchunks` injects FakeStreamingAdapter via `app.state.adapters`. |
| 10 | computer_use opt-out → HTTPException(400) BEFORE SSE opens (D-12 STRICT AND). | `test_computer_use_gated_when_opt_out` (pass). |
| 11 | `EventSourceResponse(ping=15)` per D-06; monkeypatched 0.3 + `sleep_per_chunk=1.0` shows ≥1 `:` heartbeat. | `test_heartbeat_emits` (pass). |
| 12 | task.cancel() within 50ms produces terminal Done within 2s wall-clock budget (API-06). | `test_cancellation_within_2s` (pass; `elapsed < 2.0` inline assertion). |
| 13 | `uv run pytest apps/api/tests/test_turn_streaming.py -x --timeout=30` exits 0 with 9 sub-tests. | Verified: `9 passed in 4.5s`. |

## Confirmations

- **Phase 1 D-18 import-graph guard:** `uv run pytest src/routing/tests/test_decide_smoke.py -x` → 7 passed in 2.0s. turn.py imports `decide` + `RoutingDecision` from `src.routing.*` but does NOT pull FastAPI back into `src.routing.*`.
- **Phase 2 + Phase 3 Waves 0-3 + Wave 4 whole-repo non-live suite:** `uv run pytest -m 'not live' --timeout=60` → 276 passed / 2 skipped / 3 deselected in both `apps/ src/` and `src/ apps/` orderings.
- **Negative-grep guards:**
  - `! grep -rE 'from fastapi.testclient' apps/api/tests/` → no matches (API-08 / D-20).
  - `! grep -E 'execute\(f"' apps/api/routes/turn.py` → no matches (no f-string SQL).
  - `! grep -q "TestClient" apps/api/routes/turn.py apps/api/tests/test_turn_streaming.py` → no matches.
  - `! grep -q "sys.path.append" apps/api/routes/turn.py apps/api/jsonl_log.py` → no matches.
  - `! grep -q "response.aclose" apps/api/tests/test_turn_streaming.py` → no matches (Pitfall 6 anti-pattern).

## Requirements satisfied

| REQ ID | Description | Evidence |
|--------|-------------|----------|
| API-02 | POST /api/v1/threads/{id}/turn streams ChatChunks as SSE | turn.py @router.post + EventSourceResponse; `test_streams_chatchunks`. |
| API-05 | 15s SSE heartbeat | `ping=15`; `test_heartbeat_emits` with monkeypatched 0.3. |
| API-06 | Cancellation within 2s | task.cancel + asyncio.CancelledError handler emits terminal pair; `test_cancellation_within_2s` enforces `elapsed < 2.0`. |
| API-07 | decide() via asyncio.to_thread | `await asyncio.to_thread(decide, ...)`; `test_decide_runs_in_thread` counter. |
| STORE-05 | ONE BEGIN/COMMIT per turn on Done | `persist_turn` in `event_stream`'s `finally`; `test_one_transaction_per_turn` asserts 2 messages + 1 routing row. |
| STORE-06 | routing_decisions.jsonl offline log | `append_routing_decisions_jsonl` called BEFORE adapter dispatch; `test_jsonl_log_appended`. |

## Files

### Created

- `apps/api/jsonl_log.py` (141 LOC) — STORE-06 + D-05 writer.
- `apps/api/routes/turn.py` (582 LOC) — SSE turn handler. THE HEART OF PHASE 3.
- `apps/api/tests/test_turn_streaming.py` (844 LOC) — 9 async tests covering all 6 requirements.

### Modified

- `apps/api/main.py` — `+app.include_router(turn.router)` after `settings.router`.

## Self-Check: PASSED

- `apps/api/jsonl_log.py` exists: FOUND.
- `apps/api/routes/turn.py` exists: FOUND.
- `apps/api/tests/test_turn_streaming.py` exists: FOUND.
- Commit `aa7ecad` (Task 1): FOUND.
- Commit `3c794f7` (Task 2): FOUND.
- Commit `ab68659` (Task 3): FOUND.
- Whole-repo `pytest -m 'not live'`: 276 passed.
- Phase 1 D-18 guard (`test_decide_smoke.py`): 7 passed.
- 9 sub-tests in `test_turn_streaming.py`: pass in isolation (4.5s) and in full suite (both orderings).
