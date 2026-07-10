"""Story 2.2 — load-time calibration-coverage enforcement (fail-closed).

`enforce_calibration_coverage(artifacts)` refuses a routing head that the
Story 2.1 manifest marks required-calibrated but that loaded uncalibrated
(or is missing). It runs once on the disk-load path — called from
`_load_default_artifacts()` — never on the per-turn request path (AD-3).
The raise names the offending head and the training command to run,
mirroring the `_load_one_artifact` remediation style (AD-8), so a fresh
checkout reads "which head, run what" instead of a stack trace.

Lives in src/calibration/ (a sibling util, not apps.*) so the D-18 import
guard stays green; sklearn is not a forbidden module.
"""

from __future__ import annotations

from sklearn.calibration import CalibratedClassifierCV

from src.routing.config import required_calibrated_heads

# Per-head remediation hint: the training script that re-produces a
# calibrated bundle. Mirrors the "run X first" contract of _load_one_artifact.
_TRAIN_COMMANDS: dict[str, str] = {
    "task_type_classifier": "echo train | uv run python -m src.task_classifier.train_task_classifier_robust",
    "agentic_intent_classifier": "echo train | uv run python -m src.task_classifier.train_agentic_intent",
    "model_router": "echo train | uv run python -m src.model_router.train_model_router",
}


def _is_calibrated(record: object) -> bool:
    """True iff `record` is a head bundle whose `model` is a CalibratedClassifierCV.

    The single calibration-detection predicate shared by the raising
    enforcement (2.2) and the non-raising report (2.3) — the isinstance rule
    is defined once here, not copied per consumer. A missing/non-dict record
    or a non-calibrated model returns False (never raises), so a raw estimator
    stored directly under a head key reads as "uncalibrated" rather than
    blowing up on `.get`.
    """
    model = record.get("model") if isinstance(record, dict) else None
    return isinstance(model, CalibratedClassifierCV)


def enforce_calibration_coverage(artifacts: dict) -> None:
    """Raise if any required-calibrated head is missing or uncalibrated.

    Iterates `required_calibrated_heads()` — the Story 2.1 manifest, the
    single source of truth (do not re-hardcode the head list). A head counts
    as calibrated iff `_is_calibrated()` holds (its `model` is a sklearn
    CalibratedClassifierCV — the same check test_calibration.py uses).

    Returns None on a fully-compliant set; the `artifacts` dict is never
    mutated (metadata check only — AD-10 quality-first ordering untouched).
    """
    for head in required_calibrated_heads():
        record = artifacts.get(head)
        if record is None:
            raise RuntimeError(_remediation(head, "is missing from the loaded artifacts"))
        if not _is_calibrated(record):
            raise RuntimeError(_remediation(head, "loaded uncalibrated"))


def calibration_status(artifacts: dict) -> dict[str, bool]:
    """Non-raising report of `{head: is_calibrated}` for each required head.

    The eval-gate counterpart (Story 2.3) to `enforce_calibration_coverage`
    (the raising load-time check). A required head that is missing or
    uncalibrated maps to False. Never raises and never mutates `artifacts`.
    """
    return {
        head: _is_calibrated(artifacts.get(head))
        for head in required_calibrated_heads()
    }


def _remediation(head: str, problem: str) -> str:
    # Leak nothing beyond the head name + fix command (AC #1).
    fix = _TRAIN_COMMANDS.get(head, "re-run its training script to produce a calibrated bundle")
    return (
        f"Required-calibrated routing head '{head}' {problem}. An uncalibrated "
        f"required head must never reach the policy thresholds (fail-closed). "
        f"Train/recalibrate it first:\n{fix}"
    )
