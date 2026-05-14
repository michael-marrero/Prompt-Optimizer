---
phase: 01-router-brain-foundation
reviewed: 2026-05-14T00:00:00Z
depth: standard
files_reviewed: 36
files_reviewed_list:
  - .github/workflows/ci.yml
  - .gitignore
  - pyproject.toml
  - ReadMe.md
  - scripts/expand_agentic_seeds.py
  - scripts/inject_unknown_class_rows.py
  - scripts/write_agentic_seeds.py
  - src/calibration/tests/test_calibration.py
  - src/demo/demo_router.py
  - src/demo/tests/test_artifact_compat.py
  - src/evaluation/evaluate_routing.py
  - src/evaluation/snapshot_baselines.py
  - src/evaluation/tests/test_canary_schema.py
  - src/evaluation/tests/test_evaluate_routing.py
  - src/evaluation/tests/test_no_regression.py
  - src/feature_extraction/Feature_extractor.py
  - src/feature_extraction/tests/test_agentic_features.py
  - src/feature_extraction/tests/test_text_inputs.py
  - src/feature_extraction/text_inputs.py
  - src/model_router/train_model_router.py
  - src/routing/__main__.py
  - src/routing/config.py
  - src/routing/decide.py
  - src/routing/policy.py
  - src/routing/schema.py
  - src/routing/tests/conftest.py
  - src/routing/tests/test_decide_smoke.py
  - src/routing/tests/test_gitignore.py
  - src/routing/tests/test_rule_cascade.py
  - src/routing/tests/test_schema.py
  - src/routing/tests/test_uncertainty_fallback.py
  - src/task_classifier/build_agentic_dataset.py
  - src/task_classifier/build_question_type.py
  - src/task_classifier/tests/test_agentic_intent.py
  - src/task_classifier/train_agentic_intent.py
  - src/task_classifier/train_task_classifier_robust.py
findings:
  critical: 1
  warning: 8
  info: 7
  total: 16
status: needs_fix
---

# Phase 01: Code Review Report

**Reviewed:** 2026-05-14
**Depth:** standard
**Files Reviewed:** 36
**Status:** needs_fix

## Summary

The router-brain implementation broadly meets the locked Phase 1 contract: the framework-free `src/routing/decide.py` pure function is in place, the D-18 import-graph guard is exercised by a runtime smoke test, the 5-key canonical artifact contract is preserved across the calibration retrain, and the scikit-learn 1.8 `FrozenEstimator + CalibratedClassifierCV` idiom is correctly adopted (no deprecated `cv='prefit'`). The CLAUDE.md preservation rules (CamelCase `Feature_extractor.py`, sys.path injection pattern, NLTK punkt guard) are all respected.

One **critical correctness bug** was identified in the calibration pipeline that is shared across all three calibrated trainers: the calibration carve computes a 75/25 sub-split of `X_train` but only uses the 25% calibration slice — the base classifier was already fit on **the full 100% of `X_train` (including the same 25% slice the calibrator then fits on)**, so the calibrator is trained on raw probabilities that have already overfit the calibration examples. This degrades calibration quality and is consistent with Plan 07's "canary-set ECE > 0.10 on all three calibrated heads" carry-forward, which the planner correctly flagged but did not trace to this root cause.

Eight warning-level issues cover: an inconsistency in the demo `_decision_to_legacy_dict` adapter (route metadata for unverified-but-mapped slugs misrepresents `openrouter_verified`/`source`), a missing operator log when the V7 robustness catch swallows internal errors, an incomplete `FORBIDDEN_MODULES` set in the D-18 smoke test, an `is_fallback_actual` definition in the canary evaluator that conflates "intentional fallback" with "slug-resolution-failure", and several smaller integrity gaps. Seven info-level items capture style nits and minor type confusions.

## Critical Issues

### CR-01: Calibration carve does not refit base on disjoint train slice — `X_train_only` is dead code across all 3 trainers

**File:** `src/task_classifier/train_task_classifier_robust.py:479-491`, `src/model_router/train_model_router.py:659-671`, `src/task_classifier/train_agentic_intent.py:388-400`

**Issue:** All three calibrated trainers exhibit the same pattern:

```python
# Step 1: fit the BASE classifier on the FULL 80% training split.
model.fit(X_train_combined, y_train)                       # uses 100% of X_train

# Step 2: sub-split X_train_combined into a 75/25 "train-only" / "calib" carve.
X_train_only, X_calib, y_train_only, y_calib = train_test_split(
    X_train_combined, y_train,
    test_size=0.25, random_state=42, stratify=y_train,
)

# Step 3: wrap the already-fit base and calibrate.
calibrated = CalibratedClassifierCV(FrozenEstimator(model), method="sigmoid")
calibrated.fit(X_calib, y_calib)                           # 25% slice ALREADY SEEN by base
```

`X_train_only` and `y_train_only` are computed but never used. The base classifier was fitted on the **full** `X_train_combined`, which includes the 25% subset that the calibrator then fits on. Because the base has effectively memorized those samples, the raw `predict_proba` outputs on `X_calib` are systematically over-confident, and the sigmoid calibrator inherits that bias — exactly the Pitfall-3 scenario the inline comments at `train_task_classifier_robust.py:471-478` claim to avoid.

This is the most plausible root cause of the Plan 07 carry-forward "canary-set ECE > 0.10 on all three calibrated heads". The structure of the code suggests the author intended a disjoint split and did not finish the wiring.

**Fix:** Refit the base on the disjoint train slice before freezing. Verbatim correction for `train_task_classifier_robust.py`:

```python
# Carve a fresh calibration slice FIRST, then fit the base on the disjoint
# train slice ONLY so FrozenEstimator wraps a model that has never seen X_calib.
X_train_only, X_calib, y_train_only, y_calib = train_test_split(
    X_train_combined, y_train,
    test_size=0.25, random_state=42, stratify=y_train,
)

model.fit(X_train_only, y_train_only)   # disjoint from X_calib

calibrated = CalibratedClassifierCV(
    FrozenEstimator(model),
    method="sigmoid",
    cv=None,  # FrozenEstimator -> calibrator head only; no CV refit
)
calibrated.fit(X_calib, y_calib)
```

Apply the same correction to `train_model_router.py:659-671` and `train_agentic_intent.py:388-400`. After the change, re-run `snapshot_baselines.py` and `evaluate_routing.py --check` to confirm the canary ECE drops below the 0.10 threshold; if not, switch the failing stage to `method="isotonic"` per the existing `# Open Question 1` comment.

## Warnings

### WR-01: `_decision_to_legacy_dict` overwrites `api_model` but leaves `source`/`openrouter_verified` inconsistent for unverified-but-mapped slugs

**File:** `src/demo/demo_router.py:323-340`

**Issue:** When the routing brain picks a slug that lives in `model_mapping.json` with `openrouter_verified=false` and `api_model=null` (seven such entries exist: `internlm3-8b-instruct`, `granite-3.3-8b-instruct`, `glm-4-9b-chat`, `MiniCPM4.1-8B`, `cogito-v1-preview-llama-8B`, `OpenThinker3-7B`, plus the `OTHER` fallback), `decide()` returns `model_or_agent="openrouter/auto"` because `decide.py:472` falls back via `route_info.get("api_model") or FALLBACK_MODEL_OR_AGENT`.

The demo adapter then:

```python
final_model_info = choose_final_route(chosen_slug, model_mapping)   # returns source="model_router", openrouter_verified=False
final_model_info = dict(final_model_info)
final_model_info["api_model"] = decision.model_or_agent              # overwrites with "openrouter/auto"
```

Result: a display row that reports `source=model_router`, `openrouter_verified=False`, `api_model="openrouter/auto"`. The `openrouter/auto` route IS verified per `config/model_mapping.json` (the `"openrouter"` entry has `openrouter_verified: true`), but the printed display says the route is unverified. This will mislead end users reading the demo REPL output.

**Fix:** Detect the substitution and update both fields:

```python
final_model_info = dict(final_model_info)
if final_model_info.get("api_model") != decision.model_or_agent:
    # Brain substituted the routed model_or_agent (typically the openrouter/auto
    # fallback). Re-derive openrouter_verified and source from the openrouter mapping
    # entry rather than the original slug entry.
    if decision.model_or_agent == FALLBACK_MODEL_OR_AGENT:
        auto_entry = model_mapping.get("openrouter", {})
        final_model_info["openrouter_verified"] = bool(auto_entry.get("openrouter_verified", False))
        final_model_info["source"] = "unverified_slug_fallback_to_auto"
final_model_info["api_model"] = decision.model_or_agent
```

### WR-02: `decide()` V7 robustness catch silently swallows all exceptions with no operator-visible log

**File:** `src/routing/decide.py:494-505`

**Issue:** The outermost `try/except Exception as exc` in `decide()` catches every error and emits a fallback `RoutingDecision` whose `signals` dict carries `{"error_type": ..., "error_msg": str(exc)[:500]}`. Nothing is logged to stderr or stdout. If `models/agentic_intent_classifier.joblib` becomes corrupted or a feature-column mismatch develops, the brain will silently route every prompt to `openrouter/auto` with no operator-visible signal that the calibrated heads are broken.

CLAUDE.md "Logging" guidance for inference scripts says to use `print()`. The signals dict is only inspected by downstream code that knows to look at it.

**Fix:** Add an `import warnings` and emit `warnings.warn(f"decide(): internal error: {type(exc).__name__}: {exc}", RuntimeWarning)` inside the except block (or `print(..., file=sys.stderr)` if a hard dependency on `warnings` is undesired). This preserves the V7 robustness contract while surfacing the failure during operator use.

### WR-03: `FORBIDDEN_MODULES` in D-18 smoke test missing 5 entries from the orchestrator-specified list

**File:** `src/routing/tests/test_decide_smoke.py:22-24`

**Issue:** The smoke test asserts only against `{"fastapi", "httpx", "requests", "aiohttp", "anthropic", "openai"}` (6 entries). The orchestrator and `CLAUDE.md` integration constraint list 12 forbidden top-level packages: the 6 above plus `urllib3`, `flask`, `starlette`, `pydantic`, `google-generativeai`. `urllib3` is particularly important: a transitive `requests` import would bring it in, but a future regression that imports `urllib3` directly (e.g., via `botocore` or `boto3`) would slip past the existing assertion.

`src/routing/*` does not currently import any of the missing 5, so this is a future-proofing gap rather than an active leak.

**Fix:** Extend the set:

```python
FORBIDDEN_MODULES: frozenset[str] = frozenset({
    "fastapi", "httpx", "requests", "aiohttp", "anthropic", "openai",
    "urllib3", "flask", "starlette", "pydantic", "google",
})
```

Note: `google-generativeai` ships under the top-level `google` namespace (the import name is `google.generativeai`). Putting `"google"` in the set is the only reliable top-level guard, but it has a false-positive risk if any future legitimate `google.*` package (e.g., `google.protobuf`) is imported. The safer pattern is to keep the existing top-level check and also walk `sys.modules` for the literal `"google.generativeai"` sub-module name. The simplest implementation:

```python
FORBIDDEN_TOP_LEVEL = frozenset({"fastapi","httpx","requests","aiohttp","anthropic","openai","urllib3","flask","starlette","pydantic"})
FORBIDDEN_DOTTED    = frozenset({"google.generativeai", "google.genai"})
# walk sys.modules, check name.split('.')[0] against FORBIDDEN_TOP_LEVEL,
# and the full dotted name against FORBIDDEN_DOTTED.
```

### WR-04: Canary evaluator's `is_fallback_actual` matches purely on rationale suffix and never compares against `is_fallback_expected`

**File:** `src/evaluation/evaluate_routing.py:472, 702-707`

**Issue:** The evaluator computes:

```python
is_fallback_actual = actual_rationale.endswith(FALLBACK_RATIONALE_SUFFIX)
# ...
low_conf_rate = float(n_fallback_actual) / float(len(rows_df))
```

But it never compares `is_fallback_expected` against `is_fallback_actual` to produce a fallback-recall metric. A canary row with `expected_backend="openrouter"` and `is_fallback_expected=True` would be counted as a backend match if `decide()` returns the OpenRouter backend with a clean rationale (no fallback suffix), even though the row was authored to verify the fallback path fires.

Test `test_canary_per_backend_distribution` (test_canary_schema.py:140-166) confirms that fallback rows use `expected_backend="openrouter"`, so they merge into the openrouter accuracy bucket. The result is that **D-09 / D-12 fallback fidelity is not measured by any emitted metric**, only by the per-row CSV (`per_row_results.csv`) which is not part of the D-16 success criterion deliverable.

**Fix:** Add a `fallback_pr.csv` output computed against `is_fallback_expected` vs `is_fallback_actual`, and surface a `fallback_precision`/`fallback_recall` line in the stdout summary. Example:

```python
expected_fb = rows_df["is_fallback_expected"].tolist()
actual_fb   = rows_df["is_fallback_actual"].tolist()
fp_p, fp_r, fp_f1, _ = precision_recall_fscore_support(
    expected_fb, actual_fb, labels=[True], zero_division=0,
)
pd.DataFrame({"metric": ["precision","recall","f1"], "value": [fp_p[0], fp_r[0], fp_f1[0]]})\
    .to_csv(os.path.join(output_dir, "fallback_pr.csv"), index=False)
```

### WR-05: Per-stage ECE in evaluator uses confounded ground-truth proxy without documenting limitation in user-facing output

**File:** `src/evaluation/evaluate_routing.py:507-586`, especially lines 544-546, 558-560

**Issue:** `y_true_binary` for the per-stage ECE is set to `int(backend_match)`:

> "We approximate 'correct' as: the actual backend matches the expected backend (i.e., the cascade as a whole produced the right answer)."

This is a confounded proxy: when task_type predicts wrong but the keyword path saves the day, the task_type stage is scored as "correct" even though it was the stage that erred. Likewise, when agentic-intent is right but model_router fails, the agentic stage is scored as "incorrect" despite being right.

The docstring at lines 503-525 explains this limitation, but it is buried in code. The stdout summary at line 738 prints `ece={row['ece']:.4f}` and `(>= threshold!)` annotation as if the value were a true per-stage ECE. Downstream consumers (CI gate, Plan 08 regression check) treat the value as authoritative.

**Fix:** Add a one-line caveat to the stdout summary just above the ECE table:

```python
print("Per-stage ECE (confounded proxy: y_true=backend_match across the full cascade)")
print("Target <= {:.2f}".format(ECE_THRESHOLD))
```

And/or expose the true per-stage ECE from the LLMRouterBench test split as a separate `ece_per_stage_canonical.csv` (mirroring `snapshot_baselines.py`).

### WR-06: `_decision_to_legacy_dict` assumes `model_mapping` available but `decide()` already consumed it from `artifacts`

**File:** `src/demo/demo_router.py:439-445`

**Issue:** `route_prompt()` packs `model_mapping` into `artifacts={...}` and then ALSO passes it as the third argument to `_decision_to_legacy_dict(decision, prompt, model_mapping)`. This works, but the decoupling is fragile: if a caller of `route_prompt` ever loads a different `model_mapping` for the brain than the demo holds, `_decision_to_legacy_dict` will resolve `choose_final_route(chosen_slug, model_mapping)` against the demo's view of the world while `decide()` used the brain's view.

A safer contract is to source the mapping from `decision.signals` (which records `route_source`, `openrouter_verified`, `route_tier` already) or from `artifacts["model_mapping"]` consistently.

**Fix:** Either (a) have `_decision_to_legacy_dict` accept `artifacts` instead of `model_mapping` and pull the mapping from there, or (b) document the assumption in the function docstring and add an `assert` that the demo and brain share the same dict object.

### WR-07: `src/routing/__main__.py` raises `SystemExit` at module body level instead of behind `if __name__ == "__main__"`

**File:** `src/routing/__main__.py:11`

**Issue:** The file's body is:

```python
from src.routing.decide import main
raise SystemExit(main())
```

Because `__main__.py` is only loaded by `python -m src.routing` in normal usage, the absence of a `__name__ == "__main__"` guard is benign in the documented invocation path. But it is non-idiomatic and a footgun: any tool that imports `src.routing.__main__` directly (some IDE auto-discovery, some doc builders, a poorly-written test that walks subpackages) will hard-exit the calling process.

**Fix:**

```python
from src.routing.decide import main

if __name__ == "__main__":
    raise SystemExit(main())
```

### WR-08: `snapshot_baselines.py` reads `classifier_training_with_types.csv` which is mutated in place by `inject_unknown_class_rows.py`

**File:** `src/evaluation/snapshot_baselines.py:56`, `scripts/inject_unknown_class_rows.py:36`

**Issue:** `scripts/inject_unknown_class_rows.py` rewrites `data_processed/classifier_training_with_types.csv` **in place** (`OUTPUT_CSV = INPUT_CSV`). `snapshot_baselines.py` then reads the same path to compute the **pre-calibration** baseline for the uncalibrated artifact in `models/uncalibrated/`. Whether the snapshot reflects the original 10-class CSV or the 11-class injected CSV depends entirely on which order the operator ran the two scripts.

Both orders happen to produce a stable baseline today because the uncalibrated artifact's `label_encoder.classes_` doesn't contain `"unknown"` and the `known_mask` filter in `_score_task_type_classifier` drops the injected rows. But the design is fragile: a future change that broadens the labeler vocabulary could silently change the baseline JSON without anyone realizing.

**Fix:** Either (a) make `inject_unknown_class_rows.py` write to a separate output file (e.g., `classifier_training_with_types_with_ood.csv`) and have the calibration training read that file, leaving the original immutable for the baseline snapshot; or (b) add a `--input-source-version` argument to `snapshot_baselines.py` that records the SHA-256 of the CSV at snapshot time and writes it to `baselines.json` for traceability.

## Info

### IN-01: `signals["agentic_intent"]` stores the string label, not the boolean used by the cascade

**File:** `src/routing/decide.py:368-369`

**Issue:**

```python
is_agentic = (agentic_label == "agentic")
signals["agentic_intent"] = agentic_label   # string "agentic" / "conversational"
```

The variable name `agentic_intent` implies a boolean (and the cascade in `policy.decide_backend` accepts a `bool`), but `signals["agentic_intent"]` holds the string label. CONTEXT D-03 lists `agentic_intent` as a signal key without specifying type, so the existing tests do not assert on type. Downstream consumers (Phase 3 SQLite store via STORE-02, Phase 4 UI chip) will need to be told whether to read the string label or compute the bool from it.

**Fix:** Store the bool alongside the string for clarity:

```python
signals["agentic_intent"] = bool(is_agentic)
signals["agentic_label"] = agentic_label   # string for display
```

### IN-02: Missing `__init__.py` for `src/evaluation/` and `src/task_classifier/` packages

**File:** `src/evaluation/`, `src/task_classifier/` (directories)

**Issue:** `src/routing/__init__.py` and `src/feature_extraction/__init__.py` exist (the latter empty), but `src/evaluation/` and `src/task_classifier/` lack `__init__.py`. The project works under PEP 420 namespace packages + pytest's `--import-mode=importlib`, but a future `pip install prompt-optimizer` consumer could fail to find these as importable packages depending on hatchling's wheel layout. ARCHITECTURE.md flags this as a known inconsistency.

**Fix:** Add empty `src/evaluation/__init__.py` and `src/task_classifier/__init__.py` files for consistency. Not blocking for Phase 1; can defer to a later cleanup phase.

### IN-03: `_contains_any_keyword` uses unbounded substring match — known false-positive surface

**File:** `src/routing/policy.py:67-75`

**Issue:** The keyword match is `kw in prompt_lower`, which produces substring matches like:

- `"fix"` matches `"prefix"`, `"postfix"`, `"fixture"`, `"infix"`
- `"open"` matches `"openness"`, `"open source"`, `"reopen"`
- `"url"` matches `"curl"`, `"burl"`
- `"write"` matches `"overwrite"`, `"underwrite"`

The inline comment at lines 67-74 acknowledges this and argues that "short, distinctive verbs whose substring forms rarely produce false positives in conversational prompts." The Plan 07 carry-forward "4 openrouter rows misroute to claude_code in canary" is consistent with this design choice.

This is documented and accepted; flagging as INFO so that any future cascade-tuning work has a single reference point. If the planner wants whole-word matching, the fix is `re.search(rf"\b{re.escape(kw)}\b", prompt_lower)` per keyword.

### IN-04: ROUTER-06 cost tiebreaker fires on 0/42 canonical canary prompts; not a regression but documented in policy.py for completeness

**File:** `src/routing/policy.py:214-270`

**Issue:** Per the carry-forward flags, the `quality_first_pick` tiebreaker fires 0/42 times on the canary because the calibrated `model_router` produces sharp top-1 predictions on these prompts. The policy is correct (only break ties on equal-quality candidates by lower cost), but Phase 1 has no canary case that exercises it.

The `test_quality_first_pick_tiebreak_prefers_cheaper_tier` test in `test_rule_cascade.py:162-174` does exercise the tiebreak via a synthetic top-k input, so unit-test coverage is in place even if integration coverage is dormant. No action required for Phase 1.

### IN-05: `test_schema.py` test acknowledges a plan off-by-two in dash-position assertion and asserts the canonical position

**File:** `src/routing/tests/test_schema.py:84-110`

**Issue:** The test correctly recognizes that the plan's acceptance line `ord(FALLBACK_RATIONALE_SUFFIX[-12]) == 8212` had an off-by-two error (the dash is at index -10, not -12), and asserts against the correct position. The full character-code fingerprint at lines 105-110 is also correct. No action needed — well-handled gotcha — flagging only for awareness.

### IN-06: `model_router.joblib` 6-key shape carries `target_column` outside the canonical 5-key minimum

**File:** `src/demo/tests/test_artifact_compat.py:111-138`, `src/model_router/train_model_router.py:352-359`

**Issue:** The model_router artifact correctly preserves the canonical 5 keys plus a 6th `target_column` key. `load_joblib_artifacts()` accepts it because the validator only checks the 5-key minimum. This is the intended behavior per CONTEXT, but the test explicitly asserts the 6-key shape rather than just the 5-key minimum, which couples the test to the current implementation. If a future Plan ever consolidates `target_column` into the artifact's `target_type` metadata, the test will break unnecessarily.

**Fix:** Optional — relax the assertion to check the 5-key minimum plus `target_column`'s presence/value rather than exact key set. Not blocking.

### IN-07: `snapshot_baselines.py` and `evaluate_routing.py` have duplicated 16-line ECE helpers

**File:** `src/evaluation/snapshot_baselines.py:88-123`, `src/evaluation/evaluate_routing.py:187-218`, `src/evaluation/tests/test_no_regression.py:129-154`, `src/task_classifier/train_agentic_intent.py:236-272`

**Issue:** Four copies of the same `expected_calibration_error()` helper exist across the codebase. Each comment explains the duplication as "lifted verbatim so this module doesn't import from the other". A single shared helper in `src/evaluation/__init__.py` (once IN-02 is fixed) or `src/evaluation/metrics.py` would collapse the duplication.

The implementations are NOT bit-identical: `train_agentic_intent.py` puts the `if n == 0: return 0.0` check on line 256-257 (AFTER computing `pred_class`/`confidences`/`accuracies` on lines 249-251), which on a zero-length input would `arr.argmax(axis=1)` first. The other three copies check len first. With `numpy`, `np.empty((0, k)).argmax(axis=1)` raises `ValueError: attempt to get argmax of an empty sequence`, so the agentic-intent copy will CRASH on an empty input where the other three return 0.0.

In practice, none of the call sites pass an empty array, so the latent bug is dormant. But this is exactly the kind of drift that motivates de-duplication.

**Fix:** Consolidate into a single `src/evaluation/metrics.py:expected_calibration_error(...)` and import from it everywhere. Bonus: fix the empty-input ordering in the agentic-intent version (move the `if n == 0` check above the `argmax` / `max` calls).

---

_Reviewed: 2026-05-14_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
