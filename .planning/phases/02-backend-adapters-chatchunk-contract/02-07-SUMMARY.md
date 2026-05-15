---
phase: 02
plan: 07
subsystem: redaction-pattern-parity-and-ordering
gap_closure: true
closes_gaps:
  - "CR-04 (Truth 19) — pre-commit no-secrets.sh regex set MATCHES logging_filter.SECRET_PATTERNS"
  - "CR-05 (Truth 20) — Bearer sk-ant-… redacts as a single `Bearer ***REDACTED***` unit"
tags: [redaction, secret-scanning, pattern-parity, bearer-ordering, gap-closure, secure-01, secure-02]
dependency_graph:
  requires:
    - "apps.api.backends.logging_filter.SECRET_PATTERNS (Plan 02-00 Wave 0 — original three-pattern list)"
    - "scripts/no-secrets.sh (Plan 02-04 — pre-commit hook with locked D-09 regex)"
    - ".github/workflows/ci.yml (Plan 02-04 — pre-commit step at line 31-32)"
    - "apps.api.backends.tests.test_logging_filter (Plan 02-00 — existing 7-test suite)"
  provides:
    - "logging_filter.SECRET_PATTERNS reordered (Bearer FIRST) — canonical Authorization headers redact as a single unit"
    - "scripts/no-secrets.sh — unified regex matching SECRET_PATTERNS alphabets exactly"
    - "test_bearer_prefixed_sk_ant_redacts_as_bearer_unit — CR-05 regression"
    - "test_logging_filter_and_no_secrets_regex_parity — CR-04 parity check at CI time"
    - ".github/workflows/ci.yml — dedicated `Regex parity check` step"
  affects:
    - "VERIFICATION.md Truth 19 (CR-04) and Truth 20 (CR-05) — flip FAILED → VERIFIED upon re-verification"
    - "Every future PR — drift between the two regex sets now fails CI in a one-line failure"
    - "Every future `git commit` — underscore-bearing OpenAI keys (`sk-…_…`) and tab-separated Bearer headers now blocked at staging time"
tech_stack:
  added: []
  patterns:
    - "More-general carrier consumes its more-specific payload: order regex-redaction stack so the broader pattern (Bearer\\s+…) fires before the narrower one (sk-ant-…) when both could match the same span"
    - "Synchronisation contract enforced by automated test rather than developer convention: parity test reads the bash script verbatim, extracts the alternation, and asserts each sub-pattern (modulo `[[:space:]]+` ↔ `\\s+` translation) appears in SECRET_PATTERNS"
    - "Dedicated CI step duplicates the test from the broader suite so a future contract drift surfaces with a single named-step failure rather than buried inside `pytest apps/api/backends`"
key_files:
  created:
    - ".planning/phases/02-backend-adapters-chatchunk-contract/02-07-SUMMARY.md"
  modified:
    - "apps/api/backends/logging_filter.py"
    - "scripts/no-secrets.sh"
    - "apps/api/backends/tests/test_logging_filter.py"
    - ".github/workflows/ci.yml"
decisions:
  - "Bearer pattern FIRST in SECRET_PATTERNS — canonical `Authorization: Bearer sk-…` headers consume the Bearer pattern (whose alphabet `[A-Za-z0-9_.-]{20,}` is wider than sk-ant- / sk-) as a single span before the more-specific provider rules would otherwise match the body. Replacement string is the locked `Bearer ***REDACTED***` (literal space + marker) that downstream scrubbers anchor on."
  - "Parity translation is one-way: bash `[[:space:]]+` → python `\\s+`. The reverse (python `\\s+` → bash `[[:space:]]+`) is also valid because `\\s` and `[[:space:]]` are equivalent character classes in this context. Parity test translates bash → python before substring comparison; if a future contributor switches the script to a different whitespace form (e.g. literal space), the translation no longer maps and the test surfaces the drift."
  - "Existing `test_redaction_replaces_anthropic_keys` updated to drop the `Bearer ` prefix from its input rather than left as-is. Reason: with the Bearer-first reorder, a Bearer-prefixed sk-ant-… payload now redacts to `Bearer ***REDACTED***` rather than `***REDACTED-ANTHROPIC***`, so the original assertion would have failed. The dedicated `test_bearer_prefixed_sk_ant_redacts_as_bearer_unit` covers the Bearer-prefixed path explicitly."
  - "CI parity step ALSO runs as part of the broader `Phase 2 — apps/api/backends unit tests (no live)` step; the duplication is intentional. A dedicated named step provides (a) a one-line failure signal in workflow logs when someone edits one of the two regex sets, and (b) explicit contract naming (SECURE-01 + SECURE-02) in the GitHub Actions UI."
metrics:
  duration: "3m"
  tasks_completed: 1
  files_modified: 4
  files_created: 1
  completed_date: "2026-05-15"
  test_results:
    test_logging_filter_pass: "9/9 (was 7; +2 new gap-closure regressions)"
    phase_2_backends_pass: "133 passed / 1 skipped / 3 deselected (was 131 passed; +2 new tests)"
    phase_1_d18_guard_pass: "7/7 (no regression)"
    pre_commit_clean_tree: "exits 0"
    yaml_workflow_parses: true
---

# Phase 02 Plan 07: Redaction Pattern Parity & Bearer Ordering Summary

**One-liner:** Closes CR-04 + CR-05 — `SECRET_PATTERNS` reordered (Bearer first) so canonical Authorization headers redact as a single `Bearer ***REDACTED***` unit; `scripts/no-secrets.sh` regex unified with `logging_filter` alphabets; parity test + dedicated CI step prevent future drift.

## Goal

Close two redaction-subsystem defects discovered by Plan 02-04's verification report:

- **CR-04 (Truth 19, FAILED):** the pre-commit hook regex set in `scripts/no-secrets.sh` DIVERGED from the runtime filter:
  - OpenAI: filter `sk-[A-Za-z0-9_-]{20,}` vs hook `sk-[A-Za-z0-9]{20,}` (alphabet missing `_-`). An underscore-bearing key like `sk-AAAAA_AAAAAAAAAAAAAAAAAA` was redacted at runtime but **committed through unblocked**.
  - Bearer: filter `Bearer\s+` (any whitespace) vs hook `Bearer ` (literal space). A `Bearer\t<key>` header was redacted at runtime but **committed through unblocked**.
- **CR-05 (Truth 20, FAILED):** pattern ORDER caused `Authorization: Bearer sk-ant-…` to rewrite to `Authorization: Bearer ***REDACTED-ANTHROPIC***` — the `Bearer ` literal was preserved verbatim alongside the anthropic marker. Downstream scrubbers anchoring on the canonical `Bearer ***REDACTED***` form missed this case.

The `logging_filter.py` docstring (lines 29-31) explicitly claimed the two regex sets were "intentionally synchronised" — a contract drift here defeated both controls.

## Tasks Completed

### Task 1: Reorder SECRET_PATTERNS (Bearer first), unify scripts/no-secrets.sh regex, add regression + parity tests, wire CI (TDD)

**RED gate:** commit `3c5f71c` — `test(02-07): add failing regressions for redaction regex parity + Bearer ordering`. Added three test changes:
- New `test_bearer_prefixed_sk_ant_redacts_as_bearer_unit`: asserts `Authorization: Bearer sk-ant-api03-XYZ…` redacts to `Bearer ***REDACTED***` (and NOT `Bearer ***REDACTED-ANTHROPIC***`). Failed RED with `AssertionError: assert 'Bearer ***REDACTED***' in 'INFO test.bearer_anthropic:test_logging_filter.py:48 Authorization: Bearer ***REDACTED-ANTHROPIC***'`.
- New `test_logging_filter_and_no_secrets_regex_parity`: reads `scripts/no-secrets.sh`, extracts the alternation regex via `_re.search(r"grep -E '\((?P<body>[^']+)\)'", script_src)`, splits on `|`, translates `[[:space:]]+` → `\s+`, and asserts each sub-pattern appears in SECRET_PATTERNS. Failed RED with `AssertionError: scripts/no-secrets.sh contains pattern 'sk-[A-Za-z0-9]{20,}' which is NOT present in logging_filter.SECRET_PATTERNS ['sk-ant-…', 'sk-[A-Za-z0-9_-]{20,}', 'Bearer\\s+…']`.
- Updated `test_redaction_replaces_anthropic_keys` to drop the `Bearer ` prefix from its input (the dedicated new test now covers Bearer-prefixed sk-ant-).

**GREEN gate:** commit `e4383e5` — `fix(02-07): unify redaction regex sets + Bearer-first ordering (CR-04 + CR-05)`. Applied four file modifications:

1. **`apps/api/backends/logging_filter.py`:**
   - Reordered `SECRET_PATTERNS`: `[Bearer\s+…, sk-ant-…, sk-…]` (was `[sk-ant-, sk-, Bearer]`).
   - Updated module docstring (lines 29-41) to record the unified alphabets contract and the Bearer-first ordering rationale. Points readers at the parity test as the authoritative drift detector.
   - Replaced the `Ordered: more-specific patterns first` inline comment (now stale) with `Ordered: Bearer pattern FIRST so a canonical Authorization: Bearer sk-… header is consumed as a single unit. …`
   - Alphabets unchanged: `Bearer\s+[A-Za-z0-9_.\-]{20,}`, `sk-ant-[A-Za-z0-9_-]{8,}`, `sk-[A-Za-z0-9_-]{20,}`.

2. **`scripts/no-secrets.sh`:**
   - Updated line 14 from `(sk-ant-[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9]{20,}|Bearer [A-Za-z0-9_.-]{20,})` to `(sk-ant-[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9_-]{20,}|Bearer[[:space:]]+[A-Za-z0-9_.-]{20,})`. Two diffs from the prior form:
     - sk-: `[A-Za-z0-9]{20,}` → `[A-Za-z0-9_-]{20,}` (alphabet gains `_-`).
     - Bearer: literal space → `[[:space:]]+` (any whitespace, matches python `\s+`).
   - Updated the header comment block (lines 2-13) to record the unified alphabets, name the parity test, and point at `02-VERIFICATION.md CR-04`.

3. **`apps/api/backends/tests/test_logging_filter.py`:**
   - Added two new tests (described above in RED gate).
   - Updated `test_redaction_replaces_anthropic_keys` to drop the `Bearer ` prefix from its input so the test still exercises the sk-ant- branch after the reorder.
   - Existing `test_redaction_replaces_bearer_tokens` uses `abcdefghijklmnopqrstuvwxyz0123ABCDEF` (no `sk-` prefix), so it continues to exercise the Bearer pattern without conflict.
   - `test_secret_patterns_count` unchanged — still asserts `len(SECRET_PATTERNS) == 3`. Count is unchanged; only the ORDER changed.

4. **`.github/workflows/ci.yml`:**
   - Inserted new step `Regex parity check (SECURE-01 + SECURE-02 contract)` between the existing `Run pre-commit hooks (SECURE-02 + OSS-06)` and `OSS-06 — claude_agent_sdk import smoke` steps. Runs:
     ```
     uv run pytest -m 'not live' \
       apps/api/backends/tests/test_logging_filter.py::test_logging_filter_and_no_secrets_regex_parity \
       -x -q
     ```
   - The parity test ALSO runs as part of the broader `Phase 2 — apps/api/backends unit tests (no live)` step (preserved verbatim). The duplication is intentional — a dedicated step gives a single-line failure signal in workflow logs when a future contributor hand-edits one of the two regex sets.

## Files Modified

| File | Change |
| ---- | ------ |
| `apps/api/backends/logging_filter.py` | SECRET_PATTERNS reordered (Bearer first); docstring + inline comment updated to record the unified alphabets contract and Bearer-first rationale. |
| `scripts/no-secrets.sh` | Regex on line 14 unified with SECRET_PATTERNS alphabets (`sk-` gains `_-`; `Bearer ` → `Bearer[[:space:]]+`). Header comment updated. |
| `apps/api/backends/tests/test_logging_filter.py` | +2 new tests (Bearer-prefixed sk-ant- regression + parity check). One existing test updated to drop now-stale Bearer prefix. |
| `.github/workflows/ci.yml` | +1 dedicated parity-check step after pre-commit and before OSS-06 smoke. |

## Files Created

| File | Purpose |
| ---- | ------- |
| `.planning/phases/02-backend-adapters-chatchunk-contract/02-07-SUMMARY.md` | This summary. |

## Manual Paste-Test Outcomes

Both CR-04 reproductions now BLOCK at staging time (were previously committed through unblocked):

| Reproduction | Pre-fix behavior | Post-fix behavior |
| ------------ | ---------------- | ----------------- |
| `printf 'sk-AAAAA_AAAAAAAAAAAAAAAAAA\n' > deleteme.tmp && git add deleteme.tmp && bash scripts/no-secrets.sh` | exit 0 (slipped through) | exit 1 — `ERROR: Staged content contains what looks like an API key or bearer token.` BLOCKED. |
| `printf 'Bearer\tabcdefghijklmnopqrstuvwxyz0123ABCDEF\n' > deleteme.tmp && git add deleteme.tmp && bash scripts/no-secrets.sh` | exit 0 (slipped through) | exit 1 — `ERROR: Staged content contains what looks like an API key or bearer token.` BLOCKED. |

CR-05 regression:

| Input | Pre-fix output | Post-fix output |
| ----- | -------------- | --------------- |
| `logger.info("Authorization: Bearer sk-ant-api03-XYZ1234567890ABCDEFGHIJKL")` | `Authorization: Bearer ***REDACTED-ANTHROPIC***` (Bearer literal exposed) | `Authorization: Bearer ***REDACTED***` (single unit; downstream scrubbers anchor here). |

## Verification

All acceptance criteria PASS:

```bash
# 1. Full logging_filter test file: 9 passed (was 7; +2 new).
$ uv run pytest -m 'not live' apps/api/backends/tests/test_logging_filter.py -v
============================== 9 passed in 0.01s ===============================

# 2 + 3. New gap-closure tests pass in isolation.
$ uv run pytest -m 'not live' \
    apps/api/backends/tests/test_logging_filter.py::test_bearer_prefixed_sk_ant_redacts_as_bearer_unit \
    apps/api/backends/tests/test_logging_filter.py::test_logging_filter_and_no_secrets_regex_parity \
    -v
============================== 2 passed in 0.01s ===============================

# 4. Pre-commit clean-tree run exits 0 (no false positives from the updated regex).
$ uv run pre-commit run --all-files
Block secrets in staged content..........................................Passed
Block deprecated claude-code-sdk.........................................Passed

# 5. Manual paste test — underscore-bearing OpenAI key now blocks.
$ printf 'sk-AAAAA_AAAAAAAAAAAAAAAAAA\n' > deleteme_cr04.tmp && git add deleteme_cr04.tmp && bash scripts/no-secrets.sh
ERROR: Staged content contains what looks like an API key or bearer token.
exit=1

# 6. Manual paste test — tab-separated Bearer now blocks.
$ printf 'Bearer\tabcdefghijklmnopqrstuvwxyz0123ABCDEF\n' > deleteme_tabws.tmp && git add deleteme_tabws.tmp && bash scripts/no-secrets.sh
ERROR: Staged content contains what looks like an API key or bearer token.
exit=1

# 7. SECRET_PATTERNS[0] is now the Bearer pattern.
$ uv run python -c "from apps.api.backends.logging_filter import SECRET_PATTERNS; print(SECRET_PATTERNS[0][0].pattern)"
Bearer\s+[A-Za-z0-9_.\-]{20,}

# 8. scripts/no-secrets.sh sk- alphabet has _-.
$ grep "sk-\[A-Za-z0-9_-\]{20,}" scripts/no-secrets.sh
#   sk-[A-Za-z0-9_-]{20,}                   OpenAI-style keys (alphabet incl. _-)
   grep -E '(sk-ant-[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9_-]{20,}|Bearer[[:space:]]+[A-Za-z0-9_.-]{20,})' > /dev/null; then

# 9. scripts/no-secrets.sh Bearer uses POSIX whitespace class.
$ grep "Bearer\[\[:space:\]\]\+" scripts/no-secrets.sh
#   Bearer[[:space:]]+[A-Za-z0-9_.-]{20,}   Generic bearer tokens (any whitespace)
   grep -E '(sk-ant-[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9_-]{20,}|Bearer[[:space:]]+[A-Za-z0-9_.-]{20,})' > /dev/null; then

# 10. CI workflow has Regex parity check step + YAML parses.
$ grep -q "Regex parity check" .github/workflows/ci.yml && echo "PRESENT"
PRESENT
$ uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('YAML OK')"
YAML OK

# 11. Phase 2 non-live suite: 133 passed (was 131; +2 new).
$ uv run pytest -m 'not live' apps/api/backends -q
133 passed, 1 skipped, 3 deselected in 1.03s

# 12. Phase 1 D-18 import-graph guard stays green.
$ uv run pytest src/routing/tests/test_decide_smoke.py -x -q
7 passed
```

## Decisions Made

1. **Bearer pattern FIRST in SECRET_PATTERNS.** Canonical `Authorization: Bearer sk-…` headers consume the Bearer pattern (whose alphabet `[A-Za-z0-9_.-]{20,}` is wider than `sk-ant-` / `sk-`) as a single span before the more-specific provider rules would otherwise match the body. Replacement string is the locked `Bearer ***REDACTED***` (literal space + marker) that downstream scrubbers anchor on. This is the canonical "more-general carrier consumes its more-specific payload" pattern for regex-redaction stacks.
2. **Parity translation is one-way at the test boundary: bash `[[:space:]]+` → python `\s+`.** The reverse is also valid (the two character classes are equivalent), but standardising on python form simplifies the substring comparison in the parity test. If a future contributor switches the script to a literal space (or other form), the translation no longer maps and the test surfaces the drift with a clear `'Bearer …{20,}' NOT in [SECRET_PATTERNS]` failure.
3. **Existing `test_redaction_replaces_anthropic_keys` updated rather than left as-is.** The original assertion `"***REDACTED-ANTHROPIC***" in caplog.text` against an input `Bearer sk-ant-…` would FAIL after the reorder (Bearer now consumes the whole span). Dropping the `Bearer ` prefix from the input keeps the assertion semantically valid (sk-ant- branch alone) while the dedicated new `test_bearer_prefixed_sk_ant_redacts_as_bearer_unit` covers the Bearer-prefixed path explicitly. Option (b) from the plan (split into two tests) was chosen over option (a) (single test without Bearer prefix) because the latter would leave the Bearer-prefixed code path uncovered.
4. **CI parity step DUPLICATES the test from the broader suite.** A dedicated named step provides (a) a one-line failure signal in workflow logs when someone edits one regex set, and (b) explicit contract naming (SECURE-01 + SECURE-02) in the GitHub Actions UI. The broader `Phase 2 — apps/api/backends unit tests (no live)` step is preserved verbatim — the duplication is intentional.

## Deviations from Plan

None — plan executed exactly as written. No Rule 1/2/3 auto-fixes were needed during execution.

## TDD Gate Compliance

| Gate | Commit | Verification |
| ---- | ------ | ------------ |
| RED | `3c5f71c` — `test(02-07): add failing regressions for redaction regex parity + Bearer ordering` | Both new tests FAILED before implementation, demonstrating the bugs (CR-04 + CR-05). Existing 7 tests still PASSED. |
| GREEN | `e4383e5` — `fix(02-07): unify redaction regex sets + Bearer-first ordering (CR-04 + CR-05)` | All 9 tests PASS after implementation. Phase 2 backends suite: 133 passed (was 131; +2 new). Phase 1 D-18 guard: 7 passed. Pre-commit clean tree: exits 0. |
| REFACTOR | (not applied) | The implementation is minimal — no separate refactor commit needed. The docstring/comment updates landed atomically in the GREEN commit because the regex changes and their rationale are inseparable. |

## Success Criteria

- [x] VERIFICATION.md Truth 19 (CR-04) flips FAILED → VERIFIED: `scripts/no-secrets.sh` regex alphabet matches `SECRET_PATTERNS` exactly.
- [x] VERIFICATION.md Truth 20 (CR-05) flips FAILED → VERIFIED: `Bearer sk-ant-...` redacts to `Bearer ***REDACTED***` as a single unit; the `Bearer ` literal is no longer left dangling alongside an anthropic-branch marker.
- [x] A new pytest-based parity test prevents future regex drift between the two controls; a dedicated CI step makes the failure visible in workflow logs.
- [x] The pre-commit hook now blocks the two reproductions that previously slipped through: `sk-AAAAA_AAAAAAAAAAAAAAAAAA` (underscore-bearing OpenAI key) and `Bearer\t<token>` (tab-separated Bearer header).
- [x] No regression in the existing 7 logging_filter tests, the 131-passing phase-test baseline, the pre-commit clean-tree run, or the YAML workflow parse.
- [x] The `logging_filter.py:29-41` docstring claim ("the regex sets are intentionally synchronised") is now backed by a programmatic check (`test_logging_filter_and_no_secrets_regex_parity` + dedicated CI step) rather than developer convention.

## Commits

| Phase | Hash | Message |
| ----- | ---- | ------- |
| RED | `3c5f71c` | `test(02-07): add failing regressions for redaction regex parity + Bearer ordering` |
| GREEN | `e4383e5` | `fix(02-07): unify redaction regex sets + Bearer-first ordering (CR-04 + CR-05)` |
| DOCS | _(pending — this commit)_ | `docs(02-07): complete redaction pattern parity + Bearer ordering plan (CR-04 + CR-05)` |

## Self-Check

Verification of claims:
- `apps/api/backends/logging_filter.py` modified — FOUND, SECRET_PATTERNS[0][0].pattern == `Bearer\s+[A-Za-z0-9_.\-]{20,}` (Bearer first).
- `scripts/no-secrets.sh` modified — FOUND, line 14 contains `sk-[A-Za-z0-9_-]{20,}` and `Bearer[[:space:]]+`.
- `apps/api/backends/tests/test_logging_filter.py` modified — FOUND, 9 tests (was 7).
- `.github/workflows/ci.yml` modified — FOUND, `Regex parity check` step present.
- `.planning/phases/02-backend-adapters-chatchunk-contract/02-07-SUMMARY.md` created — FOUND.
- Commit `3c5f71c` (RED) — FOUND in `git log`.
- Commit `e4383e5` (GREEN) — FOUND in `git log`.

## Self-Check: PASSED
