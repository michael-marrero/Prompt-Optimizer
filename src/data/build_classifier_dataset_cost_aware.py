"""
STEP 2b — Build a *cost-aware* classifier training CSV from the flattened records CSV.

For every question (grouped by ``question_id``), label ``best_value_model``:

    Among models whose ``score`` is within a relative band of the best score
    (default: within 10%, i.e. score ≥ best_score × (1 − tolerance) when
    best_score > 0; in general: score ≥ best_score − |best_score| × tolerance),
    pick the *cheapest* model (lowest ``cost``; missing cost = +inf).

    Tie-breaks for the value pick: lower cost, then alphabetical ``model_name``.

The absolute best model (highest score, then lowest cost) is also written as
``best_model`` / ``best_score`` / ``best_cost`` for comparison with experiment A.

Output schema:
    question_id, dataset, split, origin_query, prompt,
    best_value_model, best_value_score, best_value_cost,
    best_model, best_score, best_cost,
    score_rel_tolerance, n_models_compared, n_models_in_value_band,
    models_evaluated

Run from the repo root:

    python -m src.data.build_classifier_dataset_cost_aware \\
        --input  data_processed/flat_records.csv \\
        --output data_processed/classifier_training_cost_aware.csv \\
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


def _raise_csv_field_limit() -> None:
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
DEFAULT_OUTPUT = PROJECT_ROOT / "data_processed" / "classifier_training_cost_aware.csv"


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
    "score_rel_tolerance",
    "n_models_compared",
    "n_models_in_value_band",
    "models_evaluated",
]


@dataclass
class QuestionBucket:
    """All evaluated (model, score, cost) rows for one question_id."""

    dataset: str = ""
    split: str = ""
    origin_query: str = ""
    prompt: str = ""
    observations: list[tuple[str, float, float]] = field(default_factory=list)

    def add(self, model: str, score: float, cost: float) -> None:
        self.observations.append((model, score, cost))


def _to_float(value: str | None, *, default: float) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _dedupe_per_model(observations: list[tuple[str, float, float]]) -> list[tuple[str, float, float]]:
    """Keep one row per model: best score, then lowest cost (same ordering as build_classifier_dataset)."""
    best_by_model: dict[str, tuple[float, float]] = {}
    for model, score, cost in observations:
        prev = best_by_model.get(model)
        if prev is None or (score, -cost, model) > (prev[0], -prev[1], model):
            best_by_model[model] = (score, cost)
    return [(m, s, c) for m, (s, c) in best_by_model.items()]


def _value_band_threshold(best_score: float, rel_tol: float) -> float:
    """Minimum score still considered 'good enough' when higher is better."""
    return best_score - abs(best_score) * rel_tol


def pick_best_absolute(rows: list[tuple[str, float, float]]) -> tuple[str, float, float] | None:
    best: tuple[str, float, float] | None = None
    for model, score, cost in rows:
        if not math.isfinite(score):
            continue
        if best is None or (score, -cost if math.isfinite(cost) else float("-inf"), model) > (
            best[1],
            -best[2] if math.isfinite(best[2]) else float("-inf"),
            best[0],
        ):
            best = (model, score, cost)
    return best


def pick_best_value(
    rows: list[tuple[str, float, float]],
    *,
    best_score: float,
    rel_tol: float,
) -> tuple[str, float, float] | None:
    thr = _value_band_threshold(best_score, rel_tol)
    eligible = [(m, s, c) for m, s, c in rows if math.isfinite(s) and s >= thr]
    if not eligible:
        return None
    # Cheapest with valid tie-break; missing cost (+inf) loses to finite costs.
    def sort_key(item: tuple[str, float, float]) -> tuple[float, str]:
        m, _s, c = item
        cost_key = c if math.isfinite(c) else math.inf
        return (cost_key, m)

    return min(eligible, key=sort_key)


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
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        yield from reader


def aggregate_buckets(rows: Iterable[dict[str, str]], log_every: int = 100_000) -> dict[str, QuestionBucket]:
    buckets: dict[str, QuestionBucket] = {}
    n_rows = 0

    for row in rows:
        n_rows += 1
        qid = row.get("question_id") or ""
        if not qid:
            continue

        model = row.get("model_name") or row.get("model_dir") or "<unknown>"
        score = _to_float(row.get("score"), default=-math.inf)
        cost = _to_float(row.get("cost"), default=math.inf)

        b = buckets.get(qid)
        if b is None:
            b = QuestionBucket(
                dataset=row.get("dataset_name") or "",
                split=row.get("split") or "",
                origin_query=row.get("origin_query") or "",
                prompt=row.get("prompt") or "",
            )
            buckets[qid] = b
        b.add(model=model, score=score, cost=cost)

        if n_rows % log_every == 0:
            logging.info("rows_processed=%d unique_questions=%d", n_rows, len(buckets))

    logging.info("Final: rows_processed=%d unique_questions=%d", n_rows, len(buckets))
    return buckets


def write_cost_aware_csv(
    buckets: dict[str, QuestionBucket],
    output: Path,
    *,
    rel_tol: float,
) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    n_written = 0
    with output.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()

        for qid in sorted(buckets):
            bucket = buckets[qid]
            rows = _dedupe_per_model(bucket.observations)
            models_seen = sorted({m for m, _, _ in rows})

            abs_pick = pick_best_absolute(rows)
            if abs_pick is None:
                logging.debug("Skipping %s - no finite score from any model", qid)
                continue

            best_model, best_score, best_cost = abs_pick
            value_pick = pick_best_value(rows, best_score=best_score, rel_tol=rel_tol)
            if value_pick is None:
                logging.debug("Skipping %s - empty value band", qid)
                continue

            vm, vs, vc = value_pick
            thr = _value_band_threshold(best_score, rel_tol)
            n_in_band = sum(1 for _m, s, _c in rows if math.isfinite(s) and s >= thr)

            def _fmt_cost(c: float) -> str | float:
                return c if math.isfinite(c) else ""

            writer.writerow(
                {
                    "question_id": qid,
                    "dataset": bucket.dataset,
                    "split": bucket.split,
                    "origin_query": bucket.origin_query,
                    "prompt": bucket.prompt,
                    "best_value_model": vm,
                    "best_value_score": vs,
                    "best_value_cost": _fmt_cost(vc),
                    "best_model": best_model,
                    "best_score": best_score,
                    "best_cost": _fmt_cost(best_cost),
                    "score_rel_tolerance": rel_tol,
                    "n_models_compared": len(models_seen),
                    "n_models_in_value_band": n_in_band,
                    "models_evaluated": ";".join(models_seen),
                }
            )
            n_written += 1

    return n_written


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Path of the flattened records CSV (default: {DEFAULT_INPUT}).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Path to write the cost-aware classifier CSV (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--score-rel-tolerance",
        type=float,
        default=0.10,
        metavar="T",
        help="Relative score band vs best (e.g. 0.10 = within 10%% of best score). Default: 0.10.",
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

    if not (0.0 < args.score_rel_tolerance < 1.0):
        logging.error("--score-rel-tolerance must be between 0 and 1 (exclusive).")
        return 2

    if not args.input.exists():
        logging.error("Input CSV not found: %s", args.input)
        return 2

    logging.info(
        "Building cost-aware labels (rel_tolerance=%s) from %s",
        args.score_rel_tolerance,
        args.input,
    )
    buckets = aggregate_buckets(stream_rows(args.input), log_every=args.log_every)
    n_written = write_cost_aware_csv(buckets, args.output, rel_tol=args.score_rel_tolerance)
    logging.info("Wrote %d question rows to %s", n_written, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
