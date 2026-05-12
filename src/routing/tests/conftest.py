"""Shared pytest fixtures for the routing brain test suite.

Session-scoped fixtures load joblib artifacts once per test run; missing
artifacts are skipped, not failed, because Wave 0 ships before the
calibrated/new artifacts in Plans 04 and 05.
"""

import json
import os

import pytest

REPO_ROOT = os.path.abspath(os.path.join(__file__, "..", "..", "..", ".."))
MODELS_DIR = os.path.join(REPO_ROOT, "models")
CONFIG_DIR = os.path.join(REPO_ROOT, "config")

TASK_CLASSIFIER_PATH = os.path.join(MODELS_DIR, "task_type_classifier.joblib")
MODEL_ROUTER_PATH = os.path.join(MODELS_DIR, "model_router.joblib")
AGENTIC_INTENT_PATH = os.path.join(MODELS_DIR, "agentic_intent_classifier.joblib")
MODEL_MAPPING_PATH = os.path.join(CONFIG_DIR, "model_mapping.json")


def _load_joblib_or_skip(path: str, label: str):
    joblib = pytest.importorskip("joblib")
    if not os.path.exists(path):
        pytest.skip(f"{label} not found at {path} — produced by a later plan")
    return joblib.load(path)


@pytest.fixture(scope="session")
def task_artifacts():
    """Calibrated task-type classifier artifact dict (Plan 05)."""
    return _load_joblib_or_skip(TASK_CLASSIFIER_PATH, "task_type_classifier.joblib")


@pytest.fixture(scope="session")
def model_router_artifacts():
    """Calibrated model-router artifact dict (Plan 05)."""
    return _load_joblib_or_skip(MODEL_ROUTER_PATH, "model_router.joblib")


@pytest.fixture(scope="session")
def agentic_intent_artifacts():
    """Agentic-intent binary classifier artifact dict (Plan 04 — NEW)."""
    return _load_joblib_or_skip(AGENTIC_INTENT_PATH, "agentic_intent_classifier.joblib")


@pytest.fixture(scope="session")
def model_mapping():
    """config/model_mapping.json loaded once per session."""
    if not os.path.exists(MODEL_MAPPING_PATH):
        pytest.skip(f"model_mapping.json not found at {MODEL_MAPPING_PATH}")
    with open(MODEL_MAPPING_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)
