"""
STEP 2 - Build the classifier training CSV from the flattened records CSV.

For every question (grouped by ``question_id``), pick the *best model* using:
    1. highest ``score``  (None / NaN treated as -inf)
    2. tie-break: lowest ``cost`` (None / NaN treated as +inf)
    3. final tie-break: alphabetical model_name (deterministic ordering)

Output schema:
    question_id, dataset, split, origin_query, prompt,
    best_model, best_score, best_cost,
    n_models_compared, models_evaluated

The script streams the input CSV row by row, keeping at most one
candidate per question_id in memory, so it scales to millions of rows.

Run from the repo root:

    python -m src.data.build_classifier_dataset \
        --input  data_processed/flat_records.csv \
        --output data_processed/classifier_training.csv
"""

from __future__ import annotations

import argparse
import csv
import logging
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


def _raise_csv_field_limit() -> None:
    """Lift csv's 128 KB per-field cap so we can read very long prompts.

    sys.maxsize can overflow the underlying C long on Windows, so we step
    the value down until the call succeeds.
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
DEFAULT_INPUT = PROJECT_ROOT / "data_processed" / "flat_records.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "data_processed" / "classifier_training.csv"


OUTPUT_FIELDS: list[str] = [
    "question_id",
    "dataset",
    "split",
    "origin_query",
    "prompt",
    "best_model",
    "best_score",
    "best_cost",
    "n_models_compared",
    "models_evaluated",
]


@dataclass
class BestCandidate:
    """Running best-model record for a single question_id."""

    dataset: str = ""
    split: str = ""
    origin_query: str = ""
    prompt: str = ""
    best_model: str = ""
    best_score: float = -math.inf
    best_cost: float = math.inf
    models_seen: set[str] = field(default_factory=set)

    def consider(self, model: str, score: float, cost: float) -> None:
        self.models_seen.add(model)
        if (score, -cost, model) > (self.best_score, -self.best_cost, self.best_model):
            self.best_score = score
            self.best_cost = cost
            self.best_model = model


def _to_float(value: str | None, *, default: float) -> float:
    """Parse a CSV cell to float, returning ``default`` for blanks / unparseable."""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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


def stream_rows(path: Path) -> Iterable[dict[str, str]]:
    """Yield one dict per row from the flattened CSV."""
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        yield from reader


def aggregate_best(rows: Iterable[dict[str, str]], log_every: int = 100_000) -> dict[str, BestCandidate]:
    """Stream over rows and keep only the best candidate per question_id."""
    best: dict[str, BestCandidate] = {}
    n_rows = 0

    for row in rows:
        n_rows += 1
        qid = row.get("question_id") or ""
        if not qid:
            continue

        model = row.get("model_name") or row.get("model_dir") or "<unknown>"
        score = _to_float(row.get("score"), default=-math.inf)
        cost = _to_float(row.get("cost"), default=math.inf)

        cand = best.get(qid)
        if cand is None:
            cand = BestCandidate(
                dataset=row.get("dataset_name") or "",
                split=row.get("split") or "",
                origin_query=row.get("origin_query") or "",
                prompt=row.get("prompt") or "",
            )
            best[qid] = cand

        cand.consider(model=model, score=score, cost=cost)

        if n_rows % log_every == 0:
            logging.info("rows_processed=%d unique_questions=%d", n_rows, len(best))

    logging.info("Final: rows_processed=%d unique_questions=%d", n_rows, len(best))
    return best


def write_classifier_csv(best: dict[str, BestCandidate], output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    n_written = 0
    with output.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()

        for qid in sorted(best):
            cand = best[qid]

            if cand.best_model == "" or not math.isfinite(cand.best_score):
                logging.debug("Skipping %s - no usable score from any model", qid)
                continue

            writer.writerow(
                {
                    "question_id": qid,
                    "dataset": cand.dataset,
                    "split": cand.split,
                    "origin_query": cand.origin_query,
                    "prompt": cand.prompt,
                    "best_model": cand.best_model,
                    "best_score": cand.best_score,
                    "best_cost": cand.best_cost if math.isfinite(cand.best_cost) else "",
                    "n_models_compared": len(cand.models_seen),
                    "models_evaluated": ";".join(sorted(cand.models_seen)),
                }
            )
            n_written += 1

    return n_written


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Path of the flattened records CSV (default: {DEFAULT_INPUT}).",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Path to write the classifier training CSV (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=100_000,
        help="Emit a progress line every N rows processed (default: 100000).",
    )
    parser.add_argument("-v", "--verbose", action="count", default=1, help="-v info, -vv debug.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _setup_logging(args.verbose)

    if not args.input.exists():
        logging.error("Input CSV not found: %s", args.input)
        return 2

    logging.info("Aggregating best models from %s", args.input)
    best = aggregate_best(stream_rows(args.input), log_every=args.log_every)
    n_written = write_classifier_csv(best, args.output)
    logging.info("Wrote %d question rows to %s", n_written, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
