---
baseline_commit: c230dc53e5c512ebc454b4a2302dbb29107e49c6
---

# Story 2.3: Add a calibration-coverage check to the eval gate

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the builder,
I want the evaluation / no-regression gate to verify calibration coverage and per-head ECE against the Story 2.1 manifest,
so that a retrain or model swap that breaks calibration (an uncalibrated required head, or a calibrated head whose ECE drifts past its threshold) is caught at the gate before promotion — closing the loop that 2.1 declared and 2.2 enforced at load.

## Acceptance Criteria

1. **The gate reports per-required-head calibration status and ECE vs. threshold.**
   **Given** the loaded candidate heads and the `CALIBRATION_COVERAGE` manifest (Story 2.1)
   **When** `evaluate_routing.py --check` runs
   **Then** it reports, for each head in `required_calibrated_heads()`, whether it is calibrated (a `CalibratedClassifierCV`) and its measured canary ECE alongside that head's `ece_threshold` from the manifest
   **And** the report is printed (mirrors the existing "Per-stage ECE" block at `src/evaluation/evaluate_routing.py:785-788`).

2. **The gate exits non-zero on any coverage violation.**
   **Given** a candidate set where a required head is uncalibrated OR a required head's ECE exceeds its manifest `ece_threshold`
   **When** `--check` runs
   **Then** `evaluate_check(...)` returns `(False, [...])` and the CLI exits `1` with each failure named (which head, and whether it was "uncalibrated" or "ece=X > threshold=Y")
   **And** a fully-compliant set still returns `(True, [])` and exits `0` — with today's calibrated heads at ECE ≤ 0.10 the pass/fail outcome is unchanged from the current gate (no threshold semantics change; all manifest thresholds are 0.10 today).

3. **The per-head ECE threshold comes from the manifest, not the global constant.**
   **Given** Story 2.1 declared a per-head `ece_threshold` in `CALIBRATION_COVERAGE`
   **When** the gate checks a required head's ECE
   **Then** it compares against that head's manifest `ece_threshold` (via a `src.routing.config` accessor), not the module-level global `ECE_THRESHOLD`
   **And** the calibration-status detection reuses the Story 2.2 logic in `src/calibration/coverage.py` (the same `isinstance(model, CalibratedClassifierCV)` check) — the detection rule is not re-implemented a third time.

4. **The check is callable standalone and importable for the FR-15 no-regression gate (Epic 3).**
   **Given** Epic 3's promotion gate will consume this check
   **When** it is invoked
   **Then** `evaluate_check(metrics)` remains a pure function over a metrics dict (no artifact/disk I/O inside it), importable by Epic 3, and a data-independent unit test proves both directions (compliant passes; one-uncalibrated and one-ECE-over-threshold each fail, naming the head) **without** requiring trained `models/*.joblib` or a regenerated canary CSV — extending the existing `test_check_flag_*` pattern at `src/evaluation/tests/test_evaluate_routing.py:233-286`.

## Tasks / Subtasks

- [x] Task 1: Add a per-head ECE-threshold accessor + a non-raising calibration-status reader (AC: #1, #3)
  - [x] `ece_threshold_for(head: str) -> float` added in `src/routing/config.py` beside `required_calibrated_heads()` (returns `float(CALIBRATION_COVERAGE[head]["ece_threshold"])`). No new import — D-18 preserved.
  - [x] Extracted the isinstance detection into shared `_is_calibrated(record)` in `src/calibration/coverage.py`; `enforce_calibration_coverage` (2.2) now calls it, and new `calibration_status(artifacts) -> dict[str, bool]` reuses it — one predicate, no duplication. Missing/non-dict head → `False` (never raises).
- [x] Task 2: Populate calibration status into the metrics dict in `run()` (AC: #1, #4)
  - [x] `run()` metrics dict now includes `"per_head_calibrated": calibration_status(artifacts)`. All artifact I/O stays in `run()`; `evaluate_check` remains pure.
  - [x] Confirmed `per_stage_ece` keys == manifest head names, so no name-mapping shim needed.
- [x] Task 3: Extend `evaluate_check(metrics)` to enforce coverage (AC: #2, #3)
  - [x] Added a per-required-head loop: uncalibrated → `"{head} uncalibrated"`; calibrated but ECE over `ece_threshold_for(head)` → `"{head} ece=X > threshold=Y"`.
  - [x] Fail-closed: required head absent from `per_head_calibrated` → `"{head} could not confirm calibration (no status in metrics)"`; no ECE recorded → `"{head} no ECE recorded"`.
  - [x] Chose the recommended split: required heads use the manifest threshold; the global `ECE_THRESHOLD` loop now only covers non-manifest stages (none today) → no double-reporting. Commented.
  - [x] Exit codes `0/1/2` in `main()` untouched; calibration failures surface as exit `1`.
- [x] Task 4: Update the print/report block (AC: #1)
  - [x] Added a "Calibration coverage (required heads, per-head manifest threshold)" report block after the per-stage ECE print, showing `calibrated=yes/no`, `ece`, `threshold`, and a flag. No CSV schema change.
- [x] Task 5: Data-independent tests (AC: #2, #3, #4)
  - [x] Extended the three `test_check_flag_*` cases with `per_head_calibrated` (via `_all_calibrated()` helper) and added `test_check_flag_fails_when_required_head_uncalibrated` + `test_check_flag_fails_closed_when_calibration_status_missing`. (ECE-over is the existing `test_check_flag_fails_when_any_ece_above_threshold`, now asserting the ECE message.)
  - [x] Added `test_calibration_status_all_calibrated` + `test_calibration_status_flags_uncalibrated_and_missing` in `test_coverage.py`, reusing 2.2's toy fixtures. No trained artifacts.
  - [x] All green without `models/*.joblib` or a regenerated canary CSV.
- [x] Task 6: Regression sanity (AC: #2, #4)
  - [x] `uv run pytest src/calibration src/evaluation src/routing` → **73 passed, 15 skipped, 5 failed**. All 5 failures are pre-existing `test_no_regression.py` `KeyError: 'origin_query'` data-dependent flakes — verified identical on the stashed baseline (my changes removed), so NOT a 2.3 regression. `test_check_flag_*`, `test_coverage.py`, `test_calibration_coverage.py`, and D-18 `test_decide_smoke.py` all stay green. The artifact-gated `run()` e2e tests skip cleanly (15 skips).

### Review Findings

_Code review 2026-07-10 (3 adversarial layers). Acceptance Auditor: PASS — all 4 ACs met, all guardrails preserved, scope respected. 0 decision-needed, 1 patch, 3 defer, 9 dismissed as noise/safe-by-construction._

- [x] [Review][Patch] **FIXED 2026-07-10.** Duplicate `calibration_status(artifacts)` call in `run()` [src/evaluation/evaluate_routing.py:836] — was computed at line 795 for the print block and recomputed at 836 for the metrics dict. Now reuses the `per_head_calibrated` local. Tests green.
- [x] [Review][Defer] ECE-proxy deflation is fail-open (pre-existing) [src/evaluation/evaluate_routing.py:539-590,220] — when `_stage_predict_proba` throws, `run()` substitutes `prob=0.0`, which lands in no ECE bin and *lowers* a head's canary ECE, so a broken head could pass the ECE threshold. This is a pre-existing property of the ECE proxy (documented in `run()`'s own "proxy for y_true" note) and is unchanged by 2.3 — the old gate compared the same ECE to the global threshold. 2.3 actually strengthens the gate by adding the calibration-*status* check (robust `isinstance`, not subject to deflation). Deferred: eval-harness/Epic-3 concern, not caused by this change.
- [x] [Review][Defer] `evaluate_check` does not guard NaN ECE [src/evaluation/evaluate_routing.py:889] — `NaN > threshold` is False → a NaN ECE passes. Confirmed NOT reachable via `run()` today; latent only for Epic 3's reuse of `evaluate_check` as the FR-15 gate. Deferred to Epic 3 (a one-line `math.isnan` fail-closed guard) rather than adding speculative code now (scope fence: don't build Epic 3 surface here).
- [x] [Review][Defer] `main()` conflates infra errors with gate-fail exit 1 (pre-existing) [src/evaluation/evaluate_routing.py:953-955] — only `FileNotFoundError` maps to exit 2; any other `run()` exception exits 1 with a traceback, indistinguishable from a legitimate gate failure. Pre-existing in `main()`, untouched by 2.3.

## Dev Notes

**This story CLOSES Epic 2: 2.1 declared the manifest (`CALIBRATION_COVERAGE` + `required_calibrated_heads()`), 2.2 enforced it at artifact load (fail-closed), and 2.3 enforces it at the eval/no-regression gate so a bad retrain is caught before promotion. Scope is the eval gate ONLY — do not touch the load-time enforcement (2.2, done) or add new heads to the manifest (2.1).**

### Current state (verified 2026-07-10, HEAD `c230dc5` + uncommitted Story 2.2)

- **The eval gate already exists** — `src/evaluation/evaluate_routing.py`. `--check` mode (`main()`, lines 845-916) runs the canary via `run()` and applies `evaluate_check(metrics)` (lines 821-837), exiting `0`/`1`/`2`. CI (`.github/workflows/ci.yml`) is gated on it (docstring lines 27-29).
- **`evaluate_check(metrics)` is a PURE function** over a metrics dict — no disk I/O. It is already unit-tested data-independently with hand-built `good_metrics`/`bad_metrics` dicts (`test_evaluate_routing.py:233-286`). **This is the AC #4 contract and the established test pattern — preserve it. Add the calibration inputs to the metrics dict, keep the function pure.**
- **`run()` returns the metrics dict** (`evaluate_routing.py:807-813`) with `backend_accuracy`, `per_stage_ece` (dict keyed by head name), `low_confidence_rate`, `fallback_recall`, `n_rows`. It already loads the artifacts at line 443 — the natural place to compute `per_head_calibrated` (Task 2).
- **`per_stage_ece` keys == manifest head names** — `task_type_classifier`, `agentic_intent_classifier`, `model_router` (see `per_stage_records`, lines 456-460, and the manifest `CALIBRATION_COVERAGE`, `config.py:159-163`). No name-mapping shim needed.
- **The manifest (Story 2.1)** — `src/routing/config.py:159-176`: `CALIBRATION_COVERAGE` = 3 heads each `{required_calibrated: True, ece_threshold: 0.10}`; `required_calibrated_heads()` returns the sorted required-head list. **Consume both. Add an `ece_threshold_for(head)` accessor here — do not read the dict directly from the gate and do not re-hardcode 0.10.**
- **Calibration detection lives in `src/calibration/coverage.py` (Story 2.2)** — `enforce_calibration_coverage()` uses `isinstance(model, CalibratedClassifierCV)` (with a hardened non-dict guard). **Reuse it: extract the per-head "is calibrated?" predicate and add a non-raising `calibration_status()` reader for the gate. This is the third consumer of the same detection rule — centralize it, do not copy the `isinstance` a third time.**
- **Global `ECE_THRESHOLD = 0.10`** (`evaluate_routing.py:111`) is what `evaluate_check` compares every stage against today. 2.3 shifts required heads onto the per-head manifest threshold. Since all manifest thresholds are 0.10, **today's pass/fail outcome does not change** (AC #2) — this is a plumbing change that makes the threshold per-head-tunable later, exactly as 2.1's manifest comment intended (`config.py:150-152`).

### What this story changes vs. must preserve

- **Changes:** `config.py` (+1 accessor), `src/calibration/coverage.py` (+1 non-raising reader + shared predicate), `evaluate_routing.py` (`run()` adds `per_head_calibrated` to metrics; `evaluate_check` adds the coverage loop; one print block), and the two test files (+cases).
- **Must preserve:** exit codes `0/1/2`; the D-16 CSV/PNG output schemas (do not add/rename columns); `evaluate_check` purity (no disk I/O); the existing `test_check_flag_*` semantics (enrich the fixtures, don't invert expectations); `test_no_regression.py` behavior; 2.2's load-time enforcement and its `test_coverage.py`; the D-18 import guard. No artifact retrain, no manifest head changes, no CI-workflow edit.

### Design decisions to confirm (defaults chosen)

- **Calibration-status reader in `coverage.py` (recommended)** vs. computing `isinstance` inline in `evaluate_routing.py`. Putting it in `coverage.py` keeps the detection rule in one module (already the home per 2.1/2.2) and lets Epic 3 reuse it. Default: add `calibration_status()` to `coverage.py`.
- **Per-head threshold vs. keep global for non-manifest stages.** All three evaluated stages are manifest heads, so the global `ECE_THRESHOLD` becomes vestigial for `--check`. Recommended: required heads use `ece_threshold_for(head)`; keep the global constant as a documented default for any future stage not in the manifest, rather than deleting it (smaller diff, no CI docstring churn). Comment the choice.
- **Missing-data handling = fail-closed.** If `run()` somehow yields a required head with no calibration status or no ECE, `evaluate_check` should FAIL, not pass. Matches Epic 2's posture and prevents a silent green gate on incomplete metrics.

### Guardrails

- **AD-8 (self-contained + clear remediation):** each failure string names the head and the reason ("uncalibrated" / "ece=X > threshold=Y") so an operator reads "which head, what's wrong" — same spirit as 2.2's load-time messages and the existing `evaluate_check` failure strings (lines 826-834).
- **AD-10 (quality-first):** this is a gate/report change only — it does not alter any routing decision, threshold value, or `decide()` behavior. The manifest thresholds are unchanged (still 0.10).
- **Data-independence:** the enforcing logic (`evaluate_check`, `calibration_status`) must be unit-testable with synthetic dicts / toy models — NO dependency on trained `models/*.joblib` or a regenerated canary CSV. This is the lesson from 2.1 (a data-dependent test flaked) and the pattern 2.2 followed. The end-to-end `run()` tests may remain artifact-gated and skip cleanly.
- **Don't reach into Epic 3:** "consumed by the FR-15 no-regression gate" means keep `evaluate_check` importable and pure. Do NOT build the Epic 3 promotion gate here — only ensure this check is a clean, importable building block.
- **D-18 import guard:** `evaluate_routing.py` already imports sklearn + `src.routing.*`; adding `from src.calibration.coverage import calibration_status` is fine (sibling util, sklearn allowed). `src.calibration` and `src.routing.config` must not gain forbidden imports.

### Previous-story intelligence (Story 2.2 — done, code-review passed 2026-07-10)

- 2.2 built `src/calibration/coverage.py` with `enforce_calibration_coverage(artifacts)` (raises) using `isinstance(model, CalibratedClassifierCV)`, and a hardened guard treating a **missing head or present-but-non-dict record as uncalibrated** (not a cryptic error). 2.3's `calibration_status()` should apply the same guard and share the predicate.
- 2.2's tests (`src/calibration/tests/test_coverage.py`) build in-memory fake artifacts with a toy `CalibratedClassifierCV(FrozenEstimator(LogisticRegression().fit(_X,_Y)), method="sigmoid")` on **10 toy rows** (`[[0.],[1.]]*5`) so the default 5-fold calibrator CV is satisfied. **Reuse those fixtures** for the `calibration_status` test — don't invent a new toy-model recipe.
- 2.2 code review dismissed an "empty manifest → no-op" concern because a runtime head-list floor would violate AC #4's no-hardcode rule and 2.1's `test_calibration_coverage.py` consistency test already forbids emptying the manifest. Same reasoning applies here — trust `required_calibrated_heads()`; do not add a hardcoded floor.
- Test runner is `uv run pytest` (needs sandbox-off locally). RED-then-GREEN is the established rhythm. sklearn is 1.8.0 (`FrozenEstimator` in `sklearn.frozen`).

### Project Structure Notes

- Modified: `src/routing/config.py` (+ `ece_threshold_for` accessor), `src/calibration/coverage.py` (+ `calibration_status` reader + shared predicate), `src/evaluation/evaluate_routing.py` (`run()` metrics + `evaluate_check` + report print).
- Tests: `src/evaluation/tests/test_evaluate_routing.py` (extend `test_check_flag_*`), `src/calibration/tests/test_coverage.py` (add `calibration_status` case).
- No new files strictly required; no `apps/` change, no artifact change, no CI-workflow change, no migration.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.3] Story 2.3 user story + acceptance criteria (the source of truth for scope)
- [Source: src/evaluation/evaluate_routing.py#821-837] `evaluate_check(metrics)` — the pure gate function to extend (Task 3)
- [Source: src/evaluation/evaluate_routing.py#807-813] `run()` metrics dict — where to add `per_head_calibrated` (Task 2)
- [Source: src/evaluation/evaluate_routing.py#785-788] "Per-stage ECE" print block — the report to extend (Task 4)
- [Source: src/evaluation/evaluate_routing.py#100-111] `BACKEND_ACCURACY_THRESHOLD` / `ECE_THRESHOLD` module constants
- [Source: src/evaluation/evaluate_routing.py#845-916] `main()` `--check` — exit-code contract (0/1/2) to preserve
- [Source: src/evaluation/tests/test_evaluate_routing.py#233-286] `test_check_flag_*` — the data-independent synthetic-metrics test pattern to extend (AC #4)
- [Source: src/evaluation/tests/test_no_regression.py#32-54] canary-set ECE vs. training-set ECE distinction — do not conflate; must stay green
- [Source: src/routing/config.py#159-176] `CALIBRATION_COVERAGE` + `required_calibrated_heads()` (Story 2.1) — add `ece_threshold_for` here
- [Source: src/calibration/coverage.py] Story 2.2 `enforce_calibration_coverage` + `isinstance(CalibratedClassifierCV)` detection — reuse for `calibration_status`
- [Source: src/calibration/tests/test_coverage.py] 2.2 toy-model fixtures to reuse
- [Source: _bmad-output/implementation-artifacts/2-2-enforce-coverage-at-artifact-load-fail-closed.md] Story 2.2 dev notes + review (calibration/ detection home; fail-closed posture; data-independence lesson)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-Prompt-Optimizer-2026-06-25/ARCHITECTURE-SPINE.md] AD-8 (self-contained + remediation), AD-10 (quality-first)

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m]

### Debug Log References

- Full-suite run showed 5 `test_no_regression.py` failures (`KeyError: 'origin_query'`). Verified pre-existing: `git stash`-ed the 2.3 tracked changes and re-ran → identical failure on baseline `c230dc5`. Root cause is a data-dependent test reading a training CSV without the `origin_query` column (the 2.1-documented flake class) — out of scope for 2.3, not introduced by it.
- Repo pytest config uses `maxfail=1`; used `--maxfail=50` to see the full pass/fail picture.

### Completion Notes List

- Closes Epic 2's calibration-coverage arc: 2.1 declared the manifest → 2.2 enforced at load → 2.3 enforces at the eval gate.
- `evaluate_check` stays a **pure function** over the metrics dict (AC #4): `run()` computes `per_head_calibrated` where the artifacts are already loaded; the gate function does zero disk I/O, so Epic 3's FR-15 gate can import it directly.
- Detection rule centralized: `_is_calibrated()` is now the single isinstance predicate shared by `enforce_calibration_coverage` (raising, 2.2) and `calibration_status` (reporting, 2.3) — third consumer, no third copy (AC #3).
- Per-head threshold via `ece_threshold_for()` (AC #3). All manifest thresholds are 0.10 today, so the pass/fail outcome is unchanged from the prior gate (AC #2) — this is plumbing that makes thresholds per-head-tunable later.
- Fail-closed on incomplete metrics: a required head with no calibration status or no ECE is a failure, not a silent green gate.
- Global `ECE_THRESHOLD` loop scoped to non-manifest stages only → required heads are checked once against the manifest, no double-reporting.
- Exit codes `0/1/2` and all D-16 CSV/PNG schemas preserved; no `apps/` change, no artifact retrain, no CI-workflow edit, no migration.
- Tests: 73 passed / 15 skipped / 5 pre-existing data-dependent failures (see Debug Log). New: 2 in `test_coverage.py`, 2 in `test_evaluate_routing.py`, plus 3 existing `test_check_flag_*` enriched.

### File List

- `src/routing/config.py` (modified) — added `ece_threshold_for(head)` accessor
- `src/calibration/coverage.py` (modified) — extracted shared `_is_calibrated()`; added non-raising `calibration_status()`
- `src/evaluation/evaluate_routing.py` (modified) — import calibration/config helpers; `per_head_calibrated` in `run()` metrics; per-head coverage loop in `evaluate_check`; calibration-coverage report block
- `src/evaluation/tests/test_evaluate_routing.py` (modified) — `_all_calibrated()` helper; enriched 3 `test_check_flag_*`; +2 coverage-failure tests
- `src/calibration/tests/test_coverage.py` (modified) — +2 `calibration_status()` tests

## Change Log

- 2026-07-10: Story 2.3 implemented — calibration-coverage check added to the eval gate. `evaluate_check` now consumes the 2.1 manifest (`required_calibrated_heads()` + `ece_threshold_for()`) and per-head calibration status, failing closed on uncalibrated/over-ECE/missing-status required heads. Detection centralized in `_is_calibrated()`; new non-raising `calibration_status()` reader. Additive; no threshold-value/routing/artifact change. Status → review.
- 2026-07-10: Code review (3 adversarial layers) — Auditor PASS on all 4 ACs. 1 patch applied (removed a duplicate `calibration_status` call in `run()`); 3 items deferred (pre-existing ECE-proxy deflation, NaN-ECE guard for Epic 3 reuse, `main()` exit-code conflation → logged in deferred-work.md); 9 dismissed. Status → done.
