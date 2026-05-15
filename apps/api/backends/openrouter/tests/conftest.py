"""OpenRouter test fixtures — pricing + key store + happy-path fake client.

The session-scoped ``pricing_table`` fixture reads ``config/pricing.json``
from the repo root (5 directory levels up from this file). Function-
scoped fixtures (``fake_openai_client``, ``fake_openai_factory``)
return a fresh fake per test so accumulated ``create_calls`` from one
test never leak into another.
"""

from __future__ import annotations

import os

import pytest

from apps.api.backends.openrouter.tests.fakes import (
    FakeAsyncStream,
    FakeChatCompletions,
    FakeChoice,
    FakeChunk,
    FakeDelta,
    FakeOpenAIClient,
    FakeUsage,
)
from apps.api.backends.pricing import PricingTable

# apps/api/backends/openrouter/tests/conftest.py -> repo root is 5 ups.
REPO_ROOT = os.path.abspath(os.path.join(__file__, "..", "..", "..", "..", "..", ".."))
PRICING_PATH = os.path.join(REPO_ROOT, "config", "pricing.json")


@pytest.fixture(scope="session")
def pricing_table() -> PricingTable:
    """Loaded once per session — pure data, no mutation expected."""

    return PricingTable.from_static(PRICING_PATH)


@pytest.fixture
def fake_openai_client() -> FakeOpenAIClient:
    """Happy-path 2-chunk fake: one TextDelta then a final usage chunk."""

    chunks = [
        FakeChunk(
            choices=[
                FakeChoice(
                    delta=FakeDelta(content="hi"),
                    finish_reason="stop",
                )
            ],
            usage=None,
        ),
        FakeChunk(
            choices=[],
            usage=FakeUsage(prompt_tokens=10, completion_tokens=5),
        ),
    ]
    return FakeOpenAIClient(chunks)


@pytest.fixture
def fake_openai_factory(fake_openai_client: FakeOpenAIClient):
    """Returns a ``client_factory`` callable bound to a fresh fake client.

    Usage in tests::

        adapter = OpenRouterAdapter(
            api_key="fake",
            client_factory=fake_openai_factory,
        )
    """

    def factory(_api_key: str) -> FakeOpenAIClient:
        return fake_openai_client

    return factory
