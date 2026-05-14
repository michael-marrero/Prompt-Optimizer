# Plan 04 — ROUTER-01 — train_agentic_intent.py persists a binary classifier
# to models/agentic_intent_classifier.joblib using the canonical 5-key artifact
# dict shape ({model, vectorizer, scaler, label_encoder, feature_columns}) so
# load_joblib_artifacts() in src/demo/demo_router.py accepts it unmodified.
#
# Tests to be implemented in Plan 04:
#   - test_artifact_dict_has_required_keys()
#   - test_predict_proba_returns_binary_distribution()
#   - test_held_out_precision_recall_above_threshold()  # ROUTER-01 success criterion
#
# Plan 03 — ROUTER-01 — fills in the dataset-shape contract slice below. The
# remaining three classifier tests stay as named placeholder functions so
# pytest --collect-only still enumerates them.

from pathlib import Path

import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TRAINING_CSV = PROJECT_ROOT / "data_processed" / "agentic_intent_training.csv"


# --------------------------------------------------------------------------- #
# Plan 03 — dataset-shape contract (REQUIREMENT-ID: ROUTER-01 prerequisite)   #
# --------------------------------------------------------------------------- #


def test_dataset_csv_well_formed() -> None:
    """data_processed/agentic_intent_training.csv satisfies the locked schema.

    Mirrors `build_agentic_dataset.py --check`:
      - 4 columns exactly: text, label, source, dataset
      - >= 800 rows (target ~1000)
      - label cardinality is exactly {agentic, conversational}
      - balance is within [0.45, 0.55] for the agentic class
      - no NaN in label column
      - no duplicate (text, label) rows
    """
    if not TRAINING_CSV.exists():
        pytest.skip(
            "data_processed/agentic_intent_training.csv not built yet. "
            "Run `uv run python -m src.task_classifier.build_agentic_dataset` first."
        )

    df = pd.read_csv(TRAINING_CSV)

    expected_columns = {"text", "label", "source", "dataset"}
    assert set(df.columns) == expected_columns, (
        f"Columns {sorted(df.columns)} != expected {sorted(expected_columns)}"
    )

    n = len(df)
    assert 800 <= n <= 1100, f"Row count {n} outside [800, 1100]"

    assert df["label"].notna().all(), "Found NaN in label column"

    labels = set(df["label"].unique())
    assert labels == {"agentic", "conversational"}, (
        f"Label cardinality {sorted(labels)} != {{'agentic', 'conversational'}}"
    )

    n_ag = int((df["label"] == "agentic").sum())
    ag_ratio = n_ag / n
    assert 0.45 <= ag_ratio <= 0.55, (
        f"Class balance out of bounds: agentic={n_ag}/{n} = {ag_ratio:.3f}; "
        f"required 0.45 <= ratio <= 0.55"
    )

    dupes = df.duplicated(subset=["text", "label"]).sum()
    assert dupes == 0, f"Found {dupes} duplicate (text, label) rows"


# --------------------------------------------------------------------------- #
# Plan 04 placeholders — stay RED until Plan 04 implements them.              #
# --------------------------------------------------------------------------- #


def test_artifact_dict_has_required_keys_placeholder():
    pytest.skip("Wave 2 — implemented in Plan 04 (ROUTER-01)")


def test_predict_proba_returns_binary_distribution_placeholder():
    pytest.skip("Wave 2 — implemented in Plan 04 (ROUTER-01)")


def test_held_out_precision_recall_above_threshold_placeholder():
    pytest.skip("Wave 2 — implemented in Plan 04 (ROUTER-01)")
