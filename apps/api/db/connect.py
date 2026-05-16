"""Async SQLite connection factory; D-03 pragmas applied on first connect.

Public surface (STORE-01, D-03):

    open_db(path)   async -> aiosqlite.Connection

The factory accepts either a ``Path`` or a ``str`` (the canonical
``":memory:"`` sentinel is a string). When the path is NOT
``":memory:"`` we ``mkdir(parents=True, exist_ok=True)`` on the
parent so the user-home root is created on first boot. After opening
the connection, FOUR pragmas are applied IN THIS ORDER:

    1. ``PRAGMA journal_mode=WAL``       — Write-Ahead Log mode for
                                           non-blocking readers.
    2. ``PRAGMA synchronous=NORMAL``     — fewer fsync()s; safe with WAL.
    3. ``PRAGMA busy_timeout=5000``      — wait up to 5s on lock
                                           contention before raising.
    4. ``PRAGMA foreign_keys=ON``        — REQUIRED for ``ON DELETE
                                           CASCADE`` (D-13) to fire.

A single ``await db.commit()`` follows the four PRAGMA writes.

Pitfall 1 (RESEARCH §"Pattern 4" line 361): SQLite disables foreign-
key enforcement by DEFAULT, per connection. Without
``PRAGMA foreign_keys=ON`` applied AFTER the connection opens, the
``ON DELETE CASCADE`` declarations in ``schema_v0.sql`` (D-13) are
silently ignored — a ``DELETE FROM threads WHERE id=?`` would orphan
the dependent ``messages`` and ``routing_decisions`` rows. The pragma
must be FOURTH (the order in D-03) so it is the last to write before
the commit.

This module never imports from ``apps.api.paths`` because every
callsite passes an explicit path. Tests use ``":memory:"``; the
production lifespan passes ``apps.api.paths.DB_PATH``.

Cross-refs:
    - 03-RESEARCH.md §"Pattern 4" lines 357-405 (canonical source)
    - 03-RESEARCH.md §"Pitfall 1" (foreign_keys default-off per-connection)
    - 03-CONTEXT.md D-03 (pragma order + rationale)
    - 03-CONTEXT.md D-13 (ON DELETE CASCADE relies on this pragma)
"""

from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)


async def open_db(path: Path | str) -> aiosqlite.Connection:
    """Open an ``aiosqlite.Connection`` with the D-03 pragmas applied.

    The pragma order is load-bearing — see Pitfall 1 above.

    ``path`` may be a ``Path`` (the production case) or a ``str``
    (tests pass ``":memory:"``). ``mkdir(parents=True,
    exist_ok=True)`` runs only when the path is NOT ``":memory:"`` so
    test fixtures never touch the filesystem.
    """

    # Coerce str -> Path so we get a single code path for parent-dir
    # creation. ``Path(":memory:")`` is a valid Path but we deliberately
    # don't ``mkdir`` it; SQLite interprets the literal string as the
    # in-memory sentinel.
    path_obj: Path = path if isinstance(path, Path) else Path(path)

    # The literal ``":memory:"`` sentinel must reach aiosqlite verbatim.
    # Any other path triggers the user-home dir bootstrap.
    if str(path) != ":memory:":
        path_obj.parent.mkdir(parents=True, exist_ok=True)

    # aiosqlite accepts a string for both file paths and ``":memory:"``.
    db = await aiosqlite.connect(str(path))

    # Order matters — D-03. Each pragma is its own statement so an
    # error on one pragma leaves the previous ones effective (and the
    # subsequent ones unset; the caller sees the AIOSQLite OperationalError).
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA synchronous=NORMAL")
    await db.execute("PRAGMA busy_timeout=5000")
    # Pitfall 1: SQLite disables FK enforcement by default per
    # connection. The ``ON DELETE CASCADE`` declarations in schema_v0
    # (D-13) require this pragma to actually fire. MUST be after the
    # other three so the four pragmas form the canonical D-03 prefix.
    await db.execute("PRAGMA foreign_keys=ON")

    await db.commit()
    return db
