"""OpenRouter ``_default_client_factory`` — max_retries=0 lock (RELI-01).

VALIDATION.md / 09-02 Task 1: the OpenRouter ``AsyncOpenAI`` client MUST
be constructed with ``max_retries=0`` so the application-level RELI-01
retry loop in ``turn.py`` is the SOLE retry authority. The openai SDK
default is ``max_retries=2``; left unset, those SDK retries silently
stack with the D-02 3-attempt loop → up to ~9 upstream calls against a
hard-down provider (RESEARCH Pitfall 1 — the load-bearing landmine for
the whole phase).

``-k "openrouter and (max_retries or client_factory)"``.
"""

from __future__ import annotations

from openai import AsyncOpenAI

from apps.api.backends.openrouter.adapter import (
    OPENROUTER_BASE_URL,
    OpenRouterAdapter,
)


def test_default_client_factory_sets_max_retries_zero() -> None:
    """The real client factory forces ``max_retries=0`` (Pitfall 1 fix).

    Builds the genuine ``AsyncOpenAI`` via ``_default_client_factory``
    (no network — construction only) and asserts the SDK retry budget is
    pinned to zero. Without this, ``stream()``'s single round-trip would
    fan out into the SDK's own exponential-backoff retries beneath the
    app loop's 3 attempts.
    """

    client = OpenRouterAdapter._default_client_factory("sk-test-key")

    assert isinstance(client, AsyncOpenAI)
    assert client.max_retries == 0, (
        "OpenRouter AsyncOpenAI must be built with max_retries=0 so the "
        "app-level RELI-01 retry loop is the sole retry authority "
        "(RESEARCH Pitfall 1 — no SDK stacking)"
    )
    # Sanity: the attribution base_url is still wired (regression guard
    # that the constructor edit did not drop the existing kwargs).
    assert str(client.base_url).rstrip("/") == OPENROUTER_BASE_URL


def test_adapter_uses_zero_retry_client_by_default() -> None:
    """An adapter built without a ``client_factory`` gets a 0-retry client.

    End-to-end of the default path: ``OpenRouterAdapter(api_key=...)`` with
    no injected factory must construct an ``AsyncOpenAI`` whose
    ``max_retries`` is 0 (the adapter stores it on ``self._client``).
    """

    adapter = OpenRouterAdapter(api_key="sk-test-key")

    assert adapter._client.max_retries == 0, (
        "the default (non-injected) OpenRouter client must carry "
        "max_retries=0"
    )
