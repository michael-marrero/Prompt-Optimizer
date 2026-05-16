"""``apps.api.routes`` — FastAPI router package marker.

Empty package marker. Submodules to import directly:

    - ``apps.api.routes.health``     GET /api/v1/healthz (Wave 2)

Wave 3 adds ``threads`` (CRUD). Wave 4 adds ``turn`` (SSE).
Wave 6 adds ``settings`` (GET/PATCH) and ``rename`` (one-shot title).
Each module exports a single ``router: APIRouter`` that the Wave 2
``apps.api.main.create_app`` factory mounts via ``app.include_router``.
"""
