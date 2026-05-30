"""OSS-07 / D-06 — process-level fake OpenRouter adapter for the E2E drift gate.

The Playwright drift spec (Plan 06-03) boots a real ``uvicorn apps.api.main:app``
subprocess. Phase 3's in-process fake-adapter injection (D-20, the conftest
``app_factory`` fixture overriding ``app.state.adapters``) cannot reach that
subprocess, so the deterministic-E2E seam must live where ``app.state.adapters``
is populated at startup. When ``PROMPT_OPTIMIZER_FAKE_ADAPTERS=1``,
``apps/api/lifespan.py`` calls :func:`build_fake_openrouter_adapter` to wire the
REAL :class:`OpenRouterAdapter` to a canned fake client — so the entire
production SSE path (``turn.py`` named-event framing, ``sse-translate.ts``, the
AI SDK UI Message Stream, the RoutingChip render) runs unmodified while only the
upstream OpenRouter HTTP call is faked. A hand-maintained mock cannot catch
Next↔FastAPI / AI-SDK message-format drift; only the real wire can.

The ``Fake*`` dataclasses below are a DELIBERATE verbatim copy of the fakes in
``apps/api/backends/tests/conftest.py`` (lines 59-112). Do NOT refactor them to a
shared import: importing the pytest ``tests/`` tree into production code couples
the app to pytest and breaks ``uv run`` / wheel packaging (the
test-tree-into-production coupling is the anti-pattern being avoided — see
06-RESEARCH Anti-Patterns and the T-06-01-COUPLE threat-register entry). The
only import of production code is the LAZY import of ``OpenRouterAdapter`` inside
the builder body, mirroring the conftest's lazy-import-inside-factory pattern.
"""

from __future__ import annotations

from dataclasses import dataclass


# --------------------------------------------------------------------
# OpenAI / OpenRouter fakes — copied verbatim from
# apps/api/backends/tests/conftest.py:59-112. The adapter expects an
# object exposing ``.chat.completions.create(**kw) -> stream`` where
# the stream yields objects shaped like OpenAI's ChatCompletionChunk.
# --------------------------------------------------------------------


@dataclass
class FakeDelta:
    content: str | None = None
    tool_calls: list | None = None


@dataclass
class FakeChoice:
    delta: FakeDelta
    finish_reason: str | None = None


@dataclass
class FakeUsage:
    prompt_tokens: int = 10
    completion_tokens: int = 5


@dataclass
class FakeChunk:
    choices: list[FakeChoice]
    usage: FakeUsage | None = None


class FakeAsyncStream:
    def __init__(self, chunks: list[FakeChunk]):
        self._chunks = chunks

    def __aiter__(self):
        async def gen():
            for chunk in self._chunks:
                yield chunk

        return gen()

    async def close(self) -> None:
        pass


class FakeChatCompletions:
    def __init__(self, chunks: list[FakeChunk]):
        self._chunks = chunks

    async def create(self, **_kw) -> FakeAsyncStream:
        return FakeAsyncStream(self._chunks)


class FakeOpenAIClient:
    def __init__(self, chunks: list[FakeChunk]):
        self.chat = type(
            "Chat",
            (),
            {"completions": FakeChatCompletions(chunks)},
        )()


def build_fake_openrouter_adapter() -> "OpenRouterAdapter":  # noqa: F821
    """Return a REAL ``OpenRouterAdapter`` wired to a canned fake client.

    - ``OpenRouterAdapter`` is imported LAZILY inside this function (mirrors
      ``apps/api/backends/tests/conftest.py:341-342``) to avoid import-time
      coupling and keep the module collectable.
    - ``api_key="fake"`` is non-empty, so the adapter does NOT raise the
      missing-key error in its constructor.
    - The three canned chunks stream ``"Paris"`` then ``" is the capital."``
      then a usage chunk. This literal content is what Plan 06-03's drift spec
      asserts appears in the assistant DOM.
    """

    from apps.api.backends.openrouter.adapter import OpenRouterAdapter

    chunks = [
        FakeChunk(
            choices=[
                FakeChoice(delta=FakeDelta(content="Paris"), finish_reason=None)
            ]
        ),
        FakeChunk(
            choices=[
                FakeChoice(
                    delta=FakeDelta(content=" is the capital."),
                    finish_reason="stop",
                )
            ]
        ),
        FakeChunk(choices=[], usage=FakeUsage(prompt_tokens=12, completion_tokens=4)),
    ]
    return OpenRouterAdapter(
        api_key="fake",
        client_factory=lambda _key: FakeOpenAIClient(chunks),
    )
