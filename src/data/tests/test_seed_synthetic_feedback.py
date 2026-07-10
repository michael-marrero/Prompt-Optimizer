"""Story 3.1 — light test for the disposable dry-run seed scaffold.

Confirms the scaffold emits a valid, coherent JSONL pair that the assembler can
read, with a discriminative up/down/cleared mix. Not exhaustive — this module is
a throwaway scaffold, not a safety path.
"""

from __future__ import annotations

from pathlib import Path

from src.data.build_retraining_dataset import assemble_rated_turns, stream_jsonl
from src.data.seed_synthetic_feedback import main, synthesize


def test_synthesize_has_discriminative_mix() -> None:
    _decisions, feedback = synthesize(40)
    sentiments = {f["sentiment"] for f in feedback}
    assert {"up", "down", "cleared"} <= sentiments  # all three present
    # at least one reroute breadcrumb was emitted
    assert any(f["decision"]["signals"].get("rerouted_from") for f in feedback)


def test_seed_is_readable_by_assembler(tmp_path: Path) -> None:
    rc = main(["--count", "30", "--output-dir", str(tmp_path)])
    assert rc == 0
    fb = tmp_path / "routing_feedback.jsonl"
    dec = tmp_path / "routing_decisions.jsonl"
    assert fb.exists() and dec.exists()

    turns = assemble_rated_turns(stream_jsonl(fb))
    assert turns  # non-empty
    labels = {t.label for t in turns.values()}
    assert "up" in labels and "down" in labels
    # every 10th turn cleared-supersedes -> those turns carry the cleared label
    assert any(t.label == "cleared" for t in turns.values())
    # reroute turns expose original != dispatched
    assert any(
        t.original_backend != t.dispatched_backend for t in turns.values()
    )
