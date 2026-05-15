---
phase: 02-backend-adapters-chatchunk-contract
plan: 01
subsystem: backend-adapters
tags: [openrouter, openai-sdk, async-streaming, cost-tracking, cancellation, chatchunk, tiktoken]
dependency_graph:
  requires:
    - "apps.api.backends.chunks (Wave 0 — TextDelta, ToolCall, StreamError, Done)"
    - "apps.api.backends.protocol (Wave 0 — BackendAdapter, Message, AdapterOptions)"
    - "apps.api.backends.cost (Wave 0 — CostTracker, DEFAULT_PER_TURN_COST_USD)"
    - "apps.api.backends.pricing (Wave 0 — PricingTable)"
    - "config/pricing.json (Wave 0 — 14 model rows + _default fallback)"
  provides:
    - "apps.api.backends.openrouter.OpenRouterAdapter (BackendAdapter Protocol impl)"
    - "apps.api.backends.openrouter.cost.OpenRouterCostTracker (tiktoken pre-flight + record_final_usage)"
    - "apps.api.backends.openrouter.errors.map_provider_error / PROVIDER_ERROR_MAP"
    - "apps.api.backends.openrouter.tests.fakes.FakeOpenAIClient + FakeAsyncStream + FakeChunk family"
    - "apps.api.backends.openrouter CLI: `python -m apps.api.backends.openrouter --prompt '...'`"
  affects:
    - "Wave 1 Plan 02 (Claude Code adapter) — same module-layout convention"
    - "Wave 1 Plan 03 (computer-use adapter) — same module-layout convention"
    - "Wave 2 Plan 04 (live smoke harness) — consumes test_live.py marker"
    - "Phase 3 FastAPI adapter registry — imports OpenRouterAdapter directly"
tech_stack:
  added:
    - "openai 2.36 AsyncOpenAI client pointed at https://openrouter.ai/api/v1"
    - "tiktoken gpt-4 encoder for input pre-flight (close-enough for non-OpenAI slugs)"
    - "secrets.choice base32 for tc_<6-char> tool_call_id generation"
  patterns:
    - "Module-level constants for service attribution (HTTP_REFERER, X_TITLE)"
    - "Lazy singleton PricingTable cached at module level (_get_pricing_table)"
    - "client_factory dependency injection for unit-test fakes (no monkeypatching required)"
    - "try/except/finally with terminal-pair emit then re-raise on CancelledError (PEP 789)"
    - "Tool-call streaming delta accumulation by tc_delta.index dict slot"
    - "Canonical-class-name fallback in PROVIDER_ERROR_MAP for sys.modules purge robustness"
key_files:
  created:
    - "apps/api/backends/openrouter/__init__.py"
    - "apps/api/backends/openrouter/__main__.py"
    - "apps/api/backends/openrouter/adapter.py"
    - "apps/api/backends/openrouter/cost.py"
    - "apps/api/backends/openrouter/errors.py"
    - "apps/api/backends/openrouter/tests/__init__.py"
    - "apps/api/backends/openrouter/tests/conftest.py"
    - "apps/api/backends/openrouter/tests/fakes.py"
    - "apps/api/backends/openrouter/tests/test_adapter.py"
    - "apps/api/backends/openrouter/tests/test_cost_and_errors.py"
    - "apps/api/backends/openrouter/tests/test_live.py"
  modified: []
decisions:
  - "openai SDK 2.36 AuthenticationError / APIStatusError constructors dereference response.request; the older response=None pattern in RESEARCH Pattern 3 line 514 raises AttributeError. Adapter builds a minimal httpx.Request + httpx.Response (status 401) via _build_missing_key_error so the typed exception surfaces correctly. Same fix applied in tests via _make_auth_error / _make_api_status_error helpers."
  - "Phase 1 D-18 guard test deliberately purges openai from sys.modules to verify the routing brain has no transitive HTTP / SDK import. After the purge, openai re-imports with fresh class objects, breaking object-identity isinstance against the import-time PROVIDER_ERROR_MAP keys. Fix: map_provider_error compares via the fully-qualified class name (cls.__module__ + cls.__qualname__) as a fallback to isinstance; test_provider_error_map_has_all_four_classes also compares by name."
  - "PricingTable is loaded once per process via _get_pricing_table() singleton (Path(__file__).resolve().parents[4] / 'config' / 'pricing.json'). Each OpenRouterAdapter instance reuses the cached table, avoiding the ~1 ms JSON load on every construction."
  - "package __init__.py re-exports OpenRouterAdapter at Task 2 completion (not Task 1), so the cost / errors / fakes submodules are importable during Task 1 RED phase without an unresolved import chain."
metrics:
  duration_min: 26
  tasks_completed: 3
  files_created: 11
  files_modified: 0
  unit_tests_pass: 24
  contract_tests_pass: 5
  contract_tests_skipped: 1
  d18_guard_state: green
  completed_at: "2026-05-15"
---

# Phase 02 Plan 01: OpenRouter Adapter Summary

**Implements `OpenRouterAdapter` — async streaming via OpenAI SDK 2.36 pointed at `https://openrouter.ai/api/v1`, with HTTP-Referer + X-Title attribution headers, `stream_options.include_usage` for provider-truth usage, per-turn USD cost cap, tool-call delta accumulation, 2-second cancellation budget, and a CLI entry point.**

## Performance

- **Duration:** 26 min
- **Started:** 2026-05-15T15:01:05Z
- **Completed:** 2026-05-15T15:27:19Z
- **Tasks:** 3
- **Files created:** 11
- **Files modified:** 0

## Accomplishments

- Wave 1 OpenRouter adapter lands first of three backend adapters; D-19 shared contract suite now passes 5/6 invariants for the `openrouter` parameterization (1 skipped — step_cap_aborts N/A for OpenRouter's single round-trip).
- Phase 2 Success Criterion #1 is satisfied: `python -m apps.api.backends.openrouter --prompt "hi"` streams one JSON line per ChatChunk to stdout with the last line carrying `"type":"done"` (D-04 invariant).
- All three locked pitfalls from `02-RESEARCH.md` have explicit regression tests in `test_adapter.py`: Pitfall 1 (`stream_options.include_usage`), Pitfall 3 (`default_headers` on constructor), and the tc_<6-char-base32> tool_call_id shape from CONTEXT specifics line 257.
- Cancellation contract (BACKEND-07 / PEP 789): `try / except asyncio.CancelledError / yield StreamError + Done / raise` plus `finally: await in_flight.close()`. Empirically enforced via `@pytest.mark.timeout(2)` on the cancellation test.
- Phase 1 D-18 import-graph guard remains green — Phase 2's `openai` / `httpx` additions do not leak into `src.routing.decide`'s sys.modules graph.

## Task Commits

Each task was committed atomically:

1. **Task 1: Author OpenRouterCostTracker + error map + fakes** — `8034486` (test)
2. **Task 2: Implement OpenRouterAdapter (stream + cancellation + cost cap + tool-call accumulation)** — `c4b622d` (feat)
3. **Task 3: Adapter tests + CLI + live smoke + D-19 verification** — `134577c` (test)

## Files Created (11)

| Path | Purpose |
| ---- | ------- |
| `apps/api/backends/openrouter/__init__.py` | Re-exports `OpenRouterAdapter`; `__all__ = ["OpenRouterAdapter"]`. |
| `apps/api/backends/openrouter/__main__.py` | CLI: `python -m apps.api.backends.openrouter --prompt '...'` per Phase 2 SC #1. Lazy adapter import + `_entrypoint` indirection (WR-07). |
| `apps/api/backends/openrouter/adapter.py` | `OpenRouterAdapter` class implementing `BackendAdapter` Protocol. Module constants `OPENROUTER_BASE_URL`, `HTTP_REFERER`, `X_TITLE`. `_default_client_factory` injects `default_headers` on `AsyncOpenAI` constructor. `stream()` is a 6-stage async generator: tiktoken pre-flight → `create(stream_options.include_usage=True)` → per-chunk loop → tool-call flush → final usage override → terminal Done. Full V7-style exception handling for `AuthenticationError`, `APITimeoutError`, `APIStatusError`, generic `Exception`, and `asyncio.CancelledError` (re-raised after terminal pair). `finally` block aborts in_flight via `in_flight.close()`. |
| `apps/api/backends/openrouter/cost.py` | `OpenRouterCostTracker(CostTracker)` with class-level `_ENCODING = tiktoken.encoding_for_model("gpt-4")` shared across instances. `record_input_estimate` joins prompt + history.content + encodes. `record_output_delta` per-token tally. `record_final_usage` overrides estimate with provider truth. |
| `apps/api/backends/openrouter/errors.py` | `PROVIDER_ERROR_MAP: {openai.AuthenticationError → ("auth_failed", False), openai.RateLimitError → ("rate_limited", True), openai.APITimeoutError → ("timeout", True), openai.APIStatusError → ("provider_unavailable", True)}` + `map_provider_error(exc) → (code, message, retriable)` with canonical-class-name fallback (Rule 1 fix below). |
| `apps/api/backends/openrouter/tests/__init__.py` | Empty package marker. |
| `apps/api/backends/openrouter/tests/conftest.py` | Session-scoped `pricing_table` fixture (5-up path resolution: `apps/api/backends/openrouter/tests/conftest.py` → repo root). Function-scoped `fake_openai_client` (happy-path 2-chunk) + `fake_openai_factory` (callable returning fake). |
| `apps/api/backends/openrouter/tests/fakes.py` | `FakeDelta`, `FakeChoice`, `FakeUsage`, `FakeChunk` dataclasses + `FakeAsyncStream`, `FakeChatCompletions` (records `create_calls` kwargs for Pitfall-1 regression), `FakeOpenAIClient`. Per RESEARCH Common Operation 3 lines 1916-1979 verbatim shape. |
| `apps/api/backends/openrouter/tests/test_adapter.py` | 13 unit tests (T1-T12 plus internal_error test). Covers happy path, default_headers constructor wiring (Pitfall 3), stream_options.include_usage (Pitfall 1), cost-cap mid-stream abort, cancellation within 2s, tool-call delta accumulation, missing-key raise, AuthenticationError / APITimeoutError / APIStatusError@429 / APIStatusError@503 / RuntimeError mid-stream mapping, and routing_signals pass-through. |
| `apps/api/backends/openrouter/tests/test_cost_and_errors.py` | 11 unit tests covering `record_input_estimate` / `record_output_delta` / `record_final_usage` arithmetic, `over_cap()` predicate at boundary, `map_provider_error` for AuthenticationError / RateLimitError / APITimeoutError / unrelated exception, PROVIDER_ERROR_MAP class membership (by canonical name), and FakeOpenAIClient async iteration + create-kwargs recording. |
| `apps/api/backends/openrouter/tests/test_live.py` | One opt-in `@pytest.mark.live` test against the real OpenRouter API, gated by `skipif(not os.getenv("OPENROUTER_API_KEY"))`. Asks GPT-5 for "say hi in exactly one word" with `max_cost_usd=0.10`; asserts ≥ 1 TextDelta, final Done, `0 < cost_usd < 0.10`. |

## Constants Chosen

| Constant | Value | Reason |
| -------- | ----- | ------ |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | BACKEND-03 |
| `HTTP_REFERER` | `https://github.com/marreroii-michael/Prompt-Optimizer` | OpenRouter per-app attribution; matches userEmail in CLAUDE.md context |
| `X_TITLE` | `Prompt-Optimizer` | OpenRouter per-app attribution; matches project name |

## D-19 Invariant Pass Count for OpenRouter

```
$ uv run pytest -m 'not live' apps/api/backends/tests/test_adapter_contract.py -k openrouter -v
collected 18 items / 12 deselected / 6 selected
apps/api/backends/tests/test_adapter_contract.py ..s...
================= 5 passed, 1 skipped, 12 deselected in 0.37s =================
```

- ✓ `test_happy_path_terminates_with_done[openrouter]`
- ✓ `test_cost_cap_aborts[openrouter]`
- ⊘ `test_step_cap_aborts[openrouter]` — `pytest.skip("step cap not applicable to OpenRouter (single round-trip)")` per D-19 frontmatter note
- ✓ `test_cancellation_within_2_seconds[openrouter]`
- ✓ `test_done_always_lands[openrouter]`
- ✓ `test_missing_api_key_raises_before_stream[openrouter]`

## Live Test Instructions

```bash
OPENROUTER_API_KEY=sk-or-v1-... uv run pytest -m live apps/api/backends/openrouter/
```

Without the key the test is skipped (still collectable). The test ceiling-checks `cost_usd < 0.10` so it cannot accidentally bill a real account more than ~10¢.

## Decisions Made

1. **httpx-backed exception construction.** The openai SDK 2.36 constructor for `AuthenticationError` and `APIStatusError` dereferences `response.request` so the older `response=None` shape from RESEARCH Pattern 3 line 514 raises `AttributeError` before the exception is even raised. Adapter and tests build minimal `httpx.Request + httpx.Response(status=401)` via `_build_missing_key_error` / `_make_auth_error` helpers.

2. **Canonical-class-name fallback in `map_provider_error`.** Phase 1's D-18 guard test purges `openai` from `sys.modules` and re-imports `src.routing.decide` to prove the routing brain doesn't pull SDK imports. The next test that creates an openai exception gets a fresh class object that fails identity comparison against the import-time `PROVIDER_ERROR_MAP` keys (which still reference the previous module's classes). Fix: in addition to `isinstance` check, compare `f"{cls.__module__}.{cls.__qualname__}"` strings.

3. **Lazy singleton `PricingTable`.** Loading `config/pricing.json` is cheap (~1 ms) but each adapter construction would otherwise repeat it. `_get_pricing_table()` caches the table at module level on first call.

4. **`__init__.py` re-export deferred to Task 2 commit.** Writing `from .adapter import OpenRouterAdapter` at Task 1 commit time would have made the `openrouter` package unimportable (no adapter.py yet). Task 1 commit ships an empty `__init__.py`; Task 2 commit replaces it with the canonical re-export.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] openai SDK 2.36 AuthenticationError requires non-None httpx.Response**

- **Found during:** Task 1 (errors module tests).
- **Issue:** RESEARCH Pattern 3 line 514 + spec text use `openai.AuthenticationError("OPENROUTER_API_KEY not set", response=None, body=None)`. In openai SDK 2.x the constructor body dereferences `response.request`, so passing `response=None` raises `AttributeError: 'NoneType' object has no attribute 'request'` before the typed exception can be raised. Tests fail with the wrong exception class.
- **Fix:** Build a minimal real `httpx.Request("POST", url=...)` + `httpx.Response(status_code=401, request=request)` and pass them through to `AuthenticationError(message=..., response=response, body=None)`. Wrapped in:
  - `apps/api/backends/openrouter/adapter.py::_build_missing_key_error()` (production adapter).
  - `apps/api/backends/openrouter/tests/test_cost_and_errors.py::_make_auth_error / _make_rate_limit_error / _make_api_status_error` (test helpers).
- **Files modified:** `adapter.py`, `tests/test_cost_and_errors.py`, `tests/test_adapter.py`.
- **Verification:** `OpenRouterAdapter(api_key='')` now correctly raises `openai.AuthenticationError` before returning from `__init__` (D-19 invariant #6); 24 unit tests + 5 D-19 contract cases pass.
- **Committed in:** `8034486` (Task 1), `c4b622d` (Task 2).

**2. [Rule 1 — Bug] PROVIDER_ERROR_MAP class identity fails after `sys.modules` purge**

- **Found during:** Task 3 (full-suite run after adding adapter tests).
- **Issue:** Phase 1's `src/routing/tests/test_decide_smoke.py::test_no_forbidden_modules_imported_after_decide` deliberately deletes every `openai*` / `httpx*` / `anthropic*` / etc. key from `sys.modules` to verify the routing brain doesn't pull SDK imports. After the purge, any subsequent `import openai` loads a fresh module with fresh class objects. The `PROVIDER_ERROR_MAP` dict (constructed at module load time inside `apps.api.backends.openrouter.errors`) still references the previous module's class objects. `isinstance(new_exc, old_class)` returns False; `new_class in PROVIDER_ERROR_MAP` returns False. `map_provider_error` falls through to `("internal_error", ...)` and the corresponding contract test fails.
- **Fix:** Added a name-based fallback in `map_provider_error`: iterate `PROVIDER_ERROR_MAP` keys, compute `f"{cls.__module__}.{cls.__qualname__}"` for each, and match against the exception's own MRO names. Also rewrote `test_provider_error_map_has_all_four_classes` to compare by canonical name instead of object identity. Adapter's own `except openai.AuthenticationError as exc:` blocks are unaffected because Python loads the adapter module fresh after the purge (and thus its class references are always the current ones).
- **Files modified:** `apps/api/backends/openrouter/errors.py`, `apps/api/backends/openrouter/tests/test_cost_and_errors.py`.
- **Verification:** Full `uv run pytest -m 'not live'` exits 0 regardless of file-collection order; running `pytest test_cost_and_errors.py test_decide_smoke.py test_cost_and_errors.py` to force the purge between two invocations of the cost-and-errors suite also exits 0.
- **Committed in:** `134577c` (Task 3).

---

**Total deviations:** 2 Rule-1 bug fixes.

**Impact on plan:** Both fixes preserve the behavior contracts named in the plan (typed `AuthenticationError` on missing key; D-06 closed-vocabulary mapping for every openai exception). The SDK-version-specific constructor signature was a documented assumption in RESEARCH; the canonical-name fallback is purely defensive against an existing test pattern. No scope creep, no architecture changes, no new dependencies.

## Authentication Gates

None. All work in this plan ran offline against fakes. The opt-in live test is preserved for when the user supplies `OPENROUTER_API_KEY` per the BYOK contract.

## Verification Commands Re-run at Completion

```bash
# 1. Adapter unit + cost / errors / fakes tests.
$ uv run pytest -m 'not live' apps/api/backends/openrouter/ -q
........................                                                 [100%]
24 passed, 1 deselected in 0.09s

# 2. D-19 shared contract suite for openrouter parameterization.
$ uv run pytest -m 'not live' apps/api/backends/tests/test_adapter_contract.py -k openrouter -v
collected 18 items / 12 deselected / 6 selected
apps/api/backends/tests/test_adapter_contract.py ..s...                  [100%]
================= 5 passed, 1 skipped, 12 deselected =================

# 3. Phase 1 D-18 import-graph guard (no regression).
$ uv run pytest src/routing/tests/test_decide_smoke.py -x -q
.......                                                                  [100%]

# 4. CLI help — accepts --prompt, --model, --max-cost-usd, --max-steps.
$ uv run python -m apps.api.backends.openrouter --help
usage: python -m apps.api.backends.openrouter [-h] --prompt PROMPT
                                              [--model MODEL]
                                              [--max-cost-usd MAX_COST_USD]
                                              [--max-steps MAX_STEPS]
...

# 5. CLI without OPENROUTER_API_KEY exits 1 with stderr message.
$ unset OPENROUTER_API_KEY && uv run python -m apps.api.backends.openrouter --prompt "hi"
ERROR: set OPENROUTER_API_KEY in env or .env
exit=1

# 6. Whole-repo test pass (no regressions in src/* or apps/*).
$ uv run pytest -m 'not live' -q
.............................s.......................................... [ 38%]
......................................................ss.sssss.ss.ss.ss. [ 77%]
..........................................                               [100%]
```

## Next Plan Readiness

Wave 1 Plans 02 (Claude Code adapter) and 03 (computer-use adapter) can now follow the locked module layout:

- `apps/api/backends/<backend>/__init__.py` (re-export `XxxAdapter`).
- `apps/api/backends/<backend>/__main__.py` (CLI mirror of `openrouter/__main__.py`, parametrized on backend).
- `apps/api/backends/<backend>/adapter.py` (BackendAdapter Protocol impl).
- `apps/api/backends/<backend>/cost.py` (CostTracker subclass).
- `apps/api/backends/<backend>/errors.py` (PROVIDER_ERROR_MAP + map_provider_error).
- `apps/api/backends/<backend>/tests/{__init__,conftest,fakes,test_adapter,test_live}.py`.

The D-19 shared contract suite at `apps/api/backends/tests/test_adapter_contract.py` activates per-adapter as each one lands, with the same `try / except ImportError → pytest.skip` lazy-import pattern already in place inside `conftest.adapter_factory`.

## Self-Check: PASSED

All files claimed in the SUMMARY exist; all three task commits exist in the git log.

```
$ for f in apps/api/backends/openrouter/__init__.py \
          apps/api/backends/openrouter/__main__.py \
          apps/api/backends/openrouter/adapter.py \
          apps/api/backends/openrouter/cost.py \
          apps/api/backends/openrouter/errors.py \
          apps/api/backends/openrouter/tests/__init__.py \
          apps/api/backends/openrouter/tests/conftest.py \
          apps/api/backends/openrouter/tests/fakes.py \
          apps/api/backends/openrouter/tests/test_adapter.py \
          apps/api/backends/openrouter/tests/test_cost_and_errors.py \
          apps/api/backends/openrouter/tests/test_live.py; do
    [ -f "$f" ] && echo "FOUND: $f" || echo "MISSING: $f"
done

$ git log --oneline --all | grep -E "8034486|c4b622d|134577c"
134577c test(02-01): add OpenRouter adapter tests, CLI, and live smoke
c4b622d feat(02-01): implement OpenRouterAdapter with cost cap + cancellation
8034486 test(02-01): add OpenRouter cost tracker, error map, and fakes
```

All 11 created files present; all 3 task commits present.

---

*Phase: 02-backend-adapters-chatchunk-contract*
*Plan: 01*
*Completed: 2026-05-15*
