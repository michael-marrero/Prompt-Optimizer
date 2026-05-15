"""ChatChunk Pydantic v2 discriminated union — the single adapter contract.

Public surface (BACKEND-01, D-01, D-02, D-06, D-14):

    Variants (7 total, ``type`` discriminator literal in parentheses):
        TextDelta     ("text_delta")     incremental assistant tokens
        ToolCall      ("tool_call")      assistant-issued tool invocation
        ToolResult    ("tool_result")    backend-rendered tool result
        FileDiff      ("file_diff")      file-system mutation (Claude Code)
        Screenshot    ("screenshot")     captured screen (computer-use)
        StreamError   ("stream_error")   structured failure mid-stream
        Done          ("done")           terminal chunk with usage / cost

    Type alias and TypeAdapter:
        ChatChunk            Annotated[Union[...], Field(discriminator="type")]
        chat_chunk_adapter   TypeAdapter(ChatChunk) — ingestion helper

The discriminator-driven union lets a JSON payload like
``{"type": "text_delta", "text": "hi"}`` be parsed into the correct
``TextDelta`` instance without manual ``match`` dispatch. Each variant
has a ``Literal[...]`` ``type`` field with a default value so callers
can construct ``TextDelta(text="hi")`` without specifying ``type``.
Pydantic v2 validates the literal at construction time.

Every Phase 2 adapter yields ``AsyncIterator[ChatChunk]``. Phase 3
FastAPI SSE serialises each chunk via ``chunk.model_dump_json()`` and
deserialises via ``chat_chunk_adapter.validate_json(line)`` when
replaying persisted streams.

Cross-refs:
    - 02-RESEARCH.md §"Pattern 1" lines 330-417 (canonical source)
    - 02-CONTEXT.md D-01..D-06 (closed code vocabulary, discriminator)
    - 02-CONTEXT.md D-14 (Screenshot dual ``image_b64`` / ``image_ref``)
    - 02-CONTEXT.md specifics line 267 (Done.routing_signals)
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter


# --------------------------------------------------------------------
# Individual chunk variants — each with a Literal[...] discriminator
# --------------------------------------------------------------------


class TextDelta(BaseModel):
    """Incremental assistant token (D-05: one provider event = one delta)."""

    type: Literal["text_delta"] = "text_delta"
    text: str


class ToolCall(BaseModel):
    """Assistant-issued tool invocation.

    ``tool_call_id`` is set by the adapter; format
    ``tc_<6-char-base32>`` (CONTEXT specifics). ``arguments`` is the
    parsed JSON object from the provider's streaming function-call
    accumulator.
    """

    type: Literal["tool_call"] = "tool_call"
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]


class ToolResult(BaseModel):
    """Backend-rendered tool result keyed by ``tool_call_id``.

    ``content`` is either the text body (most tools) or a structured
    dict (image-returning tools that pre-serialised to JSON).
    ``is_error`` flips True for non-zero exit codes / structured tool
    errors.
    """

    type: Literal["tool_result"] = "tool_result"
    tool_call_id: str
    content: str | dict[str, Any]
    is_error: bool = False


class FileDiff(BaseModel):
    """File-system mutation emitted by the Claude Code adapter.

    Emitted in addition to the underlying ``ToolResult`` so the UI can
    render a diff hunk for Edit/Write tool calls without re-parsing
    the tool result payload.
    """

    type: Literal["file_diff"] = "file_diff"
    tool_call_id: str
    path: str
    diff: str
    operation: Literal["create", "edit", "delete"]


class Screenshot(BaseModel):
    """Captured screen emitted by the computer-use adapter (D-14).

    Phase 2 sets ``image_b64`` directly; Phase 3 STORE-04 conditionally
    swaps in an ``image_ref`` (e.g. a file path or object key) when the
    base64 payload exceeds 256 KB. ``image_format`` defaults to PNG to
    match Playwright's default screenshot encoding.
    """

    type: Literal["screenshot"] = "screenshot"
    step: int
    image_b64: str | None = None
    image_ref: str | None = None
    image_format: Literal["png", "jpeg"] = "png"


class StreamError(BaseModel):
    """Structured failure chunk emitted before a terminal Done (D-06).

    ``code`` is a CLOSED literal vocabulary so callers can ``match`` on
    it exhaustively and so the UI can map each code to a localised
    message. Adding a new code requires a coordinated change across
    adapters and the UI — do not extend casually.
    """

    type: Literal["stream_error"] = "stream_error"
    code: Literal[
        "cost_cap_exceeded",
        "step_cap_exceeded",
        "cancelled",
        "rate_limited",
        "auth_failed",
        "provider_unavailable",
        "timeout",
        "validation_error",
        "internal_error",
    ]
    message: str
    retriable: bool


class Done(BaseModel):
    """Terminal chunk for every stream (D-04: ALWAYS the last chunk).

    All fields are optional because some failure paths emit ``Done``
    with no usage information (auth failure before the first round-
    trip). ``routing_signals`` carries the Phase 1
    ``RoutingDecision.signals`` dict through to Phase 3 storage so a
    persisted turn can be replayed with its original rationale.
    """

    type: Literal["done"] = "done"
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None
    routing_signals: dict[str, Any] | None = None


# --------------------------------------------------------------------
# Discriminated union and TypeAdapter
# --------------------------------------------------------------------

# The canonical adapter return-type alias.
# ``Field(discriminator="type")`` tells Pydantic to look at the
# ``type`` string and pick the matching variant — no fallback parse.
ChatChunk = Annotated[
    Union[
        TextDelta,
        ToolCall,
        ToolResult,
        FileDiff,
        Screenshot,
        StreamError,
        Done,
    ],
    Field(discriminator="type"),
]

# Ingestion helper for tests, replay paths, and Phase 3 SSE consumers.
# Usage:
#     chat_chunk_adapter.validate_python({"type": "text_delta", "text": "hi"})
#     chat_chunk_adapter.validate_json('{"type":"done"}')
chat_chunk_adapter = TypeAdapter(ChatChunk)
