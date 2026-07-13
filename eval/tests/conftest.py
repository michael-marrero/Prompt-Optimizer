"""Shared pytest fixtures for the Layer-0 eval test suite.

Mirrors `src/routing/tests/conftest.py` (the routing-brain conftest) but is
adjusted for this directory's depth: `eval/tests/` is two parents below the
repo root, so `PROJECT_ROOT = Path(__file__).resolve().parents[2]` (RESEARCH
§Project Constraints). This file MUST live inside `eval/tests/` — pytest runs in
`--import-mode=importlib` (pyproject.toml), so a repo-root conftest would not be
discovered for this package (RESEARCH Pitfall 3).

The Layer-0 tests (`test_canary_disjoint.py`, `test_import_graph.py`) are
stdlib-only and key-free; the fixtures here expose stable paths so the tests do
not each re-derive the project root.

Cross-refs:
    - src/routing/tests/conftest.py (PROJECT_ROOT depth + skip idiom)
    - eval/budgets.py (DISJOINTNESS_TUNING_FILES — the tuning-CSV set)
    - 10-PATTERNS.md §eval/tests/conftest.py
"""

from __future__ import annotations

import pathlib

import pytest

# eval/tests/ -> eval/ -> <repo root>
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA_PROCESSED_DIR = PROJECT_ROOT / "data_processed"
CANARY_PATH = PROJECT_ROOT / "eval" / "data" / "canary_routing.jsonl"


@pytest.fixture(scope="session")
def project_root() -> pathlib.Path:
    """Absolute path to the repository root (eval/tests/ is two levels down)."""
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def canary_path() -> pathlib.Path:
    """Absolute path to the frozen routing canary JSONL."""
    return CANARY_PATH


@pytest.fixture(scope="session")
def data_processed_dir() -> pathlib.Path:
    """Absolute path to the data_processed/ tuning-CSV directory."""
    return DATA_PROCESSED_DIR
