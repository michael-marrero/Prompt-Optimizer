"""Story 2.1 (DEF-3) — the calibration-coverage contract is declared and stays
in sync with the heads the routing brain actually loads.

``config.CALIBRATION_COVERAGE`` is the single source of truth for which heads
MUST be calibrated (vs. may use raw ``predict_proba``) and each head's ECE
ceiling. Story 2.2 enforces it at artifact-load time; Story 2.3 consumes the
per-head ``ece_threshold`` in the eval gate. This test guards the *declaration*:
it fails if a head joins ``DEFAULT_ARTIFACT_PATHS`` (the live routing path) but
is not added to the manifest, so coverage can never silently drift.
"""

from __future__ import annotations

from src.routing import config


def test_manifest_covers_exactly_the_loaded_heads() -> None:
    # DEFAULT_ARTIFACT_PATHS is the set of heads decide.py loads for the live
    # cascade. The coverage contract must name exactly those heads — no more
    # (no experimental heads), no fewer (no uncovered live head).
    assert set(config.CALIBRATION_COVERAGE) == set(config.DEFAULT_ARTIFACT_PATHS)


def test_manifest_entries_well_formed() -> None:
    for head, record in config.CALIBRATION_COVERAGE.items():
        assert isinstance(record["required_calibrated"], bool), head
        ece = record["ece_threshold"]
        assert isinstance(ece, float), f"{head}: ece_threshold must be float"
        assert 0.0 < ece <= 1.0, f"{head}: ece_threshold {ece} out of (0, 1]"


def test_all_live_heads_are_required_calibrated() -> None:
    # All three live heads are calibrated today (CalibratedClassifierCV, per
    # src/calibration/tests/test_calibration.py); the contract asserts it.
    assert config.required_calibrated_heads() == sorted(config.DEFAULT_ARTIFACT_PATHS)


def test_experimental_heads_not_claimed_required() -> None:
    # tier_router / embedding_router are NOT on the live path and must never be
    # silently marked required by this contract.
    required = config.required_calibrated_heads()
    assert "tier_router" not in required
    assert "embedding_router" not in required
