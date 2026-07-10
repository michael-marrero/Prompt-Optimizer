---
baseline_commit: c230dc53e5c512ebc454b4a2302dbb29107e49c6
---

# Story 2.2: Enforce coverage at artifact load, fail-closed

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the builder,
I want the artifact-load path to refuse a routing head that the Story 2.1 manifest says must be calibrated but isn't,
so that an uncalibrated required head can never silently reach the policy thresholds — the check fails closed at load, once, never on the per-turn request path.

## Acceptance Criteria

1. **A required-calibrated head with no calibration fails the load, closed.**
   **Given** the `CALIBRATION_COVERAGE` manifest (Story 2.1) and the `models/*.joblib` bundles loaded at startup
   **When** a head named by `required_calibrated_heads()` loads with a `model` that is **not** calibrated
   **Then** the load raises with a remediation hint that **names the offending head** and **the training step to run** (mirrors the AD-8 loader contract in `_load_one_artifact` — see `src/routing/decide.py:122-131`)
   **And** the message does not leak keys/paths beyond the head name + fix command.

2. **A fully-compliant set loads cleanly, no behavior change.**
   **Given** all three required heads (`task_type_classifier`, `agentic_intent_classifier`, `model_router`) load as calibrated bundles
   **When** enforcement runs
   **Then** it returns without raising and the loaded artifacts dict is unchanged (same shape `decide()` consumes today)
   **And** no routing decision, threshold, or rationale changes (AD-10 quality-first ordering untouched).

3. **The check runs once at load, never per turn (AD-3).**
   **Given** the lifespan preloads artifacts once into `app.state.artifacts` and passes them to `decide(artifacts=...)`
   **When** turns are served
   **Then** enforcement executes only on the disk-load path (`_load_default_artifacts()`), and a per-turn `decide()` call with preloaded artifacts never re-invokes it
   **And** nothing calibration-related runs on the async request hot path.

4. **Enforcement reads the manifest, not a re-hardcoded head list.**
   **Given** Story 2.1 declared `required_calibrated_heads()` as the single source of truth
   **When** enforcement decides which heads to check
   **Then** it iterates `required_calibrated_heads()` (adding a head to the routing path + manifest auto-covers it)
   **And** a test proves both directions: a compliant fake-artifact set passes, and a fake set with one required head uncalibrated raises naming that head — the test runs **without** requiring trained `models/*.joblib` on disk.

## Tasks / Subtasks

- [x] Task 1: Author the coverage-enforcement logic in `src/calibration/` (AC: #1, #2, #4)
  - [x] Add `src/calibration/coverage.py` with `enforce_calibration_coverage(artifacts: dict) -> None`.
  - [x] Iterate `required_calibrated_heads()` from `src.routing.config`; for each head, pull `artifacts[head]["model"]` and check it is calibrated.
  - [x] **Detection:** treat a head as calibrated iff its `model` is a `sklearn.calibration.CalibratedClassifierCV` (chose `isinstance` for consistency with `test_calibration.py:69`; sklearn is not a D-18 forbidden module so the guard stays green).
  - [x] On a required-but-uncalibrated head, raise `RuntimeError` whose message names the head and the training command, mirroring the `_load_one_artifact` remediation style.
  - [x] If a required head key is missing from `artifacts` entirely, raise the same way (`artifacts.get(head)` → RuntimeError, not a cryptic `KeyError`).
- [x] Task 2: Wire enforcement into the canonical loader (AC: #1, #2, #3)
  - [x] Call `enforce_calibration_coverage(...)` inside `_load_default_artifacts()` in `src/routing/decide.py`, after the three `_load_one_artifact` calls, before the `return`. NOTE (review 2026-07-10): the server-startup path (`lifespan.py:140` → loader directly) hard-aborts uvicorn = true fail-closed; a direct `decide(artifacts=None)` caller (CLI/tests) instead has the raise caught by `decide()`'s V7 wrapper → **logged fallback**, not an abort. Safe either way (uncalibrated head never reaches thresholds), by design.
  - [x] Do **not** add any call on the per-turn path (AC #3). Confirmed `decide()` only calls `_load_default_artifacts()` when `artifacts is None`.
- [x] Task 3: Data-independent RED→GREEN test (AC: #1, #2, #4)
  - [x] Add `src/calibration/tests/test_coverage.py`. In-memory fake artifact dicts; no dependency on trained `models/*.joblib`.
  - [x] Compliant case: every required head's `model` is a real `CalibratedClassifierCV` → returns, no raise.
  - [x] Violation case: one required head's `model` is a bare `LogisticRegression` → raises, message contains that head name. Plus a missing-head case.
  - [x] Confirmed RED first (`ModuleNotFoundError` before `coverage.py` existed), then GREEN.
- [x] Task 4: Regression sanity (AC: #2, #3)
  - [x] Ran `uv run pytest src/calibration src/routing apps/api/tests/test_health.py` — all pass; D-18 import guard `test_decide_smoke.py` stays green.

### Review Findings

_Code review 2026-07-10 (3 adversarial layers: Blind Hunter, Edge Case Hunter, Acceptance Auditor). Auditor: all 4 ACs met, all guardrails honored, scope respected. 1 decision-needed, 1 patch, 5 dismissed as noise._

- [x] [Review][Decision] **RESOLVED (dismissed, accept-as-is 2026-07-10).** Fail-closed asymmetry between server startup and direct `decide(artifacts=None)` — the enforce raise inside `_load_default_artifacts()` is caught by `decide()`'s V7 `except Exception` (`src/routing/decide.py:566`) on the `artifacts is None` path (CLI `main()`, direct/test callers), producing a **logged** (`logger.exception` + error in signals) openrouter/auto fallback rather than a hard abort. The server startup path (`apps/api/lifespan.py:140` calls `_load_default_artifacts()` directly, no try/except) correctly hard-aborts uvicorn. The safety invariant (an uncalibrated head never reaches the policy thresholds) holds on **both** paths — the direct path bails to fallback before Stage 4/5 and surfaces the error. Decision: accept as-is — the production server fails closed hard; the dev-CLI path logs + degrades safely, and forcing the raise past the intentional T-01-RB V7 wrapper would fight a deliberate design. Spec Task-2 wording corrected below to say "logs + degrades" rather than "fail closed" for the direct-caller path.
- [x] [Review][Patch] **FIXED 2026-07-10.** Non-dict head value raises cryptic `AttributeError` instead of clean remediation [src/calibration/coverage.py:45] — `record.get("model")` only guarded `record is None`; a present-but-non-dict head value (raw estimator stored directly, list, etc.) `AttributeError`d past the crafted message. Fix: `model = record.get("model") if isinstance(record, dict) else None` → a non-dict value now hits the clean "loaded uncalibrated" remediation. Added `test_non_dict_head_value_raises_cleanly`.

## Dev Notes

**This is load-time ENFORCEMENT of the contract Story 2.1 declared. 2.1 authored the manifest (`CALIBRATION_COVERAGE` + `required_calibrated_heads()` in `src/routing/config.py`); this story makes it bite at load. Do NOT touch the eval gate — that is Story 2.3.**

### Current state (verified 2026-07-09, HEAD `c230dc5`)

- **The manifest already exists** — `src/routing/config.py:159-176`: `CALIBRATION_COVERAGE` (3 live heads, each `{required_calibrated: True, ece_threshold: 0.10}`) + `required_calibrated_heads() -> list[str]`. **Consume it. Do not re-hardcode the head list.**
- **Canonical loader** — `_load_default_artifacts()` at `src/routing/decide.py:135-175` loads the 3 heads via `_load_one_artifact` and returns `{task_type_classifier, agentic_intent_classifier, model_router, model_mapping}`. Each per-file load already fails closed on missing file (`FileNotFoundError`) / missing key (`KeyError`) — `src/routing/decide.py:120-132`. **Match that remediation-hint style.**
- **Lifespan** — `apps/api/lifespan.py:135-140` step 3 calls `app.state.artifacts = _load_default_artifacts()` **once** at startup. Wiring enforcement into `_load_default_artifacts()` (Task 2) means the lifespan fails closed with no `apps/api` edit needed. A raise here aborts uvicorn startup — that **is** the intended fail-closed behavior (an uncalibrated required head must never serve).
- **Per-turn path is safe** — `decide()` only calls `_load_default_artifacts()` when `artifacts is None` (`decide.py:332`). Turns pass the preloaded `app.state.artifacts`, so enforcement never runs per request (AC #3 / AD-3 satisfied by construction).
- **How calibration is detected today** — `src/calibration/tests/test_calibration.py:69,103` asserts `isinstance(artifacts["model"], CalibratedClassifierCV)`. Trained heads are calibrated via `CalibratedClassifierCV(FrozenEstimator(...))` in the train scripts (e.g. `src/task_classifier/train_agentic_intent.py:291`, `src/model_router/train_model_router.py:672`). Reuse the same `isinstance` check for consistency.
- **`src/calibration/` is an empty package** (`__init__.py` 0 lines) + a tests dir. Story 2.1 explicitly reserved it as the home for calibration *logic* (2.2/2.3), keeping the *declaration* in `config.py`. **`coverage.py` belongs here**, not in `config.py`.

### What this story changes vs. must preserve

- **Changes:** adds `src/calibration/coverage.py` (enforcement fn) + one call inside `_load_default_artifacts()` + one test module. Purely additive to behavior on the compliant path.
- **Must preserve:** the 3-head loaded shape, all tau/ECE constants, `decide()` behavior on the happy path, and the D-18 import guard. No threshold semantics change, no artifact retrain, no migration.

### Design decision to confirm (non-blocking; default chosen)

- **Enforcement call site = `_load_default_artifacts()` (recommended)** vs. the lifespan step 3 directly. The AC wording says "the FastAPI lifespan load to refuse," but `_load_default_artifacts()` is the canonical loader the lifespan *delegates to* — placing the check there gives fail-closed on every disk-load path (lifespan **and** CLI/test) with zero `apps/` edits and keeps AD-2 clean. If you'd rather scope the raise to the server only, call it in `apps/api/lifespan.py` after line 140 instead — but then a direct `decide(artifacts=None)` caller stays unguarded. Default: put it in the loader.

### Guardrails

- **AD-2 / D-18 import guard** (`src/routing/tests/test_decide_smoke.py`): `src.routing` must not import `apps.*` or any of `FORBIDDEN_MODULES` (`fastapi, httpx, requests, aiohttp, anthropic, openai, urllib3, flask, starlette, pydantic, google-generativeai`). `src.calibration` is a sibling util (not `apps`), and **sklearn is not forbidden** — importing `sklearn.calibration.CalibratedClassifierCV` into `src/calibration/coverage.py` and importing that module from `decide.py` keeps the guard green. Run `test_decide_smoke.py` to confirm (Task 4). If you'd rather add zero sklearn edge, use the `hasattr(model, "calibrated_classifiers_")` duck-type instead.
- **AD-3 (nothing blocks the request loop):** enforcement is load-time only. Never call it from the turn path.
- **AD-8 (self-contained artifact + loader remediation):** the raise must name the head and the fix command, like the existing `FileNotFoundError`/`KeyError` messages — a fresh checkout should read "which head, run what," not a stack trace.
- **AD-10 (quality-first):** metadata check only; do not reorder or reweight any routing decision.
- **Test data-independence:** build fake artifact dicts in-memory. Do **not** gate the new test on `models/*.joblib` existing (2.1's `test_no_regression` failure came from a data-dependent test needing a regenerated CSV — avoid that class of flake here).

### Previous-story intelligence (Story 2.1 — done, code-review passed 2026-07-09)

- 2.1 established the manifest home (`config.py`) + accessor (`required_calibrated_heads()`). **This story's single dependency — use the accessor.**
- 2.1's consistency test (`src/routing/tests/test_calibration_coverage.py`) currently forces every live head to `required_calibrated: True` (set-equality + all-required assertions). All 3 heads being required means enforcement simply iterates all 3 — **no conflict for 2.2**. A `ponytail:` comment on `test_all_live_heads_are_required_calibrated` flags that this over-constraint should be loosened only when `tier_router` is actually promoted onto the live path (still out of scope here — don't add `tier_router`/`embedding_router`).
- Scope is the **3 live heads** decide.py loads. `tier_router`/`embedding_router` are off the live path and deliberately excluded (tier_router is uncalibrated by Plan 05) — do not enforce against them.
- Test runner is `uv run pytest` (needs sandbox-off locally). RED-then-GREEN is the established rhythm.

### Project Structure Notes

- New: `src/calibration/coverage.py`, `src/calibration/tests/test_coverage.py`.
- Modified: `src/routing/decide.py` (one call inside `_load_default_artifacts()`).
- No `apps/` change (lifespan inherits enforcement via the loader), no artifact change, no migration.

### References

- [Source: src/routing/config.py#159-176] `CALIBRATION_COVERAGE` manifest + `required_calibrated_heads()` (Story 2.1 — the contract to enforce)
- [Source: src/routing/decide.py#120-132] `_load_one_artifact` — the AD-8 remediation-hint pattern to mirror
- [Source: src/routing/decide.py#135-175] `_load_default_artifacts` — enforcement call site (Task 2)
- [Source: src/routing/decide.py#296-332] `decide()` — only loads when `artifacts is None` (proves AC #3)
- [Source: apps/api/lifespan.py#135-140] lifespan step 3 — the once-at-startup load that inherits fail-closed
- [Source: src/calibration/tests/test_calibration.py#63-120] existing `isinstance(model, CalibratedClassifierCV)` calibration detection
- [Source: src/routing/tests/test_decide_smoke.py#22-55] D-18 `FORBIDDEN_MODULES` guard (sklearn not forbidden)
- [Source: _bmad-output/implementation-artifacts/2-1-declare-the-calibration-coverage-contract.md] Story 2.1 dev notes + review (calibration/ reserved for 2.2/2.3 logic)
- [Source: _bmad-output/planning-artifacts/epics.md#189-201] Epic 2 / Story 2.2 acceptance criteria
- [Source: _bmad-output/planning-artifacts/architecture/architecture-Prompt-Optimizer-2026-06-25/ARCHITECTURE-SPINE.md] AD-3 (no blocking on loop), AD-8 (self-contained artifacts + loader contract), AD-10 (quality-first)

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m]

### Debug Log References

- First GREEN run failed: toy calibration set (4 rows) < default 5-fold calibrator CV → `ValueError: n_splits=5 > n_samples=4`. Fixed by bumping the toy set to 10 rows (`[[0.],[1.]]*5`). Not a logic bug — test fixture sizing only.

### Completion Notes List

- Additive, fail-closed enforcement wired at the single canonical disk-load path (`_load_default_artifacts()`), so both FastAPI lifespan (step 3) and any `decide(artifacts=None)` caller inherit it with zero `apps/` edits (chose the recommended default call site).
- Enforcement consumes `required_calibrated_heads()` (the 2.1 manifest) — no re-hardcoded head list; adding a head to the manifest auto-covers it.
- Detection = `isinstance(model, CalibratedClassifierCV)`, matching `test_calibration.py`. sklearn is not a D-18 forbidden module; `test_decide_smoke.py` stays green (verified).
- Raise names the offending head + its training command only; leaks no keys/paths (AC #1). Missing head and uncalibrated head both raise `RuntimeError` with the same remediation style (mirrors `_load_one_artifact`).
- AC #3 satisfied by construction: enforcement lives only in the loader; the per-turn path passes preloaded `app.state.artifacts` and never re-invokes it.
- Full suite: `uv run pytest src/calibration src/routing apps/api/tests/test_health.py` → all pass (68 in the broad run; 15 in the focused coverage+smoke+health run, none skipped).

### File List

- `src/calibration/coverage.py` (new) — `enforce_calibration_coverage()` + `_remediation()`
- `src/calibration/tests/test_coverage.py` (new) — data-independent RED→GREEN tests (compliant / uncalibrated / missing head)
- `src/routing/decide.py` (modified) — import + one enforcement call inside `_load_default_artifacts()` before return

## Change Log

- 2026-07-09: Story 2.2 implemented — load-time calibration-coverage enforcement (fail-closed) in `src/calibration/coverage.py`, wired into `_load_default_artifacts()`. Additive; no threshold/routing/artifact changes. Status → review.
- 2026-07-10: Code review (3 adversarial layers) — all 4 ACs confirmed met. 1 decision-needed dismissed (server startup fails closed hard; direct `decide(artifacts=None)` logs+degrades via the V7 wrapper — safe by design; spec wording corrected). 1 patch applied: non-dict head value now hits clean remediation instead of `AttributeError` + `test_non_dict_head_value_raises_cleanly`. 16 tests green. Status → done.
