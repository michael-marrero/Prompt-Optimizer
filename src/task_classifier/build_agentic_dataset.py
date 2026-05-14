"""
Build the agentic-intent training CSV from seeds + synthesized + mined negatives.

Output schema: text, label (agentic|conversational), source, dataset

Run from the repo root:

    uv run python -m src.task_classifier.build_agentic_dataset \\
        --seeds-input    data_processed/agentic_intent_seeds.csv \\
        --synthesized-input data_processed/agentic_intent_synthesized.csv \\
        --negatives-input data_processed/agentic_intent_negatives.csv \\
        --output         data_processed/agentic_intent_training.csv

Or just::

    uv run python -m src.task_classifier.build_agentic_dataset

to use the defaults (all four CSVs in data_processed/). On the first run, the
negatives CSV does not yet exist, so the script mines ~500 conversational rows
out of data_processed/classifier_training.csv and writes them to
data_processed/agentic_intent_negatives.csv before assembling the final
training CSV.

To validate an already-built training CSV (used by CI and by Plan 04 as a
pre-flight gate)::

    uv run python -m src.task_classifier.build_agentic_dataset --check

Returns exit code 0 if the output CSV is well-formed and balanced; non-zero
otherwise.

------------------------------------------------------------------------------
LLM expansion prompt template (Task 2, RESEARCH §Pattern 3 Step 2 + Open Question 3)
------------------------------------------------------------------------------

The committed data_processed/agentic_intent_synthesized.csv was produced by a
ONE-TIME OFFLINE LLM call (RESEARCH Assumption A3) using the following prompt
template. The template is recorded here verbatim so future maintainers can
re-run the expansion or audit the synthesis decisions:

    I am building a training dataset for an "agentic intent" binary classifier.
    Here are 30 hand-written examples of AGENTIC prompts (build/edit code, browse
    the web, multi-step actions). For each seed, generate 15 paraphrastic
    variations that preserve the agentic intent but vary in: verb diversity,
    prompt length (5 tokens to 200 tokens), phrasing style (terse vs. polite),
    and domain spread.

    Output ONLY a CSV with header `text,label,source,dataset` where
    label="agentic", source="synthesized", dataset="llm-expansion".

    Seed prompts:
    <paste data_processed/agentic_intent_seeds.csv here>

The expansion was performed by Claude Opus 4.7 via Claude Code on 2026-05-13,
working only against the committed seeds CSV. The full set of 477 paraphrases
is also embedded verbatim in scripts/expand_agentic_seeds.py so the CSV is
reproducible without any live LLM call.

------------------------------------------------------------------------------
Negatives source — Rule 4 architectural deviation
------------------------------------------------------------------------------

The original plan (CONTEXT D-06; PLAN.md line 21) called for mining ~500
non-agentic conversational rows out of data_processed/flat_records.csv (the
raw LLMRouterBench flattener output). On this developer's machine,
flat_records.csv is NOT available — it is not committed (the data_raw/ JSON
tree it derives from is also not present), so it cannot be regenerated in this
environment.

Instead, this script mines negatives out of data_processed/classifier_training.csv,
the per-question best-model aggregate that already exists on disk. That file
has the same two columns the miner needs (`dataset` and `origin_query`), so
the filter logic from RESEARCH §Pattern 3 Step 4 applies verbatim. This is a
Rule 4 source substitution and is documented in the SUMMARY for Plan 01-03.

If a future developer has flat_records.csv available, they can pass
``--negatives-source flat_records`` (or pipe their own pre-built negatives in
via ``--negatives-input``) to use the originally-planned source. The default
points at classifier_training.csv so the script Just Works on a fresh clone
that has only the committed CSVs.
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def _raise_csv_field_limit() -> None:
    """Lift csv's 128 KB per-field cap so we can read very long prompts.

    Mirrors src/data/build_classifier_dataset.py:36-48 — sys.maxsize can
    overflow the underlying C long on Windows, so we step the value down
    until the call succeeds.
    """
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


_raise_csv_field_limit()


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_PROCESSED_DIR = PROJECT_ROOT / "data_processed"
DEFAULT_SEEDS = DATA_PROCESSED_DIR / "agentic_intent_seeds.csv"
DEFAULT_SYNTHESIZED = DATA_PROCESSED_DIR / "agentic_intent_synthesized.csv"
DEFAULT_NEGATIVES = DATA_PROCESSED_DIR / "agentic_intent_negatives.csv"
DEFAULT_CLASSIFIER_TRAINING = DATA_PROCESSED_DIR / "classifier_training.csv"
DEFAULT_FLAT_RECORDS = DATA_PROCESSED_DIR / "flat_records.csv"
DEFAULT_OUTPUT = DATA_PROCESSED_DIR / "agentic_intent_training.csv"


# RESEARCH §Pattern 3 Step 4 (lines 540-541): drop any row whose `dataset` slug
# contains any of these substrings (lowercased) so tool-use and code-execution
# benchmarks never leak into the conversational class.
TOOL_USE_DATASET_SUBSTRINGS: tuple[str, ...] = (
    "tau2",
    "tau",
    "tool",
    "agent",
    "humaneval",
    "livecodebench",
    "mbpp",
    "swe-bench",
)


# Final output column contract — locked by PLAN.md `<interfaces>`.
OUTPUT_COLUMNS: list[str] = ["text", "label", "source", "dataset"]


def _setup_logging(verbosity: int) -> None:
    """Mirror src/data/build_classifier_dataset.py:104-114."""
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )


def _missing_input_error(path: Path, kind: str, hint: str) -> FileNotFoundError:
    """Multi-line FileNotFoundError per CLAUDE.md "Error Handling".

    `kind` is a short human label (e.g. "seeds CSV"); `hint` is a one-line
    remediation pointer.
    """
    return FileNotFoundError(
        f"\n{kind} not found at: {path}\n"
        f"  {hint}\n"
        f"  Re-check the --{kind.replace(' CSV', '-input')} flag if you passed one,\n"
        f"  or run the upstream generator that produces this file."
    )


def mine_negatives_from_classifier_training(
    classifier_training_path: Path,
    target_count: int,
    random_state: int = 42,
) -> pd.DataFrame:
    """Mine `target_count` non-agentic conversational rows out of
    data_processed/classifier_training.csv.

    Returns a DataFrame with the four output columns
    ``text, label, source, dataset`` where ``text`` is the row's
    ``origin_query``, ``label`` is the literal string ``"conversational"``,
    ``source`` is ``"llmbench"`` (LLMRouterBench's negatives), and ``dataset``
    is the original benchmark dataset slug.

    The mining filter is RESEARCH §Pattern 3 Step 4 verbatim:
      - drop datasets that contain any tool-use / code-execution substring
        in TOOL_USE_DATASET_SUBSTRINGS (case-insensitive on the dataset slug)
      - drop rows whose origin_query is empty / NaN
      - stratify by dataset so the negatives are not all math / MMLU
    """
    if not classifier_training_path.exists():
        raise _missing_input_error(
            classifier_training_path,
            "classifier-training CSV",
            "Expected at data_processed/classifier_training.csv. "
            "Build it via `python -m src.data.build_classifier_dataset` "
            "from the LLMRouterBench flattener output.",
        )

    logging.info("Loading classifier_training.csv from %s", classifier_training_path)
    df = pd.read_csv(classifier_training_path)
    logging.info("Loaded %d rows from classifier_training.csv", len(df))

    required = {"dataset", "origin_query"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"classifier_training.csv at {classifier_training_path} is missing "
            f"required columns: {sorted(missing)}. Found: {sorted(df.columns)}"
        )

    # Defensive coercion for negatives mining — mirrors CLAUDE.md's
    # ".fillna('').astype(str)" pattern for text columns.
    df["dataset"] = df["dataset"].fillna("").astype(str)
    df["origin_query"] = df["origin_query"].fillna("").astype(str)

    # 1. Drop empty origin_query rows.
    non_empty_mask = df["origin_query"].str.strip().ne("").to_numpy()
    df = df.loc[non_empty_mask].reset_index(drop=True)
    logging.info("After dropping empty origin_query: %d rows", len(df))

    # 2. Drop tool-use / code-execution datasets (substring match, lowercased).
    ds_lower = df["dataset"].str.lower()
    keep_mask = pd.Series(True, index=df.index)
    for substring in TOOL_USE_DATASET_SUBSTRINGS:
        keep_mask &= ~ds_lower.str.contains(substring, regex=False, na=False)
    df = df.loc[keep_mask.to_numpy()].reset_index(drop=True)
    logging.info(
        "After excluding tool-use datasets %s: %d rows remaining",
        list(TOOL_USE_DATASET_SUBSTRINGS),
        len(df),
    )

    if df.empty:
        raise ValueError(
            "No rows remain after filtering tool-use datasets — cannot mine "
            "negatives. Inspect classifier_training.csv's `dataset` column."
        )

    # 3. Stratified sample by `dataset` so the negatives don't collapse onto
    #    whichever benchmark happens to have the most rows in classifier_training.csv.
    rng = np.random.default_rng(random_state)
    per_dataset = max(1, target_count // df["dataset"].nunique())
    logging.info(
        "Stratifying by dataset: %d unique datasets, taking up to %d per group",
        df["dataset"].nunique(),
        per_dataset,
    )

    sampled_chunks: list[pd.DataFrame] = []
    for dataset_name, group in df.groupby("dataset", sort=False):
        n_take = min(per_dataset, len(group))
        if n_take <= 0:
            continue
        idx = rng.choice(group.index.to_numpy(), size=n_take, replace=False)
        sampled_chunks.append(group.loc[idx])

    stratified = pd.concat(sampled_chunks, ignore_index=True)
    logging.info("Stratified sample yielded %d rows", len(stratified))

    # 4. If we're short, top-up randomly from the remaining pool (still
    #    respecting the tool-use exclusion).
    if len(stratified) < target_count:
        shortfall = target_count - len(stratified)
        remaining = df.drop(stratified.index, errors="ignore")
        if len(remaining) >= shortfall:
            top_up_idx = rng.choice(
                remaining.index.to_numpy(), size=shortfall, replace=False
            )
            stratified = pd.concat(
                [stratified, remaining.loc[top_up_idx]], ignore_index=True
            )
            logging.info(
                "Topped up by %d random rows to reach target %d",
                shortfall,
                target_count,
            )

    # 5. If we're over target_count (e.g. small group count made per_dataset
    #    larger than necessary), randomly truncate.
    if len(stratified) > target_count:
        keep_idx = rng.choice(
            stratified.index.to_numpy(), size=target_count, replace=False
        )
        stratified = stratified.loc[keep_idx].reset_index(drop=True)
        logging.info("Truncated to target %d rows", target_count)

    negatives = pd.DataFrame(
        {
            "text": stratified["origin_query"].astype(str).to_numpy(),
            "label": "conversational",
            "source": "llmbench",
            "dataset": stratified["dataset"].astype(str).to_numpy(),
        }
    )

    logging.info(
        "Mined %d negatives across %d unique datasets",
        len(negatives),
        negatives["dataset"].nunique(),
    )
    return negatives


def _load_positives(path: Path, kind: str) -> pd.DataFrame:
    """Load a positives CSV (seeds or synthesized) and verify its schema."""
    if not path.exists():
        raise _missing_input_error(
            path,
            f"{kind} CSV",
            "Re-run Task 1 (seeds) or Task 2 (synthesized) of Plan 01-03 "
            "before invoking the dataset builder.",
        )

    df = pd.read_csv(path)
    missing = set(OUTPUT_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(
            f"{kind} CSV at {path} is missing required columns: {sorted(missing)}. "
            f"Found: {sorted(df.columns)}. Expected: {OUTPUT_COLUMNS}."
        )
    # Coerce all four columns to string per CLAUDE.md text-column convention.
    for col in OUTPUT_COLUMNS:
        df[col] = df[col].fillna("").astype(str)
    return df[OUTPUT_COLUMNS]


def _check_output_csv(output_path: Path) -> int:
    """Validate an already-built training CSV; return 0 on success, 1 on failure.

    Mirrors the `--check` contract in PLAN.md Task 3 (line 212).
    """
    if not output_path.exists():
        logging.error("--check: training CSV not found at %s", output_path)
        return 1

    try:
        df = pd.read_csv(output_path)
    except Exception as exc:  # pragma: no cover - exercised only by malformed CSV
        logging.error("--check: failed to read %s: %s", output_path, exc)
        return 1

    cols = set(df.columns)
    expected = set(OUTPUT_COLUMNS)
    if cols != expected:
        logging.error(
            "--check: column mismatch. Got %s; expected exactly %s.",
            sorted(cols),
            sorted(expected),
        )
        return 1

    if df["label"].isna().any():
        logging.error("--check: found NaN in label column.")
        return 1

    n = len(df)
    if n < 800:
        logging.error("--check: row count %d is below the 800-row floor.", n)
        return 1

    labels_present = set(df["label"].dropna().unique())
    if labels_present != {"agentic", "conversational"}:
        logging.error(
            "--check: label values must be exactly {'agentic', 'conversational'}; got %s",
            sorted(labels_present),
        )
        return 1

    n_ag = int((df["label"] == "agentic").sum())
    n_co = int((df["label"] == "conversational").sum())
    ag_ratio = n_ag / n
    if not (0.45 <= ag_ratio <= 0.55):
        logging.error(
            "--check: class balance out of bounds. agentic=%d (%.3f), "
            "conversational=%d. Required: 0.45 <= agentic/total <= 0.55.",
            n_ag,
            ag_ratio,
            n_co,
        )
        return 1

    logging.info(
        "--check: PASSED. rows=%d agentic=%d conversational=%d ag_ratio=%.3f",
        n,
        n_ag,
        n_co,
        ag_ratio,
    )
    return 0


def assemble_training_csv(
    seeds: pd.DataFrame,
    synthesized: pd.DataFrame,
    negatives: pd.DataFrame,
    *,
    random_seed: int,
) -> pd.DataFrame:
    """Concatenate the three sources, shuffle deterministically, drop dups."""
    combined = pd.concat([seeds, synthesized, negatives], ignore_index=True)
    logging.info(
        "Concatenated: seeds=%d synthesized=%d negatives=%d total=%d",
        len(seeds),
        len(synthesized),
        len(negatives),
        len(combined),
    )

    # Drop exact-duplicate (text, label) pairs. Two rows can share text if
    # they got into different sources (extremely rare for the seeds vs.
    # synthesized cases but cheap to guard against).
    n_before = len(combined)
    combined = combined.drop_duplicates(subset=["text", "label"]).reset_index(drop=True)
    n_dropped = n_before - len(combined)
    if n_dropped:
        logging.info("Dropped %d duplicate (text,label) rows", n_dropped)

    shuffled = combined.sample(
        frac=1.0, random_state=random_seed
    ).reset_index(drop=True)

    # Balance sanity log (not a hard failure here — --check enforces).
    n_ag = int((shuffled["label"] == "agentic").sum())
    n_co = int((shuffled["label"] == "conversational").sum())
    if shuffled.empty:
        ag_ratio = 0.0
    else:
        ag_ratio = n_ag / len(shuffled)
    if not (0.45 <= ag_ratio <= 0.55):
        logging.warning(
            "Class balance is %.3f agentic (n_ag=%d, n_co=%d). "
            "Outside [0.45, 0.55]; --check will fail on this CSV.",
            ag_ratio,
            n_ag,
            n_co,
        )
    else:
        logging.info(
            "Balance OK: agentic=%d conversational=%d ag_ratio=%.3f",
            n_ag,
            n_co,
            ag_ratio,
        )

    return shuffled


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--seeds-input",
        type=Path,
        default=DEFAULT_SEEDS,
        help=f"Path of the hand-written seeds CSV (default: {DEFAULT_SEEDS}).",
    )
    parser.add_argument(
        "--synthesized-input",
        type=Path,
        default=DEFAULT_SYNTHESIZED,
        help=(
            "Path of the LLM-synthesized positives CSV "
            f"(default: {DEFAULT_SYNTHESIZED})."
        ),
    )
    parser.add_argument(
        "--negatives-input",
        type=Path,
        default=DEFAULT_NEGATIVES,
        help=(
            "Path of the mined negatives CSV. If this file does not yet exist, "
            "it will be mined from --classifier-training-input (or --flat-records-input "
            f"if available) and persisted to this path (default: {DEFAULT_NEGATIVES})."
        ),
    )
    parser.add_argument(
        "--classifier-training-input",
        type=Path,
        default=DEFAULT_CLASSIFIER_TRAINING,
        help=(
            "Path of data_processed/classifier_training.csv (the negatives source). "
            f"Default: {DEFAULT_CLASSIFIER_TRAINING}."
        ),
    )
    parser.add_argument(
        "--flat-records-input",
        type=Path,
        default=DEFAULT_FLAT_RECORDS,
        help=(
            "Path of data_processed/flat_records.csv (originally-planned negatives "
            f"source; ignored unless it exists). Default: {DEFAULT_FLAT_RECORDS}."
        ),
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Path to write the assembled training CSV (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--negatives-target-count",
        type=int,
        default=500,
        help="Number of conversational negatives to mine (default: 500).",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=42,
        help="Deterministic seed for sampling and shuffling (default: 42).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Validate an already-built --output CSV (balance, columns, no NaN labels). "
            "Exit 0 on success, non-zero on failure. Used by CI."
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=1,
        help="-v info (default), -vv debug.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _setup_logging(args.verbose)

    if args.check:
        return _check_output_csv(args.output)

    # 1. Load positives.
    seeds = _load_positives(args.seeds_input, "seeds")
    logging.info("Loaded %d seed rows from %s", len(seeds), args.seeds_input)

    synthesized = _load_positives(args.synthesized_input, "synthesized")
    logging.info(
        "Loaded %d synthesized rows from %s",
        len(synthesized),
        args.synthesized_input,
    )

    # 2. Resolve negatives — load if cached, else mine.
    if args.negatives_input.exists():
        negatives = pd.read_csv(args.negatives_input)
        missing = set(OUTPUT_COLUMNS) - set(negatives.columns)
        if missing:
            raise ValueError(
                f"Cached negatives at {args.negatives_input} is missing "
                f"required columns: {sorted(missing)}."
            )
        for col in OUTPUT_COLUMNS:
            negatives[col] = negatives[col].fillna("").astype(str)
        negatives = negatives[OUTPUT_COLUMNS]
        logging.info(
            "Loaded %d cached negatives from %s",
            len(negatives),
            args.negatives_input,
        )
    else:
        # Prefer flat_records.csv if a future developer regenerates it; fall back
        # to classifier_training.csv (the Rule 4 source substitution).
        if args.flat_records_input.exists():
            logging.info(
                "flat_records.csv found at %s — mining negatives from the "
                "originally-planned source.",
                args.flat_records_input,
            )
            negatives = mine_negatives_from_classifier_training(
                args.flat_records_input,
                target_count=args.negatives_target_count,
                random_state=args.random_seed,
            )
        else:
            logging.info(
                "flat_records.csv not present at %s — applying Rule 4 source "
                "substitution and mining from %s instead.",
                args.flat_records_input,
                args.classifier_training_input,
            )
            negatives = mine_negatives_from_classifier_training(
                args.classifier_training_input,
                target_count=args.negatives_target_count,
                random_state=args.random_seed,
            )

        args.negatives_input.parent.mkdir(parents=True, exist_ok=True)
        negatives.to_csv(args.negatives_input, index=False)
        print(f"Saved {len(negatives)} mined negatives to: {args.negatives_input}")

    # 3. Assemble + shuffle + write final CSV.
    final = assemble_training_csv(
        seeds, synthesized, negatives, random_seed=args.random_seed
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    final.to_csv(args.output, index=False)
    print(f"Saved {len(final)} training rows to: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
