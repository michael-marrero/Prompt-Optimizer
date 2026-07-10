"""
Story 2.2 — load-time calibration-coverage enforcement tests.

Data-independent by design: builds in-memory fake artifact dicts so the
check is provable without trained models/*.joblib on disk (2.1's
data-independence lesson — a data-dependent test flaked when the CSV needed
regeneration). RED before src/calibration/coverage.py exists, GREEN after.

Covers AC #1 (uncalibrated required head fails closed, message names it),
AC #2 (fully-compliant set passes, no raise), AC #4 (both directions via the
manifest accessor, no trained artifacts required).
"""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression

from src.calibration.coverage import calibration_status, enforce_calibration_coverage
from src.routing.config import required_calibrated_heads


# Toy 2-class data — 10 rows so the calibrator's default 5-fold CV is happy;
# no dataset needed.
_X = np.array([[0.0], [1.0]] * 5)
_Y = np.array([0, 1] * 5)


def _calibrated_model() -> CalibratedClassifierCV:
    """A real CalibratedClassifierCV (same isinstance target the enforcer checks)."""
    lr = LogisticRegression().fit(_X, _Y)
    return CalibratedClassifierCV(FrozenEstimator(lr), method="sigmoid").fit(_X, _Y)


def _uncalibrated_model() -> LogisticRegression:
    return LogisticRegression().fit(_X, _Y)


def _compliant_artifacts() -> dict:
    return {head: {"model": _calibrated_model()} for head in required_calibrated_heads()}


def test_compliant_set_passes() -> None:
    """AC #2 / #4: every required head calibrated -> returns without raising."""
    assert enforce_calibration_coverage(_compliant_artifacts()) is None


def test_uncalibrated_required_head_raises() -> None:
    """AC #1 / #4: one required head uncalibrated -> raises naming that head."""
    offending = required_calibrated_heads()[0]
    artifacts = _compliant_artifacts()
    artifacts[offending] = {"model": _uncalibrated_model()}

    with pytest.raises((RuntimeError, ValueError)) as exc:
        enforce_calibration_coverage(artifacts)
    assert offending in str(exc.value)


def test_missing_required_head_raises() -> None:
    """AC #1: a required head absent entirely raises the same way (no cryptic KeyError)."""
    offending = required_calibrated_heads()[0]
    artifacts = _compliant_artifacts()
    del artifacts[offending]

    with pytest.raises((RuntimeError, ValueError)) as exc:
        enforce_calibration_coverage(artifacts)
    assert offending in str(exc.value)


def test_non_dict_head_value_raises_cleanly() -> None:
    """Review fix: a present-but-non-dict head value (raw estimator stored
    directly) raises the clean remediation, not a cryptic AttributeError."""
    offending = required_calibrated_heads()[0]
    artifacts = _compliant_artifacts()
    artifacts[offending] = _calibrated_model()  # raw model, not a {"model": ...} bundle

    with pytest.raises((RuntimeError, ValueError)) as exc:
        enforce_calibration_coverage(artifacts)
    assert offending in str(exc.value)


# --- Story 2.3: non-raising calibration_status() reader ---------------------


def test_calibration_status_all_calibrated() -> None:
    """Compliant set -> every required head reports True; never raises."""
    status = calibration_status(_compliant_artifacts())
    assert status == {head: True for head in required_calibrated_heads()}


def test_calibration_status_flags_uncalibrated_and_missing() -> None:
    """An uncalibrated head and a non-dict head both report False (no raise)."""
    heads = required_calibrated_heads()
    uncal, nondict = heads[0], heads[1]
    artifacts = _compliant_artifacts()
    artifacts[uncal] = {"model": _uncalibrated_model()}
    artifacts[nondict] = _calibrated_model()  # raw model, not a bundle

    status = calibration_status(artifacts)
    assert status[uncal] is False
    assert status[nondict] is False
    # untouched heads stay True
    for head in heads[2:]:
        assert status[head] is True
