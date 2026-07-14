"""Story 5.2 review F5 — routing confidence persistence coercion.

A non-finite `decision.confidence` (NaN/inf) must NOT reach the DB: it would
later serialise to bare `NaN` (invalid JSON) and break the strict client parse
of the ENTIRE GET-messages response — whole-thread restore failure, not one row.
`insert_routing_decision` coerces non-finite → NULL, which restores as the safe
no-nudge default. Finite values round-trip unchanged.

Direct DB round-trip (no httpx) — open_db(:memory:) + the real insert/read paths.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pytest

from apps.api.db.connect import open_db
from apps.api.db.migrate import up_to_latest
from apps.api.db.queries import (
    create_thread,
    get_thread_messages_with_routing,
    insert_assistant_message_with_blocks,
    insert_routing_decision,
)


@dataclass
class _FakeDecision:
    """Duck-typed stand-in for src.routing.schema.RoutingDecision."""

    model_or_agent: str
    rationale: str
    confidence: float
    signals: dict


async def _persisted_confidence(confidence: float) -> float | None:
    """Insert a routing decision with the given confidence; return what reads back."""
    db = await open_db(":memory:")
    try:
        await up_to_latest(db)
        thread = await create_thread(db, title="t")
        await insert_assistant_message_with_blocks(
            db,
            message_id="m1",
            thread_id=thread.id,
            text="answer",
            content_blocks="[]",
            backend_used="openrouter",
            model_used="openai/gpt-5",
            cost_usd=None,
            latency_ms=None,
            tokens_in=None,
            tokens_out=None,
        )
        await insert_routing_decision(
            db,
            decision_id="d1",
            message_id="m1",
            decision=_FakeDecision(
                model_or_agent="openai/gpt-5",
                rationale="close call",
                confidence=confidence,
                signals={},
            ),
        )
        await db.commit()
        rows = await get_thread_messages_with_routing(db, thread.id)
        [assistant] = [r for r in rows if r["role"] == "assistant"]
        return assistant["routing"]["confidence"]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_finite_confidence_round_trips() -> None:
    assert await _persisted_confidence(0.4) == 0.4


@pytest.mark.asyncio
async def test_nan_confidence_coerced_to_null() -> None:
    assert await _persisted_confidence(math.nan) is None


@pytest.mark.asyncio
async def test_inf_confidence_coerced_to_null() -> None:
    assert await _persisted_confidence(math.inf) is None
