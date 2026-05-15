---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Completed 02-07-PLAN.md (CR-04 + CR-05 gap closure — redaction regex parity + Bearer-first ordering)
last_updated: "2026-05-15T19:57:57.536Z"
last_activity: 2026-05-15
progress:
  total_phases: 6
  completed_phases: 2
  total_plans: 16
  completed_plans: 16
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-11)

**Core value:** Every prompt routes to the LLM or agent best suited to deliver a high-quality answer, with no manual model selection from the user.
**Current focus:** Phase 02 — backend-adapters-chatchunk-contract

## Current Position

Phase: 02 (backend-adapters-chatchunk-contract) — EXECUTING
Plan: 4 of 8
Status: Ready to execute
Last activity: 2026-05-15

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**

- Total plans completed: 11
- Average duration: ~44 min
- Total execution time: ~132 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 8 | - | - |

**Recent Trend:**

- Last 5 plans: 01-01 (31 min, 23 files created, OSS-01 + SECURE-03 delivered), 01-02 (90 min, 2 created + 4 modified, ROUTER-01 prep — 5 agentic features + text_inputs.py), 01-03 (~11 min on-CPU, 7 files created + 1 modified, ROUTER-01 prep — agentic_intent_training.csv assembled)
- Trend: 01-03 was fast because two of three tasks were commit-only (prior gsd-executor authored the seeds + synthesized CSVs offline before pausing at a 3-gate checkpoint that the developer resolved between sessions); the real implementation work (negatives miner + builder script + test slice) compressed into Task 3

**Per-plan metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 01 P01 | 31 min | 4 tasks | 23 files |
| Phase 01 P02 | 90 min | 3 tasks | 6 files |
| Phase 01 P03 | 11 min | 3 tasks | 8 files |

*Updated after each plan completion*
| Phase 01 P04 | 37m | 2 tasks | 4 files |
| Phase 01 P05 | 98m | 7 tasks | 9 files |
| Phase 01 P06 | 51m | 3 tasks | 10 files |
| Phase 01 P07 | 15m | 4 tasks | 12 files |
| Phase 01 P08 | 10m | 4 tasks | 5 files |
| Phase 02 P00 | 13 | 4 tasks | 17 files |
| Phase 02 P01 | 26 | 3 tasks | 11 files |
| Phase 02 P02 | 29 | 3 tasks | 14 files |
| Phase 02 P03 | 15 | 3 tasks | 13 files |
| Phase 02 P04 | 22 | 5 tasks | 9 files |
| Phase 02 P05 | 5 | 1 tasks | 3 files |
| Phase 02 P06 | 5 | 1 tasks | 2 files |
| Phase 02 P07 | 3 | 1 tasks | 5 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Roadmap: 6-phase shape (Router Brain → Backend Adapters → FastAPI+Storage → Minimal UI → Feature-Complete UI → OSS Hardening). Standard granularity. Persistence merged into the FastAPI phase because both serve the HTTP turn lifecycle.
- Roadmap: Security hygiene (`.gitignore`, key redaction, computer-use opt-in, pre-commit secret-grep, claude-agent-sdk pin) is enforced from the earliest phase that needs it, not deferred to Phase 6.
- Roadmap: `OSS-01` (pyproject.toml + uv.lock) lives in Phase 1 because `apps/api/` cannot import `src.routing` cleanly without it.
- Phase 1 Plan 01: scikit-learn resolved to **1.8.0** (latest in `>=1.7,<2.0`). `cv='prefit'` is **removed** in 1.8, not just deprecated — Plan 05's `FrozenEstimator` calibration approach is now mandatory, not optional. Pin range stays `>=1.7,<2.0`.
- Phase 1 Plan 01: pytest `--import-mode=importlib` set in `pyproject.toml` to handle duplicate bare `tests` package names across `src/<pkg>/tests/`. Every future plan that adds tests must keep this mode (and place new `conftest.py` files inside the owning package's tests dir, not at repo root).
- Phase 1 Plan 01: RED-stub contract finalized — named placeholder test functions calling `pytest.skip()` in their body, NOT module-level `pytest.skip(allow_module_level=True)`. This keeps the placeholder names visible to `pytest --collect-only` while still reporting as skipped in normal runs.
- Phase 1 Plan 02: imperative-verb set for `_agentic_features` is **locked to 26 verbs** (build, make, create, write, edit, refactor, fix, implement, add, remove, delete, update, rewrite, open, browse, click, navigate, visit, fill, submit, scrape, fetch, download, install, run). "explain" is deliberately EXCLUDED so the canary's explain-vs-build edge case (CONTEXT D-15) resolves correctly. Action-keyword set is locked to 7 verbs (build, open, scrape, fill, click, edit, refactor).
- Phase 1 Plan 02: `_agentic_features` truncates input to 50,000 chars before any regex call. ReDoS mitigation against threat T-01-FE-1; bounds NLTK sentence-tokenizer cost too.
- Phase 1 Plan 02: tier-router family (`src/model_router_tier/train_tier_router.py`, `src/model_router_tier/router_tier_system.py`) was NOT migrated to `text_inputs.py` in this plan — explicitly out of scope. The two tier-router files still define their own `build_text_input`. Plan 06's `decide.py` is the third migration site; tier-router cleanup is deferred to a later plan / dedicated cleanup phase.
- Phase 1 Plan 02: NLTK lazy download (`_ensure_nltk_sentence_tokenizer`) collides with Claude Code's network/filesystem sandbox. Local test runs require either a one-time `dangerouslyDisableSandbox: true` to populate `~/nltk_data/` or pre-fetching NLTK data outside the sandbox. CI workflow already pre-fetches; downstream plans inherit this constraint.
- [Phase 01]: Plan 03 Rule 4 deviation: negatives mined from data_processed/classifier_training.csv instead of flat_records.csv (upstream JSON tree absent; classifier_training.csv shares dataset + origin_query columns so the RESEARCH §Pattern 3 Step 4 filter applies verbatim).
- [Phase 01]: Plan 03 LLM expansion performed by Claude Opus 4.7 via Claude Code on 2026-05-13 (one-time offline per RESEARCH A3); 477 paraphrases embedded verbatim in scripts/expand_agentic_seeds.py for deterministic reproducibility. src/routing/ remains HTTP-library-free.
- [Phase ?]: Phase 1 Plan 04: agentic-intent classifier calibrated with method=sigmoid via FrozenEstimator+CalibratedClassifierCV; held-out accuracy=0.9505, macro-F1=0.9505, ECE=0.0364. method=isotonic switch is NOT needed (ECE well below 0.10 threshold).
- [Phase ?]: Phase 1 Plan 05: calibrated task_type_classifier (11 classes incl unknown OOD) and model_router (16 classes) via FrozenEstimator + CalibratedClassifierCV(method=sigmoid); models/uncalibrated/ backup directory established (Pitfall 6); evaluation/baselines.json snapshot captured for Plan 08 regression guard (ROUTER-07).
- [Phase ?]: Phase 1 Plan 05: 50 synthetic OOD prompts injected as unknown class (LLMRouterBench has 0 organic OOD rows). Final unknown count: 50 of 27253 rows (0.18%), well within Pitfall 2 bounds.
- [Phase ?]: Phase 1 Plan 05: training-set ECE mildly regressed on both heads (task_type 0.116 -> 0.142; model_router 0.063 -> 0.074). Plan 07 should compute canary-set ECE; if > 0.10 there, switch to method='isotonic' (Open Question 1 escape hatch).
- [Phase 01]: Phase 1 Plan 06: routing-brain D-01 cascade ordering deviates from literal `if/elif` order — browse-keyword fires BEFORE coding-task because the calibrated task classifier sometimes labels short browse prompts (e.g., "open URL and click X") as `coding`. CONTEXT D-15 "Informational-URL" explicitly says URL+action_verb -> computer-use; the reorder honors that intent. All other cascade semantics preserved.
- [Phase 01]: Phase 1 Plan 06: task_type tau gate moved to AFTER the cascade (Stage 3b instead of Stage 1 exit). High-precision keyword/coding paths (D-01 cascade branches 1+2) bypass the task tau because they require only the agentic-intent signal; gating Stage 1 first would force fallback on clear "build me X" / "open URL" prompts because the calibrated task classifier is under-confident on short inputs (Plan 05 ECE 0.142). OpenRouter branch (Stage 3b) still gates on task_type tau because the model_router prediction depends on a well-defined task_type.
- [Phase 01]: Phase 1 Plan 06: empty/whitespace prompt short-circuits to fallback BEFORE any classifier runs (V5 input validation). The calibrated heads would otherwise produce a "confident" prediction on "" by sheer prior.
- [Phase 01]: Phase 1 Plan 06: fallback rationale suffix is the 25-character locked string "low confidence — fallback" with U+2014 em-dash at index 15. _build_fallback_decision asserts endswith at construction time as belt-and-suspenders for the unit tests. All fallback paths (3 tau gates + V5 empty + V7 try/except wrapper) emit a rationale ending with this suffix.
- [Phase 01]: Phase 1 Plan 06: D-18 runtime import-graph guard in src/routing/tests/test_decide_smoke.py walks sys.modules after `import src.routing.decide` and asserts none of {fastapi, httpx, requests, aiohttp, anthropic, openai} appear at the top-level-package level. Test passes today; Phase 2 / Phase 3 planners must keep the guard green when adding new imports to src/routing/.
- [Phase 01]: Phase 1 Plan 06: ROUTER-06 quality_first_pick cost-tiebreaker did NOT fire during CLI smoke testing on canonical prompts (top-1 to top-2 gap >> epsilon=0.02). Plan 07's canary should exercise boundary prompts to confirm the tiebreaker fires when expected; sweeping epsilon ∈ {0.01, 0.02, 0.05, 0.10} via the settings dict will produce the activation-rate histogram.
- [Phase ?]: Phase 1 Plan 07: routing_decision_eval canary has 42 hand-labeled rows; first end-to-end run gives backend_accuracy=0.9048 (PASS, > 0.65 threshold) but per-stage ECE on canary-proxy y_true (0.42 task_type, 0.14 agentic_intent, 0.44 model_router) all exceed 0.10 — proxy uses backend_match as per-stage truth so NOT directly comparable to Plan 05 training-set ECE. --check exits 1 today; Plan 08 owns the isotonic recalibration decision.
- [Phase ?]: Phase 1 Plan 07: D-01 cascade mis-routes 4 chat-side prompts (write a haiku, write a Python function for fizzbuzz, show me a one-liner to reverse a string, summarize URL article) to claude_code because 'write' is in BUILD_KEYWORDS AND/OR the calibrated task classifier predicts task=coding on short chat-coding requests. Canary surfaces this as designed (Plan 06 follow-up; Plan 07 is not responsible for the fix). Possible fixes: tighten BUILD_KEYWORDS, raise agentic_intent_tau on the canary slice, or add a chat-snippet vs project-edit feature.
- [Phase ?]: Phase 1 Plan 07: ROUTER-06 tier_tiebreaker fires 0 of 42 times on canary at default epsilon=0.02 — calibrated model_router produces sharp top-1 predictions on every canary prompt. Boundary-region prompts I added (haiku, fizzbuzz, one-liner) route to claude_code BEFORE the model_router stage runs so they never exercise the tiebreaker. Plan 08 would need a dedicated boundary-region slice (deliberately within epsilon of two equal-tier OpenRouter models) AND a --epsilon CLI flag to exercise this.
- [Phase ?]: Phase 1 Plan 08: asymmetric regression-guard tolerance — block accuracy regressions > 0.02, accept improvements freely (Plan 05 SUMMARY carry-forward). Plan 05's model_router accuracy improved +0.23 (Option-A extended-feature retrain) which would have wrongly failed a strict |delta| <= 0.02 check.
- [Phase ?]: Phase 1 Plan 08: carry-forward known-delta pattern in test_no_regression.py — macro_f1 (0.30 carry), task_type ECE (0.05 carry), model_router ECE (0.02 carry) admit Plan 05's documented retrain deltas. baselines.json NOT re-snapshotted; preserves traceability back to Plan 05's pre-calibration numbers.
- [Phase ?]: Phase 1 Plan 08: argmax-agreement floors set as CANARIES (0.65 task_type / 0.10 model_router) — above random-baseline 1/n_classes but below observed first-run values. Plan 05's Option-A retrain legitimately moves many argmaxes; floors catch vectorizer/scaler refit accidents (collapse near random), not the documented retrain shift.
- [Phase ?]: Phase 1 Plan 08: route_prompt signature stays BACKWARD-COMPATIBLE via optional agentic_intent_artifacts kwarg. main() pre-loads all 3 calibrated heads + model_mapping before the REPL loop. NEW result['routing_decision'] key surfaces alongside legacy keys; print_route_result emits Rationale/Confidence with graceful degradation when key absent.
- [Phase ?]: Phase 1 Plan 08 carry-forwards (NOT regressions): canary-set ECE > 0.10 on all 3 heads (Plan 07 finding — proxy y_true; not directly comparable to per-stage training ECE); 4 openrouter canary rows misroute to claude_code (D-01 cascade boundary); ROUTER-06 tier_tiebreaker fires 0/42 (calibrated router top-1 is sharp). All three deferred to follow-up plans per Plan 07 SUMMARY guidance.
- [Phase ?]: Phase 2 Plan 00: RedactionFilter Pattern 10 recipe fixed — Filter on root logger is not consulted when child-logger records propagate to parent handlers (Python logging quirk). Added logging.setLogRecordFactory wrapper that redacts every LogRecord at creation time. RedactionFilter on root + handlers retained as belt-and-suspenders. Both layers clear record.args (Pitfall 8).
- [Phase ?]: Phase 2 Plan 00: D-19 contract suite stub lazy-imports adapter classes inside conftest.adapter_factory (try/except ImportError -> pytest.skip). test_adapter_contract.py has zero module-level adapter imports (B3 fix verified by negative grep).
- [Phase ?]: Phase 2 Plan 00: config/pricing.json _default row locked at {input_per_mtok: 5.00, output_per_mtok: 20.00} per CONTEXT specifics line 266 — conservative upper bound so cost cap trips even on unknown OpenRouter slugs.
- [Phase ?]: Phase 2 Plan 00: apps/api uses pathlib.Path(__file__).resolve().parents[2] for PROJECT_ROOT (CONTEXT line 245) rather than the Phase 1 os.path.dirname chain. Establishes pathlib as the convention inside the apps/ subtree.
- [Phase 02]: openai SDK 2.36 AuthenticationError + APIStatusError constructors dereference response.request — passing response=None per RESEARCH Pattern 3 raises AttributeError. Adapter and tests construct minimal httpx.Request + httpx.Response(status=401) via _build_missing_key_error / _make_auth_error helpers.
- [Phase 02]: PROVIDER_ERROR_MAP isinstance lookup fails after Phase 1 D-18 guard purges openai from sys.modules. Fix: map_provider_error compares by fully-qualified class name as fallback to isinstance. test_provider_error_map_has_all_four_classes also rewritten to compare by name.
- [Phase 02]: D-19 contract suite for openrouter parameterization passes 5/6 invariants (test_step_cap_aborts skipped per pytest.skip — N/A for single-round-trip OpenRouter). 24 unit tests + 5 parametric cases pass.
- [Phase ?]: Phase 2 Plan 02: ClaudeCodeAdapter uses duck-typed message/block dispatch (_is_* helper pair: isinstance + class-name fallback) so Fake* dataclasses in tests/fakes.py work without monkeypatching the SDK imports. Real SDK objects still match via the isinstance leg. Plan Task 1 line 251 explicitly anticipated this choice.
- [Phase ?]: Phase 2 Plan 02: ClaudeCodeAdapter constructor skips ANTHROPIC_API_KEY preflight when client_factory is provided (test-injection escape valve). D-19 shared contract suite's adapter_factory passes client_factory and no api_key — without this gate the contract suite cannot construct the adapter. The standalone test_missing_api_key_raises_before_stream invariant (no factory, no env) still raises correctly.
- [Phase ?]: Phase 2 Plan 02: D-19 step_cap_aborts contract test passes as a real positive for claude_code (unlike openrouter's pytest.skip single-round-trip N/A). The conftest fake yields multiple AssistantMessages, the StepCounter trips on the second one, and the adapter emits StreamError(step_cap_exceeded) + Done + interrupt(). All 6 D-19 invariants are real passes.
- [Phase ?]: Phase 2 Plan 02: ClaudeCodeAdapter re-export in __init__.py deferred to Task 2 commit (same pattern Plan 02-01 Decision #4 for OpenRouter). Task 1 ships __init__.py with only the watchdog setdefault so the cost/errors/step_counter/workspace submodules are importable during the Task 1 RED phase without an unresolved import chain.
- [Phase 02]: Phase 2 Plan 03: anthropic SDK 0.102 AuthenticationError requires response: httpx.Response (non-Optional, keyword-only). Adapter and tests construct minimal httpx.Request + httpx.Response(status_code=401) via _build_missing_key_error helpers. Same Rule 1 pattern as Plan 02-01 Decision #1 (openai SDK 2.36).
- [Phase 02]: Phase 2 Plan 03: ComputerUseAdapter cap checks are duplicated at TOP and BOTTOM of every agent-loop iteration. Post-iteration checks fire AFTER steps.increment() AND AFTER final_msg.usage is recorded — the primary cap gates because single-iteration streams cannot trip the cap via pre-increment top-of-loop checks alone (D-19 invariants #2 + #3).
- [Phase 02]: Phase 2 Plan 03: All 3 Wave 1 adapters now in place; D-19 shared contract suite passes 17/18 (computer_use 6/6 + claude_code 6/6 + openrouter 5/6 with 1 intentional N/A skip). Whole-repo non-live test pass: 229 passed / 2 skipped / 3 deselected.
- [Phase 02]: Phase 2 Plan 03: ComputerUseAdapter step_counter.py is sibling to claude_code/step_counter.py per D-08 — same class shape, only DEFAULT_STEP_CAP differs (15 vs 25). No cross-import. Future plan can promote to shared module once class shape proves stable.
- [Phase 02]: Phase 2 Plan 04: Pre-commit no-deprecated-sdk.sh fixed (Rule 1) — RESEARCH Pattern 11's single-regex form silently failed because [^+] consumes the 'i' of 'import' and .* cannot backtrack. Replaced with two-step grep pipeline mirroring no-secrets.sh.
- [Phase 02]: Phase 2 Plan 04: OSS-06 triad fully landed — (a) pre-commit hook on staged content + uv.lock, (b) CI 'from claude_agent_sdk import ClaudeAgentOptions' import smoke, (c) CI '! grep -q claude-code-sdk uv.lock' assertion. Plus pyproject.toml pin (Wave 0). Four redundant guardrails against re-introducing the deprecated SDK.
- [Phase 02]: Phase 2 Plan 04: live-smoke.yml weekly cron is OpenRouter-only. Anthropic / computer-use excluded from the cron because computer-use also needs Chromium + COMPUTER_USE_OPT_IN=1. Operators use workflow_dispatch for those. Budget ~$0.43/month per repo with OPENROUTER_API_KEY set.
- [Phase 02]: Phase 2 Plan 04: REQUIREMENTS.md BACKEND-01 union grew from 6 to 7 variants — ToolResult between ToolCall and FileDiff per CONTEXT D-02. Phase 2 Plans 00-03 already built against 7-variant shape; docs reconciliation only. BACKEND-06 verified as already correct per D-15.
- [Phase 02]: Phase 2 complete (15/15 requirements satisfied; 5/5 success criteria verifiable). Wave 0 + Wave 1 + Wave 2 all green. Whole-repo non-live suite passes (exit 0). Ready for /gsd-verify-work to validate.
- [Phase 02]: Phase 2 Plan 05 (gap closure CR-01): Claude Code adapter now uses _pending_tool_calls dict (local to each stream() invocation) to pair ToolUseBlock(id, name, input) with ToolResultBlock(tool_use_id) — matches the real claude_agent_sdk==0.1.81 ToolResultBlock three-field shape (tool_use_id + content + is_error). FakeToolResultBlock fields tool_name and input removed (they masked the bug).
- [Phase 02]: Phase 2 Plan 05: TDD RED gate landed first (commit fd297a3) — regression test test_filediff_emitted_against_real_sdk_shape fails on the buggy adapter with len(file_diffs) == 0. GREEN landed in commit 2e79161 with adapter + fakes + existing T6/T7/T8 updates atomically.
- [Phase 02]: Phase 2 Plan 05: _pending_tool_calls.pop(tool_use_id, ('', {})) defensive default — if a ToolResultBlock arrives without a preceding ToolUseBlock the empty tool_name falls through to the ToolResult branch (no FileDiff misfire, no raise). Aligns with surrounding V7 robustness style.
- [Phase ?]: Phase 2 Plan 06 (gap closure CR-02): ComputerUseCostTracker.record_iteration_usage uses override semantics (=) for _tokens_in/_tokens_out matching its docstring and the parallel OpenRouter/Claude Code trackers; cache counters (_cache_read_total/_cache_write_total) PRESERVED as += because they are visibility-only running totals across iterations.
- [Phase ?]: Phase 2 Plan 06: TDD RED gate landed first (commit 43b40ab) — regression test test_record_iteration_usage_overrides_running_estimate asserts tokens_out() == 5 after text='x'*40 + record_iteration_usage(input_tokens=10, output_tokens=5). RED commit showed 'assert 15 == 5'. GREEN landed in commit a95617a.
- [Phase 02]: Phase 2 Plan 07 (gap closure CR-04 + CR-05): SECRET_PATTERNS reordered with Bearer pattern FIRST so canonical Authorization: Bearer sk-... headers consume as a single Bearer ***REDACTED*** unit; scripts/no-secrets.sh regex set unified with logging_filter alphabets (sk- gains _-, Bearer gains [[:space:]]+); parity test test_logging_filter_and_no_secrets_regex_parity + dedicated CI step prevent future drift. Manual paste tests for sk-AAAAA_AAAA... and Bearer<tab><token> now BLOCK at staging time (previously slipped through). 9/9 logging_filter tests pass; 133 Phase 2 tests pass (was 131; +2 new).

### Pending Todos

None yet.

### Blockers/Concerns

None yet. Two items flagged in research need resolution during Phase 1 planning:

- Phase 1: OOD/unknown task-type class definition + uncertainty threshold values are judgment calls (research recommends a half-day spike before training).
- Phase 2: Computer-use adapter shape (coordinate scaling, screenshot→tool_result loop) warrants a thin implementation spike before detailed planning.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none — first milestone)* | | | |

## Session Continuity

Last session: 2026-05-15T19:57:57.528Z
Stopped at: Completed 02-07-PLAN.md (CR-04 + CR-05 gap closure — redaction regex parity + Bearer-first ordering)
Resume file: None
