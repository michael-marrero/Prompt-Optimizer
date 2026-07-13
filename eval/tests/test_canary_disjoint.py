"""EVAL-02 — hash-disjointness of the routing canary vs the tuning CSVs.

The routing accuracy number (Plan 03) is only interpretable if the canary is
provably disjoint from the data the routing heads were tuned on. A single leaked
tuning prompt in `eval/data/canary_routing.jsonl` would inflate the score (false
confidence). This test hashes every normalized canary prompt and every
normalized tuning prompt and asserts the two sets do NOT intersect.

Scope of the scan (Open Question 1, resolved in Plan 01's budgets.py): we hash
ONLY the *tuning* CSVs named in `eval.budgets.DISJOINTNESS_TUNING_FILES` — NOT
every `data_processed/*.csv`. In particular `routing_decision_eval.csv` is
EXCLUDED: it is itself an eval set (the 42-row canary precedent), not tuning
data, so hashing it would guarantee a false-positive overlap.

CRITICAL (RESEARCH Pitfall 2 / threat T-10-LFS): if a tuning CSV is an
unmaterialized git-LFS pointer, this test FAILS loudly via pytest.fail(...) — it
must NEVER take a skip path. A silently-green disjointness check would let a
contaminated canary through. Plan 05's eval-gate.yml checks out with
`lfs: true`; locally run `git lfs pull` first.

Stdlib-only and key-free (csv, hashlib, json, pathlib, pytest) — the eval
harness package is NOT imported here — so this gate runs first in CI with zero
API spend.

Cross-refs:
    - eval/budgets.py (DISJOINTNESS_TUNING_FILES — the locked tuning-file set)
    - src/evaluation/tests/test_canary_schema.py:79-92 (LFS-pointer detection)
    - 10-RESEARCH.md §Code Examples lines 438-471 (hashlib + set-intersection)
    - 10-RESEARCH.md §Pitfall 2 (LFS pointer must FAIL not skip)
"""

from __future__ import annotations

import csv
import hashlib
import json
import pathlib

import pytest

from eval.budgets import DISJOINTNESS_TUNING_FILES

# eval/tests/ -> eval/ -> <repo root>
ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA_PROCESSED = ROOT / "data_processed"
CANARY_PATH = ROOT / "eval" / "data" / "canary_routing.jsonl"

LFS_MARK = "version https://git-lfs.github.com/spec/"

# Prompt-bearing columns across the tuning CSVs (mirrors RESEARCH Code Examples).
PROMPT_COLUMNS = ("origin_query", "prompt")


def _norm(prompt: str) -> str:
    """Normalize a prompt before hashing: strip, lowercase, collapse whitespace."""
    return " ".join(prompt.strip().lower().split())


def _h(prompt: str) -> str:
    """SHA-256 hex digest of the normalized prompt."""
    return hashlib.sha256(_norm(prompt).encode("utf-8")).hexdigest()


def _tuning_hashes() -> set[str]:
    """Hash every prompt in the locked tuning-CSV set.

    Scans ONLY the files named in eval.budgets.DISJOINTNESS_TUNING_FILES
    (routing_decision_eval.csv is deliberately absent). Calls pytest.fail —
    never takes a skip path — when a tuning CSV is an unmaterialized LFS
    pointer, so the scan can never go silently green.
    """
    hashes: set[str] = set()
    for name in sorted(DISJOINTNESS_TUNING_FILES):
        csv_path = DATA_PROCESSED / name
        if not csv_path.exists():
            pytest.fail(
                f"tuning CSV {csv_path} is missing — the disjointness scan cannot "
                "run against a partial tuning set; a SKIPPED disjointness check "
                "must never be green (Pitfall 2). Materialize the data."
            )
        with csv_path.open("r", encoding="utf-8") as fh:
            head = fh.readline()
            if head.startswith(LFS_MARK):
                pytest.fail(
                    f"{csv_path} is an unmaterialized git-LFS pointer — run "
                    "`git lfs pull` (CI must check out with lfs: true). A SKIPPED "
                    "disjointness check must never be green (Pitfall 2 / T-10-LFS)."
                )
            fh.seek(0)
            for row in csv.DictReader(fh):
                for col in PROMPT_COLUMNS:
                    value = row.get(col)
                    if value:
                        hashes.add(_h(value))
    return hashes


def _canary_hashes() -> set[str]:
    """Hash every prompt in the frozen routing canary."""
    lines = CANARY_PATH.read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines if line.strip()]
    return {_h(row["prompt"]) for row in rows}


def test_canary_disjoint_from_tuning() -> None:
    """EVAL-02: no canary prompt may collide with any tuning-CSV prompt."""
    overlap = _canary_hashes() & _tuning_hashes()
    assert not overlap, (
        f"EVAL-02 violation: {len(overlap)} canary prompt(s) collide with "
        f"data_processed/ tuning rows (hash overlap). The routing accuracy score "
        f"would be inflated by contamination — reword the offending canary "
        f"prompt(s) to restore disjointness. Overlapping hashes: {sorted(overlap)}"
    )
