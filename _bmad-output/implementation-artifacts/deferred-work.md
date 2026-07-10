# Deferred Work

## Deferred from: code review of story 1.1 (2026-07-08)

- **Non-openrouter reroute fallback branch untested** — `_enabled_backends` only applies the `["openrouter"]` floor when the enabled set is empty; if openrouter is explicitly disabled but another backend is enabled, `fallback = enabled[0]` (a non-openrouter backend). That branch (`turn.py:840`) — including that the fallback adapter dispatches and the breadcrumb reads correctly — has no test. Breadcrumb logic itself is correct (uses `original.*`), so this is coverage, not a bug.
- **`computer_use`→openrouter reroute doesn't assert the breadcrumb** — `test_computer_use_unreachable_on_auto_turn_without_strict_and` (`test_turn_allowlist.py:212`) checks only `row["backend"]`, not `rerouted_from`/`rerouted_from_model`, though it exercises the same synth path. Low-value coverage gap.

## Deferred from: code review of story 2.3 (2026-07-10)

- **ECE-proxy deflation is fail-open** — `src/evaluation/evaluate_routing.py:539-590,220`. When `_stage_predict_proba` throws, `run()` substitutes `prob=0.0`, which lands in no ECE bin and lowers a head's canary ECE, so a broken head could pass the ECE threshold. Pre-existing property of the ECE proxy (documented in `run()`'s own note), unchanged by 2.3. Harden the ECE computation / fallback accounting when the eval harness / Epic 3 gate is next touched.
- **`evaluate_check` does not guard NaN ECE** — `src/evaluation/evaluate_routing.py:889`. `NaN > threshold` is False → a NaN ECE passes. Not reachable via `run()` today; latent for Epic 3's reuse of `evaluate_check` as the FR-15 gate. Add a one-line `math.isnan` fail-closed guard when Epic 3 wires the reusable gate.
- **`main()` conflates infra errors with gate-fail exit 1** — `src/evaluation/evaluate_routing.py:953-955`. Only `FileNotFoundError` → exit 2; any other `run()` exception exits 1 with a traceback, indistinguishable from a real gate failure. Pre-existing in `main()`. Widen the handler (distinct exit code for infra vs. policy failure) if CI needs to tell them apart.
