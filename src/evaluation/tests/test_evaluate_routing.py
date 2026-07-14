"""Plan 01-07 — ROUTER-04 / Success Criterion #3 — evaluator runs the
canary CSV through decide() and emits the D-16 metric suite under
evaluation/routing/.

Strategy:
  - The integration tests invoke `src.evaluation.evaluate_routing.run()`
    directly (Python-level) and assert the 9 output files materialize
    and parse correctly. This is faster and more deterministic than
    spawning a subprocess for every test.
  - A separate test spawns `uv run python -m ...` as a subprocess to
    confirm the module-style invocation works end-to-end (the form
    documented in CLAUDE.md "Module Design" and used by CI).
  - The --check flag's exit-code semantics are exercised via
    `evaluate_check()` directly (deterministic, not subject to the
    runtime state of the canary or calibrated artifacts).

`test_check_flag_behavior` deliberately does NOT assert on the
runtime --check exit code because the calibrated heads' ECE may
exceed the 0.10 threshold (RESEARCH Open Question 1 carry-forward;
Plan 05 documented ECE 0.116 -> 0.142 training-set regression).
Plan 08's regression guard owns the recalibration decision.
"""

from __future__ import annotations

import csv
import os
import pathlib
import subprocess
import sys

import pytest


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", ".."))
CANARY_PATH = pathlib.Path(PROJECT_ROOT) / "data_processed" / "routing_decision_eval.csv"
DEFAULT_OUTPUT_DIR = pathlib.Path(PROJECT_ROOT) / "evaluation" / "routing"

# Files emitted by D-16. The .png paths are dependency-imaged so we
# check existence not content.
D16_EXPECTED_FILES = [
    "backend_accuracy.csv",
    "per_backend_pr.csv",
    "confusion_matrix.csv",
    "confusion_matrix.png",
    "ece_per_stage.csv",
    "low_confidence_rate.txt",
    "reliability_diagram_task_type_classifier.png",
    "reliability_diagram_agentic_intent_classifier.png",
    "reliability_diagram_model_router.png",
]


def _is_lfs_pointer(path: pathlib.Path) -> bool:
    """Return True if the path is an unfetched LFS pointer."""
    if not path.exists():
        return False
    with path.open("r", encoding="utf-8") as fh:
        return fh.readline().strip().startswith("version https://git-lfs.github.com/spec/")


def _skip_if_canary_unavailable():
    """Skip the test if the canary CSV doesn't exist or is an LFS pointer.

    LFS pointers aren't materialized on a fresh CI clone without an
    explicit `git lfs pull`; the test_canary_csv_exists test in
    test_canary_schema.py will still fail loudly on a missing file.
    """
    if not CANARY_PATH.exists():
        pytest.skip(f"canary CSV missing at {CANARY_PATH}")
    if _is_lfs_pointer(CANARY_PATH):
        pytest.skip("canary CSV is an unfetched LFS pointer; run `git lfs pull`")


def _skip_if_artifacts_unavailable():
    """Skip if any of the 3 calibrated joblib heads are missing.

    The evaluator will raise FileNotFoundError otherwise. Plan 04 +
    Plan 05 own these artifacts; in a fresh checkout they may be
    missing until those plans are re-executed.
    """
    from src.routing.config import DEFAULT_ARTIFACT_PATHS
    for key, path in DEFAULT_ARTIFACT_PATHS.items():
        if not os.path.exists(path):
            pytest.skip(f"missing artifact {key} at {path}; run Plan 01-04/05 training")


# ----------------------------------------------------------------------
# 1. End-to-end: `evaluate_routing.run` completes + emits all D-16 files
# ----------------------------------------------------------------------


def test_evaluate_routing_completes(tmp_path: pathlib.Path):
    """Smoke test: `run()` on the real canary writes all D-16 files.

    Uses a tmp_path output dir so this test is isolated from the
    committed `evaluation/routing/` artifacts (which Task 3 produced).
    """
    _skip_if_canary_unavailable()
    _skip_if_artifacts_unavailable()

    from src.evaluation.evaluate_routing import run

    metrics = run(canary_path=str(CANARY_PATH), output_dir=str(tmp_path))

    assert "backend_accuracy" in metrics
    assert "per_stage_ece" in metrics
    assert "low_confidence_rate" in metrics
    assert "n_rows" in metrics
    assert metrics["n_rows"] > 0
    assert 0.0 <= metrics["backend_accuracy"] <= 1.0
    assert 0.0 <= metrics["low_confidence_rate"] <= 1.0


def test_evaluate_routing_output_files_exist(tmp_path: pathlib.Path):
    """All 9 D-16 output files are written by `run()`."""
    _skip_if_canary_unavailable()
    _skip_if_artifacts_unavailable()

    from src.evaluation.evaluate_routing import run

    run(canary_path=str(CANARY_PATH), output_dir=str(tmp_path))

    for filename in D16_EXPECTED_FILES:
        out = tmp_path / filename
        assert out.exists(), f"D-16 output file missing: {filename}"
        assert out.stat().st_size > 0, f"D-16 output file empty: {filename}"


# ----------------------------------------------------------------------
# 2. backend_accuracy.csv is well-formed
# ----------------------------------------------------------------------


def test_backend_accuracy_csv_well_formed(tmp_path: pathlib.Path):
    """backend_accuracy.csv has expected columns + numeric accuracy."""
    _skip_if_canary_unavailable()
    _skip_if_artifacts_unavailable()

    from src.evaluation.evaluate_routing import run

    run(canary_path=str(CANARY_PATH), output_dir=str(tmp_path))

    csv_path = tmp_path / "backend_accuracy.csv"
    with csv_path.open("r", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    assert {"backend", "accuracy", "n_expected", "n_actual"}.issubset(rows[0].keys())
    backends_seen = {r["backend"] for r in rows}
    # Must include the OVERALL summary row + at least one backend row.
    assert "OVERALL" in backends_seen
    # 3 backends + OVERALL = 4 rows minimum
    assert len(rows) >= 4

    # At least one row has accuracy > 0
    accuracies = [float(r["accuracy"]) for r in rows]
    assert any(a > 0.0 for a in accuracies), (
        "no row had accuracy > 0; canary or decide() may be misconfigured"
    )


# ----------------------------------------------------------------------
# 3. ece_per_stage.csv has 3 rows (one per calibrated head) in [0, 1]
# ----------------------------------------------------------------------


def test_ece_per_stage_csv_has_three_rows(tmp_path: pathlib.Path):
    """ece_per_stage.csv contains exactly the 3 calibrated heads."""
    _skip_if_canary_unavailable()
    _skip_if_artifacts_unavailable()

    from src.evaluation.evaluate_routing import run

    run(canary_path=str(CANARY_PATH), output_dir=str(tmp_path))

    csv_path = tmp_path / "ece_per_stage.csv"
    with csv_path.open("r", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    assert len(rows) == 3, f"expected 3 ECE rows; got {len(rows)}"

    expected_stages = {
        "task_type_classifier",
        "agentic_intent_classifier",
        "model_router",
    }
    actual_stages = {r["stage"] for r in rows}
    assert actual_stages == expected_stages, (
        f"ECE stages mismatch.\n"
        f"  expected: {sorted(expected_stages)}\n"
        f"  actual:   {sorted(actual_stages)}"
    )

    for row in rows:
        ece = float(row["ece"])
        assert 0.0 <= ece <= 1.0, (
            f"ECE for {row['stage']} out of [0, 1]: {ece}"
        )


# ----------------------------------------------------------------------
# 4. low_confidence_rate.txt parses to a float in [0, 1]
# ----------------------------------------------------------------------


def test_low_confidence_rate_in_valid_range(tmp_path: pathlib.Path):
    """low_confidence_rate.txt parses as `low_confidence_rate=<float>`."""
    _skip_if_canary_unavailable()
    _skip_if_artifacts_unavailable()

    from src.evaluation.evaluate_routing import run

    run(canary_path=str(CANARY_PATH), output_dir=str(tmp_path))

    txt_path = tmp_path / "low_confidence_rate.txt"
    content = txt_path.read_text(encoding="utf-8").strip()

    assert content.startswith("low_confidence_rate="), (
        f"low_confidence_rate.txt format wrong: {content!r}"
    )

    rate_str = content.split("=", 1)[1].strip()
    rate = float(rate_str)
    assert 0.0 <= rate <= 1.0, f"low_confidence_rate out of [0, 1]: {rate}"


# ----------------------------------------------------------------------
# 5. --check flag exit-code behavior (deterministic via evaluate_check)
# ----------------------------------------------------------------------


def _all_calibrated() -> dict:
    """{head: True} for every required head — the compliant coverage input."""
    from src.routing.config import required_calibrated_heads

    return {head: True for head in required_calibrated_heads()}


def test_check_flag_passes_when_thresholds_met():
    """evaluate_check returns (True, []) when all metrics pass."""
    from src.evaluation.evaluate_routing import evaluate_check

    good_metrics = {
        "backend_accuracy": 0.95,
        "per_stage_ece": {
            "task_type_classifier": 0.05,
            "agentic_intent_classifier": 0.03,
            "model_router": 0.07,
        },
        "per_head_calibrated": _all_calibrated(),
        "low_confidence_rate": 0.15,
    }
    passed, failures = evaluate_check(good_metrics)
    assert passed is True, f"--check should pass; got failures: {failures}"
    assert failures == []


def test_check_flag_fails_when_accuracy_below_threshold():
    """evaluate_check returns (False, [...]) when accuracy < 0.65."""
    from src.evaluation.evaluate_routing import evaluate_check

    bad_metrics = {
        "backend_accuracy": 0.40,  # below 0.65 threshold
        "per_stage_ece": {
            "task_type_classifier": 0.05,
            "agentic_intent_classifier": 0.03,
            "model_router": 0.07,
        },
        "per_head_calibrated": _all_calibrated(),
        "low_confidence_rate": 0.15,
    }
    passed, failures = evaluate_check(bad_metrics)
    assert passed is False
    assert any("backend_accuracy" in f for f in failures)


def test_check_flag_fails_when_any_ece_above_threshold():
    """evaluate_check returns (False, [...]) when a calibrated head's ECE > its threshold."""
    from src.evaluation.evaluate_routing import evaluate_check

    bad_metrics = {
        "backend_accuracy": 0.95,
        "per_stage_ece": {
            "task_type_classifier": 0.42,  # above the manifest 0.10 threshold
            "agentic_intent_classifier": 0.03,
            "model_router": 0.07,
        },
        "per_head_calibrated": _all_calibrated(),
        "low_confidence_rate": 0.15,
    }
    passed, failures = evaluate_check(bad_metrics)
    assert passed is False
    assert any("task_type_classifier" in f and "ece" in f for f in failures)


def test_check_flag_fails_closed_on_nan_ece():
    """Deferred F(2.3-#4): a required head with a NaN ECE must FAIL, not pass.

    `NaN > threshold` is False, so without the guard an unmeasurable calibration
    slips through the gate. Mirrors the live promotion gate's G3 NaN guard.
    """
    from src.evaluation.evaluate_routing import evaluate_check

    metrics = {
        "backend_accuracy": 0.95,
        "per_stage_ece": {
            "task_type_classifier": float("nan"),  # unmeasurable — must fail closed
            "agentic_intent_classifier": 0.03,
            "model_router": 0.07,
        },
        "per_head_calibrated": _all_calibrated(),
        "low_confidence_rate": 0.15,
    }
    passed, failures = evaluate_check(metrics)
    assert passed is False
    assert any("task_type_classifier" in f and "NaN" in f for f in failures)


def test_check_flag_fails_when_required_head_uncalibrated():
    """Story 2.3: a required head reported uncalibrated fails, naming the head."""
    from src.evaluation.evaluate_routing import evaluate_check

    per_head = _all_calibrated()
    offending = sorted(per_head)[0]
    per_head[offending] = False
    metrics = {
        "backend_accuracy": 0.95,
        "per_stage_ece": {
            "task_type_classifier": 0.05,
            "agentic_intent_classifier": 0.03,
            "model_router": 0.07,
        },
        "per_head_calibrated": per_head,
        "low_confidence_rate": 0.15,
    }
    passed, failures = evaluate_check(metrics)
    assert passed is False
    assert any(offending in f and "uncalibrated" in f for f in failures)


def test_check_flag_fails_closed_when_calibration_status_missing():
    """Story 2.3: a required head with no calibration status fails closed (not a silent pass)."""
    from src.evaluation.evaluate_routing import evaluate_check

    per_head = _all_calibrated()
    offending = sorted(per_head)[0]
    del per_head[offending]  # status absent for a required head
    metrics = {
        "backend_accuracy": 0.95,
        "per_stage_ece": {
            "task_type_classifier": 0.05,
            "agentic_intent_classifier": 0.03,
            "model_router": 0.07,
        },
        "per_head_calibrated": per_head,
        "low_confidence_rate": 0.15,
    }
    passed, failures = evaluate_check(metrics)
    assert passed is False
    assert any(offending in f and "confirm calibration" in f for f in failures)


def test_check_flag_behavior():
    """Runtime --check exit code (informational, never asserts on value).

    Plan 01-07 PLAN.md Task 4 Action step 2 specifies that this test
    captures the exit code into a stdout log line but does NOT assert
    on it because the canary accuracy depends on Plan 04+05's
    calibrated artifacts at runtime. Plan 08's regression guard is
    where the runtime exit code becomes a CI gate.
    """
    _skip_if_canary_unavailable()
    _skip_if_artifacts_unavailable()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.evaluation.evaluate_routing",
            "--check",
            "--canary-input",
            str(CANARY_PATH),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    print(f"[informational] --check exited with code={result.returncode}")
    # Test always passes; the exit code is a Plan 08 signal.
    assert True


# ----------------------------------------------------------------------
# 6. Module-style invocation works (CI gate path)
# ----------------------------------------------------------------------


def test_module_invocation_runs_end_to_end(tmp_path: pathlib.Path):
    """`python -m src.evaluation.evaluate_routing` (without --check) exits 0.

    This is the form CI uses (gated by hashFiles in .github/workflows/ci.yml)
    so we exercise it via subprocess. Without --check the runner is allowed
    to surface threshold violations without failing — exit 0 is the contract.
    """
    _skip_if_canary_unavailable()
    _skip_if_artifacts_unavailable()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.evaluation.evaluate_routing",
            "--canary-input",
            str(CANARY_PATH),
            "--output-dir",
            str(tmp_path),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, (
        f"evaluator exited non-zero without --check.\n"
        f"  stdout: {result.stdout[-2000:]}\n"
        f"  stderr: {result.stderr[-2000:]}"
    )

    # All 9 D-16 files should now exist in the tmp_path output dir.
    for filename in D16_EXPECTED_FILES:
        out = tmp_path / filename
        assert out.exists(), f"D-16 file missing after module invocation: {filename}"
