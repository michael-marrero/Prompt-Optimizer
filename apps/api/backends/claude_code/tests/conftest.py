"""Claude Code adapter test fixtures — pricing + happy-path fake client.

The session-scoped ``pricing_table`` fixture reads ``config/pricing.json``
from the repo root (5 directory levels up from this file). Function-
scoped fixtures (``fake_claude_sdk_client``, ``fake_client_factory``)
return a fresh fake per test so accumulated counter state never leaks.

Cross-refs:
    - 02-RESEARCH.md §"Pattern 4" lines 664-868 (full SDK message shapes)
    - apps/api/backends/openrouter/tests/conftest.py (parallel layout)
"""

from __future__ import annotations

import os

import pytest

from apps.api.backends.claude_code.tests.fakes import (
    FakeAssistantMessage,
    FakeClaudeSDKClient,
    FakeResultMessage,
    FakeTextBlock,
)
from apps.api.backends.pricing import PricingTable

# apps/api/backends/claude_code/tests/conftest.py -> repo root is 5 ups.
REPO_ROOT = os.path.abspath(os.path.join(__file__, "..", "..", "..", "..", "..", ".."))
PRICING_PATH = os.path.join(REPO_ROOT, "config", "pricing.json")


@pytest.fixture(scope="session")
def pricing_table() -> PricingTable:
    """Loaded once per session — pure data, no mutation expected."""

    return PricingTable.from_static(PRICING_PATH)


@pytest.fixture
def fake_claude_sdk_client() -> FakeClaudeSDKClient:
    """Happy-path fake: one AssistantMessage(TextBlock) + ResultMessage."""

    return FakeClaudeSDKClient(
        response_messages=[
            FakeAssistantMessage(content=[FakeTextBlock(text="hello")]),
            FakeResultMessage(total_cost_usd=0.001),
        ],
    )


@pytest.fixture
def fake_client_factory(fake_claude_sdk_client: FakeClaudeSDKClient):
    """Returns a ``client_factory`` callable bound to the happy-path fake.

    Usage in tests::

        adapter = ClaudeCodeAdapter(
            client_factory=fake_client_factory,
        )
    """

    def factory(*, options=None, **_kw) -> FakeClaudeSDKClient:
        fake_claude_sdk_client.options = options
        return fake_claude_sdk_client

    return factory
