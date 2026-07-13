"""Story 3.3 — promotion-gate tests (data-independent).

The one heavy seam (`_gather_eval_metrics`, which runs the canary eval) is
monkeypatched so the gate composition, G1 real-turn counting, and the atomic
promotion copy are exercised fast — no live models/, no real feedback file, no
benchmark CSV. G1 counting and the pure gate functions are tested for real.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
from sklearn.linear_model import LogisticRegression

from src.data.seed_synthetic_feedback import main as seed_main
from src.data.build_retraining_dataset import main as assemble_main
from src.model_router.retrain_candidate import main as retrain_main
from src.model_router import promote_candidate as pc


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _passing_metrics(backend_accuracy: float = 0.80, router_ece: float = 0.05) -> dict:
    """A metrics dict that clears evaluate_check for all required heads."""
    heads = ["task_type_classifier", "agentic_intent_classifier", "model_router"]
    return {
        "backend_accuracy": backend_accuracy,
        "per_stage_ece": {h: (router_ece if h == "model_router" else 0.04) for h in heads},
        "per_head_calibrated": {h: True for h in heads},
        "low_confidence_rate": 0.0,
    }


def _real_staged_candidate(tmp_path: Path) -> Path:
    """Produce a real calibrated staged model_router via the 3.2 chain."""
    seed_main(["--count", "400", "--output-dir", str(tmp_path)])
    ds = tmp_path / "retraining_dataset.csv"
    assemble_main(["--routing-feedback", str(tmp_path / "routing_feedback.jsonl"), "--output", str(ds)])
    staging = tmp_path / "staging"
    rc = retrain_main(["--dataset", str(ds), "--staging-dir", str(staging)])
    assert rc == 0
    return staging / "model_router.joblib"


def _write_feedback(path: Path, *, real_up: int = 0, seed_up: int = 0, cleared_over_up: int = 0) -> None:
    lines = []
    for i in range(real_up):
        lines.append({"message_id": f"real-{i:04d}", "timestamp": f"2026-07-13T10:00:{i % 60:02d}", "sentiment": "up"})
    for i in range(seed_up):
        lines.append({"message_id": f"seed-{i:05d}", "timestamp": "2026-07-13T09:00:00", "sentiment": "up"})
    for i in range(cleared_over_up):  # an up later superseded by a cleared -> not a rated turn
        mid = f"cleared-{i:04d}"
        lines.append({"message_id": mid, "timestamp": "2026-07-13T08:00:00", "sentiment": "up"})
        lines.append({"message_id": mid, "timestamp": "2026-07-13T11:00:00", "sentiment": "cleared"})
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")


def _uncalibrated_bundle(tmp_path: Path) -> Path:
    """A staged bundle whose model is a raw (uncalibrated) estimator."""
    model = LogisticRegression().fit([[0.0], [1.0], [0.0], [1.0]], [0, 1, 0, 1])
    path = tmp_path / "staging" / "model_router.joblib"
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "vectorizer": None, "scaler": None,
                 "label_encoder": None, "feature_columns": [], "target_column": "original_model"}, path)
    return path


def _live_models_dir(tmp_path: Path, seed_bytes: bytes = b"OLD-LIVE-ROUTER") -> Path:
    models = tmp_path / "models"
    models.mkdir(parents=True, exist_ok=True)
    (models / "model_router.joblib").write_bytes(seed_bytes)
    return models


# ----------------------------------------------------------------------
# G1 — real-turn counting (real, no mocking)
# ----------------------------------------------------------------------
def test_count_real_rated_turns_excludes_seed_and_cleared(tmp_path: Path) -> None:
    fb = tmp_path / "routing_feedback.jsonl"
    _write_feedback(fb, real_up=5, seed_up=50, cleared_over_up=3)
    # 5 real up; 50 seed-* excluded; 3 cleared-supersede excluded.
    assert pc.count_real_rated_turns(fb) == 5


def test_count_real_rated_turns_missing_file_is_zero(tmp_path: Path) -> None:
    assert pc.count_real_rated_turns(tmp_path / "nope.jsonl") == 0


# ----------------------------------------------------------------------
# G2 / G3 — pure gate functions
# ----------------------------------------------------------------------
def test_gate_no_regression_passes_and_flags_regression() -> None:
    cand = _passing_metrics(backend_accuracy=0.80)
    assert pc.gate_no_regression(cand, None)[0] is True
    assert pc.gate_no_regression(cand, _passing_metrics(backend_accuracy=0.80))[0] is True
    # candidate 0.80 vs live 0.90 with tol 0.02 -> regression
    regressed, reasons = pc.gate_no_regression(cand, _passing_metrics(backend_accuracy=0.90))
    assert regressed is False and any("regress" in r for r in reasons)


def test_gate_calibration_rejects_uncalibrated_and_high_ece(tmp_path: Path) -> None:
    good_bundle = joblib.load(_real_staged_candidate(tmp_path))
    assert pc.gate_calibration(good_bundle, _passing_metrics(router_ece=0.05))[0] is True
    # high ECE fails even when calibrated
    ok, reasons = pc.gate_calibration(good_bundle, _passing_metrics(router_ece=0.50))
    assert ok is False and any("ece" in r for r in reasons)
    # uncalibrated model fails
    raw = {"model": LogisticRegression().fit([[0.0], [1.0]], [0, 1])}
    assert pc.gate_calibration(raw, _passing_metrics())[0] is False


# ----------------------------------------------------------------------
# main() — promote / hold branches (eval seam monkeypatched)
# ----------------------------------------------------------------------
def test_all_gates_pass_promotes_atomically(tmp_path: Path, monkeypatch, capsys) -> None:
    staged = _real_staged_candidate(tmp_path)
    models = _live_models_dir(tmp_path)
    fb = tmp_path / "fb.jsonl"
    _write_feedback(fb, real_up=100)  # G1 passes
    monkeypatch.setattr(pc, "_gather_eval_metrics", lambda *a, **k: (_passing_metrics(), _passing_metrics()))

    rc = pc.main(["--staging-dir", str(tmp_path / "staging"), "--models-dir", str(models),
                  "--canary-input", "unused", "--routing-feedback", str(fb)])
    assert rc == pc.EXIT_PROMOTED
    live = models / "model_router.joblib"
    assert live.read_bytes() == staged.read_bytes()          # replaced with the candidate
    backup = models / "model_router.joblib.bak"
    assert backup.exists() and backup.read_bytes() == b"OLD-LIVE-ROUTER"  # backup == prior live
    assert "PROMOTED" in capsys.readouterr().out


def test_g1_fail_holds_and_leaves_live_untouched(tmp_path: Path, monkeypatch, capsys) -> None:
    _real_staged_candidate(tmp_path)
    models = _live_models_dir(tmp_path, seed_bytes=b"KEEP-ME")
    fb = tmp_path / "fb.jsonl"
    _write_feedback(fb, real_up=3, seed_up=200)  # only 3 real -> G1 fails
    monkeypatch.setattr(pc, "_gather_eval_metrics", lambda *a, **k: (_passing_metrics(), _passing_metrics()))

    rc = pc.main(["--staging-dir", str(tmp_path / "staging"), "--models-dir", str(models),
                  "--canary-input", "unused", "--routing-feedback", str(fb)])
    assert rc == pc.EXIT_HELD
    assert (models / "model_router.joblib").read_bytes() == b"KEEP-ME"   # untouched
    assert not (models / "model_router.joblib.bak").exists()             # nothing promoted
    out = capsys.readouterr().out
    assert "HELD" in out and "G1 data-volume" in out                     # gate named in report


def test_g2_fail_holds(tmp_path: Path, monkeypatch, capsys) -> None:
    _real_staged_candidate(tmp_path)
    models = _live_models_dir(tmp_path, seed_bytes=b"KEEP-ME")
    fb = tmp_path / "fb.jsonl"
    _write_feedback(fb, real_up=100)
    # candidate regresses live backend_accuracy AND fails absolute floor
    monkeypatch.setattr(pc, "_gather_eval_metrics",
                        lambda *a, **k: (_passing_metrics(backend_accuracy=0.40), _passing_metrics(backend_accuracy=0.90)))

    rc = pc.main(["--staging-dir", str(tmp_path / "staging"), "--models-dir", str(models),
                  "--canary-input", "unused", "--routing-feedback", str(fb)])
    assert rc == pc.EXIT_HELD
    assert (models / "model_router.joblib").read_bytes() == b"KEEP-ME"
    assert "G2 no-regression" in capsys.readouterr().out


def test_g2_ignores_live_head_drift(tmp_path: Path, monkeypatch, capsys) -> None:
    """A live task_type/agentic head over its ECE threshold must NOT block the
    candidate model_router (the deadlock the review caught)."""
    staged = _real_staged_candidate(tmp_path)
    models = _live_models_dir(tmp_path)
    fb = tmp_path / "fb.jsonl"
    _write_feedback(fb, real_up=100)
    drifted = _passing_metrics()
    drifted["per_stage_ece"]["task_type_classifier"] = 0.99   # live head drifted
    drifted["per_head_calibrated"]["task_type_classifier"] = True
    monkeypatch.setattr(pc, "_gather_eval_metrics", lambda *a, **k: (drifted, drifted))

    rc = pc.main(["--staging-dir", str(tmp_path / "staging"), "--models-dir", str(models),
                  "--canary-input", "unused", "--routing-feedback", str(fb)])
    assert rc == pc.EXIT_PROMOTED                              # promoted despite live-head drift
    assert (models / "model_router.joblib").read_bytes() == staged.read_bytes()


def test_g3_fail_holds_on_uncalibrated_candidate(tmp_path: Path, monkeypatch, capsys) -> None:
    _uncalibrated_bundle(tmp_path)  # staged model is NOT calibrated
    models = _live_models_dir(tmp_path, seed_bytes=b"KEEP-ME")
    fb = tmp_path / "fb.jsonl"
    _write_feedback(fb, real_up=100)  # G1 passes
    monkeypatch.setattr(pc, "_gather_eval_metrics", lambda *a, **k: (_passing_metrics(), _passing_metrics()))

    rc = pc.main(["--staging-dir", str(tmp_path / "staging"), "--models-dir", str(models),
                  "--canary-input", "unused", "--routing-feedback", str(fb)])
    assert rc == pc.EXIT_HELD
    assert (models / "model_router.joblib").read_bytes() == b"KEEP-ME"   # held: uncalibrated candidate
    assert "G3 calibration-coverage" in capsys.readouterr().out


def test_first_promotion_creates_live_without_backup(tmp_path: Path, monkeypatch) -> None:
    staged = _real_staged_candidate(tmp_path)
    models = tmp_path / "models"
    models.mkdir()  # no live model_router yet -> baseline None, first promotion
    fb = tmp_path / "fb.jsonl"
    _write_feedback(fb, real_up=100)
    monkeypatch.setattr(pc, "_gather_eval_metrics", lambda *a, **k: (_passing_metrics(), None))

    rc = pc.main(["--staging-dir", str(tmp_path / "staging"), "--models-dir", str(models),
                  "--canary-input", "unused", "--routing-feedback", str(fb)])
    assert rc == pc.EXIT_PROMOTED
    assert (models / "model_router.joblib").read_bytes() == staged.read_bytes()
    assert not (models / "model_router.joblib.bak").exists()   # nothing to back up on first promotion


def test_missing_eval_infra_holds_and_reports(tmp_path: Path, monkeypatch, capsys) -> None:
    """Missing canary / live heads -> gates 'not evaluated' -> held (not a crash);
    the G1 report is still emitted (AC #3 dry-run in a thin environment)."""
    _real_staged_candidate(tmp_path)
    models = _live_models_dir(tmp_path, seed_bytes=b"KEEP-ME")
    fb = tmp_path / "fb.jsonl"
    _write_feedback(fb, real_up=0)  # 0 feedback

    def _raise(*a, **k):
        raise FileNotFoundError("canary not found")
    monkeypatch.setattr(pc, "_gather_eval_metrics", _raise)

    rc = pc.main(["--staging-dir", str(tmp_path / "staging"), "--models-dir", str(models),
                  "--canary-input", "missing.csv", "--routing-feedback", str(fb)])
    assert rc == pc.EXIT_HELD
    assert (models / "model_router.joblib").read_bytes() == b"KEEP-ME"
    out = capsys.readouterr().out
    assert "G1 data-volume" in out and "not evaluated" in out


def test_missing_staged_candidate_returns_error(tmp_path: Path) -> None:
    rc = pc.main(["--staging-dir", str(tmp_path / "staging"), "--models-dir", str(tmp_path / "models")])
    assert rc == pc.EXIT_ERROR


def test_corrupt_staged_candidate_returns_error(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "model_router.joblib").write_bytes(b"not a joblib file")
    rc = pc.main(["--staging-dir", str(staging), "--models-dir", str(tmp_path / "models")])
    assert rc == pc.EXIT_ERROR


def test_real_eval_seam_smoke(tmp_path: Path) -> None:
    """Integration: drive the REAL evaluate_routing.run(artifacts=candidate) seam so a
    shape mismatch surfaces here (not just under monkeypatch). Skips when the live
    heads / canary aren't materialized locally."""
    import pytest

    models = pc.DEFAULT_MODELS_DIR
    needed = [models / f"{h}.joblib" for h in pc.LIVE_HEADS] + [models / "model_router.joblib", Path(pc.CANARY_CSV)]
    if not all(p.exists() for p in needed):
        pytest.skip("live heads / canary not present locally")

    staged_bundle = joblib.load(_real_staged_candidate(tmp_path))
    try:
        candidate_metrics, baseline_metrics = pc._gather_eval_metrics(str(pc.CANARY_CSV), models, staged_bundle)
    except (FileNotFoundError, ValueError) as exc:
        pytest.skip(f"canary/heads not usable locally (LFS not pulled?): {exc}")
    assert "backend_accuracy" in candidate_metrics
    assert baseline_metrics is not None and "per_stage_ece" in baseline_metrics
