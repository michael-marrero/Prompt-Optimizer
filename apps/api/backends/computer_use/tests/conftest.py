"""Computer-use adapter test fixtures — pricing + happy-path fakes.

The session-scoped ``pricing_table`` fixture reads ``config/pricing.json``
from the repo root (6 directory levels up from this file). Function-
scoped fakes (``fake_screen``, ``fake_anthropic``, ``fake_client_factory``,
``fake_screen_factory``) return a fresh instance per test so per-test
counter state never leaks.

Cross-refs:
    - 02-RESEARCH.md §"Pattern 5" lines 870-1210 (full adapter)
    - apps/api/backends/claude_code/tests/conftest.py (parallel layout)
    - apps/api/backends/openrouter/tests/conftest.py (parallel layout)
"""

from __future__ import annotations

import os

import pytest

from apps.api.backends.computer_use.tests.fakes import (
    FakeAsyncAnthropic,
    FakePlaywrightScreen,
    make_happy_path_stream,
)
from apps.api.backends.pricing import PricingTable

# apps/api/backends/computer_use/tests/conftest.py -> repo root is 6 ups.
REPO_ROOT = os.path.abspath(
    os.path.join(__file__, "..", "..", "..", "..", "..", "..")
)
PRICING_PATH = os.path.join(REPO_ROOT, "config", "pricing.json")


@pytest.fixture(scope="session")
def pricing_table() -> PricingTable:
    """Loaded once per session — pure data, no mutation expected."""

    return PricingTable.from_static(PRICING_PATH)


@pytest.fixture
def fake_screen() -> FakePlaywrightScreen:
    """Fresh ``FakePlaywrightScreen`` per test (counters reset)."""

    return FakePlaywrightScreen()


@pytest.fixture
def fake_anthropic() -> FakeAsyncAnthropic:
    """Happy-path fake: one TextDelta event + end_turn final message.

    Tests that need different iteration shapes construct their own
    ``FakeAsyncAnthropic(iterations=[...])`` directly — this fixture
    is the default convenience for happy-path tests.
    """

    return FakeAsyncAnthropic(
        api_key="fake",
        iterations=[make_happy_path_stream(text="hello")],
    )


@pytest.fixture
def fake_screen_factory(fake_screen: FakePlaywrightScreen):
    """Returns a ``screen_factory`` callable bound to ``fake_screen``.

    Usage in tests::

        adapter = ComputerUseAdapter(
            api_key="fake",
            screen_factory=fake_screen_factory,
        )
    """

    def factory(**_kw) -> FakePlaywrightScreen:
        return fake_screen

    return factory


@pytest.fixture
def fake_client_factory(fake_anthropic: FakeAsyncAnthropic):
    """Returns a ``client_factory`` callable bound to ``fake_anthropic``.

    Usage in tests::

        adapter = ComputerUseAdapter(
            api_key="fake",
            client_factory=fake_client_factory,
        )
    """

    def factory(api_key: str) -> FakeAsyncAnthropic:
        return fake_anthropic

    return factory
