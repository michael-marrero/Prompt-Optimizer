"""Append-only JSONL log of routing decisions (STORE-06 + D-05).

Public surface:

    JSONL_LOG_PATH                     re-exported from apps.api.paths so
                                       downstream code can import it from
                                       either module interchangeably.
    append_routing_decisions_jsonl     async writer — appends one JSON
                                       line per routing decision to
                                       ``.planning/data/routing_decisions.jsonl``.

The writer is invoked from ``apps.api.routes.turn.post_turn`` AFTER
``decide()`` returns (or after a synthesised override decision) AND
BEFORE the adapter is dispatched (D-05 — captures every decision the
brain emitted, including turns the user cancels mid-stream).

Each line carries the eight canonical fields:

    {
      "turn_id":        str,           # secrets.token_urlsafe(12)
      "thread_id":      str,           # path-param from POST /threads/{id}/turn
      "timestamp":      str,           # ISO 8601 UTC with "Z" suffix
      "backend":        str,           # "openrouter" | "claude_code" | "computer_use"
      "model_or_agent": str,           # provider-ready identifier
      "rationale":      str,           # human-readable reason
      "confidence":     float,         # min of per-stage max-probs
      "signals":        dict           # per-stage telemetry
    }

**Append-atomicity (RESEARCH Open Question 4):**
    POSIX ``write(2)`` is append-atomic up to PIPE_BUF (~4 KB on Linux,
    ~512 B on macOS). Our routing-decision rows are well under that
    bound (~200 B typical, ~2 KB worst case with rich signals) so plain
    ``open(path, "a")`` is sufficient — no file lock needed for the
    single-user local server. A future multi-tenant deployment would
    swap this for a per-process queue + dedicated writer, but that is
    out of scope for v1.

**Security domain (RESEARCH §Security Domain + T-03-Disclo):**
    The ``signals`` dict NEVER contains key material — Phase 1
    ``decide()`` composes signals from stage telemetry (task_type,
    confidence floats, rule_fired strings, top-K prediction labels)
    and never embeds user-supplied secrets. Defense in depth: Wave 6's
    ``test_secure_no_key_in_logs.py`` regression-greps this file for
    ``sk-or-v1`` / ``sk-ant-`` / ``Bearer `` patterns after every test
    run so a future signals-dict mutation that smuggled a key in would
    fail CI.

Cross-refs:
    - 03-CONTEXT.md D-05 (jsonl appended BEFORE adapter dispatch)
    - 03-CONTEXT.md specifics line 326 (canonical line shape)
    - 03-CONTEXT.md STORE-06 (offline-analysis log requirement)
    - 03-RESEARCH.md §"Open Question 4" lines 1115-1118 (file-lock
      vs POSIX append-atomic decision)
    - apps/api/paths.py (``JSONL_LOG_PATH`` constant)
    - apps/api/routes/turn.py (the single call site)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from apps.api.paths import JSONL_LOG_PATH

logger = logging.getLogger(__name__)

# Re-export for callers that only need ``JSONL_LOG_PATH`` via this
# module (avoids requiring two imports — one from ``apps.api.paths``
# and one from here — when the call site already needs the writer).
__all__ = ["append_routing_decisions_jsonl", "JSONL_LOG_PATH"]


async def append_routing_decisions_jsonl(
    decision: Any, thread_id: str, turn_id: str
) -> None:
    """Append one JSON line to ``JSONL_LOG_PATH``.

    The function is declared ``async`` to keep the call site uniform
    with the rest of the per-turn write path (``await persist_turn``
    etc.) even though the underlying write is a plain blocking
    ``open + write`` per the Open Question 4 resolution. Single-user
    local server has near-zero concurrency; the blocking write is
    bounded by PIPE_BUF atomicity and finishes in <1 ms typical.

    Args:
      decision:   A ``RoutingDecision``-shaped object exposing
                  ``backend``, ``model_or_agent``, ``rationale``,
                  ``confidence``, ``signals`` attributes. Duck-typed
                  so this module never imports from ``src.routing.*``
                  (the route handler's import edge to Phase 1 is the
                  single import boundary).
      thread_id:  The thread the turn belongs to.
      turn_id:    The per-turn correlation ID generated server-side.

    Side effects:
      - Creates ``JSONL_LOG_PATH.parent`` (default
        ``.planning/data/``) if it does not exist.
      - Appends one UTF-8 JSON line to ``JSONL_LOG_PATH``.

    Never raises on the happy path. A genuinely unwritable filesystem
    would surface as the underlying OSError — the route handler logs
    and continues so a failed log line never blocks a turn.
    """

    # Auto-create parent so a fresh checkout does not need to create
    # ``.planning/data/`` manually before the first turn lands.
    JSONL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # ISO 8601 UTC with the ``Z`` suffix matches the Phase 1 routing
    # telemetry convention and the schema_v0.sql ``-- ISO 8601 UTC``
    # comment on ``decided_at``.
    timestamp = datetime.now(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )

    record = {
        "turn_id": turn_id,
        "thread_id": thread_id,
        "timestamp": timestamp,
        "backend": getattr(decision, "backend", None),
        "model_or_agent": getattr(decision, "model_or_agent", None),
        "rationale": getattr(decision, "rationale", ""),
        "confidence": float(getattr(decision, "confidence", 0.0)),
        "signals": getattr(decision, "signals", None) or {},
    }

    # ``ensure_ascii=False`` preserves the U+2014 em-dash that Phase 1
    # fallback rationales include verbatim (FALLBACK_RATIONALE_SUFFIX
    # = "low confidence — fallback"). Mirrors the
    # ``RoutingDecision.to_json`` choice in src/routing/schema.py:64.
    line = json.dumps(record, ensure_ascii=False) + "\n"

    # Plain blocking append — POSIX ``write(2)`` is atomic up to
    # PIPE_BUF (RESEARCH Open Question 4). The single-user local
    # server has near-zero concurrency on this file; a future
    # multi-tenant deployment would swap this for a queue + writer.
    with open(JSONL_LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(line)
