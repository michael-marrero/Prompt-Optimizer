---
baseline_commit: 75868e5f96b7d1f8ac2d2a03e026848215da9e67
---

# Story 3.1: Assemble a retraining dataset from captured signal

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the builder,
I want a data-pipeline stage that joins the captured routing signal (`routing_decisions.jsonl`, `routing_feedback.jsonl`) — enriched from the transcript where available — into a single labeled CSV,
so that captured routes and their up/down/cleared ratings become training rows keyed on the route the brain **originally wanted** (Epic 1), ready for Story 3.2 to retrain candidate heads.

## Acceptance Criteria

1. **One labeled row per rated turn, keyed on the original pick.**
   **Given** the JSONL sinks (starting from the synthetic seed) and, where present, the transcript
   **When** `python -m src.data.build_retraining_dataset` runs
   **Then** it emits a CSV under `data_processed/` with one row per **rated** turn carrying: the prompt (`origin_query`), the **original pick** (`original_backend` + `original_model` — Epic 1's `rerouted_from`/`rerouted_from_model`, falling back to the dispatched route when no reroute occurred), the **dispatched route** (`dispatched_backend` + `dispatched_model`), and the `label` ∈ {`up`, `down`, `cleared`}
   **And** prompt features (the `PromptFeatureExtractor` handcrafted columns) are attached to each row (inline, or via the existing `build_features.py` step — see Dev Notes).

2. **`cleared` supersedes a prior rating for the same turn.**
   **Given** multiple feedback events for the same turn (e.g. `up` then `cleared`)
   **When** assembly runs
   **Then** the turn produces exactly ONE row whose `label` is the latest event by timestamp (a `cleared` supersedes an earlier `up`/`down`), never two rows for the same turn
   **And** the dedup key is the feedback turn identifier (`message_id`) — documented in the module.

3. **Files-on-disk coupling only; no `apps.*` import (AD-8 / AD-2 / D-18).**
   **Given** the stage lives in `src/data/`
   **When** it reads the signal
   **Then** it reads the JSONL files (and, if the transcript is used, the SQLite DB) purely as on-disk artifacts via stdlib — it does **not** `import apps.*` (or `src.routing`/`eval`), so the one-way dependency arrow is preserved
   **And** the D-18 import-graph guard (`eval/tests/test_import_graph.py`) stays green.

4. **Dry-run on the synthetic seed completes and reports, deterministically.**
   **Given** the ~1,210-row synthetic seed and today's real feedback (0 events)
   **When** the stage runs
   **Then** it completes without error, logs how many decisions/feedback events it read and how many rated rows it wrote, and writes a well-formed CSV (header + rows) — producing 0 rated rows if there are genuinely 0 rated turns, without crashing
   **And** the assembly logic is covered by a **data-independent** unit test that builds in-memory JSONL records (no dependency on a materialized seed or `chat.db`), proving the join, the `cleared`-supersede rule, and the original-pick fallback.

## Tasks / Subtasks

- [x] Task 1: Create the assembly stage skeleton in `src/data/` (AC: #1, #3)
  - [x] Add `src/data/build_retraining_dataset.py` mirroring `src/data/build_classifier_dataset.py`: module docstring with CLI usage, `PROJECT_ROOT = Path(__file__).resolve().parents[2]`, `argparse` CLI (`--routing-decisions`, `--routing-feedback`, `--output`, `-v/--verbose`), `_setup_logging`, `main(argv) -> int` returning `0` on success / `2` on missing input, `if __name__ == "__main__": sys.exit(main())`.
  - [x] Default paths: `--routing-decisions` and `--routing-feedback` default to the runtime sinks under `PROMPT_OPTIMIZER_HOME`/`~/.prompt-optimizer/.planning/data/` (resolve the same way `apps/api/paths.py` does, but WITHOUT importing `apps.*` — re-derive `os.environ.get("PROMPT_OPTIMIZER_HOME") or Path.home()/".prompt-optimizer"` locally). Output defaults to `data_processed/retraining_dataset.csv`.
  - [x] Imports: stdlib (`argparse`, `csv`, `json`, `logging`, `os`, `sys`, `pathlib`, `dataclasses`, `typing`) + `pandas` + the `PromptFeatureExtractor` (via the `sys.path` shim used across `src/`, OR reuse `build_features.py`). **No `apps.*`, no `src.routing`, no `eval`.**
- [x] Task 2: Parse + join the two JSONL sinks into rated turns (AC: #1, #2)
  - [x] `stream_jsonl(path) -> Iterable[dict]`: yield `json.loads(line)` for each non-blank line (mirror the test reader at `apps/api/tests/test_turn_allowlist.py:109-116`; tolerate a missing file → empty, and a malformed line → `logging.warning` + skip, like `flatten_raw_jsons.py`).
  - [x] **Primary source = `routing_feedback.jsonl`** (each row is self-contained: `prompt`, `decision{backend, model_or_agent, signals, ...}`, `sentiment`, `message_id`, `thread_id`, `timestamp`). Build one `RatedTurn` per feedback event, then dedup by `message_id`.
  - [x] **Original pick:** from the feedback row's `decision.signals` — `signals.get("rerouted_from")`/`signals.get("rerouted_from_model")` if present (a reroute happened), ELSE fall back to `decision.backend`/`decision.model_or_agent` (no reroute → brain's pick == dispatched). **Dispatched route** = `decision.backend`/`decision.model_or_agent`.
  - [x] **`cleared` supersede (AC #2):** group events by `message_id`; within a group keep the event with the max `timestamp` (ISO-8601 sorts lexically). The surviving event's `sentiment` is the row's `label`. One row per `message_id`.
  - [x] **Optional decisions.jsonl enrichment:** because `decisions.jsonl` keys on `turn_id` and feedback on `message_id` (no shared key — only `thread_id`), do NOT attempt a lossy id join. Treat `--routing-decisions` as an optional cross-source for the dry run (see Task 4 + Dev Notes design decision). The rated-turn row is fully constructable from the feedback record alone.
- [x] Task 3: Attach prompt features and write the CSV (AC: #1)
  - [x] Compute handcrafted features per row with `PromptFeatureExtractor().extract(origin_query)` (same call `build_features.py:48-67` uses), OR emit the base labeled columns and document that `python -m src.feature_extraction.build_features` appends the `*_features.csv`. **Pick one, comment the choice** (inline keeps the output directly trainable; the two-step reuses the existing feature stage — Dev Notes recommends inline for a self-contained artifact).
  - [x] Base output columns (before features): `message_id`, `thread_id`, `timestamp`, `origin_query`, `original_backend`, `original_model`, `dispatched_backend`, `dispatched_model`, `label`. Write via `csv.DictWriter(..., extrasaction="ignore")` with `newline=""`; `output.parent.mkdir(parents=True, exist_ok=True)`. Sort rows deterministically (e.g. by `timestamp` then `message_id`).
  - [x] Log counts: decisions read, feedback events read, turns after dedup, rows written (INFO), and print/log `Wrote N rated turns to <path>`.
- [x] Task 4: Dry-run resilience (AC: #4)
  - [x] The stage must complete cleanly with **0 rated turns** (empty/absent `routing_feedback.jsonl`): write a header-only CSV and log `0 rated turns`, exit `0` (do NOT treat empty feedback as an error — Story 3.3 depends on "0 feedback events → loop runs, promotes nothing").
  - [x] The assembly stage itself stays a **pure feedback→CSV reader** — it does NOT synthesize or default any labels. The dry-run's labels come from the separate scaffold in Task 7, which writes a real-shaped `routing_feedback.jsonl` that this stage then reads through the ordinary path. (Judged decision D2 = Option E, 2026-07-10.)
- [x] Task 7: Dry-run seed scaffold — **throwaway**, isolated from the assembly (AC: #4)
  - [x] Add `src/data/seed_synthetic_feedback.py` (a distinct module, NOT part of `build_retraining_dataset.py`) that synthesizes a coherent `routing_decisions.jsonl` + `routing_feedback.jsonl` seed from the benchmark ground-truth so 3.2's dry run has discriminative rows. Mark it clearly as a disposable dry-run scaffold (module docstring: "delete once real feedback flows").
  - [x] **Label rule (Option D, principled — no fabrication-by-fiat):** join the benchmark best-model labels (`data_processed/classifier_training.csv` / the router dataset — `origin_query` → `best_model`); for each synthesized turn set `sentiment = "up"` when the router's `original_pick` model matches the benchmark winner, `"down"` otherwise. Emit a small fraction of `"cleared"` events (superseding an earlier rating for the same `message_id`) so the dry run exercises AC #2's supersede path. Log the up/down/cleared counts.
  - [x] Keep the two files coherent: each feedback row's embedded `decision` snapshot (backend/model_or_agent/signals) must match its paired decision record, and `signals.rerouted_from*` should be populated on the subset meant to represent reroutes so the original-pick fallback (Task 2) is exercised both ways.
  - [x] CLI mirrors the other builders (`argparse`, `main() -> int`, `-v`); default output dir = the seed's `.planning/data/` under `PROMPT_OPTIMIZER_HOME`, overridable via a flag so tests write to `tmp_path`.
  - [x] This module is a scaffold, not a safety path — a light unit test that it emits a valid, coherent JSONL pair (readable by Task 2's reader) is sufficient; no exhaustive coverage.
- [x] Task 5: Data-independent test (AC: #2, #3, #4)
  - [x] Add `src/data/tests/test_build_retraining_dataset.py` (create `src/data/tests/__init__.py` if absent). Build in-memory JSONL records written to `tmp_path` — NO dependency on a materialized seed or `chat.db`.
  - [x] Cases: (a) two feedback events for one `message_id` (`up` then later `cleared`) → ONE row, `label == "cleared"`; (b) a rerouted decision → `original_*` come from `rerouted_from*`, `dispatched_*` from `decision.*`; (c) a non-rerouted decision → `original_* == dispatched_*`; (d) empty feedback file → header-only CSV, exit 0.
  - [x] Assert the output CSV columns and the row count. RED-then-GREEN.
- [x] Task 6: Regression + guard sanity (AC: #3)
  - [x] Run `uv run pytest src/data eval/tests/test_import_graph.py` — the new test passes and the D-18 import-graph guard stays green (proving no `apps.*`/`eval` import crept in).

### Review Findings

_Code review 2026-07-10 (3 adversarial layers). Acceptance Auditor: all 4 ACs MET, deviations honest, scope intact, D-18 green. 0 decision-needed, 3 patch, 3 defer, 5 dismissed. The feared silent feature-column-drop was verified a NON-issue (`extract("")` returns an identical key set to any real prompt)._

- [x] [Review][Patch] **FIXED 2026-07-10.** Supersede breaks on mixed-precision ISO timestamps [src/data/build_retraining_dataset.py] — added `_ts_key()` parsing `datetime.fromisoformat(ts.replace("Z","+00:00"))`; `assemble_rated_turns` and the output sort now compare parsed datetimes (exact ties keep the later-seen append-only record). Regression test `test_cleared_wins_over_earlier_whole_second_up`.
- [x] [Review][Patch] **FIXED 2026-07-10.** One malformed feedback line crashes the whole build [src/data/build_retraining_dataset.py] — `assemble_rated_turns` now `isinstance`-guards the record, `decision`, and `signals` (non-dict → warn+skip / coerce to `{}`). Regression test `test_malformed_records_warn_and_skip`.
- [x] [Review][Patch] **FIXED 2026-07-10.** Dead `--routing-decisions` CLI flag [src/data/build_retraining_dataset.py] — removed the flag and the `DEFAULT_DECISIONS` constant.
- [x] [Review][Defer] Empty-string `message_id` silently skipped [src/data/build_retraining_dataset.py:116] — the real UI can send `message_id=""` (fallback), pydantic accepts it, and `if not mid` skips it (warn-logged, not surfaced in the row count). A genuine rating whose server id didn't arrive is excluded. Upstream data-quality issue; low volume; deferred.
- [x] [Review][Defer] Scaffold degenerate at tiny counts + mix-test asserts on raw list [src/data/seed_synthetic_feedback.py; test_seed_synthetic_feedback.py] — `synthesize(1)/(2)` don't yield all three labels post-dedup, and the mix test checks the raw feedback list, not the post-dedup CSV distribution. Throwaway scaffold; realistic counts (1210) are fine; deferred.
- [x] [Review][Defer] AD-8 `apps.*` half is convention-only [eval/tests/test_import_graph.py] — the D-18 guard forbids only `{eval, inspect_ai}` under `src/`; the `no apps.*/src.routing` half of AD-8 is not test-enforced. Currently satisfied; a guard extension is out of 3.1 scope. Deferred.

## Dev Notes

**Epic 3 builds the feedback→retrain loop as a gated dry-run. 3.1 = the ASSEMBLY stage (signal → labeled CSV). 3.2 retrains candidate heads from this CSV into a staging dir; 3.3 gates promotion behind data-volume + FR-15 no-regression + Epic 2's calibration-coverage check. Scope of 3.1 is the CSV assembly ONLY — do not retrain, do not promote, do not touch `models/`.**

### The captured signal — exact schemas (verified 2026-07-10)

- **`routing_decisions.jsonl`** — written by `apps/api/jsonl_log.py:119-134`, called from `apps/api/routes/turn.py:872`. Path `USER_HOME/.planning/data/routing_decisions.jsonl` (`apps/api/paths.py:75`; `USER_HOME` = `PROMPT_OPTIMIZER_HOME` env or `~/.prompt-optimizer`). Record:
  `{turn_id, thread_id, timestamp, backend, model_or_agent, rationale, confidence, signals}`.
  The Epic-1 breadcrumb lives in `signals`: `signals["rerouted_from"]` / `signals["rerouted_from_model"]` are the **backend/model the brain originally picked** before an allowlist reroute (set at `turn.py:590-595`); **absent when no reroute** (then the brain's pick == the dispatched route).
- **`routing_feedback.jsonl`** — written by `apps/api/routes/feedback.py:143-178`. Path `USER_HOME/.planning/data/routing_feedback.jsonl` (`paths.py:91`). Record:
  `{sentiment: "up"|"down"|"cleared", timestamp, thread_id, message_id, prompt, decision: {backend, model_or_agent, rationale, confidence, signals}}`.
  **This row is self-contained for a rated turn** — it carries the prompt AND a snapshot of the decision (including the `signals` with the `rerouted_from*` breadcrumb the UI saw). `sentiment == "cleared"` is a literal string, not a null/delete.
- **Join reality (load-bearing):** `decisions.jsonl` keys on `turn_id`; `feedback.jsonl` keys on `message_id`; **they share no id — only `thread_id`.** The transcript (`messages` table in `chat.db`) links `message_id ↔ thread_id`. Because the feedback record already embeds the decision snapshot, **3.1 builds each rated row from the feedback record alone** and does NOT need a fragile `turn_id↔message_id` correlation. Treat `decisions.jsonl` as an optional dry-run source (see below), not a required join partner.

### Conventions to mirror (do not reinvent)

- **Home for the stage:** `src/data/build_retraining_dataset.py` — the `src/data/` pipeline-builder layer; naming `build_<artifact>_dataset.py` (CLAUDE.md Naming Patterns). No `src/retrain/` dir exists; do not create one.
- **Canonical builder shape:** `src/data/build_classifier_dataset.py:1-231` — module docstring with `python -m ...` usage, `argparse` CLI (pipeline tools take flags, NOT interactive `input()`), `main(argv) -> int` (`0` ok / `2` missing input), `csv.DictReader`/`DictWriter` with `newline=""`, in-memory dict keyed by the grouping dimension for dedup (NOT list-append), `logging` module with timestamped format configurable via `-v`. `flatten_raw_jsons.py` shows the malformed-input `logging.warning`+skip pattern.
- **Prompt features:** `PromptFeatureExtractor.extract(text) -> dict` (`src/feature_extraction/Feature_extractor.py:101`) yields ~50 handcrafted columns; `build_features.py:48-67` shows the `pd.concat([df, feats_df], axis=1)` attach pattern writing `<name>_features.csv`. The training text column convention is `origin_query`.
- **Output:** `data_processed/retraining_dataset.csv` (constant `DEFAULT_OUTPUT = PROJECT_ROOT / "data_processed" / "retraining_dataset.csv"`).

### Guardrails

- **AD-8 / AD-2 / D-18 — no `apps.*` import.** `src/data/` and `src/feature_extraction/` currently import zero `apps.*` (verified). Re-derive the `PROMPT_OPTIMIZER_HOME` path locally rather than importing `apps.api.paths`. Reading `chat.db` (if the transcript is ever used) must be via stdlib `sqlite3` on the file path — never `apps.api.db`. The guard is `eval/tests/test_import_graph.py` (D-18); keep it green.
- **Determinism.** Sort output rows; ISO-8601 timestamps sort lexically for the `cleared`-supersede tiebreak. No `Date.now()`/random in the assembly — timestamps come from the records.
- **Redaction already applied.** `feedback.py:178` redacts key-shapes before disk, so the JSONL prompt is already sanitized; 3.1 does not need to re-redact, but must not log full prompts at INFO.
- **Data-independence (2.1/2.2/2.3 lesson).** The assembly logic MUST be unit-testable from in-memory JSONL fixtures in `tmp_path` — never gate the test on a materialized seed or `chat.db`. This is the recurring flake class across Epic 2.
- **Fail-open is fine here (opposite of Epic 2).** This is a data-prep stage, not a safety gate: 0 rated turns is a valid, non-error outcome (Story 3.3 relies on it). Do not raise on empty feedback.

### Design decisions (RESOLVED 2026-07-10)

- **D1 — Primary source = feedback JSONL.** Build rated rows from `routing_feedback.jsonl` alone (self-contained). `routing_decisions.jsonl` is optional dry-run fodder, not joined by id. Rejected: correlate `turn_id↔message_id` via `thread_id` + chronology — lossy and needs the DB.
- **D2 — Synthetic-seed label semantics → Option E (LLM-as-judge, 2026-07-10; winner 4.4/5).** The assembly stage stays a **pure feedback→CSV reader** and never fabricates labels. A separate, disposable scaffold (`src/data/seed_synthetic_feedback.py`, Task 7) synthesizes a coherent `decisions.jsonl` + `feedback.jsonl` seed from benchmark ground-truth, labeling `up`/`down` by whether the router's original pick matches the benchmark winner (Option D's principled label), plus a small `cleared` fraction. Rejected: (A) pure-only → 0 rows, vacuous dry-run [disqualified on usefulness]; (B) generate the seed inside `build_retraining_dataset.py` → scope creep, impurity; (C) default/fabricate a label inside the assembly → poisons training, dishonest.
- **D3 — Feature attachment → inline (confirmed by user).** Call `PromptFeatureExtractor` inside the stage so the CSV is directly trainable by 3.2. Comment the choice.
- **D4 — Original-pick granularity.** Capture both `original_backend` + `original_model` (and the dispatched pair) so 3.2 can target whichever head it retrains. Do not collapse to a single string.

### Previous-story intelligence (Epic 1 + Epic 2, all done)

- Epic 1 shipped the capture this story consumes: `rerouted_from`/`rerouted_from_model` in `signals` (JSONL `turn.py:872` + DB `routing_decisions.signals` `queries.py:530-569`), guarded by `apps/api/tests/test_turn_allowlist.py`. The breadcrumb is the whole point — retrain on the brain's **original** intent, not the reroute fallback.
- Epic 2 (2.1/2.2/2.3) established the data-independence discipline (in-memory fixtures, no CSV/DB gating), the `uv run pytest` runner (needs sandbox-off locally), and RED-then-GREEN. Story 3.3 will consume Epic 2's `evaluate_check` + `required_calibrated_heads()` as the promotion gate — 3.1 need only produce a clean CSV for 3.2.
- `apps/api/paths.py` co-locates all per-user state under `PROMPT_OPTIMIZER_HOME` (recent DB-relocation work); the seed and live sinks share `.planning/data/`.

### Project Structure Notes

- New: `src/data/build_retraining_dataset.py`, `src/data/tests/test_build_retraining_dataset.py` (+ `src/data/tests/__init__.py` if absent).
- Output artifact: `data_processed/retraining_dataset.csv` (+ `_features.csv` if the two-step feature path is chosen).
- No `apps/` change, no `models/` change, no migration, no retrain (that's 3.2).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.1] user story + acceptance criteria
- [Source: apps/api/jsonl_log.py#119-134] `routing_decisions.jsonl` record schema
- [Source: apps/api/routes/turn.py#590-595] where `rerouted_from`/`rerouted_from_model` (original pick) are set
- [Source: apps/api/routes/feedback.py#143-178] `routing_feedback.jsonl` record schema (self-contained decision snapshot + sentiment)
- [Source: apps/api/paths.py#56-91] `PROMPT_OPTIMIZER_HOME` / `.planning/data/` path resolution (re-derive locally, do NOT import)
- [Source: apps/api/db/queries.py#530-569] DB `routing_decisions.signals` mirror (reference only; JSONL is the file-coupled source)
- [Source: apps/api/tests/test_turn_allowlist.py#109-116] the minimal JSONL line-reader pattern to reuse
- [Source: src/data/build_classifier_dataset.py#1-231] canonical builder shape (docstring, argparse, main()->int, dedup dict, CSV I/O)
- [Source: src/data/flatten_raw_jsons.py#249-280] malformed-input warn+skip + streaming CSV write pattern
- [Source: src/feature_extraction/Feature_extractor.py#101-110] `PromptFeatureExtractor.extract()` feature contract
- [Source: src/feature_extraction/build_features.py#48-67] feature-attach pattern (`pd.concat`, `_features.csv`)
- [Source: eval/tests/test_import_graph.py#49-64] D-18 import-graph guard (AD-8 no-apps constraint)
- [Source: _bmad-output/specs/spec-Prompt-Optimizer/SPEC.md#152] the 1,210-row synthetic seed reference

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m]

### Debug Log References

- **Deviation 1 — scaffold labels (Task 7): benchmark-join → self-contained deterministic.** The story specified deriving `up`/`down` from the benchmark best-model (`data_processed/classifier_training.csv`). All `data_processed/*.csv` are unpulled **git-LFS pointers** (134 bytes) — the benchmark ground-truth is not materialized locally. Rather than require an LFS pull, the scaffold synthesizes prompts + labels from a small deterministic template set (each turn has an "ideal" route; `up` when the brain's original pick matches, `down` when it deliberately doesn't). This is fully self-contained and matches the Epic's data-independence discipline. Same Option-E intent (pure assembler + isolated principled scaffold), different (available) label source.
- **Deviation 2 — scaffold default output dir (safety).** The story suggested defaulting the scaffold to the live `~/.prompt-optimizer/.planning/data/` sinks. Writing synthetic data there would clobber a user's real captured signal — so the default is a repo-local `data_processed/synthetic_seed/`, overridable via `--output-dir`. No footgun; the assembler still reads whichever path you point it at.
- End-to-end smoke: `seed_synthetic_feedback --count 60` → 66 feedback events → `build_retraining_dataset` → 60 rated turns (dedup superseded the 6 cleared events) with `up=36 down=18 cleared=6` and handcrafted feature columns attached. D-18 import-graph guard green.

### Completion Notes List

- `build_retraining_dataset.py` is a **pure feedback→CSV reader** (D2/Option E): one row per `message_id`, latest-timestamp-wins so `cleared` supersedes (AC #2); `original_*` from `signals.rerouted_from*` with dispatched-route fallback (AC #1); inline `PromptFeatureExtractor` features (D3, user-confirmed); empty/absent feedback → header-only CSV, exit 0 (AC #4).
- AD-8 honored (AC #3): re-derives `PROMPT_OPTIMIZER_HOME` locally, imports only stdlib + pandas + `PromptFeatureExtractor` (via the documented `sys.path` shim). No `apps.*`/`src.routing`/`eval`. D-18 guard (`eval/tests/test_import_graph.py`) stays green.
- `seed_synthetic_feedback.py` is a disposable dry-run scaffold (isolated from the assembler) producing a coherent decisions+feedback JSONL pair with a discriminative up/down/cleared mix + reroute breadcrumbs.
- Tests: 7 data-independent tests (5 assembler + 2 scaffold), all in-memory / `tmp_path` — no seed or `chat.db` dependency. `uv run pytest src/data eval/tests/test_import_graph.py` green. (The pre-existing `src/evaluation/tests/test_no_regression.py` LFS-data failures are unrelated and untouched.)

### File List

- `src/data/build_retraining_dataset.py` (new) — assembly stage (feedback JSONL → labeled features CSV)
- `src/data/seed_synthetic_feedback.py` (new) — disposable dry-run seed scaffold
- `src/data/tests/__init__.py` (new) — test package marker
- `src/data/tests/test_build_retraining_dataset.py` (new) — 5 assembler tests
- `src/data/tests/test_seed_synthetic_feedback.py` (new) — 2 scaffold tests

## Change Log

- 2026-07-10: Code review (3 adversarial layers) — Auditor PASS on all 4 ACs; feared silent feature-column drop verified a non-issue. 3 patches applied (parsed-datetime supersede fix, malformed-line resilience, dropped dead `--routing-decisions` flag) + 2 regression tests; 3 deferred (logged in deferred-work.md); 5 dismissed. 10 tests green. Status → done.
- 2026-07-10: Story 3.1 implemented — `src/data/build_retraining_dataset.py` assembles `routing_feedback.jsonl` into a labeled, feature-carrying retraining CSV (one row per rated turn, cleared-supersede, original-pick fallback, inline features, files-on-disk/AD-8, empty-feedback resilient). Added disposable `seed_synthetic_feedback.py` scaffold for the dry run (self-contained deterministic labels — deviation from benchmark-join because `data_processed/*.csv` are unpulled LFS pointers; scaffold defaults to repo-local output for safety). 7 data-independent tests; D-18 guard green. Status → review.
