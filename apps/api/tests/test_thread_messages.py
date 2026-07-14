"""Phase 8 Plan 08-00 Wave 0 — SC-1 RED endpoint test.

GET /api/v1/threads/{id}/messages — chronological persisted rows plus the
per-assistant ``routing`` decision (rationale + manual-override flag) from a
``routing_decisions`` LEFT JOIN (08-CONTEXT D-01). This is the read seam Phase 8
wires; the endpoint does NOT exist yet (only ``GET /threads/{id}`` and
``GET /threads`` are registered in ``apps/api/routes/threads.py``), so every
request to ``…/messages`` 404s on the missing route. That 404 is the RED signal:
the test COLLECTS and FAILS for a missing-route reason — NOT a collection/import
error.

08-VALIDATION.md §"Sampling detail" SC-1 — what proves the endpoint is MET (not
merely present): seed a thread with TWO distinct turn kinds and assert
   (a) chronological order (created_at ASC: user, assistant, user, assistant),
   (b) ``content_blocks`` parsed to a LIST carrying the stored chunk ``type``s
       (NOT the raw JSON string the DB row holds — RESEARCH Pitfall 3),
   (c) the override turn's ``routing.rationale == "user override"`` +
       ``routing.override is True``, and the auto turn carries a real rationale,
   (d) 404 on an unknown thread id,
   (e) a real-but-empty thread returns ``200 []`` (NOT 404) — the 404-ordering
       hazard (RESEARCH §Pattern 4: call ``get_thread`` first).

HARNESS (Phase 3 D-20 — load-bearing): ``httpx.AsyncClient + ASGITransport``
ONLY. The synchronous FastAPI test-client wrapper is FORBIDDEN under
``apps/api/tests/`` (the negative-grep guard in test_smoke.py / conftest.py
enforces). This file uses the async ASGITransport path exclusively and contains
no synchronous-test-client import (the forbidden symbol is referenced here only
by description, matching the conftest.py convention, so the CLI guard stays
clean).

Seed mechanism (mirrors ``test_threads_crud.py::test_delete_unlinks_blobs``
lines 389-509): drive real turns via ``FakeStreamingAdapter`` +
``monkeypatch.setattr("apps.api.routes.turn.decide", fake_decide)`` so the
``messages`` + ``routing_decisions`` rows are written by the production
``persist_turn`` path. The auto turn emits a ``ToolCall`` + ``FileDiff`` (+
``Done``) so ``content_blocks`` is non-empty; the override turn POSTs with
``override_backend`` set so the synthesized decision lands
``rationale="user override"`` / ``signals={"override": True}``
(``turn.py:_synthesize_override_decision`` lines 219-259).

Cross-refs:
    - 08-PLAN-00 Task 2 (a) + 08-VALIDATION.md SC-1 sampling
    - 08-RESEARCH.md §"SC-1 endpoint test skeleton", §"Pattern 4", §Pitfall 3
    - 08-PATTERNS.md §"apps/api/tests/test_thread_messages.py"
    - apps/api/tests/test_threads_crud.py:77-95 (_fresh_app), :389-509 (seed-a-turn)
    - apps/api/routes/turn.py:219-259 (_synthesize_override_decision)
    - apps/api/backends/chunks.py (ToolCall / FileDiff / Done chunk shapes)
"""

from __future__ import annotations

import importlib
import sys

import httpx
import pytest
from httpx import ASGITransport


# ---------------------------------------------------------------------
# Fresh-app helper — tmp DB via PROMPT_OPTIMIZER_HOME, lifespan-triggered.
#
# Mirrors test_threads_crud.py:_fresh_app but extends the reload chain to
# include apps.api.routes.turn (and purges sse_starlette) the same way
# test_delete_unlinks_blobs:429-453 does — the Phase 1 D-18 smoke test
# invalidates cached class identities (sse_starlette / starlette) when this
# file runs after src/routing/tests/, which otherwise breaks the SSE turn route
# under the reloaded FastAPI. We need a real turn to seed messages, so the turn
# route must be reloaded against the fresh app.
# ---------------------------------------------------------------------


def _fresh_app(monkeypatch: pytest.MonkeyPatch, tmp_path) -> object:
    monkeypatch.setenv("PROMPT_OPTIMIZER_HOME", str(tmp_path))

    for name in list(sys.modules):
        if name.startswith("sse_starlette"):
            del sys.modules[name]

    import apps.api.paths

    importlib.reload(apps.api.paths)
    import apps.api.db.queries

    importlib.reload(apps.api.db.queries)
    import apps.api.lifespan

    importlib.reload(apps.api.lifespan)
    import apps.api.routes.turn

    importlib.reload(apps.api.routes.turn)
    import apps.api.routes.threads

    importlib.reload(apps.api.routes.threads)
    import apps.api.main

    importlib.reload(apps.api.main)
    return apps.api.main.create_app()


def _fake_decide_factory():
    """Return a ``decide`` stub that yields a deterministic auto RoutingDecision.

    The auto turn's rationale is a real (non-override) string so the SC-1
    assertion that the auto turn carries a genuine rationale holds. ``signals``
    has NO ``override`` key, so the join's ``override`` flag is False for this
    turn.
    """

    from src.routing.schema import RoutingDecision

    def fake_decide(*args, **kwargs):
        return RoutingDecision(
            backend="openrouter",
            model_or_agent="openai/gpt-5",
            rationale="Strong reasoning fit for this coding task",
            confidence=0.9,
            signals={"task_type": "coding", "rule_fired": "coding_task"},
        )

    return fake_decide


async def _drive_turn(
    client: httpx.AsyncClient, thread_id: str, message: str, *, override_backend=None
) -> None:
    """POST one turn and drain the SSE stream to the terminal ``done``.

    Mirrors test_delete_unlinks_blobs:493-509 — open the stream, iterate lines
    until the ``done`` event, then exit the context so ``persist_turn`` fires in
    the route's ``finally`` block. ``override_backend`` (when set) flows into the
    TurnRequest body so the route synthesizes an override decision.
    """

    body: dict = {"message": message}
    if override_backend is not None:
        body["override_backend"] = override_backend

    async with client.stream(
        "POST",
        f"/api/v1/threads/{thread_id}/turn",
        json=body,
    ) as resp:
        assert resp.status_code == 200, (
            f"turn POST failed: {resp.status_code} {await resp.aread()!r}"
        )
        async for line in resp.aiter_lines():
            if line.startswith("event:") and line.split(":", 1)[1].strip() == "done":
                break


# ---------------------------------------------------------------------
# SC-1 main test — chronological rows + routing JOIN, both turn kinds.
# ---------------------------------------------------------------------


async def test_get_thread_messages_returns_chronological_with_routing(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """SC-1 sampling: 2 turn kinds + both routing variants + chronological.

    EXPECTED RED until 08-01 registers ``GET /threads/{id}/messages``: the GET
    404s on the missing route, so ``r.status_code == 200`` fails. This is a
    missing-IMPLEMENTATION failure (the route is absent), NOT a collection error.
    """

    app = _fresh_app(monkeypatch, tmp_path)

    from apps.api.backends.chunks import Done, FileDiff, ToolCall
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    # Auto coding turn — non-empty content_blocks (tool_call + file_diff) so the
    # parsed-list assertion has stored chunk types to verify. The override turn
    # reuses the same adapter (a single text + Done is enough; the override's
    # routing row is what matters there).
    auto_chunks = [
        ToolCall(
            tool_call_id="tc_sc1_001",
            tool_name="edit_file",
            arguments={"path": "src/app.py", "instruction": "add a total"},
        ),
        FileDiff(
            tool_call_id="tc_sc1_001",
            path="src/app.py",
            diff="@@ -1 +1 @@\n-old\n+new",
            operation="edit",
        ),
        Done(tokens_in=12, tokens_out=8, cost_usd=0.001, latency_ms=900),
    ]
    app.state.adapters = {"openrouter": FakeStreamingAdapter(auto_chunks)}
    monkeypatch.setattr(
        "apps.api.routes.turn.decide", _fake_decide_factory()
    )

    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            # Create the thread.
            create = await client.post(
                "/api/v1/threads", json={"title": "sc1"}
            )
            assert create.status_code == 200
            thread_id = create.json()["id"]

            # Turn 1 — AUTO (real rationale, content_blocks non-empty).
            await _drive_turn(client, thread_id, "build me a budget total")

            # Turn 2 — OVERRIDE. Re-arm the adapter for the second turn (the fake
            # yields its chunk list once per stream() call; FakeStreamingAdapter
            # re-iterates the same list each call, so a fresh Done-terminated
            # stream is produced again). The override_backend body forces
            # _synthesize_override_decision → rationale="user override".
            app.state.adapters = {
                "openrouter": FakeStreamingAdapter(
                    [Done(tokens_in=4, tokens_out=2, cost_usd=0.0, latency_ms=100)]
                )
            }
            await _drive_turn(
                client,
                thread_id,
                "actually use openrouter",
                override_backend="openrouter",
            )

            # ---- SC-1 assertions (RED until 08-01 ships the route) ----
            r = await client.get(f"/api/v1/threads/{thread_id}/messages")
            assert r.status_code == 200, (
                f"GET messages must be 200 once 08-01 registers the route; "
                f"got {r.status_code}: {r.text}"
            )
            rows = r.json()

            # (a) chronological order — two turns => user, assistant, user, assistant.
            assert [m["role"] for m in rows] == [
                "user",
                "assistant",
                "user",
                "assistant",
            ], f"rows out of chronological order: {[m['role'] for m in rows]}"

            assistant_rows = [m for m in rows if m["role"] == "assistant"]
            auto_asst, override_asst = assistant_rows[0], assistant_rows[1]

            # (b) content_blocks parsed to a LIST (Pitfall 3 — not the raw str)
            #     carrying the stored chunk types from the auto coding turn.
            assert isinstance(auto_asst["content_blocks"], list), (
                "content_blocks must be a parsed list, not a JSON string"
            )
            block_types = {b.get("type") for b in auto_asst["content_blocks"]}
            assert {"tool_call", "file_diff"} <= block_types, (
                f"auto turn content_blocks missing stored chunk types; "
                f"saw {block_types}"
            )

            # (c) routing JOIN — auto turn has a real rationale + override False;
            #     override turn has rationale=="user override" + override True.
            assert auto_asst["routing"] is not None
            assert auto_asst["routing"]["rationale"], "auto turn needs a rationale"
            assert auto_asst["routing"]["override"] is False
            # Story 5.2: the route's confidence round-trips through the DB
            # (schema_v3 column) so the restored low-confidence nudge matches
            # live (AD-7). The stub decides confidence=0.9.
            assert auto_asst["routing"]["confidence"] == 0.9

            assert override_asst["routing"] is not None
            assert override_asst["routing"]["rationale"] == "user override"
            assert override_asst["routing"]["override"] is True

            # (e) real-but-empty thread → 200 [] (NOT 404). 404-ordering hazard.
            empty_create = await client.post(
                "/api/v1/threads", json={"title": "empty"}
            )
            empty_id = empty_create.json()["id"]
            r_empty = await client.get(f"/api/v1/threads/{empty_id}/messages")
            assert r_empty.status_code == 200, (
                f"a real-but-empty thread must return 200 []; got "
                f"{r_empty.status_code}"
            )
            assert r_empty.json() == []

            # (d) unknown thread id → 404 (no-enum-leak beyond existence).
            r_404 = await client.get(
                "/api/v1/threads/does-not-exist/messages"
            )
            assert r_404.status_code == 404, (
                f"unknown thread must 404; got {r_404.status_code}"
            )
