---
phase: "03"
plan: "02"
subsystem: "fastapi-service-persistent-storage / app shell + healthz"
tags: [fastapi, lifespan, cors, healthz, sse-preflight, async, D-15, D-18, D-12, OSS-05, API-01]
requires:
  - phase: "03-00"
    provides: "apps.api.paths.{DB_PATH,SETTINGS_PATH}, apps/api/tests/conftest.py:{app_factory,asgi_client,aiosqlite_inmemory_db} fixtures, sse-starlette / fastapi / uvicorn / aiosqlite / httpx-sse deps"
  - phase: "03-01"
    provides: "apps.api.db.connect.open_db (four-pragma prefix), apps.api.db.migrate.up_to_latest, apps.api.db.queries.read_schema_version (cached at lifespan)"
  - phase: "01"
    provides: "src.routing.decide._load_default_artifacts — canonical 4-key dict {task_type_classifier, agentic_intent_classifier, model_router, model_mapping} (Phase 1 D-04)"
  - phase: "02"
    provides: "apps.api.backends.keystore.KeyStore — in-memory primary + env-fallback; apps/api/__init__.py — load_dotenv + install_redaction_filter at import (D-11 + SECURE-01)"
provides:
  - "apps.api.settings._default_settings() — canonical settings shape (backends_enabled, computer_use_opt_in=False, default_max_cost_usd=0.50)"
  - "apps.api.settings.load_settings_file() — reads SETTINGS_PATH; returns defaults on first boot"
  - "apps.api.settings.write_settings_file(settings) — atomic tmp.write_text + tmp.replace(target) per RESEARCH Example 5"
  - "apps.api.settings.computer_use_enabled(settings) — D-12 STRICT AND-semantics (env literal `1` AND settings flag True)"
  - "apps.api.lifespan.lifespan — @asynccontextmanager; D-15 + discretion line 178 order: open DB → migrate → load 4-key artifacts → load settings → KeyStore → app.state.adapters = {} → cache schema_version; defensive finally close"
  - "apps.api.main.create_app() — FastAPI factory; mounts CORSMiddleware (OSS-05 explicit allowlist) + lifespan + health.router"
  - "apps.api.main.app — module-level binding for `uvicorn apps.api.main:app`"
  - "apps.api.routes.health.router — APIRouter(prefix='/api/v1', tags=['health']); GET /api/v1/healthz returns the D-18 rich payload"
  - "apps.api.routes.health.AdapterStatus — Literal['ready','missing_key','opt_out','error'] closed vocabulary"
  - "apps/api/tests/test_health.py — 5 passing tests covering API-01 / STORE-01 carry-forward / D-18"
  - "apps/api/tests/test_cors.py — 3 passing tests covering OSS-05 default + env override + evil-origin rejection"
affects:
  - "Phase 3 Wave 3 (thread CRUD) — POST/GET/PATCH/DELETE /api/v1/threads route handlers register via app.include_router; will mount inside create_app() alongside health.router"
  - "Phase 3 Wave 4 (turn SSE) — reads request.app.state.{db, artifacts, settings, keystore, adapters} populated by this lifespan; lazy-builds adapters on first turn into app.state.adapters[backend]"
  - "Phase 3 Wave 6 (settings PATCH) — PATCH /api/v1/settings will call write_settings_file (atomic) + clear app.state.adapters per D-15"
  - "Phase 3 Wave 6 (rename) — rename endpoint constructs a fresh OpenRouterAdapter (single-use) bypassing the cache"
  - "Phase 4 (UI proxy) — consumes /api/v1/healthz over CORS; the http://localhost:3000 default + Last-Event-ID allow header pre-wire Phase 4's SSE proxy"
  - "Phase 5 (UI-11 status dot strip) — polls /api/v1/healthz and renders per-adapter status dots using the AdapterStatus closed vocabulary"
tech-stack:
  added:
    - "(none — fastapi/uvicorn/sse-starlette/aiosqlite/httpx-sse already landed in Wave 0)"
  patterns:
    - "@asynccontextmanager async def lifespan(app: FastAPI) — D-15 + discretion line 178 startup order; replaces the legacy @app.on_event(\"startup\")/\"shutdown\" API deprecated since FastAPI 0.95.0"
    - "EMPTY app.state.adapters at startup + lazy build at first turn (D-15) — keeps server bootable when ANTHROPIC_API_KEY / COMPUTER_USE_OPT_IN are unset"
    - "CORSMiddleware with OSS-05 explicit allowlist (default http://localhost:3000; env override via PROMPT_OPTIMIZER_CORS_ORIGINS comma-separated); NEVER ['*'] (allow_credentials=True + wildcard is browser-rejected)"
    - "D-12 STRICT AND-semantics for computer-use enable (env literal `1` AND in-app settings toggle True) — Phase 2 single-gate adapter check is EXTENDED, not replaced"
    - "Atomic settings.json write via tmp = path.with_suffix(suffix + '.tmp'); tmp.write_text(...); tmp.replace(target) — POSIX + Windows atomic-rename within same filesystem"
    - "D-18 read-only healthz precheck — KeyStore.get + computer_use_enabled() consult ONLY; NEVER constructs an adapter so polling is fast and side-effect-free"
    - "Closed-vocabulary AdapterStatus = Literal['ready','missing_key','opt_out','error'] mirrors Phase 1 Backend / Phase 2 StreamError.code patterns"
    - "B3 lazy-override pattern (CONTEXT carry-forward) — lifespan honours pre-set app.state.{adapters,settings,keystore} via getattr(_SENTINEL) guard so the conftest app_factory can inject fakes without re-implementing the lifespan"
    - "Defensive finally close — try/except on app.state.db.close() (aiosqlite raises on double-close; the cancellation contract only needs the close to be attempted)"
    - "Manual lifespan trigger in tests via app.router.lifespan_context(app) — httpx.AsyncClient + ASGITransport does NOT auto-trigger lifespan (known caveat); the built-in FastAPI router exposes the context manager so we avoid adding asgi-lifespan as a new dep"
    - "importlib.reload(apps.api.{paths,lifespan,main}) per test for PROMPT_OPTIMIZER_HOME tmp-dir override + PROMPT_OPTIMIZER_CORS_ORIGINS env-override"
key-files:
  created:
    - "apps/api/settings.py"
    - "apps/api/lifespan.py"
    - "apps/api/main.py"
    - "apps/api/routes/__init__.py"
    - "apps/api/routes/health.py"
    - "apps/api/tests/test_health.py"
    - "apps/api/tests/test_cors.py"
  modified: []
key-decisions:
  - "RESEARCH Open Question 3 resolved (single shared aiosqlite.Connection at app.state.db) — locked in lifespan; serialises writes via the connection's worker thread; saves re-running pragmas per request"
  - "RESEARCH Open Question 5 resolved (cache schema_version at startup) — app.state.schema_version is set once in step 7 of the lifespan and read straight from app.state in /healthz; the /healthz endpoint never re-queries SQLite for the version"
  - "Lifespan artifact loader = src.routing.decide._load_default_artifacts (NOT src.demo.demo_router.load_joblib_artifacts) — the former returns the canonical 4-key dict {task_type_classifier, agentic_intent_classifier, model_router, model_mapping} that decide() consumes; the latter is the wrong shape (single-artifact loader)"
  - "Routes imported INSIDE create_app() rather than at apps/api/main.py module top — avoids circular-import surface area if a future route ever pulls from apps.api.main; matches FastAPI best practice for factory-based app construction"
  - "Lifespan honours conftest app_factory's pre-set app.state.{adapters,settings,keystore} via _SENTINEL guard — overriding the lifespan body would force every test to bypass the production code path; honouring the override keeps the same code path for tests AND production"
  - "Test-side: ASGITransport does NOT auto-trigger lifespan, so each test wraps the AsyncClient in `async with app.router.lifespan_context(app)`. Built-in to FastAPI; no new dep (asgi-lifespan would have worked but isn't installed)"
  - "Test-side: PROMPT_OPTIMIZER_HOME=tmp_path + importlib.reload(apps.api.paths) re-routes DB_PATH per test; the same reload chain handles PROMPT_OPTIMIZER_CORS_ORIGINS for the CORS env-override test"
patterns-established:
  - "FastAPI lifespan with D-15 + discretion line 178 ordering"
  - "OSS-05 explicit-origin CORS allowlist with env override (NEVER wildcard)"
  - "D-12 STRICT AND-semantics for security opt-ins"
  - "D-18 read-only adapter status precheck (closed Literal vocabulary)"
  - "Atomic JSON-file write via tmp.write_text + tmp.replace"
  - "B3 lazy app.state override pattern (test overrides land before lifespan runs)"
  - "Manual lifespan-trigger in async tests via app.router.lifespan_context"
  - "importlib.reload chain (paths → lifespan → main) for env-override tests"
requirements-completed: [API-01, OSS-05]

duration: 1h 9m
completed: 2026-05-17
---

# Phase 03 Plan 02: Wave 2 App Shell + Healthz Summary

**FastAPI app shell — lifespan that opens the DB, runs migrations, loads the Phase 1 4-key joblib artifact dict, instantiates KeyStore, sets an EMPTY adapter registry (lazy-build on first turn per D-15), and caches schema_version. CORSMiddleware with OSS-05 explicit allowlist (default http://localhost:3000; env override). GET /api/v1/healthz returns the D-18 rich payload with per-backend AdapterStatus dots — strictly read-only (never constructs an adapter). D-12 STRICT AND-semantics for computer-use opt-in (env literal `1` AND in-app settings flag).**

## Performance

- **Duration:** ~1 h 9 m (wall clock)
- **Tasks:** 3 (all `type=auto`, `tdd=true`)
- **Files created:** 7 (5 source + 2 tests)
- **Files modified:** 0
- **Lines added:** 1,217 (source 676 + tests 541)
- **Tests added:** 8 passing (5 in test_health, 3 in test_cors)
- **Cold app import time:** ~1.23 s (well under the 3 s SC budget)

## Accomplishments

- **API-01 satisfied:** `apps/api/lifespan.py` loads Phase 1 joblib artifacts ONCE at startup via `src.routing.decide._load_default_artifacts`; subsequent requests reuse `app.state.artifacts`. The `test_artifacts_loaded_once` test asserts the counter is 1 after two GETs to `/api/v1/healthz`.
- **OSS-05 satisfied:** `apps/api/main.py` mounts CORSMiddleware with `allow_origins=[default 'http://localhost:3000']` and `PROMPT_OPTIMIZER_CORS_ORIGINS` env override (comma-separated). NEVER `['*']` (the negative-grep guard in acceptance criteria + the runtime test `test_cors_preflight_rejected_for_evil` enforce). With `allow_credentials=True`, wildcard is browser-rejected anyway.
- **D-15 satisfied:** `app.state.adapters = {}` at lifespan startup; lazy-build at first turn lands in Wave 4. The conftest's `app_factory` fixture can pre-populate this dict to inject fake adapters; the lifespan honours the override via the `_SENTINEL` guard.
- **D-18 satisfied:** `/api/v1/healthz` returns the rich payload `{status, artifacts_loaded, db_ok, schema_version, adapters{openrouter,claude_code,computer_use}, version}` with the `AdapterStatus = Literal["ready","missing_key","opt_out","error"]` closed vocabulary. **Read-only precheck** — the `test_healthz_never_constructs_adapters` test monkeypatches every adapter `__init__` to raise and confirms healthz still returns 200.
- **D-12 satisfied:** `apps.api.settings.computer_use_enabled(settings)` returns True ONLY when `os.environ.get("COMPUTER_USE_OPT_IN") == "1"` AND `settings["computer_use_opt_in"] is True`. Both gates required. The 7-case behaviour test verifies env-only, setting-only, both-set, "true" instead of "1", and absence/missing-key scenarios.
- **D-11 satisfied:** `apps.api.settings.write_settings_file` uses the canonical `tmp = SETTINGS_PATH.with_suffix(SETTINGS_PATH.suffix + ".tmp"); tmp.write_text(...); tmp.replace(SETTINGS_PATH)` atomic pattern. The behaviour test asserts the tmp file is cleaned up post-replace.
- **Lifespan order locked (CONTEXT discretion line 178):** open DB → migrations → load artifacts → load settings → KeyStore → empty adapter registry → cache schema_version. Each step's source line is annotated with the step number.
- **B3 lazy-override pattern carried forward:** lifespan honours pre-set `app.state.{adapters,settings,keystore}` from the conftest `app_factory` fixture via `getattr(app.state, attr, _SENTINEL)` guards so test overrides land BEFORE production initialisation.
- **Phase 1 D-18 import-graph guard still green:** `uv run pytest src/routing/tests/test_decide_smoke.py -x` exits 0 (7/7). The lifespan imports `_load_default_artifacts` from `src.routing.decide` — direction is `apps.api → src.routing`, never the reverse.
- **Phase 2 whole-repo non-live suite still green:** 250 passed / 2 skipped / 3 deselected (`uv run pytest -m 'not live' -x`).

## Task Commits

Each task was committed atomically; no rule deviations or checkpoints fired this wave.

1. **Task 1: apps/api/settings.py — atomic write + D-12 STRICT AND** — `b352a79` (feat)
2. **Task 2: lifespan + main + routes/{__init__,health}** — `12fbeab` (feat)
3. **Task 3: test_health.py + test_cors.py (8 passing tests)** — `302dd03` (test)

**Plan metadata commit:** to be authored after this SUMMARY lands.

## Files Created/Modified

### Created (7)

- `apps/api/settings.py` (180 LOC) — `_default_settings`, `load_settings_file`, `write_settings_file` (atomic tmp+replace), `computer_use_enabled` (D-12 STRICT AND). Imports only `json`, `logging`, `os`, `apps.api.paths.SETTINGS_PATH`. No KeyStore reference (D-11 — keys NEVER enter settings.json).
- `apps/api/lifespan.py` (179 LOC) — `@asynccontextmanager async def lifespan(app: FastAPI)` per D-15 + discretion line 178. Imports `src.routing.decide._load_default_artifacts` (the canonical 4-key loader). 7-step startup body (numbered inline); defensive `finally: await app.state.db.close()`. `_SENTINEL` guard honours conftest pre-set overrides.
- `apps/api/main.py` (128 LOC) — `create_app()` factory + module-level `app = create_app()`. CORSMiddleware with OSS-05 allowlist (default `http://localhost:3000`; env override). Routes imported INSIDE the factory to avoid circular-import risk.
- `apps/api/routes/__init__.py` (11 LOC) — package marker; mirrors `apps/api/backends/__init__.py` shape.
- `apps/api/routes/health.py` (178 LOC) — `router = APIRouter(prefix="/api/v1", tags=["health"])`; `GET /api/v1/healthz` returns the D-18 rich payload. Three internal helpers (`_openrouter_status`, `_claude_code_status`, `_computer_use_status`) — all read-only (KeyStore + settings + env consults; NEVER constructor calls).
- `apps/api/tests/test_health.py` (338 LOC) — 5 async tests: `test_artifacts_loaded_once`, `test_pragmas_applied`, `test_healthz_returns_200_with_required_keys`, `test_healthz_status_dots`, `test_healthz_never_constructs_adapters`. Uses `httpx.AsyncClient + ASGITransport` + manual `app.router.lifespan_context(app)` trigger.
- `apps/api/tests/test_cors.py` (203 LOC) — 3 async tests: `test_cors_preflight_allowed_for_localhost`, `test_cors_preflight_rejected_for_evil`, `test_cors_env_override`. All exercise the OPTIONS preflight verb directly.

### Modified (0)

No existing files were touched. The Wave 0 conftest's `app_factory` fixture already expected this Wave 2 `create_app` factory shape via B3 lazy import; the lifespan honours the conftest pre-sets via the `_SENTINEL` guard.

## Decisions Made

- **Open Question 3 → single shared `aiosqlite.Connection` at `app.state.db`:** lifespan opens ONE connection and stashes it; Wave 3-6 route handlers read `request.app.state.db`. WAL + busy_timeout=5000 (D-03) tolerates concurrent reads gracefully; the single connection's worker thread serialises writes safely; saves us from re-running pragmas per request.
- **Open Question 5 → cache `schema_version` at startup:** `app.state.schema_version = await read_schema_version(app.state.db)` runs once in the lifespan; `/healthz` reads from memory. Avoids per-request SQLite hit on the hot poll path (Phase 5 UI-11 status dots).
- **Lifespan artifact loader = `src.routing.decide._load_default_artifacts`** (NOT `src.demo.demo_router.load_joblib_artifacts`): the former is the canonical 4-key dict (`task_type_classifier`, `agentic_intent_classifier`, `model_router`, `model_mapping`) that `decide()` consumes verbatim; the latter loads a single artifact and returns the wrong shape. Documented inline in `lifespan.py` so a future contributor doesn't swap it.
- **Routes imported INSIDE `create_app()`** rather than at module top: keeps circular-import risk at zero; matches FastAPI best practice for factory-based app construction.
- **Lifespan-trigger in tests via `app.router.lifespan_context(app)`:** `httpx.AsyncClient + ASGITransport` does NOT auto-trigger lifespan (verified empirically — `triggered['startup'] is False` without the explicit wrap). FastAPI exposes the context manager built-in so we avoid adding `asgi-lifespan` as a new dep.
- **Test isolation via `PROMPT_OPTIMIZER_HOME=tmp_path` + `importlib.reload` chain:** every test reloads `apps.api.{paths,lifespan,main}` so the DB lands in `tmp_path/chat.db`. The `PROMPT_OPTIMIZER_CORS_ORIGINS` env override is honoured the same way.

## Deviations from Plan

### None

Every task executed exactly as planned. No Rule 1 bugs, no Rule 2 missing-functionality additions, no Rule 3 blocking issues, no Rule 4 architectural questions. Two small in-source-only docstring scrubs were needed to satisfy the plan's literal grep guards:

1. **Health.py docstring scrub:** the original docstring mentioned `OpenRouterAdapter(`, `ClaudeCodeAdapter(`, `ComputerUseAdapter(` to explain that the module does NOT construct adapters. The plan's negative-grep acceptance check matched those docstring mentions at the byte level. Rewrote the docstring to describe the contract without including the literal constructor token sequences. The runtime behaviour is unchanged; the file now passes both the grep guard and the `test_healthz_never_constructs_adapters` runtime test.

2. **test_health.py docstring scrub:** identical issue — the original docstring contained the bare word `TestClient` to explain it's forbidden. The plan's negative-grep matched at the byte level. Rewrote the docstring to use "the synchronous FastAPI test-client wrapper" instead. The runtime API-08 CI guard in `test_smoke.py` (which uses a sophisticated runtime-constructed regex specifically to avoid matching its own source) was always passing.

Both scrubs are pure documentation edits with zero behavioural impact; tracking them as deviations is overkill (no Rule N fired) but documented here for completeness.

**Total deviations:** 0 substantive (2 cosmetic docstring scrubs)
**Impact on plan:** None.

## Issues Encountered

The only friction was the `ASGITransport`-does-NOT-trigger-lifespan caveat. Resolved by using FastAPI's built-in `app.router.lifespan_context(app)` context manager rather than adding `asgi-lifespan` as a new dep. The pattern is well-documented in FastAPI best practices for AsyncClient testing.

## User Setup Required

None. No external services. No environment configuration required for the Wave 2 contract; the lifespan creates `~/.prompt-optimizer/chat.db` on first boot and tests run against `tmp_path` isolated dirs. Phase 5's `PATCH /api/v1/settings` (Wave 6) is where the user will be able to set OpenRouter / Anthropic keys interactively; for now, env vars (`OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `COMPUTER_USE_OPT_IN`) feed the KeyStore + `computer_use_enabled` directly.

## Next Phase Readiness

- **Wave 3 (thread CRUD):** Ready to consume `app.state.db` for the storage layer, and ready to register `threads.router` inside `create_app()`. The Wave 1 `apps.api.db.queries.{create_thread, get_thread, list_threads, update_thread_title, delete_thread}` are the canonical query functions.
- **Wave 4 (turn SSE):** Ready to read `request.app.state.{db, artifacts, settings, keystore, adapters}` populated by this Wave 2 lifespan. The empty `app.state.adapters` registry is the lazy-build target — Wave 4's `_get_or_create_adapter(app, backend)` helper instantiates the per-backend adapter on first turn and caches it.
- **Wave 5 (blob cascade):** No new surface from Wave 2; Wave 5 extends `delete_thread` with a pre-step that walks `messages.content_blocks` JSON to unlink referenced blob files BEFORE the DB delete.
- **Wave 6 (settings + rename):** `PATCH /api/v1/settings` will use `apps.api.settings.{load_settings_file, write_settings_file}` for atomic file I/O and will clear `app.state.adapters` per D-15 (so the next turn rebuilds with fresh KeyStore values). `POST /api/v1/threads/{id}/rename` constructs a fresh `OpenRouterAdapter` (single-use, NOT cached) per D-17.
- **Phase 4 (UI proxy):** Will consume `/api/v1/healthz` over CORS. The default `http://localhost:3000` allowlist + `Last-Event-ID` allow-header pre-wire Phase 4's Next.js dev server.
- **Phase 5 (UI-11 status dot strip):** Will poll `/api/v1/healthz` and render per-adapter status dots using the closed `AdapterStatus` vocabulary.

No blockers. No concerns. All 11 Wave 2 truths verify at a CLI / pytest level.

## All 11 Wave 2 Truths Verified

```
Truth 1  OK: no sys.path.append in any Phase 3 source file
Truth 2  OK: apps/api/* imports trigger dotenv.load_dotenv() + install_redaction_filter() via apps/api/__init__.py (no module re-installs)
Truth 3  OK: `from apps.api.main import app, create_app` succeeds; app.title='Prompt-Optimizer API', version='0.1.0', lifespan registered
Truth 4  OK: lifespan opens DB → migrate → _load_default_artifacts (4-key dict) → settings → KeyStore → adapters={} → schema_version cache
Truth 5  OK: settings.py exports load_settings_file, write_settings_file (atomic tmp.replace), computer_use_enabled
Truth 6  OK: computer_use_enabled enforces STRICT AND (env literal `1` AND settings flag True); 7-case behaviour test passes
Truth 7  OK: GET /api/v1/healthz returns 200 with {status, artifacts_loaded, db_ok, schema_version, adapters{openrouter,claude_code,computer_use}, version}; AdapterStatus closed vocabulary
Truth 8  OK: CORS default http://localhost:3000; PROMPT_OPTIMIZER_CORS_ORIGINS env override; NEVER ['*']
Truth 9  OK: OPTIONS preflight with Origin=http://localhost:3000 returns 200 with matching Access-Control-Allow-Origin; OPTIONS with Origin=http://evil.example does NOT echo
Truth 10 OK: `python -c "from apps.api.main import app"` cold import = 1.23 s (well under 3 s SC budget)
Truth 11 OK: `uv run pytest apps/api/tests/test_health.py apps/api/tests/test_cors.py -x` exits 0 (8/8 pass — artifacts_loaded_once, pragmas_applied, healthz_status_dots, cors_preflight_allowed/rejected/env_override + 2 more)
```

## Self-Check: PASSED

- All 7 files referenced in `key-files.created` exist on disk:
  - `apps/api/settings.py` — 180 LOC
  - `apps/api/lifespan.py` — 179 LOC
  - `apps/api/main.py` — 128 LOC
  - `apps/api/routes/__init__.py` — 11 LOC
  - `apps/api/routes/health.py` — 178 LOC
  - `apps/api/tests/test_health.py` — 338 LOC
  - `apps/api/tests/test_cors.py` — 203 LOC
- All 3 task commits referenced above are present in `git log --oneline`:
  - `b352a79` — feat(03-02): add apps/api/settings.py
  - `12fbeab` — feat(03-02): add FastAPI app shell — lifespan + main + health route
  - `302dd03` — test(03-02): add test_health.py + test_cors.py (8 passing tests)
- The plan-metadata commit follows this SUMMARY landing on disk.

---

*Phase: 03-fastapi-service-persistent-storage*
*Plan: 02 (Wave 2 — app shell + healthz)*
*Completed: 2026-05-17*
