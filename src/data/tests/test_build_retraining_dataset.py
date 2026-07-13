"""Story 3.1 — retraining-dataset assembly tests (data-independent).

Builds in-memory routing_feedback.jsonl fixtures in tmp_path — NO dependency
on a materialized seed or chat.db. Proves: the feedback join, the cleared-
supersede rule (AC #2), the original-pick fallback (AC #1), inline feature
attachment, and empty-feedback resilience (AC #4).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from src.data.build_retraining_dataset import assemble_rated_turns, main, stream_jsonl


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")


def _feedback(
    message_id: str,
    sentiment: str,
    timestamp: str,
    *,
    backend: str,
    model: str,
    prompt: str = "write a python function to sort a list",
    rerouted_from: str | None = None,
    rerouted_from_model: str | None = None,
) -> dict:
    signals: dict = {}
    if rerouted_from is not None:
        signals["rerouted_from"] = rerouted_from
        signals["rerouted_from_model"] = rerouted_from_model
    return {
        "sentiment": sentiment,
        "timestamp": timestamp,
        "thread_id": "t1",
        "message_id": message_id,
        "prompt": prompt,
        "decision": {
            "backend": backend,
            "model_or_agent": model,
            "rationale": "x",
            "confidence": 0.9,
            "signals": signals,
        },
    }


def test_cleared_supersedes_prior_rating(tmp_path: Path) -> None:
    fb = tmp_path / "routing_feedback.jsonl"
    _write_jsonl(fb, [
        _feedback("m1", "up", "2026-07-10T00:00:00Z", backend="openrouter", model="gpt-5"),
        _feedback("m1", "cleared", "2026-07-10T00:01:00Z", backend="openrouter", model="gpt-5"),
    ])
    turns = assemble_rated_turns(stream_jsonl(fb))
    assert list(turns.keys()) == ["m1"]  # one row, not two
    assert turns["m1"].label == "cleared"  # latest event wins


def test_original_pick_fallback_when_no_reroute(tmp_path: Path) -> None:
    fb = tmp_path / "routing_feedback.jsonl"
    _write_jsonl(fb, [
        _feedback("m1", "up", "2026-07-10T00:00:00Z", backend="openrouter", model="gpt-5"),
    ])
    t = assemble_rated_turns(stream_jsonl(fb))["m1"]
    assert (t.original_backend, t.original_model) == ("openrouter", "gpt-5")
    assert (t.dispatched_backend, t.dispatched_model) == ("openrouter", "gpt-5")


def test_original_pick_uses_reroute_breadcrumb(tmp_path: Path) -> None:
    fb = tmp_path / "routing_feedback.jsonl"
    _write_jsonl(fb, [
        _feedback(
            "m1", "down", "2026-07-10T00:00:00Z",
            backend="openrouter", model="openrouter/auto",
            rerouted_from="claude_code", rerouted_from_model="anthropic/claude-sonnet-4-5",
        ),
    ])
    t = assemble_rated_turns(stream_jsonl(fb))["m1"]
    assert (t.original_backend, t.original_model) == ("claude_code", "anthropic/claude-sonnet-4-5")
    assert (t.dispatched_backend, t.dispatched_model) == ("openrouter", "openrouter/auto")


def test_end_to_end_csv_one_row_per_turn_with_features(tmp_path: Path) -> None:
    fb = tmp_path / "routing_feedback.jsonl"
    out = tmp_path / "retraining_dataset.csv"
    _write_jsonl(fb, [
        _feedback("m1", "up", "2026-07-10T00:00:00Z", backend="openrouter", model="gpt-5"),
        _feedback("m2", "down", "2026-07-10T00:02:00Z", backend="claude_code", model="anthropic/claude-sonnet-4-5"),
    ])
    rc = main(["--routing-feedback", str(fb), "--output", str(out)])
    assert rc == 0
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert len(rows) == 2
    for col in ("message_id", "origin_query", "original_backend", "dispatched_backend", "label"):
        assert col in rows[0]
    assert "char_count" in rows[0]  # inline handcrafted feature attached


def test_cleared_wins_over_earlier_whole_second_up(tmp_path: Path) -> None:
    """Review P1: a fractional-second `cleared` must supersede a whole-second `up`
    even though `…00.5Z` sorts lexically BELOW `…00Z` ("Z" > ".")."""
    fb = tmp_path / "routing_feedback.jsonl"
    _write_jsonl(fb, [
        _feedback("m1", "up", "2026-07-10T00:00:00Z", backend="openrouter", model="gpt-5"),
        _feedback("m1", "cleared", "2026-07-10T00:00:00.500000Z", backend="openrouter", model="gpt-5"),
    ])
    turns = assemble_rated_turns(stream_jsonl(fb))
    assert turns["m1"].label == "cleared"  # chronological, not lexical


def test_malformed_records_warn_and_skip(tmp_path: Path) -> None:
    """Review P2: a non-object line or non-dict decision/signals must not abort the build."""
    fb = tmp_path / "routing_feedback.jsonl"
    with fb.open("w", encoding="utf-8") as fh:
        fh.write("[]\n")            # valid JSON, not an object
        fh.write("42\n")            # valid JSON scalar
        fh.write("not json at all\n")  # JSONDecodeError
        # a record whose decision is a non-empty non-dict
        fh.write(json.dumps({"sentiment": "up", "timestamp": "2026-07-10T00:00:00Z",
                             "message_id": "bad", "prompt": "hi", "decision": "oops"}) + "\n")
        # a well-formed record
        fh.write(json.dumps(_feedback("good", "down", "2026-07-10T00:01:00Z",
                                      backend="claude_code", model="anthropic/claude-sonnet-4-5")) + "\n")
    turns = assemble_rated_turns(stream_jsonl(fb))
    assert set(turns) == {"bad", "good"}  # both survive; nothing crashed
    assert turns["bad"].dispatched_backend == ""  # non-dict decision -> empty routes
    assert turns["good"].label == "down"


def test_empty_feedback_writes_header_only(tmp_path: Path) -> None:
    out = tmp_path / "retraining_dataset.csv"
    rc = main(["--routing-feedback", str(tmp_path / "absent.jsonl"), "--output", str(out)])
    assert rc == 0
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1  # header only, no rows
    assert "label" in lines[0]
