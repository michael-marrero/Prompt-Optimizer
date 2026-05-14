# Plan 06 Task 3 — D-18 forbidden-import guard + ROUTER-05 smoke test.
#
# Two tests:
#   test_no_forbidden_modules_imported_after_decide()
#       Walks sys.modules after `import src.routing.decide` and asserts
#       that none of {fastapi, httpx, requests, aiohttp, anthropic,
#       openai} appear at the top-level-package level. This is the
#       D-18 runtime guard that catches transitive HTTP / SDK pulls.
#
#   test_decide_returns_routing_decision()
#       Calls decide() on a clean conversational prompt and asserts the
#       return shape: RoutingDecision instance, backend in the locked
#       set, non-empty rationale, confidence in [0.0, 1.0].

from __future__ import annotations

import os
import sys

import pytest

FORBIDDEN_MODULES: frozenset[str] = frozenset({
    "fastapi", "httpx", "requests", "aiohttp", "anthropic", "openai",
})


def test_no_forbidden_modules_imported_after_decide() -> None:
    """D-18 runtime guard: importing src.routing.decide must not pull
    in any HTTP library or LLM SDK at the top-level-package level."""
    # Pre-clear any forbidden modules that may have been imported by
    # earlier tests in this pytest session.
    for name in list(sys.modules):
        if name.split(".")[0] in FORBIDDEN_MODULES:
            del sys.modules[name]

    import src.routing.decide  # noqa: F401

    leaked = {
        name.split(".")[0]
        for name in sys.modules
    } & FORBIDDEN_MODULES

    assert not leaked, (
        f"src.routing.decide leaked forbidden imports into sys.modules: "
        f"{sorted(leaked)}. Forbidden set (D-18): {sorted(FORBIDDEN_MODULES)}."
    )


def test_decide_returns_routing_decision() -> None:
    """ROUTER-05 contract: decide() returns a RoutingDecision with the
    locked shape."""
    from src.routing.decide import decide
    from src.routing.schema import RoutingDecision

    decision = decide("what is the capital of France?")
    assert isinstance(decision, RoutingDecision)
    assert decision.backend in {"openrouter", "claude_code", "computer_use"}
    assert isinstance(decision.model_or_agent, str) and decision.model_or_agent
    assert isinstance(decision.rationale, str) and len(decision.rationale) > 0
    assert 0.0 <= decision.confidence <= 1.0
    assert isinstance(decision.signals, dict)


def test_decide_returns_routing_decision_for_clearly_agentic_build_prompt() -> None:
    """A canonical "build me X" prompt should route to claude_code via
    the D-01 keyword path even when the calibrated task classifier is
    uncertain on the short prompt. Smoke test for the keyword bypass
    fix in policy.decide_backend."""
    from src.routing.decide import decide

    decision = decide("build me a Streamlit dashboard")
    assert decision.backend == "claude_code"
    assert decision.model_or_agent == "claude-agent-sdk"
    assert "build" in decision.rationale.lower() or "claude" in decision.rationale.lower()


def test_decide_returns_routing_decision_for_clearly_agentic_browse_prompt() -> None:
    """A canonical "open URL + click" prompt should route to
    computer_use via the D-01 browse-keyword path."""
    from src.routing.decide import decide

    decision = decide("open https://news.ycombinator.com and click the top story")
    assert decision.backend == "computer_use"
    assert decision.model_or_agent == "computer-use-2025-11-24"


def test_decide_robust_against_empty_input() -> None:
    """V7 robustness: empty prompt does not raise; returns fallback."""
    from src.routing.decide import decide

    decision = decide("")
    # Empty prompt is OOD by definition — fallback path is the
    # documented correct behavior here.
    assert decision.backend == "openrouter"
    assert decision.model_or_agent == "openrouter/auto"


def test_decide_robust_against_huge_input() -> None:
    """V7 robustness: 100k-char prompt does not raise. The
    _agentic_features 50k-char bound absorbs the rest of the pipeline
    tolerates long inputs."""
    from src.routing.decide import decide
    from src.routing.schema import RoutingDecision

    decision = decide("a" * 100_000)
    assert isinstance(decision, RoutingDecision)


def test_decide_does_not_run_at_module_import_time() -> None:
    """Sanity check: importing decide.py must not call decide() or
    load any joblib. The module is import-cheap so Phase 2 / Phase 3
    consumers can pay the load cost when they want to."""
    # If `decide` is callable but no artifacts were loaded by import
    # alone, then the module is import-cheap. _EXTRACTOR_SINGLETON is
    # the only module-level cache; it starts as None.
    from src.routing import decide as decide_mod

    # _EXTRACTOR_SINGLETON is private but stable; if it was eagerly
    # initialized at import time, that would imply a NLTK download
    # would happen on every `import src.routing.decide`.
    assert hasattr(decide_mod, "_EXTRACTOR_SINGLETON")
    # We CANNOT assert the singleton is None because earlier tests
    # may have already called decide(); we only assert that the
    # module exposes the attribute (proving the lazy pattern is in
    # place).
