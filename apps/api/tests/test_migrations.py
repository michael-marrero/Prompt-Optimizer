"""Migration test suite — schema_v0 four-table presence, D-03 pragmas,
v0->v1 round-trip preserves data + adds index. STORE-01 / STORE-02 /
STORE-03.

Four async tests:

    test_schema_v0_has_all_four_tables       Confirms the canonical
                                              schema_v0.sql writes the
                                              four-table set (D-13).
    test_pragmas_applied                     Confirms open_db() applies
                                              the four D-03 pragmas in
                                              order (busy_timeout=5000,
                                              foreign_keys=1,
                                              synchronous=1; journal_mode
                                              relaxed for :memory:).
    test_up_to_latest_idempotent             Confirms running the runner
                                              twice on the same DB is a
                                              no-op the second time
                                              (the version-gate
                                              short-circuit fires).
    test_v0_to_v1_preserves_data             The canonical STORE-03
                                              round-trip: load
                                              schema_v0 only, ingest
                                              the Wave 0 seed (1 thread
                                              + 2 messages + 1
                                              routing_decisions row),
                                              run up_to_latest(), assert
                                              every seeded row is still
                                              present AND the v1 index
                                              landed.

Tests use raw ``aiosqlite.connect(":memory:")`` for the schema-only
case (no open_db pragmas needed when we're only loading DDL); other
tests use ``open_db(":memory:")`` so the D-03 pragmas are exercised.
The fixture in conftest is not used here because some sub-tests need
to apply schema_v0.sql ONLY (without running schema_v1.sql), which
the conftest fixture does not support.

Per API-08 / D-20 and the negative-grep guard in apps/api/tests/
test_smoke.py: this file MUST NOT import the synchronous FastAPI
test-client wrapper. Storage tests don't need it anyway.

Cross-refs:
    - 03-PLAN-01 Task 3 lines 469-526 (behaviour + action)
    - 03-VALIDATION.md row "3-01-01" / "3-01-02" lines 47-49
    - 03-CONTEXT.md specifics line 346 (round-trip seed contract)
    - 03-RESEARCH.md §"Pattern 5" lines 386-455 (migration runner)
"""

from __future__ import annotations

import os

import aiosqlite
import pytest

# Path to the repo root — matches apps/api/backends/tests/conftest.py
# (``<repo>/apps/api/tests/test_migrations.py`` is FOUR ``..`` away
# from the repo root).
REPO_ROOT = os.path.abspath(os.path.join(__file__, "..", "..", "..", ".."))

SCHEMA_V0_PATH = os.path.join(
    REPO_ROOT, "apps", "api", "db", "migrations", "schema_v0.sql"
)
SEED_SQL_PATH = os.path.join(
    REPO_ROOT, "apps", "api", "tests", "fixtures", "schema_v0_seed.sql"
)


# --------------------------------------------------------------------
# Test 1: schema_v0 has all four tables (D-13).
# --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schema_v0_has_all_four_tables() -> None:
    """Confirm schema_v0.sql creates threads, messages,
    routing_decisions, and schema_meta — the four-table set locked by
    D-13."""

    # Raw aiosqlite.connect — this test asserts the SQL DDL alone, no
    # need for the D-03 pragmas. The FK declarations still parse
    # cleanly without ``foreign_keys=ON`` (enforcement is a runtime
    # toggle, the schema syntax check happens regardless).
    db = await aiosqlite.connect(":memory:")
    try:
        # Parse the FK declarations defensively — same pragma the
        # production path sets.
        await db.execute("PRAGMA foreign_keys=ON")
        with open(SCHEMA_V0_PATH, "r", encoding="utf-8") as fh:
            sql = fh.read()
        await db.executescript(sql)

        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " ORDER BY name"
        ) as cur:
            tables = {row[0] async for row in cur}

        assert {
            "threads",
            "messages",
            "routing_decisions",
            "schema_meta",
        }.issubset(tables), f"missing tables; saw {tables}"
    finally:
        await db.close()


# --------------------------------------------------------------------
# Test 2: D-03 pragmas applied on first connect (STORE-01).
# --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pragmas_applied() -> None:
    """Confirm open_db() applies foreign_keys=1, busy_timeout=5000,
    synchronous=1 (NORMAL). journal_mode is relaxed: ``:memory:``
    returns ``'memory'`` because WAL has no sidecar to write to; file
    DBs would return ``'wal'``."""

    from apps.api.db.connect import open_db

    db = await open_db(":memory:")
    try:
        async with db.execute("PRAGMA foreign_keys") as cur:
            fk = (await cur.fetchone())[0]
        async with db.execute("PRAGMA busy_timeout") as cur:
            bt = (await cur.fetchone())[0]
        async with db.execute("PRAGMA synchronous") as cur:
            sync = (await cur.fetchone())[0]
        async with db.execute("PRAGMA journal_mode") as cur:
            jm = (await cur.fetchone())[0]

        assert fk == 1, f"foreign_keys expected 1, got {fk}"
        assert bt == 5000, f"busy_timeout expected 5000, got {bt}"
        assert sync == 1, f"synchronous expected 1 (NORMAL), got {sync}"
        # ``:memory:`` cannot host a WAL sidecar so SQLite falls back
        # to ``memory``. Production callers with a file path get
        # ``wal``; we accept either.
        assert jm in ("memory", "wal"), f"journal_mode unexpected: {jm!r}"
    finally:
        await db.close()


# --------------------------------------------------------------------
# Test 3: up_to_latest is idempotent.
# --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_up_to_latest_idempotent() -> None:
    """Confirm running the migration runner twice on the same DB is a
    no-op the second time (the ``version <= current`` gate fires).
    Also confirms schema_meta has exactly one row after either call."""

    from apps.api.db.connect import open_db
    from apps.api.db.migrate import up_to_latest
    from apps.api.db.queries import read_schema_version

    db = await open_db(":memory:")
    try:
        # ``up_to_latest`` walks to the HIGHEST schema_v*.sql on disk.
        # Story 5.2 added schema_v3.sql (routing_decisions.confidence), so
        # latest is now 3 (Phase 11 was 2). The idempotency property under
        # test is unchanged: the second run is a no-op and the version stays put.
        await up_to_latest(db)
        v1 = await read_schema_version(db)
        assert v1 == 3, f"first run version {v1}"

        await up_to_latest(db)
        v2 = await read_schema_version(db)
        assert v2 == 3, f"second run version {v2}"

        async with db.execute("SELECT COUNT(*) FROM schema_meta") as cur:
            count = (await cur.fetchone())[0]
        assert count == 1, f"expected 1 schema_meta row, got {count}"
    finally:
        await db.close()


# --------------------------------------------------------------------
# Test 4: v0 -> v1 round-trip preserves seeded data + applies index
# (STORE-03 canonical test — the row from VALIDATION 3-01-02).
# --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_v0_to_v1_preserves_data() -> None:
    """STORE-03 round-trip:

    1. Manually apply schema_v0.sql only — DB is at v0.
    2. Ingest fixtures/schema_v0_seed.sql — 1 thread, 2 messages, 1
       routing_decisions row.
    3. Run up_to_latest(db) — advances v0 -> v1.
    4. Assert: schema_meta.version == 1; every seeded row still
       present (by literal ID); idx_messages_thread_id_created_at
       index appears in sqlite_master."""

    from apps.api.db.migrate import up_to_latest
    from apps.api.db.queries import read_schema_version

    db = await aiosqlite.connect(":memory:")
    try:
        # Foreign keys must be on for the cascade-on-delete declarations
        # to parse and for any downstream cascade test to work — set it
        # explicitly because we're bypassing open_db here.
        await db.execute("PRAGMA foreign_keys=ON")

        # Step 1: apply schema_v0 only (NOT schema_v1).
        with open(SCHEMA_V0_PATH, "r", encoding="utf-8") as fh:
            v0_sql = fh.read()
        await db.executescript(v0_sql)

        # Step 2: ingest the Wave 0 seed.
        with open(SEED_SQL_PATH, "r", encoding="utf-8") as fh:
            seed_sql = fh.read()
        await db.executescript(seed_sql)

        # Verify seeded counts BEFORE migration.
        async with db.execute("SELECT COUNT(*) FROM threads") as cur:
            tc = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM messages") as cur:
            mc = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM routing_decisions"
        ) as cur:
            rc = (await cur.fetchone())[0]
        assert tc == 1, f"expected 1 thread, got {tc}"
        assert mc == 2, f"expected 2 messages, got {mc}"
        assert rc == 1, f"expected 1 routing_decision, got {rc}"

        # Step 3: advance to the latest on-disk schema.
        await up_to_latest(db)

        # Step 4a: schema_meta.version bumped to the HIGHEST schema_v*.sql
        # on disk. Story 5.2 added schema_v3.sql, so up_to_latest from v0
        # now lands on 3 (Phase 11 was 2). The substantive STORE-03
        # assertions below — seeded rows preserved + the schema_v1 index
        # present — are unchanged.
        v = await read_schema_version(db)
        assert v == 3, f"expected version 3, got {v}"

        # Step 4b: seeded rows still present by literal ID.
        async with db.execute(
            "SELECT id FROM threads WHERE id = ?", ("thr_seed_0001",)
        ) as cur:
            thr_row = await cur.fetchone()
        assert thr_row is not None, "thr_seed_0001 lost during migration"

        async with db.execute(
            "SELECT id FROM messages WHERE thread_id = ?"
            " ORDER BY created_at ASC",
            ("thr_seed_0001",),
        ) as cur:
            msg_ids = [row[0] async for row in cur]
        assert msg_ids == [
            "msg_seed_user_0001",
            "msg_seed_asst_0001",
        ], f"messages lost / reordered: {msg_ids}"

        async with db.execute(
            "SELECT id FROM routing_decisions WHERE id = ?",
            ("rd_seed_0001",),
        ) as cur:
            rd_row = await cur.fetchone()
        assert rd_row is not None, "rd_seed_0001 lost during migration"

        # Step 4c: schema_v1 index landed in sqlite_master.
        async with db.execute(
            "SELECT name FROM sqlite_master"
            " WHERE type='index' AND name=?",
            ("idx_messages_thread_id_created_at",),
        ) as cur:
            ix_row = await cur.fetchone()
        assert ix_row is not None, (
            "idx_messages_thread_id_created_at missing — schema_v1 "
            "didn't apply"
        )
    finally:
        await db.close()


# --------------------------------------------------------------------
# Test 5: v1 -> v2 adds control_events on top of schema_v1 (CTRL-02 /
# D-02). Mirrors test_v0_to_v1_preserves_data: apply v0+v1, seed prior
# rows, run up_to_latest, assert version==2, the table + index appear in
# sqlite_master, and the seeded schema_v1 rows survived.
# --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_v1_to_v2_creates_control_events() -> None:
    """CTRL-02 / D-02 round-trip:

    1. Manually apply schema_v0.sql + schema_v1.sql only — DB is at v1.
    2. Ingest fixtures/schema_v0_seed.sql — 1 thread, 2 messages, 1
       routing_decisions row (the "prior rows" that must survive).
    3. Run up_to_latest(db) — advances v1 -> v2.
    4. Assert: schema_meta.version == 2; control_events table AND
       idx_control_events_turn_id index both in sqlite_master; every
       seeded prior row still present (proves "on top of schema_v1")."""

    from apps.api.db.migrate import up_to_latest
    from apps.api.db.queries import read_schema_version

    schema_v1_path = os.path.join(
        REPO_ROOT, "apps", "api", "db", "migrations", "schema_v1.sql"
    )

    db = await aiosqlite.connect(":memory:")
    try:
        await db.execute("PRAGMA foreign_keys=ON")

        # Step 1: apply schema_v0 + schema_v1 only (NOT schema_v2). After
        # these two scripts the DB is structurally at v1, but schema_meta
        # still reads 0 because schema_v0 seeds 0 and the runner has not
        # bumped it. Stamp it to 1 so up_to_latest only applies v2.
        with open(SCHEMA_V0_PATH, "r", encoding="utf-8") as fh:
            await db.executescript(fh.read())
        with open(schema_v1_path, "r", encoding="utf-8") as fh:
            await db.executescript(fh.read())
        await db.execute("UPDATE schema_meta SET version = 1")
        await db.commit()

        # Step 2: ingest the Wave 0 seed — these are the prior rows that
        # MUST survive the v1 -> v2 migration.
        with open(SEED_SQL_PATH, "r", encoding="utf-8") as fh:
            await db.executescript(fh.read())

        async with db.execute("SELECT COUNT(*) FROM threads") as cur:
            tc = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM messages") as cur:
            mc = (await cur.fetchone())[0]
        assert tc == 1, f"expected 1 thread pre-migration, got {tc}"
        assert mc == 2, f"expected 2 messages pre-migration, got {mc}"

        # Step 3: advance v1 -> latest (walks through v2, then v3).
        await up_to_latest(db)

        # Step 4a: schema_meta.version bumped to the latest on disk (3 as of
        # Story 5.2); control_events (v2) still lands on the way — asserted below.
        v = await read_schema_version(db)
        assert v == 3, f"expected version 3, got {v}"

        # Step 4b: control_events table landed.
        async with db.execute(
            "SELECT name FROM sqlite_master"
            " WHERE type='table' AND name=?",
            ("control_events",),
        ) as cur:
            tbl_row = await cur.fetchone()
        assert tbl_row is not None, (
            "control_events table missing — schema_v2 didn't apply"
        )

        # Step 4c: idx_control_events_turn_id index landed.
        async with db.execute(
            "SELECT name FROM sqlite_master"
            " WHERE type='index' AND name=?",
            ("idx_control_events_turn_id",),
        ) as cur:
            ix_row = await cur.fetchone()
        assert ix_row is not None, (
            "idx_control_events_turn_id missing — schema_v2 didn't apply"
        )

        # Step 4d: seeded prior rows survived (proves "on top of v1").
        async with db.execute(
            "SELECT id FROM threads WHERE id = ?", ("thr_seed_0001",)
        ) as cur:
            thr_row = await cur.fetchone()
        assert thr_row is not None, "thr_seed_0001 lost during v1->v2 migration"

        async with db.execute(
            "SELECT id FROM messages WHERE thread_id = ?"
            " ORDER BY created_at ASC",
            ("thr_seed_0001",),
        ) as cur:
            msg_ids = [row[0] async for row in cur]
        assert msg_ids == [
            "msg_seed_user_0001",
            "msg_seed_asst_0001",
        ], f"messages lost / reordered during v1->v2: {msg_ids}"
    finally:
        await db.close()
