# Plan 06 — ROUTER-05 / D-18 — smoke test that decide() is callable and the
# routing brain imports no HTTP / provider-SDK modules.
#
# Tests to be implemented in Plan 06:
#   - test_decide_returns_routing_decision()           # ROUTER-05 shape contract
#   - test_no_forbidden_modules_imported_after_decide  # D-18 import-graph guard
#       forbidden set = {"fastapi", "httpx", "requests", "aiohttp", "anthropic", "openai"}

import pytest


def test_decide_returns_routing_decision_placeholder():
    pytest.skip("Wave 3 — implemented in Plan 06 (ROUTER-05)")


def test_no_forbidden_modules_imported_after_decide_placeholder():
    pytest.skip("Wave 3 — implemented in Plan 06 (D-18 forbidden-import guard)")
