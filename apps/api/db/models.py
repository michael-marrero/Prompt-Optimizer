"""Pydantic v2 DB-row models.

Public surface (STORE-02, D-01, D-13):

    Thread              read path; immutable row of ``threads``.
    Message             read path; immutable row of ``messages``.
    RoutingDecision     read path; immutable row of ``routing_decisions``.

    ThreadCreate        write path; POST /threads body (Wave 3).
    ThreadUpdate        write path; PATCH /threads/{id} body (Wave 6).

Read-path models use ``model_config = ConfigDict(frozen=True)`` so a
query result that flows through the request lifecycle can be passed
by reference without fear of mutation by a downstream consumer.
Write-path models stay non-frozen for ergonomic construction in route
handlers (``ThreadCreate.model_validate(await request.json())`` then
mutate ``title`` if needed).

The Pydantic class name ``RoutingDecision`` deliberately overlaps with
the Phase 1 ``src.routing.schema.RoutingDecision`` frozen dataclass.
They are DIFFERENT TYPES with DIFFERENT FIELDS:

    src.routing.schema.RoutingDecision  the in-flight decision
                                         returned by ``decide()``.
                                         5 fields.
    apps.api.db.models.RoutingDecision   the persisted shape stored
                                         in the ``routing_decisions``
                                         SQLite table. 10 fields.

Phase 3 route handlers import both with explicit names:
``from src.routing.schema import RoutingDecision as InFlightDecision``
and ``from apps.api.db.models import RoutingDecision``. Wave 4's
``persist_turn`` does the field projection from the in-flight decision
into the persisted shape.

Cross-refs:
    - 03-CONTEXT.md D-01 (raw aiosqlite + Pydantic + ~10-12 functions)
    - 03-CONTEXT.md D-13 (column set this module mirrors)
    - 03-PATTERNS.md §"Database Layer" lines 33-37 (read vs write split)
    - 03-PATTERNS.md §"Excerpt 3" lines 230-291 (frozen Pydantic shape)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


# --------------------------------------------------------------------
# Read-path models (frozen) — what query functions return.
# --------------------------------------------------------------------


class Thread(BaseModel):
    """Immutable row of the ``threads`` table.

    Field order mirrors the column order in ``schema_v0.sql`` so a
    SELECT-* result can be unpacked positionally without re-ordering.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    created_at: str  # ISO 8601 UTC, ``Z``-suffixed.
    updated_at: str


class Message(BaseModel):
    """Immutable row of the ``messages`` table.

    The closed-vocabulary ``Literal[...]`` on ``role`` and ``status``
    mirrors the schema-level ``CHECK`` constraints in
    ``schema_v0.sql``. A SELECT result that violates the literal (e.g.
    a corrupted row) raises ``pydantic.ValidationError`` at construction
    so the failure mode is loud rather than silent.

    ``content_blocks`` is the JSON-as-string of the non-TextDelta
    ChatChunk list; ``text`` is the collapsed TextDelta text.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    thread_id: str
    role: Literal["user", "assistant"]
    content_blocks: str  # JSON array of non-TextDelta chunks
    text: str
    backend_used: str | None = None
    model_used: str | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    created_at: str
    status: Literal["complete", "error", "cancelled"] = "complete"


class RoutingDecision(BaseModel):
    """Immutable row of the ``routing_decisions`` table.

    Distinct from ``src.routing.schema.RoutingDecision`` (the in-flight
    decision returned by ``decide()``). This class is the PERSISTED
    shape — flatter, with separate per-signal fields the Phase 1
    decision packs into its ``signals`` dict.

    Nullable per-signal fields default to ``None`` because not every
    decision path populates every signal (the override path emits a
    synthesised decision with only ``rationale`` and ``signals``).
    """

    model_config = ConfigDict(frozen=True)

    id: str
    message_id: str
    task_type: str | None = None
    task_confidence: float | None = None
    agentic_intent: int | None = None  # 0/1
    agentic_confidence: float | None = None
    predicted_model: str | None = None
    rationale: str
    signals: str  # JSON of the in-flight decision's signals dict
    decided_at: str


# --------------------------------------------------------------------
# Write-path models (non-frozen) — what route handlers receive.
# --------------------------------------------------------------------


class ThreadCreate(BaseModel):
    """Body of ``POST /api/v1/threads`` (Wave 3).

    A title is required at creation time; the lifespan does NOT
    auto-generate titles. Wave 6's rename endpoint replaces the
    placeholder title once the first user message lands.
    """

    title: str


class ThreadUpdate(BaseModel):
    """Body of ``PATCH /api/v1/threads/{id}`` (Wave 6).

    Partial update — fields absent from the request body are left
    unchanged. Only ``title`` is mutable today; future plans may
    grow ``pinned: bool | None`` etc.
    """

    title: str | None = None
