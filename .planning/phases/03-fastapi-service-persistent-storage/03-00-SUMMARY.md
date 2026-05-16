---
phase: "03"
plan: "00"
subsystem: "fastapi-service-persistent-storage / scaffolding"
tags: [scaffolding, dependencies, test-infrastructure, API-08, paths, env]
requires:
  - "Phase 2 P00..P07 complete (apps/api/backends/* contract surface)"
  - "Phase 2 OSS-06 pre-commit + CI guard against claude-code-sdk"
  - "Phase 2 SECURE-02 pre-commit secret-grep"
provides:
  - "apps.api.paths (PROJECT_ROOT, USER_HOME, DB_PATH, BLOBS_DIR, SETTINGS_PATH, WORKSPACES_DIR, JSONL_LOG_PATH)"
  - "apps.api.tests.conftest (aiosqlite_inmemory_db, asgi_client, app_factory) with B3 lazy imports"
  - "apps.api.tests.fake_adapter.FakeStreamingAdapter implementing BackendAdapter Protocol"
  - "apps/api/tests/fixtures/schema_v0_seed.sql (1 thread + 2 messages + 1 routing_decisions row)"
  - "API-08 / D-20 negative-grep guard (no synchronous FastAPI test-client wrapper allowed under apps/api/tests/)"
  - ".env.example template (5 env vars; empty values)"
  - "pyproject.toml Phase 3 deps: fastapi, uvicorn[standard], sse-starlette, aiosqlite, httpx-sse"
affects:
  - "Wave 1-6 of Phase 3 (consume paths.py, conftest fixtures, seed SQL, fake adapter)"
tech-stack:
  added:
    - "fastapi 0.136.1 (>=0.115,<1.0)"
    - "uvicorn[standard] (>=0.30,<1.0) — includes httptools, uvloop, watchfiles"
    - "sse-starlette (>=2.1,<4.0) — widened from CONTEXT D-06's <3.0 per RESEARCH OQ1 to allow mcp transitive 3.x"
    - "aiosqlite 0.22.1 (>=0.20,<1.0)"
    - "httpx-sse (>=0.4,<1.0) — dev extra, for SSE test parsing (aconnect_sse)"
  patterns:
    - "B3 lazy-import pattern (try/except ImportError → pytest.skip) for every Wave 1-6 producer module referenced inside a fixture"
    - "pathlib.Path(__file__).resolve().parents[2] for repo-root computation (Phase 2 convention extended to apps/api/paths.py)"
    - "PROMPT_OPTIMIZER_HOME env override pattern (read at import; tests use importlib.reload to flip)"
    - "Runtime-built regex with string-fragment concatenation to avoid negative-grep self-match (test_smoke.py guard)"
key-files:
  created:
    - "apps/api/paths.py"
    - "apps/api/tests/__init__.py"
    - "apps/api/tests/conftest.py"
    - "apps/api/tests/fake_adapter.py"
    - "apps/api/tests/fixtures/schema_v0_seed.sql"
    - "apps/api/tests/test_smoke.py"
    - ".env.example"
  modified:
    - "pyproject.toml"
    - "uv.lock"
    - ".gitignore"
    - ".planning/phases/03-fastapi-service-persistent-storage/03-VALIDATION.md"
decisions:
  - "sse-starlette range widened to >=2.1,<4.0 per RESEARCH Open Question 1 (CONTEXT D-06 originally locked <3.0 but the mcp transitive pins 3.x; the public surface Phase 3 consumes is unchanged across 2.x/3.x)."
  - "test_no_testclient_imports_under_apps_api_tests builds its forbidden regex at runtime from string fragments so this very file does not match its own pattern (Rule 1 fix during execution)."
  - "test_smoke.py negative-grep uses --include='*.py' --include='*.sql' so .pyc files cannot trigger false positives."
  - "conftest.py docstrings reference 'the synchronous FastAPI test-client wrapper' by description rather than literal name so the negative-grep guard at CLI does not match documentation text."
metrics:
  duration_min: 944
  completed: "2026-05-16"
  tasks: 5
  files_created: 7
  files_modified: 4
---

# Phase 03 Plan 00: Wave 0 Scaffolding Summary

## One-liner

Installed 4 Phase 3 deps + 1 dev dep, authored `apps/api/paths.py` (7 path constants honoring `PROMPT_OPTIMIZER_HOME`), wired the B3-lazy `apps/api/tests/conftest.py` (aiosqlite/asgi/app_factory fixtures), shipped `FakeStreamingAdapter`, the schema_v0 migration-seed SQL, the `test_smoke.py` Wave 0 sanity (5 sub-tests) including the API-08 / D-20 negative-grep guard, and signed off `03-VALIDATION.md` as `nyquist_compliant: true` / `wave_0_complete: true`.

## What shipped

### New files (7)

1. **`apps/api/paths.py`** — single source for path constants. Exports `PROJECT_ROOT` (`Path(__file__).resolve().parents[2]`), `USER_HOME` (env-overridable via `PROMPT_OPTIMIZER_HOME`, defaults to `~/.prompt-optimizer/`), `DB_PATH`, `BLOBS_DIR`, `SETTINGS_PATH`, `WORKSPACES_DIR`, `JSONL_LOG_PATH`. No `sys.path` mutation; no stringly-typed path concatenation. **Wave 1+ consumes:** Wave 1 `db/connect.py` (`DB_PATH`), Wave 2 lifespan (`SETTINGS_PATH`, `WORKSPACES_DIR`), Wave 4 turn route (`JSONL_LOG_PATH`), Wave 5 blob store (`BLOBS_DIR`).

2. **`apps/api/tests/__init__.py`** — package marker with one-paragraph docstring documenting the B3 pattern.

3. **`apps/api/tests/conftest.py`** — three core fixtures with **lazy** Wave 1-6 producer imports:
   - `aiosqlite_inmemory_db` — async function-scoped, lazy-imports `apps.api.db.connect.open_db` + `apps.api.db.migrate.up_to_latest` (Wave 1). 4 try/except ImportError → pytest.skip blocks total.
   - `asgi_client` — returns a factory that yields `httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")`. Never the synchronous FastAPI test-client wrapper.
   - `app_factory` — returns a factory accepting `adapters_override`, `settings_override`, `keystore_override`; lazy-imports `apps.api.main:create_app` (Wave 2). Stashes the overrides on `app.state.*` before lifespan runs.
   - Only module-level import of a producer module is `aiosqlite` itself (the actual driver, not a Wave 1 module).

4. **`apps/api/tests/fake_adapter.py`** — `class FakeStreamingAdapter(BackendAdapter)`. Constructor takes `chunks: list[ChatChunk]` and optional `sleep_per_chunk: float = 0.0`. The `stream(prompt, history, options)` async-iterator yields each chunk in order, awaiting `asyncio.sleep(sleep_per_chunk)` before each yield when set. **Does not synthesize a terminal `Done`** — tests must include one. Used by Wave 4 streaming/heartbeat tests and Wave 6 rename.

5. **`apps/api/tests/fixtures/schema_v0_seed.sql`** — INSERT-only seed: 1 thread (`thr_seed_0001`), 2 messages (`msg_seed_user_0001`, `msg_seed_asst_0001`), 1 routing_decisions row (`rd_seed_0001`). All literal IDs are 13 chars, distinct from production `secrets.token_urlsafe(12)` shape. References only schema_v0 columns; Wave 1's `test_v0_to_v1_preserves_data` asserts row preservation after `up_to_latest()`.

6. **`apps/api/tests/test_smoke.py`** — 5 sub-tests (all pass in 0.19s):
   - `test_phase_3_deps_importable` — `fastapi`, `uvicorn`, `aiosqlite`, `sse_starlette.sse.EventSourceResponse`, `httpx_sse.aconnect_sse`.
   - `test_paths_constants_well_formed` — each path ends with its expected filename suffix; `PROJECT_ROOT` contains `pyproject.toml`; `USER_HOME` is the parent of `DB_PATH`/`BLOBS_DIR`/`SETTINGS_PATH`/`WORKSPACES_DIR`.
   - `test_paths_honors_env_override` — `monkeypatch.setenv("PROMPT_OPTIMIZER_HOME", "/tmp/po-test")` + `importlib.reload(paths_module)` → `USER_HOME == Path("/tmp/po-test")`.
   - `test_fake_streaming_adapter_yields_chunks` — async iteration of `FakeStreamingAdapter([TextDelta(text="hi"), Done()])` → 2 chunks; last is `Done`.
   - `test_no_testclient_imports_under_apps_api_tests` — runs the API-08 / D-20 negative-grep via `subprocess.run(["grep", "-rE", "--include=*.py", "--include=*.sql", PATTERN, tests_dir])`; asserts exit code 1. The pattern is BUILT AT RUNTIME from string fragments so the source file does not contain its own pattern.

7. **`.env.example`** — first-time-in-repo env template. 5 entries: `OPENROUTER_API_KEY=`, `ANTHROPIC_API_KEY=`, `COMPUTER_USE_OPT_IN=0`, commented `# PROMPT_OPTIMIZER_HOME=`, commented `# PROMPT_OPTIMIZER_CORS_ORIGINS=http://localhost:3000`. Each line preceded by a one-paragraph `#` comment header explaining the variable.

### Modified files (4)

8. **`pyproject.toml`** — appended to `[project.dependencies]`: `"fastapi>=0.115,<1.0"`, `"uvicorn[standard]>=0.30,<1.0"`, `"sse-starlette>=2.1,<4.0"` (widened from CONTEXT D-06's `<3.0` — see Decisions), `"aiosqlite>=0.20,<1.0"`. Appended to `[project.optional-dependencies] dev`: `"httpx-sse>=0.4,<1.0"`. **`claude-code-sdk` not added** (Phase 2 OSS-06 guard still active).

9. **`uv.lock`** — regenerated via `uv lock`. Added: `aiosqlite v0.22.1`, `annotated-doc v0.0.4`, `fastapi v0.136.1`, `httptools v0.7.1`, `uvloop v0.22.1`, `watchfiles v1.1.1`, `websockets v16.0`. `sse-starlette` was already resolved transitively (mcp dependency); only metadata updated. `claude-code-sdk` still absent.

10. **`.gitignore`** — added `.planning/data/` exclusion (forward-compat for STORE-06 JSONL log Wave 4 writes).

11. **`.planning/phases/03-fastapi-service-persistent-storage/03-VALIDATION.md`** — frontmatter `status: draft → signed`, `nyquist_compliant: false → true`, `wave_0_complete: false → true`. Per-Task Verification Map rows `3-00-01` and `3-00-02` flipped to `✅ landed` / `✅ green`. All 6 Validation Sign-Off boxes checked; Approval line set to `signed — 2026-05-16`. Line count preserved at 118.

## How it works (key design choices)

### B3 lazy-import pattern (Phase 2 P00 carry-forward)

Producer modules from Wave 1-6 (`apps.api.main:create_app`, `apps.api.lifespan`, `apps.api.db.connect.open_db`, `apps.api.db.migrate.up_to_latest`) are imported INSIDE the fixture body, wrapped in `try: ... except ImportError: pytest.skip(...)`. The conftest is collectable in Wave 0 BEFORE any of those modules exist. When a Wave 1 test asks for `aiosqlite_inmemory_db` before Wave 1 has authored `db/connect.py`, the test is skipped (not collection-failed). Once Wave 1 lands, the same fixture activates without code changes.

### API-08 / D-20 negative-grep — self-non-matching test

The literal CI form is `! grep -rE 'from fastapi.testclient|fastapi\.testclient\.TestClient' apps/api/tests/`. Running this *naively* against a guard test that hard-codes the regex would always fail because the test file itself contains the literal pattern. Two fixes:

1. **Runtime-built regex.** The pattern is constructed at test-call time from string fragments (`"fastapi" + "." + "testclient"`, `"Test" + "Client"`) so the source file does not contain a literal match.
2. **Include filter.** The grep call passes `--include=*.py --include=*.sql` so `.pyc` compiled bytecode files (which embed the runtime-constructed pattern in their constants table) cannot trigger false positives.

Same risk applied to `conftest.py` docstrings — replaced literal `fastapi.testclient.TestClient` mentions with the descriptive phrase "the synchronous FastAPI test-client wrapper" so the CLI guard at `grep -rE 'from fastapi.testclient|fastapi\.testclient\.TestClient' apps/api/tests/` exits 1 (clean) without `--include` filtering.

### sse-starlette upper bound widened

CONTEXT D-06 locks `sse-starlette<3.0`. RESEARCH Open Question 1 resolved this: the `mcp` package (which the Claude Code SDK pulls transitively) pins `sse-starlette>=3.0`. Forcing `<3.0` would require downgrading `mcp`, breaking the Phase 2 Claude Code adapter. The public Phase 3 surface (`EventSourceResponse`, `ServerSentEvent`, `_listen_for_disconnect`) is unchanged between 2.x and 3.x. Plan landed `>=2.1,<4.0` per OQ1.

## Tasks completed (5 / 5)

| # | Task                                                                  | Commit    | Files                                                                                                                                                                  |
| - | --------------------------------------------------------------------- | --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | Extend pyproject.toml + regenerate uv.lock                            | `913932c` | `pyproject.toml`, `uv.lock`                                                                                                                                            |
| 2 | Author paths.py + .env.example + extend .gitignore                    | `085b772` | `apps/api/paths.py`, `.gitignore`, `.env.example`                                                                                                                      |
| 3 | Scaffold conftest, fake_adapter, schema_v0 seed                       | `550d713` | `apps/api/tests/__init__.py`, `apps/api/tests/conftest.py`, `apps/api/tests/fake_adapter.py`, `apps/api/tests/fixtures/schema_v0_seed.sql`                             |
| 4 | Wave 0 sanity test_smoke.py + API-08 guard                            | `9cbd549` | `apps/api/tests/test_smoke.py`, plus follow-on fix to `apps/api/tests/conftest.py` docstrings to avoid false-positive negative-grep matches                            |
| 5 | Sign off VALIDATION.md (`nyquist_compliant: true`)                    | `43c36df` | `.planning/phases/03-fastapi-service-persistent-storage/03-VALIDATION.md`                                                                                              |

## Verification — all 10 truths from `must_haves.truths` confirmed at CLI

1. **No `sys.path.append` in Phase 3 source.** `! grep -q "sys.path.append" apps/api/paths.py` exits 0. Path discovery uses `Path(__file__).resolve().parents[2]`.
2. **Phase 3 modules import `apps.api.*` first.** Verified by inspection — `conftest.py` imports `apps.api.backends.keystore`; `paths.py` is self-contained but reachable only via `apps.api.paths` (triggering `apps/api/__init__.py:load_dotenv() + install_redaction_filter()`).
3. **API-08 negative-grep clean.** `grep -rE 'from fastapi.testclient|fastapi\.testclient\.TestClient' apps/api/tests/` exits 1.
4. **All 4 new deps installed.** `uv run python -c "from fastapi import FastAPI; from sse_starlette.sse import EventSourceResponse; import aiosqlite; import uvicorn; print('ok')"` prints `ok`.
5. **`pytest --collect-only apps/api/tests/` works.** `test_smoke.py` collected; `conftest.py` and `fake_adapter.py` import cleanly; the 3 fixtures are discoverable. Lazy imports defer until first call.
6. **`apps/api/paths.py` exports the 7 constants + honors env override.** `uv run python -c "from apps.api.paths import ..."` works; `os.environ['PROMPT_OPTIMIZER_HOME']='/tmp/test'` + reload routes `USER_HOME` to `/tmp/test`.
7. **`.gitignore` excludes `.planning/data/`.** Confirmed at line ~34 in `.gitignore`.
8. **Phase 1 D-18 import-graph guard green.** `uv run pytest src/routing/tests/test_decide_smoke.py -x` → 7 passed in 2.61s.
9. **Phase 2 whole-repo non-live suite green.** `uv run pytest -m 'not live' -x` → **238 passed, 2 skipped, 3 deselected in 58.87s** (was 233 passed before Wave 0; +5 new smoke tests). No regression.
10. **`03-VALIDATION.md` frontmatter signed.** `nyquist_compliant: true`, `wave_0_complete: true`, `status: signed`, Approval `signed — 2026-05-16`, 6 of 6 Validation Sign-Off boxes checked, line count preserved at 118.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Anti-pattern doctring in apps/api/paths.py triggered own grep guards.**

- **Found during:** Task 2 verification step.
- **Issue:** The module docstring contained "`sys.path.append`" and "`os.path.join`" as literal strings in explanation prose. The Task 2 acceptance criteria included `! grep -q "sys.path.append" apps/api/paths.py` and `! grep -q "os.path.join" apps/api/paths.py` — these failed because grep matched the docstring.
- **Fix:** Rewrote the docstring to describe the anti-patterns ("never mutates `sys.path`", "never builds paths via stringly-typed concatenation") rather than name them with literal tokens.
- **Files modified:** `apps/api/paths.py`.
- **Commit:** part of `085b772`.

**2. [Rule 1 — Bug] test_smoke.py API-08 guard self-matched its own pattern.**

- **Found during:** Task 4 first pytest run.
- **Issue:** `test_no_testclient_imports_under_apps_api_tests` hard-coded the forbidden regex as `r"from fastapi.testclient|fastapi\.testclient\.TestClient"`. When grep searched `apps/api/tests/`, the literal string in the source file itself matched. Also: `conftest.py` docstrings mentioned `fastapi.testclient.TestClient` in API-08 explanation prose. Plus: `.pyc` files in `__pycache__/` embedded the same constant strings.
- **Fix:**
  - Built the forbidden regex at runtime from string fragments (`"fastapi" + "." + "testclient"`, `"Test" + "Client"`) so the source file does NOT contain a literal match.
  - Added `--include='*.py' --include='*.sql'` to the subprocess grep call to exclude binary `.pyc` files.
  - Rewrote `conftest.py` docstrings to reference "the synchronous FastAPI test-client wrapper" by description rather than literal name.
  - Cleaned `__pycache__/` before re-running the test (stale .pyc files would still embed the old strings until regenerated).
- **Files modified:** `apps/api/tests/test_smoke.py`, `apps/api/tests/conftest.py`.
- **Commit:** part of `9cbd549`.

### Non-deviations (planned items applied as-written)

- `sse-starlette` upper bound widened to `>=2.1,<4.0` — this was already specified in the plan body as the resolution of RESEARCH Open Question 1; not a deviation but a planned override of CONTEXT D-06's `<3.0`.

## Deferred Issues

None. All five tasks landed; all 10 truths verified.

## Threat Flags

None. No new network endpoints, auth paths, or trust-boundary changes introduced by Wave 0 — only test infrastructure, path constants, env-template documentation, and a dependency-list extension.

## What's next (Wave 1+)

Wave 0 is the unblocker for the rest of Phase 3. With this plan complete:

- **Wave 1 (03-01)** authors `apps/api/db/{connect,migrate,queries,models}.py` + `apps/api/db/migrations/schema_v{0,1}.sql`. The migration round-trip test reuses `apps/api/tests/fixtures/schema_v0_seed.sql`. The `aiosqlite_inmemory_db` fixture's lazy imports activate on first Wave 1 test run.
- **Wave 2 (03-02)** authors `apps/api/{main,lifespan,settings}.py` + `apps/api/routes/health.py`. The `app_factory` fixture's lazy `create_app` import activates here.
- **Wave 3 (03-03)** authors `apps/api/routes/{threads,settings}.py`. All tests already have `asgi_client(app)` ready.
- **Wave 4 (03-04)** authors `apps/api/routes/turn.py` SSE handler. Heartbeat tests reuse `FakeStreamingAdapter(sleep_per_chunk=0.6)` with monkeypatched `DEFAULT_PING_INTERVAL=0.5`.
- **Wave 5 (03-05)** authors `apps/api/blobs.py` blob store. Uses `BLOBS_DIR` from `paths.py`.
- **Wave 6 (03-06)** authors `apps/api/routes/rename.py`. Uses `FakeStreamingAdapter` for the one-shot title-collect path.

## Self-Check: PASSED

All claimed files exist on disk; all 5 task commits exist in git history; all 10 truths verifiable at CLI; whole-repo non-live test suite green at 238 passed.
