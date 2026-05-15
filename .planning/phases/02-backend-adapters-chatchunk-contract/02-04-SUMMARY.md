---
phase: 02-backend-adapters-chatchunk-contract
plan: 04
subsystem: ops-precommit-and-ci
tags: [pre-commit, ci, github-actions, secure-02, oss-06, requirements-reconciliation, validation-signoff]
dependency_graph:
  requires:
    - "apps/api/backends/* (Wave 0 + Wave 1 adapters — exercised by the new `pytest -m 'not live' apps/api/backends` CI step)"
    - "uv.lock (already absent of `claude-code-sdk` per OSS-06; CI grep makes this a permanent invariant)"
    - ".github/workflows/ci.yml (Phase 1 minimal workflow extended additively)"
  provides:
    - ".pre-commit-config.yaml (two LOCAL hooks: no-secrets + no-deprecated-claude-code-sdk)"
    - "scripts/no-secrets.sh (SECURE-02 — D-09 locked regex)"
    - "scripts/no-deprecated-sdk.sh (OSS-06 — staged-content grep + uv.lock grep)"
    - ".github/workflows/ci.yml (extended CI per D-20)"
    - ".github/workflows/live-smoke.yml (NEW — manual + weekly cron, OpenRouter only)"
    - ".planning/REQUIREMENTS.md (BACKEND-01 D-02 reconciliation)"
    - ".planning/ROADMAP.md (Phase 2 SC #5 B1 placeholder annotation)"
    - ".planning/phases/02-backend-adapters-chatchunk-contract/02-VALIDATION.md (B4 fix — real task IDs + nyquist_compliant + sign-off)"
  affects:
    - "Every future push to main / every future PR — CI now runs pre-commit + OSS-06 smoke + dual pytest split on each event"
    - "Every future `git commit` — pre-commit hooks scan staged content before the commit lands locally"
    - "Phase 2 verifier `/gsd-verify-work` — SECURE-02 + OSS-06 now have concrete artifacts to point at; B1 + B4 plan-checker issues resolved"
tech_stack:
  added:
    - "pre-commit 4.6.0 framework (already in pyproject.toml [tool.uv.dev-dependencies] from Wave 0; now used)"
  patterns:
    - "Local-only pre-commit repos (no `repo: https://...` references — D-09 keeps the supply chain narrow)"
    - "Two-step `git diff --cached | grep '^\\+[^+]' | grep PATTERN` pipeline for staged-content scanning"
    - "Triad OSS-06 enforcement: (a) pre-commit hook on staged content, (b) CI import smoke `from claude_agent_sdk import ClaudeAgentOptions`, (c) CI lockfile grep `! grep -q '\"claude-code-sdk\"' uv.lock`"
    - "Additive CI YAML extension — every Phase 1 step preserved verbatim, new steps inserted between sync + pytest"
    - "Optional weekly cron live-smoke workflow gated by `secrets.OPENROUTER_API_KEY != ''` so forks no-op cleanly"
    - "Documentation reconciliation via `Edit` tool (single-line replacements preserve every other line)"
key_files:
  created:
    - ".pre-commit-config.yaml"
    - "scripts/no-secrets.sh"
    - "scripts/no-deprecated-sdk.sh"
    - ".github/workflows/live-smoke.yml"
    - ".planning/phases/02-backend-adapters-chatchunk-contract/02-04-SUMMARY.md"
  modified:
    - ".github/workflows/ci.yml"
    - ".planning/REQUIREMENTS.md"
    - ".planning/ROADMAP.md"
    - ".planning/phases/02-backend-adapters-chatchunk-contract/02-VALIDATION.md"
decisions:
  - "RESEARCH Pattern 11 line 1607's single-regex form for no-deprecated-sdk.sh (`^\\+[^+].*\\b(import claude_code_sdk|...)`) cannot match `+import claude_code_sdk` because `[^+]` consumes the `i` of `import` and `.*` cannot backtrack across it. Rule 1 fix: split into a two-grep pipeline (filter to ADDED lines, then pattern-match the body) mirroring the no-secrets.sh shape. Both hooks now behave correctly under deliberate paste tests."
  - "live-smoke.yml is OpenRouter-only on the weekly cron. Anthropic / computer-use are excluded from the cron because computer-use additionally requires Chromium + `COMPUTER_USE_OPT_IN` — operators wanting that smoke can dispatch the workflow manually with both secrets and the opt-in env var. Cost budget: ~$0.10 per OpenRouter run × ~4.3 runs/month = ~$0.43/month per repo with the secret set."
  - "BACKEND-06 wording verification was a planned NO-OP. Re-reading REQUIREMENTS.md line 27 confirmed the locked D-15 phrasing `per-iteration step cap (25 for Claude Code, 15 for computer-use)` was already present — no edit needed."
  - "VALIDATION.md `wave_0_complete: false` left as-is (B4 only required `nyquist_compliant: true`). The sign-off certifies the validation SCHEMA is finalized; runtime wave-completion state lives in STATE.md / SUMMARY.md, not in the validation frontmatter."
  - "VALIDATION.md Per-Task Verification Map column 'Plan' was off-by-one in the original draft (`01 (scaffold)` actually referred to plan 00). The B4 reconciliation also fixed the Plan column to match the canonical plan IDs: `00 (scaffold)`, `01 (OpenRouter)`, `02 (Claude Code)`, `03 (computer-use)`, `04 (pre-commit + CI)`."
metrics:
  duration_min: 22
  tasks_completed: 5
  files_created: 5
  files_modified: 4
  files_total: 9
  d18_guard_state: green
  apps_backends_test_state: "129 passed, 1 skipped, 3 deselected"
  whole_repo_test_state: "all non-live tests pass (exit 0)"
  completed_at: "2026-05-15"
---

# Phase 02 Plan 04: Pre-commit Hooks + CI Extension + Docs Reconciliation Summary

## One-liner

Wave 2 closes Phase 2 by landing SECURE-02 (`.pre-commit-config.yaml` + two local hooks blocking `sk-`/`sk-ant-`/`Bearer …` and deprecated `claude_code_sdk`), OSS-06 triad enforcement in CI (`pre-commit run --all-files` + `claude_agent_sdk` import smoke + `uv.lock` absence grep), an optional weekly OpenRouter live-smoke workflow, and three docs reconciliations (REQUIREMENTS BACKEND-01 D-02 wording, ROADMAP SC #5 B1 annotation, VALIDATION B4 task-ID + sign-off).

## Performance

- **Duration:** 22 min
- **Started:** 2026-05-15T16:37:17Z
- **Completed:** 2026-05-15
- **Tasks:** 5
- **Files created:** 5
- **Files modified:** 4

## Accomplishments

- **SECURE-02 landed end-to-end.** Pre-commit framework installed (`uv run pre-commit run --all-files` exits 0 on the existing tree); two LOCAL hooks registered. Deliberate paste test: `echo "sk-ant-AAAAAAAAAAAAAAAAAAAA" >> deleteme.tmp && git add deleteme.tmp && uv run pre-commit run no-secrets` exits 1 with the canonical error message "ERROR: Staged content contains what looks like an API key or bearer token."
- **OSS-06 triad in place.** Triple-redundant enforcement: (a) pre-commit hook on staged `claude_code_sdk` imports + `uv.lock` entries, (b) CI step `uv run python -c "from claude_agent_sdk import ClaudeAgentOptions"`, (c) CI step `! grep -q '"claude-code-sdk"' uv.lock`. Deliberate test: `echo "import claude_code_sdk" >> deleteme_sdk.tmp && git add deleteme_sdk.tmp && uv run pre-commit run no-deprecated-claude-code-sdk` exits 1.
- **CI workflow extended additively.** Every Phase 1 step preserved verbatim (Checkout / Install uv / Install Python / Sync deps / Pre-fetch NLTK / Routing canary eval). Six new steps inserted: keyring extra sync, pre-commit run, OSS-06 import smoke, OSS-06 absence assertions, split Phase 1 `pytest src/` + Phase 2 `pytest -m 'not live' apps/api/backends`. Both YAML files parse cleanly via `yaml.safe_load`.
- **live-smoke.yml created.** Manual `workflow_dispatch` + weekly Monday 06:00 UTC cron; gated by `secrets.OPENROUTER_API_KEY != ''` so forks no-op; `continue-on-error: true` so provider hiccups don't cascade; `pytest -m live apps/api/backends/openrouter -x --maxfail=1` keeps a single budget overshoot from chain-reacting.
- **REQUIREMENTS.md BACKEND-01 reconciled.** Discriminated union grew from 6 variants to 7 to match CONTEXT D-02 — `ToolResult` lands between `ToolCall` and `FileDiff`. Phase 2 Plans 00-03 were already built against the 7-variant shape; this is a docs reconciliation, not a behavior change.
- **REQUIREMENTS.md BACKEND-06 verified as already correct.** Planned NO-OP — re-read confirmed the locked D-15 phrasing was already present.
- **ROADMAP.md Phase 2 SC #5 B1 annotation applied.** In-line parenthetical clarifies that the Phase 2 CLI uses `tempfile.mkdtemp(prefix='pomu-cc-')` as a placeholder; the canonical `~/.prompt-optimizer/workspaces/<thread_id>/` path is preserved verbatim. Line count unchanged at 129.
- **VALIDATION.md B4 sign-off complete.** All 13 placeholder `02-NN-XX` task IDs replaced with real `02-NN-TM` IDs derived from the committed PLAN.md files. The 'Plan' column off-by-one corrected (`01 (scaffold)` → `00 (scaffold)`, etc.). Frontmatter `nyquist_compliant: false` → `true`. All six Validation Sign-Off boxes ticked. `Approval: pending` → `approved (B4 fix; task IDs reconciled with committed plans 02-00..02-04)`.
- **Phase 1 D-18 import-graph guard remains green.** `uv run pytest src/routing/tests/test_decide_smoke.py -x -q` exits 0.
- **`apps/api/backends/` test state preserved.** `uv run pytest -m 'not live' apps/api/backends` reports 129 passed, 1 skipped, 3 deselected in 1.36s. No code touched in this plan; only repo-tooling + CI + docs.

## Task Commits

Each task was committed atomically:

1. **Task 1: Author pre-commit config + two shell scripts (no-secrets, no-deprecated-sdk)** — `4ca6268` (chore)
2. **Task 2: Extend `.github/workflows/ci.yml` + add `.github/workflows/live-smoke.yml`** — `20c7042` (ci)
3. **Task 3: Reconcile `.planning/REQUIREMENTS.md` BACKEND-01 wording with D-02** — `c191d4e` (docs)
4. **Task 4: Annotate `.planning/ROADMAP.md` Phase 2 SC #5 with `pomu-cc-` placeholder note (B1 fix)** — `64a28f1` (docs)
5. **Task 5: Finalize `.planning/phases/02-backend-adapters-chatchunk-contract/02-VALIDATION.md` (B4 fix)** — `edd233c` (docs)

## Files Created (5)

### Source / Tooling (4)

| Path | Purpose |
| ---- | ------- |
| `.pre-commit-config.yaml` | Two LOCAL hooks per D-09 — no third-party repo references. Both hooks set `pass_filenames: false`, `language: script`, `stages: [pre-commit]`. |
| `scripts/no-secrets.sh` | SECURE-02 staged-content scanner. The locked D-09 regex matches `sk-ant-[A-Za-z0-9_-]{8,}`, `sk-[A-Za-z0-9]{20,}`, and `Bearer [A-Za-z0-9_.-]{20,}`. Two-step grep pipeline (filter to ADDED lines, then pattern-match the body) so the `[^+]` diff-header filter doesn't consume the first letter of the keyword. `set -euo pipefail` for safety. |
| `scripts/no-deprecated-sdk.sh` | OSS-06 enforcer. Check 1: scans staged content for `import claude_code_sdk`, `from claude_code_sdk`, or `"claude-code-sdk"`. Check 2: scans `uv.lock` for `"claude-code-sdk"` (catches contributors who run `uv add claude-code-sdk` even if they don't stage a Python file). |
| `.github/workflows/live-smoke.yml` | Optional opt-in CI workflow. `on: { workflow_dispatch:, schedule: [ - cron: "0 6 * * 1" ] }`. Job gate `if: ${{ secrets.OPENROUTER_API_KEY != '' }}`. Single step: `pytest -m live apps/api/backends/openrouter -x --maxfail=1` with `continue-on-error: true`. |

### Docs (1)

| Path | Purpose |
| ---- | ------- |
| `.planning/phases/02-backend-adapters-chatchunk-contract/02-04-SUMMARY.md` | This file. |

## Files Modified (4)

| Path | Diff Summary |
| ---- | ------------ |
| `.github/workflows/ci.yml` | Additive — six new steps inserted between Phase 1's `Sync dependencies (locked)` and the existing `Routing canary eval` step. The single `Run full pytest suite` step replaced with `Phase 1 — src/ tests` + `Phase 2 — apps/api/backends unit tests (no live)`. |
| `.planning/REQUIREMENTS.md` | Single-line BACKEND-01 wording update: 6-variant union → 7-variant union with `ToolResult` between `ToolCall` and `FileDiff`. BACKEND-06 line untouched (planned NO-OP verification). |
| `.planning/ROADMAP.md` | In-line parenthetical annotation on Phase 2 SC #5: ``` (Phase 2 CLI uses `tempfile.mkdtemp(prefix='pomu-cc-')` as a placeholder until thread IDs are introduced in Phase 3) ```. Line count unchanged. |
| `.planning/phases/02-backend-adapters-chatchunk-contract/02-VALIDATION.md` | Four edits: (1) all 13 placeholder `02-NN-XX` task IDs replaced with real `02-NN-TM` IDs; the Plan column off-by-one corrected; status column updated to `✅ / ✅ green`. (2) Explanatory note rewritten — dropped "placeholders pending" language. (3) Frontmatter `nyquist_compliant: false` → `true`. (4) All six Validation Sign-Off boxes ticked; `Approval: pending` → `approved (B4 fix; task IDs reconciled with committed plans 02-00..02-04)`. |

## Deliberate Test Outcomes

Per the plan's Task 1 acceptance criteria + the `<output>` block, two deliberate paste tests must trigger the hooks. Both confirmed:

### Secret paste test

```bash
$ echo "sk-ant-AAAAAAAAAAAAAAAAAAAA" >> deleteme.tmp
$ git add deleteme.tmp
$ uv run pre-commit run no-secrets
Block secrets in staged content..........................................Failed
- hook id: no-secrets
- exit code: 1

ERROR: Staged content contains what looks like an API key or bearer token.
If this is a false positive, remove the literal and use an env-var reference.

$ git restore --staged deleteme.tmp && rm -f deleteme.tmp
```

### Deprecated SDK import test

```bash
$ echo "import claude_code_sdk" >> deleteme_sdk.tmp
$ git add deleteme_sdk.tmp
$ uv run pre-commit run no-deprecated-claude-code-sdk
Block deprecated claude-code-sdk.........................................Failed
- hook id: no-deprecated-claude-code-sdk
- exit code: 1

ERROR: Use 'claude_agent_sdk' (NOT the deprecated 'claude-code-sdk').
See OSS-06 in .planning/REQUIREMENTS.md.

$ git restore --staged deleteme_sdk.tmp && rm -f deleteme_sdk.tmp
```

### Clean baseline test

```bash
$ uv run pre-commit run --all-files
Block secrets in staged content..........................................Passed
Block deprecated claude-code-sdk.........................................Passed
```

No false positives across the entire repo (including planning docs that reference `sk-ant-...` and `claude_code_sdk` in regex patterns — those live in shell scripts and docs that aren't being newly ADDED via `git diff --cached`).

## CI Workflow Verification

```bash
$ uv run python -c "import yaml; \
    yaml.safe_load(open('.github/workflows/ci.yml')); \
    yaml.safe_load(open('.github/workflows/live-smoke.yml')); \
    print('YAML OK')"
YAML OK
```

D-20 step list in `ci.yml`:

| Step | Purpose | Locked Phrase |
| ---- | ------- | ------------- |
| Checkout (with LFS for data_processed/*.csv) | Phase 1 preserved | unchanged |
| Install uv | Phase 1 preserved | unchanged |
| Install Python 3.11 | Phase 1 preserved | unchanged |
| Sync dependencies (locked) | Phase 1 preserved | unchanged |
| Sync with keyring extra (SECURE-04) | NEW | `uv sync --locked --extra keyring` |
| Run pre-commit hooks (SECURE-02 + OSS-06) | NEW | `uv run pre-commit run --all-files` |
| OSS-06 — claude_agent_sdk import smoke | NEW | `uv run python -c "from claude_agent_sdk import ClaudeAgentOptions"` |
| OSS-06 — ensure deprecated claude-code-sdk absent | NEW | `! uv run python -c "import claude_code_sdk" 2>/dev/null` + `! grep -q '"claude-code-sdk"' uv.lock` |
| Pre-fetch NLTK data | Phase 1 preserved | unchanged |
| Phase 1 — src/ tests (D-18 import-graph guard stays green) | NEW (split from old single step) | `uv run pytest -x -q src/` |
| Phase 2 — apps/api/backends unit tests (no live) | NEW (split from old single step) | `uv run pytest -x -q -m 'not live' apps/api/backends` |
| Routing canary eval (advisory) | Phase 1 preserved | unchanged; `continue-on-error: true` |

## OSS-06 Triad Coverage Verification

```bash
# 1. uv.lock absence (locked invariant since Wave 0).
$ if grep -q '"claude-code-sdk"' uv.lock; then echo BAD; else echo OK; fi
OK

# 2. Import smoke (the canonical Anthropic agent SDK).
$ uv run python -c "from claude_agent_sdk import ClaudeAgentOptions; print('OK')"
OK

# 3. Pre-commit hook lockfile-grep is encoded in scripts/no-deprecated-sdk.sh:
$ grep -A1 'Check 2' scripts/no-deprecated-sdk.sh
# Check 2: lockfile — D-09 says: catch contributors who add the dep accidentally.
if [ -f uv.lock ] && grep -q '"claude-code-sdk"' uv.lock; then
    echo "ERROR: 'claude-code-sdk' found in uv.lock. Remove the dep and re-lock."
    exit 1
fi

# 4. CI absence assertion mirrors the same grep in the workflow:
$ grep -A2 "OSS-06 — ensure deprecated" .github/workflows/ci.yml
      - name: OSS-06 — ensure deprecated claude-code-sdk absent
        run: |
          ! uv run python -c "import claude_code_sdk" 2>/dev/null
          ! grep -q '"claude-code-sdk"' uv.lock
```

Four redundant guardrails: `pyproject.toml` pin (Wave 0), CI uv.lock grep, CI import smoke, pre-commit hook. Any contributor who introduces `claude-code-sdk` must defeat all four to land it.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] RESEARCH Pattern 11's single-regex form for `no-deprecated-sdk.sh` cannot match `+import claude_code_sdk`**

- **Found during:** Task 1, deliberate paste test of `import claude_code_sdk` after writing the script verbatim per RESEARCH Pattern 11 lines 1601-1618.
- **Issue:** RESEARCH line 1607 specifies a SINGLE regex combining the diff-header filter and the keyword match:
  ```bash
  grep -E '^\+[^+].*\b(import claude_code_sdk|from claude_code_sdk|"claude-code-sdk")'
  ```
  This form cannot match `+import claude_code_sdk` because:
  - `^\+` matches the diff `+` prefix.
  - `[^+]` requires the NEXT character to be non-`+` — fine, it matches `i`.
  - But `[^+]` has now CONSUMED the `i` of `import`.
  - `.*\b` then tries to find a word boundary followed by `(import claude_code_sdk|...)` later in the line.
  - The remaining line is `mport claude_code_sdk` — there is no second occurrence of `import` to match.
  - Result: regex returns no match; the hook silently passes; deprecated imports slip through.
- **Fix:** Mirror the working two-step pipeline from `no-secrets.sh`:
  ```bash
  if git diff --cached --diff-filter=AM | \
     grep -E '^\+[^+]' | \
     grep -E '(import claude_code_sdk|from claude_code_sdk|"claude-code-sdk")' > /dev/null; then
      ...
      exit 1
  fi
  ```
  The first grep filters to ADDED lines (excluding `+++` headers); the second grep scans the line body without re-consuming the diff prefix. Both deliberate paste tests now correctly block.
- **Files modified:** `scripts/no-deprecated-sdk.sh`.
- **Verification:** `bash scripts/no-deprecated-sdk.sh` against a staged `import claude_code_sdk` line returns exit 1 with the canonical error message; `uv run pre-commit run no-deprecated-claude-code-sdk` reports `Failed` in the same scenario. Clean repo state still passes (`uv run pre-commit run --all-files` exits 0).
- **Committed in:** `4ca6268` (Task 1 commit; the fix was made before the commit so the wrong version never landed).
- **Why this is a Rule 1 fix and not a Rule 4 architectural change:** The behavior contract (block any staged content that re-introduces `claude_code_sdk`) is unchanged. The pipeline shape was already established by the working `no-secrets.sh` — applying it consistently is a one-line implementation correction. No new API, no new dependency, no scope creep. The same two-step pattern is also used in pre-commit ecosystem examples (e.g. `git secrets`, `detect-secrets`'s own legacy bash hooks).

### Other deviations: NONE

All other plan steps executed exactly as written. The four documentation reconciliations (Tasks 3-5) are all single-line edits that preserve every other line in their respective files. The CI workflow extension (Task 2) is purely additive; every Phase 1 step is preserved verbatim.

**Total deviations:** 1 Rule-1 bug fix in `no-deprecated-sdk.sh`. No new dependencies, no scope creep, no architectural surface change.

## Authentication Gates

None. All work in this plan ran offline. The optional `live-smoke.yml` workflow is opt-in (requires `OPENROUTER_API_KEY` repository secret) and runs in CI, not in this executor's environment.

## Verification Commands Re-run at Completion

```bash
# 1. Pre-commit clean baseline.
$ uv run pre-commit run --all-files
Block secrets in staged content..........................................Passed
Block deprecated claude-code-sdk.........................................Passed

# 2. OSS-06 import smoke.
$ uv run python -c "from claude_agent_sdk import ClaudeAgentOptions; print('OK')"
OK

# 3. OSS-06 lockfile absence.
$ if grep -q '"claude-code-sdk"' uv.lock; then echo BAD; else echo OK; fi
OK

# 4. YAML parse.
$ uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); yaml.safe_load(open('.github/workflows/live-smoke.yml')); print('YAML OK')"
YAML OK

# 5. Phase 1 D-18 import-graph guard.
$ uv run pytest src/routing/tests/test_decide_smoke.py -x -q
.......                                                                  [100%]

# 6. apps/api/backends test pass.
$ uv run pytest -m 'not live' apps/api/backends
129 passed, 1 skipped, 3 deselected in 1.36s

# 7. Whole-repo non-live suite — completed in the background with exit 0.
$ uv run pytest -m 'not live' -q
.............................s.......................................... [ 31%]
........................................................................ [ 62%]
................................s....................................... [ 93%]
...............                                                          [100%]
# Exit code 0; whole-repo state matches the Plan 02-03 baseline (no regressions).

# 8. Test count.
$ uv run pytest -m 'not live' --co
231/234 tests collected (3 deselected) in 1.86s
```

## Phase 2 Closeout

With Plan 02-04 landing, **all four waves of Phase 2 are complete**:

- **Wave 0 (Plan 02-00):** Shared module surface + D-19 contract suite stub + Pydantic ChatChunk union.
- **Wave 1 (Plans 02-01 / 02 / 03):** Three adapters (OpenRouter / Claude Code / computer-use) all passing the D-19 contract suite.
- **Wave 2 (Plan 02-04 — this plan):** SECURE-02 + OSS-06 enforced via pre-commit + CI; REQUIREMENTS / ROADMAP / VALIDATION reconciled.

**Phase 2 Success Criteria mapping:**

- **SC #1** (per-adapter CLI streams ChatChunk JSON lines) — satisfied by Plans 01/02/03 acceptance criteria.
- **SC #2** (cost cap + step cap + 2 s cancellation) — satisfied by D-19 contract suite (Wave 0 + Wave 1); 17/18 invariants pass, 1 intentional N/A skip for OpenRouter `step_cap_aborts`.
- **SC #3** (logger redaction + BYOK key store) — satisfied by Wave 0 unit tests (`test_logging_filter.py` 7 tests + `test_keystore.py` 8 tests).
- **SC #4** (OSS-06 smoke + watchdog + OpenRouter headers) — satisfied by this plan's CI extension + Plan 01's `test_adapter.py` (`HTTP-Referer` + `X-Title` recording) + Plan 02's `test_watchdog_env.py` (2 tests).
- **SC #5** (COMPUTER_USE_OPT_IN + Claude Code workspace + pre-commit hook) — satisfied by Plan 03's `test_optin.py` (4 tests) + Plan 02's `test_workspace.py` (3 tests) + this plan's `.pre-commit-config.yaml` + deliberate paste test.

**Phase 2 Requirements mapping (15 total):**

- BACKEND-01..09 ✓ (Plans 02-00 / 02-01 / 02-02 / 02-03; reconciled wording in this plan)
- SECURE-01 ✓ (Wave 0)
- SECURE-02 ✓ (this plan)
- SECURE-04 ✓ (Wave 0)
- SECURE-05 ✓ (Wave 1 — Plan 03)
- OSS-06 ✓ (this plan)

**Total: 15 / 15 satisfied.**

## Next Plan Readiness

Phase 2 is complete. Phase 3 (FastAPI service layer, API-01..08, STORE-01..06, OSS-05) can now import from `apps.api.backends.{openrouter,claude_code,computer_use}` and assume the CI gates established here continue to enforce the contracts on every PR.

## Self-Check: PASSED

All files claimed in the SUMMARY exist; all five task commits exist in the git log.

```
$ for f in .pre-commit-config.yaml \
          scripts/no-secrets.sh \
          scripts/no-deprecated-sdk.sh \
          .github/workflows/live-smoke.yml \
          .planning/phases/02-backend-adapters-chatchunk-contract/02-04-SUMMARY.md; do
    [ -f "$f" ] && echo "FOUND: $f" || echo "MISSING: $f"
done

$ for f in .github/workflows/ci.yml \
          .planning/REQUIREMENTS.md \
          .planning/ROADMAP.md \
          .planning/phases/02-backend-adapters-chatchunk-contract/02-VALIDATION.md; do
    [ -f "$f" ] && echo "FOUND: $f" || echo "MISSING: $f"
done

$ git log --oneline --all | grep -E "4ca6268|20c7042|c191d4e|64a28f1|edd233c"
edd233c docs(02-04): finalize 02-VALIDATION.md per B4 fix
64a28f1 docs(02-04): annotate ROADMAP Phase 2 SC #5 with pomu-cc- placeholder note (B1 fix)
c191d4e docs(02-04): reconcile REQUIREMENTS BACKEND-01 wording with D-02 (add ToolResult)
20c7042 ci(02-04): extend ci.yml + add live-smoke.yml (D-20)
4ca6268 chore(02-04): add pre-commit hooks for SECURE-02 + OSS-06
```

All 4 created + 4 modified files present; all 5 task commits present.

---

*Phase: 02-backend-adapters-chatchunk-contract*
*Plan: 04*
*Completed: 2026-05-15*
