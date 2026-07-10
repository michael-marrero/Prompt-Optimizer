"""
STEP 3.1 (scaffold) - Synthesize a coherent decisions+feedback seed for the
Epic-3 retrain DRY RUN. **Throwaway: delete once real feedback flows.**

`build_retraining_dataset.py` is a pure feedback->CSV reader and never fabricates
labels. This disposable scaffold gives the dry run discriminative rows by writing
a real-shaped pair of JSONL files:

    <out-dir>/routing_decisions.jsonl   # {turn_id, thread_id, timestamp, backend, model_or_agent, rationale, confidence, signals}
    <out-dir>/routing_feedback.jsonl    # {sentiment, timestamp, thread_id, message_id, prompt, decision{...}}

Labels are DETERMINISTIC and self-contained (no benchmark join — the
data_processed/*.csv benchmark files are unpulled git-LFS pointers, and the whole
retrain pipeline follows a data-independence discipline). Each synthetic turn has a
designated "ideal" route; `up` when the brain's original pick matches the ideal,
`down` when it deliberately does not, plus a reroute subset (original != dispatched,
`signals.rerouted_from*` populated) and a `cleared` subset that supersedes an
earlier rating for the same turn.

SAFETY: defaults to a repo-local `data_processed/synthetic_seed/` — it will NOT
overwrite the user's live `~/.prompt-optimizer/.planning/data/` sinks unless you
pass `--output-dir` there explicitly.

Run from the repo root:

    python -m src.data.seed_synthetic_feedback --count 1210
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data_processed" / "synthetic_seed"
DEFAULT_COUNT = 1210  # matches the SPEC's synthetic seed size

logger = logging.getLogger(__name__)

# (prompt, ideal_backend, ideal_model) — the route a perfect brain would pick.
_TEMPLATES: list[tuple[str, str, str]] = [
    ("write a python function to reverse a linked list", "claude_code", "anthropic/claude-sonnet-4-5"),
    ("open github.com and star the anthropics/claude-code repo", "computer_use", "computer-use-2025-11-24"),
    ("what is the capital of france and why", "openrouter", "openrouter/auto"),
    ("summarize this article in three bullet points", "openrouter", "google/gemini-2.5-flash"),
]
# A generic "wrong" pick used for the down-labeled turns.
_WRONG = ("openrouter", "mistralai/mistral-small")
_BASE_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _iso(offset_minutes: int) -> str:
    return (_BASE_TS + timedelta(minutes=offset_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def synthesize(count: int) -> tuple[list[dict], list[dict]]:
    """Return (decision_records, feedback_records) — coherent, deterministic.

    kinds by index: i%3==1 -> wrong pick (down); elif i%5==0 -> reroute (up,
    original==ideal, dispatched==wrong, rerouted_from set); else correct (up).
    Every 10th turn also emits a later `cleared` event that supersedes its rating.
    """
    decisions: list[dict] = []
    feedback: list[dict] = []
    for i in range(count):
        prompt, ideal_backend, ideal_model = _TEMPLATES[i % len(_TEMPLATES)]
        prompt = f"{prompt} (case {i})"
        turn_id = f"turn-{i:05d}"
        message_id = f"seed-{i:05d}"
        thread_id = f"seed-thread-{i // 20}"
        ts = _iso(i)

        signals: dict = {}
        if i % 3 == 1:  # wrong pick, no reroute -> down
            original_backend, original_model = _WRONG
            dispatched_backend, dispatched_model = _WRONG
            sentiment = "down"
        elif i % 5 == 0:  # reroute: brain wanted ideal, got sent elsewhere -> up
            original_backend, original_model = ideal_backend, ideal_model
            dispatched_backend, dispatched_model = _WRONG
            signals["rerouted_from"] = ideal_backend
            signals["rerouted_from_model"] = ideal_model
            sentiment = "up"
        else:  # correct pick -> up
            original_backend, original_model = ideal_backend, ideal_model
            dispatched_backend, dispatched_model = ideal_backend, ideal_model
            sentiment = "up"

        decision = {
            "backend": dispatched_backend,
            "model_or_agent": dispatched_model,
            "rationale": "synthetic seed decision",
            "confidence": 0.9,
            "signals": signals,
        }
        decisions.append({
            "turn_id": turn_id,
            "thread_id": thread_id,
            "timestamp": ts,
            **decision,
        })
        feedback.append({
            "sentiment": sentiment,
            "timestamp": ts,
            "thread_id": thread_id,
            "message_id": message_id,
            "prompt": prompt,
            "decision": decision,
        })
        # Supersede path: a later `cleared` event for the same turn.
        if i % 10 == 0:
            feedback.append({
                "sentiment": "cleared",
                "timestamp": _iso(count + i),  # strictly later than the original event
                "thread_id": thread_id,
                "message_id": message_id,
                "prompt": prompt,
                "decision": decision,
            })
    return decisions, feedback


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _setup_logging(verbosity: int) -> None:
    level = logging.INFO if verbosity else logging.WARNING
    logging.basicConfig(level=level, format="%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--count", "-n", type=int, default=DEFAULT_COUNT, help=f"Turns to synthesize (default: {DEFAULT_COUNT}).")
    parser.add_argument("--output-dir", "-o", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help=f"Directory for the JSONL pair (default: {DEFAULT_OUTPUT_DIR}).")
    parser.add_argument("-v", "--verbose", action="count", default=1, help="-v info.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _setup_logging(args.verbose)

    decisions, feedback = synthesize(args.count)
    _write_jsonl(args.output_dir / "routing_decisions.jsonl", decisions)
    _write_jsonl(args.output_dir / "routing_feedback.jsonl", feedback)

    n_up = sum(1 for f in feedback if f["sentiment"] == "up")
    n_down = sum(1 for f in feedback if f["sentiment"] == "down")
    n_cleared = sum(1 for f in feedback if f["sentiment"] == "cleared")
    logger.info(
        "Wrote %d decisions + %d feedback events (up=%d down=%d cleared=%d) to %s",
        len(decisions), len(feedback), n_up, n_down, n_cleared, args.output_dir,
    )
    print(f"Wrote synthetic seed ({len(feedback)} feedback events) to: {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
