"""``apps.api.db`` — async SQLite storage package marker.

Empty package marker. Submodules to import directly:

    - ``apps.api.db.connect``       open_db factory + D-03 pragmas
    - ``apps.api.db.migrate``       hand-rolled schema migration runner
    - ``apps.api.db.models``        Pydantic v2 DB-row models
    - ``apps.api.db.queries``       typed async query functions

Wave 1 ships the full storage layer; Waves 2+ consume via the
``apps.api.lifespan`` startup hook.
"""
