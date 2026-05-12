# Plan 01 — SECURE-03 — root .gitignore must exclude all 7 secret-bearing patterns
# from the very first commit that touches key handling.
#
# This test is IMPLEMENTED NOW (Wave 0). Every other test in this directory is a
# RED stub until its owning plan lands.

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
GITIGNORE_PATH = REPO_ROOT / ".gitignore"

# The 7 patterns are NON-NEGOTIABLE per CONTEXT D + ROADMAP Phase 1 success
# criterion #5 + REQUIREMENTS.md SECURE-03. Each MUST appear on its own line
# (i.e. with no leading whitespace and no trailing comment) for git's pattern
# matcher to honor it.
REQUIRED_PATTERNS = [
    ".env",
    "*.db",
    "*.db-journal",
    "*.db-wal",
    "__pycache__/",
    ".venv/",
    "chat.db",
]


def _gitignore_lines() -> list[str]:
    if not GITIGNORE_PATH.exists():
        pytest.fail(f".gitignore missing at {GITIGNORE_PATH}")
    return [line.rstrip("\n") for line in GITIGNORE_PATH.read_text().splitlines()]


@pytest.mark.parametrize("pattern", REQUIRED_PATTERNS)
def test_required_pattern_present(pattern):
    """Each SECURE-03 pattern is its own non-commented line in .gitignore."""
    lines = _gitignore_lines()
    assert pattern in lines, (
        f"SECURE-03 violation: required pattern {pattern!r} is missing from "
        f"{GITIGNORE_PATH}. Required patterns: {REQUIRED_PATTERNS}"
    )
