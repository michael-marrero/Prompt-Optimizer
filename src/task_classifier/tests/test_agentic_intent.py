# Plan 04 — ROUTER-01 — train_agentic_intent.py persists a binary classifier
# to models/agentic_intent_classifier.joblib using the canonical 5-key artifact
# dict shape ({model, vectorizer, scaler, label_encoder, feature_columns}) so
# load_joblib_artifacts() in src/demo/demo_router.py accepts it unmodified.
#
# Tests to be implemented in Plan 04:
#   - test_artifact_dict_has_required_keys()
#   - test_predict_proba_returns_binary_distribution()
#   - test_held_out_precision_recall_above_threshold()  # ROUTER-01 success criterion

import pytest


def test_artifact_dict_has_required_keys_placeholder():
    pytest.skip("Wave 2 — implemented in Plan 04 (ROUTER-01)")


def test_predict_proba_returns_binary_distribution_placeholder():
    pytest.skip("Wave 2 — implemented in Plan 04 (ROUTER-01)")


def test_held_out_precision_recall_above_threshold_placeholder():
    pytest.skip("Wave 2 — implemented in Plan 04 (ROUTER-01)")
