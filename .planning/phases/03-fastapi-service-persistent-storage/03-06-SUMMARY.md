---
gsd_summary_version: 1.0
phase: "03"
plan: "06"
plan_id: "03-06-rename-secure-boot-smoke"
subsystem: "api/rename + api/security + api/boot"
tags: [phase-03, wave-6, rename, ui-14, api-04, secure-04, boot-smoke, d-17, d-19, phase-3-complete]
requires:
  - 03-00-SUMMARY.md   # Wave 0 — fake_adapter (FakeStreamingAdapter), paths.py
  - 03-01-SUMMARY.md   # Wave 1 — update_thread_title query helper
  - 03-02-SUMMARY.md   # Wave 2 — create_app() factory + lifespan
  - 03-03-SUMMARY.md   # Wave 3 — settings PATCH handler (RedactionFilter applies)
  - 03-04-SUMMARY.md   # Wave 4 — POST /turn handler (persist_turn writes to DB)
  - 03-05-SUMMARY.md   # Wave 5 — blobs cascade (turn flow already integrated)
provides:
  - "apps.api.routes.rename:router (POST /api/v1/threads/{id}/rename per D-17)"
  - "apps.api.routes.rename:RenameRequest (Pydantic v2 body)"
  - "apps.api.routes.rename:RENAME_MODEL = 'openai/gpt-4o-mini' (cheapest GPT slug per A2)"
  - "apps.api.routes.rename:RENAME_MAX_COST_USD = 0.01 ($0.01 per rename ceiling)"
  - "apps.api.routes.rename:RENAME_MAX_INPUT_TOKENS = 1500 (tiktoken pre-flight cap)"
  - "apps.api.routes.rename:RENAME_PROMPT_TEMPLATE (system prompt per CONTEXT 348)"
  - "Extended apps.api.main:create_app — final include_router(rename.router)"
  - "Phase 3 SC #1 boot-smoke gate: from apps.api.main import app under 3 s warm"
  - "API-04 canonical disclosure regression — caplog + DB + settings.json + jsonl scans"
affects:
  - "apps/api/main.py (final include_router list — health + threads + settings + turn + rename)"
  - "Phase 5 UI-14 hook — endpoint is now live for the auto-rename flow"
  - "REQUIREMENTS.md API-07 wording (asyncio.to_thread permitted alongside run_in_threadpool)"
tech_stack:
  added:
    - "(no new third-party libs — tiktoken already a Phase 2 carry-forward dep)"
  patterns:
    - "One-shot adapter consume pattern (mirrors apps/api/backends/openrouter/__main__.py 30-80)"
    - "Defensive constants pinned at module load (Final[T] + module-level _ENC encoder)"
    - "Pre-stream pipeline order — 404 → tiktoken cap (413) → key pre-check (400) → adapter ctor"
    - "Fresh per-request adapter (NOT cached) — defense against stale cache after missed invalidation"
    - "API-04 four-surface scan — caplog + SQLite columns + settings.json + routing_decisions.jsonl"
    - "Boot smoke via subprocess.run([sys.executable, '-c', ...]) — fresh process avoids module-cache short-circuit"
key_files:
  created:
    - "apps/api/routes/rename.py (301 LOC) — POST /api/v1/threads/{id}/rename endpoint with defensive constants, tiktoken pre-flight, fresh per-request adapter, ≤60 char trim, bypasses the brain"
    - "apps/api/tests/test_rename.py (558 LOC) — 8 sub-tests covering happy path, 413 cap, 60-char trim, brain bypass, fresh-adapter, 404, quote-strip, 400 on missing key"
    - "apps/api/tests/test_secure_no_key_in_logs.py (495 LOC) — 4 sub-tests covering the canonical API-04 regression (PATCH /settings + turn flow + Anthropic + Bearer)"
    - "apps/api/tests/test_boot_smoke.py (145 LOC) — 3 sub-tests covering <3s subprocess import, app singleton attributes, all Phase 3 routes mounted"
  modified:
    - "apps/api/main.py — +rename import, +include_router(rename.router) after turn (2 lines net)"
    - ".planning/REQUIREMENTS.md — API-07 line rewritten to permit asyncio.to_thread OR starlette.concurrency.run_in_threadpool per D-16"
decisions:
  - "D-17 rename endpoint locked: hardcoded model=openai/gpt-4o-mini (cheapest GPT-class OpenRouter slug per CONTEXT specifics line 348 + Assumption A2), max_cost_usd=0.01, max_steps=1. Fresh OpenRouterAdapter per request — NOT app.state.adapters['openrouter']. System prompt is the verbatim line 348 template. Plain JSON response (NOT SSE)."
  - "Tiktoken pre-flight cap landed as RENAME_MAX_INPUT_TOKENS=1500. Rejection (413) fires BEFORE the adapter constructor so an adversarial oversized first_user_message cannot blow the $0.01 budget. Encoding resolved via tiktoken.encoding_for_model('gpt-4o-mini') → o200k_base (verified at execute time)."
  - "OpenRouter key pre-check landed as a 400 with detail mentioning OPENROUTER_API_KEY. Without this pre-check, openai.AuthenticationError from the adapter constructor would bubble up as an opaque 500. The cleaner 400 + remediation hint is the WARNING-fix carry-forward from the plan critical-context."
  - "Title trim sequence is .strip().strip('\"').strip(\"'\").strip()[:60] — handles leading/trailing whitespace, then ASCII double-quote, then single-quote, then any whitespace exposed by the quote-strip. Final [:60] cap is unconditional regardless of model output."
  - "Inline docstring anti-pattern references rewritten so the literal substrings 'decide' and 'app.state.adapters[\"openrouter\"]' do NOT appear anywhere in apps/api/routes/rename.py — keeps the negative-grep CI guards satisfied without changing the documented intent. Same Rule 1 fix style as Wave 4 ('response.aclose') and Wave 5 ('os.rename' / 'os.path.join')."
  - "API-04 canonical regression scans 4 surfaces: caplog.text (RedactionFilter), every text column across threads / messages / routing_decisions / schema_meta (D-04 + STORE-05), SETTINGS_PATH (D-11), and JSONL_LOG_PATH (D-05). Both full-key and 8-char-prefix matches are checked — prefix-only would be a partial disclosure the test would otherwise miss."
  - "Boot smoke uses subprocess.run with a fresh sys.executable child rather than importlib.reload inside the test process. The fresh process avoids module-cache short-circuit (sklearn / tiktoken loaded by earlier tests would otherwise mask the boot cost). 60s pytest-timeout absorbs the Pitfall 9 cold-cache worst case while the 3.0s assertion is the warm-cache budget per ROADMAP SC #1."
  - "API-07 REQUIREMENTS.md wording landed per D-16: both asyncio.to_thread AND starlette.concurrency.run_in_threadpool are now explicitly permitted. The Phase 3 turn handler uses asyncio.to_thread (Wave 4); the REQUIREMENTS update aligns the wording with the actual implementation."
metrics:
  duration: "81m"
  completed: "2026-05-18T01:37:34Z"
requirements_completed: [API-04]
---

# Phase 3 Plan 06: Rename + Secure Regression + Boot Smoke Summary

**Wave 6 closes Phase 3.** Lights up the rename endpoint (UI-14 forward-wire — Phase 5 hooks it from the UI), authors the canonical API-04 disclosure regression test (the gate for "BYOK keys NEVER appear in DB or logs"), authors the boot-smoke test that proves ROADMAP Phase 3 SC #1 (<3s warm import), and updates the API-07 requirement wording per D-16.

## Performance

- **Duration:** ~81 min
- **Started:** 2026-05-18T00:16:26Z
- **Completed:** 2026-05-18T01:37:34Z
- **Tasks:** 5 (4 TDD + 1 docs)
- **Files modified:** 6 (4 created + 2 modified)
- **Tests added:** 15 sub-tests (8 + 4 + 3)

## Accomplishments

- **D-17 rename endpoint shipped.** `POST /api/v1/threads/{id}/rename` accepts `{"first_user_message": str}`, runs one OpenRouter completion (fresh `OpenRouterAdapter` per request — NOT the cached one), accumulates `TextDelta` text into a string, trims to `≤60` chars (`.strip().strip('"').strip("'").strip()[:60]`), persists via `update_thread_title`, returns `{"title": "..."}` as plain JSON. NEVER calls the routing brain (UI-14 explicit). NEVER returns SSE (D-17 explicit). All defensive constants land as `Final[T]` at module load.
- **API-04 canonical regression test landed.** `test_secure_no_key_in_logs.py` covers 4 sub-tests: PATCH /settings with `sk-or-v1-…`, turn-via-keystore with a different shape, PATCH /settings with `sk-ant-…`, and a manual `Authorization: Bearer …` log line. Each test scans 4 disclosure surfaces — `caplog.text`, SQLite text columns across `threads / messages / routing_decisions / schema_meta`, `SETTINGS_PATH` file, and `JSONL_LOG_PATH` file. ZERO matches across all four surfaces in all four tests.
- **ROADMAP Phase 3 SC #1 boot smoke verified.** `test_boot_under_3_seconds` runs `subprocess.run([sys.executable, "-c", "from apps.api.main import app"])` in a fresh Python process and asserts wall-clock <3.0 s. Direct measurement: 2.11s in a fresh process, 1.48s in-process. The `test_all_phase_3_routes_mounted` companion test walks `app.routes` and confirms every Phase 3 path is mounted (healthz, threads CRUD, turn, rename, settings).
- **API-07 REQUIREMENTS wording updated.** Old: `wrapped in run_in_threadpool when invoked from async handlers`. New (per D-16): `wrapped in asyncio.to_thread (or equivalent thread-pool offload such as starlette.concurrency.run_in_threadpool) when invoked from async handlers`. The new wording matches the actual Wave 4 implementation in `turn.py` which uses `asyncio.to_thread(decide, ...)`.
- **5 new files (4 created + 2 modified — main.py + REQUIREMENTS.md);** whole-repo non-live suite **301 passed / 2 skipped / 3 deselected** (+15 vs Wave 5's 286 baseline). All 8 rename tests, all 4 secure tests, all 3 boot smoke tests pass.

## Task Commits

Each task was committed atomically:

1. **Task 1: apps/api/routes/rename.py + apps/api/main.py extension** — `e8d8811` (feat)
2. **Task 2: apps/api/tests/test_rename.py — 8 sub-tests via httpx + ASGITransport + monkeypatched OpenRouterAdapter** — `6bb7cef` (test)
3. **Task 3: apps/api/tests/test_secure_no_key_in_logs.py — 4 sub-tests covering the canonical API-04 regression** — `7b22e19` (test)
4. **Task 4: apps/api/tests/test_boot_smoke.py — 3 sub-tests (subprocess import + app attrs + route inventory)** — `9e8c915` (test)
5. **Task 5: .planning/REQUIREMENTS.md — API-07 wording updated per D-16** — `01f2f71` (docs)

## Files Created/Modified

### Created

- **`apps/api/routes/rename.py`** (301 LOC) — Public surface: `router`, `RenameRequest`, `RENAME_MODEL`, `RENAME_MAX_COST_USD`, `RENAME_MAX_INPUT_TOKENS`, `RENAME_PROMPT_TEMPLATE`. Module-level `_ENC = tiktoken.encoding_for_model("gpt-4o-mini")` for the pre-flight token estimate. Endpoint `rename_thread` follows the 8-step pipeline: 404 thread check → tiktoken estimate → 413 cap → 400 key pre-check → fresh adapter → consume stream into title_parts → trim+cap → persist → return JSON. No imports from `src.routing.decide` (rename bypasses the brain). No reference to `app.state.adapters` (rename builds a fresh adapter).
- **`apps/api/tests/test_rename.py`** (558 LOC) — 8 sub-tests:
  - `test_rename_happy_path` — 2-TextDelta + Done emits `"Brief Title"`; DB row updated.
  - `test_rename_tiktoken_cap_returns_413` — oversized body returns 413; adapter ctor never called.
  - `test_rename_truncates_to_60_chars` — 200-char output trimmed to exactly 60.
  - `test_rename_bypasses_decide` — monkeypatched brain raises but rename still 200s.
  - `test_rename_uses_fresh_adapter_not_cached` — sentinel pre-populated in adapter cache survives the rename.
  - `test_rename_thread_not_found_returns_404` — unknown thread_id returns 404 before any adapter call.
  - `test_rename_strips_quotes_from_title` — `'"Quoted Title"'` becomes `'Quoted Title'`.
  - `test_rename_returns_400_when_openrouter_key_missing` — empty KeyStore returns 400 with OPENROUTER_API_KEY in detail; adapter ctor never called.
- **`apps/api/tests/test_secure_no_key_in_logs.py`** (495 LOC) — 4 sub-tests (the canonical API-04 disclosure regression):
  - `test_secure_no_key_in_logs_after_patch_settings` (CANONICAL) — PATCH /settings carries `sk-or-v1-…`; scan caplog + DB + settings.json + jsonl; ZERO matches.
  - `test_secure_no_key_in_logs_after_turn_via_keystore` — full turn through FakeStreamingAdapter writes via `persist_turn`; same 4-surface scan.
  - `test_secure_no_anthropic_key_in_logs` — `sk-ant-…` shape covered by the dedicated `***REDACTED-ANTHROPIC***` branch.
  - `test_secure_no_bearer_token_in_logs` — manual `Authorization: Bearer …` log line rewritten as `Bearer ***REDACTED***` (CR-05 carry-forward).
- **`apps/api/tests/test_boot_smoke.py`** (145 LOC) — 3 sub-tests:
  - `test_boot_under_3_seconds` — `subprocess.run([sys.executable, '-c', 'from apps.api.main import app'])` in a fresh process; wall-clock <3.0 s.
  - `test_app_module_attribute_is_fastapi_instance` — in-process confirms FastAPI class + canonical title.
  - `test_all_phase_3_routes_mounted` — walks `app.routes`; asserts every Phase 3 path is present.

### Modified

- **`apps/api/main.py`** — +`rename` import in the lazy-imports tuple, +`app.include_router(rename.router)` after `turn`. 2 lines net.
- **`.planning/REQUIREMENTS.md`** — API-07 line rewritten to permit `asyncio.to_thread` OR `starlette.concurrency.run_in_threadpool` (D-16).

## Truth Audit — 10 of 10

The plan's `must_haves.truths` are all observable at the CLI / pytest level:

1. ✓ **Path discovery:** All Phase 3 source files use `pathlib.Path(__file__).resolve().parents[N]`; `grep -r "sys.path.append" apps/api/` returns no matches.
2. ✓ **Import side effects:** `apps/api/routes/rename.py` imports `apps.api.*` transitively (via `OpenRouterAdapter`, `update_thread_title`); the `dotenv.load_dotenv()` + `install_redaction_filter()` side effects in `apps/api/__init__.py` run exactly once per process.
3. ✓ **Rename happy path:** `test_rename_happy_path` asserts 200 + `{"title": "Brief Title"}` + DB row updated; fresh `OpenRouterAdapter(api_key=key, max_cost_usd=RENAME_MAX_COST_USD)` ctor; never touches `app.state.adapters`.
4. ✓ **400 on missing key:** `test_rename_returns_400_when_openrouter_key_missing` asserts 400 + `OPENROUTER_API_KEY` in detail + adapter ctor never called.
5. ✓ **Bypass the brain:** `test_rename_bypasses_decide` monkeypatches `src.routing.decide.decide` to raise; rename still 200s. The literal substring `decide` does NOT appear in `apps/api/routes/rename.py`.
6. ✓ **Tiktoken pre-flight cap:** `test_rename_tiktoken_cap_returns_413` asserts 413 + adapter ctor never called for `"lorem ipsum " * 1500` body.
7. ✓ **API-04 secure regression:** `test_secure_no_key_in_logs_after_patch_settings` asserts ZERO matches for `sk-or-v1` in caplog + DB scan across 4 tables + `SETTINGS_PATH.read_text()` + `JSONL_LOG_PATH.read_text()`.
8. ✓ **Boot smoke under 3s:** `test_boot_under_3_seconds` asserts subprocess `python -c 'from apps.api.main import app'` wall-clock <3.0 s; direct measurement 2.11s fresh / 1.48s warm.
9. ✓ **API-07 wording:** `grep "asyncio.to_thread.*or equivalent thread-pool offload" .planning/REQUIREMENTS.md` returns exit 0.
10. ✓ **Whole-repo non-live + Wave 6 suites:** `pytest apps/api/tests/test_rename.py apps/api/tests/test_secure_no_key_in_logs.py apps/api/tests/test_boot_smoke.py` 15 passed; `pytest -m 'not live'` 301 passed / 2 skipped / 3 deselected.

## Deviations from Plan

### Rule 1 fix — anti-pattern docstring references rewritten

- **Found during:** Task 1 verification — the plan's negative greps fire literally (`! grep -q "decide"` and `! grep -q "app.state.adapters\[.openrouter.\]"`). The first pass of `rename.py` had multiple references to both substrings in docstrings explaining "what we should NOT do" — which is correct documentation but trips the literal grep.
- **Fix:** Rewrote docstring lines to describe the anti-pattern without using the literal substring (same pattern as Wave 4's `response.aclose` rewrite and Wave 5's `os.rename` / `os.path.join` rewrites — already documented as a deviation precedent in `03-05-SUMMARY.md`).
- **Files modified:** `apps/api/routes/rename.py` (4 docstring lines).
- **Commit:** Included in Task 1 commit `e8d8811`.

### Rule 1 fix — TestClient docstring reference in test_boot_smoke.py

- **Found during:** Task 4 verification — the docstring contained `NEVER uses TestClient (API-08 / D-20)` which trips the literal `! grep -q "TestClient"` negative guard.
- **Fix:** Rewrote to `NEVER uses the synchronous FastAPI test-client wrapper (API-08 / D-20)`. Same intent, no literal substring.
- **Files modified:** `apps/api/tests/test_boot_smoke.py` (1 docstring line).
- **Commit:** Included in Task 4 commit `9e8c915`.

### Rule 3 fix — HTTPException multi-line vs grep-line constraint

- **Found during:** Task 1 verification — the plan's verify line uses `grep -q "HTTPException(status_code=413"` which requires the substring to be on a single line. My first pass had `raise HTTPException(\n    status_code=413,\n    detail=(...),\n)` (multi-line for readability).
- **Fix:** Refactored both the 413 (tiktoken cap) and 400 (missing key) raises to first assign `detail = (...)` then `raise HTTPException(status_code=N, detail=detail)` on one line.
- **Files modified:** `apps/api/routes/rename.py` (two raise blocks).
- **Commit:** Included in Task 1 commit `e8d8811`.

### Note — `OpenRouterAdapter(api_key` single-line refactor

- **Found during:** Task 1 verification — the plan's acceptance grep `grep -q "OpenRouterAdapter(api_key" apps/api/routes/rename.py` matches only when the constructor call has `api_key` on the same line as `OpenRouterAdapter(`. My first pass split across two lines.
- **Fix:** Inlined `adapter = OpenRouterAdapter(api_key=key, max_cost_usd=RENAME_MAX_COST_USD)` to a single line.
- **Files modified:** `apps/api/routes/rename.py` (one line).
- **Commit:** Included in Task 1 commit `e8d8811`.

## Phase 3 — All 5 ROADMAP Success Criteria

After Wave 6 lands, all 5 ROADMAP Phase 3 success criteria are verifiable:

1. ✓ **Boot under 3s:** `test_boot_under_3_seconds` (this wave).
2. ✓ **All routes mounted:** `test_all_phase_3_routes_mounted` (this wave).
3. ✓ **Adapters loaded lazily:** Wave 4 `test_decide_runs_in_thread` + Wave 3 `test_patch_settings_invalidates_adapter_cache` (D-15).
4. ✓ **Persistence atomic:** Wave 4 `test_one_transaction_per_turn` (D-04 + STORE-05).
5. ✓ **Keys never persist to disk:** Wave 6 `test_secure_no_key_in_logs_after_patch_settings` (CANONICAL API-04).

## Phase 3 — All 15 Requirements Satisfied

After Wave 6 lands, every Phase 3 requirement is verified by at least one passing test:

| Requirement | Spec | Verified by |
|---|---|---|
| API-01 | Routing brain via decide() | Wave 4 `test_decide_runs_in_thread` |
| API-02 | POST /turn streams ChatChunks | Wave 4 `test_streams_chatchunks` |
| API-03 | Thread CRUD | Wave 3 `test_threads_crud` (8 tests) |
| API-04 | BYOK keys never persist | Wave 6 `test_secure_no_key_in_logs_*` (CANONICAL) |
| API-05 | 15s heartbeat | Wave 4 `test_heartbeat_emits` |
| API-06 | Disconnect → cancel | Wave 4 `test_cancellation_within_2s` |
| API-07 | decide() in to_thread | Wave 4 `test_decide_runs_in_thread` |
| API-08 | httpx.AsyncClient + ASGITransport | Negative grep CI guard |
| STORE-01 | SQLite schema | Wave 1 `test_migrations` |
| STORE-02 | Pydantic models | Wave 1 `test_queries` |
| STORE-03 | persist_turn one transaction | Wave 4 `test_one_transaction_per_turn` |
| STORE-04 | Blob storage ≥256KB | Wave 5 `test_blobs_by_hash` (9 tests) |
| STORE-05 | Cascade delete | Wave 3 + Wave 5 `test_delete_unlinks_blobs` |
| STORE-06 | JSONL routing log | Wave 4 `test_jsonl_log_appended` |
| OSS-05 | No wildcard CORS | Wave 2 `test_cors` |

## Self-Check: PASSED

- ✓ `apps/api/routes/rename.py` exists (301 LOC).
- ✓ `apps/api/tests/test_rename.py` exists (558 LOC).
- ✓ `apps/api/tests/test_secure_no_key_in_logs.py` exists (495 LOC).
- ✓ `apps/api/tests/test_boot_smoke.py` exists (145 LOC).
- ✓ `apps/api/main.py` modified (include_router(rename.router) added).
- ✓ `.planning/REQUIREMENTS.md` modified (API-07 wording updated per D-16).
- ✓ Commit `e8d8811` exists (Task 1 — rename endpoint).
- ✓ Commit `6bb7cef` exists (Task 2 — rename tests).
- ✓ Commit `7b22e19` exists (Task 3 — secure regression).
- ✓ Commit `9e8c915` exists (Task 4 — boot smoke).
- ✓ Commit `01f2f71` exists (Task 5 — REQUIREMENTS API-07).
- ✓ All 15 Wave 6 sub-tests pass.
- ✓ Whole-repo non-live suite: 301 passed / 2 skipped / 3 deselected.
- ✓ D-18 guard still passes: `src/routing/tests/test_decide_smoke.py` 7 passed.

**Phase 3 complete.** Ready for `gsd-verify-work`.
