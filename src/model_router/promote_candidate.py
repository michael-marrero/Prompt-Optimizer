"""
STEP 3.3 - Promotion GATE: promote the staged candidate model_router to live
ONLY if all three gates pass. This is the feature — at 0 real feedback it
promotes nothing.

Three gates (all must pass):
  G1 data-volume     - routing_feedback.jsonl holds >= MIN_REAL_RATED_TURNS real
                       rated turns (real = message_id not `seed-*`, up/down after
                       the `cleared`-supersede dedup reused from Story 3.1).
  G2 no-regression   - the candidate, evaluated through the EXISTING routing-canary
                       pipeline, clears the backend_accuracy floor AND does not drop
                       the live baseline's backend_accuracy beyond REGRESSION_TOLERANCE
                       (FR-15). It deliberately does NOT fail on the unchanged live
                       task_type/agentic heads (that would deadlock promotion); the
                       candidate model_router's own calibration + ECE is gated by G3.
  G3 calibration     - the staged model_router is a CalibratedClassifierCV and its
                       measured ECE <= the Story 2.1 manifest threshold (Epic 2).

On all-pass: back up the current live model_router, then atomically replace it.
On any fail: hold the candidate, promote nothing (live models/ untouched), and
print a report naming each failed gate.

This is the ONE pipeline module allowed to write live models/ — and only on the
all-pass path.

Reuses (does NOT reinvent): evaluate_routing.run + BACKEND_ACCURACY_THRESHOLD (G2),
calibration.coverage.calibration_status + routing.config thresholds (G3),
build_retraining_dataset.stream_jsonl/assemble_rated_turns (G1 dedup).

Run from the repo root:

    python -m src.model_router.promote_candidate \
        --staging-dir models/staging --models-dir models
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path

import joblib

from src.calibration.coverage import calibration_status
from src.data.build_retraining_dataset import (
    DEFAULT_FEEDBACK,
    assemble_rated_turns,
    stream_jsonl,
)
from src.evaluation.evaluate_routing import (
    BACKEND_ACCURACY_THRESHOLD,
    CANARY_CSV,
    DEFAULT_MODEL_MAPPING_PATH,
    run as run_canary_eval,
)
from src.routing.config import ece_threshold_for

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STAGING_DIR = PROJECT_ROOT / "models" / "staging"
DEFAULT_MODELS_DIR = PROJECT_ROOT / "models"

ROUTER_ARTIFACT = "model_router.joblib"
LIVE_HEADS = ("task_type_classifier", "agentic_intent_classifier")  # unchanged live heads

MIN_REAL_RATED_TURNS = 100   # SPEC recalibration trigger — gate the loop on real data
REGRESSION_TOLERANCE = 0.02  # candidate backend_accuracy may not drop below live - this (FR-15)

# Exit codes (automation-facing — a held candidate is distinct from a promotion).
EXIT_PROMOTED = 0  # all gates passed, candidate promoted
EXIT_ERROR = 2     # can't run: missing/corrupt staged candidate, bad args
EXIT_HELD = 3      # gates ran (or couldn't be evaluated) and the candidate was held

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# G1 — data-volume gate
# ----------------------------------------------------------------------
def count_real_rated_turns(feedback_path: Path) -> int:
    """Real rated turns in routing_feedback.jsonl: message_id not `seed-*` and a
    final up/down label after the `cleared`-supersede dedup (reused from 3.1)."""
    turns = assemble_rated_turns(stream_jsonl(Path(feedback_path)))
    return sum(
        1 for t in turns.values()
        if not str(t.message_id).startswith("seed-") and t.label in ("up", "down")
    )


def gate_data_volume(feedback_path: Path) -> tuple[bool, str]:
    n = count_real_rated_turns(feedback_path)
    ok = n >= MIN_REAL_RATED_TURNS
    return ok, f"{n}/{MIN_REAL_RATED_TURNS} real rated turns"


# ----------------------------------------------------------------------
# G2 — FR-15 no-regression gate (pure over metrics dicts)
# ----------------------------------------------------------------------
def gate_no_regression(candidate_metrics: dict, baseline_metrics: dict | None) -> tuple[bool, list[str]]:
    """FR-15 no-regression on backend_accuracy — the metric the candidate actually
    moves. The candidate must clear the absolute floor AND not drop the live
    baseline beyond REGRESSION_TOLERANCE.

    Deliberately does NOT re-run the full evaluate_check over every required head:
    task_type/agentic are the unchanged live heads (already coverage-enforced at
    load), so failing G2 on their canary ECE would block a candidate model_router
    for reasons it didn't cause — and, since the baseline is never held to the same
    bar, would deadlock promotion once the live cascade drifts. The candidate
    model_router's own calibration + ECE is gated absolutely by G3.
    """
    reasons: list[str] = []
    cand = candidate_metrics.get("backend_accuracy")
    if cand is None:
        return False, ["candidate backend_accuracy was not measured"]
    if cand < BACKEND_ACCURACY_THRESHOLD:
        reasons.append(f"backend_accuracy={cand:.4f} < floor={BACKEND_ACCURACY_THRESHOLD:.4f}")
    if baseline_metrics is not None:
        base = baseline_metrics.get("backend_accuracy", 0.0)
        bound = base - REGRESSION_TOLERANCE
        if cand < bound:
            reasons.append(
                f"backend_accuracy regressed: candidate={cand:.4f} < {bound:.4f} (live {base:.4f} - {REGRESSION_TOLERANCE})"
            )
    return (len(reasons) == 0, reasons)


# ----------------------------------------------------------------------
# G3 — calibration-coverage gate (Epic 2, pure)
# ----------------------------------------------------------------------
def gate_calibration(staged_bundle: dict, candidate_metrics: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not calibration_status({"model_router": staged_bundle}).get("model_router", False):
        reasons.append("model_router candidate is uncalibrated (not a CalibratedClassifierCV)")
    ece = candidate_metrics.get("per_stage_ece", {}).get("model_router")
    threshold = ece_threshold_for("model_router")
    if ece is None or (isinstance(ece, float) and math.isnan(ece)):
        reasons.append("model_router ECE was not measured (missing or NaN)")  # NaN must fail, not silently pass
    elif ece > threshold:
        reasons.append(f"model_router ece={ece:.4f} > threshold={threshold:.4f}")
    return (len(reasons) == 0, reasons)


# ----------------------------------------------------------------------
# Evaluation seam (the one heavy part — isolated so tests can inject metrics)
# ----------------------------------------------------------------------
def _head_set(models_dir: Path, model_router_bundle: dict) -> dict:
    """Live task_type + agentic heads + model_mapping (from models_dir), with the
    given model_router bundle swapped in — the artifact dict run()/decide() expect."""
    artifacts: dict = {}
    for key in LIVE_HEADS:
        artifacts[key] = joblib.load(models_dir / f"{key}.joblib")
    with open(DEFAULT_MODEL_MAPPING_PATH, "r", encoding="utf-8") as fh:
        artifacts["model_mapping"] = json.load(fh)
    artifacts["model_router"] = model_router_bundle
    return artifacts


def _gather_eval_metrics(canary_input: str, models_dir: Path, staged_bundle: dict) -> tuple[dict, dict | None]:
    """Evaluate the candidate (live heads + staged model_router) and the live
    baseline (live heads + the CURRENT live model_router in models_dir) through the
    same canary pipeline. Returns (candidate, baseline); baseline is None when there
    is no live model_router yet (first promotion).

    Both sides are built from `models_dir` so the regression comparison is
    apples-to-apples against the exact artifact promotion would overwrite.

    Raises FileNotFoundError if the canary or a required live head is missing.
    """
    live_router = models_dir / ROUTER_ARTIFACT
    with tempfile.TemporaryDirectory() as tmp:
        candidate_metrics = run_canary_eval(
            canary_input, os.path.join(tmp, "candidate"),
            artifacts=_head_set(models_dir, staged_bundle),
        )
        baseline_metrics = None
        if live_router.exists():
            baseline_metrics = run_canary_eval(
                canary_input, os.path.join(tmp, "baseline"),
                artifacts=_head_set(models_dir, joblib.load(live_router)),
            )
    return candidate_metrics, baseline_metrics


# ----------------------------------------------------------------------
# Promotion (atomic + reversible) — the ONLY live models/ write
# ----------------------------------------------------------------------
def _next_backup_path(live_path: Path) -> Path:
    """First non-existing `.bak`, `.bak.1`, `.bak.2`, ... so a second promotion
    never clobbers a prior backup (reversibility beyond one step)."""
    base = live_path.with_name(live_path.name + ".bak")
    if not base.exists():
        return base
    i = 1
    while True:
        candidate = live_path.with_name(f"{live_path.name}.bak.{i}")
        if not candidate.exists():
            return candidate
        i += 1


def promote(staged_path: Path, live_path: Path) -> Path | None:
    """Back up the current live artifact (if any), then atomically replace it with
    the staged candidate. Returns the backup path, or None on first promotion."""
    backup: Path | None = None
    if live_path.exists():
        backup = _next_backup_path(live_path)
        shutil.copy2(live_path, backup)
    tmp = live_path.with_name(live_path.name + ".tmp")
    shutil.copy2(staged_path, tmp)
    os.replace(tmp, live_path)  # atomic on the same filesystem
    return backup


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def _setup_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity >= 2:
        level = logging.DEBUG
    elif verbosity >= 1:
        level = logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--staging-dir", "-s", type=Path, default=DEFAULT_STAGING_DIR,
                        help=f"Dir holding the staged candidate (default: {DEFAULT_STAGING_DIR}).")
    parser.add_argument("--models-dir", "-m", type=Path, default=DEFAULT_MODELS_DIR,
                        help=f"Live models dir (promotion target; default: {DEFAULT_MODELS_DIR}).")
    parser.add_argument("--canary-input", "-c", type=str, default=CANARY_CSV,
                        help=f"Canary CSV for the FR-15 gate (default: {CANARY_CSV}).")
    parser.add_argument("--routing-feedback", "-f", type=Path, default=DEFAULT_FEEDBACK,
                        help=f"routing_feedback.jsonl for the data-volume gate (default: {DEFAULT_FEEDBACK}).")
    parser.add_argument("-v", "--verbose", action="count", default=1, help="-v info, -vv debug.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _setup_logging(args.verbose)

    staged_path = args.staging_dir / ROUTER_ARTIFACT
    live_path = args.models_dir / ROUTER_ARTIFACT

    if not staged_path.exists():
        logger.error("No staged candidate to promote at: %s (run retrain_candidate first)", staged_path)
        return EXIT_ERROR

    # Guard: staging and live must not alias (samefile catches macOS case-insensitive aliases).
    if (args.staging_dir.exists() and args.models_dir.exists()
            and os.path.samefile(args.staging_dir, args.models_dir)):
        logger.error("--staging-dir and --models-dir resolve to the same directory: %s", args.models_dir)
        return EXIT_ERROR

    try:
        staged_bundle = joblib.load(staged_path)
    except Exception as exc:  # corrupt/truncated/non-joblib staged file
        logger.error("Could not load staged candidate %s: %s", staged_path, exc)
        return EXIT_ERROR

    # G1 — cheap, always evaluated so the report exists even with no eval infra (AC #3).
    g1_ok, g1_msg = gate_data_volume(args.routing_feedback)

    # G2 + G3 — need the canary + live heads. MISSING infra degrades to "not evaluated"
    # (→ held), so the dry-run at 0 feedback still runs and reports (AC #3). A malformed
    # canary/head (present but broken) is a real operator error → EXIT_ERROR, not a crash.
    candidate_metrics = None
    eval_error = None
    try:
        candidate_metrics, baseline_metrics = _gather_eval_metrics(args.canary_input, args.models_dir, staged_bundle)
    except FileNotFoundError as exc:
        eval_error = f"not evaluated (missing eval infra): {exc}"
        logger.warning("FR-15 / calibration gates %s", eval_error)
    except Exception as exc:
        logger.error("Cannot evaluate FR-15 / calibration gates (malformed canary or heads): %s", exc)
        return EXIT_ERROR

    if candidate_metrics is None:
        g2_ok, g2_reasons = False, [eval_error]
        g3_ok, g3_reasons = False, [eval_error]
    else:
        g2_ok, g2_reasons = gate_no_regression(candidate_metrics, baseline_metrics)
        g3_ok, g3_reasons = gate_calibration(staged_bundle, candidate_metrics)

    results = [
        ("G1 data-volume", g1_ok, g1_msg),
        ("G2 no-regression (FR-15)", g2_ok, "; ".join(g2_reasons) or "ok"),
        ("G3 calibration-coverage", g3_ok, "; ".join(g3_reasons) or "ok"),
    ]
    print("\nPromotion gate report:")
    for name, ok, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    # G1 passing means real feedback exists → the 3.2 train/serve parity gap now bites
    # (candidate trains without Stage-1 task_type/keyword_type tokens). Warn before promoting.
    if g1_ok:
        print("\n⚠ REAL-PROMOTION READINESS: the candidate trains without the Stage-1 "
              "task_type/keyword_type tokens the live router serves with (train/serve schema "
              "gap — see deferred-work.md). Close that before promoting on real feedback.")

    if all(ok for _, ok, _ in results):
        backup = promote(staged_path, live_path)
        where = f" (backup: {backup})" if backup else " (first promotion — no prior live artifact)"
        print(f"\nPROMOTED candidate -> {live_path}{where}")
        return EXIT_PROMOTED

    failed = [name for name, ok, _ in results if not ok]
    print(f"\nHELD candidate — promoted nothing. Failed gate(s): {', '.join(failed)}.")
    return EXIT_HELD


if __name__ == "__main__":
    sys.exit(main())
