# Plan 02-03 Task 1 — SECURE-05 opt-in regression. The
# ComputerUseAdapter constructor MUST raise RuntimeError BEFORE any
# provider client is constructed when COMPUTER_USE_OPT_IN is unset or
# not "1" (CONTEXT specifics line 263 / Pattern 13).
#
# Four invariants:
#   1. Unset env var -> RuntimeError with "COMPUTER_USE_OPT_IN" in msg.
#   2. Env var = "0" -> RuntimeError ("1" is the ONLY enabling value).
#   3. Opt-in check fires BEFORE the api_key check (no api_key + no
#      opt-in -> RuntimeError, NOT AuthenticationError).
#   4. Env var = "1" + factories provided -> construction succeeds.

from __future__ import annotations

import pytest


def test_constructor_raises_without_opt_in(monkeypatch) -> None:
    """SECURE-05 invariant: unset opt-in raises RuntimeError."""

    monkeypatch.delenv("COMPUTER_USE_OPT_IN", raising=False)
    # Import inside the test so monkeypatch can clear the env BEFORE
    # the constructor runs. The constructor reads os.environ at call
    # time, not at module import.
    from apps.api.backends.computer_use.adapter import ComputerUseAdapter

    with pytest.raises(RuntimeError, match="COMPUTER_USE_OPT_IN"):
        ComputerUseAdapter(api_key="fake")


def test_constructor_raises_when_opt_in_is_not_one(monkeypatch) -> None:
    """SECURE-05 invariant: only "1" enables; "0" / "true" / etc. raise."""

    monkeypatch.setenv("COMPUTER_USE_OPT_IN", "0")
    from apps.api.backends.computer_use.adapter import ComputerUseAdapter

    with pytest.raises(RuntimeError, match="COMPUTER_USE_OPT_IN"):
        ComputerUseAdapter(api_key="fake")


def test_opt_in_check_fires_before_api_key_check(monkeypatch) -> None:
    """SECURE-05 invariant: opt-in is checked BEFORE the api_key check.

    CONTEXT specifics line 263: "Constructor raises RuntimeError if env
    var != '1' BEFORE any provider client is constructed AND BEFORE the
    api_key check." With no opt-in AND no api_key, the opt-in
    RuntimeError must surface — NOT the AuthenticationError that would
    fire if the api_key check ran first.
    """

    monkeypatch.delenv("COMPUTER_USE_OPT_IN", raising=False)
    from apps.api.backends.computer_use.adapter import ComputerUseAdapter

    with pytest.raises(RuntimeError, match="COMPUTER_USE_OPT_IN"):
        # api_key="" would normally raise AuthenticationError if the
        # api_key check ran first — but the opt-in check is FIRST, so
        # we get RuntimeError instead.
        ComputerUseAdapter(api_key="")


def test_opt_in_one_allows_construction(monkeypatch) -> None:
    """Smoke: with COMPUTER_USE_OPT_IN=1 and factories provided, the
    constructor returns successfully — opt-in is the only blocker."""

    monkeypatch.setenv("COMPUTER_USE_OPT_IN", "1")
    # Defensively set ANTHROPIC_API_KEY — not strictly required when
    # api_key= is supplied to the constructor, but the env var is the
    # most common production source so let it be set.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")

    from apps.api.backends.computer_use.adapter import ComputerUseAdapter

    # No exception expected — the factories bypass the real
    # AsyncAnthropic / PlaywrightScreen construction so we don't need
    # a real key or a real browser.
    adapter = ComputerUseAdapter(
        api_key="fake",
        client_factory=lambda api_key: object(),
        screen_factory=lambda **kw: object(),
    )
    assert adapter is not None
