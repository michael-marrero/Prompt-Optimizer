"""
STEP 1 - Flatten the nested benchmark JSON tree into a single CSV.

Input layout (default):
    data_raw/<benchmark-release>/<dataset>/<split>/<model_dir>/<file>.json

Each JSON file is expected to contain top-level metadata
(performance, time_taken, prompt_tokens, completion_tokens, cost, counts,
model_name, dataset_name, split) plus a "records" array whose entries
contain origin_query, prompt, prediction, ground_truth, score,
prompt_tokens, completion_tokens and cost.

The script walks the input tree, loads every JSON file safely, skips
unreadable / malformed files (logging the reason) and streams one row
per (file, record) pair to a single output CSV.

Memory profile: only ONE file is kept in memory at a time and rows are
written incrementally with csv.DictWriter, so the script handles
multi-GB trees without trouble.

Run from the repo root:

    python -m src.data.flatten_raw_jsons \
        --input  data_raw \
        --output data_processed/flat_records.csv
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "data_raw"
DEFAULT_OUTPUT = PROJECT_ROOT / "data_processed" / "flat_records.csv"


CSV_FIELDS: list[str] = [
    "source_file",
    "model_dir",
    "model_name",
    "dataset_name",
    "split",
    "file_performance",
    "file_time_taken",
    "file_prompt_tokens",
    "file_completion_tokens",
    "file_cost",
    "file_counts",
    "record_index",
    "instance_id",
    "question_id",
    "origin_query",
    "prompt",
    "prediction",
    "ground_truth",
    "score",
    "prompt_tokens",
    "completion_tokens",
    "cost",
]


@dataclass
class WalkStats:
    files_seen: int = 0
    files_ok: int = 0
    files_skipped: int = 0
    records_written: int = 0


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


def iter_json_files(root: Path) -> Iterator[Path]:
    """Yield every *.json file under ``root`` (recursively), sorted for determinism."""
    yield from sorted(root.rglob("*.json"))


def safe_load_json(path: Path) -> dict[str, Any] | None:
    """Load a JSON file, returning None if the file is missing/corrupted/non-dict."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        logging.warning("File vanished while reading: %s", path)
        return None
    except json.JSONDecodeError as exc:
        logging.warning("Corrupt JSON skipped: %s (%s)", path, exc)
        return None
    except OSError as exc:
        logging.warning("OS error reading %s: %s", path, exc)
        return None

    if not isinstance(data, dict):
        logging.warning("Top-level JSON is not an object, skipping: %s", path)
        return None
    return data


def _coerce_number(value: Any) -> float | int | str | None:
    """Pass through numerics, return None for missing, and stringify weird types."""
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    return str(value)


def _hash_text(text: str, n: int = 16) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:n]


def _resolve_model_dir(file_path: Path, root: Path) -> str:
    """Parent folder of the JSON file relative to ``root`` (the model directory)."""
    try:
        rel = file_path.relative_to(root)
    except ValueError:
        rel = file_path
    parts = rel.parts
    return parts[-2] if len(parts) >= 2 else ""


def _resolve_dataset_split(file_path: Path, root: Path) -> tuple[str, str]:
    """Best-effort recovery of (dataset, split) from the path components.

    Layout assumption: ``<root>/<release>/<dataset>/<split>/<model>/<file>``
    """
    try:
        rel = file_path.relative_to(root)
    except ValueError:
        rel = file_path
    parts = rel.parts
    dataset = parts[-4] if len(parts) >= 4 else ""
    split = parts[-3] if len(parts) >= 3 else ""
    return dataset, split


def build_question_id(
    *, instance_id: Any, dataset: str, split: str, index: Any, origin_query: str
) -> str:
    """Stable per-question identifier shared across models.

    Priority:
      1. instance_id when present (e.g. swe-bench).
      2. dataset::split::index when index is available.
      3. dataset::split::sha1(origin_query) as a final fallback.
    """
    if instance_id not in (None, "", []):
        return f"{dataset}::{split}::{instance_id}"
    if index not in (None, ""):
        return f"{dataset}::{split}::idx-{index}"
    return f"{dataset}::{split}::q-{_hash_text(origin_query or '')}"


def flatten_file(
    file_path: Path, root: Path
) -> Iterable[dict[str, Any]]:
    """Yield one flattened row per record in ``file_path``."""
    payload = safe_load_json(file_path)
    if payload is None:
        return

    records = payload.get("records")
    if not isinstance(records, list):
        logging.warning("No 'records' list in %s, skipping", file_path)
        return

    model_dir = _resolve_model_dir(file_path, root)
    path_dataset, path_split = _resolve_dataset_split(file_path, root)

    model_name = payload.get("model_name") or model_dir
    dataset_name = payload.get("dataset_name") or path_dataset
    split = payload.get("split") or path_split

    try:
        rel_source = str(file_path.relative_to(root))
    except ValueError:
        rel_source = str(file_path)

    file_meta = {
        "source_file": rel_source,
        "model_dir": model_dir,
        "model_name": model_name,
        "dataset_name": dataset_name,
        "split": split,
        "file_performance": _coerce_number(payload.get("performance")),
        "file_time_taken": _coerce_number(payload.get("time_taken")),
        "file_prompt_tokens": _coerce_number(payload.get("prompt_tokens")),
        "file_completion_tokens": _coerce_number(payload.get("completion_tokens")),
        "file_cost": _coerce_number(payload.get("cost")),
        "file_counts": _coerce_number(payload.get("counts")),
    }

    for rec in records:
        if not isinstance(rec, dict):
            logging.debug("Non-dict record skipped in %s", file_path)
            continue

        origin_query = rec.get("origin_query") or ""
        record_index = rec.get("index")
        instance_id = rec.get("instance_id")

        question_id = build_question_id(
            instance_id=instance_id,
            dataset=dataset_name,
            split=split,
            index=record_index,
            origin_query=origin_query,
        )

        row = dict(file_meta)
        row.update(
            {
                "record_index": _coerce_number(record_index),
                "instance_id": instance_id if instance_id is not None else "",
                "question_id": question_id,
                "origin_query": origin_query,
                "prompt": rec.get("prompt") or "",
                "prediction": rec.get("prediction") if rec.get("prediction") is not None else "",
                "ground_truth": rec.get("ground_truth") if rec.get("ground_truth") is not None else "",
                "score": _coerce_number(rec.get("score")),
                "prompt_tokens": _coerce_number(rec.get("prompt_tokens")),
                "completion_tokens": _coerce_number(rec.get("completion_tokens")),
                "cost": _coerce_number(rec.get("cost")),
            }
        )
        yield row


def flatten_tree(input_root: Path, output_csv: Path, log_every: int = 25) -> WalkStats:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    stats = WalkStats()

    with output_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()

        for file_path in iter_json_files(input_root):
            stats.files_seen += 1
            wrote_any = False
            for row in flatten_file(file_path, input_root):
                writer.writerow(row)
                stats.records_written += 1
                wrote_any = True

            if wrote_any:
                stats.files_ok += 1
            else:
                stats.files_skipped += 1

            if stats.files_seen % log_every == 0:
                logging.info(
                    "scanned=%d ok=%d skipped=%d rows=%d  last=%s",
                    stats.files_seen,
                    stats.files_ok,
                    stats.files_skipped,
                    stats.records_written,
                    file_path.name,
                )

    return stats


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Root folder containing the nested JSON benchmark dump (default: {DEFAULT_INPUT}).",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Path of the flattened CSV to produce (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=25,
        help="Emit a progress line every N files (default: 25).",
    )
    parser.add_argument("-v", "--verbose", action="count", default=1, help="-v info, -vv debug.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _setup_logging(args.verbose)

    if not args.input.exists():
        logging.error("Input directory does not exist: %s", args.input)
        return 2

    logging.info("Flattening %s -> %s", args.input, args.output)
    stats = flatten_tree(args.input, args.output, log_every=args.log_every)
    logging.info(
        "Done. files_seen=%d files_ok=%d files_skipped=%d rows=%d output=%s",
        stats.files_seen,
        stats.files_ok,
        stats.files_skipped,
        stats.records_written,
        args.output,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
