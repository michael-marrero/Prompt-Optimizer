"""
Weak labeler: map an LLMRouterBench dataset slug to a broad question type.

Returns one of: coding, writing, medical, emotion, agentic, math, reasoning,
factual, knowledge, data, general, or "unknown" if no keyword group fires
(D-09 OOD sentinel class — trained on rows the keyword groups cannot place,
used by the Plan 05 calibrated task-type classifier as the literal `unknown`
class in its label encoder).

Run from the repo root:

    python -m src.task_classifier.build_question_type [--dry-run] [--input PATH] [--output PATH]

`--dry-run` prints the distinct dataset slugs that fall through to "unknown"
without writing the output CSV; intended for the Pitfall 2 spot-audit that
ensures the unknown bucket is not absorbing in-distribution datasets that just
didn't match a keyword group.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "data_processed" / "classifier_training_features.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "data_processed" / "classifier_training_with_types.csv"

# Legacy constants kept for backwards-compatibility with any script that imports
# them by name. New code should prefer DEFAULT_INPUT / DEFAULT_OUTPUT above.
INPUT_CSV = str(DEFAULT_INPUT)
OUTPUT_CSV = str(DEFAULT_OUTPUT)


def map_dataset_to_question_type(dataset: str) -> str:
    """
    Convert a benchmark dataset name into a broad question type.

    This is weak labeling, not perfect labeling. Returns one of the canonical
    task-type bucket strings, or the literal "unknown" sentinel (D-09) when
    no keyword group fires — used as the OOD class for the task-type classifier.
    """

    dataset = str(dataset).lower().strip()

    coding_datasets = [
        "humaneval",
        "livecodebench",
        "mbpp",
        "apps",
        "code",
        "arenahard_coding",
        "swe-bench",
        "swebench",
    ]

    math_datasets = [
        "aime",
        "gsm8k",
        "math",
        "minerva",
        "olympiad",
    ]

    reasoning_datasets = [
        "bbh",
        "bigbench",
        "arc",
        "hellaswag",
        "winogrande",
        "boolq",
        "commonsense",
        "korbench",
        "kandk",
    ]

    knowledge_datasets = [
        "mmlu",
        "mmlu_pro",
        "gpqa",
        "triviaqa",
        "natural_questions",
        "nq",
        "hle",
    ]

    factual_datasets = [
        "simpleqa",
    ]

    writing_datasets = [
        "arenahard_creative_writing",
        "creative_writing",
        "writing",
    ]

    medical_datasets = [
        "medqa",
        "medical",
        "medicine",
    ]

    emotion_datasets = [
        "emorynlp",
        "meld",
        "emotion",
        "sentiment",
        "dialogue_emotion",
    ]

    agentic_datasets = [
        "tau2",
        "tau",
        "tool",
        "agent",
    ]

    data_datasets = [
        "tabular",
        "csv",
        "sql",
        "data",
        "database",
    ]

    general_datasets = [
        "arenahard",
    ]

    # More specific classes should come first.
    # Example: "arenahard_coding" contains "code"/"coding",
    # and should become coding before "arenahard" becomes general.

    for name in coding_datasets:
        if name in dataset:
            return "coding"

    for name in writing_datasets:
        if name in dataset:
            return "writing"

    for name in medical_datasets:
        if name in dataset:
            return "medical"

    for name in emotion_datasets:
        if name in dataset:
            return "emotion"

    for name in agentic_datasets:
        if name in dataset:
            return "agentic"

    for name in math_datasets:
        if name in dataset:
            return "math"

    for name in reasoning_datasets:
        if name in dataset:
            return "reasoning"

    for name in factual_datasets:
        if name in dataset:
            return "factual"

    for name in knowledge_datasets:
        if name in dataset:
            return "knowledge"

    for name in data_datasets:
        if name in dataset:
            return "data"

    for name in general_datasets:
        if name == dataset:
            return "general"

    # No keyword group fired — this is the D-09 OOD sentinel class.
    # Distinguished from "general" so the calibrated task-type classifier
    # (Plan 05) can learn the unknown bucket as a real class rather than
    # absorbing it into the general bucket and poisoning the OOD signal.
    return "unknown"


def _print_dry_run_report(df: pd.DataFrame, question_types: pd.Series) -> None:
    """
    Print the Pitfall 2 spot-audit: which distinct dataset slugs now map to
    the literal "unknown" sentinel? Reviewer must visually confirm the slugs
    are genuine OOD (foreign-language slugs, typo'd slugs, novel benchmark
    families) and NOT in-distribution datasets that just didn't match a
    keyword regex.
    """

    unknown_mask = question_types == "unknown"
    unknown_datasets = df.loc[unknown_mask, "dataset"].dropna().unique().tolist()

    print("\n--dry-run: Pitfall 2 spot-audit")
    print("--------------------------------")
    print(f"Total rows assigned 'unknown': {int(unknown_mask.sum())} of {len(df)}")
    if unknown_mask.sum() > 0:
        pct = unknown_mask.sum() / len(df) * 100.0
        print(f"  ({pct:.2f}% of training data — Pitfall 2 cap is 15%)")

    if not unknown_datasets:
        print("No distinct dataset slugs fell through to 'unknown'.")
        return

    print("\nDistinct dataset slugs mapping to 'unknown':")
    for name in sorted(unknown_datasets):
        n = int((df["dataset"] == name).sum())
        print(f"  - {name}  ({n} rows)")
    print(
        "\nReview the slugs above: any in-distribution dataset that landed here "
        "should get its keyword group expanded BEFORE regenerating the CSV "
        "(per RESEARCH §Pitfall 2 lines 916-926)."
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Path of the input CSV (default: {DEFAULT_INPUT}).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Path to write the output CSV (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Compute the mapping and print the Pitfall 2 spot-audit (which "
            "dataset slugs landed in 'unknown') but do NOT write the output CSV."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    df = pd.read_csv(args.input)

    if "dataset" not in df.columns:
        raise ValueError("CSV must contain a 'dataset' column.")

    question_types = df["dataset"].apply(map_dataset_to_question_type)

    print("Question type counts:")
    print(question_types.value_counts())

    print("\nDataset to question type mapping:")
    dataset_mapping = (
        pd.DataFrame({"dataset": df["dataset"], "question_type": question_types})
        .drop_duplicates()
        .sort_values(by=["question_type", "dataset"])
    )

    for _, row in dataset_mapping.iterrows():
        print(f"- {row['dataset']} -> {row['question_type']}")

    general_datasets = (
        df[question_types == "general"]["dataset"]
        .dropna()
        .unique()
    )

    print("\nDatasets mapped to general:")
    if len(general_datasets) == 0:
        print("None")
    else:
        for dataset in general_datasets:
            print(f"- {dataset}")

    if args.dry_run:
        _print_dry_run_report(df, question_types)
        print("\n--dry-run: skipping CSV write.")
        return 0

    df["question_type"] = question_types
    df.to_csv(args.output, index=False)

    print(f"\nSaved labeled CSV to: {args.output}")
    print(f"Total rows: {len(df)}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())