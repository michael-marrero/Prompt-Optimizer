"""Package marker for ``apps.api.tests``.

Phase 3 tests live here (test_smoke.py is the Wave 0 sanity test;
Waves 1-6 author the integration suites). Producer modules from
Waves 1-6 are imported lazily inside fixture bodies in
``conftest.py`` so the test infrastructure collects in Wave 0
BEFORE the Wave 1-6 modules land (B3 pattern from Phase 2 P00).
"""
