---
phase: 1
slug: router-brain-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-11
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> See `01-RESEARCH.md` § "Validation Architecture" for the full per-requirement test map.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (installed via `uv add --dev pytest`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (created in Wave 0) |
| **Quick run command** | `uv run pytest src/routing/tests/ -x -q` |
| **Full suite command** | `uv run pytest -x -q` |
| **Estimated runtime** | ~30 seconds (full suite, target) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest src/routing/tests/ -x -q` (the just-touched module's tests)
- **After every plan wave:** Run `uv run pytest -x -q` (full suite)
- **Before `/gsd-verify-work`:** Full suite must be green AND `python -m src.evaluation.evaluate_routing` must run cleanly
- **Max feedback latency:** 30 seconds (full suite)

---

## Per-Task Verification Map

> The complete map lives in `01-RESEARCH.md` § "Validation Architecture" → "Test File Map" and "Per-Requirement Validation Coverage". The planner derives task-level `<automated>` blocks from that source.

Skeleton — populated when PLAN.md task IDs are emitted:

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-XX | 01-toolchain-bootstrap | 0 | OSS-01 | T-01-01 | gitignored secret-bearing files never committed | infra | `test -f pyproject.toml && test -f uv.lock && test -f .gitignore` | ❌ W0 | ⬜ pending |
| 01-02-XX | 02-features-extension | 1 | ROUTER-01 | — | N/A | unit | `uv run pytest src/feature_extraction/tests/test_agentic_features.py -x -q` | ❌ W0 | ⬜ pending |
| 01-03-XX | 03-agentic-dataset | 1 | ROUTER-01 | — | N/A | data | `uv run python -m src.task_classifier.build_agentic_dataset --check` | ❌ W0 | ⬜ pending |
| 01-04-XX | 04-agentic-classifier | 2 | ROUTER-01 | — | N/A | unit | `uv run pytest src/task_classifier/tests/test_agentic_intent.py -x -q` | ❌ W0 | ⬜ pending |
| 01-05-XX | 05-calibration | 2 | ROUTER-02, ROUTER-03 | — | N/A | unit | `uv run pytest src/calibration/tests/ -x -q` | ❌ W0 | ⬜ pending |
| 01-06-XX | 06-routing-package | 3 | ROUTER-05, ROUTER-06 | T-01-02, T-01-04 | secrets never appear in `rationale`; framework-free import graph | unit | `uv run pytest src/routing/tests/ -x -q` | ❌ W0 | ⬜ pending |
| 01-07-XX | 07-canary-eval | 3 | ROUTER-04 | — | N/A | integration | `uv run python -m src.evaluation.evaluate_routing` | ❌ W0 | ⬜ pending |
| 01-08-XX | 08-demo-and-regression | 4 | ROUTER-07 | T-01-03 | benchmark eval shows no regression | integration | `uv run pytest src/demo/tests/ src/evaluation/tests/ -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

> Source of truth for the per-requirement coverage and exact commands is `01-RESEARCH.md` § "Validation Architecture". Planner MUST cross-reference that section when emitting `<automated>` blocks per task.

---

## Wave 0 Requirements

- [ ] `pyproject.toml` — project metadata, dep pins (sklearn ≥1.7, pandas, scipy, joblib, sentence-transformers, nltk), dev deps (pytest, pytest-cov), `[tool.pytest.ini_options]` config
- [ ] `uv.lock` — committed lockfile from `uv sync`
- [ ] `.gitignore` — excludes `.env`, `*.db`, `*.db-journal`, `*.db-wal`, `__pycache__/`, `.venv/`, `chat.db`
- [ ] `src/routing/tests/conftest.py` — shared fixtures (sample prompts, fake calibrated artifacts)
- [ ] `src/routing/tests/__init__.py` — make tests directory importable
- [ ] `src/routing/tests/test_decide_smoke.py` — smoke stubs for ROUTER-05 / ROUTER-06 / Success Criterion #1
- [ ] `src/routing/tests/test_uncertainty_fallback.py` — stub for Success Criterion #4
- [ ] `src/feature_extraction/tests/test_agentic_features.py` — stub for ROUTER-01 (5 new agentic features)
- [ ] `src/task_classifier/tests/test_agentic_intent.py` — stub for ROUTER-01 classifier
- [ ] `src/calibration/tests/test_calibration.py` — stub for ROUTER-02 / ROUTER-03 (FrozenEstimator pattern)
- [ ] `src/evaluation/tests/test_evaluate_routing.py` — stub for ROUTER-04 / Success Criterion #3
- [ ] `src/demo/tests/test_artifact_compat.py` — stub for ROUTER-07 (regression guard against `load_joblib_artifacts()` shape)
- [ ] `.github/workflows/ci.yml` — GitHub Actions workflow that runs `uv sync` + `uv run pytest -x -q` + `uv run python -m src.evaluation.evaluate_routing` on every PR

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Hand-labeled canary CSV quality (30–50 prompts, balanced across backends, includes ambiguous + OOD examples) | ROUTER-04 | Quality of human-curated labels can't be auto-checked; only the load + run can | Open `evaluation/routing_decision_eval.csv`, spot-check 5 random rows per backend, confirm `expected_backend` ∈ {openrouter, claude_code_sdk, computer_use, fallback} |
| Agentic-intent training data spot-audit (5–15% expected drop) | ROUTER-01 | LLM-generated/heuristic-labeled rows need a human to confirm they actually describe agentic vs. conversational tasks | Sample 30 rows from `data_processed/agentic_intent_dataset.csv`, manually re-label, compare; flag drift > 15% |
| Calibration reliability-diagram visual sanity check | ROUTER-02, ROUTER-03 | ECE numbers can hide pathological per-bin behavior | Open `evaluation/calibration_plots/*.png`, confirm post-calibration curve is closer to diagonal than pre-calibration |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
