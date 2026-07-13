---
baseline_commit: b099f89b059f07959a8c0872314224edea9d760b
---

# Story 3.3: Gate promotion behind data-volume + regression + calibration

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the builder,
I want promotion of the candidate `model_router` head to live blocked unless the real-data threshold, the FR-15 no-regression gate, and Epic 2's calibration-coverage check all pass,
so that the feedback→retrain loop never overwrites a live routing head on absent data or ships a regression — closing the north-star mechanism honestly.

## Acceptance Criteria

1. **Three gates, all must pass to promote.**
   **Given** the candidate `models/staging/model_router.joblib` (Story 3.2) and the current live baselines in `models/`
   **When** the promotion step runs
   **Then** it promotes the candidate to live **only if** all three gates pass:
   - **G1 — Data volume:** `routing_feedback.jsonl` holds ≥ `MIN_REAL_RATED_TURNS` (100) **real** rated turns (real = `message_id` not `seed-*`, `sentiment ∈ {up, down}` after `cleared`-supersede dedup).
   - **G2 — FR-15 no-regression:** the candidate, evaluated through the existing routing-canary pipeline, passes `evaluate_check(...)` (absolute thresholds) **and** does not regress the live baseline's `backend_accuracy` (candidate ≥ live − `REGRESSION_TOLERANCE`).
   - **G3 — Calibration coverage (Epic 2):** the candidate bundle's `model_router` is calibrated per `calibration_status(...)` and its ECE ≤ the manifest threshold.

2. **Fail-closed with a named report.**
   **When** any gate fails
   **Then** the step holds the candidate (promotes nothing, live `models/*.joblib` unchanged) and emits a report naming each failed gate and why (e.g. `G1 FAILED: 0/100 real rated turns`).

3. **Dry-run outcome at 0 feedback.**
   **Given** today's data (0 real feedback events)
   **When** the step runs
   **Then** G1 fails, the step runs to completion, reports "promoted nothing", makes **no** change under `models/`, and exits cleanly (a valid dry-run outcome, not a crash).

4. **Atomic, reversible promotion + data-independent test.**
   **When** all gates pass
   **Then** the current live `models/model_router.joblib` is backed up before being overwritten, and the staged bundle replaces it atomically (self-contained 6-key bundle, loadable by `decide.py`'s loader).
   **And** a data-independent unit test proves: (a) all-gates-pass → live file is replaced + backup exists; (b) each single failing gate → live file byte-unchanged + that gate named in the report — all in `tmp_path`, no live `models/` write, no real feedback file.

## Tasks / Subtasks

- [x] Task 1: Create the promotion orchestration (AC: #1, #2)
  - [x] Add `src/model_router/promote_candidate.py` — mirror `retrain_candidate.py`'s shape exactly: module docstring with run-from-root example, `argparse` CLI, `main(argv: list[str] | None = None) -> int`, `if __name__ == "__main__": sys.exit(main())`. NOT interactive `input()`.
  - [x] CLI flags (defaults in parens): `--staging-dir` (`models/staging`), `--models-dir` (`models/`), `--canary-input` (`CANARY_CSV` from `evaluate_routing`), `--routing-feedback` (`DEFAULT_FEEDBACK` from `build_retraining_dataset`), `-v/--verbose` (count, default 1). Reuse the same `_setup_logging` pattern.
  - [x] Structure: evaluate **all three gates**, collect `(gate, passed, reason)` for each, promote iff all pass, and ALWAYS print a report naming any failed gate(s). Do NOT short-circuit past reportable gates unless an input is missing.
  - [x] Exit codes: `0` = clean run (promoted OR held — the report says which); `2` = error (staging candidate missing, canary missing). See Saved Question SQ-1 on whether "held" needs a distinct code.
- [x] Task 2: G1 data-volume gate (AC: #1, #3)
  - [x] Count **real** rated turns from `routing_feedback.jsonl`. Reuse `stream_jsonl` (`src/data/build_retraining_dataset.py:92`) and the **existing** `cleared`-supersede dedup already in `build_retraining_dataset.py` — do NOT reimplement dedup. Real = `message_id` present and not starting with `"seed-"`, final `sentiment ∈ {up, down}`.
  - [x] Define `MIN_REAL_RATED_TURNS = 100` as a module constant with a comment citing the SPEC recalibration trigger. Gate passes iff `real_count >= MIN_REAL_RATED_TURNS`.
  - [x] Missing/empty feedback file → `real_count = 0` (not an error); G1 fails cleanly.
- [x] Task 3: G2 FR-15 no-regression gate (AC: #1) — **the core integration**
  - [x] Evaluate the candidate through the EXISTING canary pipeline. Make `evaluate_routing.run(...)` accept an optional artifacts override (smallest possible change — see Dev Notes "The G2 seam"), then: build `candidate_artifacts = {task_type_classifier: live, agentic_intent_classifier: live, model_router: <staged bundle>, model_mapping: live}` and call `run(canary, tmp_output_dir, artifacts=candidate_artifacts)` → candidate metrics; call `run(canary, tmp_output_dir2)` (live) → baseline metrics.
  - [x] Gate passes iff `evaluate_check(candidate_metrics)[0] is True` **AND** `candidate_metrics["backend_accuracy"] >= baseline_metrics["backend_accuracy"] - REGRESSION_TOLERANCE` (define `REGRESSION_TOLERANCE`, e.g. `0.02`). Reuse `evaluate_check` verbatim — it already applies the Story 2.3 per-head thresholds. Do NOT reimplement thresholds.
  - [x] Write the eval outputs to a throwaway dir (e.g. under the output/`tmp` dir), never polluting `evaluation/routing/` or `models/`.
- [x] Task 4: G3 calibration-coverage gate (AC: #1)
  - [x] Load the staged bundle and call `calibration_status({"model_router": staged_bundle})` (`src/calibration/coverage.py:63`). Gate passes iff `result["model_router"] is True` AND the candidate's measured `model_router` ECE (from G2's candidate metrics `per_stage_ece["model_router"]`) `<= ece_threshold_for("model_router")` (`src/routing/config.py:179`). Reuse both — do NOT hardcode 0.10.
  - [x] Note: G2 and G3 both key off the candidate's `model_router` ECE; compute once, reuse.
- [x] Task 5: Atomic + reversible promotion (AC: #4)
  - [x] Only after all three gates pass: back up the current live `models/model_router.joblib` before overwriting (reuse `snapshot_baselines.py`'s backup convention if it exposes a callable; else copy to a `.bak`/timestamped path under `models/`). Then write the staged bundle to `models/model_router.joblib` atomically (write to a temp path in the same dir, then `os.replace`).
  - [x] This is the ONE module allowed to write live `models/` — but only on the all-pass path. Guard: if `--models-dir` resolves to the staging dir (or vice-versa) refuse (mirror the `os.path.samefile` guard added to `retrain_candidate.py` in the 3.2 review).
  - [x] Promote ONLY `model_router` (the only feedback-retrained head — Story 3.2 D1). Do not touch `task_type_classifier`/`agentic_intent_classifier`.
- [x] Task 6: Data-independent tests (AC: #2, #3, #4)
  - [x] Add `src/model_router/tests/test_promote_candidate.py`. Build everything in `tmp_path`: a tiny staged candidate (reuse the 3.2 chain `seed_synthetic_feedback` → `build_retraining_dataset` → `retrain_candidate` into `tmp_path/staging`), a `tmp_path/models` with placeholder live heads, and a tiny feedback JSONL.
  - [x] Cover: (a) all-gates-pass → `tmp_path/models/model_router.joblib` replaced + backup exists + report says promoted; (b) G1 fail (0 real turns) → live byte-unchanged, report names G1, exit 0; (c) G2 fail and (d) G3 fail (inject an uncalibrated/degraded candidate) → live unchanged, that gate named. Assert live-dir bytes are unchanged on every hold path.
  - [x] No dependency on the real `~/.prompt-optimizer/...routing_feedback.jsonl`, real `models/`, or a materialized benchmark CSV. RED-then-GREEN.
- [x] Task 7: Regression + guard sanity (AC: all)
  - [x] Run `uv run pytest src/model_router src/evaluation src/data eval/tests/test_import_graph.py`. New tests pass; the D-18 import-graph guard stays green (the module may import `src.evaluation`, `src.calibration`, `src.routing.config`, `src.data.*`, sklearn/joblib — but NOT `eval`/`inspect_ai`/`apps.*`). Confirm live `models/` is byte-unchanged by the test run.
  - [x] If `evaluate_routing.run(...)` was changed to accept the artifacts override, confirm existing `src/evaluation` tests (`test_evaluate_routing*`) still pass — the override must be backward-compatible (default `None` → `_load_artifacts()`).

## Dev Notes

**Epic 3 = feedback→retrain loop, gated. 3.1 assembled the dataset; 3.2 retrained a calibrated candidate into `models/staging/`; 3.3 is THE GATE — the feature. It decides promotion behind three gates and, at 0 real feedback, promotes nothing. Do NOT retrain here (3.2 did), do NOT build new eval metrics (reuse `evaluate_routing`), do NOT touch the other two heads.**

### The three gates — exact reuse map (do NOT reinvent any of this)

| Gate | Reuse | Location |
|------|-------|----------|
| G1 volume | `stream_jsonl`, `DEFAULT_FEEDBACK`, existing `cleared`-dedup | `src/data/build_retraining_dataset.py:51,92` |
| G2 no-regression | `run(canary, out)` → metrics; `evaluate_check(metrics) -> (bool, failures)` | `src/evaluation/evaluate_routing.py:428,849` |
| G3 calibration | `calibration_status(artifacts) -> {head: bool}`; `required_calibrated_heads()`, `ece_threshold_for(head)` | `src/calibration/coverage.py:63`; `src/routing/config.py:166,179` |

- `evaluate_check` is a **pure function over a metrics dict** (`evaluate_routing.py:849`) — no I/O — explicitly built "reusable by Epic 3's FR-15 no-regression gate." It already enforces `backend_accuracy >= 0.65` and, per required head, calibrated-status + per-head ECE ≤ manifest threshold (Story 2.3). Feed it the candidate's metrics dict; do not duplicate its logic.
- `calibration_status` is the **non-raising** coverage reporter (returns `{head: is_calibrated}`); a head is calibrated iff `bundle["model"]` is a `CalibratedClassifierCV` (`coverage.py:30`). Use it, NOT the raising `enforce_calibration_coverage` (that one is decide.py's load-time fail-closed guard).

### The G2 seam (the one real integration decision)

`run(canary_path, output_dir)` currently calls `_load_artifacts()` internally (hardcoded live paths, `evaluate_routing.py:378`) then `decide(prompt, artifacts=artifacts)` per canary row. To evaluate the **candidate**, the smallest reuse-preserving change is to add an optional param:

```python
def run(canary_path: str, output_dir: str, artifacts: dict | None = None) -> dict:
    ...
    if artifacts is None:
        artifacts = _load_artifacts()   # unchanged default → backward-compatible
    ...
```

Then the gate builds `candidate_artifacts` = live `task_type_classifier` + live `agentic_intent_classifier` + **staged** `model_router` + live `model_mapping`, and calls `run(canary, tmp_out, artifacts=candidate_artifacts)`. `decide()` already accepts `artifacts=` so no brain change is needed. This reuses ALL metric computation (per-stage ECE, backend accuracy, `per_head_calibrated`) and returns a dict `evaluate_check` consumes directly. **Prefer this over recomputing metrics inline** (recomputation would duplicate ~400 lines and drift from the CI gate). If you reject editing `evaluate_routing`, the fallback is a thin wrapper that temporarily copies the candidate into a scratch models dir and points `_load_artifacts` there — messier; flagged as SQ-2.

- "No-regression" here = candidate passes the same absolute gate CI runs on live (`evaluate_check`) AND does not drop live `backend_accuracy` (the SM-2 baseline metric) beyond `REGRESSION_TOLERANCE`. Compute the live baseline by calling `run(canary, tmp_out2)` with no override.

### G1 volume — count real rated turns

- Feedback lives at `DEFAULT_FEEDBACK` = `$PROMPT_OPTIMIZER_HOME/.planning/data/routing_feedback.jsonl` (or `~/.prompt-optimizer/...`), `build_retraining_dataset.py:51`. `stream_jsonl` (`:92`) handles a missing file as an empty iterator.
- **Real** = `message_id` not `seed-*` (synthetic seed uses `seed-%05d`, `seed_synthetic_feedback.py:73`) and final `sentiment ∈ {up, down}`. `cleared` supersedes an earlier rating for the same `message_id` — reuse `build_retraining_dataset.py`'s existing supersede dedup so G1 counts the same rows the retrain would train on. Simplest correct path: run the 3.1 assembler over the real feedback and count rows whose `message_id` is non-seed; or reuse its dedup helper directly. Do not hand-roll a second dedup.
- Today: 0 real events → G1 fails `0/100`. This is AC #3's expected dry-run.

### Promotion mechanics (AC #4)

- No promote/copy-to-live helper exists yet — this story creates it. Live path: `models/model_router.joblib` (`config.py:130` `DEFAULT_ARTIFACT_PATHS`).
- Reversible: back up current live `model_router.joblib` before overwrite. `models/uncalibrated/` (`snapshot_baselines.py:47`) holds the *pre-calibration* baseline — do NOT clobber it; use a distinct promotion backup (e.g. `models/model_router.joblib.bak` or a timestamped copy). Atomic: write to a temp file in `models/` then `os.replace(tmp, live)` (same-filesystem atomic rename).
- Promoted artifact must satisfy `decide.py`'s loader: required keys `("model","vectorizer","scaler","label_encoder","feature_columns")` (`decide.py:118`). The 3.2 staged bundle carries these 6 keys (incl. `target_column`) — no reshaping needed.
- **This module intentionally writes live `models/`** (unlike `retrain_candidate.py`, which refuses). Keep it minimal and only on the all-pass path; still guard against `--models-dir`/`--staging-dir` aliasing via `os.path.samefile` (the guard pattern added to `retrain_candidate.py` in the 3.2 review — catches macOS case-insensitive aliases).

### Guardrails

- **D-18 import graph** (`eval/tests/test_import_graph.py:49`): `src/` may import `src.*`, sklearn/scipy/joblib/pandas/numpy, stdlib — NOT `eval`, `inspect_ai`, `apps.*`, or LLM/HTTP SDKs. `promote_candidate.py` imports `src.evaluation.evaluate_routing`, `src.calibration.coverage`, `src.routing.config`, `src.data.build_retraining_dataset` — all allowed. Keep the guard green.
- **AD-8 self-contained bundle**: promote by copying the 6-key joblib; no external state.
- **Determinism / data-independence**: tests build everything in `tmp_path`; no real feedback file, no live `models/` write, no benchmark CSV (the recurring Epic-2/3.1/3.2 discipline).
- **Only `model_router` is promoted** — it is the sole feedback-retrained head (3.2 D1). The other two heads are out of the feedback loop.

### Previous-story intelligence (Story 3.2 — done, code-reviewed 2026-07-13)

- 3.2 shipped `src/model_router/retrain_candidate.py` → writes a calibrated 6-key candidate to `models/staging/model_router.joblib`; **mirror its CLI/structure** (`argparse`, `main(argv)->int`, `_setup_logging`, `InsufficientData`-style clean exits, `os.path.samefile` live-dir guard, module-docstring run example). This is the closest analog — copy its shape.
- 3.2 review added the `os.path.samefile` guard because `Path('models').resolve() != Path('Models').resolve()` on macOS (case-insensitive FS) — **reuse that guard** for the `--models-dir`/`--staging-dir` aliasing check here.
- Open 3.2 deferral that intersects 3.3: the candidate trains WITHOUT the Stage-1 `task_type`/`keyword_type` tokens the production router text carries (train/serve schema gap, `deferred-work.md`). At 0 real feedback this is harmless (3.3 promotes nothing). **Before G1 ever passes for real, that parity gap must be closed** (project `decision.signals.task_type` into the 3.1 dataset) — otherwise a promoted candidate would serve on a different feature schema than it trained on. Surface this in the report if G1 passes (a real-promotion readiness warning), and cross-reference `deferred-work.md`.
- Epic 2 (done) is the calibration contract G3 enforces (`required_calibrated_heads()`, `calibration_status`, per-head ECE thresholds). Runner: `uv run pytest` (sandbox-off locally); sklearn 1.8.0 (`n_jobs=-1` emits a harmless FutureWarning — matches legacy scripts).

### Project Structure Notes

- New: `src/model_router/promote_candidate.py`, `src/model_router/tests/test_promote_candidate.py`.
- Minimal edit: `src/evaluation/evaluate_routing.py` — add backward-compatible `artifacts: dict | None = None` param to `run(...)` (the G2 seam). No other production edits.
- Backup output: a promotion `.bak` (or timestamped copy) under `models/` at runtime — consider `.gitignore`. No `apps/` change; no migration.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.3] user story + acceptance criteria
- [Source: _bmad-output/planning-artifacts/epics.md:39,73,114] FR-15 no-regression gate; SM-2 baseline; AD-8
- [Source: src/evaluation/evaluate_routing.py:428] `run(canary_path, output_dir) -> dict` (add optional `artifacts`)
- [Source: src/evaluation/evaluate_routing.py:849] `evaluate_check(metrics) -> (bool, failures)` — reuse verbatim (built for Epic 3)
- [Source: src/evaluation/evaluate_routing.py:378] `_load_artifacts()` — the live-path loader the G2 seam replaces via override
- [Source: src/calibration/coverage.py:63] `calibration_status(artifacts) -> {head: bool}` (non-raising)
- [Source: src/routing/config.py:166,179] `required_calibrated_heads()`, `ece_threshold_for(head)` — the Story 2.1 manifest
- [Source: src/data/build_retraining_dataset.py:51,92] `DEFAULT_FEEDBACK`, `stream_jsonl` + `cleared`-supersede dedup (G1)
- [Source: src/data/seed_synthetic_feedback.py:73] `seed-%05d` message_id (real-vs-synthetic discriminator)
- [Source: src/model_router/retrain_candidate.py] Story 3.2 CLI/structure to mirror + staging bundle contract + `os.path.samefile` guard
- [Source: src/routing/decide.py:118] loader required keys the promoted artifact must satisfy
- [Source: src/routing/config.py:130] `DEFAULT_ARTIFACT_PATHS` live model paths
- [Source: src/evaluation/snapshot_baselines.py:47] `models/uncalibrated/` backup convention (do not clobber; use a distinct promotion backup)
- [Source: eval/tests/test_import_graph.py:49] D-18 import-graph guard
- [Source: _bmad-output/implementation-artifacts/deferred-work.md] 3.2 train/serve parity gap to close before real promotion

### Saved Questions (for the dev / reviewer — do not block implementation)

- **SQ-1 (exit codes):** Default here is `0` = clean run whether promoted or held (mirrors `retrain_candidate`'s "insufficient data → 0"). If the automated loop/CI needs to distinguish "held" from "promoted", add a distinct non-zero (e.g. `3` = held) — decide when the loop harness lands (Epic 3 has no scheduler yet).
- **SQ-2 (G2 seam):** Recommended = add `artifacts=None` to `evaluate_routing.run(...)`. Alternative = a scratch-models-dir wrapper that avoids editing `evaluate_routing`. The former is smaller and keeps the candidate on the exact CI code path; the latter avoids touching a reviewed eval module. Recommendation: the param override.
- **SQ-3 (no-regression definition):** Implemented as `evaluate_check` pass (absolute) + `backend_accuracy ≥ live − REGRESSION_TOLERANCE` (relative). Confirm `REGRESSION_TOLERANCE` (default `0.02`) and whether per-stage ECE should also be held to "no worse than live" vs only the manifest absolute threshold.

### Review Findings (code review 2026-07-13)

- [x] [Review][Patch] Distinct exit code for a held candidate (SQ-1, resolved 2026-07-13) [src/model_router/promote_candidate.py] — a promotion gate is automation-facing, so return `3` when gates fail and the candidate is held; keep `0` only for a successful promotion and `2` for errors (missing/corrupt staged candidate, bad args). Missing eval infra (P2) counts as held (`3`), not error.
- [x] [Review][Patch] G2 is not a true no-regression gate — deadlock risk [src/model_router/promote_candidate.py:99-108,144-159] — `evaluate_check(candidate_metrics)` fail-closes over ALL required heads, so a live task_type/agentic head drifting above ECE 0.10 on the noisy canary blocks the candidate model_router; and the baseline is never held to `evaluate_check` (only `backend_accuracy` read), so once the live cascade drifts you can never promote a fix. Also the baseline is loaded via `run(artifacts=None)` → default paths, ignoring `--models-dir`. Fix: build the baseline explicitly from `--models-dir` (live heads + live model_router) and make G2 fail only on failures the candidate INTRODUCES vs baseline (delta) plus a backend_accuracy regression; model_router's absolute ECE stays gated by G3.
- [x] [Review][Patch] AC#3 dry-run report not emitted in a thin environment [src/model_router/promote_candidate.py:221-231] — at 0 feedback `main()` calls `_gather_eval_metrics` before printing the report; a missing canary or live head → `return 2` with no gate report. Fix: degrade gracefully — always print the G1 result; if eval infra is missing mark G2/G3 "not evaluated" (→ held) and return 0, reserving 2 for a missing staged candidate.
- [x] [Review][Patch] 3.2 train/serve parity readiness warning not surfaced [src/model_router/promote_candidate.py] — the story explicitly directs "surface this in the report if G1 passes (a real-promotion readiness warning), cross-reference deferred-work.md". Not implemented. Fix: when G1 passes, emit the warning before promoting.
- [x] [Review][Patch] Tests assert rc + bytes but not the report / backup fidelity [src/model_router/tests/test_promote_candidate.py] — AC#4(b) requires proving the failed gate is NAMED and the all-pass path prints PROMOTED; add `capsys` assertions, and assert the `.bak` equals the prior live bytes.
- [x] [Review][Patch] Real `run(artifacts=candidate)` seam never integration-tested [src/model_router/tests/test_promote_candidate.py] — `_gather_eval_metrics` is monkeypatched in every `main()` test, so a shape mismatch (staged bundle missing `vectorizer`/`scaler`/`label_encoder`) would pass tests but crash in prod. Add a guarded integration test (skip if live heads/canary absent), plus a first-promotion (`baseline_metrics is None`) path test.
- [x] [Review][Patch] Backup robustness + misleading log [src/model_router/promote_candidate.py:163-172,102-104,246-249] — a second promotion clobbers the prior `.bak` (single-level reversibility); the backup path is printed even on first promotion when no `.bak` was written; the regression message prints the literal `- 0.02` instead of the effective bound. Fix: timestamped/unique backup, only report a backup that exists, show `base - tol`.
- [x] [Review][Patch] Defensive hardening [src/model_router/promote_candidate.py:218,119-124] — wrap `joblib.load(staged_path)` → clean `return 2` on a corrupt bundle (mirrors the file-not-found path); treat a NaN model_router ECE as a G3 failure (`nan > threshold` is currently False → silent pass).

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m]

### Debug Log References

- **G2 seam decision (SQ-2 → recommended path taken):** added a backward-compatible `artifacts: dict | None = None` param to `evaluate_routing.run(...)` (`src/evaluation/evaluate_routing.py:428`, gated at `:445` `if artifacts is None:`). `run()` already returns `per_head_calibrated` via `calibration_status(artifacts)` (`:803,:845`), so passing the candidate set (live task_type + agentic + staged model_router) evaluates the candidate through the exact CI code path — no metric recomputation. Existing `src/evaluation/tests/test_evaluate_routing.py` stays green (default `None` → `_load_artifacts()`).
- **Gate overlap (intentional):** G2 reuses `evaluate_check` verbatim (which already checks per-head calibration + ECE) AND G3 independently inspects the staged bundle via `calibration_status`. An uncalibrated candidate fails both; both are named in the report. G3 also fires without a full eval (direct artifact inspection), giving a clean early signal — kept per story Task 4.
- **Test seam:** the one heavy part (`_gather_eval_metrics`, runs the canary eval twice) is isolated so the 10 tests stay data-independent — pure gate functions + real G1 counting over a tiny JSONL + real atomic promotion copy, with `_gather_eval_metrics` monkeypatched to inject candidate/baseline metrics for the promote/hold branches. No real `~/.prompt-optimizer` feedback, no live `models/`, no benchmark CSV.
- **Pre-existing failure (NOT a regression):** `src/evaluation/tests/test_no_regression.py::test_task_type_accuracy_no_regression` fails `KeyError: 'origin_query'` — it reads `data_processed/classifier_training_with_types.csv`, an unmaterialized data file. Verified identical failure with this story's changes stashed → pre-existing environment/data dependency, unrelated to 3.3.
- **Verification:** `uv run pytest src/model_router src/evaluation src/data src/calibration eval/tests/test_import_graph.py` (import-mode preserved, the data-dependent `test_no_regression` ignored) → **43 passed, 14 skipped**. D-18 import-graph guard green; `evaluate_routing` backward-compat confirmed.

### Completion Notes List

- New `src/model_router/promote_candidate.py` (mirrors `retrain_candidate.py`'s CLI shape): three gates — G1 data-volume (≥100 real rated turns, reusing `stream_jsonl` + `assemble_rated_turns` cleared-supersede dedup, real = `message_id` not `seed-*`), G2 FR-15 no-regression (reuses `evaluate_routing.run` + `evaluate_check`, plus `backend_accuracy ≥ live − REGRESSION_TOLERANCE`), G3 Epic-2 calibration (`calibration_status` + `ece_threshold_for`). Promotes only when all three pass.
- Promotion is atomic + reversible: backs up live `model_router.joblib` → `.bak`, writes via `os.replace` (Task 5). This is the only module that writes live `models/` — and only on the all-pass path; guarded against `--staging-dir`/`--models-dir` aliasing via `os.path.samefile` (reused from the 3.2 review).
- Fail-closed report names each failed gate; at 0 real feedback G1 fails → holds, promotes nothing, exit 0 (AC #3 dry-run). Exit 2 only for missing staged candidate or missing canary (SQ-1 default: 0 = clean run whether promoted or held).
- Only `model_router` is promoted (the sole feedback-retrained head, 3.2 D1); live task_type/agentic heads untouched.
- Minimal production edit: backward-compatible `artifacts=None` param on `evaluate_routing.run` (the G2 seam, SQ-2 recommended path).
- 10 data-independent tests (all-pass promote, G1/G2/G3 hold, missing-staged→2, canary-missing→2, real G1 counting, pure gate fns). D-18 guard green.
- **Real-promotion readiness caveat carried from 3.2:** the candidate still trains without the Stage-1 `task_type`/`keyword_type` tokens (train/serve schema gap, `deferred-work.md`). Harmless while G1 blocks promotion at 0 feedback; must be closed before G1 ever passes for real.

### File List

- `src/model_router/promote_candidate.py` (new) — the three-gate promotion orchestration
- `src/model_router/tests/test_promote_candidate.py` (new) — 10 data-independent tests
- `src/evaluation/evaluate_routing.py` (modified) — `run(...)` accepts optional `artifacts` (backward-compatible G2 seam)

## Change Log

- 2026-07-13: Story 3.3 implemented — `src/model_router/promote_candidate.py` gates promotion of the staged candidate model_router behind three gates (G1 data-volume ≥100 real rated turns, G2 FR-15 no-regression, G3 Epic-2 calibration coverage), promoting atomically with backup only when all pass and holding+reporting otherwise. Reuses `evaluate_routing.run`/`evaluate_check`, `calibration_status`/`ece_threshold_for`, and the 3.1 feedback dedup; adds a backward-compatible `artifacts` param to `evaluate_routing.run`. 10 data-independent tests; D-18 guard green. Status → review.
- 2026-07-13: Addressed code review — 8 findings (1 decision + 7 patch) resolved. Reworked G2 into a true no-regression gate (backend_accuracy floor + regression tolerance from `--models-dir` baseline; no longer deadlocks on unchanged live-head ECE drift); graceful eval-infra degradation so the 0-feedback dry-run reports even in a thin env; distinct exit codes (0 promoted / 3 held / 2 error); surfaced the 3.2 parity readiness warning when G1 passes; unique/reversible backups; wrapped `joblib.load` + NaN-ECE guard; added a real `run(artifacts=candidate)` integration smoke (which surfaced + fixed a malformed-canary crash → clean EXIT_ERROR) plus capsys/backup-fidelity/first-promotion tests. 16 promote tests; full suite 46 passed / 15 skipped; D-18 guard green. Status → done.
