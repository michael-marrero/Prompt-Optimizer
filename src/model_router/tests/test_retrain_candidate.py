"""Story 3.2 — retrain-candidate tests (data-independent).

Drives the real Story 3.1 chain (synthetic scaffold -> assemble) into a tmp_path
CSV, then retrains a candidate model_router into a tmp staging dir. No dependency
on live models/*.joblib or a materialized benchmark CSV.
"""

from __future__ import annotations

import csv
from pathlib import Path

import joblib
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV

from src.data.build_retraining_dataset import main as assemble_main
from src.data.seed_synthetic_feedback import main as seed_main
from src.model_router.retrain_candidate import build_training_frame, main as retrain_main

_CANONICAL_KEYS = {"model", "vectorizer", "scaler", "label_encoder", "feature_columns", "target_column"}


def _make_dataset(tmp_path: Path, count: int) -> Path:
    """Synthesize a seed and assemble it into a 3.1 retraining CSV."""
    seed_main(["--count", str(count), "--output-dir", str(tmp_path)])
    ds = tmp_path / "retraining_dataset.csv"
    assemble_main(["--routing-feedback", str(tmp_path / "routing_feedback.jsonl"), "--output", str(ds)])
    return ds


def test_retrain_writes_calibrated_candidate_to_staging(tmp_path: Path) -> None:
    ds = _make_dataset(tmp_path, count=400)
    staging = tmp_path / "staging"

    rc = retrain_main(["--dataset", str(ds), "--staging-dir", str(staging)])
    assert rc == 0

    candidate = staging / "model_router.joblib"
    assert candidate.exists()  # written to the given staging dir, not live models/
    bundle = joblib.load(candidate)
    assert _CANONICAL_KEYS <= set(bundle)  # self-contained 6-key shape (AD-8)
    assert isinstance(bundle["model"], CalibratedClassifierCV)  # calibrated (Epic-2 contract)
    assert bundle["target_column"] == "original_model"
    assert isinstance(bundle["feature_columns"], list) and bundle["feature_columns"]
    # Story 3.2 close-out (serve parity): the candidate trains on the same
    # question_type_confidence numeric the live router serves with — it must be in
    # feature_columns (get_numeric_feature_columns picks it up from the projected
    # column), and the CSV must carry the question_type text token the router text
    # input uses. Absent these, the candidate's feature schema would diverge from
    # decide.py's and it must not be promoted.
    assert "question_type_confidence" in bundle["feature_columns"]
    header = ds.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert "question_type" in header and "question_type_confidence" in header


def test_build_training_frame_keeps_only_up_rows() -> None:
    """Directly prove the up-only filter drops down/cleared rows (data-independent)."""
    df = pd.DataFrame({
        "label": ["up", "down", "cleared", "up", ""],
        "original_model": ["gpt-5", "wrong-a", "wrong-b", "claude", "gpt-5"],
        "origin_query": ["a", "b", "c", "d", "e"],
    })
    out = build_training_frame(df)
    assert set(out["label"]) == {"up"}                        # only up rows survive
    assert list(out["original_model"]) == ["gpt-5", "claude"]  # down/cleared targets excluded
    assert "wrong-a" not in set(out["original_model"])         # a down-only target is gone


def test_insufficient_data_exits_clean_without_artifact(tmp_path: Path) -> None:
    """A degenerate dataset (one model class) reports insufficient and stages nothing."""
    ds = tmp_path / "tiny.csv"
    with ds.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["origin_query", "original_model", "label", "char_count", "word_count"])
        writer.writeheader()
        for i in range(4):
            writer.writerow({"origin_query": f"do thing {i}", "original_model": "gpt-5",
                             "label": "up", "char_count": 10 + i, "word_count": 3})
    staging = tmp_path / "staging"

    rc = retrain_main(["--dataset", str(ds), "--staging-dir", str(staging)])
    assert rc == 0  # insufficient data is a valid dry-run outcome, not a crash
    assert not (staging / "model_router.joblib").exists()  # nothing staged


def test_thin_multiclass_split_failure_exits_clean(tmp_path: Path) -> None:
    """Multiclass but too thin to stratify: slips past the count guard, fails inside
    train_test_split, and is converted to InsufficientData (exit 0, nothing staged)."""
    ds = tmp_path / "thin.csv"
    with ds.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["origin_query", "original_model", "label", "char_count", "word_count"])
        writer.writeheader()
        rows = [("gpt-5", 10), ("gpt-5", 11), ("claude", 12), ("claude", 13)]  # 2 classes x 2 rows
        for i, (model, cc) in enumerate(rows):
            writer.writerow({"origin_query": f"q {i}", "original_model": model,
                             "label": "up", "char_count": cc, "word_count": 3})
    staging = tmp_path / "staging"

    rc = retrain_main(["--dataset", str(ds), "--staging-dir", str(staging)])
    assert rc == 0
    assert not (staging / "model_router.joblib").exists()


def test_missing_required_column_returns_2(tmp_path: Path) -> None:
    """A CSV missing a required column exits 2 cleanly instead of a raw KeyError traceback."""
    ds = tmp_path / "bad.csv"
    with ds.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["origin_query", "label"])  # no original_model
        writer.writeheader()
        writer.writerow({"origin_query": "hi", "label": "up"})
    rc = retrain_main(["--dataset", str(ds), "--staging-dir", str(tmp_path / "staging")])
    assert rc == 2


def test_missing_dataset_returns_2(tmp_path: Path) -> None:
    rc = retrain_main(["--dataset", str(tmp_path / "nope.csv"), "--staging-dir", str(tmp_path / "staging")])
    assert rc == 2
