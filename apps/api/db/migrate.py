"""Hand-rolled schema migration runner.

Public surface (STORE-02, STORE-03, D-02):

    MIGRATIONS_DIR     Final[Path] — sibling ``migrations/`` directory.
    up_to_latest(db)   async — idempotent schema walker; applies any
                       pending ``schema_v{N}.sql`` files in numeric
                       order and bumps ``schema_meta.version``.

The runner reads the single-row ``schema_meta.version`` table to
determine the current version, globs ``schema_v*.sql`` from
``MIGRATIONS_DIR``, parses the integer suffix, sorts ascending, and
applies any file whose integer is GREATER than the current version.
Each file is executed inside an explicit ``BEGIN ... COMMIT`` block.
On a fresh DB (no ``schema_meta`` row yet) the runner inserts the
first row; on subsequent migrations it ``UPDATE``s.

NO Alembic. NO yoyo. NO SQLAlchemy. NO ORM. Per D-02 the runner is
~40 lines of stdlib + aiosqlite and lives entirely in this module.

Pitfall 3 (RESEARCH §"Pattern 5" line 455): ``aiosqlite.executescript``
ultimately calls into ``sqlite3.Cursor.executescript``, which
**commits any pending transaction before executing the script**. The
``BEGIN`` we issue immediately above ``executescript`` is therefore
implicitly committed before the script runs, so the DDL statements
inside ``schema_v{N}.sql`` are NOT atomically wrapped with the
``schema_meta`` version bump that follows. For Phase 3's APPEND-ONLY
DDL pattern (CREATE TABLE / CREATE INDEX / ALTER TABLE ADD COLUMN)
this is acceptable — a half-applied migration leaves a partial schema
that the next run picks up safely. If a future schema introduces
DESTRUCTIVE DDL (DROP COLUMN, DROP TABLE, etc.), the planner MUST
restructure this module to split the SQL file on ``;`` and execute
each statement individually inside the explicit BEGIN/COMMIT so the
implicit commit no longer fires. CONTEXT line 369 (deferred items)
locks Phase 3 to forward-only migrations precisely so this trade-off
stays safe.

Cross-refs:
    - 03-RESEARCH.md §"Pattern 5" lines 386-455 (canonical source)
    - 03-RESEARCH.md §"Pitfall 3" (executescript implicit commit)
    - 03-CONTEXT.md D-02 (migration runner shape)
    - 03-CONTEXT.md D-13 (schema_v0 + schema_meta seed)
    - 03-CONTEXT.md deferred line 369 (forward-only-migrations rule)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

import aiosqlite

logger = logging.getLogger(__name__)

# ``schema_v{N}.sql`` files live in the sibling ``migrations/`` directory.
# ``Path(__file__).resolve().parent`` lands at ``apps/api/db/`` so the
# resolved value is ``apps/api/db/migrations/``. Phase 3 paths use
# ``pathlib`` exclusively — no string-concat path-joining anywhere.
MIGRATIONS_DIR: Final[Path] = Path(__file__).resolve().parent / "migrations"


async def _current_version(db: aiosqlite.Connection) -> int:
    """Return the current ``schema_meta.version`` or -1 on a fresh DB.

    -1 sentinel means ``schema_meta`` table itself does not yet exist
    (first run). 0 means the table exists but has no row (rare; we
    fall through to ``INSERT`` on the first migration). Otherwise the
    integer value of the single row is returned.

    The ``aiosqlite.OperationalError`` branch catches the "no such
    table" failure that fires before the first ``schema_v0.sql``
    application creates the table.
    """

    try:
        async with db.execute(
            "SELECT version FROM schema_meta LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
            if row is None:
                return 0
            return int(row[0])
    except aiosqlite.OperationalError:
        # ``schema_meta`` table absent — fresh DB.
        return -1


def _discover_migrations() -> list[tuple[int, Path]]:
    """Return ``[(version_int, sql_path), ...]`` sorted ascending.

    Globs ``schema_v*.sql`` from ``MIGRATIONS_DIR``, parses the
    integer suffix via ``Path.stem.removeprefix("schema_v")``, and
    silently skips files whose suffix is not a clean integer
    (defensive against operator typos like ``schema_v1.sql.bak``).
    """

    found: list[tuple[int, Path]] = []
    for path in MIGRATIONS_DIR.glob("schema_v*.sql"):
        try:
            num = int(path.stem.removeprefix("schema_v"))
        except ValueError:
            # Non-integer suffix — operator artifact, skip silently.
            continue
        found.append((num, path))
    return sorted(found, key=lambda pair: pair[0])


async def up_to_latest(db: aiosqlite.Connection) -> None:
    """Apply every pending ``schema_v{N}.sql`` in numeric order.

    Idempotent: re-running with the version already at the latest is
    a no-op (the per-file ``version <= current`` gate short-circuits).
    On the first call against a fresh DB the runner ``INSERT``s the
    initial ``schema_meta`` row; on subsequent migrations it
    ``UPDATE``s the existing row.

    Each migration runs inside its own explicit BEGIN/COMMIT block.
    On any exception inside the body, we ``rollback()`` and re-raise so
    the caller (lifespan startup) sees the failure immediately.
    """

    current = await _current_version(db)
    for version, path in _discover_migrations():
        if version <= current:
            # Already applied (or older than the current version).
            continue

        sql = path.read_text(encoding="utf-8")

        await db.execute("BEGIN")
        try:
            # Pitfall 3: aiosqlite.executescript() ultimately calls
            # sqlite3.Cursor.executescript() which COMMITS any pending
            # transaction before running the script. The BEGIN above is
            # therefore implicitly committed and the DDL below is NOT
            # inside our explicit transaction. Acceptable for the
            # APPEND-ONLY migrations in Phase 3 (CREATE TABLE / CREATE
            # INDEX / ALTER TABLE ADD COLUMN); a future destructive
            # migration MUST split the SQL on ``;`` and execute
            # statements individually instead.
            await db.executescript(sql)
            # ``schema_v0.sql`` ITSELF seeds the schema_meta row
            # (``INSERT INTO schema_meta (version) VALUES (0)``). On a
            # fresh DB the runner therefore sees the row land mid-
            # script and must UPDATE rather than INSERT to avoid a
            # duplicate row. We re-read schema_meta after the script
            # to make the choice safely; if schema_meta is somehow
            # still empty (a future migration that doesn't seed),
            # INSERT does the right thing.
            async with db.execute(
                "SELECT COUNT(*) FROM schema_meta"
            ) as cur:
                meta_count = (await cur.fetchone())[0]
            if meta_count == 0:
                await db.execute(
                    "INSERT INTO schema_meta (version) VALUES (?)",
                    (version,),
                )
            else:
                await db.execute(
                    "UPDATE schema_meta SET version = ?",
                    (version,),
                )
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        logger.info("Applied schema_v%d.sql", version)
        current = version
