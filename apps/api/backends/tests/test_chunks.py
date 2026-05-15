# Plan 00 Task 3 — BACKEND-01 ChatChunk schema test (D-01, D-02, D-06, D-14).
#
# Test contracts:
#   - 7-variant discriminated union: TextDelta, ToolCall, ToolResult,
#     FileDiff, Screenshot, StreamError, Done. Each has a Literal["..."]
#     `type` field defaulted so callers can construct without specifying it.
#   - TypeAdapter(ChatChunk).validate_python({"type": "text_delta", ...})
#     returns the correct typed subclass.
#   - model_dump_json() / chat_chunk_adapter.validate_json() round-trip
#     preserves every field including dict-valued routing_signals.
#   - StreamError("bad_code") raises ValidationError — closed literal
#     vocabulary per D-06.
#   - Screenshot defaults (image_ref=None, image_format="png") match D-14.
#   - Done preserves dict-valued routing_signals through round-trip.

from __future__ import annotations

import json

import pytest


def test_text_delta_default_type_and_round_trip() -> None:
    from apps.api.backends.chunks import TextDelta, chat_chunk_adapter

    td = TextDelta(text="hi")
    assert td.type == "text_delta"
    restored = chat_chunk_adapter.validate_json(td.model_dump_json())
    assert isinstance(restored, TextDelta)
    assert restored.text == "hi"


def test_tool_call_round_trip_with_nested_arguments() -> None:
    from apps.api.backends.chunks import ToolCall, chat_chunk_adapter

    tc = ToolCall(
        tool_call_id="tc_abc123",
        tool_name="Bash",
        arguments={"command": "ls", "timeout": 5},
    )
    assert tc.type == "tool_call"
    restored = chat_chunk_adapter.validate_json(tc.model_dump_json())
    assert isinstance(restored, ToolCall)
    assert restored.tool_call_id == "tc_abc123"
    assert restored.tool_name == "Bash"
    assert restored.arguments == {"command": "ls", "timeout": 5}


def test_tool_result_round_trip_with_error_flag() -> None:
    from apps.api.backends.chunks import ToolResult, chat_chunk_adapter

    tr = ToolResult(
        tool_call_id="tc_abc123",
        content="exit 1: command not found",
        is_error=True,
    )
    assert tr.type == "tool_result"
    restored = chat_chunk_adapter.validate_json(tr.model_dump_json())
    assert isinstance(restored, ToolResult)
    assert restored.is_error is True
    assert restored.content == "exit 1: command not found"


def test_tool_result_accepts_dict_content() -> None:
    from apps.api.backends.chunks import ToolResult

    tr = ToolResult(tool_call_id="tc_x", content={"foo": "bar"}, is_error=False)
    assert tr.content == {"foo": "bar"}


def test_file_diff_round_trip() -> None:
    from apps.api.backends.chunks import FileDiff, chat_chunk_adapter

    fd = FileDiff(
        tool_call_id="tc_a",
        path="src/example.py",
        diff="@@ -1 +1 @@\n-old\n+new\n",
        operation="edit",
    )
    assert fd.type == "file_diff"
    restored = chat_chunk_adapter.validate_json(fd.model_dump_json())
    assert isinstance(restored, FileDiff)
    assert restored.operation == "edit"


def test_screenshot_defaults_match_d14() -> None:
    from apps.api.backends.chunks import Screenshot

    s = Screenshot(step=1, image_b64="abc")
    assert s.type == "screenshot"
    assert s.image_ref is None
    assert s.image_format == "png"
    assert s.step == 1
    assert s.image_b64 == "abc"


def test_stream_error_defaults_and_round_trip() -> None:
    from apps.api.backends.chunks import StreamError, chat_chunk_adapter

    err = StreamError(code="cancelled", message="m", retriable=True)
    assert err.type == "stream_error"
    restored = chat_chunk_adapter.validate_json(err.model_dump_json())
    assert isinstance(restored, StreamError)
    assert restored.code == "cancelled"
    assert restored.message == "m"
    assert restored.retriable is True


def test_stream_error_rejects_invalid_code() -> None:
    """D-06: the ``code`` literal vocabulary is closed."""

    from pydantic import ValidationError

    from apps.api.backends.chunks import StreamError

    with pytest.raises(ValidationError):
        StreamError(code="not_a_code", message="m", retriable=False)


def test_done_default_construction_round_trip() -> None:
    from apps.api.backends.chunks import Done, chat_chunk_adapter

    d = Done()
    assert d.type == "done"
    restored = chat_chunk_adapter.validate_json(d.model_dump_json())
    assert isinstance(restored, Done)
    assert restored.tokens_in is None
    assert restored.tokens_out is None
    assert restored.cost_usd is None
    assert restored.latency_ms is None
    assert restored.routing_signals is None


def test_done_preserves_routing_signals_through_round_trip() -> None:
    from apps.api.backends.chunks import Done, chat_chunk_adapter

    d = Done(
        tokens_in=100,
        tokens_out=50,
        cost_usd=0.0125,
        latency_ms=2500,
        routing_signals={
            "task_type": "coding",
            "agentic_intent": True,
            "rule_fired": "build_keyword",
        },
    )
    payload = d.model_dump_json()
    restored = chat_chunk_adapter.validate_json(payload)
    assert isinstance(restored, Done)
    assert restored.routing_signals == {
        "task_type": "coding",
        "agentic_intent": True,
        "rule_fired": "build_keyword",
    }


def test_chat_chunk_discriminator_routes_to_text_delta() -> None:
    from apps.api.backends.chunks import TextDelta, chat_chunk_adapter

    parsed = chat_chunk_adapter.validate_python(
        {"type": "text_delta", "text": "hi"}
    )
    assert isinstance(parsed, TextDelta)
    assert parsed.text == "hi"


def test_chat_chunk_discriminator_routes_to_done() -> None:
    from apps.api.backends.chunks import Done, chat_chunk_adapter

    parsed = chat_chunk_adapter.validate_python({"type": "done"})
    assert isinstance(parsed, Done)


def test_chat_chunk_discriminator_routes_to_stream_error() -> None:
    from apps.api.backends.chunks import StreamError, chat_chunk_adapter

    parsed = chat_chunk_adapter.validate_python(
        {
            "type": "stream_error",
            "code": "rate_limited",
            "message": "429",
            "retriable": True,
        }
    )
    assert isinstance(parsed, StreamError)
    assert parsed.code == "rate_limited"


def test_chat_chunk_union_has_seven_members() -> None:
    """D-02: exactly 7 discriminator literals in the union."""

    from apps.api.backends.chunks import chat_chunk_adapter

    # Round-trip every literal — if any are missing or extra, this set
    # will not match.
    valid_types = {
        "text_delta",
        "tool_call",
        "tool_result",
        "file_diff",
        "screenshot",
        "stream_error",
        "done",
    }
    for type_str in valid_types:
        # Each minimal payload below construct-validates if the type
        # is part of the union; the discriminator routes it to the
        # matching variant.
        payloads = {
            "text_delta": {"type": "text_delta", "text": "x"},
            "tool_call": {
                "type": "tool_call",
                "tool_call_id": "tc_x",
                "tool_name": "Bash",
                "arguments": {},
            },
            "tool_result": {
                "type": "tool_result",
                "tool_call_id": "tc_x",
                "content": "ok",
            },
            "file_diff": {
                "type": "file_diff",
                "tool_call_id": "tc_x",
                "path": "a",
                "diff": "",
                "operation": "create",
            },
            "screenshot": {"type": "screenshot", "step": 1},
            "stream_error": {
                "type": "stream_error",
                "code": "cancelled",
                "message": "m",
                "retriable": True,
            },
            "done": {"type": "done"},
        }
        parsed = chat_chunk_adapter.validate_python(payloads[type_str])
        assert parsed.type == type_str


def test_chat_chunk_rejects_unknown_discriminator() -> None:
    from pydantic import ValidationError

    from apps.api.backends.chunks import chat_chunk_adapter

    with pytest.raises(ValidationError):
        chat_chunk_adapter.validate_python(
            {"type": "not_a_chunk_type", "text": "hi"}
        )


def test_text_delta_payload_serialises_compact_json() -> None:
    """Phase 3 SSE will serialise each chunk via model_dump_json()."""

    from apps.api.backends.chunks import TextDelta

    td = TextDelta(text="hello")
    payload = td.model_dump_json()
    parsed = json.loads(payload)
    assert parsed == {"type": "text_delta", "text": "hello"}
