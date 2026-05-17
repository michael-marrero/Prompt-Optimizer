"""Typed async DB query functions.

Public surface (STORE-02, D-01, D-04, D-05):

    create_thread                       insert + return Thread.
    get_thread                          Thread | None by id.
    list_threads                        list[Thread] paginated.
    update_thread_title                 Thread | None (returns updated).
    delete_thread                       bool (rowcount > 0).
    get_thread_messages                 list[Message] for one thread.
    insert_user_message                 None — caller commits.
    insert_assistant_message_with_blocks None — caller commits.
    insert_routing_decision             None — caller commits.
    persist_turn                        None — ONE BEGIN/COMMIT for the
                                        per-turn write triple (D-04).
    read_schema_version                 int — cached at lifespan.

Every function takes ``db: aiosqlite.Connection`` as the first arg,
typed kwargs for the rest, and returns a Pydantic model (or None /
bool / int). Parameter substitution is ALWAYS via ``?`` placeholders
— f-string SQL is forbidden by the T-03-SQLi threat (RESEARCH §
Security Domain). The acceptance criteria for Wave 1 enforce this
with a negative grep on ``execute\\(f"``.

The three INSERT helpers (``insert_user_message``,
``insert_assistant_message_with_blocks``, ``insert_routing_decision``)
deliberately DO NOT call ``await db.commit()``. They are the
building blocks of ``persist_turn`` — a single BEGIN/COMMIT block
that writes the per-turn triple atomically (D-04). Standalone
callers (Wave 6 thread CRUD) commit explicitly inside their own
helper.

ID generation: ``secrets.token_urlsafe(12)`` per CONTEXT discretion
line 176. The result is ~16 chars of URL-safe base64; paste-safe in
JSON request bodies, collision-free at single-user scale, no
external dep on UUID/ULID.

Cross-refs:
    - 03-CONTEXT.md D-01 (raw aiosqlite + Pydantic + ~10-12 functions)
    - 03-CONTEXT.md D-04 (one transaction per turn on Done)
    - 03-CONTEXT.md D-05 (NO per-chunk DB writes)
    - 03-CONTEXT.md D-13 (column set + ON DELETE CASCADE)
    - 03-CONTEXT.md discretion line 176 (secrets.token_urlsafe(12))
    - 03-RESEARCH.md §"Pattern 3" lines 311-355 (persist_turn canonical)
    - 03-RESEARCH.md §"Pattern 4" lines 357-383 (single shared connection)
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from apps.api.blobs import (
    _collect_blob_refs_from_content_blocks,
    _is_inside_blobs_dir,
)
from apps.api.db.models import Message, RoutingDecision, Thread

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------
# Internal helpers
# --------------------------------------------------------------------


def _now_iso() -> str:
    """Return an ISO 8601 UTC timestamp with ``Z`` suffix.

    Matches the ``-- ISO 8601 UTC`` comment in ``schema_v0.sql``.
    ``datetime.isoformat()`` produces ``+00:00`` for UTC; we swap the
    suffix so downstream consumers see the canonical ``Z`` form that
    the Phase 1 routing telemetry already uses.
    """

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_id() -> str:
    """Generate a paste-safe, collision-free ID.

    ``secrets.token_urlsafe(12)`` returns ~16 chars of URL-safe base64
    (12 random bytes encoded with `=` stripping). Phase 1 already uses
    the stdlib ``secrets`` module; no new dep.
    """

    return secrets.token_urlsafe(12)


# --------------------------------------------------------------------
# Thread CRUD
# --------------------------------------------------------------------


async def create_thread(db: aiosqlite.Connection, *, title: str) -> Thread:
    """Insert a new thread and return the persisted ``Thread`` model.

    Generates the ID server-side via ``_new_id`` so callers cannot
    spoof an ID. ``created_at`` and ``updated_at`` are both set to
    the SAME ``_now_iso()`` value at creation so ``updated_at >=
    created_at`` is an invariant the UI can rely on.
    """

    new_id = _new_id()
    now = _now_iso()
    await db.execute(
        "INSERT INTO threads (id, title, created_at, updated_at)"
        " VALUES (?, ?, ?, ?)",
        (new_id, title, now, now),
    )
    await db.commit()
    return Thread(id=new_id, title=title, created_at=now, updated_at=now)


async def get_thread(
    db: aiosqlite.Connection, thread_id: str
) -> Thread | None:
    """Return one ``Thread`` row or ``None`` when the id is unknown.

    Parameterised ``WHERE id = ?`` placeholder — never f-string
    interpolation (T-03-SQLi).
    """

    async with db.execute(
        "SELECT id, title, created_at, updated_at FROM threads"
        " WHERE id = ?",
        (thread_id,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    return Thread(
        id=row[0], title=row[1], created_at=row[2], updated_at=row[3]
    )


async def list_threads(
    db: aiosqlite.Connection, *, limit: int = 100, offset: int = 0
) -> list[Thread]:
    """Return threads ordered newest-first.

    ``ORDER BY created_at DESC`` matches the Phase 4 chat sidebar
    expectation (most-recent on top). ``limit`` / ``offset`` are
    bound via parameterised placeholders, never string interpolation.
    """

    threads: list[Thread] = []
    async with db.execute(
        "SELECT id, title, created_at, updated_at FROM threads"
        " ORDER BY created_at DESC"
        " LIMIT ? OFFSET ?",
        (limit, offset),
    ) as cur:
        async for row in cur:
            threads.append(
                Thread(
                    id=row[0],
                    title=row[1],
                    created_at=row[2],
                    updated_at=row[3],
                )
            )
    return threads


async def update_thread_title(
    db: aiosqlite.Connection, thread_id: str, title: str
) -> Thread | None:
    """Update the thread's title + ``updated_at`` and return the row.

    Returns ``None`` when ``thread_id`` is unknown (mirrors
    ``get_thread`` behaviour). The follow-up SELECT through
    ``get_thread`` keeps the response shape consistent so route
    handlers can just ``return await update_thread_title(...)``.
    """

    now = _now_iso()
    await db.execute(
        "UPDATE threads SET title = ?, updated_at = ? WHERE id = ?",
        (title, now, thread_id),
    )
    await db.commit()
    return await get_thread(db, thread_id)


async def delete_thread(
    db: aiosqlite.Connection, thread_id: str
) -> bool:
    """Delete a thread and cascade-unlink any referenced blob files.

    Order matters (D-14):

        1. SELECT ``content_blocks`` for every message in the thread.
        2. JSON-walk each row to collect every ``image_ref`` /
           ``diff_ref`` Path.
        3. Path-traversal-defensively unlink each file inside
           ``BLOBS_DIR`` (``_is_inside_blobs_dir`` guards each entry
           — tampered DB rows pointing outside BLOBS_DIR are SKIPPED,
           not unlinked).
        4. THEN run ``DELETE FROM threads WHERE id = ?`` — the
           foreign-key ``ON DELETE CASCADE`` (D-13) plus
           ``PRAGMA foreign_keys=ON`` (D-03) clean up the dependent
           ``messages`` and ``routing_decisions`` rows atomically.

    Rationale: blobs FIRST means an interrupted delete (process killed
    between unlink and DB delete) leaves orphan blobs (recoverable by
    a future ``make gc-blobs``) rather than stale DB rows pointing to
    missing files. The reverse order — DB first, blobs after — would
    leak storage AND break the invariant that every persisted
    ``image_ref`` resolves to a real file on disk.

    Returns ``True`` iff a thread row was removed (rowcount > 0).
    Unknown thread ids return ``False`` (idempotent).

    Cross-refs:
        - 03-CONTEXT.md D-14 (cascade unlink semantics)
        - 03-RESEARCH.md §"Pattern 10" lines 670-671 (order rationale)
        - 03-RESEARCH.md §"Security Domain" lines 1198-1200 (path
          traversal defense at unlink time)
    """

    # Step 1: collect every blob ref referenced by this thread's
    # messages BEFORE we delete the rows (otherwise the cascade would
    # nuke our source of truth for the ref paths).
    async with db.execute(
        "SELECT content_blocks FROM messages WHERE thread_id = ?",
        (thread_id,),
    ) as cur:
        rows = await cur.fetchall()

    refs_to_unlink: list = []
    for row in rows:
        content_blocks_json = row[0] if row else None
        if content_blocks_json:
            refs_to_unlink.extend(
                _collect_blob_refs_from_content_blocks(content_blocks_json)
            )

    # Step 2: unlink each ref inside BLOBS_DIR. T-03-Path defense —
    # any ref that resolves outside BLOBS_DIR (tampered DB row) is
    # SKIPPED, never touched. ``missing_ok=True`` makes this safe to
    # replay even if a prior partial delete already removed the file.
    for ref in refs_to_unlink:
        if _is_inside_blobs_dir(ref):
            ref.unlink(missing_ok=True)
        else:
            logger.warning(
                "skipping unlink of out-of-bounds blob ref: %s", ref
            )

    # Step 3: DB DELETE — FK CASCADE handles messages +
    # routing_decisions in one statement.
    async with db.execute(
        "DELETE FROM threads WHERE id = ?", (thread_id,)
    ) as cur:
        deleted = cur.rowcount > 0
    await db.commit()
    return deleted


async def get_thread_messages(
    db: aiosqlite.Connection, thread_id: str
) -> list[Message]:
    """Return messages for one thread ordered oldest-first.

    ``ORDER BY created_at ASC`` matches the chat UI's chronological
    rendering. The ``idx_messages_thread_id_created_at`` index
    introduced in schema_v1 is a perfect prefix match for this
    query (composite index on ``thread_id ASC, created_at ASC``).
    """

    messages: list[Message] = []
    async with db.execute(
        "SELECT id, thread_id, role, content_blocks, text,"
        " backend_used, model_used, cost_usd, latency_ms, tokens_in,"
        " tokens_out, created_at, status"
        " FROM messages"
        " WHERE thread_id = ?"
        " ORDER BY created_at ASC",
        (thread_id,),
    ) as cur:
        async for row in cur:
            messages.append(
                Message(
                    id=row[0],
                    thread_id=row[1],
                    role=row[2],
                    content_blocks=row[3],
                    text=row[4],
                    backend_used=row[5],
                    model_used=row[6],
                    cost_usd=row[7],
                    latency_ms=row[8],
                    tokens_in=row[9],
                    tokens_out=row[10],
                    created_at=row[11],
                    status=row[12],
                )
            )
    return messages


# --------------------------------------------------------------------
# Per-turn write helpers (NO commit — persist_turn owns the commit)
# --------------------------------------------------------------------


async def insert_user_message(
    db: aiosqlite.Connection,
    *,
    message_id: str,
    thread_id: str,
    text: str,
) -> None:
    """Insert a user-role message row WITHOUT committing.

    Called inside ``persist_turn``'s explicit BEGIN/COMMIT block. The
    ``content_blocks`` column is set to ``'[]'`` because user messages
    are plain text (no tool calls, no diffs, no screenshots).
    """

    await db.execute(
        "INSERT INTO messages (id, thread_id, role, content_blocks,"
        " text, created_at, status)"
        " VALUES (?, ?, 'user', '[]', ?, ?, 'complete')",
        (message_id, thread_id, text, _now_iso()),
    )


async def insert_assistant_message_with_blocks(
    db: aiosqlite.Connection,
    *,
    message_id: str,
    thread_id: str,
    text: str,
    content_blocks: str,
    backend_used: str | None,
    model_used: str | None,
    cost_usd: float | None,
    latency_ms: int | None,
    tokens_in: int | None,
    tokens_out: int | None,
    status: str = "complete",
) -> None:
    """Insert an assistant-role message row WITHOUT committing.

    Called inside ``persist_turn``'s explicit BEGIN/COMMIT block.
    ``content_blocks`` is the pre-serialised JSON string from
    ``json.dumps(non_text_chunks)``; ``text`` is the collapsed
    TextDelta text. ``status`` carries through whatever
    ``persist_turn`` derived from the buffer (complete / error /
    cancelled).
    """

    await db.execute(
        "INSERT INTO messages (id, thread_id, role, content_blocks,"
        " text, backend_used, model_used, cost_usd, latency_ms,"
        " tokens_in, tokens_out, created_at, status)"
        " VALUES (?, ?, 'assistant', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            message_id,
            thread_id,
            content_blocks,
            text,
            backend_used,
            model_used,
            cost_usd,
            latency_ms,
            tokens_in,
            tokens_out,
            _now_iso(),
            status,
        ),
    )


async def insert_routing_decision(
    db: aiosqlite.Connection,
    *,
    decision_id: str,
    message_id: str,
    decision: Any,
) -> None:
    """Insert a routing_decisions row WITHOUT committing.

    ``decision`` is the Phase 1
    ``src.routing.schema.RoutingDecision`` frozen dataclass — duck-
    typed here so this module never imports from ``src.routing.*``
    and the D-18 import-graph guard stays green when tested in
    isolation. ``decision.signals`` is the per-stage telemetry dict
    we serialise to JSON; per-stage fields (``task_type``,
    ``agentic_intent`` etc.) are pulled out of the dict via
    ``.get(..., None)`` for null-safety on partial decisions (e.g.
    the override path).
    """

    signals_dict = getattr(decision, "signals", None) or {}
    signals_json = json.dumps(signals_dict)
    await db.execute(
        "INSERT INTO routing_decisions (id, message_id, task_type,"
        " task_confidence, agentic_intent, agentic_confidence,"
        " predicted_model, rationale, signals, decided_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            decision_id,
            message_id,
            signals_dict.get("task_type"),
            signals_dict.get("task_confidence"),
            signals_dict.get("agentic_intent"),
            signals_dict.get("agentic_confidence"),
            getattr(decision, "model_or_agent", None),
            getattr(decision, "rationale", ""),
            signals_json,
            _now_iso(),
        ),
    )


# --------------------------------------------------------------------
# Per-turn ONE-transaction writer
# --------------------------------------------------------------------


async def persist_turn(
    db: aiosqlite.Connection,
    *,
    thread_id: str,
    user_text: str,
    user_message_id: str,
    assistant_message_id: str,
    routing_decision_id: str,
    buffer: list,
    decision: Any,
    status: str = "complete",
) -> None:
    """Write the per-turn triple (user msg + asst msg + decision) atomically.

    STORE-05 + D-04: ONE ``BEGIN ... COMMIT`` block wraps all three
    inserts. The buffer is a ``list[ChatChunk]`` accumulated by the
    Wave 4 streaming route; we collapse TextDelta chunks into a single
    text string and serialise the rest as the ``content_blocks`` JSON.
    The terminal ``Done`` chunk (if present) supplies the cost / tokens
    / latency for the assistant row.

    Duck-typed buffer dispatch: chunks expose ``.type`` (the
    discriminator) and the variant-specific attrs (``.text``,
    ``.cost_usd`` etc.). Tests pass real ``ChatChunk`` instances; the
    fake adapter from Wave 0 produces the same shape.

    On exception inside the body, ``rollback()`` runs before re-raise
    so a half-written turn never lands.
    """

    # Collapse TextDelta -> single string; everything else -> JSON list.
    text_parts: list[str] = []
    non_text_payloads: list[dict[str, Any]] = []
    done_chunk = None
    for chunk in buffer:
        chunk_type = getattr(chunk, "type", None)
        if chunk_type == "text_delta":
            text_parts.append(getattr(chunk, "text", ""))
        elif chunk_type == "done":
            done_chunk = chunk
        else:
            # Pydantic v2 model_dump() gives us a plain dict suitable
            # for ``json.dumps``. Non-Pydantic shapes never reach here
            # because the buffer is typed as ``list[ChatChunk]`` at
            # the route handler boundary.
            non_text_payloads.append(chunk.model_dump())

    text = "".join(text_parts)
    content_blocks = json.dumps(non_text_payloads)

    # Pull out usage from the terminal Done (may be absent on errors).
    cost_usd: float | None = (
        getattr(done_chunk, "cost_usd", None) if done_chunk else None
    )
    tokens_in: int | None = (
        getattr(done_chunk, "tokens_in", None) if done_chunk else None
    )
    tokens_out: int | None = (
        getattr(done_chunk, "tokens_out", None) if done_chunk else None
    )
    latency_ms: int | None = (
        getattr(done_chunk, "latency_ms", None) if done_chunk else None
    )

    backend_used = getattr(decision, "backend", None)
    model_used = getattr(decision, "model_or_agent", None)

    await db.execute("BEGIN")
    try:
        await insert_user_message(
            db,
            message_id=user_message_id,
            thread_id=thread_id,
            text=user_text,
        )
        await insert_assistant_message_with_blocks(
            db,
            message_id=assistant_message_id,
            thread_id=thread_id,
            text=text,
            content_blocks=content_blocks,
            backend_used=backend_used,
            model_used=model_used,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            status=status,
        )
        await insert_routing_decision(
            db,
            decision_id=routing_decision_id,
            message_id=assistant_message_id,
            decision=decision,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise


# --------------------------------------------------------------------
# Schema-meta read
# --------------------------------------------------------------------


async def read_schema_version(db: aiosqlite.Connection) -> int:
    """Return the current ``schema_meta.version``.

    Wave 2 lifespan caches the result on ``app.state.schema_version``
    so the ``/healthz`` route reads from memory without re-hitting
    SQLite. Returns 0 when ``schema_meta`` is unexpectedly empty
    (never happens in production after migrations run; defensive).
    """

    async with db.execute(
        "SELECT version FROM schema_meta LIMIT 1"
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return 0
    return int(row[0])
