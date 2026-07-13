"""POST /api/v1/turns/{turn_id}/control — per-turn control channel (CTRL-01).

Public surface (D-04, D-07):

    router        APIRouter(prefix="/api/v1", tags=["control"])
    post_control  ``POST /turns/{turn_id}/control`` — enqueue a control
                  command onto the addressed live turn's mailbox and
                  persist a control_events audit row, OR 404 when the
                  turn is unknown/finished.

Why this endpoint exists:

    A control command (approve / pause / interrupt / redirect / take-over)
    must be deliverable to an IN-FLIGHT turn from a CONCURRENT request
    while the turn's SSE stream is still open. The turn loop owns one
    ``ControlMailbox`` per live turn, registered under its ``turn_id`` in
    ``app.state.control_registry`` (seeded in lifespan, registered in
    ``turn.py`` before the try, deregistered in its finally). This route
    is the ingress: it looks the mailbox up by ``turn_id`` and either
    enqueues (202) or 404s.

Contract (D-04 / D-07):

    - 202 path: the registry has a LIVE mailbox for ``turn_id`` →
      ``await mailbox.enqueue(body)`` THEN persist exactly one
      ``control_events`` row (persist-only-on-202, D-07) and return
      ``{"status": "accepted", "turn_id": turn_id}``.
    - 404 path: ``registry.get(turn_id) is None`` (unknown OR already
      finished/deregistered turn) → ``HTTPException(404)`` with NO
      persistence and NO partial enqueue (D-07).
    - 422: an unknown ``kind`` outside the closed ``ControlMessage``
      Literal is rejected by Pydantic before the handler body runs.
    - 413: an oversize ``payload`` (serialised length > the cap) is
      rejected BEFORE enqueue/persist (V5 input validation, T-11-06).

Security (T-11-05 / T-11-06 / T-11-09):

    - ``turn_id`` is a ``secrets.token_urlsafe(12)`` (~72-bit) capability
      minted in ``turn.py``; a control POST 404s unless the EXACT live
      ``turn_id`` is known, so a control command cannot be injected into
      another turn (T-11-05). Single-user local removes multi-tenant
      exposure.
    - The route-layer size cap on ``json.dumps(payload)`` returns 413
      before any enqueue/persist (T-11-06 DoS); ``extra="forbid"`` on
      ``ControlMessage`` (Plan 01) rejects shape inflation.
    - ``logging.getLogger`` (NEVER ``print``) so the Phase 2 redaction
      filter catches every record; the opaque ``payload`` is NOT logged
      verbatim (T-11-09).

Cross-refs:
    - 11-02-PLAN Task 1 (action + acceptance criteria)
    - apps/api/control/mailbox.py (ControlMessage + ControlMailbox)
    - apps/api/control/registry.py (get helper over app.state.control_registry)
    - apps/api/db/queries.py:insert_control_event (the 202-path writer)
    - apps/api/routes/feedback.py (the non-SSE POST route shape)
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Request

from apps.api.control.mailbox import ControlMessage
from apps.api.db.queries import insert_control_event

# ``__name__`` resolves to ``apps.api.routes.control`` so the Phase 2
# RedactionFilter on the root logger catches every record. NEVER print().
logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1", tags=["control"])


# Route-layer size cap on the opaque ``payload`` (T-11-06 DoS). The
# substrate never interprets ``payload``; the cap bounds the serialised
# length so an oversize body is rejected with 413 BEFORE enqueue/persist.
MAX_CONTROL_PAYLOAD_CHARS = 16384


@router.post("/turns/{turn_id}/control", status_code=202)
async def post_control(
    turn_id: str, body: ControlMessage, request: Request
) -> dict:
    """Deliver a control command to the addressed live turn (D-04/D-07).

    Returns 202 + persists exactly one audit row when ``turn_id`` names a
    live registered mailbox; 404 (no persistence) when it does not; 413
    when the payload exceeds the size cap; 422 (via Pydantic) for an
    unknown ``kind``.
    """

    # V5 input validation / T-11-06 DoS: reject an oversize opaque payload
    # BEFORE any enqueue or persist. The substrate never interprets the
    # payload, so a serialised-length cap is the right bound.
    if body.payload is not None:
        payload_len = len(json.dumps(body.payload))
        if payload_len > MAX_CONTROL_PAYLOAD_CHARS:
            raise HTTPException(
                status_code=413,
                detail="control payload too large",
            )

    # D-04: look the live mailbox up by turn_id. ``registry.get`` returns
    # None for an unknown OR already-finished/deregistered turn — both
    # 404 with NO persistence (D-07 persist-only-on-202).
    registry = getattr(request.app.state, "control_registry", None)
    mailbox = registry.get(turn_id) if registry is not None else None
    if mailbox is None:
        raise HTTPException(
            status_code=404, detail="unknown or finished turn_id"
        )

    # 202 path: enqueue FIRST, THEN persist exactly one audit row (D-07).
    # ``insert_control_event`` does not commit (it composes inside larger
    # BEGIN/COMMIT blocks), so this route owns the commit.
    await mailbox.enqueue(body)
    await insert_control_event(
        request.app.state.db, turn_id=turn_id, message=body
    )
    await request.app.state.db.commit()

    logger.info("control_accepted turn_id=%s kind=%s", turn_id, body.kind)

    return {"status": "accepted", "turn_id": turn_id}
