"""
STEP 3.1 - Assemble a retraining dataset from captured routing signal.

Reads the feedback sink (`routing_feedback.jsonl`) — each row is self-contained:
it carries the prompt, a snapshot of the routing decision (backend/model +
`signals` with the Epic-1 `rerouted_from`/`rerouted_from_model` breadcrumb),
and the up/down/cleared sentiment. Emits one labeled row per RATED turn:

    message_id, thread_id, timestamp, origin_query,
    original_backend, original_model,          # the route the brain WANTED (Epic 1)
    dispatched_backend, dispatched_model,       # the route actually used
    label,                                       # up | down | cleared
    question_type, question_type_confidence,     # Stage-1 signal the brain served with (parity)
    <handcrafted prompt features...>             # PromptFeatureExtractor, attached inline

Feature/serve parity (Story 3.2 close-out): the production router text input carries the
Stage-1 `task_type` token + `question_type_confidence` numeric (src/routing/decide.py Stage 4:
`build_router_text_input_single(question_type=task_label, keyword_question_type="unknown")` +
`extra_values={"question_type_confidence": task_conf}`). Those signals were captured on the
turn — each feedback row's `decision.signals` carries `task_type` + `task_confidence` — so we
project them straight through here (NOT re-derived via the live classifier, which would skew).
`retrain_candidate` then reproduces the exact serve features: `build_router_text_input_series`
reads the `question_type` column, `keyword_question_type` is absent → falls back to "unknown"
(matching serve's hardcoded value), and `get_numeric_feature_columns` picks up
`question_type_confidence`.

Dedup: a turn is keyed on `message_id`; the latest event by timestamp wins, so a
`cleared` supersedes an earlier up/down rather than duplicating the turn (AC #2).

Original pick: from the feedback row's `decision.signals` — `rerouted_from*` when a
reroute happened, else the dispatched route (no reroute -> brain's pick == dispatched).

Couples to other components ONLY via files on disk (AD-8): reads JSONL with stdlib,
imports no `apps.*` / `src.routing` / `eval`. `routing_decisions.jsonl` shares no id
with the feedback sink (turn_id vs message_id), so it is NOT id-joined here — the
feedback record alone is sufficient.

Run from the repo root:

    python -m src.data.build_retraining_dataset \
        --routing-feedback ~/.prompt-optimizer/.planning/data/routing_feedback.jsonl \
        --output data_processed/retraining_dataset.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Re-derive the per-user state root the SAME way apps/api/paths.py does, but
# WITHOUT importing apps.* (AD-8): PROMPT_OPTIMIZER_HOME or ~/.prompt-optimizer.
USER_HOME = Path(os.environ.get("PROMPT_OPTIMIZER_HOME") or (Path.home() / ".prompt-optimizer"))
DEFAULT_FEEDBACK = USER_HOME / ".planning" / "data" / "routing_feedback.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "data_processed" / "retraining_dataset.csv"

# PromptFeatureExtractor via the documented sys.path shim (CLAUDE.md; same as
# src/routing/decide.py and src/evaluation/evaluate_routing.py). Import by bare
# name, not package path.
_FE_DIR = os.path.join(PROJECT_ROOT, "src", "feature_extraction")
if _FE_DIR not in sys.path:
    sys.path.append(_FE_DIR)
from Feature_extractor import PromptFeatureExtractor  # noqa: E402

logger = logging.getLogger(__name__)

BASE_FIELDS: list[str] = [
    "message_id",
    "thread_id",
    "timestamp",
    "origin_query",
    "original_backend",
    "original_model",
    "dispatched_backend",
    "dispatched_model",
    "label",
    # Stage-1 signal the brain served with — projected from decision.signals so the
    # candidate trains on the exact router features production used (serve parity).
    "question_type",
    "question_type_confidence",
]


@dataclass
class RatedTurn:
    """One rated turn ready for training (base columns; features added at write)."""

    message_id: str
    thread_id: str
    timestamp: str
    origin_query: str
    original_backend: str
    original_model: str
    dispatched_backend: str
    dispatched_model: str
    label: str
    question_type: str
    question_type_confidence: float


def stream_jsonl(path: Path) -> Iterator[dict]:
    """Yield one dict per non-blank line. Missing file -> empty; bad line -> warn+skip."""
    if not path.exists():
        logger.warning("JSONL not found (treating as empty): %s", path)
        return
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning("Skipping malformed JSON at %s:%d (%s)", path, lineno, exc)


def _ts_key(ts: str) -> datetime:
    """Chronological sort key robust to variable ISO fractional precision.

    The live server stamps `datetime.now(timezone.utc).isoformat()`, which OMITS
    the fractional part when microsecond==0 — so a lexical string compare ranks a
    whole-second `…00Z` above a `…00.5Z` half a second later (`"Z" > "."`) and
    would misorder the supersede. Parse to a datetime to compare correctly; an
    unparseable/missing timestamp sorts oldest (can never supersede).
    """
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.min.replace(tzinfo=timezone.utc)


def assemble_rated_turns(feedback_records: Iterable[dict]) -> dict[str, RatedTurn]:
    """Join feedback events into one RatedTurn per message_id (cleared supersedes).

    Latest event by parsed timestamp wins for a given message_id; on an exact tie
    the later-seen record wins (JSONL is append-only, so later line == later event).
    A malformed record (non-object, or a non-dict `decision`/`signals`) is warned
    and skipped rather than aborting the whole build.
    """
    latest: dict[str, tuple[datetime, str, dict]] = {}
    for rec in feedback_records:
        if not isinstance(rec, dict):
            logger.warning("Skipping non-object feedback record: %r", rec)
            continue
        mid = rec.get("message_id")
        if not mid:
            logger.warning("Skipping feedback record with no message_id: %r", rec.get("timestamp"))
            continue
        ts = str(rec.get("timestamp", ""))
        key = _ts_key(ts)
        if mid not in latest or key >= latest[mid][0]:
            latest[mid] = (key, ts, rec)

    turns: dict[str, RatedTurn] = {}
    for mid, (key, ts, rec) in latest.items():
        decision = rec.get("decision")
        if not isinstance(decision, dict):
            decision = {}
        signals = decision.get("signals")
        if not isinstance(signals, dict):
            signals = {}
        dispatched_backend = decision.get("backend") or ""
        dispatched_model = decision.get("model_or_agent") or ""
        turns[mid] = RatedTurn(
            message_id=mid,
            thread_id=str(rec.get("thread_id", "")),
            timestamp=ts,
            origin_query=str(rec.get("prompt", "")),
            # Epic-1 breadcrumb when a reroute happened, else the dispatched route.
            original_backend=signals.get("rerouted_from") or dispatched_backend,
            original_model=signals.get("rerouted_from_model") or dispatched_model,
            dispatched_backend=dispatched_backend,
            dispatched_model=dispatched_model,
            label=str(rec.get("sentiment", "")),
            # Stage-1 signal the brain served with (serve parity). Projected straight
            # from the captured signals — never re-derived. Missing (e.g. an override
            # turn) -> the neutral "unknown" / 0.0 the brain itself used there.
            question_type=str(signals.get("task_type") or "unknown"),
            question_type_confidence=_safe_float(signals.get("task_confidence")),
        )
    return turns


def _safe_float(value: object) -> float:
    """Coerce a possibly-missing/stringy confidence to float; default 0.0."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def write_dataset(turns: dict[str, RatedTurn], output: Path) -> int:
    """Write one row per turn with inline handcrafted features. Returns rows written.

    Feature columns come from PromptFeatureExtractor and are stable, so the
    header is derived from `extract("")` even when there are zero rows (header-
    only CSV is a valid empty dry-run output, AC #4).
    """
    extractor = PromptFeatureExtractor()
    feature_fields = list(extractor.extract("").keys())
    fieldnames = BASE_FIELDS + feature_fields

    output.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(turns.values(), key=lambda t: (_ts_key(t.timestamp), t.message_id))
    with output.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for turn in ordered:
            row = {
                "message_id": turn.message_id,
                "thread_id": turn.thread_id,
                "timestamp": turn.timestamp,
                "origin_query": turn.origin_query,
                "original_backend": turn.original_backend,
                "original_model": turn.original_model,
                "dispatched_backend": turn.dispatched_backend,
                "dispatched_model": turn.dispatched_model,
                "label": turn.label,
                "question_type": turn.question_type,
                "question_type_confidence": turn.question_type_confidence,
            }
            row.update(extractor.extract(turn.origin_query))
            writer.writerow(row)
    return len(ordered)


def _setup_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity >= 2:
        level = logging.DEBUG
    elif verbosity >= 1:
        level = logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--routing-feedback", "-f", type=Path, default=DEFAULT_FEEDBACK,
                        help=f"Path to routing_feedback.jsonl (default: {DEFAULT_FEEDBACK}).")
    parser.add_argument("--output", "-o", type=Path, default=DEFAULT_OUTPUT,
                        help=f"Path to write the retraining dataset (default: {DEFAULT_OUTPUT}).")
    parser.add_argument("-v", "--verbose", action="count", default=1, help="-v info, -vv debug.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """`python -m src.data.build_retraining_dataset` — exit 0 (empty feedback is OK)."""
    args = parse_args(argv)
    _setup_logging(args.verbose)

    # Empty/absent feedback is NOT an error: 0 rated turns is a valid dry-run
    # output (Story 3.3 relies on "0 feedback events -> loop runs, promotes nothing").
    records = list(stream_jsonl(args.routing_feedback))
    logger.info("Read %d feedback events from %s", len(records), args.routing_feedback)

    turns = assemble_rated_turns(records)
    n_written = write_dataset(turns, args.output)
    logger.info("Wrote %d rated turns to %s", n_written, args.output)
    print(f"Wrote {n_written} rated turns to: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
