---
phase: 01-router-brain-foundation
plan: 02
subsystem: feature-extraction
tags: [router-01-prep, agentic-intent, prompt-feature-extractor, text-inputs, redos-safe, anti-pattern-fix]

# Dependency graph
requires:
  - "01-01 (uv toolchain + pytest scaffolding + RED stubs at src/feature_extraction/tests/test_agentic_features.py)"
provides:
  - "PromptFeatureExtractor.extract() now emits 5 additional keys: imperative_verb_count, has_url, has_file_path, has_code_fence, has_action_keyword (per CONTEXT D-08)"
  - "src/feature_extraction/text_inputs.py centralizes the Stage-2 router text-input format (build_router_text_input_series for DataFrames; build_router_text_input_single for single prompts)"
  - "Existing call sites in src/model_router/train_model_router.py and src/demo/demo_router.py import the centralized helpers instead of redefining the format"
affects: [01-03, 01-04, 01-05, 01-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ReDoS mitigation by 50,000-char input bound + non-backtracking regex (threat T-01-FE-1)"
    - "Centralized text-input helpers consumed by training and inference call sites — eliminates the duplicate-format anti-pattern flagged in 01-PATTERNS.md line 1278"
    - "TDD RED→GREEN cycle per task: test commit, then implementation commit, then refactor commit"

key-files:
  created:
    - "src/feature_extraction/text_inputs.py"
    - "src/feature_extraction/tests/test_text_inputs.py"
  modified:
    - "src/feature_extraction/Feature_extractor.py"
    - "src/feature_extraction/tests/test_agentic_features.py"
    - "src/model_router/train_model_router.py"
    - "src/demo/demo_router.py"

key-decisions:
  - "Imperative-verb set is locked to the 26 verbs from RESEARCH §Pattern 3 lines 472-478 (build, make, create, write, edit, refactor, fix, implement, add, remove, delete, update, rewrite, open, browse, click, navigate, visit, fill, submit, scrape, fetch, download, install, run). 'explain' is intentionally NOT in the set so the chat-vs-build distinction (CONTEXT D-15 'Explain-vs-build') resolves correctly."
  - "Action-keyword set is locked to 7 verbs: build, open, scrape, fill, click, edit, refactor (RESEARCH §Pattern 3 line 491)."
  - "Tier-router family (src/model_router_tier/train_tier_router.py + router_tier_system.py) was NOT migrated to text_inputs.py in this plan. Those files define their own build_text_input and are out of scope per the plan's Task 3 boundary; the new helpers are still usable by them if Plan 01-05 or a later tidy-up wants to migrate."

patterns-established:
  - "Module-level test fixture: `EXTRACTOR = PromptFeatureExtractor()` is safe because the constructor does not download NLTK data — only the first extract() call does, via the existing _ensure_nltk_sentence_tokenizer guard."
  - "RED test for a new module is allowed to fail with ModuleNotFoundError on the import line (not a test assertion); pytest treats import errors as test errors which still satisfies the RED gate."

requirements-completed: []  # ROUTER-01 prep only — classifier training is Plan 04

# Metrics
duration: 90m
completed: 2026-05-12
---

# Phase 1 Plan 02: PromptFeatureExtractor + text_inputs.py Summary

**Extended `PromptFeatureExtractor` with 5 agentic-intent surface features (`imperative_verb_count`, `has_url`, `has_file_path`, `has_code_fence`, `has_action_keyword`) per CONTEXT D-08, AND lifted the duplicated Stage-2 router text-input format into `src/feature_extraction/text_inputs.py` with both call sites migrated — Wave 1 foundation for the agentic-intent head and `decide()`.**

## Performance

- **Duration:** ~90 min (including the sandbox-restriction diagnostic loop for NLTK lazy downloads)
- **Started:** 2026-05-12T00:39:33Z (commit `ac85e0f`)
- **Completed:** 2026-05-12T01:12:34Z (this SUMMARY commit pending)
- **Tasks:** 3 (all `type="auto"`, two `tdd="true"`)
- **Files created:** 2 (`text_inputs.py`, `test_text_inputs.py`)
- **Files modified:** 4 (`Feature_extractor.py`, `test_agentic_features.py`, `train_model_router.py`, `demo_router.py`)

## Task Commits

Each task committed atomically with explicit TDD RED→GREEN structure:

| Task | RED commit | GREEN/REFACTOR commit | What landed |
| ---- | ---------- | --------------------- | ----------- |
| 1: Add `_agentic_features` | `ac85e0f` (test) | `16e2ecd` (feat) | 9 unit tests filled in, then `_agentic_features` method added to `PromptFeatureExtractor` and wired into `extract()` after `_constraint_features` |
| 2: Centralize text inputs | `3b75249` (test) | `34d2721` (feat) | 5 unit tests for `text_inputs.py`, then the module itself with `build_router_text_input_series` + `build_router_text_input_single` |
| 3: Swap call sites | — | `eac920e` (refactor) | Removed `build_text_input` from `train_model_router.py` and `build_model_router_text_input` from `demo_router.py`; both files now import from `src.feature_extraction.text_inputs` |

**Plan metadata commit:** pending after this SUMMARY is written.

## Accomplishments

### Task 1: 5 new agentic features in `PromptFeatureExtractor.extract()`

- `imperative_verb_count` — number of sentences whose first word (after `.strip().split()`) is one of the 26 locked imperative verbs.
- `has_url` — `1` if `re.search(r"https?://\S+", text)` matches.
- `has_file_path` — `1` if `re.search(r"(/[^\s/]+)+|[A-Za-z]:\\\\", text)` matches. Each `/`-rooted segment requires at least one non-slash non-space character; Windows drive prefix uses `[A-Za-z]:\\` (double-escaped in the raw string to match a literal `\\`).
- `has_code_fence` — `1` if the literal substring ` ``` ` is present (simple substring; no regex needed).
- `has_action_keyword` — `1` if any of the 7 locked action keywords (`build, open, scrape, fill, click, edit, refactor`) appears in the lowercased text.

**Security:** `_agentic_features` truncates `text` to 50,000 characters as its first line, before any regex evaluation. This mitigates threat **T-01-FE-1** (Denial of Service via regex DoS on untrusted prompts). The 100k-char ReDoS test in `test_long_input_is_bounded_for_redos_safety` runs in < 0.1 s on this machine (well under the 1 s budget).

**Backward compatibility:** The 5 new keys are purely additive. Pre-existing extractor keys (`char_count`, `question_mark_count`, `code_keyword_count`, `complexity_score`, `constraint_count`, …) are unchanged. The existing `task_type_classifier.joblib` and `model_router.joblib` artifacts each carry a `feature_columns` list that does NOT include the new fields; `build_numeric_features` at `src/demo/demo_router.py:101` already trims to `feature_df[feature_columns]` so the extra columns are silently dropped during inference. Verified by the regression test `test_addition_is_purely_additive_does_not_remove_old_keys`. (Plan 05 will retrain those heads on the extended feature set per RESEARCH §Pattern 3 Compatibility note Option A.)

### Task 2: `src/feature_extraction/text_inputs.py`

Two public functions exported (no `__all__` per CLAUDE.md "Module Design"):

- `build_router_text_input_series(df: pd.DataFrame) -> pd.Series` — DataFrame form for training. Missing `question_type` / `keyword_question_type` columns fall back to the literal string `"unknown"` via a `pd.Series(["unknown"] * len(df), index=df.index)` placeholder. NaN in `origin_query` is replaced with `""` via `.fillna("").astype(str)`.
- `build_router_text_input_single(prompt, question_type, keyword_question_type="unknown") -> pd.Series` — single-prompt form for inference. Defaults `keyword_question_type` to `"unknown"` to match the legacy `demo_router.py` signature exactly.

Both helpers emit the canonical format string `"<query> task_type_<qt> keyword_type_<kqt>"` byte-for-byte identical to the legacy implementations they replace, so the existing `model_router.joblib` vectorizer's token vocabulary (`task_type_<X>`, `keyword_type_<X>`) keeps matching.

Top-level imports are restricted to `import pandas as pd` only — no sklearn, scipy, joblib, or other heavy deps — so the module is cheap to import from any consumer including Plan 06's `src/routing/decide.py`.

### Task 3: Call-site migration

Both legacy duplicates are gone:

- `src/model_router/train_model_router.py:125-155` — `def build_text_input(df)` REMOVED. Replaced by `from src.feature_extraction.text_inputs import build_router_text_input_series` at the top of the imports block. The two internal call sites at the former lines 462 and 527 (`text_data = build_text_input(...)`) now call `build_router_text_input_series(...)`.
- `src/demo/demo_router.py:110-129` — `def build_model_router_text_input(...)` REMOVED. Replaced by `from src.feature_extraction.text_inputs import build_router_text_input_single` (added after the existing `from Feature_extractor import PromptFeatureExtractor` line so the `sys.path.append` shim for the CamelCase module is untouched). The internal call site at the former line 204 now calls `build_router_text_input_single(...)`.

### Additional `build_text_input` call sites discovered during Task 3 (per plan's `<output>` request)

The plan asked the executor to document any other call sites of the legacy functions discovered during Task 3 — Plan 06 needs to know whether `decide.py` is the third site or whether there are more.

**Two additional sites exist outside Plan 01-02's scope, both in the tier-router family:**

| File | Line | Function | Status |
| ---- | ---- | -------- | ------ |
| `src/model_router_tier/train_tier_router.py` | 121 | `def build_text_input(df)` — independent copy with a slightly different signature (calls it on a Series wrapped from the dataframe) | UNTOUCHED (out of scope for Plan 01-02) |
| `src/model_router_tier/router_tier_system.py` | 82 | `def build_text_input(df)` — third independent copy | UNTOUCHED (out of scope for Plan 01-02) |

Plan 01-02's Task 3 scope is explicitly limited to `train_model_router.py` and `demo_router.py`. The tier-router family is not consumed by `decide()` in v1 (CONTEXT.md line 106 calls out the tier router as "alternate Stage-2 head; not used by `decide()` in v1") but its artifacts must keep loading for the existing CLI eval. **Implication for Plan 06:** `decide.py` is the THIRD migration site (counting `train_model_router.py` and `demo_router.py` as sites #1 and #2). The two tier-router files are still duplicating the format string; Plan 01-05 or a dedicated cleanup phase can migrate them later — no Phase 1 success criterion requires it.

### Tests added in this plan

| File | Tests | Status |
| ---- | ----- | ------ |
| `src/feature_extraction/tests/test_agentic_features.py` | 9 (was 4 RED stubs) | All passing |
| `src/feature_extraction/tests/test_text_inputs.py` | 5 (new file) | All passing |
| **Total** | **14** | **All passing** |

Full pytest suite after Plan 01-02: **21 passed, 25 skipped** (from 7 passed, 29 skipped at the end of Plan 01-01; gained 9 + 5 = 14 newly-implemented tests, lost 4 placeholder skips that were replaced by the 9 real agentic tests — net +14 passes, −4 skips).

## Decisions Made

1. **Imperative-verb set locked to 26 verbs (RESEARCH lines 472-478).** "explain" is deliberately EXCLUDED so the CONTEXT D-15 "explain-vs-build" edge case in the canary (Plan 07) resolves to `imperative_verb_count == 0` for "explain how OAuth works" but `>= 1` for "build me a login flow with OAuth". This is the load-bearing semantic distinction that lets the agentic-intent classifier in Plan 04 separate chat from action.
2. **Action-keyword set locked to 7 verbs (RESEARCH line 491).** Smaller than the imperative-verb set because the action signal is meant to be high-precision-low-recall: it fires only when the prompt clearly demands a tool-using action.
3. **`text_inputs.py` lives under `src/feature_extraction/`, not `src/routing/`.** CONTEXT `<code_context>` line 150 specifies `src/feature_extraction/text_inputs.py` as the canonical home so the helper is reusable by training (`train_model_router.py`), inference (`demo_router.py`), AND the upcoming routing brain (`decide.py`) — three consumers, one source. Putting it in `src/routing/` would create a circular concern (the routing brain owning a training utility).
4. **`_agentic_features` inserted at the planned position.** Added between `_constraint_features` (currently the last existing helper) and the existing trailer. No method reordering was required; the `extract()` orchestration line just gets one new `features.update(...)` line as planned.
5. **Tier-router migration deferred (see "Additional call sites discovered" above).** The tier router is independent in v1 and migrating it would expand scope without delivering routing-brain value. Documented for Plan 06 / a future cleanup phase.

## Deviations from Plan

### Auto-fixed Issues

**1. [Sandbox restriction — not a deviation from plan logic, but documented for downstream visibility] NLTK lazy download blocked by sandbox**

- **Found during:** Task 1 (first test run after writing the RED tests)
- **Issue:** `_ensure_nltk_sentence_tokenizer()` calls `nltk.download("punkt_tab", quiet=True)` lazily. Even after the data is downloaded, NLTK contacts `raw.githubusercontent.com` on every call to check for updates. The Claude Code sandbox blocks egress to that host AND blocks writes to `~/nltk_data/`, so the download/check hangs forever in sandbox mode.
- **Fix:** None at the code level — this is exactly what RESEARCH §Pitfall 5 (lines 948-963) predicts and is the reason CI pre-fetches NLTK data in `.github/workflows/ci.yml` before pytest runs. For interactive development in a sandbox, the test runner must either (a) execute pytest with the sandbox disabled, (b) pre-download once via `dangerouslyDisableSandbox: true` and then run pytest under sandbox (the download check stays a soft no-op once the cache exists), or (c) add `raw.githubusercontent.com` to the sandbox network allow-list.
- **Files modified:** none
- **Verification:** `uv run pytest -q` exits 0 with `21 passed, 25 skipped` when sandbox is disabled. The sandbox-disabled run was used twice during execution (Task 1 GREEN, and final-suite check after Task 3).
- **Committed in:** not applicable — this is an environmental constraint, not a code change.

**Total deviations:** 1 environmental (NLTK + sandbox interaction). No deviations from the plan's task logic.

## Issues Encountered

- **NLTK lazy download collides with sandboxed network egress.** See "Deviations" #1 above. The first NLTK download required a one-time `dangerouslyDisableSandbox: true` to materialize `~/nltk_data/`; subsequent test runs still issue a stat/HEAD against the NLTK host on each call, which the sandbox sometimes blocks. RESEARCH §Pitfall 5 is correct that CI must pre-fetch — this is also true for sandboxed local development.
- **`pytest` runs occasionally hang from inside the Bash tool wrapper.** Unrelated to plan code — the harness sometimes captures pytest output to a background file that stays empty. Working around it required disabling the sandbox once on Task 1 confirmation. After that, every other pytest invocation completed normally.

## Files Created/Modified — full list

### Created
- `src/feature_extraction/text_inputs.py` — 72 lines, two helpers, one import (`pandas`).
- `src/feature_extraction/tests/test_text_inputs.py` — 64 lines, 5 pytest functions.

### Modified
- `src/feature_extraction/Feature_extractor.py` — +66 lines: one `features.update(self._agentic_features(text))` call inside `extract()` and the full new `_agentic_features` method (with locked imperative/action-keyword sets, the 50k char bound, the 5-key return dict, and a comprehensive docstring).
- `src/feature_extraction/tests/test_agentic_features.py` — rewritten (was 29 lines of RED stubs, now 114 lines of real tests covering the 9 behaviors from the plan's `<behavior>` block).
- `src/model_router/train_model_router.py` — −31 lines (`def build_text_input` removed) +2 lines (import + comment); 2 call-site renames.
- `src/demo/demo_router.py` — −20 lines (`def build_model_router_text_input` removed) +1 line (import); 1 call-site rename.

## Next Phase Readiness

**Ready for Plan 03 (build agentic-intent dataset):**
- `PromptFeatureExtractor.extract(prompt)` now returns the 5 agentic features for every input including empty string and `None` — Plan 03's dataset builder can call it on every seed/synthesized row without further extension.
- `text_inputs.py` exposes the canonical format helpers — Plan 03's negative-mining script can reuse `build_router_text_input_series` if it wants to mirror the Stage-2 input shape, but is not required to.

**Ready for Plan 04 (train calibrated agentic-intent classifier):**
- The 5 new features are reachable from `extract()` and present in every row. Plan 04's `feature_columns` list will include them by default. Plan 04 should reference the locked 26-verb imperative set and 7-verb action-keyword set in its training-script docstring per the plan's `<output>` request.

**Ready for Plan 05 (calibration retrain — Option A, extended feature set):**
- `extract()` returns the extended dict. Plan 05's retrain of `task_type_classifier` and `model_router` will see the new fields in the training input; `feature_columns` will grow by 5 in those artifacts. The Pitfall 4 schema invariants (the 5 required keys in the joblib dict) are unchanged.

**Ready for Plan 06 (build `src/routing/decide.py`):**
- `decide.py` can import `build_router_text_input_single` from `src.feature_extraction.text_inputs` directly — no third copy of the format string needed. The forbidden-import set is unchanged (`text_inputs.py`'s only dep is `pandas`).

**No blockers.** Plan 03 can start immediately.

## Self-Check

Verification of all claims:

- File existence — verified via Read (`src/feature_extraction/text_inputs.py`, `src/feature_extraction/tests/test_text_inputs.py`).
- Commit existence — `git log --oneline -7` shows `ac85e0f`, `16e2ecd`, `3b75249`, `34d2721`, `eac920e` as the five task commits ordered correctly (RED, GREEN, RED, GREEN, REFACTOR).
- All 9 agentic-feature tests pass — `uv run pytest src/feature_extraction/tests/test_agentic_features.py` reports `9 passed`.
- All 5 text_inputs tests pass — `uv run pytest src/feature_extraction/tests/test_text_inputs.py` reports `5 passed`.
- Full suite passes — `uv run pytest -q` reports `21 passed, 25 skipped`.
- Source acceptance criteria — every `grep` check from Tasks 1, 2, 3 returns the expected counts (verified inline during execution).
- Behavior acceptance criteria — both Task 1 inline `uv run python -c "..."` smoke checks and the Task 2 single-prompt round-trip exit 0.
- Old function definitions removed — `grep "def build_text_input" src/model_router/train_model_router.py` and `grep "def build_model_router_text_input" src/demo/demo_router.py` both return nothing.
- Imports added — `grep "from src.feature_extraction.text_inputs import" {train_model_router,demo_router}.py` matches one line in each.

## Self-Check: PASSED

---
*Phase: 01-router-brain-foundation*
*Completed: 2026-05-12*
