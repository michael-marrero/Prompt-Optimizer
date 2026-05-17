---
phase: "03"
plan: "03"
subsystem: "fastapi-service-persistent-storage / thread CRUD + settings"
tags: [fastapi, thread-crud, settings, json-merge-patch, byok, masked-keys, atomic-write, adapter-cache, async, D-09, D-10, D-11, D-13, D-15, D-19, API-03, SECURE-04]
requires:
  - phase: "03-00"
    provides: "apps.api.paths.{DB_PATH,SETTINGS_PATH}, apps/api/tests/conftest.py:{app_factory,asgi_client,aiosqlite_inmemory_db} fixtures, httpx-sse / fastapi / aiosqlite deps"
  - phase: "03-01"
    provides: "apps.api.db.queries.{create_thread,get_thread,list_threads,update_thread_title,delete_thread} (parameterised async query functions; ON DELETE CASCADE via FK + PRAGMA), apps.api.db.models.Thread (frozen Pydantic v2)"
  - phase: "03-02"
    provides: "apps.api.main.create_app() — factory with CORS + lifespan + health router; apps.api.lifespan — populates app.state.{db,artifacts,settings,keystore,adapters,schema_version}; apps.api.settings.{load_settings_file,write_settings_file,_default_settings}; apps.api.routes.health.router"
  - phase: "02"
    provides: "apps.api.backends.keystore.KeyStore — in-memory primary + env fallback + optional keyring; apps/api/__init__.py — load_dotenv + install_redaction_filter at import (SECURE-01); apps.api.backends.logging_filter.RedactionFilter — sk-…/sk-ant-…/Bearer rewrite rules"
provides:
  - "apps.api.routes.threads.router — APIRouter(prefix='/api/v1', tags=['threads']); POST/GET/PATCH/DELETE /threads(/{id}) per API-03 + D-09"
  - "apps.api.routes.threads.{ThreadCreateRequest,ThreadUpdateRequest,ThreadListResponse} — Pydantic v2 request/response models"
  - "apps.api.routes.settings.router — APIRouter(prefix='/api/v1', tags=['settings']); GET /settings (masked) + PATCH /settings (JSON Merge Patch) per D-10 + D-11 + D-15"
  - "apps.api.routes.settings.{KeyPatch,SettingsPatch} — Pydantic v2 patch models with model_config=ConfigDict(extra='forbid') (422 on unknown fields)"
  - "apps.api.routes.settings._mask_key(key) — masked rendering of a key for safe display (sk-or-…ABC form)"
  - "apps.api.routes.settings._mask_settings_for_response(settings, keystore) — canonical GET-shape dict with keys ALWAYS masked"
  - "apps/api/main.py extended — create_app() now mounts threads.router + settings.router alongside health.router"
  - "apps/api/tests/test_threads_crud.py — 9 passing async tests covering POST happy/422, GET list (DESC), GET single + 404, PATCH happy + 404, DELETE 204 + 404"
  - "apps/api/tests/test_settings.py — 8 passing async tests covering GET masking, PATCH adds/round-trip/null-deletes/cache-invalidation/atomic-write/422-unknown/no-plaintext-in-logs"
affects:
  - "Phase 3 Wave 4 (turn SSE) — POST /threads/{id}/turn will read request.app.state.adapters (empty after every settings PATCH per D-15) and lazy-build adapters against the fresh KeyStore"
  - "Phase 3 Wave 5 (blob cascade) — EXTENDS apps.api.routes.threads.delete_single_thread with a pre-step that walks messages.content_blocks JSON to unlink blob files BEFORE the DB delete fires (D-14); current handler ships the minimal DB-only path"
  - "Phase 3 Wave 6 (rename + canonical SECURE-04 regression) — apps/api/tests/test_secure_no_key_in_logs.py is the canonical 4-test disclosure regression for API-04; the partial pre-wire in Wave 3 (test_patch_settings_does_not_log_plaintext_keys) is the first of the four"
  - "Phase 4 (UI proxy) — Next.js dev server consumes /api/v1/threads + /api/v1/settings over CORS (Wave 2 default http://localhost:3000 allowlist already in place)"
  - "Phase 5 (UI-02 sidebar) — POST/GET/PATCH/DELETE /api/v1/threads is the gate that lets the sidebar render real persistent threads instead of a stub"
  - "Phase 5 (UI-12 settings panel) — GET/PATCH /api/v1/settings is the API surface the settings drawer reads + writes; D-15 cache invalidation ensures the next turn rebuilds adapters with the new keys"
tech-stack:
  added:
    - "(none — fastapi/pydantic/aiosqlite/httpx-sse already landed in Wave 0; this plan only adds two new route modules + two new test modules)"
  patterns:
    - "Pydantic v2 JSON Merge Patch via body.model_dump(exclude_unset=True) — differentiates 'field omitted from request' from 'field set to None'; the canonical primitive for partial-update PATCH handlers"
    - "Pitfall 7 (RESEARCH lines 952-957) None-as-delete semantics on KeyPatch — explicit `null` on a provider field deletes the key from KeyStore._memory; field omission leaves the key untouched"
    - "D-10 SECURE-04 boundary — plaintext keys are write-only on the wire: PATCH request carries them; PATCH response NEVER does; GET response ALWAYS masks to sk-or-…ABC form"
    - "D-11 atomic settings.json write — write_settings_file delegates to the existing Wave 2 tmp.write_text + tmp.replace(target) atomic pattern; keys NEVER touch the file"
    - "D-15 lazy adapter cache invalidation — app.state.adapters.clear() runs AFTER the file is rewritten and BEFORE the response returns; next turn rebuilds against the fresh KeyStore"
    - "model_config = ConfigDict(extra='forbid') on KeyPatch + SettingsPatch — typo'd top-level fields ({'unknown_field': 42}) and typo'd provider slots ({'keys': {'openroter': '...'}}) raise 422 instead of silently landing"
    - "D-19 logging contract — handler uses logger = logging.getLogger(__name__) so the Phase 2 RedactionFilter installed at apps/api/__init__.py import time applies; NEVER print(...), NEVER log body content"
    - "FastAPI APIRouter(prefix='/api/v1', tags=['...']) — matches Wave 2 health router shape exactly so all Phase 3 routes share the canonical /api/v1 prefix per D-09"
    - "204 No Content via return Response(status_code=204) — empty-body delete return; the @router.delete decorator gets status_code=204 so the auto-generated OpenAPI spec carries it"
    - "ISO 8601 Z-suffixed timestamp ordering — string-compare on created_at/updated_at is reliable for UTC chronology so the GET DESC ordering test asserts threads[0].created_at >= threads[1].created_at"
    - "Test reload chain extension — test_settings.py::_fresh_app reloads apps.api.settings AND apps.api.routes.settings AFTER apps.api.paths so the cached SETTINGS_PATH constants pick up tmp_path; without this chain, write_settings_file would target the user's REAL ~/.prompt-optimizer/settings.json"
    - "Lifespan-context manual trigger via app.router.lifespan_context(app) — carry-forward from Wave 2 (ASGITransport does NOT auto-trigger lifespan); every test wraps the AsyncClient in this context"
key-files:
  created:
    - "apps/api/routes/threads.py"
    - "apps/api/routes/settings.py"
    - "apps/api/tests/test_threads_crud.py"
    - "apps/api/tests/test_settings.py"
  modified:
    - "apps/api/main.py — create_app() now mounts threads.router + settings.router alongside health.router (3-line import change + 2-line include_router calls)"
key-decisions:
  - "Wave 3 mounts BOTH threads.router and settings.router inside create_app() — single mount-list edit per Wave 2's factory pattern; routes imported INSIDE the factory (not at module top) to keep circular-import surface area at zero"
  - "_mask_key returns sk-or-…ABC form (first 6 chars + ellipsis + last 3) for keys longer than 6 chars; very short keys (<=6) drop the prefix entirely so we can never accidentally show 100% of a short malformed key — defense in depth"
  - "_mask_settings_for_response iterates the CLOSED provider set ('openrouter', 'anthropic') so a typo'd provider slot in KeyStore never leaks into the GET response — even if a future contributor adds a new provider to KeyStore without updating the response shape"
  - "PATCH handler deletes keys via app.state.keystore._memory.pop(provider, None) rather than KeyStore.set(provider, None) — the public set() type-signature is str, so setting None would be a type-invalid cache entry; popping is the explicit deletion path that mirrors Phase 2's KeyStore.get fallback chain (in-memory → keyring → env)"
  - "Adapter cache invalidation runs AFTER write_settings_file and BEFORE the masked response builds — if write_settings_file raises, the adapters cache stays intact (partial state never lands); if cache.clear() raises (impossible — dict.clear is infallible) the file write has already committed atomically"
  - "test_settings.py::_fresh_app extends the Wave 2 reload chain to also reload apps.api.settings + apps.api.routes.settings — discovered during Test 6 runtime when write_settings_file targeted the user's real home; the additional reload propagates the fresh SETTINGS_PATH through the dependency graph"
  - "Wave 3 partial pre-wire of SECURE-04 (test_patch_settings_does_not_log_plaintext_keys) — Wave 6 ships the canonical 4-test test_secure_no_key_in_logs.py; this partial confirms the handler emits records and that the plaintext is never present in caplog.text"
patterns-established:
  - "Pydantic v2 JSON Merge Patch via model_dump(exclude_unset=True) + extra='forbid'"
  - "Pitfall 7 None-as-delete on keyed sub-dicts (KeyPatch)"
  - "Closed provider set iteration in masked-response builders"
  - "D-15 cache invalidation after atomic file write + before response build"
  - "Extended importlib.reload chain for module-cached path constants (paths → settings → routes.settings → lifespan → main)"
  - "Manual lifespan-context trigger carried forward from Wave 2"
requirements-completed: [API-03]

duration: 38m
completed: 2026-05-17
---

# Phase 03 Plan 03: Wave 3 Thread CRUD + Settings Summary

**Wave 3 of Phase 3 — author the thread CRUD endpoints (`POST/GET/PATCH/DELETE /api/v1/threads(/{id})`) and the settings endpoints (`GET /api/v1/settings` masked + `PATCH /api/v1/settings` JSON Merge Patch). Pydantic v2 `model_dump(exclude_unset=True)` is the canonical differentiator between "field omitted" and "field is None" — explicit `null` on a key field DELETES the key from KeyStore (Pitfall 7). Non-key settings flow through the existing atomic `write_settings_file` (Wave 2 D-11). `app.state.adapters.clear()` runs on every successful PATCH so the next turn rebuilds adapters against the fresh KeyStore (D-15). Plaintext keys are write-only on the wire (D-10 / SECURE-04): the PATCH request carries them; the PATCH response NEVER does; the GET response ALWAYS masks to `sk-or-…ABC` form.**

## Performance

- **Duration:** ~38 min (wall clock)
- **Tasks:** 3 (all `type=auto`, `tdd=true`)
- **Files created:** 4 (2 source + 2 tests)
- **Files modified:** 1 (`apps/api/main.py` — extend `create_app()` with two new `include_router` calls + one new import)
- **Lines added:** 1,409 (source 528: threads 211 + settings 317; tests 881: threads 380 + settings 501)
- **Tests added:** 17 passing (9 in `test_threads_crud`, 8 in `test_settings`)
- **Whole-repo non-live suite after Wave 3:** 267 passed / 2 skipped / 3 deselected (+17 new tests vs Wave 2's 250)
- **Phase 1 D-18 import-graph guard:** still green (7/7 in `src/routing/tests/test_decide_smoke.py`)

## Accomplishments

- **API-03 satisfied:** `apps/api/routes/threads.py` ships the 5-endpoint thread CRUD surface (`POST`, `GET` list, `GET` single, `PATCH`, `DELETE`). Every endpoint delegates to `apps.api.db.queries.*` async functions — NO raw SQL in route handlers (T-03-SQLi mitigated by the negative grep). `DELETE` returns 204 with an empty body; cascade to `messages` + `routing_decisions` rows fires via the FK `ON DELETE CASCADE` (D-13) plus `PRAGMA foreign_keys=ON` (D-03).
- **D-09 satisfied:** Both new routers use `APIRouter(prefix="/api/v1", tags=[...])` so every Phase 3 endpoint shares the canonical `/api/v1` namespace.
- **D-10 satisfied (masked GET + plaintext PATCH):** `GET /api/v1/settings` ALWAYS returns the masked form `{"present": bool, "masked": "sk-or-…ABC"}`. `PATCH /api/v1/settings` accepts plaintext keys on the wire; the response NEVER includes them. The 8 settings tests confirm the boundary at both the `_mask_settings_for_response` helper level AND the full HTTP round-trip level.
- **D-11 satisfied (atomic settings.json):** Non-key fields flow through `apps.api.settings.write_settings_file` (Wave 2's `tmp.write_text + tmp.replace(target)` pattern). Keys NEVER touch the file. `test_patch_settings_writes_non_key_settings_atomically` asserts `backends_enabled` round-trips through the file and that `"keys"` is absent from the on-disk JSON.
- **D-15 satisfied (lazy adapter cache invalidation):** `request.app.state.adapters.clear()` runs AFTER the file write and BEFORE the response build. `test_patch_settings_invalidates_adapter_cache` pre-populates the registry with a sentinel and asserts `app.state.adapters == {}` after the PATCH returns. The next turn rebuilds every adapter against the fresh KeyStore.
- **D-19 satisfied (logger; never print):** Both route handlers use `logger = logging.getLogger(__name__)` so the Phase 2 `RedactionFilter` (installed at `apps/api/__init__.py` import time) applies to every record. The PATCH handler emits exactly one INFO record describing the EFFECT (`"settings updated; adapter cache cleared"`) and NEVER the input — `test_patch_settings_does_not_log_plaintext_keys` confirms the plaintext is absent from `caplog.text` after a PATCH that sets a key.
- **Pitfall 7 satisfied (None-as-delete):** The PATCH handler iterates `patch["keys"].items()` and treats explicit `None` as deletion (via `_memory.pop(provider, None)`); concrete values land via `KeyStore.set(provider, key)`. `test_patch_settings_null_deletes_key` confirms the deletion (with `OPENROUTER_API_KEY` env unset so the env-fallback in `KeyStore.get` cannot mask the deletion).
- **extra="forbid" satisfied:** Both `KeyPatch` and `SettingsPatch` set `model_config = ConfigDict(extra="forbid")`. Unknown top-level fields (`{"unknown_top_level_field": 42}`) and unknown provider slots (`{"keys": {"openroter": "..."}}`) raise 422 instead of silently landing. `test_patch_settings_rejects_unknown_keys` enforces.
- **API-08 / D-20 satisfied:** Both test files use `httpx.AsyncClient + ASGITransport` with manual `app.router.lifespan_context(app)` triggering. No `TestClient` import anywhere. The CI negative-grep in `test_smoke.py` stays green.
- **Phase 2 + Phase 3 Waves 0-2 carry-forward:** Whole-repo non-live suite passes (`uv run pytest -m 'not live' -x`) with 267 passes vs Wave 2's 250 (+17 new tests, zero regressions).
- **Phase 1 D-18 import-graph guard:** `src/routing/tests/test_decide_smoke.py` still passes 7/7. The new route modules import from `apps.api.db.queries` (Wave 1) and `apps.api.settings` (Wave 2) only — direction stays `apps.api → src.routing → src.demo`, never the reverse.

## Task Commits

Each task was committed atomically.

1. **Task 1: `apps/api/routes/threads.py` + mount in `create_app()`** — `6c2a772` (feat)
2. **Task 2: `apps/api/routes/settings.py` + mount in `create_app()`** — `2a9b2c0` (feat)
3. **Task 3: `test_threads_crud.py` + `test_settings.py` (17 passing tests)** — `cd49a57` (test)

**Plan metadata commit:** to be authored after this SUMMARY lands.

## Files Created/Modified

### Created (4)

- `apps/api/routes/threads.py` (211 LOC) — 5 endpoints: `POST /threads` (`ThreadCreateRequest` body), `GET /threads` (`ThreadListResponse` envelope), `GET /threads/{thread_id}`, `PATCH /threads/{thread_id}` (no-op when body omits title; FastAPI auto-422 for invalid types), `DELETE /threads/{thread_id}` (status_code=204, empty body). All delegate to `apps.api.db.queries.*` — NO raw SQL in route handlers.
- `apps/api/routes/settings.py` (317 LOC) — 2 endpoints: `GET /settings` (returns the masked shape), `PATCH /settings` (Pydantic v2 JSON Merge Patch via `model_dump(exclude_unset=True)`). Internal helpers: `_mask_key` (sk-…ABC form), `_mask_settings_for_response` (canonical GET-shape dict). `KeyPatch` + `SettingsPatch` Pydantic models with `model_config = ConfigDict(extra="forbid")`. `logger = logging.getLogger(__name__)` so the Phase 2 RedactionFilter applies.
- `apps/api/tests/test_threads_crud.py` (380 LOC) — 9 async tests covering POST happy + 422, GET list (DESC), GET single + 404, PATCH happy (`updated_at > created_at`) + 404, DELETE 204 + 404. Uses the `_fresh_app` helper lifted from `test_health.py` (Wave 2).
- `apps/api/tests/test_settings.py` (501 LOC) — 8 async tests covering GET masking, PATCH adds key + round-trips masked, PATCH null deletes (Pitfall 7), PATCH invalidates adapter cache (D-15), PATCH atomic file write (D-11), PATCH rejects unknown field (422), PATCH does not log plaintext (D-19 partial pre-wire for Wave 6 canonical regression). Extended `_fresh_app` reload chain reloads `apps.api.settings` + `apps.api.routes.settings` so `SETTINGS_PATH` picks up `tmp_path`.

### Modified (1)

- `apps/api/main.py` — 3-line change inside `create_app()`: added `settings` and `threads` to the `from apps.api.routes import ...` line and added two `app.include_router(...)` calls. Comment block updated to reflect the new Wave 3 mount surface.

## Decisions Made

- **Wave 3 mounts BOTH threads.router and settings.router inside `create_app()`:** A single mount-list edit per Wave 2's factory pattern. Routes imported INSIDE the factory (not at module top) to keep the circular-import surface area at zero — Wave 4's `turn` router and Wave 6's `rename` router will follow the same pattern.
- **`_mask_key` returns `<first6>…<last3>` for keys longer than 6 chars:** Keeps the leading provider prefix visible so the user can verify which key is installed; hides the body. Very short keys (`len <= 6`) lose the prefix entirely so we can never accidentally show 100% of a short malformed key — defense in depth.
- **`_mask_settings_for_response` iterates the CLOSED provider set `("openrouter", "anthropic")`:** Avoids leaking a typo'd provider slot in KeyStore into the GET response. Even if a future contributor adds a new provider to KeyStore without updating the response shape, the GET response stays clean.
- **PATCH handler deletes keys via `app.state.keystore._memory.pop(provider, None)` rather than `KeyStore.set(provider, None)`:** The public `set` signature is `str`, so setting `None` would be a type-invalid cache entry. Popping the in-memory cache directly is the explicit deletion path that mirrors Phase 2's `KeyStore.get` fallback chain (in-memory → keyring → env). Documented inline with a Pitfall 7 reference.
- **Adapter cache invalidation runs AFTER `write_settings_file` and BEFORE the masked response builds (D-15):** If `write_settings_file` raises, the adapters cache stays intact (partial state never lands). If `dict.clear()` ever raised (it cannot — infallible), the file write has already committed atomically. The ordering is the explicit consistency boundary.
- **`test_settings.py::_fresh_app` extends the Wave 2 reload chain:** Discovered during Test 6 runtime when `write_settings_file` targeted the user's real home directory because `apps.api.settings.SETTINGS_PATH` was cached at the original module-load time. The fix reloads `apps.api.settings` + `apps.api.routes.settings` AFTER `apps.api.paths` so the dependency graph picks up the fresh `tmp_path`. Documented in the helper's docstring as Pitfall 2 (stale module constants survive `importlib.reload` on a sibling module).
- **Wave 3 partial pre-wire of SECURE-04:** `test_patch_settings_does_not_log_plaintext_keys` is the first of the four canonical disclosure-regression checks Wave 6 will ship in `test_secure_no_key_in_logs.py`. Wave 3 confirms the handler emits records AND that the plaintext is absent from `caplog.text`; Wave 6 adds three more checks (env-redaction, error-stack redaction, full body redaction).
- **`updated_at > created_at` via string compare:** ISO 8601 `Z`-suffixed timestamps sort lexicographically per UTC chronology — `"2026-05-17T01:23:45.123Z" > "2026-05-17T01:23:45.122Z"` evaluates correctly. No `datetime.fromisoformat` parsing needed in the test.

## Deviations from Plan

### None

Every task executed exactly as planned. No Rule 1 bugs, no Rule 2 missing-functionality additions, no Rule 4 architectural questions.

One Rule 3 in-flight fix landed inside Task 3 (test reload chain extension), documented as an explicit Pitfall 2 finding in the test helper's docstring:

1. **[Rule 3 — Blocking issue] Extended `test_settings.py::_fresh_app` reload chain to also reload `apps.api.settings` + `apps.api.routes.settings`:**
   - **Found during:** Task 3 — Test 6 (`test_patch_settings_writes_non_key_settings_atomically`).
   - **Issue:** The Wave 2 `_fresh_app` reload chain reloaded `apps.api.paths` + `apps.api.lifespan` + `apps.api.main`, but `apps.api.settings.SETTINGS_PATH` was imported at module-top time and survived the sibling reload. As a result, `write_settings_file` targeted the user's REAL `~/.prompt-optimizer/settings.json` instead of `tmp_path/settings.json` — the test then failed at `(tmp_path / "settings.json").read_text(...)` with a `FileNotFoundError`.
   - **Fix:** Added two `importlib.reload(...)` calls (`apps.api.settings`, `apps.api.routes.settings`) between the `apps.api.paths` reload and the `apps.api.lifespan` reload. Documented the reload-chain-order rationale in the helper's docstring as a Pitfall 2 carry-forward.
   - **Files modified:** `apps/api/tests/test_settings.py` (helper docstring + body).
   - **Commit:** `cd49a57` (folded into the Task 3 test-files commit so the fix lands with the tests it enables).

**Total deviations:** 1 Rule 3 blocking-issue fix (test-helper reload chain).
**Impact on plan:** None — all 17 sub-tests pass, all 12 Wave 3 truths verify, all 7 acceptance criteria for Task 3 pass.

## Issues Encountered

The reload-chain bug surfaced AFTER Tests 1-5 passed (which exercised only the in-memory KeyStore + the adapter cache, neither of which touches `SETTINGS_PATH`). Test 6 was the first one to write `settings.json` through the route handler — the failure was loud and obvious (`FileNotFoundError` at the test assertion) so the fix landed in <2 minutes once the cause was identified.

The Phase 1 + Phase 2 D-18 import-graph guard stayed green throughout. The Phase 2 redaction filter applies to the new settings handler automatically because the handler uses `logger = logging.getLogger(__name__)` (no manual filter installation needed; the filter is at the root logger + record factory level per Phase 2 Plan 00).

## User Setup Required

None. No external services or environment configuration. The thread CRUD operates against the SQLite DB the Wave 2 lifespan opens at `~/.prompt-optimizer/chat.db` (or `tmp_path/chat.db` during tests). The settings PATCH writes to `~/.prompt-optimizer/settings.json` (or `tmp_path/settings.json` during tests). BYOK keys flow through `KeyStore` in-memory by default; the optional `keyring` extra (Phase 2 D-10) is not required by Wave 3.

## Next Phase Readiness

- **Wave 4 (turn SSE):** Ready to lazy-build adapters into `app.state.adapters` on first turn. Wave 3's PATCH handler is the only writer that clears the cache (`app.state.adapters.clear()`), so Wave 4 only needs to populate the registry — never invalidate it.
- **Wave 5 (blob cascade):** Will EXTEND `apps.api.routes.threads.delete_single_thread` with a pre-step that walks `messages.content_blocks` JSON to unlink referenced blob files BEFORE the DB delete fires. The current handler ships the minimal DB-only path; the FK + pragma cascade is sufficient for v1 without blobs.
- **Wave 6 (rename + canonical SECURE-04 regression):** Will ship `apps/api/tests/test_secure_no_key_in_logs.py` with the full 4-test disclosure regression for API-04. Wave 3's `test_patch_settings_does_not_log_plaintext_keys` is the first of those four. The rename endpoint (POST `/threads/{id}/rename`) constructs a fresh `OpenRouterAdapter` (single-use, NOT cached) per D-17 — independent of the Wave 4 lazy adapter cache.
- **Phase 4 (UI proxy):** Next.js dev server reads `/api/v1/threads` + `/api/v1/settings` over CORS. The Wave 2 default `http://localhost:3000` allowlist + `Last-Event-ID` allow-header pre-wire Phase 4's SSE proxy.
- **Phase 5 (UI-02 sidebar):** Reads/writes `/api/v1/threads` to render persistent threads.
- **Phase 5 (UI-12 settings panel):** Reads `/api/v1/settings` to render the BYOK key state (present / masked); writes `/api/v1/settings` to update keys + backends-enabled toggles + cost cap. D-15 cache invalidation ensures the next turn rebuilds adapters with the fresh keys.

No blockers. No concerns.

## All 12 Wave 3 Truths Verified

```
Truth 1  OK: no sys.path.append in any Phase 3 source file
Truth 2  OK: apps.api.* imports trigger dotenv.load_dotenv() + install_redaction_filter() via apps/api/__init__.py; no module re-installs the filter
Truth 3  OK: POST /api/v1/threads with {"title": "T1"} returns 200 with id/title/created_at/updated_at; row lands in threads table
Truth 4  OK: GET /api/v1/threads returns {"threads": [...]} ordered by created_at DESC
Truth 5  OK: GET /api/v1/threads/{id} returns 200 with the thread + 404 for unknown id
Truth 6  OK: PATCH /api/v1/threads/{id} {"title": "New"} returns 200 with updated_at > created_at
Truth 7  OK: DELETE /api/v1/threads/{id} returns 204 No Content + 404 for unknown; FK CASCADE unlinks child rows
Truth 8  OK: GET /api/v1/settings returns masked shape; plaintext NEVER on the wire (sk-or-…ABC form)
Truth 9  OK: PATCH /api/v1/settings {"keys": {"openrouter": "sk-or-v1-..."}} returns 200; KeyStore.get returns plaintext; settings.json does NOT contain plaintext
Truth 10 OK: PATCH /api/v1/settings {"keys": {"openrouter": null}} deletes the key from KeyStore (Pitfall 7)
Truth 11 OK: PATCH /api/v1/settings invalidates app.state.adapters AFTER the file is rewritten and BEFORE the response returns (D-15)
Truth 12 OK: `uv run pytest apps/api/tests/test_threads_crud.py apps/api/tests/test_settings.py -x` exits 0 (17/17 — POST happy/422, GET list/single/404, PATCH happy/404, DELETE 204/404, GET masks, PATCH adds/round-trips/null-deletes/invalidates-cache/atomic-write/422-unknown/no-plaintext)
```

## Self-Check: PASSED

- All 4 files referenced in `key-files.created` exist on disk:
  - `apps/api/routes/threads.py` — 211 LOC
  - `apps/api/routes/settings.py` — 317 LOC
  - `apps/api/tests/test_threads_crud.py` — 380 LOC
  - `apps/api/tests/test_settings.py` — 501 LOC
- The 1 file in `key-files.modified` exists and includes the new mount calls:
  - `apps/api/main.py` — `grep -c "include_router" apps/api/main.py` returns 3 (health + threads + settings)
- All 3 task commits referenced above are present in `git log --oneline`:
  - `6c2a772` — feat(03-03): add apps/api/routes/threads.py + mount in create_app
  - `2a9b2c0` — feat(03-03): add apps/api/routes/settings.py — GET masked + PATCH merge-patch
  - `cd49a57` — test(03-03): add test_threads_crud.py + test_settings.py (17 passing)
- The plan-metadata commit follows this SUMMARY landing on disk.

---

*Phase: 03-fastapi-service-persistent-storage*
*Plan: 03 (Wave 3 — thread CRUD + settings)*
*Completed: 2026-05-17*
