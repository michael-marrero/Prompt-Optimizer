"""Affirmative ChatChunk-union freeze test (Phase 11, CTRL-02 SC#2).

CTRL-02 SC#2 demands an AFFIRMATIVE proof that the frozen Phase-2
``ChatChunk`` discriminated union is STILL exactly 7 variants and that
``awaiting_approval`` is NOT a member — Phase 11 is backend-only and
adds the control channel WITHOUT touching the streaming wire contract.

This is distinct from the existing byte-for-byte parity guards
(``test_chunks.py`` + the Zod port) which prove the freeze by staying
green-and-unmodified. Here we introspect the union directly and assert
the membership set positively.

``chunks.py`` and ``test_chunks.py`` are NOT modified by this plan — the
acceptance criterion greps ``git diff --stat`` on both to confirm zero
changes.

Cross-refs:
    - 11-01-PLAN Task 3 (action + acceptance criteria)
    - apps/api/backends/chunks.py (the 7-variant Annotated Union)
    - apps/api/backends/tests/test_chunks.py (union-walking precedent)
"""

from __future__ import annotations

import typing


# The frozen Phase-2 discriminator vocabulary — exactly these 7 ``type``
# literals, no more, no fewer. Mirrors the union member order in
# ``chunks.py`` (TextDelta, ToolCall, ToolResult, FileDiff, Screenshot,
# StreamError, Done).
EXPECTED_CHUNK_TYPES = {
    "text_delta",
    "tool_call",
    "tool_result",
    "file_diff",
    "screenshot",
    "stream_error",
    "done",
}


def _chunk_union_members() -> tuple[type, ...]:
    """Return the variant classes inside the ``ChatChunk`` union.

    ``ChatChunk`` is ``Annotated[Union[...], Field(discriminator="type")]``
    so the underlying ``Union`` is the first ``get_args`` element; a
    second ``get_args`` on that Union yields the member classes — the
    same introspection style ``test_chunks.py`` uses on the
    ``StreamError.code`` Literal.
    """

    from apps.api.backends.chunks import ChatChunk

    # First unwrap the Annotated layer to reach the Union, then expand
    # the Union into its member classes.
    annotated_args = typing.get_args(ChatChunk)
    union = annotated_args[0]
    return typing.get_args(union)


def _member_type_literal(member: type) -> str:
    """Return the ``type`` discriminator literal string of a member."""

    type_hint = typing.get_type_hints(member)["type"]
    literal_args = typing.get_args(type_hint)
    # Each member's ``type`` is a single-value Literal (e.g.
    # ``Literal["text_delta"]``); return that one string.
    assert len(literal_args) == 1, (
        f"{member.__name__}.type is not a single-value Literal: {literal_args}"
    )
    return literal_args[0]


def test_chat_chunk_union_has_exactly_seven_members() -> None:
    """The ChatChunk union has EXACTLY 7 members with the frozen
    Phase-2 ``type`` discriminator set — no additions."""

    members = _chunk_union_members()
    assert len(members) == 7, (
        f"ChatChunk union must have exactly 7 members, found {len(members)}: "
        f"{[m.__name__ for m in members]}"
    )

    type_literals = {_member_type_literal(m) for m in members}
    assert type_literals == EXPECTED_CHUNK_TYPES, (
        f"ChatChunk discriminator set drifted: {type_literals} "
        f"!= {EXPECTED_CHUNK_TYPES}"
    )


def test_awaiting_approval_is_not_a_chunk_type() -> None:
    """No union member carries the ``awaiting_approval`` discriminator,
    and no ``awaiting_approval`` / ``turn_start`` member class exists —
    Phase 11's control channel does NOT leak into the streaming wire."""

    members = _chunk_union_members()
    type_literals = {_member_type_literal(m) for m in members}

    assert "awaiting_approval" not in type_literals, (
        "awaiting_approval must NOT be a ChatChunk discriminator literal "
        "(CTRL-02 SC#2 — control channel stays off the streaming wire)"
    )
    assert "turn_start" not in type_literals, (
        "turn_start must NOT be a ChatChunk discriminator literal"
    )

    member_class_names = {m.__name__ for m in members}
    assert "AwaitingApproval" not in member_class_names, (
        "no AwaitingApproval member class may exist in the ChatChunk union"
    )
    assert "TurnStart" not in member_class_names, (
        "no TurnStart member class may exist in the ChatChunk union"
    )
