---
baseline_commit: a5ab764
---

# Story 4.1: Produce evidence the labels are the weakness

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the builder,
I want a confusion-matrix eval slice that isolates the `general` / `knowledge` / `factual` task-type labels and quantifies their contribution to misroutes,
so that the AD-9 full-retrain tax (Epic 4.2/4.3) is only paid if the data proves these labels are the real SM-1 weakness — a no-go halts the epic with the evidence recorded.

## Acceptance Criteria

1. **Confusion slice isolating the trio.**
   **Given** the saved `task_type_classifier.joblib` and a labelled eval set (rows carrying a true `question_type`)
   **When** the slice runs
   **Then** it reports the inter-label confusion among `general`/`knowledge`/`factual` — a 3×3 (+ "escaped-to-other") confusion matrix over the trio, per-class precision/recall/F1/support, and a single **trio-confusion rate** (share of true-trio rows the classifier assigns to a *different* trio label).

2. **Misroute-contribution signal.**
   **When** the slice runs
   **Then** it estimates how much the trio confusion drives misroutes: for each misclassified trio row, whether swapping the true `task_type_<label>` token for the predicted one in the Stage-2 router text (AD-9) flips the `model_router` top pick — reported as a count/rate. If the model_router isn't available, it falls back to reporting the confusion rate alone and says so (never crashes).

3. **Explicit go/no-go against a stated threshold.**
   **When** the slice finishes
   **Then** it emits a go/no-go signal: **GO** (merge justified) iff the trio-confusion rate ≥ `--threshold` (a stated, defaulted value), else **NO-GO**; the decision, the measured rate, the threshold, and the misroute estimate are written to an evidence report under `evaluation/`.
   **And** with `--check`, the process exit code encodes the decision: `0` = GO, `1` = NO-GO (halt the epic, no retrain), `2` = evidence unavailable (see AC #4). A NO-GO is a clean, successful outcome — not a crash.

4. **Graceful when the eval data isn't materialized (git-LFS).**
   **Given** the labelled CSVs are git-LFS pointers in a fresh checkout
   **When** the slice runs against an LFS-stub or missing input
   **Then** it detects the stub, prints a clear "run `git lfs pull` / provide `--input`" message, records "evidence unavailable — no decision", and exits `2` (does not fabricate a decision or crash).

5. **Data-independent test proves the metric + gate.**
   **And** a unit test proves the confusion-rate + go/no-go + misroute-flip logic on a tiny in-memory labelled set and a tiny classifier bundle in `tmp_path` (no live `models/`, no materialized benchmark CSV, no LFS dependency), covering a GO case, a NO-GO case, and the LFS-stub → exit-2 path.

## Tasks / Subtasks

- [x] Task 1: Create the evidence-slice module (AC: #1, #3)
  - [x] Add `src/evaluation/evaluate_task_type_confusion_slice.py`. Mirror `evaluate_routing.py`'s CLI shape: module docstring with run-from-root example, `argparse`, `main(argv: list[str] | None = None) -> int`, `run(input_csv, output_dir, threshold, ...) -> dict`, `if __name__ == "__main__": sys.exit(main())`. matplotlib `Agg` backend (no display).
  - [x] Flags: `--input` (default the labelled CSV, see Dev Notes B), `--output-dir` (default `evaluation/task_type_slice/`), `--threshold` (default per SQ-1), `--check` (exit-code gate), `-v/--verbose`.
  - [x] `TRIO = ("general", "knowledge", "factual")` as a module constant.
- [x] Task 2: Load classifier + evaluate on a held-out slice (AC: #1)
  - [x] Load `models/task_type_classifier.joblib` (6-key/5-key bundle: `model, vectorizer, scaler, label_encoder, feature_columns`). Build the feature matrix with the EXACT training contract — word+char TF-IDF `FeatureUnion.transform` ⊕ `StandardScaler.transform`'d handcrafted numerics (`PromptFeatureExtractor`) ⊕ `scipy.sparse.hstack` (`train_task_classifier_robust.py:405-458`). Reuse `get_numeric_feature_columns` and the `predict_user_input` feature-build path — do NOT reinvent the pipeline.
  - [x] Evaluate on a **held-out** slice, not the training rows: reproduce the training split `train_test_split(test_size=0.2, random_state=42, stratify=question_type)` and score the test portion (the 20% the saved classifier did not fit), so the confusion is honest. Log train/test sizes.
- [x] Task 3: Trio confusion + metrics (AC: #1)
  - [x] Compute the confusion matrix restricted to true-label ∈ TRIO, columns = TRIO + `other`. Reuse `sklearn.metrics.confusion_matrix` and the `save_classification_metrics_csv` pattern (`train_task_classifier_robust.py:310-335`) for per-class precision/recall/F1/support.
  - [x] `trio_confusion_rate` = (# true-trio rows predicted as a *different* trio label) / (# true-trio rows). Write `confusion_matrix.csv` + `.png` (reuse a `plot_confusion_matrix` helper) and `metrics_per_class.csv`.
- [x] Task 4: Misroute contribution (AC: #2)
  - [x] For each misclassified trio test row, build the Stage-2 router text with the TRUE label vs the PREDICTED label (`build_router_text_input_single(question_type=...)`, `src/feature_extraction/text_inputs.py`) and check whether the `model_router` top-1 prediction flips. Report `misroute_flip_count` / `misroute_flip_rate`.
  - [x] If `models/model_router.joblib` is absent/unloadable, skip the flip analysis, set the misroute fields to `None`, and log that the confusion rate alone drives the decision. Never crash. (See SQ-2 on going deeper via full `decide()`.)
- [x] Task 5: Go/no-go + evidence report (AC: #3)
  - [x] `go = trio_confusion_rate >= threshold`. Write `go_no_go_decision.md` (or `.txt`) recording: decision (GO/NO-GO), measured rate, threshold, per-class metrics summary, misroute estimate, n_test rows, and timestamp (pass the date in — do not call the clock inside a testable pure function). Return a dict `{trio_confusion_rate, go, threshold, misroute_flip_rate, n_test, per_class}`.
  - [x] `--check`: exit `0` on GO, `1` on NO-GO. Non-`--check` runs always exit `0` after writing the report (unless data unavailable → `2`).
- [x] Task 6: Graceful data-unavailable path (AC: #4)
  - [x] Detect a git-LFS pointer stub: a small text file beginning with `version https://git-lfs.github.com/spec/`. Add `_is_lfs_pointer(path) -> bool` (or reuse the helper in `src/evaluation/tests/` if one exists). Missing file OR LFS stub → log the `git lfs pull` remediation, write "evidence unavailable" to the report, return `2`. Do the same if `models/task_type_classifier.joblib` is missing.
- [x] Task 7: Data-independent tests (AC: #5)
  - [x] Add `src/evaluation/tests/test_evaluate_task_type_confusion_slice.py`. Build a tiny in-memory labelled CSV (a handful of rows across the trio + a couple other labels, with the handcrafted numeric columns) in `tmp_path`, and a tiny fitted `task_type_classifier`-shaped bundle (or monkeypatch the load) — no live `models/`, no benchmark CSV.
  - [x] Cover: (a) high-confusion input → GO (`--check` exit 0); (b) low/zero-confusion input → NO-GO (exit 1); (c) LFS-stub / missing input → exit 2 with no fabricated decision; (d) the pure `trio_confusion_rate` + go/no-go functions over synthetic confusion arrays. RED-then-GREEN.
- [x] Task 8: Regression + guard sanity (AC: all)
  - [x] Run `uv run pytest src/evaluation src/task_classifier eval/tests/test_import_graph.py`. New tests pass; D-18 import-graph guard green (the module imports only `sklearn`, `pandas`, `numpy`, `joblib`, `matplotlib` (Agg), `scipy`, and `src.*` — NOT `eval`/`inspect_ai`/`apps.*`/HTTP/LLM SDKs). No writes under `models/`.

## Dev Notes

**Epic 4 = task-label taxonomy cleanup, EVIDENCE-GATED. 4.1 produces the evidence (this story) — it does NOT merge labels or retrain. 4.2 merges + retrains (only on a GO), 4.3 gates the merged candidate. 4.1's entire job: measure whether `general`/`knowledge`/`factual` confuse the classifier enough to justify paying the AD-9 full-retrain tax, and emit a defensible go/no-go with the evidence recorded. A NO-GO must halt the epic cleanly.**

### Why this gate exists (AD-9 / SM-1 / DEF-2)

- **AD-9:** the Stage-2 text format `"<query> task_type_X keyword_type_Y"` is baked into the trained `model_router` vectorizer vocabulary; changing the label taxonomy invalidates `model_router.joblib` and forces a coordinated full retrain (epics.md:62). That tax is why 4.1 must prove the labels are the weakness first (DEF-2, epics.md:74,117).
- **SM-1** (route acceptance ≥80% interim) is the weakness the merge is meant to lift; **SM-2** (tier-router accuracy ≈0.78 / macro-F1 ≈0.75) is the health guardrail 4.3 protects. 4.1 only produces evidence — it does not touch either baseline.

### The trio and where the labels come from (verified)

- Labels exist in `src/task_classifier/build_question_type.py` (`map_dataset_to_question_type`): **`general`** ← `arenahard` (:129-131); **`knowledge`** ← MMLU / MMLU-Pro / GPQA / TriviaQA / NQ / HLE (:80-88); **`factual`** ← SimpleQA (:90-92). Full label set: coding, writing, medical, emotion, agentic, math, reasoning, factual, knowledge, data, general, unknown.
- These are dataset-derived weak labels — the hypothesis is that `general`/`knowledge`/`factual` overlap semantically and the classifier confuses them.

### Classifier + feature contract to reuse (do NOT reinvent)

- Bundle `models/task_type_classifier.joblib`: `{model (CalibratedClassifierCV), vectorizer (FeatureUnion word+char TF-IDF), scaler (StandardScaler), label_encoder, feature_columns}` (`train_task_classifier_robust.py:594-614`).
- Inference feature matrix = `vectorizer.transform(text)` ⊕ `csr_matrix(scaler.transform(df[feature_columns].fillna(0)))` via `scipy.sparse.hstack` (`:405-458`); `PromptFeatureExtractor.extract` supplies the handcrafted numerics. Reuse `get_numeric_feature_columns` and the `predict_user_input` build path. `label_encoder.inverse_transform` maps predictions back to label strings.
- Import `PromptFeatureExtractor` via the `sys.path` shim the repo uses (`from Feature_extractor import PromptFeatureExtractor`) — see `evaluate_routing.py:_get_extractor()` for the exact pattern; reuse it.

### Eval data — the LFS reality (B)

- The only per-row labelled source is `data_processed/classifier_training_with_types.csv` (`origin_query` text + `question_type` true label + handcrafted numeric columns), produced by `src/task_classifier/build_question_type.py`. **It is a git-LFS pointer stub in a fresh checkout** (`git check-attr filter` → `lfs`; ~128 MB when pulled). `src/evaluation/tests/test_no_regression.py` already fails locally for exactly this reason — treat unmaterialized data as an expected, handled state (AC #4), not an error to debug.
- Evaluate on the **held-out 20%** (`train_test_split(test_size=0.2, random_state=42, stratify=y)`) so confusion isn't measured on rows the classifier trained on. The saved classifier was fit on the 80%; the 20% is a fair slice.

### Misroute contribution (D) — keep it lean

- Stage-2 router text carries the `task_type_<label>` token (`text_inputs.py:build_router_text_input_single`, AD-9). A confused trio label → wrong token → potentially different `model_router` top pick. The cheap, defensible measure: for each misclassified trio test row, compare `model_router` top-1 under the true vs predicted token and count flips. This is a proxy for real misroute impact and is enough evidence for a go/no-go. Full end-to-end `decide()` re-routing is heavier and deferred (SQ-2).

### Guardrails

- **No retrain, no label merge, no live-model writes.** 4.1 only reads `models/*.joblib` and writes reports under `evaluation/task_type_slice/`. The merge + retrain is 4.2.
- **D-18 import graph** (`eval/tests/test_import_graph.py`): the module may import `src.task_classifier.*`, `src.feature_extraction.*`, `src.model_router.*`, sklearn/scipy/joblib/pandas/numpy/matplotlib — NOT `eval`, `inspect_ai`, `apps.*`, or HTTP/LLM SDKs. Use matplotlib's `Agg` backend.
- **Determinism** — `random_state=42` for the split, mirroring every training script.
- **Data-independence** — tests build tiny in-memory data + a tiny classifier bundle; the recurring Epic-2/3 discipline. The go/no-go and confusion-rate logic must be pure functions unit-tested without any file I/O.

### Previous-story intelligence (Epic 3, done)

- Epic 3's `retrain_candidate.py` / `promote_candidate.py` established the CLI shape to mirror here: `argparse` + `main(argv)->int`, distinct exit codes, module-docstring run example, `_setup_logging`, graceful "can't proceed" exits (return code, not traceback), and data-independent tests that monkeypatch heavy seams. Reuse that shape.
- Recurring lesson from the 3.2/3.3 reviews: isolate any heavy/data-dependent seam behind a small function so tests stay fast and data-independent; assert reports via `capsys`; wrap `joblib.load` so a corrupt/missing artifact returns a clean code, not a crash.
- The LFS-stub gotcha bit the 3.3 integration test (`test_no_regression` / the canary CSV) — handle it here up front (AC #4) rather than discovering it in review.

### Project Structure Notes

- New: `src/evaluation/evaluate_task_type_confusion_slice.py`, `src/evaluation/tests/test_evaluate_task_type_confusion_slice.py`.
- New output dir: `evaluation/task_type_slice/` (created at runtime; consider `.gitignore`).
- No production edits, no `models/` writes, no migration. Pure read + report.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.1] user story + ACs
- [Source: _bmad-output/planning-artifacts/epics.md:62,74,117] AD-9 retrain tax; DEF-2 evidence gate
- [Source: _bmad-output/planning-artifacts/prds/prd.md:262,265] SM-1 (≥80%), SM-2 (0.78 / 0.75)
- [Source: src/task_classifier/build_question_type.py:80-92,129-131] general/knowledge/factual label sources
- [Source: src/task_classifier/train_task_classifier_robust.py:405-458] inference feature-matrix contract to reuse
- [Source: src/task_classifier/train_task_classifier_robust.py:310-335] `save_classification_metrics_csv` pattern
- [Source: src/task_classifier/train_task_classifier_robust.py:594-614] classifier bundle shape
- [Source: src/feature_extraction/text_inputs.py] `build_router_text_input_single` (AD-9 Stage-2 token)
- [Source: src/evaluation/evaluate_routing.py:428,903] `run(...)`/`main(argv)->int` CLI shape + `_get_extractor()` shim
- [Source: data_processed/classifier_training_with_types.csv] labelled eval source (git-LFS stub — handle per AC #4)
- [Source: eval/tests/test_import_graph.py] D-18 import-graph guard

### Saved Questions (non-blocking — sensible defaults chosen)

- **SQ-1 (metric + threshold):** default `trio_confusion_rate` = off-trio-diagonal share among true-trio rows, `--threshold` default **0.15**. Confirm the exact metric (mutual trio confusion vs any-misclassification of trio rows) and the GO threshold — this number decides whether Epic 4 proceeds, so it deserves an explicit sign-off before 4.2.
- **SQ-2 (misroute depth):** default = model_router top-1 flip under true-vs-predicted token (a proxy). Deeper = full `decide()` re-route comparison (backend + model), heavier; deferred unless the proxy is judged insufficient evidence.
- **SQ-3 (eval set):** default = held-out 20% of `classifier_training_with_types.csv` (same seed as training). Alternative = a dedicated, independently-labelled eval CSV (avoids weak-label circularity, but none exists yet). Flag if the weak-label provenance undermines the evidence.

### Review Findings (code review 2026-07-13)

- [x] [Review][Patch] Silent train/test leakage — "held-out" claim not honest [src/evaluation/evaluate_task_type_confusion_slice.py:150-159] — `_heldout_slice` falls back to scoring the FULL frame (resubstitution on rows the classifier trained on) when stratify fails, with only a default-verbosity warning and no flag in the result; this understates confusion and can flip a real GO into a false NO-GO. Also the split diverges from training on NaN labels (training does `fillna("general")`, this does `.astype(str)`→`"nan"`, a different stratum). Fix: mirror `fillna("general")` before the split; return a `held_out` boolean (held-out vs resubstitution) in the result and report; warn loudly when falling back.
- [x] [Review][Patch] `_feature_matrix` silently zero-fills missing numeric columns → silently wrong predictions [src/evaluation/evaluate_task_type_confusion_slice.py:136-140] — `df.reindex(columns=feature_columns, fill_value=0)` means an `--input` whose numeric columns don't match the bundle produces all-zero features and a plausible-but-bogus confusion number with no error (only `origin_query`/`question_type` are validated). Fix: validate the bundle's `feature_columns` are present in the CSV; if a meaningful share is missing → `EXIT_UNAVAILABLE` with a clear message.
- [x] [Review][Patch] Empty/corrupt input crashes instead of clean exit-2 (AC #4) [src/evaluation/evaluate_task_type_confusion_slice.py:325-333] — a 0-byte/truncated non-stub CSV makes `pd.read_csv` raise `EmptyDataError`/`ParserError` (uncaught), and `joblib.load(classifier)` is unwrapped; both break the "unavailable, not a crash" contract. Fix: wrap `pd.read_csv` + `joblib.load` → `EXIT_UNAVAILABLE` (same lesson as the 3.3 malformed-canary fix).
- [x] [Review][Patch] Confusion rate can be misread; guard insufficient trio support [src/evaluation/evaluate_task_type_confusion_slice.py:73-91] — the trio→trio-only rate (spec-correct) reads as "no confusion" (0.0) even when the classifier dumps the whole trio into `other`, and an empty-trio slice yields a confident false NO-GO. Fix: also report a `trio_escape_rate` (true-trio rows → non-trio label, from the matrix `other` column) and a `trio_support` count; warn/flag when trio support is too low to decide.
- [x] [Review][Patch] Misroute-flip runs on zero-filled router numerics — absolute rate unrepresentative [src/evaluation/evaluate_task_type_confusion_slice.py:185-192] — `model_router` expects router-native numerics (`question_type_confidence`, `best_model_tier`) absent from the classifier CSV, so they zero-fill; the token comparison still isolates the AD-9 token (both sides share the zeroed numerics) so the DIRECTION is valid, but the absolute flip rate is degraded. Fix: label the misroute-flip in the report as a directional token-sensitivity proxy (not a calibrated misroute rate); note the router-feature gap.
- [x] [Review][Patch] `go_no_go_decision.md` missing the per-class summary (Task 5) [src/evaluation/evaluate_task_type_confusion_slice.py:258-272] — per-class P/R/F1 go to `metrics_per_class.csv` but Task 5 asked for a summary in the decision `.md`. Fix: add a short per-class block to the report.
- [x] [Review][Patch] Threshold uses `>=` but AC #3 says "exceeds" [src/evaluation/evaluate_task_type_confusion_slice.py:118-120] — change `go_no_go` to strictly `>` for AC-wording fidelity (boundary-only impact).
- [x] [Review][Patch] Tests don't exercise the leakage fallback or the zero-fill trap [src/evaluation/tests/test_evaluate_task_type_confusion_slice.py] — the two highest-severity traps are invisible to the suite (balanced synthetic data always stratifies; every bundle's columns match the df). Add: a thin-data test asserting `held_out=False`; a missing-feature-columns test asserting the new guard fires; and a measured-confusion GO test (genuinely confused labels, not a threshold extreme). Fix the doc's "14 tests" miscount (currently 13).

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m]

### Debug Log References

- **No PromptFeatureExtractor needed:** the labelled CSV carries the handcrafted numeric feature columns inline (same as the 3.1 CSV), and each bundle stores its own `feature_columns`, so `_feature_matrix` selects numerics from the CSV via `df.reindex(columns=feature_columns, fill_value=0)` — no NLTK/extractor/sys.path shim. Simpler + keeps tests data-independent.
- **Report-first, threshold provisional (per the build directive):** the `trio_confusion_rate` is the headline printed line and the top of `go_no_go_decision.md`; `--threshold` (default 0.15) is labelled PROVISIONAL everywhere. The weak-label caveat (`_WEAK_LABEL_CAVEAT`) is printed and written into the report so the number is never mistaken for proof.
- **Held-out slice with fallback:** `_heldout_slice` reproduces `train_test_split(0.2, seed=42, stratify=question_type)`; on data too thin to stratify it logs and scores the full frame (tests hit this path).
- **Misroute-flip:** for misclassified true-trio rows, compares `model_router` top-1 under the true vs predicted AD-9 `task_type_` token (reusing `build_router_text_input_single`); returns `None` (and says so) when no model_router is available — never crashes.
- **LFS reality (AC #4):** `_is_lfs_pointer` detects the pointer stub; a missing/stub input or classifier → clean `EXIT_UNAVAILABLE` (2) with a `git lfs pull` remediation + an "evidence unavailable" report, not a crash. Locally `data_processed/classifier_training_with_types.csv` IS an LFS stub, so the real evidence run requires `git lfs pull` on a data-materialized machine — the tool is correct and tested; the number can't be produced in this checkout.
- **Verification (post-review):** `uv run pytest src/evaluation/tests/test_evaluate_task_type_confusion_slice.py eval/tests/test_import_graph.py` → **20 passed + guard green**. Broader `src/evaluation src/task_classifier` run: all mine pass (28 passed / 14 skipped); 2 `test_agentic_intent` + 1 `test_no_regression` failures are **pre-existing git-LFS data-availability** issues (`data_processed/*.csv` are LFS stubs), unrelated to this additive-only story (2 new files under `src/evaluation/`).

### Completion Notes List

- New `src/evaluation/evaluate_task_type_confusion_slice.py`: scores the saved `task_type_classifier` on the held-out slice, isolates `general`/`knowledge`/`factual`, and reports a trio confusion matrix + per-class P/R/F1 + the headline `trio_confusion_rate`, a misroute-flip estimate (AD-9 token swap → model_router top-1 flip), and a provisional go/no-go. NO retrain, NO label merge, NO `models/` writes.
- Exit codes encode the decision for Epic 4.2 to gate on: `0` GO / `1` NO-GO / `2` evidence-unavailable. `--check` gates; plain runs always exit 0 after writing the report (unless unavailable).
- Reports written to `evaluation/task_type_slice/`: `confusion_matrix.csv` + `.png` (Agg), `metrics_per_class.csv`, `go_no_go_decision.md` (decision + rate + threshold + misroute estimate + weak-label caveat).
- Pure metric functions (`trio_confusion_rate`, `trio_escape_rate`, `trio_confusion_matrix`, `per_class_metrics`, `go_no_go`, `_is_lfs_pointer`) are unit-tested on synthetic arrays; `run()`/`main()` end-to-end tested with tiny fitted bundles (measured-confusion GO, clean-data NO-GO, held-out-flag, missing-feature-columns / empty-CSV / LFS-stub → exit 2). 20 data-independent tests; D-18 guard green.
- **Open decision for the reviewer/user (SQ-1):** the go/no-go threshold is provisional — set it from the first real run's measured `trio_confusion_rate` (needs `git lfs pull`). SQ-3 (weak-label provenance) is surfaced in the report; it caps how conclusive the evidence can be.

### File List

- `src/evaluation/evaluate_task_type_confusion_slice.py` (new) — evidence slice + go/no-go
- `src/evaluation/tests/test_evaluate_task_type_confusion_slice.py` (new) — 20 data-independent tests

## Change Log

- 2026-07-13: Story 4.1 implemented — `src/evaluation/evaluate_task_type_confusion_slice.py` produces the general/knowledge/factual confusion evidence (held-out slice, trio confusion matrix + rate, misroute-flip estimate via the AD-9 token) and a provisional go/no-go (exit 0 GO / 1 NO-GO / 2 unavailable), report-first with the weak-label caveat baked in. Handles the git-LFS-stub data reality cleanly. Data-independent tests; D-18 guard green; no retrain, no models/ writes. Status → review.
- 2026-07-13: Addressed code review — 8 patch findings resolved. Made the "held-out" claim honest (mirror training's `fillna("general")` for the split; return a `held_out` flag; loud RESUBSTITUTION warning + report label when falling back); guard against silent zero-fill of missing classifier feature columns (→ clean EXIT_UNAVAILABLE); wrap `pd.read_csv`/`joblib.load` so empty/corrupt inputs exit-2 instead of crashing (the 3.3 lesson); report `trio_escape_rate` + `trio_support` alongside the rate and warn on low support; label the misroute-flip a directional proxy (router-native numerics absent); add the per-class summary to the decision `.md`; change the gate to strict `>` ("exceeds", AC #3). Tests grew 13→20 incl. measured-confusion GO, held-out-flag, missing-feature-columns, and empty-CSV cases. Full suite: 28 passed / 14 skipped (2 pre-existing LFS failures deselected); D-18 guard green. Status → done.
