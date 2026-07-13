# Deferred Work

## Deferred from: code review of story 1.1 (2026-07-08)

- **Non-openrouter reroute fallback branch untested** — `_enabled_backends` only applies the `["openrouter"]` floor when the enabled set is empty; if openrouter is explicitly disabled but another backend is enabled, `fallback = enabled[0]` (a non-openrouter backend). That branch (`turn.py:840`) — including that the fallback adapter dispatches and the breadcrumb reads correctly — has no test. Breadcrumb logic itself is correct (uses `original.*`), so this is coverage, not a bug.
- **`computer_use`→openrouter reroute doesn't assert the breadcrumb** — `test_computer_use_unreachable_on_auto_turn_without_strict_and` (`test_turn_allowlist.py:212`) checks only `row["backend"]`, not `rerouted_from`/`rerouted_from_model`, though it exercises the same synth path. Low-value coverage gap.

## Deferred from: code review of story 2.3 (2026-07-10)

- **ECE-proxy deflation is fail-open** — `src/evaluation/evaluate_routing.py:539-590,220`. When `_stage_predict_proba` throws, `run()` substitutes `prob=0.0`, which lands in no ECE bin and lowers a head's canary ECE, so a broken head could pass the ECE threshold. Pre-existing property of the ECE proxy (documented in `run()`'s own note), unchanged by 2.3. Harden the ECE computation / fallback accounting when the eval harness / Epic 3 gate is next touched.
- **`evaluate_check` does not guard NaN ECE** — `src/evaluation/evaluate_routing.py:889`. `NaN > threshold` is False → a NaN ECE passes. Not reachable via `run()` today; latent for Epic 3's reuse of `evaluate_check` as the FR-15 gate. Add a one-line `math.isnan` fail-closed guard when Epic 3 wires the reusable gate.
- **`main()` conflates infra errors with gate-fail exit 1** — `src/evaluation/evaluate_routing.py:953-955`. Only `FileNotFoundError` → exit 2; any other `run()` exception exits 1 with a traceback, indistinguishable from a real gate failure. Pre-existing in `main()`. Widen the handler (distinct exit code for infra vs. policy failure) if CI needs to tell them apart.

## Deferred from: code review of story 3.1 (2026-07-10)

- **Empty-string `message_id` silently skipped** — `src/data/build_retraining_dataset.py:116`. The web UI can send `message_id=""` (fallback when the server id didn't arrive); pydantic accepts it and the assembler's `if not mid` skips it (warn-logged only). A genuine rating is then excluded from training. Upstream data-quality issue; surface the skip count or fix the UI fallback if it proves common.
- **Scaffold degenerate at tiny counts; mix-test asserts on raw list** — `src/data/seed_synthetic_feedback.py` + `test_seed_synthetic_feedback.py`. `synthesize(1)/(2)` don't produce all three labels post-dedup, and `test_synthesize_has_discriminative_mix` checks the raw feedback list rather than the post-dedup assembled CSV. Throwaway scaffold; tighten only if the scaffold outlives the dry run.
- **AD-8 `apps.*` half is convention-only** — `eval/tests/test_import_graph.py` forbids only `{eval, inspect_ai}` under `src/`; the "no `apps.*`/`src.routing`" half of AD-8 is not test-enforced. Extend the import-graph guard to assert the apps-direction arrow when convenient.

## Deferred from: story 3.2 design (2026-07-10)

- **Close the retrain feature/serve-parity gap before real promotion** — the model_router candidate (Story 3.2) trains on `origin_query` + inline handcrafted numerics but WITHOUT the Stage-1 `task_type`/`keyword_type` tokens and `question_type_confidence` that the production router text input carries, so the candidate's feature schema differs from `decide.py`'s. Harmless in the dry run (Story 3.3 with 0 feedback promotes nothing), but a candidate must not be promoted until this is closed. **Fix:** the signals were never lost — each `routing_feedback.jsonl` row's `decision.signals` already carries `task_type` + `task_confidence`; project those into Story 3.1's `retraining_dataset.csv` (a small `build_retraining_dataset.py` amendment) so the candidate trains on the exact features the brain used — do NOT re-derive via the live classifier (re-derivation skew). Gate this behind the same ≥100-real-feedback threshold that arms promotion.

## Deferred from: code review of story-3.2 (2026-07-13)

- **Trivial-N candidate metrics/ECE can mislead the 3.3 gate** — `src/model_router/retrain_candidate.py:158-166`. At the thin-data guard boundary (e.g. 2 classes × 3 rows) the 0.2 test split leaves a 1–2 row test set, so the printed `accuracy`/`macro_f1`/`ECE` are statistically meaningless but non-crashing. Deferred because Story 3.3's ≥100-real-feedback volume gate blocks promotion of any trivial-N candidate, so these numbers never drive a decision. Revisit if 3.3 ever consumes candidate ECE at low N.
