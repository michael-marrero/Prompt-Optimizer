"""Phase 7 Plan 07-01 Wave 0 — NEW RED test: parallel-completions /compare SSE contract.

07-VALIDATION.md row: "Compare endpoint contract | L5 | backend".

RED-by-design: there is NO ``/compare`` route in ``apps/api/routes/`` yet — the
parallel-two-completions backend path (one prompt rendered side-by-side across
two candidate models) lands in Plan 07-07. Until then the POST below returns
404/405 and the lane assertions fail for "endpoint not implemented" reasons —
the correct Wave-0 RED state, NOT a malformed-test failure.

The pinned contract (07-CONTEXT D-08 "Claude's discretion: Compare backend
shape" + UI-SPEC §8 Compare view; planner may refine internals, but the
two-labeled-lane SSE shape is the locked target this test turns GREEN):

    POST /api/v1/threads/{id}/compare
    body: {"message": "<prompt>", "models": ["<m1>", "<m2>"]}

    → an SSE stream carrying TWO labeled lanes. Each event carries a ``lane``
      discriminator (0 / 1) so the 2-up UI can demux the interleaved stream.
      Per lane the sequence is: routing_decision  →  >=1 text_delta  →  done.
      The forced model id for each lane is echoed back (in the lane's
      routing_decision payload) so the UI can label each column.

This test reuses the existing httpx.AsyncClient + ASGITransport + fake-adapter
harness (apps/api/tests/test_turn_streaming.py ``_fresh_app`` reload chain +
apps/api/tests/fake_adapter.FakeStreamingAdapter). The fake yields canned chunks
with zero network / cost so the lane shape is deterministic and fork-PR-safe.

Cross-refs:
    - apps/api/tests/test_turn_streaming.py (the _fresh_app + finite-consume pattern this mirrors)
    - apps/api/tests/fake_adapter.py (FakeStreamingAdapter)
    - 07-UI-SPEC.md §8 (Compare view) + §Copywriting (Compare card head)
    - 07-CONTEXT.md D-08 ("Compare backend shape" — Claude's discretion)
"""

from __future__ import annotations

import importlib
import json

import httpx
import pytest
from httpx import ASGITransport


# ---------------------------------------------------------------------
# Helper — fresh app under tmp_path. Mirrors test_turn_streaming.py:_fresh_app
# (same reload chain + sse_starlette purge for the D-18 smoke-test interaction).
# ---------------------------------------------------------------------


def _fresh_app(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("PROMPT_OPTIMIZER_HOME", str(tmp_path))

    import sys

    for name in list(sys.modules):
        if name.startswith("sse_starlette"):
            del sys.modules[name]

    import apps.api.paths

    importlib.reload(apps.api.paths)
    import apps.api.jsonl_log

    importlib.reload(apps.api.jsonl_log)
    import apps.api.lifespan

    importlib.reload(apps.api.lifespan)
    import apps.api.routes.turn

    importlib.reload(apps.api.routes.turn)
    import apps.api.main

    importlib.reload(apps.api.main)
    return apps.api.main.create_app()


async def _create_thread(client, title: str = "compare-t1") -> str:
    resp = await client.post("/api/v1/threads", json={"title": title})
    assert resp.status_code == 200, (
        f"thread create failed: {resp.status_code} {resp.text}"
    )
    return resp.json()["id"]


# ---------------------------------------------------------------------
# Test 1 — /compare streams two labeled lanes, each routing_decision→text_delta→done
# ---------------------------------------------------------------------


async def test_compare_streams_two_labeled_lanes(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """POST /compare with two models emits two ``lane``-tagged SSE lanes.

    Each lane must carry the routing_decision → >=1 text_delta → done sequence.
    The fake adapter supplies canned chunks for the openrouter backend both
    forced models resolve to (Compare forces the model id per lane rather than
    routing through decide()).
    """

    app = _fresh_app(monkeypatch, tmp_path)

    from apps.api.backends.chunks import Done, TextDelta
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    # Both lanes stream through a fake openrouter adapter (the two forced models
    # are OpenRouter slugs). The fake yields a tiny text_delta + terminal Done.
    def make_fake() -> FakeStreamingAdapter:
        return FakeStreamingAdapter(
            [
                TextDelta(text="lane-answer"),
                Done(tokens_in=1, tokens_out=1, cost_usd=0.001, latency_ms=10),
            ]
        )

    app.state.adapters = {"openrouter": make_fake()}
    app.state.settings = {
        "default_max_cost_usd": 0.50,
        "computer_use_opt_in": False,
    }

    model_a = "openai/gpt-5"
    model_b = "anthropic/claude-sonnet-4.5"

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)

            events: list[tuple[str, str]] = []  # (event_name, data_json)
            current_event: str | None = None
            done_count = 0

            async with client.stream(
                "POST",
                f"/api/v1/threads/{thread_id}/compare",
                json={
                    "message": "Explain transformer attention in one paragraph.",
                    "models": [model_a, model_b],
                },
            ) as resp:
                assert resp.status_code == 200, (
                    f"POST /compare should open an SSE stream; got "
                    f"{resp.status_code}: {await resp.aread()!r}"
                )
                ctype = resp.headers.get("content-type", "")
                assert ctype.startswith("text/event-stream"), (
                    f"Content-Type was {ctype!r}; expected SSE"
                )
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        current_event = line.split(":", 1)[1].strip()
                    elif line.startswith("data:") and current_event is not None:
                        events.append((current_event, line.split(":", 1)[1].strip()))
                        if current_event == "done":
                            done_count += 1
                            # Two lanes → two terminal done events. Finite
                            # consume so ASGITransport never hangs (Pitfall 4).
                            if done_count >= 2:
                                break

    # ---- Two distinct lane discriminators appear on the wire ----
    lanes_seen: set[int] = set()
    for _name, data in events:
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and "lane" in payload:
            lanes_seen.add(payload["lane"])
    assert lanes_seen == {0, 1}, (
        f"Compare must emit exactly two labeled lanes (0 and 1); "
        f"saw {sorted(lanes_seen)}"
    )

    # ---- Per-lane sequence: routing_decision → >=1 text_delta → done ----
    def lane_event_names(lane: int) -> list[str]:
        names: list[str] = []
        for name, data in events:
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and payload.get("lane") == lane:
                names.append(name)
        return names

    for lane in (0, 1):
        names = lane_event_names(lane)
        assert names, f"lane {lane} produced no events"
        assert names[0] == "routing_decision", (
            f"lane {lane} must lead with routing_decision; got {names[:3]}"
        )
        assert names.count("text_delta") >= 1, (
            f"lane {lane} must emit >=1 text_delta; got {names}"
        )
        assert names[-1] == "done", (
            f"lane {lane} must terminate with done; got {names[-3:]}"
        )


# ---------------------------------------------------------------------
# Test 2 — each lane echoes its forced model id (so the UI can label columns)
# ---------------------------------------------------------------------


async def test_compare_echoes_forced_model_per_lane(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Each lane's routing_decision payload echoes the forced model id.

    Compare FORCES a model per lane (it does not route through decide()), so the
    routing_decision payload for lane 0 must carry ``model_a`` and lane 1 must
    carry ``model_b`` — that is how the 2-up Compare view labels each column
    (UI-SPEC §Copywriting Compare card head "{Model} · {latency}s · ${cost}").
    """

    app = _fresh_app(monkeypatch, tmp_path)

    from apps.api.backends.chunks import Done, TextDelta
    from apps.api.tests.fake_adapter import FakeStreamingAdapter

    app.state.adapters = {
        "openrouter": FakeStreamingAdapter(
            [TextDelta(text="x"), Done(cost_usd=0.001, latency_ms=10)]
        )
    }
    app.state.settings = {
        "default_max_cost_usd": 0.50,
        "computer_use_opt_in": False,
    }

    model_a = "openai/gpt-5"
    model_b = "anthropic/claude-sonnet-4.5"

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            thread_id = await _create_thread(client)

            model_by_lane: dict[int, str] = {}
            current_event: str | None = None
            done_count = 0

            async with client.stream(
                "POST",
                f"/api/v1/threads/{thread_id}/compare",
                json={"message": "Compare these two.", "models": [model_a, model_b]},
            ) as resp:
                assert resp.status_code == 200, (
                    f"got {resp.status_code}: {await resp.aread()!r}"
                )
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        current_event = line.split(":", 1)[1].strip()
                    elif line.startswith("data:") and current_event is not None:
                        data = line.split(":", 1)[1].strip()
                        try:
                            payload = json.loads(data)
                        except json.JSONDecodeError:
                            payload = None
                        if (
                            current_event == "routing_decision"
                            and isinstance(payload, dict)
                            and "lane" in payload
                        ):
                            model_by_lane[payload["lane"]] = payload.get(
                                "model_or_agent", ""
                            )
                        if current_event == "done" and isinstance(payload, dict):
                            done_count += 1
                            if done_count >= 2:
                                break

    assert model_by_lane.get(0) == model_a, (
        f"lane 0 must echo the first forced model {model_a!r}; "
        f"got {model_by_lane.get(0)!r}"
    )
    assert model_by_lane.get(1) == model_b, (
        f"lane 1 must echo the second forced model {model_b!r}; "
        f"got {model_by_lane.get(1)!r}"
    )
