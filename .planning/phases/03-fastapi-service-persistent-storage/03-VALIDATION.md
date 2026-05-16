---
phase: 03
slug: fastapi-service-persistent-storage
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-15
---

# Phase 03 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `.planning/phases/03-fastapi-service-persistent-storage/03-RESEARCH.md` §Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 + pytest-asyncio 1.3.0 + pytest-timeout 2.4.0 |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` (already configured: `--import-mode=importlib`, `asyncio_mode=auto`, `markers=["live"]`, `testpaths=["src", "apps"]`) |
| **Quick run command** | `uv run pytest -m 'not live' apps/api/tests -x --timeout=30` |
| **Full suite command** | `uv run pytest -m 'not live' -x --timeout=60` |
| **Estimated runtime** | Quick: <60 s · Full: <120 s (in-memory SQLite, fake adapters, monkeypatched ping interval) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -m 'not live' apps/api/tests -x --timeout=30` (Phase 3 only).
- **After every plan wave:** Run `uv run pytest -m 'not live' -x --timeout=60` (Phase 1 + Phase 2 + Phase 3 — confirms no D-18 import-guard breakage and no Phase 2 adapter-contract regression).
- **Before `/gsd-verify-work`:** Full suite must be green AND `uvicorn apps.api.main:app` boots in <3 s with no errors.
- **Max feedback latency:** <60 seconds for per-task-commit suite (achievable because every Phase 3 integration test uses `:memory:` SQLite, fake adapters via `app.state.adapters` override, and monkeypatched `DEFAULT_PING_INTERVAL=0.5`).

---

## Per-Task Verification Map

> Status legend: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky
> Test files are listed as "❌ Wave N" where N is the wave that authors them; Wave 0 authors test infrastructure.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 3-00-01 | 00 | 0 | API-08 | — | Enforce httpx + ASGITransport (no TestClient) | meta | `! grep -rE 'from fastapi.testclient\|fastapi\.testclient\.TestClient' apps/api/tests/` | ❌ Wave 0 | ⬜ pending |
| 3-00-02 | 00 | 0 | API-01 / STORE-01 / STORE-02 | — | conftest fixtures load before app startup | unit | `uv run pytest apps/api/tests/test_smoke.py -x` (Wave 0 sanity) | ❌ Wave 0 | ⬜ pending |
| 3-01-01 | 01 | 1 | STORE-01 / STORE-02 | T-03-Mig | Migrations idempotent + pragmas applied | unit | `uv run pytest apps/api/tests/test_migrations.py::test_schema_v0_has_all_three_tables -x` | ❌ Wave 1 | ⬜ pending |
| 3-01-02 | 01 | 1 | STORE-03 | T-03-Mig | Migration runner is forward-only, idempotent | integration | `uv run pytest apps/api/tests/test_migrations.py::test_v0_to_v1_preserves_data -x` | ❌ Wave 1 | ⬜ pending |
| 3-01-03 | 01 | 1 | STORE-01 | — | WAL + busy_timeout + foreign_keys ON | unit | `uv run pytest apps/api/tests/test_health.py::test_pragmas_applied -x` | ❌ Wave 1 | ⬜ pending |
| 3-02-01 | 02 | 2 | API-01 | T-03-LL | Joblib artifacts load once at lifespan | unit | `uv run pytest apps/api/tests/test_health.py::test_artifacts_loaded_once -x` | ❌ Wave 2 | ⬜ pending |
| 3-02-02 | 02 | 2 | OSS-05 | T-03-CORS | Explicit origin; no wildcard | unit | `uv run pytest apps/api/tests/test_cors.py -x` | ❌ Wave 2 | ⬜ pending |
| 3-02-03 | 02 | 2 | API-01 | — | healthz adapter-status precheck (read-only) | unit | `uv run pytest apps/api/tests/test_health.py::test_healthz_status_dots -x` | ❌ Wave 2 | ⬜ pending |
| 3-03-01 | 03 | 3 | API-03 | T-03-SQLi | Thread CRUD (POST/GET/PATCH/DELETE) | integration | `uv run pytest apps/api/tests/test_threads_crud.py -x` | ❌ Wave 3 | ⬜ pending |
| 3-03-02 | 03 | 3 | API-04 / STORE-04 | T-03-Disclo | Settings GET masks keys; PATCH never persists plaintext | integration | `uv run pytest apps/api/tests/test_settings.py -x` | ❌ Wave 3 | ⬜ pending |
| 3-04-01 | 04 | 4 | API-02 / API-07 | T-03-Disclo | SSE stream + decide() in asyncio.to_thread | integration | `uv run pytest apps/api/tests/test_turn_streaming.py::test_streams_chatchunks -x --timeout=30` | ❌ Wave 4 | ⬜ pending |
| 3-04-02 | 04 | 4 | API-05 | — | 15s heartbeat (monkeypatched to <1s for tests) | integration | `uv run pytest apps/api/tests/test_turn_streaming.py::test_heartbeat_emits -x --timeout=10` | ❌ Wave 4 | ⬜ pending |
| 3-04-03 | 04 | 4 | API-06 | T-03-Cancel | request.is_disconnected() cancels within 2s | integration | `uv run pytest apps/api/tests/test_turn_streaming.py::test_cancellation_within_2s -x --timeout=5` | ❌ Wave 4 | ⬜ pending |
| 3-04-04 | 04 | 4 | STORE-05 | — | One transaction per turn on Done | integration | `uv run pytest apps/api/tests/test_turn_streaming.py::test_one_transaction_per_turn -x` | ❌ Wave 4 | ⬜ pending |
| 3-04-05 | 04 | 4 | STORE-06 | — | routing_decisions.jsonl appended at decide-time | integration | `uv run pytest apps/api/tests/test_turn_streaming.py::test_jsonl_log_appended -x` | ❌ Wave 4 | ⬜ pending |
| 3-04-06 | 04 | 4 | API-02 | — | override_backend body field bypasses decide() | integration | `uv run pytest apps/api/tests/test_turn_streaming.py::test_override_backend -x` | ❌ Wave 4 | ⬜ pending |
| 3-05-01 | 05 | 5 | STORE-04 | T-03-Path | Blobs ≥256 KB written by sha256 ref | unit + integration | `uv run pytest apps/api/tests/test_blobs_by_hash.py -x` | ❌ Wave 5 | ⬜ pending |
| 3-05-02 | 05 | 5 | API-03 / STORE-04 | T-03-Path | DELETE thread unlinks blobs THEN DB cascade | integration | `uv run pytest apps/api/tests/test_threads_crud.py::test_delete_unlinks_blobs -x` | ❌ Wave 5 | ⬜ pending |
| 3-06-01 | 06 | 6 | API-04 | T-03-Disclo | BYOK keys never in DB or log | integration | `uv run pytest apps/api/tests/test_secure_no_key_in_logs.py -x` | ❌ Wave 6 | ⬜ pending |
| 3-06-02 | 06 | 6 | API-03 | — | Rename endpoint (defensive constants) | integration | `uv run pytest apps/api/tests/test_rename.py -x` | ❌ Wave 6 | ⬜ pending |
| 3-06-03 | 06 | 6 | — | — | uvicorn boots in <3 s (boot-smoke) | smoke | `time uv run python -c "from apps.api.main import app; print('ok')"` | ❌ Wave 6 | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `apps/api/tests/__init__.py` — package marker.
- [ ] `apps/api/tests/conftest.py` — three core fixtures:
  - `aiosqlite_inmemory_db` — yields an `aiosqlite.Connection` to `":memory:"` with all migrations applied. Closes on teardown.
  - `asgi_client` — yields `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")`. Uses a per-test `create_app()` factory so state overrides land BEFORE startup.
  - `app_factory` — accepts `adapters_override: dict[str, BackendAdapter]`, `settings_override: dict`, `keystore_override: KeyStore` and returns a fresh FastAPI app whose lifespan honors the overrides.
- [ ] `apps/api/tests/fixtures/schema_v0_seed.sql` — INSERTs 1 thread + 2 messages + 1 routing_decisions row into a fresh v0 DB; used by migration round-trip test.
- [ ] `apps/api/tests/fake_adapter.py` — `class FakeStreamingAdapter` implementing `BackendAdapter`; constructor takes a list of `ChatChunk` to emit + optional sleep-per-chunk for heartbeat tests.
- [ ] Negative-grep CI step: `! grep -rE 'from fastapi.testclient\|fastapi\.testclient\.TestClient' apps/api/tests/` — enforces API-08 / D-20.
- [ ] Framework install: `uv sync` after Wave 0 pyproject.toml edits brings in `fastapi`, `uvicorn[standard]`, `sse-starlette`, `aiosqlite`. `pytest-asyncio` + `pytest-timeout` already present.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live SSE end-to-end against a real OpenRouter call from `uvicorn apps.api.main:app` | API-02 + API-05 | Hits paid provider; BYOK required; non-deterministic completion text. | Start `OPENROUTER_API_KEY=… uv run uvicorn apps.api.main:app --reload`; `curl -N -X POST http://127.0.0.1:8000/api/v1/threads/<id>/turn -H "Content-Type: application/json" -d '{"message":"hello"}'`. Observe `event: text_delta` lines and a terminal `event: done` with `cost_usd > 0`. |
| 15-second wall-clock heartbeat during a long agentic turn | API-05 | Automated test uses monkeypatched ping interval; this confirms the real 15s default. | Run a Claude Code turn that takes >20 s (e.g., "scaffold a new package"); confirm `: ping` comment lines arrive at 15-second intervals on the live `curl -N` stream. |
| End-to-end CORS preflight from Next.js dev server | OSS-05 | Phase 4 isn't built yet; manually craft an `OPTIONS` preflight to confirm the response includes `Access-Control-Allow-Origin: http://localhost:3000`. | `curl -X OPTIONS http://127.0.0.1:8000/api/v1/threads -H "Origin: http://localhost:3000" -H "Access-Control-Request-Method: POST" -i` → must see `200` with explicit-origin header. |

---

## Threat Refs

> Compact reference for the **Threat Ref** column above. Full STRIDE table lives in `03-RESEARCH.md §Security Domain`.

| Threat Ref | STRIDE | Description | Mitigation |
|------------|--------|-------------|------------|
| T-03-SQLi | Tampering | SQL injection via path/body params | Parameterised queries; never f-string SQL |
| T-03-Path | Tampering | Path traversal via `image_ref` in DB | `image_ref` set by Phase 3 only; resolve-real-path guard at unlink time |
| T-03-Disclo | Information Disclosure | Plaintext key in log, response, or JSONL | Phase 2 RedactionFilter + D-10 mask + JSONL signals never carry keys |
| T-03-Cancel | Tampering | Cancellation doesn't propagate; orphaned upstream call | sse-starlette `_listen_for_disconnect`; D-19 `task.cancel()` pattern in tests |
| T-03-CORS | Spoofing | Wildcard or reflected origin | Explicit allowlist; env override; no `*` |
| T-03-LL | Information Disclosure | Stale joblib artifact pinned at lifespan after a re-train | Acknowledged; restart required (single-process local server) |
| T-03-Mig | Tampering | Replayed old migration overwrites newer state | `schema_meta.version` gate; idempotent runner |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (Phase 3 tests + fixtures + fake adapter)
- [ ] No watch-mode flags (`-x --timeout=N` is the canonical form)
- [ ] Feedback latency < 60 s
- [ ] `nyquist_compliant: true` set in frontmatter after Wave 0 lands

**Approval:** pending
