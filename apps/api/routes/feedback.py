"""POST /api/v1/feedback — append-only routing-feedback log (UI-15, D-11..D-14).

Public surface:

    router    APIRouter(prefix="/api/v1", tags=["feedback"])

Why this endpoint exists:

    The browser cannot write the filesystem, so the thumbs-up/down
    feedback affordance in the chat UI (UI-15) POSTs a D-12 full-context
    row here and FastAPI appends it to ``FEEDBACK_LOG_PATH``
    (``.planning/data/routing_feedback.jsonl`` under the user's home).
    The log is the offline-analysis dataset for tuning the routing
    brain — every row pairs the prompt + the routing decision the brain
    emitted with the user's sentiment.

Append contract (mirrors ``apps/api/jsonl_log.py`` verbatim):

    - ``FEEDBACK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)`` —
      a fresh checkout never needs to pre-create ``.planning/data/``.
    - The ``timestamp`` is stamped SERVER-SIDE
      (``datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")``)
      — the client clock is never trusted (D-14).
    - One ``json.dumps(record, ensure_ascii=False) + "\\n"`` line per
      call via a plain blocking append (append-only per D-13 — no
      read-modify-write; POSIX ``write(2)`` is atomic up to PIPE_BUF and
      feedback rows are well under that bound).

D-11 authority resolution (surfaced in the plan SUMMARY):

    This endpoint logs BOTH ``up`` and ``down`` (and ``cleared``)
    sentiments. CONTEXT D-11 is a locked user decision and is
    AUTHORITATIVE over UI-SPEC §13's earlier wording (which reserved
    up-logging for v2 and called the up signal "silent"). Both
    sentiments durably land here.

Security (T-05-01-FB-KEY — Information Disclosure, T-05-01-FB-VAL — Tampering):

    - ``model_config = ConfigDict(extra="forbid")`` on both body models
      and a closed ``Literal["up","down","cleared"]`` on ``sentiment``
      reject unknown fields / typo'd sentiments with 422 (V5 input
      validation, T-05-01-FB-VAL).
    - Feedback rows legitimately carry the routing decision's
      ``signals``, which never hold key material in normal operation
      (Phase 1 composes signals from stage telemetry only). As defense
      in depth against a future signals-shape change (or a hostile
      client smuggling a key-shaped value into ``signals``), the
      serialised line is passed through the SAME ``_redact_text`` the
      logging RedactionFilter uses BEFORE it is written to disk, so a
      ``sk-``/``sk-ant-``/``Bearer`` shape can never land in the log
      (T-05-01-FB-KEY; mirrors ``test_secure_no_key_in_logs.py``).

Cross-refs:
    - 05-PATTERNS.md "apps/api/routes/feedback.py" + "JSONL append writer"
    - apps/api/jsonl_log.py:append_routing_decisions_jsonl (writer template)
    - apps/api/backends/logging_filter.py:_redact_text (no-key-on-disk guard)
    - apps/api/paths.py:FEEDBACK_LOG_PATH
    - 05-CONTEXT.md D-11..D-14
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from apps.api.backends.logging_filter import _redact_text
from apps.api.paths import FEEDBACK_LOG_PATH

# ``__name__`` resolves to ``apps.api.routes.feedback`` so the Phase 2
# RedactionFilter on the root logger catches every record. NEVER print().
logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1", tags=["feedback"])


# --------------------------------------------------------------------
# Pydantic v2 request models — extra="forbid" + closed sentiment Literal
# --------------------------------------------------------------------


class FeedbackDecision(BaseModel):
    """The routing decision the UI is giving feedback on (D-12).

    Mirrors the ``RoutingDecision`` shape the SSE ``routing_decision``
    event carries so the UI can round-trip the chip payload verbatim.
    ``extra="forbid"`` rejects unknown fields (T-05-01-FB-VAL).
    """

    model_config = ConfigDict(extra="forbid")

    backend: str
    model_or_agent: str
    rationale: str
    confidence: float
    signals: dict


class FeedbackRequest(BaseModel):
    """Body of ``POST /api/v1/feedback`` (the D-12 full-context row).

    The client NEVER sends a timestamp — the server stamps it (D-14).
    The closed ``Literal`` on ``sentiment`` returns 422 on a typo
    instead of silently logging an unknown sentiment.
    """

    model_config = ConfigDict(extra="forbid")

    sentiment: Literal["up", "down", "cleared"]
    thread_id: str
    message_id: str
    prompt: str
    decision: FeedbackDecision


# --------------------------------------------------------------------
# The endpoint — POST /api/v1/feedback
# --------------------------------------------------------------------


@router.post("/feedback")
async def post_feedback(body: FeedbackRequest) -> dict:
    """Append one D-12 feedback row to ``FEEDBACK_LOG_PATH``.

    Returns ``{"ok": True}`` on success. The append is append-only
    (D-13) — no read-modify-write — and the parent directory is
    auto-created so a fresh checkout works without manual setup.
    """

    # Auto-create parent so a fresh checkout does not need to create
    # ``.planning/data/`` manually before the first feedback row lands.
    FEEDBACK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # ISO 8601 UTC with the ``Z`` suffix — stamped SERVER-SIDE (D-14).
    # The client clock is never trusted.
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    record = {
        "sentiment": body.sentiment,
        "timestamp": timestamp,
        "thread_id": body.thread_id,
        "message_id": body.message_id,
        "prompt": body.prompt,
        "decision": {
            "backend": body.decision.backend,
            "model_or_agent": body.decision.model_or_agent,
            "rationale": body.decision.rationale,
            "confidence": body.decision.confidence,
            "signals": body.decision.signals,
        },
    }

    # ``ensure_ascii=False`` preserves the U+2014 em-dash that Phase 1
    # fallback rationales include verbatim. Mirrors jsonl_log.py.
    line = json.dumps(record, ensure_ascii=False)

    # T-05-01-FB-KEY defense in depth: redact any sk-/sk-ant-/Bearer
    # shape BEFORE the line lands on disk. Feedback rows carry no key
    # material in normal operation, but a hostile client could smuggle a
    # key-shaped value into ``signals``; the same _redact_text the
    # logging filter uses guarantees no key shape ever persists.
    #
    # WR-02 data-fidelity note (BY DESIGN): _redact_text operates on the
    # whole serialized JSON line, blind to JSON structure. Any key-shaped
    # substring ANYWHERE in the row — including a legitimate ``prompt`` or
    # ``rationale`` value where a user pasted an example token to ask about
    # it — is redacted to the mask, not just smuggled keys in ``signals``.
    # This is an accepted security-over-fidelity tradeoff: the offline
    # analysis dataset may lose a rare key-shaped substring in prose, but
    # the log can never persist a real key. If fidelity matters more than
    # this belt later, narrow the redaction to the ``signals`` sub-object
    # before serialization.
    line = _redact_text(line) + "\n"

    # Plain blocking append — POSIX ``write(2)`` is atomic up to
    # PIPE_BUF (same Open Question 4 resolution as jsonl_log.py). The
    # single-user local server has near-zero concurrency on this file.
    with open(FEEDBACK_LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(line)

    logger.info(
        "feedback_logged sentiment=%s thread_id=%s message_id=%s",
        body.sentiment,
        body.thread_id,
        body.message_id,
    )

    return {"ok": True}
