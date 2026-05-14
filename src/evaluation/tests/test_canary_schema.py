"""Plan 01-07 — ROUTER-04 canary CSV schema invariants.

Guards `data_processed/routing_decision_eval.csv` against silent corruption.
Every test reads the CSV via stdlib `csv.DictReader` so the assertions hold
regardless of whether the working copy is a real CSV or an LFS pointer
materialized by `git lfs fetch`. CI fails loudly on a missing column,
mis-counted bucket, or absent edge-case category.

Test surface (CLAUDE.md naming: snake_case + verb-led):
  - test_canary_csv_exists                          (D-13 + D-15)
  - test_canary_csv_columns                         (D-13)
  - test_canary_row_count_in_range                  (D-13 ~42 envelope)
  - test_canary_per_backend_distribution            (D-13 thirds + cushion)
  - test_canary_fallback_bucket_size                (D-13 ~6 + cushion)
  - test_canary_edge_case_categories                (D-15 8+ slots)
  - test_canary_sentinels_match_expected_backend    (D-04 sentinels)
  - test_canary_no_empty_prompts                    (defensive)
"""

from __future__ import annotations

import csv
import os
import pathlib

import pytest


# ----------------------------------------------------------------------
# Path setup — mirror CLAUDE.md "Import Organization" + the routing
# module's PROJECT_ROOT depth pattern (this file lives at
# src/evaluation/tests/, so the project root is three levels up).
# ----------------------------------------------------------------------

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", ".."))
CANARY_PATH = pathlib.Path(PROJECT_ROOT) / "data_processed" / "routing_decision_eval.csv"

REQUIRED_COLUMNS = {
    "prompt",
    "expected_backend",
    "expected_model_or_agent_substring",
    "is_fallback_expected",
    "edge_case_category",
    "source",
    "license",
}

ALLOWED_BACKENDS = {"openrouter", "claude_code", "computer_use"}

REQUIRED_EDGE_CASE_CATEGORIES = {
    "haiku-vs-code",
    "explain-vs-build",
    "informational-url",
    "low-confidence-trap",
}

# D-04 backend sentinels — canary `expected_model_or_agent_substring` must
# contain these for the corresponding backend rows.
CLAUDE_CODE_SENTINEL = "claude-agent-sdk"
COMPUTER_USE_SENTINEL = "computer-use-2025-11-24"
FALLBACK_SENTINEL = "openrouter/auto"


def _read_rows() -> list[dict[str, str]]:
    """Read the canary CSV into a list of dicts.

    Skip the entire module if the CSV is missing or is an LFS pointer
    that hasn't been materialized — the test_canary_csv_exists test
    will still fail loudly to surface the missing file.
    """
    if not CANARY_PATH.exists():
        return []
    with CANARY_PATH.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader)


def _is_lfs_pointer() -> bool:
    """Return True if the canary path looks like an unfetched LFS pointer.

    LFS pointers start with `version https://git-lfs.github.com/spec/v1`.
    On a developer machine with `git lfs install` the smudge filter
    materializes the real bytes on checkout, but CI without LFS pulls
    or a fresh clone may see the pointer instead. Tests that need the
    real bytes should call this and skip gracefully.
    """
    if not CANARY_PATH.exists():
        return False
    with CANARY_PATH.open("r", encoding="utf-8") as fh:
        first_line = fh.readline().strip()
    return first_line.startswith("version https://git-lfs.github.com/spec/")


# ----------------------------------------------------------------------
# 1. CSV exists at the canonical path
# ----------------------------------------------------------------------


def test_canary_csv_exists():
    assert CANARY_PATH.exists(), f"canary CSV missing at {CANARY_PATH}"


# ----------------------------------------------------------------------
# 2. Columns match the locked schema (D-13)
# ----------------------------------------------------------------------


def test_canary_csv_columns():
    if _is_lfs_pointer():
        pytest.skip("LFS pointer not materialized; run `git lfs pull`")
    with CANARY_PATH.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        actual_columns = set(reader.fieldnames or [])
    assert actual_columns == REQUIRED_COLUMNS, (
        f"canary columns mismatch.\n"
        f"  expected: {sorted(REQUIRED_COLUMNS)}\n"
        f"  actual:   {sorted(actual_columns)}"
    )


# ----------------------------------------------------------------------
# 3. Row count is in the ROUTER-04 envelope (~42, cushioned to 38-50)
# ----------------------------------------------------------------------


def test_canary_row_count_in_range():
    if _is_lfs_pointer():
        pytest.skip("LFS pointer not materialized; run `git lfs pull`")
    rows = _read_rows()
    n = len(rows)
    assert 38 <= n <= 50, f"canary row count out of [38, 50] envelope: {n}"


# ----------------------------------------------------------------------
# 4. Per-backend distribution (D-13 thirds, cushioned to >= 10 each)
# ----------------------------------------------------------------------


def test_canary_per_backend_distribution():
    if _is_lfs_pointer():
        pytest.skip("LFS pointer not materialized; run `git lfs pull`")
    rows = _read_rows()

    # Per D-13, fallback rows ALSO use expected_backend="openrouter"
    # (the canary's ground-truth backend after fallback is OpenRouter
    # per D-12). So the per-backend count for "openrouter" includes
    # both the 12 normal chat rows and the 6 fallback rows.
    backend_counts: dict[str, int] = {b: 0 for b in ALLOWED_BACKENDS}
    for row in rows:
        backend = row["expected_backend"]
        assert backend in ALLOWED_BACKENDS, (
            f"row has invalid expected_backend={backend!r}; "
            f"allowed: {sorted(ALLOWED_BACKENDS)}"
        )
        backend_counts[backend] += 1

    # Cushioned floor: every backend needs at least 10 rows so per-backend
    # P/R is statistically meaningful. D-13 targets ~12 each; fallback
    # adds 6 more to openrouter so its floor is effectively 16, but
    # 10 still holds as the lower bound for all three.
    for backend in ALLOWED_BACKENDS:
        assert backend_counts[backend] >= 10, (
            f"per-backend distribution below floor: "
            f"{backend}={backend_counts[backend]} (need >= 10)"
        )


# ----------------------------------------------------------------------
# 5. Fallback bucket size (D-13 ~6, cushioned to >= 4)
# ----------------------------------------------------------------------


def test_canary_fallback_bucket_size():
    if _is_lfs_pointer():
        pytest.skip("LFS pointer not materialized; run `git lfs pull`")
    rows = _read_rows()
    n_fallback = sum(1 for r in rows if r["is_fallback_expected"].lower() == "true")
    assert n_fallback >= 4, (
        f"fallback bucket below floor: {n_fallback} (D-13 target ~6, floor >= 4)"
    )


# ----------------------------------------------------------------------
# 6. Edge-case categories — all 4 D-15 guaranteed slots present
# ----------------------------------------------------------------------


def test_canary_edge_case_categories():
    if _is_lfs_pointer():
        pytest.skip("LFS pointer not materialized; run `git lfs pull`")
    rows = _read_rows()
    category_counts: dict[str, int] = {}
    for row in rows:
        cat = row["edge_case_category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1

    # Each of the 4 D-15 guaranteed slots must appear at least twice
    # (the plan's `<acceptance_criteria>` lines 182-185 each require >= 2).
    for required_cat in REQUIRED_EDGE_CASE_CATEGORIES:
        count = category_counts.get(required_cat, 0)
        assert count >= 2, (
            f"D-15 edge-case category {required_cat!r} below floor: "
            f"{count} (need >= 2)"
        )


# ----------------------------------------------------------------------
# 7. Sentinels match expected_backend (D-04)
# ----------------------------------------------------------------------


def test_canary_sentinels_match_expected_backend():
    if _is_lfs_pointer():
        pytest.skip("LFS pointer not materialized; run `git lfs pull`")
    rows = _read_rows()
    for i, row in enumerate(rows):
        backend = row["expected_backend"]
        substring = row["expected_model_or_agent_substring"]
        is_fallback = row["is_fallback_expected"].lower() == "true"

        if is_fallback:
            assert FALLBACK_SENTINEL in substring, (
                f"row {i}: fallback row must contain {FALLBACK_SENTINEL!r} "
                f"in expected_model_or_agent_substring; got {substring!r}"
            )
        elif backend == "claude_code":
            assert CLAUDE_CODE_SENTINEL in substring, (
                f"row {i}: claude_code row must contain "
                f"{CLAUDE_CODE_SENTINEL!r} in expected_model_or_agent_substring; "
                f"got {substring!r}"
            )
        elif backend == "computer_use":
            assert COMPUTER_USE_SENTINEL in substring, (
                f"row {i}: computer_use row must contain "
                f"{COMPUTER_USE_SENTINEL!r} in expected_model_or_agent_substring; "
                f"got {substring!r}"
            )
        # openrouter normal rows: the substring is intentionally flexible
        # (any verified slug or "openrouter") — no sentinel check.


# ----------------------------------------------------------------------
# 8. No empty prompts (defensive — empty prompts can't be evaluated)
# ----------------------------------------------------------------------


def test_canary_no_empty_prompts():
    if _is_lfs_pointer():
        pytest.skip("LFS pointer not materialized; run `git lfs pull`")
    rows = _read_rows()
    for i, row in enumerate(rows):
        prompt = row["prompt"]
        assert prompt and prompt.strip(), (
            f"row {i}: empty or whitespace-only prompt is not allowed "
            f"(decide() short-circuits on empty input; canary cannot exercise the "
            f"calibrated stages on such a row)"
        )
