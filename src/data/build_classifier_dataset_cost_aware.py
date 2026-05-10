"""
STEP 2b — Build a cost-aware classifier/router training CSV from the flattened records CSV.

For every question grouped by question_id, this script labels:

1. best_model:
   The absolute best model by highest score, then lowest cost.

2. best_value_model:
   Among models whose score is within a relative band of the best score,
   pick the cheapest model.

   Example:
   If score_rel_tolerance = 0.10, then any model with:
       score >= best_score - abs(best_score) * 0.10
   is considered close enough.

Optional controls:
- --min-acceptable-score:
  Prevents very weak models from being considered value-eligible.

- --require-cheaper-than-best:
  Only picks a value model if it is cheaper than the absolute best model.
  If no cheaper eligible model exists, the row is skipped.

Output includes:
    question_id, dataset, split, origin_query, prompt,
    best_value_model, best_value_score, best_value_cost,
    best_model, best_score, best_cost,
    cost_saved_vs_best, score_drop_vs_best, value_model_changed,
    score_rel_tolerance, min_acceptable_score,
    n_models_compared, n_models_in_value_band,
    models_evaluated

Run from the repo root:

    python -m src.data.build_classifier_dataset_cost_aware ^
        --input data_processed/flat_records.csv ^
        --output data_processed/classifier_training_cost_aware.csv ^
        --score-rel-tolerance 0.10
"""

from __future__ import annotations

import argparse
import csv
import logging
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


# ------------------------------------------------------------
# CSV safety
# ------------------------------------------------------------

def _raise_csv_field_limit() -> None:
    """
    Raise CSV field size limit so huge prompts/records do not crash reading.
    """

    limit = sys.maxsize

    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


_raise_csv_field_limit()


# ------------------------------------------------------------
# Paths
# ------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_INPUT = PROJECT_ROOT / "data_processed" / "flat_records.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "data_processed" / "classifier_training_cost_aware.csv"


# ------------------------------------------------------------
# Output schema
# ------------------------------------------------------------

OUTPUT_FIELDS: list[str] = [
    "question_id",
    "dataset",
    "split",
    "origin_query",
    "prompt",

    "best_value_model",
    "best_value_score",
    "best_value_cost",

    "best_model",
    "best_score",
    "best_cost",

    "cost_saved_vs_best",
    "score_drop_vs_best",
    "value_model_changed",

    "score_rel_tolerance",
    "min_acceptable_score",

    "n_models_compared",
    "n_models_in_value_band",
    "models_evaluated",
]


# ------------------------------------------------------------
# Data containers
# ------------------------------------------------------------

@dataclass
class QuestionBucket:
    """
    All evaluated model rows for one question_id.
    """

    dataset: str = ""
    split: str = ""
    origin_query: str = ""
    prompt: str = ""
    observations: list[tuple[str, float, float]] = field(default_factory=list)

    def add(self, model: str, score: float, cost: float) -> None:
        self.observations.append((model, score, cost))


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def _to_float(value: str | None, *, default: float) -> float:
    """
    Safely convert CSV string values into floats.
    """

    if value is None or value == "":
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _fmt_float(value: float) -> str | float:
    """
    Write finite floats normally and missing/infinite values as empty strings.
    """

    if math.isfinite(value):
        return value

    return ""


def _dedupe_per_model(
    observations: list[tuple[str, float, float]]
) -> list[tuple[str, float, float]]:
    """
    Keep one row per model.

    If the same model appears more than once for a question:
    - keep the highest score
    - if tied, keep the lowest cost
    """

    best_by_model: dict[str, tuple[float, float]] = {}

    for model, score, cost in observations:
        previous = best_by_model.get(model)

        if previous is None:
            best_by_model[model] = (score, cost)
            continue

        previous_score, previous_cost = previous

        current_key = (
            score,
            -cost if math.isfinite(cost) else float("-inf"),
        )

        previous_key = (
            previous_score,
            -previous_cost if math.isfinite(previous_cost) else float("-inf"),
        )

        if current_key > previous_key:
            best_by_model[model] = (score, cost)

    return [
        (model, score, cost)
        for model, (score, cost) in best_by_model.items()
    ]


def _value_band_threshold(best_score: float, rel_tol: float) -> float:
    """
    Minimum score still considered close enough to the best score.
    """

    return best_score - abs(best_score) * rel_tol


# ------------------------------------------------------------
# Model selection logic
# ------------------------------------------------------------

def pick_best_absolute(
    rows: list[tuple[str, float, float]]
) -> tuple[str, float, float] | None:
    """
    Pick absolute best model:
    - highest score
    - then lowest cost
    - then alphabetical model name
    """

    best: tuple[str, float, float] | None = None

    for model, score, cost in rows:
        if not math.isfinite(score):
            continue

        if best is None:
            best = (model, score, cost)
            continue

        best_model, best_score, best_cost = best

        current_key = (
            score,
            -cost if math.isfinite(cost) else float("-inf"),
            model,
        )

        best_key = (
            best_score,
            -best_cost if math.isfinite(best_cost) else float("-inf"),
            best_model,
        )

        if current_key > best_key:
            best = (model, score, cost)

    return best


def pick_best_value(
    rows: list[tuple[str, float, float]],
    *,
    best_score: float,
    best_cost: float,
    rel_tol: float,
    min_acceptable_score: float,
    require_cheaper_than_best: bool,
) -> tuple[str, float, float] | None:
    """
    Pick cost-aware value model.

    Eligible models must:
    - have finite score
    - be within the score tolerance band
    - be at least min_acceptable_score
    - optionally be cheaper than the absolute best model

    Selection:
    - cheapest cost
    - then higher score
    - then alphabetical model name
    """

    score_threshold = max(
        _value_band_threshold(best_score, rel_tol),
        min_acceptable_score,
    )

    eligible = [
        (model, score, cost)
        for model, score, cost in rows
        if math.isfinite(score) and score >= score_threshold
    ]

    if require_cheaper_than_best and math.isfinite(best_cost):
        eligible = [
            (model, score, cost)
            for model, score, cost in eligible
            if math.isfinite(cost) and cost < best_cost
        ]

    if not eligible:
        return None

    def sort_key(item: tuple[str, float, float]) -> tuple[float, float, str]:
        model, score, cost = item
        cost_key = cost if math.isfinite(cost) else math.inf

        # Cheapest first, then highest score, then alphabetical model.
        return (cost_key, -score, model)

    return min(eligible, key=sort_key)


# ------------------------------------------------------------
# Logging
# ------------------------------------------------------------

def _setup_logging(verbosity: int) -> None:
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


# ------------------------------------------------------------
# CSV reading and aggregation
# ------------------------------------------------------------

def stream_rows(path: Path) -> Iterable[dict[str, str]]:
    """
    Stream rows from flat_records.csv.
    """

    with path.open("r", encoding="utf-8", newline="") as file_handle:
        reader = csv.DictReader(file_handle)

        for row in reader:
            yield row


def aggregate_buckets(
    rows: Iterable[dict[str, str]],
    log_every: int = 100_000,
) -> dict[str, QuestionBucket]:
    """
    Group flattened model-result rows by question_id.
    """

    buckets: dict[str, QuestionBucket] = {}
    n_rows = 0

    for row in rows:
        n_rows += 1

        question_id = row.get("question_id") or ""

        if not question_id:
            continue

        model = row.get("model_name") or row.get("model_dir") or "<unknown>"
        score = _to_float(row.get("score"), default=-math.inf)
        cost = _to_float(row.get("cost"), default=math.inf)

        bucket = buckets.get(question_id)

        if bucket is None:
            bucket = QuestionBucket(
                dataset=row.get("dataset_name") or row.get("dataset") or "",
                split=row.get("split") or "",
                origin_query=row.get("origin_query") or "",
                prompt=row.get("prompt") or "",
            )

            buckets[question_id] = bucket

        bucket.add(
            model=model,
            score=score,
            cost=cost,
        )

        if n_rows % log_every == 0:
            logging.info(
                "rows_processed=%d unique_questions=%d",
                n_rows,
                len(buckets),
            )

    logging.info(
        "Final: rows_processed=%d unique_questions=%d",
        n_rows,
        len(buckets),
    )

    return buckets


# ------------------------------------------------------------
# CSV writing
# ------------------------------------------------------------

def write_cost_aware_csv(
    buckets: dict[str, QuestionBucket],
    output: Path,
    *,
    rel_tol: float,
    min_acceptable_score: float,
    require_cheaper_than_best: bool,
) -> int:
    """
    Write cost-aware classifier/router dataset.
    """

    output.parent.mkdir(parents=True, exist_ok=True)

    n_written = 0
    n_skipped_no_best = 0
    n_skipped_no_value = 0
    n_changed = 0
    n_saved_money = 0

    total_cost_saved = 0.0
    total_score_drop = 0.0

    with output.open("w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(
            file_handle,
            fieldnames=OUTPUT_FIELDS,
            extrasaction="ignore",
        )

        writer.writeheader()

        for question_id in sorted(buckets):
            bucket = buckets[question_id]
            rows = _dedupe_per_model(bucket.observations)
            models_seen = sorted({model for model, _, _ in rows})

            absolute_pick = pick_best_absolute(rows)

            if absolute_pick is None:
                n_skipped_no_best += 1
                logging.debug(
                    "Skipping %s because no finite score exists.",
                    question_id,
                )
                continue

            best_model, best_score, best_cost = absolute_pick

            value_pick = pick_best_value(
                rows,
                best_score=best_score,
                best_cost=best_cost,
                rel_tol=rel_tol,
                min_acceptable_score=min_acceptable_score,
                require_cheaper_than_best=require_cheaper_than_best,
            )

            if value_pick is None:
                n_skipped_no_value += 1
                logging.debug(
                    "Skipping %s because no eligible value model exists.",
                    question_id,
                )
                continue

            value_model, value_score, value_cost = value_pick

            score_threshold = max(
                _value_band_threshold(best_score, rel_tol),
                min_acceptable_score,
            )

            n_models_in_value_band = sum(
                1
                for _model, score, _cost in rows
                if math.isfinite(score) and score >= score_threshold
            )

            cost_saved_vs_best = ""
            score_drop_vs_best = best_score - value_score
            value_model_changed = value_model != best_model

            if math.isfinite(best_cost) and math.isfinite(value_cost):
                cost_saved_vs_best = best_cost - value_cost

                if cost_saved_vs_best > 0:
                    n_saved_money += 1
                    total_cost_saved += cost_saved_vs_best

            if math.isfinite(score_drop_vs_best):
                total_score_drop += score_drop_vs_best

            if value_model_changed:
                n_changed += 1

            writer.writerow(
                {
                    "question_id": question_id,
                    "dataset": bucket.dataset,
                    "split": bucket.split,
                    "origin_query": bucket.origin_query,
                    "prompt": bucket.prompt,

                    "best_value_model": value_model,
                    "best_value_score": value_score,
                    "best_value_cost": _fmt_float(value_cost),

                    "best_model": best_model,
                    "best_score": best_score,
                    "best_cost": _fmt_float(best_cost),

                    "cost_saved_vs_best": cost_saved_vs_best,
                    "score_drop_vs_best": score_drop_vs_best,
                    "value_model_changed": value_model_changed,

                    "score_rel_tolerance": rel_tol,
                    "min_acceptable_score": min_acceptable_score,

                    "n_models_compared": len(models_seen),
                    "n_models_in_value_band": n_models_in_value_band,
                    "models_evaluated": ";".join(models_seen),
                }
            )

            n_written += 1

    logging.info("Rows written: %d", n_written)
    logging.info("Skipped no absolute best: %d", n_skipped_no_best)
    logging.info("Skipped no value model: %d", n_skipped_no_value)
    logging.info("Value model changed vs absolute best: %d", n_changed)
    logging.info("Rows with positive cost savings: %d", n_saved_money)

    if n_written > 0:
        logging.info(
            "Average score drop vs best: %.8f",
            total_score_drop / n_written,
        )

    if n_saved_money > 0:
        logging.info(
            "Average cost saved on rows with savings: %.8f",
            total_cost_saved / n_saved_money,
        )

    return n_written


# ------------------------------------------------------------
# Args
# ------------------------------------------------------------

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
        help=f"Path of the flattened records CSV. Default: {DEFAULT_INPUT}",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Path to write the cost-aware CSV. Default: {DEFAULT_OUTPUT}",
    )

    parser.add_argument(
        "--score-rel-tolerance",
        type=float,
        default=0.10,
        metavar="T",
        help="Relative score band vs best. Example: 0.10 = within 10%% of best score.",
    )

    parser.add_argument(
        "--min-acceptable-score",
        type=float,
        default=0.0,
        help="Minimum score required for value eligibility. Default: 0.0.",
    )

    parser.add_argument(
        "--require-cheaper-than-best",
        action="store_true",
        help="Only choose value models that are cheaper than the absolute best model.",
    )

    parser.add_argument(
        "--log-every",
        type=int,
        default=100_000,
        help="Emit a progress line every N rows processed. Default: 100000.",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=1,
        help="-v info, -vv debug.",
    )

    return parser.parse_args(argv)


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    _setup_logging(args.verbose)

    if not (0.0 < args.score_rel_tolerance < 1.0):
        logging.error("--score-rel-tolerance must be between 0 and 1 exclusive.")
        return 2

    if args.min_acceptable_score < 0:
        logging.error("--min-acceptable-score must be >= 0.")
        return 2

    if not args.input.exists():
        logging.error("Input CSV not found: %s", args.input)
        return 2

    logging.info("Building cost-aware labels")
    logging.info("Input: %s", args.input)
    logging.info("Output: %s", args.output)
    logging.info("Score relative tolerance: %s", args.score_rel_tolerance)
    logging.info("Minimum acceptable score: %s", args.min_acceptable_score)
    logging.info("Require cheaper than best: %s", args.require_cheaper_than_best)

    buckets = aggregate_buckets(
        stream_rows(args.input),
        log_every=args.log_every,
    )

    n_written = write_cost_aware_csv(
        buckets,
        args.output,
        rel_tol=args.score_rel_tolerance,
        min_acceptable_score=args.min_acceptable_score,
        require_cheaper_than_best=args.require_cheaper_than_best,
    )

    logging.info("Wrote %d question rows to %s", n_written, args.output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
